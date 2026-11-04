"""Independent C2 REMAINING numerical verifier. No production C2 modules or online/core math calls.
Original locked SourceFFD is the only observation provider, reevaluated only at
predetermined samples. All transition/update edges and evaluator metrics are
independently checked; preceding branch posteriors and accepted DEV refs are reused.
Read-only; run only after terminal successful REMAINING. No new scientific policy run.
"""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import csv,hashlib,importlib.metadata,importlib.util,json,math,platform,subprocess,sys
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_info
ROOT=Path('D:/codex/MBVAR_PRR_001_20261103')
HERE=ROOT/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C2/C2_001'
OUT=HERE/'REMAINING_001'
CACHE=Path('D:/codex/MBVAR_PRR_001_20261103_inputs/C1B_001')
INPUTS=CACHE.parent/'C1A_001'
C1B=HERE.parents[1]/'C1/C1B_001'
MODES=('fixed','fixed','fixed','own','own','own')
ARMS=('LF','FL','LL','LF','FL','LL')
BOUND=('authority.py','engine.py','evaluate.py','run.py','launch.py','test_engine.py','PLAN.json','WINDOWS.json','INPUT_LOCK.json','CONTRACT_KO.md','GOVERNANCE.json','../../C1/C1B_001/legacy.py')
MAX={}
COUNT=dict(source_cells=0,window_cells=0,trajectories=0,posterior_rows=0,
 source_observer_states=0,source_observer_calls=0,MB_rows=0,BASE_rows=0,
 source_MB_population=0,source_BASE_population=0,source_MB_sampled=0,source_BASE_sampled=0,
 summary_rows=0,block_rows=0,acf_rows=0,accepted_GT_refs_reused=0)
SAMPLE_LEDGER=hashlib.sha256()
MIN_EIG=float('inf')
MAX_SYM=0.
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def js(p):return json.loads(p.read_bytes())
def read(p):
 with np.load(p,allow_pickle=False) as d:return dict(d)
def exact(name,a,b):assert np.array_equal(a,b),(name,'exact mismatch')
def chk(name,a,b,angular=False):
 a,b=np.asarray(a),np.asarray(b);assert a.shape==b.shape,(name,a.shape,b.shape)
 assert np.isfinite(a).all() and np.isfinite(b).all(),(name,'nonfinite')
 delta=a-b
 if angular:delta=np.arctan2(np.sin(delta),np.cos(delta))
 peak=float(np.max(np.abs(delta))) if a.size else 0.
 MAX[name]=max(MAX.get(name,0.),peak)
 assert np.all(np.abs(delta)<=1e-10+1e-10*np.abs(b)),(name,peak)
def tree(name,a,b):
 if isinstance(b,dict):
  assert set(a)==set(b),(name,set(a)^set(b))
  for k in b:tree(name+'/'+k,a[k],b[k])
 elif isinstance(b,(list,tuple)):
  assert len(a)==len(b),name
  for i,v in enumerate(b):tree(name+'/'+str(i),a[i],v)
 elif b is None or isinstance(b,(str,bool)):
  assert a==b,(name,a,b)
 else:chk('structured_scalars',a,b)
def csvrow(actual,expected):
 assert set(actual)==set(expected),(set(actual)^set(expected))
 for k,b in expected.items():
  a=actual[k]
  if b is None:assert a=='',(k,a)
  elif isinstance(b,(str,bool)):assert a==str(b),(k,a,b)
  else:chk('CSV_numeric',float(a),b)
def sym(P):return (P+P.T)*.5
def wrap(v):return (v+np.pi)%(2*np.pi)-np.pi
def covariance(mats):
 global MIN_EIG,MAX_SYM
 P=np.asarray(mats);assert np.isfinite(P).all()
 delta=np.max(np.abs(P-P.swapaxes(-1,-2)),axis=(-1,-2))
 eigen=np.linalg.eigvalsh((P+P.swapaxes(-1,-2))*.5)
 scale=np.maximum(1.,np.max(np.abs(eigen),axis=-1))
 assert np.all(delta<=1e-12*scale) and np.all(eigen[...,0]>=-1e-12*scale)
 MIN_EIG=min(MIN_EIG,float(eigen.min()));MAX_SYM=max(MAX_SYM,float(delta.max()))
