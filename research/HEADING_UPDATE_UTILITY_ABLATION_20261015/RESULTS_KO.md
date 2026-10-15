# Heading update usefulness: source-audited frozen-RF ablation (2026-10-15)

**TECHNICAL_SMOKE_PASS / scientific_PASS=false.** Separate source ZIP and results ZIP delivered in conversation; not claimed to be hosted in this GitHub branch. Frozen original S4/J4/SR4, native LoS/Full RF, LUT and R0 unchanged.

## Exact decomposition
`e_pre=wrap(psi_pre-psi_GT)`, `a_s=K_psi,s * nu_s`, `a_r=K_psi,r * nu_r` after the original RF joint gate. Whenever no +/-pi wrap boundary is crossed, the squared heading error improvement is exactly `delta_e2=2*e_pre*(a_s+a_r)+(a_s+a_r)^2 = (2*e_pre*a_s+a_s^2)+(2*e_pre*a_r+a_r^2)+2*a_s*a_r`. Ground truth is **offline diagnostic**, not available to deployed estimator.

## Frozen native RF test
- **3-state DR prior**: 7 cases × LoS/Full =14 original one-step traces, 14,502 frames. In R2 Full mount0: DR prior RMSE 0.484°, posterior 1.914°, accepted harmful updates 70.11%. Mount45: 0.484°→3.548°, harmful 79.62%.
- **4-state J4 actual recursive prior**: R2 2 mounts × LoS/Full × B0/L2 =8 recursions, 7,832 frames total, evaluation t>=30s (829 frames per arm). In Full B0 mount0: pre 7.506°→posterior 7.490°, harmful 40.49%; L2 pre 7.538°→7.521°, harmful 39.82%; Full B0 mount45 pre 0.848°→0.845°, harmful 47.46%. This contrast cannot be attributed entirely to gyro bias because DR3 frozen and J4 recursive priors differ.
- In B0 Full mount0, the signed s correction aligned with offline prior heading error on 373 accepted frames, **73.73% harmful**. In the opposite direction on 395 frames, **9.11% harmful**. This explains utility but requires unknown true-heading error sign.
- R5 pre-trained p_MP G5 vs actual J4 harm AUROC: mount0/B0 0.448, mount45/B0 0.556; high p_MP>0.5 had **32.81%** harm vs low p_MP **42.03%** in evaluated accepted frames for mount0/B0. Physical pollution risk is not update harm probability.

## Frozen-Gate Oracle controls (NOT deployable)
Using same original accepted mask, pre-state, gain, and geometry while replacing ONLY multipath difference with matched native LoS:
- DR3 Full mount0 1.914°→0.904° if s multipath removed; DR3 Full mount45 3.548°→0.358°.
- Recursive J4 prior Full B0 mount0 7.490°→7.465° if current s multipath removed; both s+r removed 7.449°. Past cumulative errors do not vanish after one correction.
- Altering oracle readings while recomputing gate would change gate decisions, e.g. Full mount45/B0 removing s MP changes gate on 152/829 evaluation frames. Controls above intentionally keep gates fixed.
- Same-step masking of prior bias cross-covariance does not alter K_psi,s/r because H_r,b=H_s,b=0; gyro bias protection acts through future predictions, not an instantaneous ψ gain row.

## RF-free DR reference counterexample
Estimate prior heading error direction using `e_proxy=wrap(psi_J4_pre-psi_DR4)` (shares odometry/gyro noise, no RF). In B0 Full mount0/mount45, DR4 RMSE=0.484° and update-harm AUROC=0.997/0.905. In L2 true b=+0.20°/s, uncorrected DR4 RMSE=24.969° and harm AUROC collapses to **0.007/0.634**. With **oracle-known true gyro bias** in DR4, RMSE returns to 0.484° and harm AUROC 0.993/0.916 (scientific upper-bound only; true bias unavailable online).

## Audit and limits
- 6 original input archive SHA256/CRC, 120 manifest assets, 14 trace SHAs, 87 source files bytewise matched; 8/8 math and negative tests; code change -> re-audit.
- 22,334 direct harm identities independently recomputed; 7,832 SPD 4-state Joseph covariances verified; gain discrepancy 1.11e-16, Joseph covariance discrepancy 0, joint gate differences 0.
- Historical strict 1e−9 parity of recursive J4: 7/8 PASS; B0 Full mount0 remains max state deviation ~4.013e−8 **FAIL at historical strict threshold**; original gate differences zero.
- One corridor, fixed single RF realization, sensor seed0, B0/L2 only; 3state is DR-prior one-step, 4state full recursion baseline. Ground truth, native LoS, and known-bias reference **never constitute deployable estimator inputs**. Held-route MP proxy does not validate online heading harm calibration.

**Scientific decision:** Do not merge physical MP risk with Heading-update harmfulness into a single quality threshold. Better conditional measurement models and genuinely bias-calibrated independent Heading references warrant new heldout full recursive validation. This is a diagnostic ablation, not a new approved Kalman policy.