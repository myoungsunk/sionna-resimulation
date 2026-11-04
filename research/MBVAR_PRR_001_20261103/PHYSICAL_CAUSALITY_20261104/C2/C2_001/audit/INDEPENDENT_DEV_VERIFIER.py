"""Independent C2 DEV verifier. No production C2 modules or online/core math calls.
Original locked SourceFFD is the only observation provider. All recursive states,
motion, gates, Joseph updates and evaluator metrics below are independently built.
Read-only; run only after terminal successful DEV. No new scientific policy run.
"""
import os
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import csv,hashlib,importlib.metadata,importlib.util,json,math,platform,subprocess,sys
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_info
ROOT=Path('D:/codex/MBVAR_PRR_001_20261103')
HERE=ROOT/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/C2/C2_001'
OUT=HERE/'DEV_001'
CACHE=Path('D:/codex/MBVAR_PRR_001_20261103_inputs/C1B_001')
INPUTS=CACHE.parent/'C1A_001'
C1B=HERE.parents[1]/'C1/C1B_001'
MODES=('fixed','fixed','fixed','own','own','own')
ARMS=('LF','FL','LL','LF','FL','LL')
BOUND=('authority.py','engine.py','evaluate.py','run.py','launch.py','test_engine.py','PLAN.json','WINDOWS.json','INPUT_LOCK.json','CONTRACT_KO.md','GOVERNANCE.json','../../C1/C1B_001/legacy.py')
MAX={}
COUNT=dict(source_cells=0,window_cells=0,trajectories=0,posterior_rows=0,
 source_observer_states=0,source_observer_calls=0,Full_reference_MB_rows=0,
 Full_reference_BASE_rows=0,intervention_MB_rows=0,intervention_BASE_rows=0,
 GT_reference_rows=0,summary_rows=0,block_rows=0,acf_rows=0)
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
def motion(x,P,k,ctl):
 if not k:return x.copy(),P.copy(),np.eye(4),np.zeros((4,3)),np.zeros((3,3))
 ds,gy,dt=(float(ctl[q][k]) for q in ('ds','gy','dt'))
 assert dt>0 and np.isfinite([ds,gy,dt]).all()
 a=gy-x[3]*dt
 if abs(a)<1e-4:
  a2=a*a;c=1-a2/24+a2*a2/1920-a2**3/322560;dc=-a/12+a**3/480-a**5/53760
 else:
  h=a/2;c=math.sin(h)/h;dc=(h*math.cos(h)-math.sin(h))/(2*h*h)
 phi=x[2]+a/2;u=np.array([math.cos(phi),math.sin(phi)])
 disp=ds*c*u;der=ds*(dc*u+c*np.array([-u[1],u[0]])/2)
 y=x.copy();y[:2]+=disp;y[2]=wrap(x[2]+a)
 F=np.eye(4);F[:2,2]=[-disp[1],disp[0]];F[:2,3]=-dt*der;F[2,3]=-dt
 G=np.zeros((4,3));G[:2,0]=c*u;G[:2,1]=der;G[2,1]=1.;G[3,2]=1.
 Q=np.diag([2e-5*abs(ds),math.radians(.015)**2*dt,0.])
 return y,sym(F@sym(P)@F.T+G@Q@G.T),F,G,Q
def update(prior,C,h,H,z,mu,R,allowed=None):
 nu=z-h-mu;S=H@C@H.T+R
 if allowed is not None:S=sym(S)
 nis=float(nu@np.linalg.solve(S,nu))
 permitted=nis<=9.210340371976184 if allowed is None else bool(allowed)
 K=np.linalg.solve(S,H@C).T if permitted else np.zeros((4,2))
 u=prior+K@nu;x=u.copy()
 if permitted:x[2]=wrap(x[2]);A=np.eye(4)-K@H;P=sym(A@C@A.T+K@R@K.T)
 else:P=C.copy()
 return dict(x=x,P=P,h=h,H=H,K=K,S=S,nu=nu,nis=nis,mask=permitted,u=u)
