"""Stored-evidence checker independent of production selection/update helpers.

This checker does not import engine/numerics/selection/evaluation. It checks
bytes, denominators and Joseph arithmetic, not raw RF physics or independence
of a human reviewer. Its verdict is NEVER INDEPENDENT_ACCEPT.
"""
from __future__ import annotations
from pathlib import Path
import gzip
import hashlib
import json
import math
import numpy as np


def _require(ok, message):
    if not ok:
        raise ValueError("AUDIT:"+message)


def _near(actual, expected):
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    _require(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all(), "SHAPE_OR_NONFINITE")
    delta = float(np.max(np.abs(a-b)/np.maximum(1., np.abs(b))))
    _require(delta <= 1e-10, "NUMERICAL_MISMATCH")
    return delta


def check_update(record):
    x = np.asarray(record["prior"], float)
    P = np.asarray(record["Pprior"], float)
    if not record.get("updated", record.get("mask", False)) and "H" not in record:
        return {"max_normalized_error": max(_near(record["x"], x), _near(record["P"], P)), "predict_only": True}
    H = np.asarray(record["H"], float)
    R = np.asarray(record["R"], float)
    v = np.asarray(record["z"], float)-np.asarray(record["h"], float)-np.asarray(record["mu"], float)
    _require(x.shape == (4,) and P.shape == (4,4) and H.shape == (2,4) and R.shape == (2,2), "UPDATE_SHAPE")
    for c in (P, R, np.asarray(record["P"], float)):
        _require(np.isfinite(c).all(), "COVARIANCE_NONFINITE")
        _require(np.max(abs(c-c.T)) <= 1e-12*max(1.,np.linalg.norm(c,2)), "COVARIANCE_ASYMMETRY")
        _require(np.linalg.eigvalsh((c+c.T)/2).min() >= -1e-12, "COVARIANCE_NEGATIVE")
    # Explicit construction, independent of production update().
    S = np.array([[sum(H[i,a]*P[a,b]*H[j,b] for a in range(4) for b in range(4))+R[i,j]
                   for j in range(2)] for i in range(2)])
    S = (S+S.T)/2
    K = np.linalg.solve(S,H@P).T if record["mask"] else np.zeros((4,2))
    y=x+K@v
    if record["mask"]:
        y[2]=(y[2]+math.pi)%(2*math.pi)-math.pi
    A=np.eye(4)-K@H
    C=A@P@A.T+K@R@K.T
    C=(C+C.T)/2
    errors=[_near(record["K"],K),_near(record["x"],y),_near(record["P"],C)]
    if "S" in record:errors.append(_near(record["S"],S))
    return {"max_normalized_error":max(errors),"predict_only":False}


def check_denominators(rows, summary):
    valid=[r for r in rows if r["raw_valid"] and r["reference_valid"]]
    normal=[r for r in valid if r["raw_tap"]==r["reference_tap"]]
    wrong=[r for r in valid if r["raw_tap"]!=r["reference_tap"]]
    changed=[r for r in valid if r["raw_tap"]!=r["selected_tap"]]
    counts=dict(total=len(rows),eligible=len(valid),normal=len(normal),wrong=len(wrong),corrected=len(changed),
                false_corrections=sum(r["selected_tap"]!=r["reference_tap"] for r in normal),
                rescues=sum(r["selected_tap"]==r["reference_tap"] for r in wrong))
    for key,n in counts.items():_require(summary[key]==n,"DENOMINATOR_"+key)
    _require(not (not changed and summary["observed_numeric_gate"]),"NO_ACTION_FALSE_PASS")
    return counts


def check_result(value):
    checks={"updates":0,"summaries":0,"max_normalized_error":0.}
    def visit(node):
        if isinstance(node,list):
            for item in node:visit(item)
        elif isinstance(node,dict):
            if {"prior","Pprior","x","P","mask"} <= set(node):
                result=check_update(node);checks["updates"]+=1
                checks["max_normalized_error"]=max(checks["max_normalized_error"],result["max_normalized_error"])
            if "rows" in node and "summary" in node and isinstance(node["summary"],dict) and "eligible" in node["summary"]:
                check_denominators(node["rows"],node["summary"]);checks["summaries"]+=1
            for v in node.values():visit(v)
        elif isinstance(node,float):
            _require(math.isfinite(node),"NONFINITE_STORED_NUMBER")
    visit(value)
    return checks


def audit_directory(directory: Path):
    directory=directory.resolve()
    hashes=json.loads((directory/"ARTIFACT_HASHES.json").read_text(encoding="utf-8"))
    _require(bool(hashes),"EMPTY_HASH_REGISTRY")
    actual_files = {str(p.relative_to(directory)) for p in directory.rglob("*")
                    if p.is_file() and p.name != "ARTIFACT_HASHES.json"}
    _require(set(hashes) == actual_files, "UNINDEXED_OR_MISSING_ARTIFACT")
    total={"files":0,"updates":0,"summaries":0,"max_normalized_error":0.}
    manifest = json.loads((directory/"RUN_MANIFEST.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "COMPLETE_TECHNICAL_ONLY":
        # Inspect file bytes but never run the scientific result checker or
        # return PASS for failed, interrupted or partial manual execution.
        for name,expected in hashes.items():
            path=(directory/name).resolve()
            _require(path.is_relative_to(directory) and path.is_file(),"INVALID_ARTIFACT_PATH")
            with path.open("rb") as f:actual=hashlib.file_digest(f,"sha256").hexdigest()
            _require(actual==expected,"FILE_HASH_MISMATCH:"+name)
        return dict(status="HOLD_INCOMPLETE_RUN",run_status=manifest.get("status"),
                    byte_integrity_checked=len(hashes),
                    numerical_science_pass=False,external_independent_accept=False)
    for name,expected in hashes.items():
        path=(directory/name).resolve()
        _require(path.is_relative_to(directory) and path.is_file(),"INVALID_ARTIFACT_PATH")
        with path.open("rb") as f:actual=hashlib.file_digest(f,"sha256").hexdigest()
        _require(actual==expected,"FILE_HASH_MISMATCH:"+name);total["files"]+=1
        if path.name.endswith(".json.gz"):
            with gzip.open(path,"rt",encoding="utf-8") as f:value=json.load(f)
            result=check_result(value)
            for k in ("updates","summaries"):total[k]+=result[k]
            total["max_normalized_error"]=max(total["max_normalized_error"],result["max_normalized_error"])
    return dict(status="PASS_STORED_EVIDENCE_SELF_CHECK",checks=total,
                raw_waveforms_recomputed=False,source_FFD_reimplemented=False,external_independent_accept=False)
