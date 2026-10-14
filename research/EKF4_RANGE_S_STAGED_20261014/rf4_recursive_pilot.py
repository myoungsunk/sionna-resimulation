"""P6 development-only: actual frozen LoS/Full RF and 4-state recursive filter.

No P5 posterior certification, no independent scene generalization. All
observations come from the original immutable H/Sensor-v2 pipeline.
Truth is for initial coordinate alignment (as in frozen contract) and scoring
ONLY; never input to MAP or online gate selection.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,sys,traceback
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from core import predict,gaussian_update,map_update,wrap,SyntheticRF

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
LEGACY=REPO/'research/EKF3_INDEPENDENT_20261013'
sys.path.insert(0,str(LEGACY))
import p2_frozen_rf_one_step as old

CASES=('R2_aA_m0','R4_aA_m0','R5_aA_m0')
MODES=('los','full')
CONDITIONS=(('noise_pair',1),('gyro_bias',2))
SEED=0
MODELS=('DR3','EKF4','MAP4_GATED','MAP4_ALL')
R=np.diag([old.RR,old.RS])

def sha(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path,obj):
 Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+'\n')


def source_guard(audit):
 a=json.loads(Path(audit).read_text())
 if not (a['verdict']=='GO' and a['git_sha']==os.environ.get('GITHUB_SHA')):
  raise RuntimeError('P6 pre-run code audit not passed')
 return a


def loaded_lut():
 old.freeze_assert(old.ARCHIVE/'LUT/hs_lut_2deg.npy')
 old.freeze_assert(old.ARCHIVE/'LUT/hs_lut_meta.json')
 old.freeze_assert(old.REPO/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy')
 meta=json.loads((old.ARCHIVE/'LUT/hs_lut_meta.json').read_text())['meta']
 theta=np.asarray(meta['theta_deg'],float)
 lo,hi,step=map(float,meta['phi_deg'])
 phi=np.arange(lo,hi+step/2,step)
 lut_raw=np.load(old.ARCHIVE/'LUT/hs_lut_2deg.npy',mmap_mode='r',allow_pickle=False)
 if lut_raw.shape!=(len(theta),len(phi),len(phi)):
  raise RuntimeError('LUT metadata shape mismatch')
 lut=old.HsLut(dict(theta_deg=theta,phi_deg=phi,s=lut_raw))
 freq=np.load(old.REPO/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy')
 if freq.shape!=(257,) or not np.all(np.diff(freq)>0):
  raise RuntimeError('frequency identity mismatch')
 return lut,freq


def prepare(route,condition,level,seed):
 t,truth,ids=old.read_tnone(route)
 ds_true,dth_true=old.motion_increments(t,truth,convention='legacy-euler')
 cfg=old.SensorV2Config(level=level,condition=condition,common_scale=0.,
    bias_rw_rad_s_sqrt_s=0.,slip_mode='time')
 inputs,_=old.generate(t,ds_true,dth_true,cfg,seed)
 initial_error=old.sensor_rng(seed,'initial').standard_normal(3)*np.array(
    [.1,.1,math.radians(5.)])
 x0=truth[0]+initial_error
 x0[2]=old.wrap(x0[2])
 if len(t)!=len(inputs['ds_odom']):
  raise RuntimeError('generator timeline mismatch')
 return {'t':t,'truth':truth,'ids':ids,'input':inputs,'x0':x0}


def model_for(lut,case):
 scalar=old.archived_direct_s_model(lut,
    anchor_xyz_m=tuple(case['anchor']),
    tag_height_m=float(case['robot_z_m']),mount_deg=float(case['mount_deg']))
 ax,ay,az=map(float,case['anchor'])
 dz=az-float(case['robot_z_m'])
 def model(x):
  x=np.asarray(x,float)
  n=len(x)
  ss,jac_s=scalar(x[:3])
  dx,dy=x[0]-ax,x[1]-ay
  rr=math.sqrt(dx*dx+dy*dy+dz*dz)
  HH=np.zeros((2,n))
  HH[0,:2]=[dx/rr,dy/rr]
  HH[1,:3]=jac_s
  return np.array([rr+old.OFFSET,float(ss)]),HH
 return model


def filter_one(data,obs,case,mode,lut,name):
 n=3 if name=='DR3' else 4
 x=data['x0'].copy()
 P=np.diag([.1**2,.1**2,math.radians(5.)**2])
 if n==4:
  x=np.r_[x,0.]
  P4=np.zeros((4,4));P4[:3,:3]=P
  P4[3,3]=math.radians(.1)**2
  P=P4
 nsteps=len(data['t'])
 states=[];covs=[];fails=[];accepted=0;rejected=0;nis_values=[]
 model=model_for(lut,case)
 for k in range(nsteps):
  if k>0:
   dt=float(data['input']['dt_s'][k])
   ds=float(data['input']['ds_odom'][k])
   da=float(data['input']['dtheta_gyro'][k])
   varl=2e-5*abs(ds);vart=math.radians(.015)**2*dt
   Q=np.diag([varl,vart,0.]) if n==4 else np.diag([varl,vart])
   x,P,_,_=predict(x,P,ds,da,dt,Q)
  if name=='DR3':
   states.append(x.copy());covs.append(P.copy());continue
  if not bool(obs['detected'][k]):
   states.append(x.copy());covs.append(P.copy());continue
  z=np.array([float(obs['range_m'][k]),float(obs['s'][k])])
  if not np.isfinite(z).all():
   fails.append({'k':k,'type':'NONFINITE_OBSERVATION'});break
  h,H=model(x)
  inv=z-h
  SS=H@P@H.T+R
  nis=float(inv@np.linalg.solve(SS,inv))
  nis_values.append(nis)
  if name!='MAP4_ALL' and nis>9.21034037197618:
   rejected+=1
   states.append(x.copy());covs.append(P.copy());continue
  if name=='EKF4':
   x,P,diagnostics=gaussian_update(x,P,z,model,R)
  else:
   result=map_update(x,P,z,model,R,range_first=True,
      max_iter=80,gradient_tol=1e-8)
   if result.status!='CONVERGED':
    fails.append({'k':k,'t_s':float(data['t'][k]),'status':result.status,
     'gradient_inf':result.gradient_inf,'cost':result.cost,
     'history':result.history,'prior_x':x.tolist(),'prior_P':P.tolist(),
     'observation':z.tolist()})
    break
   x,P=result.x,result.P
  accepted+=1
  states.append(x.copy());covs.append(P.copy())
 states=np.asarray(states)
 covs=np.asarray(covs)
 m=len(states)
 if m:
  truth=data['truth'][:m]
  e=states[:,:3]-truth
  e[:,2]=wrap(e[:,2])
  window=np.asarray(data['t'][:m])>=30
  evaluated=e[window]
  heading_rmse_deg=math.degrees(float(np.sqrt(np.mean(evaluated[:,2]**2)))) if len(evaluated) else None
  pos_rmse_m=float(np.sqrt(np.mean(np.sum(evaluated[:,:2]**2,axis=1)))) if len(evaluated) else None
 else:
  heading_rmse_deg=pos_rmse_m=None
 return {'model':name,'case':case['id'],'mode':mode,'status':'VALID' if not fails else 'INVALID_NUMERICAL',
  'steps_total':nsteps,'steps_calculated':m,'accepted':accepted,'rejected':rejected,
  'median_nis':float(np.median(nis_values)) if nis_values else None,
  'heading_RMSE_deg':heading_rmse_deg,'xy_RMSE_m':pos_rmse_m,
  'failures':fails,'states':states,'covariances':covs}


def main():
 p=argparse.ArgumentParser()
 p.add_argument('--audit',required=True)
 p.add_argument('--out',required=True)
 a=p.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true':raise RuntimeError('GitHub cloud only')
 source_guard(a.audit)
 out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
 lut,freq=loaded_lut()
 p0=old.P0
 cases=[case for case in p0['cases'] if case['id'] in CASES]
 route_map={r['id']:r for r in p0['routes']}
 metrics=[];failed=0
 status='COMPLETE'
 for case in cases:
  route=route_map[case['route']]
  for cond,level in CONDITIONS:
   data=prepare(route,cond,level,SEED)
   for ch in MODES:
    obs=old.read_rf(case,ch,data['ids'],freq)
    scene=out/case['id']/cond/ch
    scene.mkdir(parents=True,exist_ok=False)
    for name in MODELS:
     try:
      r=filter_one(data,obs,case,ch,lut,name)
     except Exception as exc:
      (scene/(name+'_exception.log')).write_text(traceback.format_exc())
      failed+=1
      metrics.append({'case':case['id'],'condition':cond,'channel':ch,'model':name,
       'status':'IMPLEMENTATION_BLOCK','error':str(exc)})
      continue
     states=r.pop('states');covs=r.pop('covariances')
     np.savez_compressed(scene/(name+'.npz'),states=states,covariances=covs)
     metrics.append({'condition':cond,'channel':ch,**r})
     if r['status']!='VALID':failed+=1
     print('P6_LOCAL_CASE '+json.dumps({k:r[k] for k in
       ('case','mode','model','status','steps_calculated','accepted','rejected','heading_RMSE_deg','xy_RMSE_m')},
        ensure_ascii=False,allow_nan=False),flush=True)
 result={'schema':'EKF4_P6_LOCAL_MAP_FROZEN_RF_PILOT','stage':'P6_PILOT_NOT_CERTIFIED_FULL_P6',
  'git_sha':os.environ['GITHUB_SHA'],'run_id':os.environ['GITHUB_RUN_ID'],
  'P5_reference_status':'UNRESOLVED_HISTORICAL_NUMERICAL_FAILURE',
  'scientific_PASS':False,'real_RF_full_scene_generalization':'NOT_ESTABLISHED',
  'evaluation_seed':[SEED],'metrics':metrics,'invalid_arms':failed,
  'status':'PILOT_COMPLETE' if failed==0 else 'PILOT_COMPLETE_WITH_INVALID_ARMS',
  'ended_utc':datetime.now(timezone.utc).isoformat()}
 write(out/'FINAL.json',result)
 print('P6_LOCAL_FINAL '+json.dumps({'status':result['status'],'invalid_arms':failed,'arms':len(metrics),
 'scientific_PASS':False},ensure_ascii=False),flush=True)
 return 0 if failed==0 else 2

if __name__=='__main__':raise SystemExit(main())
