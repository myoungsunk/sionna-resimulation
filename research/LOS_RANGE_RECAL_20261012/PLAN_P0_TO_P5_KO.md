# LoS First-Arrival Detector Bias 재보정: P0 → P1 → P2 → P3 → P4 → P5 실행 계약

작성: 2026-10-12 · 상태: PLAN_ONLY · 기준 저장소: `myoungsunk/sionna-resimulation` · 기준 소스 HEAD: `claude/practical-goodall-wnsjv4@25b504f29e382bac52bf5aa01a54f79b9e6d6f41`

> **실험 결과를 숨기지 않는다.** 기존 `research/LOS_RANGE_RECAL_20261012/REPORT_KO.md`의 LORO 탐색 결과(12조건, 16,432 pose)는 Full-RF range RMSE가 고정 offset에서 **0.143847 m**, LoS constant refit **0.145249 m**, LoS affine refit **0.144594 m**였다. 새 보정은 각각 약 **0.98%, 0.52% 악화**됐다. 이는 거리 측정의 평가이며 6D EKF의 position/heading 결과는 아니다. 동일 복도 내 route holdout일 뿐 외부 geometry holdout도 아니다. 새 상수 offset으로 성능이 반드시 개선된다고 가정하지 않는다.

## 0. 실행 전 공통 계약

1. 단계는 P0→P1→P2→P3→P4→P5 순서로 시행. 단계의 **실제 실행 증거**와 gate를 기록하기 전 다음 단계의 과학적 승인 금지. P1 실패는 기존 offset 유지 후 P2로 넘어가는 **정상적인 의사결정 분기**다.
2. 평가 입력: `research/V01B_CLOSURE_20261012/G7/out/01_FEATURES_12.csv`(관측)와 `02_LABELS_EVAL_ONLY_12.csv`(평가 전용). `(case,route,pose_id)` one-to-one 결합 및 12조건/R2,R4,R5×anchor A,B×mount 0°,45° 확인. 같은 XY의 여러 yaw, 동일 tap, 인접 주행 tick을 독립 site로 간주하지 않는다.
3. 원본 수신기/FFD/LUT/source hash와 Python, NumPy, BLAS, Sionna 버전, seed, site-split, 실행 명령 및 원시 측정 SHA를 `RUN_MANIFEST.json`에 고정. LFS pointer는 실제 FFD 데이터로 인정하지 않음. 각 run은 새 output directory 사용, 기존 결과 덮어쓰기 금지.
4. 원래 detector는 257 frequency bins → Hann → 4N zero-padded IFFT → strongest RX 선택 → peak의 30% leading edge first-arrival. 참고한 `codex/noisy-probe-ekf-sionna-20261010`의 `scripts/drive_sim/calibrate_body_range_los.py`, `replay_independent_los_range_calibration.py`, `src/qclean_uwb/drivesim/observation.py`는 **별개 브랜치 소스**다. 같은 버전이라고 가정하거나 원본 코드에 즉시 덮어쓰지 않는다. G7 `obs_frozen`과 동일 복소 H에서 tap, range, P1/P2, s를 먼저 parity 검증.
5. 단위/부호: `e_LoS = range_los-d_true`, `e_MP=range_full-range_los`, `e_full=e_LoS+e_MP`. 고정 기준 `b_old=-0.5315983906250129 m`. EKF에서 `h(x)=d(x)+b` 또는 `z_corrected=z-b, h(x)=d(x)` 중 한 방식만 사용; offset 두 번 적용 금지. 실측 하드웨어 antenna delay는 UNKNOWN으로 두고 detector shift와 혼동 금지.
6. 학습·검증·시험 물리 site, route, scene을 분리한다. 학습/calibration site의 정답 기하 거리는 계수 적합에 허용하지만, **held-out 평가 데이터의 true distance, LoS-only oracle, reflection ID, clean-H 통계, 향후 EKF truth를 온라인 feature/모델 적합/gate 튜닝에 사용하지 않는다.** 모델 예측을 저장한 뒤 평가 프로세스에서만 truth를 열어 채점한다.
7. G7의 기존 strict replay mismatch(309/4,200)와 V02 LARGE 일관성 FAIL을 임의로 해제하지 않는다. 이 계획의 일부 PASS는 전체 연구 `scientific_PASS` 승인이 아니다.
8. 1차 paired 비교는 raw H/RF packet, IMU/wheel, 물리 궤적, x0/P0, F/G/Q/R, gate, timestamp, seed를 고정. detector·bias·R의 변경은 서로 분리한 arm으로 수행. 결과는 site-weighted vs pose-pooled, noise-free vs noisy, drive vs turn/probe를 명시하여 산출.

