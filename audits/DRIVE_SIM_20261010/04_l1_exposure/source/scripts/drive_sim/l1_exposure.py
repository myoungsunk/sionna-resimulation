"""Frozen legacy replay instrumentation and offline L1 exposure analysis only."""
import sys, json, hashlib, math, time, subprocess, itertools
from pathlib import Path
from dataclasses import asdict
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'src'))
import validation_repair as V
from qclean_uwb.drivesim import hs_lut as L, observation as O
from qclean_uwb.drivesim.rf_store import load_banks
SOURCE=Path('D:/SLAM_bot/artifacts/DRIVE_SIM_VALIDATION_REPAIR_20261008_01a11a0b/checkout')
OLD=SOURCE/'results/DRIVE_SIM_20261007/VALIDATION_REPAIR_20261008'
MET=OLD/'METRICS_INDEPENDENT_CHECK_20261008'
L1=Path('D:/SLAM_bot/artifacts/DRIVE_SIM_SENSOR_V2_REVIEW_20261008_01a11a7b/checkout/results/DRIVE_SIM_L1_STAGE3_20261008')
OUT=ROOT/'results/DRIVE_SIM_L1_EXPOSURE_20261008'
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(n,x):
    (OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False,default=lambda x:x.item() if isinstance(x,np.generic) else x.tolist()),encoding='utf-8')
def frozen_table():
    d=read(OLD/'STEP5_CALIBRATION.json')['tables']['distance']
    return V.ResidualTable((5.,10.),(15.,30.),d['scalar_rms'],np.array([np.nan if v is None else v for v in d['distance_rms']]),np.array([[np.nan if v is None else v for v in row] for row in d['joint_rms']]),tuple(d['distance_support']),'distance')
def prepare():
    OUT.mkdir(parents=True,exist_ok=False)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip();assert head==V.REV
    src=[p for p in (ROOT/'src/qclean_uwb/drivesim').glob('*.py')]+[ROOT/'scripts/drive_sim/validation_repair.py',ROOT/'scripts/drive_sim/independent_metrics_check.py',ROOT/'src/qclean_uwb/scenarios/corridor.py']
    original_plan=read(MET/'PLAN.json')
    for name in ('src/qclean_uwb/drivesim/filters.py','src/qclean_uwb/drivesim/uncertainty.py','scripts/drive_sim/validation_repair.py'):
        p=SOURCE/name;assert sha(p)==original_plan['hashes'][str(p)]
        assert sha(ROOT/name)==sha(p)
    inherited={str(p):sha(p) for folder in ('src','scripts','tests') for p in (SOURCE/folder).rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    files=[V.RAW/x for x in ('H_R2_aA_m0.npy','freqs_hz.npy','hs_lut_2deg.npy','hs_lut_meta.json')]+[OLD/x for x in ('STEP5_CALIBRATION.json','STEP6_JOINT_EVALUATION.json','INPUT_MANIFEST.json')]+[MET/x for x in ('PLAN.json','RESULT.json','OUTPUT_MANIFEST.json','INSTRUMENTATION_AMENDMENT.json')]+[MET/f'distance_{s}.npz' for s in range(5000,5024)]+[L1/x for x in ('PLAN.json','RESULT.json','OUTPUT_MANIFEST.json','ALL_POINTS.json','RAW_CHANNEL_CIR.npz','FINAL_REPORT_KO.md')]+[L1/'inputs'/x for x in ('LP_plus45_bank.npz','LP_minus45_bank.npz','hs_lut_2deg.npy','hs_lut_meta.json','BANK_MANIFEST.json')]+[ROOT/'results/DRIVE_SIM_20261007/S1/routes'/x for x in ('timeline_R2_Tnone.csv','rf_poses_R2.json')]
    hashes={str(p):sha(p) for p in files}
    old_result=read(MET/'RESULT.json')
    for s in range(5000,5024):assert hashes[str(MET/f'distance_{s}.npz')]==old_result['npz_hashes'][f'distance_{s}.npz']
    l1man=read(L1/'OUTPUT_MANIFEST.json')
    for p in files:
        if p.is_relative_to(L1) and p.name!='OUTPUT_MANIFEST.json':assert hashes[str(p)]==l1man['files'][str(p.relative_to(L1))]['sha256']
    cfg=V.cfg0(frozen_table().scalar_rms);cfg.s_residual_table=frozen_table();snap=asdict(cfg)
    snap['s_residual_table']=read(OLD/'STEP5_CALIBRATION.json')['tables']['distance']
    write('PLAN.json',dict(revision=head,branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),origin=subprocess.check_output(['git','remote','-v'],cwd=ROOT,text=True),
        original_execution_source_hashes={str(p):sha(p) for p in src},input_hashes=hashes,source_preservation=inherited,
        source_checkout=str(SOURCE),l1_checkout=str(L1),seeds=list(range(5000,5024)),condition='R2-A-m0/P0 distance legacy EKF direct-s, NOT sensor-v2',config=snap,
        mask='Frozen STEP5 evaluation_indices, 392/979; all-time and held-out reported separately',
        reason_for_replay='Saved post-update estimate/covariance/gate exist, pre-s state/actual LUT queries/R/innovation not saved',
        matching=dict(array_atol=1e-10,array_rtol=1e-10,metric_atol=1e-8,metric_rtol=1e-10,require_gate_identical=True),
        offline=dict(distance_m=10,tx=0,threshold_s_error=.01,polar_cell='0<=theta<2 degrees',tap_risk='8 vertices and query index mixed; risk does not imply error',
            fixed_tap='query index for vertex ratio decomposition only',derivative='central +/-0.01 degree body heading; report per radian, mark tap changes',
            derivative_selection='each seed top 2 polar, top 2 mixed, top 2 >.01, top 2 same-index by |L1 error|, plus time quartiles; dedupe; max 12/seed',
            max_queries=23472,max_new_vertices=20000,max_derivative_points=576,reuse_saved_l1_vertices=True,
            no_new_RF=True,no_model_change=True,no_truth_to_estimator=True,association_unit='seed; descriptive, no causal fraction'),
        runtime=dict(python=sys.version,numpy=np.__version__),script_sha256=sha(__file__)))
    (OUT/'GIT_STATUS_BEFORE.txt').write_bytes(subprocess.check_output(['git','status','--short'],cwd=ROOT))
    print('PREPARED INPUTS',len(hashes),'CONFIG',json.dumps(snap,default=lambda x:list(x)))

