"""Exploratory causal fixed-lag factor graph; frozen S4 motion/LUT reused.

The graph is parameterized by its boundary state and standardized driving
noises. This exactly eliminates deterministic motion constraints and constant
gyro bias, without adding artificial process noise. Old information is removed
only through the oldest prior, observation and transition (never the entire
window posterior). Covariances marginalize all nuisance variables.
"""
import os
os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import sys, json, time, math, hashlib, csv, platform
from pathlib import Path
import numpy as np
from scipy.optimize import least_squares
from scipy.linalg import cho_factor, cho_solve
BASE=Path(__file__).resolve().parent
REPO=BASE/'frozen/repo'
sys.path.insert(0,str(REPO/'research/EKF4_RANGE_S_STAGED_20261014'))
from r2_bias_replay import build_positive_bias_controls, predict_one, filter_one, INITIAL_POSE_STD, BIAS_PRIOR_STD
from core import transition, wrap, gaussian_update
from p3_rf_adapter4 import FrozenLut, RS
OLD=Path(r'C:\Users\Myoungsun Kim\Obsidian Vault\03_Research\EKF\2026-11-02 Anchor B 8-arm 실행 준비\run_v1_20261102')
CASE=next(c for c in json.loads((REPO/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text())['cases'] if c['id']=='R2_aB_m0')
LUT=FrozenLut(REPO)
LAG=10 # ten intervals = 2 seconds at the frozen 5-Hz rate

def dump(name,obj):
 (BASE/name).write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def data(ch):
 with np.load(OLD/f'verified_inputs/R2_aB_m0_{ch}_seed0_ONE_STEP.npz') as d:return {k:d[k].copy() for k in d.files}
def motion(x,ds,da,dt):
 y,F,G=transition(x[:4],ds,da,dt)
 return y,F,G[:,:2]
def noise_std(ds,dt):return np.sqrt([2e-5*abs(ds),math.radians(.015)**2*dt])

class Window:
 def __init__(self,mu,P,indices,controls,z,R,sc2=0.,tau=1.,linear_model=None):
  self.mu=mu; self.L=np.linalg.cholesky(P); self.ids=indices; self.ctrl=controls; self.z=z
  self.R=R; self.sc2=sc2; self.tau=tau; self.d=len(mu); self.nd=3 if self.d==5 else 2
  self.n=self.d+self.nd*(len(indices)-1); self.linear_model=linear_model
 def model(self,x):
  if self.linear_model is not None:return self.linear_model(x)
  h,H=LUT.model(x[:4],CASE); return h[1],H[1]
 def decode(self,v):
  x=self.mu+self.L@v[:self.d]; D=np.zeros((self.d,self.n));D[:,:self.d]=self.L
  states=[x]; deriv=[D]
  for j,k in enumerate(self.ids[1:]):
   at=self.d+j*self.nd;dt=self.ctrl['dt_s'][k];ds=self.ctrl['ds_odom'][k];da=self.ctrl['dtheta_gyro'][k]
   std=noise_std(ds,dt); yy,F,G=motion(x,ds+std[0]*v[at],da+std[1]*v[at+1],dt)
   DD=np.zeros_like(D);DD[:4]=F@D[:4];DD[:4,at:at+2]+=G*std
   if self.d==5:
    rho=np.exp(-dt/self.tau);sw=np.sqrt(self.sc2*(1-rho*rho))
    yy=np.r_[yy,rho*x[4]+sw*v[at+2]];DD[4]=rho*D[4];DD[4,at+2]+=sw
   x,D=yy,DD;states.append(x);deriv.append(D)
  return np.asarray(states),np.asarray(deriv)
 def evaluate(self,v):
  xs,Ds=self.decode(v);r=np.empty(self.n+len(xs));r[:self.n]=v
  J=np.zeros((len(r),self.n));J[:self.n]=np.eye(self.n)
  for j,(x,D,k) in enumerate(zip(xs,Ds,self.ids)):
   h,H=self.model(x);hh=np.zeros(self.d);hh[:4]=H
   if self.d==5:h+=x[4];hh[4]=1
   r[self.n+j]=(h-self.z[k])/np.sqrt(self.R);J[self.n+j]=hh@D/np.sqrt(self.R)
  return r,J,xs,Ds
 def solve(self):
  cache={}
  def ev(v):
   if 'v' not in cache or not np.array_equal(v,cache['v']):cache.update(v=v.copy(),out=self.evaluate(v))
   return cache['out']
  sol=least_squares(lambda v:ev(v)[0],np.zeros(self.n),jac=lambda v:ev(v)[1],method='lm',
                    ftol=1e-9,xtol=1e-9,gtol=1e-7,max_nfev=60)
  r,J,xs,Ds=ev(sol.x);cf=cho_factor(J.T@J)
  cov=Ds[-1]@cho_solve(cf,Ds[-1].T);cov=(cov+cov.T)/2
  return xs,cov,{'status':int(sol.status),'nfev':int(sol.nfev),'optimality':float(sol.optimality),'cost':float(sol.cost)},sol.x
 def marginalize_oldest(self,xstar):
  # Marginalize ONLY the old prior+old observation+first transition.
  # Linearize these factors at the optimized old state, keeping the prior fixed.
  h,H=self.model(xstar);hh=np.zeros(self.d);hh[:4]=H
  if self.d==5:h+=xstar[4];hh[4]=1
  delta=self.mu-xstar;delta[2]=wrap(delta[2])
  S=float(hh@(self.L@self.L.T)@hh+self.R);P=self.L@self.L.T;K=P@hh/S
  mdelta=delta+K*(self.z[self.ids[0]]-h-hh@delta)
  A=np.eye(self.d)-np.outer(K,hh);C=A@P@A.T+self.R*np.outer(K,K)
  k=self.ids[1];dt=self.ctrl['dt_s'][k];ds=self.ctrl['ds_odom'][k];da=self.ctrl['dtheta_gyro'][k]
  pred,F,G=motion(xstar,ds,da,dt);FF=np.zeros((self.d,self.d));FF[:4,:4]=F
  Q=np.zeros_like(P);std=noise_std(ds,dt);Q[:4,:4]=(G*std)@(G*std).T
  if self.d==5:
   rho=np.exp(-dt/self.tau);pred=np.r_[pred,rho*xstar[4]];FF[4,4]=rho;Q[4,4]=self.sc2*(1-rho*rho)
  mu=pred+FF@mdelta;mu[2]=wrap(mu[2]);PP=FF@C@FF.T+Q
  return mu,(PP+PP.T)/2

def initial(x0,d,sc2=0.):
 mu=np.r_[x0,0.];P=np.diag(np.r_[INITIAL_POSE_STD**2,BIAS_PRIOR_STD**2])
 if d==5:mu=np.r_[mu,0.];PP=np.zeros((5,5));PP[:4,:4]=P;PP[4,4]=sc2;P=PP
 return mu,P
def run_fgo(ctrl,z,x0,R,sc2=0.,tau=1.):
 d=5 if sc2>0 else 4;mu,P=initial(x0,d,sc2);n=len(z);X=np.zeros((n,d));C=np.zeros((n,d,d));diag=[];start=0
 for k in range(n):
  if os.getenv('MANAGED_PROCESS_STOP_FILE') and Path(os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise RuntimeError('CANCELLED')
  w=Window(mu,P,list(range(start,k+1)),ctrl,z,R,sc2,tau)
  xs,cov,info,v=w.solve();X[k]=xs[-1];C[k]=cov;diag.append(info)
  if k-start==LAG:mu,P=w.marginalize_oldest(xs[0]);start+=1
 return X,C,diag
def run_ekf(ctrl,z,x0,gate=True):
 x,P=initial(x0,4);X=[];C=[];statuses=[]
 for k in range(len(z)):
  if k:x,P=predict_one(x,P,ctrl['ds_odom'][k],ctrl['dtheta_gyro'][k],ctrl['dt_s'][k])
  if gate:x,P,status,_=filter_one(x,P,np.array([0.,z[k]]),'S4',CASE,LUT)
  else:
   x,P,di=gaussian_update(x,P,np.array([z[k]]),lambda q:(LUT.model(q,CASE)[0][1:],LUT.model(q,CASE)[1][1:]),np.array([[RS]]));status='APPLIED'
  X.append(x.copy());C.append(P.copy());statuses.append(status)
 return np.asarray(X),np.asarray(C),np.asarray(statuses)
def metrics(X,P,truth,t):
 m=t>=30;e=X[m,:3]-truth[m];e[:,2]=wrap(e[:,2]);p=P[m,:3,:3]
 hn=e[:,2]**2/p[:,2,2];pn=np.einsum('ni,ni->n',e,np.linalg.solve(p,e[...,None])[...,0])
 return dict(n=int(m.sum()),heading_rmse_deg=float(np.rad2deg(np.sqrt(np.mean(e[:,2]**2)))),xy_rmse_m=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,axis=1)))),heading_sigma_rms_deg=float(np.rad2deg(np.sqrt(np.mean(p[:,2,2])))),xy_sigma_rms_m=float(np.sqrt(np.mean(p[:,0,0]+p[:,1,1]))),heading_nees=float(hn.mean()),pose_nees=float(pn.mean()),heading_coverage95=float(np.mean(hn<=3.841458820694124)),pose_coverage95=float(np.mean(pn<=7.814727903251179)),min_cov_eigenvalue=float(np.linalg.eigvalsh(P[m]).min()))

