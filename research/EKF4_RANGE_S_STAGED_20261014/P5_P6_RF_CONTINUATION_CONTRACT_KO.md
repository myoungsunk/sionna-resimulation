# P5/P6 continuation audit and bounded actual-RF 4state recursive experiment

## Claims and dependencies
P2 matched synthetic 600 complete paired trials at commit 3593eae0b16556e88e66734a524899b00db53324, run 38562441105: 2,400 model successes, no numerical invalid cases; MAP4 reduces heading RMSE in bias+.05 all 3 routes, degrades when bias=0. These are **synthetic only**.
P3 frozen 14 case-channel RF one-step archive eligible and P4 linearized joint numerical parity (run 38562745996). These are **not recursive RF performance**.
P5 full multimodal posterior reference from H3/G3 remains **UNRESOLVED** (original GH41→65 TV0.387065; independent RQMC ESS≈1). Nothing here changes original TV<=0.001 criterion, and a local MAP comparison CANNOT certify P5.
For P6, two separable claims:
(a) local 4state MAP **pilot** on original LoS/Full RF with fixed R0 model and frozen Sensor-v2 motion. Can run without certified G3 reference, but must report only local-filter accuracy and failure.
(b) full posterior credible calibration / generalization and P6 scientific_PASS require valid P5 posterior plus independent RF scenes, which are NOT currently validated.

## Before execution
1. GitHub cloud checkout exact SHA and P0-listed frozen H, LUT, observer, motion timeline, original archived source. Preserve SHA parity; no changes to frozen data.
2. Source audit of original `p2_frozen_rf_one_step.py`, P0 manifest and our `rf4_recursive_pilot.py` AST, no truth in estimation, same pose/time mapping, correct range OFFSET and S dimension, independent receipt.
3. Input audit `p0_verify_inputs.py` with exact original P0 39-asset checks; if any source/hash mismatch HOLD.
4. Paired LoS/Full in representative cases R2_aA_m0, R4_aA_m0, R5_aA_m0, noise_pair and gyro_bias L2, seed0. Compare DR3, EKF4, MAP4 original gate, MAP4 ungated. This is a bounded development trial, not held-out confirmation.
5. Joint Range+s Gaussian R0 with original 0.531598m calibration offset, Rs=.0081, Rr=.0068578637, Rsr=0 as **frozen assumption not proven independence**. Full 4x4 covariance and b_g state. No oracle truth, gyro bias level only used to create sensor stress, never as a classifier.
6. Preserve failure trace, numerical diagnostics and counts. Do NOT silently use DR-only fallback when MAP fails. No malicious mixing of non-independent RF sensors.
7. If Full RF causes a scientific contradiction, report it and test the R0 gate-on vs gate-off as a predeclared control. Do not post hoc tune Q/R to make results better. No P6 "scientific pass" without held-out independent scenes.

## Stop and reporting
This P6 local pilot is requested as an execution step toward P6, but it is NOT a replacement for P5 and does not establish full P6 performance. If source/audit/trace discrepancy blocks execution, mark only that subset invalid and preserve previous P2–P4 results. Any numerical code modification must have a new source audit receipt and replay relevant frozen snapshots.
