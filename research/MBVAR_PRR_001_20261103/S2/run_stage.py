"""Sequential S2 development/evaluation. Scientific replays require published grant."""
import datetime
import hashlib
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
sys.path.insert(0,str(s))
from recovery import replay,validate_covariance
from endpoints import recovery_endpoints,snapshot_end_index

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False))
def save_trace(path,tr,pk,**extra):
 np.savez_compressed(path,**tr,pose_id=pk['pose_id'][tr['sample_index']],t=pk['t'][tr['sample_index']],**extra)
 return dict(file=path.name,sha256=sha(path),n=len(tr['x']))
def load_evaluation(key,pk):
 # Native_LoS has an underscore, so use first four identity fields.
 path=p.cache.parent/'evaluator_truth'/('_'.join(key.split('_')[:4])+'.npz')
 assert p.b.sha(path)==p.lock['evaluator_truth/'+path.name]
 with np.load(path) as f:truth=dict(f)
 ef=p.cache.parent/'evaluator_epsilon_r1'/(key+'.npz')
 assert p.b.sha(ef)==json.loads((s.parent/'S1/EPSILON_INPUTS.json').read_bytes())[ef.name]
 with np.load(ef) as f:epsilon=f['epsilon_s']
 assert np.array_equal(pk['pose_id'],truth['pose_id'])
 return truth,epsilon

