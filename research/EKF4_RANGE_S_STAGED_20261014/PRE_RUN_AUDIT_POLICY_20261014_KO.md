# EKF4 향후 모든 진단·실행 코드 사전 감사 — 적용 제안 v1 (2026-10-14)

> 사용자가 요구한 규칙: **진단 코드와 실험 실행 코드는 GitHub cloud 실행 전에 무조건 사전 감사를 한다.** '감사 필수'는 '모든 발견사항으로 모든 단계를 차단'하는 뜻이 아니다.
>
> **현재 상태: 문서형 감사 기준 수립. 자동 GitHub Actions 강제 게이트는 아직 구현·실행되지 않았다.** 새 실험을 실행한 기록이 아니다.

## A. 한 문장 의사결정
검사 항목은 반드시 다음 문장을 완성한다.
**“이 검사가 [A]를 확인하여, 결과에 따라 [GO/BLOCK 해당 셀/CLAIM HOLD/REUSE/수정] 중 무엇을 선택하는가?”**
결과와 무관하게 선택이 달라지지 않는다면 **필수 게이트가 아니라 관찰용 진단**이다. 'PASS count'가 아니라 결정 효과를 표시한다.

## B. 검사·차단 네 계층

| 분류 | 판정과 영향 | 예시 |
|---|---|---|
| **HARD_EXECUTION_BLOCK** | 실행해서 생기는 결과가 기술적으로 무효이거나 입력·물리 안전 문제가 있음. 영향을 받는 실행 중지 | 잘못된 입력 파일 SHA/pose alignment, 센서 진실값 추정기 누수, 잘못된 수식·단위, 필요한 경로 미존재, 잘못된 covariance, 코드 실행 실패 |
| **CASE_RESULT_INVALID** | 해당 estimator/seed/조건의 출력 무효; 실패율·분모 보고. 결과 재사용 불가. 미영향 별도 계산까지 무조건 차단할 필요는 없음 | 수렴 실패, 비유한 상태, 특정 조건 계산 적분 미수렴 |
| **CLAIM_BLOCK** | 알고리즘 실행은 가능하지만 특정 논문·모델 채택·일반화 주장은 금지 | P2 효과가 한 경로에서 음수가 아님, 동일 RF scene에서 seed만 증가, Full RF calibration 미확인 |
| **DIAGNOSTIC_DEFECT_OR_WARNING** | 진단 신뢰/로그 비교만 제한. 실제 계산은 별도의 직접 수치 검산으로 판단 | `history[0]['curvature_ratio']` KeyError, 누락된 선택적 plot/metadata, 동일 결과의 포맷 차이 |

각 항목은 그 영향을 받는 결과/주장/단계를 명확히 표시. `FAIL_CLOSED` 하나만 보고 전체 P2–P6 차단 금지. **HARD_EXECUTION_BLOCK**은 결코 '경량 감사'를 이유로 무시하지 않는다.

## C. 실행 직전 최소 감사 (코드/진단 코드를 모두 포함)

1. **등록 원문 비교:** 최초 사용자 요구, 기존 동결 PLAN, 구현자가 추가한 규칙을 구분. 숫자 임계값 출처가 수학적·통계적 요구인지 구현 휴리스틱인지 기록. 구현자의 강한 주장 게이트가 사용자 intent를 대체할 수 없음.
2. **변경 영향표:** `source_sha256`/input SHA/environment/model version/결정하는 claim을 이전 PASS와 비교. 동일 입력·소스·수치 계약은 `REUSED_VERIFIED`; 바뀐 경로만 재검증. 이전 PASS를 다른 코드/scene에 재사용 금지.
3. **물리·수학 감리:** 상태 순서, gyro bias 부호·rad/s, F/G, R PSD 및 상관관계, Range+`s` 중복 계수, local/Gaussian vs multimodal, ground truth 사용 경로, 센서 시간 정렬·LUT 좌표.
4. **실행기 감리:** 예외를 임의 통과시키지 않음, 출력 폴더 overwrite 금지, 완료/부분 실행 분리, exact input snapshot·solver iterate·P·raw error·최종 gradient·history 보존. `scientific_PASS=false` 기본.
5. **검증 코드 감리:** 테스트 자체가 실제 공개 API를 가정하는가? 각 `history` 값은 모든 branch에 존재하는가? 특정 스텝 선택을 무의식적으로 요구하지 않는가? 임계값·개수·prior·path/seed는 실제 동결 스펙과 일치하는가? 독립 solver `success`와 원 gradient 기준을 분리했는가?
6. **대표 최소 실행:** 사전 감사가 통과한 경우에만 GitHub Actions에서 기존 실패 입력과 지정된 음성 대조를 먼저 테스트. 해당 실패가 해소된 뒤 영향 범위 실험, 마지막으로 전체 사전등록 실행. 실패를 발견하기 위해 큰 전체 실행부터 하지 않음.
7. **결과–주장 분리:** numerical receipt, eligibility, hypothesis, uncertainty coverage, independent-scene generalization을 별도 verdict로 저장. 정답 사용/held-out split의 독립 감사 필요 여부 표시.
8. **실행 예산과 STOP:** 어떤 결과가 나오면 어떤 후보를 고치고 몇 trial까지만 하는지 미리 규정. 테스트 bug 수정은 과학 가설 변경이 아님. 핵심 scientific hypothesis가 불일치하면 관련 진행을 멈추고 사용자 방향 확인을 받음.
9. **영수증 보존:** 감사 자체의 범위·작성자/검산 방식·현재 Git commit & delta·다른 run에서 재사용한 증거 ID·차단 유형·GO/HOLD를 출력. 이전 FAIL 삭제하거나 소급 PASS 금지.

