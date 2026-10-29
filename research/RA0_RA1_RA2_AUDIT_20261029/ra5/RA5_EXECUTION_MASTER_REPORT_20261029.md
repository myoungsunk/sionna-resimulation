# RA5-0~6 및 선행 A4 전체 실행 보고서

실행일: 2026-10-29. 브랜치: audit/ra5-staged-execution-20261029.
정의: 실험 계산 성공과 과학적 승인/일반화 검증은 별도 판정. 2026-10-07 original H, raw, control, 역사적 RA4 score는 불변. RT 재생성 없음. 독립 감사인 부재(SELF_REVIEW_ONLY).

## 1. GitHub 실행 원장

| 과제 | Actions run | 판정 |
|---|---|---|
| A4 전 28조건 수학적 동일성·첫 mask 추적 | [40880297969](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40880297969) | 7/7 JOB PASS |
| A4 초기화·gyro·wheel/gyro noise 요인 | [40882051848](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40882051848) | 3/3 JOB PASS |
| A4 paired contrasts 및 R5-A first-flip | [40883153212](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40883153212) | v2 PASS |
| RA5-0 H/LoS/packet 원본 재생 및 RA5-1 수학 fixture | [40881073964](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40881073964) | 8/8 JOB PASS |
| RA5-2/3/5 실제 잔차 및 구조 진단, RA5-4/6 중단 | [40882451932](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40882451932) | 4/4 JOB PASS |

마지막 JOB PASS는 실행 프로토콜이 종료된 것일 뿐 RA5-4/5/6 연구 가설의 PASS가 아니다.

## 2. A4 full28/정의 통일

7 case × 4 gyro level = 28 trajectory-condition. 각 case에서 full-length sigma_b=0 -> ORIG 및 mu_M=mu_B 대응 arm 동일성 검사: 392/392 PASS. LEGACY/PRIOR × fixed/self first mask 추적 56/56 완료. First divergence 이전 x/P/sigma 일치 56/56. gyro bias 이외 sensor source 변화 검산 28/28. 모든 source 기존 H, mu, R, original mask 유지. 단 과학적 RF 모델 검증 아님.

최초 first-flip packet 대표값: R2_aA_m0 B0 28(L0/L1/L2 26), R2_aB 11, R2_aA_m45 37, R4_aA 373, R4_aB 14, R5_aA 217, R5_aB 33.

### 초기상태·센서 요인 (선택 3개 canary)

R5_aA_m0, R5_aB_m0, R2_aA_m45에서 5개 2수준 요인 32 조합 × BASE_FIXED/SELF_NIS 각각 총 192 trajectory arms. factor: initial XY alt, heading alt, B0/L2 gyro bias, wheel noise seed alt, gyro noise seed alt. 원본 RF packet, mu, R, P0, time과 점수 채점 자료 불변. BASE_FIXED는 원래 seed0 수용 mask를 통제군으로 고정. wheel noise의 ds 변화는 Q=2e-5|ds|를 함께 바꾸므로 pure fixed-Q wheel-noise effect가 아님.

SELF_NIS Heading RMSE에 대한 요인별 대응 차이(상태1−0, 다른 네 요인의 16쌍 평균, 단위 deg):

| Factor | R5-A | R5-B | R2-A m45 |
|---|---:|---:|---:|
| init XY | -0.47485 | +0.03841 | +0.05335 |
| init Heading | -0.62011 | +0.22675 | +0.01459 |
| gyro bias L2 | +0.70022 | -0.10940 | -0.08885 |
| wheel noise alt (+Q change) | -0.45851 | +0.07614 | +0.05916 |
| gyro noise alt | -0.09312 | +0.00035 | +0.13101 |

단일 대체 seed, 같은 Corridor의 선택된 사례만이므로 population noise variance 인과 기여 또는 일반화 결과가 아니다. 사례별 부호 상이.

### R5-A 첫 수용 1 packet만 거절한 반사실

B0 MB_VAR_LEGACY, 최초 차이 k=217, t=43.4s. SELF_NIS가 수용하고 BASE_FIXED가 거절. 첫 packet만 SELF_NIS에서 강제 거절하고 그 뒤에는 원래 SELF_NIS NIS 규칙 복귀.

| 실행 | Heading deg | XY cm |
|---|---:|---:|
| BASE_FIXED | 3.8325895 | 39.59727 |
| SELF_NIS 자연 | 8.8862221 | 87.74529 |
| SELF_NIS 첫 추가 수용 1개만 강제 거절 | 8.8367189 | 87.26883 |

첫 추가 수용 거절로 Heading 개선 0.049503 deg, XY 개선 0.476466 cm. 고정 vs 자기 gate 최종 격차 전체의 설명으로 일반화 불가. 초회 mask 차이가 재귀 분기의 시작은 맞으나 이후 수용·거절 및 모델 오차·상태 피드백이 큰 부분을 차지한다. 같은 prior NIS 2x2에서 R5-A 첫 플립은 mu_M만 적용해도 수용되며 BB_VAR만으로는 수용되지 않는다.

## 3. RA5-0 original H/LoS/packet — PASS_SOURCE_REPLAY

원본 Full/LoS/SAMPLES/B0 CONTROL/FFD SHA 7/7, 257 f-bin 재검산. 전체 9,519 H/LoS pose, 주요 timeline 7,251 packet-case rows. Full H->CIR->first path r,s native parity: max abs r error 3.56e-15m, s error 2.23e-16. 각 pose의 s0 first tap, s1 next tap, ds1=s1-s0, Full-LoS oracle 차이를 해시 연결 원장으로 확보. 온라인 하드웨어 adjacent tap 제공과 독립적 물리 경로 정확성은 미검증.

## 4. RA5-1 joint covariance 음성 시험 — PASS_METHOD_ONLY

