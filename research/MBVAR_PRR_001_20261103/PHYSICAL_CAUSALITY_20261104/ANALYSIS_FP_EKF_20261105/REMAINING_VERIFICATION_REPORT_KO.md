# FP–EKF 후속 검증 실행 결과 (2026-11-05)

**판정:** `C0_NEW_154_PAIRS_PASS / C1_FROZEN_GAIN_AND_GATE_EXPLORATORY_PASS / C2_WINDOW_OBSERVATIONAL_PASS / C2_TRUE_4D_RECURSIVE_NOT_RUN`  
**제약:** NONINDEPENDENT_EXPLORATORY, 사후 사례 선택, 온라인 GT 이용 없음, 원본 필터·RF 자산 변경 없음.

## 이번에 실행한 항목

1. GitHub Actions #41958274374의 신규 shard 0–3에서 복소 H, CIR, FP를 사용하여 Full–LoS **154쌍(308 신규 작업)** 재계산. R4 118쌍, R5 36쌍. 154쌍 중 FP index 차이 69건, |Full−LoS signed-s|>0.1 68건. 원본 C0-A FP index 불일치 **0**; FFT 최대 오차 `6.9389e-17`, FP s 최대 오차 `7.4940e-16`, 관측 분해 항등식 오차 `5.5511e-17`. `PR36_FULL_SHARDS_PAIRED.csv` 및 `PR36_FULL_SHARDS_QA.json`.
2. 기존 #39376076166 POWER1 Full B0의 1,079개 짝수 시점에 대해 저장된 K_ψ와 innovation·NIS에서 실현 가능한 S 후보를 복원하여 FF, FL, LF, LL, FP-s-only, FP-s-and-range의 게이트 고정/재평가 단일 갱신 대조 결과를 검사. `C1_ALL_P0_B0_EVEN_FROZEN_AND_SELFGATE.csv`, `C1_GATE_QA.json`, `C1_GATE_AND_HEADING_SUMMARY.csv`. **오차가 바뀐 후 H 및 K를 재계산하지 않았으므로 4차원 full-state 반사실 재귀가 아님.**
3. 원래 R4/R5의 **8개 사전등록 시간창**에 대해 C1 짝비교 및 기존 자연재귀 시계열의 RF·NEES 관련성을 집계. `C1_WINDOW_LEVEL_PAIRED_RESULTS.csv`, `C2_TEMPORAL_WINDOW_ASSOCIATIONS.csv`.

### 대표 동일-gain 편파 정정 결과

| 사례 | 원본 Heading RMSE (°) | 편파만 Native-LoS 대체 후 (°) | 해석 |
|---|---:|---:|---|
| R4 초기 0–15초, 38개 짝수 시점 | 1.6135 | 1.5161 | 동일-gain 한 시점 교체 집계의 평균적 개선. 실제 재귀 이득 아님 |
| R4 33–35.2초, 6개 시점 | 2.0811 | 1.8670 | 기존 C0-A와 EKF trace 사용, 해당 창 신규 shard의 RF 짝 없음 |
| R4 99–105.4초, 16개 시점 | 1.4081 | 1.4053 | 영향 작고 오차 개선/악화 사례 혼재 |
| R5 92–94초, 6개 시점 | 0.4026 | 0.4050 | 편파 교체가 단일 시점 평균 RMSE를 소폭 악화 |
| R5 132–135초, 8개 시점 | 0.5420 | 0.5211 | 작은 변화 |

주의: 각 시점은 **원래 Full 시점의 prior를 공유하는 독립 1-step**이며 행들 사이에 새로운 상태 추정치를 전달하지 않음. 일정 시간창의 값이라도 일반적인 time-series intervention의 RMSE로 인용 금지. `C1_WINDOW_LEVEL_PAIRED_RESULTS.csv`의 `n_full_rf=0`은 이번 308 신규 key에 없다는 뜻; 이전 사용 가능한 자료가 없다는 뜻이 아니다.

### 기존 자연재귀 진단의 차이

- R4 59–61초: FP 이동 0건, |e_s| 평균 0.01463, Heading NEES 평균 **45.46**, Heading95 0%. 상태오차 이력이 지속되는 현상과 일치하지만 특정 과거 오염을 원인으로 확정하지 못함.
- R4 99–105.4초: FP 이동 15/33, NIS 평균 7.412, Heading NEES 평균 **46.28**, Heading95 0%. 오염과 과신이 공존하나 게이트와 과거 상태오차를 분리해야 함.
- R5 92–94초: FP 이동 7/11, |e_s| 최대 1.298, NIS 평균 30.86, Heading NEES 평균 **0.106**, Heading95 100%. FP/편파 오염의 크기만으로 EKF 과신을 설명하는 가설의 반례.

## 남은 검증의 정확한 경계

- **C2 동일 initial state, controls, noise seed로 FF/FL/LF/LL 각각 t=0부터 갱신하는 실제 자연재귀 시험은 미실행.** 이를 수행하려면 원래 `build_positive_bias_controls`, SourceFFD 모델과 frozen calibration/bank, 경로별 원본 시간 정렬, OOF mu/R, 전체 측정 z, 초기 x/P, 원래 joint gate를 실제 재생성하고 F/F 원본 trace 패리티부터 만족해야 한다. 저장된 `state`, `P`, `NIS`, yaw K 부분만으로는 상태가 변경된 뒤 H(x−), h(x−)를 계산할 수 없다. 동일 prior 단일 시점 수치를 이어 붙이면 **잘못된 인과 결과**가 된다.
- **C0 반사면 물리 개입:** 신규 Actions shard에서 확보된 RAW_H/FIRST_PATH 154쌍은 사용했지만 완전한 개별 ray path 계수/반사면 기록을 이번 실행에서 전수 재검산한 것은 아니다. 원본 Release `handoff.tar.gz` 838MB의 ray 상세 경로 입력을 별도 materialize 및 원본 H 재합성 패리티 검사해야 한다.
- **불확실도 성장과 과신을 구분:** P의 시간적 증가는 F/Q와 게이트/측정 효과의 합이며, 실제 오차 증가와 P 감소는 모델 불일치가 수용 갱신에 반영되지 않는 과신을 설명한다. `NEES`·coverage는 GT와 이전 경로 이력에 의존하므로 단일 스냅숏의 국소 오염과 동치가 아니다.

## 원본 출처

- PR36 workflow: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41958274374, SHA `507d7d38d2ae4159c1a401a996ccbb580dc4a961`.
- C0-A: https://github.com/myoungsunk/sionna-resimulation/actions/runs/41783949902.
- Frozen historical POWER1: https://github.com/myoungsunk/sionna-resimulation/actions/runs/39376076166.
- 관측체인: https://github.com/myoungsunk/sionna-resimulation/blob/proposal/mbvar-prr-one-shot-extract-20261105/src/qclean_uwb/drivesim/observation.py.
