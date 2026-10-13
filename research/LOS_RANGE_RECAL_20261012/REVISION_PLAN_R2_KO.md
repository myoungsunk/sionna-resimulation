# P0~P5 코드 감사 반영 수정 계획 (R2) — PLAN_ONLY

상태: 계획만 있음. 이 문서 이후 실행은 사용자 승인 후 단계별로 진행한다. 기존 R1 결과 파일은 수정하지 않고 보존한다(정정은 별도 ERRATA로 추가).
경계 유지: `scientific_PASS=false`, `stage_B_allowed=false`, V02 LARGE FAIL 불변.

## 1. 감사 항목 대조 (코드 직접 확인)

| # | 감사 지적 | 확인 | 근거 |
|---|---|---|---|
| H1 | P5 Native 6D EKF 사전 정합 미완 | **맞음** | `P5_GATE.md` 자체에 "NOT done" 기재. 결과는 G7 sensor-v2 harness 한정 |
| H2 | 케이스별 저장 RF 재사용 → 128 seed ≠ 독립 RF 128개 | **맞음 (구조상)** | `p5_arm_ranges.py`는 12 케이스마다 npz 1개(`delta_*`)를 저장; `p5_build_harness.py`는 seed와 무관하게 `arms_np[_dkey][ids]`를 range에 더함. seed가 바꾸는 것은 harness 내부 센서/잡음 경로이며, 그 range 잡음 경로의 세부는 이번에 재확인하지 않았음(R2-1에서 확인) |
| H3 | A_DR(RF off) 자체의 NEES/coverage 실패 | **맞음** | P5: A_DR 평균 pose NEES 62.9, coverage 64.2 % |
| M1 | E1 correction을 noise-free H로 사전 계산 | **맞음** | `p5_arm_ranges.py`의 `det_for()`가 `cir_mag(H)`를 잡음 없이 호출. P4의 noisy-CIR 평가(snr30/snr10)는 EKF 수준에서 재현되지 않음 |
| M2 | BEST_PLUS_R_IAT의 IAT=5.8 동일 scene 사용 | **맞음** | `IAT_COND=5.8` 하드코딩(V05, 같은 3 route에서 추정) |
| M3 | P4가 LoS에서 E1 미채점 | **맞음** | `p4_blind_range_eval.py`: `if ch=='los': arms=['B']`. LoS 열의 chosen 오차는 CSV에 있으나 요약/CI에 미반영 |
| M4 | per-run trace·재시작 driver 미보존 | **맞음** | chunk/arm SHA만 보관, driver 셸 스크립트는 scratchpad |
| S1 | P3 pooled "site-weighted" RMSE가 fold 합산 시 pose 수 `n` 가중 | **맞음** | `p3_detector_candidates.py:58` `np.sum(n*q.rmse_site**2)/n.sum()`. fold 내부는 site MSE 평균, fold 간 합산은 pose 가중 → 전역 site 균등 아님. (P3 동결 선택이 뒤집힐 가능성은 낮으나 공식 수치 재계산 필요) |
| S2 | leakage 테스트 일부는 키 존재만 확인 | **맞음 + 내 문서화 과장** | `fold_params_recorded_for_train_only`는 `loro_fold_params`에 키가 있는지만 검사. 파일 docstring의 "(4) coefficients depend only on TRAIN rows"와 코드 주석의 refit 비교는 **구현되지 않았음**. P3_LEAKAGE_TESTS.json의 `all_pass: true`는 이 항목에 대해 근거가 되지 못함 |
| S3 | "구별 불가 ≠ 동등" | **맞음 + 내 서술 과장** | P5_GATE의 "'not worse than A'" 표현은 근거 부족. TOST/비열등성 한계 없이 쓸 수 없음 → 정정 |
| S4 | CI는 12조건 재표본, 기하는 단일 scene 3 route | **맞음** | 보고서에 "시뮬레이션 조건 내 비교 불확실성"으로 명시 정정 |
| S5 | P4(전체 fit 계수)와 P5(fold 계수)가 다른 계수 집합 | **맞음** | P4 `P3_FROZEN_MODEL.params` vs P5 `loro_fold_params`. P5 결과를 P4 동결 모델 성능으로 읽을 수 없음 |

## 2. 즉시 정정 (실행 비용 ≈ 0, 새 계산 없음) — R2-0
1. `ERRATA_R2_KO.md` 추가(R1 파일은 그대로): S2(leakage 테스트 범위 과장), S3('not worse than A' 철회), S4(CI 해석), S5, M3(P4 LoS는 B만 채점), H2(seed ≠ 독립 RF)를 명시.
2. `P0_P5_GATES_SUMMARY_KO.md`/`P5_GATE.md`는 삭제·덮어쓰기 하지 않고 ERRATA에서 참조. 허용 주장 문구를 "시뮬레이션 harness 내 정확도 개선, 일관성 미확립, 일반화 미검증"으로 고정.

## 3. 수정 단계 (감사 권고 우선순위 순)

