# MBVAR-INFO-001 — R5 구현 완료 후보의 독립 재감사 의뢰서

**역할 IMPLEMENTER / SELF_REVIEW_ONLY.** 이 문서는 독립 감사자가 작성한 검산 결과나 A010 동결 서명이 아니다.

## 1. 감사 대상

- 구현 PR: https://github.com/myoungsunk/sionna-resimulation/pull/18
- 제안자 결정 원문: `contracts/AMENDMENT-010-R5-PROPOSER-DECISION-FINAL-PREFREEZE-20261103.md` 및 `AMENDMENT-010-R5-PROPOSER-SPEC-V1.json` (PR #17).
- 변경 코드: `code/a10_r5.py`, `code/c3v5.py`. 운영 S1V5 E′ (`s1v5.py`)는 변경하지 않았다.
- 음성 시험: `tests/test_a10_r5.py` + 기존 R1–R4 fixtures.
- 기술 Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41592601796 . (최종 로그/아티팩트 확인 후 결과 판정).
- 기존 archived DEV2 K1/K2 real RF probe: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41593156279 . (이전 실패 시도 #41593026993도 보존).

## 2. R5-01 — 열 개 해의 종료 정밀도 인증

1. 각 관측 키 `(field,role,cell,sensor_seed,arm)`에 대해 E′와 아홉 truth-free 시작점이 정확히 하나씩 존재하는지 원본 code/CSV로 독립 검증.
2. F2 `POLISH_TOL=1e-3 χ²`, `POLISH_MAX=30` 유지 및 start별 실제 `polish_steps`, `polish_hit_cap` 보존 확인.
3. 모든 start에 동일 SHA 기반 `R5_CERT|field|role|cell|sensor|arm` seed를 사용하고, **같은 row의 GN line + random 8쌍 probe**를 실행하는지 조사. GN 방향은 후보 최종 상태에서 재계산하므로 완전히 같은 GN 벡터는 아니라는 제한을 분명히 기록.
4. E′와 9개 start의 final objective, `dmin`, end state finite 여부, cap 여부를 개별 검사. cap/NaN/추가 descent가 단 한 개라도 있으면 `UNRESOLVED_PRECISION`, unique MAP claim denied.
5. `truth` start가 operational E′/candidate selection 또는 R5_CERT 10-set에 들어오지 않는지 확인. CPU/BLAS 별 근접 cost를 전역 최적 증명으로 해석 금지.
6. K2의 5개 near-start는 사후 포렌식 observation. R5 common precision certification 전후 구분 및 distinct physical minima 개수 미주장.

## 3. R5-02 — field-block H1/H2/H3/CAL/H4 결론 민감도

1. 기존 `V.decide_v2`의 H1 log inflation, H2 DID, H3 oracle/iid MSE ratio, CAL log inflation, H4 separability/reproduction 수식을 `a10_r5.py`와 독립 비교.
2. 기존 S1V5 원본 **전체 유효 행**에 primary P convention을 적용하고, Ambiguous 행 삭제·선택적 제외가 없는지 확인. 한 field의 start 및 sensor seed를 독립 재표집하지 않음.
3. 재표집 단위: 독립 field block, B=4000, seed=20261029, 동일 bootstrap draw index로 E′와 대안 시나리오의 95% CI paired 비교. 각 아홉 global-start 시나리오는 실제 admissible row 대입으로 구현 가능한 witness.
4. 보수적인 per-row component min/max interval은 **모든 대안 선택의 통계량을 포괄하는 상하한**이며 실제 하나의 해 선택으로 구현된 결과라고 주장하지 않는다. Baseline CI 0 포함 → alternative 0 제외, 반대 방향, 부호·범주 verdict 변화 모두 잠재 반례로 검사.
5. `ALTERNATIVE_CHANGES_CONCLUSION`은 실제 구현 가능한 witness에서 하나라도 sign/CI-zero/verdict가 변한 경우에만 증명. 보수적 bound로만 변화 가능성이 있으면 `REVIEW_REQUIRED_POSSIBLE_CHANGE`, 안정성 자동 승인 금지.
6. Δerror²/D_ref², ΔNEES4, Δlogdet(P)의 전향적 numeric material flag를 별도로 계산하고 해당 field/arm/starting point 모두 기록. 비 SPD·비유한 대안 또는 input hash 실패는 fail-closed.
7. 한 arm 또는 필요한 셀·field가 누락된 SMOKE는 `NOT_EVALUATED_INCOMPLETE`이며 전체 H1/H2/H3/CAL/H4 결과 PASS가 아님.

## 4. 필수 음성·양성 fixture

- 10/10 fixed start+finite+uncapped+common probe positive.
- 1개의 cap, 1개의 probe descent <−1e−3, NaN/Inf, 중복 start, 누락 start, truth start 침입 시 전부 `UNRESOLVED_PRECISION`.
- C10 비 SPD/NaN 대안은 admissible=false 또는 fail-closed; one-arm 99% FAIL은 pooled PASS로 가려지면 안 됨.
- 복수 field의 paired H1 변화에서 95% CI verdict 변화가 감지되는지와 no-alternative positive 안정성, 추가 start를 field 하나로 잘못 계수하는지 검사.
- Archived DEV2 K1/K2에서는 새로운 수치 보정을 해선 안 되며 0/5개의 near-start 기존 포렌식 기록과 실제 R5 precision 인증 상태를 분리.

## 5. 정식 결론 / NO-GO

- 독립 감사자의 source/contract/input SHA 비교, 별도 계산자·세션 식별, 실제 아티팩트 원본 재해싱과 감사 서명 필수.
- 정식 판정 `ACCEPT_WITH_BOUNDARIES`, `REVISION_REQUIRED`, `REDESIGN_REQUIRED`, `BLOCKED_EVIDENCE` 중 하나.
- 수정본은 구현 기술 검증 후에도 `INDEPENDENT_AUDITOR_SIGNED=false`, `A010_SCIENCE_FROZEN=false`.
- DEV3 20–29 / HOLDOUT2 / reserve / 물리 RT는 그대로 NO-GO. 이전 C3, C3V4, H1 LOW/POSE_HIGH tan FAIL 및 H2 tan sign inversion 보존.
