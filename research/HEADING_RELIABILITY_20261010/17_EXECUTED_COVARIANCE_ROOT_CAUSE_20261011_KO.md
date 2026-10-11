# 17 — 기존 RF bank 연속 Sensor-v2 EKF: Site/Point 신뢰도 3점 보정 및 일관성 실패 원인 정량 분석

작성 2026-10-11. **기존 RF와 Sensor-v2를 실제 재실행, 1,344개 full-route filter run 완결, 실패 0.** 독립 동일 코드 2-seed 재생 336개의 모든 RMSE, NEES, coverage, trigger, elapsed time이 8-seed 결과의 첫 2seed와 완전 일치. RF 채널을 신규 생성하지 않음.

실행 근거:
- Main GitHub Actions: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38104333922
- Independent two-seed check: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38105076940
- 실행 소스: research/HEADING_RELIABILITY_20261010/run_covariance_consistency_ablation_v2.py
- 원래 지속 주행 실험: https://github.com/myoungsunk/sionna-resimulation/actions/runs/38054331364
- 최신 별도 12case fixed-truth noisy-rotation 결과: codex/probe-mixture-reliability-20261010 / results/DRIVE_SIM_NOISY_PROBE_20261010/RUN_01a125b3
- 첫 LoS FFD LUT SHA256=711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079.
- 모든 케이스는 단일 corridor. 7 H existing cases만 사용: R2A m0/m45, R2B m0, R4A/B m0, R5A/B m0. 8seed ×3drift ×7case ×8arm=1344. 기존 T10 bank station에서만 발동, sample-boundary ideal stop, noise-free original RF H, v2 noisy gyro/wheel generation. 새로운 native 5 H/실물 body slip dynamics를 수행했다고 주장하지 않음.

## 1. 전체 주행 결과

아래는 **각 run에서 original Tnone route-progress t>=30s의 RMSE/NEES를 계산한 후 run들을 동일 비중으로 평균**한 숫자다. 기존 baseline의 경우 8-seed로 새로 재실행하여 비교 조건을 맞췄다.

| Arm | Heading RMSE deg | Position RMSE m | Pose NEES df3 | 95% pose coverage | Mean probes/run |
|---|---:|---:|---:|---:|---:|
| A_ODOM IMU/wheel only | 8.9347 | 1.0074 | 8.87 | 83.4% | 0 |
| B_RANGE +single anchor range | 9.7922 | 1.2854 | **1285.37** | 15.0% | 0 |
| D_DEFAULT +full RF every tick | 2.8730 | .3396 | 170.69 | 13.4% | 0 |
| E_PASSIVE q-gated s update | 2.9091 | .3609 | 156.41 | 19.5% | 0 |
| F2_PAIRED 2point Gaussian | 2.8203 | .3494 | 161.85 | 19.8% | 2.14 |
| F3_ACTIVE 3point Gaussian | 2.7872 | .3436 | 180.36 | 19.3% | 2.14 |
| **F3_MIX 3point site+point latent** | **2.4495** | **.2875** | **237.01** | **20.0%** | 2.14 |
| SHAM_F3 same turns without probe s | 2.8383 | .3517 | 207.15 | 19.4% | 2.14 |

**판정:** 16-hypothesis soft-mixture improved point-estimate error but failed covariance consistency. F3_MIX versus E: heading RMSE −.4596deg; position RMSE −.0734m; pose NEES +80.60. Cases are correlated and all from one environment; case-cluster 10k bootstrap for heading delta 95% CI [−1.061,+.007] includes zero, NEES delta 95% CI [−33.66,+274.94] includes zero. F3_MIX not a general no-harm validated method. In R2A mount0 the mean NEES worsened by +640.6 despite heading RMSE −1.938deg; in R5A mount0 heading improved −1.242deg and NEES improved −81.1. Cases differ strongly.

## 2. Root cause #1: range-driven radial covariance collapse

At every sensor tick the filter treats range as independent scalar observation at the current predicted pose. The process covariance only comes from gyro/wheel measurement noise, with no separately calibrated map-dependent position-bias state.

Representative drift0/seed0 trace of all cases, excluding original drive progress <30s:
- A_ODOM minimum conditional XY eigen-axis std median .102m.
- B_RANGE minimum conditional XY eigen-axis std median .00914m.
- F3_MIX minimum conditional XY eigen-axis std median .00902m.
- These narrow axes predominantly align with the anchor radial direction; in most samples |cos(angle)|>.9.
- In R2-A mount45 at a representative step, radial-aligned predicted std=.00766m but projected true XY error=.896m (117 standard deviations). Range-only B_RANGE mean pose NEES1285 is much worse than A_ODOM mean8.87.

This is **not simply inaccurate heading uncertainty from yaw probing**. Repeated range measurements tighten radial XY covariance unrealistically while persistent range bias and weak geometry observability can leave large physical position errors. Correct mean, colored range residual and drift-related cross-correlation must be treated before over-optimizing s R.

## 3. Root cause #2: incorrect s noise scale and colored mean

Frozen FilterConfig prior s_mismatch_sigma=.09, so R_s=.0081 in original noiseless RF replay. 7case 9519 matched full-v-LoS H s errors e_MP have:
- link <5m n4253, RMS .0406, mean bias +.0025
- link 5–10m n3605, RMS .1559, mean +.0359; squared RMS is 3.00× fixed R_s
- link ≥10m n1661, RMS .3300, mean +.0510; squared RMS **13.44×** fixed R_s
Full-v-LoS range bias simultaneously rises from +.005m (<5m) to +.1409m (≥10m). These are oracle matched channel-model mismatch, not measured EKF innovation covariance and not proof of pure physical depolarization. One distance-independent mean-zero Gaussian R is empirically mis-specified.

