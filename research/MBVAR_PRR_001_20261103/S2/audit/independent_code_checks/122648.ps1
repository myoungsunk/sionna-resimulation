@'
from pathlib import Path
import importlib.util,json,hashlib
import numpy as np
base=Path('/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103')
def load(name,p):
 sp=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
r=load('s2_timing_target',base/'S2/recovery.py');o=load('s1_timing_dependency',base/'S1/online.py')
class Core:
 @staticmethod
 def transition(x,*a):return x+np.array([2,1,0,0]),np.eye(4),np.zeros((4,3))
 @staticmethod
 def predict(x,P,*a):return x+np.array([2,1,0,0]),P+np.diag([.001,.002,1e-6,0]),np.eye(4),np.zeros((4,3))
class Model:
 @staticmethod
 def batch(x,spec):
  H=np.array([[0,1,0,0],[0,0,1,0]],float);return x@H.T,np.broadcast_to(H,(len(x),2,4)).copy()
ct=dict(x0=np.array([.05,.05,.2]),ds=np.zeros(2),gy=np.zeros(2),dt=np.ones(2)*.2);pk=dict(t=np.array([0.,.2]),z=np.array([[100.,100.],[1.05,.2]]),muBASE=np.zeros((2,2)),muMB=np.zeros((2,2)),R=np.tile(np.eye(2)*1e-4,(2,1,1)),P0=np.eye(4)*1e-6,D=np.zeros(2));spec=dict(anchor=(0.,0.,0.));schedule=np.array([False,True]);tr,_=r.replay(pk,ct,'C_P',Core,Model,spec,o,schedule=schedule)
expected_x=np.array([2.05,1.05,.2,0]);expected_P=pk['P0']+np.diag([.001,.002,1e-6,0]);rho=np.hypot(.05,.05);sig=np.interp(rho,[0,1.5,3,6,10],[.011,.020,.050,.120,.240]);u=np.array([-1.05,2.05,0,0])/np.hypot(2.05,1.05);delta=max(0,.01-u@expected_P@u)*np.outer(u,u);delta[2,2]=max(0,np.deg2rad(1)**2-expected_P[2,2])
assert np.array_equal(tr['prior'][1],expected_x) and np.allclose(tr['x'][1],expected_x);assert np.allclose(tr['Pbefore_injection'][1],expected_P);assert np.allclose(tr['delta_P'][1],delta);assert tr['sigma_b'][1]==sig
assert not tr['fallback'][1] and tr['injected'][1] and not tr['mask'][0]
repeat,_=r.replay(pk,ct,'C_P',Core,Model,spec,o,schedule=schedule)
assert all(np.array_equal(tr[k],repeat[k],equal_nan=True) if tr[k].dtype.kind not in 'U' else np.array_equal(tr[k],repeat[k]) for k in tr if k!='latency_ns')
print(json.dumps(dict(status='PASS',post_predict_pre_measurement_injection=True,sigma_b_previous_posterior_timing_preserved=True,zero_innovation_mean_unchanged=True,deterministic_except_wallclock=True,hashes={name:hashlib.sha256((base/name).read_bytes()).hexdigest() for name in ['S2/IMPLEMENTATION_RULES.json','S2/OWNER_APPROVAL.json','S2/OWNER_AUTHORIZATION.md','S1/MATERIALIZED_INPUTS.json','S1/EPSILON_INPUTS.json','A0_R3_REFIT/CONTRACT_LOCK.json']})))
'@ | wsl -d Ubuntu-24.04 env PYTHONDONTWRITEBYTECODE=1 PYTHONHOME=/home/myoung-sun/.local/share/prr31117 LD_LIBRARY_PATH=/home/myoung-sun/.local/share/prr31117/lib OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /home/myoung-sun/.local/share/prr31117/bin/python3 -