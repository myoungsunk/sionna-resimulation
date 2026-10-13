"""D15 gated dense single-tap recursive EKF comparison; fixed R0 and original motion."""
from __future__ import annotations
import argparse, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np
from d15_dense_core import (EarlyWindowConfig,read_table,validate_stage,
  new_output,write_rows,save_json,stage_finish,file_sha)
from d15_dense_los_validation import (DirectWindowModel,frozen_banks,online_d11)
from d13_d14_filter_core import (run_cell,verify_frozen_d5,ARCHIVED_D5)
from d6_d9_common import (REPO,B_OLD,check_inputs,spectrum,original_lut)
from d6_bias_observability import generate_paired
from ekf3 import archived_direct_s_model
from run_d5_regimes import timelines

FUSION={'F0_ORIGINAL':('W0_FP','EKF3'), 'F1_DENSE_EKF':('DENSE_SINGLE','EKF3')}


def gate_contract(d12, method='DENSE_SINGLE'):
    validate_stage(d12,'D12',['D12_WINDOW_ONE_STEP.csv','D12_WINDOW_SUMMARY.csv','D12_WINDOW_GATES.json'])
    report=json.loads((Path(d12)/'D12_WINDOW_GATES.json').read_text('utf-8'))
    cells=[v for v in report['gates'] if v['method']==method]
    if len(cells)!=1:raise RuntimeError('D12 missing requested window method gate')
    return cells[0],report


def d11_reference_settings(d11):
    receipt=validate_stage(d11,'D11',['D11_ONLINE_WINDOW_S.csv','D11_ORACLE_PAIR_EVAL.csv','D11_CASE_SUMMARY.csv'])
    a=receipt['config']
    return EarlyWindowConfig(co_port=a['co_port'],max_taps=a['max_taps'],
       max_search_taps=a['max_search_taps'],growth_ratio=a['growth_ratio'],
       excess_over_co_fp=a['excess_over_co_fp'],rise_factor=a['rise_factor'],
       consecutive=a['consecutive'],noise_floor_power=a['noise_floor_power']).validate(),a


def primary_window_result(d11,selection):
    pairs=read_table(Path(d11)/'D11_ORACLE_PAIR_EVAL.csv')
    by=defaultdict(list)
    for r in pairs:
        if r['method'] in ('W0_FP',selection):
            by[(r['route'],r['method'])].append(float(r['delta_s']))
            by[('ALL',r['method'])].append(float(r['delta_s']))
    result=[]
    for group in ('ALL','R2','R4','R5'):
        if not by.get((group,'W0_FP')) or not by.get((group,selection)):
            raise RuntimeError('No paired D11 W0/W2 scores '+group)
        a=np.asarray(by[(group,'W0_FP')]);b=np.asarray(by[(group,selection)])
        if a.shape!=b.shape:raise RuntimeError('D11 W0/W2 paired subset mismatch')
        r0=float(np.sqrt(np.mean(a*a)));r1=float(np.sqrt(np.mean(b*b)))
        result.append(dict(group=group,n=len(a),
            w0_full_minus_los_rms=r0,window_full_minus_los_rms=r1,
            ratio_window_over_w0=r1/max(r0,1e-15),
            primary_s_difference_improved=bool(r1<r0)))
    return result


