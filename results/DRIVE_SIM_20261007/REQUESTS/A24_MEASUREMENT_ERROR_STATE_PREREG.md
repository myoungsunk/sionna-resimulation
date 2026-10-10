# A24 — Estimator-side mitigation of the time-correlated multipath measurement error (F02 direction): pre-registration

Author: Claude (author side). Branch `claude/cool-dijkstra-hnznhm`. Status: **pre-registration; no filter code for this amendment exists yet and no A24 number has been computed.**
Definitions, procedures and interpretation rules below are fixed **before** any A24 filter run. Items marked *(proposed, unapproved)* are the assistant's proposals and are not acceptance criteria until the user approves them in writing; until then results are reported as numbers with no PASS/FAIL label.
F01, F02 and `scientific_PASS=false` stay OPEN regardless of the outcome of this amendment.

## 0. Why this experiment, and what it can and cannot answer

Evidence it builds on (all descriptive, none pre-registered as a mechanism claim):
- A23 Q1/Q2/joint (user's execution, branch `codex/a23-results-20261010`, `codex/post-a23-evidence-20261010`): a synthetic `s` error with the real bias and lag-1 (≈0.93) alone raises NEES from ~5 to 40–210; real range alone adds ≈ +6.7 NEES. The filter with matched white noise is consistent (M0 NEES ≈ 2.3).
- Post-A23 residual decomposition (`DEV_RESULTS/POST_A23_RESIDUAL_DECOMPOSITION/`, R2-A m0 only): 99.7 % of the `s` residual variance is multipath (full H − LoS-only chain at the true pose); the LUT/tap error is 0.3 %. Multipath RMS grows with distance: 0.028 / 0.101 / 0.280 (<5 / 5–10 / >10 m). The mechanism (unresolved reflections) is a hypothesis.
- The stored filter treats the residual as white with σ = 0.16 and a distance-independent variance; A21 showed that a distance-dependent *white* σ does not repair NEES.

Question A24 asks: **if the filter carries the slowly varying part of the measurement error as an explicit state (Markov bias), does the pose estimate become statistically consistent without making the accuracy worse?** It is an estimator-side mitigation; it does not change the RF model, the LUT, the gate, or the sensors.

It can answer, in this simulation: (a) whether the augmented filter is consistent under a *correct* error model (positive control); (b) how it behaves under error processes that are *not* its model (block bootstrap, aligned real residual); (c) on the one case whose residual supplied the parameters (in-sample, flagged), whether consistency and accuracy move; (d) in stage 2, on held-out routes/anchors.
It cannot answer: whether real UWB hardware multipath behaves this way; whether the mechanism is reflections; whether another estimator would do better; anything about routes/mounts not run.

## 1. Filter variants (arms of the experiment)

All variants share every stored setting (P0, process noise, gate χ²₁ 99 %, `pos_process_std = 0.01`, dt = 0.2 s, EKF, odometry/gyro handling, `mount_deg`) and the same observations as A23 (same random keys). Only the measurement-error handling differs.

| ID | State | `s` measurement | range measurement |
|---|---|---|---|
| **F0** | 6 states (stored filter) | `z_s = h_LUT(x) + v`, `R_s = thermal + σ_mm²` (stored σ_mm = 0.1610) | stored `R_r = 0.0068579` |
| **F1** | 6 + β_s | `z_s = h_LUT(x) + β_s + v`, `R_s = thermal + σ_ws²` | stored |
| **F2** (primary) | 6 + β_s + β_r | as F1 | `z_r = d(x) + off + β_r + v`, `R_r = σ_wr²` |
| **F3** (secondary) | as F2 | as F2 with `σ_β,s²(d)` scaled by the training distance profile (§2.3) | as F2 |

β_j (j = s, r) is a first-order Gauss–Markov state: `β_{k+1} = φ_j β_k + η_k`, `Var(η) = σ_βj² (1 − φ_j²)`, initial `β_0 = 0`, `Var(β_0) = σ_βj²` (stationary). It is uncorrelated with the other states at start. The β_s and β_r processes are independent in the filter (the real innovation correlation 0.52 is **not** modelled; A23 could not determine a joint effect). The 6-state block is propagated exactly as in F0; β does not enter the motion model.
Implementation constraint (stated now so it cannot be bent later): the augmented filter is a new subclass; the stored `DriveFilter` code path, `N = 6` and every stored result are untouched. With the augmentation switched off (σ_β = 0, stored R) the subclass must reproduce the stored A0 rows (§6, gate G-A24-0).
Only the `ekf` kind is covered. IEKF/UKF/GSF are out of scope.

## 2. Parameters: rule, not tuning

No parameter is chosen by looking at a filter result. The parameters come from a fixed fitting rule applied to a *training residual series*.

### 2.1 Training series
`r_s(k) = s_chain(k) − LUT(truth_k)` and `r_r(k) = range_chain(k) − (d3_k + range_offset)` from the noise-free chain, on the evaluation mask (t ≥ 30 s, 829 samples per case). Stage 1: R2-A m0 (A23 `RESIDUAL_R2A_m0.npz`). **This is the same series that generated the S-/R-arms and the A0 case**, so every stage 1 statement about those arms is in-sample for the parameters. Stage 2: leave-one-case-out (§5).

### 2.2 Fit rule (deterministic, run once, frozen)
For each variable j: fit the state-space model `y_k = β_k + w_k`, `β_{k+1} = φ β_k + η_k`, `w ~ N(0, σ_w²)` with stationary initial `β_0 ~ N(0, σ_β²)`, no separate mean (the mean is carried by the slow state), by maximum likelihood with the Kalman filter on the un-demeaned series. Bounds: `φ ∈ [0.50, 0.999]`, `σ_β², σ_w² ∈ [1e-8, 1]`. Optimiser: L-BFGS-B on `(logit φ, log σ_β², log σ_w²)`, start `(φ=lag-1 of the series, σ_β² = 0.8·var, σ_w² = 0.2·var)`. Reported with the log-likelihood and a comparison against the sample ACF at lags 1, 2, 5, 10, 25 (the real `s` residual ACF is 0.927, 0.834, 0.484, −0.024, 0.001; a pure AR(1) with φ = 0.927 gives 0.86, 0.68 and 0.47 at lags 2, 5 and 10, so the AR(1) is a known misfit).
`R_s` in F1/F2/F3 is `thermal + σ_ws²` (thermal as in F0); `R_r` is `σ_wr²` in F2/F3. The numbers are written to `A24_FIT_PARAMS.json` with its SHA256 by `scripts/drive_sim/fit_measurement_error_model.py` and **committed before the first filter run**; any later change creates a new amendment.
Sensitivity (reported, not a selection): `φ` replaced by `argmin_φ Σ_{l=1..10} (ρ_l − φ^l)²` with σ_β², σ_w² re-fitted at that φ (variant "-acf").

### 2.3 F3 distance profile
`g(d) = ms_mp(d) / ms_mp(all)` where `ms_mp` is the mean-square residual in the three distance terciles used in the post-A23 decomposition (<5, 5–10, >10 m; 3-point interpolation by `θ_geo` knots at the tercile centres, constant outside), computed from the same training series. `σ_β,s²(d) = g(d) · σ_β,s²`, `σ_ws²` unchanged. Stage 1 only; F3 is exploratory.

## 3. Stage 1 — synthetic and in-sample (R2-A, mount 0°, P0, SNR 30, drifts 0–2, seeds 0–49)

All 22 A23 observation arms are run with F1, F2, F3 (F0 rows already exist from A23): arms A0, M0, W0, S1–S8, R1–R8, J1–J3 → 22 × 150 × 3 = **9,900 runs** (+ F0 reproduction gate 150). Interpretation groups:

| Group | Arms | Role |
|---|---|---|
| Positive control | S3 (bias + AR(1) s), R3, J1 | Error generated from the fitted AR(1)+bias statistics (not identical to the fitted state-space model: the generator adds no separate white part beyond the thermal chain noise); consistency here tests the implementation and the linearisation, not the physics |
| No-harm | M0, W0, S5 (iid zero-mean) | The augmented filter must not degrade a filter-consistent case |
| Model-mismatched synthetic | S6 (aligned real, mean-removed), S7 (block bootstrap), S4 (iid resample), J3 | Error not generated by the filter's model |
| In-sample real | A0, S8, R8 | Parameters were fitted on this series; **not evidence of generalisation** |
| Factor probes | S1, S2, R1, R2, R4–R7 | Descriptive only |

Metrics (identical definitions to A23): `nees_mean`, `nees_cov95`, `heading_cov95`, `nees_tail_lo/hi`, `heading_rmse_common_deg`, `pos_rmse_common_m`, eval-mask NIS (pre-gate and accepted), rejection fractions. Added: (i) the mean of `β̂_s`, `β̂_r` and their innovations-implied variance; (ii) on the synthetic arms where the injected error is known, the RMSE between `β̂` and the injected error low-pass component (reported only as a diagnostic that the state tracks something; the low-pass definition is the moving average over 2.6 s = 13 samples); (iii) NEES, heading error and NIS_s by distance tercile (<5, 5–10, >10 m), seeds 0–1 traces; (iv) the gyro-only/odometry baseline (`odom_imu`) and the range-only baseline for the A0 key set so that "does `s` still help" is answerable.
Traces: seeds 0–4 × drifts 0–2 for all arms and variants (A23 stored seeds 0–1 only; 5 seeds because the joint effect was undetermined at 2).

## 4. Reading rules (fixed now)

Seed-paired differences (mean over drifts, 50 seeds) with bootstrap 95 % intervals as in A23. Per-drift results are reported first; pooled numbers second. The families below are the *only* inferential questions; multiplicity is not corrected and exploratory rows are labelled.

**Primary, pre-specified.**
- P1 (consistency under the correct model): F2 on the positive-control arms.
- P2 (consistency in-sample): F2 on A0.
- P3 (accuracy): F2 − F0 on A0 for `heading_rmse_common_deg` and `pos_rmse_common_m`, paired.
- P4 (no-harm): F2 − F0 on M0, W0, S5.

**Consistency criteria — *proposed, unapproved* (must be approved or replaced by the user before outcomes are read).** Two-sided, on the seed-mean over drifts:
- pose NEES mean in [2.0, 5.0] (expected 3; M0 is the one matched reference and sits at 2.3, so the lower side is not required to equal 3);
- pose NEES ≤ 7.815 coverage in [0.90, 0.99]; heading |err| ≤ 1.96σψ coverage in [0.90, 0.99];
- NEES lower-tail mass (< 0.2158) and upper-tail mass (> 9.3484) each ≤ 0.10 (nominal 0.025 each; the correlated samples make the sampling spread wider than χ²₃, which M0/W0 illustrate);
- a variant that passes only because the covariance is inflated while the accuracy is worse than F0 is **not** a mitigation: P3 is a co-requisite *(proposed, unapproved)*: neither heading nor position RMSE worse than F0 with an interval above 0.
- no-harm *(proposed, unapproved)*: on M0/W0/S5 the paired NEES difference to F0 has an upper bound ≤ +1.0 and the heading RMSE difference an upper bound ≤ +0.10°.

**Allowed statements per outcome (fixed now).**
| Outcome | Allowed statement | Not allowed |
|---|---|---|
| P1 fails (positive control inconsistent) | The augmented filter or its linearisation is inconsistent even under its own error class (implementation / observability / gating issue); stop, diagnose | Any statement about multipath physics |
| P1 passes, P2 passes, P3 no harm | In this simulation, the augmentation makes the filter consistent on the series that supplied its parameters without a measured accuracy loss | Generalisation to other routes, anchors, mounts; hardware; "F02 resolved" |
| P1 passes, P2 fails | The Markov-bias model with the fitted parameters does not remove the inconsistency on the in-sample case; report which statistic fails and the distance-tercile pattern | That the multipath cannot be mitigated by an estimator |
| P2 passes but P3 shows worse accuracy | Consistency is bought by down-weighting `s`; compare with `odom_imu` to state whether `s` still contributes | Mitigation success |
| Consistent only for mean NEES, not coverage/tails | Marginal mean is right, shape is not | Consistency |
Stage 1 cannot close F02. F02 remains OPEN until stage 2 criteria approved by the user are met on held-out cases and the clean-S6 chronology item (G3) is handled separately.

## 5. Stage 2 — held-out cases (pre-registered now; run only after stage 1 is reported)

Cases: R2-A, R2-B, R4-A, R4-B, R5-A, R5-B (mount 0°; mount 45° only where the H store exists), drifts 0–2, seeds 0–49, production observation chain (the S6 configuration, i.e. the A0-type arm, not synthetic arms). Variants F0 (reproduction gate), F1, F2.
For each target case the parameters are fitted by §2.2 on the **concatenation of the residual series of all other cases** (leave-one-case-out; segments are concatenated without bridging samples across cases, the ML recursion restarted per segment), and recorded in `A24_FIT_PARAMS_LOCO.json` before running. Data needed from the user: `H_<case>.npy` for those cases and the `RESIDUAL_<case>.npz` produced by the existing `structured_noise_control.py residuals` command (no filter, minutes on CPU).
Reading: the same P2/P3 family per case; no pooling across cases without per-case reporting. A polar-singularity (θ_geo < 2°) exposure count per case is reported because those samples are LUT-invalid and not multipath.

## 6. Gates, order, and what stops the run

1. **G-A24-0 (equivalence):** the augmented subclass with the augmentation off reproduces stored A0 (150 keys) to 1e-9 in heading RMSE, position RMSE and NEES, with the A23 request-set check (duplicates / missing / non-finite). Failure stops everything.
2. **G-A24-1 (fit frozen):** `A24_FIT_PARAMS.json` committed with SHA256 before any F1–F3 run.
3. **G-A24-2 (unit tests, local CPU):** (i) a linear-Gaussian test where the augmented filter with the true β model is consistent (NEES ≈ 3 in expectation over many seeds); (ii) a test that a constant offset in `z_s` is absorbed by β_s; (iii) the off-switch equivalence at unit level; (iv) covariance symmetry/PSD over a run.
4. Stage 1 runs, then the report; stage 2 only after the stage 1 report and the user's approval of the criteria.
Order of the stage 1 run: A0 reproduction (150) → positive control and no-harm arms → remaining arms. Settings are not changed between arms; a failed run is listed and not replaced.

## 7. Known limitations stated in advance
- The AR(1) is a misfit to the real ACF (lag-10 is −0.02 vs 0.47); results from the "-acf" sensitivity are reported but do not replace the primary rule.
- β_s is confounded with heading when the s-slope is small (`ψ+mount ≡ 0 mod 90°`); a bias state can absorb a genuine heading error there. The augmented filter is expected to lean more on the gyro; whether that helps is exactly P3.
- Residuals are modelled as stationary in time; the real process is a function of position/geometry (distance dependence) and the probes (in-place rotations) change the geometry without moving. F3 is a crude distance-only version.
- Stage 1 trains and tests on the same series for A0/S8/R8.
- The independent audit's remaining blockers (G3 chronology, anchor-B parity, F01 L1/L2) are not affected.

## 8. Reproducibility items to be implemented after this document is reviewed
`scripts/drive_sim/fit_measurement_error_model.py` (§2.2/2.3; outputs hashed), subclass `AugmentedDriveFilter` (new file `src/qclean_uwb/drivesim/filters_aug.py`), an `--filter-variant` option in `structured_noise_control.py` writing the variant into the arm key and `RUN_MANIFEST` (fit-param hash included), tests (§6.3), the stage 1 report generator (extends the A23 report), and the data request for stage 2 (§5). Not done in this commit.
