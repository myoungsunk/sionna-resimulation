from pathlib import Path
import sys,json,time,hashlib,shutil,datetime,traceback,importlib.metadata
import numpy as np
J=Path('/job');SRC=J/'source';OUT=J/'BLOCK_C';OUT.mkdir(exist_ok=False)
sys.path[:0]=[str(SRC/'scripts'),str(SRC/'src'),str(SRC/'scripts/g2_completion')]
import corridor_sionna_run as C
import drjit as dr, sionna.rt as rt
from qclean_uwb.scenarios.corridor import CorridorSetup,ANCHOR_ROTATION
from qclean_uwb.drivesim import observation as O
dr.set_thread_count(1);C.BANK_DIR=Path('/legacy/source');C.BANK_MANIFEST=C.BANK_DIR/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json';banks=C.load_banks();freq=banks[0]['freqs_hz']
R=Path('/routes/source/results/DRIVE_SIM_20261007');S2=R/'SNOWBALL_ROUTES_01a11669/S2';S6=R/'SNOWBALL_ROUTES_01a11669/S6_routes';T=R/'S1/routes';started=time.monotonic()
cfg=dict(max_depth=0,los=True,specular_reflection=False,refraction=False,diffuse_reflection=False,diffraction=False,seed=42)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def calculate(samples,setup,mount,directory):
 directory.mkdir(exist_ok=False);scene,bindings=C.build_scene(setup,directory/'scene');txp,rxp=C.make_ports(banks);solver=rt.PathSolver()
 scene.add(rt.Transmitter('tx',position=setup.anchor_position.tolist(),orientation=C.euler(ANCHOR_ROTATION)))
 for i,p in enumerate(samples):scene.add(rt.Receiver('rx_'+str(i),position=setup.robot_position(p['x'],p['y']).tolist(),orientation=C.euler(setup.robot_rotation(p.get('yaw_body_deg',p.get('yaw_deg'))+mount))))
 H=np.full((len(samples),len(freq),2,2),np.nan+1j*np.nan);tau=np.full((len(samples),len(freq)),np.nan);aa=np.full_like(H,np.nan+1j*np.nan);angles={k:np.full_like(tau,np.nan) for k in ['theta_t','phi_t','theta_r','phi_r']};counts=np.zeros_like(tau,dtype=int)
 geometries=[]
 for fi,f in enumerate(freq):
  if time.monotonic()-started>7200:raise TimeoutError('frozen 7200s RF budget exceeded')
  C.set_bin(scene,banks,txp,rxp,fi,f);paths=solver(scene,**cfg)
  a=(np.asarray(paths.a[0])+1j*np.asarray(paths.a[1])).reshape(len(samples),2,2,-1);t=np.asarray(paths.tau).reshape(len(samples),-1)
  assert a.shape[-1]==1 and t.shape[1]==1,(a.shape,t.shape)
  assert np.isfinite(a).all() and (t>=0).all()
  aa[:,fi]=a[:,:,:,0];tau[:,fi]=t[:,0];counts[:,fi]=1;H[:,fi]=(a*np.exp(-2j*np.pi*f*t)[:,None,None,:]).sum(-1)
  for k in angles:angles[k][:,fi]=np.asarray(getattr(paths,k)).reshape(len(samples),-1)[:,0]
  if fi%32==0:
   np.save(directory/'H_PARTIAL.npy',H);(J/'RF_PROGRESS.json').write_text(json.dumps({'case':directory.name,'bin_done':fi,'of':257,'poses':len(samples),'seconds':time.monotonic()-started}));print(directory.name,fi,'/257',flush=True)
 np.save(directory/'H_LoS.npy',H);np.savez_compressed(directory/'PATHS_LoS.npz',a=aa,tau=tau,counts=counts,interactions=np.zeros_like(counts),**angles,freqs_hz=freq)
 (directory/'SAMPLES.json').write_text(json.dumps(samples,separators=(',',':')))
 result={'poses':len(samples),'shape':list(H.shape),'solver_batch_calls':257,'pose_frequency_evaluations':len(samples)*257,'layout':'pose,frequency,rx(+45,-45),tx(+45,-45)','max_depth':0,'mount_deg':mount,'anchor_xyz':setup.anchor_position.tolist(),'robot_z':setup.robot_antenna_z_m,'H_sha256':sha(directory/'H_LoS.npy'),'samples_sha256':sha(directory/'SAMPLES.json'),'counts_all_one':True,'all_finite':bool(np.isfinite(H).all()),'material_bindings':bindings}
 (directory/'MANIFEST.json').write_text(json.dumps(result,indent=2));return H,tau,result
