from pathlib import Path
import sys,json,time,traceback,concurrent.futures,dataclasses
import numpy as np,pandas as pd
from scipy.stats import chi2
J=Path('/job');sys.path.insert(0,str(J/'source/src'))
from qclean_uwb.drivesim import sensor_v2 as V,filter_v2 as F
from qclean_uwb.drivesim.filters import FilterConfig
from qclean_uwb.drivesim.hs_lut import HsLut,s_model
T=Path('/routes/source/results/DRIVE_SIM_20261007/S1/routes');B=Path('/input/BLOCK_C');L=Path('/lut')
CASES=json.loads((B/'CASES.json').read_text());BYCASE={c['case']:c for c in CASES}
meta=json.loads((L/'hs_lut_meta.json').read_text());mm=meta['meta']
# phi metadata is [start,last,step], last is INCLUDED.
LUT=HsLut(dict(theta_deg=mm['theta_deg'],phi_deg=np.arange(mm['phi_deg'][0],mm['phi_deg'][1]+.01,mm['phi_deg'][2]),s=np.load(L/'hs_lut_2deg.npy')))
class Recorder(F.SensorV2Filter):
 def scalar(self,z,h,H,R,key):
  if key=='s':R*=getattr(self,'reliability_multiplier',1.)
  self.last_scalar=dict(z=float(z),h=float(h),H=H.copy(),R=float(R),x=self.comps[0].x.copy(),P=self.comps[0].P.copy())
  return F.SensorV2Filter.scalar(self,z,h,H,R,key)

def configure(case,level,use_range=False,use_s=False,known=0.):
 c=BYCASE[case]
 return FilterConfig(model_version='sensor-v2',kind='ekf',s_mode='direct',use_range=use_range,use_s=use_s,anchor_xyz=tuple(c['anchor_xyz']),mount_deg=c['mount_deg'],robot_z=c['robot_z'],bias_rw_std=0.,known_wheelbase_error=known,range_offset=meta['range_bias']['mean_m'])
