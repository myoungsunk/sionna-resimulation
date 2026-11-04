"""C3 G2 four-yaw capture only. No old-yaw RT, archive spoof, or G4 model."""
import argparse,datetime,importlib.util,json,os,sys,time,traceback
from pathlib import Path
from authority import HERE,check,sha

def put(p,x):p.write_bytes((json.dumps(x,indent=2,allow_nan=False)+'\n').encode())
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def module(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def inventory(root):return {p.relative_to(root).as_posix():sha(p) for p in sorted(root.rglob('*')) if p.is_file() and p.name!='ARTIFACT_HASHES.json'}

def frequency_value(value):
 import numpy as np
 a=np.asarray(value).reshape(-1)
 if a.size!=1 or not np.isfinite(a).all():raise ValueError('native frequency scalar')
 return float(a[0])

def main():
 p=argparse.ArgumentParser();p.add_argument('--go',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--revision',required=True);args=p.parse_args()
 plan,lock,go=check(args.go,args.out)
 if len(args.revision)!=40 or any(c not in '0123456789abcdef' for c in args.revision):raise ValueError('published revision')
 old=HERE.parents[1]/'NEW_RT_DATA/SM0'
 sys.path.insert(0,str(old/'PRECISION_AMENDMENT_001'))
 legacy=module('sm0_frozen_producer',old/'PRECISION_AMENDMENT_001/producer.py')
 qa=module('sm2_raw_qa',HERE/'qa.py')
 import numpy as np
 from native_math import grouped_spectra
 runtime=legacy.validate_runtime({'runtime_lock_sha256':lock['legacy_dependencies']['RUNTIME_LOCK.json']['sha256']})
 # All GO/input/runtime checks precede output and simulator imports.
 args.out.mkdir();(args.out/'FAILURES.jsonl').touch()
 whole=dict(question_id=plan['question_id'],status='RUNNING',code_revision=args.revision,bindings_sha256=go['bindings_sha256'],
            go_sha256=sha(args.go),command=sys.argv,start_utc=stamp(),validated_runtime=runtime,
            primary_solver_calls=0,repeat_solver_calls=0,completed_conditions=0,training_runs=0,source_model_initializations=0,
            archive_comparison='NOT_APPLICABLE_NEW_YAW',scientific_source_revision=plan['source_revision'])
 put(args.out/'MANIFEST.json',whole);current=None
 try:
  source=Path(plan['source_linux']);bank=Path(plan['bank_linux'])
  sys.path[:0]=[str(source/'scripts'),str(source/'src')]
  import corridor_sionna_run as C
  import mitsuba as mi
  import sionna.rt as rt
  import drjit as dr
  dr.set_thread_count(1)
  if dr.thread_count()!=1 or mi.variant()!='llvm_ad_mono_polarized':raise ValueError('variant/thread drift')
  C.BANK_DIR=bank;banks=C.load_banks();freq=np.asarray(banks[0]['freqs_hz'],np.float64)
  expected_freq=np.load(source/legacy.BLOCK/'freqs_hz.npy')
  if len(freq)!=257 or not np.array_equal(freq,expected_freq):raise ValueError('frequency grid')
  cfg=json.loads((source/legacy.CFG).read_bytes())['solver']
  if cfg['max_depth']!=3 or cfg['seed']!=20260924 or cfg['samples_per_src']!=100000:raise ValueError('solver config')
  expected_bindings=json.loads((source/legacy.BLOCK/'R4_aB_m0/MANIFEST.json').read_bytes())['material_bindings']
  index=[]
  for row in plan['authorized']:
   current=row['id'];out=args.out/current;out.mkdir();(out/'bins').mkdir();(out/'repeat').mkdir()
   receipt=dict(status='RUNNING',condition=row,start_utc=stamp(),code_revision=args.revision,go_sha256=sha(args.go),primary_solver_calls=0,repeat_solver_calls=0)
   put(out/'MANIFEST.json',receipt);bins=[];repeats={};direct_checks=[]
   try:
    setup=C.CorridorSetup(anchor_x_m=10.)
    if not all(v['passed'] for v in setup.validate()):raise ValueError('geometry')
    scene,bindings=C.build_scene(setup,out/'scene')
    if bindings!=expected_bindings:raise ValueError('scene PLY/material binding')
    rxpos=setup.robot_position(row['xyz'][0],row['xyz'][1]);rxorientation=C.euler(setup.robot_rotation(row['yaw_deg']));txorientation=C.euler(C.ANCHOR_ROTATION)
    if not np.array_equal(rxpos,np.asarray(row['xyz'])):raise ValueError('receiver position')
    scene.add(rt.Transmitter('tx',position=setup.anchor_position.tolist(),orientation=txorientation))
    scene.add(rt.Receiver('rx',position=rxpos.tolist(),orientation=rxorientation))
    lookup={int(v.object_id):key for key,v in scene.objects.items()};tx,rx=C.make_ports(banks);solver=rt.PathSolver()
    receipt.update(solver=cfg,scene_bindings=bindings,object_lookup=lookup,tx_position=setup.anchor_position.tolist(),rx_position=rxpos.tolist(),tx_orientation_zyx_rad=txorientation,rx_orientation_zyx_rad=rxorientation,selected_tx='LP_plus45 column0',rx_order=['LP_plus45','LP_minus45'])
    delay=float(np.linalg.norm(setup.anchor_position-rxpos)/299792458.)
    for fi,frequency in enumerate(freq):
     C.set_bin(scene,banks,tx,rx,fi,float(frequency))
     if frequency_value(scene.frequency) not in (float(frequency),float(np.float32(frequency))):raise ValueError('bin frequency drift')
     if not np.allclose(np.asarray(scene.receivers['rx'].orientation).reshape(-1),rxorientation,atol=1e-7,rtol=1e-7):raise ValueError('RX orientation drift')
     if not np.allclose(np.asarray(scene.transmitters['tx'].orientation).reshape(-1),txorientation,atol=1e-7,rtol=1e-7):raise ValueError('TX orientation drift')
     for role,desired in ((scene.receivers['rx'],rxpos),(scene.transmitters['tx'],setup.anchor_position)):
      if not np.allclose(np.asarray(role.position).reshape(-1),desired,atol=1e-6,rtol=0):raise ValueError('position drift')
     if whole['primary_solver_calls']+whole['repeat_solver_calls']>=1040:raise ValueError('call budget')
     paths=solver(scene,**cfg);whole['primary_solver_calls']+=1;receipt['primary_solver_calls']+=1
     saved=legacy.extract(paths,float(frequency),lookup,delay)
     saved['cfr32']=np.asarray(paths.cfr(frequencies=mi.Float([0.]),normalize_delays=False,normalize=False,out_type='numpy')).reshape(2,2)[:,0]
     np.savez_compressed(out/'bins'/f'{fi:03d}.npz',**saved,frequency_hz=np.asarray(frequency));bins.append(saved)
     qa.native_cfr_check(saved['cfr32'],(2,))
     # Per-bin projection detects a mismatch before tracing subsequent bins.
     single=dict(a=saved['a'],tau=saved['tau'],offsets=np.array([0,len(saved['tau'])]),direct_source_index=np.array([saved['direct_index']]),frequencies_hz=np.array([frequency]))
     direct_checks.append(qa.direct_projection(single,[{**b, 'e_theta':b['e_theta'][fi:fi+1], 'e_phi':b['e_phi'][fi:fi+1]} for b in banks],row['xyz'],row['yaw_deg']))
     if fi in plan['repeat_bins']:
      paths2=solver(scene,**cfg);whole['repeat_solver_calls']+=1;receipt['repeat_solver_calls']+=1
      second=legacy.extract(paths2,float(frequency),lookup,delay)
      np.savez_compressed(out/'repeat'/f'{fi:03d}.npz',**second,frequency_hz=np.asarray(frequency))
      repeats[str(fi)]=qa.repeat_check(saved,second)
     if fi%32==0:print('C3_BIN',current,fi,len(saved['tau']),flush=True)
    groups=grouped_spectra(bins)
    arrays={k:np.concatenate([v[k] for v in bins],axis=0) for k in ('a','tau','objects','interactions','primitives','vertices','valid','theta_t','phi_t','theta_r','phi_r','source_index','fields','original_field')}
    arrays.update(groups,offsets=np.r_[0,np.cumsum([len(v['tau']) for v in bins])],frequencies_hz=freq,direct_source_index=np.asarray([v['direct_index'] for v in bins],np.int32),native_f64=np.asarray([v['independent_sum'] for v in bins]),native_original32=np.asarray([v['original_sum'] for v in bins]),native_cfr32=np.asarray([v['cfr32'] for v in bins]))
    arrays['direct_f64']=arrays['group_fields'][int(arrays['direct_group'])]
    np.savez_compressed(out/'RAW.npz',**arrays)
    qa.source_groups(arrays,lookup);numerical,legacy_groups=qa.evaluate_arrays(arrays)
    projection=qa.direct_projection(arrays,banks,row['xyz'],row['yaw_deg'])
    arrays['legacy_group_fields']=legacy_groups;arrays['legacy_native_full']=legacy_groups.sum(0)
    np.savez_compressed(out/'RAW.npz',**arrays)
    put(out/'QA.json',dict(numerical=numerical,direct_projection=projection,per_bin_direct_projection=direct_checks,repeats=repeats,semantic_replay='EXACT',bins=257))
    receipt.update(status='C3_RAW_NUMERICAL_PASS',raw_sha256=sha(out/'RAW.npz'),groups=len(groups['group_labels']),paths_per_bin=[len(v['tau']) for v in bins])
    whole['completed_conditions']+=1;index.append(dict(condition_id=current,coordinate=row['coordinate'],yaw_deg=row['yaw_deg'],raw_sha256=receipt['raw_sha256'],status=receipt['status']))
   except BaseException as e:
    receipt.update(status='STOP_ERROR',error=repr(e));raise
   finally:
    receipt['end_utc']=stamp();put(out/'MANIFEST.json',receipt);put(out/'ARTIFACT_HASHES.json',inventory(out));put(args.out/'MANIFEST.json',whole)
  if whole['primary_solver_calls']!=1028 or whole['repeat_solver_calls']!=12 or len(index)!=4:raise ValueError('complete count')
  import csv
  with (args.out/'INDEX.csv').open('x',newline='',encoding='utf8') as f:
   w=csv.DictWriter(f,fieldnames=list(index[0]));w.writeheader();w.writerows(index)
  whole['status']='C3_CANARY_EXECUTION_PASS_PENDING_INDEPENDENT_AUDIT'
 except BaseException as e:
  whole.update(status='STOP_ERROR',error=repr(e),failed_condition=current)
  with (args.out/'FAILURES.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(dict(condition=current,error=repr(e),traceback=traceback.format_exc()))+'\n')
  raise
 finally:
  whole['end_utc']=stamp();put(args.out/'MANIFEST.json',whole);put(args.out/'ARTIFACT_HASHES.json',inventory(args.out))
 print('C3_RESULT',json.dumps(whole),flush=True)

if __name__=='__main__':main()
