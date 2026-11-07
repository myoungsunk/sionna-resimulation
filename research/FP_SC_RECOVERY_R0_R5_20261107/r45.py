import os
for k in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import sys,json,csv,gzip,hashlib,datetime,math,traceback,time
import numpy as np
ROOT=Path(__file__).resolve().parent;SRC=ROOT/'R45_sources';OUT=ROOT/'R45_RUN_001'
sys.path[:0]=[str(SRC/'src'),str(SRC/'research/FFD_P0P3_20261016'),str(SRC/'research/EKF4_RANGE_S_STAGED_20261014')]
from qclean_uwb.fp_sc.e0_baseline import load_original_model,SPEC
from qclean_uwb.drivesim import observation as obs
from r2 import choose,STEP
ARMS=['B','DROP','K1_R','K2_R','K1_RS','K2_RS']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def table(n,rs):
 with (OUT/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rs[0]));w.writeheader();w.writerows(rs)
LOCK=json.loads((ROOT/'RUN_002/SUMMARY.json').read_text())['source_hashes']
def cached(path):
 p=ROOT/'inputs'/(hashlib.sha256(path.encode()).hexdigest()[:20]+'_'+Path(path).name)
 if not p.exists():p=ROOT.parent/'vab_pm_check/inputs'/path
 assert sha(p)==LOCK[path]['sha256'];return p
def data(case,name):
 path=next(p for p in LOCK if p.endswith('/'+case+'/'+name))
 if name.endswith('.npz'):
  with np.load(cached(path),allow_pickle=False) as f:return {k:f[k] for k in f.files}
 return json.loads(gzip.decompress(cached(path).read_bytes()))
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
def centers(model,x,P):
 points=[]
 for a,b in zip(x,P):
  ev,u=np.linalg.eigh(b[:3,:3]);delta=(u*np.sqrt(np.maximum(ev,0))[None,:]*2).T
  q=np.tile(a,(7,1));q[1:4,:3]+=delta;q[4:7,:3]-=delta;points.append(q)
 _,_,d=model.batch(np.concatenate(points),SPEC,gradient=False,return_diagnostics=True)
 rr=d['native_range'].reshape(len(x),7)
 return (rr.min(axis=1)+rr.max(axis=1))/2
def prepare(case,on):
 cir=obs.cir_batch(on['Hrf']);a=abs(cir);edges=np.argmax(a>=.3*a.max(axis=1)[:,None,:],axis=1);B=edges.min(axis=1)
 p=a*a;S=(p[:,:,0]-p[:,:,1])/p.sum(axis=2)
 archived=[r for r in data(case,'ROWS.json.gz') if r['mode']=='C'];archived.sort(key=lambda r:r['k'])
 assert len(archived)==len(B)
 pools=[[dict(tap=c['tap'],cost=-math.log(max(c['support'],1e-12)),eligible=c['selection_eligible']) for c in r['decision']['scores']] for r in archived]
 oldcenter=np.array([(r['p_interval']['low']+r['p_interval']['high'])/2 for r in archived])
 return B,S,pools,oldcenter
