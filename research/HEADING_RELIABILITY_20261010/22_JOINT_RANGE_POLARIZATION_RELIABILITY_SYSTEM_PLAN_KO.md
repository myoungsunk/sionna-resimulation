# 22 — Range + Dual-LP Heading 공동 신뢰도 기반 Sensor-v2 Active Probe 개발·검증 계획

일자 2026-10-11. 요구 연속 플로우: **매시점 IMU+wheel+신뢰가능 range/s EKF → RF 신뢰도 낮으면 정지 → 동일 위치에서 몸체 yaw 2~3점 RF 측정 → 각 점/위치 오염 가중 공동 posterior/P6 → heading 복귀 → 매시점 주행 EKF 계속**. 최종 성능을 보증하지 않는다. 소스 구현 상태 및 31개 mock tests는 codex/continuous-trigger-ekf-bridge-20261011에 보존.

## 0. 기존 실험의 검증된 우선순위

- 7case×3drift×8seed의 range-only 기존 B: position run RMSE 1.285m, heading RMSE 9.792°, pose NEES1285, coverage15%.
- TRAIN-OTHER-ROUTES distance bias+R variance+AR1 redundancy approximate E: position .804m, heading6.952°, NEES146.5, coverage51.3%. 실제 비교 실행완료지만 covariance consistent 아님. Mean bias를 제거하지 않은 variance/time arm F는 posRMSE1.526m; mean bias calibration이 중요.
- filter fixed receiver-range pulse-offset -0.531598390625m는 LoS detector timing calibration, 실제 hardware antenna delay와 동일 물리량이라 주장 금지; 고정 후 multipath/distance mean +.136m at >=10m remains.
- pole: near anchor horizontal rho<.1m 4/9 stored poses |eLUT|>.1; worst -.8776, absent multipath. 8-bearing original LUT extrapolation at rho=.01m gives max-min s~1.70 and Jacobian up to171/m. Same xy near rho→0 arbitrary azimuth coordinate is ill-conditioned. Interim estimated-geometry guard, true-root branch oracle 금지.
- 128seed single-station RF thermal experiment: range bias at same XY changes -0.041/-0.340/-0.489m by yaw. Relative angle thermal s corr~0 vs spatial multipath site corr~.8, so multi-angle noise model must separate persistent site/channel bias and independent RX thermal.
- One-station predicted heading P at t18.0s .002503 rad², empirical centered .002909 and MSE .005401; systematic mean makes MSE 2.16× model P. New-scene calibration still missing.
- Existing 1344 full-route continuous EKF F3-MIX: heading RMSE2.450°, posRMSE .287m but pose NEES237, only20% pose coverage. Thus site/point nominal mixture improves point estimate in some cases, but does NOT pass consistency. Deep XY conditional Schur NEES dominates.

## 1. Unified measurement model (two distinct quality targets)

Use original 6state x=[x,y,psi,b_g,sf_g,eps_wheel] for original filter; investigate augmented persistent site bias with 7/8state or Schmidt/consider covariance without blindly mixing these models.

range: z_r,k = d(p_k) + b_hw + mu_r(f_r,k) + b_r,site(k) + n_r,k.
LP:    z_s,k = h_FFD_LUT(p_k,psi_k,mount) + mu_s(f_s,k) + b_s,site(k,psi) + n_s,k.
Where f_r includes corrected range, Psum, first-path detection tap/energy, signal quality, relative yaw, recent innovation; f_s includes s_FP, |s_FP|, common first-arrival s_window (only if HW exports amplitude CIR), Jacobian/slope/position prior and 2/3-yaw consistency.

Q_r = CALIBRATED P(abs(true range model error) <= threshold e.g .15m | features).
Q_s = CALIBRATED P(abs(RF prior-selected heading error) <= 5deg | features).
Q_site, Q_point_i: spatial/common multipath s mismatch labels for 2/3-yaw site and each angle. Never equate one probability target with another, never treat signed s, |s| and 10log(P1/P2) as three independent polarization channels.
Separate risk calibration and no-match/no-branch coverage; avoid true x/psi in inference.

## 2. Bias layers and observability

- b_hw (equipment/antenna/receiver delay): calibrate with multiple known distances, yaw/power conditions; fix per device/site source version, propagate residual calibration covariance. In current simulator use known LoS detector -0.5316m as separate fixed component.
- mu_r(f): data-trained distance/power conditional bias using train routes only, record reliable extrapolation regime. Pair with conditional residual variance and predictive uncertainty. Initial benchmark E is an AR1-inflated approximate scalar R, NOT an exact temporal likelihood. Independent new geometry required.
- b_r,site(t): colored or slowly-varying latent bias, reset/change by signal context/movement; constrained nonnegative excess range only when justified by channel detector convention; general signed bias may occur because hardware offset/leading-edge effects. A single anchor and unknown b_r make radial pose and bias jointly weakly identifiable. Prevent ungrounded simultaneous pose/bias Kalman updates without independent calibration/motion prior or known-position constraints.
- polar b_s,site or latent cluster: affects all yaw observations; rotating apparent linear polarization can be indistinguishable from true heading. Maintain covariance floor/no-harm fallback rather than force an absolute angle; a low raw LUT residual is not proof of cleanliness.

