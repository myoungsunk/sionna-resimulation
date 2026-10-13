# Sensor-v2 + dual-LP RF heading reliability simulation specification v1.0

Date 2026-10-10. STATUS=SPEC_READY; new RF/CIR heading correlation and probe validation NOT EXECUTED. Governing prereg: 00_PREREG_CIR_AND_RF_HEADING_KO.md. No original production code or artifacts are overwritten.

## Inputs and provenance

RF: codex/post-a23-evidence-20261010 SHA 047cce2, POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C; seven paired full-vs-LoS channel cases R2_aA_m0, R2_aB_m0, R2_aA_m45, R4_aA_m0, R4_aB_m0, R5_aA_m0, R5_aB_m0. Use source verified H and H_LoS arrays shape (Nposes,257,2rx,2tx), SAMPLES.json, original frequencies, identical matched pose ids, first TX (+45 LP). Require hash+shape checks in CASES.json. The existing LUT hs_lut_2deg.npy original SHA256 711e12ee48a30cb666db4dada749b983de49bd565ea351b906269ec8da375a079 is an external input; do NOT regenerate or treat Git-LFS pointer as data.

Sensor-v2 audited source: codex/drive-sim-audit-integrated-20261010 SHA 16d22fc at audits/DRIVE_SIM_20261010/02_sensor_v2_review/source/src/qclean_uwb/drivesim. Must run from isolated checkout with exact file hashes. Legacy EKF and v2 are distinct and not silently fused. v2 only supports EKF direct-s; augmented A24 is legacy-only and not v2 evidence. Existing L1/L2 and F01/F02 failures remain OPEN.

## Observation contract and physical applicability

Sionna original observer: Hann, pad to 4N, IFFT times N, strongest-RX peak 30% first integer leading edge, common tap power P1,P2 and s=(P1-P2)/(P1+P2). Frequencies 257 bins over ~500 MHz. Record branch, selected tap, per-port amplitude CIR, noise floor, peak, P1/P2, s and range, detection and SNR. Pad grid resolution not interpreted as physical path resolution. If actual amplitude-only UWB module returns only first-path powers and not complete temporal CIR envelope, report CIR feature block as HARDWARE_UNAVAILABLE. Never use phase, path-level Jones, oracle rays, ground-truth pose or delay as inference features.

## v2 sensor and matched comparator

Nominal sample period dt=0.2s (5Hz), nominal driving speed 0.2m/s; preserve actual timestamps, station turns and original routes. State x6=(x,y,yaw,gyro_bias,gyro_scale,wheel_diameter_ratio), exact SE2 arc prediction. Use existing sensor-v2 frozen generator/filter laws with independent gyro/left-right wheel streams and recorded true low/mid/high generator parameters. Previous assumptions: gyro ARW 0.015deg/sqrt(s); gyro biases 0.01/0.05/0.2deg/s, SF 0.005/0.010/0.015, diameter ratio 0.002/0.005/0.010, wheelbase mismatch 0.005/0.0075/0.010. They are scenario assumptions, not validated hardware parameters. Save actually applied values and covariance Q (gyro–wheel correlation C=-GQB^T), known vs unknown wheelbase options, slip events, initialization and timestamps; NEVER feed true parameters/slip to estimator. Initial arms: exact pose and matched stochastic initial pose error (0.1m/5deg) with calibration prior documented separately.

Paired filter baselines for each same route/seed/noise:
A = RF-disabled v2 odom+IMU;
B = v2 with UWB range only;
C = v2 with range + matched direct LoS s;
D = v2 with range + actual full RF s;
E = v2 with range + RF reliability abstention/inflation under preregistered frozen classifier;
F = v2 with same controls plus 2/3 yaw probe as an offline study first. Reflect probe time and body rotation: saved yaw sweep rotates body antenna/robot, NOT independent RF head actuator; no zero-time free probes. Separate head-yaw model requires new geometry and hardware.

## Required saved records (every time step, no averaging before archiving)