### R2-1 P5 재현성·온라인 관측 계약 감사 (가장 먼저)
- 코드 감사만, 새 채널 생성 없음: harness에서 seed가 실제로 바꾸는 요소를 표로 확정(trajectory/IMU/wheel/range 잡음/RF 실현), 저장 RF가 seed 간 동일한지 코드로 증명.
- 결과 해석 수정: 128 seed = "센서·잡음 반복", RF 실현은 12개 고정. 유효 표본 수를 RF 기준 12(조건)·site 기준으로 보고.
- driver·chunk 재개 스크립트를 repo에 커밋(`p5_confirm_driver.sh`), per-run 핵심 시계열(range 입력, innovation, pose error)을 압축 저장하는 옵션 추가(기본 off, 용량 보고 후 결정).
- 종료 기준: 입력/잡음/수신 특징량/필터 입력 계약표 + 재현 스크립트 + 변경 없는 집계 수치 재현.

### R2-2 A_DR NEES 실패 원인 분해 (RF off)
- 단일 변수 제거 실험: ① P0 prior(pose SMALL 3 cm/2°) vs 생성기 실제 초기 오차 ② IMU bias/noise 모델 vs F/G/Q ③ wheel 모델 ④ 시간 이산화·gate ⑤ 보정 prior(config) 정합. 각 항목에서 NEES 비 및 coverage 변화를 보고.
- 입력 정의: 필터 가정(F/G/Q/P0)과 생성기 파라미터를 나란히 놓은 감사표, 각 항목 불일치 크기.
- 종료 기준(사전 동결): A_DR 평균 pose NEES가 χ² 구간(자유도 3 기준) 안, coverage 95 % 구간 안. 못 맞추면 "DR 모델 불일치 미해결"로 기록하고 이후 RF 일관성 주장은 보류.

### R2-3 E1 + fold-wise 잔차 공분산/IAT (정확도 유지, 일관성 개선)
- 누수 제거: IAT를 학습 fold에서만 추정(LORO fold-wise) → BEST_PLUS_R_IAT 재평가. 5.8 상수 폐기.
- 온라인 noisy-feature E1: EKF 입력 delta를 snr30/snr10 잡음 CIR에서 per-seed로 생성(seed마다 새 잡음 → RF-잡음 독립성 개선), noise-free 사전계산과 비교.
- 시간상관 편향을 R 팽창이 아닌 구조로 분리: (a) 조건부 평균 편향(E1) (b) 잔여 분산 (c) 시간상관 성분(Gauss–Markov bias 상태 또는 Schmidt) 을 별도 arm으로 비교. 평가 지표는 정확도와 일관성(NEES/coverage/ACF)을 분리 보고.
- 동등/비열등 판정은 TOST로 사전 한계(예: NEES 비 ±25 %, coverage ±5 pp)를 동결한 뒤 수행. 한계 없이 "구별 불가"로 쓰지 않는다.

### R2-4 통계·구현 수정 (R2-3 앞에 병행 가능, 계산량 작음)
- P3 pooled site-weighted RMSE를 전역 site 균등 가중으로 재계산(`P3_RECOMPUTE_GLOBAL_SITE_WEIGHT.json`), 선택 규칙(≤0.95·B, 전 fold 개선) 재적용해 E1 유지 여부 확인. 뒤집히면 공개 정정.
- leakage 테스트 재작성: (i) 평가 route 라벨을 임의 섞어 재학습해 계수 비트 동일 확인 (ii) 학습 row 마스크에 평가 route 포함 여부 직접 assert (iii) 각 fold 학습 입력 해시 기록. 결과 `P3_LEAKAGE_TESTS_V2.json`, v1은 보존.
- P4 LoS 채점: E1을 LoS 채널에도 적용한 RMSE/CI를 별도 보고(Full-RF 보정 성과와 LoS detector 성과 분리).
- P5가 사용한 fold 계수에 대해서도 P4 형식의 blind 평가를 1회 추가(S5 해소).

### R2-5 새 scene·anchor geometry에서 P4 재검증
- 사용자 승인 필요(새 scene 확보). 승인 전까지 NOT_RUN. 코드는 `p4_*`를 scene 인자화하는 수정만 준비.
- 종료 기준: 사전 동결한 판정(점추정 ≤ −10 %, CI 상한 < 0)을 새 scene에서 동일 적용. 미충족 시 GENERALIZATION_FAILED로 기록.

### R2-6 E1 Range + 편파 s EKF 통합 (R2-2 종료 후에만)
- Stage B V06 연결. Range-only와 RF heading 추가 효과를 독립 평가. DR 일관성(R2-2)이 해결되지 않으면 수행하지 않음.

## 4. 순서와 중단점
R2-0 → R2-1 → R2-4 → R2-2 → R2-3 → (승인) R2-5 → R2-6. 단계 사이마다 짧은 상태 보고 후 승인을 기다린다.
예상 비용 감각: R2-0·R2-1·R2-4는 수 분~수십 분(재계산·코드 감사), R2-2는 단일 변수 replay 다수(수십 분), R2-3은 P5급 replay 재실행(≈ 13분×arm 수 확장), R2-5는 scene 확보에 의존.

## 5. 이 계획이 하지 않는 것
R1 결과 파일 수정·삭제, `scientific_PASS` 변경, Native range-only 실험에 대한 주장, 새 scene 없이 일반화 주장, R 팽창만으로 NEES를 맞추는 접근.
