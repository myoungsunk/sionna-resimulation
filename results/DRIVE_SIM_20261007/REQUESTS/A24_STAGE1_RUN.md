# A24 stage 1 — run instructions (for the user; CPU, minutes)

Prerequisites: this branch at the commit that contains `filters_aug.py` and `A24/A24_FIT_PARAMS.json`; the same inputs as the A23 execution (H store R2-A m0, LUT, LUT meta, frequency axis, S6 CSV `results_R2_aA_m0.csv`, S1 timelines). The same launcher/wrapper as in A23 is fine (the code-revision identification is by source hash). Output directories must be new. Use `/opt/rt-env/bin/python` on Snowball as in A23. `COMMON` below is the argument block of the A23 `check-a0` call (`--s1 … --h-dir … --lut … --lut-meta … --bank-freqs … --cases R2A --mounts 0 --drifts 0 1 2 --seeds 50 --seed0 0 --nproc 4`).

## Commands (explicit; paths as in the A23 execution, `EXECUTION.json`; adjust only the checkout path and the new `--out`)
Shell variables used below:
```
SCRIPT=<checkout of claude/cool-dijkstra-hnznhm at the commit named in "Prerequisites">/scripts/drive_sim/structured_noise_control.py
PY=/opt/rt-env/bin/python
COMMON="--s1 /routes/source/results/DRIVE_SIM_20261007/S1 \
  --h-dir /routes/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S2 \
  --lut /legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_2deg.npy \
  --lut-meta /legacy/source/results/DRIVE_SIM_20261007/S4/hs_lut_meta.json \
  --bank-freqs /job/freqs_hz.npy --cases R2A --mounts 0 --drifts 0 1 2 --seeds 50 --seed0 0 --nproc 4 --trace-seeds 0 1 2 3 4"
S6=/routes/source/results/DRIVE_SIM_20261007/SNOWBALL_ROUTES_01a11669/S6_routes/results_R2_aA_m0.csv
FIT=<checkout>/results/DRIVE_SIM_20261007/A24/A24_FIT_PARAMS.json
OUT=<new empty directory>
```
(`/job/launch.py` of A23 only supplied git metadata because the container has no git; the same wrapper may be used, with `main()` of this script.)

## Step 1 — gate G-A24-0 (blocking)
```
$PY $SCRIPT check-a0 $COMMON --filter-variant F0aug --s6-csv $S6 --out $OUT
```
Required: `A0_CHECK.json` with `inference_valid = true` (150 keys, heading RMSE / position RMSE / NEES within 1e-9 of the stored S6, `filter_variant = F0aug`). On failure stop and send `A0_CHECK.json`. A new check is needed because `filters.py` gained the `meas_state` field and `filters_aug.py` is part of the fingerprint. Optional: the same command with `--filter-variant F0 --out $OUT_F0` to show the stored path is unchanged (on the assistant's CPU environment F0 and F0aug are bit-identical, but that environment does not reproduce S6 at 1e-9; see `DEV_RESULTS/A24_LOCAL_PLATFORM_CHECK/README.md`).

## Step 2 — F2 (primary), F1, F3, then the ACF sensitivity (all into the same `$OUT`, which holds the F0aug `A0_CHECK.json`)
```
$PY $SCRIPT run $COMMON --filter-variant F2 --fit-params $FIT --arms all --label F2 --out $OUT
$PY $SCRIPT run $COMMON --filter-variant F1 --fit-params $FIT --arms all --label F1 --out $OUT
$PY $SCRIPT run $COMMON --filter-variant F3 --fit-params $FIT --arms all --label F3 --out $OUT
$PY $SCRIPT run $COMMON --filter-variant F2 --fit-params $FIT --fit-variant acf_variant --arms all --label F2acf --out $OUT
$PY $SCRIPT run $COMMON --filter-variant F1 --fit-params $FIT --fit-variant acf_variant --arms all --label F1acf --out $OUT
```
`--arms all` = 22 arms x 150 = 3,300 runs per label (A0 included for F1–F3). Run F2 first and send its package if time is short. Note: the five labels write traces with the same file names (`TRACES/<case>_m0_<arm>_s<seed>_d<drift>.npz`); use a **separate `--out` per label** for the traces (copy `A0_CHECK.json` and `RUN_MANIFEST_check-a0.json` into each) or pass `--trace-seeds` only for F2 and F1 and run the others without it.
Smoke test done on the assistant's machine (not a result, 3 seeds x 4 arms, not stored): the F2 run completes, writes `variant` and `beta_*` columns and the traces with `beta_hat`/`beta_var`/`beta_cross`.

## Step 3 — what to send back (same package structure as A23)
`ARMS_<label>.csv`, `ARM_UNIT_STATS_<label>.csv` (now with `variant`, `beta_*` columns), `RUN_MANIFEST_<label>.json` (variant, fit hash, applied parameters), `A0_CHECK.json`, `TRACES/` (seeds 0–4: now with `beta_hat`, `beta_var`, `beta_cross`), the stored S6 rows for the A0 key set including the `odom_imu` and range-only baselines (for the "does `s` still help" comparison), logs with exit codes.

## Not part of this step
The reading of the results (criteria approved; verdicts by `a24_report.py`), the held-out stage 2 and the sensor-v2 stage 3.


## Reading the package (assistant side, once the package is on a branch)
```
python scripts/drive_sim/a24_report.py --f0 <A23>/A0_ARMS.csv <A23>/ARMS_controls.csv <A23>/ARMS_q1.csv <A23>/ARMS_q2.csv <A23>/ARMS_joint.csv \
    --variant F2=OUT/ARMS_F2.csv F1=OUT/ARMS_F1.csv F3=OUT/ARMS_F3.csv --out OUT_REPORT/A24_STAGE1.json
```
Writes per-arm tables and seed-paired variant-minus-F0 contrasts (pairing on common drifts and seeds). The consistency criteria were approved on 2026-10-10 (A24 rev4); the JSON carries the P1–P4 verdicts. F0 rows are the A23 rows, so the F0 reference and the new variants must come from the same platform (Snowball).
