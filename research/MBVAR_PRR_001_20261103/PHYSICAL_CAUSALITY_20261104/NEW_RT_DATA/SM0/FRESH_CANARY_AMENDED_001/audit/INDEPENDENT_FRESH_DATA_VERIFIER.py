"""Bounded independent FRESH194 DATA audit. Read-only; no RT or causal attribution.
Reuses the SHA-pinned independent DATA15 audit's per-ray checks, not producer QA.
Only reads fresh capture and computes FFT after closed launcher PASS gate.
"""
import csv,datetime,hashlib,json,math,cmath,sys,os,platform,importlib.metadata
from pathlib import Path
import numpy as np
from scipy.fft import ifft
H=Path('/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0')
Q=H/'FRESH_CANARY_AMENDED_001'
S=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs/SM0/source')
B=S.parent.parent
BLOCK='results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(p.read_text())
run=load(Q/'RUN_RESULT.json')
if run['status']!='NUMERICAL_PASS_PENDING_INDEPENDENT_DATA_AUDIT':
 print('SM0_FRESH_DATA_WAIT '+json.dumps(dict(status=run['status'],fresh_capture_reads=0,FFT_calls=0)));sys.exit(2)
assert run['exit_code']==0 and run['capture_status']=='AMENDED_NUMERICAL_PASS'
lock=load(Q/'INPUT_LOCK.json');go=load(Q/'GO_CANARY.json');plan=load(Q/'PLAN.json')
assert sha(Q/'INPUT_LOCK.json')=='cdcb95b28d51b0636e417ff8f5dff08c0c2ee39b02a0fae6ce21e516aff0ea98'
assert sha(Q/'GO_CANARY.json')=='d3f93ace4315cdc64971ee838c54f3bad5961727c937dfdd3a2dc5877fe5308d'
assert run['go_sha256']==sha(Q/'GO_CANARY.json') and run['plan_sha256']==sha(Q/'PLAN.json')
assert go['schema']=='SM0_GO_V1' and go['decision']=='GO'
assert go['authorized']==plan['poses']==[dict(case='R4_aB_m0',pose_id=194)]
for key in ('code_sha256','source_sha256','bank_sha256','thresholds','primary_reference','runtime_lock_sha256'):assert go[key]==lock[key]
for n,d in go['execution_sha256'].items():assert sha(Q/n)==d
for n,d in lock['source_sha256'].items():assert sha(S/n)==d,n
assert sha(S/'SOURCE_HASHES.json')==lock['source_hash_manifest_sha256']
for n,d in lock['bank_sha256'].items():assert sha(B/n)==d,n
for n,d in lock['code_sha256'].items():assert sha(H/n)==d,n
assert sha(H/'RUNTIME_LOCK.json')==lock['runtime_lock_sha256']
runtime=load(H/'RUNTIME_LOCK.json')
actual=dict(python=sys.version,executable=sys.executable,platform=platform.platform(),
 cpu_model=[v.split(':',1)[1].strip() for v in Path('/proc/cpuinfo').read_text().splitlines() if v.startswith('model name')][:1],
 versions={n:importlib.metadata.version(n) for n in ('numpy','scipy','sionna-rt','mitsuba','drjit')},
 all_distributions={d.metadata['Name']:d.version for d in importlib.metadata.distributions(path=[os.environ['PYTHONPATH']])},
 llvm_path=os.environ['DRJIT_LIBLLVM_PATH'],llvm_sha256=sha(Path(os.environ['DRJIT_LIBLLVM_PATH'])),
 environment={k:os.environ[k] for k in runtime['environment']})
for k,v in actual.items():assert runtime[k]==v,('auditor_runtime',k)
relative='FRESH_CANARY_AMENDED_001/CAPTURE_001';capture=H/relative
m=load(capture/'MANIFEST.json');old=False;case='R4_aB_m0';pid=194
assert m['status']=='AMENDED_NUMERICAL_PASS' and m['case']==case and m['pose']['pose_id']==pid
assert m['lock']==lock and m['go_sha256']==sha(Q/'GO_CANARY.json')
assert m['amendment_id']=='SM0-PRECISION-001'
assert sha(capture/'RAW.npz')==m['raw_sha256']==run['raw_sha256']
assert sha(capture/'MANIFEST.json')==run['manifest_sha256']
parse=datetime.datetime.fromisoformat
assert parse('2026-11-04T08:52:00+00:00')<parse(run['start_utc'])<=parse(m['start_utc'])<=parse(m['end_utc'])<=parse(run['end_utc'])
artifact=load(capture/'ARTIFACT_HASHES.json')
actual_files={str(p.relative_to(capture)) for p in capture.rglob('*') if p.is_file() and p.name!='ARTIFACT_HASHES.json'}
assert actual_files==set(artifact)
for n,d in artifact.items():
 p=(capture/n).resolve();assert p.is_relative_to(capture.resolve());assert sha(p)==d,n
