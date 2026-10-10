from pathlib import Path
import sys,json,time,hashlib,traceback,concurrent.futures,importlib.metadata
import numpy as np
J=Path('/job');SRC=Path('/input/source');sys.path[:0]=[str(SRC/'scripts'),str(SRC/'src'),str(SRC/'scripts/g2_completion')]
import corridor_sionna_run as C
import drjit as dr,sionna.rt as rt
from qclean_uwb.scenarios.corridor import CorridorSetup,ANCHOR_ROTATION
cfg=dict(max_depth=3,samples_per_src=100000,max_num_paths_per_src=1000000,synthetic_array=True,los=True,specular_reflection=True,refraction=True,diffraction=False,edge_diffraction=False,diffuse_reflection=False,seed=20260924)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def one(case):
 dr.set_thread_count(1);C.BANK_DIR=Path('/legacy/source');C.BANK_MANIFEST=C.BANK_DIR/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json';banks=C.load_banks();freq=banks[0]['freqs_hz'];txp,rxp=C.make_ports(banks);solver=rt.PathSolver();start=time.time();out=J/'NATIVE_FULL'/case;out.mkdir();route,anchor,_=case.split('_');setup=CorridorSetup(anchor_x_m=4. if anchor=='aA' else 10.);pfile=Path('/routes/source/results/DRIVE_SIM_20261007/S1/routes')/f'rf_poses_{route}.json';samples=json.loads(pfile.read_text());scene,bindings=C.build_scene(setup,out/'scene');scene.add(rt.Transmitter('tx',position=setup.anchor_position.tolist(),orientation=C.euler(ANCHOR_ROTATION)))
 for i,p in enumerate(samples):scene.add(rt.Receiver('rx_'+str(i),position=setup.robot_position(p['x'],p['y']).tolist(),orientation=C.euler(setup.robot_rotation(p['yaw_body_deg']+45))))
 H=np.full((len(samples),257,2,2),np.nan+1j*np.nan);count=np.zeros((len(samples),257),int)
 try:
  for fi,f in enumerate(freq):
   if time.time()-start>7200:raise TimeoutError('7200s per-case cap')
   C.set_bin(scene,banks,txp,rxp,fi,f);paths=solver(scene,**cfg);a=(np.asarray(paths.a[0])+1j*np.asarray(paths.a[1])).reshape(len(samples),2,2,-1);tau=np.asarray(paths.tau).reshape(len(samples),-1);valid=tau>=0;count[:,fi]=valid.sum(1);H[:,fi]=(a*np.where(valid,np.exp(-2j*np.pi*f*tau),0)[:,None,None,:]).sum(-1)
   if fi==128:np.savez_compressed(out/'PATHS_CENTER_BIN.npz',a=a,tau=tau,interactions=np.asarray(paths.interactions),objects=np.asarray(paths.objects),valid=valid,freq_hz=f)
   if fi%32==0:(out/'PROGRESS.json').write_text(json.dumps({'case':case,'bin':fi,'seconds':time.time()-start}));print(case,fi,flush=True)
  assert np.isfinite(H).all();np.save(out/'H_full.npy',H);np.save(out/'PATH_COUNTS.npy',count);legacy=np.load(Path('/routes/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2')/f'H_{case}.npy');rel=float(np.linalg.norm(H-legacy)/np.linalg.norm(legacy));r=dict(case=case,shape=list(H.shape),H_sha256=sha(out/'H_full.npy'),poses_sha256=sha(pfile),mount=45,anchor_xyz=setup.anchor_position.tolist(),solver=cfg,seconds=time.time()-start,complete=True,legacy_Method_B_relative_H_difference=rel,legacy_parity_gate='NOT_PREREGISTERED: diagnostic only, not automatically interchangeable',path_retention='center bin full paths; path counts all bins; H all bins; per-path off-center interactions not stored')
  (out/'MANIFEST.json').write_text(json.dumps(r,indent=2));return r
 except BaseException as e:
  np.save(out/'H_PARTIAL.npy',H);(out/'FAILURE.json').write_text(json.dumps({'error':str(e),'traceback':traceback.format_exc(),'seconds':time.time()-start}));raise
if __name__=='__main__':
 assert json.loads((J/'NATIVE_LOS_PREFLIGHT.json').read_text())['passed'];(J/'NATIVE_FULL').mkdir(exist_ok=False)
 (J/'NATIVE_FULL_PREREG.json').write_text(json.dumps({'source_sha256':sha(__file__),'cases':['R2_aB_m45','R4_aA_m45','R4_aB_m45','R5_aA_m45','R5_aB_m45'],'solver':cfg,'max_workers':5,'no_interpolation':True,'legacy_full_inputs_readonly':True,'all_body_poses_original':True,'new_noise_or_actuator_model':False},indent=2))
 try:
  import multiprocessing as mp
  with concurrent.futures.ProcessPoolExecutor(max_workers=5,mp_context=mp.get_context('spawn')) as e:rows=list(e.map(one,['R2_aB_m45','R4_aA_m45','R4_aB_m45','R5_aA_m45','R5_aB_m45']))
  (J/'NATIVE_FULL_STATUS.json').write_text(json.dumps({'state':'COMPLETED','cases':rows,'versions':{n:importlib.metadata.version(n) for n in ['numpy','sionna-rt','mitsuba','drjit']},'scientific_PASS':False},indent=2))
 except BaseException as e:
  (J/'NATIVE_FULL_STATUS.json').write_text(json.dumps({'state':'PARTIAL_OR_FAILED','error':str(e),'traceback':traceback.format_exc(),'scientific_PASS':False},indent=2));raise
