#!/usr/bin/env python3
"""Read-only exact-object recovery across remote branches; no RF simulation.
Only five named missing legacy45 arrays are fetched, and accepted only by SHA256.
"""
from __future__ import annotations
import argparse,hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def run(args):return subprocess.check_output(args,cwd=ROOT,text=True,stderr=subprocess.STDOUT)
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 base=ROOT/'results/DRIVE_SIM_NOISY_PROBE_20261010/RUN_01a125b3/SUMMARY_CURRENT/MOUNT_CASE_MATRIX.json'
 matrix=json.loads(base.read_text());wanted={c['case']:c['full_sha256'] for c in matrix if c['case'].endswith('m45') and c['case']!='R2_aA_m45'}
 names={'H_'+c+'.npy':c for c in wanted};heads=[]
 for row in run(['git','ls-remote','--heads','origin']).splitlines():
  sha,ref=row.split('\t');heads.append((sha,ref))
 attempted=[];matches=[];seen=set();blobs=set()
 for commit,branch in heads:
  if commit in seen:continue
  seen.add(commit)
  try:
   subprocess.run(['git','fetch','--filter=blob:none','--depth=1','--no-tags','origin',commit],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
   tree=run(['git','ls-tree','-r',commit])
   candidates=[]
   for line in tree.splitlines():
    meta,path=line.split('\t',1)
    if Path(path).name not in names:continue
    mode,typ,blob=meta.split()
    if typ!='blob':continue
    case=names[Path(path).name];entry=dict(case=case,branch=branch,commit=commit,path=path,git_blob_sha=blob)
    candidates.append(entry)
    if (blob,case) in blobs:continue
    blobs.add((blob,case));raw=subprocess.check_output(['git','cat-file','blob',blob],cwd=ROOT)
    digest=hashlib.sha256(raw).hexdigest();entry=dict(entry,bytes=len(raw),content_sha256=digest,expected_sha256=wanted[case],sha_match=digest==wanted[case])
    matches.append(entry)
    if entry['sha_match']:(a.out/('RECOVERED_H_'+case+'.npy')).write_bytes(raw)
   attempted.append(dict(branch=branch,commit=commit,completed=True,named_candidates=candidates))
  except (subprocess.CalledProcessError,ValueError) as ex:
   attempted.append(dict(branch=branch,commit=commit,completed=False,error=str(ex)))
  print('EXACT_LEGACY45_BRANCH_SEARCH',branch,len(attempted),len(matches),flush=True)
  (a.out/'REMOTE_BRANCH_OBJECT_SCAN.json').write_text(json.dumps(dict(wanted=wanted,attempted=attempted,matches=matches),indent=2))
 found=sorted({m['case'] for m in matches if m['sha_match']})
 status=dict(execution='COMPLETE' if all(x['completed'] for x in attempted) else 'PARTIAL_BRANCH_READ_FAILURE',n_remote_branches=len(heads),n_unique_commits=len(attempted),expected_missing_cases=list(wanted),recovered_exact_cases=found,still_missing=sorted(set(wanted)-set(found)),stage_B_allowed=False)
 (a.out/'STATUS.json').write_text(json.dumps(status,indent=2));print('LEGACY45_OBJECT_RESULT',json.dumps(status),flush=True)
if __name__=='__main__':main()