## D. 독립 감사 범위

- **독립 검산 필수:** 새로운 관측/물리 수식, 핵심 수치 방법 교체로 최종 주장 달라지는 경우, 학습 라벨 및 held-out split·시간/좌표 정렬·누수, 기각률/NEES/RMSE 주요 과학 판정, 기존 reference 비트 parity 이상.
- **독립 검산 수단:** 서로 다른 구현·도구/재계산 경로 또는 별도 reviewer. 같은 계산의 동일 helper 재호출이나 기존 보고서 재인용은 독립 감사가 아님.
- **경량 자체 확인:** 바뀌지 않은 코드/데이터의 영수증 재사용, 진단 로그 컬럼명·문서 링크·해시 목록·동일 결과 패키징. 그래도 수정 범위와 GO/HOLD 기록은 남김.
- 'independent' 여부와 'scope'를 모두 기록하며, 독립 검산이 필요한 주장에 미완료면 **그 주장만 CLAIM_BLOCK**. 물리 식 오류가 드러난 실행은 HARD_EXECUTION_BLOCK.

## E. 감사 회의록/영수증 최소 필드 예시

```json
{
  "audit_id": "EKF4_PRE_RUN_<run_id_or_hash>",
  "decision": "Can this exact code+input safely run this one experiment?",
  "intended_stage": "P2|D2|R2|P3|...",
  "claim_scope": "model-correctness|synthetic-bias|RF-input|real-RF|generalization",
  "source_commit": "<git sha>",
  "changed_files_and_dependencies": ["..."],
  "frozen_input_hashes": {"P2_SPEC": "..."},
  "audit_method": "source-review-and-independent-math|source-review-only",
  "independent_reviewer": false,
  "reused_evidence": [{"run_id": "...", "source_sha": "...", "scope": "..."}],
  "findings": [
    {"id":"A001", "severity":"DIAGNOSTIC_DEFECT_OR_WARNING",
     "decision_affected":"branch diagnostic only", "required_action":"instrument separate branch test"}
  ],
  "run_decision": "GO|HOLD|GO_WITH_CLAIM_LIMITATION",
  "scientific_claim_decision": "NOT_EVALUATED",
  "planned_execution_budget": {"small_fixture":"...", "expansion":"...", "stop":"..."},
  "audited_code_matches_execution_sha": false
}
```

`audited_code_matches_execution_sha`는 **실제 GitHub cloud checkout에서 확인한 후에만 true**. `run_decision=GO`는 조건이 바뀌지 않는 한 실험 실행만 허용하는 것이고 과학적 채택 판정이 아니다.

## F. 현재 사건에 적용해 본 결정표

| 사건 | 올바른 직접 결정 | 잘못된 확장 |
|---|---|---|
| R2 `curvature_ratio` KeyError | 회귀검사의 branch metadata 체크 무효. 실제 상태·gradient·목적함수 독립 대조 필요 | 'R2 solver 미수렴', 'P2 불가능'으로 동일시 |
| R1 4.5s / R2 6.0s double ΔJ 오판 | 고정 입력에서 더 정확한 감소 증빙으로 solver 구현 수정 검토 | `gradient_tol` 사후 완화, 무조건 성공 플래그 사용 |
| P2 3경로 중 일부 bias4 효과 미지지 (가상 예시) | 해당 경로·'전 경로 개선' 주장 보류, 이질성 보고 | P3 RF 파일 적격성 검증 자체를 금지 |
| G3 41/65 적분 TV 0.387>0.001 | 그 G3 reference posterior/성능 주장은 무효 | 모든 국소 EKF, P4 동결 RF 비교까지 무효화 |
| frozen RF manifest SHA·pose 정렬 불일치 | 해당 실제 RF 실험을 즉시 차단 | 미영향 합성 P0/P1의 기존 PASS까지 삭제 |

## G. 워크플로 개선안 (미구현)

기존 자동 push workflow는 `code push → 즉시 실행`이다. 향후 설계는 **`diff inspection + reviewed PRE_RUN_AUDIT receipt → audit_sha=run_sha 확인 → P0/P1 targeted regression/fixture → authorized experiment`**.
변경 파일에 따라 자동으로 저비용 static analysis를 만들 수 있지만, 과학 실험은 명시적으로 `workflow_dispatch` 또는 승인된 audit receipt 이후 진입한다. 진단 코드 역시 audited source matching 이전에는 실행 금지. 이 디자인은 향후 구현 대상으로 남기며 지금 사용자 지시 이전에 기존 workflow에 임의 적용하지 않는다.

## H. 성공·실패 상태와 문서 고정

기존 FAIL, R2 회귀 9/10, P2=INCOMPLETE, P3–P6=NOT_RUN, scientific_PASS=false를 그대로 유지한다. `PLAN_KO.md`, `P2_SPEC.json`을 삭제/덮어쓰거나 그 기준으로 성과를 소급 재판정하지 않는다. 앞으로 채택할 수정은 별도의 `V2` amended contract와 사전 감사 영수증으로 기록해야 한다.