## P0 — 재현성·기준선·사이트 분할 확정

**입력:** G7 두 CSV; 기존 `research/STAGE_B_EXPLORATORY_20261012/v04_range_decomposition.py`, `out/v04_summary.json`; `research/LOS_RANGE_RECAL_20261012/loro_bias_audit.py` 및 기존 보고서; frozen observer/FFD/LUT 원본.

**순서:**
1. Git SHA/입력 SHA/행 수/비결측/unique key와 LFS 실파일 점검. G7 feature-label 합친 행 수가 16,432인지 확인; 달라졌다면 즉시 FAIL.
2. 기존 V04 합성 항등식 오차 `<=1e-9 m`, `mean e_LoS=-0.5361299649 m`, `mean e_MP=+0.0524597870 m`, `mean e_full=-0.4836701779 m`, tap switch=0.39398734를 독립 재계산. 기존 `v04_range_decomposition.py`의 하드코딩 절대경로를 실행 시 인자로 바꾸기 전 휴대성 PASS 금지.
3. 원본 관측기 parity·부호 계약·calibration vs evaluation read boundary 테스트.
4. LORO R2/R4/R5를 탐색 비교로 고정. 동일 XY/yaw의 site grouping 및 신규 독립 geometry blind test 계획을 `TRAIN_VAL_TEST_SITE_SPLIT.json`에 동결. 훈련과 평가 site가 겹치면 FAIL.
5. 기준 지표와 weighting을 사전 지정: primary=physical-site-weighted Full-RF range RMSE, secondary=LoS RMSE, mean, centered SD, abs-P95, missed detection, group-wise worst cases. LORO 기존 결과의 pose-pooled 값과 site-weighted 값을 혼동하지 않는다.

**read-only 점검 명령 (repo root):**
```bash
git rev-parse HEAD
git lfs ls-files
test -s research/V01B_CLOSURE_20261012/G7/out/01_FEATURES_12.csv
test -s research/V01B_CLOSURE_20261012/G7/out/02_LABELS_EVAL_ONLY_12.csv
sha256sum research/V01B_CLOSURE_20261012/G7/out/01_FEATURES_12.csv
sha256sum research/V01B_CLOSURE_20261012/G7/out/02_LABELS_EVAL_ONLY_12.csv
```

**신규 구현 TODO:** `p0_preflight.py` (현재 미구현). **산출:** `P0_INPUT_MANIFEST.json`, `P0_BASELINE_AUDIT.csv`, `TRAIN_VAL_TEST_SITE_SPLIT.json`, `P0_GATE.md`. **PASS:** 출처/데이터/parity/split/기준선 모두 통과; 아니면 P1 차단.

## P1 — 기존 고정 offset 대비 상수/선형 재보정 개선량 우선 확인

**비교 arm:** A(raw, no offset), B(existing fixed offset −0.5315983906250129 m), C(training-LoS constant), C2(training-LoS affine). Full-RF held-out measurement 평가에 LoS training offset을 적용하되 held-out full-RF truth로 보정하지 않는다.

**이미 존재하는 실행 명령:**
```bash
python3 research/LOS_RANGE_RECAL_20261012/loro_bias_audit.py
```
`loro_bias_audit.py`는 `loro_metrics.csv`, `loro_summary.json`을 기록하도록 작성됨. 보고서는 GitHub에 있지만 생성 결과 두 파일의 게시 상태는 아직 검증되지 않았다. P1에서 재생성한 뒤 실제 SHA·행 수·기존 수치와 비교하여 commit/receipt를 남긴다.

**기존 탐색 결과(Full-RF, 16,432 pose pooled):** raw 0.502326 m; B **0.143847 m**; C 0.145249 m(악화 0.98%); C2 0.144594 m(악화 0.52%). R2/R4/R5 모두 refit이 기존보다 나음이 확인되지 않음. 이 결과를 EKF RMSE로 해석하지 않는다.

