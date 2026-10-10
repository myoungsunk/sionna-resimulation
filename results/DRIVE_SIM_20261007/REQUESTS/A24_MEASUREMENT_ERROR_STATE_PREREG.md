# A24 — Estimator-side mitigation of the time-correlated multipath measurement error (F02 direction): pre-registration

Author: Claude (author side). Branch `claude/cool-dijkstra-hnznhm`. Status: **pre-registration; no filter code for this amendment exists yet and no A24 number has been computed.**
Definitions, procedures and interpretation rules below are fixed **before** any A24 filter run. Items marked *(proposed, unapproved)* are the assistant's proposals and are not acceptance criteria until the user approves them in writing; until then results are reported as numbers with no PASS/FAIL label.
F01, F02 and `scientific_PASS=false` stay OPEN regardless of the outcome of this amendment.

## 0.0 Sensor model, and stage structure (rev1, 2026-10-10, before any A24 code or run; decision by the user)

- **Stages 1 and 2 use the legacy sensor model** (`sensors.py` as in the production S6 and A23: aggregate wheel increments, unsigned Euler integration, per-sample slip, `dt = 0.2 s`, 6-state EKF with `pos_process_std = 0.01`). Reasons: the A0 gate against the stored S6 exists only for legacy; the arms pair with A23; changing the sensor and the measurement-error model together would mix the causes.
- **Stage 3 repeats F0/F2 under sensor-v2** and is pre-registered in §9. Sensor-v2 is the intended basis for subsequent work, but it is not adopted yet: its code is not committed in any production branch (the user's own re-audit lists it as uncommitted, `commit_push_merge=false`), it has had no independent review, and it has no stored production reference result. Until stage 3 is run and the user fixes the v2 code revision, "new-sensor-model results" are not claimed anywhere.
- The measurement-error fit (§2) uses the noise-free chain residual and does not depend on the sensor model; the same frozen `A24_FIT_PARAMS.json` is used in stage 3 without refitting.

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

**Consistency criteria — APPROVED by the user on 2026-10-10 as proposed (A24 rev4), before any stage-1 outcome was read.** Two-sided, on the seed-mean over drifts:
- pose NEES mean in [2.0, 5.0] (expected 3; M0 is the one matched reference and sits at 2.3, so the lower side is not required to equal 3);
- pose NEES ≤ 7.815 coverage in [0.90, 0.99]; heading |err| ≤ 1.96σψ coverage in [0.90, 0.99];
- NEES lower-tail mass (< 0.2158) and upper-tail mass (> 9.3484) each ≤ 0.10 (nominal 0.025 each; the correlated samples make the sampling spread wider than χ²₃, which M0/W0 illustrate);
- a variant that passes only because the covariance is inflated while the accuracy is worse than F0 is **not** a mitigation: P3 is a co-requisite *(approved)*: neither heading nor position RMSE worse than F0 with an interval above 0.
- no-harm *(approved)*: on M0/W0/S5 the paired NEES difference to F0 has an upper bound ≤ +1.0 and the heading RMSE difference an upper bound ≤ +0.10°.

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


## 9. Stage 3 — sensor-v2 (pre-registered now; run only after stages 1–2 are reported and the open items below are fixed by the user)

### 9.1 What sensor-v2 changes relative to legacy (from the user's `MODEL_CONTRACT.md` and source, audit branch `codex/drive-sim-audit-integrated-20261010`, `02_sensor_v2_review/source/`)
Encoder-level generation (left/right angles, common scale, wheel asymmetry, wheelbase mismatch) with signed SE(2) increments; odometry distance/yaw reconstructed from the noisy encoders with correlated left/right noise; gyro `N²dt`; optional bias random walk; time-based slip; `dt` from timestamps; a filter that applies the shared-input correlation update `C = −G Q Bᵀ` (EKF, direct-`s`, 6 states, no new calibration state); `pos_process_std` forced to 0; odometry gate χ² 99.9 %. RF range/`s` update equations are unchanged, and the RF-side correlation and LUT residual are explicitly not handled by v2. **Consequence:** F0-v2 is not expected to reproduce legacy F0; the legacy rows and the v2 rows are different experiments. Differences between them are descriptive and confounded (slack removed, input correlation, SE(2), gate, slip law).

### 9.2 Items that must be fixed by the user before stage 3 (open; none is decided by this document)
1. **v2 code revision.** v2 exists only as an uncommitted working copy and as a copy under `audits/…/02_sensor_v2_review/source/` with file hashes in `CHANGE_MANIFEST.json`. Proposal *(unapproved)*: the user commits the v2 file set on a `codex/` branch as a single commit; stage 3 uses that commit and records its SHA256 file hashes. No v2 file is imported into this branch by the assistant without that decision.
2. **Sensor configuration.** Proposal *(unapproved)*: primary `neutral.json` (`common_scale = 0`, `bias_rw = 0`, `slip_mode = time`, condition `all`); sensitivity `assumed_common_scale.json` and `assumed_bias_rw.json`, reported separately, not pooled. Levels 0, 1, 2 ↔ legacy drifts low, mid, high (same three levels).
3. **Initialisation.** Proposal *(unapproved)*: primary = prior pose uncertainty of the production setting (0.1 m, 5°, calibration priors unchanged); sensitivity = exact initial pose. The v2 limited RF run showed different behaviour for the two (exact init: NEES ≈ 100 with `s`; prior: ≈ 5), so they are never pooled.
4. **Truth convention.** v2's strict SE(2) extraction rejects the existing Euler-built paths (residual ≤ 1.46e-4 m on the R1 subset). Proposal *(unapproved)*: use the explicit `legacy-euler` increments so that the stored routes and H stores are unchanged, record the evaluation-only mismatch (SE(2) re-integration difference, ≤ 2.7 mm on the R1 subset) per route, and state in the report that the pose truth is the legacy one.
5. **v2 reference result.** A full-route v2 runner on stored H/timelines does not exist (v2's RF evaluation covers the first 201 R1 samples only). It must be written and unit-tested; it is a new script, not a change to the legacy runner.

### 9.2a Status of §9.2 after checking branch `codex/drive-sim-audit-integrated-20261010` (16d22fc), 2026-10-10 (read only; nothing imported)

| Item | Found on the branch | Status |
|---|---|---|
| 1 v2 code revision | Not a commit. Dirty snapshot at base `2337c33` in `audits/DRIVE_SIM_20261010/02_sensor_v2_review/source/`; identified by file hashes. `filter_v2.py` sha256 `af31951d…159f` equals the stage-2 `CORRECTION_RECEIPT.json` "after" hash (covariance guard `512·eps·scale`; estimator equations unchanged). `sensor_v2.py` is `56ea1c8f…` (the original `CHANGE_MANIFEST` lists `8dadbdc6…`, so it was changed during the review; the change is not itemised in the receipt I read). `evaluation_v2.py` `6f9c5e84…` matches the original. `filters.py` / `experiment.py` differ from base only by small additive v2 hooks (`model_version`, dispatch, `summarize_output`); against the current work branch the difference is limited to later additive A18–A23 code. Tests present: `test_sensor_v2*.py` (3 files) | Usable as the basis **by file hashes**. Stage 3 records these hashes; any v2 file imported into this branch is imported verbatim and hash-checked, in a separate commit |
| 2 sensor configs | `configs/sensor_v2/{neutral,assumed_common_scale,assumed_bias_rw}.json` (hashes `17ed7bb6…`, `3c1880fa…`, `37dee102…` equal `CHANGE_MANIFEST`) | Present |
| 3 initialisation | `evaluate_sensor_v2_rf.py` and `run_sensor_v2.py --initial exact legacy-prior`: `exact` = pose P0 zero; `legacy-prior` = initial pose error drawn from the production prior (0.1 m, 5°) with that prior kept | Present; matches the proposal |
| 4 truth convention | `V.motion_increments(..., convention="legacy-euler")` for the RF subset, with `evaluation_integration_mismatch_pose` stored | Present for the R1 subset; route-wise mismatch must still be recorded for R2-A |
| 5 full-route v2 runner | **Not present.** The RF evaluation is the first 201 samples of R1 y0 at **SNR 35 dB** with observation streams `(V.NAMESPACE, seed, observation)`; `run_sensor_v2.py` is synthetic fixed-truth; `run_experiments.py` / `run_route_experiments.py` refuse `sensor-v2` | Open: a new full-route runner (R2-A, SNR 30 to match A23's chain, same A23 observation arms) must be written and tested |

Further points found: the v2 sensor generator streams are separate from the legacy streams, so v2 and legacy runs share neither sensor noise nor drift draws (observation arms can still share the RF/observation keys only if the runner is built that way; this is to be specified in the runner, not assumed); the limited RF run used SNR 35, so it is not comparable with A23's 30 dB.

### 9.3 Gates
- **G-V2-0 (legacy untouched):** with the v2 code present and `--model-version legacy`, the stored A0 (150 keys) reproduces to 1e-9, as in G-A24-0.
- **G-V2-1 (v2 determinism and freeze):** the v2 F0 run on R2-A m0 A0 (150 keys) is executed twice (independent processes) and is bit-identical or ≤ 1e-12; its result file hash is committed as the v2 reference. Any later change to v2 code or settings must reproduce it or open a new amendment.
- **G-V2-2:** v2 PSD/symmetry checks pass on every run (the v2 filter raises on invalid covariance); failures are listed, not replaced.
- Fit frozen (G-A24-1) is a prerequisite; no refit.

### 9.4 Design
Case R2-A, mount 0°, P0, SNR 30, levels 0–2, seeds 0–49. Variants **F0-v2** and **F2-v2** (the v2 filter plus the same β_s, β_r augmentation as §1; implemented as a subclass of `SensorV2Filter`, with the odometry correlation update unchanged and β outside it). Arms: A0, M0, W0, S3, S5, S8, R3, J1 (positive control, no-harm, in-sample real) → 8 × 150 × 2 = **2,400 runs** per sensor configuration. Metrics, traces (seeds 0–4), reading rules, proposed criteria and allowed statements: identical to §3–§4. A stage 3 held-out extension follows §5 only after stage 3 on R2-A is reported.

### 9.5 What stage 3 cannot say
That sensor-v2 is physically correct (its parameters are assumption-based sensitivity levels, not hardware measurements); that results transfer to a real receiver; that F02 is resolved. The covariance mismatch that remains with real RF `s` in v2's own limited run (NEES ≈ 100 at exact initialisation) is exactly the quantity A24 addresses, so a stage 3 improvement would be attributable to the measurement-error state only if F0-v2 vs F2-v2 is the contrast; F2-v2 vs legacy rows is not.


## 10. rev2 (2026-10-10; after the fit and the implementation, before any F1/F2/F3 filter run): corrections, clarifications and the fit outcome

**Correction of an oversight in §1/§2.2 (implementation review).** The text said `R_r = σ_wr²` for F2/F3. The observation generator adds a known random range component (`range_sigma_m = 0.05 m`) on top of the noise-free chain, which is **not** in the noise-free training residual, so omitting it would have made the filter over-confident in range by construction. Corrected: **`R_r = range_sigma² + σ_wr²`** (σ_wr² = the fitted white remainder, which contains the first-path quantisation). The stored quantisation term and the 'extra' term are replaced by σ_wr², as before. For `s`, `R_s = thermal + σ_ws²` is unchanged (the thermal part is the SNR-30 chain noise, also absent from the noise-free residual). No filter result existed when this was changed.

**Clarifications of §2.2.** `ms` (used for the start values) is the un-demeaned mean square of the series; the start `φ` is the lag-1 autocorrelation of the demeaned series; the ACF in the report is that of the demeaned series (the A19 definition), the model ACF `σ_β² φ^l / (σ_β² + σ_w²)` is that of the fitted process.

**Fit outcome (`results/DRIVE_SIM_20261007/A24/A24_FIT_PARAMS.json`, input `RESIDUAL_R2A_m0.npz` sha256 `3b4e9018…959eea`, = git blob `475990b…` of the user's branch).**

| variable | variant | φ | σ_β² | σ_w² | note |
|---|---|---|---|---|---|
| s | primary | 0.9309 | 0.03158 | 1e-8 (lower bound) | at bound |
| s | acf | 0.8416 | 0.01534 | 1e-8 (lower bound) | at bound; total variance is half the series' mean square 0.0321 |
| range | primary | 0.9429 | 0.01324 | 0.001734 | σ_w ≈ the tap-quantisation scale (0.149²/12 = 0.00186) |
| range | acf | 0.8991 | 0.009663 | 0.001511 | |

Reading, fixed before any filter result: (i) the noise-free residual has no white measurement noise by construction (it is a deterministic function of the pose), so a white remainder of zero for `s` is expected and is not treated as a fit failure; the filter's white part for `s` is therefore the thermal term only; (ii) the AR(1) is a poor description of the autocorrelation (sample ACF at lags 5/10/25 = 0.48 / −0.02 / 0.00 against 0.70 / 0.49 / 0.17 for the primary `s` fit) and the stationary variance is a poor description of the amplitude (distance-bin mean squares differ by a factor of ~120, F3 profile g = 0.020 / 0.301 / 2.409 at θ_geo = 42.9° / 72.1° / 80.0°); both were listed as known limitations and are not repaired here; (iii) the fit rule, bounds and start values are unchanged. The bound (σ_w² ≥ 1e-8) is a numerical floor and is unchanged.

**Gate status after implementation (local CPU).** G-A24-2 unit tests: bit-identical output of the augmented subclass with the augmentation off (6 states, same arithmetic) on a synthetic world; a constant `s` offset is absorbed by β_s; covariance symmetric and PSD; a matched AR(1) bias is handled better by the augmented filter (unit-scale world, 10 seeds: NEES 22.0 for the stored filter with the total variance as white noise vs 2.93 for the augmented filter; a sanity check of the implementation, not an acceptance criterion); F3 profile scales the process noise; invalid configurations refused; `F0aug` is identical to the stored path through `run_unit`. G-A24-0 (A0 reproduction of the stored S6 with `--filter-variant F0aug`) and G-A24-1 (fit frozen) — the fit file is committed in the same change as this section; G-A24-0 must be run on the Snowball inputs (the local H store does not reproduce S6) and is the user's step: `REQUESTS/A24_STAGE1_RUN.md`.


## 11. rev3 (2026-10-10; stage-2 preparation, before any stage-1 or stage-2 filter result): fixed leave-one-case-out fits

The user's supplement (`codex/post-a23-evidence-20261010`, `SUPPLEMENT_01a12449/BLOCK_C`) provides the stored full H for R2-A (m0, m45), R2-B, R4-A/B and R5-A/B. The residual series were generated with the existing `structured_noise_control.py residuals` command (R2-A m0 reproduces the A23 statistics: s mean 0.0465, rms 0.1791, lag-1 0.927; range 0.0519 / 0.1232 / 0.804; corr 0.523) and the six leave-one-case-out fits of §5 were run once with the unchanged rule: `A24/LOCO/A24_FIT_PARAMS_LOCO_<held-out>_m0.json` (input hashes in `A24/LOCO/RESIDUAL_INPUT_SHA256.txt`).
Clarification of §5 fixed here: a *case* is a route-anchor pair at mount 0°; the training pool of a held-out case is the concatenation of the other **five mount-0 cases**; the mount-45 series is not in any pool (mount 45° would need its own pool and is not part of stage 2 as registered). Segments are concatenated without bridging samples. Results of the six fits: `s` φ 0.83–0.90, σ_β² 0.021–0.030, σ_w² at the 1e-8 floor in five of six (R5-B held-out: 1.1e-8); range φ 0.84–0.90, σ_β² 0.009–0.017, σ_w² 0.0015–0.0050. The fits depend only on the noise-free chain residual (platform-independent up to rare first-path tap flips); stage-2 filter runs still require the Snowball platform for the F0 reproduction gate.


## 12. Sensor-v2 `sensor_v2.py` hash difference resolved (read-only check, 2026-10-10)
Reconstructing the original `sensor_v2.py` from the `+` lines of `prior_sensor_work/.../REVIEW.patch` and comparing with the review snapshot under `02_sensor_v2_review/source/` (line endings normalised): the snapshot differs by **three added input-validation guards only** (finite check of the numeric `SensorV2Config` fields in `__post_init__`; a finite 1-D check of `t`, `ds`, `dtheta` in `generate`; a finite check of the generated parameters). No model equation, noise law, stream or default differs. The byte-level hash of the reconstruction was not compared (patch text vs file bytes), so this is a content comparison, not a hash proof. Stage-3 item 9.2/1 therefore only needs the user's decision on the commit.


## 13. rev4 (2026-10-10): approval of the consistency criteria, and how they are evaluated
The user approved, as written in §4, before any stage-1 filter result existed: pose NEES mean in [2.0, 5.0]; pose-coverage and heading-coverage in [0.90, 0.99]; NEES lower-tail mass (< 0.2158) and upper-tail mass (> 9.3484) each ≤ 0.10; the accuracy co-requisite (neither heading RMSE nor position RMSE worse than F0 with the paired interval entirely above 0); the no-harm limits on M0/W0/S5 (upper bound of the paired difference to F0 ≤ +1.0 NEES and ≤ +0.10° heading RMSE).
Evaluation rule fixed here (an implementation of the approved text, not a new criterion): an arm is *consistent* when all five band checks hold for its mean over the 50 seeds (each seed averaged over drifts 0–2); per-drift values and the bootstrap intervals are reported next to it and do not change the verdict. P1 = F2 consistent on S3, R3, J1; P2 = F2 consistent on A0; P3 = co-requisite on A0; P4 = no-harm on M0, W0, S5. The statements allowed per outcome are those of the §4 table; stage 1 still cannot close F02. Implemented in `scripts/drive_sim/a24_report.py` (`--criteria approved`, default).
