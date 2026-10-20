"""S2 prior-only parameter adapter. Pinned engine body and update contract unchanged."""
from pathlib import Path
import argparse,hashlib,json,os,sys,traceback
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;SOURCE=HERE.parents[2];AUDIT=SOURCE/'research/POWERJOINT_AUDIT_RERUN_20261020'
sys.path.insert(0,str(AUDIT/'T1_MEMORY'))
from unit_tests import load_engine
load_engine(SOURCE)
sys.path.insert(0,str(AUDIT));sys.path.insert(0,str(SOURCE/'research/CHAIN_HYPOTHESIS_20261019'))
import canonical_engine as engine
import run as original
from source_model import SourceFFD
from replay import score
sys.path.insert(0,str(HERE.parent/'S1_N1_EVENTS'))
from independent_score import score_window
sys.path.insert(0,str(AUDIT/'T2_NEW_ROUTE_BASELINE'))
from prepare_inputs import prepare_new_route,build_canonical_controls
from model import ARMS,PowerModel,geometry,inputs
R0=np.diag([.0068578637,.0081])
ENGINE_SHA='e725f92bd74e6a845b07418d6f3b7a2974a518b2cd03b16969518bf879ee11b8'
SENSOR_SHA='b05e7ead6cf658d20a4830094cec56332ffcc839e7dccf04fd4ce3a1f86ccef0'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):p.write_text(json.dumps(x,indent=2,allow_nan=False)+'\n')
def load(p):
 with np.load(p,allow_pickle=False) as f:return {k:f[k] for k in f.files}
def metrics(result,j,truth,bias,mask):
 x=result['state'][mask,j,:4];P=result['cov'][mask,j,:4,:4];truth=truth[mask]
 main=score(x,P,truth,bias,np.ones(len(x),bool));ind=score_window(x,P,truth,bias)
 delta=max(abs(main[k]-ind[k]) for k in main)
 assert len(main)==11 and np.isfinite(list(main.values())).all() and delta<=1e-9,('INDEPENDENT_11_METRICS',delta)
 return dict(n=int(mask.sum()),scorer_max_abs_difference=delta,**main)
def check_trace(result,j,reference,truth,bias,mask,reference_name):
 names=list(reference['names'].astype(str));k=names.index(reference_name)
 assert np.array_equal(result['t'],reference['t']),'REFERENCE_CLOCK'
 got=metrics(result,j,truth,bias,mask);old=score(reference['state'][:,k,:4],reference['cov'][:,k,:4,:4],truth,bias,mask)
 delta=abs(got['heading_rmse_deg']-old['heading_rmse_deg']);gates=int(np.count_nonzero(result['accepted'][:,j]!=reference['accepted'][:,k]))
 assert delta<=1e-6 and gates==0,('Q_HISTORICAL_REPRODUCTION',delta,gates)
 return dict(heading_difference_deg=delta,gate_mismatches=gates,state_max_abs_difference=float(abs(result['state'][:,j,:4]-reference['state'][:,k,:4]).max()),cov_max_abs_difference=float(abs(result['cov'][:,j,:4,:4]-reference['cov'][:,k,:4,:4]).max()))