**추가 계산:** site/route/mount별 mean·SD·RMSE·absolute P95, paired site/route cluster CI. 독립 route가 3개뿐이고 scene은 하나여서 통계적 일반화 제한을 기재. C/C2 선택에 held-out 성능으로 재튜닝 금지.

**산출:** `P1_LORO_COMPARISON.csv`, `P1_LORO_SUMMARY.json`, `P1_DECISION.md`. **판정:** C/C2의 Full RF holdout 이득이 없으면 B 유지·상수값 재튜닝 중지·P2 진행. 기존 보고는 이 분기에 해당하며, 재현 성공 여부를 새로 기록해야 P1 완료로 표기.

## P2 — Flat/FFD-LoS/Full-RF detector 편향과 tap 선택 분해

**목적:** 고정 offset만으로 해결하지 못한 구조적 오차가 어디서 발생하는지 인과적으로 분리.

1. **같은 물리 거리·각도·주파수·관측기**에서 ① flat-spectrum ideal LoS, ② 원본 FFD 복소 LoS, ③ full multipath RF를 관측. `e_flat`, `e_FFD`, `e_MP`를 별도 산출. flat/FFD의 비교에서 spectrum/waveform 변경 외 변수를 고정.
2. tap, strongest RX, peak, firstpath range, P1/P2, detected flag, SNR 및 (scoring-only) true delay를 기록. 기존 V04 Full-vs-LoS tap switch 약 **39.40%**를 같은 12조건에서 재검산.
3. 거리 <5 m / 5–10 m / ≥10 m, anchor A/B, mount 0/45, yaw·입사각, fractional tap phase에 따라 staircase/threshold bias 확인. 4N zero-padding은 표본 격자 개선이지 물리 대역폭/경로 분리능 개선이 아님.
4. noise-free, SNR 10, 30 dB는 별도 실험군. 잡음이 없는 기존 16,432행에 신규 noise 실험을 동일 run처럼 합치지 않는다. 잡음/seed/threshold 검출률을 같이 남긴다.
5. 동일 XY의 반복 yaw와 반복 thermal noise를 구별하고 shared tap/site bias, centered variance, spatial/distance-lag correlation을 평가. `drive`와 `turn/probe`는 분리; pose_id 순서를 그대로 초 단위 시간 ACF로 해석 금지.
6. antenna lever-arm·phase center는 알려진 geometry에 한해서만 모델링. 측정하지 않은 hardware group delay/clock offset을 추정된 수치로 주장 금지.

**TODO:** `p2_detector_components.py`(아직 없음); 기존 `v04_range_decomposition.py`의 절대경로·관측기 버전 QA 후 확장. **산출:** `P2_RANGE_ERROR_COMPONENTS.csv`, `P2_DETECTOR_TAP_TRANSITIONS.csv`, `P2_CONDITIONAL_BIAS.csv`, `P2_ACF_SITE_AUDIT.json`, `P2_GATE.md`. **PASS:** 같은 관측기 parity, 항등식, tap/조건별 분해 및 종속 표본 구분 재현. 이는 원인 감사 PASS일 뿐 성능 향상 PASS가 아니다.

## P3 — Detector timing 및 조건부 보정 후보 개발 (blind test는 봉인)

**사전 비교 arm:** B(동결 기존), C/C2(P1 상수/affine), D1(30% threshold의 fractional-tap crossing 보간), D2(training LoS template의 bounded delay fit), E1(온라인 관측 가능 feature만 쓰는 규제된 저차 conditional-bias model), D+E(단독 효과 확보 시에만).

1. D1의 fractional tap 타이밍 보간을 우선 평가하고, 이로 인한 firstpath P1/P2/s tap 정의 변경은 별도 intervention으로 다뤄 기존 s 관측기 의미를 보존한다.
2. D2 template은 training-only FFD/CIR로 적합하고 test의 true delay나 clean-H를 이용해 test마다 맞추지 않는다.
3. E1 허용 입력: raw range, noisy CIR peak/quality/전력, mount, 사용 가능한 yaw/pose estimate. **금지:** test true geometric distance, clean LoS oracle, full-vs-LoS difference, ray tracer path labels, 미래 정보.
4. site-disjoint TRAIN로 후보 학습, VALID로 초매개변수와 후보를 선정. TEST를 보며 후보/feature/threshold를 반복 수정하지 않는다. CV fold 내 site 그룹 유지. 복잡한 ML은 단순 후보가 실패한 뒤에만 검토.
5. D와 E를 각각 검증한 뒤에만 합산; 모델/코드/계수/feature/schema SHA 동결.

