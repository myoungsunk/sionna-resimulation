"""Reproduce the registered R4 seed0 Full t=60s M positive controls."""
import csv
import importlib.util
import hashlib
import json
from pathlib import Path
import numpy as np
from branching import ROOT,checkpoint_filter,covariance_recovery

def _sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def _read(path,expected):
 if _sha(path)!=expected:raise ValueError('positive-control source hash '+str(path))
 with np.load(path) as z:return dict(z)
def _same(actual,original,ids):
 delta={}
 for field in ('x','P'):
  delta[field]=float(np.max(np.abs(actual[field]-original[field])))
  if not np.allclose(actual[field],original[field],atol=1e-10,rtol=1e-10):raise ValueError('R4 M parity '+field)
 if not np.array_equal(actual['mask'],original['mask']) or not np.array_equal(ids,original['pose_id']):raise ValueError('R4 M mask/source identity')
 return dict(passed=True,max_state_abs=delta['x'],max_covariance_abs=delta['P'],mask_exact=True,source_ids_exact=True)
def _endpoint(t,x,truth):
 head=np.abs(np.degrees(np.angle(np.exp(1j*(x[:,2]-truth[:,2])))));xy=np.linalg.norm(x[:,:2]-truth[:,:2],axis=1)
 accurate=(head<=1)&(xy<=.1);first=None;recovered=None
 for i,safe in enumerate(accurate):
  if safe:
   if first is None:first=float(t[i])
   if t[i]-first>=2-1e-9:recovered=float(t[i]-t[0]);break
  else:first=None
 result=dict(recovery_s=recovered)
 for duration in (10,20):
  mask=t<=t[0]+duration+1e-9
  result[f'heading_integral_{duration}s']=float(np.trapezoid(head[mask],t[mask]))
  result[f'xy_integral_{duration}s']=float(np.trapezoid(xy[mask],t[mask]))
 return result

