# DLP Physics R1–R5 repair reproducibility

## Fixed inputs

- Recovered reconstruction root: `DualLP_Physics_Link_Validation_RERUN_20261101`, SHA-256 for its ZIP recorded in `contracts/RUN_ADMISSION_RECORD_V2.json` provenance docs.
- `code/repair_v2.py` only reads existing `results/traces/*.npz` (132), `results/shadow/*.npz` (12), `results/tables/RECURSIVE_144_LOGICAL_SCORES.csv` (144), original archived RF/CONTROL and prior self-review evidence. Original `CONFIG_LOCK.json` unchanged.
- FFD bank hashes: +45 `b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b`; -45 `39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9`. R1–R5 repair has no new RT or FFD derivatives.

## Exact command

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
python -u code/repair_v2.py --source-root "/mnt/data/DualLP_Physics_Link_Validation_RERUN_20261101" --out "/mnt/data/DLP_PHYS_LINK_REPAIR_V2_20261102"
```

Executed twice in normal and `PYTHONOPTIMIZE=1` modes. Detailed receipts in `logs/repair_run_05_regular.log`, `logs/repair_run_04_optimized.log`. Execution does not overwrite the input package or recalculate 132 whole filters: tests consume archived states and produce actual one-step updates and new QA reports.

### Fail-closed contract

1. Exact expected ID matrix: 5,288 required IDs; missing, extra or duplicate ID is `BLOCKED`.
2. Each actual measurement error is tested against a fixed code tolerance. Any error beyond tolerance is `FAIL`, rather than treating a previously published PASS flag as a result.
3. In the mutation harness, intended negative outcomes are `FAIL/BLOCKED`. A successful mutation-test status means the harness correctly rejected the corrupted sample, not that the corrupted sample passed.
4. Failed development runs are preserved. Scientific verdict remains MIXED.

## Original data versus repaired results

This repair is **not** the missing original SHA `1550335002367c656939bab4876675c612f0915c` and not a recreated pre-run independent audit. The source reconstructed package is independently identified by full hashes. New repair scripts and tables go under the separate R1–R5 folder and do not modify historical files.
