"""P4 small real frozen RF 4-state one-step diagnostic; no recursive claim."""
import argparse,json,math,sys
from pathlib import Path
import numpy as np
from core import predict,gaussian_update,sequential_affine,map_update,wrap
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'EKF3_INDEPENDENT_20261013'))
import p2_frozen_rf_one_step as old

def run(out):
 out.mkdir(parents=True,exist_ok=False)
 result={'stage':'P4_R0_REAL_RF_ONE_STEP','scientific_PASS':False,'arms':[],'P5_P6':'NOT_RUN'}
 try:
  case=next(x for x in old.P0['cases'] if x['id']=='R2_aA_m0')
  route=next(x for x in old.P0['routes'] if x['id']==case['route'])
  t,truth,ids=old.read_tnone(route)
  ds,da=old.motion_increments(t,truth,convention='legacy-euler')
  cfg=old.SensorV2Config(level=1,condition='noise_pair',common_scale=0.,bias_rw_rad_s_sqrt_s=0.,slip_mode='time')
  inputs,_=old.generate(t,ds,da,cfg,0)
  n=old.sensor_rng(0,'initial').standard_normal(3)*[.1,.1,math.radians(5.)]
  x=np.r_[truth[0]+n,0.];x[2]=wrap(x[2])
  P=np.diag([.01,.01,math.radians(5.)**2,math.radians(.1)**2])
  pri=[]
  for k in range(len(t)):
   if k:
    d=float(inputs['ds_odom'][k]);dt=float(inputs['dt_s'][k])
    Q=np.diag([2e-5*abs(d),math.radians(.015)**2*dt,0.])
    x,P,_,_=predict(x,P,d,float(inputs['dtheta_gyro'][k]),dt,Q)
   pri.append((x.copy(),P.copy()))
  a=old.ARCHIVE
  lutf=a/'LUT/hs_lut_2deg.npy';mf=a/'LUT/hs_lut_meta.json'
  ff=old.REPO/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy'
  for file in (lutf,mf,ff):old.freeze_assert(file)
  m=json.loads(mf.read_text())['meta'];theta=np.asarray(m['theta_deg'],float)
  lo,hi,inc=map(float,m['phi_deg']);phi=np.arange(lo,hi+inc/2,inc)
  l=np.load(lutf,allow_pickle=False,mmap_mode='r')
  assert l.shape==(len(theta),len(phi),len(phi))
  lut=old.HsLut(dict(theta_deg=theta,phi_deg=phi,s=l))
  fs=old.archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),tag_height_m=float(case['robot_z_m']),mount_deg=float(case['mount_deg']))
  anc=np.asarray(case['anchor']);height=float(case['robot_z_m'])
  def model(x):
   s,h3=fs(x[:3])
   dv=np.array([x[0]-anc[0],x[1]-anc[1],height-anc[2]])
   rr=float(np.linalg.norm(dv));H=np.zeros((2,4))
   H[0,:2]=dv[:2]/rr;H[1,:3]=h3
   return np.array([rr+old.OFFSET,float(s)]),H
  freq=np.load(ff,allow_pickle=False)
  idx=np.flatnonzero(t>=30.)
  idx=idx[np.linspace(0,len(idx)-1,12,dtype=int)]
  R=np.diag([old.RR,old.RS])
  for mode in ('los','full'):
   obs=old.read_rf(case,mode,ids,freq);rows=[];worst=0.
   for k in idx:
    mu,C=pri[k];row={'t_s':float(t[k]),'sample':int(k)}
    if not obs['detected'][k]:row['status']='UNDETECTED';rows.append(row);continue
    z=np.array([obs['range_m'][k],obs['s'][k]],float)
    h,H=model(mu)
    xj,Pj,info=gaussian_update(mu,C,z,model,R)
    row['joint_NIS']=info['NIS']
    if info['NIS']>9.21034037197618:
     row['status']='JOINT_GATE_REJECT';rows.append(row);continue
    xs,Ps,_=sequential_affine(mu,C,z,h,H,R)
    gap=float(max(np.max(abs(xj-xs)),np.max(abs(Pj-Ps))))
    worst=max(worst,gap)
    if gap>1e-8:raise RuntimeError('frozen affine parity mismatch')
    mp=map_update(mu,C,z,model,R,max_iter=80,gradient_tol=1e-8)
    row['status']='APPLIED' if mp.status=='CONVERGED' else 'MAP_INVALID'
    row['MAP_grad']=mp.gradient_inf;row['errors']={}
    for label,v in (('prior',mu),('joint',xj),('sequential',xs),('iterated',mp.x if mp.status=='CONVERGED' else None)):
     if v is None:continue
     diff=v[:3]-truth[k];diff[2]=wrap(diff[2])
     row['errors'][label]={'xy_m':float(np.linalg.norm(diff[:2])),'heading_deg':abs(math.degrees(diff[2]))}
    rows.append(row)
   result['arms'].append({'channel':mode,'rows':rows,'parity_max':worst,'count':len(rows)})
  result['status']='P4_REPRESENTATIVE_COMPUTED';code=0
 except Exception as e:
  import traceback
  result.update(status='P4_ERROR',exception=str(e),traceback=traceback.format_exc());code=2
 result['exit_code']=code
 (out/'P4_RESULT.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 print('P4_RESULT '+json.dumps({'status':result['status'],'channels':[(x['channel'],x['parity_max']) for x in result['arms']]},allow_nan=False),flush=True)
 return code

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
 raise SystemExit(run(parser.parse_args().out.resolve()))
