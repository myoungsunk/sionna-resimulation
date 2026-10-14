"""P6-R0: audited *local Gaussian* recursive 3/4-state on real frozen RF H.

Not a validated multimodal G3 posterior. Truth is scoring-only; one RF
[r,s] per time. Preserve failures by estimator without silent fallback.
"""
import argparse,json,math,sys,traceback
from pathlib import Path
import numpy as np
from core import predict,gaussian_update,map_update,wrap
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'EKF3_INDEPENDENT_20261013'))
import p2_frozen_rf_one_step as old

def data(lut,case):
 fs=old.archived_direct_s_model(
     lut,anchor_xyz_m=tuple(case['anchor']),
     tag_height_m=float(case['robot_z_m']),mount_deg=float(case['mount_deg']))
 anchor=np.asarray(case['anchor'],float)
 hgt=float(case['robot_z_m'])
 def model(x):
  s,H3=fs(np.asarray(x[:3],float))
  v=np.array([x[0]-anchor[0],x[1]-anchor[1],hgt-anchor[2]])
  rho=float(np.linalg.norm(v))
  H=np.zeros((2,len(x)));H[0,:2]=v[:2]/rho;H[1,:3]=H3
  return np.array([rho+old.OFFSET,float(s)]),H
 return model

def score(states,covs,t,truth,truebias,ok):
 states=np.asarray(states,float);covs=np.asarray(covs,float)
 if not states.size:return {'valid':0,'completed':False}
 err=states[:,:3]-truth[:len(states)]
 err[:,2]=wrap(err[:,2])
 e=err[t[:len(states)]>=30]
 cov=covs[t[:len(states)]>=30]
 if len(e)==0:
  return {'frames':len(states),'evaluated_frames':0,
          'status':'INSUFFICIENT_VALID_FRAMES',
          'heading_RMSE_deg':None,'xy_RMSE_m':None,
          'pose_NEES':None,'pose95':None,'heading95':None,
          'completed':False,'valid':0}
 pose_nees=np.einsum('ij,ij->i',e,np.linalg.solve(cov[:,:3,:3],e[...,None])[...,0])
 heading_nees=e[:,2]**2/cov[:,2,2]
 r={'frames':len(states),'evaluated_frames':len(e),
    'heading_RMSE_deg':float(np.sqrt(np.mean(np.degrees(e[:,2])**2))),
    'xy_RMSE_m':float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),
    'pose_NEES':float(np.mean(pose_nees)),
    'pose95':float(np.mean(pose_nees<=7.814727903251179)),
    'heading95':float(np.mean(heading_nees<=3.841458820694124)),
    'completed':bool(ok),'valid':int(len(e))}
 if states.shape[1]==4:
  r['final_bias_error_dps']=float(math.degrees(states[-1,3]-truebias))
 return r

