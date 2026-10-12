# LoS detector bias recalibration — range-only first audit (2026-10-12)

**Scope:** 12 legacy Method-B RF scenarios, 16,432 observed poses from G7, with RF `range_m` and LoS-only `range_los`. No `s` used. Baseline: G7 fixed `range_offset=-0.5315983906250129 m`.

## Leak-free-by-route protocol (within the available simulation scene)

Leave one *route* (R2, R4, or R5) out. Fit LoS detector bias ONLY on the two other routes using `range_los - true_distance_m`, including the calibration-truth geometry in **training only**. For the held-out route, correct *full-RF measured ranges* using either:
- existing: `r_full - c_existing`;
- LoS constant: `r_full - mean_train(r_los - d_true)`;
- LoS affine: train `r_los=a+b*d_true`, predict `(r_full-a)/b`.

Held-out truth is used for scoring ONLY. No hold-out full-RF multipath terms are fitted or leaked into training. The same simulation corridor is shared across routes; this is **not** independent measured LoS calibration or leave-one-environment-out. Model and comparison were evaluated exploratorily (no pre-registered gate).

## Full-RF range results (RMSE, m)

| Held-out route | Count | Existing offset | LoS constant | LoS affine |
|---|---:|---:|---:|---:|
| R2 | 5,212 | 0.125125 | 0.127471 | 0.126314 |
| R4 | 3,688 | 0.180027 | 0.181373 | 0.181147 |
| R5 | 7,532 | 0.135790 | 0.136658 | 0.136029 |
| **Pooled, by pose** | **16,432** | **0.143847** | **0.145249** | **0.144594** |

Uncalibrated full-RF RMSE: **0.502326 m**. Thus compared to the existing offset, LoS-constant refit is 0.98% worse in RMSE, LoS-affine refit 0.52% worse. Route-wise neither improves the existing offset.

## Calibration coefficients

| Held-out route | Training LoS constant bias, m | Intercept a, m | Slope b |
|---|---:|---:|---:|
| R2 | -0.53705079 | -0.54123887 | 1.00067670 |
| R4 | -0.53677565 | -0.53825303 | 1.00023401 |
| R5 | -0.53404454 | -0.53678735 | 1.00043788 |

All-data descriptive LoS detector bias: -0.53612996 m, LoS detector SD 0.04633 m; fit slope 1.000437745, intercept -0.53886912 m. **Not** used as an evaluation-fit.

## Interpretation

The previous fixed offset already matches the dominant mean LoS detector shift to within a few millimeters. LoS-only recalibration does **not** remove the additional full-RF multipath residual, which is correlated in time and changes with distance. A further retuning to held-out full-RF truth would be an oracle leakage, not a valid detector calibration. Retain the current offset as range-only baseline for now.

**Critical limitation:** This audit evaluates *range measurements only*, not a rerun of the 6-state EKF; no claim of improved/degraded position RMSE, NEES, or coverage under recalibration is made. A true EKF evaluation requires injecting the training-fold coefficients into the frozen G7 B-arm range-only filter and replaying every held-out route, matched against the unchanged B baseline and DR-only A, with 6x6 covariance/innovation records. That runtime uses additional frozen files (source, LUT, motion and per-pose RF observations), so this report is not a substitute for running it.

Reproducible implementation: `loro_bias_audit.py`, run in the branch after the G7 tables are present. It writes `loro_metrics.csv` and `loro_summary.json`.
