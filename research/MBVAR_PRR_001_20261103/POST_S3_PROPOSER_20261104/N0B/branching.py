"""One-event ON/OFF branches with the original natural policy as their prefix.

The caller must authenticate its stage GO and frozen inputs before scientific use.
This module has no CLI and runs no data on import.
"""
from copy import deepcopy
from dataclasses import dataclass
from collections import deque
import hashlib
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
for directory in ('S2','S1','S3'):
 sys.path.insert(0,str(ROOT/directory))
import recovery as covariance_recovery
import foreground as checkpoint_filter
from history import History,Checkpoint,validate_candidate
from cold_reference import cold_replay

@dataclass
class EventPair:
 stage: str
 arm: str
 index: int
 pose_id: object
 time: float
 start_hash: str
 pretreatment_prior: object
 on: dict
 off: dict
 disposition: str
 parity: dict
 decision: dict

def _canonical(value):
 if isinstance(value,np.ndarray):
  a=np.ascontiguousarray(value)
  return dict(dtype=a.dtype.str,shape=list(a.shape),sha256=hashlib.sha256(a.tobytes()).hexdigest())
 if isinstance(value,np.generic):return _canonical(value.item())
 if isinstance(value,float):return dict(float_hex=value.hex())
 if value is None or isinstance(value,(bool,int,str)):return value
 if isinstance(value,dict):return {str(k):_canonical(v) for k,v in sorted(value.items(),key=lambda p:str(p[0]))}
 if isinstance(value,(tuple,list,deque)):return [_canonical(v) for v in value]
 if hasattr(value,'__dict__'):return dict(type=type(value).__name__,fields=_canonical(vars(value)))
 raise TypeError(type(value))