At representative successive drive-station coordinates, e_MP lag1 is high in several cases (.64–.92), so a filter that assumes every 0.2s update provides an independent new error can double-count systematic geometry-dependent information. The original scalar innovation chi² gate cannot detect a slowly persistent bias merely because it stays within R/P predicted residual width. Source F01/F02 LUT mismatch gates remain OPEN.

## 4. Root cause #3: same-site multi-yaw s residuals are strongly correlated

Across 169 case-station 3point groups from 74 physical route XY locations (all same corridor):
- corr(e_0,e_10deg)=.818, corr(e_10deg,e_20deg)=.818, corr(e_0,e_20deg)=.560.
- For a simple unweighted 3point residual average, empirical variance is about 2.47 times a diagonal-only same marginal covariance assumption; equivalent independent-count approx1.21 **only for this simple average**, NOT full EKF heading information with different Jacobians.
- Previous F3 already included heuristic site shared covariance (.12)^2 11T and (8deg)^2 HpsiHpsiT. It was *not* totally iid. But those numbers were not calibrated to actual channel error and inter-time pose/measurement correlation was absent.
- In its 360 actual 3point events, the absolute estimated heading correction median was only .0636deg and the batch innovation NIS median .377; 0/360 events triggered its automatic R inflation. This gate did not identify true biased pose states.

## 5. Root cause #4: site/point mixture probabilities are not calibrated

The new F3_MIX uses all 3 s points under 2×2^3=16 nominal Gaussian latent clean/dirty site and point hypotheses, Joseph P6 update in each and moment-matched full 6x6 posterior. Cross-time measurement↔pose covariance is still approximated.

Evaluate nominal q_site/q_i *after inference*, using clean matched full-minus-LoS RF oracle residual |e_MP|>.1 as evaluation label only. Actual 360 repeated gyro/seed events come from **only 15 distinct case-specific station groups (14 route stations)**:
- 10/15 distinct case-stations had some point whose absolute s mismatch exceeded .1.
- At threshold q_site≥.5, 5 of those 10 bad sites were identified but **5 were not**. Three bad sites were even scored q_site<.2 (false confidence).
- Mean nominal site risk across repeated runs .425, actual site corruption fraction .667; calibration is poor.
- Descriptive case-station AUROC≈.82 and Brier≈.224, but tiny sample / same scene: *not statistically established generalization*.
- Actual point0/1/2 bad fractions .467/.467/.533 while mean modeled qbad .340/.206/.223 — later points too trusted.
- One false-clean example is R2-A mount0 at trigger station g350: max actual |e_MP|=.171, q_site~.106.
- Mixture improves some heading corrections while reducing XY covariance through H_(x,y,yaw); the model underestimates persistent position bias, so pose NEES worsens.

The **representative P6 Schur decomposition** (exact block inverse; drift0/seed0 stored samples) for F3_MIX has mean heading contribution6.66 and conditional XY contribution404.20, sum pose NEES410.87. **~98% conditional XY**. This is not 1344-run average but provides a direct covariance diagnosis.

## 6. Independent uploaded 12case noisy-data cross-check

The newest 12case noisy rotation report contains 53,280 *station endpoint* rows, 5 sensor seeds, SNR10/30, old prior vs newly waited/aligned prior. Its SNR30 LEGACY_SAVED_POST_ODOM prior:
A RF-off NEES mean3.21 median1.85, B range-only mean13.67 median10.49, C full range+LoS-only s mean955.5 **median8.24 and seed-unit maximum52886**, D full range+full s mean1004 median16.14 and max54703.
These results independently reproduce range-induced consistency degradation and very heavy NEES tails, but are **not the same full-route EKF experiment**. Extreme prior dependence: NEW_RF_OFF_WAIT_AND_YAW_ALIGNMENT C mean NEES~12.98. G1/G2 in that run suppress both range and s measurement count, invalidating an s-only information ablation. Native new full5 vs legacy MethodB7 parity is unapproved.

## 7. Scientific next action (do not tune NEES down by scalar R inflation alone)

1. Freeze and compare matched RF-off, range-only, full RF, high-confidence gated RF, three-point Gaussian, site/point mixture with SAME station/seed/mount/clock. Current 1344-run executed.
2. Estimation overhaul: conditional range mean bias and colored serial noise / range-s covariance, RF s model mismatch and LUT H accuracy, persistent site nuisance/bias state or fixed-lag smoother. Re-estimate cross-time pose–measurement P, not only same-time 3×3 Σ_probe, and verify NIS residual whiteness before consistent updates.
3. For 2–3point joint batch, calibrate q_site/q_point and shared covariance in held-out physical sites and entirely new geometry; use risk-calibration diagrams, Brier/ECE, high-confidence false accepts and don't mistake ability to classify |e_MP|>.1 for safe EKF update.
4. Correct G1/G2: preserve all three range packets across arms, vary only 1/2/3 s points and compare FFD-matched LoS/full RF. Fix first-cluster gate discrepancy prior4/8/16 taps vs latest station harness5/9/17 taps, and independently verify hardware availability.
5. Then 12case symmetric mount0/45 native exact-physical-pose Sionna / actual body acceleration, noisy slip and full route on same clock; until then generalization and production scientific_PASS=false, F01/F02 OPEN, L1 FAIL.

### Completion / provenance

Current outputs are in GitHub Actions artifacts and matching 8seed/2seed replay receipts. Original uploaded data branch codex/probe-mixture-reliability-20261010 was not modified. This report is a controlled exploratory consistency diagnosis, not a production filter performance claim.
