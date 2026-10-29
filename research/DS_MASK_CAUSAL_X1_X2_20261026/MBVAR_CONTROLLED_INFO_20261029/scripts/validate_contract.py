"""Contract / governance / split / protected-path validator (CI_REQUIREMENTS.md). Exit 0 = mechanical PASS only.

  validate_contract.py --contract C.md --mode draft
  validate_contract.py --contract C.md --mode frozen --phase G2|G3|G4 [--manifest M.json] [--base-sha SHA] [--splits S.json]
The frozen lock is the last ```json block under a '## FROZEN_LOCK' heading of the contract.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCIENCE_FIELDS = ("GOVERNANCE_SHA", "SOURCE_SHA", "HGEOMETRY", "FINAL_SPLITS", "EFFECT_SIZE")
RF_FIELDS = ("MATERIAL", "DIRECT_PARITY_TOL", "RF_BUDGET")
PROTECTED = (r"^data/raw/", r"^results/frozen/", r"^reports/release/", r"^_archive/", r"^archive/",
             r"^research/DS_MASK_CAUSAL_X1_X2_20261026/(mbvar_control_correction_20261029|mbvar_premodel_diag_20261029|"
             r"mbvar_e2_e5_revalidation_20261029|pol_bias_model|reflect_model)/")
HEX40 = re.compile(r"^[0-9a-f]{40}$"); HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Fail(Exception):
    pass


def lock_of(text: str):
    if "## FROZEN_LOCK" not in text:
        return None
    seg = text.split("## FROZEN_LOCK", 1)[1]
    blocks = re.findall(r"```json\n(.*?)\n```", seg, re.S)
    return json.loads(blocks[-1]) if blocks else None


def check_frozen(lock: dict, phase: str, env_gov: str | None):
    errs = []
    if not lock:
        return ["ERR_CONTRACT_DRAFT:no FROZEN_LOCK"]
    if lock.get("status") != "FROZEN":
        errs.append("ERR_CONTRACT_DRAFT:status")
    for k in ("governance_git_sha", "base_git_sha"):
        if not HEX40.match(str(lock.get(k, ""))):
            errs.append(f"ERR_ROLE_ROUTING:{k}")
    if env_gov and lock.get("governance_git_sha") != env_gov:
        errs.append("ERR_ROLE_ROUTING:governance_sha_mismatch")
    res = lock.get("resolved", {})
    for f in SCIENCE_FIELDS:
        v = res.get(f)
        if v in (None, "", "UNRESOLVED") or (isinstance(v, str) and "P0_TO_RESOLVE" in v):
            errs.append(f"ERR_CONTRACT_DRAFT:science_field:{f}")
    if phase in ("G4", "G5", "G6"):
        for f in RF_FIELDS:
            v = res.get(f)
            if v in (None, "", "DEFERRED_PRE_P3_AMENDMENT") or (isinstance(v, str) and "P0_TO_RESOLVE" in v):
                errs.append(f"ERR_RT_BUDGET:rf_field:{f}")
    if lock.get("p0_status") != "PASS":
        errs.append("ERR_CONTRACT_DRAFT:p0_not_pass")
    return errs


def check_splits(splits: dict):
    errs = []
    for track, roles in splits.items():
        seen = {}
        for role, ids in roles.items():
            for i in ids:
                if i in seen:
                    errs.append(f"ERR_SPLIT_LEAK:{track}:{i}:{seen[i]}+{role}")
                seen[i] = role
    return errs


def check_protected(base: str):
    try:
        names = subprocess.check_output(["git", "diff", "--name-only", f"{base}...HEAD"], text=True).split()
    except Exception as e:  # noqa: BLE001
        return [f"ERR_PROTECTED_WRITE:cannot_diff:{e}"]
    bad = [n for n in names if any(re.match(p, n) for p in PROTECTED)]
    return [f"ERR_PROTECTED_WRITE:{n}" for n in bad]


def check_manifest(path: Path, lock: dict | None, contract_sha: str):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
    import manifest as MF
    m = json.loads(path.read_text()); errs = [f"ERR_MANIFEST:{e}" for e in MF.validate_manifest(m)]
    if m.get("phase") not in ("P0_PREFLIGHT",) and m.get("contract_sha256") != contract_sha:
        errs.append("ERR_CONTRACT_DRAFT:manifest_contract_sha_mismatch")
    if lock and m.get("governance_git_sha") != lock.get("governance_git_sha"):
        errs.append("ERR_ROLE_ROUTING:manifest_governance_mismatch")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True); ap.add_argument("--mode", choices=("draft", "frozen"), required=True)
    ap.add_argument("--phase", default=""); ap.add_argument("--manifest"); ap.add_argument("--base-sha"); ap.add_argument("--splits")
    ap.add_argument("--expect-contract-sha256"); ap.add_argument("--print-governance", action="store_true")
    a = ap.parse_args(argv)
    p = Path(a.contract); text = p.read_text(); sha = hashlib.sha256(p.read_bytes()).hexdigest()
    if a.print_governance:
        lk = lock_of(text); print(lk["governance_git_sha"] if lk else ""); return 0
    errs = []; report = dict(contract=str(p), contract_sha256=sha, mode=a.mode, phase=a.phase)
    lock = lock_of(text)
    if a.mode == "frozen" and lock:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
        import contract_lock as CL
        try:
            lock = CL.effective_lock(contract=p)          # frozen contract + FROZEN amendment locks named in RUN_REQUEST
            report["applied_amendment_locks"] = lock.get("applied_amendment_locks", [])
        except SystemExit as e:
            errs.append(str(e))
    if a.mode == "draft":
        placeholders = sorted(set(re.findall(r"P0_TO_RESOLVE_[A-Z_]+", text)))
        report.update(placeholders=placeholders, frozen_lock_present=bool(lock), unlocks_experiments=False)
        if not placeholders and not lock:
            errs.append("ERR_CONTRACT_DRAFT:draft_without_placeholders_or_lock")
    else:
        if a.phase not in ("G2", "G3", "G4", "G5", "G6"):
            errs.append("ERR_CONTRACT_DRAFT:frozen_mode_requires_G2..G6")
        errs += check_frozen(lock, a.phase, os.environ.get("MBVAR_GOVERNANCE_SHA"))
        if a.expect_contract_sha256 and a.expect_contract_sha256 != sha:
            errs.append("ERR_CONTRACT_DRAFT:contract_sha256_changed")
        if a.splits:
            errs += check_splits(json.loads(Path(a.splits).read_text()))
        elif lock and "splits" in lock:
            errs += check_splits(lock["splits"])
    if a.base_sha:
        errs += check_protected(a.base_sha)
    if a.manifest:
        errs += check_manifest(Path(a.manifest), lock, sha)
    report["errors"] = errs; report["result"] = "PASS" if not errs else "FAIL"
    print(json.dumps(report, indent=1))
    return 0 if not errs else 1


if __name__ == "__main__":
    raise SystemExit(main())
