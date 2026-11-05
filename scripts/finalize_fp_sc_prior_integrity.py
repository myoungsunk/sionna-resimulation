"""Build non-executable preparation artifacts after component-only checks."""
import argparse,datetime,json,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
from qclean_uwb.fp_sc.followup.contracts import sha256,write_json,authorize,ContractError,digest,verify_files
from qclean_uwb.fp_sc.followup.runner import code_paths
from qclean_uwb.fp_sc.followup.integrity import INTEGRITY_RECIPE
from qclean_uwb.fp_sc.followup.detection import HISTORY_RECIPE
B=R/'research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001'
P=B/'PRIOR_INTEGRITY_R1_20261105'

def finalize(run,check,out):
    out.mkdir(exist_ok=False)
    gate=json.loads((check/'GATE.json').read_text());assert gate['verdict']=='PASS_COMPONENT_GUARDS_ONLY'
    tests=json.loads((P/'FINAL_TESTS_001/RECEIPT.json').read_text());assert tests['failures']==0 and tests['total_tests']==90
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
    old=json.loads((B/'DYNAMIC_MAPPING_R1_20261105/FINAL_PREPARATION_MANIFEST.json').read_text())
    old['code_files']={p:sha256(R/p) for p in code_paths(R)}
    old.update(preparation_code_commit=head,mapping_reviewed=False,primary_arm='VAB',
               integrity_recipe=INTEGRITY_RECIPE,history_recipe=HISTORY_RECIPE,
               integrity_provider_status='MISSING_NO_VALID_PROMOTION',
               preparation_status='COMPONENT_GUARDS_PASS_E1_02_HOLD')
    evidence=[P/'FROZEN_CONTRACT_KO.md',run/'RUN_RECEIPT.json',check/'GATE.json',P/'FINAL_TESTS_001/RECEIPT.json']
    receipt=dict(status='PASS_COMPONENT_GUARDS_ONLY',integrity_recipe=INTEGRITY_RECIPE,
        history_recipe=HISTORY_RECIPE,prior_integrity_provider='MISSING',P_M_PM_usable_fraction=0.,
        mapping_reviewed=False,wrong_prior_safety_pass=False,E1_02_started=False,E2_started=False,
        code_commit=head,evidence_files={p.relative_to(R).as_posix():sha256(p) for p in evidence})
    write_json(out/'INTEGRITY_RECEIPT.json',receipt)
    old['integrity_receipt']=(out/'INTEGRITY_RECEIPT.json').relative_to(R).as_posix()
    old['input_files'].update(receipt['evidence_files'])
    old['input_files'][old['integrity_receipt']]=sha256(out/'INTEGRITY_RECEIPT.json')
    write_json(out/'MANIFEST_PREP_ONLY.json',old)
    write_json(out/'NO_EXECUTION_APPROVAL.json',dict(execute_science=False,stages=[],manifest_sha256=sha256(out/'MANIFEST_PREP_ONLY.json')))
    verify_files(R,old['input_files']);verify_files(R,old['code_files'])
    try:authorize(R,out/'MANIFEST_PREP_ONLY.json',out/'NO_EXECUTION_APPROVAL.json',['E1-02'],code_paths(R))
    except ContractError as e:assert str(e)=='SCIENCE_EXECUTION_NOT_AUTHORIZED';blocked=str(e)
    else:raise AssertionError('EXECUTION_NOT_BLOCKED')
    assert len(old['static_cases'])==48 and sum(s['expected_rows'] for s in old['cases'].values())==6272
    write_json(out/'CHECK.json',dict(status='PASS_PREPARATION_LOCKS_ONLY',code_commit=head,dynamic=6272,static=48,total=6320,
        denial=blocked,all_input_hashes=True,all_code_hashes=True,E1_02_started=False,E2_started=False))
    governance=Path('C:/Users/Myoungsun Kim/.codex/research-governance')
    write_json(out/'GOVERNANCE_HASHES.json',{n:sha256(governance/n) for n in ('COMMON_CONTRACT.md','ROLE_PROPOSER.md','ROLE_IMPLEMENTER.md')})
    print('PREPARATION_6320_VERIFIED_EXECUTION_BLOCKED',flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser()
    for name in ('run','check','output'):a.add_argument('--'+name,type=Path,required=True)
    args=a.parse_args();finalize(args.run.resolve(),args.check.resolve(),args.output.resolve())