def prediction_batch(previous,C,global_ids,ctl):
 T,J=previous.shape[:2]
 ds,gy,dt=(np.asarray(ctl[key])[global_ids] for key in ('ds','gy','dt'))
 assert np.isfinite([ds,gy,dt]).all() and np.all(dt[global_ids>0]>0)
 angle=gy[:,None]-previous[:,:,3]*dt[:,None]
 small=np.abs(angle)<1e-4;c=np.empty_like(angle);dc=np.empty_like(angle)
 z=angle[small];z2=z*z
 c[small]=1-z2/24+z2*z2/1920-z2**3/322560
 dc[small]=-z/12+z**3/480-z**5/53760
 half=angle[~small]/2
 c[~small]=np.sin(half)/half
 dc[~small]=(half*np.cos(half)-np.sin(half))/(2*half*half)
 phi=previous[:,:,2]+angle/2
 direction=np.stack((np.cos(phi),np.sin(phi)),axis=-1)
 perpendicular=np.stack((-direction[:,:,1],direction[:,:,0]),axis=-1)
 displacement=ds[:,None,None]*c[:,:,None]*direction
 derivative=ds[:,None,None]*(dc[:,:,None]*direction+c[:,:,None]*perpendicular/2)
 x=previous.copy();x[:,:,:2]+=displacement;x[:,:,2]=wrap(previous[:,:,2]+angle)
 F=np.broadcast_to(np.eye(4),(T,J,4,4)).copy()
 F[:,:,:2,2]=np.stack((-displacement[:,:,1],displacement[:,:,0]),axis=-1)
 F[:,:,:2,3]=-dt[:,None,None]*derivative;F[:,:,2,3]=-dt[:,None]
 G=np.zeros((T,J,4,3));G[:,:,:2,0]=c[:,:,None]*direction
 G[:,:,:2,1]=derivative;G[:,:,2,1]=1.;G[:,:,3,2]=1.
 Q=np.zeros((T,3,3));Q[:,0,0]=2e-5*np.abs(ds);Q[:,1,1]=math.radians(.015)**2*dt
 atzero=global_ids==0
 x[atzero]=previous[atzero];F[atzero]=np.eye(4);G[atzero]=0.;Q[atzero]=0.
 transpose=lambda v:np.swapaxes(v,-1,-2)
 Qs=G@Q[:,None]@transpose(G)
 C=(C+transpose(C))*.5
 prior=F@C@transpose(F)+Qs;prior=(prior+transpose(prior))*.5
 return x,prior,F,G,Q,Qs
def update_batch(prior,C,h,H,z,mu,R,permitted=None):
 trans=lambda v:np.swapaxes(v,-1,-2)
 nu=z-h-mu;S=H@C@trans(H)+R
 if permitted is not None:S=(S+trans(S))*.5
 nis=np.sum(nu*np.linalg.solve(S,nu[...,None])[...,0],axis=-1)
 mask=nis<=9.210340371976184 if permitted is None else np.asarray(permitted)
 gain=trans(np.linalg.solve(S,H@C));K=np.where(mask[...,None,None],gain,0.)
 u=prior+(K@nu[...,None])[...,0];x=u.copy();x[:,:,2]=np.where(mask,wrap(x[:,:,2]),x[:,:,2])
 M=np.eye(4)-K@H;P=M@C@trans(M)+K@R@trans(K);P=(P+trans(P))*.5
 return dict(x=x,P=P,K=K,S=S,nu=nu,nis=nis,mask=mask,u=u)
def selected_indices(global_ids,mask,taps,cells,start,end):
 selected=(global_ids%25)==0
 selected[:3]=True;selected[-3:]=True
 for boundary in (start,end):
  selected|=np.abs(global_ids-boundary)<=1
 changed=np.flatnonzero((mask[1:]!=mask[:-1])|(taps[1:]!=taps[:-1])|np.any(cells[1:]!=cells[:-1],axis=1))+1
 for offset in (-1,0,1):
  points=changed+offset;points=points[(points>=0)&(points<len(selected))];selected[points]=True
 return np.flatnonzero(selected)
def verify_observer(data,key,cell,window,ids,start,end):
 prefix='BASE_' if key=='BASE' else ''
 T,J=data[prefix+'prior'].shape[:2]
 COUNT['source_'+key+'_population']+=T*J
 for j in range(J):
  selected=selected_indices(ids,data[prefix+'mask'][:,j],data[prefix+'tap'][:,j],data[prefix+'cells'][:,j],start,end)
  h,H,diag=observations(data[prefix+'prior'][selected,j])
  chk(key+'_source_h',data[prefix+'h'][selected,j],h);chk(key+'_source_H',data[prefix+'H'][selected,j],H)
  for field in ('tap','cells'):exact(key+'_source_'+field,data[prefix+field][selected,j],diag[field])
  chk(key+'_source_fp_margin',data[prefix+'fp_margin'][selected,j],diag['fp_margin'])
  COUNT['source_'+key+'_sampled']+=len(selected)
  SAMPLE_LEDGER.update((cell+'|'+window+'|'+key+'|'+str(j)+'|').encode())
  SAMPLE_LEDGER.update(np.asarray(ids[selected],dtype='<i8').tobytes())