def observations(states):
 parts=[];jacs=[];diags=[]
 for k in range(0,len(states),32):
  h,H,d=observer.batch(np.asarray(states[k:k+32]),CASE,return_diagnostics=True)
  assert np.isfinite(h).all() and np.isfinite(H).all()
  parts.append(h);jacs.append(H);diags.append(d)
  COUNT['source_observer_states']+=len(h);COUNT['source_observer_calls']+=1
 return np.concatenate(parts),np.concatenate(jacs),{key:np.concatenate([d[key] for d in diags]) for key in diags[0]}
def matching(data,i,j,rec,pred,diag,index,base=False):
 prefix='BASE_' if base else ''
 for key in ('x','P','h','H','S','nis'):
  if key=='x':
   chk(prefix+'x_nonangular',data[prefix+key][i,j,[0,1,3]],rec[key][[0,1,3]])
   chk(prefix+'yaw',data[prefix+key][i,j,2],rec[key][2],True)
  else:chk(prefix+key,data[prefix+key][i,j],rec[key])
 exact(prefix+'mask',data[prefix+'mask'][i,j],rec['mask'])
 for key,expected in [('prior',pred[0]),('Pprior',pred[1]),('F',pred[2]),('G',pred[3]),('Qstate',pred[3]@pred[4]@pred[3].T)]:
  chk(prefix+key,data[prefix+key][i,j],expected)
 for key in ('tap','cells'):exact(prefix+key,data[prefix+key][i,j],diag[key][index])
 chk(prefix+'fp_margin',data[prefix+'fp_margin'][i,j],diag['fp_margin'][index])
 if not base:
  for key in ('K','nu','u'):chk(key,data[key][i,j],rec[key])
  chk('Qinput',data['Qinput'][i],pred[4])
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
manifest=js(OUT/'MANIFEST.json');execution=js(HERE/'RUN_RESULT_DEV.json')
assert manifest['status']==execution['status']=='NUMERICAL_PASS_PENDING_INDEPENDENT_RESULT_AUDIT'
assert execution['exit_code']==0 and execution['result_status']==manifest['status']
plan=js(HERE/'PLAN.json');go=js(HERE/'GO_DEV.json');phase=plan['phases']['dev']
authorization=dict(stage='C2_only',phase='dev',routes=plan['routes'],biases=plan['biases'],seeds=[10],output='DEV_001',window_cells=22,trajectories=132,posterior_rows=76416)
assert go['schema']=='C2_GO_V1' and go['decision']=='GO' and go['authorized']==authorization
assert set(go['bindings_sha256'])==set(BOUND) and manifest['bindings_sha256']==go['bindings_sha256']
revision='c0b82a54f04e02b9fb6bcac163885c0ffd16326c'
assert manifest['code_revision']==execution['code_revision']==revision
assert manifest['go_sha256']==execution['go_sha256']==sha(HERE/'GO_DEV.json')
for name,digest in go['bindings_sha256'].items():
 assert sha(HERE/name)==digest,name
 gp=(HERE/name).resolve().relative_to(ROOT).as_posix()
 assert hashlib.sha256(subprocess.check_output(['git','-C',str(ROOT),'show',revision+':'+gp])).hexdigest()==digest
