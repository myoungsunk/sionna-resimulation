import run_heading as m
import numpy as np
mu=np.zeros(4);mu[2]=np.deg2rad(179.3);mu2=mu.copy();mu2[2]=m.e.wrap(mu[2]+np.deg2rad(20.));P=np.diag([.1,.1,np.deg2rad(1.)**2,.001])
def uninformative(x):return np.zeros(len(x)),np.zeros((len(x),4))
rows=[]
for step,phase in [(.25,0),(.125,0),(.0625,0),(.25,.125)]:
 theta=np.deg2rad(np.arange(-180+phase,180,step));parts,den,di=m.measurement([(.5,0,mu,P,0),(.5,0,mu2,P,1)],0,False,theta,uninformative)
 assert di['heading_modes']==2 and abs(den.sum()-1)<1e-12
 masses=[x[0] for x in parts];assert max(abs(np.array(masses)-.5))<1e-6
 _,X,C=m.moment([(w,x,p) for w,j,x,p,k in parts]);rows.append(dict(step=step,phase=phase,modes=di['heading_modes'],mean=X.tolist(),cov=C.tolist()))
ref=rows[2]
err=max(np.max(abs(np.array(r['cov'])-ref['cov'])) for r in rows);assert err<1e-5,err
m.dump('TOPOLOGY_TESTS.json',dict(status='PASS_SELF_CHECK',boundary_crossing_two_close_modes=True,grids=rows,max_covariance_difference=float(err)))
print('TOPOLOGY PASS',err)