def observations(states):
 parts=[];jacs=[];diags=[]
 for k in range(0,len(states),32):
  h,H,d=observer.batch(np.asarray(states[k:k+32]),CASE,return_diagnostics=True)
  assert np.isfinite(h).all() and np.isfinite(H).all()
  parts.append(h);jacs.append(H);diags.append(d)
  COUNT['source_observer_states']+=len(h);COUNT['source_observer_calls']+=1
 return np.concatenate(parts),np.concatenate(jacs),{key:np.concatenate([d[key] for d in diags]) for key in diags[0]}
def score(x,P,truth):
 covariance(P)
 np.linalg.cholesky(P);np.linalg.cholesky(P[...,:3,:3]);np.linalg.cholesky(P[...,:2,:2])
 error=x[...,:3]-truth['truth'][:,None,:];error[...,2]=np.arctan2(np.sin(error[...,2]),np.cos(error[...,2]))
 xy=np.sqrt(np.sum(error[...,:2]**2,axis=-1));yaw=np.abs(error[...,2])
 n3=np.einsum('...i,...i->...',error,np.linalg.solve(P[...,:3,:3],error[...,None])[...,0])
 m2=np.einsum('...i,...i->...',error[...,:2],np.linalg.solve(P[...,:2,:2],error[...,:2,None])[...,0])
 bg=truth.get('bg');available=bg is not None and np.asarray(bg).shape==() and np.isfinite(bg)
 if available:
  eb=x[...,3]-float(bg);e4=np.concatenate((error,eb[...,None]),axis=-1)
  n4=np.einsum('...i,...i->...',e4,np.linalg.solve(P,e4[...,None])[...,0]);bgerr=np.abs(eb)
 else:n4=np.full(xy.shape,np.nan);bgerr=n4.copy()
 return dict(xy_m=xy,heading_deg=np.degrees(yaw),bg_abs_rad_s=bgerr,NEES3=n3,NEES4=n4,
 NEES4_available=np.array(bool(available)),XY_mahalanobis2=m2,heading68=yaw<=np.sqrt(P[...,2,2]),
 heading95=yaw<=1.959963984540054*np.sqrt(P[...,2,2]),XY95=m2<=5.991464547107979,
 NEES3_upper95=n3<=7.814727903251179,NEES4_upper95=n4<=9.487729036781154,
 Ppsi_rad2=P[...,2,2],Pxy_trace_m2=P[...,0,0]+P[...,1,1],Pbg_rad2_s2=P[...,3,3])
def score_compare(saved,wanted,label):
 assert set(saved)==set(wanted),(label,set(saved)^set(wanted))
 for k,b in wanted.items():
  a=saved[k]
  if np.asarray(b).dtype.kind=='b':exact(label+k,a,b)
  elif np.isnan(b).any():
   exact(label+k+'_NA',np.isnan(a),np.isnan(b));mask=np.isfinite(b);chk(label+k,a[mask],b[mask])
  else:chk(label+k,a,b)
def primary(metrics,select,available):
 result={}
 for k in ('xy_m','heading_deg'):
  v=metrics[k][select];result[k+'_mean']=float(np.mean(v));result[k+'_rmse']=float(np.sqrt(np.mean(v*v)))
 for k in ('NEES3','NEES4','heading68','heading95','XY95','NEES3_upper95','NEES4_upper95','Ppsi_rad2','Pxy_trace_m2','Pbg_rad2_s2','bg_abs_rad_s'):
  result[k+'_mean']=None if not available and k in ('NEES4','NEES4_upper95','bg_abs_rad_s') else float(np.mean(metrics[k][select]))
 return result
def corr(v):
 ans=[]
 for lag in range(1,11):
  a,b=v[:-lag],v[lag:]
  ans.append(None if len(a)<2 or np.ptp(a)==0 or np.ptp(b)==0 else float(np.corrcoef(a,b)[0,1]))
 return ans
def integ(times,values,start,left,right):
 m=(times>=start+left-1e-9)&(times<=start+right+1e-9);tt=times[m]
 if len(tt)<2 or abs(tt[0]-start-left)>1e-9 or abs(tt[-1]-start-right)>1e-9:return None,int(m.sum())
 return float(np.sum(np.diff(tt)*(values[m][1:]+values[m][:-1])/2)),int(m.sum())