class RecordingLut(L.HsLut):
    callback=None
    def __call__(self,*a,**kw):
        result=super().__call__(*a,**kw)
        if self.callback is not None:self.callback(a,kw,result)
        return result

class RecordingFilter(V.F.DriveFilter):
    def __init__(self,*a,**kw):super().__init__(*a,**kw);self.k=0;self.pending=None;self.events=[];self.range_events=[]
    def _s_R(self,*a,**kw):
        value=super()._s_R(*a,**kw)
        if self.pending is not None:self.pending['R']=float(value)
        return value
    def _gate_ok(self,nis):
        accepted=super()._gate_ok(nis)
        if self.pending is not None:self.pending.update(nis=float(nis),accepted=bool(accepted))
        return accepted
    def update_range(self,z):
        x,p=self.mean_cov();c=self.cfg;d=np.linalg.norm(np.r_[x[:2],c.robot_z]-c.anchor_xyz);H=np.r_[(x[:2]-c.anchor_xyz[:2])/d,0,0,0,0];R=c.range_sigma**2+c.range_quant_var+c.range_extra_sigma**2;y=float(z-d-c.range_offset);ss=float(H@p@H+R);before=self.stats['r_rejected']
        super().update_range(z)
        self.range_events.append(dict(k=self.k,z=float(z),state_before=x.tolist(),covariance_before=p.tolist(),innovation=y,R=R,S=ss,nis=y*y/ss,accepted=self.stats['r_rejected']==before))
    def update_s(self,z,p1,p2):
        x,p=self.mean_cov();self.pending=dict(k=self.k,state_before=x.tolist(),covariance_before=p.tolist(),z=float(z),power=[float(p1),float(p2)],queries=[])
        def query(a,kw,result):
            h,g=result if kw.get('with_grad') else (result,None)
            self.pending['queries'].append(dict(angles=[float(v) for v in a[:3]],s=float(h),angle_gradient=g.tolist() if g is not None else None,with_grad=bool(kw.get('with_grad'))))
        self.lut.callback=query
        try:super().update_s(z,p1,p2)
        finally:self.lut.callback=None
        assert len(self.pending['queries'])==1
        q=self.pending['queries'][0];x0,y0,h0=x[:3];h,j=L.s_model(self.lut,self.cfg.anchor_xyz,self.cfg.robot_z,x0,y0,h0,self.cfg.mount_deg,with_jac=True)
        assert h==q['s'];H=np.r_[j,np.zeros(3)];self.pending.update(jacobian6=H.tolist(),innovation=float(z-h),S=float(H@p@H+self.pending['R']),state_after=self.comps[0].x.tolist(),covariance_after=self.comps[0].P.tolist())
        self.events.append(self.pending);self.pending=None