def prepare():
 d=data('full');m=d['t_s']<30;err=np.array([z-LUT.model(x,CASE)[0][1] for z,x in zip(d['z_s'][m],d['truth_for_offline_scoring_only'][m])]);v=err-err.mean()
 g0=float(v@v/len(v));g1=float(v[1:]@v[:-1]/(len(v)-1));g2=float(v[2:]@v[:-2]/(len(v)-2))
 rho=float(np.clip(g2/g1 if g1>0 else .05,.05,.98));total=max(RS,g0);sc2=float(np.clip(g1/rho,.01*total,.95*total));tau=float(-np.median(np.diff(d['t_s']))/np.log(rho))
 params=dict(R_epsilon=total-sc2,sigma_c2=sc2,tau_s=tau,total_variance=total,rho_at_02s=rho,train_n=int(m.sum()),train_mean=float(err.mean()),gamma0=g0,gamma1=g1,gamma2=g2,fit='centered lag1/lag2 method of moments; rho [.05,.98], sigma_c2 [.01,.95]*total; total=max(original_RS,gamma0); no evaluation tuning')
 dump('PARAMETERS.json',params)
 files=[OLD/'AnchorB_8arm_Run_v1.zip',BASE/'experiment.py']+list((OLD/'verified_inputs').glob('*.npz'))+list((OLD/'results/replay').glob('*recursive.npz'))+list(REPO.rglob('*.py'))+list(REPO.rglob('*.npy'))
 dump('INPUT_HASHES.json',{str(p):sha(p) for p in files})
 dump('CONTRACT.json',dict(question_id='POL-FGO-CORR-001',stage='exploratory implementation',case=CASE,lag_intervals=LAG,lag_s=2.,train='Full t<30 only, offline truth used solely for noise identification and original control generation',score='both channels t>=30,829 samples; no independent environment holdout',parameters=params,arms=['S4_original','S4_no_gate','FGO_basic','FGO_iid','FGO_corr'],gates='original S4 unchanged; all new arms and S4_no_gate admit all observations',accuracy_tolerance='exploratory candidate: <=10% degradation on BOTH RMSE metrics in every Full bias condition; not scientific acceptance',consistency='coverage closer to .95 and mean NEES closer to dimension; no independent-sample chi-square aggregate test',timing='report, no hardware budget specified',source_revision='archive snapshot; no local Git revision claimed',python=sys.version,numpy=np.__version__,scipy=__import__('scipy').__version__,governance={n:sha(Path(r'C:\Users\Myoungsun Kim\.codex\research-governance')/n) for n in ['COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md','ROLE_PROPOSER.md']},created_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()))
 print(json.dumps(params),flush=True)

