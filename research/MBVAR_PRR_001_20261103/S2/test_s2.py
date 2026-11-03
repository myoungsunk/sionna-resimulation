"""Small independent invariants before scientific phase approval."""
import json
import math
from pathlib import Path
import numpy as np
from recovery import inject,Geometry,RecoveryMachine,validate_covariance

def run():
 rng=np.random.default_rng(20261103);checks=0
 for near in (False,True):
  for axes in ('heading','tangent_heading','tangent_heading_bg'):
   for i in range(12):
    M=rng.normal(size=(4,4));scale=np.diag([.01,.01,math.radians(.1),math.radians(.005)]);P=scale@(M@M.T+np.eye(4))@scale
    x=np.array([0.01 if near else 2.,0.,.3,.002]);y,C,D,fallback=inject(x,P,[0.,0.],axes)
    assert np.array_equal(x,y);assert np.linalg.eigvalsh(D).min()>=-1e-15
    assert np.allclose(C-P,D,atol=1e-18,rtol=1e-12)
    assert np.array_equal(C[np.triu_indices(4,1)],P[np.triu_indices(4,1)])
    assert C[2,2]>=math.radians(1)**2-1e-18
    if axes!='tangent_heading_bg':assert C[3,3]==P[3,3]
    if near and axes!='heading':assert np.linalg.eigvalsh(C[:2,:2]).min()>=.01-1e-15
    checks+=1
 # An already broad covariance must not shrink, and zero innovation must preserve mean.
 x=np.array([2.,0.,.2,.01]);P=np.eye(4);y,C,D,_=inject(x,P,[0.,0.]);assert np.array_equal(C,P) and np.count_nonzero(D)==0;checks+=1
 G=Geometry();H=np.array([[1.,0.,0.,0.],[0.,1.,0.,0.]])
 G.add(0.,H,np.eye(2),np.eye(4),True);ok,_,m,_=G.information();assert not ok and m==0;checks+=1
 machine=RecoveryMachine()
 for t in (0.,.2,.4):fire,status=machine.observe(t,True,.25,1.,True);assert not fire
 for t in np.arange(.6,1.61,.2):fire,status=machine.observe(float(t),True,1.,1.,True)
 assert fire;machine.commit(1.6)
 for t in np.arange(1.8,3.81,.2):assert not machine.observe(float(t),True,1.,1.,True)[0]
 assert machine.status=='MONITORING';checks+=1
 machine=RecoveryMachine()
 for t in (0.,.2,.4):machine.observe(t,True,.25,1.,True)
 assert not machine.observe(61.,True,1.,1.,True)[0] and machine.status=='HISTORY_EXPIRED_REMAIN_SUSPECT';checks+=1
 bad=np.eye(4);bad[0,0]=-1
 try:validate_covariance(bad)
 except ValueError:checks+=1
 else:raise AssertionError('negative covariance accepted')
 # Force a synthetic recovery schedule to isolate measurement-off and zero-residual behavior.
 import importlib.util
 import sys
 source=Path(__file__).parent.parent/'S1/online.py'
 sp=importlib.util.spec_from_file_location('s1_online_test',source);online=importlib.util.module_from_spec(sp);sp.loader.exec_module(online)
 from recovery import replay
 class Core:
  @staticmethod
  def transition(x,ds,gy,dt):return x.copy(),np.eye(4),np.zeros((4,3))
  @staticmethod
  def predict(x,P,*args):return x.copy(),P.copy(),np.eye(4),np.zeros((4,3))
 class Model:
  @staticmethod
  def batch(x,spec):
   H=np.array([[0.,1.,0.,0.],[0.,0.,1.,0.]])
   return x@H.T,np.broadcast_to(H,(len(x),2,4)).copy()
 pk=dict(t=np.array([0.]),z=np.zeros((1,2)),muBASE=np.zeros((1,2)),muMB=np.zeros((1,2)),R=np.eye(2)[None]*.0001,P0=np.eye(4)*1e-6,D=np.zeros(1))
 ct=dict(x0=np.zeros(3),ds=np.zeros(1),gy=np.zeros(1),dt=np.zeros(1));spec=dict(anchor=(1.,0.,0.));schedule=np.ones(1,bool)
 tr,_=replay(pk,ct,'C_P',Core,Model,spec,online,schedule=schedule)
 assert np.array_equal(tr['x'][0],np.zeros(4)) and tr['injected'][0];checks+=1
 pk['z'][0,0]=.2
 trF,_=replay(pk,ct,'C_P',Core,Model,spec,online,schedule=schedule)
 trO,_=replay(pk,ct,'C_P',Core,Model,spec,online,schedule=schedule,gate_mode='O')
 assert not trF['mask'][0] and trO['mask'][0] and not trO['preinjection_mask'][0]
 assert np.array_equal(trF['x'][0],np.zeros(4));checks+=1
 result=dict(status='PASS' ,synthetic_cases=checks,scope='injection and causal state machine only, no scientific replay')
 print(json.dumps(result));return result
if __name__=='__main__':run()