ID: case, route, anchor, mount, pose_id, station_group, probe_id, sample time, interval dt, seed, noise/drift, SNR requested/realized, source and input SHA, motion phase.
EVALUATION_ONLY: truth x/y/yaw, true sensor biases/SF/slip, true anchor distance, direct LoS s, noise-free full s, paired multipath e_MP, RF-heading error truth, oracle nearest branch, harmful-RF-update flag.
SENSOR: left/right wheel raw increment, measured distance and yaw increment, measured gyro yaw increment and optional raw rate, Q, noise model, per-port P1/P2 s, range, first-path tap/peak, optional magnitude CIR by hardware contract, detection, noise floor, raw probe orientations.
FILTER: pre-RF predicted x6/P6, pose prior after IMU+odom, post-range prior if used, post-RF x6/P6, innovation_s/r, S_s/r, H_s/r, R_s/r, NIS pre-gate, gate decisions, reason rejected, timestamp and covariance eigenvalues, full pose NEES, heading errors and coverage.
RELIABILITY: all registered D/P/K CIR features; selected inverse LUT branch using **pre-RF prediction only**; all alternatives/ambiguity margin; q_good_5deg and classifier ID; probe angles, common fit, residual vector, whitened consistency if valid, offdiag temporal/probe covariance, accepted/rejected flags and probe-time cost.

## Experiment order

1. CHECK INPUT: checksum every H, H_LoS, LUT and frequencies; verify original Sionna antenna convention TX0 and pose matches. Record known F01/LUT caveats, abort if missing.
2. OBS PARITY: replay observation on original full/LoS H and compare with frozen observer. Abort discrepancies, no silent tolerance change.
3. V2 SENSOR-ONLY: no-RF Monte Carlo, known/unknown geometry + low/mid/high, matched/noisy initialization, PSD, Joseph, input correlations; original 12-second controlled baseline numbers are NOT parity targets unless exact settings match.
4. PASSIVE FEATURES: each full/LoS paired pose, full amplitude CIR D1-D4 P1-P5 from prereg; use true pose only to make held-out labels, no oracle inference. For distance [0,5), [5,10), [10,infty) compute bias/variance/RMS of s and range separately, by route, anchor, heading slope; report n and station-block CI.
5. HEADING: inverse LUT candidate branches using v2 RF-disabled p_minus/psi_minus, never truth-selected branch for primary. Label absolute circular heading error and correct<=5deg (sensitivity 2,10). Include ambiguity/no-match coverage.
6. RELIABILITY: Pearson and Spearman vs RF-heading error, 10-bin conditional means, partial distance/slope effects, logistic L2 probability with grouped leave-one-ROUTE-out; compare prevalence, distance, LUT slope, CIR D, polarization P, D+P+kinematic K. Report held-out Brier, AUROC, PR-AUC, ECE, calibration slope/intercept, risk-coverage and false-accept.
7. PROBE: reconstruct existing same-XY yaw blocks and preregistered index[0], [0,2], [0,2,4] (roughly 0,10,20deg); compute common correction, angle-shape residual and RF-heading reliability. Exact same station subsets and noise seeds for single/2/3-angle comparators. Probe agreement is NOT proof of absolute heading correctness. Held-out new scenes required before generalized claims.
8. FILTER: run A-E with identical seeds/trajectories, delayed pre-RF prior and no truth leakage; report heading RMSE/P95, lateral/pos RMSE, NEES and coverage, NIS, false reject/accept, outage duration, recovery, actual probe delay.
9. NEW-GEOMETRY TEST (not covered by current 7 cases): changed wall width/material, anchor mounting/placement, different corridor or room; no additional training on target until evaluation finished.

## File outputs / validation

00_INPUT_AUDIT.json, 01_FEATURES.csv/parquet, 02_LABELS_EVAL_ONLY.csv/parquet, 03_DISTANCE_BIAS_VAR.csv, 04_FEATURE_CORRELATIONS.csv, 05_CV_PREDICTIONS.csv, 06_CALIBRATION.csv, 07_PROBE_STATIONS.csv, 08_PROBE_COMPARISONS.csv, 09_V2_BASELINE.csv, 10_V2_RF_COMPARISON.csv, EXECUTION_STATUS.json, data dictionary, exact command/source/input SHA and plots (error vs features, distance bias/variance, calibrated probability, risk-coverage).

All reports must flag executed, blocked, not-run. Separate no-noise oracle, synthetic noise, v2 operational. Do not make endpoint NEES independent by treating time-correlated samples as new seeds. Use station/route blocked uncertainty and paired comparisons. Current seven cases are ONE underlying corridor environment, so GENERALIZATION_NOT_PROVEN remains true until an external geometry is tested.
