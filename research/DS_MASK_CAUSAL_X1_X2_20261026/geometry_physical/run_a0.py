from common import *
import traceback
def main():
 freeze();old,new=models();records=[]
 for case in V.MANIFEST['cases']:
  for bias in ['B0','L2']:
   f=E1/'E1'/f'{case["id"]}_{bias}.npz';z=load(f);record=dict(case=case['id'],bias=bias)
   for key in ['x','prior']:
    X=z[key].reshape(-1,4);maxh=0.;maxj=0.;maxexplicit=0.
    for k in range(0,len(X),48):
     S.stopcheck();xx=X[k:k+48];h,H=old.batch(xx,case);g,J=new.batch(xx,case)
     maxh=max(maxh,float(np.max(abs(g-h))));maxj=max(maxj,float(np.max(abs(J-H))))
     # Explicit G(u,r,psi) reconstructed independently from geometry angles.
     b,e,r=geometry(xx,case);new.explicit=(unitvec(b,e),r);hh,_=new.batch(xx,case,gradient=False);new.explicit=None
     maxexplicit=max(maxexplicit,float(np.max(abs(hh[:,1]-h[:,1]))))
    check(key+'_h',maxh,0,1e-12);check(key+'_H',maxj,0,1e-12);check(key+'_explicit_G',maxexplicit,0,1e-12)
    record[key]=dict(n=len(X),h_max=maxh,H_max=maxj,G_explicit_max=maxexplicit)
   records.append(record);write('A0_PROGRESS.json',records);S.event('A0_CASE_PASS',case=case['id'],bias=bias)
 # Targeted analytic derivative check away from active detector/cell boundaries.
 derivative=[]
 for case in [V.MANIFEST['cases'][0],next(c for c in V.MANIFEST['cases'] if c['mount_deg']==45)]:
  z=load(E1/'E1'/f'{case["id"]}_B0.npz');idx=np.arange(200,len(z['t_s']),150);X=z['prior'][idx,4].copy();gt=z['truth_scoring_only'][idx]
  new.gt=gt
  for mode in ['UNCUT','CUT_ALL','CUT_AZ','CUT_EL','CUT_R']:
   new.modes=[mode]*len(X);h,H,diag=new.batch(X,case,return_diagnostics=True)
   for axis in range(3):
    step=1e-6 if axis<2 else 1e-7;xp=X.copy();xm=X.copy();xp[:,axis]+=step;xm[:,axis]-=step
    hp,_,dp=new.batch(xp,case,return_diagnostics=True);hm,_,dm=new.batch(xm,case,return_diagnostics=True)
    stable=(dp['tap']==dm['tap'])&np.all(dp['cells']==dm['cells'],axis=1)
    err=abs((hp-hm)/(2*step)-H[:,:,axis]);mx=float(err[stable].max()) if stable.any() else None
    if mx is not None:assert mx<1e-5,(case['id'],mode,axis,mx)
    derivative.append(dict(case=case['id'],mode=mode,axis=axis,stable=int(stable.sum()),total=len(X),max_error=mx))
 new.modes=None;preserve();write('A0_GATE.json',dict(status='PASS',conditions=records,derivative_checks=derivative));write('A0_CHECKS.json',S.checks);S.event('A0_COMPLETE')
if __name__=='__main__':
 try:main()
 except BaseException as e:write('A0_FAILURE.json',dict(error=str(e),traceback=traceback.format_exc()));raise
