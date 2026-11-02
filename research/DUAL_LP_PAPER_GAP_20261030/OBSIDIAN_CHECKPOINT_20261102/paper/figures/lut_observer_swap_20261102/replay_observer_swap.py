"""User-authorized observer-only ablation. Reuses original recursive filter unchanged."""
from pathlib import Path
import os,sys,json,hashlib,datetime,platform,traceback,time
import numpy as np
import pandas as pd

OUT=Path(__file__).resolve().parent
BASE=OUT.parents[1]
SRC=BASE/'figures/conventional_ekf_20261102'
PKG=BASE/'figures/three_stage_package_20261102/DualLP_ThreeStage_Physics_20261102/tables'
REC=Path('C:/Users/Myoungsun Kim/dlp1102/DualLP_Physics_Link_Validation_20261101')
OLD=Path('C:/Users/Myoungsun Kim/dlp1102/anchor_b_8arm/repo')
os.environ['REFLECT_ROOT']=str(REC/'recovered/inputs')
sys.path.insert(0,str(REC/'recovered/legacy/research/DS_MASK_CAUSAL_X1_X2_20261026/mbvar_premodel_diag_20261029/code'))
import diag_mbvar as DG
from p3_rf_adapter4 import FrozenLut,R0,LUT_REL

CASES=['R2_aB_m0','R4_aB_m0','R5_aB_m0']
BIASES=['B0','L0','L1','L2']
STAGES=['LOS_EKF','MULTIPATH_EKF','PROPOSED_MB_VAR']
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(name,obj):
    (OUT/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def stop_check():
    f=os.environ.get('MANAGED_PROCESS_STOP_FILE')
    if f and Path(f).exists():raise RuntimeError('MANAGED_STOP_REQUESTED')
class LutBatch:
    def __init__(self):self.lut=FrozenLut(OLD)
    def batch(self,states,case):
        pairs=[self.lut.model(x,case) for x in np.asarray(states)]
        return np.stack([p[0] for p in pairs]),np.stack([p[1] for p in pairs])

def refpath(case,bias,stage):
    return REC/f'results/traces/{case}__{bias}__MB_VAR__self.npz' if stage=='PROPOSED_MB_VAR' else SRC/f'{case}_{bias}_{stage}.npz'

def make_data(case,bias):
    ref=DG.C.load_control(case,'B0');jb,jm=ref['jb'],ref['jm'];t=ref['t_s'];gt=ref['truth_scoring_only']
    ds,gy,dt,x0=DG.PB.build_controls(t,gt[:,:3],bias)
    z=ref['nu'][:,jb]+ref['h'][:,jb]+ref['mu'][:,jb]
    spec=DG.C.CASES[case]
    # acc and hg are unused in self-gated DG.run and its scorer. Do not run an extra baseline filter to create them.
    return dict(case=case,bias=bias,t=t,gt=gt,z=z,R=ref['R'][:,jb],acc=np.zeros(len(t),bool),ds=ds,gy=gy,dt=dt,
                x0=np.r_[x0,0.],P0=ref['Pprior'][0,jb],spec=spec,anchor=np.array(spec['anchor'][:2]),
                mu=dict(BB=ref['mu'][:,jb],MB=ref['mu'][:,jm]))
def arm_data(D,stage):
    E=dict(D)
    if stage=='PROPOSED_MB_VAR':return E,'MB','var'
    if stage=='LOS_EKF':
        with np.load(PKG/f'{D["case"]}_{D["bias"]}_LOS_ZERO_MEAN.npz') as los:
            assert np.array_equal(los['t'],D['t']) and np.array_equal(los['gt'],D['gt'])
            E['z']=los['z_los'].copy()
    E['R']=np.broadcast_to(R0,(len(D['t']),2,2)).copy();E['mu']={'BB':np.zeros_like(E['z'])}
    return E,'BB','orig'

def score(D,X,P,L,observer,stage):
    assert np.isfinite(X).all() and np.isfinite(P).all()
    assert np.max(abs(P-P.transpose(0,2,1)))<1e-10
    eig=float(np.linalg.eigvalsh(P).min());assert eig>0,eig
    m=D['t']>=30-1e-9;e=D['gt'][:,:3]-X[:,:3];e[:,2]=np.angle(np.exp(1j*e[:,2]))
    pp=P[:,:3,:3];pose=np.einsum('ni,ni->n',e,np.linalg.solve(pp,e[...,None])[...,0])
    whiten=np.linalg.solve(np.linalg.cholesky(pp),e[...,None])[...,0]
    assert np.allclose(pose,np.sum(whiten**2,axis=1),rtol=1e-9,atol=1e-9)
    xy=np.einsum('ni,ni->n',e[:,:2],np.linalg.solve(P[:,:2,:2],e[:,:2,None])[...,0]);head=e[:,2]**2/P[:,2,2]
    orig=DG.scores(D,X,P)
    assert abs(np.mean(xy[m])-orig['nees_xy'])<1e-9
    assert np.isclose(np.mean(head[m]),orig['head_z_rms']**2,rtol=1e-10,atol=1e-10)
    row=dict(case=D['case'],route=D['case'][:2],bias=D['bias'],stage=stage,observer=observer,n_total=len(X),n_score=int(m.sum()),
             n_used=int(L['used'].sum()),n_used_score=int(L['used'][m].sum()),min_cov_eigenvalue=eig,**orig,
             nees_heading=float(np.mean(head[m])),nees_pose=float(np.mean(pose[m])),
             pose_cov95=float(np.mean(pose[m]<7.814727903251179)))
    packet=pd.DataFrame(dict(case=D['case'],bias=D['bias'],stage=stage,observer=observer,t_s=D['t'],scored=m,
          heading_error_deg=np.degrees(e[:,2]),xy_error_cm=100*np.linalg.norm(e[:,:2],axis=1),nees_heading=head,nees_xy=xy,nees_pose=pose,used=L['used']))
    return row,packet

def main():
    assert not (OUT/'CONTRACT.json').exists(),'OUTPUT_EXISTS_DO_NOT_OVERWRITE'
    paths=[Path(__file__),SRC/'CONTRACT.json',SRC/'THREE_STAGE_SCORES.csv',SRC/'replay_conventional.py',
           OLD/(LUT_REL+'hs_lut_2deg.npy'),OLD/(LUT_REL+'hs_lut_meta.json')]
    for c in CASES:
        paths.append(REC/f'recovered/inputs/traces/{c}_B0_CONTROL.npz')
        for b in BIASES:
            paths.append(PKG/f'{c}_{b}_LOS_ZERO_MEAN.npz')
            for s in STAGES:paths.append(refpath(c,b,s))
    paths += list((REC/'recovered/legacy/research/DS_MASK_CAUSAL_X1_X2_20261026').rglob('*.py'))
    paths += list((REC/'recovered/inputs/repo/research/FFD_P0P3_20261016').glob('*.py'))
    paths += list((REC/'recovered/inputs/repo/research/EKF4_RANGE_S_STAGED_20261014').glob('*.py'))
    paths += list((REC/'recovered/inputs/banks').glob('*.npz'))
    paths += list((REC/'recovered/inputs/repo/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src').rglob('*.py'))
    gov=Path('C:/Users/Myoungsun Kim/.codex/research-governance')
    paths += [gov/'COMMON_CONTRACT.md',gov/'ROLE_IMPLEMENTER.md',gov/'ROLE_AUDITOR.md']
    hashes={str(p):sha(p) for p in sorted(set(paths))}
    contract=dict(question_id='DLP-ANCHORB-LUT-OBSERVER-SWAP-20261102',roles='IMPLEMENTER then AUDITOR self-check; not independent audit',
      authorization='User explicitly requested observer-only LUT replay, all other conditions identical',
      source_declared_original_commit='9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13',source_evidence_commit='6c7200091028fd3f0e55aa83b777d0f10b7cf063',
      checkout_status='Recovered runtime and sparse LUT files; no valid local checkout HEAD; exact file hashes are controlling execution identity',
      cases=CASES,biases=BIASES,bias_deg_s=[0,.01,.05,.20],stages=STAGES,expected_lut_replays=36,expected_source_validation_replays=36,
      intervention='Replace SourceFFD h and H with ORIGINAL frozen 2-degree 10m LUT h and H; no pole hotfix, no refit, no mean recentering',
      controls='Same packets, source sensor generator seed0, initial x/P, Q, four states, raw-range offset, self NIS threshold, R0 and frozen MB donor means and variance table',
      adaptive_rule='Same previous-posterior horizontal-distance variance lookup; realized R and gate masks may change as a consequence of changed trajectory',
      R0=R0.tolist(),variance_table=[a.tolist() for a in DG.HAND],gate=DG.GATE,
      score='All t>=30-1e-9 including rejected packets; heading degrees, XY cm; NEES heading 1D, XY 2D, pose [x,y,psi] 3D; no bias NEES',
      validation_thresholds=dict(X_max_abs=1e-10,P_max_abs=1e-10,R_max_abs=1e-12,gate_mismatch=0),
      allowed_claim='Paired retrospective observer intervention on one frozen scene and seed; no refitting, new RT, independent environment or calibrated-posterior claim',
      governance_note='Embedded MBVAR-INFO governance is scoped to a different campaign; local common contract governs this user-authorized ablation',
      input_hashes=hashes,python=sys.version,numpy=np.__version__,pandas=pd.__version__,platform=platform.platform(),
      thread_id=os.environ.get('MANAGED_PROCESS_THREAD_ID'),managed_run_id=os.environ.get('MANAGED_PROCESS_RUN_ID'),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    dump('CONTRACT.json',contract)
    # Reuse prior same-state and finite-difference observer validation as a locked precheck.
    diagnostic=BASE/'검토 기록/LUT_SourceFFD_관측모델_대조_20261102/RESULTS.json'
    check=json.loads(diagnostic.read_text(encoding='utf-8'))['checks']
    assert check['inputs_unchanged'] and check['knot_96_max_abs']<1e-6 and check['fd_lut_max_abs']<1e-7
    dump('OBSERVER_PRECHECK.json',dict(diagnostic_sha256=sha(diagnostic),checks=check))
    model=DG.C.base_model();lut=LutBatch();data={(c,b):make_data(c,b) for c in CASES for b in BIASES}
    rows=[];packets=[];parity=[];trajectory=[]
    # Gate all LUT runs on source baseline parity over all 36 archived paths.
    for c in CASES:
      for b in BIASES:
        for stage in STAGES:
            stop_check();D,bg,mode=arm_data(data[c,b],stage)
            start=time.perf_counter();X,P,L=DG.run(D,bg,mode,'self',model=model)
            with np.load(refpath(c,b,stage)) as ref:
                dx=float(abs(X-ref['X']).max());dp=float(abs(P-ref['PX']).max());dr=float(np.nanmax(abs(L['Ru']-ref['Ru'])))
                dm=int(np.count_nonzero(L['used']!=ref['used']))
                if stage!='PROPOSED_MB_VAR':assert np.array_equal(D['z'],ref['z'])
                for k in ['xp','Pp','nu','S','HPH','hx','nis']:
                    if k in ref.files:assert np.allclose(L[k],ref[k],rtol=1e-10,atol=1e-10,equal_nan=True),(c,b,stage,k)
            record=dict(case=c,bias=b,stage=stage,X_max_abs=dx,P_max_abs=dp,R_max_abs=dr,gate_mismatch=dm,seconds=time.perf_counter()-start)
            parity.append(record);pd.DataFrame(parity).to_csv(OUT/'SOURCE_BASELINE_PARITY.csv',index=False)
            assert dx<1e-10 and dp<1e-10 and dr<1e-12 and dm==0,record
            r,p=score(D,X,P,L,'SourceFFD',stage);rows.append(r);packets.append(p)
            print('SOURCE_PARITY',c,b,stage,'PASS',round(record['seconds'],2),flush=True)
    dump('BASELINE_GATE.json',dict(status='PASS',n=36,all_X_P_R_and_masks_within_frozen_tolerances=True))
    print('BASELINE_GATE_PASS_ALL_36',flush=True)
    for c in CASES:
      for b in BIASES:
        for stage in STAGES:
            stop_check();D,bg,mode=arm_data(data[c,b],stage)
            X,P,L=DG.run(D,bg,mode,'self',model=lut)
            # Preserve existing arithmetic and state dependence, including pre-predict variance lookup.
            rho=np.linalg.norm(np.vstack([D['x0'][:2],X[:-1,:2]])-D['anchor'],axis=1)
            sg=np.interp(rho,DG.HAND[0],DG.HAND[1])
            expected=D['R'].copy()
            if mode=='var':expected[:,1,1]+=sg**2
            assert np.allclose(L['Ru'],expected,rtol=0,atol=1e-14,equal_nan=True)
            with np.load(refpath(c,b,stage)) as ref:
                changes=int(np.count_nonzero(L['used']!=ref['used']))
                rdiff=float(np.nanmax(abs(L['Ru']-ref['Ru'])))
            trace=OUT/f'{c}_{b}_{stage}_LUT.npz'
            np.savez_compressed(trace,X=X,PX=P,t=D['t'],gt=D['gt'],z=D['z'],mu=D['mu'][bg],base_R=D['R'],
                 ds=D['ds'],gy=D['gy'],dt=D['dt'],x0=D['x0'],P0=D['P0'],rho_lookup=rho,sigma_lookup=sg,**L)
            r,p=score(D,X,P,L,'LUT',stage);r['gate_changes_vs_source']=changes;r['R_max_difference_vs_source']=rdiff
            rows.append(r);packets.append(p);trajectory.append(dict(case=c,bias=b,stage=stage,gate_changes=changes,R_max_difference=rdiff))
            pd.DataFrame(rows).to_csv(OUT/'ALL_SCORES_72.csv',index=False)
            print('LUT_DONE',c,b,stage,'heading',round(r['head_rmse'],6),'XYcm',round(r['xy_rmse_cm'],6),'NEES3',round(r['nees_pose'],6),flush=True)
    df=pd.DataFrame(rows)
    assert len(df)==72 and not df.duplicated(['case','bias','stage','observer']).any()
    assert all(np.isfinite(df[k]).all() for k in ['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose'])
    old=pd.read_csv(SRC/'THREE_STAGE_SCORES.csv');ss=df[df.observer=='SourceFFD'].merge(old,on=['case','bias','stage'],suffixes=('_new','_old'),validate='one_to_one')
    for k in ['head_rmse','xy_rmse_cm','nees_xy','head_cov95','xy_cov95']:assert np.allclose(ss[k+'_new'],ss[k+'_old'],rtol=1e-10,atol=1e-9),k
    metrics=['head_rmse','xy_rmse_cm','nees_heading','nees_xy','nees_pose','head_cov95','xy_cov95','pose_cov95']
    wide=df.pivot(index=['case','route','bias','stage'],columns='observer',values=metrics)
    wide.columns=[f'{a}_{b}' for a,b in wide.columns];wide=wide.reset_index()
    for k in metrics:wide[k+'_delta_LUT_minus_SourceFFD']=wide[k+'_LUT']-wide[k+'_SourceFFD']
    wide.to_csv(OUT/'PAIRED_COMPARISON_36.csv',index=False)
    pd.DataFrame(trajectory).to_csv(OUT/'GATE_AND_VARIANCE_CHANGES.csv',index=False)
    pd.concat(packets,ignore_index=True).to_csv(OUT/'PACKET_ERRORS_AND_NEES.csv.gz',index=False)
    assert all(sha(p)==h for p,h in hashes.items()),'FROZEN_INPUT_CHANGED'
    dump('RESULT_CHECKS.json',dict(status='EXECUTION_AND_SELF_CHECK_COMPLETED',source_parity_paths=36,new_lut_paths=36,metric_rows=72,
        input_hashes_unchanged=True,baseline_scores_match=True,all_covariances_positive_definite=True,
        NEES_solve_Cholesky_crosscheck=True,previous_posterior_variance_lookup_verified=True,
        independent_audit=False,scientific_adoption=False,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    print('COMPLETED_36_LUT_36_SOURCE_PARITY',flush=True)

if __name__=='__main__':
    try:main()
    except BaseException as exc:
        dump('FAILURE.json',dict(error=repr(exc),traceback=traceback.format_exc(),time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        raise
