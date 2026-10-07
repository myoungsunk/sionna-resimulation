# DRIVE_SIM — how to run the RF part on Snowball and finish locally

Simulation only; placeholder sensor parameters (see `S0/PREREG.json`, `S0/PREREG_AMENDMENTS.md`). `s` is not q_clean.

## 0. Environment (once)

```bash
python3 -m venv venv && . venv/bin/activate
pip install sionna-rt==2.0.1 mitsuba==3.8.0 drjit==1.3.1 numpy scipy pandas scikit-learn pytest
git lfs pull --include "LP_plus45_bank.npz,LP_minus45_bank.npz"      # two banks, ~248 MB each; the SHA256 check against BANK_MANIFEST.json is automatic
pytest -q tests/test_drivesim_*.py tests/test_fp_single_tx.py tests/test_corridor_setup.py        # 67+ tests, no GPU
export PYTHON=$(which python)
```
LLVM (`libLLVM.so`) must be installed for the `llvm_ad_mono_polarized` variant. All RF jobs are single-thread processes (bit-reproducible, S0 A1);
`NPROC` (default 4) processes run in parallel. Every stage is resumable: if a job is stopped, run the same command again.

## 1. RF stages (`scripts/drive_sim/run_rf_snowball.sh`)

| order | command | what | needs Sionna | rough time (4 cores) |
|---|---|---|---|---|
| 1 | `bash scripts/drive_sim/run_rf_snowball.sh traj` | S1 trajectories, pose sets, task lists (already committed in `S1/`) | no | seconds |
| 2 | `bash scripts/drive_sim/run_rf_snowball.sh parity` | G2/G2'/G4 inputs: bin-by-bin and 17-node traces at the 44 stored reference positions, method-A runs at out-of-range yaws | yes | ~0.5 h |
| 3 | `bash scripts/drive_sim/run_rf_snowball.sh parity-report` | `S2/PARITY_REPORT.json` (thresholds from `S0/PREREG.json`) | no | minutes |
| 4 | `bash scripts/drive_sim/run_rf_snowball.sh trace` | production traces (17 nodes) at all ~1,750 positions of both laterals | yes | ~1.5-2 h |
| 5 | `bash scripts/drive_sim/run_rf_snowball.sh continuity` | gate G3 (`S2/G3_continuity_y*.json`) | no | seconds |
| 6 | `bash scripts/drive_sim/run_rf_snowball.sh apply` | `S2/H_y{0,0.35}_m{0,45}.npy` (4 H stores, ~100 MB each) | no (needs banks) | minutes |

**Decision rule (pre-registered).** Use method B (stages 4-6) only if stage 3 reports `all_passed: true` and stage 5 `passed: true`. Otherwise run method A
(`scripts/drive_sim/rf_a_runner.py --tasks S1/rf_tasks_y<y>_m<m>.json --out <dir> --shard i/4`, about 14 h wall for all four combinations on 4 cores) and tell me;
the H store would then be assembled from the A outputs.

Do **not** commit `*.npz` traces (Git LFS upload is unavailable in the cloud session; they are git-ignored).

## 2. Finishing steps (numpy only, minutes to ~2 h)

```bash
D=results/DRIVE_SIM_20261007
python scripts/drive_sim/build_hs_lut.py --out $D/S4                                      # ~7 min; gate L1 is reported (see PREREG_AMENDMENTS A6)
python scripts/drive_sim/lut_los_check.py --lut $D/S4/hs_lut_2deg.npy --out $D/S4/LUT_LOS_CHECK.json   # gate L2, needs Sionna (~5 min)
python scripts/drive_sim/lut_mismatch.py --s1 $D/S1 --h-dir $D/S2 --lut $D/S4/hs_lut_2deg.npy --out $D/S4/LUT_MISMATCH.json
python scripts/drive_sim/snr_calibration.py --s1 $D/S1 --h-dir $D/S2 --out $D/S3/SNR_CALIBRATION.json --snr-db 60 50 40 30 20 10
# The SNR levels (30, 10 dB), mismatch sigma (0.18) and pos_process_std (0.01) are already fixed in S0/PREREG_AMENDMENTS.md A7. Check that your
# SNR_CALIBRATION.json / LUT_MISMATCH.json reproduce the development values in DEV_RESULTS/ (they should: same inputs). Then:
python scripts/drive_sim/run_experiments.py --s1 $D/S1 --h-dir $D/S2 --lut $D/S4/hs_lut_2deg.npy --out $D/S6 \
    --snr-db 30 10 --mismatch-sigma 0.18 --pos-process-std 0.01 --seeds 50 --nproc 4      # constants fixed in PREREG_AMENDMENTS A7 (from the local development run)
python scripts/drive_sim/analyze_experiments.py --results $D/S6 --out $D/S6/ANALYSIS
```

