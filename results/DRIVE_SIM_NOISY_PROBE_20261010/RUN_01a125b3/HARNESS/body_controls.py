from pathlib import Path
import sys,json,time,hashlib,concurrent.futures,traceback,dataclasses
import numpy as np,pandas as pd
from scipy.stats import chi2
J=Path('/job');OLD=Path('/old');B=Path('/input/BLOCK_C');R=Path('/routes/source/results/DRIVE_SIM_20261007');sys.path.insert(0,str(OLD/'source/src'))
from qclean_uwb.drivesim import observation as O,sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
from qclean_uwb.drivesim.hs_lut import HsLut
P=json.loads((J/'BODY_CONTROL_PREREG.json').read_text());L=Path('/lut');meta=json.loads((L/'hs_lut_meta.json').read_text());mm=meta['meta'];lut=HsLut(dict(theta_deg=mm['theta_deg'],phi_deg=np.arange(mm['phi_deg'][0],mm['phi_deg'][1]+.01,mm['phi_deg'][2]),s=np.load(L/'hs_lut_2deg.npy')));freq=np.load(B/'freqs_hz.npy');OUT=J/'BODY_CONTROLS'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Recorder(F.SensorV2Filter):
 def scalar(self,z,h,H,R,key):
  self.last_H=H.copy()
  return super().scalar(z,h,H,R,key)
def casepack(case):
 old=case in {c['case'] for c in json.loads((B/'CASES.json').read_text())};route=case[:2];poses=json.loads((R/'S1/routes'/f'rf_poses_{route}.json').read_text());full=np.load(B/'FULL_RF'/f'H_{case}.npy',mmap_mode='r') if old else np.load(J/'NATIVE_FULL'/case/'H_full.npy',mmap_mode='r');los=np.load(B/f'H_LoS_{case}.npy',mmap_mode='r') if old else np.load(J/'NATIVE_LOS'/case/'H_LoS.npy',mmap_mode='r');groups=[];cur=[]
 for p in poses:
  if cur and (p['x'],p['y'])!=(cur[-1]['x'],cur[-1]['y']):groups.append(cur);cur=[]
  cur.append(p)
 if cur:groups.append(cur)
 return poses,full,los,[g for g in groups if len(g)>=5]
def schedule(delta):
 yaw=[0.];steps=[];packet=[]
 for target in [*delta,0.]:
  n=int(np.ceil(abs(target-yaw[-1])/np.radians(5)-1e-9))
  start=yaw[-1]
  for k in range(n):yaw.append(start+(target-start)*(k+1)/n)
  yaw.extend([target,target]);packet.append(len(yaw)-1)
 return np.arange(len(yaw))*.2,np.array(yaw),np.array(packet[:3],int)