try:
 original=json.loads(Path('/previous/L2_ATTEMPT3/SAMPLES.json').read_text());pilotH,pilottau,pilotmeta=calculate(original,CorridorSetup(),0,OUT/'PILOT8')
 old=np.load('/previous/L2_ATTEMPT3/CHANNELS.npz');rel=[float(np.linalg.norm(pilotH[i]-old['H'][i])/np.linalg.norm(old['H'][i])) for i in range(8)];s0=O.observe(old['H'],freq,None,None)['s'];s1=O.observe(pilotH,freq,None,None)['s'];sd=float(np.max(abs(s0-s1)));td=float(np.max(abs(pilottau-old['delays_s'])))
 pcheck={'max_relative_H':max(rel),'max_absolute_s':sd,'max_delay_s':td,'passed':max(rel)<=1e-4 and sd<=1e-5 and td<=1e-12,'original_single_receiver_source':'/previous/L2_ATTEMPT3/CHANNELS.npz','single_receiver_source_sha256':sha('/previous/L2_ATTEMPT3/CHANNELS.npz'),'method':'native multi-receiver PathSolver vs archived native single-receiver PathSolver; no analytical substitution'}
 (OUT/'PILOT_VERIFICATION.json').write_text(json.dumps(pcheck,indent=2));assert pcheck['passed'],pcheck
 inputs=OUT/'INPUTS';inputs.mkdir();full=OUT/'FULL_RF';full.mkdir();records=[];preserved={}
 for case in json.loads((J/'PLAN.json').read_text())['RF']['cases']:
  route,anchor,mount=case.split('_');mount=int(mount[1:]);setup=CorridorSetup(anchor_x_m=4.0 if anchor=='aA' else 10.0)
  posesfile=T/('rf_poses_'+route+'.json');samples=json.loads(posesfile.read_text());assert [p['pose_id'] for p in samples]==list(range(len(samples)))
  hfile=S2/('H_'+case+'.npy');hm=S2/('H_'+case+'.manifest.json');oldmeta=json.loads(hm.read_text());hsha=sha(hfile);assert hsha==oldmeta['outputs'][0]['sha256']
  assert np.load(hfile,mmap_mode='r').shape==(len(samples),257,2,2)
  for p in [posesfile,hfile,hm,S6/('results_'+case+'.csv'),S6/('manifest_'+case+'.json')]+list(T.glob('timeline_'+route+'_*.csv')):
   assert p.exists(),p
   preserved[str(p)]=sha(p);target=full/p.name if p==hfile else inputs/p.name
   if target.exists():assert sha(target)==sha(p)
   else:shutil.copyfile(p,target)
  H,tt,rec=calculate(samples,setup,mount,OUT/case)
  target=OUT/('H_LoS_'+case+'.npy');shutil.copyfile(OUT/case/'H_LoS.npy',target)
  rec.update(case=case,input_H_sha256=hsha,input_rf_poses_sha256=sha(posesfile));records.append(rec)
  (OUT/'CASES.json').write_text(json.dumps(records,indent=2));print(case,'complete',flush=True)
 # Preserve stored full RF path traces for R2-A; these are historical, not newly simulated.
 shutil.copytree(S2/'traces_R2_aA',OUT/'STORED_PATH_TRACES_R2_aA')
 for n in ['G3_continuity_R2_aA.json','G3_continuity_R2_aB.json','G3_continuity_R4_aA.json','G3_continuity_R4_aB.json','G3_continuity_R5_aA.json','G3_continuity_R5_aB.json']:
  shutil.copyfile(S2/n,inputs/n)
 np.save(OUT/'freqs_hz.npy',freq)
 for p,h in preserved.items():assert sha(p)==h,p
 (OUT/'VERIFICATION.json').write_text(json.dumps({'state':'completed','cases':records,'pilot':pcheck,'wall_seconds':time.monotonic()-started,'original_inputs_unchanged':True,'original_input_sha256':preserved,'versions':{n:importlib.metadata.version(n) for n in ['sionna-rt','mitsuba','drjit','numpy']},'solver_cfg':cfg,'source_sha256':sha(__file__),'reflection_recalculation':False},indent=2))
except BaseException as e:
 (OUT/'FAILURE.json').write_text(json.dumps({'error':repr(e),'traceback':traceback.format_exc(),'seconds':time.monotonic()-started},indent=2));raise
