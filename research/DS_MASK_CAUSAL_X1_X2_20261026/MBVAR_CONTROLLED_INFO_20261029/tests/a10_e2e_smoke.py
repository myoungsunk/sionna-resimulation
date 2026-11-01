"""A010 S1V5 -> C3V5 reduced SMOKE end-to-end driver (TECHNICAL QA ONLY; not evidence, not a freeze).

Runs the real s1v5 / c3v5 entry points (cmd_run, cmd_aggregate) on SMOKE fields 900/901 only, with a reduced
cell set and one sensor seed. The contract lock is extended IN MEMORY ONLY:
  - "AMENDMENT-010" appended to applied_amendment_locks (the committed AMENDMENT-010.md stays DRAFT),
  - run_plan["S1V5"] / run_plan["C3V5"] = SMOKE fields 900/901,
  - code_sha256 = hashes of the checked-out tree (so the real M.check_code_lock runs instead of being bypassed).
No D1/D2 workaround is installed: lock_v4 is not aliased and load_receipts is not replaced.
Never DEV3 (20-29), HOLDOUT2 (5000-5059), reserve (5060-5119) or RT; RUN_REQUEST.json is only read.

  python a10_e2e_smoke.py s1run  --work W --field 900
  python a10_e2e_smoke.py s1agg  --work W
  python a10_e2e_smoke.py c3run  --work W --field 900 --group LH [--cells POSE_HIGH]
  python a10_e2e_smoke.py c3agg  --work W
(env REFLECT_ROOT = fetched inputs, FETCH_RF=0)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

EXP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXP / "code"))

SPLIT = "SMOKE"
SMOKE_FIELDS = (900, 901)
S1_CELLS = ("POSE_HIGH", "TIME_HIGH_5")        # POSE_HIGH exercises the canonical Lhalf factor; TIME_HIGH_5 the time kernel
SENSOR_SEEDS = (0,)
C3_PLAN = ((900, "LH", ("POSE_HIGH",)), (901, "RV", ("POSE_HIGH",)))   # both fields, both groups, every C3V5 arm incl. XMODEL
S0V2_REF = "results/P1_S0V2_run_40863614683"
RESERVED = [range(20, 30), range(5000, 5060), range(5060, 5120)]      # DEV3, HOLDOUT2, reserve: never touched


def _guard_fields(fields):
    for f in fields:
        if f not in SMOKE_FIELDS or any(f in r for r in RESERVED):
            raise SystemExit(f"ERR_E2E_FIELD_SCOPE {f}: SMOKE 900/901 only")


def install(cells=S1_CELLS):
    """Import the real modules with the in-memory lock extension; returns (T=s1v5, C=c3v5, lk)."""
    os.environ.setdefault("MBVAR_GOVERNANCE_SHA", json.loads((EXP / "RUN_REQUEST.json").read_text())["governance_git_sha"])
    import manifest as MF
    import s0v2 as S0V2
    import s1_mc as M
    import s1v3 as B3
    base = S0V2.lock_v2()                                   # committed, frozen effective lock (read only)
    lk = json.loads(json.dumps(base))
    if "AMENDMENT-010" in lk["applied_amendment_locks"]:
        raise SystemExit("ERR_E2E: AMENDMENT-010 is already applied on disk; this driver is for the DRAFT stage only")
    if not set(SMOKE_FIELDS) <= set(lk["splits"]["S_field"][SPLIT]):
        raise SystemExit("ERR_E2E: SMOKE split does not contain 900/901")
    lk["applied_amendment_locks"].append("AMENDMENT-010")   # IN MEMORY ONLY
    lk["run_plan"]["S1V5"] = dict(fields=list(SMOKE_FIELDS), split=SPLIT, sensor_seeds=list(SENSOR_SEEDS), cells_subset=list(cells),
                                  note="IN-MEMORY technical smoke plan; not a frozen run_plan")
    lk["run_plan"]["C3V5"] = dict(fields=list(SMOKE_FIELDS), split=SPLIT, note="IN-MEMORY technical smoke plan")
    lk["code_sha256"] = MF.code_hashes()                    # IN MEMORY: lock = this tree, so check_code_lock really executes
    B3.lock_v3 = lambda: lk
    M.SENSOR_SEEDS = SENSOR_SEEDS
    import s1v5 as T
    import c3v5 as C
    orig = T.canonical_setup

    def subset_setup(lk_):
        S = orig(lk_)
        missing = [c for c in cells if c not in S["cells"]]
        if missing:
            raise SystemExit(f"ERR_E2E_CELLS {missing}")
        S["cells"] = {c: S["cells"][c] for c in cells}
        return S
    T.canonical_setup = subset_setup
    T.requested_fields = lambda: list(SMOKE_FIELDS)        # RUN_REQUEST.json is never modified
    C.SPLIT = SPLIT
    return T, C, lk


def expected_s1_rows(cells=S1_CELLS, n_fields=len(SMOKE_FIELDS), n_seeds=len(SENSOR_SEEDS)):
    """Independent row count for the reduced S1V5 run (LOW/HIGH: 5 arms; REV60/FWD60: 2 arms + XMODEL where defined)."""
    import s0v2 as S0V2
    import s1v2 as V
    lh = sum(2 * len(V.LH_ARMS) for c in cells if c in V.LH_CELLS)
    rv = sum(2 * (2 + (c in S0V2.XMODEL)) for c in cells if c in S0V2.REV_CELLS)
    return n_fields * n_seeds * (lh + rv)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["s1run", "s1agg", "c3run", "c3agg"])
    ap.add_argument("--work", required=True); ap.add_argument("--field", type=int); ap.add_argument("--group")
    ap.add_argument("--cells", default=",".join(S1_CELLS))
    a = ap.parse_args(argv)
    work = Path(a.work).resolve(); cells = tuple(c for c in a.cells.split(",") if c)
    if a.field is not None:
        _guard_fields([a.field])
    T, C, _ = install(cells)
    os.environ["S0V2_RESULTS_DIR"] = str(EXP / S0V2_REF)
    os.environ["S1V5_RUN"] = str(work / "s1agg")             # absolute: Wd.EXP / "results" / <abs> == <abs>
    if a.step == "s1run":
        return T.cmd_run([a.field], SPLIT, work / "s1sh" / str(a.field))
    if a.step == "s1agg":
        return T.cmd_aggregate(str(work / "s1sh"), SPLIT, work / "s1agg")
    if a.step == "c3run":
        return C.cmd_run(a.field, a.group, work / "c3sh" / f"{a.field}{a.group}")
    return C.cmd_aggregate(str(work / "c3sh"), work / "c3agg")


if __name__ == "__main__":
    raise SystemExit(main())