assert sys.dont_write_bytecode
manifest=js(OUT/'MANIFEST.json');execution=js(HERE/'RUN_RESULT_REMAINING.json')
assert manifest['status']==execution['status']=='NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT'
assert execution['exit_code']==0 and execution['result_status']==manifest['status']
plan=js(HERE/'PLAN.json');go=js(HERE/'GO_REMAINING.json');phase=plan['phases']['remaining']
authorization=dict(stage='C2_only',phase='remaining',routes=plan['routes'],biases=plan['biases'],seeds=list(range(11,30)),output='REMAINING_001',window_cells=418,trajectories=2508,posterior_rows=1451904)
assert go['schema']=='C2_GO_V1' and go['decision']=='GO' and go['authorized']==authorization
assert set(go['bindings_sha256'])==set(BOUND) and manifest['bindings_sha256']==go['bindings_sha256']
revision=execution['code_revision']
assert manifest['code_revision']==execution['code_revision']==revision
assert manifest['go_sha256']==execution['go_sha256']==sha(HERE/'GO_REMAINING.json')
for name,digest in go['bindings_sha256'].items():
 assert sha(HERE/name)==digest,name
 gp=(HERE/name).resolve().relative_to(ROOT).as_posix()
 assert hashlib.sha256(subprocess.check_output(['git','-C',str(ROOT),'show',revision+':'+gp])).hexdigest()==digest
gp=(HERE/'GO_REMAINING.json').relative_to(ROOT).as_posix()
assert subprocess.check_output(['git','-C',str(ROOT),'show',revision+':'+gp])==(HERE/'GO_REMAINING.json').read_bytes()
assert execution['start_utc']<=manifest['start_utc']<manifest['end_utc']<=execution['end_utc']
env=js(CACHE/'provenance/ENV_LOCK.json')
assert sys.version==env['python'] and platform.platform()==env['os']
assert sha(Path(sys.executable))==plan['python_executable_sha256']
assert {k:importlib.metadata.version(k) for k in env['packages']}==env['packages']
assert all(os.environ.get(k)=='1' for k in env['threads'])
assert threadpool_info() and all(p['num_threads']==1 for p in threadpool_info())
assert manifest['runtime']['python']==sys.version and manifest['runtime']['packages']==env['packages']
assert all(p['num_threads']==1 for p in manifest['runtime']['threadpools'])
for path,digest in manifest['runtime']['loaded_BLAS_sha256'].items():assert sha(Path(path))==digest
lock=js(HERE/'INPUT_LOCK.json')
for name,entry in lock['accepted_prerequisites'].items():assert Path(name).stat().st_size==entry['size'] and sha(Path(name))==entry['sha256']
for parent,cache,key in [(HERE.parents[1]/'C1/C1A_001',INPUTS,'payload_sha256'),(C1B,CACHE,'sha256')]:
 for name,entry in js(parent/'INPUT_LOCK.json')['sources'].items():assert (cache/name).stat().st_size==entry['size'] and sha(cache/name)==entry[key]
