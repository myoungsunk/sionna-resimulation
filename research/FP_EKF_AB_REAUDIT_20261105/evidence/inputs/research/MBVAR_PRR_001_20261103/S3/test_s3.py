"""Synthetic S3 identity, independent cold and history failure controls."""
from copy import deepcopy
from pathlib import Path
import math
import numpy as np
from history import History,validate_candidate
from foreground import replay,initial

class Core:
 @staticmethod
 def transition(x,ds,gy,dt):
  y=x.copy();y[2]-=x[3]*dt;F=np.eye(4);F[2,3]=-dt
  return y,F,np.zeros((4,3))
 @staticmethod
 def predict(x,P,ds,gy,dt,Q):
  y,F,G=Core.transition(x,ds,gy,dt);return y,F@P@F.T,F,G
class Model:
 @staticmethod
 def batch(x,spec):
  H=np.array([[1.,0.,0.,0.],[0.,0.,1.,0.]])
  return x@H.T,np.broadcast_to(H,(len(x),2,4)).copy()
def inputs(n=25):
 pk=dict(t=np.arange(n)*.2,z=np.tile([0.,.3],(n,1)),muBASE=np.zeros((n,2)),muMB=np.zeros((n,2)),R=np.tile(np.eye(2)[None]*.1,(n,1,1)),D=np.zeros(n),P0=np.diag([1e-4,1e-4,1e-4,1e-8]),pose_id=np.arange(n))
 ct=dict(x0=np.zeros(3),ds=np.zeros(n),gy=np.zeros(n),dt=np.full(n,.2));return pk,ct

