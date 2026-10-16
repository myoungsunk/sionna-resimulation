# Pole-safe LUT systematic revalidation — execution contract (2026-10-16)

## Scope and immutable baseline
- Preserve original 46×180×180 2° LoS FFD/LUT, S4/Joint4/SR4, original R2 and all historical experiment outputs; add a versioned pole-safe LUT candidate only.
- Frozen LUT SHA256 (numpy file) **711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079**.
- An angle-consistent candidate `theta0[j,k]=original_theta0[0,(j+k+90)%180]` has passed 9,519 native LoS samples: theta<2° (5 points) RMSE 0.454941 -> 0.001143, theta>=2° (9,514 points) unchanged. Candidate SHA256 **e6db187d2b8f0507ab588affb0bae66d26d2b778ce9244c36154342800f33f0b**. Do not assume this generalizes beyond the frozen ceiling-anchor/FFD convention.
- **Historical precedence:** 2026-10-11 `codex/ffd-pole-origin-audit-20261011` already used actual LFS LP±45 banks: [original-source diagnosis](https://github.com/myoungsunk/sionna-resimulation/blob/53d33ea0b44db6f66167acebda76fed26ea03d52/research/HEADING_RELIABILITY_20261010/23_ORIGINAL_FFD_POLE_SOURCE_VS_LUT_CAUSE_KO.md). The source FFD **is recoverable with Git LFS**, so do not claim it is unavailable.

## Mandatory audit and causal order
**S0 input/source SHA & CRC and baseline observational parity → S1 FFD Cartesian limiting pole layer & Jacobian → S2 all 9,519 LoS and associated Full matched error targets → S3 refit EVERY route-heldout mean+centered variance and joint Range–s error model from corrected truth → S4 full 4-state recursive replay with source-matched original vs corrected LUT → S5 MAP optimization history and gradients → S6 cross-scene/full temporal + curvature stress**.

No result after a failed prerequisite can be promoted to PASS. Every code edit requires renewed source audit, numerical tests and signed receipts. Preserve rejected outcomes. Test *one-variable* LUT differences first, then combined LUT+retrained error model as a separate arm.

## Historical affected branches and tests
| Priority | Historical lineage | Re-test |
|---|---|---|
| P0 | 2026-10-11 raw-LFS FFD pole and 9,519 native LoS | Direct original FFD Cartesian contraction, continuity as horizontal rho -> 0, yaw/port/frame invariance and F01 knot/seam regression |
| P0 | 2026-10-15 N4-A / N4-A2 (G5 Mean+Rs) | Same-prior original-v-patched peak K/H/NIS/Gate/P and **entire recursive** B0/L0/L1/L2 mount0/mount45 LoS/Full; event k=909 t=181.8s and 181.6-195.6s NEES tail |
| P0 | 2026-10-15 N4-C original Joint4/SR4 and POWER_JOINT | Replay full 979 steps, not just 829 scoring steps. Stratify first pole entry, accepted RF, episode NEES, heading/bias/XY RMSE, pose95, conditional XY NEES. Existing POWER may never approach pole; do not fabricate improvement |
| P0 | P2 G5/G5+FFD signed-mean/variance, P2 unified channel-mixture | Regenerate e_MP/e_LUT/e_state and corrected supervised labels, refit R2/R4/R5 folds without matching XY leakage and no truth/channel labels at inference; new source and hashes for all models |
| P1 | N4-B shared Range–s / N4-C POWER signed mean and covariance | Correct label-driven means, V_s and C_rs, recompute likelihood and P2 one-step/recurrent; keep native Range raw unchanged |
| P1 | 2026-10-15 P4 MAP 4,124 failures | Original-v-patch local MAP step histories: rho of **every proposed candidate** and theta0 crossing; distinguish theta0 discontinuity from generic 2° LUT knots and unrelated numerical step-acceptance |
| P1 | 2026-10-16 Exp1–4 / High-Vr / Q tests | If traces never enter theta<2°, certify direct nonimpact; do not re-run noise/Range-only outputs unless their code/path uses corrected LUT |
| P2 | 2026-10-11 sensor-v2 1,344 bank runs / 1,008 Range-only | Range-only ignores s so no direct LUT dependence; for s-enabled arms compare entire recursive traces and quantify pole visits. Respect known 128-seed pose-index bug quarantine |
| P2 | 2026-10-14 G2/G3 P3/P4 and numerical R3 | Only rerun cases using the same frozen LUT or corrected s labels; separate toy synthetic posterior and office with different detector, avoid source mixing |
| P2 | 2026-10-15 Active Yaw R5-4, RF-MHI | Recompute frozen LoS template gradients and uncertainty at source-matched theta~0; unchanged raw angle-resolved Full data; not a proof of new active scan |

## Fixed evaluation and GO criteria
- Matched source checks: 120 original input SHA / manifest CRC, exact reconstructed raw s/r and prior/Gate/time/pose id, original baseline x/P replay (strict 1e-9 plus separately recorded historical 4e-8 numerical drift; never silently loosen).
- Jacobian finite-difference vs analytical near 0°, 2°, 4°, +/-180° azimuth; require source physical field convergence in rho ring approaches and no spurious 1/rho blow-up. Verify input rotation/source binned FFD 257-frequency parity.
- S2 must match original values **bit-identically outside the modified theta0 interval**, show all LoS/Full sites and all near-pole labels, R2/R4/R5.
- S3 evaluation: signed residual, centered variance, PSD C_rs, log likelihood, normalized error, 50/90/95/99% coverage, tail and site-block confidence intervals, per-physical-site labels and hardware-only feature arm. Refit all folds: R5 near-pole labels contaminate R2/R4 *training* if not retrained.
- S4: original/corrected full-replay conditions B0/L0/L1/L2 x 2 mounts x LoS/Full x Joint4/SR4 plus nondeployed G5 & POWER variants, same gyro/wheel seed and original RF, report naturally gated and separately fixed-original-Gate arms. One-step peak counterfactual **not** sufficient to declare global fix.
- S5: 4,124 original invalid MAP traces, full candidate history, knot distance and nonsmooth criteria. Never declare old invalid runs retrospectively converged.
- S6 new independent geometry and multiple actual RF/motion seeds required for operational scientific PASS.
- No GT/native LoS/teacher channel leakage to runtime features.
- All original experiment reports are immutable. Generate delta reports with ORIGINAL, POLE_CANDIDATE and scientifically valid causal attribution flag.

## Initial status
Structural source discovery and correction candidate evidence are already available; **a new complete S0–S6 execution has not yet been demonstrated by the mere publication of this contract**. Mark each subsequent stage only when new run IDs, output hash receipts and raw per-frame checks exist.