for k,v in m['validated_runtime'].items():assert runtime[k]==v,k
assert m['validated_runtime']==actual
assert m['environment']['versions']==runtime['versions']
assert m['environment']['variant']=='llvm_ad_mono_polarized' and m['environment']['drjit_threads']==1
assert m['environment']['threads']=={k:'1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')}
assert m['original_not_counterfactual'] is True
assert m['tx_position']==[10.,0.,2.7-.05] and m['rx_position']==[m['pose']['x'],m['pose']['y'],.45]
assert m['selected_tx']=='LP_plus45 column0' and m['rx_order']==['LP_plus45','LP_minus45']
freq=np.load(S/BLOCK/'freqs_hz.npy');assert freq.shape==(257,) and freq.dtype==np.float64
assert np.array_equal(freq,6250400000.+1950000.*np.arange(257))
solver=load(S/'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json')['solver']
assert solver==dict(max_depth=3,samples_per_src=100000,max_num_paths_per_src=1000000,synthetic_array=True,los=True,specular_reflection=True,refraction=True,diffraction=False,edge_diffraction=False,diffuse_reflection=False,seed=20260924)
assert m['solver']==solver
# SHA-pinned independently authored body: checks raw schemas, every bin/ray,
# C-contiguous complex64 reduction, independent cmath/F64 fsum, masks/groups,
# scene/material/timeline and per-RX original archive parity. No QA imports.
vpath=B/'SM0/INDEPENDENT_DATA15_VERIFIER.py'
assert sha(vpath)=='b6ef938a20c855b089475b5c99ef1dab1e4642ba8792d89c78bcae555c730d15'
vsrc=vpath.read_text()
helpers=vsrc[vsrc.index('def err('):vsrc.index("lock=load(H/'BATCH_AMENDED_001/INPUT_LOCK.json')")]
body=vsrc[vsrc.index(' samples=load(S/BLOCK/case/'):vsrc.index(' results.append(result);')]
body='\n'.join(line[1:] if line.startswith(' ') else line for line in body.splitlines())
exec(helpers,globals());exec(body,globals())
# Original STOP is preserved; its retained data is comparison evidence only.
oldcap=H/'CANARY_R4_194_001'
assert sha(oldcap/'RAW.npz')=='59e44497f52421f50450f8e4dbaf9a0e73d98d5049de4ff170e96631f1c54a2f'
assert sha(oldcap/'MANIFEST.json')=='4db494d9c75da34a9139eeddd8fc7aeff4d92bc2fb533809e028d79178884164'
assert load(oldcap/'MANIFEST.json')['status']=='STOP_MISMATCH'
with np.load(oldcap/'RAW.npz',allow_pickle=False) as z:retained={k:z[k] for k in z.files}
common=sorted(set(a)&set(retained));different=[k for k in common if not np.array_equal(a[k],retained[k])]
maxdiff={k:float(np.max(abs(a[k]-retained[k]))) for k in different if a[k].dtype.kind in 'fc' and a[k].shape==retained[k].shape}
# No exact compressed NPZ container-byte criterion is imposed.
window=.5-.5*np.cos(2*np.pi*np.arange(257)/256)
def transform(x):return ifft(np.asarray(x,complex)*window[:,None],n=1028,axis=0)*257
def signed(v):
 p=abs(v)**2;den=float(p.sum());assert den>0
 return float((p[0]-p[1])/den),den,p
def detect(c):
 assert np.isfinite(c).all()
 rx=int(np.argmax(abs(c).max(0)));peak=float(abs(c[:,rx]).max());assert peak>0
 tap=int(np.flatnonzero(abs(c[:,rx])>=.3*peak)[0]);s,den,p=signed(c[tap])
 return dict(tap=tap,rx=rx,s=s,denominator=den,power=p.tolist())
def observe(full,los):
 f,l=detect(full),detect(los);same=signed(full[l['tap']])[0]
 fixed=same-l['s'];choice=f['s']-same;emp=f['s']-l['s']
 assert abs(emp-fixed-choice)<=1e-14
 return dict(full=f,los=l,same_los_tap=fixed,detector_choice=choice,e_mp=emp,identity_error=abs(emp-fixed-choice))
native=observe(transform(G.sum(0)),transform(G[direct]))
archive=observe(transform(a['archive_full']),transform(a['archive_los']))
for k in ('full','los'):assert native[k]['tap']==archive[k]['tap'],(k,native,archive)
# Separately compare native-original32 legacy reduction to the semantic-sum reference.
original32=observe(transform(a['native_original32']),transform(a['original_field'][a['offsets'][:-1]+a['direct_source_index']]))
for k in ('full','los'):assert original32[k]['tap']==native[k]['tap']
empdiff=abs(native['e_mp']-archive['e_mp'])
answer=dict(decision='ACCEPT',scope='FRESH_NATIVE_R4_194_ONLY_DATA',question_id='SM0-FRESH-CANARY-001',
 capture=relative,raw_sha256=sha(capture/'RAW.npz'),manifest_sha256=sha(capture/'MANIFEST.json'),
 artifact_hashes_sha256=sha(capture/'ARTIFACT_HASHES.json'),run_result_sha256=sha(Q/'RUN_RESULT.json'),
 execution_log_sha256=sha(Q/'EXECUTION.log'),go_sha256=sha(Q/'GO_CANARY.json'),input_lock_sha256=sha(Q/'INPUT_LOCK.json'),
 runtime_lock_sha256=lock['runtime_lock_sha256'],start_utc=m['start_utc'],end_utc=m['end_utc'],
 independent_raw_verification=result,source_files_verified=24,banks_verified=2,scientific_code_files_verified=7,
 runtime_actual_verified=True,retained_determinism=dict(common_array_count=len(common),array_names_different=different,max_absolute_difference=maxdiff,container_byte_equality_required=False),
 detector_native=native,detector_archive=archive,detector_original32=original32,
 native_archive_eMP_absolute_difference=empdiff,old_STOP_preserved=True,new_pathsolver_calls=0,
 fresh_RF_FFTs=6,completed14_or_C0B_reruns=0,C1_C2_GO='NOT_GRANTED',
 causality='NOT_TESTED',timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
print('SM0_FRESH_DATA_AUDIT_RESULT '+json.dumps(answer),flush=True)
