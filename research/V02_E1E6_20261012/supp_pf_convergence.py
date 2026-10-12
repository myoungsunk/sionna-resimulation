"""SUPPLEMENT (not part of the frozen run): PF convergence at N=20k vs N=100k on 64 preselected confirmatory seeds (3000-3063), with ESS/resampling logs.
Same RNG streams / code path as run_e1e6.PF (instrumentation only)."""
import sys,time,json,math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import numpy as np,pandas as pd
from multiprocessing import Pool
from scipy.stats import chi2
import run_e1e6 as M
class PFLog(M.PF):
    def _maybe_resample(self):
        w=np.exp(self.lw);ess=1/np.sum(w*w);self.ess_min=min(getattr(self,'ess_min',1e18),ess);self.ess_sum=getattr(self,'ess_sum',0.)+ess;self.ess_n=getattr(self,'ess_n',0)+1
        before=self.x
        super()._maybe_resample()
        if self.x is not before:self.n_res=getattr(self,'n_res',0)+1
def one_log(args):
    n_part,wname,seed=args;cfg=M.R.cfg_();t0=time.time();truth,d,g,o,est0,std=M.world(wname,seed)
    rng=np.random.default_rng([20261012,int(seed),7007]);f=PFLog(cfg,est0,std,n_part,rng,mixture=M.sign_mixture(est0,std) if wname=='HIGH' else None)
    nr=np.random.default_rng([20261011,seed,8002]).normal(0,.08,M.N+1);E=[];Ps=[]
    for k in range(M.N+1):
        if k:f.step(float(d[k]),float(g[k]),float(o[k]),M.DT)
        r=float(np.sqrt((truth[k,0]-4.)**2+truth[k,1]**2+2.2**2))+nr[k];f.range_record(r)
        if k in M.CHECK:
            x,P=f.mean_cov();e=truth[k]-x;e[2]=M.V.wrap(e[2]);E.append(e);Ps.append(P.copy())
    return np.array(E),np.array(Ps),time.time()-t0,dict(ess_min=f.ess_min,ess_mean=f.ess_sum/f.ess_n,n_res=getattr(f,'n_res',0))
if __name__=='__main__':
    seeds=list(range(3000,3064));rows=[];t0=time.time();store={}
    for wname in ('CONS_SMALL','CONS_LARGE','HIGH'):
        for n_part in (20000,100000):
            with Pool(4) as p:res=p.map(one_log,[(n_part,wname,s) for s in seeds],chunksize=1)
            E=np.stack([r[0] for r in res]);P=np.stack([r[1] for r in res]);n=len(E)
            for j,k in enumerate(M.CHECK):
                e=E[:,j,:3];C=P[:,j,:3,:3];nees=np.einsum('ni,ni->n',e,np.linalg.solve(C,e[...,None])[...,0]);lo,hi=chi2.ppf([.025,.975],3*n)/n
                rows.append(dict(world=wname,N=n_part,k=k,n=n,NEES=float(nees.mean()),lo=float(lo),hi=float(hi),cov95=float(np.mean(nees<=chi2.ppf(.95,3))),pos_rmse=float(np.sqrt(np.mean(np.sum(e[:,:2]**2,1)))),pos_P_rms=float(np.sqrt(np.mean(P[:,j,0,0]+P[:,j,1,1]))),
                  ess_min=float(np.min([r[3]['ess_min'] for r in res])),ess_mean=float(np.mean([r[3]['ess_mean'] for r in res])),resamples_mean=float(np.mean([r[3]['n_res'] for r in res])),sec_per_seed=float(np.mean([r[2] for r in res]))))
            store[(wname,n_part)]=E[:,-1,:2]
            j=[r for r in rows if r['world']==wname and r['N']==n_part][-1]
            print(wname,n_part,'NEES48 %.3f cov95 %.3f posRMSE %.4f essmin %.0f resamples %.1f sec/seed %.1f'%(j['NEES'],j['cov95'],j['pos_rmse'],j['ess_min'],j['resamples_mean'],j['sec_per_seed']),'| %.0fs'%(time.time()-t0),flush=True)
            pd.DataFrame(rows).to_csv(Path(__file__).resolve().parent/'RESULTS_PF_SUPP.csv',index=False)
        a,b=store[(wname,20000)],store[(wname,100000)]
        print(wname,'per-seed 48 s error vector difference 20k vs 100k: rms %.4f m (pos rmse %.4f)'%(float(np.sqrt(np.mean(np.sum((a-b)**2,1)))),float(np.sqrt(np.mean(np.sum(b**2,1))))),flush=True)