def one(task,arms=None):
 case,gi,d,seed,snr=task;poses,full,los,groups=casepack(case);g=groups[gi];ids=np.array([g[i]['pose_id'] for i in [0,2,4]]);base=case.rsplit('_m',1)[0]+'_m0';oldp=OLD/'TRACES/main'/f'{base}_d{d}_s{seed}_A_stochastic_unknown.npz';a=np.load(oldp,allow_pickle=False);ix=np.flatnonzero((a['pose_id']==ids[0])&a['keep']&a['completed'])
 if not len(ix):return [{'case':case,'station':gi,'drift':d,'seed':seed,'snr':snr,'arm':'ALL','status':'NO_EVALUATION_PRIOR'}]
 k=int(ix[0]);x0=a['pre_rf_state'][k].copy();P0=a['pre_rf_cov'][k].copy();delta=V.wrap(np.radians([g[i]['yaw_body_deg']-g[0]['yaw_body_deg'] for i in [0,2,4]]));t,yaws,pi=schedule(delta);n=len(t);true=np.tile([g[0]['x'],g[0]['y'],np.radians(g[0]['yaw_body_deg'])],(n,1));true[:,2]=V.wrap(true[:,2]+yaws);ds=np.zeros(n);dy=np.r_[0,V.wrap(np.diff(yaws))];sc=V.SensorV2Config(level=d,condition='all')
 original_rng=V.rng
 # Preserve original static calibration draws, avoid replaying early trajectory noise into an already correlated prior.
 def probe_rng(s,stream):
  if stream=='drift':return original_rng(s,stream)
  return np.random.default_rng(np.random.SeedSequence([20261010,int(case[1]),0 if '_aA_' in case else 1,d,s,int(ids[0]),912,V.STREAMS[stream]]))
 V.rng=probe_rng
 try:inputs,evaluation=V.generate(t,ds,dy,sc,seed)
 finally:V.rng=original_rng
 var=O.noise_var_from_snr(snr);key=[20261010,int(case[1]),0 if '_aA_' in case else 1,d,seed,snr,int(ids[0]),811];rng=np.random.default_rng(np.random.SeedSequence(key));noise=np.sqrt(var/2)*(rng.standard_normal((3,257,2))+1j*rng.standard_normal((3,257,2)));hfull=np.asarray(full[ids]).copy();hlos=np.asarray(los[ids]).copy();hfull[:,:,:,0]+=noise;hlos[:,:,:,0]+=noise;obs=O.observe(hfull,freq,None,None,threshold=O.detection_threshold(var));obsl=O.observe(hlos,freq,None,None,threshold=O.detection_threshold(var));folder=OUT/case/f'g{gi}_d{d}_s{seed}_snr{snr}';folder.mkdir(parents=True)
 np.savez_compressed(folder/'ORACLE_EVAL_ONLY.npz',true_xypsi=true,true_body_yaw=true[:,2],**{'evaluation_'+key:val for key,val in evaluation.items()})
 np.savez_compressed(folder/'RF_PACKETS.npz',time_rf_s=t[pi],corresponding_state_index=pi,pose_id=ids,delta_measured_placeholder_status=np.array('see STATE_TRACE gyro integration; never true delta as inference input'),noise_variance=var,realized_snr_db=O.realised_snr_db(np.asarray(full[ids]),var),P1_firstpath=obs['power'][:,0],P2_firstpath=obs['power'][:,1],s_firstpath=obs['s'],range_m=obs['range_m'],selected_tap=obs['index'],detect=obs['detected'],s_los=obsl['s'],range_los=obsl['range_m'])
 rows=[];anchor=(4. if '_aA_' in case else 10.,0.,2.65);mount=45 if case.endswith('m45') else 0
 for arm in (arms if arms is not None else ['A','B','C','D','G1','G2']):
  cfg=FilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_range=arm!='A',use_s=arm not in ['A','B'],anchor_xyz=anchor,mount_deg=mount,robot_z=.45,bias_rw_std=0.,range_offset=meta['range_bias']['mean_m'],noise_var_cir_tap=6*var,noise_var_bin=var)
  f=Recorder(cfg,lut,x0,P0);z={'t_s':t,'dt_s':inputs['dt_s'],'phase':np.array(['settle' if dy[j]==0 else ('return' if j>pi[-1] else 'rotate') for j in range(n)]),'state_index':np.arange(n),'source_Tnone_index':np.array(k),'initial_state':x0,'initial_prior':P0,'commanded_w_rad_s':np.where(inputs['dt_s']>0,dy/np.where(inputs['dt_s']>0,inputs['dt_s'],1),0),'commanded_v_m_s':np.zeros(n),'packet_indices':pi,'gyro_integrated_delta_rad':np.cumsum(inputs['dtheta_gyro']),'raw_encoder_L_rad':inputs['encoder_angle_rad'][:,0],'raw_encoder_R_rad':inputs['encoder_angle_rad'][:,1],'wheel_increment_L_m':inputs['wheel_nominal_increment_m'][:,0],'wheel_increment_R_m':inputs['wheel_nominal_increment_m'][:,1]}
  for key,value in inputs.items():z['sensor_'+key]=value
  for stage in ['pred_before_odom','after_odom','after_range','before_RF','after_RF']:z['x_'+stage]=np.full((n,6),np.nan);z['P_'+stage]=np.full((n,6,6),np.nan)
  for key,shape in [('F',(6,6)),('G',(6,3)),('Q_input',(3,3)),('C_odom',(6,)),('H_odom',(6,)),('H_range',(6,)),('H_s',(6,))]:z[key]=np.zeros((n,)+shape)
  for m in ['odom','range','s']:
   for key in ['innovation','S','R','NIS']:z[m+'_'+key]=np.full(n,np.nan)
   z[m+'_status']=np.full(n,'not_run',dtype='U32')
  last=-1;error=''
  try:
   for j in range(n):
    if j:
     xp,pp=f.mean_cov();rec=f.step(inputs['ds_odom'][j],inputs['dtheta_gyro'][j],inputs['dtheta_odom'][j],inputs['dt_s'][j]);pr,Fm,G=F.transition(xp,inputs['ds_odom'][j],inputs['dtheta_gyro'][j],inputs['dt_s'][j],cfg.wheel_base);z['x_pred_before_odom'][j]=pr;z['P_pred_before_odom'][j]=Fm@pp@Fm.T+G@rec['Q']@G.T
     for key,src in [('F','F'),('G','G'),('Q_input','Q'),('C_odom','C'),('H_odom','H')]:z[key][j]=rec[src]
     for key in ['innovation','S','R','status']:z['odom_'+key][j]=rec[key]
     if rec['S']>0:z['odom_NIS'][j]=rec['innovation']**2/rec['S']
    else:z['x_pred_before_odom'][j]=x0;z['P_pred_before_odom'][j]=P0;z['odom_status'][j]='initial'
    z['x_after_odom'][j],z['P_after_odom'][j]=f.mean_cov()
    obs_i=int(np.flatnonzero(pi==j)[0]) if j in pi else -1;enabled=obs_i>=0 and arm!='A' and (arm not in ['G1','G2'] or obs_i<(1 if arm=='G1' else 2))
    for m in ['range','s']:
     chosen=obsl if arm=='C' and m=='s' else obs
     status='not_scheduled'
     if enabled:
      status='disabled' if m=='s' and not cfg.use_s else 'missing'
      if (m=='range' or cfg.use_s) and chosen['detected'][obs_i]:
       out=f.range_record(chosen['range_m'][obs_i]) if m=='range' else f.s_record(chosen['s'][obs_i],chosen['power'][obs_i]);status=out[3]
       for key,value in zip(['innovation','R','S'],out[:3]):z[m+'_'+key][j]=value
       if out[2]>0:z[m+'_NIS'][j]=out[0]**2/out[2]
       if out[3]!='undefined_geometry':z['H_'+m][j]=f.last_H
     z[m+'_status'][j]=status
     if m=='range':z['x_after_range'][j],z['P_after_range'][j]=f.mean_cov();z['x_before_RF'][j]=z['x_after_range'][j];z['P_before_RF'][j]=z['P_after_range'][j]
    z['x_after_RF'][j],z['P_after_RF'][j]=f.mean_cov();diagn=F.covariance_diagnostic(z['P_after_RF'][j],np.linalg.norm(P0,2))
    if not diagn['valid']:raise FloatingPointError(str(diagn))
    last=j
  except Exception as e:error=str(e);z['failure_traceback']=np.array(traceback.format_exc())
  z['error']=np.array(error);z['last_valid_sample']=np.array(last);z['P_eigenvalues']=np.array([np.linalg.eigvalsh(p) if np.isfinite(p).all() else np.full(6,np.nan) for p in z['P_after_RF']]);z['yaw_body_est_at_packet_rad']=z['x_before_RF'][pi,2];z['delta_probe_measured_rad']=z['gyro_integrated_delta_rad'][pi];np.savez_compressed(folder/f'STATE_TRACE_{arm}.npz',**z)
  if last>=0:
   e=true[last]-z['x_after_RF'][last,:3];e[2]=V.wrap(e[2]);pv=z['P_after_RF'][last,:3,:3];nees=float(e@np.linalg.solve(pv,e)) if np.linalg.eigvalsh(pv).min()>0 else np.nan
  else:e=np.full(3,np.nan);nees=np.nan
  row=dict(case=case,station=gi,drift=d,seed=seed,snr=snr,arm=arm,status='FAILED' if error else 'COMPLETED',error=error,last_valid_sample=last,duration_s=float(t[-1]),heading_abs_deg=float(abs(np.degrees(e[2]))),pos_error_m=float(np.linalg.norm(e[:2])),nees_pose_df3=nees,pose_coverage95=bool(nees<=chi2.ppf(.95,3)) if np.isfinite(nees) else None,heading_coverage95=bool(abs(e[2])<=1.95996398454*np.sqrt(z['P_after_RF'][last,2,2])) if last>=0 else None,mode=P['mode'],sensor_cfg=dataclasses.asdict(sc),filter_cfg=dataclasses.asdict(cfg),prior_source_sha256=sha(oldp))
  for m in ['range','s']:
   valid=np.isfinite(z[m+'_NIS']);accepted=valid&(z[m+'_status']=='applied');row[m+'_nis_pre_gate']=float(np.mean(z[m+'_NIS'][valid])) if valid.any() else None;row[m+'_nis_accepted']=float(np.mean(z[m+'_NIS'][accepted])) if accepted.any() else None;row[m+'_reject_rate']=float(np.mean(z[m+'_status'][valid]=='rejected')) if valid.any() else None
  folder.joinpath(f'MANIFEST_{arm}.json').write_text(json.dumps(row,indent=2));rows.append({key:value for key,value in row.items() if key not in ['filter_cfg','sensor_cfg']})
 return rows