def single(task):
 case,level,seed,arm,initial,wb,phase=task;c=BYCASE[case];route=case[:2];motion=np.load(J/'OUTPUT'/f'MOTION_{route}_legacy-euler.npz');t=motion['t'];truth=motion['pose'];ids=motion['pose_id'];n=len(t)
 cfgsensor=V.SensorV2Config(level=level,condition='all');inputs,evaluation=V.generate(t,motion['ds'],motion['dtheta'],cfgsensor,seed)
 known=float(evaluation['true_parameters'][3]) if wb=='known' else 0.
 cfg=configure(case,level,arm!='A',arm in ['C','D','E'],known);x0=np.r_[truth[0],0.,0.,0.]
 if initial=='stochastic':x0[:3]+=V.rng(seed,'initial').normal(size=3)*np.array(cfg.p0_std[:3])
 obsfull=np.load(J/'OBS'/f'{case}_full.npz');obslos=np.load(J/'OBS'/f'{case}_los.npz');obs={k:obsfull[k][ids] for k in ['s','power','range_m','detected']}
 if arm=='C':obs['s']=obslos['s'][ids];obs['power']=obslos['power'][ids]
 f=Recorder(cfg,LUT,x0);initialP=f.comps[0].P.copy();scale=float(np.linalg.norm(initialP,2));df=pd.read_csv(T/f'timeline_{route}_Tnone.csv');flag=df.turn_phase.to_numpy(bool)
 arr={'t':t,'truth':truth,'pose_id':ids,'keep':t>=30,'initial_state':x0,'initial_prior':initialP,'est':np.full((n,6),np.nan),'cov6':np.full((n,6,6),np.nan),'pre_rf_state':np.full((n,6),np.nan),'pre_rf_cov':np.full((n,6,6),np.nan),'post_range_state':np.full((n,6),np.nan),'post_range_cov':np.full((n,6,6),np.nan),'nees':np.full(n,np.nan),'pose_error':np.full((n,3),np.nan),'cov_eigenvalues':np.full((n,6),np.nan),'completed':np.zeros(n,bool),'turn_phase':flag}
 for key in ['gyro','ds','wheel_yaw']:arr[key]=inputs[{'gyro':'dtheta_gyro','ds':'ds_odom','wheel_yaw':'dtheta_odom'}[key]]
 for key,val in inputs.items():arr['sensor_'+key]=val
 for key,val in evaluation.items():arr['evaluation_'+key]=val
 for key in ['s','power','range_m','detected']:arr['observation_'+key]=obs[key]
 for m in ['odom','range','s']:
  for k,sh in [('innovation',()),('S',()),('R',()),('h',()),('H',(6,)),('C',(6,))]:arr[m+'_'+k]=np.full((n,)+sh,np.nan)
  arr[m+'_status']=np.full(n,'not_run',dtype='U32')
 for key,shape in [('input_Q',(3,3)),('input_F',(6,6)),('input_G',(6,3))]:arr[key]=np.zeros((n,)+shape)
 error='';last=-1;parity={};start=time.time()
 if arm=='E':
  import e_policy as E
  pack,X,ki=E.prepare(case,ids,obs,inputs);arr['q_good_5deg']=np.full(n,np.nan);arr['rf_available']=np.zeros(n,bool);arr['R_multiplier']=np.ones(n);arr['classifier_id']=np.array(case[:2]+'_DPK_leave_route_out')
 try:
  for k in range(n):
   rec=None
   if k:
    rec=f.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k])
    for key in ['innovation','S','R','H','C','status']:arr['odom_'+key][k]=rec[key]
    for key in ['Q','F','G']:arr['input_'+key][k]=rec[key]
   else:arr['odom_status'][k]='initial'
   arr['pre_rf_state'][k],arr['pre_rf_cov'][k]=f.mean_cov()
   if arm=='E':
    q,av,mult=E.evaluate(pack,X,k,ki,case,arr['pre_rf_state'][k],arr['pre_rf_cov'][k],obs,inputs);arr['q_good_5deg'][k]=q;arr['rf_available'][k]=av;arr['R_multiplier'][k]=mult;f.reliability_multiplier=mult
   for name,enabled,field in [('range',cfg.use_range,'range_m'),('s',cfg.use_s,'s')]:
    status='disabled'
    if enabled:
     status='missing'
     if bool(obs['detected'][k]) and np.isfinite(obs[field][k]):
      if arm=='E' and name=='s' and (q<.5 or not av):status='reliability_abstained'
      elif name=='s' and cfg.skip_s_in_turn and flag[k]:status='skipped_turn'
      else:
       # Frozen held-out-route model; no truth features.
       out=f.range_record(obs[field][k]) if name=='range' else f.s_record(obs[field][k],obs['power'][k]);status=out[3]
       for key,value in zip(['innovation','R','S'],out[:3]):arr[name+'_'+key][k]=value
       if status!='undefined_geometry':
        for key in ['H','h']:arr[name+'_'+key][k]=f.last_scalar[key]
    arr[name+'_status'][k]=status
    if name=='range':arr['post_range_state'][k],arr['post_range_cov'][k]=f.mean_cov()
   arr['est'][k],arr['cov6'][k]=f.mean_cov();refscale=scale
   if k:refscale=max(scale,float(np.linalg.norm(rec['F']@arr['cov6'][k-1]@rec['F'].T+rec['G']@rec['Q']@rec['G'].T,2)))
   guard=F.covariance_diagnostic(arr['cov6'][k],refscale);arr['cov_eigenvalues'][k]=np.linalg.eigvalsh(arr['cov6'][k])
   if not guard['valid']:raise FloatingPointError(f'covariance invalid at sample {k}: {guard}')
   e=truth[k]-arr['est'][k,:3];e[2]=V.wrap(e[2]);arr['pose_error'][k]=e
   P=arr['cov6'][k,:3,:3]
   if np.linalg.eigvalsh(P).min()>0:arr['nees'][k]=e@np.linalg.solve(P,e)
   arr['completed'][k]=True;last=k
  if phase=='pilot':
   direct=F.run_filter_v2(cfg,LUT,inputs,obs,{'turn_phase':flag},x0)
   pe=float(np.max(abs(direct['est']-arr['est'])));pc=float(np.max(abs(direct['cov_full']-arr['cov6'])));assert pe<=1e-12 and pc<=1e-12;parity={'max_state':pe,'max_cov':pc}
 except Exception as e:error=str(e);arr['failure_traceback']=np.array(traceback.format_exc())
 mask=arr['keep']&arr['completed'];err=arr['pose_error'][mask];pv=arr['cov6'][mask,:3,:3];nees=arr['nees'][mask];pheading=pv[:,2,2] if len(pv) else np.array([]);finite=np.isfinite(nees)
 row=dict(case=case,route=route,drift=level,seed=seed,arm=arm,initial=initial,wheelbase=wb,phase=phase,error=error,last_valid_sample=last,n_eval=int(mask.sum()),n_nees=int(finite.sum()),seconds=time.time()-start,known_wheelbase_error=known,pose_cov_singular=int((~finite).sum()),heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(err[:,2]**2)))) if len(err) else None,pos_rmse_m=float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1)))) if len(err) else None,nees_mean=float(np.mean(nees[finite])) if finite.any() else None,pose_coverage=float(np.mean(nees[finite]<=chi2.ppf(.95,3))) if finite.any() else None,nees_lower_fraction=float(np.mean(nees[finite]<chi2.ppf(.025,3))) if finite.any() else None,nees_upper_fraction=float(np.mean(nees[finite]>chi2.ppf(.975,3))) if finite.any() else None,heading_coverage=float(np.mean(abs(err[:,2])<=1.959963984540054*np.sqrt(pheading))) if len(err) else None,parity=parity)
 for name in ['range','s']:
  valid=mask&np.isfinite(arr[name+'_S'])&(arr[name+'_S']>0);accepted=valid&(arr[name+'_status']=='applied');nis=arr[name+'_innovation']**2/arr[name+'_S']
  row[name+'_nis_pregate']=float(np.mean(nis[valid])) if valid.any() else None;row[name+'_nis_accepted']=float(np.mean(nis[accepted])) if accepted.any() else None;row[name+'_reject_rate']=float(np.mean(arr[name+'_status'][valid]=='rejected')) if valid.any() else None
 arr['failed']=np.array(bool(error));arr['error']=np.array(error);arr['last_valid_sample']=np.array(last)
 path=J/'TRACES'/phase/f'{case}_d{level}_s{seed}_{arm}_{initial}_{wb}.npz';path.parent.mkdir(parents=True,exist_ok=True);assert not path.exists();np.savez_compressed(path,**arr)
 path.with_suffix('.json').write_text(json.dumps({'row':row,'filter_config':dataclasses.asdict(cfg),'generator':cfgsensor.manifest()},indent=2));return row
