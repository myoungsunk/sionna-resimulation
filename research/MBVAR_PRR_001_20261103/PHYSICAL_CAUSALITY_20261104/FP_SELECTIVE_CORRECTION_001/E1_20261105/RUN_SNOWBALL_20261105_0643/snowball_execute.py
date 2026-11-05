"""E1-01-only orchestration; frozen scientific source is not edited."""
import copy,datetime,hashlib,json,pathlib,subprocess,sys,time,traceback
ROOT=pathlib.Path('/work');sys.path.insert(0,str(ROOT/'src'))
from qclean_uwb.fp_sc.contracts import environment,sha256,write_json
from qclean_uwb.fp_sc.e1_contracts import verify_e1_lock
E=pathlib.Path('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/E1_20261105')
OUT=E/'RUN_SNOWBALL_20261105_0643'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def command(args,log):
 start=now();t=time.monotonic()
 with (OUT/log).open('x') as f:
  p=subprocess.run(args,stdout=f,stderr=subprocess.STDOUT,cwd=ROOT)
 receipt={'command':args,'start_utc':start,'end_utc':now(),'elapsed_s':time.monotonic()-t,'exit_code':p.returncode}
 write_json(OUT/(log+'.receipt.json'),receipt)
 print(json.dumps(receipt),flush=True)
 if p.returncode:raise RuntimeError('COMMAND_FAILED:'+log)
def preflight():
 assert not OUT.exists();OUT.mkdir()
 original=json.loads((E/'EXECUTION_LOCK.json').read_text());go=json.loads((E/'GO_E1_01.json').read_text())
 env=environment();oldenv=json.loads((E/'ENV_LOCK.json').read_text())
 assert env['packages']==oldenv['packages']
 assert env['system']=='Linux' and sys.version_info[:2]==(3,12)
 write_json(OUT/'ENV_LOCK.json',env)
 amendment={'study_id':'FP-SC-001','stage':'E1-01','amendment_id':'SNOWBALL_RUNTIME_20261105_0643','created_utc':now(),
 'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
 'scientific_implementation_commit':original['implementation_commit'],
 'authorization_verbatim':'깃허브에서 가져온 코드와 로컬 입력을 스노우볼로 옮겨 E1-01 실행·검산하고 결과는 깃허브에 올린다. E2는 시작하지 않는다.',
 'runtime_only_change':True,'original_environment':oldenv,'new_environment':env,
 'scientific_code_changed':False,'input_bytes_changed':False,'thresholds_changed':False,
 'result_seen_before_amendment':False,'review_provenance':'IMPLEMENTER_SELF_REVIEW_WITH_SEPARATELY_IMPLEMENTED_CHECKER',
 'external_independent_accept':False,'E2_GO':False,'E1_02_E5_GO':False,
 'classification':'EXPLORATORY_RUNTIME_AMENDMENT_NOT_EXACT_ORIGINAL_ENVIRONMENT',
 'governance':'Local RESEARCH-GOVERNANCE-v1; repository governance is scoped to MBVAR-INFO, not FP-SC. Copies and hashes retained.'}
 write_json(OUT/'AMENDMENT.json',amendment)
 lock=copy.deepcopy(original)
 del lock['documents'][lock['environment_file']]
 lock['environment_file']=(OUT/'ENV_LOCK.json').as_posix()
 lock['documents'][lock['environment_file']]=sha256(OUT/'ENV_LOCK.json')
 lock['documents'][(OUT/'AMENDMENT.json').as_posix()]=sha256(OUT/'AMENDMENT.json')
 lock['amendment']=amendment['amendment_id'];lock['source_execution_lock_sha256']=sha256(E/'EXECUTION_LOCK.json')
 write_json(OUT/'EXECUTION_LOCK.json',lock)
 go['execution_lock_sha256']=sha256(OUT/'EXECUTION_LOCK.json')
 go['authorization_source']='Explicit current user request, Codex chat 01a1aa5d-88fe-7213-bc5e-75413ca107f5'
 go['authorization_verbatim']=amendment['authorization_verbatim'];go['amendment']=amendment['amendment_id'];go['E2_GO']=False
 write_json(OUT/'GO_E1_01.json',go)
 command([sys.executable,'-m','unittest','discover','-s','tests','-p','test_fp_sc_*.py','-q'],'TESTS.log')
 receipt=verify_e1_lock(ROOT,OUT/'EXECUTION_LOCK.json',OUT/'GO_E1_01.json')
 write_json(OUT/'PREFLIGHT.json',receipt);print('PREFLIGHT_PASS',flush=True)
def execute():
 assert json.loads((OUT/'PREFLIGHT.json').read_text())['status']=='PASS_PRE_EXECUTION_IDENTITIES'
 command([sys.executable,'-u','scripts/fp_sc_e1.py','run','--lock',str(OUT/'EXECUTION_LOCK.json'),'--approval',str(OUT/'GO_E1_01.json'),'--output',str(OUT/'RUN_001')],'PRODUCTION.log')
 command([sys.executable,'-u',str(E/'audit/check_candidates.py'),'--repo','.', '--run',str(OUT/'RUN_001'),'--output',str(OUT/'REVIEW_001'),'--lock',str(OUT/'EXECUTION_LOCK.json'),'--approval',str(OUT/'GO_E1_01.json')],'CHECKER.log')
 summary=json.loads((OUT/'RUN_001/SUMMARY.json').read_text());review=json.loads((OUT/'REVIEW_001/E1_RESULT_REVIEW.json').read_text())
 write_json(OUT/'COMPLETION.json',{'status':'EXECUTION_AND_CHECKER_COMPLETED','completed_utc':now(),'observed_gate':summary['observed_gate'],'checker_status':review['status'],'external_independent_accept':False,'review_provenance':'SELF_REVIEW_WITH_SEPARATE_CHECKER_CODE','E2_GO':False,'E2_started':False})
 print('E1_COMPLETE_STOP_BEFORE_E2',flush=True)
try:
 {'preflight':preflight,'execute':execute}[sys.argv[1]]()
except Exception:
 if OUT.exists():write_json(OUT/('FAILURE_'+sys.argv[1]+'.json'),{'utc':now(),'traceback':traceback.format_exc(),'E2_GO':False})
 raise
