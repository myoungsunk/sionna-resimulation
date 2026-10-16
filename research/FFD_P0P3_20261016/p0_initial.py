"""Source-bank diagnostic only: direct global E fields, no GT-trained correction."""
from pathlib import Path
import numpy as np,json,sys,hashlib,time
ROOT=Path(__file__).resolve().parents[2];DATA=ROOT.parent;OUT=DATA/'ffd_p0p3/out'
sys.path.insert(0,str(ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'))
sys.path.insert(0,str(ROOT/'research/EKF4_RANGE_S_STAGED_20261014'))
from qclean_uwb.drivesim import pattern_apply as P, observation as O, hs_lut as L
from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION
from p3_rf_adapter4 import FrozenLut

def load_banks():
 m=json.loads((DATA/'BANK_MANIFEST.json').read_text());banks=[];records=[]
 for name in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
  path=DATA/name
  with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
  assert sha==m['npz_sha256'][name]
  with np.load(path,allow_pickle=False) as z:b=P.Bank(dict(z))
  assert b.e_theta.shape==(257,181,361) and b.e_theta.dtype==np.complex64
  assert np.isfinite(b.e_theta).all() and np.isfinite(b.e_phi).all()
  assert np.array_equal(b.freqs_hz,6250400000.+1950000.*np.arange(257))
  poles={}
  for idx in (0,-1):
   th=np.repeat(b.theta[idx],b.np);tt,pp=P.sph_basis(th,b.phi)
   e=b.e_theta[:,idx,:,None]*tt[None]+b.e_phi[:,idx,:,None]*pp[None]
   mu=e.mean(axis=1,keepdims=True)
   poles[str(idx)]=float(np.max(np.linalg.norm(e-mu,axis=-1)/np.maximum(np.linalg.norm(mu,axis=-1),1e-30)))
  records.append(dict(name=name,bytes=path.stat().st_size,sha256=sha,pole_cartesian_relative_dispersion=poles,seam_max_abs=float(max(np.max(abs(b.e_theta[:,:,-1]-b.e_theta[:,:,0])),np.max(abs(b.e_phi[:,:,-1]-b.e_phi[:,:,0]))))))
  banks.append(b)
 (OUT/'BANK_AUDIT.json').write_text(json.dumps(records,indent=2));print('BANKS',records,flush=True)
 return banks

def fields(b,local):
 th=np.arctan2(np.hypot(local[:,0],local[:,1]),local[:,2]);ph=np.arctan2(local[:,1],local[:,0])
 et,ep=b.sample(th,ph);tt,pp=P.sph_basis(th,ph)
 return P.SCALE*(et[...,None]*tt[None]+ep[...,None]*pp[None])

def direct(banks,xyz,yaw,anchor,dist_override=None):
 d=np.asarray(xyz)-np.asarray(anchor);dist=np.linalg.norm(d,axis=1);d=d/dist[:,None]
 T=np.array([fields(b,d@ANCHOR_ROTATION)@ANCHOR_ROTATION.T for b in banks])
 yy=np.asarray(yaw)*np.pi/180.;co=np.cos(yy);si=np.sin(yy)
 v=-d;local=np.column_stack([co*v[:,0]+si*v[:,1],-si*v[:,0]+co*v[:,1],v[:,2]])
 Rs=[]
 for b in banks:
  e=fields(b,local);ew=e.copy();ew[:,:,0]=co[None]*e[:,:,0]-si[None]*e[:,:,1];ew[:,:,1]=si[None]*e[:,:,0]+co[None]*e[:,:,1];Rs.append(ew)
 R=np.array(Rs)
 f=banks[0].freqs_hz;dist=dist if dist_override is None else np.broadcast_to(dist_override,dist.shape)
 fac=O.C0/f[None,:]/(4*np.pi*dist[:,None])*np.exp(-2j*np.pi*f[None,:]*dist[:,None]/O.C0)
 return np.einsum('rfni,tfni->nfrt',R,T)*fac[:,:,None,None]

def main():
 import pandas as pd
 banks=load_banks();lut=FrozenLut(ROOT);m=json.loads((ROOT/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text());summary=[]
 for case in m['cases']:
  samples=pd.DataFrame(json.loads((ROOT/case['samples_path']).read_text()));xyz=np.column_stack([samples.x,samples.y,np.full(len(samples),case['robot_z_m'])]);yaw=samples.yaw_body_deg.to_numpy()+case['mount_deg'];ref=np.load(ROOT/case['los_path'],mmap_mode='r');rows=[];start=time.perf_counter()
  for st in range(0,len(samples),64):
   en=min(len(samples),st+64);h=direct(banks,xyz[st:en],yaw[st:en],case['anchor']);h10=direct(banks,xyz[st:en],yaw[st:en],case['anchor'],10.)
   p=O.observe(h,banks[0].freqs_hz,None,None);a=O.observe(ref[st:en],banks[0].freqs_hz,None,None);p10=O.observe(h10,banks[0].freqs_hz,None,None)
   delta=h-ref[st:en];rel=np.linalg.norm(delta.reshape(len(h),-1),axis=1)/np.linalg.norm(ref[st:en].reshape(len(h),-1),axis=1)
   for j in range(en-st):
    k=st+j;x=np.array([samples.x[k],samples.y[k],np.radians(samples.yaw_body_deg[k]),0.]);old=lut.model(x,case)[0][1]
    th,pt,pr=L.geometry_angles(case['anchor'],xyz[k],yaw[k]);rows.append(dict(case=case['id'],pose_id=int(samples.pose_id[k]),theta_deg=float(th),phi_tx_deg=float(pt),phi_rx_deg=float(pr),distance_m=float(np.linalg.norm(xyz[k]-case['anchor'])),h_relative_l2=float(rel[j]),s_native=float(a['s'][j]),s_direct=float(p['s'][j]),s_direct_d10=float(p10['s'][j]),s_old=float(old),tap_native=int(a['index'][j]),tap_direct=int(p['index'][j]),tap_d10=int(p10['index'][j]),r_native=float(a['range_m'][j]),r_direct=float(p['range_m'][j])))
  df=pd.DataFrame(rows);df.to_csv(OUT/f'P0_INITIAL_{case["id"]}.csv',index=False)
  rec=dict(case=case['id'],n=len(df),h_relative_max=float(df.h_relative_l2.max()),h_relative_rms=float(np.sqrt(np.mean(df.h_relative_l2**2))),s_direct_native_rmse=float(np.sqrt(np.mean((df.s_direct-df.s_native)**2))),s_direct_native_max=float(abs(df.s_direct-df.s_native).max()),s_old_native_rmse=float(np.sqrt(np.mean((df.s_old-df.s_native)**2))),s_ref_actual_rmse=float(np.sqrt(np.mean((df.s_direct-df.s_direct_d10)**2))),tap_mismatch=int(np.sum(df.tap_native!=df.tap_direct)),seconds=time.perf_counter()-start);summary.append(rec);print('CASE',rec,flush=True)
 (OUT/'P0_INITIAL_SUMMARY.json').write_text(json.dumps(summary,indent=2))
if __name__=='__main__': main()
