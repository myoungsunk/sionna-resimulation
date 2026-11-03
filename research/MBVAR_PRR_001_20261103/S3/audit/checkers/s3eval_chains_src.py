import json,hashlib,subprocess,sys,math,types,importlib.util,time
from pathlib import Path
from copy import deepcopy
import numpy as np
root=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');pkg=root/'research/MBVAR_PRR_001_20261103';s=pkg/'S3';code='e68482d262665fff7d0c43749758a523fbf0f4e4'
def git(*a):return subprocess.check_output(['git','--git-dir='+str(root/'.git'),*a])
def load(p):
 with np.load(p) as z:return dict(z)
for st in ('S1','S2','S3'):
 for p in (pkg/st).glob('*.py'):assert p.read_bytes()==git('show',code+':'+str(p.relative_to(root))),str(p)
rulesraw=(s/'RULES.json').read_bytes();ruleshash=hashlib.sha256(rulesraw).hexdigest()
# Linux runner lacks psutil; exact RSS/HWM telemetry from proc is instrumentation only.
ps=types.ModuleType('psutil')
class Proc:
 def memory_info(self):
  v={a.split(':')[0]:int(a.split()[1])*1024 for a in Path('/proc/self/status').read_text().splitlines() if a.startswith(('VmRSS:','VmHWM:'))}
  return types.SimpleNamespace(rss=v['VmRSS'],peak_wset=v['VmHWM'])
ps.Process=Proc;sys.modules['psutil']=ps
sys.path.insert(0,str(s));import foreground as fg
from history import History,validate_candidate
# Under-test synthetic types have explicit linear observation and unchanged four-state motion.
class Core:
 @staticmethod
 def transition(x,ds,gy,dt):
  y=x.copy();y[0]+=ds;y[2]=(x[2]+gy-x[3]*dt+np.pi)%(2*np.pi)-np.pi;F=np.eye(4);F[2,3]=-dt;G=np.zeros((4,3));G[0,0]=1;G[2,1]=1;G[3,2]=1;return y,F,G
 @staticmethod
 def predict(x,P,ds,gy,dt,Q):
  y,F,G=Core.transition(x,ds,gy,dt);return y,F@P@F.T+G@Q@G.T,F,G
class Model:
 @staticmethod
 def batch(x,spec):
  H=np.array([[1.,.1,0.,0.],[.05,0.,1.,0.]])
  return x@H.T,np.broadcast_to(H,(len(x),2,4)).copy()
def inputs(n=320):
 pk=dict(t=np.arange(n,dtype=float)*.2,z=np.tile([0.,.3],(n,1)),muBASE=np.zeros((n,2)),muMB=np.zeros((n,2)),R=np.tile(np.diag([.1,.1])[None],(n,1,1)),D=np.zeros(n),P0=np.diag([.002,.001,.001,1e-6]),pose_id=np.arange(n))
 ct=dict(x0=np.zeros(3),ds=np.zeros(n),gy=np.zeros(n),dt=np.full(n,.2));return pk,ct
def independent(checkpoint,rows,prevention,first,identity,core,model,spec):
 # Direct equations; no production update/weight/step or cold helper.
 x=np.array(checkpoint['x']);P=np.array(checkpoint['P']);sx=np.array(checkpoint['shadow_x']);sp=np.array(checkpoint['shadow_P']);records=[]
 for k,t,row in rows:
  def pred(a,C):
   if k==0:return a.copy(),C.copy()
   Q=np.diag([2e-5*abs(row['ds']),np.deg2rad(.015)**2*row['dt'],0]);return core.predict(a,C,row['ds'],row['gy'],row['dt'],Q)[:2]
  def upd(a,C,H,v,R,allow):
   S=H@C@H.T+R
   if not allow:return a,C
   K=C@H.T@np.linalg.inv(S);y=a+K@v;y[2]=np.arctan2(np.sin(y[2]),np.cos(y[2]));J=np.eye(4)-K@H;N=J@C@J.T+K@R@K.T;return y,(N+N.T)/2
  sx,sp=pred(sx,sp);h,H=model.batch(sx[None],spec);v=row['z']-h[0]-row['muBASE'];gate=float(v@np.linalg.inv(H[0]@sp@H[0].T+row['R'])@v)<=9.210340371976184;sx,sp=upd(sx,sp,H[0],v,row['R'],gate)
  radius=np.linalg.norm(x[:2]-np.array(spec['anchor'][:2]));sigma=np.interp(radius,[0,1.5,3,6,10],[.011,.020,.050,.120,.240]);xp,pp=pred(x,P);h,H=model.batch(xp[None],spec);h,H=h[0],H[0];w=1.
  if prevention:
   d=min(1.,.2/(abs(row['z'][1]-h[1])+1e-12))**2;u=min(1.,.07138038868537433/(abs(row['D'])+1e-12))**2;w=max(.25,max(.25,d)*max(.25,u))
  if not identity and t>=first:w=min(w,.25)
  R=row['R'].copy();R[1,1]=(R[1,1]+sigma**2)/w;x,P=upd(xp,pp,H,row['z']-h-row['muMB'],R,gate);records.append((k,x.copy(),P.copy(),sx.copy(),sp.copy()))
 return records
