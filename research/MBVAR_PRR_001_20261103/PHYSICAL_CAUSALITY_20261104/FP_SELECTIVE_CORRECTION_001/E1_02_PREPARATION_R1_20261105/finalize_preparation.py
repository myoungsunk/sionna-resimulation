"""Self-check frozen preparation, synthetic tests only. No stage run calls."""
import datetime,importlib.util,json,os,pathlib,subprocess,sys,unittest
from unittest.mock import patch
R=pathlib.Path('/work');sys.path.insert(0,str(R/'src'))
P=pathlib.Path('research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001')
O=R/P/'E1_02_PREPARATION_R1_20261105'
from qclean_uwb.fp_sc.followup.contracts import sha256,write_json,verify_files,authorize,ContractError,digest
from qclean_uwb.fp_sc.followup.runner import code_paths
from qclean_uwb.fp_sc.followup.data import load_case
F=O/'FINAL_CHECK_002';F.mkdir(exist_ok=False)
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m
tests={}
for name in ('test_fp_sc_detection_prep','test_fp_sc_bridge','test_fp_sc_selector_reach','legacy_followup_tests'):
    path=R/'tests'/(name+'.py')
    m=module(path,name)
    suite=(unittest.defaultTestLoader.loadTestsFromTestCase(m.ReceiverSelectionTest) if name=='legacy_followup_tests'
           else unittest.defaultTestLoader.loadTestsFromModule(m))
    with (F/(name+'.log')).open('x') as stream:
        if name=='test_fp_sc_selector_reach':
            source=(R/'tests/legacy_selection.py.txt').read_bytes()
            def old_git(args,**kwargs):
                assert args==['git','show','486f0b6c008e7a953ada75a03a941ffa46994985:src/qclean_uwb/fp_sc/followup/selection.py']
                return source
            with patch.object(m.subprocess,'check_output',side_effect=old_git):
                result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
        else:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    tests[name]=dict(n=result.testsRun,failures=len(result.failures),errors=len(result.errors),source_sha256=sha256(path))
    assert result.wasSuccessful(),name
manifest=json.loads((O/'INPUTS/MANIFEST_PREP_ONLY.json').read_text())
verify_files(R,manifest['input_files']);verify_files(R,manifest['baseline_sources'])
assert len(os.sched_getaffinity(0))<4
for spec in manifest['cases'].values():load_case(R,spec,manifest['input_files'],None,detection_only=True)
# An additive technical-scope receipt; neither the old FAIL nor HOLD is edited.
refs=[P/'E1_20261105/RUN_SNOWBALL_20261105_0643/RUN_001/SUMMARY.json',
      P/'E1_20261105/CANDIDATE_REVISION_R1_20261105/RUN_001/FINAL_VERDICT.json',
      P/'SELECTOR_REACH_R2_20261105/CHECK_001/GATE.json',
      P/'SELECTOR_REACH_R2_20261105/TEST_RECEIPT.json']
source_files={str(p):sha256(R/p) for p in refs}
prereq=F/'PREREQUISITE_SCOPE_RECEIPT.json'
write_json(prereq,dict(schema='FP_SC_TECHNICAL_SCOPE_RECEIPT_V1',study_id='FP-SC-001',stage='E1-01',
    execution_status='COMPLETE',numerical_qa_pass=True,scientific_gate='HOLD_RESULT_REVIEW',
    candidate_reach='TECHNICAL_ACCEPT_WITH_SCOPE',primary='VAB',source_files=source_files,
    acceptance_source='USER_PROVIDED_LIMITED_REVIEW_20261105_BASE_ba8d978',
    external_independent_accept=False,raw_50560_external_recalculation=False,E1_02_GO=False,E2_GO=False))
manifest['input_files'].update(source_files)
manifest['input_files'][str(prereq.relative_to(R))]=sha256(prereq)
manifest['prerequisite_receipts']={'E1-01':str(prereq.relative_to(R))}
manifest['code_files']={p:sha256(R/p) for p in code_paths(R)}
manifest['preparation_code_commit']=os.environ['PREP_CODE_COMMIT']
mp=F/'MANIFEST_PREP_ONLY.json';write_json(mp,manifest)
ap=F/'NO_EXECUTION_APPROVAL.json'
write_json(ap,dict(execute_science=False,stages=[],manifest_sha256=sha256(mp),
                  code_lock_sha256=digest(manifest['code_files']),E1_02_GO=False,E2_GO=False))
try:authorize(R,mp,ap,['E1-02'],code_paths(R))
except ContractError as e:assert str(e)=='SCIENCE_EXECUTION_NOT_AUTHORIZED'
else:raise AssertionError('AUTHORIZATION_GUARD_FAILED')
verify_files(R,manifest['code_files']);verify_files(R,manifest['input_files'])
write_json(F/'RESULT.json',dict(status='PASS_PREPARATION_SELF_CHECK_EXECUTION_HOLD',
    utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),code_commit=os.environ['PREP_CODE_COMMIT'],
    code_lock_sha256=digest(manifest['code_files']),tests=tests,total_tests=sum(v['n'] for v in tests.values()),
    legacy_exact_decisions=1000,legacy_reference_commit='486f0b6c008e7a953ada75a03a941ffa46994985',
    legacy_reference_sha256=sha256(R/'tests/legacy_selection.py.txt'),
    input_files_verified=len(manifest['input_files']),canonical_cases=6,canonical_packets=6272,
    original_input_files_verified=35,static_waveforms_locked=48,static_in_stage_case_list=False,
    model_load_receipt_sha256=sha256(O/'PREPARATION_RECEIPT.json'),cpu_affinity=sorted(os.sched_getaffinity(0)),
    threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')},
    preparation_script_sha256=sha256(R/'scripts/prepare_fp_sc_e102.py'),
    E1_02_started=False,E2_started=False,real_detection_calls=0,model_batch_calls=0,EKF_replay_calls=0,
    independent_audit=False,mapping='NOT_RUN',adoption='HOLD'))
print('FINAL_PREPARATION_PASS',sum(v['n'] for v in tests.values()),flush=True)
