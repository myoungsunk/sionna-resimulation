# D6 사전등록 — DR EKF 불일치 원인 판정의 독립 확증 (실행 전 동결)

이 문서와 `D6_SPEC.json`은 seed 8100–8399를 한 번도 실행하지 않은 상태에서 커밋한다. `confirm_dr_independent.py`는 `D6_SPEC.json`이 커밋되지 않았거나 수정된 상태면 실행을 거부한다. 결과를 본 뒤 기준·임계값·arm을 바꾸지 않는다. 추가 분석은 "사후(post-hoc)"로 따로 표기한다.

## 개발 단계에서 형성된 가설 (seed 6000–6299, 8000–8031)
H1 현상: B0 과신은 heading이 아니라 heading 조건부 XY(along-track) 성분에 있다.
H2 필요조건: 보정 불확실성이 없으면(oracle) 과신이 사라진다.
H3 모델 불일치는 필요조건이 아니다: 필터 모델과 정확히 일치하는 세계에서도 heading 불확실성이 큰 셀은 과신이다.
H4 기전 = EKF 선형화: 같은 데이터·모델에서 (근사적으로) 정확한 사후분포(PF)는 일관적이고, EKF 사후분포는 heading 분산은 맞지만 조건부 XY에서 PF와 어긋난다.
H5 상관 C 처리와는 무관하다.
H6 EKF 유효 영역: 모델 일치 세계에서 필터 σψ ≲ 5°이면 일관, ≳ 7°이면 과신.

## 설정
- seed 8100–8399 (N=300), 9셀(R2/R4/R5 × drift 0/1/2), 동결 생성기·EKF(`RUN_01a124ff`), 하네스 `dr_harness.py`(커밋된 버전).
- arm(정의는 `dr_harness.ARMS`): `B0`, `ORACLE_CAL`, `NO_C`, `A2_3_GAUSS_LEVEL`, `A2_3D_GAUSS_DEFAULT`, `CKF_A2_3`(서술용), `PF_A2_3`(20 000 particles).
- 통계는 R2-2와 같다(t ≥ 30 s 앙상블 ANEES, coverage, 말기 25 %). ENEES = EKF Gaussian 아래 PF 사후분포의 기대 NEES = `tr(P_EKF⁻¹P_PF) + dᵀP_EKF⁻¹d`.

## 판정 기준 (모두 `D6_SPEC.json`에 기계 판독 형태로 동결)
| id | 가설 | 기준 |
|---|---|---|
| C1_PHENOMENON | H1 | B0 9셀 모두: 조건부 XY 기여/2 > 1.5 그리고 > heading 기여 |
| C2_CALIBRATION_NECESSARY | H2 | ORACLE_CAL 9셀 모두: ANEES ≤ 3.6, 말기 ≤ 3.6, coverage ≥ 0.92 |
| C3_MISMATCH_NOT_NECESSARY | H3 | A2_3_GAUSS_LEVEL의 R2_d2, R5_d2: ANEES > 3.6 그리고 heading 기여 ≤ 1.5 |
| C4_EXACT_POSTERIOR_FIXES | H4 | R2_d1, R2_d2, R4_d2, R5_d1, R5_d2에서 PF ANEES ≤ 3.6 그리고 log 척도로 EKF보다 3에 가까움 |
| C5_EKF_POSTERIOR_ERROR | H4 | ENEES(EKF vs PF) > 10 (R2_d2, R5_d2), ≤ 4 (R2_d0, R4_d0, R5_d0), heading 분산비 PF/EKF ∈ [0.9, 1.1] (9셀) |
| C6_C_TERM_IRRELEVANT | H5 | NO_C vs B0: 9셀 모두 \|log ANEES 비\| ≤ 0.05 |
| C7_VALIDITY_REGION | H6 | A2_3D_GAUSS_DEFAULT: σψ ≤ 5° 표본의 ≥ 90 %가 ANEES_k ≤ 3.6, σψ ≥ 7° 표본의 ≥ 90 %가 ANEES_k > 3.6 (t ≥ 10 s) |
| S1_PF_STRICT_GATE (보조) | 배포 가능성 | PF_A2_3가 R2-2 전체 일관성 기준을 9/9 통과. FAIL은 PF를 그대로 해결책으로 쓰는 데의 한계이지 원인 판정을 뒤집지 않는다 |

개발 데이터에서 C1–C7은 모두 충족, S1은 7/9(R2_d2 말기 5.3, R5_d0 coverage 0.902; N=32).

## 판정어
- C1–C7 모두 PASS → **`CAUSE_CONFIRMED: EKF_LINEARISATION_UNDER_CALIBRATION_DRIVEN_HEADING_UNCERTAINTY`** (보조 원인: drift 2에서 기본 보정 prior 과소 → heading 자체 과신, 개발 데이터 근거).
- C2·C3·C4·C5 중 하나라도 FAIL → 원인 판정 `UNRESOLVED`로 기록하고 실패 기준을 보고한다.
- C1·C6·C7만 FAIL → 원인 판정은 유지하되 해당 서술(현상 범위·C 무관성·유효 영역 임계)을 철회/수정한다.
- R2-2 사전등록 판정(`DR_MODEL_MISMATCH_UNRESOLVED`)은 그대로 둔다. D6는 R2-2 기준의 "합법 구성" 목록을 바꾸지 않는다.
