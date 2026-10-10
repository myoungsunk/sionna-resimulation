from pathlib import Path
import sys,json,hashlib,time,concurrent.futures
import numpy as np,pandas as pd
J=Path('/job'); OLD=Path('/old'); B=Path('/input/BLOCK_C'); R=Path('/routes/source/results/DRIVE_SIM_20261007'); S2=R/'SNOWBALL_ROUTES_01a11669/S2'
sys.path.insert(0,str(OLD/'source/src'))
from qclean_uwb.drivesim.filter_v2 import transition,covariance_diagnostic
OUT=J/'RAW_BACKFILL';OUT.mkdir(exist_ok=False)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def groups(case):
 a=json.loads((B/case/'SAMPLES.json').read_text());g=[];cur=[]
 for x in a:
  if cur and (cur[-1]['x'],cur[-1]['y'])!=(x['x'],x['y']):g.append(cur);cur=[]
  cur.append(x)
 if cur:g.append(cur)
 return [x for x in g if len(x)>=5]
def one(task):
 case,d,seed,arm=task;p=OLD/'TRACES'/('E' if arm=='E' else 'main')/f'{case}_d{d}_s{seed}_{arm}_stochastic_unknown.npz'
 if not p.exists():return {'case':case,'drift':d,'seed':seed,'arm':arm,'status':'RAW_MISSING'}
 a=np.load(p,allow_pickle=False);meta=json.loads(p.with_suffix('.json').read_text());cfg=meta['filter_config'];keys=[];idx=[];stations=[];statuses=[]
 for gi,g in enumerate(groups(case)):
  # all three RF poses get explicit timeline availability, not fabricated priors
  for j in [0,2,4]:
   pid=g[j]['pose_id'];ix=np.flatnonzero(a['pose_id']==pid)
   if not len(ix):keys.append({'station':gi,'probe_index':j,'pose_id':pid,'status':'NOT_IN_TNONE'});continue
   for k in ix:
    st='AVAILABLE' if a['keep'][k] and a['completed'][k] else ('OUTSIDE_MASK' if not a['keep'][k] else 'INCOMPLETE')
    keys.append({'station':gi,'probe_index':j,'pose_id':pid,'state_index':int(k),'status':st});idx.append(int(k));stations.append(gi);statuses.append(st)
 ids=np.array(idx,int);n=len(ids);z={'source_state_index':ids,'station_id':np.array(stations,int),'status':np.array(statuses),'initial_state':a['initial_state'],'initial_prior':a['initial_prior']}
 for key in a.files:
  v=a[key]
  if v.ndim and v.shape[0]==len(a['t']):z[key]=v[ids]
 for old,new in [('pre_rf_state','x_after_odom'),('pre_rf_cov','P_after_odom'),('post_range_state','x_after_range'),('post_range_cov','P_after_range'),('est','x_after_RF'),('cov6','P_after_RF')]:z[new]=a[old][ids]
 z['x_before_RF']=z['x_after_range'].copy();z['P_before_RF']=z['P_after_range'].copy()
 z['x_pred_before_odom']=np.empty((n,6));z['P_pred_before_odom']=np.empty((n,6,6));maxF=maxG=0.;bad=0
 for j,k in enumerate(ids):
  if k==0:z['x_pred_before_odom'][j]=a['initial_state'];z['P_pred_before_odom'][j]=a['initial_prior']
  else:
   x,F,G=transition(a['est'][k-1],float(a['ds'][k]),float(a['gyro'][k]),float(a['sensor_dt_s'][k]),cfg['wheel_base']/(1+cfg['known_wheelbase_error']))
   maxF=max(maxF,float(abs(F-a['input_F'][k]).max()));maxG=max(maxG,float(abs(G-a['input_G'][k]).max()))
   z['x_pred_before_odom'][j]=x;z['P_pred_before_odom'][j]=F@a['cov6'][k-1]@F.T+G@a['input_Q'][k]@G.T
  for key in ['P_pred_before_odom','P_after_odom','P_after_range','P_before_RF','P_after_RF']:
   P=z[key][j];bad+=not covariance_diagnostic(P,float(np.linalg.norm(a['initial_prior'],2)))['valid']
 assert maxF<=1e-12 and maxG<=1e-12 and bad==0,(p,maxF,maxG,bad)
 # original power is per-port, preserve exact receiver convention
 if 'observation_power' in z:z['P1_firstpath']=z['observation_power'][:,0];z['P2_firstpath']=z['observation_power'][:,1]
 z['derived_prediction']=np.array(True);z['oracle_namespace_notice']=np.array('truth and evaluation_* are OFFLINE_EVAL_ONLY; never estimator inputs')
 target=OUT/f'{case}_d{d}_s{seed}_{arm}.npz';np.savez_compressed(target,**z)
 target.with_suffix('.json').write_text(json.dumps({'source':str(p),'source_sha256':sha(p),'metadata_source_sha256':sha(p.with_suffix('.json')),'keys':keys,'filter_config':cfg,'generator':meta['generator'],'prediction':'DERIVED_FROM_PREVIOUS_POSTERIOR_AND_MEASURED_INPUTS','before_RF_mapping':'exact alias of after-range, no intervening update','original_fields_preserved':True},indent=2))
 return dict(case=case,drift=d,seed=seed,arm=arm,status='COMPLETED',rows=n,keys=len(keys),available=sum(s=='AVAILABLE' for s in statuses),outside=sum(s=='OUTSIDE_MASK' for s in statuses),not_in_tnone=sum(k['status']=='NOT_IN_TNONE' for k in keys),source_sha256=sha(p),output_sha256=sha(target),output_bytes=target.stat().st_size,max_F_diff=maxF,max_G_diff=maxG,cov_invalid=bad)
