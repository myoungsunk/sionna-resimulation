# P0–P3 실제 G2/G3 물리적 3-state 융합 — 사전 감사 (2026-10-14)

## 사용자 목적
단일 반례를 전체 진행 중단 사유로 사용하지 않고 DR-only 대비 G2/G3의 전체 Position/Heading 및 불확실성 성능을 비교한다. 실험이 계산적으로 유효하면 나쁜 성능도 데이터로 포함한다. 실제 결과를 무효화하는 input/SHA/truth-leak/double-counting/numerical precision은 엄격히 해당 종속셀을 차단한다.

## 원본/재사용
- Frozen H3 32ee990b0d9dfc3bf3010e5ccabf404fa9d3aa20
- H3 Stage4 original R0 data, original G2X gate and MAP, archived D0 parity.
- B2 Office TX0 observed mixture model was fitted on *static other scene* and not verified to share exact H3 s/Range RF characteristics. Therefore initial **R0 LoS/Full/B_OLD/E1** can be evaluated without falsely asserting B2 transfer. Candidate B2 original H3 insertion awaits source compatibility or an explicit exploratory branch.
- Prior R0 tilted GH/RQMC original Heading posterior one-cell PASS from run 38531405523. Its G3 Heading accuracy 52.58° vs G2X 24.56° in run 38532581455; **numeric precision does not guarantee accuracy**. This negative result is deliberately retained.
- User proposed audit policy commit 9beb061f354edef18e1f977f5d462d7e0d8b1f2e.

## New target and validation
P0: P0 frozen blob SHA, input truth timeline, D0 pose parity, G0 heading archived parity; uses original h3_cloud_stage1.frozen_snapshot without altering source.
P1: use exact original R0 Rs=.0081 and RR=.0068578637, Range G2X EKF gate parity, G0 MAP parity; independently verify bivariate Gaussian joint vs sequential conditional likelihood with nonzero R_sr and no double counting.
P2: physical H3 LoS/B_OLD at R2_aA_m0/gyro L2/seed0/t195.6s. Joint S+Range nonlinear G3 from original LUT, original DR joint 3x3 prior and **no Range gate**. Numerical integration uses range-only tilted proposal with exact prior/proposal density corrections: GH25/41 and scrambled Sobol8192 two seeds on the same 1440 Heading grid. Output FULL 3state posterior mean/cov and XY-Heading cross covariance via conditional moments (not only Heading MAP). Compare posterior TV<=0.001, MAP<=.1°, evidence rel<=.005 and exploratory state mean diff<=.05m/cov max entry diff<=.15. Last two are engineering repeatability gates, not previous scientific contract.
P3: exact original data, five pre-registered physical snapshots: LoS normal, Full E1 low bias, LoS high bias, Full E1 high bias, R4 Full E1 low bias. For each, G2X (EKF gated Range once then integrate S only) and G3 (joint Range+S without gate) posterior moments. Compare fixed GH17/25/41 with 720 fixed angle bins; report TV/MAP/moments, all errors and numerical invalid rows. No omission of bad performance.

## Independent physics/inference sanity
- State (x,y,psi), radians for ψ, Anchor z=2.65m and robot z=.45m. XY-psi cross covariance always retained in prior and posterior.
- G3 exact target p(x,y,ψ)*L_s*L_r, R0 cross R_sr=0. G2X uses old NIS gate and only S conditional likelihood once afterward. Gate vs joint observation policy confounded with numerical approximation; do not ascribe performance to Bayes ordering.
- Proposal tilted with Range is proposal only; weights include p_original/q, all observations counted once, normalisation evidence across independent algorithms.
- Joint Heading on circle: circular mean except near-zero resultant then MAP as reference; Pψ and Pxyψ from weighted shortest wrapped δψ. Original covariance may be multimodal: single Gaussian moments are descriptive and must not replace the full stored Heading posterior without an approximation audit.
- Scoring truth appears only after likelihood integration and proposal; no oracle truth used in estimator.
- c.check_inputs(full_p0=false) verifies original frozen source hashes/P3 model SHA and RF H in original c.rf_case; no original file modifications.
- Numeric invalid G3 case output must stay CASE_RESULT_INVALID for that CASE ONLY. G2 valid cells and R0 P0 remain valid.
- Prior Stage D Heading TV PASS does not automatically certify full 3state moment accuracy; this is a new independent consistency check.
- Sparse checkout explicitly contains original P0/observer/sensor v2 RF binaries for R2/R4/R5 (needed for chosen cases), LUT, original frozen G0/G2X archived cases.

## Severity and execution
HARD_EXECUTION_BLOCK: source/input SHA mismatch, data-time misalignment, ground truth in likelihood, Range double-counting, invalid input covariance, incompatible actual RF model. BLOCK only dependent stage.
CASE_RESULT_INVALID: GH/QMC disagreement, nonfinite or PSD failure, only affected G3 snapshot.
CLAIM_BLOCK: external B2 probability calibration, synthetic fault prior, R0 G3 full-route superiority, independent scene statistical generalization.
DIAGNOSTIC_DEFECT: optional CSV/JSON representation; re-audit restricted artifact, do not re-run frozen simulator blindly.
Result quality is *not* a safety gate: individual 52.58° Heading error is scientific performance observation and stays in comparative results.
Reusing previous P0/G0 source validation where bytes unchanged: REUSED_VERIFIED after local Git blob checks.

Approval must pin exact source blobs; every stage is gated by strict stdlib SOURCE hash before execution. PRE_RUN audit JSON includes run source/sha and claim blocks. GitHub Actions archives all outputs including invalid cells. No new numerical tolerance relaxation after results.

## Expected conclusions
P0 and P1 should pass if source bundle complete. P2 original L2 GH/QMC Heading posterior expected to converge but full 3state covariance may not; actual result determines certification of that one cell. P3 execution proceeds with fail-closed per cell, records numerical rates and performance deterioration, *does not claim full One-step exhaustive or recursive*.
All later P4/P5/P6 require separate stage implementation + reviewed source. No scientific PASS until physical full actual one-step and recursive route coverage and independent model claims are measured.
