"""Load unmodified SourceFFD with explicit pinned banks; no legacy output writes."""
from pathlib import Path
import importlib,sys,hashlib
import numpy as np
def load(lock):
 cache=Path(lock['source_model_cache']);root=cache/'legacy'
 sys.path[:0]=[str(root/'research/FFD_P0P3_20261016'),str(root/'research/EKF4_RANGE_S_STAGED_20261014'),str(root/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
 from source_model import SourceFFD
 from qclean_uwb.drivesim.pattern_apply import Bank
 names=['source_model','p0_initial','p3_rf_adapter4','qclean_uwb','qclean_uwb.drivesim','qclean_uwb.scenarios','qclean_uwb.drivesim.pattern_apply','qclean_uwb.drivesim.observation','qclean_uwb.drivesim.hs_lut','qclean_uwb.scenarios.corridor']
 imported={}
 for name in names:
  path=Path(sys.modules[name].__file__).resolve();relative=path.relative_to(cache).as_posix()
  if relative not in lock['source_model_dependencies']:raise ValueError('unlocked import '+str(path))
  digest=hashlib.sha256(path.read_bytes()).hexdigest()
  if digest!=lock['source_model_dependencies'][relative]['sha256']:raise ValueError('import drift '+name)
  imported[name]=dict(path=str(path),sha256=digest)
 banks=[]
 for n in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
  with np.load(lock['banks'][n]['path'],allow_pickle=False) as z:b=Bank(dict(z))
  if b.e_theta.shape!=(257,181,361) or b.e_theta.dtype!=np.complex64 or not np.isfinite(b.e_theta).all() or not np.isfinite(b.e_phi).all():raise ValueError('model bank schema')
  banks.append(b)
 return SourceFFD(banks=banks),imported
def branch(diag,i):
 return dict(tap=int(diag['tap'][i]),strong_port=int(diag['strong_port'][i]),cells=diag['cells'][i].tolist())
def evaluate(model,row,plan):
 state=np.array([row['xyz'][0],row['xyz'][1],np.deg2rad(row['yaw_deg']),0.],float)
 case=dict(anchor=plan['anchor'],robot_z_m=plan['robot_z_m'],mount_deg=plan['mount_deg'])
 h,J,d=model.batch(state[None,:],case,gradient=True,return_diagnostics=True)
 analytic=float(J[0,1,2]);center=branch(d,0);checks=[]
 for eps in plan['fd_steps_rad']:
  xx=np.repeat(state[None,:],2,axis=0);xx[:,2]+=[-eps,eps]
  y,_,dd=model.batch(xx,case,gradient=False,return_diagnostics=True)
  minus,plus=branch(dd,0),branch(dd,1);same=minus==center==plus;fd=float((y[1,1]-y[0,1])/(2*eps));error=abs(fd-analytic);tol=plan['fd_abs_tol']+plan['fd_rel_tol']*abs(analytic)
  if same and error>tol:raise ValueError('smooth SourceFFD Hpsi mismatch '+row['id'])
  checks.append(dict(eps_rad=eps,minus_state=xx[0].tolist(),plus_state=xx[1].tolist(),minus_h_s=float(y[0,1]),plus_h_s=float(y[1,1]),minus_branch=minus,plus_branch=plus,same_branch=same,finite_difference_s_per_rad=fd,absolute_error=error,tolerance=tol,status='VERIFIED_SMOOTH' if same else 'UNDEFINED_BRANCH_CHANGE'))
 if not np.isfinite(h).all() or not np.isfinite(J).all():raise ValueError('nonfinite model')
 return dict(state=state.tolist(),h_s=float(h[0,1]),h_range=float(h[0,0]),Hpsi_s_per_rad=analytic,Hpsi_s_per_deg=analytic*np.pi/180.,base_branch=center,fd_checks=checks,derivative_status='VERIFIED_SMOOTH' if all(c['same_branch'] for c in checks) else 'UNDEFINED_BRANCH_CHANGE',model_native_range=float(d['native_range'][0]),model_fp_margin=float(d['fp_margin'][0]))