checks=0;maxdiff=0;coldpackets=0
def compare_events(pk,ct,arm,tr,ev,retro,core,model,spec,identity=False):
 global checks,maxdiff,coldpackets
 assert len(ev)>0
 for e in ev:
  if e['checkpoint'] is None:continue
  start=e['checkpoint']+1;end=e['index'];rows=[(k,float(pk['t'][k]),fg.frame(pk,ct,k)) for k in range(start,end+1)]
  ref=independent(e['checkpoint_state'],rows,arm=='D_CP',e['first'],identity,core,model,spec);coldpackets+=len(ref)
  if e['disposition']=='ACCEPT':
   actual=next(path for k,path in retro if k==end)
   assert len(actual)==len(ref)
   for a,b in zip(actual,ref):
    assert a[0]==b[0]
    for av,bv in zip(a[1:3],b[1:3]):
     assert np.allclose(av,bv,atol=1e-10,rtol=1e-10);maxdiff=max(maxdiff,float(np.max(abs(av-bv))));checks+=1
   for field,val in [('x',ref[-1][1]),('P',ref[-1][2]),('shadow_x',ref[-1][3]),('shadow_P',ref[-1][4])]:
    assert np.allclose(tr[field][end],val,atol=1e-10,rtol=1e-10);checks+=1
  assert e['historical_indices']==([] if identity else [k for k,t,row in rows if t>=e['first']]);assert e['checkpoint']<next(k for k in range(len(pk['t'])) if pk['t'][k]>=e['first']-1e-8);checks+=1
