"""Locked new-route test, no parameter selection from new observations or outcomes.
Physical sensor controls at full .25s motion cadence; RF only at provided samples.
Fixed old R2-heldout POWER learner (train R4/R5 M0) and its memory parameters.
All pose truth used only for control simulation and offline scoring/LoS parity.
"""
from pathlib import Path
import numpy as np,pandas as pd,json,sys,inspect,hashlib,traceback
ROOT=Path.cwd();SOURCE=ROOT/'source';OLD=ROOT/'main_result';NEW=ROOT/'heldout';POSE=ROOT/'poses';OUT=ROOT/'external_out';OUT.mkdir(exist_ok=True);(OUT/'traces').mkdir(exist_ok=True)
sys.path.insert(0,str(SOURCE/'research/CHAIN_HYPOTHESIS_20261019'))
import run as setup
import engine
from scipy.spatial import cKDTree
from r2_bias_replay import build_positive_bias_controls,BIAS_LEVELS
from features import extract,GROUPS
from n4b_rf_errors import fit_model,site_weights,feature_splits
from source_model import SourceFFD
from core import wrap

# The sole engine adaptation skips measurement updates at absent RF times.
# It neither changes prediction nor imputes a synthetic RF observation.
text=inspect.getsource(engine.run)
needle='        xp[i]=x;pp[i]=P\n'
assert text.count(needle)==1
replacement=needle+'''        if not np.isfinite(z[i]).all():
            xs[i]=x;ps[i]=P
            continue
'''
text=text.replace(needle,replacement).replace('def run(','def run_missing_rf(',1)
namespace=vars(engine).copy();exec(compile(text,'engine_missing_rf.py','exec'),namespace)
run_missing=namespace['run_missing_rf'];(OUT/'engine_missing_rf.py').write_text(text)
frames=pd.read_csv(OLD/'PACKETS_SOURCE_LABELS.csv.gz');full=frames[frames.channel=='full'].reset_index(drop=True)
fold=next(v for v in feature_splits(np,full) if v[0]=='R2');train=full.loc[fold[1]].copy()
mem=next(v for v in json.loads((OLD/'MEMORY_TRAIN_PARAMS.json').read_text()) if v['held_route']=='R2')
chosen=['JOINT4','POWER1','POWER_INDEPENDENT','POWER_MEMORY','POWER_MEMORY_NO_CROSS','POWER_SR4']
specs=[s for s in engine.specifications(None,mem) if s['name'] in chosen]
lock={'models':chosen,'training_routes':['R4','R5'],'training_mounts':[0],'training_rows':len(train),'fold':'Original R2-heldout (with original R2 site-exclusion); not refit with new tests','memory':mem,'selection_used_test_performance':False,'source_model_sha':'4b82e9801a1e065593fdd67a0f3ebd721ba29848','main_candidate_commit':'736d25092a36e4d1ccf33661d5d1f740260cfbeb','new_sensor_controls':'synthetic from original full .25s pose/time, generated separately for evaluation; no GT enters inference','radio_policy':'update only at provided RF pose_id; no CIR interpolation'}
(OUT/'EXTERNAL_TEST_LOCK.json').write_text(json.dumps(lock,indent=2));print('EXTERNAL_LOCK',json.dumps(lock),flush=True)
model=SourceFFD();rows=[];qas=[];errors=[]
case_dirs=sorted(p for p in NEW.glob('**/CASES/*') if p.is_dir() and (p/'H_FULL.npy').exists())
if len(case_dirs)!=8:raise RuntimeError('EXPECTED_8_NEW_ROUTE_ANCHOR_CASES:'+str(len(case_dirs)))
for folder in case_dirs:
 cid=folder.name;route,anchor=cid.split('_')[:2]
 try:
  radio=pd.read_csv(folder/'RADIO_POSE.csv');pose_candidates=list(POSE.rglob(route+'_ROUTE_POSE.csv'))
  if len(pose_candidates)!=1:raise RuntimeError('FULL_POSE_NOT_UNIQUE')
  motion=pd.read_csv(pose_candidates[0]);t=motion.t_s.to_numpy();ids=radio.pose_id.to_numpy(int)
  if not (np.diff(t)>0).all() or motion.pose_id.duplicated().any():raise RuntimeError('MOTION_CLOCK')
  mapping=pd.Series(np.arange(len(t)),index=motion.pose_id);ix=mapping.loc[ids].to_numpy(int)
  posmatch=motion.set_index('pose_id').loc[ids]
  for c in ['t_s','x_m','y_m','z_m','yaw_body_deg','yaw_antenna_deg']:
   if np.max(abs(posmatch[c].to_numpy()-radio[c].to_numpy()))>1e-6:raise RuntimeError('RADIO_POSE_MISMATCH:'+c)
  mount_delta=wrap(np.radians(radio.yaw_antenna_deg-radio.yaw_body_deg))-np.pi/4
  if abs(mount_delta).max()>1e-7:raise RuntimeError('MOUNT_NOT45')
  f=np.load(folder/'FREQUENCIES_HZ.npy');H=np.load(folder/'H_FULL.npy');L=np.load(folder/'H_DIRECT_LOS.npy');los=np.load(folder/'LOS_EXISTS.npy').astype(bool)
  if H.shape!=(len(radio),257,2,2) or L.shape!=H.shape or not np.isfinite(H).all():raise RuntimeError('RF_SCHEMA')
  if not np.array_equal(f,model.freqs):raise RuntimeError('FREQUENCY_GRID')
  xyz={'A':[4.,0.,2.65],'B':[10.,0.,2.65],'O0':[5.,2.2,2.65]}[anchor]
  case={'id':cid,'anchor':xyz,'mount_deg':45.,'robot_z_m':float(radio.z_m.iloc[0])}
  truth=np.c_[motion.x_m,motion.y_m,np.radians(motion.yaw_body_deg)];truth4=np.c_[truth,np.zeros(len(t))]
  q=pd.DataFrame(extract(H[:,:,:,0],f));ql=pd.DataFrame(extract(L[:,:,:,0],f))
  predicted=[]
  for st in range(0,len(ix),48):predicted.append(model.batch(truth4[ix[st:st+48]],case,gradient=False)[0])
  pred=np.concatenate(predicted);smatch=float(np.max(abs(ql.s_fp.to_numpy()[los]-pred[los,1]))) if los.any() else None
  # Source s fixture tolerance; failure remains a case-level issue, not an all-run stop.
  if smatch is not None and smatch>1e-3:raise RuntimeError('SOURCE_LOS_S_PARITY:'+str(smatch))
  mu,C,fit=fit_model(np,train,q,site_weights(np,pd,train),'POWER_BIN_JOINT',GROUPS)
  Z=np.full((len(t),2),np.nan);Z[ix]=np.c_[q.range_m,q.s_fp]
  M=np.zeros((len(t),2));CC=np.repeat(C[:1],len(t),axis=0)
  M[ix]=mu;CC[ix]=C
  # Carry only observed parameters forward between RF packets (never interpolate).
  latest=0
  for k in range(len(t)):
   if latest+1<len(ix) and ix[latest+1]<=k:latest+=1
   M[k]=mu[latest];CC[k]=C[latest]
  qas.append({'case':cid,'motion_frames':len(t),'rf_frames':len(ix),'los_available':int(los.sum()),'source_s_max':smatch,'control_dt_median':float(np.median(np.diff(t))),'RF_H_SHA256':hashlib.sha256((folder/'H_FULL.npy').read_bytes()).hexdigest()})
  for label,bias in BIAS_LEVELS.items():
   controls,initial=build_positive_bias_controls(t,truth,label,0)
   result=run_missing(t,controls,initial,Z,M,CC,np.zeros(len(t)),case,model,specs)
   names=list(result['names']);j=names.index('POWER1');k=names.index('POWER_INDEPENDENT');dx=float(np.max(abs(result['state'][:,j,:4]-result['state'][:,k,:4])))
   if dx>1e-7:raise RuntimeError('NO_MEMORY_PARITY_EXTERNAL:'+str(dx))
   e=wrap(result['state'][:,:,2]-truth[:,None,2]);sigma=np.sqrt(result['cov'][:,:,2,2]);masks=[('evaluation',t>=30),('whole',np.ones(len(t),bool)),('straight',(t>=30)&(motion.phase.to_numpy()=='STRAIGHT')),('turn_scan',(t>=30)&(motion.phase.to_numpy()!='STRAIGHT'))]
   for jj,name in enumerate(names):
    for scope,mask in masks:
     if not mask.any():continue
     ee=e[mask,jj];vv=sigma[mask,jj]**2;ne=ee*ee/vv
     rows.append({'case':cid,'environment':'office' if route.startswith('O') else 'corridor','bias_dps':bias,'method':str(name),'scope':scope,'n':int(mask.sum()),'heading_rmse_deg':float(np.degrees(np.sqrt(np.mean(ee*ee)))),'signed_heading_deg':float(np.degrees(ee.mean())),'heading_nees':float(ne.mean()),'heading95':float(np.mean(ne<=3.841458820694124)),'sigma_rms_deg':float(np.degrees(np.sqrt(vv.mean()))),'heading_nll_rad':float(np.mean(.5*(np.log(2*np.pi*vv)+ne))),'bias_rmse_dps':float(np.sqrt(np.mean((np.degrees(result['state'][mask,jj,3])-bias)**2))),'rf_accepted_fraction':float(result['accepted'][ix,jj].mean())})
   result.update(truth_for_offline_scoring_only=truth,pose_id=motion.pose_id.to_numpy(),rf_indices=ix,observations=Z,controls_ds=controls['ds_odom'],controls_dyaw=controls['dtheta_gyro'],controls_dt=controls['dt_s'])
   np.savez_compressed(OUT/'traces'/f'{cid}_{label}.npz',**result)
   pd.DataFrame(rows).to_csv(OUT/'EXTERNAL_SCORES.csv',index=False)
   print('EXTERNAL_RESULT',cid,label,json.dumps([r for r in rows if r['case']==cid and r['bias_dps']==bias and r['scope']=='evaluation']),flush=True)
 except Exception as e:
  errors.append({'case':cid,'error':repr(e),'traceback':traceback.format_exc()});print('EXTERNAL_CASE_FAILED_CONTINUE',cid,repr(e),flush=True)
 pd.DataFrame(qas).to_csv(OUT/'EXTERNAL_INPUT_QA.csv',index=False);(OUT/'EXTERNAL_ERRORS.json').write_text(json.dumps(errors,indent=2))
s=pd.DataFrame(rows);evaluation=s[s.scope=='evaluation'];evaluation.to_csv(OUT/'EXTERNAL_EVALUATION.csv',index=False)
(OUT/'EXTERNAL_SUMMARY.json').write_text(json.dumps({'cases_expected':8,'cases_scored':int(evaluation['case'].nunique()) if len(evaluation) else 0,'bias_conditions_expected':32,'method_condition_rows':len(evaluation),'errors':errors,'candidate_tuned_on_new_data':False,'same_corridor_routes_vs_one_office_scene':'not five independent physical scenes'},indent=2))
manifest=[]
for p in sorted(OUT.rglob('*')):
 if p.is_file():
  with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
  manifest.append({'path':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':h})
(OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2));print('EXTERNAL_FINAL',json.dumps(json.loads((OUT/'EXTERNAL_SUMMARY.json').read_text())),flush=True)
