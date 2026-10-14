"""P4 audited one-step frozen LoS/Full s+Range observation comparisons.

Source audit uses ONLY stdlib before dependency installation/experiments.
Source and frozen assets are read-only. No recursive claims in this stage.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from datetime import datetime,timezone

REPO=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
P0=REPO/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json"
EXPECTED_BLOB="8bf216cf606f5e3c11139cacbf42f15a44556feb"
OLD_CODE_SHA={"p2_frozen_rf_one_step.py":"69e02f89b64792ceafe2dc01e4b92794109fb487",
              "ekf3.py":"c010981d387cf9b50c2f50911ac37624e80318ec"}
NAME="R2_aA_m0"
P4_FRAMES=(150,300,600,900,978)

def hash256(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):
   h.update(b)
 return h.hexdigest()

def git_blob_sha(path):
 b=Path(path).read_bytes()
 return hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()

def fetch_contract():
 if git_blob_sha(P0)!=EXPECTED_BLOB:raise RuntimeError("Changed P0 manifest")
 p=json.loads(P0.read_text(encoding='utf-8'))
 case=next(c for c in p['cases'] if c['id']==NAME)
 assets=[]
 for a in p['assets']:
  if a['kind'] in ('FREQUENCY','HS_LUT','HS_LUT_META','AUDITED_SOURCE','SENSOR_CONFIG'):
   assets.append(a)
  elif a['kind']=='TIMELINE_TNONE':
   assets.append(a)  # legacy DR generator loads ALL 3 routes
  elif a['path'] in (case['los_path'],case['full_path'],case['samples_path']):
   assets.append(a)
 return p,case,assets

def record(out,name,payload):
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 (out/name).write_text(json.dumps(payload,indent=2,allow_nan=False)+'\n')

def audit(out):
 p,case,assets=fetch_contract()
 rc={'stage':'P4_SOURCE_AUDIT','status':'HOLD','git_sha':os.getenv('GITHUB_SHA'),
     'run_id':os.getenv('GITHUB_RUN_ID'),
     'time_utc':datetime.now(timezone.utc).isoformat(),
     'decision':'May pinned R0 s/Range frozen one-step models be evaluated on R2_aA_m0?',
     'independent_peer_audit':False,'scientific_PASS':False,'checks':[],
     'case':NAME,'frames':P4_FRAMES}
 try:
  for f,sha in OLD_CODE_SHA.items():
   path=REPO/'research/EKF3_INDEPENDENT_20261013'/f
   value=git_blob_sha(path)
   rc['checks'].append({'file':f,'kind':'frozen_original_code','pass':value==sha})
  for key in ('core.py','stable_descent.py'):
   file=REPO/'research/EKF4_RANGE_S_STAGED_20261014'/key
   rc['checks'].append({'file':key,'kind':'new_4state_code_present','pass':file.is_file()})
  for key in ('p4_one_step.py','P4_CONTRACT_KO.md'):
   rc['checks'].append({'file':key,'kind':'P4_source_exists','pass':(HERE/key).is_file()})
  wf=REPO/'.github/workflows/ekf4-p4-one-step.yml'
  text=wf.read_text()
  source=text.index('p4_one_step.py --phase audit')
  downstream=text.index('p4_one_step.py --phase evaluate')
  rc['checks'].append({'file':str(wf),'kind':'pre_run_audit_execution_order','pass':source<downstream})
  rc['checks'].append({'kind':'P0_manifest_and_asset_selection','pass':len(assets)>=15})
  rc['asset_paths']=[x['path'] for x in assets]
  if not all(x['pass'] for x in rc['checks']):
   raise RuntimeError('Source workflow/model-identity audit failed')
  rc['status']='GO'
 except Exception as e:
  rc['error']=type(e).__name__+': '+str(e)
  rc['status']='HOLD'
 record(out,'SOURCE_AUDIT.json',rc)
 print('P4_AUDIT '+json.dumps({k:rc[k] for k in ('status','git_sha','checks')},ensure_ascii=False),flush=True)
 return 0 if rc['status']=='GO' else 2

def evaluate(args):
 # Enforce source identity BEFORE importing/using numerical or RF code.
 audit=json.loads((args.audit/'SOURCE_AUDIT.json').read_text())
 if audit['status']!='GO' or audit['git_sha']!=os.getenv('GITHUB_SHA'):
  raise RuntimeError('P4 execution not audited at this source SHA')
 p,case,assets=fetch_contract()
 for a in assets:
  f=REPO/a['path']
  if f.stat().st_size!=a['bytes']:
   raise RuntimeError('P4 asset size mismatch '+a['path'])
  if a.get('sha256'):
   if hash256(f)!=a['sha256']:raise RuntimeError('P4 asset SHA mismatch '+a['path'])
  elif git_blob_sha(f)!=a.get('git_blob_sha1'):
   raise RuntimeError('P4 lineage blob mismatch')
 import sys
 import numpy as np
 sys.path.insert(0,str(REPO/'research/EKF3_INDEPENDENT_20261013'))
 sys.path.insert(0,str(REPO/'research/EKF4_RANGE_S_STAGED_20261014'))
 import p2_frozen_rf_one_step as legacy
 from qclean_uwb.drivesim.hs_lut import HsLut
 from ekf3 import EKF3, archived_direct_s_model
 from core import predict, gaussian_update, sequential_affine, map_update,wrap

 lutfile=legacy.ARCHIVE/'LUT/hs_lut_2deg.npy'
 meta=json.loads((legacy.ARCHIVE/'LUT/hs_lut_meta.json').read_text())['meta']
 loaded=np.load(lutfile,allow_pickle=False,mmap_mode='r')
 th=np.asarray(meta['theta_deg'],float)
 start,stop,step=map(float,meta['phi_deg'])
 ph=np.arange(start,stop+step/2,step)
 if loaded.shape!=(len(th),len(ph),len(ph)):
  raise RuntimeError('frozen LUT meta/shape discrepancy')
 lut=HsLut(dict(theta_deg=th,phi_deg=ph,s=loaded))
 s3=archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),
                          tag_height_m=float(case['robot_z_m']),mount_deg=float(case['mount_deg']))
 R=np.diag([legacy.RR,legacy.RS])
 zanchor=np.asarray(case['anchor'],float)
 dz=float(zanchor[2]-case['robot_z_m'])
 def joint(x):
  s,j=s3(np.asarray(x[:3]))
  delta=x[:2]-zanchor[:2]
  distance=math.sqrt(float(delta@delta)+dz*dz)
  h=np.array([distance+legacy.OFFSET,s])
  H=np.zeros((2,len(x)))
  H[0,:2]=delta/distance
  H[1,:3]=j
  return h,H
 def rawrange(x):
  h,H=joint(x);return h[:1],H[:1]
 def raws(x):
  h,H=joint(x);return h[1:],H[1:]

 t,truth,ids=legacy.read_tnone(next(r for r in legacy.P0['routes'] if r['id']=='R2'))
 xpri,ppri,_=legacy.dr_only_pred(t,truth,seed=0)
 ds,dtheta=legacy.motion_increments(t,truth,convention='legacy-euler')
 cfg=legacy.SensorV2Config(level=1,condition='noise_pair',common_scale=0.,
    bias_rw_rad_s_sqrt_s=0.,slip_mode='time')
 inputs,_=legacy.generate(t,ds,dtheta,cfg,0)
 # Check identical frozen motion inputs before adding bias uncertainty.
 x4=np.r_[xpri[0],0.]
 P4=np.zeros((4,4))
 P4[:3,:3]=legacy.P0_COV
 P4[3,3]=math.radians(.1)**2
 pri4={0:(x4.copy(),P4.copy())}
 for k in range(1,max(P4_FRAMES)+1):
  dt=float(inputs['dt_s'][k])
  dd=float(inputs['ds_odom'][k])
  dg=float(inputs['dtheta_gyro'][k])
  q=np.diag([2e-5*abs(dd),math.radians(.015)**2*dt,0.])
  x4,P4,_,_=predict(x4,P4,dd,dg,dt,q)
  if np.max(np.abs(np.r_[x4[:2]-xpri[k,:2],wrap(x4[2]-xpri[k,2])]))>1e-7:
   raise RuntimeError('4state nominal motion mean not matched to original independent D0')
  if k in P4_FRAMES: pri4[k]=(x4.copy(),P4.copy())
 freq=np.load(legacy.REPO/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy',allow_pickle=False)
 records=[]
 for mode in ('los','full'):
  obs=legacy.read_rf(case,mode,ids,freq)
  for k in P4_FRAMES:
   if not bool(obs['detected'][k]):
    records.append({'channel':mode,'k':k,'status':'RF_UNDETECTED'})
    continue
   z=np.array([float(obs['range_m'][k]),float(obs['s'][k])])
   # Precisely same original prior and frozen R0, WITHOUT NIS rejection.
   x3,P3=xpri[k].copy(),ppri[k].copy()
   old=EKF3(x3,P3).update_joint(
        z[1],z[0],legacy.RS,legacy.RR,0.,s_model=s3,
        anchor_xyz_m=tuple(case['anchor']),tag_height_m=float(case['robot_z_m']),
        range_offset_m=legacy.OFFSET,gate=False)
   new3,c3,_=gaussian_update(x3,P3,z,joint,R)
   error3=float(max(np.max(np.abs(new3-old.post_x)),np.max(np.abs(c3-old.post_P))))
   if error3>1e-8:
    raise RuntimeError(f'Archived EKF3 vs new 3-state forward model parity failed {mode}/{k}: {error3}')
   x,P=pri4[k]
   simultaneous,cjoint,info=gaussian_update(x,P,z,joint,R)
   h,H=joint(x)
   seq,cseq,_=sequential_affine(x,P,z,h,H,R)
   frozen_err=float(max(np.max(np.abs(simultaneous-seq)),np.max(np.abs(cjoint-cseq))))
   if frozen_err>1e-8:
    raise RuntimeError(f'4state joint/fixed-sequential parity failed {mode}/{k}')
   xafter,cafter,ri=gaussian_update(x,P,z[:1],rawrange,R[:1,:1])
   xafter,cafter,si=gaussian_update(xafter,cafter,z[1:],raws,R[1:,1:])
   nonlinear=map_update(x,P,z,joint,R,range_first=True,max_iter=80,gradient_tol=1e-8)
   truth3=truth[k]
   def pose_error(x):
    e=x[:3]-truth3
    e[2]=wrap(e[2])
    return float(np.linalg.norm(e[:2])),float(math.degrees(e[2]))
   records.append({'case':NAME,'channel':mode,'k':int(k),'t_s':float(t[k]),
        'status':'VALID_ONE_STEP',
        'input_range_m':float(z[0]),'input_s':float(z[1]),
        'original_EKF3_frozen_parity':error3,'fourstate_joint_seq_parity':frozen_err,
        'joint4_x':simultaneous.tolist(),'joint4_P':cjoint.tolist(),
        'relinearized_sequential4_x':xafter.tolist(),'relinearized_sequential4_P':cafter.tolist(),
        'MAP4_status':nonlinear.status,'MAP4_gradient_inf':nonlinear.gradient_inf,
        'MAP4_x':nonlinear.x.tolist(),'MAP4_local_P':nonlinear.P.tolist(),
        'baseline3_pose_error_m_deg':pose_error(old.post_x),
        'joint4_pose_error_m_deg':pose_error(simultaneous),
        'map4_pose_error_m_deg':pose_error(nonlinear.x) if nonlinear.status=='CONVERGED' else None,
        'joint4_innovation_NIS':info['NIS'],
        'bias_prior_cov':float(P[3,3]),'bias_posterior_cov':float(cjoint[3,3]),
        'note':'one-step same-current prior, R0, gate OFF; truth only for score; not recursive RF'
   })
 summary={'stage':'P4_R0_FROZEN_ONE_STEP_R2_SEED0','status':'ONE_STEP_EXECUTED',
     'git_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
     'dataset_case':NAME,'channels':['los','full'],'frames':list(P4_FRAMES),
     'observed_valid_rows':sum(a['status']=='VALID_ONE_STEP' for a in records),
     'numerical_MAP_invalid_rows':sum(a.get('MAP4_status') not in (None,'CONVERGED') for a in records),
     'scientific_PASS':False,'P5_P6':'NOT_RUN',
     'scope':'FROZEN P0/R0 ONLY; one-step comparison not recursive filter success',
     'items':records}
 record(args.out,'FINAL.json',summary)
 print('P4_FINAL '+json.dumps({k:v for k,v in summary.items() if k!='items'},ensure_ascii=False),flush=True)
 for r in records:print('P4_ROW '+json.dumps({k:v for k,v in r.items() if k in ('channel','k','status','original_EKF3_frozen_parity','fourstate_joint_seq_parity','MAP4_status','MAP4_gradient_inf')},allow_nan=False),flush=True)
 return 0

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--phase',choices=['audit','evaluate'],required=True)
 ap.add_argument('--audit',type=Path)
 ap.add_argument('--out',type=Path,required=True)
 args=ap.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true':
  raise RuntimeError('This research numerical calculation runs on GitHub Actions ONLY')
 if args.phase=='audit':return audit(args.out)
 try:return evaluate(args)
 except Exception as e:
  import traceback
  out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
  record_existing=out/'FAILURE.json'
  record_existing.write_text(json.dumps({'status':'P4_INPUT_OR_NUMERICAL_FAIL','error':str(e),
   'traceback':traceback.format_exc(),'git_sha':os.environ.get('GITHUB_SHA'),
   'scientific_PASS':False},indent=2)+'\n')
  print('P4_FAILURE '+str(e),flush=True)
  return 2

if __name__=='__main__':
 raise SystemExit(main())
