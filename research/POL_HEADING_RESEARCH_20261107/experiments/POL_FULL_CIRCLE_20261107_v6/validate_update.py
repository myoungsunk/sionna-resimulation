import model as m
import numpy as np
original=m.old.model
try:
 H=np.array([.3,-.1,2.,0.]);mu=np.array([.02,.01,.03,0.]);P=np.diag([.01,.01,.001,.0001]);P[0,2]=P[2,0]=.0005
 def linear(xx):return xx@H,np.tile(H,(len(xx),1))
 m.old.model=linear;p=dict(residual_variance=.03,sigma_angle_rad=.05,outlier_probability=1e-14);z=.12
 parts,_=m.measurement([(1.,mu,P)],z,p);_,x,C=m.moment(parts)
 R=.03+4*.05**2;K=P@H/(H@P@H+R);refx=mu+K*(z-H@mu);refP=P-np.outer(K,H@P)
 dx=float(abs(x-refx).max());dc=float(abs(C-refP).max());assert dx<1e-9 and dc<1e-9
 def constant(xx):return np.zeros(len(xx)),np.zeros_like(xx)
 m.old.model=constant;a=np.zeros(4);b=a.copy();b[2]=np.pi;P=np.diag([.01,.01,.001,.0001])
 parts,_=m.measurement([(.5,a,P),(.5,b,P)],0.,p);assert len(parts)==2
 we=max(abs(w-.5) for w,_,_ in parts);assert we<1e-10
 m.dump('UPDATE_VALIDATION.json',dict(status='PASS',linear_gaussian_state_error=dx,linear_gaussian_covariance_error=dc,antipodal_update_branches=len(parts),antipodal_weight_error=we))
 print('PASS',dx,dc,we)
finally:m.old.model=original