# Load shared frozen canonical motion/FFD only; all replay-conditioning equations above remain independent.
orig=Path('/mnt/d/SLAM_bot/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/execution_33e9849');base=orig/'p2'
sys.path[:0]=[str(base/'research/FFD_P0P3_20261016'),str(base/'research/EKF4_RANGE_S_STAGED_20261014'),str(base/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src')]
core=types.ModuleType('qa_core');sys.modules['qa_core']=core;exec(compile(git('show','7e2855314de867e0481f8eb5ed1a07c48710f364:research/EKF4_RANGE_S_STAGED_20261014/core.py'),'frozen_core','exec'),core.__dict__)
import source_model
from qclean_uwb.drivesim import pattern_apply as PA
banks=[PA.Bank(load(orig/('LP_'+n+'45_bank.npz'))) for n in ('plus','minus')];model=source_model.SourceFFD(banks=banks)

run=s/'runs/EVAL_001';cache=Path('/mnt/d/codex/MBVAR_PRR_001_20261103_inputs/S1_INPUTS/algorithm_input');ixs=json.loads((run/'TRACE_INDEX.json').read_text());spec=dict(anchor=(10.,0.,2.65),robot_z_m=.45,mount_deg=0.);selected=0;pathschecked=0;retrorecords=0;guarded=0;histmiss=0;packetschecked=0;propmax=0.;ckptchecked=0
def equal(a,b,label):
 global checks,maxdiff
 assert np.allclose(a,b,atol=2e-10,rtol=2e-10),(label,float(np.max(abs(np.asarray(a)-b))))
 maxdiff=max(maxdiff,float(np.max(abs(np.asarray(a)-b))));checks+=1
def one_prior(x,P,k,ct):
 if k==0:return x.copy(),P.copy()
 Q=np.diag([2e-5*abs(ct['ds'][k]),np.deg2rad(.015)**2*ct['dt'][k],0]);return core.predict(x,P,float(ct['ds'][k]),float(ct['gy'][k]),float(ct['dt'][k]),Q)[:2]
for no,ix in enumerate(ixs):
 route,bias,ch,seed,arm=(ix[k] for k in ('route','bias','channel','seed','arm'));key=f'{route}_aB_m0_{bias}_{ch}';variant=ix.get('variant','main');pk=load(cache/(key+'.npz'));ct=load(cache/f'{route}_aB_m0_{bias}_{seed}.npz');tr=load(run/ix['file']);idx=tr['sample_index'];n=len(idx);x=tr['x'];P=tr['P'];initialx=tr['initial_x'] if ix['kind']=='M' else np.r_[ct['x0'],0.];initialP=tr['initial_P'] if ix['kind']=='M' else pk['P0'];ev=json.loads((run/(Path(ix['file']).stem+'_EVENTS.json')).read_text())
 adopted={e['index'] for e in ev if e['disposition']=='ACCEPT'}
 # Vector direct kinematics, independent of production predictor, checks online continuity and absence of P injection.
 prev=np.vstack((initialx,x[:-1]));pc=np.concatenate((initialP[None],P[:-1]));ds=ct['ds'][idx];gy=ct['gy'][idx];dt=ct['dt'][idx];a=gy-prev[:,3]*dt;small=abs(a)<1e-4;c=np.empty(n);dc=np.empty(n);aa=a[small];c[small]=1-aa**2/24+aa**4/1920-aa**6/322560;dc[small]=-aa/12+aa**3/480-aa**5/53760;hh=a[~small]/2;c[~small]=np.sin(hh)/hh;dc[~small]=(hh*np.cos(hh)-np.sin(hh))/(2*hh*hh)
 phi=prev[:,2]+a/2;u=np.column_stack((np.cos(phi),np.sin(phi)));up=np.column_stack((-u[:,1],u[:,0]));d=ds[:,None]*c[:,None]*u;v=ds[:,None]*(dc[:,None]*u+c[:,None]*up/2);xp=prev.copy();xp[:,:2]+=d;xp[:,2]=(prev[:,2]+a+np.pi)%(2*np.pi)-np.pi;F=np.broadcast_to(np.eye(4),(n,4,4)).copy();F[:,:2,2]=np.column_stack((-d[:,1],d[:,0]));F[:,:2,3]=-dt[:,None]*v;F[:,2,3]=-dt;G=np.zeros((n,4,3));G[:,:2,0]=c[:,None]*u;G[:,:2,1]=v;G[:,2,1]=1;G[:,3,2]=1;Q=np.zeros((n,3,3));Q[:,0,0]=2e-5*abs(ds);Q[:,1,1]=np.deg2rad(.015)**2*dt;pp=F@pc@F.swapaxes(1,2)+G@Q@G.swapaxes(1,2);pp=(pp+pp.swapaxes(1,2))/2
 if idx[0]==0:xp[0]=prev[0];pp[0]=pc[0]
 equal(tr['pre_replay_prior'],xp,'original foreground prior');ordinary=~np.isin(idx,list(adopted));equal(tr['prior'][ordinary],xp[ordinary],'ordinary prior');equal(tr['Pprior'][ordinary],pp[ordinary],'ordinary covariance');packetschecked+=n
 retrofile=run/(Path(ix['file']).stem+'_RETROSPECTIVE.npz')
 if adopted:
  rt=load(retrofile);assert len(rt['created_index'])==len(rt['sample_index'])==len(rt['pose_id'])==len(rt['x'])==len(rt['P'])
  assert set(rt['created_index'].tolist())==adopted
 else:assert not retrofile.exists()
 for event in ev:
  k=event['index'];j=int(np.searchsorted(idx,k));first=event['first'];seconds=int(variant.replace('history','')) if ix['kind']=='length' else 60
  assert idx[j]==k and event['end_index']==k and event['current_pose_id']==int(pk['pose_id'][k]);assert first<=pk['t'][k]
  # Check latest valid one-second checkpoint strictly before first causal risky sample.
  firstidx=int(np.flatnonzero(np.isclose(pk['t'],first,atol=1e-8,rtol=0))[0]);candidates=[i for i in [-1,*range(0,k+1,5)] if i<firstidx and (pk['t'][0]-1 if i==-1 else pk['t'][i])>=pk['t'][k]-seconds]
  expectedcp=candidates[-1] if candidates else None
  assert event['checkpoint']==expectedcp,(ix['file'],event['checkpoint'],expectedcp)
  if expectedcp is None:
   assert event['disposition']=='HISTORY_INSUFFICIENT' and event['checkpoint_state'] is None and event['historical_indices']==[] and event['historical_pose_ids']==[];histmiss+=1;continue
  selected+=1;cp=event['checkpoint_state'];assert cp['last_index']==expectedcp and cp['last_pose_id']==(None if expectedcp==-1 else int(pk['pose_id'][expectedcp]));assert event['checkpoint_pose_id']==cp['last_pose_id']
  if expectedcp>=idx[0]:
   cpj=int(np.searchsorted(idx,expectedcp))
   for fld in ('x','P','shadow_x','shadow_P'):equal(cp[fld],tr[fld][cpj],'checkpoint '+fld)
  elif ix['kind']=='M':
   ini=json.loads((run/f'{key}_{variant}_INITIAL.json').read_text());cc=next(z for z in ini['checkpoints'] if z['last_index']==expectedcp)['chain']
   for fld in ('x','P','shadow_x','shadow_P'):equal(cp[fld],cc[fld],'M checkpoint '+fld)
  else:
   equal(cp['x'],initialx,'initial checkpoint x');equal(cp['P'],initialP,'initial checkpoint P')
  ckptchecked+=1;rows=[(i,float(pk['t'][i]),fg.frame(pk,ct,i)) for i in range(expectedcp+1,k+1)];ref=independent(cp,rows,arm=='D_CP',first,bool(event['identity']),core,model,spec);coldpackets+=len(ref)
  changed=[] if event['identity'] else [i for i,t,row in rows if t>=first]
  assert event['historical_indices']==changed and event['historical_pose_ids']==pk['pose_id'][changed].tolist() and len(set(event['historical_pose_ids']))==len(changed)
  assert event['end_pose_id']==int(pk['pose_id'][k])
  # Fixed technical adoption bounds against original current foreground, without GT or NIS selection.
  originalxp,originalpp=xp[j],pp[j];h,H=model.batch(originalxp[None],spec);h,H=h[0],H[0];radius=np.linalg.norm(prev[j,:2]-[10.,0.]);sig=np.interp(radius,[0,1.5,3,6,10],[.011,.020,.050,.120,.240]);w=1.
  if arm=='D_CP':
   wd=max(.25,min(1.,.2/(abs(pk['z'][k,1]-h[1])+1e-12))**2);ws=max(.25,min(1.,.07138038868537433/(abs(pk['D'][k])+1e-12))**2);w=max(.25,wd*ws)
  R=pk['R'][k].copy();R[1,1]=(R[1,1]+sig**2)/w;v=pk['z'][k]-h-pk['muMB'][k];oldcurrent=originalxp.copy()
  if tr['mask'][j]:oldcurrent+=originalpp@H.T@np.linalg.solve(H@originalpp@H.T+R,v);oldcurrent[2]=(oldcurrent[2]+np.pi)%(2*np.pi)-np.pi
  candidate=ref[-1][1];cov=ref[-1][2];delta=candidate-oldcurrent;delta[2]=np.arctan2(np.sin(delta[2]),np.cos(delta[2]));valid=np.isfinite(candidate).all() and np.isfinite(cov).all() and np.linalg.norm(delta[:2])<=.5 and abs(delta[2])<=np.deg2rad(10) and abs(delta[3])<=np.deg2rad(.1)
  assert event['disposition']==('ACCEPT' if valid else 'CANDIDATE_OUT_OF_BOUNDS'),(ix['file'],event['disposition'],delta)
  guarded+=1
  if not valid:equal(tr['x'][j],oldcurrent,'guard rejection keeps foreground');continue
  sel=rt['created_index']==k;pathidx=rt['sample_index'][sel];assert np.array_equal(pathidx,np.arange(expectedcp+1,k+1));assert np.array_equal(rt['pose_id'][sel],pk['pose_id'][pathidx]);assert np.all(pathidx<=k)
  equal(rt['x'][sel],np.array([a[1] for a in ref]),'independent retrospective x');equal(rt['P'][sel],np.array([a[2] for a in ref]),'independent retrospective P');retrorecords+=len(ref);pathschecked+=1
  for fld,val in [('x',ref[-1][1]),('P',ref[-1][2]),('shadow_x',ref[-1][3]),('shadow_P',ref[-1][4])]:equal(tr[fld][j],val,'atomic replacement '+fld)
  # Current measurement model and covariance are recomputed at the replayed candidate's current prior.
  bx=ref[-2][1] if len(ref)>1 else np.array(cp['x']);bP=ref[-2][2] if len(ref)>1 else np.array(cp['P']);px,pP=one_prior(bx,bP,k,ct);ph,pH=model.batch(px[None],spec)
  equal(tr['prior'][j],px,'candidate prior');equal(tr['Pprior'][j],pP,'candidate prior P');equal(tr['h'][j],ph[0],'candidate model h');equal(tr['H'][j],pH[0],'candidate H')
 if (no+1)%80==0:print('CHAIN_VERIFIED',no+1,'cold_packets',coldpackets,flush=True)
print(json.dumps(dict(status='PASS',packet_propagations=packetschecked,selected_candidates=selected,complete_cold_paths=pathschecked,cold_packet_records=coldpackets,retrospective_records=retrorecords,history_insufficient_retained=histmiss,technical_guards_checked=guarded,checkpoint_states_checked=ckptchecked,checks=checks,max_abs_difference=maxdiff,immutable_emitted_paths=True,no_P_injection=True,scientific_outcome_reruns=0)),flush=True)
