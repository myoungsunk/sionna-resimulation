import csv,hashlib,json,os,sys,time,traceback
from pathlib import Path
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from itertools import product
work=Path(os.environ['RT_WORK'])
src=work/'source'
data=src/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
out=Path(os.environ['RT_OUT'])
base=next(src.rglob('native_rt_batch.py'));sys.path.insert(0,str(base.parent))
import native_rt_batch as B
def dump(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(x,y):return float(np.linalg.norm(x-y)/np.linalg.norm(y))
task=json.loads(Path(sys.argv[1]).read_text())
poses={(task['route'].split('_')[0],int(task['pose_id'])):dict(case=task['route'].split('_')[0]+'_aB_m0',x=task['x_m'],y=task['y_m'],yaw_body_deg=task['yaw_deg'])}
stop=out/'STOP'
def row_for(route,pid):
 case=route+'_aB_m0'
 rows=json.loads((data/case/'SAMPLES.json').read_text())
 row=rows[pid]
 assert row['pose_id']==pid and sum(v['pose_id']==pid for v in rows)==1
 with (data/'INPUTS'/f'timeline_{route}_Tnone.csv').open() as fp:
  line,=[v for v in csv.DictReader(fp) if int(v['pose_id'])==pid]
 registered=poses[route,pid]
 assert registered['case']==case
 for field in ('x','y','yaw_body_deg'):
  assert abs(float(row[field])-float(line[field]))<=6e-7 and abs(float(line[field])-float(registered[field]))<1e-9
 return row
def worker(key):
 route,pid,mode=key;case=route+'_aB_m0';m=json.loads((data/case/'MANIFEST.json').read_text());folder=out/f'{route}B_{pid}_{mode}';folder.mkdir();bins=folder/'bins';bins.mkdir();calls=0;start=time.monotonic();result=dict(route=route,pose=pid,mode=mode,status='RUNNING')
 try:
  import resource
  assert not stop.exists()
  rt,C=B.imports();from qclean_uwb.drivesim import observation as O
  B.check_runtime();C.BANK_DIR=work/'bank';banks=C.load_banks();tx,rx=C.make_ports(banks);f=banks[0]['freqs_hz'];assert np.array_equal(f,np.load(data/'freqs_hz.npy'))
  setup=C.CorridorSetup(anchor_x_m=10.);scene,bind=C.build_scene(setup,folder/'scene');assert bind==m['material_bindings'] or sorted(bind,key=lambda x:x['object'])==sorted(m['material_bindings'],key=lambda x:x['object'])
  row=row_for(route,pid);pos=setup.robot_position(row['x'],row['y']);anchor=setup.anchor_position
  scene.add(rt.Transmitter('tx',position=anchor.tolist(),orientation=C.euler(C.ANCHOR_ROTATION)))
  scene.add(rt.Receiver('rx',position=pos.tolist(),orientation=C.euler(setup.robot_rotation(row['yaw_body_deg']))))
  lookup={int(v.object_id):k for k,v in scene.objects.items()};dump(folder/'object_map.json',lookup)
  opt=json.loads((src/'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json').read_text())['solver']
  if mode=='LoS':opt=B.solver_options(opt,'C00_DIRECT')
  ref=np.load(data/(f'FULL_RF/H_{case}.npy' if mode=='Full' else f'H_LoS_{case}.npy'),mmap_mode='r')[pid]
  solver=rt.PathSolver();hs=[];reb=[];hi=[];counts=[]
  for i,fr in enumerate(f):
   assert not stop.exists() and not (out.parent/'STOP').exists() and time.monotonic()-start<900 and sum(q.stat().st_size for q in bins.iterdir())<64*1024**2
   C.set_bin(scene,banks,tx,rx,i,float(fr));calls+=1;dump(folder/'CALL_PROGRESS.json',dict(calls_started=calls,bin=i));p=solver(scene,**opt);tau=np.asarray(p.tau).reshape(-1).copy();n=len(tau)
   a=(np.asarray(p.a[0])+1j*np.asarray(p.a[1])).reshape(2,2,n).copy()
   raw={k:np.asarray(getattr(p,k)).copy() for k in ['objects','interactions','primitives','vertices','valid','theta_t','theta_r','phi_t','phi_r']}
   H=B.archive_channel(a,tau,fr);path=bins/f'{i:03d}.npz'
   np.savez_compressed(path,a=a,tau=tau,source_index=np.arange(n),freq=fr,H=H,**raw)
   assert n and np.isfinite(a).all() and np.isfinite(tau).all()
   obj=raw['objects'].reshape(-1,n);di=np.flatnonzero(np.all(obj==np.iinfo(obj.dtype).max,axis=0)&raw['valid'].reshape(-1,n).any(axis=0))
   assert len(di)==1 and abs(float(tau[di[0]])-np.linalg.norm(pos-anchor)/299792458)<1e-12
   with np.load(path) as z:
    field=z['a']*np.exp(np.complex64(-2j*np.pi*float(z['freq']))*z['tau'])[None,None,:];reb.append(field.sum(axis=-1))
   hi.append((a*np.exp(-2j*np.pi*float(fr)*tau.astype(float))[None,None,:]).sum(-1));hs.append(H);counts.append(n)
  H=np.asarray(hs,dtype=complex);cr=O.cir_batch(H[None,:,:,0]);obs=O.first_path_batch(cr,float(f[1]-f[0]));cref=O.cir_batch(ref[None,:,:,0]);oref=O.first_path_batch(cref,float(f[1]-f[0]))
  np.savez_compressed(folder/'RAW_H.npz',H=H,reference=ref,frequency=f,counts=counts,offsets=np.r_[0,np.cumsum(counts)],cir=cr)
  np.savez_compressed(folder/'FIRST_PATH.npz',**{'observed_'+k:v for k,v in obs.items()},**{'reference_'+k:v for k,v in oref.items()})
  e=rel(H[:,:,0],ref[:,:,0]);rec=rel(np.array(reb),H);normmax=float(np.max(abs(np.array(reb)-H))/np.max(abs(H)))
  result.update(archive_rel_L2=e,all_ports_rel_L2=rel(H,ref),reassembly_rel_L2=rec,reassembly_max_normalized=normmax,independent_F64_diagnostic=rel(np.array(hi),H),tap=int(obs['index'][0]),reference_tap=int(oref['index'][0]),signed_s=float(obs['s'][0]),min_paths=min(counts),max_paths=max(counts))
  assert e<=({'LoS':1e-5,'Full':1e-3}[mode]) and rec<=1e-8 and normmax<=1e-8 and result['tap']==result['reference_tap'] and np.isfinite(obs['s']).all(),'PARITY_OR_EXTRACTOR_STOP'
  result['status']='PASS_TECHNICAL'
 except Exception:
  stop.touch();(out.parent/'STOP').touch();result.update(status='STOP',error=traceback.format_exc())
 finally:
  result.update(calls=calls,elapsed_s=time.monotonic()-start);dump(folder/'receipt.json',result)
 return result
if __name__=='__main__':
 out.mkdir(parents=True,exist_ok=False)
 result=worker((task['route'].split('_')[0],int(task['pose_id']),'Full' if task['rf_mode']=='FULL' else 'LoS'))
 dump(out/'result.json',dict(result,task_id=task['task_id']))
 sys.exit(result['status']!='PASS_TECHNICAL')