def tests():
 from scipy.optimize._numdiff import approx_derivative
 d=data('los');ctrl,x0=build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],'B0');par=json.loads((BASE/'PARAMETERS.json').read_text());mu,P=initial(x0,5,par['sigma_c2'])
 w=Window(mu,P,list(range(8)),ctrl,d['z_s'],par['R_epsilon'],par['sigma_c2'],par['tau_s'])
 v=np.random.default_rng(42).normal(0,.01,w.n);an=w.evaluate(v)[1];num=approx_derivative(lambda a:w.evaluate(a)[0],v,method='3-point');je=float(np.max(abs(an-num)));assert je<2e-5,je
 # Zero-motion linear observation special case: graph vs direct Gaussian conditioning.
 cc={k:a.copy() for k,a in ctrl.items()};cc['ds_odom'][:]=0;cc['dtheta_gyro'][:]=0
 mu,P=initial(np.zeros(3),4);H=np.array([.2,-.1,1.,0.]);z=np.linspace(-.01,.01,8)
 wl=Window(mu,P,list(range(8)),cc,z,RS,linear_model=lambda x:(H@x[:4],H));xs,cov,info,_=wl.solve()
 xx,pp=mu.copy(),P.copy()
 for k in range(8):
  if k:xx,pp=predict_one(xx,pp,0,0,cc['dt_s'][k])
  xx,pp,_=gaussian_update(xx,pp,np.array([z[k]]),lambda x:(np.array([H@x]),H[None,:]),np.array([[RS]]))
 dx=float(np.max(abs(xx-xs[-1])));dp=float(np.max(abs(pp-cov)));assert max(dx,dp)<1e-8,(dx,dp)
 # Colored nuisance elimination equals dense correlated observation covariance.
 rng=np.random.default_rng(3);A=rng.normal(size=(9,3));prior=np.diag([.2,.3,.4]);rho=.8;sc=.04;re=.01
 K=sc*rho**np.abs(np.arange(9)[:,None]-np.arange(9)[None,:]);V=K+re*np.eye(9)
 expected=np.linalg.inv(np.linalg.inv(prior)+A.T@np.linalg.solve(V,A))
 Iqq=np.linalg.inv(prior)+A.T@A/re;Iqc=A.T/re;Icc=np.linalg.inv(K)+np.eye(9)/re
 actual=np.linalg.inv(Iqq-Iqc@np.linalg.solve(Icc,Iqc.T));se=float(np.max(abs(expected-actual)));assert se<1e-12,se
 # Fixed-lag marginalization must not double count measurements (linear case).
 prior_mu,prior_P=mu.copy(),P.copy();start=0;last=None
 for k in range(8):
  ww=Window(prior_mu,prior_P,list(range(start,k+1)),cc,z,RS,linear_model=lambda x:(H@x[:4],H));ss,cp,_,_=ww.solve();last=(ss[-1],cp)
  if k-start==2:prior_mu,prior_P=ww.marginalize_oldest(ss[0]);start+=1
 md=float(max(np.max(abs(last[0]-xx)),np.max(abs(last[1]-pp))));assert md<1e-8,md
 dump('TESTS.json',dict(status='PASS_SELF_CHECK',jacobian_max_abs=je,linear_mean_max_abs=dx,linear_cov_max_abs=dp,colored_schur_max_abs=se,linear_fixed_lag_max_abs=md))
 print('TESTS PASS',flush=True)

