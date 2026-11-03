import json,numpy as np
import parity as p
O=p.online
rng=np.random.default_rng(120)
for i in range(50):
 A=rng.normal(size=(4,4));P=A@A.T+np.eye(4);x=rng.normal(size=4);H=rng.normal(size=(2,4));v=rng.normal(size=2);R=np.diag([.04,.07])
 y,C,_,_=O.joseph(x,P,H,v,R,True,0.);h=H[0];k=P@h/(h@P@h+R[0,0]);z=x+k*v[0];z[2]=p.b.core.wrap(z[2]);assert np.allclose(y,z) and np.allclose(C,P-np.outer(k,h@P))
 _,C0,_,_=O.joseph(x,P,H,v,R,True,1.);R[1,1]*=4;_,C1,_,_=O.joseph(x,P,H,v,R,True,.25);assert np.linalg.eigvalsh(C1-C0).min()>-1e-11
 y,C,_,_=O.joseph(x,P,H,v,R,False,.25);assert np.array_equal(x,y) and np.array_equal(P,C)
assert O.weight('H-d0',.2,1)==1 and O.weight('H-d0',.20001,1)==0 and O.weight('W-d0',1.,0)==.25 and O.weight('W-d0-DS',0,100)==.25
pk=p.read('R4_aB_m0_B0_Full');ct=p.read('R4_aB_m0_B0_0');pk={k:(v[:35].copy() if k!='P0' else v.copy()) for k,v in pk.items()}
a=O.replay(pk,ct,'W-d0-DS',p.b.core,p.b.model,p.spec)
poison={**pk,'truth':np.full((35,3),np.nan),'z':pk['z'].copy()};poison['z'][20:]+=.2
b=O.replay(poison,ct,'W-d0-DS',p.b.core,p.b.model,p.spec)
assert all(np.array_equal(a[k][:20],b[k][:20]) for k in a if k!='latency_ns')
assert np.allclose(a['d0'],a['nu'][:,1]+a['mu'][:,1]) and np.allclose(a['Reff'][:,1,1],a['Rvar'][:,1,1]/a['weight'])
fixed=O.replay(pk,ct,'W-d0-DS',p.b.core,p.b.model,p.spec,fixed_mask=a['mask'])
assert all(np.array_equal(a[k],fixed[k]) for k in a if k!='latency_ns')
print('50 SPD cases, scalar/remove/reject/PSD, causal prefix, same-packet innovation, variance scale and O/F output passed')
