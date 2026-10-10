from pathlib import Path
import sys,json,time,hashlib,importlib.metadata,traceback
import numpy as np
ROOT=Path('/job'); SRC=ROOT/'source'; OUT=ROOT/'L2_ATTEMPT3';OUT.mkdir(exist_ok=False)
sys.path[:0]=[str(SRC/'scripts'),str(SRC/'src'),str(SRC/'scripts/g2_completion')]
started=time.monotonic();calls=0;rows=[];samples=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
try:
 import corridor_sionna_run as C
 import drjit as dr
 import sionna.rt as rt
 from qclean_uwb.drivesim import hs_lut as L,observation as O,pattern_apply as P
 from qclean_uwb.scenarios.corridor import CorridorSetup,ANCHOR_ROTATION
 dr.set_thread_count(1)
 C.BANK_DIR=Path('/legacy/source');C.BANK_MANIFEST=C.BANK_DIR/'results/SIONNA_G2_FFD_NOFLIP_20260924_01a0d30b/bank/BANK_MANIFEST.json'
 banks=C.load_banks();pbanks=[P.Bank(b) for b in banks];freq=banks[0]['freqs_hz'];assert len(freq)==257
 lutpath=C.BANK_DIR/'results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy';metap=lutpath.parent/'hs_lut_meta.json'
 meta=json.loads(metap.read_text())['meta'];step=meta['phi_deg'][2]
 lut=L.HsLut(dict(theta_deg=np.array(meta['theta_deg']),phi_deg=np.arange(-180.,180.,step),s=np.load(lutpath)))
 setup=CorridorSetup();rng=np.random.default_rng(20261007)
 for i in range(8):
  x,y,yaw=rng.uniform(*setup.robot_x_range_m),rng.uniform(-.7,.7),rng.uniform(-50.,230.)
  rx=setup.robot_position(x,y);d=rx-setup.anchor_position;dist=float(np.linalg.norm(d));ang=[float(v) for v in L.geometry_angles(setup.anchor_position,rx,yaw)]
  samples.append(dict(pose_id=i,x=float(x),y=float(y),yaw_deg=float(yaw),range_m=dist,angles_deg=ang))
 (OUT/'SAMPLES.json').write_text(json.dumps(samples,indent=2))
 cfg=dict(max_depth=0,los=True,specular_reflection=False,refraction=False)
 inputs=[lutpath,metap,C.BANK_MANIFEST]+[C.BANK_DIR/(n+'_bank.npz') for n in C.PORTS]
 sources=[Path(__file__),SRC/'scripts/drive_sim/lut_los_check.py',SRC/'scripts/corridor_sionna_run.py',SRC/'scripts/g2_completion/sionna_native_runtime.py',SRC/'src/qclean_uwb/drivesim/hs_lut.py',SRC/'src/qclean_uwb/drivesim/observation.py',SRC/'src/qclean_uwb/drivesim/pattern_apply.py',SRC/'src/qclean_uwb/scenarios/corridor.py']
 manifest=dict(revision='f81b42d541fdf9a37b6868d4901c2a3bb9d8090e',input_sha256={str(p):sha(p) for p in inputs},source_sha256={str(p):sha(p) for p in sources},samples_sha256=sha(OUT/'SAMPLES.json'),seed=20261007,ports=['LP_plus45','LP_minus45'],tx_column=0,frequency_hz=freq.tolist(),observation='Hann, 4N pad IFFT*N, leading edge 0.3, same RX-selected tap, no noise',cfg=cfg,threshold=.005,versions={n:importlib.metadata.version(n) for n in ['sionna-rt','mitsuba','drjit','numpy']},max_solver_calls=2056,max_wall_seconds=600)
 (OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2))
 scene,bindings=C.build_scene(setup,OUT/'scene');txp,rxp=C.make_ports(banks);solver=rt.PathSolver()
 H=np.full((8,257,2,2),np.nan+1j*np.nan);HD=np.full_like(H,np.nan+1j*np.nan);HD10=np.full_like(H,np.nan+1j*np.nan);counts=np.zeros((8,257),int);delays=np.full((8,257),np.nan);coeff=np.full_like(H,np.nan+1j*np.nan)
 for p in samples:
  i=p['pose_id'];rx=setup.robot_position(p['x'],p['y']);direction=(rx-setup.anchor_position)/p['range_m']
  if 'tx' in scene.transmitters:scene.remove('tx');scene.remove('rx')
  scene.add(rt.Transmitter('tx',position=setup.anchor_position.tolist(),orientation=C.euler(ANCHOR_ROTATION)))
  scene.add(rt.Receiver('rx',position=rx.tolist(),orientation=C.euler(setup.robot_rotation(p['yaw_deg']))))
  HD[i]=L.los_h(pbanks,direction,p['yaw_deg'],dist_m=p['range_m']);HD10[i]=L.los_h(pbanks,direction,p['yaw_deg'],dist_m=10.)
  for fi,f in enumerate(freq):
   if time.monotonic()-started>590:raise TimeoutError('bounded RF budget exhausted; partial channels preserved')
   C.set_bin(scene,banks,txp,rxp,fi,f);a,tau,inter,obj=C.solve(solver,scene,cfg);calls+=1;counts[i,fi]=len(tau)
   if len(tau)!=1:raise ValueError('LoS path count differs from one: '+str((i,fi,len(tau))))
   delays[i,fi]=tau[0];coeff[i,fi]=a[...,0];H[i,fi]=(a*np.exp(-2j*np.pi*f*tau)[None,None,:]).sum(-1)
   if fi%32==0:np.savez_compressed(OUT/'CHANNELS_PARTIAL.npz',H=H,H_direct=HD,H_direct10=HD10,counts=counts,delays_s=delays,coeff=coeff,freqs_hz=freq,solver_calls=calls)
  outs=[O.observe(h[None],freq,None,None,tx=0) for h in [H[i],HD[i],HD10[i]]];sl=float(lut(*p['angles_deg']))
  row=dict(**p,s_lut=sl,s_sionna=float(outs[0]['s'][0]),s_direct_actual=float(outs[1]['s'][0]),s_direct10=float(outs[2]['s'][0]),tap_sionna=int(outs[0]['index'][0]),tap_direct=int(outs[1]['index'][0]),tap_direct10=int(outs[2]['index'][0]),power_sionna=outs[0]['power'][0].tolist(),power_direct=outs[1]['power'][0].tolist(),power_direct10=outs[2]['power'][0].tolist(),delay_geom_s=p['range_m']/O.C0)
  row['abs_ds_L2']=abs(sl-row['s_sionna']);row['ds_direct_actual_vs_sionna']=row['s_direct_actual']-row['s_sionna'];row['ds_distance']=row['s_direct_actual']-row['s_direct10'];row['ds_L1_at_pose']=sl-row['s_direct10']
  rows.append(row);(OUT/'ROWS_PARTIAL.json').write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)
 np.savez_compressed(OUT/'CHANNELS.npz',H=H,H_direct=HD,H_direct10=HD10,counts=counts,delays_s=delays,coeff=coeff,freqs_hz=freq)
 assert len(rows)==8 and np.isfinite(H).all() and len({r['pose_id'] for r in rows})==8
 result=dict(state='completed',solver_calls=calls,wall_seconds=time.monotonic()-started,rows=rows,threshold=.005,abs_ds_max=max(r['abs_ds_L2'] for r in rows),passed=max(r['abs_ds_L2'] for r in rows)<=.005,finite=True,input_preserved=all(sha(p)==manifest['input_sha256'][str(p)] for p in inputs))
 (OUT/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)
except BaseException as e:
 (OUT/'FAILURE.json').write_text(json.dumps(dict(state='failed',solver_calls=calls,completed_poses=len(rows),wall_seconds=time.monotonic()-started,error=repr(e),traceback=traceback.format_exc()),indent=2));raise
