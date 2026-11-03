#!/usr/bin/env python3
"""Original R4-B: native full Sionna 257-bin ray decomposition, mount=0."""
import csv,hashlib,json,math,os,pathlib,sys,time
from collections import defaultdict
import numpy as np
R=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'src'));sys.path.insert(0,str(R/'scripts'))
import corridor_sionna_run as C
from qclean_uwb.drivesim import observation as O
D=R/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
def hashf(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
def ob(H,freq):
 cir=O.cir_batch(H[None])[0]
 o=O.first_path_batch(cir[None],float(freq[1]-freq[0]))
 return {'s':float(o['s'][0]),'tap':int(o['index'][0]),'power':o['power'][0].tolist()},cir
def selected(region):
 with (D/'INPUTS/timeline_R4_Tnone.csv').open() as f: rows=list(csv.DictReader(f))
 poses=json.loads((D/'R4_aB_m0/SAMPLES.json').read_text())
 targets=[6.1,6.9] if region=='approach' else [13.1,13.9]
 rows=[q for q in rows if q['phase']=='drive' and float(q['t_s'])>=30]
 out=[]
 for tx in targets:
  q=min(rows,key=lambda q:abs(float(q['x'])-tx))
  v=poses[int(q['pose_id'])]
  assert all(abs(float(q[k])-float(v[k]))<6e-7 for k in ('x','y','yaw_body_deg'))
  out.append({'pose_id':int(v['pose_id']),'t':float(q['t_s']),'x':float(v['x']),'y':float(v['y']),'yaw':float(v['yaw_body_deg'])})
 return out
def main(region,out):
 out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
 C.BANK_DIR=pathlib.Path(os.environ['R4B_BANK'])
 banks=C.load_banks();f=np.asarray(banks[0]['freqs_hz'],float);assert len(f)==257
 expected=json.loads((R/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json').read_text())['npz_sha256']
 assert all(hashf(C.BANK_DIR/n)==expected[n] for n in ('LP_plus45_bank.npz','LP_minus45_bank.npz'))
 cfg=json.loads((R/'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json').read_text())['solver']
 assert cfg['max_depth']==3 and cfg['seed']==20260924
 archivedF=np.load(D/'FULL_RF/H_R4_aB_m0.npy',mmap_mode='r')
 archivedL=np.load(D/'H_LoS_R4_aB_m0.npy',mmap_mode='r')
 assert archivedF.shape==archivedL.shape==(922,257,2,2)
 setup=C.CorridorSetup(anchor_x_m=10.)
 assert all(p['passed'] for p in setup.validate())
 import mitsuba as mi
 import sionna.rt as rt
 solver=rt.PathSolver();tx,rx=C.make_ports(banks);answers=[]
 for row in selected(region):
  pid=row['pose_id'];scene,bindings=C.build_scene(setup,out/('scene_'+str(pid)))
  orig={v['object']:v['ply_sha256'] for v in json.loads((D/'R4_aB_m0/MANIFEST.json').read_text())['material_bindings']}
  assert {v['object']:v['ply_sha256'] for v in bindings}==orig
  scene.add(rt.Transmitter('tx',position=setup.anchor_position.tolist(),orientation=C.euler(C.ANCHOR_ROTATION)))
  scene.add(rt.Receiver('rx',position=setup.robot_position(row['x'],row['y']).tolist(),orientation=C.euler(setup.robot_rotation(row['yaw']))))
  lookup={int(v.object_id):key for key,v in scene.objects.items()}
  T=float(np.linalg.norm(setup.anchor_position-setup.robot_position(row['x'],row['y']))/299792458.)
  traces=defaultdict(lambda:np.zeros((257,2),complex))
  full=np.zeros((257,2),complex);direct=np.zeros((257,2),complex);counts=[]
  for i in range(257):
   C.set_bin(scene,banks,tx,rx,i,float(f[i]))
   coef,tau,inter,obj=C.solve(solver,scene,cfg)
   n=len(tau);counts.append(n)
   idx=int(np.argmin(abs(tau-T)))
   if abs(float(tau[idx])-T)>1e-12:raise ValueError('DIRECT_MISSING fi='+str(i))
   v=coef[:,0,:]*np.exp(-2j*np.pi*f[i]*tau)[None,:]
   full[i]=v.sum(axis=1);direct[i]=v[:,idx]
   for j in range(n):
    if j==idx:key=('DIRECT',)
    else:
     chain=tuple((lookup.get(int(k),'id'+str(int(k))),int(inter[depth,j]))
      for depth,k in enumerate(obj[:,j]) if int(k)>=0 and int(k) in lookup)
     key=chain or (('UNKNOWN',int(round(float(tau[j])*1e12)),j),)
    traces[key][i]+=v[:,j]
  checksum=max(abs(sum(traces.values())-full).reshape(-1))
  assert checksum<1e-10,checksum
  fobs,Fcir=ob(full,f);dobs,Dcir=ob(direct,f)
  aobs,_=ob(archivedF[pid,:,:,0],f);bobs,_=ob(archivedL[pid,:,:,0],f)
  rel=lambda x,y:float(np.linalg.norm(x-y)/max(np.linalg.norm(y),1e-300))
  eF=rel(full,archivedF[pid,:,:,0]);eL=rel(direct,archivedL[pid,:,:,0])
  kk=fobs['tap'];vec={k:O.cir_batch(v[None])[0,kk,:] for k,v in traces.items()}
  L=vec[('DIRECT',)];Q=sum((v for k,v in vec.items() if k!=('DIRECT',)),start=np.zeros(2,complex))
  p0=abs(L)**2;pF=abs(L+Q)**2
  rows=[]
  for k,v in vec.items():
   if k==('DIRECT',):continue
   # Shapley allocation is exact for coherent quadratic power, including interference.
   dP=2*np.real(np.conj(L)*v)+np.real(np.conj(v)*Q)
   vv=L+Q-v;ss=(abs(vv[0])**2-abs(vv[1])**2)/max((abs(vv[0])**2+abs(vv[1])**2),1e-300)
   rows.append({'surface_sequence':[[str(a),int(b)] for a,b in k],
     'dP_plus':float(dP[0]),'dP_minus':float(dP[1]),
     'dP_sum':float(sum(dP)),'delta_s_leave_one_out_fixed_tap':float(fobs['s']-ss),
     'reflected_CIR_amplitude_plus':float(abs(v[0])),'reflected_CIR_amplitude_minus':float(abs(v[1]))})
  rows.sort(key=lambda x:max(abs(x['dP_plus']),abs(x['dP_minus'])),reverse=True)
  check=np.array([sum(v['dP_plus'] for v in rows),sum(v['dP_minus'] for v in rows)])
  assert np.allclose(check,pF-p0,rtol=1e-8,atol=1e-9)
  v={'case':'R4_aB_m0','region':region,'pose':row,'max_depth':cfg['max_depth'],
   'matched_original_H':eF<.03 and eL<.03,'relative_H_full_error':eF,'relative_H_los_error':eL,
   'native_full':fobs,'native_direct':dobs,'archived_full':aobs,'archived_direct':bobs,
   'full_minus_direct_s':float(fobs['s']-dobs['s']),
   'power_common_full_tap':{'los_plus':float(p0[0]),'los_minus':float(p0[1]),
   'full_plus':float(pF[0]),'full_minus':float(pF[1]),
   'delta_plus':float((pF-p0)[0]),'delta_minus':float((pF-p0)[1])},
   'ray_stats':{'count_min':min(counts),'count_max':max(counts),'groups':len(rows)},
   'power_attribution_error':float(max(abs(check-(pF-p0)))),
   'top_paths':rows[:20]}
  (out/('R4B_'+region+'_pose'+str(pid)+'.json')).write_text(json.dumps(v,indent=2)+'\n')
  print('R4B_RESULT',json.dumps({key:val for key,val in v.items() if key!='top_paths'}),flush=True)
  for q in rows[:8]:print('R4B_RAY',region,pid,json.dumps(q),flush=True)
  answers.append(v)
 (out/'R4B_SUMMARY.json').write_text(json.dumps({'region':region,'data':answers},indent=2)+'\n')
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--region',choices=['approach','depart'],required=True);p.add_argument('--out',required=True)
 a=p.parse_args();main(a.region,a.out)