## 3. Stable pole handling before joint heading

- Original frozen LUT near (theta=0, rho<=.1m) is not numerically continuous in approach bearing and can yield huge spurious x/y gradients. Implement temporary online guard based ONLY on estimated horizontal rho plus confidence bound on rho, not true pose.
- Independently inspect original Cartesian FFD Jones fields for theta→0, ensure phi basis rotation is physically gauge invariant, refit/replace near-pole h and analytic Jacobian. Any modified LUT gets a NEW version and SHA. Verify 0/45 mount, all 7 original cases and 5 native counterparts before endpoint inference.
- Holdout evaluation: LoS-only s with and without near-pole update and pole-safe Cartesian correction. Compare actual retained gyro-wheel accuracy/NEES, not just s residual.

## 4. Correct joint covariance (do not double count)

Per sensor time use full covariance P6 and H_r/H_s. Same-time joint S = H P6 H^T + R_rs + valid state–measurement cross terms. R_rs must include empirically calibrated range/s receiver covariance, excluding correlation already modeled by persistent nuisance b_r/b_s states.
For 2/3yaw pose changes, if using post-turn single batch, require P(t_i,t_j), pose-to-RF noise C_ij, RF site covariance B_ij, and independent receiver noise; either:
- fixed-lag smoother relinearizing full 6state states and group bias factors with sensor process between measurement times (preferred for consistent temporal modeling), or
- conservative Schmidt Kalman nuisance-state approximation with audited covariance; covariance inflation must be predeclared and checked, not adjusted on heldout NEES.

Key attention: RF multi-yaw s errors are strongly correlated across 169 stored sites, but 128 independent receiver-noise realisations at a fixed site have near-zero thermal cross-angle correlation. Both facts can be true. Do not use one as substitute for the other.

## 5. Causal control & instrument feasibility

Every 0.2s normal drive sample:
1. EKF predict+wheel/gyro; range trust q_r and s trust q_s BEFORE any s assimilation.
2. If enough independent range information, apply bias-corrected calibrated range with correct joint/colored covariance. Good s applies regular reliable single-s update; low s withheld.
3. Trigger stationary probe only if expected additional heading information exceeds time/uncertainty cost and q_s low with usable LUT slope. Stop with physical brake time; actual post-brake x_stop,y_stop is the site, new reference RF measurement is collected there.
4. Rotate body yaw (or verified independent head) to 1 or 2 additional angles: total M=2 or3. Noise/gyro slip, range/s uncertainty, actual timestamps and motion time all recorded. Record firstpath P1/P2 and common early-gate LP ratio (single-tap h LUT only, gate ratio quality covariate unless separate clean gate LUT).
5. Joint posterior (q_site, q_point_i, pose6/P6) with all points retained, no smallest-residual point selection; if all bad/underobserved, expand uncertainty/abstain and resume without forced correction.
6. Actual heading return→continuous same EKF with corrected full covariance. No oracle true yaw, no double-s application; guarantee false-low time and battery cost bounded.

## 6. Prioritized executable experiments and gates

P0 (DONE): original 7case 1008-run range-only train-other-route correction + actual 9519 LOS/LUT/polar and 128-seed single-station cross-time covariance diagnostics.
P1: lengthen empirical cross-time Monte Carlo to multiple station/mount/anchor and 12case source-consistent H. Use original H, sensor-v2 noise generator and calibrated thermal model before requesting fresh Sionna.
P2: train-only bias-nuisance and cross-time models; run matched B/B_bias/B_var/AR1proxy/B_bias_state with same RF H / seed, heldout routes and recalculated NIS whiteness, NEES/95coverage. Seek improvement over current B NEES1285 and E NEES146, not arbitrary large R to create flat covariance.
P3: FFD near-pole h and Jacobian parity, pole guard and LoS-only full-route EKF recalculation, verify radial false certainty and early 0/45 points.
P4: source-consistent 12case full/LoS paired H including mount0/45, accurate first-arrival gate (choose exactly 4/8/16 versus 5/9/17 taps and freeze), full dynamic physics noisy 2/3yaw controller, range-s joint covariance and nuisance posterior.
P5: full-route baseline controls A/B/C/D, E, SHAM, F2/F3 under SAME physical route checkpoint/time budgets; compare good5/route RMSE, pose NEES df3, heading confidence coverage, Brier/ECE, outage/false accept, real timing and energy. Preserve experimental clock/seed and event matching. 3 route all same geometry; do not infer true transfer.
P6: independent novel corridor geometries and actual robot radio receive availability. Production acceptance requires consistent error distribution, stable calibrated probability, meaningful risk-coverage, no harmful RF-only points, real-sensor time/cost under constrained user scenario.

Do not claim scientific_PASS while F01/F02 OPEN and new range bias/cross-time model is not statistically calibrated. Use explicit NOT_RUN for unexecuted states, and do not describe any document as completed native physical Monte Carlo merely because integration/mock source passes.
