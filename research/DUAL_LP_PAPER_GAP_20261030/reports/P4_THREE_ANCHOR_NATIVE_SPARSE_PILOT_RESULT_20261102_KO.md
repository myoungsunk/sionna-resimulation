# DLP-EKF-GAPS-001 / P4 Native three-anchor 4-state EKF — Sparse pilot

**Date:** 2026-11-02 KST. **Status:** P4 Pilot FROZEN, execution PASS, postrun numerical verification PASS. Full P4 remains BLOCKED by 3097 missing Native C RF epochs.

## Evidence and provenance

P3 Sionna Native C run 41395666117 previously passed 39 original preselected pose samples, 13 each on R2, R4, R5, with true Full/NativeLoS complex H, paths.tau and path counts. Native RF ZIP SHA256: f16c91872993f19341a9cb791c4872c9d13567b715596e9ac4dd085d2fe2c5de. Existing original A/B Full/LoS H were physically SHA-verified, not regenerated or substituted.

Proposer P4-PILOT contract SHA256: 34891c60e2c3cff30d1920b97a71c200a3f29ffb1b0fa64aa97b435a5c029744. Config SHA256: ed9e479fc71a2c2cf4e76cb32c16e374875b54a5f97a57f63d3d9ba38c77be0a. Original pre-run independent-formula GitHub Actions [41404548292](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41404548292): 11/11 PASS, zero failure, source/pose/math/negative-controls verified. FROZEN limited to pilot, never full RF.

