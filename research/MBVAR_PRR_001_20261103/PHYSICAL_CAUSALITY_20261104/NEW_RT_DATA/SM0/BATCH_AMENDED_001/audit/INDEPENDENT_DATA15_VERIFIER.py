"""Read-only independent SM0 DATA15 verifier. No RT/FFT, no producer math imports.
Re-run under the frozen NumPy 1.26.4 runtime; JSON markers are the only output.
"""
import csv,datetime,hashlib,json,math,cmath,sys
from pathlib import Path
import numpy as np
H=Path('/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/NEW_RT_DATA/SM0')
S=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs/SM0/source')
B=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs')
BLOCK='results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
assert np.__version__=='1.26.4'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(p.read_text())
def err(x,y):
 x=np.asarray(x,complex);y=np.asarray(y,complex)
 assert x.shape==y.shape and np.isfinite(x).all() and np.isfinite(y).all()
 n=float(np.linalg.norm(y));peak=float(abs(y).max());assert n>0 and peak>0
 return dict(relative_l2=float(np.linalg.norm(x-y)/n),max_normalized=float(abs(x-y).max()/peak))
def small(x,y,tol=1e-8):
 r=err(x,y);assert r['relative_l2']<=tol and r['max_normalized']<=tol,r
 return r
lock=load(H/'BATCH_AMENDED_001/INPUT_LOCK.json')
assert sha(H/'BATCH_AMENDED_001/INPUT_LOCK.json')=='cdcb95b28d51b0636e417ff8f5dff08c0c2ee39b02a0fae6ce21e516aff0ea98'
for n,d in lock['source_sha256'].items():assert sha(S/n)==d,n
for n,d in lock['bank_sha256'].items():assert sha(B/n)==d,n
for n,d in lock['code_sha256'].items():assert sha(H/n)==d,n
assert sha(H/'RUNTIME_LOCK.json')==lock['runtime_lock_sha256']
runtime=load(H/'RUNTIME_LOCK.json')
go=load(H/'BATCH_AMENDED_001/GO_BATCH.json')
plan=load(H/'BATCH_AMENDED_001/PLAN.json')
for n,d in go['execution_sha256'].items():assert sha(H/'BATCH_AMENDED_001'/n)==d
assert go['authorized']==plan['poses']
expected=[dict(case='R4_aB_m0',pose_id=194),*plan['poses']]
assert len(expected)==15 and len({(v['case'],v['pose_id']) for v in expected})==15
freq=np.load(S/BLOCK/'freqs_hz.npy');assert freq.shape==(257,) and freq.dtype==np.float64
solver=load(S/'results/SIONNA_NATIVE41_REFRESH_20260925_01a0d84e/CONFIG.json')['solver']
assert solver==dict(max_depth=3,samples_per_src=100000,max_num_paths_per_src=1000000,synthetic_array=True,los=True,specular_reflection=True,refraction=True,diffraction=False,edge_diffraction=False,diffuse_reflection=False,seed=20260924)
results=[];accepted=[];pending=[]
for item in expected:
 case,pid=item['case'],item['pose_id']
 relative='CANARY_R4_194_001' if pid==194 and case=='R4_aB_m0' else 'BATCH_AMENDED_001/captures/'+case+'_'+str(pid)
 capture=H/relative
 if not (capture/'MANIFEST.json').exists():pending.append(item);continue
 m=load(capture/'MANIFEST.json')
 old=relative=='CANARY_R4_194_001'
 if m['status']=='RUNNING' or not (capture/'ARTIFACT_HASHES.json').exists():pending.append(item);continue
 assert m['status']==('STOP_MISMATCH' if old else 'AMENDED_NUMERICAL_PASS'),(case,pid,m['status'])
 assert m['case']==case and m['pose']['pose_id']==pid
 artifact=load(capture/'ARTIFACT_HASHES.json')
 for n,digest in artifact.items():
  path=(capture/n).resolve();assert path.is_relative_to(capture.resolve())
  assert sha(path)==digest,(case,pid,n)
 assert sha(capture/'RAW.npz')==m['raw_sha256']
 for k,v in m['validated_runtime'].items():assert runtime[k]==v,(case,pid,'runtime '+k)
 assert m['environment']['versions']==runtime['versions']
 assert m['environment']['variant']=='llvm_ad_mono_polarized' and m['environment']['drjit_threads']==1
 assert m['solver']==solver and m['original_not_counterfactual'] is True
 assert m['tx_position']==[10.,0.,2.7-.05]
 assert m['rx_position']==[m['pose']['x'],m['pose']['y'],.45]
 assert m['selected_tx']=='LP_plus45 column0' and m['rx_order']==['LP_plus45','LP_minus45']
 assert m['lock']['source_sha256']==lock['source_sha256'] and m['lock']['bank_sha256']==lock['bank_sha256']
 if not old:
  assert m['lock']==lock and m['go_sha256']==sha(H/'BATCH_AMENDED_001/GO_BATCH.json')
  assert m['amendment_id']=='SM0-PRECISION-001'
 else:
  assert sha(capture/'RAW.npz')=='59e44497f52421f50450f8e4dbaf9a0e73d98d5049de4ff170e96631f1c54a2f'
  rv=load(H/'PRECISION_AMENDMENT_001/REVALIDATION_002/RESULT.json')
  assert rv['status']=='AMENDED_NUMERICAL_PASS' and rv['input_sha256']['RAW.npz']==sha(capture/'RAW.npz')
 samples=load(S/BLOCK/case/'SAMPLES.json');sample=samples[pid]
 assert int(sample['pose_id'])==pid
 with (S/BLOCK/'INPUTS'/('timeline_'+case.split('_')[0]+'_Tnone.csv')).open() as f:timeline=[r for r in csv.DictReader(f) if int(r['pose_id'])==pid]
 assert len(timeline)==1
 for k in ('x','y','yaw_body_deg'):
  assert abs(float(sample[k])-float(timeline[0][k]))<=6e-7
  assert float(sample[k])==m['pose'][k]
 assert float(timeline[0]['t_s'])==m['pose']['t']
 original_manifest=load(S/BLOCK/case/'MANIFEST.json')
 bindings={v['object']:v for v in original_manifest['material_bindings']}
 for v in m['scene_bindings']:
  ref=bindings[v['object']]
  for k in ('itu_type','thickness_m','ply_sha256'):assert ref[k]==v[k]
  assert sha(capture/'scene'/(v['object']+'.ply'))==v['ply_sha256']
 with np.load(capture/'RAW.npz',allow_pickle=False) as z:a={k:z[k] for k in z.files}
 for n,schema in m['array_schema'].items():assert a[n].shape==tuple(schema['shape']) and str(a[n].dtype)==schema['dtype']
 for n,v in a.items():
  if v.dtype.kind in 'fc':assert np.isfinite(v).all(),(case,pid,n)
 assert np.array_equal(a['frequencies_hz'],freq)
 assert np.array_equal(a['archive_full'],np.load(S/BLOCK/'FULL_RF'/('H_'+case+'.npy'),mmap_mode='r')[pid,:,:,0])
 assert np.array_equal(a['archive_los'],np.load(S/BLOCK/('H_LoS_'+case+'.npy'),mmap_mode='r')[pid,:,:,0])
 assert a['a'].dtype==np.complex64 and a['tau'].dtype==np.float32
 labels=a['group_labels'].tolist();ng=len(labels);lookup={int(k):v for k,v in m['object_lookup'].items()}
 assert labels==sorted(set(labels)) and labels.count('DIRECT')==1
 for label,gid in zip(labels,a['group_ids']):assert hashlib.sha256(label.encode()).hexdigest()==gid
 direct=labels.index('DIRECT');assert int(a['direct_group'])==direct
 G=np.zeros((ng,257,2),complex);F=np.zeros_like(G);counts=np.zeros((ng,257),np.int32)
 native=[];legacy=[];direct_fields=[];scalar_legacy=[];max_raw_f64=0.
 for fi,f in enumerate(freq):
  lo,hi=map(int,a['offsets'][fi:fi+2]);n=hi-lo;assert n>0
  assert m['paths_per_bin'][fi]==n
  with np.load(capture/'bins'/f'{fi:03d}.npz',allow_pickle=False) as z:
   for k in ('a','tau','objects','interactions','primitives','vertices','valid','theta_t','phi_t','theta_r','phi_r','source_index','fields','original_field'):
    assert np.array_equal(z[k],a[k][lo:hi]),(case,pid,fi,k)
   assert np.array_equal(z['cfr32'],a['native_cfr32'][fi])
   assert float(z['frequency_hz'])==float(f)
  assert np.array_equal(a['source_index'][lo:hi],np.arange(n))
  coef=np.array(a['a'][lo:hi].transpose(1,2,0),order='C',copy=True);tau=a['tau'][lo:hi]
  v=coef[:,0,:]*np.exp(-2j*np.pi*f*tau)[None,:]
  assert v.dtype==np.complex64 and np.array_equal(v.T,a['original_field'][lo:hi])
  assert np.array_equal(v.sum(axis=1),a['native_original32'][fi])
  w=np.empty((n,2),complex);local_labels=[]
  for j in range(n):
   valid=bool(a['valid'][lo+j].any());chain=[]
   if not valid:assert np.all(coef[:,:,j]==0)
   for oid,kind in zip(a['objects'][lo+j],a['interactions'][lo+j]):
    oid,kind=int(oid),int(kind)
    if oid in (-1,4294967295):assert kind==0;continue
    assert oid in lookup and kind!=0
    chain.append([lookup[oid],kind])
   label='INVALID' if not valid else json.dumps(chain,separators=(',',':')) if chain else 'DIRECT'
   local_labels.append(label);gi=labels.index(label)
   assert int(a['source_group'][lo+j])==gi
   for rx in range(2):w[j,rx]=complex(coef[rx,0,j])*cmath.exp(complex(0,-2*math.pi*float(f)*float(tau[j])))
   G[gi,fi]+=v[:,j];F[gi,fi]+=w[j];counts[gi,fi]+=1
  matches=[j for j,label in enumerate(local_labels) if label=='DIRECT']
  assert matches==[int(a['direct_source_index'][fi])]
  di=matches[0]
  distance=math.sqrt(sum((t-r)**2 for t,r in zip(m['tx_position'],m['rx_position'])))
  assert abs(float(tau[di])-distance/299792458.)<=1e-12
  max_raw_f64=max(max_raw_f64,float(abs(w-a['fields'][lo:hi]).max()))
  native.append([complex(math.fsum(w[:,r].real),math.fsum(w[:,r].imag)) for r in range(2)])
  scalar_legacy.append([complex(math.fsum(float(x.real) for x in v[r]),math.fsum(float(x.imag) for x in v[r])) for r in range(2)])
  legacy.append(v.sum(axis=1));direct_fields.append(v[:,di])
 assert np.array_equal(counts,a['group_count']) and np.array_equal(counts==0,a['group_missing'])
 assert np.array_equal(counts.sum(0),np.diff(a['offsets']))
 f64closure=small(F.sum(0),np.array(native));small(F,a['group_fields']);small(native,a['native_f64']);small(F[direct],a['direct_f64'])
 legacyclosure=small(G.sum(0),np.array(scalar_legacy))
 if not old:
  assert np.array_equal(G,a['legacy_group_fields']) and np.array_equal(G.sum(0),a['legacy_native_full'])
 checks={}
 for name,x,y,tol in [('legacy_original_full',legacy,a['archive_full'],1e-3),('legacy_attribution_full',G.sum(0),a['archive_full'],1e-3),('legacy_los',direct_fields,a['archive_los'],1e-5)]:
  x=np.asarray(x);r=err(x,y);ports=[err(x[:,j],y[:,j]) for j in range(2)]
  assert all(e['relative_l2']<=tol for e in [r,*ports]),(case,pid,name,r,ports)
  checks[name]=dict(**r,per_rx=ports)
 result=dict(case=case,pose_id=pid,status='INDEPENDENT_NUMERICAL_PASS',capture=relative,raw_sha256=sha(capture/'RAW.npz'),manifest_sha256=sha(capture/'MANIFEST.json'),artifact_hashes_sha256=sha(capture/'ARTIFACT_HASHES.json'),verified_artifacts=len(artifact),bins=257,raw_paths=int(a['offsets'][-1]),groups=ng,checks=checks,f64closure=f64closure,legacyclosure=legacyclosure,max_independent_f64_perray_absolute_difference=max_raw_f64,original_status=m['status'],contract_timing='posthoc retained canary' if old else 'prospectively amended new pose')
 results.append(result);accepted.append({k:result[k] for k in ('case','pose_id','capture','raw_sha256','manifest_sha256')})
 print('SM0_DATA15_POSE_RESULT '+json.dumps(result),flush=True)
