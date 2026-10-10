# Post-A23 descriptive checks (exploratory; no thresholds, no adoption decision)

Inputs: user's published branches `codex/a23-results-20261010` (H, LUT, FFD banks; hashes verified) and `codex/post-a23-evidence-20261010` (Q2/joint/L2).
Scripts: `scripts/drive_sim/residual_decomposition.py`, `scripts/drive_sim/post_a23_arm_summary.py`. These were run after seeing the data, not pre-registered.
Scope: R2-A, mount 0, one H store. No other route/anchor/mount can be said anything about.

## 1. Residual decomposition (R2A m0, 829 evaluated samples)
`r_s = s(H_full) - LUT(truth) = [s(H_full) - s(H_LoS)] + [s(H_LoS) - LUT(truth)]`. `H_LoS` is synthesised from the FFD banks at the actual
link length and passed through the same first-path chain (it is not a Sionna max_depth=0 run on this timeline; the 8-pose L2 audit shows the two
agree to <1e-6). The sum reproduces the A23 `RESIDUAL_R2A_m0.npz` `r_s` to 2e-15.

| s residual | mean | RMS | lag-1 | variance share |
|---|---|---|---|---|
| total | +0.0465 | 0.179 | 0.927 | 1 |
| multipath (full - LoS chain) | +0.0510 | 0.181 | 0.925 | 1.007 |
| LoS chain vs LUT | -0.0045 | 0.0109 | 0.150 | 0.003 |

By distance (multipath RMS): <5 m 0.028, 5-10 m 0.101, >10 m 0.280. LoS-chain-vs-LUT RMS stays 0.007-0.012 at all distances.
Range residual (RMS): total 0.123, multipath 0.132, LoS chain 0.045. The first-path tap differs between full H and LoS-only in 42 % of samples.
Reading: for this case the LUT/tap error (the L1/L2 gate failures) accounts for ~0.3 % of the `s` residual variance; the time-correlated bias that drives
the NEES inflation is almost entirely multipath. The distance growth is consistent with unresolved reflections (tap 0.149 m); that mechanism is
a hypothesis, no path-level data on this timeline was used.

## 2. Q1/Q2/joint arms (`ARM_SUMMARY.json`, 50 seeds, mean over drifts, bootstrap 95 % CI)
- Range-only structured error with white `s` (R1-R8): NEES 5.8-21.5 vs W0 5.0; heading RMSE 1.5-2.1 deg. Real range alone adds 6.7 NEES [5.5, 7.7].
- Real `s` with white range (S8): NEES 99.9, heading 11.8 deg, vs A0 106.5 / 10.9 deg. Adding real range to real `s`: +6.6 NEES [0.5, 16.8], heading -0.73 deg.
- AR(1) in both (J1) NEES 240, J2 (innovation correlation target 0.52, achieved 0.477): J2-J1 = +9.7 NEES [-14.3, 37.9] (undetermined), heading +0.39 deg [0.14, 0.70], position -0.007 m [-0.065, 0.062].
- J3 (joint block bootstrap): NEES 52, heading 3.0 deg; it does not reproduce A0 (106, 10.9), as S7 did not.
- Additivity J1-S3-R3+W0: NEES +14.6 [-1.1, 31.3], heading -0.55 [-0.98, -0.17], position -0.082 [-0.150, -0.017].
- NIS(s) in A0 by distance (seeds 0-1): 0.22 (<5 m), 0.37 (5-10 m), 3.44 (>10 m): the fixed sigma is over-conservative near and over-confident far.
