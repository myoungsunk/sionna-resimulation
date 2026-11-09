"""Package final measured evidence, excluding raw Release assets and source trees."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

FOLDERS=('baseline','bias_causal','bias_feedback','horizons','independent_unit_audit_final',
         'model_truth','policy_calibration_final','policy_primary_precheck','precheck_motion',
         'precheck_oracle','profiles_final','projection','recovery_cause','recovery_feasibility',
         'recovery_final','source_adversarial_final','synthetic_adversarial_final',
         'delivery_evaluation','uncertainty')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main(root):
    result=json.loads((root/'results/delivery_evaluation/RESULTS.json').read_text())
    assert result['status']=='COMPLETED_NUMERICAL_DELIVERY_EVALUATION'
    assert len(result['evaluated_records'])==42
    ci=json.loads((root/'results/github_ci/CI_REMOTE_AUDIT.json').read_text())
    assert ci['status']=='PASS_REMOTE_REPLAY_AND_LOCAL_RECONCILIATION'
    files={}
    def add(p,arc=None):
        if not p.is_file():return
        if any(q in p.parts for q in ('__pycache__',)):return
        if p.name.endswith(('_PARTIAL.npz','_RUNNING.json','.part','.pyc')):return
        files[arc or str(p.relative_to(root))]=p
    for folder in FOLDERS:
        path=root/'results'/folder
        assert path.is_dir(),folder
        for p in sorted(path.rglob('*')):
            if p.suffix in ('.json','.csv','.npz','.md','.log','.txt'):add(p)
    for s in ('B_FROZEN','B_BIAS_COV'):
        for mode in ('OFF','OBSERVE_ONLY','ACTIVE_R','ACTIVE_S','ACTIVE_RS','DR_ONLY','NAIVE_YAW_CLIP'):
            for route in ('R2','R4','R5'):
                for suffix in ('.json','.npz'):
                    p=root/'results/active'/s/mode/(route+'_'+mode+suffix)
                    assert p.is_file(),p
                    add(p)
    for p in (root/'results/active').glob('*_GRID.json'):add(p)
    for p in (root/'results/github_ci').glob('*.json'):
        if 'PROGRESS' not in p.name:add(p)
    for d in (root/'results/github_ci').glob('b-mcg-v1-*'):
        if not d.is_dir():continue
        for p in d.rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(d)
            # Keep numeric CI evidence, not duplicate committed source or large raw inputs.
            if ('active' in rel.parts or 'baseline' in rel.parts or p.name in
                ('CI_ROUTE_SUMMARY.json','UNIT.log','CALIBRATION_TESTS.log','ARCHIVE_RECEIPT.json',
                 'EXECUTED_SOURCE_SHA256.txt','COMMIT_SHA.txt')):
                if p.suffix in ('.json','.npz','.txt','.log'):add(p)
    for name in ('INPUT_RECEIPT.json','SOURCE_RECOVERY_RECEIPT.json'):
        add(root/'recovery'/name)
    for name in ('FINAL_ADVERSARIAL_VERDICT_KO.md','FINAL_POLICY_INDEPENDENT_CHECK.json',
                 'FINAL_POLICY_INDEPENDENT_CHECK.md','GITHUB_WORKFLOW_INDEPENDENT_CHECK.json'):
        add(root/'review'/name)
    for p in (root/'deliverables/figures').iterdir():
        if p.suffix in ('.png','.svg'):add(p,'figures/'+p.name)
    # Retain specifically used superseded diagnostic receipts. Never promote them to final traces.
    for folder in ('source_adversarial','source_adversarial_v1','recovery_v1'):
        path=root/'results'/folder
        for p in path.glob('*.json'):add(p,'superseded_diagnostics/'+folder+'/'+p.name)
    manifest={'schema':'B_MCG_V1_EVIDENCE_MANIFEST_V1','execution_code_commit':
        'e3ddc9fa4371d899a08a2a873d2ee5cf32074a01','github_actions_run':42600632209,
        'final_runtime_sha256':{'mcg.py':'8f58b7c412e54ca5fa308e61aa16c59c0fec30f05e482c505cb5cdea11099faf',
            'experiment.py':'e4abd56b3224782efb2f4c861d61e0bd724e0e3687a8e06d8b81f0520229ed28'},
        'policy_default':'OFF','policy_adoption':'NOT_READY_OR_NOT_DEMONSTRATED',
        'unique_input_rows':3136,'local_streams':42,'local_rows_repeated_across_settings':43904,
        'ci_off_active_streams':12,'ci_rows_repeated_across_settings':12544,
        'row_repetition_is_not_independent_sample_size':True,
        'excluded':['raw Release NPZ/FFD assets','Git source trees','interleaved or partial prototype profiles',
                    'RUNNING/PARTIAL checkpoints','temporary signed transfer URLs'],
        'superseded_scope':'Retained diagnostic JSONs document the correction chain only; all final metrics use final_runtime hashes.',
        'files':{n:{'bytes':p.stat().st_size,'sha256':sha(p)} for n,p in sorted(files.items())}}
    readme='''B-MCG v1 실행·검증 근거 (2026-11-09)

먼저 results/delivery_evaluation/RESULTS.json과 METRICS.csv를 확인하십시오.
정책 채택은 OFF입니다. 실행 성공, 단위시험, 고정 대조군의 작은 평균 개선은
사전 정책 유용성·정상 복귀 보호·실시간 비용의 통과를 대체하지 않습니다.

results/active: 42개 최종 실제 재귀, 각 JSON과 NPZ SHA 연결.
results/policy_calibration_final: train/dev split, 후보별 손익, 6개 OFF lock.
results/recovery_cause + recovery_feasibility: 첫 정상 복귀의 오감쇠 원인과 누락된 허용해.
results/uncertainty: 실제 coverage와 interval width/ellipse area, 연속 이탈 시간.
results/github_ci: 성공한 원격 실행과 로컬 대조 영수증, 원격 수치 근거.
review: 같은 협업팀 안의 별도 계산 경로/적대적 감사. 외부 인증은 아닙니다.
superseded_diagnostics: 수정 이력만 설명하며 최종 성능 산출에 사용하지 않습니다.

FILE_SHA256.json의 모든 file bytes/SHA로 파일 일치를 확인할 수 있습니다.
원본 데이터와 코드는 GitHub 저장소의 고정 commit/Release/archive lock을 사용합니다.
원본 대용량 입력과 Git source tree는 이 묶음에 중복 포함하지 않았습니다.

실행 코드: https://github.com/myoungsunk/sionna-resimulation/tree/e3ddc9fa4371d899a08a2a873d2ee5cf32074a01/research/B_MCG_V1_20261109
Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/42600632209
'''
    out=root/'deliverables/B_MCG_V1_EVIDENCE_20261109.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for n,p in sorted(files.items()):z.write(p,n)
        z.writestr('README_KO.txt',readme)
        z.writestr('FILE_SHA256.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None
        for n,info in manifest['files'].items():
            data=z.read(n)
            assert len(data)==info['bytes'] and hashlib.sha256(data).hexdigest()==info['sha256'],n
    receipt={'status':'PASS_ZIP_MEMBERS_AND_SHA256','file':str(out),'bytes':out.stat().st_size,
        'sha256':sha(out),'evidence_files':len(files),'archive_members':len(files)+2}
    (root/'deliverables/EVIDENCE_PACKAGE_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();main(a.root)