def replay_six(core,online,model,on,B,S,pools,case):
 n=len(B);x=np.tile(on['x0'],(6,1));P=np.tile(on['P0'],(6,1,1));sx=x.copy();sp=P.copy()
 controls={k:on[k] for k in ['ds','gy','dt']}
 shapes={'x':(6,4),'P':(6,4,4),'prior':(6,4),'Pprior':(6,4,4),'shadow_x':(6,4),'shadow_P':(6,4,4),'H':(6,2,4),'h':(6,2),'R':(6,2,2),'K':(6,4,2),'z':(6,2),'center':(6,),'nis':(6,),'gate_nis':(6,),'selected':(6,),'alarm':(6,),'accepted':(6,)}
 tr={k:np.zeros((n,*v)) for k,v in shapes.items()}
 for k in range(n):
  if os.environ.get('MANAGED_PROCESS_STOP_FILE') and Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise RuntimeError('STOP_REQUESTED')
  sigma=np.interp(np.linalg.norm(x[:,:2]-np.array(SPEC['anchor'][:2]),axis=1),[0,1.5,3,6,10],[.011,.020,.050,.120,.240])
  xp=[];pp=[]
  for j in range(6):
   a,b=online.predict(core,x[j],P[j],k,controls);xp.append(a);pp.append(b)
   sx[j],sp[j]=online.predict(core,sx[j],sp[j],k,controls)
  xp=np.array(xp);pp=np.array(pp);center=centers(model,xp,pp)
  h,H=model.batch(np.concatenate([xp,sx]),SPEC);h,sh=h[:6],h[6:];H,sH=H[:6],H[6:]
  z=np.tile([B[k]*STEP,S[k,B[k]]],(6,1));selected=np.full(6,B[k],int);alarm=abs(B[k]*STEP-center)>.075+1e-12
  for j,arm in enumerate(ARMS):
   if alarm[j] and arm.startswith('K'):
    selected[j],_=choose(int(B[k]),center[j],pools[k],arm[:2]);z[j,0]=selected[j]*STEP
    if arm.endswith('RS'):z[j,1]=S[k,selected[j]]
   v=z[j]-sh[j]-on['muBASE'][k];ss=sH[j]@sp[j]@sH[j].T+on['R'][k];gn=float(v@np.linalg.solve(ss,v));allow=gn<=online.GATE and not (arm=='DROP' and alarm[j])
   if allow:
    gain=np.linalg.solve(ss,sH[j]@sp[j]).T;sx[j]+=gain@v;sx[j,2]=wrap(sx[j,2]);A=np.eye(4)-gain@sH[j];sp[j]=A@sp[j]@A.T+gain@on['R'][k]@gain.T;sp[j]=(sp[j]+sp[j].T)*.5
   R=on['R'][k].copy();R[1,1]+=sigma[j]**2;nu=z[j]-h[j]-on['muMB'][k]
   x[j],P[j],K,innov=online.joseph(xp[j],pp[j],H[j],nu,R,allow,1.)
   for key,value in [('x',x[j]),('P',P[j]),('prior',xp[j]),('Pprior',pp[j]),('shadow_x',sx[j]),('shadow_P',sp[j]),('h',h[j]),('H',H[j]),('R',R),('K',K),('z',z[j]),('center',center[j]),('nis',float(nu@np.linalg.solve(innov,nu))),('gate_nis',gn),('selected',selected[j]),('alarm',alarm[j]),('accepted',allow)]:tr[key][k,j]=value
  if k%200==0:print('R5',case,k,'/',n,flush=True)
 assert all(np.isfinite(v).all() for v in tr.values())
 assert np.linalg.eigvalsh(tr['P']).min()>-1e-12
 return tr
