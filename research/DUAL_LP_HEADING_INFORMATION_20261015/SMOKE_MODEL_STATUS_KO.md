# Dual-LP RF measurement reliability vs Heading information — smoke/final-model preregistration (2026-10-15)

**Status: numerical/source audit PASS; RF-MHI-v0 structural model FREEZE; scientific/4-state deployment NOT PASS.** Existing H/FFD/LUT, S4, Joint4, SR4, original G5 and R2/R5 results are frozen and untouched. Full audited 24.5 KB Korean plan, runnable scripts, 140 score rows, full source-linked evaluations and hashes were delivered in conversation as `dual_lp_heading_reliability_model_smoke_and_plan_20261015.zip` (SHA256 `852f272ca7bea1bc96b074126c05ea5b48ffcda36e253c4d2b4a843fa3730319`). ZIP is *not* a GitHub artifact.

## Model choice

Separate (A) learned RF measurement error `mu_s,V_s` from dual-polarization CIR/quality measured packet, and (B) FFD/LUT `H_s` and current **pre-RF** state/covariance/Range-conditioned `eta_psi_s|r`, `K_psi_s|r` for potential heading information and expected *projected* error. Range `mu_r,V_r` calibrated independently; `C_rs` and colored temporal RF errors are pending. M1=(1+s_LoS)/2, M2=(1−s_LoS)/2, B=1−s_LoS² are **reparameterizations of the same LoS LUT prediction**, not novel independent multipath features. The actual frozen geometric angles are phi_tx=atan2(−v,u), phi_rx=wrap(atan2(−v,−u)−psi−mount). TX0 +45° LP is already embedded in FFD; never subtract it twice.

Offline exact decomposition: `s_full−h_LUT(x_prior) = (s_full−s_native_los) + (s_native_los−h_LUT(x_true)) + (h_LUT(x_true)−h_LUT(x_prior))`. Oracle/true pose may ONLY be scoring/training labels, never runtime inputs.

## Actual source-backed smoke results

- Original immutable input archive hashes and 120 member SHA256/length checks PASS; 14 original RF trace hashes PASS. Mathematics/negative tests **6/6**, frozen one-step Joint 14/14 state/P/K parity below 1e−9, gate differences **0**.
- Audited frozen DR3 source 7 cases×Full/LoS=14 traces, 14,502 observations. Two Gate policies × 5 frozen Rs model arms = **140 score rows**. Independent direct inverse vs Joseph recomputation verified **145,020 SPD 3×3 posterior matrices** and score maximum deviation **5.55e−15**.
- R2 Anchor A Full RF, t>=30: mount0/mount45 `e_sMP` RMS=0.1809/0.2376; native LoS-to-LUT RMS=0.0109/0.0081; prior-state-in-s space RMS=0.0057/0.0155; median |Hpsi|=0.4126/1.6614 per radian; median `eta_psi_s|r`=0.1393/0.7231.
- **Critical falsification:** p90 of actual offline `|Kpsi,s*(s_full−s_native_los)|` in degrees is **3.41° mount0 vs 10.23° mount45**. A steep LoS slope and high assumed Gaussian information do NOT guarantee small erroneous heading updates.
- Frozen original-gate Full 6,201-step pooled one-step Heading RMSE: R0 **2.3454°**, held-route HGBR G5 **1.6000°**, G5+predicted-distance **1.6008°**, G5+LoS expected matching & slope **1.6127°**, G5+matching/prior-info **1.6060°**. Dynamic gate G5=1.7013°, G5+matching=1.7010°, matching+info=1.6964°. NO consistent additional accuracy from matching features has been demonstrated.
- Case-averaged Full one-step AUC, heldout G5: `sqrt(Rs)` vs `|Kpsi,s|sqrt(Rs)` for **actual error projected to heading >3°** = **0.842 vs 0.875**, but for **actual update harmfulness** = **0.606 vs 0.571**. Projected contamination *size* and update harmfulness are distinct prediction targets.
- 169 real stored stationary-XY Full/LoS yaw response groups, centered ±10° subwindows: R2 mount0/mount45 native LoS LUT median slope |ds/dyaw| **0.433/1.586** per radian; median |Full−native LoS gradient mismatch| **0.161/0.064** per radian. Original archived yaw data only, NOT a completed moving-robot 10s active scan.

## Experimental gates before true final-model approval

| Gate | Needed evidence |
|---|---|
| P0 original/frozen audit | source hashes, exact s/r/time+LUT H parity and no leaked GT |
| P1 error decomposition | eMP/eLUT/eState, linearization vs true local model; F01 LUT interpolation limits |
| P2 signed measurement statistics | mu_s,V_s separately from M2; calibrate conditional NLL/coverage + LoS false alarms |
| P3 heading relevance | conditional information, actual Kpsi×error, genuine harm labels, uncertainty/multimodes |
| P4 independent ranging and correlation | mu_r,V_r and PSD C_rs, same-time and temporal correlations |
| P5 full 4-state recursive | paired B0/L0/L1/L2 ± bias, mount0/45 LoS/Full, DR4/S4/J4/SR4, RMSE/NEES/coverage and bias |
| P6 new paths and scenes | curved/yaw-varying path; ≥2 independent scene geometries, multiple sensor/RF seeds, site/scene holdout |
| P7 hardware/scan if necessary | actual available port power/phase, real Full RF yaw response, no double-counted packets |

**Scientific model FREEZE = false until all required gates pass.** Parameters/thresholds and deployment policy not fixed. R0/J4/G5 remains reference. S4/Joint4/SR4 must not be silently overwritten.

Source lineage: [frozen EKF RF observation model](https://github.com/myoungsunk/sionna-resimulation/blob/research/physics-range-pol-joint-20261015/research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py), [original G5 physical extraction](https://github.com/myoungsunk/sionna-resimulation/blob/b437fd154a9cf38f6b0bfe11a21c59ca63e0b25e/research/PHYSICS_RS_STAGED_20261015/code/features.py), [previous G5 physical-sensor report](https://github.com/myoungsunk/sionna-resimulation/blob/b437fd154a9cf38f6b0bfe11a21c59ca63e0b25e/research/PHYSICS_RS_STAGED_20261015/RESULTS_KO.md).