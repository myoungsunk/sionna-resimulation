"""Explicit execution adapter for the already-published common.py arithmetic.
Scalar and vector source have same real-valued model but recursive roundoff differs.
Original numerical tolerances unchanged; failed scalar run is preserved.
"""
import argparse
from pathlib import Path
import numpy as np
import driver

def observe(self,x):
    h,H,clip=self.raw.observe(np.asarray(x[:4],float))
    return float(h),np.asarray(H,float),bool(clip)

def baseline(self,z,c,x0,P0,gate):
    n=len(z);X=np.empty((n,4));V=np.empty((n,4,4));N=np.full(n,np.nan);A=np.zeros(n,bool)
    x,P=x0.copy(),P0.copy()
    for k in range(n):
        x,P=self.predict(x,P,c,k)
        if gate is not None:
            y,C,d=self.raw.candidate(x,P,float(z[k]));N[k]=d['nis'];A[k]=d['nis']<=gate
            if d['clip']:raise ValueError('LUT out of domain')
            if A[k]:x,P=y,C
        X[k]=x;V[k]=P
    return dict(X=X,P=V,nis=N,accepted=A)

def install():
    driver.Adapter.observe=observe;driver.Adapter.baseline=baseline

if __name__=='__main__':
    install();p=argparse.ArgumentParser();p.add_argument('--phase',required=True);p.add_argument('--data',type=Path,default=Path('.'));p.add_argument('--out',type=Path,required=True);p.add_argument('--case',default='R2_aB_m0');a=p.parse_args();driver.experiment(a.data,a.out,a.phase,a.case)
