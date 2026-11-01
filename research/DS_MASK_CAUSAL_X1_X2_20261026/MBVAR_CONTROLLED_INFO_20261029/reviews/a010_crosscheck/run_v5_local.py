"""Local SMOKE-only technical cross-check of the S1V5/C3V5 draft (in-memory lock; NOT evidence, NOT a freeze).

Fields 900/901 (SMOKE split) only. Never DEV3 (20-29), HOLDOUT2 or RT.
usage: python run_v5.py <step> [args]   (cwd = EXP of the a010smoke worktree)
  probe_nameerror           show that unpatched s1v5.cmd_run fails
  s1 <field>                S1V5 run (with local lock_v4 alias workaround)
  s1agg                     S1V5 aggregate
  c3 <field> <group> [dup]  C3V5 run; 'dup' = allow byte-identical duplicate keys (local workaround)
  c3agg
"""
import os
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, "code")
import numpy as np  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import s1v3 as B3  # noqa: E402

OUT = Path("/home/claude/a10test2")
os.environ.setdefault("MBVAR_GOVERNANCE_SHA", "e16e98dc0000000000000000000000000000000")
lk = S0V2.lock_v2()
lk["applied_amendment_locks"] = lk["applied_amendment_locks"] + ["AMENDMENT-010"]   # IN-MEMORY ONLY
lk["run_plan"]["S1V5"] = dict(lk["run_plan"]["S1V4"], fields=[900, 901])
lk["run_plan"]["C3V5"] = dict(fields=[900, 901])
B3.lock_v3 = lambda: lk
M.check_code_lock = lambda _lk: None
import s1v5 as T  # noqa: E402

step = sys.argv[1]
t0 = time.time()
if step == "probe_nameerror":
    try:
        T.cmd_run([900], "SMOKE", OUT / "probe")
        print("NO ERROR")
    except Exception as ex:  # noqa: BLE001
        print("UNPATCHED cmd_run ->", type(ex).__name__, ex)
        traceback.print_exc(limit=2)
    try:
        T.cmd_aggregate(str(OUT / "probe"), "SMOKE", OUT / "probe_agg")
    except Exception as ex:  # noqa: BLE001
        print("UNPATCHED cmd_aggregate ->", type(ex).__name__, ex)
    sys.exit(0)

T.lock_v4 = T.lock_v5          # LOCAL WORKAROUND for the NameError (defect D1)
T.requested_fields = lambda: [900, 901]
if step == "s1":
    f = int(sys.argv[2])
    print("rc", T.cmd_run([f], "SMOKE", OUT / "s1sh" / str(f)), "sec", round(time.time() - t0))
elif step == "s1agg":
    os.environ["S0V2_RESULTS_DIR"] = str(Path.cwd() / "results/P1_S0V2_run_40863614683")
    print("rc", T.cmd_aggregate(str(OUT / "s1sh"), "SMOKE", OUT / "s1agg"))
elif step in ("c3", "c3agg"):
    import c3v5 as C
    C.SPLIT = "SMOKE"
    os.environ["S1V5_RUN"] = str(OUT / "s1agg")
    if step == "c3":
        f, g = int(sys.argv[2]), sys.argv[3]
        if len(sys.argv) > 4 and sys.argv[4] == "dup":
            orig_load = np.load

            def load_receipts(d):
                import json
                man = json.loads((d / "MANIFEST.json").read_text()); hashes = man["output_sha256"]; rec = {}; ndup = 0; nconf = 0
                for z in sorted(d.glob("S1V5_INPUTS_SMOKE_*.zip")):
                    assert C.CAN.sha_file(z) == hashes[z.name]
                    with orig_load(z, allow_pickle=False) as a:
                        for k in a.files:
                            if k in rec:
                                ndup += 1
                                if not np.array_equal(rec[k], a[k]):
                                    nconf += 1
                                continue
                            rec[k] = a[k]
                print("LOCAL dup-tolerant loader: duplicate keys", ndup, "conflicting", nconf, flush=True)
                return rec
            C.load_receipts = load_receipts
        if len(sys.argv) > 5:          # mini subset: one cell, one sensor seed (pipeline check only)
            cell = sys.argv[5]; orig_setup = C.T.canonical_setup

            def mini_setup(lk_):
                S = orig_setup(lk_); S["cells"] = {cell: S["cells"][cell]}; return S
            C.T.canonical_setup = mini_setup; C.M.SENSOR_SEEDS = C.M.SENSOR_SEEDS[:1]
        try:
            print("rc", C.cmd_run(f, g, OUT / "c3sh" / f"{f}{g}"), "sec", round(time.time() - t0))
        except SystemExit as ex:
            print("C3V5 cmd_run SystemExit ->", ex)
    else:
        print("rc", C.cmd_aggregate(str(OUT / "c3sh"), OUT / "c3agg"))
