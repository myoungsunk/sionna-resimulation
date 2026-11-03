"""Bounded additive repair. Authorize before loading any scientific input."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
s=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write_json(path,value):path.write_text(json.dumps(value,indent=2,allow_nan=False))
def execute(output):
 sp=importlib.util.spec_from_file_location('s2_repair_grant',s/'grant.py');g=importlib.util.module_from_spec(sp);sp.loader.exec_module(g)
 grant=g.authorize('repair')
 import numpy as np
 import pandas as pd
 import run_stage as runner
 from endpoints import recovery_endpoints,snapshot_end_index
 p=runner.p
 scope=json.loads((s/'REPAIR_SCOPE.json').read_bytes());source=s/scope['source_directory'];index=json.loads((source/'TRACE_INDEX.json').read_bytes())
 assert not output.exists();output.mkdir(parents=True)
 manifest=dict(stage='S2',phase='dev_repair',grant=grant,source_commit=scope['source_commit'],source_manifest_sha256=sha(source/'RUN_MANIFEST.json'),source_index_sha256=sha(source/'TRACE_INDEX.json'),source_code_commit=scope['source_code_commit'],utc_start=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,maximum_scientific_replays=8)
 write_json(output/'RUN_MANIFEST.json',manifest);(output/'FAILURES.jsonl').touch()
 fixed=set(scope['replay_files']);assert len(fixed)==8 and fixed=={r['file'] for r in index if r['file'] in fixed and r['kind']=='M'}
 merged=[];snapshot_rows=[];event_rows=[];corrections=[];replayed_events=[]
 try:
  # Validate every immutable original trace, including all400 reused main/ablation results.
  for row in index:
   if sha(source/row['file'])!=row['sha256']:raise ValueError('immutable trace hash '+row['file'])
  identities={(r['route'],r['bias'],r['channel'],r['seed'],r['arm'],r['kind'],r.get('snapshot')):r for r in index}
  for row in index:
   rec=dict(row);rec.update(origin='IMMUTABLE_DEV_001',directory=scope['source_directory'])
   if row['file'] in fixed:
    key=f"{row['route']}_aB_m0_{row['bias']}_{row['channel']}";pk=p.read(key);ct=p.read(f"{row['route']}_aB_m0_{row['bias']}_{row['seed']}")
    baseline=identities[(row['route'],row['bias'],row['channel'],row['seed'],'A','P',None)]
    with np.load(source/baseline['file']) as b:common_schedule=b['candidate'].copy()
    with np.load(source/row['file']) as old:
     initial=(old['initial_x'].copy(),old['initial_P'].copy());start=row['start_index'];end=snapshot_end_index(pk['t'],start)
     if end!=start+row['n']+1:raise ValueError('repair not exactly one endpoint packet')
     tr,events=runner.replay(pk,ct,row['arm'],p.b.core,p.b.model,p.spec,p.online,schedule=common_schedule,start=start,initial=initial,end=end)
     for field in ('x','P','prior','Pprior','H','h','K','mask','weight','delta_P'):
      if not np.array_equal(tr[field][:-1],old[field]):raise ValueError('repair changes original prefix '+field)
    identity={k:v for k,v in row.items() if k not in ('file','sha256','n')}
    actual=runner.save_trace(output/row['file'],tr,pk,initial_x=initial[0],initial_P=initial[1],common_schedule=common_schedule[start:end])
    rec.update(**actual,origin='REPAIRED_ENDPOINT',directory=str(output.relative_to(s)).replace('\\','/'))
    corrections.append(dict(file=row['file'],original_sha256=row['sha256'],repaired_sha256=actual['sha256'],original_n=row['n'],repaired_n=actual['n'],identical_original_prefix=True))
    replayed_events.extend(dict(**identity,**event) for event in events)
   merged.append(rec)
  if len(corrections)!=8:raise ValueError('repair cap')
  for row in merged:
   if row['kind']!='M':continue
   key=f"{row['route']}_aB_m0_{row['bias']}_{row['channel']}";pk=p.read(key);truth,_=runner.load_evaluation(key,pk)
   baseline=identities[(row['route'],row['bias'],row['channel'],row['seed'],'A','P',None)]
   with np.load(source/baseline['file']) as base:before=base['prior'][row['start_index']].copy()
   path=s/row['directory']/row['file']
   with np.load(path) as tr:
    sel=tr['sample_index'];start=row['start_index']
    endpoint=recovery_endpoints(tr['t'],tr['x'],truth['truth'][sel],pk['t'][start],pretreatment_prior=before,pretreatment_truth=truth['truth'][start])
   snapshot_rows.append(dict(**{k:v for k,v in row.items() if k not in ('file','sha256','n','origin','directory')},**endpoint))
  original_events=json.loads((source/'EVENTS.json').read_bytes())
  # Event cohorts are defined immediately before treatment in each arm; ablations included.
  for event in original_events:
   if event['kind']=='M':continue
   row=identities[(event['route'],event['bias'],event['channel'],event['seed'],event['arm'],event['kind'],None)]
   key=f"{event['route']}_aB_m0_{event['bias']}_{event['channel']}";pk=p.read(key);truth,_=runner.load_evaluation(key,pk);ei=event['index']
   with np.load(source/row['file']) as tr:
    endpoint=recovery_endpoints(pk['t'][ei:],tr['x'][ei:],truth['truth'][ei:],pk['t'][ei],pretreatment_prior=tr['prior'][ei],pretreatment_truth=truth['truth'][ei])
   event_rows.append(dict(**{k:v for k,v in event.items() if k not in ('index','time','episode_first','common_schedule')},event_index=ei,**endpoint))
 except Exception as error:
  (output/'FAILURES.jsonl').write_text(json.dumps(dict(error=repr(error)))+'\n');raise
 finally:
  write_json(output/'TRACE_INDEX.json',merged);write_json(output/'REPLAY_CORRECTIONS.json',corrections)
  write_json(output/'REPLAYED_EVENTS.json',replayed_events)
  pd.DataFrame(snapshot_rows).to_csv(output/'SNAPSHOT_ENDPOINTS_CORRECTED.csv',index=False)
  pd.DataFrame(event_rows).to_csv(output/'EVENT_ENDPOINTS_CORRECTED.csv',index=False)
 # Explicit pointers preserve original scores without recomputing or copying them.
 write_json(output/'UNCHANGED_RESULT_REFERENCES.json',{name:dict(source_directory=scope['source_directory'],sha256=sha(source/name)) for name in scope['source_metadata_hashes'] if name not in ('SNAPSHOT_ENDPOINTS.csv','EVENT_ENDPOINTS.csv')})
 manifest.update(status='COMPLETE',scientific_replays=8,reused_main_ablation_traces=sum(r['kind'] in ('P','ablation') for r in index),reused_snapshot_traces=sum(r['kind']=='M' and r['file'] not in fixed for r in index),snapshot_endpoint_rows=len(snapshot_rows),event_endpoint_rows=len(event_rows),utc_end=datetime.datetime.now(datetime.timezone.utc).isoformat())
 write_json(output/'RUN_MANIFEST.json',manifest)
 write_json(output/'ARTIFACT_HASHES.json',{p.name:sha(p) for p in sorted(output.iterdir()) if p.is_file() and p.name!='ARTIFACT_HASHES.json'})
if __name__=='__main__':execute(Path(sys.argv[1]))
