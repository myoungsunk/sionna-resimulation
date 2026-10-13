"""D12: matched LoS FFD *direct* observation model for each window method.

Do NOT reuse the FP LUT for W1/W2/W3/W4.  The model synthesizes LoS H
from frozen calibrated FFD banks at the estimated pose and the same receiver.
Finite difference derivatives are of the same on-demand observation. No truth
enters the online measurement model; truth is offline for scoring only.

This direct model is a correctness reference; a 4-D angle+distance LUT may
later accelerate it but cannot be assumed identical to original angular LUT.
"""
from __future__ import annotations
import argparse, json, math
from functools import lru_cache
from collections import defaultdict
from pathlib import Path
import numpy as np
from d10_d14_core import (EarlyWindowConfig,METHODS,extract_cir_methods,
  hann_pulse_template,read_table,validate_stage,write_rows,
  stage_finish,new_output,save_json,file_sha)
from d6_d9_common import (OBS,B_OLD,RR,RS,REPO,check_inputs,checked_path,
  spectrum,original_lut,wrap)
from ekf3 import EKF3, archived_direct_s_model
from run_d0_d4 import (load_p2_one_step,verify_p2_artifact_integrity)
from run_d5_regimes import timelines


def frozen_banks():
    """Load FROM main repository, not archived relative rf_store. LFS files needed."""
    from qclean_uwb.drivesim.pattern_apply import Bank
    manifest=REPO/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json'
    if not manifest.is_file():raise FileNotFoundError(manifest)
    j=json.loads(manifest.read_text(encoding='utf-8'))
    banks=[];hashes={}
    for port in ('LP_plus45','LP_minus45'):
        path=REPO/(port+'_bank.npz')
        if not path.is_file():raise FileNotFoundError('Need git lfs pull for '+str(path))
        h=file_sha(path)
        if h!=j['npz_sha256'][path.name]:
            raise RuntimeError('FFD BANK sha mismatch / LFS pointer: '+str(path))
        with np.load(path,allow_pickle=False) as z:
            banks.append(Bank({k:z[k] for k in z.files}))
        hashes[path.name]=h
    if not np.array_equal(banks[0].freqs_hz,banks[1].freqs_hz):
        raise RuntimeError('FFD RX bank frequency mismatch')
    return banks,{'bank_manifest_sha256':file_sha(manifest),'bank_sha256':hashes}


class DirectWindowModel:
    """LoS observation h_W(x,y,yaw) with common RX window, dynamic distance.

    FFD LoS synthesis receives ONLY estimated x, y, yaw (and known geometry).
    Uses same TX0, same 4N Hann receiver as frozen Full/LoS H.
    """
    def __init__(self, case, banks, method, cfg=None, *, diff_xy=.003,diff_psi=.0005):
        if method not in METHODS:raise ValueError('Unknown window method')
        self.case=case;self.banks=banks;self.method=method
        self.cfg=(cfg or EarlyWindowConfig()).validate()
        self.diff_xy=float(diff_xy);self.diff_psi=float(diff_psi)
        if self.diff_xy<=0 or self.diff_psi<=0:raise ValueError('Invalid derivative steps')
        self.freqs=np.asarray(banks[0].freqs_hz)
        self.template=hann_pulse_template(len(self.freqs),4*len(self.freqs))

    def value(self,x):
        state=np.asarray(x,float)
        if state.shape!=(3,) or not np.isfinite(state).all():
            raise ValueError('LoS model input must be finite 3-state estimate')
        return self._value(tuple(float(v) for v in state))

    @lru_cache(maxsize=4096)
    def _value(self, state_tuple):
        from qclean_uwb.drivesim.hs_lut import los_h
        state=np.asarray(state_tuple,float)
        a=np.asarray(self.case['anchor'],float)
        vec=np.array([state[0]-a[0],state[1]-a[1],self.case['robot_z_m']-a[2]])
        dist=float(np.linalg.norm(vec))
        if dist<.5:raise ValueError('Near-zero direct LoS range unsupported')
        H=los_h(self.banks,vec/dist,math.degrees(state[2])+float(self.case['mount_deg']),dist_m=dist)
        if H.shape!=(len(self.freqs),2,2):raise RuntimeError('Direct LoS FFD H shape mismatch')
        cir=OBS.cir_batch(np.asarray(H[None,...,0]))
        fp=OBS.first_path_batch(cir,float(self.freqs[1]-self.freqs[0]))
        vals,_=extract_cir_methods(cir[0],fp_index=int(fp['index'][0]),
                                   config=self.cfg,template=self.template)
        v=float(vals[self.method])
        if not math.isfinite(v):raise RuntimeError('Nonfinite LoS s model')
        return v

    def __call__(self,x):
        s=self.value(x);xx=np.asarray(x,float).copy()
        jac=np.empty(3,float)
        for i,h in enumerate((self.diff_xy,self.diff_xy,self.diff_psi)):
            a=xx.copy();b=xx.copy();a[i]+=h;b[i]-=h
            jac[i]=(self.value(a)-self.value(b))/(2*h)
        if not np.isfinite(jac).all():raise RuntimeError('LoS Jacobian nonfinite')
        return s,jac