Invertible [r,s0,s1]↔[r,s0,ds1]와 J,R 동시 변환 후 posterior X/P 최대 차이 4.17e-16 / 3.47e-18, NIS 차이 6.76e-14. 동일 관측 d0 중복 사용 시 추가 Fisher 0, 잘못 대각화하면 spurious information 발생하는 음성 fixture PASS. MA(1) first-difference noise Var=2σ², lag1 Cov=-σ² 재생. 조건부 Fisher/Schur 및 수치 rank fixture PASS. 이것은 RF 기반 신규 정보 발견이 아닌 synthetic 수학 검증.

## 5. RA5-2 실제 Corridor 오차 재분석 — RETROSPECTIVE_PASS / TIME_FIELD_BLOCKED

7 case, 3 route, 독립 scene 수 1. Full-LoS 결정론적 관측 차이를 진단용 모델 잔차로 사용, 센서 독립 잡음 R로 취급하지 않음. LORO train-only 잔차 covariance:

| Held route | train rows | test rows | corr(e_r,e_s) | corr(e_s,e_ds1) | Var(e_ds1\|e_r,e_s) |
|---|---:|---:|---:|---:|---:|
| R2 | 4314 | 2937 | +0.24884 | +0.36941 | 0.0041631 |
| R4 | 5767 | 1484 | +0.26056 | +0.38708 | 0.0038705 |
| R5 | 4421 | 2830 | +0.07891 | +0.44908 | 0.0033087 |

e_ds1=(s1_full−s0_full)−(s1_los−s0_los). 두 tap의 정확한 공분산 변환 및 residual covariance PSD 검사 PASS. 양의 조건부 잔차 분산은 conditional Fisher Delta I >0의 증명이 아님. 동일 정적 scene의 시간별 독립 RF 실현이 없어 spatial field vs temporal process 식별 불가능(BLOCKED_STATIC_H_SINGLE_REALIZATION).

## 6. RA5-3 geometry×Sigma 통제 — METHOD_DIAGNOSTIC_PASS

7 case의 original FFD LoS Jacobian J를 outcome에 의존하지 않는 사전 선택 25%/75% packet pose에서 계산, 동일 원 R에서 synthetic scale 0.5x/2x 변화시킨 28 matched-prior cells 검사. Fisher, Heading posterior SD, nuisance marginalization 수치 계산. 실제 공간 재질 변경, 측정 잡음 재추정, 새로운 RF 환경이 아님. Heading 개선·새 scene 전파 claim 금지.

## 7. RA5-4 conditional ds1 online filter — BLOCKED_INPUT_MODEL

저장 복소 H에는 다음 tap이 존재하지만 실제 UWB 하드웨어의 포트 동기 및 tap 제공은 미확인. 추가 tap의 온라인 h1 및 Jacobian J1, r/s0/ds1의 calibrated stochastic joint R 3x3 및 tap/port switching noise 미검증. 기존 deterministic Full-LoS 오류 covariance를 sensor R로 치환하지 않음. 실제 R0/R2/R3 EKF와 새로운 feature 정보량 scientific PASS는 실행 금지; RA5-1의 대수 동등성만 PASS.

## 8. RA5-5 b_s latent state — STRUCTURE_ONLY / FULL_FILTER_BLOCKED

원본 FFD Jacobian과 고정 40 packet window, 7 case×3 windows×3 b prior = 63 observability/Schur nuisance rows 검산. 가정: 해당 window에서 b_s constant, prior b std=0.02/0.1/0.5. 구조적 Gramian rank는 선택한 state dynamics의 조건부 판별이며 실제 white/colored covariance 및 independent temporal process 정당성을 증명하지 못함. 4-state vs 5-state full-EKF validation 중단.

## 9. RA5-6 new scene TEST — BLOCKED_EXTERNAL_HOLDOUT

이번 실행에는 사전에 SHA 동결된 신규 독립 scene/route/measurement TEST가 등록되지 않았다. Corridor 3 route 및 기존 탐색된 Office는 회고적 DEV로 유지. 미실행 TEST에 대해 일반화 accuracy/cov calibration을 주장하지 않는다.

## 10. QA·잔여 조건

- 첫 A4 집계 run [40882948861](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40882948861)은 DataFrame 컬럼 인덱싱 타입 오류로 분석 전에 실패했으며, 수정된 v2 [40883153212](https://github.com/myoungsunk/sionna-resimulation/actions/runs/40883153212)는 동일 원본 실험자료를 재사용하여 PASS. 첫 실패 기록 보존.
- 동일 브랜치 push에서 자동 실행된 별도 powerjoint-separate-rs-model-validation 워크플로는 실패했음. 본 RA5 성공 workflow 범위와 혼동 금지; 전체 repository CI green 아님.
- G3 R2_aA ray62의 unmerged strict 잔차 문제는 독립 물리 검증 미완료. 원 H source parity를 전체 물리 모델 정확성으로 확대 금지.
- 과학적 독립 audit 서명 없음(SELF_REVIEW_ONLY).
- 다음 scientific gate: 실제 인접 tap·포트 동기, full joint stochastic covariance와 tap-switch robustness, 추가 tap Jacobian, 반복 pose 시간 실현/화이트-컬러 구분, 4v5 필터의 사전 동결, 완전히 새 unseen environment, independent auditor.

최종 상태: A4_TECHNICAL_PASS; RA5-0_PASS; RA5-1_PASS; RA5-2_RETROSPECTIVE_PASS_TIME_BLOCKED; RA5-3_METHOD_ONLY; RA5-4_BLOCKED; RA5-5_STRUCTURE_ONLY_FILTER_BLOCKED; RA5-6_BLOCKED_NEW_TEST; SCIENCE_RELEASE_SELF_REVIEW_ONLY.