def runphase(phase):
 start=time.time();plan=json.loads((J/'PLAN.json').read_text());cases=plan['cases']
 if phase=='pilot':tasks=[('R2_aA_m0',0,s,a,'stochastic','unknown',phase) for s in range(20) for a in ['A','B','C','D']]
 elif phase=='main':tasks=[(c,d,s,a,'stochastic','unknown',phase) for c in cases for d in range(3) for s in range(50) for a in ['A','B','C','D']]
 elif phase=='controls':tasks=[(c,d,s,'A',i,w,phase) for c in ['R2_aA_m0','R4_aA_m0','R5_aA_m0'] for d in range(3) for s in range(20) for i,w in [('exact','unknown'),('stochastic','known')]]
 elif phase=='E':tasks=[(c,d,s,'E','stochastic','unknown',phase) for c in cases for d in range(3) for s in range(50)]
 else:raise ValueError(phase)
 rows=[]
 with concurrent.futures.ProcessPoolExecutor(max_workers=32) as ex:
  for r in ex.map(single,tasks,chunksize=1):
   rows.append(r)
   if len(rows)%40==0:print(phase,len(rows),'/',len(tasks),'elapsed',round(time.time()-start),flush=True)
 pd.DataFrame(rows).drop(columns=['parity']).to_csv(J/'OUTPUT'/f'09_V2_{phase}.csv',index=False)
 report={'phase':phase,'runs':len(rows),'failed':sum(bool(r['error']) for r in rows),'errors':pd.Series([r['error'] for r in rows if r['error']]).value_counts().to_dict(),'seconds':time.time()-start,'parity':[{k:r[k] for k in ['case','seed','arm','error','parity']} for r in rows] if phase=='pilot' else [],'raw_every_run':True}
 (J/'OUTPUT'/f'{phase.upper()}_STATUS.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='parity'}),flush=True)
 if phase=='pilot' and report['failed']:sys.exit(2)
if __name__=='__main__':runphase(sys.argv[1])


