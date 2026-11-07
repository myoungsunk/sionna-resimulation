"""Predeclared common-gate comparison, added after ungated B0 exposes confound.
Frozen causal S4 decisions are shared, never selected from truth or FGO error.
This estimates conditional performance of a composite S4-selector/FGO system.
"""
import experiment as e
import numpy as np
import json,time,csv,sys
from pathlib import Path
from scipy.optimize import least_squares
from scipy.linalg import cho_factor,cho_solve
OUT=e.BASE/'matched_gate'

class MatchedWindow(e.Window):
 def __init__(self,*args,mask,**kwargs):super().__init__(*args,**kwargs);self.mask=mask
 def evaluate(self,v):
  r,J,xs,Ds=super().evaluate(v);keep=np.r_[np.ones(self.n,dtype=bool),self.mask[self.ids]]
  return r[keep],J[keep],xs,Ds
 def marginalize_oldest(self,xstar):
  if self.mask[self.ids[0]]:return super().marginalize_oldest(xstar)
  # No old observation: marginalize only prior and first transition.
  delta=self.mu-xstar;delta[2]=e.wrap(delta[2]);P=self.L@self.L.T
  k=self.ids[1];dt=self.ctrl['dt_s'][k];ds=self.ctrl['ds_odom'][k];da=self.ctrl['dtheta_gyro'][k]
  pred,F,G=e.motion(xstar,ds,da,dt);FF=np.zeros_like(P);FF[:4,:4]=F
  Q=np.zeros_like(P);std=e.noise_std(ds,dt);Q[:4,:4]=(G*std)@(G*std).T
  if self.d==5:
   rho=np.exp(-dt/self.tau);pred=np.r_[pred,rho*xstar[4]];FF[4,4]=rho;Q[4,4]=self.sc2*(1-rho*rho)
  mu=pred+FF@delta;mu[2]=e.wrap(mu[2]);PP=FF@P@FF.T+Q
  return mu,(PP+PP.T)/2

def run(ctrl,z,x0,R,sc2,tau,mask):
 mu,P=e.initial(x0,5 if sc2 else 4,sc2);X=[];C=[];di=[];start=0
 for k in range(len(z)):
  if e.os.getenv('MANAGED_PROCESS_STOP_FILE') and Path(e.os.environ['MANAGED_PROCESS_STOP_FILE']).exists():raise RuntimeError('CANCELLED')
  w=MatchedWindow(mu,P,list(range(start,k+1)),ctrl,z,R,sc2,tau,mask=mask)
  xs,cov,info,v=w.solve();X.append(xs[-1]);C.append(cov);di.append(info)
  if k-start==e.LAG:mu,P=w.marginalize_oldest(xs[0]);start+=1
 return np.asarray(X),np.asarray(C),di

