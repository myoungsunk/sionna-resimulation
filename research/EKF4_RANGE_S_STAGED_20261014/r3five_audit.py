"""Read-only mandatory audit before the R3 five-failure diagnostic.

NO numerical solver, no test, no fixture replay in this process.
Refuse to run if any source, workflow ordering, or frozen data differs.
"""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ORIGINAL = "2547f147ea347563a186a886bd25a543871825f3"
FROZEN = {
    "core.py": "11d0662c4a96af9f0b6dab8d209cbd126b0a50774f15f463a256792dfabc1526",
    "P2_SPEC.json": "548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7",
    "synthetic.py": "c3fc54d9726beab176971aa8652c0b6f61353f55f596613e4c8150351c4d9643",
}
ARTIFACT = {
    "run_id": 38562146793,
    "artifact_id": 11892566974,
    "zip_sha256": "931ee7cd8552820f3b6311877bb6ccc4ecc910669231290efb82e5868756c9b4",
    "source_sha": ORIGINAL,
    "invalid_model_cases": 5
}
FILES = ("r3five_audit.py", "r3five_diag.py", "solver_r3.py", "stable_descent.py",
         "core.py", "synthetic.py", "P2_SPEC.json", "requirements.txt")
WORKFLOW = REPO / ".github/workflows/ekf4-r3-five-failure-diagnostic.yml"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    fatal = []
    source_hashes = {}
    run_sha = os.environ.get("GITHUB_SHA", "")
    if os.getenv("GITHUB_ACTIONS") != "true" or not run_sha:
        fatal.append("NOT_GITHUB_ACTIONS_EXACT_COMMIT")
    try:
        git_head = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
        if git_head != run_sha:
            fatal.append("GIT_CHECKOUT_MISMATCH")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ORIGINAL, "HEAD"],
            cwd=REPO, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if ancestor.returncode != 0:
            fatal.append("ORIGINAL_COMMIT_NOT_ANCESTOR")
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", ORIGINAL, "HEAD"],
            cwd=REPO, text=True).splitlines()
        authorized = {
            "research/EKF4_RANGE_S_STAGED_20261014/r3five_audit.py",
            "research/EKF4_RANGE_S_STAGED_20261014/r3five_diag.py",
            "research/EKF4_RANGE_S_STAGED_20261014/R3_FIVE_FAILURE_DIAG_PLAN_20261014.md",
            ".github/workflows/ekf4-r3-five-failure-diagnostic.yml",
        }
        if set(changed)-authorized:
            fatal.append("UNAUTHORIZED_SOURCE_CHANGE:" + repr(sorted(set(changed)-authorized)))
        for f in FILES:
            p = HERE / f
            if not p.is_file():
                fatal.append("MISSING:" + f)
                continue
            source_hashes[f] = sha(p)
            if f.endswith(".py"):
                ast.parse(p.read_text(encoding="utf-8"), filename=f)
        for f, expected in FROZEN.items():
            if source_hashes.get(f) != expected:
                fatal.append("FROZEN_SHA_MISMATCH:" + f)
        # Verify our read-only fixture reader has not redefined MAP, the
        # synthetic generator, or the data scoring implementation.
        src = (HERE / "r3five_diag.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        funcs = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
        # mpmath's LU helper accepts *vector* RHS. The first diagnostic
        # trial failed when a 2-by-n matrix RHS was passed; fail closed on
        # unreviewed matrix products as RHS in this numerical diagnostic.
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "lu_solve" and len(node.args) >= 2
                    and isinstance(node.args[1], ast.BinOp)):
                fatal.append("MP_LU_SOLVE_NONVECTOR_RHS_UNREVIEWED")
        if not {"diagnose", "high_precision_analysis", "run"}.issubset(funcs):
            fatal.append("DIAGNOSTIC_API_MISSING")
        for token in ("FAILED_STEP.npz", "FAILURE.json", "CASE_INVALID.json",
                      "zipfile", "mpmath", "source_hashes"):
            if token not in src:
                fatal.append("DIAGNOSTIC_AUDIT_CONTRACT:" + token)
        wf = WORKFLOW.read_text(encoding="utf-8")
        ia = wf.index("python research/EKF4_RANGE_S_STAGED_20261014/r3five_audit.py")
        idn = wf.index("python research/EKF4_RANGE_S_STAGED_20261014/r3five_diag.py")
        if not (ia < idn and ia >= 0):
            fatal.append("AUDIT_ORDER_VIOLATED")
        if "actions: read" not in wf:
            fatal.append("CLOUD_ARTIFACT_READ_PERMISSION_MISSING")
    except Exception as e:
        fatal.append("AUDIT_IMPLEMENTATION:" + type(e).__name__ + ":" + str(e))
    report = {
        "schema": "R3_FIVE_FAILURE_PREEXECUTION_AUDIT_V1",
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "stage": "FIVE_FIXED_FAILURE_FORENSICS",
        "git_sha": run_sha,
        "original_solver_commit": ORIGINAL,
        "frozen_input_hashes": FROZEN,
        "source_sha256": source_hashes,
        "workflow_sha256": sha(WORKFLOW) if WORKFLOW.is_file() else None,
        "artifact_contract": ARTIFACT,
        "actions_run_id": os.environ.get("GITHUB_RUN_ID"),
        "decision": "HOLD" if fatal else "GO",
        "fatal": fatal,
        "audit_scope": "static read-only audit, not high-precision solver validation",
        "independent_scientific_review": False,
        "scientific_PASS": False
    }
    (out / "PRE_AUDIT.json").write_text(json.dumps(report, indent=2) + "\n")
    print("R3_FIVE_PREAUDIT", json.dumps({k: report[k] for k in
          ("decision", "fatal", "git_sha", "original_solver_commit")}), flush=True)
    return 0 if not fatal else 2


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: r3five_audit.py <new_output_directory>")
    raise SystemExit(audit(sys.argv[1]))