def online_d11(d11):
    validate_stage(d11,'D11',['D11_ONLINE_WINDOW_S.csv','D11_ORACLE_PAIR_EVAL.csv','D11_CASE_SUMMARY.csv'])
    data=read_table(Path(d11)/'D11_ONLINE_WINDOW_S.csv')
    bykey={}
    for r in data:
        key=(r['case'],r['channel'],int(r['sample_index']),r['method'])
        if key in bykey:raise RuntimeError('Duplicate D11 sample')
        bykey[key]=r
    return bykey


def compare_one_step(x,P,s_obs,r_raw,model,case,arm):
    f=EKF3(x,np.asarray(P,float))
    if arm=='A':
        step=f.update_heading(s_obs,RS,s_model=model)
    elif arm=='C':
        step=f.update_joint(s_obs,r_raw,RS,RR,0.,s_model=model,
            anchor_xyz_m=tuple(case['anchor']),tag_height_m=float(case['robot_z_m']),
            range_offset_m=B_OLD)
    else:raise ValueError('Only A or C in D12')
    return f.x,f.P,step


def assemble_gates(rows, *, config, full_exhaustive):
    groups=defaultdict(list)
    for r in rows:
        groups[(r['route'],r['method'])].append(r)
        groups[('ALL',r['method'])].append(r)
    summaries=[]
    for (group,method),rec in sorted(groups.items()):
        full=[x for x in rec if x['channel']=='full']
        los=[x for x in rec if x['channel']=='los']
        if len(full)!=len(los):raise RuntimeError('D12 no paired channel scoring')
        mean=lambda v:float(np.mean(np.asarray(v,float))) if v else None
        sums=lambda v:float(np.sqrt(np.mean(np.square(v)))) if v else None
        summaries.append(dict(group=group,method=method,n_full=len(full),
           rms_full_minus_los_s=sums([r['full_minus_los_s'] for r in full]),
           rms_los_model_error=sums([r['los_model_error_s'] for r in los]),
           mean_abs_hpsi=mean([abs(r['hpsi']) for r in los]),
           fraction_stable_hpsi=mean([r['hpsi_stable'] for r in los]),
           a_heading_rmse_full_deg=sums([r['heading_error_deg'] for r in full if r['arm']=='A']),
           c_heading_rmse_full_deg=sums([r['heading_error_deg'] for r in full if r['arm']=='C'])))
    by={(r['group'],r['method']):r for r in summaries}
    gates=[]
    for method in METHODS:
        base=by.get(('ALL','W0_FP'));new=by.get(('ALL',method))
        if base is None or new is None:raise RuntimeError('Missing D12 W0 baseline')
        def ratio(a,b):return float(a/max(b,1e-15))
        improve=ratio(new['rms_full_minus_los_s'],base['rms_full_minus_los_s'])
        los=ratio(new['rms_los_model_error'],base['rms_los_model_error'])
        sensitivity=ratio(new['mean_abs_hpsi'],base['mean_abs_hpsi'])
        stable=float(new['fraction_stable_hpsi'])
        route_ratios=[]
        for route in ('R2','R4','R5'):
            x=by.get((route,method));y=by.get((route,'W0_FP'))
            if x and y:route_ratios.append(ratio(x['rms_full_minus_los_s'],y['rms_full_minus_los_s']))
        heading=ratio(new['c_heading_rmse_full_deg'],base['c_heading_rmse_full_deg'])
        # Exploratory, preregistered thresholds, not scientific validation.
        passed=(method!='W0_FP' and improve<=.95 and len(route_ratios)==3 and
            sum(x<1 for x in route_ratios)>=2 and max(route_ratios)<=1.05 and
            los<=1.25 and sensitivity>=.80 and stable>=.95 and heading<=1.05)
        gates.append(dict(method=method,scope='ONE_FROZEN_SCENE',
           status=('EXPLORATORY_GATE_PASS' if passed and full_exhaustive else
                   'SMOKE_ONLY' if not full_exhaustive else 'EXPLORATORY_GATE_FAIL'),
           full_minus_los_rms_ratio=improve,los_model_rms_ratio=los,
           mean_heading_sensitivity_ratio=sensitivity,
           fraction_stable_hpsi=stable,
           full_joint_heading_rmse_ratio=heading,
           route_full_los_rms_ratios=route_ratios,
           thresholds={'max_full_minus_los_ratio':.95,'minimum_route_wins':2,
            'max_worst_route_ratio':1.05,'max_los_model_rms_ratio':1.25,
            'minimum_hpsi_ratio':.8,'minimum_stable_hpsi_fraction':.95,
            'max_joint_heading_rmse_ratio':1.05},
           scientific_PASS=False))
    return summaries,gates


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--d11',type=Path,required=True)
    ap.add_argument('--p2-dir',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--seed',type=int,default=0)
    ap.add_argument('--cases',nargs='*',default=[])
    ap.add_argument('--stride',type=int,default=1)
    ap.add_argument('--max-eval-per-case',type=int,default=0)
    ap.add_argument('--co-port',choices=['auto','rx1','rx2'],default='auto')
    args=ap.parse_args()
    if args.stride<1 or args.max_eval_per_case<0:raise ValueError('Bad sample controls')
    p0=check_inputs();obs=online_d11(args.d11)
    meta=json.loads((args.d11/'D11_MANIFEST.json').read_text('utf-8'))
    if meta['config']['co_port']!=args.co_port:raise RuntimeError('D11/D12 co-port differs')
    config=EarlyWindowConfig(co_port=args.co_port,
        max_taps=meta['config']['max_taps'],max_search_taps=meta['config']['max_search_taps'],
        growth_ratio=meta['config']['growth_ratio'],
        excess_over_co_fp=meta['config']['excess_over_co_fp'],
        rise_factor=meta['config']['rise_factor'],consecutive=meta['config']['consecutive'],
        noise_floor_power=meta['config']['noise_floor_power']).validate()
    verify_p2_artifact_integrity(args.p2_dir,args.seed)
    cases={q['id']:q for q in p0['cases']}
    selected=args.cases or list(cases)
    if any(x not in cases for x in selected) or len(set(selected))!=len(selected):
        raise ValueError('Invalid case list')
    banks,bank_evidence=frozen_banks();lut=original_lut(p0)
    tdata=timelines(p0);result=[]
    for name in selected:
        case=cases[name];t,truth,pids=tdata[case['route']]
        models={method:DirectWindowModel(case,banks,method,config)
                for method in METHODS if method!='W0_FP'}
        models['W0_FP']=archived_direct_s_model(lut,
             anchor_xyz_m=tuple(case['anchor']),tag_height_m=case['robot_z_m'],
             mount_deg=case['mount_deg'])
        full_original=load_p2_one_step(args.p2_dir,name,'full',args.seed)
        los_original=load_p2_one_step(args.p2_dir,name,'los',args.seed)
        ids=[int(i) for i in np.flatnonzero(t>=30)[::args.stride]]
        if args.max_eval_per_case:ids=ids[:args.max_eval_per_case]
        for idx in ids:
            if (int(full_original['pose_id'][idx])!=int(pids[idx]) or
                int(los_original['pose_id'][idx])!=int(pids[idx])):
                raise RuntimeError('P2 / D11 pose alignment mismatch')
            for method,model in models.items():
                lo=obs.get((name,'los',idx,method));fu=obs.get((name,'full',idx,method))
                if lo is None or fu is None:raise RuntimeError('D11 method/case incomplete')
                h,jac=model(truth[idx]) # strictly offline: no truth in online filter model
                # Adaptive discrete window cutoffs can make h_W nonsmooth;
                # test centered yaw derivative against a second step size.
                delta=float(getattr(model,'diff_psi',.0005))
                yp=np.asarray(truth[idx],float).copy();ym=yp.copy()
                yp[2]+=delta/2;ym[2]-=delta/2
                eval_h=lambda x: model.value(x) if hasattr(model,'value') else model(x)[0]
                hpsi_half=(float(eval_h(yp))-float(eval_h(ym)))/delta
                grad_relative_error=abs(float(jac[2])-hpsi_half)/max(.01,abs(float(jac[2])),abs(hpsi_half))
                gradient_stable=int(grad_relative_error<=.25)
                lo_err=float(lo['s_value'])-float(h)
                full_delta=float(fu['s_value'])-float(lo['s_value'])
                for ch,row,p2 in [('los',lo,los_original),('full',fu,full_original)]:
                    if float(row['t_s'])!=float(p2['t_s'][idx]):
                        raise RuntimeError('D11/P2 time mismatch')
                    x=np.asarray(p2['xminus'][idx],float)
                    P=np.asarray(p2['Pminus'][idx],float)
                    for arm,arm_index in (('A',0),('C',2)):
                        post,Ppost,step=compare_one_step(x,P,float(row['s_value']),
                            float(row['frozen_range_m']),model,case,arm)
                        if method=='W0_FP':
                            if (np.max(abs(post-p2['xplus'][idx,arm_index]))>1e-8 or
                                np.max(abs(Ppost-p2['Pplus'][idx,arm_index]))>1e-8 or
                                step.status!=str(p2['status'][idx,arm_index])):
                                raise RuntimeError('D12 W0 != frozen P2 same-prior baseline')
                        e=wrap(float(post[2]-truth[idx,2]))
                        result.append(dict(case=name,route=case['route'],channel=ch,
                          sample_index=idx,pose_id=int(pids[idx]),t_s=float(t[idx]),
                          arm=arm,method=method,
                          full_minus_los_s=full_delta,
                          los_model_error_s=lo_err,hpsi=float(jac[2]),
                          hpsi_relative_step_error=float(grad_relative_error),
                          hpsi_stable=gradient_stable,
                          heading_error_deg=math.degrees(e),
                          xy_error_m=float(np.linalg.norm(post[:2]-truth[idx,:2])),
                          status=step.status,nis_pre_gate=step.NIS))
    summaries,gates=assemble_gates(result,config=config,
        full_exhaustive=(len(selected)==7 and args.stride==1 and args.max_eval_per_case==0))
    out=new_output(args.out)
    x=out/'D12_WINDOW_ONE_STEP.csv';y=out/'D12_WINDOW_SUMMARY.csv';z=out/'D12_WINDOW_GATES.json'
    write_rows(x,result);write_rows(y,summaries)
    save_json(z,{'stage':'D12','window_configuration':meta['config'],
       'gates':gates,'scientific_PASS':False,'full_rf_refit_performed':False})
    stage_finish(out,'D12',[x,y,z],config=vars(args),evidence={
       'D11_online_sha256':file_sha(args.d11/'D11_ONLINE_WINDOW_S.csv'),
       'P2_seed':args.seed,**bank_evidence},warnings=[
       'Direct reference LoS FFD observation computed from estimated state; not a prebuilt 4D LUT',
       'Original FP-LUT retained ONLY for W0 frozen baseline, W1/W2/W3/W4 receive matching direct LoS model',
       'Ground-truth LoS model evaluation used ONLY for scoring and sensitivity',
       'Finite-difference yaw Jacobian evaluated twice to flag nonsmooth adaptive tap/window decisions',
       'P2 same-prior one-step only, no recursive EKF proof',
       'Gate is exploratory and requires ALL 7 cases, stride=1 and no per-case truncation'])
    print('D12_EXPLORATORY_DONE',str(out))
if __name__=='__main__':main()
