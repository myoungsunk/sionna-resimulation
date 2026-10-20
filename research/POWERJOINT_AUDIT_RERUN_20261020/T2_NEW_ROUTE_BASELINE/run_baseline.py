"""Train old routes only; replay immutable new RF on full canonical motion clock."""
from pathlib import Path
import argparse,json,os,sys,traceback,hashlib
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;AUDIT=HERE.parent;SOURCE=AUDIT.parents[1];DATA=SOURCE.parent
sys.path.insert(0,str(AUDIT/'T1_MEMORY'));sys.path.insert(0,str(AUDIT));sys.path.insert(0,str(SOURCE/'research/CHAIN_HYPOTHESIS_20261019'))
from prepare_inputs import prepare_new_route,build_canonical_controls,BIAS_LEVELS
from unit_tests import load_engine
original_engine,_=load_engine(SOURCE)
import canonical_engine as engine
from replay import score,specifications
import run as original
from source_model import SourceFFD
def digest(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--route',required=True);p.add_argument('--route-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);(a.out/'traces').mkdir(exist_ok=True)
 rows=[];checks=[]
 try:
  prepared=prepare_new_route(a.route_root,a.route);t=prepared['motion_t'];truth=prepared['motion_truth'];ri=prepared['rf_motion_indices'];radio=np.zeros(len(t),bool);radio[ri]=True
  train=pd.read_csv(DATA/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz');train=train[train.channel=='full'].copy().reset_index(drop=True)
  raw=original.frozen_inputs();model=SourceFFD();target_frames=[];case_metadata=[]
  for rec in prepared['cases']:
   h=np.load(rec['full_path'],allow_pickle=False)
   if h.shape!=(len(ri),257,2,2):raise RuntimeError('NEW_H_SHAPE')
   frame=pd.concat([pd.DataFrame(original.extract(h[i:i+64,:,:,0],model.freqs)) for i in range(0,len(h),64)],ignore_index=True)
   frame['case']=rec['case_id'];frame['route']=a.route;frame['channel']='full';frame['pose_id']=prepared['rf_pose_ids']
   anchor={'A':[4.,0.,2.65],'B':[10.,0.,2.65],'O0':[5.,2.2,2.65]}[rec['anchor']]
   case=dict(id=rec['case_id'],anchor=anchor,mount_deg=45.,robot_z_m=.45)
   target_frames.append(frame);case_metadata.append((rec,case))
  target=pd.concat(target_frames,ignore_index=True);combined=pd.concat([train,target],ignore_index=True)
  mu,C,fit=original.fit_model(np,train,combined,original.site_weights(np,pd,train),'POWER_BIN_JOINT',original.GROUPS);nt=len(train)
  mp=original.fit_memory(train,mu[:nt],C[:nt],raw)
  (a.out/'TRAIN_PARAMS.json').write_text(json.dumps(dict(memory=mp,power=fit,train_input_sha256=digest(DATA/'reference_ae/PACKETS_SOURCE_LABELS.csv.gz'),training='all R2/R4/R5 only'),indent=2,default=str))
  offset=0
  for (rec,case),frame in zip(case_metadata,target_frames):
   nr=len(frame);mm=mu[nt+offset:nt+offset+nr];cc=C[nt+offset:nt+offset+nr];offset+=nr
   z=np.zeros((len(t),2));z[ri]=frame[['range_m','s_fp']].to_numpy();mu_motion=np.zeros_like(z);mu_motion[ri]=mm;C_motion=np.repeat(np.diag([.0068578637,.0081])[None],len(t),axis=0);C_motion[ri]=cc
   for seed in range(5):
    for label,bias in BIAS_LEVELS.items():
     controls,initial,sensor_receipt=build_canonical_controls(prepared,label,seed,SOURCE)
     specs=specifications(mp['tau_s'],mp['fraction']) if seed==0 else [dict(name='JOINT4',base='r0'),dict(name='POWER1',base='power')]
     specs=[dict(name='DR4',base='r0',skip_all=True)]+specs
     result=engine.run(t,controls,initial,z,mu_motion,C_motion,np.zeros(len(t)),case,model,specs,radio_mask=radio)
     names=list(result['names']);scorer_max=0.
     for j,name in enumerate(names):
      for scope,mask in [('motion',t>=30),('radio',radio&(t>=30))]:
       values=score(result['state'][:,j],result['cov'][:,j],truth,bias,mask);ind=score(result['state'][:,j],result['cov'][:,j],truth,bias,mask,scalar=True)
       scorer_max=max(scorer_max,max(abs(values[k]-ind[k]) for k in values))
       rows.append(dict(case=case['id'],bias=label,seed=seed,arm=name,scope=scope,n=int(mask.sum()),**values))
     if scorer_max>1e-9:raise RuntimeError('NEW_INDEPENDENT_SCORER')
     j=names.index('POWER1');check=dict(case=case['id'],bias=label,seed=seed,independent_scorer_max=scorer_max,no_nonradio_updates=int(result['accepted'][~radio].sum())==0)
     if not check['no_nonradio_updates']:raise RuntimeError('NONRADIO_UPDATE')
     checks.append(check)
     if seed==0:
      result.update(truth_for_offline_scoring_only=truth,observations=z,mu_input=mu_motion,C_input=C_motion,radio_mask=radio,radio_pose_ids=prepared['rf_pose_ids'],controls_dt=controls['dt_s'],controls_ds=controls['ds_odom'],controls_dyaw=controls['dtheta_gyro'],initial_pose=initial,los_exists_at_radio=rec['los_exists'])
      np.savez_compressed(a.out/'traces'/f"{case['id']}_{label}.npz",**result)
     pd.DataFrame(rows).to_csv(a.out/'ALL_METRICS.csv',index=False)
     pd.DataFrame(checks).to_csv(a.out/'CHECKS.csv',index=False)
     print('NEW_BASELINE_DONE',case['id'],label,seed,flush=True)
  df=pd.DataFrame(rows);df[(df.seed==0)&(df.scope=='motion')&df.arm.isin(['DR4','JOINT4','POWER1'])].to_csv(a.out/'BASELINE.csv',index=False)
  df[(df.seed==0)&(df.scope=='motion')].to_csv(a.out/'T1_NEW_CANONICAL_RESULTS.csv',index=False)
  df[df.scope=='motion'].groupby(['case','bias','arm']).heading_rmse_deg.agg(['min','max']).reset_index().to_csv(a.out/'MOTION_NOISE_REPEAT_RANGE.csv',index=False)
  (a.out/'MANIFEST.json').write_text(json.dumps(dict(technical='TECHNICAL_PASS',scientific='NOT_ESTABLISHED',route=a.route,inputs=prepared['metadata'],sensor=sensor_receipt,sensor_settings_sha256=digest(HERE/'PROTOCOL_LOCK.json'),engine_sha256=digest(AUDIT/'canonical_engine.py'),actions_run_id=os.getenv('GITHUB_RUN_ID'),artifact_id=None,training='all old routes; no new target labels used',n_rows=len(rows)),indent=2))
 except Exception as e:
  (a.out/'ERRORS.json').write_text(json.dumps([dict(error=str(e),traceback=traceback.format_exc(),retry='requires cause review; no parameter tuning')],indent=2));raise
if __name__=='__main__':main()
