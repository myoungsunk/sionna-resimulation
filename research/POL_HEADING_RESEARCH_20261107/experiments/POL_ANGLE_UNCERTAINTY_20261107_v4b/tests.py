import run_angle as m
import numpy as np
from scipy.special import logsumexp
errors=[]
for S in [.01,.49,.5,1.,10.,100.]:
 for r in [-3.14,-1.,0.,.7,3.14]:
  v=r+2*np.pi*np.arange(-100,101);logs=-.5*v*v/S-.5*np.log(2*np.pi*S);lp=logsumexp(logs);w=np.exp(logs-lp);mean=w@v;var=w@((v-mean)**2);expected=np.array([lp,-mean/S,var/S**2-1/S]);errors.append(float(abs(np.array(m.wrapped_stats(r,S))-expected).max()))
assert max(errors)<1e-7,max(errors)
mu=np.zeros(4);P=np.diag([.1,.1,.01,.001]);P[0,2]=P[2,0]=.01;H=np.array([.2,0,1,0]);z=.03
root=lambda mu,z:[(z-.2*mu[0],np.array([.2,0,0]))]
parts,di=m.measurement([(1.,0,mu,P,0)],z,rootfun=root);_,x,C=m.moment([(w,x,p) for w,j,x,p,k in parts]);K=P@H/(H@P@H+m.SCALES[0]);err=max(abs(x-K*z).max(),abs(C-(P-np.outer(K,H@P))).max());assert err<1e-10
P=np.diag([.1,.1,1e-12,.001]);parts,di=m.measurement([(1.,0,mu,P,0)],0.,rootfun=root);den=m.density(parts,m.TH);assert np.isfinite(den).all() and abs(den.sum()-1)<1e-14
P=np.diag([.1,.1,np.deg2rad(1.)**2,.001]);mu[2]=.3;m2=mu.copy();m2[2]=m.e.wrap(.3+np.pi)
root=lambda x,z:[(.3,np.zeros(3)),(m.e.wrap(.3+np.pi),np.zeros(3))]
parts,di=m.measurement([(.5,0,mu,P,0),(.5,0,m2,P,1)],0,rootfun=root);assert di['modes']==2 and max(abs(np.array([c[0] for c in parts])-.5))<1e-10
m2[2]=.3+np.deg2rad(20);parts,di=m.reduce_mixture([(.5,0,mu,P,0),(.5,0,m2,P,1)]);assert di['modes']==2
m.dump('TESTS.json',dict(status='PASS_SELF_CHECK',wrapped_derivative_error=max(errors),linear_angular_gaussian_error=float(err),subgrid_sigma_supported=True,antipodal_modes_preserved=True,close20deg_modes_preserved=True,previous_inverse_tests='../POL_ANGLE_UNCERTAINTY_20261107_v4/TESTS.json'))
print('PASS',max(errors),err)
