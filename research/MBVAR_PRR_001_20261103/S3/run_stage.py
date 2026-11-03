"""S3 phase runner. Published grants are mandatory for any scientific replay."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import numpy as np
import pandas as pd
s=Path(__file__).resolve().parent
sys.path.insert(0,str(s.parent/'S1'))
import parity as p
from score import score
from summary import paired_summary
sys.path.insert(0,str(s.parent/'S2'))
from endpoints import recovery_endpoints,snapshot_end_index
sys.path.insert(0,str(s))
from foreground import replay,state_record

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False))
def save_trace(path,tr,pk,**extra):
 indices=tr['sample_index'];np.savez_compressed(path,**tr,pose_id=pk['pose_id'][indices],t=pk['t'][indices],**extra)
 return dict(file=path.name,sha256=sha(path),n=len(indices))
def evaluator(key,pk):
 tf=p.cache.parent/'evaluator_truth'/('_'.join(key.split('_')[:4])+'.npz');assert p.b.sha(tf)==p.lock['evaluator_truth/'+tf.name]
 with np.load(tf) as f:truth=dict(f)
 ef=p.cache.parent/'evaluator_epsilon_r1'/(key+'.npz');assert p.b.sha(ef)==json.loads((s.parent/'S1/EPSILON_INPUTS.json').read_bytes())[ef.name]
 with np.load(ef) as f:eps=f['epsilon_s']
 assert np.array_equal(pk['pose_id'],truth['pose_id']);return truth,eps

def execute(phase,output):
 sp=importlib.util.spec_from_file_location('s3_grant',s/'grant.py');g=importlib.util.module_from_spec(sp);sp.loader.exec_module(g);grant=g.authorize(phase)
 config=sha(s/'RULES.json');assert not output.exists();output.mkdir(parents=True)
 meta=dict(stage='S3',phase=phase,grant=grant,config_hash=config,utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,expected_main=320 if phase=='dev' else 640,expected_auxiliary=48 if phase=='dev' else 0)
 write_json(output/'RUN_MANIFEST.json',meta);(output/'FAILURES.jsonl').touch()
 index=[];scores=[];events=[];timings=[];snaprows=[];counts=[];endpoints=[]
 def record(identity,tr,ev,retro,timing,pk,truth,eps,**extra):
  label=identity['arm'];suffix=identity.get('variant','main')
  name=f"{identity['route']}_aB_m0_{identity['bias']}_{identity['channel']}_{identity['seed']}_{label}_{suffix}"
  path=output/(name+'.npz');index.append(dict(**identity,**save_trace(path,tr,pk,**extra)))
  events.extend(dict(**identity,**event) for event in ev);timings.append(dict(**identity,**timing));counts.append(dict(**identity,attempts=len(ev),adoptions=sum(e['disposition']=='ACCEPT' for e in ev)))
  write_json(output/(name+'_EVENTS.json'),ev)
  # The retrospective curve is a separate output with its creation time retained.
  values=[(emitted,i,x,P) for emitted,path in retro for i,x,P in path]
  if values:
   np.savez_compressed(output/(name+'_RETROSPECTIVE.npz'),created_index=np.array([v[0] for v in values]),sample_index=np.array([v[1] for v in values]),x=np.array([v[2] for v in values]),P=np.array([v[3] for v in values]))
  if identity['kind']!='M':
   scores.extend(dict(**identity,**row) for row in score(pk,tr,truth,identity['channel'],eps))
   for event in ev:
    ei=event['index']
    endpoints.append(dict(**identity,event_index=ei,disposition=event['disposition'],**recovery_endpoints(pk['t'][ei:],tr['x'][ei:],truth['truth'][ei:],pk['t'][ei],pretreatment_prior=tr['pre_replay_prior'][ei],pretreatment_truth=truth['truth'][ei])))
 try:
  for route in ('R4','R5'):
   for bias in ('B0','L2'):
    for channel in ('Full','Native_LoS'):
     key=f'{route}_aB_m0_{bias}_{channel}';pk=p.read(key);truth,eps=evaluator(key,pk)
     for seed in (range(10) if phase=='dev' else range(10,30)):
      sf=os.environ.get('MANAGED_PROCESS_STOP_FILE')
      if sf and Path(sf).exists():raise InterruptedError('owner stopped')
      ct=p.read(f'{route}_aB_m0_{bias}_{seed}');main={};selected=None;baseline=None
      for arm in ('A','B','C_CP','D_CP'):
       tr,ev,retro,snap,timing=replay(pk,ct,arm,p.b.core,p.b.model,p.spec,config,timed=phase=='dev' and seed==0,capture_snapshots=phase=='dev' and seed==0 and arm=='A')
       ident=dict(route=route,bias=bias,channel=channel,seed=seed,arm=arm,kind='P')
       record(ident,tr,ev,retro,timing,pk,truth,eps)
       expected=p.b.pb.gated_mask(pk['z'],pk['muBASE'],pk['R'],ct['ds'],ct['gy'],ct['dt'],np.r_[ct['x0'],0.],pk['P0'],p.spec,p.b.model)
       assert np.array_equal(tr['mask'],expected)
       if arm in ('A','B'):
        name='W0' if arm=='A' else 'W-d0-DS';source=s.parent/'S1/runs'/('DEV_001' if phase=='dev' else 'EVAL_001')/f'{key}_{seed}_{name}.npz'
        with np.load(source) as prior:assert np.allclose(tr['x'],prior['x'],atol=1e-10,rtol=1e-10) and np.allclose(tr['P'],prior['P'],atol=1e-10,rtol=1e-10)
       if seed==0 and phase=='dev':
        main[arm]=tr
        if arm=='A':selected={k:snap[k] for k in sorted(snap)[:10]};baseline=tr
      if phase=='dev' and seed==0:
       counts.append(dict(route=route,bias=bias,channel=channel,seed=0,kind='M_eligibility',selected=len(selected),missing=10-len(selected)))
       for arm in ('C_CP','D_CP'):
        control='A' if arm=='C_CP' else 'B'
        tr,ev,retro,_,timing=replay(pk,ct,arm,p.b.core,p.b.model,p.spec,config,identity=True)
        assert np.allclose(tr['x'],main[control]['x'],atol=1e-10,rtol=1e-10) and np.allclose(tr['P'],main[control]['P'],atol=1e-10,rtol=1e-10)
        ident=dict(route=route,bias=bias,channel=channel,seed=0,arm=arm,kind='identity',variant='identity');record(ident,tr,ev,retro,timing,pk,truth,eps)
        for seconds in (10,30):
         tr,ev,retro,_,timing=replay(pk,ct,arm,p.b.core,p.b.model,p.spec,config,seconds=seconds)
         ident=dict(route=route,bias=bias,channel=channel,seed=0,arm=arm,kind='length',variant=f'history{seconds}');record(ident,tr,ev,retro,timing,pk,truth,eps)
       for number,(start,state) in enumerate(selected.items()):
        end=snapshot_end_index(pk['t'],start)
        write_json(output/f'{key}_M{number}_INITIAL.json',dict(start_index=start,chain=state_record(state[0]),history_last_index=state[1].last_index,history_seconds=state[1].seconds,checkpoints=[dict(last_index=cp.last_index,timestamp=cp.timestamp,config_hash=cp.config_hash,chain=state_record(cp.filter_state)) for cp in state[1].checkpoints]))
        for arm in ('A','B','C_CP','D_CP'):
         tr,ev,retro,_,timing=replay(pk,ct,arm,p.b.core,p.b.model,p.spec,config,start=start,end=end,initial_state=state,common_schedule=baseline['candidate'],common_first=baseline['episode_first'])
         ident=dict(route=route,bias=bias,channel=channel,seed=0,arm=arm,kind='M',variant=f'M{number}')
         record(ident,tr,ev,retro,timing,pk,truth,eps,initial_x=state[0].x,initial_P=state[0].P)
         snaprows.append(dict(**ident,start_index=start,**recovery_endpoints(pk['t'][start:end],tr['x'],truth['truth'][start:end],pk['t'][start],pretreatment_prior=baseline['prior'][start],pretreatment_truth=truth['truth'][start])))
      print(key,seed,flush=True)
 except Exception as error:
  (output/'FAILURES.jsonl').write_text(json.dumps(dict(error=repr(error),key=locals().get('key'),seed=locals().get('seed'),arm=locals().get('arm')))+'\n');raise
 finally:
  write_json(output/'TRACE_INDEX.json',index);write_json(output/'EVENTS.json',events)
  pd.DataFrame(scores).to_csv(output/'SCORES_PER_SEED.csv',index=False);pd.DataFrame(timings).to_csv(output/'TIMING.csv',index=False)
  pd.DataFrame(counts).to_csv(output/'RECOVERY_COUNTS.csv',index=False);pd.DataFrame(snaprows).to_csv(output/'SNAPSHOT_ENDPOINTS.csv',index=False);pd.DataFrame(endpoints).to_csv(output/'EVENT_ENDPOINTS.csv',index=False)
 table=pd.DataFrame(scores);primary=table[table.kind=='P'].copy();primary['arm']=primary.arm.replace({'A':'W0'})
 paired_summary(primary).to_csv(output/'PAIRED_SUMMARY.csv',index=False)
 contrasts=[]
 for keys,group in table[table.kind=='P'].groupby(['route','bias','channel','seed','window']):
  by=group.set_index('arm',verify_integrity=True)
  for metric in ('heading_rmse_deg','xy_rmse_m','nees4','heading_coverage95'):
   A,B,C,D=(by.loc[a,metric] for a in ('A','B','C_CP','D_CP'))
   contrasts.append(dict(zip(('route','bias','channel','seed','window'),keys),metric=metric,D_minus_B=D-B,D_minus_C=D-C,interaction=D-B-C+A))
 pd.DataFrame(contrasts).to_csv(output/'FACTORIAL_CONTRASTS.csv',index=False)
 ref=table[table.kind=='P'].set_index(['route','bias','channel','seed','window','arm'],verify_integrity=True);comparisons=[]
 for _,row in table[table.kind.isin(['length','identity'])].iterrows():
  keys=tuple(row[k] for k in ('route','bias','channel','seed','window','arm'));old=ref.loc[keys]
  for metric in ('heading_rmse_deg','xy_rmse_m','nees4','heading_coverage95'):comparisons.append(dict(zip(('route','bias','channel','seed','window','arm'),keys),variant=row['variant'],metric=metric,paired_delta=row[metric]-old[metric]))
 pd.DataFrame(comparisons).to_csv(output/'AUXILIARY_PAIRED_CONTRASTS.csv',index=False)
 # Cross-stage D_CP minus D_P uses the same phase, RF and sensor seed.
 previous=pd.read_csv(s.parent/'S2/runs'/('DEV_001' if phase=='dev' else 'EVAL_001')/'SCORES_PER_SEED.csv');previous=previous[(previous.kind=='P')&(previous.arm=='D_P')].set_index(['route','bias','channel','seed','window'],verify_integrity=True)
 cross=[]
 for _,row in table[(table.kind=='P')&(table.arm=='D_CP')].iterrows():
  keys=tuple(row[k] for k in ('route','bias','channel','seed','window'));old=previous.loc[keys]
  for metric in ('heading_rmse_deg','xy_rmse_m','nees4','heading_coverage95'):cross.append(dict(zip(('route','bias','channel','seed','window'),keys),metric=metric,D_CP_minus_D_P=row[metric]-old[metric]))
 pd.DataFrame(cross).to_csv(output/'CROSS_STAGE_PAIRED.csv',index=False)
 assert sum(v['kind']=='P' for v in index)==meta['expected_main'];assert sum(v['kind'] in ('identity','length') for v in index)==meta['expected_auxiliary']
 meta.update(status='COMPLETE',n=len(index),utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat());write_json(output/'RUN_MANIFEST.json',meta)
 write_json(output/'ARTIFACT_HASHES.json',{path.name:sha(path) for path in sorted(output.iterdir()) if path.is_file() and path.name!='ARTIFACT_HASHES.json'})
if __name__=='__main__':execute(sys.argv[1],Path(sys.argv[2]))
