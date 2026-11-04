"""Synthetic-only same-event branching controls. No scientific inputs are loaded."""
from collections import deque
from copy import deepcopy
from unittest.mock import patch
import sys
from pathlib import Path
import numpy as np
from branching import iter_event_pairs,state_hash,covariance_recovery,checkpoint_filter
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'S1'))
import online

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
class SafeGeometry:
 def __init__(self):self.history=deque()
 def add(self,t,H,R,F,accepted):
  self.history.append((t,H.copy(),R.copy(),F.copy(),accepted))
  while self.history and t-self.history[0][0]>2+1e-9:self.history.popleft()
 def information(self):return True,1.,1.,np.eye(4)

def inputs(n=160):
 s=np.zeros(n);s[:8]=.5;s[60:68]=.5
 pk=dict(t=np.arange(n)*.2,z=np.column_stack((np.zeros(n),s)),muBASE=np.zeros((n,2)),muMB=np.zeros((n,2)),R=np.tile(np.eye(2)[None]*.1,(n,1,1)),D=np.zeros(n),P0=np.diag([1e-4,1e-4,1e-4,1e-8]),pose_id=np.arange(n)*3+10)
 ct=dict(x0=np.zeros(3),ds=np.zeros(n),gy=np.zeros(n),dt=np.full(n,.2));return pk,ct

def run():
 checks=0;spec=dict(anchor=(1.,0.,0.))
 with patch.object(covariance_recovery,'Geometry',SafeGeometry),patch.object(checkpoint_filter,'Geometry',SafeGeometry):
  for stage,arm in [('S2','C_P'),('S2','D_P'),('S3','C_CP'),('S3','D_CP')]:
   packet,controls=inputs()
   if stage=='S2':natural,events=covariance_recovery.replay(packet,controls,arm,Core,Model,spec,online)
   else:natural,events,*_=checkpoint_filter.replay(packet,controls,arm,Core,Model,spec,'synthetic')
   natural['pose_id']=packet['pose_id'].copy()
   assert len(events)==2
   pairs=list(iter_event_pairs(stage,packet,controls,arm,Core,Model,spec,online,natural,events,'synthetic'))
   assert len(pairs)==2
   for pair in pairs:
    assert pair.parity['passed'] and pair.parity['start_hash_exact'] and np.array_equal(pair.on['mask'],pair.off['mask'])
    assert pair.off['recovery_applied'].sum()==0 and pair.on['recovery_applied'].sum()<=1
    assert pair.start_hash and pair.pretreatment_prior.shape==(4,)
    assert pair.pose_id==packet['pose_id'][pair.index]
   assert pairs[0].off['recovery_suppressed'].any();checks+=1
   # Future observations beyond the complete follow-up cannot affect this pair.
   end=int(pairs[0].on['sample_index'][-1])+1;changed=deepcopy(packet);changed['z'][end:]=1000
   result=next(iter_event_pairs(stage,changed,controls,arm,Core,Model,spec,online,natural,events,'synthetic',target_indices={pairs[0].index}))
   assert np.array_equal(result.on['x'],pairs[0].on['x']) and np.array_equal(result.off['x'],pairs[0].off['x'])
   assert result.start_hash==pairs[0].start_hash;checks+=1
  # Reject the original S3 replay candidate and retain it as an ON=OFF policy attempt.
  packet,controls=inputs();packet['P0'][3,3]=1e-4
  natural,events,*_=checkpoint_filter.replay(packet,controls,'C_CP',Core,Model,spec,'rejection')
  natural['pose_id']=packet['pose_id'];rejected=[e for e in events if e['disposition']!='ACCEPT']
  assert rejected
  pair=next(iter_event_pairs('S3',packet,controls,'C_CP',Core,Model,spec,online,natural,events,'rejection',target_indices={rejected[0]['index']}))
  assert pair.disposition=='CANDIDATE_OUT_OF_BOUNDS' and not pair.on['recovery_applied'].any()
  assert np.array_equal(pair.on['x'],pair.off['x']) and np.array_equal(pair.on['P'],pair.off['P']);checks+=1
  bad=deepcopy(packet);bad['pose_id'][3]=bad['pose_id'][2]
  try:list(iter_event_pairs('S3',bad,controls,'C_CP',Core,Model,spec,online,natural,events,'rejection'))
  except ValueError:checks+=1
  else:raise AssertionError('source ID duplication accepted')
 print(dict(status='PASS',synthetic_cases=checks,scope='synthetic packets and deterministic guard fixture only'))
if __name__=='__main__':run()
