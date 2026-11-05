import csv,hashlib,json,os,sys,time,traceback
from pathlib import Path
import numpy as np
from concurrent.futures import ProcessPoolExecutor
from itertools import product
src=Path('/src'); data=Path('/data'); out=Path('/out')
base=next(src.rglob('native_rt_batch.py'));sys.path.insert(0,str(base.parent))
import native_rt_batch as B
def dump(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False))
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(x,y):return float(np.linalg.norm(x-y)/np.linalg.norm(y))
contract=json.loads(Path(__file__).with_name('FROZEN_CRITERIA.json').read_text())
keys=list(product(contract['new_yaws'],['Full','LoS']))
poses={('R4',168):None}
stop=out/'STOP'
def row_for(route,pid):
 case=route+'_aB_m0'
 rows=json.loads((data/case/'SAMPLES.json').read_text())
 row=rows[pid]
 assert row['pose_id']==pid and sum(v['pose_id']==pid for v in rows)==1
 with (data/'INPUTS'/f'timeline_{route}_Tnone.csv').open() as fp:
  line,=[v for v in csv.DictReader(fp) if int(v['pose_id'])==pid]
 return row
def worker(key):
 yaw,mode=key;route='R4';pid=168;case=route+'_aB_m0';m=json.loads((data/case/'MANIFEST.json').read_text());folder=out/f'yaw_{yaw}_{mode}';folder.mkdir();bins=folder/'bins';bins.mkdir();calls=0;start=time.monotonic();result=dict(route=route,pose=pid,yaw=yaw,mode=mode,status='RUNNING')
 try:
  import resource
  assert not stop.exists()
  rt,C=B.imports();from qclean_uwb.drivesim import observation as O
  B.check_runtime();C.BANK_DIR=Path('/bank');banks=C.load_banks();tx,rx=C.make_ports(banks);f=banks[0]['freqs_hz'];assert np.array_equal(f,np.load(data/'freqs_hz.npy'))
  setup=C.CorridorSetup(anchor_x_m=10.);scene,bind=C.build_scene(setup,folder/'scene');assert bind==m['material_bindings'] or sorted(bind,key=lambda x:x['object'])==sorted(m['material_bindings'],key=lambda x:x['object'])
  row=row_for(route,pid);row['yaw_body_deg']=yaw;pos=setup.robot_position(row['x'],row['y']);anchor=setup.anchor_position
  scene.add(rt.Transmitter('tx',position=anchor.tolist(),orientation=C.euler(C.ANCHOR_ROTATION)))
  scene.add(rt.Receiver('rx',position=pos.tolist(),orientation=C.euler(setup.robot_rotation(row['yaw_body_deg']))))
  lookup={int(v.object_id):k for k,v in scene.objects.items()};dump(folder/'object_map.json',lookup)
  opt=json.loads((src/'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json').read_text())['solver']
  if mode=='LoS':opt=B.solver_options(opt,'C00_DIRECT')
  solver=rt.PathSolver();hs=[];reb=[];hi=[];counts=[]
  for i,fr in enumerate(f):
   assert not stop.exists() and time.monotonic()-start<900 and sum(q.stat().st_size for q in bins.iterdir())<80*1024**2
   C.set_bin(scene,banks,tx,rx,i,float(fr));calls+=1;p=solver(scene,**opt);tau=np.asarray(p.tau).reshape(-1).copy();n=len(tau)
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
  H=np.asarray(hs,dtype=complex);cr=O.cir_batch(H[None,:,:,0]);obs=O.first_path_batch(cr,float(f[1]-f[0]))
  np.savez_compressed(folder/'RAW_H.npz',H=H,frequency=f,counts=counts,offsets=np.r_[0,np.cumsum(counts)],cir=cr)
  rec=rel(np.array(reb),H);normmax=float(np.max(abs(np.array(reb)-H))/np.max(abs(H)))
  magnitude=abs(cr[0]);branch=int(magnitude.max(axis=0).argmax())
  peak=float(magnitude[:,branch].max());assert peak>0 and np.isfinite(cr).all()
  idx=next(j for j,v in enumerate(magnitude[:,branch]) if v>=0.3*peak)
  power=abs(cr[0,idx])**2;assert power.sum()>0
  signed=float((power[0]-power[1])/power.sum())
  distance=idx/(1028*float(f[1]-f[0]))*299792458
  assert idx==int(obs['index'][0]) and abs(signed-float(obs['s'][0]))<=1e-12 and abs(distance-float(obs['range_m'][0]))<=1e-12
  result.update(reassembly_rel_L2=rec,reassembly_max_normalized=normmax,independent_F64_diagnostic=rel(np.array(hi),H),tap=idx,signed_s=signed,range_m=distance,min_paths=min(counts),max_paths=max(counts))
  assert rec<=1e-8 and normmax<=1e-8,'RAY_REASSEMBLY_STOP'
  result['status']='PASS_TECHNICAL'
 except Exception:
  stop.touch();result.update(status='STOP',error=traceback.format_exc())
 finally:
  result.update(calls=calls,elapsed_s=time.monotonic()-start);dump(folder/'receipt.json',result)
 return result
if __name__=='__main__':
 assert os.sched_getaffinity(0)==set(range(32))
 lock=json.loads(B.ORIG.read_text()); ledger={}
 for k,h in lock['source_sha256'].items():
  if str(B.BLOCK)+'/' in k:

   p=data/k.split(str(B.BLOCK)+'/')[1]
  else:
   p=src/k
   if not p.exists():continue
  assert digest(p)==h,k;ledger[k]=h
 for route,pid in poses:
  row_for(route,pid)
  case=route+'_aB_m0'
  m=json.loads((data/case/'MANIFEST.json').read_text())
  for v in m['material_bindings']:
   p=data/case/'scene'/(v['object']+'.ply');assert digest(p)==v['ply_sha256'];ledger[str(p)]=digest(p)
 for k,h in lock['bank_sha256'].items():assert digest(Path('/bank')/k)==h;ledger[k]=h
 assert digest(base)=='79226718784565a5b7d414350ed2eeb884363ad547654d555065275df5ff9de4'
 dump(out/'INPUT_LOCK.json',dict(hashes=ledger,phase32_sha256=digest(base),runner_sha256=digest(Path(__file__)),keys=keys,full_rel_L2=.001,los_rel_L2=.00001,ray_sum_rel_L2=1e-8,ray_max_normalized=1e-8))
 dump(out/'APPROVAL.json',contract)
 results=[]
 with ProcessPoolExecutor(4) as pool:
  for offset in range(0,len(keys),4):
   results.extend(pool.map(worker,keys[offset:offset+4]))
   dump(out/'QA.json',results)
   if stop.exists():break
 with (out/'FAILED_KEYS.csv').open('w',newline='') as fp:
  writer=csv.writer(fp);writer.writerow(['yaw','mode','status'])
  indexed={(r['yaw'],r['mode']):r for r in results}
  for key in keys:
   status=indexed.get(key,{}).get('status','NOT_RUN')
   if status!='PASS_TECHNICAL':writer.writerow([*key,status])
 receipts=[json.loads(p.read_text()) for p in out.glob('*/receipt.json')]
 from collections import Counter
 assert Counter((r['yaw'],r['mode']) for r in receipts)==Counter(keys)
 assert len(results)==8 and all(r['status']=='PASS_TECHNICAL' and r['calls']==257 for r in receipts)
 print('PASS_TECHNICAL',sum(r['calls'] for r in receipts),flush=True)