gp=(HERE/'GO_DEV.json').relative_to(ROOT).as_posix()
assert subprocess.check_output(['git','-C',str(ROOT),'show',revision+':'+gp])==(HERE/'GO_DEV.json').read_bytes()
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
assert manifest['FF_source_verification_replays']==6
for key,expected in [('source_cells_completed',6),('window_cells_completed',22),('trajectories',132),('posterior_rows',76416)]:assert manifest[key]==expected
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
pindex=C1B/'DEV_001/ARTIFACT_HASHES.json';assert sha(pindex)==parent_audit['phase_artifact_and_report_sha256']['DEV_001/ARTIFACT_HASHES.json']
parent_index=js(pindex)
for route in plan['routes']:
 for bias in plan['biases']:
  cell=f'{route}_{bias}_10';full=read(INPUTS/f'{route}_aB_m0_{bias}_Full.npz');los=read(INPUTS/f'{route}_aB_m0_{bias}_Native_LoS.npz')
  trace=read(INPUTS/(cell+'_TRACE.npz'));ctl=read(CACHE/'controls'/f'{route}_aB_m0_{bias}_10.npz')
  pp=C1B/'DEV_001/cells'/(cell+'.npz');assert sha(pp)==parent_index['cells/'+cell+'.npz'];base=read(pp)
  truth=read(INPUTS/f'{route}_{bias}_TRUTH.npz');ff=read(OUT/'verification'/(cell+'.npz'))
  n=plan['route_rows'][route];assert len(full['t'])==n
  for d in (los,trace,base,truth,ff):
   for key in ('t','pose_id'):exact(cell+key,d[key],full[key])
  assert len(set(full['pose_id'].tolist()))==n
  chk('5Hz',np.diff(full['t']),np.full(n-1,.2));exact('FF_arms',ff['arms'],['FF']);exact('FF_modes',ff['modes'],['own'])
  ff_x=[];ff_P=[];bb_x=[];bb_P=[]
  x=np.r_[ctl['x0'],0.];P=full['P0'].copy();bx=x.copy();bP=P.copy()
  for k in range(n):
   mb=motion(x,P,k,ctl);bp=motion(bx,bP,k,ctl)
   h,H,diag=observations([bp[0],mb[0]])
   br=update(bp[0],bp[1],h[0],H[0],full['z'][k],full['muBASE'][k],full['R'][k])
   rho=math.hypot(x[0]-10.,x[1]);sig=float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]))
   R=full['R'][k].copy();R[1,1]+=sig*sig
   mr=update(mb[0],mb[1],h[1],H[1],full['z'][k],full['muMB'][k],R,br['mask'])
   matching(ff,k,0,mr,mb,diag,1);matching(ff,k,0,br,bp,diag,0,True)
   for key,v in [('R',R),('rho',rho),('sigma_b',sig),('z',full['z'][k])]:chk('FF_'+key,ff[key][k,0],v)
   exact('FF_mask_archived',br['mask'],trace['mask'][k])
   for key in ('x','P','h','H','K','nu','S','prior','Pprior'):
    v=mr[key] if key not in ('prior','Pprior') else mb[0 if key=='prior' else 1]
    chk('FF_archived_'+key,trace[key][k],v,angular=False)
   for key in ('x','P','h','H','S','prior','Pprior'):
    v=br[key] if key not in ('prior','Pprior') else bp[0 if key=='prior' else 1]
    chk('Full_BASE_archived_'+key,base['BASE_'+key][k],v)
   ff_x.append(mr['x']);ff_P.append(mr['P']);bb_x.append(br['x']);bb_P.append(br['P'])
   x,P=mr['x'],mr['P'];bx,bP=br['x'],br['P']
   COUNT['Full_reference_MB_rows']+=1;COUNT['Full_reference_BASE_rows']+=1
  ff_x=np.asarray(ff_x);ff_P=np.asarray(ff_P);bb_x=np.asarray(bb_x);bb_P=np.asarray(bb_P)
  # Reference GT observer is evaluator-only, after the Full recurrence above.
  reference=read(OUT/'evaluation_refs'/f'{route}_{bias}.npz')
  assert str(reference['truth_sha256'])==sha(INPUTS/f'{route}_{bias}_TRUTH.npz')
  hg,Hg,dg=observations(truth['truth'])
  chk('GT_source_h',reference['h'],hg);chk('GT_source_H',reference['H'],Hg)
  for key,dkey in [('source_tap','tap'),('source_cells','cells')]:exact('GT_'+key,reference[key],dg[dkey])
  chk('GT_margin',reference['source_fp_margin'],dg['fp_margin']);COUNT['GT_reference_rows']+=n
  rfrows=[RF[(route,int(pid))] for pid in full['pose_id']]
  physical=np.array([[float(r['delta_range_m']),float(r['physical_e_mp'])] for r in rfrows]);taps=np.array([int(r['delta_tap']) for r in rfrows])
  chk('physical_delta',reference['physical_delta'],physical);exact('physical_taps',reference['physical_delta_tap'],taps)
  distance=np.r_[0.,np.cumsum(np.sqrt(np.sum(np.diff(truth['truth'][:,:2],axis=0)**2,axis=1)))]
  chk('GT_distance',reference['distance_m'],distance)
  timebin=np.floor((full['t']+1e-9)/1.).astype(np.int64);distbin=np.floor((distance+1e-12)/.2).astype(np.int64)
  exact('time_bin',reference['time_bin'],timebin);exact('distance_bin',reference['distance_bin'],distbin)
  baseline={k:(v[:,0] if v.ndim==2 else v) for k,v in score(ff_x[:,None],ff_P[:,None],truth).items()}
  bs=read(OUT/'baselines'/(cell+'.npz'));exact('baseline_t',bs.pop('t'),full['t']);exact('baseline_pose',bs.pop('pose_id'),full['pose_id'])
  score_compare(bs,baseline,'baseline_')
  for w in [w for w in windows if w['route']==route]:
   start,end=w['first_index'],w['last_index'];stem=cell+'_'+w['id'];data=read(OUT/'filter'/(stem+'.npz'))
   exact('branch_modes',data['modes'],MODES);exact('branch_arms',data['arms'],ARMS);exact('BASE_indices',data['BASE_branch_indices'],[3,4,5])
   for key in ('t','pose_id'):exact('suffix_'+key,data[key],full[key][start:])
   exact('first_index',data['first_index'],start);exact('last_intervention_index',data['last_intervention_index'],end)
   exact('filled_rows',data['filled_rows'],n-start)
   for key,fkey in [('mu','muMB'),('BASE_mu','muBASE'),('BASE_R','R')]:exact('frozen_'+key,data[key],full[fkey][start:])
   assert n-start==w['suffix_rows'] and end-start+1==w['intervention_packets']
   X=np.repeat((ff_x[start-1] if start else np.r_[ctl['x0'],0.])[None],6,axis=0)
   C=np.repeat((ff_P[start-1] if start else full['P0'])[None],6,axis=0)
   B=np.repeat((bb_x[start-1] if start else np.r_[ctl['x0'],0.])[None],3,axis=0)
   D=np.repeat((bb_P[start-1] if start else full['P0'])[None],3,axis=0)
   for k in range(start,n):
    i=k-start;mb=[motion(X[j],C[j],k,ctl) for j in range(6)];bp=[motion(B[j],D[j],k,ctl) for j in range(3)]
    h,H,diag=observations([q[0] for q in bp]+[q[0] for q in mb])
    z=np.repeat(full['z'][k][None],6,axis=0)
    if k<=end:z[[0,2,3,5],0]=los['z'][k,0];z[[1,2,4,5],1]=los['z'][k,1]
    bm=[]
    for b in range(3):
     br=update(bp[b][0],bp[b][1],h[b],H[b],z[b+3],full['muBASE'][k],full['R'][k])
     matching(data,i,b,br,bp[b],diag,b,True);bm.append(br['mask']);B[b],D[b]=br['x'],br['P']
     COUNT['intervention_BASE_rows']+=1
    for j in range(6):
     rho=math.hypot(X[j,0]-10.,X[j,1]);sig=float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]))
     R=full['R'][k].copy();R[1,1]+=sig**2
     mr=update(mb[j][0],mb[j][1],h[j+3],H[j+3],z[j],full['muMB'][k],R,bool(trace['mask'][k]) if j<3 else bm[j-3])
     matching(data,i,j,mr,mb[j],diag,j+3)
     for key,value in [('z',z[j]),('rho',rho),('sigma_b',sig),('R',R)]:chk(key,data[key][i,j],value)
     X[j],C[j]=mr['x'],mr['P'];COUNT['intervention_MB_rows']+=1
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
    row=dict(route=route,bias=bias,seed=10,window=w['id'],mode=mode,arm=arm,start_s=w['start_s'],end_s=w['end_s'],
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
    ac=dict(route=route,bias=bias,seed=10,window=w['id'],mode=mode,arm=arm,epsilon_range_acf=corr(epsilon[active,j,0]),epsilon_s_acf=corr(epsilon[active,j,1]),
     physical_range_acf=corr(physical[start:][active,0]),physical_s_acf=corr(physical[start:][active,1]))
    tree('ACF',saved_acf[COUNT['acf_rows']],ac);COUNT['acf_rows']+=1
    for kind,labels in [('time_1s',timebin[start:]),('distance_0p2m',distbin[start:])]:
     for label in np.unique(labels[active]):
      mask=active&(labels==label)
      block=dict(route=route,bias=bias,seed=10,window=w['id'],mode=mode,arm=arm,block_kind=kind,block_id=int(label),n=int(mask.sum()),
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
   print('C2_DEV_WINDOW_VERIFIED',cell,w['id'],COUNT['window_cells'],COUNT['source_observer_states'],flush=True)
  COUNT['source_cells']+=1
assert next(blocks,None) is None and next(csv_summaries,None) is None
assert COUNT['summary_rows']==COUNT['acf_rows']==len(saved_summaries)==len(saved_acf)==132
assert COUNT['source_cells']==6 and COUNT['window_cells']==22 and COUNT['trajectories']==132 and COUNT['posterior_rows']==76416
assert COUNT['Full_reference_MB_rows']==COUNT['Full_reference_BASE_rows']==6272
assert COUNT['intervention_MB_rows']==76416 and COUNT['intervention_BASE_rows']==38208 and COUNT['GT_reference_rows']==6272
assert manifest['FFD_states_filter']==114624 and manifest['FFD_states_FF_verification']==12544 and manifest['FFD_states_truth_reference']==6272
assert COUNT['source_observer_states']==133440
# Immutable hash recheck at end, after independent numerical reconstruction.
for name,digest in index.items():assert sha(OUT/name)==digest
result=dict(decision='ACCEPT',scope='C2_DEV_SEED10_22_WINDOWS_ALL_RECURSIVE_BRANCHES',question_id='C2-RECURSIVE-001',
 code_revision=revision,artifact_hashes_sha256=sha(OUT/'ARTIFACT_HASHES.json'),manifest_sha256=sha(OUT/'MANIFEST.json'),
 run_result_sha256=sha(HERE/'RUN_RESULT_DEV.json'),GO_DEV_sha256=sha(HERE/'GO_DEV.json'),bindings_sha256=go['bindings_sha256'],
 counts=COUNT,max_abs_errors=MAX,minimum_covariance_eigenvalue=MIN_EIG,maximum_covariance_symmetry_error=MAX_SYM,
 independent_original_observer_initializations=1,new_RT_calls=0,new_training_runs=0,production_C2_math_functions_called=0,
 full_from_t0_prefix_reference_source_cells=6,independent_postintervention_reference_branches=132,
 claim_scope='Frozen SourceFFD offline window interventions on published same-RF seed10 only; no benefit/adoption/generalization claim',
 remaining_GO_in_this_verifier=False)
print('C2_DEV_INDEPENDENT_RESULT '+json.dumps(result,sort_keys=True),flush=True)
