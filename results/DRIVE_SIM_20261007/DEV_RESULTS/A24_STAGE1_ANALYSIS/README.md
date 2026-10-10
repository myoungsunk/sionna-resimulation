# A24 stage 1 — analysis of the user's execution (branch `codex/post-a23-evidence-20261010`, commit `047cce2`)

Inputs: `A24_STAGE1_RESULTS_20261010_01a12477/` (gate `OUTPUT_GATE/`, F2/F1/F3/F2acf/F1acf, 3,300 runs each, seeds 0–49 × drifts 0–2, 22 arms, traces seeds 0–4), A23 rows as F0. Frozen source and fit in that package equal the committed code after line-ending normalisation (sha256 of filters_aug.py, filters.py, experiment.py, structured_noise_control.py, A24_FIT_PARAMS.json, hs_lut.py, sensors.py, observation.py all match). Gate: F0aug reproduces S6 on 150 keys (max diff 2.8e-14), so the F0 (A23) vs F1–F3 pairing is on one platform.
Verdicts below are computed by `scripts/drive_sim/a24_report.py` with the criteria approved on 2026-10-10 (A24 rev4); full numbers in `A24_STAGE1.json` / `.md`.

## Verdicts (approved criteria, arm mean over 50 seeds, each averaged over drifts)
| | F2 (primary) | F1 | F3 | F2acf | F1acf |
|---|---|---|---|---|---|
| P1 positive control (S3, R3, J1 consistent) | no, no, no | no | no | no | no |
| P2 A0 consistent | no | no | no | no | no |
| P3 accuracy not worse than F0 on A0 | yes | yes | yes | yes | yes |
| P4 no-harm (M0, W0, S5) | no, no, no | no | no | no | no |

Per the pre-registered reading, **P1 fails**: no statement about the multipath mechanism or mitigation is allowed; the augmented filter is to be diagnosed first. F01/F02/`scientific_PASS=false` stay open.

## Key numbers (mean over seeds; NEES / pose coverage / heading RMSE °) — see `ARM_TABLE.md`
F2 vs F0: A0 40.3 vs 106.5 NEES, heading 7.56 vs 10.51 °, position RMSE 0.919 vs 0.927 m; S3 15.7 vs 209.0; J1 16.1 vs 240.1; the white-error arms get worse: M0 13.4 vs 2.3, W0 16.7 vs 5.0, S5 9.5 vs 3.8 (paired F2−F0: M0 +11.0 NEES [+7.9, +15.3], heading +2.35° [+2.06, +2.66]). F3 (distance profile) is much worse: A0 NEES 8,140. s-gate rejection of F2 on M0: 34 % vs 1 % for F0.
Descriptive only: F2 is closer to consistency than F0 on the structured-error arms and A0, and farther on the white arms; it is within the approved bands on none of S3, R3, J1, A0.

## Diagnosis of the P1 failure (post-hoc, exploratory, assistant's CPU; `scripts/drive_sim/a24_p1_diagnosis.py`, outputs `P1_DIAG_*.csv`)
1. **Not a model-mismatch of the positive-control arms.** In worlds generated exactly by the F2 model (zero-mean AR(1) β_s, β_r with the fitted φ, σ_β², plus the white parts; route R2-A, 20 seeds × 3 drifts) F2 still gives NEES 12.5, pose coverage 0.68, heading coverage 0.79 (`matched@1`), while the innovations are consistent (NIS_s 0.96, NIS_r 0.92, lag-1 of normalised s innovations ≈ 0.09). F0 in the same world: NEES 253.
2. **The inconsistency is a state-level effect concentrated within 5 m of the anchor.** NEES by distance in `matched@1`: <5 m 22.1, 5–10 m 8.0, >10 m 8.5; with the error scaled down (`matched@0.03`: σ_s ≈ 0.03 of the fitted scale) the near-field NEES rises to 19,690 (two runs > 1e4; median 7.9) while the far-field stays 4.7–5.2. Position NEES dominates (e.g. 13.4 of 15.9 in the S3 traces; heading part 3.1 vs 1 expected).
3. **Mechanism seen in the worst run (seed 16, drift 1, `matched@0.03`)**: the estimate carries a 0.52 m y-error for several seconds while the filter's σ_y is 1–2 cm (min eigenvalue of the pose covariance 6e-10 at the worst sample), under the anchor (ρ ≈ 0.5 m, θ_geo ≈ 14°). The s measurement model has a very large position gradient and an azimuth degeneracy there (the polar-singularity issue already found for the LUT); a small white noise lets the EKF commit to a wrong point with a collapsed covariance. This is consistent with F3 (s trusted most in the near field) failing worst. It is an observation of a mechanism in a few runs, not a proof; the median near-field NEES is also ≈ 2–3× the expected value.
4. P4 failure is the expected cost of the model: with σ_w² at the floor the filter treats white noise (σ 0.16) as a smooth process, rejects 34 % of the s updates on M0 and absorbs noise into β.
5. Not tested here: whether an IEKF/sigma-point `s` update, an s-gate near the anchor (θ_geo small), or a covariance floor removes the near-field collapse; each is a new model change that needs its own pre-registration (A25) and must not be tuned on these results.

