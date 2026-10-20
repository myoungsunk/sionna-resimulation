"""Publish T7A recovered evidence and completed T7B results without tuning."""
import csv
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    src=HERE/'policy_control'
    decision=json.loads((src/'DECISION.json').read_text())
    assert decision['complete'] and len(decision['cells'])==72
    assert not json.loads((src/'ERRORS.json').read_text())
    for name in ['POLICY_RESULTS.csv','BASELINE_CHECKS.csv','DECISION.json','ERRORS.json']:
        (HERE/name).write_bytes((src/name).read_bytes())
    (HERE/'T7B_RUNTIME_MANIFEST.json').write_bytes((src/'MANIFEST.json').read_bytes())
    cells=decision['cells']
    with (HERE/'POLICY_COMPARISON.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cells[0]);w.writeheader();w.writerows(cells)
    bad_full=sum(x['channel']=='full' and not x['pass_10pct'] for x in cells)
    bad_los=sum(x['channel']=='los' and not x['pass_10pct'] for x in cells)
    checks=list(csv.DictReader((src/'BASELINE_CHECKS.csv').open(newline='')))
    maxheading=max(float(x['heading_difference_deg']) for x in checks)
    assert maxheading<=1e-6 and all(int(x['gate_mismatches'])==0 for x in checks)
    receipts=[]
    for p in sorted((HERE/'execution_39361956622').rglob('ACTIONS_ARTIFACT.json')):
        d=json.loads(p.read_text());receipts.append(dict(id=d['id'],sha256=d['digest'],run_id=d['workflow_run']['id'],receipt=p.relative_to(HERE).as_posix(),receipt_sha256=sha(p)))
    preview=json.loads((src/'ACTIONS_ARTIFACT.json').read_text())
    if preview['id'] not in {x['id'] for x in receipts}:
        receipts.append(dict(id=preview['id'],sha256=preview['digest'],run_id=39361956622,receipt='policy_control/ACTIONS_ARTIFACT.json',receipt_sha256=sha(src/'ACTIONS_ARTIFACT.json')))
    report=f'''# T7 온라인 특징과 효용 target 정책

T7A TECHNICAL_PASS / SUPPORTED_BUT_LIMITED. 원본5ac914f의 run39354151551, artifact12233874874를 회수했다. 고정12이벤트·2647패킷에서 Full-only abs_s rank AUC=.742857, 포화=.700000이다. 역사적 이벤트 label에 대한 기술 통계이며 T2 정본의 인과효과나 장면 일반화를 인증하지 않는다.

T7B TECHNICAL_PASS / {decision['scientific']}; {decision['go_no_go']}. 원본 실행 source4eb01aa85344553dfb5111e1369d7658522ef277, run39361956622, artifact12238630433이다. 16 Full조건×4bias와 Native LoS2조건×4bias, 총72셀을 POWER1/R0/POLICY로 실행했다. motion/radio 각각 11개 지표를 보존한 POLICY_RESULTS.csv는432행이다. Full64셀 중{bad_full}개, Native LoS8셀 중{bad_los}개에서 사전 등록10% 악화 한도를 초과했다. POLICY_COMPARISON.csv에 모든 셀을 보존했다.

예: O01 L2 motion에서 POWER1 .452926° → POLICY9.363465° (20.673291배). 최대 악화 셀을 지우거나 파라미터를 다시 맞추지 않았다. 재귀 정책 채택은 하지 않는다.

Nested route-heldout P1 prior와 offline10s counterfactual utility label을 사용했다. 신규9조건은 학습에 쓰지 않았다. 온라인 행동은 현재 Full RF 특징과 해당 정책의 prior NIS/sigma/Pψb/Hsψ만 사용하며 원래 gate를 유지한다. GT·미래는 offline label 생성·평가에만 사용한다. 학습 label·fold·모델 SHA·CSV 행동 로그를 보존했고 큰 NPZ trace는 artifact에 보존하고 원본 학습 pickle은 TRAINED_MODELS_BASE64.json에 byte 그대로 인코딩해 git에도 보존한다. restore_models.py로 hash 검증 후 복원한다.

POWER1 기준선64셀의 Heading 최대 차={maxheading:.15g}°, gate 불일치0. 모든 평가에서 독립 scorer≤1e−9를 요구했고 오류는0건이다. Native LoS는 별도 안전성 대조로 평가했다. 모델 학습/인터페이스 시험/최종 재귀는 단계별 manifest로 구분한다. T4 완료 dependency는 원래 GLOBAL 집계에서 확인했으며 후속 POST30 판정 범위 수정은 정책 label·feature·학습·파라미터를 바꾸지 않는다.

## 주장하지 않는 것

독립 장면 일반화, 정규화 Bayesian posterior, 하드웨어 실증, 효용 label의 온라인 접근을 주장하지 않는다. 원래 복도와 C조건은 같은 장면이며 O조건도 한 오피스다. 조건 수를 독립 표본 수로 사용하거나 p-value를 제시하지 않는다. NO-GO를 보존한다.
'''
    (HERE/'RESULTS_KO.md').write_text(report,encoding='utf-8')
    m=dict(task='T7_A_AND_B',technical='TECHNICAL_PASS',scientific=decision['scientific'],go_no_go=decision['go_no_go'],
           source_commit='4eb01aa85344553dfb5111e1369d7658522ef277',actions_run_id=39361956622,artifact_id=12238630433,
           artifact_sha256=preview['digest'],artifacts=receipts,protocol_sha256=sha(HERE/'PROTOCOL_LOCK.json'),
           T7A=json.loads((HERE/'RECOVERY_MANIFEST.json').read_text()),
           inputs={'T7B_RUNTIME_MANIFEST.json':sha(HERE/'T7B_RUNTIME_MANIFEST.json')},
           outputs={name:sha(HERE/name) for name in ['POLICY_RESULTS.csv','BASELINE_CHECKS.csv','DECISION.json','ERRORS.json','POLICY_COMPARISON.csv','RESULTS_KO.md','TRAINED_MODELS_BASE64.json','restore_models.py']})
    (HERE/'MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    print(json.dumps(dict(scientific=decision['scientific'],go_no_go=decision['go_no_go'],full_failed=bad_full,los_failed=bad_los)))

if __name__=='__main__':main()
