"""Approved, isolated X0a/X1 replay; consumes frozen published predictions."""
from pathlib import Path
import os,sys,json,hashlib,datetime,traceback,time
ROOT=Path(__file__).resolve().parent
PARENT=Path(r'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849')
SRC=PARENT/'p2'; ART=PARENT/'p2_artifacts'; PKG=SRC/'research/PJ_DS_GATED_20261021'
sys.dont_write_bytecode=True
for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='1'
os.environ.update(PJ_SOURCE_ROOT=str(SRC),PJ_ART=str(ART),PJ_OUT=str(ROOT/'runtime'))
import numpy as np
import pandas as pd

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(name,data):
 p=ROOT/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def event(stage,**kw):
 rec=dict(utc=now(),stage=stage,**kw)
 with (ROOT/'events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(rec,ensure_ascii=False)+'\n')
 print(json.dumps(rec,ensure_ascii=False),flush=True)
def one(g):
 m=list(ART.rglob(g));assert len(m)==1,(g,len(m));return m[0]
def stopcheck():
 f=os.environ.get('MANAGED_PROCESS_STOP_FILE')
 if f and Path(f).exists():raise RuntimeError('MANAGED_STOP_REQUESTED')

checks=[]
def check(name,a,b,atol,rtol=0):
 a=np.asarray(a);b=np.asarray(b);assert a.shape==b.shape,(name,a.shape,b.shape)
 if a.dtype.kind=='b' or b.dtype.kind=='b':diff=int(np.count_nonzero(a!=b));ok=diff==0
 else:diff=float(np.max(np.abs(a-b)));ok=bool(np.all(np.isfinite(a)) and np.all(np.isfinite(b)) and np.allclose(a,b,atol=atol,rtol=rtol))
 checks.append(dict(name=name,max_abs_difference=diff,atol=atol,rtol=rtol,pass_check=ok))
 if not ok:
  write('CHECKS_FAILURE.json',checks);raise RuntimeError('PARITY_FAILED:'+name+':'+str(diff))

def preflight():
 event('INPUT_FREEZE_START');records=[]
 lock=json.loads((ROOT/'source_blob_lock.json').read_text())
 for x in lock['files']+lock['reference_files']:
  p=SRC/x['path'];b=p.read_bytes();blob=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest();assert blob==x['sha'],('SOURCE_BLOB',p)
  records.append(dict(path=str(p),sha256=hashlib.sha256(b).hexdigest(),git_blob=blob,bytes=len(b)))
 staged=json.loads((PARENT/'STAGING_RECEIPT.json').read_text())
 for x in staged['snapshot_data']:
  p=SRC/x['path'];assert sha(p)==x['sha256'],('SNAPSHOT_HASH',p)
  records.append(dict(path=str(p),sha256=x['sha256'],bytes=p.stat().st_size))
 for n,h in staged['banks'].items():
  p=PARENT/n;assert sha(p)==h,('BANK',n);records.append(dict(path=str(p),sha256=h,bytes=p.stat().st_size))
 manifest=json.loads((SRC/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())
 art_lock={x['path']:x for x in json.loads((ART/'SHA256_MANIFEST.json').read_text())['files']}
 needed=[one('OBSERVATION_FEATURES_LABELS.csv.gz'),one('OOF_PARAMETERS.csv.gz')]
 for case in manifest['cases']:
  for bias in ('B0','L2'):needed.append(one(f'{case["id"]}_full_{bias}_TRACE.npz'))
 for p in needed:
  rel=p.relative_to(ART).as_posix();h=sha(p);assert rel in art_lock,('UNRECEIPTED',rel);assert art_lock[rel]['sha256']==h,('ART_HASH',rel)
  records.append(dict(path=str(p),sha256=h,bytes=p.stat().st_size))
 import scipy,sklearn
 assert [np.__version__,scipy.__version__,pd.__version__,sklearn.__version__]==['2.3.3','1.16.2','2.3.2','1.7.2']
 write('INPUT_LOCK.json',dict(utc=now(),source_run=39574195919,source_commit=lock['original_sha'],runtime=sys.version,packages=dict(numpy=np.__version__,scipy=scipy.__version__,pandas=pd.__version__,sklearn=sklearn.__version__),platform_note='Original CI Python 3.11 Linux; local Python 3.13 Windows. Numerical parity required before interventions.',files=records,protocol_sha256=sha(ROOT/'PROTOCOL.md'),script_sha256=sha(__file__),command=sys.argv))
 event('INPUT_FREEZE_PASS',files=len(records));return manifest

def forced_update(x,P,z,h,H,mu,R,accept,ronly):
 """Fixed acceptance, physical joint/scalar Kalman updates, no re-gating."""
 v=z[None]-h-mu;HP=H@P;S=HP@np.swapaxes(H,-1,-2)+R;S=.5*(S+np.swapaxes(S,-1,-2))
 nis=np.einsum('ni,ni->n',v,np.linalg.solve(S,v[...,None])[...,0])
 K=np.swapaxes(np.linalg.solve(S,HP),-1,-2)
 for j in np.flatnonzero(ronly):
  K[j]=0.;K[j,:,0]=HP[j,0]/S[j,0,0]
 cand=x+np.einsum('nij,nj->ni',K,v);cand[:,2]=V.MC.wrap(cand[:,2])
 A=np.eye(4)[None]-K@H;C=A@P@np.swapaxes(A,-1,-2)+K@R@np.swapaxes(K,-1,-2);C=.5*(C+np.swapaxes(C,-1,-2))
 return np.where(accept[:,None],cand,x),np.where(accept[:,None,None],C,P),nis,accept.copy(),K

def test_update():
 rng=np.random.default_rng(4026);J=4
 x=rng.normal(size=(J,4));L=rng.normal(size=(J,4,4));P=L@L.swapaxes(-1,-2)+np.eye(4)*.1
 H=rng.normal(size=(J,2,4));h=rng.normal(size=(J,2));z=np.array([.7,-.2]);mu=np.zeros((J,2));R=np.tile(np.diag([.4,.2]),(J,1,1))
 ref=V.MC.update(x,P,z,h,H,mu,R,R,np.ones(J));got=forced_update(x,P,z,h,H,mu,R,ref[3],np.zeros(J,bool))
 for k in (0,1,2,3,4):check('unit_joint_'+str(k),got[k],ref[k],1e-12)
 yes=np.array([True,False,True,False]);got=forced_update(x,P,z,h,H,mu,R,yes,np.ones(J,bool))
 for j in range(J):
  if not yes[j]:check('unit_reject_x'+str(j),got[0][j],x[j],0);check('unit_reject_P'+str(j),got[1][j],P[j],0);continue
  hr=H[j,0];kr=P[j]@hr/(hr@P[j]@hr+R[j,0,0]);xp=x[j]+kr*(z[0]-h[j,0]);xp[2]=V.MC.wrap(xp[2]);A=np.eye(4)-np.outer(kr,hr);cp=A@P[j]@A.T+R[j,0,0]*np.outer(kr,kr)
  check('unit_scalar_x'+str(j),got[0][j],xp,1e-12);check('unit_scalar_P'+str(j),got[1][j],cp,1e-12)
 event('HARNESS_UNIT_PASS')

def load_case(case,bias,feat,par,mr,hg):
 cid=case['id'];old=np.load(one(f'{cid}_full_{bias}_TRACE.npz'),allow_pickle=False)
 t=old['t_s'];ids=old['pose_id'];truth=old['truth_scoring_only'];old.close()
 d=feat[(feat.case==cid)&(feat.channel=='full')].set_index('pose_id').loc[ids]
 p=par[(par.case==cid)&(par.channel=='full')&(par.model=='POWER_DIAG')].set_index('pose_id').loc[ids]
 q=mr[(mr.case==cid)&(mr.bias==bias)&(mr.channel=='full')].set_index('pose_id').loc[ids]
 g=hg[(hg.case==cid)&(hg.bias==bias)].set_index('pose_id').loc[ids]
 for nm,table in [('MR',q),('HG',g)]:check(cid+bias+nm+'_time',table.t_s,t,0);check(cid+bias+nm+'_ids',table.index,ids,0)
 mu=p[['mu_r','mu_s']].to_numpy(float);R=np.zeros((len(t),2,2));R[:,0,0]=p.Vr;R[:,1,1]=p.Vs;R[:,0,1]=R[:,1,0]=p.Crs
 assert np.all(p.Crs==0)
 pred=d.e_r.to_numpy()-q.MU_R_EXDS__meas_r_cm.to_numpy()/100
 check(cid+bias+'_base_recovered_mu',d.e_r.to_numpy()-q.BASE__meas_r_cm.to_numpy()/100,mu[:,0],1e-12)
 other=mr[(mr.case==cid)&(mr.bias!=bias)&(mr.channel=='full')].set_index('pose_id').loc[ids]
 check(cid+bias+'_frozen_prediction_bias_independent',other.MU_R_EXDS__meas_r_cm,q.MU_R_EXDS__meas_r_cm,1e-10)
 check(cid+bias+'_archived_label',g.e_r,d.e_r,1e-12)
 controls,x0=V.build_positive_bias_controls(t,truth,bias)
 return dict(t=t,ids=ids,truth=truth,z=d[['range_m','s_fp']].to_numpy(float),e=d[['e_r','e_s']].to_numpy(float),mu=mu,R=R,pred=pred,controls=controls,x0=x0,mr=q,hg=g)

def replay(case,inp,model,names,kind,masks=None):
 t=inp['t'];n=len(t);J=len(names);x=np.tile(np.r_[inp['x0'],0.],(J,1));P=np.tile(np.diag(np.r_[V.INITIAL_POSE_STD**2,V.BIAS_PRIOR_STD**2]),(J,1,1))
 shapes={'x':(4,),'P':(4,4),'prior':(4,),'Pprior':(4,4),'K':(4,2),'H':(2,4),'h':(2,),'nu':(2,),'mu':(2,),'R':(2,2),'nis':()}
 out={key:np.empty((n,J)+shape) for key,shape in shapes.items()};out['acc']=np.empty((n,J),bool);out['ronly']=np.zeros((n,J),bool)
 for k in range(n):
  if k%128==0:stopcheck()
  if k:
   c=inp['controls']
   for j in range(J):x[j],P[j]=V.predict_one(x[j],P[j],float(c['ds_odom'][k]),float(c['dtheta_gyro'][k]),float(c['dt_s'][k]))
  h,H=model.batch(x,case);mu=np.tile(inp['mu'][k],(J,1));R=np.tile(inp['R'][k],(J,1,1))
  for j,name in enumerate(names):
   if name.startswith('M'):mu[j,0]=inp['pred'][k]
  out['prior'][k]=x;out['Pprior'][k]=P;out['H'][k]=H;out['h'][k]=h;out['nu'][k]=inp['z'][k][None]-h-mu;out['mu'][k]=mu;out['R'][k]=R
  ronly=np.zeros(J,bool)
  if kind=='reference':x,P,nis,acc,K=V.MC.update(x,P,inp['z'][k],h,H,mu,R,R,np.ones(J))
  else:
   acc=np.array([masks[k,0 if name[1]=='B' else 1] for name in names],bool)
   for j,name in enumerate(names):
    if name=='MM_NEW_RANGE_ONLY':ronly[j]=bool(masks[k,1] and not masks[k,0])
   x,P,nis,acc,K=forced_update(x,P,inp['z'][k],h,H,mu,R,acc,ronly)
  out['x'][k]=x;out['P'][k]=P;out['nis'][k]=nis;out['acc'][k]=acc;out['K'][k]=K;out['ronly'][k]=ronly
 return out

def metrics(case,bias,inp,out,names):
 X=out['x'];C=out['P'];truth=inp['truth'];t=inp['t'];m=t>=30
 scores=V.MC.score(X,C,t,truth,np.radians(V.BIAS_LEVELS[bias]));anc=np.asarray(case['anchor']);dz=anc[2]-case['robot_z_m']
 dtrue=np.sqrt(np.sum((truth[:,:2]-anc[:2])**2,axis=1)+dz**2);dh=np.sqrt(np.sum((X[:,:,:2]-anc[:2])**2,axis=2)+dz**2);rerr=(dh-dtrue[:,None])*100
 herr=np.degrees(V.MC.wrap(X[:,:,2]-truth[:,None,2]));hsig=np.degrees(np.sqrt(C[:,:,2,2]))
 rows=[]
 for j,name in enumerate(names):rows.append(dict(case=case['id'],route=case['route'],bias=bias,arm=name,**scores[j],range_err_rmse_cm=float(np.sqrt(np.mean(rerr[m,j]**2))),accepted_n=int(out['acc'][m,j].sum()),accepted_all_n=int(out['acc'][:,j].sum()),scoring_n=int(m.sum()),n=len(t)))
 return rows,dict(herr=herr,range_err=rerr,hsig=hsig)

def save_trace(stage,cid,bias,inp,out,names):
 d=ROOT/stage;d.mkdir(exist_ok=True)
 np.savez_compressed(d/f'{cid}_{bias}.npz',t_s=inp['t'],pose_id=inp['ids'],truth_scoring_only=inp['truth'],names=np.asarray(names),z=inp['z'],**out)

def main():
 global V
 manifest=preflight()
 sys.path.insert(0,str(PKG));import v_replay as V
 test_update()
 feat=pd.read_csv(one('OBSERVATION_FEATURES_LABELS.csv.gz'));par=pd.read_csv(one('OOF_PARAMETERS.csv.gz'))
 mr=pd.read_csv(PKG/'results_murec/MR_SERIES.csv.gz');hg=pd.read_csv(PKG/'results_hgate/HG_SERIES.csv.gz');oldsc=pd.read_csv(PKG/'results_murec/MR_SCORES.csv')
 model=V.SourceFFD();ref_names=['BB','MM'];all_ref=[]
 for case in manifest['cases']:
  for bias in ('B0','L2'):
   label=case['id']+'_'+bias;event('X0A_START',condition=label);inp=load_case(case,bias,feat,par,mr,hg)
   out=replay(case,inp,model,ref_names,'reference');rows,ser=metrics(case,bias,inp,out,ref_names)
   for j,nm in enumerate(['BASE','MU_R_EXDS']):
    check(label+nm+'_published_mask',out['acc'][:,j],inp['hg'][nm+'__acc'].to_numpy(bool),0)
    check(label+nm+'_published_nis',out['nis'][:,j],inp['hg'][nm+'__nis'],1e-7)
    for ch,idx in [('r',0),('s',1)]:check(label+nm+'_published_nu_'+ch,out['nu'][:,j,idx],inp['hg'][nm+'__nu_'+ch],1e-9)
    for key,col in [('herr','herr_deg'),('range_err','range_err_cm'),('hsig','hsig_deg')]:check(label+nm+'_published_'+key,ser[key][:,j],inp['mr'][nm+'__'+col],1e-8)
    check(label+nm+'_HG_heading',ser['herr'][:,j],inp['hg'][nm+'__herr'],1e-8)
    old=oldsc[(oldsc.case==case['id'])&(oldsc.bias==bias)&(oldsc.channel=='full')&(oldsc.arm==nm)].iloc[0]
    for metric in ['heading_rmse_deg','range_err_rmse_cm','bias_rmse_dps','xy_rmse_m']:check(label+nm+'_score_'+metric,rows[j][metric],old[metric],1e-8)
   identity=replay(case,inp,model,ref_names,'forced',out['acc'])
   for key in out:check(label+'_harness_identity_'+key,identity[key],out[key],1e-11,1e-10)
   save_trace('x0a',case['id'],bias,inp,out,ref_names);all_ref.extend(rows)
   write('X0A_CHECKS.json',checks);event('X0A_CASE_PASS',condition=label)
 pd.DataFrame(all_ref).to_csv(ROOT/'X0A_SCORES.csv',index=False)
 write('X0A_GATE.json',dict(status='PASS',conditions=14,checks=len(checks),archived_full_state_available=False,archived_columns='mask,NIS,innovations,heading,range_error,heading_sigma,scores',new_instrumented_identity='all prior/posterior/P/K/H/mu/R/innovation/mask',utc=now()))
 event('X0A_ALL_PASS',conditions=14)
 # No intervention runs before the global parity gate passes.
 names=['BB','MB','BM','MM','MM_NEW_RANGE_ONLY'];all_rows=[];trans=[];packets=[]
 for case in manifest['cases']:
  for bias in ('B0','L2'):
   label=case['id']+'_'+bias;event('X1_START',condition=label);inp=load_case(case,bias,feat,par,mr,hg)
   with np.load(ROOT/'x0a'/f'{label}.npz',allow_pickle=False) as z:ref={k:z[k] for k in ['acc','x','P','prior','Pprior','K','H','h','nu','mu','R','nis']}
   out=replay(case,inp,model,names,'forced',ref['acc']);rows,ser=metrics(case,bias,inp,out,names)
   for j,jr in [(0,0),(3,1)]:
    for key in ref:check(label+'_X1_identity_'+names[j]+'_'+key,out[key][:,j],ref[key][:,jr],1e-11,1e-10)
   for j,name in enumerate(names):
    check(label+'_forced_mask_'+name,out['acc'][:,j],ref['acc'][:,0 if name[1]=='B' else 1],0)
    rejected=~out['acc'][:,j]
    check(label+'_reject_x_'+name,out['x'][rejected,j],out['prior'][rejected,j],0) if rejected.any() else None
    check(label+'_reject_P_'+name,out['P'][rejected,j],out['Pprior'][rejected,j],0) if rejected.any() else None
   asym=float(np.max(abs(out['P']-out['P'].swapaxes(-1,-2))));eig=float(np.linalg.eigvalsh(out['P']).min());assert asym<1e-12 and eig>=-1e-12,(asym,eig)
   ab,am=ref['acc'].T;new=am&~ab;m=inp['t']>=30
   check(label+'_range_only_set',out['ronly'][:,4],new,0)
   for window,sel in [('all',np.ones(len(m),bool)),('t_ge_30',m)]:
    trans.append(dict(case=case['id'],bias=bias,window=window,both_accept=int((ab&am&sel).sum()),new_accept=int((new&sel).sum()),new_reject=int((ab&~am&sel).sum()),both_reject=int((~ab&~am&sel).sum()),min_cov_eigenvalue=eig))
   for j,name in enumerate(names):
    packets.append(pd.DataFrame(dict(case=case['id'],bias=bias,arm=name,pose_id=inp['ids'],t_s=inp['t'],base_accept=ab,mur_accept=am,new_accept=new,accepted=out['acc'][:,j],range_only=out['ronly'][:,j],counterfactual_self_nis=out['nis'][:,j],self_would_accept=out['nis'][:,j]<=V.MC.G2,nu_r=out['nu'][:,j,0],nu_s=out['nu'][:,j,1],heading_error_deg=ser['herr'][:,j],range_error_cm=ser['range_err'][:,j],heading_update_r_deg=np.degrees(out['K'][:,j,2,0]*out['nu'][:,j,0])*out['acc'][:,j],heading_update_s_deg=np.degrees(out['K'][:,j,2,1]*out['nu'][:,j,1])*out['acc'][:,j],bias_estimate_dps=np.degrees(out['x'][:,j,3]))))
   save_trace('x1',case['id'],bias,inp,out,names);all_rows.extend(rows);event('X1_CASE_PASS',condition=label,new_accept_after30=int((new&m).sum()))
 pd.DataFrame(all_rows).to_csv(ROOT/'X1_SCORES.csv',index=False);pd.DataFrame(trans).to_csv(ROOT/'X1_MASK_TRANSITIONS.csv',index=False);pd.concat(packets,ignore_index=True).to_csv(ROOT/'X1_PACKETS.csv.gz',index=False,compression='gzip')
 write('ALL_CHECKS.json',checks)
 # Verify imported source files did not change, and retain the complete dependency inventory.
 imported=[]
 for name,module in list(sys.modules.items()):
  file=getattr(module,'__file__',None)
  if file and Path(file).is_relative_to(SRC) and Path(file).is_file():imported.append(dict(module=name,path=str(file),sha256=sha(file)))
 write('IMPORTED_SOURCES.json',imported)
 locked=json.loads((ROOT/'INPUT_LOCK.json').read_text())
 for rec in locked['files']:assert sha(rec['path'])==rec['sha256'],('INPUT_CHANGED',rec['path'])
 write('EXECUTION_RESULT.json',dict(status='TECHNICAL_PASS',X0a='PASS',X1='EXECUTED',conditions=14,x1_arms=5,checks=len(checks),scientific_claim='NONLINEAR_FIXED_MASK_DIAGNOSTIC_ONLY',inputs_preserved=True,utc=now()))
 event('EXECUTION_COMPLETE',checks=len(checks))

if __name__=='__main__':
 try:main()
 except BaseException as e:
  write('FAILURE.json',dict(status='STOP',error=str(e),traceback=traceback.format_exc(),utc=now()));event('STOP',error=str(e));raise