## Addendum — was the run or the filter wrong? (post-hoc checks, assistant's CPU; scripts `a24_p1_deep.py`, `a24_p1_linear.py`, `a24_p1_iekf.py`)
- **Execution**: frozen sources equal the committed code, the F0aug gate reproduces S6 (2.8e-14), 16,500 runs with no missing/duplicate/failed rows; nothing found wrong in the run.
- **Augmented-filter algebra**: with the LUT replaced by a *linear* measurement function (everything else unchanged: R2-A route, sensors, odometry, gates, F2, AR(1) β drawn exactly as assumed; 30 seeds × 3 drifts) F2 is consistent: pose NEES 3.29 (pos 2.55 / heading 1.37 vs 2 / 1), β_s z-score sd 0.89.
- **With the real nonlinear `s` model and exactly matched data** the same filter is not: by θ_geo, NEES mean/median 114/9.1 (<15°), 30/8.6 (15–25°), 21.7/7.8 (25–40°), 12.6/5.9 (40–60°), 8.3/3.5 (60–90°); heading part ≈ 3 (expected 1) even at 60–90°; β_s z-score sd 1.1–3.1. Excluding θ_geo < 25° the mean is 9.8 (median 4.0). So the inconsistency is not only the few near-anchor collapses.
- **Iterating the s update does not repair it**: 1 iteration reproduces the 12.46 above (check), 4 iterations give mean 43.7 (heading part 21, β z-sd 4.4). The simple "linearisation error" explanation is therefore not supported; the sign-ambiguous, non-injective dependence of `s` on heading (s = −cos 2·yaw) makes the posterior multi-modal, which a single Gaussian cannot represent. This is an inference from these runs, not a demonstrated cause.
- **Process note**: the unit-scale world used before the run (NEES 2.93) was easier than the route world; an exactly-matched route-world run with the real LUT, done before the Snowball run, would have shown P1 failing.

## Addendum 2 — the inconsistency depends on the antenna mount (same route, same filter, same exactly-matched error world; `A24_MOUNT=0|45 a24_p1_deep.py`)
| θ_geo bin | mount 0°: NEES mean / median, heading part, β z-sd | mount 45°: NEES mean / median, heading part, β z-sd |
|---|---|---|
| 60–90° (36,420 samples) | 8.27 / 3.48, 3.01, 1.83 | **3.30 / 2.12, 1.06, 1.12** |
| 40–60° | 12.6 / 5.9, 3.08, 3.09 | 6.9 / 2.5, 1.61, 0.96 |
| 25–40° | 21.7 / 7.8, 3.95, 2.95 | 9.1 / 3.0, 1.98, 0.98 |
| 15–25° | 30.0 / 8.6, 4.27, 1.30 | 12.3 / 3.2, 1.98, 1.15 |
| <15° | 114 / 9.1, 4.38, 1.14 | 46.7 / 3.2, 1.94, 1.22 |
Excluding θ_geo < 25°: mean 9.82 (mount 0°) vs 4.25 (mount 45°). With mount 45° the augmented filter is nearly consistent away from the anchor; the residual inflation is concentrated within ~25° of vertical. Reading: with mount 0° and the robot heading ≈ 0°/180° on the two lanes the antenna yaw sits at the extremum of s = −cos 2(ψ+mount+180°) (slope zero), where s depends on the heading quadratically and a smooth bias of 0.1 corresponds to a heading change of ≈ 0.22 rad (≈ 13°) with either sign; mount 45° puts the same lanes at the steepest slope. This is an inference supported by the mount comparison, not a separate proof. Stage 1 as registered used mount 0° only.