**TODO:** `p3_detector_candidates.py`, `p3_feature_leakage_tests.py` (미구현). **산출:** `P3_MODEL_CANDIDATES.json`, `P3_VALIDATION_PAIRED.csv`, `P3_FROZEN_MODEL.json`, `P3_DECISION.md`. **게이트:** 독립 VALID에서 LoS RMSE/abs P95와 Full-RF 영향 확인. 유의미한 후보 없으면 기존 B 유지, P4는 baseline·실패 이유 검증용으로만 진행.

## P4 — LoS 및 Full RF의 독립 test 거리 정확도 확증

1. 검증 레벨 분리: (a) 기존 복도 LORO route holdout=exploratory, (b) site-disjoint 신규 XY, (c) **다른 scene/material/anchor geometry**의 독립 holdout=일반화 확증. (c)가 없으면 `GENERALIZATION_NOT_VERIFIED`.
2. P3에 동결한 detector/model만 테스트하며, 같은 raw RF/noise 시퀀스로 B와 paired 평가. test truth는 예측 후 scorer만 읽는다. missed detections를 숨기지 않는다.
3. 사전 제안 게이트: primary **site-weighted Full RF range RMSE가 B보다 ≥10% 감소**, paired site/scene bootstrap 95% CI가 개선을 지지. 이 10%는 **새 실험을 위한 제안값**이며 test 전에 확정; 기존 승인 기준이 아님.
4. secondary: LoS mean/SD/RMSE, Full RF absolute P95, near/far·mount·anchor 조건별 worst case, tap switch, detection rate. LoS-only 개선을 Full RF 개선이라 주장하지 않는다.
5. bootstrap resampling 단위는 독립 물리 site/geometry/scene cluster. 16,432개 pose를 독립 관측으로 bootstrap하지 않음. cluster 수가 적으면 `INCONCLUSIVE` 처리.

**TODO:** `p4_blind_range_eval.py` (미구현). **산출:** `P4_HELDOUT_LOS_PAIRED.csv`, `P4_HELDOUT_FULLRF_PAIRED.csv`, `P4_SITE_BOOTSTRAP_CI.json`, `P4_FAILURE_CASES.csv`, `P4_GATE.md`. **판정:** FULL_PASS / LoS-only improvement / FAIL / INCONCLUSIVE / GENERALIZATION_NOT_VERIFIED. P5는 P4 FULL_PASS 시 확증, 그렇지 않으면 **진단용**으로만 실행.

## P5 — 동일 입력·상태/공분산의 6D EKF paired replay

**필수 선행:** 현재 G7 측정 계보와 별개의 `codex/noisy-probe-ekf-sionna-20261010` Native range-only 6D replay를 **API·receiver·RF packet/pose index·timestamp·F/G/Q/P6·FFD/LUT 버전**에 대해 정합. G7 0-offset baseline replay가 저장된 B-arm과 수치적으로 재현될 때까지 개입 실험 금지. 3-point Native 독립 실험의 갱신 0/3→3/3 및 위치 RMSE 약 0.09 mm→84.30 mm 악화는 별개 실험이므로 G7 LORO와 수치 합산 금지.

| Arm | 센서 및 관측 | 목적 |
|---|---|---|
| A_DR | wheel + IMU, RF OFF | passive baseline |
| B_OLD | 동일 RF, 기존 고정 offset | 현재 범위 baseline |
| C_CONST/C_AFFINE | 동일 RF, P1 training-fold LoS 보정 | 오프셋 재보정의 순수 효과 |
| D_NEW | 동일 raw H에서 P3 frozen detector 재검출 | timing detector 효과 |
| E_CONDITIONAL | 동일 raw RF + P3 frozen online-only conditional model | 조건부 bias 효과 |
| BEST_PLUS_R | P4에서 사전 선택한 후보 + train-derived residual covariance | 평균 정확도와 일관성 함께 분석, **별도** arm |