def run():
 checks=0
 for arm,base in [('C_CP','A'),('D_CP','B')]:
  pk,ct=inputs();schedule=np.zeros(len(pk['t']),bool);schedule[15]=True;first=np.zeros(len(schedule))
  tr,ev,_,_,_=replay(pk,ct,arm,Core,Model,dict(anchor=(1.,0.,0.)),'test',identity=True,common_schedule=schedule,common_first=first)
  reference,*_=replay(pk,ct,base,Core,Model,dict(anchor=(1.,0.,0.)),'test',common_schedule=schedule,common_first=first)
  assert ev and ev[0]['disposition']=='ACCEPT';assert np.allclose(tr['x'],reference['x'],atol=1e-10,rtol=1e-10);assert np.allclose(tr['P'],reference['P'],atol=1e-10,rtol=1e-10);checks+=1
  tr,ev,retro,_,_=replay(pk,ct,arm,Core,Model,dict(anchor=(1.,0.,0.)),'test',common_schedule=schedule,common_first=first)
  assert ev[0]['disposition']=='ACCEPT' and ev[0]['cold_max_abs']<1e-10 and retro;checks+=1
  prefix,*_=replay({k:v[:16].copy() if hasattr(v,'shape') and len(v.shape) and k!='P0' else v for k,v in pk.items()},{k:v[:16].copy() if k!='x0' else v for k,v in ct.items()},arm,Core,Model,dict(anchor=(1.,0.,0.)),'test',common_schedule=schedule[:16],common_first=first[:16])
  pk['z'][16:]=1000;changed,*_=replay(pk,ct,arm,Core,Model,dict(anchor=(1.,0.,0.)),'test',common_schedule=schedule,common_first=first)
  assert np.array_equal(prefix['x'],changed['x'][:16]) and np.array_equal(prefix['P'],changed['P'][:16]);checks+=1
 pk,ct=inputs(100);schedule=np.zeros(100,bool);schedule[90]=True
 _,ev,_,_,_=replay(pk,ct,'C_CP',Core,Model,dict(anchor=(1.,0.,0.)),'test',seconds=10,common_schedule=schedule,common_first=np.zeros(100));assert ev[0]['disposition']=='HISTORY_INSUFFICIENT';checks+=1
 for defect in ('missing','duplicate','late','corrupt','after_episode'):
  h=History(60,'test',np.arange(8));h.save(-1,-1.,dict(x=1))
  for i in range(5):h.append(i,i*.2,dict(pose_id=i))
  if defect=='missing':h.packets.pop()
  if defect=='duplicate':assert not h.append(4,1.,{})
  if defect=='late':assert not h.append(5,.1,{})
  if defect=='corrupt':h.checkpoints[0].config_hash='bad'
  if defect=='after_episode':h.checkpoints.clear();h.save(4,.8,{})
  assert h.replay_input(0,4) is None;checks+=1
 x=np.zeros(4);P=np.eye(4)
 for reason,xx,PP,last,current in [('CANDIDATE_BEHIND',x,P,1,2),('NONFINITE',np.full(4,np.nan),P,1,1),('INVALID_COVARIANCE',x,-P,1,1),('CANDIDATE_OUT_OF_BOUNDS',np.array([1.,0.,0.,0.]),P,1,1)]:
  assert validate_candidate(x,xx,PP,last,current,end_pose_id=7,current_pose_id=7)==reason;checks+=1
 pk,ct=inputs(2);_,_,_,_,timing=replay(pk,ct,'A',Core,Model,dict(anchor=(1.,0.,0.)),'test',timed=True)
 assert timing['real_clock_5Hz'] and timing['wall_clock_s']>=.19 and timing['dropped_packets']==0;checks+=1
 # Registered IDs need not be consecutive; sequence positions still have exact identities.
 ids=np.array([2,9,20,40,100]);h=History(60,'ids',ids);h.save(-1,-1.,{})
 for k,source in enumerate(ids):assert h.append(k,k*.2,dict(pose_id=int(source)))
 assert h.replay_input(0,4) is not None;checks+=1
 for defect in ('duplicate_source','reordered_source','missing_source'):
  h=History(60,'ids',ids);h.save(-1,-1.,{});assert h.append(0,0.,dict(pose_id=2))
  source={'duplicate_source':2,'reordered_source':20,'missing_source':None}[defect]
  assert not h.append(1,.2,dict(pose_id=source));assert h.replay_input(0,1) is None;checks+=1
 h=History(60,'ids',ids);h.save(-1,-1.,{})
 for k,source in enumerate(ids):h.append(k,k*.2,dict(pose_id=int(source)))
 h.packets[-1][2]['pose_id']=40
 assert h.replay_input(0,4) is None;checks+=1
 assert validate_candidate(x,x,P,4,4,end_pose_id=40,current_pose_id=100)=='SOURCE_ID_MISMATCH';checks+=1
 pk,ct=inputs();pk['pose_id']=np.arange(len(pk['t']))*3+10
 tr,ev,*_=replay(pk,ct,'C_CP',Core,Model,dict(anchor=(1.,0.,0.)),'gaps',common_schedule=np.arange(len(pk['t']))==15,common_first=np.zeros(len(pk['t'])))
 assert ev[0]['end_pose_id']==55 and ev[0]['current_pose_id']==55 and ev[0]['checkpoint_pose_id'] is None
 assert ev[0]['historical_pose_ids']==pk['pose_id'][:16].tolist();checks+=1
 # Terminal acceptance cannot be rewritten alongside an arbitrary replacement manifest.
 import importlib.util,json
 sp=importlib.util.spec_from_file_location('s3_grant_test',Path(__file__).parent/'grant.py');g=importlib.util.module_from_spec(sp);sp.loader.exec_module(g)
 manifest=json.dumps(dict(status='COMPLETE',phase='eval',grant=dict(code_commit='frozen'))).encode()
 receipt=json.dumps(dict(complete=True,independent_audit='ACCEPT',code_commit='frozen',run_manifest_sha256=g.g.digest(manifest))).encode()
 token=dict(s2_final_sha256=g.g.digest(receipt),s2_manifest_sha256=g.g.digest(manifest))
 g.verify_terminal_bytes(receipt,receipt,manifest,manifest,'frozen',token);checks+=1
 for defect in ('receipt','manifest','receipt_and_manifest','grant_receipt_hash'):
  current=receipt if defect not in ('receipt','receipt_and_manifest') else receipt+b' '
  current_manifest=manifest if defect not in ('manifest','receipt_and_manifest') else manifest+b' '
  grant=token.copy()
  if defect=='grant_receipt_hash':grant['s2_final_sha256']='wrong'
  try:g.verify_terminal_bytes(receipt,current,manifest,current_manifest,'frozen',grant)
  except RuntimeError:checks+=1
  else:raise AssertionError('mutable S2 terminal evidence accepted')
 print(dict(status='PASS',synthetic_cases=checks,scope='synthetic packets only'))
if __name__=='__main__':run()