def tests():
 from scipy.optimize._numdiff import approx_derivative
 d=e.data('los');ctrl,x0=e.build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],'B0')
 par=json.loads((e.BASE/'PARAMETERS.json').read_text());mu,P=e.initial(x0,5,par['sigma_c2']);mask=np.arange(len(d['t_s']))%3!=0
 w=MatchedWindow(mu,P,list(range(7)),ctrl,d['z_s'],par['R_epsilon'],par['sigma_c2'],par['tau_s'],mask=mask)
 v=np.random.default_rng(44).normal(0,.02,w.n);error=float(np.max(abs(w.evaluate(v)[1]-approx_derivative(lambda v:w.evaluate(v)[0],v))));assert error<2e-5
 # Missing-observation linear KF vs marginalized graph, including colored state.
 ctrl['ds_odom'][:]=0;ctrl['dtheta_gyro'][:]=0;mu,P=e.initial(np.zeros(3),5,par['sigma_c2']);x,C=mu.copy(),P.copy();start=0
 H=np.array([0.,0.,1.,0.]);z=np.linspace(-.02,.02,len(mask));rho=np.exp(-.2/par['tau_s'])
 for k in range(12):
  if k:
   xx,F,G=e.motion(x,0,0,.2);FF=np.zeros((5,5));FF[:4,:4]=F;FF[4,4]=rho;std=e.noise_std(0,.2);Q=np.zeros((5,5));Q[:4,:4]=(G*std)@(G*std).T;Q[4,4]=par['sigma_c2']*(1-rho*rho);x=np.r_[xx,rho*x[4]];C=FF@C@FF.T+Q
  if mask[k]:
   h=np.r_[H,1.];K=C@h/(h@C@h+par['R_epsilon']);x=x+K*(z[k]-h@x);A=np.eye(5)-np.outer(K,h);C=A@C@A.T+par['R_epsilon']*np.outer(K,K)
  ww=MatchedWindow(mu,P,list(range(start,k+1)),ctrl,z,par['R_epsilon'],par['sigma_c2'],par['tau_s'],linear_model=lambda a:(H@a[:4],H),mask=mask)
  xs,cp,_,_=ww.solve()
  if k-start==3:mu,P=ww.marginalize_oldest(xs[0]);start+=1
 err=float(max(np.max(abs(x-xs[-1])),np.max(abs(C-cp))));assert err<1e-8,err
 e.dump('MATCHED_TESTS.json',dict(status='PASS_SELF_CHECK',jacobian_max_abs=error,linear_colored_missing_observation_fixed_lag_error=err))
 print('MATCHED TEST PASS',flush=True)

def main():
 OUT.mkdir(exist_ok=False);par=json.loads((e.BASE/'PARAMETERS.json').read_text());rows=[]
 e.dump('MATCHED_CONTRACT.json',dict(reason='ungated S4 B0 Full degrades; common frozen causal S4 gate isolates structural comparison',parameter_changes=False,lag_changes=False,comparison='S4 causal selector + FGO, not standalone FGO; masks channel and bias specific',source_sha256=e.sha(__file__),parent_sha256=e.sha(e.BASE/'experiment.py')))
 for level in ['B0','L0','L1','L2']:
  for ch in ['los','full']:
   d=e.data(ch);ctrl,x0=e.build_positive_bias_controls(d['t_s'],d['truth_for_offline_scoring_only'],level)
   saved=np.load(e.OLD/f'results/replay/R2_aB_m0_{ch}_{level}_seed0_recursive.npz');j=saved['names'].tolist().index('S4');mask=saved['status'][:,j]=='APPLIED'
   for arm in ['FGO_basic_matched','FGO_corr_matched']:
    before=time.perf_counter();corr='corr' in arm
    X,P,di=run(ctrl,d['z_s'],x0,par['R_epsilon'] if corr else e.RS,par['sigma_c2'] if corr else 0.,par['tau_s'],mask)
    assert np.isfinite(X).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
    np.savez_compressed(OUT/f'{ch}_{level}_{arm}.npz',estimate=X,covariance=P,t_s=d['t_s'],mask=mask)
    e.dump(f'matched_gate/{ch}_{level}_{arm}_solver.json',di)
    row=dict(channel=ch,level=level,method=arm,seconds=time.perf_counter()-before,solver_failures=sum(a['status']<=0 for a in di),max_optimality=max(a['optimality'] for a in di),gate_rejected=int((~mask).sum()),**e.metrics(X,P,d['truth_for_offline_scoring_only'],d['t_s']))
    rows.append(row);e.dump('MATCHED_PROGRESS.json',rows);print(json.dumps(row),flush=True)
 with (e.BASE/'MATCHED_COMPARISON.csv').open('w',newline='',encoding='utf-8-sig') as f:
  wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
 e.dump('MATCHED_RESULT.json',dict(status='EXECUTION_COMPLETED',rows=len(rows),scientific_adoption=False,solver_failures=sum(r['solver_failures'] for r in rows),output_hashes={str(p.relative_to(e.BASE)):e.sha(p) for p in OUT.glob('*')}))

if __name__=='__main__':{'tests':tests,'run':main}[sys.argv[1]]()
