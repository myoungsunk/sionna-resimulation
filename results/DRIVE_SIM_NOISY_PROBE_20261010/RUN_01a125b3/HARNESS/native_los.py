from pathlib import Path
import json,sys,time,hashlib,traceback,importlib.metadata
import numpy as np
from scipy.interpolate import RegularGridInterpolator
J=Path('/job');SRC=Path('/input/source');sys.path[:0]=[str(SRC/'scripts'),str(SRC/'src'),str(SRC/'scripts/g2_completion')]
import corridor_sionna_run as C
import drjit as dr,sionna.rt as rt
from qclean_uwb.scenarios.corridor import CorridorSetup,ANCHOR_ROTATION
from qclean_uwb.drivesim.observation import observe
dr.set_thread_count(1);C.BANK_DIR=Path('/legacy/source');C.BANK_MANIFEST=C.BANK_DIR/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json'
OUT=J/'NATIVE_LOS';OUT.mkdir(exist_ok=False);t0=time.time();plan=json.loads((J/'PLAN.json').read_text());banks=C.load_banks();freq=banks[0]['freqs_hz'];txp,rxp=C.make_ports(banks);solver=rt.PathSolver()
cfg=dict(max_depth=0,los=True,specular_reflection=False,refraction=False,diffuse_reflection=False,diffraction=False,seed=42)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def fields(rot,local,fi):
 th=np.arccos(np.clip(local[2],-1,1));ph=np.arctan2(local[1],local[0]);et=np.array([np.cos(th)*np.cos(ph),np.cos(th)*np.sin(ph),-np.sin(th)]);ep=np.array([-np.sin(ph),np.cos(ph),0.]);vec=[]
 for b in banks:
  tt=np.radians(b['theta_deg']);pp=np.radians(b['phi_deg']);p=(ph-pp[0])%(2*np.pi)+pp[0]
  e=RegularGridInterpolator((tt,pp),np.stack([b['e_theta'][fi],b['e_phi'][fi]],-1))([[th,p]])[0]
  vec.append(rot@(et*e[0]+ep*e[1])*np.sqrt(2*np.pi/376.730313668))
 return np.array(vec)