def state_hash(value):
 return hashlib.sha256(json.dumps(_canonical(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()

def _parity(actual,reference,k):
 delta={}
 for field in ('x','P'):
  delta[field]=float(np.max(np.abs(actual[field]-reference[field][k])))
  if not np.allclose(actual[field],reference[field][k],atol=1e-10,rtol=1e-10):raise ValueError('natural ON parity '+field)
 if bool(actual['mask'])!=bool(reference['mask'][k]):raise ValueError('natural mask parity')
 if 'weight' in actual and not np.allclose(actual['weight'],reference['weight'][k],atol=1e-10,rtol=1e-10):raise ValueError('natural weight parity')
 if 'pose_id' not in reference:raise ValueError('natural trace source IDs absent')
 return dict(passed=True,max_state_abs=delta['x'],max_covariance_abs=delta['P'],mask_exact=True)

def _pack(records,packet):
 keys=records[0].keys();out={key:np.asarray([r[key] for r in records]) for key in keys}
 indices=out['sample_index'];out['t']=packet['t'][indices].copy();out['pose_id']=packet['pose_id'][indices].copy()
 if not np.isfinite(out['x']).all() or not np.isfinite(out['P']).all():raise ValueError('nonfinite branch')
 return out

def _record(rec,k,*,applied=False,suppressed=False):
 result={key:np.asarray(rec[key]).copy() for key in ('x','P','prior','Pprior','mask','weight')}
 result.update(sample_index=k,recovery_applied=bool(applied),recovery_suppressed=bool(suppressed))
 return result

def _prepare_s2(chain,packet,controls,k,prevention,core,model,spec,online):
 if chain.last_index+1!=k or packet['pose_id'][k]!=chain.source_pose_ids[k]:raise ValueError('S2 packet identity')
 row=checkpoint_filter.frame(packet,controls,k)
 chain.shadow_x,chain.shadow_P=online.predict(core,chain.shadow_x,chain.shadow_P,k,controls)
 sh,sH=model.batch(chain.shadow_x[None],spec);sh,sH=sh[0],sH[0]
 R=packet['R'][k];sv=row['z']-sh-row['muBASE'];ss=sH@chain.shadow_P@sH.T+R
 allowed=bool(sv@np.linalg.solve(ss,sv)<=online.GATE)
 chain.shadow_x,chain.shadow_P,_,_=online.joseph(chain.shadow_x,chain.shadow_P,sH,sv,R,allowed,1.)
 rho=math.hypot(chain.x[0]-spec['anchor'][0],chain.x[1]-spec['anchor'][1])
 sig=float(np.interp(rho,[0.,1.5,3.,6.,10.],[.011,.020,.050,.120,.240]))
 F=np.eye(4) if k==0 else core.transition(chain.x,float(controls['ds'][k]),float(controls['gy'][k]),float(controls['dt'][k]))[1]
 xp,pp=online.predict(core,chain.x,chain.P,k,controls);h,H=model.batch(xp[None],spec);h,H=h[0],H[0]
 nu=row['z']-h-row['muMB'];rw=online.weight('W-d0-DS',row['z'][1]-h[1],row['D']);w=rw if prevention else 1.
 rv=R.copy();rv[1,1]+=sig**2;re=rv.copy();re[1,1]/=w
 chain.geometry.add(row['t'],H,re,F,allowed);ok,_,_,_=chain.geometry.information()
 candidate,_=chain.machine.observe(float(row['t']),allowed,rw,float(np.linalg.norm(xp[:2]-np.asarray(spec['anchor'])[:2])),ok)
 return dict(xp=xp,pp=pp,h=h,H=H,nu=nu,R=re,allowed=allowed,w=w,candidate=candidate,row=row)

def _finish_s2(chain,prepared,k,apply,consume,online,spec):
 xp=prepared['xp'].copy();pp=prepared['pp'].copy();delta=np.zeros((4,4))
 if apply:xp,pp,delta,_=covariance_recovery.inject(xp,pp,spec['anchor'])
 if consume:chain.machine.commit(float(prepared['row']['t']))
 chain.x,chain.P,_,_=online.joseph(xp,pp,prepared['H'],prepared['nu'],prepared['R'],prepared['allowed'],prepared['w'])
 covariance_recovery.validate_covariance(chain.P);chain.last_index=k;chain.last_pose_id=chain.source_pose_ids[k]
 rec=dict(x=chain.x.copy(),P=chain.P.copy(),prior=xp,Pprior=pp,mask=prepared['allowed'],weight=prepared['w'])
 return rec,delta

def _s2_branch(chain,prepared,k,apply,end,packet,controls,prevention,core,model,spec,online):
 current,delta=_finish_s2(chain,prepared,k,apply,True,online,spec)
 rows=[_record(current,k,applied=apply)]
 for index in range(k+1,end):
  next_packet=_prepare_s2(chain,packet,controls,index,prevention,core,model,spec,online)
  rec,_=_finish_s2(chain,next_packet,index,False,False,online,spec)
  rows.append(_record(rec,index,suppressed=next_packet['candidate']))
 return _pack(rows,packet),delta

def _s3_candidate(chain,hist,first,k,row,prevention,core,model,spec,config_hash):
 first_index=next((i for i,t,_ in hist.packets if abs(t-first)<1e-8),None)
 selected=hist.replay_input(first_index,k) if first_index is not None else None
 decision=dict(index=k,first=float(first),checkpoint=None,historical_indices=[],historical_pose_ids=[],candidate_weights=[],disposition='HISTORY_INSUFFICIENT',cold_max_abs=None)
 if selected is None:return chain,hist,None,decision
 cp,suffix=selected;proposed=cp.filter_state;rebuilt=deepcopy(hist)
 decision['checkpoint']=cp.last_index;decision['checkpoint_pose_id']=cp.last_pose_id
 cx,cP,ci,cold_path=cold_replay(proposed,suffix,prevention,first,False,core,model,spec)
 while rebuilt.checkpoints and rebuilt.checkpoints[-1].last_index>cp.last_index:rebuilt.checkpoints.pop()
 rebuilt.next_checkpoint=cp.timestamp+1.-1e-10
 path=[]
 for index,t,saved in suffix:
  rec,_=checkpoint_filter.step(proposed,saved,index,prevention,t>=first,core,model,spec)
  path.append((index,rec['x'].copy(),rec['P'].copy()));decision['candidate_weights'].append([index,float(rec['weight'])])
  if t>=first:decision['historical_indices'].append(index);decision['historical_pose_ids'].append(proposed.source_pose_ids[index])
  if t>=rebuilt.next_checkpoint and index!=k:
   rebuilt.checkpoints.append(Checkpoint(index,t,config_hash,deepcopy(proposed),proposed.last_pose_id));rebuilt.next_checkpoint=t+1.-1e-10
 if ci!=proposed.last_index or len(path)!=len(cold_path):raise ValueError('cold end/length')
 for actual,expected in zip(path,cold_path):
  if actual[0]!=expected[0] or not np.allclose(actual[1],expected[1],atol=1e-10,rtol=1e-10) or not np.allclose(actual[2],expected[2],atol=1e-10,rtol=1e-10):raise ValueError('cold candidate path')
 decision['cold_max_abs']=max(float(np.max(np.abs(cx-proposed.x))),float(np.max(np.abs(cP-proposed.P))))
 decision['end_pose_id']=proposed.last_pose_id
 decision['disposition']=validate_candidate(chain.x,proposed.x,proposed.P,proposed.last_index,k,end_pose_id=proposed.last_pose_id,current_pose_id=row['pose_id'])
 if decision['disposition']=='ACCEPT':
  proposed.machine.first=first;proposed.machine.commit(row['t']);return proposed,rebuilt,rec,decision
 return chain,hist,None,decision

def _s3_branch(chain,hist,rec,row,k,first,apply,end,packet,controls,prevention,core,model,spec,config_hash):
 decision=dict(disposition='SUPPRESSED_CURRENT_EVENT',historical_indices=[],historical_pose_ids=[])
 if apply:
  chain,hist,candidate,decision=_s3_candidate(chain,hist,first,k,row,prevention,core,model,spec,config_hash)
  if candidate is not None:rec=candidate
 if not apply or decision['disposition']!='ACCEPT':
  chain.machine.first=first;chain.machine.commit(row['t'])
 hist.save(k,row['t'],chain)
 rows=[_record(rec,k,applied=apply and decision['disposition']=='ACCEPT')]
 for index in range(k+1,end):
  future=checkpoint_filter.frame(packet,controls,index)
  if not hist.append(index,future['t'],future):raise ValueError('branch source identity')
  next_rec,candidate=checkpoint_filter.step(chain,future,index,prevention,False,core,model,spec)
  # No later recovery opportunity changes either branch in this single-event estimand.
  hist.save(index,future['t'],chain);rows.append(_record(next_rec,index,suppressed=candidate))
 return _pack(rows,packet),decision

def iter_event_pairs(stage,packet,controls,arm,core,model,spec,online,natural_trace,natural_events,config_hash,target_indices=None):
 """Yield same-history event branches, preserving every original rejected attempt."""
 if stage not in ('S2','S3'):raise ValueError(stage)
 permitted=('C_P','D_P') if stage=='S2' else ('C_CP','D_CP')
 if arm not in permitted:raise ValueError(arm)
 events=list(natural_events.values()) if isinstance(natural_events,dict) and 'index' not in natural_events else ([natural_events] if isinstance(natural_events,dict) else list(natural_events))
 by_index={int(event['index']):event for event in events}
 if len(by_index)!=len(events):raise ValueError('duplicate natural event')
 targets=set(by_index) if target_indices is None else set(map(int,target_indices))
 if not targets<=set(by_index):raise ValueError('unregistered target')
 if not targets:return
 if not np.array_equal(packet['pose_id'],natural_trace['pose_id']):raise ValueError('natural source registry')
 prevention=arm.startswith('D');chain=checkpoint_filter.initial(packet,controls)
 hist=None
 if stage=='S3':hist=History(60,config_hash,packet['pose_id']);hist.save(-1,float(packet['t'][0])-1.,chain)
 last_attempt=-math.inf;prefix=hashlib.sha256();seen=set();effective_weights={};emitted_weights=[];prior_interventions=[]
 for k in range(max(targets)+1):
  row=checkpoint_filter.frame(packet,controls,k);prefix.update(state_hash(row).encode())
  if stage=='S2':
   prepared=_prepare_s2(chain,packet,controls,k,prevention,core,model,spec,online)
   candidate=bool(prepared['candidate']);first=chain.machine.first;before_prior=prepared['xp'].copy()
   if candidate!=(k in by_index):raise ValueError('natural S2 event schedule')
   if k in targets:
    before=dict(chain=chain,prepared=prepared,input_prefix=prefix.hexdigest(),effective_weight_history=effective_weights,emitted_weight_history=emitted_weights,prior_interventions=prior_interventions);start_hash=state_hash(before)
    left,right=deepcopy(before),deepcopy(before)
    if state_hash(left)!=start_hash or state_hash(right)!=start_hash:raise ValueError('branch start mismatch')
    end=int(np.searchsorted(packet['t'],float(row['t'])+20+1e-9,side='right'))
    on,delta=_s2_branch(left['chain'],left['prepared'],k,True,end,packet,controls,prevention,core,model,spec,online)
    off,off_delta=_s2_branch(right['chain'],right['prepared'],k,False,end,packet,controls,prevention,core,model,spec,online)
    if np.count_nonzero(off_delta):raise ValueError('OFF injection')
    if not np.array_equal(on['mask'],off['mask']):raise ValueError('branch mask separation')
    parity=_parity({key:on[key][0] for key in ('x','P','mask','weight')},natural_trace,k)
    if not np.allclose(before_prior,natural_trace['prior'][k],atol=1e-10,rtol=1e-10):raise ValueError('S2 pre-treatment mean parity')
    parity.update(start_hash_exact=True,source_ids_exact=bool(np.array_equal(on['pose_id'],off['pose_id'])),off_delta_zero=True,pretreatment_prior_matches_natural=True)
    decision=dict(delta_P=delta.tolist(),episode_first=float(first),later_recovery_suppressed=True)
    seen.add(k);yield EventPair(stage,arm,k,chain.source_pose_ids[k],float(row['t']),start_hash,before_prior,on,off,'APPLIED',parity,decision)
   rec,_=_finish_s2(chain,prepared,k,candidate,candidate,online,spec)
   if candidate:prior_interventions.append(dict(index=k,stage=stage,disposition='APPLIED'))
  else:
   if not hist.append(k,row['t'],row):raise ValueError('natural source identity')
   rec,candidate=checkpoint_filter.step(chain,row,k,prevention,False,core,model,spec)
   first=chain.machine.first;attempt=bool(candidate and first is not None and first>last_attempt);before_prior=rec['prior'].copy()
   if attempt!=(k in by_index):raise ValueError('natural S3 event schedule')
   if attempt:
    if k in targets:
     before=dict(chain=chain,history=hist,current=rec,last_attempt=last_attempt,input_prefix=prefix.hexdigest(),effective_weight_history=effective_weights,emitted_weight_history=emitted_weights,prior_interventions=prior_interventions);start_hash=state_hash(before)
     left,right=deepcopy(before),deepcopy(before)
     if state_hash(left)!=start_hash or state_hash(right)!=start_hash:raise ValueError('branch start mismatch')
     end=int(np.searchsorted(packet['t'],float(row['t'])+20+1e-9,side='right'))
     on,decision=_s3_branch(left['chain'],left['history'],left['current'],row,k,first,True,end,packet,controls,prevention,core,model,spec,config_hash)
     off,_=_s3_branch(right['chain'],right['history'],right['current'],row,k,first,False,end,packet,controls,prevention,core,model,spec,config_hash)
     if not np.array_equal(on['mask'],off['mask']):raise ValueError('branch mask separation')
     if decision['disposition']!=by_index[k]['disposition']:raise ValueError('original candidate disposition')
     parity=_parity({key:on[key][0] for key in ('x','P','mask','weight')},natural_trace,k)
     if 'pre_replay_prior' not in natural_trace or not np.allclose(before_prior,natural_trace['pre_replay_prior'][k],atol=1e-10,rtol=1e-10):raise ValueError('S3 pre-treatment mean parity')
     parity.update(start_hash_exact=True,source_ids_exact=bool(np.array_equal(on['pose_id'],off['pose_id'])),off_replacement_zero=True,pretreatment_prior_matches_natural=True)
     decision['later_recovery_suppressed']=True
     seen.add(k);yield EventPair(stage,arm,k,chain.source_pose_ids[k],float(row['t']),start_hash,before_prior,on,off,decision['disposition'],parity,decision)
    last_attempt=first
    chain,hist,new,natural_decision=_s3_candidate(chain,hist,first,k,row,prevention,core,model,spec,config_hash)
    prior_interventions.append(dict(index=k,stage=stage,disposition=natural_decision['disposition']))
    if new is not None:
     rec=new
     effective_weights.update({int(i):float(w) for i,w in natural_decision['candidate_weights']})
   hist.save(k,row['t'],chain)
  _parity(rec,natural_trace,k)
  effective_weights[k]=float(rec['weight']);emitted_weights.append([k,chain.source_pose_ids[k],float(rec['weight'])])
 if seen!=targets:raise ValueError('missing target event')