[Actual P4 3-route GitHub Actions 41405327966](https://github.com/myoungsunk/sionna-resimulation/actions/runs/41405327966): R2/R4/R5 all completed successfully, postrun 5/5 checks passed, 0 numerical failures, 84 result rows, 28 pooled statistics, 48 matched comparisons. Recomputed posterior recursion from own prior, original frozen EKF4 motion F/Q, NIS/Joseph with max covariance mismatch 1.33e-15. Saved 12 full-time state/P/gate/innovation traces in ZIP SHA256 967deb80b763988daee453a0918590446ef01f64a09b4d61e91af4d740bb1acb. This is numerical verification in a second GitHub runner, but the code was authored in the same ChatGPT conversation and **not** independently authenticated human peer review.

## Scope / exact comparison

Each of the R2 979, R4 742 and R5 1415 original timestamps is propagated with exact original P2 B0/L2 seed0 motion controls and common initialization. A new C RF update exists ONLY at the 13 preselected pose timestamps per route. All others are prediction-only, not silently synthesized. Evaluation is t >= 30s, total 2686 scored original time labels for each channel/bias/arm. The same original simulated Corridor scene is reused, not an independent new environment or hardware synchronized multi-anchor measurement.

Seven 4-state arms: DR4 (0 RF), R4_A13 (13 A range/route), J4_A13 (13 A DualLP joint r/s packets, 26 scalar components/route), R4_AB13 (26 AB range packets/route), R4_ABC13 (39 ABC range packets/route), R4_A_EQ12 (12 A packet epochs/route), R4_ABC_EQ4 (4 three-anchor batch epochs/route, 12 range packets/route). Range h=d-0.5315983906250129m, Rr=0.0068578637m²; J4 Rs=0.0081. Correct chi-square 99 percent gates for 1,2,3 dimensions and Joseph update; R diagonal across anchors remains an assumption not calibrated from clock/multipath errors. At each actual 3-anchor epoch the simulated pose/time label is common, but **hardware synchronized acquisition, cross-anchor noise independence and equal energy are NOT verified**.

## Retrospective Heading RMSE, degrees — same single Corridor, t >= 30

| Mode | Bias | DR4 | A13 range | J4_A13 | AB13 range | ABC13 range |
|---|---|---:|---:|---:|---:|---:|
| Native LoS | B0 | **0.498** | 3.858 | 0.830 | 2.896 | 1.705 |
| Native LoS | L2 (+0.20deg/s) | 29.225 | 15.264 | **6.021** | 6.829 | 7.567 |
| Full multipath | B0 | **0.498** | 3.168 | 2.123 | 4.267 | 4.520 |
| Full multipath | L2 (+0.20deg/s) | 29.225 | 13.671 | 16.082 | **7.023** | 7.549 |

Secondary *same 12 total range packet count* (but different cadence and spatial geometry):

| Mode | Bias | A_EQ12 (12 epochs) | ABC_EQ4 (4 three-anchor epochs) |
|---|---|---:|---:|
| Native LoS | B0 | 3.858 | **2.016** |
| Native LoS | L2 | **15.262** | 20.834 |
| Full | B0 | **3.143** | 4.961 |
| Full | L2 | **13.672** | 16.828 |

These are observed comparisons, not predetermined successful targets. Notably Full-B0 DR4 is already 0.498° whereas ABC13 deteriorates to 4.520°. For Full-L2, A13 13.671°, AB13 7.023° and ABC13 7.549°: more anchors are not monotonic improvement. Candidate explanatory mechanisms include range-only indirect heading/bias observability through propagation cross-covariance, heterogeneous geometry and multipath bias under fixed diagonal covariance. This experiment cannot attribute a unique cause or prove covariances independent without subsequent ablation.

Full B0 ABC13 nominal 95 percent pose coverage **20.66 percent**, Full L2 ABC13 **21.41 percent**, with 34/39 and 32/39 accepted update epochs respectively. This is a substantial posterior-overconfidence warning, but single-seed, time-correlated samples should not be used as independent coverage calibration evidence.

## Why Full P4 is NOT completed

The routes have 3136 unique actual original time labels and new C Native Full/LoS physically exists at only 39. **3097 missing Native C updates remain**, and no interpolation, SourceFFD replacement or borrowed A/B packet is used. A direct 257-frequency × 2 mode acquisition requires **1,591,858 additional actual PathSolver calls** for those missing C epochs. The observed P3 per-pose steady-state CPU runtime was roughly 74 sec, so a naive direct acquisition would be on the order of 64 CPU-hours; new resource timing and a separate bounded RT contract are necessary. Existing method-B trace factorization may speed this up only if its C-anchor H/first-tap/path continuity gates pass independently.

Full-P4 3136-observation-epoch trial, independent P5 verification, hardware synchronization, physical cross-anchor R estimation and multi-scene generalization are all NOT_RUN. The present result is P4 PILOT **implementation and execution**, not full RF availability.

## Inspectable files

- [P4 proposer-locked pilot contract](../contracts/DLP-EKF-GAPS-001/P4_20261102/P4_PILOT_PROPOSER_CONTRACT.md)
- [P4 original pre-run 11/11 audit](../audits/P4_20261102/pre_run_41404548292/P4_PRE_RUN_AUDIT.json)
- [P4 FROZEN limited ratification](../contracts/DLP-EKF-GAPS-001/P4_20261102/P4_PILOT_FROZEN_RATIFICATION.json)
- [P4 84 case scores](../runs/P4_NATIVE_SPARSE_PILOT_41405327966/P4_84_CASE_METRICS.csv)
- [P4 28 pooled scores](../runs/P4_NATIVE_SPARSE_PILOT_41405327966/P4_28_POOLED_METRICS.csv)
- [P4 48 case-level comparisons](../runs/P4_NATIVE_SPARSE_PILOT_41405327966/P4_48_PAIRED_CONTRASTS.csv)
- [Original 12 complete state/P/NIS/gate trace ZIP](../runs/P4_NATIVE_SPARSE_PILOT_41405327966/P4_ALL_12_FULL_TIMELINE_7ARM_NATIVE_SPARSE_TRACES.zip)
- [P4 postrun QA and hash-bound manifest](../runs/P4_NATIVE_SPARSE_PILOT_41405327966/P4_POSTRUN_QA.json)
- [Implementation code](../p4_runtime/p4_sparse_ekf.py) and [independent-formula postrun checks](../p4_runtime/p4_postrun_verify.py)

**Final:** P4_PILOT = PASS; P4_FULL = BLOCKED_MISSING_3097_C_NATIVE_RF; P4_GENERALIZATION = NOT_TESTED. All source P1/P2/P3 and main unchanged.