try:
 audit=[];pre=[];setup=CorridorSetup()
 for mount in [0,45]:
  for yaw in [0,50,130,180]:
   Rr=setup.robot_rotation(yaw+mount);nom=np.array([[1,1,0],[1,-1,0]])/np.sqrt(2);audit.append({'mount':mount,'yaw':yaw,'TX0_world_nominal':(ANCHOR_ROTATION@nom[0]).tolist(),'RX_world_nominal':(Rr@nom.T).T.tolist(),'co_like_definition':'direction-conditional FFD contraction; no globally fixed co port','boresight_actual_world_Jones':[[[float(z.real),float(z.imag)] for z in v] for v in fields(Rr,np.array([0.,0.,1.]),128)]})
 (J/'ANTENNA_POL_FRAME_AUDIT.json').write_text(json.dumps({'bank_manifest_sha256':sha(C.BANK_MANIFEST),'banks':{n+'_bank.npz':sha(C.BANK_DIR/(n+'_bank.npz')) for n in C.PORTS},'axes':audit,'Jones_fields_used':True,'not_hardware_validation':True},indent=2))
 for xy in plan['LoS_preflight']['xy']:
  for mount in [0,45]:
   for yaw in [0,50,130,180]:
    rtrot=ANCHOR_ROTATION;rr=setup.robot_rotation(yaw+mount);p=setup.robot_position(*xy);direction=(p-setup.anchor_position);dist=np.linalg.norm(direction);direction/=dist
    for fi in [0,128,256]:
     scene=rt.load_scene();C.set_bin(scene,banks,txp,rxp,fi,freq[fi]);scene.add(rt.Transmitter('tx',position=setup.anchor_position.tolist(),orientation=C.euler(rtrot)));scene.add(rt.Receiver('rx',position=p.tolist(),orientation=C.euler(rr)));paths=solver(scene,**cfg)
     actual=(np.asarray(paths.a[0])+1j*np.asarray(paths.a[1])).reshape(2,2);expected=fields(rr,rr.T@(-direction),fi)@fields(rtrot,rtrot.T@direction,fi).T*C.C0/freq[fi]/(4*np.pi*dist);rel=float(np.linalg.norm(actual-expected)/np.linalg.norm(expected));delay=float(abs(np.asarray(paths.tau).ravel()[0]-dist/C.C0));pre.append(dict(xy=xy,mount=mount,yaw=yaw,bin=fi,relative_complex_error=rel,delay_error_s=delay,passed=bool(rel<=1e-4 and delay<=1e-12)))
 result={'samples':pre,'passed':all(x['passed'] for x in pre),'tolerances':plan['LoS_preflight'],'seconds':time.time()-t0};(J/'NATIVE_LOS_PREFLIGHT.json').write_text(json.dumps(result,indent=2));assert result['passed'],'ANTENNA_LOS_PREFLIGHT_FAILED'
 records=[]
 for case in ['R2_aB_m45','R4_aA_m45','R4_aB_m45','R5_aA_m45','R5_aB_m45']:
  route,anchor,_=case.split('_');setup=CorridorSetup(anchor_x_m=4. if anchor=='aA' else 10.);pfile=Path('/routes/source/results/DRIVE_SIM_20261007/S1/routes')/f'rf_poses_{route}.json';samples=json.loads(pfile.read_text());directory=OUT/case;directory.mkdir();scene,bindings=C.build_scene(setup,directory/'scene');scene.add(rt.Transmitter('tx',position=setup.anchor_position.tolist(),orientation=C.euler(ANCHOR_ROTATION)))
  for i,p in enumerate(samples):scene.add(rt.Receiver('rx_'+str(i),position=setup.robot_position(p['x'],p['y']).tolist(),orientation=C.euler(setup.robot_rotation(p['yaw_body_deg']+45))))
  H=np.full((len(samples),257,2,2),np.nan+1j*np.nan);tau=np.full((len(samples),257),np.nan);aa=np.full_like(H,np.nan+1j*np.nan)
  for fi,f in enumerate(freq):
   if time.time()-t0>plan['wall_budget_s']:raise TimeoutError('7200s cap')
   C.set_bin(scene,banks,txp,rxp,fi,f);paths=solver(scene,**cfg);a=(np.asarray(paths.a[0])+1j*np.asarray(paths.a[1])).reshape(len(samples),2,2,-1);delay=np.asarray(paths.tau).reshape(len(samples),-1);assert a.shape[-1]==1 and delay.shape[1]==1;H[:,fi]=a[:,:,:,0]*np.exp(-2j*np.pi*f*delay[:,0])[:,None,None];aa[:,fi]=a[:,:,:,0];tau[:,fi]=delay[:,0]
   if fi%32==0:(J/'RF_PROGRESS.json').write_text(json.dumps({'case':case,'bin':fi,'seconds':time.time()-t0}));print(case,fi,flush=True)
  assert np.isfinite(H).all();np.save(directory/'H_LoS.npy',H);np.savez_compressed(directory/'PATHS_LoS.npz',a=aa,tau=tau,freqs_hz=freq);obs=observe(H,freq,None,None);np.savez_compressed(directory/'OBS_LoS.npz',**obs)
  records.append(dict(case=case,shape=list(H.shape),H_sha256=sha(directory/'H_LoS.npy'),poses_sha256=sha(pfile),solver=cfg,anchor_xyz=setup.anchor_position.tolist(),mount=45,source='NEW_NATIVE_PATHSOLVER',all_finite=True,complete=True));(OUT/'CASES.json').write_text(json.dumps(records,indent=2))
 (J/'NATIVE_LOS_STATUS.json').write_text(json.dumps({'state':'COMPLETED','cases':records,'seconds':time.time()-t0,'versions':{n:importlib.metadata.version(n) for n in ['numpy','sionna-rt','mitsuba','drjit']},'source_sha256':sha(__file__),'native_full_RF':'NOT_RUN'},indent=2))
except BaseException as e:
 (J/'NATIVE_LOS_STATUS.json').write_text(json.dumps({'state':'FAILED_PRECONDITION' if not (OUT/'CASES.json').exists() else 'PARTIAL','error':str(e),'traceback':traceback.format_exc(),'seconds':time.time()-t0},indent=2));raise