def evaluate(case,on,ev,B,S,pools,oldcenter,tr):
 truth=ev['truth'];assert truth.shape==(len(B),3)
 assert np.array_equal(ev['t'],on['t']) and np.array_equal(ev['pose_id'],on['pose_id'])
 refs=obs.first_path_batch(obs.cir_batch(ev['clean_H']),1950000);ref=refs['index'];los=refs['s']
 metrics=[];rows=[];r4=[]
 for offset in [-.15,-.075,-.05,-.025,0,.025,.05,.075,.15]:
  center=oldcenter+offset;alarm=abs(B*STEP-center)>.075+1e-12
  for policy in ['K0','K1','K2','K3']:
   selected=np.array([choose(int(B[k]),center[k],pools[k],policy)[0] if alarm[k] else B[k] for k in range(len(B))]);wrong=B!=ref
   r4.append(dict(case=case,offset_cm=offset*100,policy=policy,n=len(B),alarms=int(alarm.sum()),TP=int((alarm&wrong).sum()),FP=int((alarm&~wrong).sum()),FN=int((~alarm&wrong).sum()),exact_recovery=int((wrong&(selected==ref)).sum()),normal_harm=int((~wrong&(selected!=ref)).sum()),retained=int((alarm&(selected==B)).sum()),range_MAE_cm=float(np.mean(abs(selected-ref))*STEP*100),S_MAE=float(np.mean(abs(S[np.arange(len(B)),selected]-los)))))
 for j,arm in enumerate(ARMS):
  e=tr['x'][:,j,:3]-truth;e[:,2]=wrap(e[:,2]);xy=np.linalg.norm(e[:,:2],axis=1);hd=np.degrees(e[:,2]);cov=tr['P'][:,j,:3,:3]
  nees=np.einsum('ni,ni->n',e,np.linalg.solve(cov,e[...,None])[...,0]);nxy=np.einsum('ni,ni->n',e[:,:2],np.linalg.solve(cov[:,:2,:2],e[:,:2,None])[...,0]);nh=e[:,2]**2/cov[:,2,2]
  sel=tr['selected'][:,j].astype(int);alarm=tr['alarm'][:,j].astype(bool);acc=tr['accepted'][:,j].astype(bool);wrong=B!=ref;harm=~wrong&(sel!=ref)
  rec=dict(case=case,arm=arm,n=len(B),heading_MAE_deg=float(np.mean(abs(hd))),heading_RMSE_deg=float(np.sqrt(np.mean(hd**2))),heading_P95_deg=float(np.quantile(abs(hd),.95)),heading_max_deg=float(max(abs(hd))),XY_RMSE_m=float(np.sqrt(np.mean(xy**2))),XY_P95_m=float(np.quantile(xy,.95)),XY_max_m=float(max(xy)),NEES3_mean=float(nees.mean()),pose95_coverage=float(np.mean(nees<=7.814727903251179)),XY95_coverage=float(np.mean(nxy<=5.991464547107979)),heading95_coverage=float(np.mean(nh<=3.841458820694124)),alarms=int(alarm.sum()),TP=int((alarm&wrong).sum()),FP=int((alarm&~wrong).sum()),FN=int((~alarm&wrong).sum()),selected_exact_recovery=int((wrong&(sel==ref)).sum()),selected_normal_harm=int(harm.sum()),accepted_recovery=int((acc&wrong&(sel==ref)).sum()),accepted_normal_harm=int((acc&harm).sum()),accepted=int(acc.sum()),excluded_by_P=int(alarm.sum()) if arm=='DROP' else 0)
  metrics.append(rec)
  for k in range(len(B)):rows.append(dict(case=case,k=k,time_s=float(on['t'][k]),arm=arm,heading_error_deg=float(hd[k]),XY_error_m=float(xy[k]),NEES3=float(nees[k]),P_center_m=float(tr['center'][k,j]),alarm=bool(alarm[k]),accepted=bool(acc[k]),B=int(B[k]),selected=int(sel[k]),reference=int(ref[k]),selected_normal_harm=bool(harm[k]),x=float(tr['x'][k,j,0]),y=float(tr['x'][k,j,1]),heading_rad=float(tr['x'][k,j,2])))
 return metrics,rows,r4
