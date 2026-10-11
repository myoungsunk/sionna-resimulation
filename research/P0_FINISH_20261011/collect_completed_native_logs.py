#!/usr/bin/env python3
"""Read-only recovery of COMPLETED Stage A logs. No source or science mutation.
The first Native runs printed exact per-point results but hidden output dirs
were omitted by artifact upload. Preserve this as LOG_ONLY evidence explicitly.
Fresh V03 raw H/CSV is separately re-executed with non-hidden output.
"""
from __future__ import annotations
import argparse,ast,csv,json,re,subprocess
from pathlib import Path
REPO='myoungsunk/sionna-resimulation'
RUNS=[(38125306839,114428371207,'native_family_and_pole'),(38126178840,114430906793,'fresh_pole_first_execution')]

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 receipts=[];family=[];near=[]
 for rid,jid,name in RUNS:
  response=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/runs/{rid}'],text=True)
  r=json.loads(response);assert r['status']=='completed','Only completed runs may be archived'
  data=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/jobs/{jid}/logs']);log=data.decode('utf-8-sig')
  (a.out/(name+'.log')).write_text(log,encoding='utf-8')
  rec=dict(run_id=rid,job_id=jid,source_commit=r['head_sha'],workflow_status=r['status'],workflow_conclusion=r['conclusion'],raw_H_artifact_status='NOT_UPLOADED_HIDDEN_DIRECTORY',proof_level='COMPLETED_EXECUTION_LOG_ONLY',stage_B_allowed=False)
  for line in log.splitlines():
   m=re.match(r'^\d{4}-\d\d-\d\dT\S+Z FAMILY_POINT (\S+) (\d+) (\[.*\])$',line)
   if m:
    for q in ast.literal_eval(m.group(3)):family.append(dict(source_run=rid,**q))
   for marker in ('NATIVE_POLE_POINT ','FRESH_NATIVE_V03 '):
    m=re.match(r'^\d{4}-\d\d-\d\dT\S+Z '+marker+r'(\{.*\})$',line)
    if m:near.append(dict(source_run=rid,**ast.literal_eval(m.group(1))))
   for marker in ('P0_CLOSURE_NATIVE_RESULT ','V03_FRESH_NATIVE_RESULT '):
    m=re.match(r'^\d{4}-\d\d-\d\dT\S+Z '+marker+r'(\{.*\})$',line)
    if m:rec['executed_result']=json.loads(m.group(1))
  receipts.append(rec)
 def table(path,rows):
  if not rows:return
  keys=list(dict.fromkeys(k for r in rows for k in r))
  with path.open('w',newline='') as f:
   w=csv.DictWriter(f,keys);w.writeheader();w.writerows(rows)
 table(a.out/'NATIVE_FAMILY_LOGGED_COMPARISONS.csv',family);table(a.out/'NATIVE_POLE_LOGGED_COMPARISONS.csv',near)
 status=dict(execution='COMPLETED_LOG_RECOVERY',n_family_comparisons=len(family),n_near_pole_logged_points=len(near),receipts=receipts,not_raw_H_verification=True,stage_B_allowed=False)
 (a.out/'STATUS.json').write_text(json.dumps(status,indent=2));print('A_NATIVE_LOG_RECEIPT',json.dumps(status),flush=True)
if __name__=='__main__':main()