def execute(phase,output):
 # Import the local grant explicitly despite inherited S1 search path.
 import importlib.util
 sp=importlib.util.spec_from_file_location('s2_grant',s/'grant.py');g=importlib.util.module_from_spec(sp);sp.loader.exec_module(g)
 grant=g.authorize(phase)
 assert not output.exists();output.mkdir(parents=True)
 meta=dict(stage='S2',phase=phase,grant=grant,utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,expected_main=320 if phase=='dev' else 640,expected_ablation=80 if phase=='dev' else 0)
 write_json(output/'RUN_MANIFEST.json',meta);(output/'FAILURES.jsonl').touch()
 index=[];scores=[];events=[];snapshot_rows=[];counts=[];event_endpoints=[]
 try:
  for route in ('R4','R5'):
   for bias in ('B0','L2'):
    for channel in ('Full','Native_LoS'):
     key=f'{route}_aB_m0_{bias}_{channel}';pk=p.read(key);truth,epsilon=load_evaluation(key,pk)
     for seed in (range(10) if phase=='dev' else range(10,30)):
      stop=os.environ.get('MANAGED_PROCESS_STOP_FILE')
      if stop and Path(stop).exists():raise InterruptedError('owner stop')
      ct=p.read(f'{route}_aB_m0_{bias}_{seed}');common=None
      baselines={}
      for arm in ('A','B','C_P','D_P'):
       tr,ev=replay(pk,ct,arm,p.b.core,p.b.model,p.spec,p.online)
       expected=p.b.pb.gated_mask(pk['z'],pk['muBASE'],pk['R'],ct['ds'],ct['gy'],ct['dt'],np.r_[ct['x0'],0.],pk['P0'],p.spec,p.b.model)
       assert np.array_equal(tr['mask'],expected)
       assert np.isfinite(tr['x']).all() and np.isfinite(tr['P']).all()
       identity=dict(route=route,bias=bias,channel=channel,seed=seed,arm=arm,kind='P')
       f=output/f'{key}_{seed}_{arm}.npz';index.append(dict(**identity,**save_trace(f,tr,pk)))
       scores.extend(dict(**identity,**row) for row in score(pk,tr,truth,channel,epsilon))
       events.extend(dict(**identity,**row) for row in ev);counts.append(dict(**identity,recoveries=len(ev)))
       for event in ev:
        ei=event['index'];event_endpoints.append(dict(**identity,event_index=ei,**recovery_endpoints(pk['t'][ei:],tr['x'][ei:],truth['truth'][ei:],pk['t'][ei],pretreatment_prior=tr['prior'][ei],pretreatment_truth=truth['truth'][ei])))
       if arm=='A':common=tr;common_schedule=tr['candidate'].copy()
       if arm in ('A','B'):
        baseline='W0' if arm=='A' else 'W-d0-DS'
        source=s.parent/'S1/runs'/('DEV_001' if phase=='dev' else 'EVAL_001')/f'{key}_{seed}_{baseline}.npz'
        with np.load(source) as old:
         assert np.allclose(tr['x'],old['x'],atol=1e-10,rtol=1e-10)
         assert np.allclose(tr['P'],old['P'],atol=1e-10,rtol=1e-10)
        baselines[arm]=tr
      if phase=='dev':
       axes='heading' if seed<=3 else ('tangent_heading_bg' if seed<=6 else 'tangent_heading')
       gate='O' if seed>=7 else 'F'
       tr,ev=replay(pk,ct,'D_P',p.b.core,p.b.model,p.spec,p.online,axes=axes,gate_mode=gate)
       label='heading_only' if seed<=3 else ('bg_axis' if seed<=6 else 'O_gate')
       identity=dict(route=route,bias=bias,channel=channel,seed=seed,arm=label,kind='ablation')
       f=output/f'{key}_{seed}_{label}.npz';index.append(dict(**identity,**save_trace(f,tr,pk)))
       scores.extend(dict(**identity,**row) for row in score(pk,tr,truth,channel,epsilon));events.extend(dict(**identity,**row) for row in ev);counts.append(dict(**identity,recoveries=len(ev)))
       for event in ev:
        ei=event['index'];event_endpoints.append(dict(**identity,event_index=ei,**recovery_endpoints(pk['t'][ei:],tr['x'][ei:],truth['truth'][ei:],pk['t'][ei],pretreatment_prior=tr['prior'][ei],pretreatment_truth=truth['truth'][ei])))
       if seed==0:
        starts={int(np.searchsorted(pk['t'],time)) for time in (30,60,90) if time<=pk['t'][-1]}
        # First packet of each virtual baseline latch is a causal diagnostic start.
        episode=common['episode_first'];active=episode>=0
        starts.update(np.flatnonzero(active&(episode!=np.r_[-1.,episode[:-1]])).tolist())
        selected=sorted(k for k in starts if k>=0)[:10]
        counts.append(dict(route=route,bias=bias,channel=channel,seed=seed,kind='M_eligibility',eligible=len(starts),selected=len(selected),missing=10-len(selected)))
        for number,start in enumerate(selected):
         end=snapshot_end_index(pk['t'],start);initial=(common['x'][start-1].copy(),common['P'][start-1].copy()) if start else (np.r_[ct['x0'],0.],pk['P0'].copy())
         for arm in ('A','B','C_P','D_P'):
          tr,ev=replay(pk,ct,arm,p.b.core,p.b.model,p.spec,p.online,schedule=common_schedule,start=start,initial=initial,end=end)
          identity=dict(route=route,bias=bias,channel=channel,seed=0,arm=arm,kind='M',snapshot=number,start_index=start)
          f=output/f'{key}_snapshot{number}_{arm}.npz';index.append(dict(**identity,**save_trace(f,tr,pk,initial_x=initial[0],initial_P=initial[1],common_schedule=common_schedule[start:end])))
          snapshot_rows.append(dict(**identity,**recovery_endpoints(pk['t'][start:end],tr['x'],truth['truth'][start:end],pk['t'][start],pretreatment_prior=common['prior'][start],pretreatment_truth=truth['truth'][start])))
          events.extend(dict(**identity,**row) for row in ev)
      print(key,seed,flush=True)
 except Exception as error:
  (output/'FAILURES.jsonl').write_text(json.dumps(dict(error=repr(error),key=locals().get('key'),seed=locals().get('seed'),arm=locals().get('arm')))+'\n');raise
 finally:
  write_json(output/'TRACE_INDEX.json',index);write_json(output/'EVENTS.json',events)
  pd.DataFrame(scores).to_csv(output/'SCORES_PER_SEED.csv',index=False)
  pd.DataFrame(snapshot_rows).to_csv(output/'SNAPSHOT_ENDPOINTS.csv',index=False)
  pd.DataFrame(counts).to_csv(output/'RECOVERY_COUNTS.csv',index=False)
  pd.DataFrame(event_endpoints).to_csv(output/'EVENT_ENDPOINTS.csv',index=False)
 main=pd.DataFrame(scores);primary=main[main.kind=='P'].copy();primary['arm']=primary.arm.replace({'A':'W0'})
 paired_summary(primary).to_csv(output/'PAIRED_SUMMARY.csv',index=False)
 # Paired factorial contrasts share identical seed and condition keys.
 rows=[]
 for keys,table in main[main.kind=='P'].groupby(['route','bias','channel','seed','window']):
  table=table.set_index('arm',verify_integrity=True)
  for metric in ('heading_rmse_deg','xy_rmse_m','nees4','heading_coverage95'):
   A,B,C,D=(table.loc[arm,metric] for arm in ('A','B','C_P','D_P'))
   rows.append(dict(zip(('route','bias','channel','seed','window'),keys),metric=metric,D_minus_B=D-B,D_minus_C=D-C,interaction=D-B-C+A))
 pd.DataFrame(rows).to_csv(output/'FACTORIAL_CONTRASTS.csv',index=False)
 ablations=[]
 if phase=='dev':
  reference=main[(main.kind=='P')&(main.arm=='D_P')].set_index(['route','bias','channel','seed','window'],verify_integrity=True)
  for _,row in main[main.kind=='ablation'].iterrows():
   key=tuple(row[k] for k in ('route','bias','channel','seed','window'));ref=reference.loc[key]
   for metric in ('heading_rmse_deg','xy_rmse_m','nees4','heading_coverage95'):
    ablations.append(dict(zip(('route','bias','channel','seed','window'),key),ablation=row['arm'],metric=metric,reference=float(ref[metric]),ablation_value=float(row[metric]),paired_delta=float(row[metric]-ref[metric])))
 pd.DataFrame(ablations).to_csv(output/'ABLATION_PAIRED_CONTRASTS.csv',index=False)
 assert sum(v['kind']=='P' for v in index)==meta['expected_main']
 assert sum(v['kind']=='ablation' for v in index)==meta['expected_ablation']
 meta.update(status='COMPLETE',n=len(index),utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat());write_json(output/'RUN_MANIFEST.json',meta)
if __name__=='__main__':execute(sys.argv[1],Path(sys.argv[2]))
