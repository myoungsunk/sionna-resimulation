import sys;sys.path.insert(0,'/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad/decomp')
import numpy as np,pandas as pd
from scipy.stats import chi2
import run as R
base=np.asarray(R.Config().p0_std,float).copy()
variants={'full LARGE':[1,1,1,1,1,1],'xy only large (yaw,cal small)':[1,1,0.0,0,0,0],'yaw only large':[0,0,1,0,0,0],'cal states only large':[0,0,0,1,1,1],
          'xy+yaw large, cal small':[1,1,1,0,0,0],'yaw+cal large, xy small':[0,0,1,1,1,1]}
S=R.SMALL
rows=[]
for name,m in variants.items():
    m=np.array(m,float);std=np.where(m>0,base,S)
    R.prior_std=lambda prior,scale=1.,std=std:std.copy()
    n=0;Es=[];Ps=[]
    for s in range(1000,1256):
        E,P=R.run('CONS_EKF','LARGE',s);Es.append(E);Ps.append(P)
    E=np.stack(Es);P=np.stack(Ps);n=len(E);j=3
    e=E[:,j,:3];C=P[:,j,:3,:3];nees=np.einsum('ni,ni->n',e,np.linalg.solve(C,e[...,None])[...,0]);lo,hi=chi2.ppf([.025,.975],3*n)/n
    rows.append((name,nees.mean(),float(np.mean(nees<=chi2.ppf(.95,3))),lo<=nees.mean()<=hi))
    print('%-34s NEES48=%.2f cov95=%.2f inside=%s'%(rows[-1][0],*rows[-1][1:]),flush=True)
