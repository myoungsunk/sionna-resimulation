# P5 gate — matched 6D EKF replay (range-only), confirmatory seeds 5100–5227

Planned vs executed
- Planned (plan §P5): arms A_DR, B_OLD, C_CONST/C_AFFINE, D_NEW, E_CONDITIONAL, BEST_PLUS_R; dev 32 seeds, confirmatory ≥128 seeds; position/heading RMSE, endpoint error, pose NEES/coverage, innovation ACF, rejection.
- Executed: all of the above, 12 conditions x 3 drift levels x 128 seeds x 8 arms = **36,864 runs, 0 failures, 0 duplicates**. Added arm BEST_PLUS_R_IAT (R inflated by the V05 conditional IAT constant 5.8; listed as a mild information leak). Not executed: full 6-state NEES (no per-run true calibration vector saved), `s`-using arms, LARGE prior, a 2nd scene.
- Criteria were frozen before the confirmatory run (`../P5_CONFIRM_CRITERIA_FROZEN.md`); the development run (seeds 5000–5031) had been inspected.
- Not matched to the plan: P5 'pre-condition' (API/receiver match to the codex noisy-probe-ekf branch) was NOT done; this replay uses the frozen G7/sensor-v2 harness (same lineage as G7), so no claim is made about the Native range-only 3-point experiment.
- Source/inputs: harness = RUN_01a124ff `simulate.py` via text substitution (`p5_build_harness.py`); per-pose range deltas from LORO fold coefficients (`p5_arm_ranges.py`); manifest of chunk/arm SHA256: `P5_TRACE_SHA256_MANIFEST.csv` (per-run traces were not stored; reproduce with the code).

Results (mean over runs; CI = bootstrap over the 12 conditions, LIMITED: one scene, 3 routes)
| arm | pos RMSE [m] | heading RMSE [deg] | mean pose NEES (median) | pose95 coverage |
|---|---:|---:|---:|---:|
| A_DR (IMU+wheel only) | 1.066 | 9.57 | 62.9 (8.3) | 64.2 % |
| B_OLD (fixed offset) | 1.406 | 12.43 | 2221 (532) | 11.9 % |
| C_CONST | 1.476 | 13.02 | 2435 (637) | 9.1 % |
| C_AFFINE | 1.461 | 12.86 | 2340 (605) | 8.7 % |
| D_NEW (fractional crossing) | 1.395 | 12.42 | 2406 (689) | 13.8 % |
| E_COND (frozen P3 model) | 0.654 | 5.92 | 331 (37.9) | 25.9 % |
| BEST_PLUS_R | 0.732 | 6.82 | 297 (23.3) | 34.5 % |
| BEST_PLUS_R_IAT | **0.618** | **5.58** | **65.7 (8.1)** | **62.6 %** |

Pre-frozen questions
- Q1 E_COND vs B_OLD: position −53.4 % [−59.8, −47.3], heading −52.3 % [−58.6, −44.1] -> **PASS (accuracy)**.
- Q2 BEST_PLUS_R_IAT vs B_OLD: position −56.0 % [−62.4, −47.4], heading −55.1 % [−62.4, −44.0] -> **PASS (accuracy)**.
- Q3 vs A_DR: BEST_PLUS_R_IAT position −42.0 % [−49.4, −33.5]; E_COND −38.6 % [−49.9, −25.0] -> **PASS** (range is worth using only with the corrected model).
- Negative findings: B_OLD is **worse than no RF at all** (position +31.8 % [11.2, 50.9] vs A_DR); C_CONST/C_AFFINE do not improve B_OLD (+5.0 % / +3.9 %); D_NEW no effect (−0.7 %, CI crosses 0).
- Consistency: BEST_PLUS_R_IAT is statistically indistinguishable from A_DR (NEES ratio +4.5 % [−38.9, +51.1]; coverage −1.6 pp [−7.6, +4.7]) -> 'not worse than A'. **No arm is statistically consistent** in the absolute sense (mean pose NEES is far above the 3-DoF reference and A_DR itself is far outside it). Innovation lag-1 autocorrelation stays 0.57–0.75, i.e. range residuals remain strongly serially correlated in every arm.

Verdict: **P5 = ACCURACY_PASS_DIAGNOSTIC, CONSISTENCY_NOT_ESTABLISHED.** P4 was within-scene only (GENERALIZATION_NOT_VERIFIED) so P5 is diagnostic and cannot lift `scientific_PASS` (stays false; V02 LARGE FAIL untouched).
Limitations: pose-SMALL prior engineering setting; calibration prior as configured; IAT constant leak into BEST_PLUS_R_IAT; harness lineage differs from the Native range-only experiment; a single corridor scene.
Next branch: (1) obtain a second scene/anchor geometry for P4(c); (2) fold-wise IAT for BEST_PLUS_R_IAT; (3) add the `s` update on top of the corrected range (Stage B V06) before any Stage C use; (4) investigate why even the corrected arms keep NEES >> 3 (A_DR itself fails: sensor-v2 prior vs generator).
