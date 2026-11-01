# DLP-PHYS-LINK-001 — R4 QA 제한 보완 V3 (2026-11-02)

## 판정

**구현자 자체검증: `R4_QA_REPAIR_PASS`; 독립 재감사: `PENDING`.** 핵심 수치 `ACCEPT_WITH_BOUNDARIES`, 과학적 해석 `MIXED` 유지. 원본 실행 `15503350…`은 `MISSING/BLOCKED_EVIDENCE`이며 이 패키지는 이를 복구한 것이 아니다.

이 패키지는 사용자 제공 [사전 감사 문서](https://github.com/myoungsunk/sionna-resimulation/blob/25e16bfb71786835dbd7260467e243016c0bca6b/research/DUAL_LP_PAPER_GAP_20261030/PHYSICS_LINK_REAUDIT_READINESS_20261102/01_PREAUDIT_VALIDITY_AND_OPEN_R4_KO.md)의 **R4-OPEN-01/02**만 수정한다. 기존 R2/R4/R5-B × B0/L0/L1/L2, 정수 first-path 거리, signed s, 4상태 EKF, 원 평균·분산·gate·seed를 유지한다. 신규 RT, 모델 수정, 전체 EKF 132회 재실행 없음.

## 수정 내용

1. **오래된 `got` 제거:** pose/time 음성시험은 매 시도 `trace_metrics`에서 반환된 `current_metrics`를 받아 별도의 `r4_mutation_probe`에서 평가한다. 예전 dt 시험의 결과를 재사용하지 않는다.
2. **시간 엄격성:** `np.diff(t)>0`를 요구하고 중복·역순·비유한 timestamp를 검출한다. 각 packet의 시간은 해시로 동결된 원 CONTROL `t_s`와 독립 비교하며, 저장된 `dt[1:]`와 차분도 대조한다.
3. **독립 분모:** 자기 자신과 빼서 0을 만들던 `score_count` 대신 원 CONTROL의 t≥30s 기준 분모와 실제 분모의 차이를 계산한다. 두 score mask의 packet별 차이도 확인한다.
4. **거짓 PASS 방지:** 정상 무오염 입력은 검출되지 않아야 하며, 오염 검출 함수를 고의로 0으로 무력화하면 **그 오염 시험 자체가 FAIL**해야 한다. 단독 실행·순서 반전 결과가 같아야 한다.
5. 모든 새 수치 검사 ID는 필수 검사 목록에 선언되고 final `all(required_checks)`에 포함된다.

## 재실행 결과

| 검사 | 기록 |
|---|---:|
| `pytest` 회귀시험 | **8/8 PASS** |
| 일반 / `PYTHONOPTIMIZE=1` 전체 QA 실행 | **PASS / PASS** |
| 선언된 필수 QA ID | **5,729/5,729 PASS** |
| 선택 진단 | 2개 PASS (필수 개수에서 제외) |
| V2에서 유지된 검사 행 | **5,290개, 값·상태 차이 0** |
| 신규 검사 행 | **441개** |
| 오염 및 검출기 메타시험 | **76/76 기대 결과** |
| source/control lock | 108개 확인 (외부 FFD 2개 해시 검증 후) |
| 기존 144조건 점수 CSV | 바이트 SHA-256 불변 `f3bb20b1225463ae76a5ac25cd1e4e6603865b1c2f0d7da9b3c1ecaf7e976905` |

R2-B/B0에서 시간 1초 이동은 평가 분모 **829→834**, `score_count=5`, `score_mask=5`로 감지됐다. 같은 시간 `t[1]=t[0]`는 `time_order=1` 이상으로 감지된다. 강제 0 반환은 해당 negative test에서 `FAIL`이 되는 것을 확인했다. `MUTATE_DETECTOR_DISABLED_*`의 상위 메타시험이 PASS인 것은 **의도적 무력화로 음성시험이 FAIL한 사실을 검증했다**는 뜻이다.

## 읽는 순서

- [수정 차이](REPAIR_DIFF_R4_V3.md)
- [실행 및 부정 시험 재현](REPRODUCE.md)
- [실제 코드](code/repair_v3.py) / [실제 pytest](tests/test_r4_guard_v3.py)
- [대조 판정서](results/PARITY_V2_TO_V3.json) / [음성 시험](results/NULL_AND_MUTATION_TESTS_V3_SUPPLEMENT.json)
- [필수 QA 판정](results/REQUIRED_CHECKS_V3.json) / [실행 판정](results/REPAIR_VERDICT_V3.json)

이 패키지는 기존 대용량 trace를 복사하지 않은 **append-only 보완 산출물**이다. 실행 근거는 보존된 `DualLP_Physics_Link_Validation_RERUN_20261101.zip`와 원래 FFD 두 은행이다. 외부 독립 감사 서명이 없어 전 계약 독립 검증 완료라고 표시하지 않는다.