def main():
 p=argparse.ArgumentParser();p.add_argument('--route',required=True);p.add_argument('--execution-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);(a.out/'traces').mkdir(exist_ok=True)
 rows=[];aux=[];refs=[];checks=[];errors=[];proof={};features=[];metadata={};attempt=None
 matrix=pd.read_csv(HERE/'CASE_MATRIX.csv');expected=matrix[matrix.route==a.route].to_dict('records')
 try:
  assert os.getenv('GITHUB_SHA'),'COMMITTED_ACTIONS_REQUIRED'
  assert sha(AUDIT/'canonical_engine.py')==ENGINE_SHA and sha(AUDIT/'T2_NEW_ROUTE_BASELINE/PROTOCOL_LOCK.json')==SENSOR_SHA
  lock=json.loads((HERE/'PROTOCOL_LOCK.json').read_text())
  for name,expected_hash in lock['contract_hashes'].items():assert sha(HERE/name)==expected_hash,('CONTRACT_BYTES',name)
  params=json.loads((HERE/'TRAIN_PARAMS.json').read_text());meta=json.loads((HERE/'CASE_METADATA.json').read_text())
  for path in [HERE/'PROTOCOL_LOCK.json',HERE/'CASE_MATRIX.csv',HERE/'TRAIN_SPLITS.json',HERE/'TRAIN_PARAMS.json',HERE/'model.py',Path(__file__),AUDIT/'canonical_engine.py',AUDIT/'T2_NEW_ROUTE_BASELINE/PROTOCOL_LOCK.json',Path(sys.modules['core'].__file__),Path(sys.modules['source_model'].__file__),Path(sys.modules['independent_score'].__file__)]:proof[str(path)]=sha(path)
  for path in [a.execution_root/'RESTORE_RECEIPT.json',a.execution_root/'references/S2_REFERENCE_RECEIPT.json',a.execution_root/'source_route/ARCHIVE_CONTENTS_AND_SHA.json']:
   if path.exists():proof[str(path)]=sha(path)
  import p0_initial
  p0_initial.OUT=a.out/'bank_audit';p0_initial.OUT.mkdir(exist_ok=True)
  model=SourceFFD();fold=a.route if a.route.startswith('R') else 'ALL_OLD';models={k:PowerModel(v) for k,v in params[fold]['models'].items()}
  t9=pd.read_csv(AUDIT/'T9_SPEC/RESULTS.csv');t2=pd.read_csv(AUDIT/'T2_NEW_ROUTE_BASELINE/ALL_METRICS.csv');key=pd.read_csv(SOURCE/'research/CHAIN_VALIDATED_RESULTS_20261019/evidence/KEY_B0_RESULTS.csv')
  data=[]
  if a.route.startswith('R'):
   raw=original.frozen_inputs();labels=pd.read_csv(a.execution_root/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz')
   assert sha(a.execution_root/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz')==lock['labels_sha256']
   for case in meta['legacy']:
    if case['route']!=a.route:continue
    cid=case['id']
    for channel in ['full']+(['los'] if cid in ('R2_aA_m0','R2_aA_m45') else []):
     packet=raw[cid,channel];t=packet['t_s'];truth=packet['truth_for_offline_scoring_only'][:,:3];frame=labels[(labels.case==cid)&(labels.channel==channel)].set_index('pose_id').loc[packet['pose_id']]
     z=np.c_[packet['z_r_m'],packet['z_s']];assert np.max(abs(z-frame[['range_m','s_fp']].to_numpy()))<=1e-10,'OBSERVER_ALIGNMENT'
     data.append(dict(case=case,channel=channel,t=t,truth=truth,z=z,q=frame.log_fp_power.to_numpy(),radio=np.ones(len(t),bool),seeds=[0],biases=['B0','L2'],prepared=None))
  else:
   prepared=prepare_new_route(a.execution_root/'source_route',a.route);metadata=prepared['metadata'];t=prepared['motion_t'];ri=prepared['rf_motion_indices'];radio=np.zeros(len(t),bool);radio[ri]=True
   for rec in prepared['cases']:
    cid=rec['case_id'];case=next(c for c in meta['new'] if c['id']==cid);h=np.load(rec['full_path'],allow_pickle=False)
    assert h.shape==(len(ri),257,2,2),'FULL_H_SHAPE'
    frame=pd.concat([pd.DataFrame(original.extract(h[i:i+64,:,:,0],model.freqs)) for i in range(0,len(h),64)],ignore_index=True)
    z=np.zeros((len(t),2));z[ri]=frame[['range_m','s_fp']].to_numpy();q=np.zeros(len(t));q[ri]=frame.log_fp_power.to_numpy()
    proof[rec['full_path']]=sha(rec['full_path'])
    data.append(dict(case=case,channel='full',t=t,truth=prepared['motion_truth'],z=z,q=q,radio=radio,seeds=list(range(5)),biases=list(original.BIAS_LEVELS),prepared=prepared,los_exists=rec['los_exists']))
  for d in data:
   case=d['case'];cid=case['id'];channel=d['channel'];t=d['t'];radio=d['radio'];truth=d['truth'];z=d['z'];q=d['q']
   for seed in d['seeds']:
    for bias in d['biases']:
     common=dict(case=cid,route=a.route,channel=channel,bias=bias,seed=seed,scope='motion',mount_status='OUT_OF_TRAINING_RANGE_MOUNT' if cid=='R2_aA_m45' else 'IN_TRAINING_MOUNT_RANGE')
     attempt=common
     if d['prepared'] is None:controls,initial=original.build_positive_bias_controls(t,truth,bias,seed)
     else:controls,initial,metadata['sensor']=build_canonical_controls(d['prepared'],bias,seed,SOURCE)
     features=[]
     def provider(i,prior,spec):
      # Engine supplies this arm's just-predicted physical state, no truth/future argument.
      arm=spec['name']
      if not radio[i] or arm=='JOINT4_R0':return np.zeros(2),R0.copy()
      dd,theta,X=geometry(prior[None],case);AA,bb=inputs(arm,np.array([q[i]]),dd,X);mm,cc=models[arm].predict(AA,bb)
      features.append(dict(arm=arm,frame=i,t_s=float(t[i]),prior_x=float(prior[0]),prior_y=float(prior[1]),prior_yaw_rad=float(prior[2]),distance_m=float(dd[0]),theta_rad=float(theta[0]),bin_scalar=float(bb[0]),q=float(q[i]) if arm in ('Q_POWER1','GEOM_Q') else None,mu_r=float(mm[0,0]),mu_s=float(mm[0,1]),C00=float(cc[0,0,0]),C01=float(cc[0,0,1]),C11=float(cc[0,1,1]),**{f'f{k}':float(v) for k,v in enumerate(AA[0])}))
      return mm[0],cc[0]
     qm,qc=models['Q_POWER1'].predict(q[:,None],q)
     specs=[dict(name=arm,base='power') for arm in ARMS]+([dict(name='JOINT4_R0',base='r0')] if channel=='los' else [])
     result=engine.run(t,controls,initial,z,qm,qc,np.zeros(len(t)),case,model,specs,radio_mask=radio,parameter_provider=provider)
     # Persist first, including an otherwise failing trace. No covariance repair.
     stem=f'{cid}_{channel}_{bias}_seed{seed}'
     result.update(truth_for_offline_scoring_only=truth,observations=z,q_observed=q,radio_mask=radio,controls_dt=controls['dt_s'],controls_ds=controls['ds_odom'],controls_dyaw=controls['dtheta_gyro'],initial_pose=initial)
     if 'los_exists' in d:result['los_exists_at_radio']=d['los_exists']
     np.savez_compressed(a.out/'traces'/f'{stem}.npz',**result)
     pd.DataFrame(features).to_csv(a.out/f'ONLINE_FEATURES_{stem}.csv',index=False)
     assert np.isfinite(result['state']).all() and np.isfinite(result['cov']).all(),'NONFINITE'
     eig=min(float(np.linalg.eigvalsh(result[k]).min()) for k in ('cov','prior_cov'));assert eig>0,('NONSPD_ALL_FRAMES',eig)
     assert not result['accepted'][~radio].any(),'NONRADIO_UPDATE'
     nfeature=sum(1 for _ in features);assert nfeature==int(radio.sum())*4,'PRIOR_PROVIDER_CALL_COVERAGE'
     # Audit own-prior identity independently against the engine's saved prior.
     for f in features:
      j=list(ARMS).index(f['arm']);saved=result['prior'][f['frame'],j,:3]
      assert np.array_equal(saved,np.array([f['prior_x'],f['prior_y'],f['prior_yaw_rad']])),'OWN_PRIOR_IDENTITY'
     j=0;mask=t>=30;baseline=metrics(result,j,truth,original.BIAS_LEVELS[bias],mask)
     if d['prepared'] is None:
      path=a.execution_root/'reference_ae/traces'/f'{cid}_{bias}.npz' if channel=='full' else next((a.execution_root/'references').rglob(f'{cid}_los_{bias}_Q_POWER1.npz'))
      hist=load(path);reference_name='POWER1' if channel=='full' else 'Q_POWER1';kind='HISTORICAL_TRACE'
     else:
      path=next((a.execution_root/'references').rglob(f'{cid}_{bias}.npz'));hist=load(path);reference_name='POWER1';kind='HISTORICAL_TRACE' if seed==0 else 'REGENERATED_FROZEN_T2_REFERENCE_NO_HISTORICAL_GATES'
      assert np.array_equal(t,hist['t']) and np.array_equal(truth,hist['truth_for_offline_scoring_only']) and np.array_equal(z,hist['observations']) and np.array_equal(radio,hist['radio_mask']),'T2_INPUT_IDENTITY'
      parity=max(float(abs(qm[radio]-hist['mu_input'][radio]).max()),float(abs(qc[radio]-hist['C_input'][radio]).max()));assert parity<=1e-10,('ALL_OLD_Q_T2_MU_C',parity)
      if seed==0:
       assert np.array_equal(initial,hist['initial_pose']) and all(np.array_equal(controls[k],hist[h]) for k,h in [('dt_s','controls_dt'),('ds_odom','controls_ds'),('dtheta_gyro','controls_dyaw')]),'T2_CONTROLS_IDENTITY'
      else:
       hist=engine.run(t,controls,initial,z,hist['mu_input'],hist['C_input'],np.zeros(len(t)),case,model,[dict(name='POWER1',base='power')],radio_mask=radio)
      old=t2[(t2.case==cid)&(t2.bias==bias)&(t2.seed==seed)&(t2.arm=='POWER1')&(t2.scope=='motion')];assert len(old)==1
      delta=abs(baseline['heading_rmse_deg']-float(old.iloc[0].heading_rmse_deg));assert delta<=1e-6,('T2_SAME_SEED_HEADING',delta)
      checks.append(dict(**common,check='T2_SAME_SEED_METRICS',status='PASS',heading_difference_deg=delta,historical_gate_available=seed==0,mu_C_max_abs_difference=parity))
     proof[str(path)]=sha(path)
     reproduction=check_trace(result,j,hist,truth,original.BIAS_LEVELS[bias],mask,reference_name)
     checks.append(dict(**common,check='Q_BASELINE_REPRODUCTION',status='PASS',reference_kind=kind,minimum_prior_posterior_eigenvalue=eig,nonradio_updates=0,**reproduction))
     if d['prepared'] is None and channel=='full' and bias=='B0':
      kk=key[(key.case==cid)&(key.method=='POWER1')];assert len(kk)==1
      delta=abs(baseline['heading_rmse_deg']-float(kk.iloc[0].heading_rmse_deg));assert delta<=1e-6,('KEY_B0',delta)
      checks.append(dict(**common,check='KEY_B0_REPRODUCTION',status='PASS',heading_difference_deg=delta))
     for j,arm in enumerate(result['names'].astype(str)):
      for scope,smask in [('motion',mask),('radio',mask&radio)]:
       values=metrics(result,j,truth,original.BIAS_LEVELS[bias],smask);row=dict(common,scope=scope,arm=arm,status='TECHNICAL_PASS',**values)
       if arm=='JOINT4_R0':
        if scope=='motion':refs.append(row)
       elif scope=='motion':rows.append(row)
       else:aux.append(row)
      if arm=='DIST_ONLY' and d['prepared'] is None:
       old=t9[(t9.case==cid)&(t9.channel==channel)&(t9.bias==bias)&(t9.arm=='DISTANCE_ONLY_POWER1')];assert len(old)==1
       checks.append(dict(**common,check='DIST_ONLY_T9_ROWWISE',status='RECORDED',heading_difference_deg=rows[-1]['heading_rmse_deg']-float(old.iloc[0].heading_rmse_deg)))
     pd.DataFrame(rows).to_csv(a.out/'RESULTS.csv',index=False);pd.DataFrame(checks).to_csv(a.out/'CHECKS.csv',index=False)
     print('S2_CELL_DONE',cid,channel,bias,seed,flush=True)
 except Exception as e:
  errors.append(dict(cell=attempt,error=str(e),traceback=traceback.format_exc(),retry=False,affected_route_stopped=True))
 # Failed/unattempted rows retain the full locked denominator.
 present={(r['case'],r['channel'],r['bias'],r['seed'],r['arm']) for r in rows}
 for e in expected:
  if (e['case'],e['channel'],e['bias'],e['seed'],e['arm']) not in present:rows.append(dict(e,status='NOT_EXECUTED_AFTER_TECHNICAL_FAILURE'))
 for name,items in [('RESULTS',rows),('RF_ONLY_RESULTS',aux),('LOS_REFERENCE',refs),('CHECKS',checks)]:pd.DataFrame(items).to_csv(a.out/f'{name}.csv',index=False)
 for path in a.out.glob('*.csv'):
  if path.stat().st_size>20_000_000:errors.append(dict(error='CSV_EXCEEDS_20MB',file=path.name,retry=False))
 dump(a.out/'ERRORS.json',errors)
 dump(a.out/'MANIFEST.json',dict(task='S2_N2_GEOMETRY',route=a.route,technical='TECHNICAL_PASS' if not errors else 'ERROR_OR_INCOMPLETE',scientific='AGGREGATE_REQUIRED',actions_run_id=os.getenv('GITHUB_RUN_ID'),source_commit=os.getenv('GITHUB_SHA'),engine_sha256=ENGINE_SHA,sensor_lock_sha256=SENSOR_SHA,protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),model_sha256=sha(HERE/'TRAIN_PARAMS.json'),inputs=proof,metadata=metadata,n_expected=len(expected),n_valid=sum(r.get('status')=='TECHNICAL_PASS' for r in rows),outputs={str(p.relative_to(a.out)):sha(p) for p in a.out.rglob('*') if p.is_file() and p.name!='MANIFEST.json'}))
 if errors:raise SystemExit(1)
 print('S2_ROUTE_PASS',a.route,len(rows),flush=True)
if __name__=='__main__':main()