def main():
 OUT.mkdir(exist_ok=False)
 write('CONTRACT.json',dict(question_id='B-P075-R4-R5-20261107',role='IMPLEMENTER_SELF_CHECK',source_commit='fca24720524068badeab79b78098a244cebc62b5',script_sha256=sha(Path(__file__)),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),arms=ARMS,P_radius_m=.075,native_stencil_sigma=2,R4_offsets_cm=[-15,-7.5,-5,-2.5,0,2.5,5,7.5,15],R4='fixed archived P with additive bias, redetect all 3136 samples, no radius tuning',R5='own main premeasurement prior and covariance each arm; own original W0 shadow gate using arm observation; DROP skips both main and shadow updates on alarm',fixed='initial state/cov, controls, Q, base R, muMB/muBASE and original SourceFFD observer; no refit',truth='evaluation after recursive runs only; 3D pose NEES, no invented gyro bias truth',scope='R4 and R5 only; exposed seed10 B0 Full R2/R4/R5; not real hardware, no generalization',governance={n:sha(Path('C:/Users/Myoungsun Kim/.codex/research-governance')/n) for n in ['COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md']}))
 print('LOAD_MODEL',flush=True);core,online,model,hashes=load_original_model(SRC);write('MODEL_SOURCE_HASHES.json',hashes)
 allmetrics=[];allrows=[];allsens=[];checks={}
 for route in ['R2','R4','R5']:
  case=route+'_B0_Full_10';on=data(case,'online.npz');controls={k:on[k] for k in ['ds','gy','dt']};controls['x0']=on['x0'][:3]
  print('BASELINE_REPLAY',case,flush=True)
  original=online.replay(on,controls,'W0',core,model,SPEC)
  parity={}
  for key in ['h','H','prior','Pprior','Reff','K','mask']:
   a=original[key];b=on['trace_'+key];err=float(np.max(abs(a.astype(float)-b.astype(float))/np.maximum(1,abs(b))))
   parity[key]=err
  checks[case]={'original_parity':parity};write('CHECKS_PROGRESS.json',checks)
  assert max(parity.values())<=1e-10,('ORIGINAL_PARITY_FAIL',case,parity)
  B,S,pools,oldcenter=prepare(case,on)
  # Verify native mapping against all archived centers before own-state recursion.
  mapped=np.concatenate([centers(model,on['prior'][k:k+32],on['Pprior'][k:k+32]) for k in range(0,len(B),32)])
  checks[case]['archived_P_max_error']=float(max(abs(mapped-oldcenter)));assert max(abs(mapped-oldcenter))<1e-10
  tr=replay_six(core,online,model,on,B,S,pools,case)
  # Own B arm independently checked using original unmodified W0 replay.
  bp=dict(on);bp['z']=np.column_stack([B*STEP,S[np.arange(len(B)),B]])
  bcheck=online.replay(bp,controls,'W0',core,model,SPEC)
  for key in ['x','P','prior','Pprior','h','H','K']:
   err=float(np.max(abs(tr[key][:,0]-bcheck[key])/np.maximum(1,abs(bcheck[key]))));checks[case]['B_'+key+'_error']=err;assert err<=1e-10,(case,key,err)
  assert np.array_equal(tr['accepted'][:,0].astype(bool),bcheck['mask'])
  np.savez_compressed(OUT/(route+'_TRACE.npz'),**tr,t=on['t'],pose_id=on['pose_id'],arms=ARMS)
  ev=data(case,'evaluator.npz');metrics,rows,sens=evaluate(case,on,ev,B,S,pools,oldcenter,tr)
  allmetrics+=metrics;allrows+=rows;allsens+=sens
  table('R5_METRICS.csv',allmetrics);table('R5_ROWS.csv',allrows);table('R4_SENSITIVITY.csv',allsens);write('CHECKS_PROGRESS.json',checks)
  print('CASE_DONE',case,json.dumps(metrics),flush=True)
 # R4 zero-offset result must reproduce frozen R2 recovery totals.
 frozen=json.loads((ROOT/'R2_RUN_001/SUMMARY.json').read_text())
 for p in ['K0','K1','K2','K3']:
  rr=[r for r in allsens if r['offset_cm']==0 and r['policy']==p]
  assert sum(r['exact_recovery'] for r in rr)==frozen[p]['TP_exact']
  assert sum(r['normal_harm'] for r in rr)==frozen[p]['FP_harmed']
 write('CHECKS.json',dict(status='PASS_IMPLEMENTER_CHECK',cases=checks,R4_zero_offset_matches_R2=True,finite_covariances=True,independent_audit=False,ended_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),exit_code=0))
 write('SUMMARY.json',dict(R5=allmetrics,R4=allsens))
 write('ARTIFACT_HASHES.json',{p.name:sha(p) for p in OUT.iterdir() if p.is_file()})
 print('COMPLETE_R4_R5',flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:
  if OUT.exists():write('FAILURE.json',dict(error=repr(e),traceback=traceback.format_exc()))
  raise