b_lock=js(C1B/'INPUT_LOCK.json')
for entry in b_lock['banks'].values():assert Path(entry['path']).stat().st_size==entry['size'] and sha(Path(entry['path']))==entry['sha256']
assert sha(Path(lock['C0A_csv']['path']))==lock['C0A_csv']['sha256']
index=js(OUT/'ARTIFACT_HASHES.json');assert {p.relative_to(OUT).as_posix() for p in OUT.rglob('*') if p.is_file()}==set(index)|{'ARTIFACT_HASHES.json'}
for name,digest in index.items():assert sha(OUT/name)==digest,name
assert (OUT/'FAILURES.jsonl').read_bytes()==b''
for k in ('new_MBVAR_baseline_experiments','new_training_runs','new_RT_calls'):assert manifest[k]==0,k
assert manifest['model_initializations']==manifest['model_initialization_attempts']==1
assert manifest['FF_source_verification_replays']==0
for key,expected in [('source_cells_completed',114),('window_cells_completed',418),('trajectories',2508),('posterior_rows',1451904)]:assert manifest[key]==expected
devreceipt=HERE/'audit/C2_DEV_RESULT_AUDIT_RESULT.json'
assert sha(devreceipt)==go['prerequisite_sha256']=='ea4af6f8aa2cd79928bf4a94aaea7d72a24d6c1d17dc2a84ee7d6c41978c0f6c'
dev=js(devreceipt);assert dev['decision']=='ACCEPT' and dev['counts']['window_cells']==22
gp=devreceipt.relative_to(ROOT).as_posix()
assert subprocess.check_output(['git','-C',str(ROOT),'show',revision+':'+gp])==devreceipt.read_bytes()
devindex=HERE/'DEV_001/ARTIFACT_HASHES.json'
assert sha(devindex)==dev['artifact_hashes_sha256']
accepted_refs=js(devindex)
legacy=CACHE/'legacy'
sys.path[:0]=[str(legacy/'research/FFD_P0P3_20261016'),str(legacy/'research/EKF4_RANGE_S_STAGED_20261014'),str(legacy/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
loader=importlib.util.spec_from_file_location('c2_independent_original_source',legacy/'research/FFD_P0P3_20261016/source_model.py')
original=importlib.util.module_from_spec(loader);loader.loader.exec_module(original)
observer=original.SourceFFD(banks=[original.P.Bank(read(Path(b_lock['banks'][name]['path']))) for name in ('LP_plus45_bank.npz','LP_minus45_bank.npz')])
CASE=dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.)
RF={}
for row in csv.DictReader(Path(lock['C0A_csv']['path']).open(encoding='utf8')):
 key=(row['route'],int(row['pose_id']));assert key not in RF;RF[key]=row
windows=js(HERE/'WINDOWS.json')['windows']
saved_summaries=js(OUT/'TRAJECTORY_SUMMARY.json');csv_summaries=iter(csv.DictReader((OUT/'TRAJECTORY_SUMMARY.csv').open(encoding='utf8',newline='')))
saved_acf=js(OUT/'AUTOCORRELATION.json');blocks=iter(csv.DictReader((OUT/'DIAGNOSTIC_BLOCKS.csv').open(encoding='utf8',newline='')))
parent_audit=js(C1B/'audit/C1B_RESULT_AUDIT_RESULT.json');assert parent_audit['decision']=='ACCEPT'
parent_indexes={}
for parent_phase in ('DEV_001','REMAINING_001'):
 pindex=C1B/parent_phase/'ARTIFACT_HASHES.json'
 assert sha(pindex)==parent_audit['phase_artifact_and_report_sha256'][parent_phase+'/ARTIFACT_HASHES.json']
 parent_indexes[parent_phase]=js(pindex)
for route in plan['routes']:
 for bias in plan['biases']:
  full=read(INPUTS/f'{route}_aB_m0_{bias}_Full.npz');los=read(INPUTS/f'{route}_aB_m0_{bias}_Native_LoS.npz')
  truth=read(INPUTS/f'{route}_{bias}_TRUTH.npz');n=plan['route_rows'][route]
  refpath=HERE/'DEV_001/evaluation_refs'/f'{route}_{bias}.npz'
  assert sha(refpath)==accepted_refs['evaluation_refs/'+route+'_'+bias+'.npz']
  reference=read(refpath);assert str(reference['truth_sha256'])==sha(INPUTS/f'{route}_{bias}_TRUTH.npz')
  hg=reference['h'];COUNT['accepted_GT_refs_reused']+=1
  for d in (los,truth,reference):
   for key in ('t','pose_id'):exact('fixed_join_'+key,d[key],full[key])
  rfrows=[RF[(route,int(pid))] for pid in full['pose_id']]
  chk('C0A_time_join',np.array([float(r['t_s']) for r in rfrows]),full['t'])
  physical=np.array([[float(r['delta_range_m']),float(r['physical_e_mp'])] for r in rfrows]);taps=np.array([int(r['delta_tap']) for r in rfrows])
  chk('physical_delta',reference['physical_delta'],physical);exact('physical_taps',reference['physical_delta_tap'],taps)
  distance=np.r_[0.,np.cumsum(np.sqrt(np.sum(np.diff(truth['truth'][:,:2],axis=0)**2,axis=1)))]
  chk('GT_distance',reference['distance_m'],distance)
  timebin=np.floor((full['t']+1e-9)/1.).astype(np.int64);distbin=np.floor((distance+1e-12)/.2).astype(np.int64)
  exact('time_bin',reference['time_bin'],timebin);exact('distance_bin',reference['distance_bin'],distbin)
  for seed in range(11,30):
   cell=f'{route}_{bias}_{seed}';trace=read(INPUTS/(cell+'_TRACE.npz'));ctl=read(CACHE/'controls'/f'{route}_aB_m0_{bias}_{seed}.npz')
   pp=C1B/'REMAINING_001/cells'/(cell+'.npz')
   assert sha(pp)==parent_indexes['REMAINING_001']['cells/'+cell+'.npz'];base=read(pp)
   for d in (trace,base):
    for key in ('t','pose_id'):exact(cell+key,d[key],full[key])
   assert len(full['t'])==n and len(set(full['pose_id'].tolist()))==n
   chk('5Hz',np.diff(full['t']),np.full(n-1,.2))
   baseline={k:(v[:,0] if v.ndim==2 else v) for k,v in score(trace['x'][:,None],trace['P'][:,None],truth).items()}
   bs=read(OUT/'baselines'/(cell+'.npz'));exact('baseline_t',bs.pop('t'),full['t']);exact('baseline_pose',bs.pop('pose_id'),full['pose_id'])
   score_compare(bs,baseline,'baseline_')
   cell_source_before=COUNT['source_observer_states']
   for w in [w for w in windows if w['route']==route]:
    start,end=w['first_index'],w['last_index'];stem=cell+'_'+w['id'];data=read(OUT/'filter'/(stem+'.npz'))
    exact('branch_modes',data['modes'],MODES);exact('branch_arms',data['arms'],ARMS);exact('BASE_indices',data['BASE_branch_indices'],[3,4,5])
    for key in ('t','pose_id'):exact('suffix_'+key,data[key],full[key][start:])
    exact('first_index',data['first_index'],start);exact('last_intervention_index',data['last_intervention_index'],end)
    exact('filled_rows',data['filled_rows'],n-start)
    for key,fkey in [('mu','muMB'),('BASE_mu','muBASE'),('BASE_R','R')]:exact('frozen_'+key,data[key],full[fkey][start:])
    assert n-start==w['suffix_rows'] and end-start+1==w['intervention_packets']
    ids=np.arange(start,n)
    for label,J in [('MB',6),('BASE',3)]:
     pre='' if label=='MB' else 'BASE_'
     oldx=trace['x'] if label=='MB' else base['BASE_x'];oldP=trace['P'] if label=='MB' else base['BASE_P']
     initial_x=oldx[start-1] if start else np.r_[ctl['x0'],0.]
     initial_P=oldP[start-1] if start else full['P0']
     previous=np.concatenate((np.repeat(initial_x[None,None],J,axis=1),data[pre+'x'][:-1]),axis=0)
     previousP=np.concatenate((np.repeat(initial_P[None,None],J,axis=1),data[pre+'P'][:-1]),axis=0)
     xp,C,F,G,Q,Qs=prediction_batch(previous,previousP,ids,ctl)
     for field,expected in [('prior',xp),('Pprior',C),('F',F),('G',G),('Qstate',Qs)]:chk(pre+field,data[pre+field],expected)
     chk('Qinput',data['Qinput'],Q)
     z=np.repeat(full['z'][start:,None],J,axis=1);inside=ids<=end
     arms=ARMS if label=='MB' else ARMS[3:]
     for j,arm in enumerate(arms):
      if arm in ('LF','LL'):z[inside,j,0]=los['z'][ids[inside],0]
      if arm in ('FL','LL'):z[inside,j,1]=los['z'][ids[inside],1]
     R=np.repeat(full['R'][start:,None],J,axis=1)
     if label=='MB':
      rho=np.hypot(previous[:,:,0]-10.,previous[:,:,1]);sigma=np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240])
      R[:,:,1,1]+=sigma*sigma
      for field,expected in [('rho',rho),('sigma_b',sigma),('R',R),('z',z)]:chk(field,data[field],expected)
      allowed=np.column_stack((np.repeat(trace['mask'][start:,None],3,axis=1),data['BASE_mask']))
      mu=full['muMB'][start:,None]
     else:allowed=None;mu=full['muBASE'][start:,None]
     rec=update_batch(xp,C,data[pre+'h'],data[pre+'H'],z,mu,R,allowed)
     for field in ('x','P','S','nis'):chk(pre+field,data[pre+field],rec[field])
     exact(pre+'mask',data[pre+'mask'],rec['mask'])
     if label=='MB':
      for field in ('K','nu','u'):chk(field,data[field],rec[field])
     COUNT[label+'_rows']+=(n-start)*J
     verify_observer(data,label,cell,w['id'],ids,start,end)
    for key in ('P','Pprior','BASE_P','BASE_Pprior'):covariance(data[key])
    suffix_truth=dict(truth=truth['truth'][start:],**({'bg':truth['bg']} if 'bg' in truth else {}))
    values=score(data['x'],data['P'],suffix_truth)
    epsilon=data['z']-hg[start:,None,:]-full['muMB'][start:,None,:]
    delta=hg[start:,None,:]-data['h'];identity=epsilon+delta-data['nu']
    chk('innovation_identity',identity,np.zeros_like(identity))
    values.update(epsilon=epsilon,delta_h=delta,identity_error=identity,pose_id=data['pose_id'],t=data['t'],modes=data['modes'],arms=data['arms'])
    saved=read(OUT/'metrics'/(stem+'.npz'))
    for name in ('pose_id','t','modes','arms'):exact('metric_'+name,saved.pop(name),values.pop(name))
    score_compare(saved,values,'metric_')
    active=np.arange(start,n)<=end;available=bool(values['NEES4_available']);primary_mask=full['t']>=30.
    ffprimary=primary(baseline,primary_mask,available);rows=[]
    for j,(mode,arm) in enumerate(zip(MODES,ARMS)):
     row=dict(route=route,bias=bias,seed=seed,window=w['id'],mode=mode,arm=arm,start_s=w['start_s'],end_s=w['end_s'],
      first_index=start,suffix_rows=n-start,primary_rows=int(primary_mask.sum()),NEES4_available=available,
      NEES4_unavailable_reason='' if available else 'source scalar gyro-bias truth unavailable',epsilon_identity_max=float(np.abs(identity[:,j]).max()))
     combined={key:np.r_[baseline[key][:start],v[:,j]] for key,v in values.items() if v.ndim==2 and key in baseline}
     current=primary(combined,primary_mask,available)
     for key,value in current.items():row['primary_'+key]=value;row['FF_primary_'+key]=ffprimary[key];row['delta_primary_'+key]=None if value is None else value-ffprimary[key]
     for left,right in ((0.,2.),(2.,5.),(5.,10.),(10.,20.)):
      for name,unit in [('heading_deg','deg_s'),('xy_m','m_s')]:
       v,packets=integ(data['t'],values[name][:,j],w['start_s'],left,right);f,_=integ(full['t'],baseline[name],w['start_s'],left,right)
       key=f'I_{name}_{left:g}_{right:g}_{unit}'
       row[key]=v;row['FF_'+key]=f;row['delta_'+key]=None if v is None or f is None else v-f
       row[key+'_available']=v is not None and f is not None;row[key+'_actual_packets']=packets
       row[key+'_unavailable_reason']='' if v is not None and f is not None else 'complete interval endpoints unavailable; no partial integral'
     for predicate,pkey,tkey in [(data['mask'][:,j]&(np.abs(physical[start:,1])>.20)&(arm=='LF'),'first_delivered_Full_s_bad_pose','first_delivered_Full_s_bad_t'),
      (data['mask'][:,j]&(taps[start:]!=0),'first_original_RF_tap_change_accepted_pose','first_original_RF_tap_change_accepted_t')]:
      inds=np.flatnonzero(active&predicate);row[pkey]=int(data['pose_id'][inds[0]]) if len(inds) else None;row[tkey]=float(data['t'][inds[0]]) if len(inds) else None
     row['gate_flips_all']=int(np.count_nonzero(data['mask'][:,j]!=trace['mask'][start:]));rows.append(row)
     ac=dict(route=route,bias=bias,seed=seed,window=w['id'],mode=mode,arm=arm,epsilon_range_acf=corr(epsilon[active,j,0]),epsilon_s_acf=corr(epsilon[active,j,1]),
      physical_range_acf=corr(physical[start:][active,0]),physical_s_acf=corr(physical[start:][active,1]))
     tree('ACF',saved_acf[COUNT['acf_rows']],ac);COUNT['acf_rows']+=1
     for kind,labels in [('time_1s',timebin[start:]),('distance_0p2m',distbin[start:])]:
      for label in np.unique(labels[active]):
       mask=active&(labels==label)
       block=dict(route=route,bias=bias,seed=seed,window=w['id'],mode=mode,arm=arm,block_kind=kind,block_id=int(label),n=int(mask.sum()),
        mean_original_eMP_range_m=float(physical[start:,0][mask].mean()),mean_original_eMP_s=float(physical[start:,1][mask].mean()),
        mean_delivered_eMP_range_m=0. if arm in ('LF','LL') else float(physical[start:,0][mask].mean()),
        mean_delivered_eMP_s=0. if arm in ('FL','LL') else float(physical[start:,1][mask].mean()),
        mean_epsilon_range_m=float(epsilon[mask,j,0].mean()),mean_epsilon_s=float(epsilon[mask,j,1].mean()),
        mean_heading_deg=float(values['heading_deg'][mask,j].mean()),mean_xy_m=float(values['xy_m'][mask,j].mean()),
        mean_delta_heading_vs_FF=float((values['heading_deg'][:,j]-baseline['heading_deg'][start:])[mask].mean()),
        mean_delta_xy_vs_FF=float((values['xy_m'][:,j]-baseline['xy_m'][start:])[mask].mean()),
        mean_Ppsi_rad2=float(data['P'][mask,j,2,2].mean()),accepted_fraction=float(data['mask'][mask,j].mean()))
       csvrow(next(blocks),block);COUNT['block_rows']+=1
    paired=[key for key in rows[0] if (key.startswith('primary_') and key!='primary_rows') or (key.startswith('I_') and key.endswith(('deg_s','m_s')))]
    for j,row in enumerate(rows):
     for key in paired:row['own_minus_fixed_'+key]=None if j<3 or row[key] is None or rows[j-3][key] is None else row[key]-rows[j-3][key]
     tree('summary',saved_summaries[COUNT['summary_rows']],row);csvrow(next(csv_summaries),row);COUNT['summary_rows']+=1
    COUNT['window_cells']+=1;COUNT['trajectories']+=6;COUNT['posterior_rows']+=(n-start)*6
    print('C2_REMAINING_WINDOW_VERIFIED',cell,w['id'],COUNT['window_cells'],COUNT['source_observer_states'],flush=True)
   COUNT['source_cells']+=1
   print('C2_REMAINING_CELL_VERIFIED',cell,COUNT['source_cells'],COUNT['window_cells'],COUNT['source_observer_states']-cell_source_before,COUNT['source_observer_states'],flush=True)