def check_inputs(plan):
    for p,h in plan['input_hashes'].items():assert sha(p)==h,p
    for p,h in plan['original_execution_source_hashes'].items():assert sha(p)==h,p
    assert sha(__file__)==read(OUT/'HARNESS_AMENDMENT.json')['new_script_sha256']

def replay():
    plan=read(OUT/'PLAN.json');check_inputs(plan);start=time.perf_counter();data=V.load();table=frozen_table()
    meta=data['meta'];lut=RecordingLut(dict(theta_deg=meta['meta']['theta_deg'],phi_deg=np.arange(-180.,180.,2.),s=data['lut'].s))
    keep=np.zeros(len(data['t']),bool);keep[read(OLD/'STEP5_CALIBRATION.json')['evaluation_indices']]=True
    receipts=[]
    for seed in plan['seeds']:
        inp,x0=V.physical(seed,data);obs=V.makeobs(data,seed);cfg=V.cfg0(table.scalar_rms);cfg.s_residual_table=table;f=RecordingFilter(cfg,lut,x0);est=[];cov=[];failed=None
        for k in range(len(data['t'])):
            f.k=k
            try:
                if k:
                    f.predict(inp['ds_odom'][k],inp['dtheta_gyro'][k]);f.update_odom_heading(inp['dtheta_odom'][k],inp['dtheta_gyro'][k],inp['ds_odom'][k])
                    if obs['detected'][k]:f.update_range(obs['range_m'][k]);f.update_s(obs['s'][k],*obs['power'][k])
                x,p=f.mean_cov();assert np.isfinite(x).all() and np.isfinite(p).all()
                # Same existing legacy run_filter validity boundary, no clamp/jitter.
                if np.linalg.eigvalsh(p).min() < -1e-10:raise ValueError('NON_PSD_COVARIANCE')
                est.append(x);cov.append(p)
            except Exception as exc:failed=dict(k=k,last_valid_sample=k-1,reason=repr(exc));break
        path=OUT/f'REPLAY_{seed}.npz';np.savez_compressed(path,estimate=est,covariance6=cov,truth=data['truth'],time_s=data['t'],evaluation_mask=keep,inputs_ds=inp['ds_odom'],inputs_gyro=inp['dtheta_gyro'],inputs_wheel_yaw=inp['dtheta_odom'],observed_s=obs['s'],observed_range=obs['range_m'],observed_power=obs['power'],detected=obs['detected'],initial_state=x0)
        write(f'EVENTS_{seed}.json',dict(s=f.events,range=f.range_events,failure=failed))
        old=np.load(MET/f'distance_{seed}.npz');e=np.array(est);p=np.array(cov)
        if failed:
            receipts.append(dict(seed=seed,matched=False,failure=failed));write('REPLAY_MATCH.json',dict(runs=receipts,complete=False));raise RuntimeError(failed)
        assert np.array_equal(keep,old['evaluation_mask'])
        gate=np.array([[r['k'],1,r['nis'],float(r['accepted'])] for r in f.events]);ref=old['gate_events'];ref=ref[ref[:,1]==1]
        err=e[keep,:3]-data['truth'][keep];err[:,2]=V.F.wrap(err[:,2]);pp=p[keep,:3,:3];nees=np.einsum('ni,ni->n',err,np.linalg.solve(pp,err[...,None])[...,0]);met=dict(pos_rmse_m=float(np.sqrt((err[:,:2]**2).sum(1).mean())),heading_rmse_deg=float(np.rad2deg(np.sqrt((err[:,2]**2).mean()))),nees_mean=float(nees.mean()),pose_cov95=float((nees<=7.814727903251179).mean()))
        refmet=next(r for r in read(MET/'RESULT.json')['runs'] if r['seed']==seed and r['model']=='distance')['metrics']
        delta=dict(state_max=float(np.max(abs(e-old['estimate']))),covariance_max=float(np.max(abs(p-old['covariance6']))),gate_nis_max=float(np.max(abs(gate[:,2]-ref[:,2]))),gate_identical=bool(np.array_equal(gate[:,[0,1,3]],ref[:,[0,1,3]])),metrics={k:abs(v-refmet[k]) for k,v in met.items()})
        matched=bool(np.allclose(e,old['estimate'],rtol=1e-10,atol=1e-10) and np.allclose(p,old['covariance6'],rtol=1e-10,atol=1e-10) and delta['gate_identical'] and all(np.isclose(met[k],refmet[k],atol=1e-8,rtol=1e-10) for k in met))
        receipts.append(dict(seed=seed,matched=matched,differences=delta,metrics=met,failure=failed,n_actual_s_queries=len(f.events)));print('REPLAY',seed,matched,flush=True)
    write('REPLAY_MATCH.json',dict(runs=receipts,complete=len(receipts)==24,all_matched=all(r['matched'] for r in receipts),elapsed_s=time.perf_counter()-start,summary={k:float(np.mean([r['metrics'][k] for r in receipts])) for k in met}))
    assert all(r['matched'] for r in receipts),'REPLAY_NOT_HISTORICALLY_EQUIVALENT'

