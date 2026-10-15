# R5: distance-normalized FP / Heading-harm Schmidt / Polarization XY — audited smoke

Date 2026-10-15. **Technical execution complete; scientific generalization NOT proven.** This result comes from a separate local research harness, not modifications to frozen Sionna RF, original LUT, R0 or original Joint4/S4/SR4.

**Design:** 19,038 LoS/Full samples across 7 RF cases, additional kappa_FP80 = detected-common-tap power / first-80tap sum, and distance-normalized log first-path power calibrated on R4/R5 LoS. Harm label is whether original J4 RF update worsened squared heading error; R4/R5 used for training, R2 held out. Original G5 Rs and signed-mean arms remain unmodified controls. New arms: harm-score gain attenuation, hard bias Schmidt K_b=0, prior pose–bias covariance-block damping (lambda=0.2), OU shrinkage tau=30 s, H_s,xy=0 approximation and separate range-then-s update with s-only K_xy=0, plus G5 Rr comparator.

## Physical risk / held-route results

| Metric | Raw distance/power | Normalized power + kappa |
|---|---:|---:|
| R4 MP-proxy AUROC | 0.842 | 0.796 |
| R5 MP-proxy AUROC | 0.885 | 0.756 |
| R2/B0 Full mount0 MP-proxy AUROC | 0.783 | 0.736 |
| R2/B0 Full mount45 MP-proxy AUROC | 0.808 | 0.731 |

The normalized MP classifier never exceeded p=0.5 in either R2 Full condition. The existing original-J4 bias deviation surpassed 0.05 deg/s at 5.8s in B0/Full/mount0: **the hypothesis of early multipath detection by this normalized score is rejected for the frozen test**. R4/R5 held-route AUROC for heading harm with prior/innovation/physics was ~0.574/0.512, not reliably calibrated. Heldout R2 B0 AUROC was 0.789 (mount0 Full) but 0.523 (mount45 Full); false alarms occurred on LoS.

## Heading RMSE (degrees)

| Arm | B0 Full m0 | B0 Full m45 | L2 Full m0 | L2 Full m45 | L2 LoS m0 |
|---|---:|---:|---:|---:|---:|
| J4 | 7.490 | 0.845 | 7.521 | 0.848 | 0.243 |
| G5 Rs only | 4.304 | 1.349 | 4.378 | 1.361 | 0.237 |
| G5 Rs + old MP gain attenuation | 4.138 | 1.634 | 4.244 | 1.569 | 0.403 |
| G5 Rs + new harm-score bias gain attenuation | 3.343 | 1.832 | 4.113 | 1.732 | 1.444 |
| G5 Rs + new hard bias Schmidt freeze | 3.446 | 1.499 | 3.912 | 1.495 | 1.076 |
| G5 Rs + harm-triggered prior cross-P damping | 2.437 | 0.906 | 3.800 | 0.949 | 1.337 |
| G5 Rs + OU leak | 3.663 | 1.959 | 4.644 | 1.847 | 1.486 |
| J4 H_s,xy=0 diagnostic | 7.304 | 1.317 | 7.430 | 1.334 | 0.356 |
| J4 range-then-s K_xy=0 | 6.991 | 1.436 | 7.236 | 1.571 | 0.686 |

## Pose NEES

| Arm | B0 Full m0 | B0 Full m45 | L2 Full m0 | L2 Full m45 |
|---|---:|---:|---:|---:|
| J4 | 2591.15 | 86.87 | 297.85 | 86.84 |
| G5 Rs only | 214.34 | 134.87 | 2787.35 | 135.05 |
| Harm-score gain attenuation | 271.20 | 136.84 | 217.75 | 134.73 |
| Prior cross-P damping | 202.76 | 134.09 | 218.07 | 131.71 |
| G5 with s H_s,xy=0 | 198.94 | 164.16 | 184.70 | 165.45 |

These arms reduce errors in specific conditions, but **none provides validated 95% Pose coverage across Full RF conditions**. In particular, masking the physically correct H_s spatial derivatives does NOT isolate a universal overconfidence cause, and harms mount45/LoS.

## Mathematical and code audit

For ANY Kalman gain K, Joseph P+ = (I-KH) P- (I-KH)^T + K R K^T is PSD for PSD P-, R. Selective row attenuation cannot algebraically destroy PSD; posterior calibration may nonetheless fail. The hard K_b=0 Joseph control is Schmidt-like, whereas convex prior cross-block covariance damping is a DISTINCT heuristic. OU bias reversion toward 0 is deliberately unsuitable as a general L2 model.

Six original immutable input ZIPs and seven key source Git blob hashes checked. Original shared-tap s parity <=1e-12 over 19,038 frames. After code defects and re-audit: 8/8 source-backed mathematical tests PASS, 160 paired arm evaluations, **156,640 SPD full covariance matrices**, independent metric discrepancy max 1.27e-11, original J4/G5 gate mismatches **0**. Historical strict state parity 11/12 on B0 (one known Full mount0 numerical delta ~4e-8 preserved as failure).

## Limitations and evidence transfer

One corridor, gyro/wheel seed0, B0 and L2 only; R4/R5 training and R2 held out are not independent scenes. Complex multi-port CIR is research-only until hardware availability confirmed. Early kappa_FP80 in LoS is about 0.02–0.03 because this is a leading-edge tap, not physical direct-path power fraction. The R4/R5 exploratory OOF normalized reference P0 was pooled over train routes; final R2 test remained held out, and strictly fold-local P0 calibration is pending.

Independent full source and raw-result ZIPs are linked in the accompanying ChatGPT research conversation, not committed to this branch: source SHA256 c7036f15c4de50f6023c7d6c42437e1eb4ea30b8c94e6fd0552aa6c6ad125659, results SHA256 1ab095283f8141134680f83732964186dc05e15aca8851ae7c80d68930433163. Frozen RF/previous results have NOT been modified. Do not promote these prototypes into production.