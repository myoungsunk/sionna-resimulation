from pathlib import Path
import sys,subprocess,json,hashlib,datetime,traceback,os
ROOT=Path(__file__).resolve().parent
PYTHON=Path(r"D:\SLAM_bot\DS_REASSESS_V1_20261027\.venv\Scripts\python.exe")
REPO=Path(r"D:\SLAM_bot\DS_X1_X2_RESULTS_COMMIT_20261026")
SOURCE=Path(r"D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849\p2")
ARTIFACTS=SOURCE.parent/'p2_artifacts'
CODE=ROOT/'code';OUTPUT=ROOT/'results';PACKAGE=ROOT/'package'
logs=ROOT/'logs';logs.mkdir(exist_ok=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,data):(ROOT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
base=REPO/'research/DS_REASSESS_1_TO_6_20261027'
protected=[p for folder in ('code','results') for p in (base/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts]
before={str(p):sha(p) for p in protected};write('ORIGINAL_HASHES_BEFORE.json',before)
record={'started_utc':now(),'steps':[],'allowed_stages':[2,3,5],'excluded_stages':[1,4,6],'real_data':True}
env=os.environ.copy();env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONUNBUFFERED']='1';env['PYTHONUTF8']='1'
common=['--repo-root',str(REPO),'--source-root',str(SOURCE),'--artifacts-root',str(ARTIFACTS),'--output-root',str(OUTPUT)]
commands=[('package_verify',[str(PYTHON),str(PACKAGE/'VERIFY_PACKAGE.py')]),('apply',[str(PYTHON),str(PACKAGE/'APPLY_PATCH.py'),'--repo-root',str(REPO),'--code-out',str(CODE)])]
commands += [(s,[str(PYTHON),str(CODE/'run_selective.py'),*common,'--step',s]) for s in ('preflight','2','3','5')]
exitcode=0
try:
 for name,cmd in commands:
  print('[START]',name,now(),flush=True)
  item={'step':name,'command':cmd,'started_utc':now()};record['steps'].append(item);write('EXECUTION_STATUS.json',record)
  with (logs/(name+'.log')).open('w',encoding='utf-8') as log:
   r=subprocess.run(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
  item.update(exit_code=r.returncode,finished_utc=now(),log=str(logs/(name+'.log')))
  write('EXECUTION_STATUS.json',record)
  if r.returncode:
   record['status']='STOPPED_AT_FAILED_GATE';record['failed_step']=name;exitcode=r.returncode
   print('[STOP]',name,'exit',r.returncode,flush=True);break
  print('[PASS]',name,flush=True)
 else:
  final=json.loads((OUTPUT/'PATCH_V2_FINAL.json').read_text(encoding='utf-8'))
  assert final['status']=='TECHNICAL_QA_PASS_NOT_SCIENTIFIC_ADOPTION' and final['completed_steps']==['2','3','5']
  record['status']='TECHNICAL_QA_PASS_NOT_SCIENTIFIC_ADOPTION'
except BaseException:
 record['status']='HARNESS_FAILURE';record['traceback']=traceback.format_exc();exitcode=2
finally:
 changed=[p for p,h in before.items() if not Path(p).is_file() or sha(Path(p))!=h]
 record.update(finished_utc=now(),original_files_checked=len(before),original_files_changed=changed)
 if changed:record['status']='ORIGINAL_PRESERVATION_FAILED';exitcode=3
 write('EXECUTION_STATUS.json',record)
 print('[RESULT]',record['status'],'original changed',len(changed),flush=True)
sys.exit(exitcode)
