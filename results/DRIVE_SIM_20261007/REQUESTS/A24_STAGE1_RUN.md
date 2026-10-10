# A24 stage 1 — run instructions (for the user; CPU, minutes)

Prerequisites: this branch at the commit that contains `filters_aug.py` and `A24/A24_FIT_PARAMS.json`; the same inputs as the A23 execution (H store R2-A m0, LUT, LUT meta, frequency axis, S6 CSV `results_R2_aA_m0.csv`, S1 timelines). The same launcher/wrapper as in A23 is fine (the code-revision identification is by source hash). Output directories must be new. Use `/opt/rt-env/bin/python` on Snowball as in A23. `COMMON` below is the argument block of the A23 `check-a0` call (`--s1 … --h-dir … --lut … --lut-meta … --bank-freqs … --cases R2A --mounts 0 --drifts 0 1 2 --seeds 50 --seed0 0 --nproc 4`).

## Step 1 — gate G-A24-0 (blocking)
```
structured_noise_control.py check-a0 COMMON --filter-variant F0aug --s6-csv <results_R2_aA_m0.csv> --trace-seeds 0 1 2 3 4 --out OUT_A24/GATE
```
Required: `inference_valid = true` (150 keys; heading RMSE, position RMSE and NEES within 1e-9 of the stored S6). Failure stops everything; report `A0_CHECK.json`. (A new check is required because `filters.py` gained the `meas_state` field and `filters_aug.py` is part of the fingerprint.) Optionally also run `--filter-variant F0` once to show that the stored path is unchanged by the additive edit.

## Step 2 — F1, F2, F3 (each needs the F0aug A0 check in the same `--out` directory)
```
structured_noise_control.py run COMMON --filter-variant F2 --fit-params A24/A24_FIT_PARAMS.json --arms all --label F2 --trace-seeds 0 1 2 3 4 --out OUT_A24/GATE
structured_noise_control.py run COMMON --filter-variant F1 --fit-params A24/A24_FIT_PARAMS.json --arms all --label F1 --trace-seeds 0 1 2 3 4 --out OUT_A24/GATE
structured_noise_control.py run COMMON --filter-variant F3 --fit-params A24/A24_FIT_PARAMS.json --arms all --label F3 --trace-seeds 0 1 2 3 4 --out OUT_A24/GATE
```
`--arms all` = 22 arms × 150 = 3,300 runs per variant (A0 is included for F1–F3). Primary variant F2; F1 and F3 are secondary. The ACF sensitivity (`--fit-variant acf_variant`) is a separate run of F2 (and F1) with a different label; run it after the primary ones.
Expected duration: the A23 1,650 runs took about two minutes on 4 workers.

## Step 3 — what to send back (same package structure as A23)
`ARMS_<label>.csv`, `ARM_UNIT_STATS_<label>.csv` (now with `variant`, `beta_*` columns), `RUN_MANIFEST_<label>.json` (variant, fit hash, applied parameters), `A0_CHECK.json`, `TRACES/` (seeds 0–4: now with `beta_hat`, `beta_var`, `beta_cross`), the stored S6 rows for the A0 key set including the `odom_imu` and range-only baselines (for the "does `s` still help" comparison), logs with exit codes.

## Not part of this step
The reading of the results (no PASS/FAIL until the criteria are approved), the held-out stage 2 and the sensor-v2 stage 3.