1. 모든 arm의 물리 궤적, RF packet/H, IMU/wheel, 초기 x0/P0, sensor seed, EKF F/G/Q, baseline R/gating, filter timeline/clock 유지. first trial은 오직 detector/offset만 변경; R/temporal covariance 개입은 BEST_PLUS_R에서만 수행.
2. affine 역변환 시 range/R의 단위·스케일을 보존; forward model에 offset을 넣었다면 measurement에서 다시 제거하지 않는다. range-only도 IMU/wheel prior 유지한다는 뜻이며 pure rank-1 range-only와 구별한다.
3. pre/post `x6,P6`, innovation, NIS, accepted/withheld, raw/corrected range, RF packet index, cross-covariance를 저장. 실제 truth는 EKF 종료 후 scorer에서만 읽는다.
4. 개발 32 independent seed/조건, 확증 최소 128 independent sensor/RF seed/조건을 분리하고 물리 site/scene 단위 CI 보존. 결과를 run-average와 site/scene worst-tail로 제시.
5. position RMSE, heading RMSE, endpoint error, pose 3D NEES/95% coverage, 실제 6-state truth가 있다면 full 6D NEES, innovation ACF, RF rejection 및 uncertainty width를 모두 비교. range가 yaw를 직접 측정하지 않아도 `Pψx, Pψy`를 통해 영향을 줄 수 있다. lever arm이 있으면 `Hψ=0`도 재검토.
6. RF-off 및 B_OLD와 가장 좋은 사전등록 passive baseline에 대한 개선을 각각 보고. Q/R 임의 확대·gate 수용률만 상승·Joseph PSD만 확인을 일관성 성공으로 주장하지 않는다. 기존 V02 LARGE FAIL은 새 독립 검증 전까지 유지.

**TODO:** `p5_g7_matched_ekf_replay.py`, `p5_coverage_audit.py` (미구현). **산출:** `P5_EKF_PAIRED_RUNS.csv`, `P5_POSE_ERRORS.csv`, `P5_INNOVATION_ACF.csv`, `P5_COVERAGE_NEES.json`, `P5_TRACE_SHA256_MANIFEST.csv`, `P5_GATE.md`. **PASS:** 정확도·일관성·site/seed 독립성이 모두 충족. 아니면 B/DR 유지, 개선 불입증으로 보고.

## Gate 흐름

```text
P0 data/hash/observer/split FAIL → 중단·복구
P0 PASS → P1 LORO 확인
P1 no improvement(현재 보고) → 기존 B offset 유지, P2 진행
P1 improvement → coefficient 동결, 그래도 P2로
P2 decomposition/parity FAIL → 원인 수정 후 재실행
P2 PASS → P3 D/E 개발, VALID에서 후보 선택
P3 유효 후보 없음 → P4는 baseline/반증만
P3 후보 동결 → P4 새로운 site/scene에서 blind LoS/Full RF 평가
P4 FULL_PASS → P5 EKF 확증
P4 FAIL/INCONCLUSIVE → P5는 진단용, 성공 주장 금지
P5 paired RMSE+NEES+coverage 통과 → 제한된 범위의 개선만 승인
P5 불통과 → B 또는 DR 유지, scientific_PASS=false
```

## 결과 기록 규격

권장 run-specific 디렉터리: `research/LOS_RANGE_RECAL_20261012/out_p0_p5/<RUN_ID>/`. 필수 공통 파일은 `RUN_MANIFEST.json`, `TRAIN_VAL_TEST_SITE_SPLIT.json`, 단계별 `P{0..5}_GATE.md`, 그리고 각 단계의 위 명시 산출물. 모든 gate에는 `planned_vs_executed`, git source/FFD/receiver SHA, 실행 명령, input/output SHA, split SHA, sample/site count, primary/secondary metrics, uncertainty interval, result(PASS/FAIL/INCONCLUSIVE/NOT_RUN), limitation, 다음 분기를 기재한다. raw 대용량 trace는 무리하게 GitHub에 추가하지 않고 hash·재생성 방법·보존 위치만 기록한다.

**계획 작성/업로드 자체는 알고리즘 개발, 새 RF 생성, 보정 재실행 또는 scientific_PASS가 아니다.** 코드의 새 TODO 파일은 아직 존재하지 않으며 작성 후 실제 실행과 receipt로 단계 상태를 갱신해야 한다.
