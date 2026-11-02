"""D3B mandatory source and original-artifact audit before DR-only diagnostic.

Strictly scoped to the *independent* DR-only contrast with the archived
MAP-prior and RF observations. Nothing is learned from scoring truth.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
from d3_pre_audit import EXPECTED, METADATA, ARTIFACT_SHA, sha, file_sha, input_audit

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
FILES=('d3b_pre_audit.py','d3b_dr_only.py','d3_pre_audit.py','D3B_DR_ONLY_CONTRAST_PLAN_KO.md')


def main():
 p=argparse.ArgumentParser()
 p.add_argument('--phase',required=True,choices=['source','input'])
 p.add_argument('--out',required=True,type=Path)
 p.add_argument('--archive',type=Path)
 p.add_argument('--source-audit',type=Path)
 args=p.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true':
  raise RuntimeError('This code must audit cloud numerical diagnostics before execution.')
 output=args.out.resolve()
 output.mkdir(parents=True,exist_ok=False)
 rec={'schema':'EKF4_D3B_PRE_RUN_AUDIT','stage':args.phase,
      'git_sha':os.environ.get('GITHUB_SHA'),
      'run_id':os.environ.get('GITHUB_RUN_ID'),
      'time_utc':datetime.now(timezone.utc).isoformat(),
      'decision_question':'Can the archived four inputs be used to contrast RF-free DR-only, MAP prior and RF without data leakage?',
      'claim_scope':'four archived matched synthetic cases only',
      'independent_peer_audit':False,
      'scientific_PASS':False,'verdict':'HOLD','checks':[]}
 try:
  if args.phase=='source':
   for n,h in EXPECTED.items():
    rec['checks'].append({'name':n,'type':'frozen_source_hash',
                          'ok':file_sha(HERE/n)==h})
   for n in FILES:
    rec['checks'].append({'name':n,'type':'file_exists','ok':(HERE/n).is_file()})
   for n in ('d3b_pre_audit.py','d3b_dr_only.py'):
    code=(HERE/n).read_text()
    tree=ast.parse(code,filename=n)
    rec['checks'].append({'name':n,'type':'syntax','ok':tree is not None})
   original=(HERE/'d3b_dr_only.py').read_text()
   rec['checks'].append({'name':'no_external_RF_study_import','ok':'h3_range_sign_audit' not in original})
   wf=ROOT/'.github/workflows/ekf4-d3b-dr-only.yml'
   if wf.is_file():
    body=wf.read_text()
    commands=['python research/EKF4_RANGE_S_STAGED_20261014/d3b_pre_audit.py --phase source',
              'python research/EKF4_RANGE_S_STAGED_20261014/d3b_pre_audit.py --phase input',
              'python -m pip install',
              'python research/EKF4_RANGE_S_STAGED_20261014/d3b_dr_only.py']
    positions=[body.find(c) for c in commands]
    rec['checks'].append({'name':'audit_before_diagnostic','ok':min(positions)>=0 and positions==sorted(positions),
                           'positions':positions})
    rec['checks'].append({'name':'read_only_actions_token','ok':'actions: read' in body and 'contents: read' in body})
   else:
    rec['checks'].append({'name':'workflow_exists','ok':False})
  else:
   rec['checks']=input_audit(args.archive,args.source_audit)
  rec['verdict']='GO' if all(c['ok'] for c in rec['checks']) else 'HOLD'
 except Exception as e:
  rec['checks'].append({'name':'audit_internal','ok':False,'error':type(e).__name__+': '+str(e)})
 rec['source_sha256']={n:file_sha(HERE/n) for n in (*EXPECTED,*FILES) if (HERE/n).is_file()}
 name='SOURCE_AUDIT.json' if args.phase=='source' else 'INPUT_AUDIT.json'
 (output/name).write_text(json.dumps(rec,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 print('D3B_AUDIT '+json.dumps({'phase':args.phase,'verdict':rec['verdict'],
    'checks':len(rec['checks']),'failures':[c for c in rec['checks'] if not c['ok']]},
    ensure_ascii=False),flush=True)
 return 0 if rec['verdict']=='GO' else 2

if __name__=='__main__':
 raise SystemExit(main())