assert next(blocks,None) is None and next(csv_summaries,None) is None
assert COUNT['summary_rows']==COUNT['acf_rows']==len(saved_summaries)==len(saved_acf)==2508
assert COUNT['source_cells']==114 and COUNT['window_cells']==418 and COUNT['trajectories']==2508 and COUNT['posterior_rows']==1451904
assert COUNT['MB_rows']==COUNT['source_MB_population']==1451904
assert COUNT['BASE_rows']==COUNT['source_BASE_population']==725952
assert COUNT['accepted_GT_refs_reused']==6
assert COUNT['source_observer_states']==COUNT['source_MB_sampled']+COUNT['source_BASE_sampled']
assert manifest['FFD_states_filter']==2177856 and manifest['FFD_states_FF_verification']==manifest['FFD_states_truth_reference']==0
for name,digest in index.items():assert sha(OUT/name)==digest
result=dict(decision='ACCEPT',scope='C2_REMAINING_SEEDS11_29_418_WINDOWS_ALL_CORE_MATH_AND_PREDEFINED_SOURCE_SAMPLE',
 question_id='C2-RECURSIVE-001',code_revision=revision,artifact_hashes_sha256=sha(OUT/'ARTIFACT_HASHES.json'),
 manifest_sha256=sha(OUT/'MANIFEST.json'),run_result_sha256=sha(HERE/'RUN_RESULT_REMAINING.json'),
 GO_REMAINING_sha256=sha(HERE/'GO_REMAINING.json'),DEV_acceptance_sha256=sha(devreceipt),
 DEV_artifact_hashes_sha256=dev['artifact_hashes_sha256'],bindings_sha256=go['bindings_sha256'],
 counts=COUNT,max_abs_errors=MAX,minimum_covariance_eigenvalue=MIN_EIG,maximum_covariance_symmetry_error=MAX_SYM,
 source_sample_ledger_sha256=SAMPLE_LEDGER.hexdigest(),
 source_sample_rule='global index multiple25; first/last3; window endpoints+-1; previous-step gate/tap/cell changes+-1; union; MB and BASE separately',
 source_h_H_audit_scope='Predetermined partial sample of logged priors, not exhaustive remaining source reevaluation',
 all_row_math_scope='All motion/F/G/Q,independent Joseph,previous-posterior rho/R,joint gates and GT scoring/NEES/integrals/ACF/blocks/summary verified',
 accepted_DEV_GT_refs_reused=True,DEV_science_or_source_reexecutions=0,independent_original_observer_initializations=1,
 new_RT_calls=0,new_training_runs=0,production_C2_math_functions_called=0,
 report_audit_status='SEPARATE_PENDING_NO_REPORT_MATH_CALLED',
 total_with_accepted_DEV=dict(source_cells=120,window_cells=440,trajectories=2640,posterior_rows=1528320),
 claim_scope='Frozen SourceFFD offline interventions on published same-RF seeds10-29; no benefit/adoption/generalization claim; report audit separate')
print('C2_REMAINING_INDEPENDENT_RESULT '+json.dumps(result,sort_keys=True),flush=True)