def main():
 par=json.loads((BASE/'PARAMETERS.json').read_text());rows=[];parity=[];out=BASE/'outputs';out.mkdir(exist_ok=False)
 for level in ['B0','L0','L1','L2']:
  for ch in ['los','full']:
   d=data(ch);ctrl,x0=build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],level)
   np.savez_compressed(out/f'controls_{ch}_{level}.npz',**ctrl,initial_pose=x0)
   saved=np.load(OLD/f'results/replay/R2_aB_m0_{ch}_{level}_seed0_recursive.npz');j=saved['names'].tolist().index('S4')
   for arm in ['S4_original','S4_no_gate','FGO_basic','FGO_iid','FGO_corr']:
    before=time.perf_counter()
    if arm.startswith('S4'):
     X,P,st=run_ekf(ctrl,d['z_s'],x0,arm=='S4_original');di=[]
     if arm=='S4_original':
      delta=X-saved['estimate'][:,j];delta[:,2]=wrap(delta[:,2]);px=float(np.max(abs(delta)));pc=float(np.max(abs(P-saved['covariance'][:,j])));sm=int(np.sum(st!=saved['status'][:,j]));assert max(px,pc)<1e-7 and sm==0,(px,pc,sm)
      parity.append(dict(channel=ch,level=level,state_max_abs=px,cov_max_abs=pc,mask_mismatch=sm));dump('PARITY.json',parity)
    else:
     R=RS if arm=='FGO_basic' else par['total_variance'] if arm=='FGO_iid' else par['R_epsilon']
     X,P,di=run_fgo(ctrl,d['z_s'],x0,R,par['sigma_c2'] if arm=='FGO_corr' else 0.,par['tau_s'])
    elapsed=time.perf_counter()-before
    assert np.isfinite(X).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
    np.savez_compressed(out/f'{ch}_{level}_{arm}.npz',estimate=X,covariance=P,t_s=d['t_s'])
    if di:dump(f'outputs/{ch}_{level}_{arm}_solver.json',di)
    row=dict(channel=ch,level=level,method=arm,seconds=elapsed,solver_failures=sum(v['status']<=0 for v in di),max_optimality=max([v['optimality'] for v in di],default=0),**metrics(X,P,d['truth_for_offline_scoring_only'],d['t_s']))
    rows.append(row);dump('PROGRESS.json',rows)
    print(json.dumps(row),flush=True)
 with (BASE/'COMPARISON.csv').open('w',newline='',encoding='utf-8-sig') as f:
  wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
 original=json.loads((BASE/'INPUT_HASHES.json').read_text());unchanged=all(sha(p)==h for p,h in original.items());assert unchanged
 dump('RESULT.json',dict(status='EXECUTION_COMPLETED',rows=len(rows),input_source_hashes_unchanged=unchanged,scientific_adoption=False,self_check_only=True,solver_failures=sum(r['solver_failures'] for r in rows),output_hashes={str(p.relative_to(BASE)):sha(p) for p in out.glob('*')}))

if __name__=='__main__':
 {'prepare':prepare,'tests':tests,'run':main}[sys.argv[1]]()