`run_experiments.py` smoke test: add `--seeds 2 --drifts 0 --max-samples 400 --no-compare-filters`.

## 3. What to send back

`S2/PARITY_REPORT.json`, `S2/G3_continuity_*.json`, `S2/traces_*/*_trace_receipt.json` (receipts only, not the npz), `S4/*.json`, `S3/SNR_CALIBRATION.json`,
`S6/results_*.csv`, `S6/manifest_*.json`, `S6/ANALYSIS/*`.

## 4. Development run (this repo, `DEV_RESULTS/`)

All RF stages were run once locally (4 cores) to validate the code before Snowball; those files are in `DEV_RESULTS/` and are **not** production evidence.
`PARITY_REPORT.json` there already shows G2, G2' and G4 passing on 817 + 18 poses (median H error 1.5e-5, max 5.4e-5, |Δs| ≤ 1.7e-5, first-path index 100 % equal);
the stored position (4.0, 0.0) is excluded (anchor axis, A3). Your Snowball run should reproduce these numbers.

## 5. Added routes R2 / R4 / R5 and the second anchor B (PREREG_AMENDMENTS A9)

Routes (20 m corridor): R2 rectangle loop, R4 zigzag (±0.45 m, ±35.7°), R5 serpentine over lanes +0.45 / 0 / −0.45 m. R3 is the old straight run (R1). Anchors: A (x = 4 m, the original) and B (x = 10 m); each is a separate single-anchor system.

```bash
export PYTHON=$(which python); D=results/DRIVE_SIM_20261007
bash scripts/drive_sim/run_rf_snowball.sh routes-traj            # timelines/poses/tasks, already committed in S1/routes (seconds)
bash scripts/drive_sim/run_rf_snowball.sh routes-parity          # anchor-B check: method A vs method B at 5 positions x 7 yaws (~0.3 h)
bash scripts/drive_sim/run_rf_snowball.sh routes-parity-report   # S2/anchorB/PARITY_REPORT_ANCHOR_B.json (G2' thresholds from PREREG)
bash scripts/drive_sim/run_rf_snowball.sh routes-trace           # 3 routes x 2 anchors, 17-node traces, ~5,600 positions (~1-1.5 h on 4 cores)
bash scripts/drive_sim/run_rf_snowball.sh routes-continuity      # G3 per route and anchor
bash scripts/drive_sim/run_rf_snowball.sh routes-apply           # 12 H stores H_<route>_a<anchor>_m<mount>.npy
python scripts/drive_sim/lut_mismatch_routes.py --s1-routes $D/S1/routes --h-dir $D/S2 --lut $D/S4/hs_lut_2deg.npy --out $D/S4/LUT_MISMATCH_ROUTES.json
# fix --mismatch-sigma from LUT_MISMATCH_ROUTES.json (overall.rms) and write it into PREREG_AMENDMENTS (A10) BEFORE the next command
python scripts/drive_sim/run_route_experiments.py --s1-routes $D/S1/routes --h-dir $D/S2 --lut $D/S4/hs_lut_2deg.npy --out $D/S6_routes \
    --snr-db 30 10 --mismatch-sigma <rms> --pos-process-std 0.01 --seeds 50 --nproc 4
python scripts/drive_sim/analyze_route_experiments.py --results $D/S6_routes --out $D/S6_routes/ANALYSIS
```
Apply the same decision rule as v1 (method B only if the parity gate passes; G3 is reported at 5e-14 s and 2e-13 s; the relaxation needs a decision).

**Anchor B and the vanishing path (A10/A10b/A10c).** For anchor B the solver drops one path (about −45 dB to −30 dB) above ≈ bin 146–150 at every position. `rf_b_trace.py` handles it: the cut bin is found by bisection (4 extra solver calls), the path is interpolated piecewise and is exactly zero above the cut; `dropped_audit` / `screen_exceeded` are written to every trace receipt. `routes-parity-report` must show `all_passed: true` (developer run: |Δs| max 1.2e-5, H error max 5.9e-5, 35 poses); if it does not, run method A for anchor B (`rf_a_runner.py ... --anchor-x 10`, about 105 core-hours for all routes and both mounts).
