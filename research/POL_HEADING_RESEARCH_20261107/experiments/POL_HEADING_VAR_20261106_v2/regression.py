import run_heading as v
import importlib.util
import numpy as np
spec=importlib.util.spec_from_file_location('old',v.BASE.parent/'POL_HEADING_VAR_20261106_v1/run_heading.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
v.tests()
mu=np.zeros(4);P=np.diag([.1,.1,np.deg2rad(1)**2,.001]);m2=mu.copy();m2[2]=np.deg2rad(20)
c=[(.5,0,mu,P,0),(.5,0,m2,P,1)]
new=v.interact(c,1.,False);before=old.interact([x[:4] for x in c],1.,False)
assert len(new)==2 and len(before)==1
assert abs(sum(x[0] for x in new)-1)<1e-14
# Exact linear observation of x on a broad correlated unwrapped Gaussian.
# Gaussian conditioning gives an independent closed-form wrapped yaw marginal.
mu=np.array([0.,0.,2.8,0.]);P=np.diag([4.,.1,16.,.001]);P[0,2]=P[2,0]=6.
def obs(x):return x[:,0],np.tile([1.,0,0,0],(len(x),1))
z=1.2;H=np.array([1.,0,0,0]);K=P@H/(P[0,0]+v.e.RS);exact=mu+K*z;cov=P-np.outer(K,H@P)
res={}
for name,mod,comps in [('v1',old,[(1.,0,mu,P)]),('v2',v,[(1.,0,mu,P,0)])]:
 parts,den,di=mod.measurement(comps,z,False,fun=obs)
 _,mean,C=mod.moment([(c[0],c[2],c[3]) for c in parts])
 circ=np.sum(den*np.exp(1j*v.TH));target=np.exp(1j*exact[2]-.5*cov[2,2])
 err=max(abs(mean[0]-exact[0]),abs(C[0,0]-cov[0,0]),abs(circ-target))
 res[name]=float(err)
assert res['v2']<1e-9 and res['v1']>1e-3,res
v.dump('REGRESSION.json',dict(status='PASS_SELF_CHECK',close_modes_before=len(before),close_modes_after=len(new),broad_correlated_closed_form_error=res))
print(res)