def cell(pt):
    p=np.asarray(pt);t=np.clip(p[0]/2,0,45-1e-9);a=(p[1]+180)/2;b=(p[2]+180)/2;z=np.array([t,a,b]);base=np.floor(z).astype(int);f=z-base;ix=[];w=[]
    for bits in itertools.product((0,1),repeat=3):
        v=base+bits;v[1:]%=180;ix.append(tuple(v));w.append(float(np.prod([f[i] if bits[i] else 1-f[i] for i in range(3)])))
    return ix,np.array(w)

def offline():
    plan=read(OUT/'PLAN.json');check_inputs(plan);match=read(OUT/'REPLAY_MATCH.json');assert match['all_matched'];start=time.perf_counter()
    banks=load_banks(L1/'inputs');freq=banks[0].freqs_hz;S=np.load(V.RAW/'hs_lut_2deg.npy');oldrows=read(L1/'ALL_POINTS.json');archive=np.load(L1/'RAW_CHANNEL_CIR.npz');oldcir=archive['CIR_tx0'];oldmap={tuple(r['angles']):r for r in oldrows}
    vertices={};vertex_cir=[];center_cache={};n_new_vertex=0;n_direct=0;n_jac=0
    def direct(pt):
        nonlocal n_direct
        th,ph=np.deg2rad(pt[:2]);dw=V.ANCHOR # replaced with physical direction below
        dw=np.diag([1.,-1.,-1.])@np.array([np.sin(th)*np.cos(ph),np.sin(th)*np.sin(ph),np.cos(th)])
        yaw=np.rad2deg(np.arctan2(-dw[1],-dw[0]))-pt[2];h=L.los_h(banks,dw,yaw)[:,:,0];c=O.cir_batch(h[None])[0];o=O.first_path_batch(c[None],float(freq[1]-freq[0]));n_direct+=1
        return dict(s=float(o['s'][0]),index=int(o['index'][0]),power=o['power'][0].tolist()),c
    def vertex(ix):
        nonlocal n_new_vertex
        if ix in vertices:return vertices[ix]
        pt=(2*ix[0],-180+2*ix[1],-180+2*ix[2]);known=oldmap.get(pt)
        if known is not None:res=dict(s=known['s_direct'],index=known['index'],power=known['power']);c=oldcir[known['id']];origin='saved_stage3'
        else:
            assert n_new_vertex<20000,'VERTEX_CPU_CAP';res,c=direct(pt);n_new_vertex+=1;origin='new_offline'
        row=dict(id=len(vertices),grid=list(ix),angles=list(pt),**res,origin=origin,lut_vertex=float(S[ix]));vertices[ix]=row;vertex_cir.append(c);return row
    records=[];deriv=[];summary=[];segments=[];diagnostic_raw=[]
    for seed in plan['seeds']:
        ev=read(OUT/f'EVENTS_{seed}.json');z=np.load(OUT/f'REPLAY_{seed}.npz');t=z['time_s'];keep=z['evaluation_mask'];truth=z['truth'];all_seed=[]
        for e in ev['s']:
            k=e['k'];q=e['queries'][0];pt=q['angles'];key=tuple(pt)
            if key not in center_cache:
                c,cc=direct(pt);center_cache[key]=(c,cc)
            c,cc=center_cache[key];ix,w=cell(pt);vv=[vertex(v) for v in ix];tap=c['index'];fixed=[]
            for v in vv:
                power=abs(vertex_cir[v['id']][tap])**2;fixed.append(float((power[0]-power[1])/sum(power)))
            interp=float(sum(wj*S[v] for wj,v in zip(w,ix)));assert abs(interp-q['s'])<1e-12
            selection=float(q['s']-w@fixed);smooth=float(w@fixed-c['s']);dlt=q['s']-c['s'];mixed=len(set([tap]+[v['index'] for v in vv]))>1
            x=np.array(e['state_before']);err=x[:3]-truth[k];err[2]=V.F.wrap(err[2]);P=np.array(e['covariance_before'])[:3,:3];nees=float(err@np.linalg.solve(P,err))
            r=dict(seed=seed,k=k,time_s=float(t[k]),evaluation=bool(keep[k]),state_before=e['state_before'],state_after=e['state_after'],angles=pt,cell_base=list(ix[0]),vertex_ids=[v['id'] for v in vv],vertex_taps=[v['index'] for v in vv],direct_tap=tap,polar=bool(0<=pt[0]<2),mixed_tap=mixed,violation=bool(abs(dlt)>.01),delta_s=float(dlt),direct_s=c['s'],lut_s=q['s'],direct_power=c['power'],selection_component=selection,fixed_tap_interpolation_component=smooth,
                R=e['R'],S=e['S'],innovation=e['innovation'],innovation_direct_offline=float(e['z']-c['s']),nis=e['nis'],accepted=e['accepted'],jacobian6=e['jacobian6'],pre_s_position_error_m=float(np.linalg.norm(err[:2])),pre_s_heading_error_deg=float(np.rad2deg(err[2])),pre_s_pose_nees=nees,
                post_state_polar_geometry=bool(np.rad2deg(np.arctan2(np.linalg.norm(np.array(e['state_after'])[:2]-V.ANCHOR[:2]),V.ANCHOR[2]-V.RZ))<2))
            all_seed.append(r);records.append(r)
        # Diagnostic samples only: queries remain actual, derivative evaluations never enter filter.
        chosen=set()
        for name in ('polar','mixed_tap','violation'):
            rr=sorted([r for r in all_seed if r[name]],key=lambda r:(-abs(r['delta_s']),r['k']))[:2];chosen.update(r['k'] for r in rr)
        chosen.update(r['k'] for r in sorted([r for r in all_seed if not r['mixed_tap']],key=lambda r:(-abs(r['delta_s']),r['k']))[:2])
        chosen.update(all_seed[int(f*(len(all_seed)-1))]['k'] for f in (.0,.25,.5,.75))
        assert len(chosen)<=12
        for r in all_seed:
            if r['k'] not in chosen:continue
            pt=r['angles'];eps=.01;minus=pt.copy();plus=pt.copy();minus[2]+=eps;plus[2]-=eps
            dm,cm=direct(minus);dp,cp=direct(plus);n_jac+=2
            tap=r['direct_tap'];pm=abs(cm[tap])**2;pp=abs(cp[tap])**2;sm=float((pm[0]-pm[1])/sum(pm));sp=float((pp[0]-pp[1])/sum(pp));step=np.deg2rad(eps)
            dr=(dp['s']-dm['s'])/(2*step);fr=(sp-sm)/(2*step);j=r['jacobian6'][2];smooth=dm['index']==tap==dp['index']
            # Direct finite difference modifies body heading, phi_rx follows minus heading; state positions unchanged.
            deriv.append(dict(seed=seed,k=r['k'],angles=pt,taps=[dm['index'],tap,dp['index']],same_tap=smooth,direct_secant_per_rad=dr,fixed_tap_secant_per_rad=fr,lut_jacobian_per_rad=j,difference=dr-j,polar=r['polar'],mixed_tap=r['mixed_tap'],violation=r['violation']))
            diagnostic_raw.append(dict(seed=seed,k=r['k'],minus=cm,plus=cp))
        for mask_name,mask in [('all',lambda r:True),('evaluation',lambda r:r['evaluation'])]:
            rr=[r for r in all_seed if mask(r)]
            def stat(a):
                return dict(n=len(a),accepted=sum(r['accepted'] for r in a),rejected=sum(not r['accepted'] for r in a),max_abs_delta=max((abs(r['delta_s']) for r in a),default=None),mean_abs_delta=float(np.mean([abs(r['delta_s']) for r in a])) if a else None,
                    innovation_rms=float(np.sqrt(np.mean([r['innovation']**2 for r in a]))) if a else None,mean_nis=float(np.mean([r['nis'] for r in a])) if a else None,
                    pos_rmse=float(np.sqrt(np.mean([r['pre_s_position_error_m']**2 for r in a]))) if a else None,heading_rmse_deg=float(np.sqrt(np.mean([r['pre_s_heading_error_deg']**2 for r in a]))) if a else None)
            groups={}
            for label,sel in [('all',lambda r:True),('polar',lambda r:r['polar']),('mixed_tap',lambda r:r['mixed_tap']),('violation',lambda r:r['violation']),('same_index_candidate',lambda r:not r['mixed_tap'])]:
                a=[r for r in rr if sel(r)];groups[label]=dict(pre_gate=stat(a),accepted_only=stat([r for r in a if r['accepted']]),rejected_only=stat([r for r in a if not r['accepted']]))
            summary.append(dict(seed=seed,mask=mask_name,n_s_updates_attempted=len(rr),min_theta=min(r['angles'][0] for r in rr),post_state_polar_count=sum(r['post_state_polar_geometry'] for r in rr),groups=groups))
            for label in ('polar','mixed_tap','violation'):
                aa=[r for r in rr if r[label]];blocks=[]
                for r in aa:
                    if not blocks or r['k']!=blocks[-1][-1]['k']+1:blocks.append([])
                    blocks[-1].append(r)
                for block in blocks:segments.append(dict(seed=seed,mask=mask_name,type=label,start_k=block[0]['k'],end_k=block[-1]['k'],start_s=block[0]['time_s'],end_s=block[-1]['time_s'],n=len(block),span_s=block[-1]['time_s']-block[0]['time_s'],rejected=sum(not r['accepted'] for r in block),max_abs_delta=max(abs(r['delta_s']) for r in block)))
        write(f'EXPOSURE_{seed}.json',all_seed);print('OFFLINE',seed,len(all_seed),sum(r['mixed_tap'] for r in all_seed),sum(r['violation'] for r in all_seed),flush=True)
    write('SEED_SUMMARY.json',summary);write('CONTIGUOUS_SEGMENTS.json',segments);write('HEADING_JACOBIAN.json',deriv);write('VERTEX_INDEX.json',list(vertices.values()))
    np.savez_compressed(OUT/'VERTEX_CIR.npz',cir=np.array(vertex_cir),frequencies_hz=freq)
    np.savez_compressed(OUT/'DERIVATIVE_CIR.npz',minus=np.array([r['minus'] for r in diagnostic_raw]),plus=np.array([r['plus'] for r in diagnostic_raw]),seed=np.array([r['seed'] for r in diagnostic_raw]),k=np.array([r['k'] for r in diagnostic_raw]))
    assert len(records)<=plan['offline']['max_queries'] and n_jac<=plan['offline']['max_derivative_points']
    aggregate={}
    for mask in ('all','evaluation'):
        selected=[r for r in records if mask=='all' or r['evaluation']]
        aggregate[mask]=dict(n=len(selected),polar=sum(r['polar'] for r in selected),mixed=sum(r['mixed_tap'] for r in selected),violation=sum(r['violation'] for r in selected),min_theta=min(r['angles'][0] for r in selected),max_abs_delta=max(abs(r['delta_s']) for r in selected),accepted_violations=sum(r['violation'] and r['accepted'] for r in selected),rejected_violations=sum(r['violation'] and not r['accepted'] for r in selected))
    write('OFFLINE_RESULT.json',dict(aggregate=aggregate,n_new_vertex=n_new_vertex,n_saved_vertex=len(vertices)-n_new_vertex,n_unique_center=len(center_cache),n_derivative=n_jac,n_direct_los=n_direct,elapsed_s=time.perf_counter()-start,scientific_PASS=False,F01='OPEN',F02='OPEN',other_conditions='UNKNOWN',polar_effect_at_actual_queries='NO_EXPOSURE' if not aggregate['all']['polar'] else 'REQUIRES_PHYSICAL_YAW_ANALYSIS'))
    print(json.dumps(aggregate,indent=2))

if __name__=='__main__':
    {'prepare':prepare,'replay':replay,'offline':offline}[sys.argv[1]]()
