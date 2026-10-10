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

## 3. Native LoS-only H, all seven cases (added after the user's supplement `SUPPLEMENT_01a12449`, branch `codex/post-a23-evidence-20261010` `fc8a1fa`)
`NATIVE_<case>.json`: same decomposition with the native Sionna `max_depth=0` H on the full timeline (script `--h-los`). Descriptive, exploratory, mount-0 unless stated; evaluation mask t ≥ 30 s.

| case | n | s RMS total / multipath / LoS-chain-vs-LUT | variance share mp / LUT | multipath RMS by distance <5 / 5–10 / >10 m | range RMS total / mp / LoS chain | first-path tap differs | θ_geo<5° samples |
|---|---:|---|---|---|---|---:|---:|
| R2-A m0 | 829 | 0.179 / 0.181 / 0.011 | 1.007 / 0.003 | 0.028 / 0.101 / 0.280 | 0.123 / 0.132 / 0.045 | 0.42 | 0 |
| R2-A m45 | 829 | 0.238 / 0.238 / 0.008 | 0.998 / 0.001 | 0.046 / 0.186 / 0.347 | 0.151 / 0.167 / 0.048 | 0.60 | 0 |
| R2-B m0 | 829 | 0.113 / 0.113 / 0.013 | 0.981 / 0.012 | 0.023 / 0.165 / – | 0.090 / 0.094 / 0.045 | 0.26 | 0 |
| R4-A m0 | 592 | 0.221 / 0.221 / 0.009 | 1.003 / 0.002 | 0.048 / 0.170 / 0.316 | 0.148 / 0.147 / 0.044 | 0.55 | 0 |
| R4-B m0 | 592 | 0.117 / 0.117 / 0.008 | 1.005 / 0.004 | 0.076 / 0.168 / – | 0.092 / 0.094 / 0.048 | 0.35 | 0 |
| R5-A m0 | 1265 | 0.194 / 0.195 / 0.010 | 0.997 / 0.002 | 0.022 / 0.176 / 0.290 | 0.176 / 0.180 / 0.047 | 0.38 | 9 |
| R5-B m0 | 1265 | 0.098 / 0.095 / 0.030 | 0.907 / 0.095 | 0.023 / 0.132 / – | 0.130 / 0.134 / 0.045 | 0.29 | 10 |

- Multipath carries ≥ 91 % of the `s` residual variance in every case (R5-B: LUT part 9.5 %, which coincides with its 10 near-vertical θ_geo < 5° samples, where the LUT azimuth gauge is singular).
- Anchor B residuals are about half of anchor A's (RMS 0.10–0.12 vs 0.18–0.22), as are the range residuals; mount 45° is worse than 0° (0.238 vs 0.179). Lag-1 of the multipath part: 0.88–0.95 (R2, R5-A), 0.70–0.78 (R4, R5-B).
- The synthesised LoS channel used in section 1 agrees with the native one: `s` max |difference| 1.1e-5, range 0, first-path tap identical on R2-A m0 (all 829 samples). This validates the section-1 approach for the case it was applied to.
- Not done here: attribution of the multipath to reflection faces (the native LoS runs carry no interaction data; `BLOCK_D` of the supplement has stored-path first/second path delays for R2-A m0 only), and any statement about the mechanism.
