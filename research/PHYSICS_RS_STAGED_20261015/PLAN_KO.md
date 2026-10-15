# 물리 피처 기반 R_s: 감사 후 단계별 검증 (2026-10-15)

## 범위
기존 LoS/Full RF 7 case, 9519 paired case-pose, TX0/RX2 원 복소 H를 재사용한다. 새 RF 생성, 기존 LUT/Q/R/gate/core 변경 없음. 별도 연구 디렉터리만 추가한다. 같은 시점의 두 채널과 같은 위치의 모든 yaw/mount/seed는 동일한 평가 fold에 속한다.

## 감사 정책
원본 P0 SHA256와 Git blob 비교 → 실행/진단 소스 정적 검토 → 독립 수학 대조 및 negative tests → 코드/입력 해시 GO → 실행 → 독립 저장 결과 검산. 결함 시 원인/수정/재감사를 기록하고 원 실패를 보존한다. 사후 허용기준 완화로 PASS하지 않는다. 과거 원본의 구현 정합과 물리적 정확성은 구분한다.

## A: 물리 피처
G0: measured range, log FP total power, |s_FP|. G1: G0 + early 4/8/16-tap concentration, pooled delay spread, two-port peak-time difference. G2: G0 + FP/total log power-ratio discrepancy, 4/8/16-tap s contrasts, weighted tap s variance. G3: G0 + frequency Jones eigenvalue ratio and power-weighted frequency s variance. G4: G0 + detector threshold 20/30/40% sensitivity. G5: union.
원 FP observer는 257-bin Hann, 4N IFFT, stronger-RX 30% leading edge, shared tap. 원 r,s를 변경하지 않는다. 유효 delay window는 FP에서 80 taps, 초기창 4/8/16 taps; 지표 이름에 명시한다. Noisy data와 noise-free 데이터를 혼동하지 않는다. power sums below machine-relative floor/missing windows are explicit flags, not clean zeros. Jones eigenvalues are second-moment spectral diversity, NOT guaranteed physical depolarization or yaw invariance.
검사: ideal rank-one separable response, unitary basis rotation, common-gain scaling, port swap, null/invalid packets, coherent equal-delay multipath blind spot, independent scalar/vectorized implementations, source FP observation parity. Actual LoS yaw spans and Full-v-LoS matched contrasts are descriptive, not proof of universality.

## B: 예측/분산 검증
학습 target은 원 scalar s 관측의 e_total=s_channel-h_LUT(true_pose), 물리 label e_MP=s_full-s_los 및 e_LUT=s_los-h_LUT는 별도 평가한다. true pose/channel oracle는 predictor 금지. Full/LoS 함께 학습하되 channel label을 feature로 쓰지 않는다. R2/R4/R5 leave-one-route-out, 다른 route의 coincident XY distance<=1e-4m는 학습에서 제거한다. 동일 XY의 yaw/anchor/mount/channel 반복에 site-balancing weight를 적용한다. seed/time 행을 독립 RF 표본으로 세지 않는다.
고정 모델: RandomForestRegressor 160 trees, max_depth=6, min_samples_leaf=40, random_state=20261015, n_jobs=2; train target e_total^2, sample-weight by physical site. No heldout tuning. Constant train mean-square baseline and G0..G5 all report. R_pred is conditional second moment under zero mean, not unbiased variance. e^2 R2, Gaussian zero-mean NLL, E[e^2/R], 95% error coverage, per-route/channel summaries; feature correlations are not covariance calibration proof.
C용 실험 R_eff=clip(max(R0_s,R_pred),R0_s,100*R0_s), R0_s=.0081. No R decrease, no mean correction, no Rr change. This is a preregistered bounded inflation experiment, not a tuned solution.

## C: EKF 대조
B의 heldout model만 사용. C1: 14 frozen one-step traces, same archived prior/mask; J4 unchanged vs each G0..G5 changed Rs, retain original common gate for causal R-effect isolation. C2: R2 A mount0/45, B0/L0/L1/L2, seed0, recursive J4 baseline vs all feature groups, own predictive NIS with unchanged numerical 99% threshold. R2 heldout model trained exclusively other routes and noncoincident sites. No bias freeze in this experiment. Baseline in same environment uses original Gaussian routine. Archived parity is reported separately without loosening old thresholds; any disagreement diagnosed.
报告 heading/position/bias RMSE, NEES, 95% coverage, gate count, Rs distribution. No selecting best test arm as validated production model. Failure snapshots preserved. If A source/observation validity fails, dependent B/C do not run. Poor predictive performance is a scientific result, not grounds for hiding cases. B calibration not PASS means C exploratory only, scientific_PASS=false.

## 既存設計の修正対象
1. exact zero LoS or complete yaw cancellation was an idealization; calibrate empirical baseline.
2. first-tap fraction is not LoS fraction/K-factor; use explicitly bounded windows.
3. e_total^2 models MSE, not centered variance; avoid double counting LoS mismatch.
4. matching feature variance R_s alone cannot correct colored errors or range-driven position covariance collapse.
5. raw source and estimator state must not enter feature regression as oracle inputs.
