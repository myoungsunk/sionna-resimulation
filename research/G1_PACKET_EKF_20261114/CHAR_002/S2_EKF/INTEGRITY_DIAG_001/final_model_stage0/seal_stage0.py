"""Verify and index the completed trace-only Stage0 evidence package."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    contract = ROOT/'RUN_CONTRACT.json'
    frozen = json.loads(contract.read_text(encoding='utf-8'))
    for rec in frozen['bindings']:
        assert sha(rec['path']) == rec['sha256'], rec['path']
    required = ['REPORT_KO.md',
                'r2_seed_decomposition/VERIFICATION.json',
                'r5_passage_bias/VERIFICATION.json',
                'rref_exposure/VERIFICATION.json',
                'r2_seed_decomposition/REPORT_KO.md',
                'r5_passage_bias/REPORT_KO.md',
                'rref_exposure/REPORT_KO.md']
    for name in required:
        assert (ROOT/name).is_file(), name
    r2 = json.loads((ROOT/'r2_seed_decomposition/SUMMARY.json').read_text(encoding='utf-8'))
    r5 = json.loads((ROOT/'r5_passage_bias/RESULTS.json').read_text(encoding='utf-8'))
    rref = json.loads((ROOT/'rref_exposure/RESULTS.json').read_text(encoding='utf-8'))
    result = {'question_id': frozen['question_id'], 'classification': 'DIAGNOSTIC_ONLY',
              'scope': frozen['scope'], 'root_contract_sha256': sha(contract),
              'R2_primary_windows': [x for x in r2['windows'] if x['seed'] in (10,11)
                                    and x['arm']=='G1_KI' and x['start_s'] in (80,120)
                                    and x['end_s'] in (120,160)],
              'R5_paired_passages': r5['paired_passages'],
              'Rref_distance_rows': [x for x in rref['rows'] if x['population']=='accepted_supported'],
              'recommendations': {
                  'R2': 'Current G1+KI remains an unresolved comparison arm, not a validated M7 main arm. Direct injectedgyro noise alone is insufficient; causal KI intervention not evaluated.',
                  'R5': 'Own-near q_s=0 is implemented. Incoming b_theta alone and instantaneous local DeltaJyy alone are not demonstrated dominant explanations. Carry full pose/bias/crosscov hypothesis forward.',
                  'P7': 'R5 temporal correlation and accurate baseline coexist. Do not equate useful independent-noise treatment with physically white RF residuals.',
                  'adoption': 'No new arm adopted and no M7 replay authorized by this arithmetic package.'},
              'limits': ['single RF realization', 'wheel and gyro seed vary together',
                         'same initial estimate and fixed acceptance mask across seeds',
                         'realized-path additive ledgers are not counterfactual causal effects',
                         'kernel N_eff is an assumed-scale diagnostic, not fitted residual effective sample size']}
    with (ROOT/'RESULTS.json').open('x',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    manifest = {str(p.relative_to(ROOT)).replace('\\','/'): {'bytes':p.stat().st_size, 'sha256':sha(p)}
                for p in sorted(ROOT.rglob('*')) if p.is_file() and p.name != 'MANIFEST.json'}
    receipt = {'question_id': frozen['question_id'], 'sealed_utc':datetime.now(timezone.utc).isoformat(),
               'source_revision': frozen['source_revision'], 'root_contract_sha256':sha(contract),
               'command':[sys.executable,'-B','-X','utf8',str(Path(__file__))],
               'exit_code':0,'execution':'COMPLETE: existing trace arithmetic only',
               'replay_count':0,'bound_input_count':len(frozen['bindings']),
               'all_bound_inputs_unchanged':True,'files':manifest}
    with (ROOT/'MANIFEST.json').open('x',encoding='utf-8') as f:
        json.dump(receipt,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps({'status':'PASS','bound_inputs':len(frozen['bindings']),
                      'artifact_files':len(manifest),'replays':0},ensure_ascii=False))


if __name__=='__main__':main()