if __name__=='__main__':
 assert json.loads((J/'NATIVE_FULL_STATUS.json').read_text())['state']=='COMPLETED';assert json.loads((J/'NATIVE_LOS_STATUS.json').read_text())['state']=='COMPLETED';OUT.mkdir(exist_ok=False);start=time.time();cases=[f'{r}_{a}_m{m}' for r in ['R2','R4','R5'] for a in ['aA','aB'] for m in [0,45]];tasks=[]
 for case in cases:
  for gi in range(len(casepack(case)[3])):
   for d in range(3):
    for seed in range(5):
     for snr in [30,10]:tasks.append((case,gi,d,seed,snr))
 rows=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=24) as ex:
  for out in ex.map(one,tasks,chunksize=3):rows.extend(out)
 df=pd.DataFrame(rows);df.to_csv(J/'10_PAIRED_FILTER_RESULTS.csv',index=False);(J/'BODY_CONTROL_STATUS.json').write_text(json.dumps({'state':'COMPLETED' if not (df.status=='FAILED').any() else 'PARTIAL_FAILED','tasks':len(tasks),'executed_runs':int((df.status!='NO_EVALUATION_PRIOR').sum()),'missing_prior_tasks':int((df.status=='NO_EVALUATION_PRIOR').sum()),'failure_runs':int((df.status=='FAILED').sum()),'seconds':time.time()-start,'mode':P['mode'],'G3_alias_of_D':True,'full_route_reintegration':'NOT_RUN','F_and_H_mixture':'BLOCKED_CROSS_TIME_COVARIANCE_NOT_VALIDATED','scientific_PASS':False},indent=2));print('body controls completed',len(df),flush=True)
