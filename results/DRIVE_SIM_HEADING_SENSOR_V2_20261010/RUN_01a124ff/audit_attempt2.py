from pathlib import Path
import json,hashlib,sys,time,concurrent.futures,traceback
import numpy as np,pandas as pd
J=Path('/job');sys.path.insert(0,str(J/'source/src'))
from qclean_uwb.drivesim import observation as O,sensor_v2 as V
B=Path('/input/BLOCK_C');T=Path('/routes/source/results/DRIVE_SIM_20261007/S1/routes');L=Path('/lut')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(2**20),b''):h.update(b)
 return h.hexdigest()
def work(c):
 name=c['case'];p=B/f'H_LoS_{name}.npy';full=B/'FULL_RF'/f'H_{name}.npy';samp=B/name/'SAMPLES.json';samples=json.loads(samp.read_text())
 assert sha(p)==c['H_sha256'] and sha(full)==c['input_H_sha256'] and sha(samp)==c['samples_sha256']
 rf=B/'INPUTS'/('rf_poses_'+name[:2]+'.json');assert sha(rf)==c['input_rf_poses_sha256'];assert json.loads(rf.read_text())==samples
 freqs=np.load(B/'freqs_hz.npy');records=[]
 for mode,path in [('full',full),('los',p)]:
  H=np.load(path,mmap_mode='r');assert list(H.shape)==c['shape'] and np.isfinite(H).all();ref=O.observe(H,freqs,None,None)
  n=len(freqs);w=.5-.5*np.cos(2*np.pi*np.arange(n)/(n-1));z=np.fft.ifft(H[:,:,:,0]*w[None,:,None],n=4*n,axis=1)*n
  mag=np.abs(z);branch=np.max(mag,axis=1).argmax(1);a=mag[np.arange(len(z)),:,branch];peak=a.max(1);tap=np.argmax(a>=.3*peak[:,None],1);powers=abs(z[np.arange(len(z)),tap,:])**2
  s=(powers[:,0]-powers[:,1])/powers.sum(1);r=tap/(4*n*(freqs[1]-freqs[0]))*O.C0
  ds=float(np.max(abs(s-ref['s'])));dp=float(np.max(abs(powers-ref['power'])));dr=float(np.max(abs(r-ref['range_m'])))
  assert np.array_equal(tap,ref['index']) and ds<=1e-12 and dp<=1e-20 and dr<=1e-12
  records.append(dict(mode=mode,shape=list(H.shape),sha256=sha(path),max_s=ds,max_power=dp,max_range=dr,tap_equal=True))
  np.savez_compressed(J/'OBS'/f'{name}_{mode}.npz',**ref,branch=branch)
 return dict(case=name,anchor=c['anchor_xyz'],mount=c['mount_deg'],robot_z=c['robot_z'],samples_sha256=sha(samp),parity=records)
if __name__=='__main__':
 start=time.time();(J/'OBS').mkdir(exist_ok=True);(J/'OUTPUT').mkdir(exist_ok=True);assert not list((J/'OBS').glob('*.npz'));status={'stage':'input_audit','state':'running'}
 try:
  frozen=json.loads((J/'SOURCE_MANIFEST.json').read_text())
  for rel,h in frozen['sha256'].items():assert sha(J/rel.replace('\\','/'))==h,rel
  assert sha(L/'hs_lut_2deg.npy')=='711e12ee48a30cb666db4dada749b983de49bd565ea351b906269ec8da375a079'
  freq=np.load(B/'freqs_hz.npy');assert freq.shape==(257,) and np.allclose(np.diff(freq),np.diff(freq)[0],rtol=0,atol=1e-6)
  cases=json.loads((B/'CASES.json').read_text());assert {c['case'] for c in cases}==set(json.loads((J/'PLAN.json').read_text())['cases'])
  with concurrent.futures.ProcessPoolExecutor(max_workers=7) as ex:res=list(ex.map(work,cases))
  motion={}
  for route in ['R2','R4','R5']:
   df=pd.read_csv(T/f'timeline_{route}_Tnone.csv');rf=json.loads((B/'INPUTS'/f'rf_poses_{route}.json').read_text());pose=df[['x','y','yaw_body_deg']].to_numpy();pose[:,2]=np.radians(pose[:,2]);t=df.t_s.to_numpy();ids=df.pose_id.to_numpy(int)
   assert ids.min()>=0 and ids.max()<len(rf);rp=np.array([[r['x'],r['y'],r['yaw_body_deg']] for r in rf])[ids]
   errors=abs(df[['x','y','yaw_body_deg']].to_numpy()-rp);assert np.max(errors)<=1e-6
   outcomes={}
   for mode in ['se2','legacy-euler']:
    try:d,a=V.motion_increments(t,pose,convention=mode);outcomes[mode]={'valid':True};np.savez_compressed(J/'OUTPUT'/f'MOTION_{route}_{mode}.npz',t=t,pose=pose,ds=d,dtheta=a,pose_id=ids)
    except ValueError as e:outcomes[mode]={'valid':False,'error':str(e)}
   a=V.wrap(np.diff(pose[:,2]));dp=np.diff(pose[:,:2],axis=0)
   for mode in ['se2','legacy-euler']:
    mid=pose[:-1,2]+(a/2 if mode=='se2' else 0);outcomes[mode]['max_lateral_m']=float(np.max(abs(-dp[:,0]*np.sin(mid)+dp[:,1]*np.cos(mid))))
   motion[route]={'timeline_sha256':sha(T/f'timeline_{route}_Tnone.csv'),'samples':len(df),'duration_s':float(t[-1]),'pose_max_abs_diff':float(errors.max()),'contracts':outcomes,'columns':list(df.columns)}
  status={'state':'completed','cases':res,'motion':motion,'lut_sha256':sha(L/'hs_lut_2deg.npy'),'lut_meta_sha256':sha(L/'hs_lut_meta.json'),'frequency_sha256':sha(B/'freqs_hz.npy'),'frequency_range_hz':[float(freq[0]),float(freq[-1])],'seconds':time.time()-start,'F01':'OPEN','F02':'OPEN','scientific_PASS':False}
  (J/'OUTPUT/00_INPUT_AUDIT.json').write_text(json.dumps(status,indent=2));print(json.dumps(status));
  if not all(v['contracts']['legacy-euler']['valid'] for v in motion.values()):raise ValueError('original motion increments not reconstructible; sensor prior blocked')
 except Exception as e:
  status.update(state='BLOCKED',error=str(e),traceback=traceback.format_exc());(J/'EXECUTION_STATUS.json').write_text(json.dumps(status,indent=2));print(json.dumps(status));sys.exit(2)
 (J/'EXECUTION_STATUS.json').write_text(json.dumps({'state':'input_and_parity_complete','seconds':time.time()-start},indent=2))
