import run_angle as m
import numpy as np
mu=np.zeros(4);P=np.diag([.1,.1,.01,.001]);P[0,2]=P[2,0]=.01
H=np.array([.2,0,1,0]);z=.03
def linear(mu,z):return [(z-.2*mu[0],np.array([.2,0,0]))]
parts,den,di=m.measurement([(1.,0,mu,P,0)],z,False,rootfun=linear)
_,X,C=m.moment([(w,x,p) for w,j,x,p,k in parts]);K=P@H/(H@P@H+m.SCALES[0]);exact=mu+K*z;cov=P-np.outer(K,H@P);error=max(abs(X-exact).max(),abs(C-cov).max());assert error<1e-8,error
saved=m.e.RS;m.e.RS*=100
parts2,den2,_=m.measurement([(1.,0,mu,P,0)],z,False,rootfun=linear);m.e.RS=saved;assert np.array_equal(den,den2)
# Antipodal candidates cannot be selected by truth or nearest-prior branch.
a=mu.copy();a[2]=.3;b=mu.copy();b[2]=m.e.wrap(.3+np.pi);Q=np.diag([.1,.1,.01,.001])
def amb(mu,z):return [(.3,np.zeros(3)),(m.e.wrap(.3+np.pi),np.zeros(3))]
parts,den,di=m.measurement([(.5,0,a,Q,0),(.5,0,b,Q,1)],0.,False,rootfun=amb)
mass=float(den[abs(m.e.wrap(m.TH-.3))<np.pi/2].sum());assert abs(mass-.5)<1e-6 and di['heading_modes']==2
# Real LUT inverse and implicit derivative checked at well-separated smooth roots.
rng=np.random.default_rng(7);errors=[];jac=[];checked=0
for _ in range(80):
 q=np.array([rng.uniform(2,18),rng.uniform(-.4,.4),rng.uniform(-np.pi,np.pi),0.]);z=float(m.model(q[None])[0][0]);roots=m.inverse_roots(q,z)
 if not roots:continue
 angle,Ho=min(roots,key=lambda a:abs(m.e.wrap(a[0]-q[2])));qq=q.copy();qq[2]=angle;errors.append(abs(m.model(qq[None])[0][0]-z))
 for axis in [0,1]:
  eps=1e-5;q1=q.copy();q2=q.copy();q1[axis]+=eps;q2[axis]-=eps;r1=m.inverse_roots(q1,z);r2=m.inverse_roots(q2,z)
  if not r1 or not r2:continue
  a1=min(r1,key=lambda a:abs(m.e.wrap(a[0]-angle)))[0];a2=min(r2,key=lambda a:abs(m.e.wrap(a[0]-angle)))[0]
  diff=m.e.wrap(a1-a2)/(2*eps);jac.append(abs(diff+Ho[axis]));checked+=1
assert max(errors)<1e-10 and max(jac)<1e-4,(max(errors),max(jac))
parts,_,_=m.measurement([(float(w),j,mu,P,0) for j,w in enumerate(m.PI)],0,True,rootfun=linear);post=np.array([sum(w for w,j,x,p,k in parts if j==i) for i in range(6)]);assert post[0]>m.PI[0]
# No inverse solution is an uninformative update, not an invented angle.
parts,_,_=m.measurement([(1.,0,mu,P,0)],99,False,rootfun=lambda x,z:[]);_,X,C=m.moment([(w,x,p) for w,j,x,p,k in parts]);assert max(abs(X-mu).max(),abs(C-P).max())<1e-8
m.dump('TESTS.json',dict(status='PASS_SELF_CHECK',linear_angular_gaussian_error=float(error),s_variance_independence=True,antipodal_mass=mass,inverse_value_error=float(max(errors)),implicit_jacobian_error=float(max(jac)),jacobian_checks=checked,no_inverse_no_information=True,angular_sigma_posterior=post.tolist()))
print('PASS',error,max(errors),max(jac))
