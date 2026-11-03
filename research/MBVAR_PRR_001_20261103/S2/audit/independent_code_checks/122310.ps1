@'
from pathlib import Path
import importlib.util,math,json,hashlib,subprocess
import numpy as np
repo=Path('/mnt/d/codex/MBVAR_PRR_001_20261103');base=repo/'research/MBVAR_PRR_001_20261103';stage=base/'S2';code='4eeb7f539ea40fbbc4a4d5eb477d788f2d230945'
def load(name,path):
 sp=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
rc=load('independent_s2_target',stage/'recovery.py');online=load('audited_s1_online',base/'S1/online.py')
def git(*args):return subprocess.check_output(['git','-c','safe.directory='+str(repo),'-C',str(repo),*args])
for d in ['S1','S2']:
 for p in (base/d).glob('*.py'):assert p.read_bytes()==git('show',code+':'+p.relative_to(repo).as_posix()),str(p)
rng=np.random.default_rng(91372);n=0;mutation_kills=[];maxdiff=0.
def close(a,b):
 global maxdiff
 assert np.allclose(a,b,atol=1e-12,rtol=1e-10),(a,b)
 maxdiff=max(maxdiff,float(np.max(abs(np.asarray(a)-b))))
# Direct independent axis/rank-one floor reference, including correlated and already-broad priors.
for near in [False,True]:
 for axes in ['heading','tangent_heading','tangent_heading_bg']:
  for k in range(12):
   D=np.diag([.02,.03,np.deg2rad(.3),np.deg2rad(.02)]);M=rng.normal(size=(4,4));P=D@(M@M.T+np.eye(4))@D
   if k==11:P*=1e4
   x=np.array([.1,.1,.3,.004]) if near else np.array([1.7,-.4,.3,.004]);anchor=np.zeros(3);expected=np.zeros((4,4));rho=np.hypot(*x[:2])
   if axes!='heading':
    if rho<.25:expected[:2,:2]=np.eye(2)*max(0,.01-min(np.linalg.eigvalsh(P[:2,:2])))
    else:
     u=np.array([-x[1],x[0],0,0])/rho;expected+=max(0,.01-u.dot(P).dot(u))*u[:,None]*u[None,:]
   expected[2,2]=max(0,(np.pi/180)**2-P[2,2])
   if axes.endswith('_bg'):expected[3,3]=max(0,(np.pi/3600)**2-P[3,3])
   y,C,delta,fallback=rc.inject(x,P,anchor,axes);assert np.array_equal(y,x);close(delta,expected);close(C,P+expected);assert min(np.linalg.eigvalsh(delta))>=-1e-15;assert fallback==(near and axes!='heading');n+=1
   # The tangent update may change XY off-diagonal covariance; unrelated cross terms must remain.
   close(C[:2,2:],P[:2,2:]);assert C[2,3]==P[2,3]
   if axes!='tangent_heading_bg':assert C[3,3]==P[3,3]
# Mutation counterexamples against the independent formula checks.
x=np.array([2.,1.,.3,.004]);P=np.diag([1e-4,2e-4,1e-6,1e-8]);_,C,d,_=rc.inject(x,P,[0,0])
u=np.r_[-x[1],x[0],0,0]/np.linalg.norm(x[:2]);rad=np.r_[x[:2],0,0]/np.linalg.norm(x[:2]);mut=max(0,.01-rad@P@rad)*np.outer(rad,rad);mut[2,2]=d[2,2]
assert not np.allclose(mut,d,atol=1e-12);mutation_kills.append('radial_instead_of_tangent')
mut=d.copy();mut[2,2]=max(0,math.radians(1)-P[2,2]);assert not np.allclose(mut,d);mutation_kills.append('degrees_or_unsquared_angle')
P=np.eye(4);_,C,d,_=rc.inject(x,P,[0,0]);assert np.array_equal(P,C);assert np.any(abs(np.diag([.01,.01,math.radians(1)**2,math.radians(.05)**2])-P)>0);mutation_kills.append('replace_or_shrink_covariance')
P=np.eye(4)*.001;P[0,2]=P[2,0]=1e-4;_,C,_,_=rc.inject(x,P,[0,0]);assert C[0,2]==P[0,2] and np.diag(np.diag(C))[0,2]!=C[0,2];mutation_kills.append('diagonalize_existing_P')
# Independent motion transport via forward products and inverse once, with noncommuting F matrices.
for k in range(20):
 geom=rc.Geometry();history=[]
 for j in range(6):
  F=np.eye(4)+rng.normal(0,.02,(4,4));H=rng.normal(size=(2,4));R=np.diag(rng.uniform(.1,2,2));accepted=j!=2
  geom.add(j*.2,H,R,F,accepted);history.append((H,R,F,accepted))
 I=np.zeros((4,4));bad=np.zeros((4,4))
 for j,(H,R,F,a) in enumerate(history):
  if not a:continue
  product=np.eye(4)
  for h in range(j+1,len(history)):product=history[h][2]@product
  B=np.linalg.inv(product);I+=B.T@H.T@np.linalg.inv(R)@H@B;bad+=H.T@np.linalg.inv(R)@H
 G=rc.SCALES[:,None]*I*rc.SCALES[None,:];ok,conditional,marginal,actual=geom.information();close(actual,G)
 S=G[:3,:3]-np.outer(G[:3,3],G[:3,3])/G[3,3];close(marginal,np.linalg.eigvalsh(S)[0]);assert ok==(marginal>=1e-6);assert not np.allclose(G,rc.SCALES[:,None]*bad*rc.SCALES[None,:],atol=1e-12);n+=1