def runner(out):
 out.mkdir(parents=True,exist_ok=False)
 report={'schema':'EKF4_P6_R0_LOCAL_GAUSSIAN_ONLY',
         'status':'STARTED','scientific_PASS':False,
         'P5_MULTIMODAL_G3_REFERENCE':'NOT_VALIDATED',
         'scope':'one frozen R2 case, 2 RF channels, 2 motion conditions, one seed',
         'results':[]}
 try:
  case=next(c for c in old.P0['cases'] if c['id']=='R2_aA_m0')
  route=next(r for r in old.P0['routes'] if r['id']==case['route'])
  t,truth,ids=old.read_tnone(route)
  ds,da=old.motion_increments(t,truth,convention='legacy-euler')
  archive=old.ARCHIVE
  lutfile=archive/'LUT/hs_lut_2deg.npy'
  metafile=archive/'LUT/hs_lut_meta.json'
  freqfile=old.REPO/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy'
  for f in (lutfile,metafile,freqfile):old.freeze_assert(f)
  meta=json.loads(metafile.read_text())['meta']
  theta=np.asarray(meta['theta_deg'],float)
  lo,hi,inc=map(float,meta['phi_deg'])
  phi=np.arange(lo,hi+inc/2,inc)
  raw=np.load(lutfile,allow_pickle=False,mmap_mode='r')
  assert raw.shape==(len(theta),len(phi),len(phi))
  lut=old.HsLut(dict(theta_deg=theta,phi_deg=phi,s=raw))
  model=data(lut,case)
  freq=np.load(freqfile,allow_pickle=False)
  obs={channel:old.read_rf(case,channel,ids,freq) for channel in ('los','full')}
  covR=np.diag([old.RR,old.RS])
  for condition,level in (('noise_pair',1),('gyro_bias',2)):
   cfg=old.SensorV2Config(level=level,condition=condition,common_scale=0.,
         bias_rw_rad_s_sqrt_s=0.,slip_mode='time')
   inp,eval_only=old.generate(t,ds,da,cfg,0)
   bias_true=np.asarray(eval_only['true_bias_rad_s'],float)
   initial_error=old.sensor_rng(0,'initial').standard_normal(3)*[.1,.1,math.radians(5.)]
   pose0=truth[0]+initial_error;pose0[2]=wrap(pose0[2])
   for channel in ('los','full'):
    estimator={}
    for name in ('DR3','EKF3','EKF4','MAP4'):
     x=np.asarray(pose0.copy(),float)
     P=np.diag([.01,.01,math.radians(5.)**2])
     if name.endswith('4'):
      x=np.r_[x,0.]
      P=np.diag([.01,.01,math.radians(5.)**2,math.radians(.1)**2])
     estimator[name]={'x':x,'P':P,'states':[],'covs':[],'nis':[],
                      'accepted':0,'rejected':0,'failed':None}
    for k in range(len(t)):
     z=np.array([obs[channel]['range_m'][k],obs[channel]['s'][k]],float)
     received=bool(obs[channel]['detected'][k])
     for name,e in estimator.items():
      if e['failed']:continue
      try:
       if k:
        d=float(inp['ds_odom'][k]);dt=float(inp['dt_s'][k])
        Q=np.diag([2e-5*abs(d),math.radians(.015)**2*dt])
        if len(e['x'])==4:Q=np.diag([Q[0,0],Q[1,1],0.])
        e['x'],e['P'],_,_=predict(e['x'],e['P'],d,float(inp['dtheta_gyro'][k]),dt,Q)
       if name!='DR3' and received:
        prior_x=e['x'].copy();prior_P=e['P'].copy()
        filtered,PC,info=gaussian_update(prior_x,prior_P,z,model,covR,gate_threshold=9.21034037197618)
        e['nis'].append(info['NIS'])
        if not info['accepted']:
         e['rejected']+=1
        elif name=='MAP4':
         sol=map_update(prior_x,prior_P,z,model,covR,max_iter=80,gradient_tol=1e-8)
         if sol.status!='CONVERGED':
          e['failed']={'stage':'MAP_UPDATE','sample':k,'status':sol.status,
                       'gradient_inf':sol.gradient_inf,'history':sol.history,
                       'prior_x':prior_x.tolist(),'prior_P':prior_P.tolist(),
                       'z':z.tolist(),'R':covR.tolist()}
         else:
          e['x'],e['P']=sol.x,sol.P;e['accepted']+=1
        else:
         e['x'],e['P']=filtered,PC;e['accepted']+=1
       if not e['failed']:
        e['states'].append(e['x'].copy());e['covs'].append(e['P'].copy())
      except Exception as ex:
       e['failed']={'stage':'TECHNICAL_ERROR','sample':k,'exception':str(ex),
                    'traceback':traceback.format_exc()}
    for name,e in estimator.items():
     good=len(e['states'])==len(t) and e['failed'] is None
     row={'condition':condition,'level':level,'seed':0,'channel':channel,
          'estimator':name,'status':'COMPLETE' if good else 'INVALID_OR_INCOMPLETE',
          'accepted':e['accepted'],'rejected':e['rejected'],'failed':e['failed'],
          'metrics':score(e['states'],e['covs'],t,truth,bias_true[-1],good)}
     report['results'].append(row)
     np.savez_compressed(out/f'{condition}_{channel}_{name}.npz',
                        states=np.asarray(e['states']),covariance=np.asarray(e['covs']),
                        truth_for_evaluation_only=truth[:len(e['states'])],
                        NIS=np.asarray(e['nis']))
  report['status']='P6_R0_LOCAL_GAUSSIAN_EXECUTED'
  rc=0
 except Exception as ex:
  report.update(status='P6_HARD_FAILURE',error=str(ex),traceback=traceback.format_exc())
  rc=2
 report['exit_code']=rc
 (out/'P6_RESULT.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
 print('P6_FINAL '+json.dumps({'status':report['status'],
     'rows':len(report['results']),
     'failed':sum(r['status']!='COMPLETE' for r in report['results'])},allow_nan=False),flush=True)
 return rc

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
 raise SystemExit(runner(parser.parse_args().out.resolve()))