if __name__=='__main__':
 t=time.time();cases=json.loads((B/'CASES.json').read_text());matrix=[]
 for route in ['R2','R4','R5']:
  samples=R/'S1/routes'/f'rf_poses_{route}.json';poses=json.loads(samples.read_text())
  for anchor in ['aA','aB']:
   for mount in [0,45]:
    case=f'{route}_{anchor}_m{mount}';p=S2/f'H_{case}.npy';m=S2/f'H_{case}.manifest.json';q=json.loads(m.read_text());h=sha(p);assert h==q['outputs'][0]['sha256'];assert sha(samples)==q['inputs'][0]['sha256'];assert np.load(p,mmap_mode='r').shape==(len(poses),257,2,2)
    isold=case in {c['case'] for c in cases};matrix.append(dict(case=case,full_status='LEGACY_METHOD_B_PRESENT_HASH_VERIFIED',full_source=str(p),full_sha256=h,full_bytes=p.stat().st_size,full_method=q['command'],native_full_new_status='NOT_RUN',los_status='EXISTING' if isold else 'MISSING_NATIVE_LOS',poses=len(poses),rf_pose_sha256=sha(samples)))
 (J/'MOUNT_CASE_MATRIX.json').write_text(json.dumps(matrix,indent=2))
 tasks=[(c['case'],d,s,a) for c in cases for d in range(3) for s in range(50) for a in 'ABCDE']
 with concurrent.futures.ProcessPoolExecutor(max_workers=24) as e:rows=list(e.map(one,tasks,chunksize=5))
 pd.DataFrame(rows).to_csv(J/'RAW_BACKFILL_INDEX.csv',index=False)
 result={'state':'COMPLETED' if all(r['status']=='COMPLETED' for r in rows) else 'PARTIAL','runs':len(rows),'rows':sum(r.get('rows',0) for r in rows),'available_rows':sum(r.get('available',0) for r in rows),'outside_rows':sum(r.get('outside',0) for r in rows),'not_in_tnone':sum(r.get('not_in_tnone',0) for r in rows),'output_bytes':sum(r.get('output_bytes',0) for r in rows),'cov_invalid':sum(r.get('cov_invalid',0) for r in rows),'seconds':time.time()-t,'full_trajectory_raw':'preserved remote original; this delivery is station-matched full-P6 only','not_claimed':'independent covariance derivation; only stored F/G equivalence and original PSD guard checked','scientific_PASS':False}
 (J/'01_BACKFILL_P6_CHECK.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
