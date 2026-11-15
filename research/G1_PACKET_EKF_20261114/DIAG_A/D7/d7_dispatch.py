"""Prepare and dispatch frozen D7 case/cohort jobs after the entry checks."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

for env in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[env] = "1"

import numpy as np
import pandas as pd
import scipy

from check_d7_limits import SPEC_COMMIT
from d7_d1 import synthetic_checks
from d7_run import ROOT, VARIANTS
from diag_inputs import CASES, COHORTS, sha256
from run_diag import scenario_key, utc, write_json

HERE = Path(__file__).resolve().parent
WORKERS = 8


def worker(case, level, sign):
    key = f"{case}_{scenario_key(level, sign)}"
    log = ROOT/"logs"/f"{key}.log"
    task = [sys.executable, "-u", str(HERE/"d7_run.py"), "--case", case,
            "--level", level, "--sign", str(sign)]
    started = utc()
    with log.open("x", encoding="utf-8") as f:
        exit_code = subprocess.run(task, stdout=f, stderr=subprocess.STDOUT).returncode
    rec = {"started_utc": started, "finished_utc": utc(), "command": task, "exit": exit_code,
           "log_sha256": sha256(log), "case": case, "level": level, "sign": sign}
    write_json(ROOT/"receipts"/f"{key}.json", rec)
    print(key, exit_code, utc(), flush=True)
    return rec


def main():
    print("START", SPEC_COMMIT, utc(), flush=True)
    tests = {d: synthetic_checks(d) for d in range(4, 9)}
    subprocess.run([sys.executable, "-u", str(HERE/"d7_run.py"), "--prepare"], check=True)
    for directory in ("logs", "receipts"):
        (ROOT/directory).mkdir()
    manifest = {
        "classification": "DIAGNOSTIC_ONLY", "spec_commit": SPEC_COMMIT,
        "question": "QA5", "s2_prime": "STOP (FULL_6)", "step_3": "HOLD",
        "recorded_utc": utc(), "cases": CASES, "cohorts": COHORTS, "arms": VARIANTS,
        "seeds": list(range(20)), "independence": "sensor repeats conditional on 4 fixed RF cases",
        "python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__,
        "pandas": pd.__version__, "platform": platform.platform(), "workers": WORKERS,
        "image": "sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f",
        "governance_common_sha256": "a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
        "governance_implementer_sha256": "2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da",
        "main_inputs_sha256": {str(p.relative_to(HERE)): sha256(p) for p in
            [ROOT/"PARAMETERS.json", HERE/"S0_REGRESSION.json", HERE/"range_input_diagnostic.json",
             *sorted((HERE/"attempt_02").glob("GATE_*.json"))]},
        "code_sha256": {p.name: sha256(p) for p in sorted(HERE.glob("*.py"))},
        "D1_synthetic": tests,
    }
    write_json(ROOT/"MANIFEST.json", manifest)
    jobs = iter((case, level, sign) for level, sign in COHORTS for case in CASES)
    all_receipts = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        active = {pool.submit(worker, *next(jobs)) for _ in range(WORKERS)}
        blocked = False
        while active:
            complete, active = wait(active, return_when=FIRST_COMPLETED)
            records = [f.result() for f in complete]
            all_receipts.extend(records)
            blocked = blocked or any(r["exit"] for r in records)
            if not blocked:
                active |= {pool.submit(worker, *job) for _, job in zip(complete, jobs)}
    write_json(ROOT/"EXECUTION.json", all_receipts)
    if not blocked and len(all_receipts) != len(CASES)*len(COHORTS):
        raise AssertionError("Missing D7 cohorts")
    print("RUN_COMPLETE" if not blocked else "RUN_FAILED", len(all_receipts), utc(), flush=True)
    return int(blocked)


if __name__ == "__main__":
    raise SystemExit(main())