mutation_kills.append('omit_or_wrong_transition_transport')
g=rc.Geometry();H=np.array([[1,0,0,0],[0,1,0,0],[0,0,1,1]],float);g.add(0,H,np.eye(3),np.eye(4),True);ok,conditional,marginal,G=g.information();assert conditional>1e-6 and abs(marginal)<1e-15 and not ok;mutation_kills.append('conditional_pose_information_as_marginal');n+=1
g=rc.Geometry();H=np.c_[np.eye(3),np.zeros(3)];g.add(0,H,np.eye(3),np.eye(4),True);assert g.information()[0];n+=1
g.add(2.2,np.zeros((2,4)),np.eye(2),np.eye(4),False);assert len(g.history)==1 and not g.information()[0];n+=1
# Threshold, one-shot, quiet reset, range, geometry, expiry, cooldown, max count.
def latched():
 m=rc.RecoveryMachine()
 for t in [0,.2,.4]:assert not m.observe(t,True,.25,1.,True)[0]
 return m
m=latched()
for t in [.6,.8,1.,1.2,1.4]:assert not m.observe(t,True,1.,1.,True)[0]
assert m.observe(1.6,True,1.,1.,True)[0];m.commit(1.6)
for t in np.arange(1.8,3.81,.2):assert not m.observe(float(t),True,1.,1.,True)[0]
assert m.first is None and m.status=='MONITORING' and m.count==1;n+=1
for why,change in [('geometry',dict(geometry_ok=False)),('range',dict(rho=1.500001)),('quiet',dict(w=.5)),('rejected',dict(accepted=False))]:
 m=latched();kw=dict(accepted=True,w=1.,rho=1.,geometry_ok=True);m.observe(.6,**kw);kw.update(change);assert not m.observe(2.,**kw)[0];n+=1
mutation_kills+=['bypass_geometry_guard','bypass_range_guard','bypass_quiet_or_acceptance']
m=latched();m.observe(.6,True,1,1,True);m.observe(.8,False,1,1,True);assert not m.observe(1.6,True,1,1,True)[0];n+=1
m=latched();assert not m.observe(61,True,1,1,True)[0] and m.status=='HISTORY_EXPIRED_REMAIN_SUSPECT';n+=1
m=latched();m.last=0.;m.observe(.6,True,1,1,True);assert not m.observe(19.999,True,1,1,True)[0];assert m.observe(20.,True,1,1,True)[0];n+=1
m=latched();m.count=3;m.observe(.6,True,1,1,True);assert not m.observe(2.,True,1,1,True)[0] and m.status=='MAX_RECOVERY';n+=1
mutation_kills+=['multiple_injections_same_episode','ignore_cooldown','ignore_max_three','ignore_latch_expiry']
# Fully synthetic model: forced common schedule isolates P-only, zero innovation and F/O gate resurrection.
class Core:
 @staticmethod
 def transition(x,*args):return x.copy(),np.eye(4),np.zeros((4,3))
 @staticmethod
 def predict(x,P,*args):return x.copy(),P.copy(),np.eye(4),np.zeros((4,3))
class Model:
 @staticmethod
 def batch(x,spec):
  H=np.array([[0,1,0,0],[0,0,1,0]],float);return x@H.T,np.broadcast_to(H,(len(x),2,4)).copy()
pk=dict(t=np.array([0.]),z=np.zeros((1,2)),muBASE=np.zeros((1,2)),muMB=np.zeros((1,2)),R=np.eye(2)[None]*1e-4,P0=np.eye(4)*1e-6,D=np.zeros(1));ct=dict(x0=np.zeros(3),ds=np.zeros(1),gy=np.zeros(1),dt=np.ones(1)*.2);spec=dict(anchor=(1.,0.,0.));schedule=np.ones(1,bool)
a,_=rc.replay(pk,ct,'C_P',Core,Model,spec,online,schedule=schedule);assert a['injected'][0] and np.array_equal(a['x'][0],np.zeros(4));n+=1
pk['z'][0,0]=.2;f,_=rc.replay(pk,ct,'C_P',Core,Model,spec,online,schedule=schedule);o,_=rc.replay(pk,ct,'C_P',Core,Model,spec,online,schedule=schedule,gate_mode='O');assert not f['mask'][0] and not o['preinjection_mask'][0] and o['mask'][0];assert np.array_equal(f['x'][0],np.zeros(4));assert abs(o['x'][0,1])>.1;n+=1
mutation_kills+=['P_injection_moves_mean_without_measurement','F_gate_recomputed_after_injection']
# All four snapshot arms begin from identical nonzero-bias initial state and covariance.
initial=(np.array([.01,.02,.03,.004]),np.eye(4)*1e-6);pk['z'][0]=[.02,.03]
for arm in ['A','B','C_P','D_P']:
 a,_=rc.replay(pk,ct,arm,Core,Model,spec,online,initial=initial,schedule=schedule);assert a['prior'][0,3]==initial[0][3];close(a['Pbefore_injection'][0],initial[1]);assert a['delta_P'][0,3,3]==0;n+=1
mutation_kills.append('reset_bg_or_inflate_bg_in_primary')
print(json.dumps(dict(status='PASS',synthetic_cases=n,independent_math_max_abs_difference=maxdiff,mutation_counterexamples_killed=mutation_kills,code_commit=code,rules_sha256=hashlib.sha256((stage/'IMPLEMENTATION_RULES.json').read_bytes()).hexdigest())))
'@ | wsl -d Ubuntu-24.04 env PYTHONDONTWRITEBYTECODE=1 PYTHONHOME=/home/myoung-sun/.local/share/prr31117 LD_LIBRARY_PATH=/home/myoung-sun/.local/share/prr31117/lib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/myoung-sun/.local/share/prr31117/bin/python3 -