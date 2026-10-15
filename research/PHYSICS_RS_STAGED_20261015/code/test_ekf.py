import numpy as np
from common import setup_original
setup_original()
from core import gaussian_update
from stage_c import recursive_filter,METHODS,metric
class Toy:
 def model(self,x,case):
  H=np.array([[1.,0.,0.,0.],[0.,.2,.5,0.]])
  return H@x,H

def test_original_update_independent_information_form():
 x=np.array([1.,2.,.1,.002]);P=np.diag([.2,.3,.1,.005]);H=Toy().model(x,None)[1]
 R=np.diag([.0068578637,.0081]);z=np.array([1.04,.48])
 y,C,d=gaussian_update(x,P,z,lambda q:Toy().model(q,None),R)
 ref=np.linalg.inv(np.linalg.inv(P)+H.T@np.linalg.solve(R,H))
 mean=ref@(np.linalg.solve(P,x)+H.T@np.linalg.solve(R,z))
 np.testing.assert_allclose(y,mean,rtol=0,atol=1e-12);np.testing.assert_allclose(C,ref,atol=1e-12,rtol=0)

def test_dynamic_R_equal_baseline_has_exact_same_results():
 n=5;t=np.arange(n)*.2;controls={'ds_odom':np.full(n,.01),'dtheta_gyro':np.full(n,.002),'dt_s':np.full(n,.2)}
 z=np.tile([1.04,.48],(n,1));r=np.full((n,len(METHODS)),.0081)
 x,P,nis,acc=recursive_filter(t,controls,z,{},Toy(),np.array([1.,2.,.1]),r)
 for j in range(1,len(METHODS)):
  np.testing.assert_allclose(x[:,j],x[:,0],rtol=0,atol=1e-12)
  np.testing.assert_allclose(P[:,j],P[:,0],rtol=0,atol=1e-12)
  np.testing.assert_array_equal(acc[:,j],acc[:,0])

def test_offline_metrics_correct_subspace():
 n=5;x=np.zeros((n,4));P=np.tile(np.diag([1.,1.,.01,.001]),(n,1,1));truth=np.zeros((n,3));t=np.arange(30,35)
 x[:,2]=.1;row=metric(x,P,truth,t,0.)
 assert abs(row['heading_NEES']-1)<1e-12
 assert abs(row['pose_NEES']-1)<1e-12
 assert row['heading95']==1 and row['bias_RMSE_dps']==0

def test_batch_matches_original_scalar():
 from stage_c import frozen_batch_update
 rng=np.random.default_rng(902);n=20
 mu=rng.normal(size=(n,4));P=[]
 for k in range(n):
  a=rng.normal(size=(4,4));P.append(a@a.T+np.eye(4))
 P=np.array(P);H=rng.normal(size=(n,2,4));h=(H@mu[...,None])[...,0]
 z=h+rng.normal(size=(n,2))*.1;R=np.tile(np.diag([.03,.12]),(n,1,1));acc=np.arange(n)%3!=0
 yy,CC=frozen_batch_update(mu,P,z,h,H,R,acc)
 for k in range(n):
  if acc[k]:
   y,C,_=gaussian_update(mu[k],P[k],z[k],lambda q:(h[k],H[k]),R[k])
  else:y,C=mu[k],P[k]
  np.testing.assert_allclose(y,yy[k],atol=1e-12,rtol=0)
  np.testing.assert_allclose(C,CC[k],atol=1e-12,rtol=0)

def test_fast_scalar_exact_algebra_random_cases():
 from stage_c import fast_predict,fast_update
 from r2_bias_replay import predict_one
 rng=np.random.default_rng(301)
 for i in range(30):
  x=rng.normal(size=4);a=rng.normal(size=(4,4));P=a@a.T+np.eye(4)*.01
  ds,gy,dt=float(rng.normal()*.02),float(rng.normal()*.01),.2
  yp,Cp=predict_one(x,P,ds,gy,dt);yq,Cq=fast_predict(x,P,ds,gy,dt)
  np.testing.assert_array_equal(yp,yq);np.testing.assert_array_equal(Cp,Cq)
  R=np.diag([.0068578637,.0081*float(rng.uniform(1,20))]);z=rng.normal(size=2)
  y,C,d=gaussian_update(yp,Cp,z,lambda q:Toy().model(q,None),R,gate_threshold=9.210340371976184)
  yf,Cf,ns,acc=fast_update(yp,Cp,z,lambda q:Toy().model(q,None),R,9.210340371976184)
  np.testing.assert_array_equal(y,yf);np.testing.assert_array_equal(C,Cf)
  assert acc==d['accepted'] and ns==d['NIS']

def test_independent_cholesky_score():
 from post_validate import independent_score
 n=5;x=np.zeros((n,4));x[:,2]=.1
 P=np.tile(np.diag([1.,1.,.01,.001]),(n,1,1));truth=np.zeros((n,3));t=np.arange(30,35)
 r=independent_score(x,P,truth,t,0.)
 assert abs(r['heading_NEES']-1)<1e-12 and abs(r['pose_NEES']-1)<1e-12
 assert r['heading95']==1 and r['n']==5

def test_nees_decomposition_identity():
 from diagnose_gate import decomposition
 rng=np.random.default_rng(15);x=rng.normal(size=(12,4))*.01;truth=np.zeros((12,3));a=rng.normal(size=(12,4,4));P=a@a.transpose(0,2,1)+np.eye(4)[None]
 d=decomposition(x,P,truth,np.arange(30,42))
 from post_validate import independent_score
 m=independent_score(x,P,truth,np.arange(30,42))
 assert abs(d['pose_NEES_mean']-m['pose_NEES'])<1e-12
 assert abs(d['heading_term_mean']+d['conditional_xy_term_mean']-m['pose_NEES'])<1e-12
