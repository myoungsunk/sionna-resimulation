"""D3 mandatory PRE-RUN audit. Stdlib-only; runs before numerical code.

Phase source: audit the exact mathematical code and diagnostics source.
Phase input: verify ORIGINAL GitHub Actions artifact and four saved inputs.
A failed optional analysis must not become a false scientific inference.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
EXPECTED={
 'core.py':'46746402e3a40e4acf673ae4fa2ab86dd293f62004632108374349f838ff5ffe',
 'stable_descent.py':'57271cef8fc828b383153642db812a2e537730689d46974b17f6c9b778608089',
 'synthetic.py':'c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643',
 'P2_SPEC.json':'548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7',
}
SOURCE_FILES=['d3_pre_audit.py','d3_fixed_four.py']
METADATA=[
 ('straight','MAP3',55,'f8fd1d3f0ceeebfda3322ca8a03c3eddbeb663d1078e39db342c3ec23cf2bb55','7e60e4b376ea843f9cd17c6c73d35c5fe2be937d8ac96aead85c165831021b0d'),
 ('straight','MAP4',60,'77415d27128ba08ba193bab632fed98a858aeec530f64d0963c2331e5e080dd2','e51e441f3fee5c6f288789c9ff4c848685b13a006da3205bda42b4ce77ad4192'),
 ('turn','MAP3',63,'ea1298400b662769466fc3219c3ec8ad32be3a9da3119e0af855e7bfafd3755a','639fcc0d5eb40f900aa6da9c47f8ed0ceac57538e3e91926f4071d7083b6c380'),
 ('return','MAP3',63,'b43db01f7bbc59cd2f27a553c2841173392342416b4a609001c2abecae96f16c','8755584b0d749327ee3914095491eec44ad9020f74d0dc530856b23452f9d8fe')
]
ARTIFACT_SHA='d25e96077a6b487fd0d90591362e141ee3908457808edf8688a7d3a480bad26b'
ARTIFACT_RUN=38526390416
ARTIFACT_COMMIT='99be5e38f8b68d2ed441b75222d8ff599db40a52'


def sha(data):
 return hashlib.sha256(data).hexdigest()


def file_sha(path):
 return sha(Path(path).read_bytes())


def path_for(route,model,name):
 return '_temp/p2_preflight/trials/'+route+'/0.05/000/'+model+'/'+name


def write_receipt(out,r):
 Path(out).mkdir(parents=True,exist_ok=False)
 (Path(out)/('SOURCE_AUDIT.json' if r['phase']=='source' else 'INPUT_AUDIT.json')).write_text(
  json.dumps(r,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')


def source_audit():
 checks=[]
 for name,expected in EXPECTED.items():
  actual=file_sha(HERE/name)
  checks.append({'check':'frozen_file','file':name,'ok':actual==expected,'actual':actual})
 for name in SOURCE_FILES:
  path=HERE/name
  checks.append({'check':'diagnostic_code_exists','file':name,'ok':path.is_file()})
  if path.is_file():
   try:
    root=ast.parse(path.read_text(encoding='utf-8'),filename=name)
    checks.append({'check':'diagnostic_ast_parse','file':name,'ok':root is not None})
   except SyntaxError as e:
    checks.append({'check':'diagnostic_ast_parse','file':name,'ok':False,'reason':str(e)})
 for name in ('D3_FOUR_FAILURE_AUDITED_PLAN_KO.md','D3_SCOPE_CLARIFICATION_KO.md'):
  checks.append({'check':'preregistered_plan_exists','file':name,'ok':(HERE/name).is_file()})
 wf=ROOT/'.github/workflows/ekf4-d3-four-failures.yml'
 checks.append({'check':'workflow_exists','ok':wf.is_file()})
 if wf.is_file():
  s=wf.read_text(encoding='utf-8')
  checkpoints=['python research/EKF4_RANGE_S_STAGED_20261014/d3_pre_audit.py --phase source',
               'python research/EKF4_RANGE_S_STAGED_20261014/d3_pre_audit.py --phase input',
               'python -m pip install',
               'python research/EKF4_RANGE_S_STAGED_20261014/d3_fixed_four.py']
  idx=[s.find(k) for k in checkpoints]
  checks.append({'check':'audit_before_all_numerical_executions',
                 'ok':all(i>=0 for i in idx) and idx==sorted(idx),'positions':idx})
  checks.append({'check':'workflow_read_only_github_token',
                 'ok':'actions: read' in s and 'contents: read' in s})
 checks.append({'check':'source_model_separate_rf_branch_not_imported',
               'ok':not ('h3_range_sign_audit' in (HERE/'d3_fixed_four.py').read_text())})
 return checks


def input_audit(archive,source_receipt):
 checks=[]
 src=json.loads(Path(source_receipt).read_text())
 checks.append({'check':'source_audit_GO_same_commit',
                'ok':src.get('verdict')=='GO' and src.get('git_sha')==os.environ.get('GITHUB_SHA')})
 checks.append({'check':'source_sha_unchanged_since_audit',
                'ok':all(file_sha(HERE/n)==value for n,value in src.get('source_sha256',{}).items())})
 blob=Path(archive).read_bytes()
 checks.append({'check':'original_artifact_sha256','ok':sha(blob)==ARTIFACT_SHA,'actual':sha(blob)})
 with zipfile.ZipFile(archive) as z:
  checks.append({'check':'original_zip_integrity','ok':z.testzip() is None})
  receipt=json.loads(z.read('_temp/p2_preflight/FINAL.json'))
  checks.append({'check':'original_run_provenance',
                 'ok':receipt.get('run_id')==str(ARTIFACT_RUN)
                      and receipt.get('commit')==ARTIFACT_COMMIT
                      and receipt.get('invalid_model_cases')==4
                      and receipt.get('scientific_PASS') is False})
  checks.append({'check':'original_math_source_identity',
                 'ok':all(receipt.get('source_hashes',{}).get(k)==v for k,v in EXPECTED.items())})
  for route,model,index,npz_sha,json_sha in METADATA:
   a=path_for(route,model,'FAILED_STEP.npz');b=path_for(route,model,'FAILURE.json')
   chk=sha(z.read(a))==npz_sha and sha(z.read(b))==json_sha
   failure=json.loads(z.read(b))
   chk=chk and failure['cell']['path']==route and failure['model']==model and failure['step']==index and failure['solver_status']=='LINE_SEARCH_FAILED'
   checks.append({'check':'four_frozen_failures','case':route+'/'+model,'ok':chk,
                  'NPZ_SHA':sha(z.read(a)),'JSON_SHA':sha(z.read(b))})
 return checks


def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--phase',required=True,choices=['source','input'])
 ap.add_argument('--out',required=True,type=Path)
 ap.add_argument('--archive',type=Path)
 ap.add_argument('--source-audit',type=Path)
 args=ap.parse_args()
 if os.environ.get('GITHUB_ACTIONS')!='true':
  raise RuntimeError('Every diagnostic execution requires GitHub-hosted pre-audit')
 result={'schema':'EKF4_D3_SCOPE_AND_SOURCE_AUDIT','phase':args.phase,
         'git_sha':os.environ.get('GITHUB_SHA'),'run_id':os.environ.get('GITHUB_RUN_ID'),
         'time_utc':datetime.now(timezone.utc).isoformat(),
         'decision':'Do the four archived synthetic MAP failures have a numerical solver cause, and does DR vs RF range disagreement affect them?',
         'new_scientific_estimator_runs':0,'independent_peer_audit':False,
         'scientific_PASS':False,'verdict':'HOLD','checks':[]}
 try:
  result['checks']=(source_audit() if args.phase=='source' else
                     input_audit(args.archive,args.source_audit))
  result['verdict']='GO' if all(c['ok'] for c in result['checks']) else 'HOLD'
 except Exception as exc:
  result['checks'].append({'check':'audit_execution_integrity','ok':False,
                           'error_type':type(exc).__name__,'message':str(exc)})
 result['source_sha256']={n:file_sha(HERE/n) for n in (*EXPECTED.keys(),*SOURCE_FILES)
                          if (HERE/n).exists()}
 write_receipt(args.out,result)
 print('D3_PRE_AUDIT '+json.dumps({'phase':args.phase,'verdict':result['verdict'],
    'checks':len(result['checks']),
    'failures':[c for c in result['checks'] if not c['ok']]},ensure_ascii=False),flush=True)
 return 0 if result['verdict']=='GO' else 2

if __name__=='__main__':
 raise SystemExit(main())
