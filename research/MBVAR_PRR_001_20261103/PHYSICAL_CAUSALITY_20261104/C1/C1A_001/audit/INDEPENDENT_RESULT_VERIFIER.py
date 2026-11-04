"""Independent C1a result audit. Read-only; no production core/evaluator imports.
All posterior math is reconstructed from frozen priors; no recursive filter or RT.
"""
import csv,datetime,hashlib,json,sys,os,platform
from pathlib import Path
import numpy as np
Q=Path('/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C1/C1A_001')
B=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs/C1A_001')
O=Q/'RESULTS_001'
def load(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
def arrays(p):
 with np.load(p,allow_pickle=False) as z:return {k:z[k] for k in z.files}
run=load(Q/'RUN_RESULT.json')
if run['status']=='RUNNING':
 print('C1A_RESULT_AUDIT_WAIT '+json.dumps(dict(status='RUNNING',scientific_data_reads=0)));sys.exit(2)
if run['status']=='STOP':
 print('C1A_RESULT_AUDIT_RESULT '+json.dumps(dict(decision='STOP',scope='C1A_EXECUTION_FAILURE',run_result=run,new_runs=0)));sys.exit(3)
assert run['status']=='NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT' and run['exit_code']==0
assert sys.version_info[:3]==(3,11,17) and np.__version__=='1.26.4'
assert all(os.environ[n]=='1' for n in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'))
plan=load(Q/'PLAN.json');go=load(Q/'GO.json');lock=load(Q/'INPUT_LOCK.json');manifest=load(O/'MANIFEST.json')
expected_authorized=dict(stage='C1a_only',routes=['R2','R4','R5'],biases=['B0','L2'],seeds=list(range(10,30)))
assert plan['authorized']==go['authorized']==expected_authorized and go['schema']=='C1A_GO_V1' and go['decision']=='GO'
assert manifest['bindings_sha256']==go['bindings_sha256']
for n,d in go['bindings_sha256'].items():assert sha(Q/n)==d,n
assert sha(Q/'GO.json')==run['go_sha256']==manifest['go_sha256']=='298652840436a042e63aedcf1ef89d6a0077f0a63c36eba963b10dc0ba75dfcd'
assert sha(Q/'INPUT_LOCK.json')=='d40567d088c02d09e95e32530c3377d1aa68680157f31b3baf10cb1889efe453'
for n,v in lock['sources'].items():
 assert sha(B/n)==v['payload_sha256'] and (B/n).stat().st_size==v['size'],n
gov=load(Q/'GOVERNANCE.json')
for n,d in gov['documents_sha256'].items():assert sha(Path('/mnt/c/Users/Myoungsun Kim/.codex/research-governance')/n)==d
assert manifest['python']==sys.version and manifest['numpy']==np.__version__ and manifest['platform']==platform.platform()
assert manifest['scientific_source_revision']=='17cbfb8bef78518729d5010dbf463df87e828c0c'
assert manifest['new_filter_replays']==manifest['new_RT_calls']==0
parse=datetime.datetime.fromisoformat
assert parse(run['start_utc'])<=parse(manifest['start_utc'])<=parse(manifest['end_utc'])<=parse(run['end_utc'])
assert manifest['status']==run['status']
artifact=load(O/'ARTIFACT_HASHES.json')
actual_files={p.relative_to(O).as_posix() for p in O.rglob('*') if p.is_file() and p.name!='ARTIFACT_HASHES.json'}
assert actual_files==set(artifact)
for n,d in artifact.items():
 p=(O/n).resolve();assert p.is_relative_to(O.resolve()) and sha(p)==d,n
assert (O/'FAILURES.jsonl').stat().st_size==0
export=load(Q/'FROZEN_PACKETS/MANIFEST.json');assert len(export)==18
for n,v in export.items():
 e=lock['sources'][v['input_lock_key']];p=Q/'FROZEN_PACKETS'/n
 assert sha(p)==v['sha256']==e['payload_sha256'] and p.stat().st_size==v['size']==e['size'],n
maxima={};counts=dict(cells=0,priors=0,posterior_rows=0,summary_rows=0)
def circular(delta):return np.arctan2(np.sin(delta),np.cos(delta))
def compare(name,a,b,angular=False):
 a=np.asarray(a);b=np.asarray(b);assert a.shape==b.shape,(name,a.shape,b.shape)
 assert np.isfinite(a).all() and np.isfinite(b).all(),name
 d=circular(a-b) if angular else a-b
 maxima[name]=max(maxima.get(name,0.),float(abs(d).max()))
 if angular:assert np.all(abs(d)<=1e-10+1e-10*abs(b)),(name,maxima[name])
 else:assert np.allclose(a,b,atol=1e-10,rtol=1e-10),(name,maxima[name])
min_eigen=float('inf');max_sym=0.;check_record={}
def record(name,a,b,angular=False):
 d=(a-b+np.pi)%(2*np.pi)-np.pi if angular else a-b
 check_record[name]=max(check_record.get(name,0.),float(abs(d).max()))
def covariance(name,p):
 global min_eigen,max_sym
 sym=abs(p-p.swapaxes(-1,-2)).max(axis=(1,2))
 ev=np.linalg.eigvalsh((p+p.swapaxes(-1,-2))/2);scale=np.maximum(1.,abs(ev).max(1))
 assert np.all(sym<=1e-12*scale) and np.all(ev[:,0]>=-1e-12*scale),name
 min_eigen=min(min_eigen,float(ev.min()));max_sym=max(max_sym,float(sym.max()))
 key=name+'_minimum_eigenvalue';check_record[key]=min(check_record.get(key,float('inf')),float(ev.min()))
 key=name+'_maximum_symmetry_error';check_record[key]=max(check_record.get(key,0.),float(sym.max()))
summary=load(O/'CELL_SUMMARY.json');summary_index=0
expected_cell_names=set()
arms=('FF','LF','FL','LL')
with (O/'POSE_EFFECTS.csv').open(newline='') as f:
 reader=csv.DictReader(f)
 assert reader.fieldnames==['route','bias','seed','pose_id','t_s','arm','xy_m','heading_deg','delta_xy_m','delta_heading_deg']
 for route in expected_authorized['routes']:
  for bias in expected_authorized['biases']:
   full=arrays(B/f'{route}_aB_m0_{bias}_Full.npz');los=arrays(B/f'{route}_aB_m0_{bias}_Native_LoS.npz')
   truth=arrays(B/f'{route}_{bias}_TRUTH.npz');n=plan['route_rows'][route]
   for seed in expected_authorized['seeds']:
    cell=f'{route}_{bias}_{seed}';expected_cell_names.add(cell+'.npz')
    tr=arrays(B/(cell+'_TRACE.npz'));saved=arrays(O/'cells'/(cell+'.npz'))
    for packet in (full,los,truth,saved):
     for key in ('pose_id','t'):assert np.array_equal(packet[key],tr[key]),(cell,key)
    assert tr['pose_id'].shape==(n,) and len(np.unique(tr['pose_id']))==n and np.all(np.diff(tr['t'])>0)
    assert tr['mask'].dtype==bool and np.array_equal(saved['mask'],tr['mask'])
    assert np.array_equal(saved['arms'],np.array(arms))
    for key,ref in [('prior',tr['prior']),('Pprior',tr['Pprior']),('H',tr['H']),('h',tr['h']),('mu',tr['mu']),('R',tr['Rvar']),('z_full',full['z']),('z_los',los['z']),('delta_z',los['z']-full['z'])]:
     assert np.array_equal(saved[key],ref),(cell,key)
    X,P,H,h,mu,R,mask=(tr[k] for k in ('prior','Pprior','H','h','mu','Rvar','mask'))
    assert n==len(X) and np.array_equal(tr['weight'],np.ones(n))
    compare('full_mean',mu,full['muMB']);record('full_mean',mu,full['muMB'])
    compare('full_innovation',tr['nu'],full['z']-h-mu);record('full_innovation',tr['nu'],full['z']-h-mu)
    compare('W0_effective_R',R,tr['Reff']);record('W0_effective_R',R,tr['Reff'])
    # Independent analytic inverse of the symmetric 2x2 innovation covariance.
    ph=np.einsum('nij,nkj->nik',P,H)
    S=np.einsum('nij,njk->nik',H,ph)+R;S=(S+S.swapaxes(-1,-2))/2
    determinant=S[:,0,0]*S[:,1,1]-S[:,0,1]*S[:,1,0];assert np.all(determinant>0)
    inverse=np.empty_like(S)
    inverse[:,0,0]=S[:,1,1]/determinant;inverse[:,1,1]=S[:,0,0]/determinant
    inverse[:,0,1]=-S[:,0,1]/determinant;inverse[:,1,0]=-S[:,1,0]/determinant
    K=ph@inverse;K[~mask]=0.
    A=np.eye(4)-K@H
    post=A@P@A.swapaxes(-1,-2)+K@R@K.swapaxes(-1,-2);post=(post+post.swapaxes(-1,-2))/2;post[~mask]=P[~mask]
    z=np.array([full['z'],np.column_stack((los['z'][:,0],full['z'][:,1])),np.column_stack((full['z'][:,0],los['z'][:,1])),los['z']]).transpose(1,0,2)
    U=X[:,None,:]+np.matmul(K[:,None,:,:],(z-h[:,None,:]-mu[:,None,:])[...,None])[...,0]
    x=U.copy();x[:,:,2]=circular(U[:,:,2]);x[:,:,2][x[:,:,2]>=np.pi]-=2*np.pi;x[~mask]=X[~mask,None,:]
    compare('independent_K',saved['K'],K);compare('independent_Joseph',saved['P'],post)
    compare('independent_u',saved['u'],U);compare('independent_x_nonangular',saved['x'][:,:,[0,1,3]],x[:,:,[0,1,3]])
    compare('independent_x_heading',saved['x'][:,:,2],x[:,:,2],True)
    assert np.all(saved['x'][mask,:,2]>=-np.pi) and np.all(saved['x'][mask,:,2]<np.pi)
    for j in range(4):assert np.array_equal(saved['x'][~mask,j],X[~mask])
    compare('baseline_xy_bias',saved['x'][:,0,[0,1,3]],tr['x'][:,[0,1,3]]);record('baseline_xy_bias',saved['x'][:,0,[0,1,3]],tr['x'][:,[0,1,3]])
    compare('baseline_heading',saved['x'][:,0,2],tr['x'][:,2],True);record('baseline_heading',saved['x'][:,0,2],tr['x'][:,2],True)
    compare('baseline_P',saved['P'],tr['P']);record('baseline_P',saved['P'],tr['P'])
    compare('baseline_K',saved['K'],tr['K']);record('baseline_K',saved['K'],tr['K'])
    dz=los['z']-full['z']
    for label,a,b in [('range_identity',saved['u'][:,1]-saved['u'][:,0],saved['K'][:,:,0]*dz[:,0,None]),('s_identity',saved['u'][:,2]-saved['u'][:,0],saved['K'][:,:,1]*dz[:,1,None]),('interaction_identity',saved['u'][:,3]-saved['u'][:,1]-saved['u'][:,2]+saved['u'][:,0],np.zeros_like(X))]:
     compare(label,a,b);record(label,a,b)
    covariance('prior',P);covariance('posterior',saved['P'])
    # Evaluator uses only already calculated posterior arrays and immutable GT.
    xy=np.sqrt(np.sum((x[:,:,:2]-truth['truth'][:,None,:2])**2,axis=2))
    heading=np.abs(circular(x[:,:,2]-truth['truth'][:,None,2]))*180/np.pi
    primary=tr['t']>=30.
    for j,arm in enumerate(arms):
     data=[]
     for k in range(n):
      row=next(reader)
      assert (row['route'],row['bias'],int(row['seed']),int(row['pose_id']),float(row['t_s']),row['arm'])==(route,bias,seed,int(tr['pose_id'][k]),float(tr['t'][k]),arm)
      data.append([float(row[key]) for key in ('xy_m','heading_deg','delta_xy_m','delta_heading_deg')])
     data=np.array(data);ref=np.column_stack((xy[:,j],heading[:,j],xy[:,j]-xy[:,0],heading[:,j]-heading[:,0]))
     compare('all_CSV_scores',data,ref)
     sr=summary[summary_index];summary_index+=1
     assert (sr['route'],sr['bias'],sr['seed'],sr['arm'],sr['n'])==(route,bias,seed,arm,int(primary.sum()))
     expected=dict(mean_xy_m=float(xy[primary,j].mean()),median_xy_m=float(np.median(xy[primary,j])),mean_heading_deg=float(heading[primary,j].mean()),median_heading_deg=float(np.median(heading[primary,j])),mean_delta_xy_m=float((xy[primary,j]-xy[primary,0]).mean()),mean_delta_heading_deg=float((heading[primary,j]-heading[primary,0]).mean()))
     assert set(sr)=={'route','bias','seed','arm','n',*expected}
     for key,val in expected.items():compare('primary_summary',np.array([sr[key]]),np.array([val]))
    counts['cells']+=1;counts['priors']+=n;counts['posterior_rows']+=4*n
    if counts['cells']%20==0:print('C1A_INDEPENDENT_PROGRESS '+str(counts['cells']),flush=True)
 assert next(reader,None) is None
assert {p.name for p in (O/'cells').iterdir()}==expected_cell_names
counts['summary_rows']=summary_index
assert counts==dict(cells=120,priors=125440,posterior_rows=501760,summary_rows=480)
assert (manifest['completed_cells'],manifest['priors'],manifest['posterior_rows'],manifest['verified_input_files'])==(120,125440,501760,145)
checks=load(O/'CHECKS.json');assert set(checks)==set(check_record)
for k,v in check_record.items():compare('saved_checks',np.array([checks[k]]),np.array([v]))
answer=dict(decision='ACCEPT',scope='C1A_FROZEN_FULL_PRIOR_ONE_STEP_SUBSTITUTION_ONLY',question_id='C1A-SAME-PRIOR-001',counts=counts,
 verified_artifacts=len(artifact),input_files_verified=145,frozen_packet_truth_exports_verified=18,bindings_sha256=go['bindings_sha256'],
 go_sha256=sha(Q/'GO.json'),manifest_sha256=sha(O/'MANIFEST.json'),artifact_hashes_sha256=sha(O/'ARTIFACT_HASHES.json'),
 pose_effects_sha256=sha(O/'POSE_EFFECTS.csv'),cell_summary_sha256=sha(O/'CELL_SUMMARY.json'),checks_sha256=sha(O/'CHECKS.json'),
 run_result_sha256=sha(Q/'RUN_RESULT.json'),max_absolute_differences=maxima,minimum_covariance_eigenvalue=min_eigen,maximum_covariance_symmetry_error=max_sym,
 baseline_mask_and_pose_time_exact=True,all_four_arms_same_K_and_P=True,hybrid_Full_mean_R_preserved=True,production_core_calls=0,production_evaluator_calls=0,
 new_recursive_baseline_runs=0,new_RT_calls=0,new_FFT_calls=0,files_changed_by_auditor=0,C1b_C2_GO=False,
 claim_boundary='Conditional one-step substitution on already published same-RF Full priors; numerical pass is not algorithm improvement/adoption, recursive causality, recovery benefit or independent environment validation',
 timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
print('C1A_RESULT_AUDIT_RESULT '+json.dumps(answer),flush=True)