def compare_variants(rows):
    baseline={(r['case'],r['channel'],r['condition'],r['level'],r['seed'],
               r['sigma_heading_deg'],r['bias_mode'],r['arm']):r for r in rows
              if r['fusion_arm']=='F0_ORIGINAL'}
    out=[]
    for r in rows:
        if r['fusion_arm']=='F0_ORIGINAL':continue
        k=(r['case'],r['channel'],r['condition'],r['level'],r['seed'],
           r['sigma_heading_deg'],r['bias_mode'],r['arm'])
        b=baseline.get(k)
        if b is None:raise RuntimeError('D14 incomplete paired original F0 control')
        out.append(dict(case=r['case'],channel=r['channel'],seed=r['seed'],
           level=r['level'],sigma_heading_deg=r['sigma_heading_deg'],
           bias_mode=r['bias_mode'],arm=r['arm'],fusion_arm=r['fusion_arm'],
           delta_heading_rmse_deg=float(r['heading_rmse_deg']-b['heading_rmse_deg']),
           delta_xy_rmse_m=float(r['xy_rmse_m']-b['xy_rmse_m']),
           delta_pose95=float(r['pose95']-b['pose95']),
           delta_mean_pose_nees=float(r['mean_pose_NEES']-b['mean_pose_NEES']),
           relative_heading_rmse=float(r['heading_rmse_deg']/max(1e-15,b['heading_rmse_deg'])),
           comparison_same_motion_truth_rf=True))
    return out


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--d11',type=Path,required=True)
    ap.add_argument('--d12',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--cases',nargs='*',default=[])
    ap.add_argument('--channels',choices=['los','full'],nargs='+',default=['los','full'])
    ap.add_argument('--seeds',type=int,nargs='+',default=[0])
    ap.add_argument('--levels',type=int,nargs='+',default=[1])
    ap.add_argument('--heading-std-deg',type=float,nargs='+',default=[5.])
    ap.add_argument('--bias-modes',choices=['off','on'],nargs='+',default=['off'])
    ap.add_argument('--methods',choices=list(FUSION),nargs='+',default=list(FUSION))
    ap.add_argument('--save-trace',action='store_true')
    ap.add_argument('--d5-reference',type=Path,default=REPO/ARCHIVED_D5)
    args=ap.parse_args()
    if any(len(set(x))!=len(x) for x in (args.cases,args.seeds,args.levels,
        args.heading_std_deg,args.bias_modes,args.methods,args.channels)):
        raise ValueError('Duplicated D14 design controls')
    if 'F0_ORIGINAL' not in args.methods:
        raise RuntimeError('D14 must include F0 for a paired comparison')
    if any(x<=0 for x in args.heading_std_deg) or any(x not in (0,1,2) for x in args.levels):
        raise ValueError('Invalid D14 uncertainty grid')
    cfg,d11params=d11_reference_settings(args.d11)
    gate,report=gate_contract(args.d12)
    d12receipt=json.loads((args.d12/'D12_MANIFEST.json').read_text('utf-8'))
    for name in ('d15_dense_core.py','d15_dense_los_validation.py','d15_dense_observations.py','d13_d14_filter_core.py'):
        if d12receipt['script_sha256'][name]!=file_sha(Path(__file__).parent/name):
            raise RuntimeError('Gate/source mismatch: '+name)
    if d12receipt['input_evidence']['D11_online_sha256']!=file_sha(args.d11/'D11_ONLINE_WINDOW_S.csv'):
        raise RuntimeError('D12 gate was scored using different D11 receiver observations')
    if report['window_configuration']!=d11params:
        raise RuntimeError('D11/D12 adaptive-window detector configuration differs')
    window_required=any(FUSION[m][0]!='W0_FP' for m in args.methods)
    if window_required and gate['status']!='EXPLORATORY_GATE_PASS':
        raise RuntimeError('D12 window gate FAILED or SMOKE_ONLY; fusion prohibited')
    p0=check_inputs();cases={q['id']:q for q in p0['cases']}
    requested=args.cases or list(cases)
    if any(x not in cases for x in requested):raise ValueError('Unknown D14 case')
    obs=online_d11(args.d11);tdata=timelines(p0)
    banks,bank_hash=frozen_banks() if window_required else (None,{})
    if window_required:
        for label in ('bank_manifest_sha256','bank_sha256'):
            if bank_hash[label]!=d12receipt['input_evidence'][label]:
                raise RuntimeError('D12/D14 direct FFD bank source differs: '+label)
    lut=original_lut(p0)
    metrics=[];trace=[]
    for name in requested:
        case=cases[name];t,truth,pids=tdata[case['route']]
        models={'W0_FP':archived_direct_s_model(lut,
           anchor_xyz_m=tuple(case['anchor']),tag_height_m=case['robot_z_m'],
           mount_deg=case['mount_deg'])}
        if window_required:
            models['DENSE_SINGLE']=DirectWindowModel(case,banks,'DENSE_SINGLE',cfg)
        for ch in args.channels:
            z={}
            for method in set(FUSION[m][0] for m in args.methods):
                rows=[obs.get((name,ch,k,method)) for k in range(len(t))]
                if any(v is None for v in rows):
                    raise RuntimeError('D11 missing online sequence '+str((name,ch,method)))
                z[method]=np.asarray([float(q['s_value']) for q in rows])
            reference=[obs[(name,ch,k,'W0_FP')] for k in range(len(t))]
            r=np.asarray([float(q['frozen_range_m']) for q in reference])-float(B_OLD)
            for level in args.levels:
                for seed in args.seeds:
                    m0,mb,_=generate_paired(t,truth,level,seed)
                    for bm in args.bias_modes:
                        motion=m0 if bm=='off' else mb
                        for sigma in args.heading_std_deg:
                            for arm in ('D0','A','B','C'):
                                for fkey in args.methods:
                                    method,filter_name=FUSION[fkey]
                                    result,samples=run_cell(case,t,truth,motion,z[method],r,
                                      models[method],channel=ch,seed=seed,level=level,
                                      bias_mode=bm,sigma_heading_deg=sigma,arm=arm,
                                      variant=filter_name,save_trace=args.save_trace)
                                    result['fusion_arm']=fkey;result['window_method']=method
                                    for row in samples:
                                        row['fusion_arm']=fkey;row['window_method']=method
                                    metrics.append(result);trace.extend(samples)
    b=[r for r in metrics if r['fusion_arm']=='F0_ORIGINAL' and r['sigma_heading_deg']==5 and r['bias_mode']=='off']
    parity=(verify_frozen_d5(b,args.d5_reference) if b else
        {'status':'NOT_RUN_NO_REFERENCED_5DEG_EKF3_CONTROL'})
    deltas=compare_variants(metrics)
    primary=primary_window_result(args.d11,'DENSE_SINGLE')
    out=new_output(args.out)
    x=out/'D14_RECURSIVE_ABLATION.csv';y=out/'D14_DELTA_VS_F0.csv'
    z=out/'D14_PRIMARY_FULL_LOS_S_RMS.csv';q=out/'D14_BASELINE_PARITY.json'
    write_rows(x,metrics);write_rows(z,primary);save_json(q,parity)
    files=[x,z,q]
    if deltas:write_rows(y,deltas);files.append(y)
    if trace:
        tpath=out/'D14_RECURSIVE_SAMPLE_TRACE.csv'
        write_rows(tpath,trace);files.append(tpath)
    stage_finish(out,'D14',files,config=vars(args),evidence={
       'D12_gate':gate,'D13_original_F0_parity':parity,
       'D11_online_sha256':file_sha(args.d11/'D11_ONLINE_WINDOW_S.csv'),**bank_hash},
       warnings=['Dense single-tap with matching direct LoS model; original R0 and Rsr=0',
                 'One frozen scene, seed 0 is development evidence; scientific_PASS=false'])
    print('D14_EXPLORATORY_DONE',str(out))
if __name__=='__main__':main()