assert [v for v in expected if v in pending]==pending
summary=dict(decision='INCOMPLETE' if pending else 'ACCEPT',scope='PARTIAL_CLOSED_SM0_CAPTURES' if pending else 'ALL_15_AMENDED_SM0_DATA',auditor='independent_precision_audit',completed=len(results),pending=pending,captures=accepted,new_pathsolver_calls=0,real_RF_FFT_calls=0,source_files_verified=24,banks_verified=2,source_runtime_lock_sha256=lock['runtime_lock_sha256'],timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),original_STOP_preserved=True,causality='NOT_TESTED')
if not pending:
 batch=load(H/'BATCH_AMENDED_001/BATCH_RESULT.json')
 assert batch['status']=='ALL_14_NUMERICAL_PASS_PENDING_INDEPENDENT_AUDIT' and len(batch['results'])==14
 for record,entry in zip(batch['results'],plan['poses']):
  assert record['case']==entry['case'] and record['pose_id']==entry['pose_id'] and record['exit_code']==0 and record['status']=='AMENDED_NUMERICAL_PASS'
 print('SM0_DATA15_ACCEPTANCE_RESULT '+json.dumps(summary),flush=True)
else:print('SM0_DATA15_PARTIAL_RESULT '+json.dumps(summary),flush=True)
