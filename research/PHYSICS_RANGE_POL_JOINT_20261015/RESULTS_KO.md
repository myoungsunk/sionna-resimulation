# Range–Polarization Physical Feature Covariance: audited staged experiment (2026-10-15)

**Scope:** Read-only replay of original archived 7 Sionna cases (LoS/Full), 14,502 one-step frames and 16 paired R2 recursive conditions. Original RF H/LUT/core/Q, baseline range/heading data untouched. **scientific_PASS=false**.

## Main scientific conclusions

Existing G0–G5 measured RF physics features (CIR energy/delay, dual-polarization temporal and frequency response, 20/30/40% detector sensitivity) were used to fit a separate *out-of-route conditional squared range residual* predictor. Previous G5 polarization predictors were frozen. The first-range model does not simply reuse the polarization error scale.

- Ranging target: `e_r=z_r-(geometric_range(true_pose)+B_old)`, `B_old=-0.5315983906250129 m`, with truth restricted to train/test labels, never input features.
- Adaptive measurement covariance: `R=diag(Rr,Rs)`, `Rr=clip(E[e_r²|features],0.0068578637,0.68578637) m²`, `Rs=clip(existing E[e_s²|features],0.0081,0.81)`. This is **second-moment inflation**, not centred variance or bias correction; `Rrs=0` remains unverified.
- Leave-one-ROUTE-out R2/R4/R5, same-XY purge and site weights; 19,038 feature rows. Full-channel range `e_r²` R² of G5: R2 +0.120, R4 **−1.440**, R5 +0.148. Raw range 95% nominal coverage R0: 90.5%/86.3%/91.9%; bounded G5: 98.8%/94.8%/98.7%. **Prediction fit is poor in R4 despite nominal coverage**.
- Full range/heading signed error correlation by route: +0.241/−0.069/+0.404, evidence against silently assuming an universally independent joint likelihood.

## Same-prior one-step, Full RF pooled `t>=30` (6,201 frames/channel)

| Arm | Heading RMSE (deg) | Position RMSE (m) |
|---|---:|---:|
| R0 Joint4 | 2.345 | 0.574 |
| Polarization G5 only | 1.581 | 0.364 |
| Range G5 only | 2.321 | 0.567 |
| Both G5 Joint4 | **1.519** | **0.346** |
| Both G5 frozen Range→s sequential | **1.519** | **0.346** |
| Both G5 relinearized Range→s | 1.542 | 0.350 |
| Both G5 relinearized s→Range | 1.527 | 0.345 |
| Both G5 squared exponential multiplier (max 100×) | 1.319 | 0.289 |

Joint vs same-linearization sequential state/covariance parity at approximately 1e−15. Original R0 replay matches the 14 archived one-step traces at 1e−9.

## Recursive RF / L2 +0.20deg/s, 829 frames per condition

| Full RF arm | Mount0 heading RMSE | Mount0 Pose NEES | Mount45 heading RMSE | Mount45 Pose NEES |
|---|---:|---:|---:|---:|
| Original R0 | 7.521° | 297.85 | 0.848° | 86.84 |
| Polarization G5 only | **4.378°** | 2787.35 | 1.361° | 135.05 |
| Range G5 only | 9.464° | 309.73 | **0.687°** | 36.45 |
| Both G0 | 6.989° | 116.40 | 0.718° | 18.45 |
| Both G5 Joint | 4.874° | **6987.25** | 1.212° | 52.16 |
| Both G5 frozen sequential | 4.874° | 6987.25 | 1.212° | 52.16 |
| Both G5 relinearized Range→s | 4.865° | 8143.29 | 1.211° | 52.18 |
| Both G5 shared multiplier | 5.006° | 8046.41 | 1.148° | 42.31 |
| Both G5 power-of-two multiplier | 5.030° | 1830.25 | 1.781° | 30.44 |

Both-G5 Mount0 recursive Heading improves for all B0/L0/L1/L2, but POSE calibration fails. For L2/Mount0, conditional XY NEES contributes ~6964 of total 6987.

## Separate-gate sequential diagnostic

Joint adaptive effective-R Gate in L2/Mount0: heading 4.874°, Pose NEES 6987.25, 828/829 packet acceptance. Using the original-R0 prior Joint Gate with new R update: heading 5.269°, Pose NEES 120.15, 771/829 accepted. Independent scalar gates Range→s: heading 4.888°, Pose NEES 6716.51. **Original Gate is not reliably better**: for B0 and L0 the original-gate counterfactual had Pose NEES ~6044/6124. Gate design needs further science, not case-based selection.

A post-hoc PSD radial XY uncertainty overlay (output-only; NEVER fed back into recursion) improved L2/Mount45 R0 Pose NEES 86.84→16.49, but changed Both-G5 Mount0 6987→6925 only. It is not an approved filter covariance or a solution to model mismatch.

## Audit and execution evidence

Original archived input hashes verified, 120 input file SHA checks, four independent mathematical test families. Audit found and repaired (a) mistaken bundle receipt status, (b) Python `common` module collision, and (c) deprecated array-to-scalar conversion in gate diagnosis. Re-audit followed every fix; (c) repair reproduced earlier D L2 CSV and sample state/cov/gate **exactly**.

Separate post-inference validation checked **301,660** stored SPD posterior matrices, 300 C model-traces, and C score table max absolute discrepancy <1.2e−10. Additional D post-check validated **78,320** SPD matrices, 80 D model-traces, max scoring discrepancy <3e−11. Historical R2 strict 1e−9 parity: **15/16 PASS**; B0/Full/Mount0 differed at state 4.3858e−8, with **zero gate differences**. No tolerance loosening or rewriting historical outputs.

**Interpretation:** Multipath physics features help, but adjusting Rr and Rs alone is insufficient; signed persistent range bias, time-correlated and cross-correlated RF noise, and position–heading cross-covariance warrant separate modelling. The experiment is one corridor with noise-free RF channel and seed0 gyro/wheel noise; not production-valid generalization.

## Artifacts and provenance

- Baseline source: [previous G5 physics Rs work](https://github.com/myoungsunk/sionna-resimulation/blob/b437fd154a9cf38f6b0bfe11a21c59ca63e0b25e/research/PHYSICS_RS_STAGED_20261015/RESULTS_KO.md)
- Archived Full/LoS RF: [GitHub Actions 38331588521](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38331588521/artifacts/11782748118)
- R2 bias benchmark: [GitHub Actions 38664617622](https://github.com/myoungsunk/sionna-resimulation/actions/runs/38664617622/artifacts/11940333419)
- Verified source ZIP `physics_range_pol_joint_source.zip`: SHA256 `0c83deaa6b4a3b3497820ded770138fd5744643726253fcbe0574f6d521d1bc7`
- Verified full-results ZIP `physics_range_pol_joint_full_results.zip`: SHA256 `823fcb4890570a4ad16626dd80a633fe413810651acb91bfa251940871eac1dd`

The last two ZIPs are **conversation delivery files, not GitHub-hosted artifacts**. The ZIP contains the actual audit, test, execution and diagnostic scripts, full x/P traces, held-out OOF risk predictions, trained models and failure logs. This GitHub note publishes the reviewed results; it does not assert that the large analysis ZIP or its scripts were committed to this repository branch.