def positive_controls(core,model,spec,online,read_packet,read_controls,*,root=None):
 """Return a JSON receipt. Caller authenticates GO and scoring-only truth first."""
 root=ROOT if root is None else Path(root)
 receipt=dict(status='PASS',scope='original R4 Full seed0 common-A-history M at60s',controls=[],comparisons=[])
 benefit_path=root/'POST_S3_PROPOSER_20261104/P0/BENEFIT.csv'
 with benefit_path.open(newline='',encoding='utf-8-sig') as handle:benefits=list(csv.DictReader(handle))
 s2=root/'S2';s2_repair=s2/'runs/DEV_REPAIR_001'
 s2_index=json.loads((s2_repair/'TRACE_INDEX.json').read_bytes())
 s3_source=root/'S3/runs/DEV_001';s3_index=json.loads((s3_source/'TRACE_INDEX.json').read_bytes())
 s3_manifest=json.loads((s3_source/'RUN_MANIFEST.json').read_bytes());config=s3_manifest['config_hash']
 # These helpers evaluate completed reproductions only; truth never enters the filters.
 module_spec=importlib.util.spec_from_file_location('n0b_positive_scoring_loader',root/'S2/run_stage.py')
 source_loader=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(source_loader)
 for bias in ('B0','L2'):
  key=f'R4_aB_m0_{bias}_Full';packet=read_packet(key);controls=read_controls(f'R4_aB_m0_{bias}_0')
  start=int(np.searchsorted(packet['t'],60.));end=int(np.searchsorted(packet['t'],float(packet['t'][start])+20+1e-9,side='right'))
  if abs(float(packet['t'][start])-60)>1e-9:raise ValueError('registered60s checkpoint absent')
  truth,_=source_loader.load_evaluation(key,packet)
  outputs={}
  baseline_record=next(r for r in s2_index if r['kind']=='P' and r['route']=='R4' and r['bias']==bias and r['channel']=='Full' and r['seed']==0 and r['arm']=='A')
  baseline=_read(s2/baseline_record['directory']/baseline_record['file'],baseline_record['sha256'])
  initial=(baseline['x'][start-1].copy(),baseline['P'][start-1].copy()) if start else (np.r_[controls['x0'],0.],packet['P0'].copy())
  for arm in ('A','B','C_P','D_P'):
   old_record=next(r for r in s2_index if r['kind']=='M' and r['route']=='R4' and r['bias']==bias and r['channel']=='Full' and r['arm']==arm and r['start_index']==start)
   old=_read(s2/old_record['directory']/old_record['file'],old_record['sha256'])
   if not np.allclose(initial[0],old['initial_x'],atol=1e-10,rtol=1e-10) or not np.allclose(initial[1],old['initial_P'],atol=1e-10,rtol=1e-10):raise ValueError('S2 M initial state parity')
   actual,_=covariance_recovery.replay(packet,controls,arm,core,model,spec,online,schedule=baseline['candidate'],start=start,initial=initial,end=end)
   parity=_same(actual,old,packet['pose_id'][start:end]);outputs[('S2',arm)]=_endpoint(packet['t'][start:end],actual['x'],truth['truth'][start:end])
   receipt['controls'].append(dict(stage='S2',bias=bias,arm=arm,start_index=start,source_file=old_record['file'],source_sha256=old_record['sha256'],parity=parity))
  baseline3,_,_,snapshots,_=checkpoint_filter.replay(packet,controls,'A',core,model,spec,config,capture_snapshots=True)
  state=snapshots[start]
  # Original M bookkeeping assigns its variant by the sorted selected start indices.
  ordered=sorted(snapshots)[:10]
  if start not in ordered:raise ValueError('registered R4 M60s outside original cap')
  variant='M'+str(ordered.index(start))
  for arm in ('A','B','C_CP','D_CP'):
   old_record=next(r for r in s3_index if r['kind']=='M' and r['route']=='R4' and r['bias']==bias and r['channel']=='Full' and r['arm']==arm and r['variant']==variant)
   old=_read(s3_source/old_record['file'],old_record['sha256'])
   if not np.allclose(state[0].x,old['initial_x'],atol=1e-10,rtol=1e-10) or not np.allclose(state[0].P,old['initial_P'],atol=1e-10,rtol=1e-10):raise ValueError('S3 M initial state parity')
   actual,_,_,_,_=checkpoint_filter.replay(packet,controls,arm,core,model,spec,config,start=start,end=end,initial_state=state,common_schedule=baseline3['candidate'],common_first=baseline3['episode_first'])
   parity=_same(actual,old,packet['pose_id'][start:end]);outputs[('S3',arm)]=_endpoint(packet['t'][start:end],actual['x'],truth['truth'][start:end])
   receipt['controls'].append(dict(stage='S3',bias=bias,arm=arm,start_index=start,source_file=old_record['file'],source_sha256=old_record['sha256'],parity=parity))
  for stage,on,off in (('S2','C_P','A'),('S2','D_P','B'),('S3','C_CP','A'),('S3','D_CP','B')):
   expected=next(row for row in benefits if row['stage']==stage and row['route']=='R4' and row['bias']==bias and row['channel']=='Full' and int(row['seed'])==0 and int(row['start_index'])==start and row['on']==on and row['off']==off)
   actual={};maximum=0.
   for field in ('heading_integral_10s','xy_integral_10s','heading_integral_20s','xy_integral_20s','recovery_s'):
    left,right=outputs[(stage,on)][field],outputs[(stage,off)][field];difference=None if left is None or right is None else left-right
    text=expected['delta_'+field]
    if difference is None:
     if text!='':raise ValueError('R4 recovery censoring parity')
    else:
     if text=='' or not np.isclose(difference,float(text),atol=1e-10,rtol=1e-10):raise ValueError('R4 BENEFIT parity '+field)
     maximum=max(maximum,abs(difference-float(text)))
    actual['delta_'+field]=difference
   receipt['comparisons'].append(dict(stage=stage,bias=bias,on=on,off=off,start_index=start,max_abs=maximum,values=actual,passed=True))
 receipt['source_benefit_sha256']=_sha(benefit_path)
 receipt['source_metadata_sha256']={str(path.relative_to(root)).replace('\\','/'):_sha(path) for path in (s2_repair/'TRACE_INDEX.json',s3_source/'TRACE_INDEX.json',s3_source/'RUN_MANIFEST.json')}
 if len(receipt['controls'])!=16 or len(receipt['comparisons'])!=8:raise ValueError('R4 positive-control denominator')
 return receipt
