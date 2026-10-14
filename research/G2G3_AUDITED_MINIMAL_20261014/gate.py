"""Reviewed stdlib-only audit bootstrap. Run before each experiment/diagnostic.

This gate is itself listed in the manually reviewed approval's Git blob hashes.
It verifies exact executed bytes, not just filenames or workflow success flags.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/'outputs/g2g3_minimal'


def main(stage):
    OUT.mkdir(parents=True,exist_ok=True)
    target=OUT/('PRE_RUN_'+stage+'.json')
    if target.exists():raise FileExistsError('Audit receipt overwrite prohibited')
    approval=json.loads((ROOT/'APPROVAL.json').read_text())
    contract=json.loads((ROOT/'CONTRACT.json').read_text())
    receipt=dict(audit_id=approval['audit_id']+'/'+stage,
        decision='May this exact code and required inputs execute this stage?',
        intended_stage=stage,source_commit=subprocess.check_output(
            ['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        review_commit=approval['reviewed_source_commit'],
        source_sha256={},findings=[],run_decision='HOLD',
        audit_method=approval['audit_method'],independent_reviewer=False,
        independent_computational_paths=approval['independent_computational_paths'],
        reused_evidence=approval['reused_evidence'],
        audited_code_matches_execution_sha=False,
        scientific_claim_decision='CLAIM_BLOCK_UNCALIBRATED_PROTOTYPE')
    try:
        if stage not in approval['authorized_stages']:
            raise RuntimeError('unauthorized execution scope')
        if approval['review_decision']!='GO_WITH_CLAIM_LIMITATION':
            raise RuntimeError('manual source review not approved')
        for rel,expected in approval['source_git_blobs'].items():
            p=REPO/rel
            if not p.is_file():raise FileNotFoundError(rel)
            actual=subprocess.check_output(['git','hash-object',str(p)],text=True).strip()
            if actual!=expected:raise RuntimeError('audited blob mismatch: '+rel)
            receipt['source_sha256'][rel]=hashlib.sha256(p.read_bytes()).hexdigest()
        # Shadow replay alone depends on the old artifact. A data problem does
        # not block independent synthetic/linear-algebra work.
        if stage=='shadow':
            manifest=REPO/'inputs/range_audit/ACQUISITION.json'
            if not manifest.is_file():raise RuntimeError('reference acquisition missing')
            acq=json.loads(manifest.read_text())
            if acq['zip_sha256']!=contract['source_artifact']['zip_sha256']:
                raise RuntimeError('reference artifact SHA mismatch')
            for name,expected in acq['file_sha256'].items():
                actual=hashlib.sha256((manifest.parent/name).read_bytes()).hexdigest()
                if actual!=expected:raise RuntimeError('extracted input mismatch: '+name)
            receipt['input_sha256']=acq['file_sha256']
        if stage=='diagnosis':
            mr=OUT/'math.json'
            if not mr.is_file() or not json.loads(mr.read_text()).get('radial_pass'):
                raise RuntimeError('radial model math not validated; dependent diagnostic cannot run')
        receipt['audited_code_matches_execution_sha']=True
        receipt['run_decision']='GO_WITH_CLAIM_LIMITATION'
        receipt['findings'].append(dict(severity='CLAIM_BLOCK',scope='source identification/generalization',
            reason='Synthetic prior/likelihood parameters are not independently calibrated; calculations remain admissible.'))
        result=0
    except Exception as exc:
        receipt['findings'].append(dict(severity='HARD_EXECUTION_BLOCK',scope=stage,reason=str(exc)))
        result=2
    target.write_text(json.dumps(receipt,indent=2,ensure_ascii=False))
    print('PRE_RUN_AUDIT',stage,receipt['run_decision'],receipt['findings'])
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage')
    raise SystemExit(main(ap.parse_args().stage))
