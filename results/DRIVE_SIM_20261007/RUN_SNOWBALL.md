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
# choose the two SNR levels from SNR_CALIBRATION.json and the mismatch sigma from LUT_MISMATCH.json (overall.rms) BEFORE the next command;
# write both values into S0/PREREG_AMENDMENTS.md (A7) and commit, then:
python scripts/drive_sim/run_experiments.py --s1 $D/S1 --h-dir $D/S2 --lut $D/S4/hs_lut_2deg.npy --out $D/S6 \
    --snr-db <high> <low> --mismatch-sigma <rms> --seeds 50 --nproc 4
python scripts/drive_sim/analyze_experiments.py --results $D/S6 --out $D/S6/ANALYSIS
```

`run_experiments.py` smoke test: add `--seeds 2 --drifts 0 --max-samples 400 --no-compare-filters`.

## 3. What to send back

`S2/PARITY_REPORT.json`, `S2/G3_continuity_*.json`, `S2/traces_*/*_trace_receipt.json` (receipts only, not the npz), `S4/*.json`, `S3/SNR_CALIBRATION.json`,
`S6/results_*.csv`, `S6/manifest_*.json`, `S6/ANALYSIS/*`.
