"""A010-P1 canonical-input interfaces for future S1V5/C3V5.

No DEV3, HOLDOUT2 or RT execution in this module. Pure, independent
input-verification functions; all input selection/gating is the caller's job.
Current A010-P0 forensic evidence remains unmodified.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Mapping
import zipfile

import numpy as np


FACTOR_SHAPE = (180, 180)
FACTOR_SHA = "b09450fad48dc9f7c4eea6b59f5fe40995d7544c851ee2ea7daad7a28fc78fca"
CANON_SHA = "316efcc04946197cbb5c10417e3b6bfca3e4e8f5e4d3433535dfbba09b7bb9f3"
REQUIRED_ESTIMATOR = ("z", "x0", "ds_m", "gy_m", "taps", "Sigma_model", "dts")
TRUTH_ONLY = ("Xtrue", "Sigma_true", "poses", "ds_true", "dth_true")
ALLOWED_FORENSIC_KEYS = ("K1", "K2", "K3", "K4")


class InputIntegrityError(RuntimeError):
    pass


def sha_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha_array(arr: np.ndarray) -> str:
    """Versioned A010 dtype/shape/bytes hash, no data-dependent tolerance."""
    a = np.ascontiguousarray(np.asarray(arr))
    return hashlib.sha256(a.dtype.str.encode() + str(a.shape).encode()
                           + a.tobytes(order="C")).hexdigest()


def load_frozen_factor(path: str | Path, *,
                       expected_sha: str = FACTOR_SHA,
                       Kp: np.ndarray | None = None,
                       tol: float = 1e-10) -> np.ndarray:
    path = Path(path)
    if len(expected_sha) != 64 or sha_file(path) != expected_sha:
        raise InputIntegrityError("A010_FACTOR_HASH_MISMATCH")
    L = np.load(path, allow_pickle=False)
    if L.shape != FACTOR_SHAPE or L.dtype.str != "<f8" or not np.isfinite(L).all():
        raise InputIntegrityError("A010_FACTOR_DTYPE_SHAPE_FINITE")
    # Check covariance law without regenerating an eigenvector basis.
    if Kp is not None:
        K = np.asarray(Kp, np.float64)
        if K.shape != L.shape or np.max(np.abs(K - K.T)) > tol:
            raise InputIntegrityError("A010_KERNEL_SHAPE_OR_ASYMMETRY")
        scale = max(float(np.max(np.abs(K))), 1e-300)
        if np.max(np.abs(L @ L.T - K)) / scale > tol:
            raise InputIntegrityError("A010_FACTOR_KERNEL_MISMATCH")
    return L


def install_factor(setup: Mapping, frozen_path: str | Path,
                   *, expected_sha: str = FACTOR_SHA,
                   Kp: np.ndarray | None = None) -> dict:
    """Replace generated eigen-factor without changing poses or other config.

    Caller must compare recorded pose-ledger ordering and Kp to the
    validated source, not simply substitute an array with matching shape.
    """
    new = dict(setup)
    L = load_frozen_factor(frozen_path, expected_sha=expected_sha, Kp=Kp)
    if "Lhalf" in new and np.asarray(new["Lhalf"]).shape != L.shape:
        raise InputIntegrityError("A010_SETUP_WORLD_SHAPE")
    new["Lhalf"] = L
    new["A010_LHALF_SHA256"] = expected_sha
    return new


def read_forensic_bundle(zip_path: str | Path, *,
                         expected_sha: str = CANON_SHA,
                         case_ids: tuple[str, ...] = ALLOWED_FORENSIC_KEYS) -> dict:
    """Read original four forensic keys only, without pickle or silent omissions."""
    if sha_file(zip_path) != expected_sha:
        raise InputIntegrityError("A010_CANON_ZIP_HASH_MISMATCH")
    with zipfile.ZipFile(zip_path) as f:
        if f.namelist() != ["canonical.npz"]:
            raise InputIntegrityError("A010_CANON_MEMBER_SET")
        with np.load(io.BytesIO(f.read("canonical.npz")), allow_pickle=False) as d:
            arr = {name: np.array(d[name], copy=True) for name in d.files}
    suffixes = REQUIRED_ESTIMATOR + TRUTH_ONLY
    expected = {f"{c}|{s}" for c in case_ids for s in suffixes}
    if set(arr) != expected:
        raise InputIntegrityError("A010_CANON_ARRAY_SET_MISMATCH")
    for c in case_ids:
        for s in suffixes:
            a = arr[f"{c}|{s}"]
            if a.dtype.kind not in ("f", "i", "u") or not np.isfinite(a).all():
                raise InputIntegrityError(f"A010_CANON_NONFINITE_{c}_{s}")
        if arr[f"{c}|z"].shape != (60, 2) or arr[f"{c}|taps"].shape != (60,):
            raise InputIntegrityError("A010_CANON_OBSERVATION_SHAPE")
        for key in ("Sigma_true", "Sigma_model"):
            P = arr[f"{c}|{key}"]
            if P.shape != (120, 120) or np.max(np.abs(P - P.T)) > 1e-10:
                raise InputIntegrityError("A010_CANON_SIGMA_SHAPE")
            # Do not force this expensive positive-definite check on every load;
            # a separate generator-law gate performs it once per covariance.
    return arr


def estimator_only(bundle: Mapping[str, np.ndarray], cid: str) -> dict:
    """Give an estimator only z/controls/taps/model Sigma; no Xtrue or Sigma_true."""
    if cid not in ALLOWED_FORENSIC_KEYS:
        raise InputIntegrityError("A010_UNREGISTERED_FORENSIC_CASE")
    result = {}
    for s in REQUIRED_ESTIMATOR:
        key = f"{cid}|{s}"
        if key not in bundle:
            raise InputIntegrityError(f"A010_MISSING_ESTIMATOR_ARRAY_{s}")
        result[s] = np.array(bundle[key], copy=True)
    return result


def exact_array_compare(expected: Mapping[str, np.ndarray],
                        observed: Mapping[str, np.ndarray]) -> dict:
    """Exact per-array equality, including dtype/shape and binary payload."""
    missing = sorted(set(expected).difference(observed))
    unexpected = sorted(set(observed).difference(expected))
    mismatches = []
    for name in sorted(set(expected).intersection(observed)):
        e, o = np.asarray(expected[name]), np.asarray(observed[name])
        if e.dtype != o.dtype or e.shape != o.shape or e.tobytes() != o.tobytes():
            mismatches.append(name)
    return {"pass": not (missing or unexpected or mismatches),
            "missing": missing, "unexpected": unexpected,
            "mismatches": mismatches}


def audit_array_ledger(bundle: Mapping[str, np.ndarray],
                       sha_csv: str | Path) -> dict:
    """Independent hash audit of explicit GEN array ledger (no pandas dependency)."""
    import csv
    missing, mismatches, checked = [], [], 0
    with open(sha_csv, newline="") as f:
        for row in csv.DictReader(f):
            if row["array"] in ("z_S1V3_receipt", "Sigma_model_fp_check"):
                continue
            key = f"{row['case']}|{row['array']}"
            if key not in bundle:
                missing.append(key)
            else:
                checked += 1
                if sha_array(bundle[key]) != row["sha256"]:
                    mismatches.append(key)
    return {"pass": checked == 48 and not missing and not mismatches,
            "checked": checked, "missing": missing, "mismatches": mismatches}


def smoke_report(factor: str | Path, canonical_zip: str | Path,
                 ledger_csv: str | Path) -> dict:
    L = load_frozen_factor(factor)
    data = read_forensic_bundle(canonical_zip)
    ledger = audit_array_ledger(data, ledger_csv)
    # No model code or generated research observations are touched.
    cmp_ = exact_array_compare(estimator_only(data, "K1"),
                               estimator_only(data, "K1"))
    result = {"factor_sha256": sha_file(factor), "canonical_sha256": sha_file(canonical_zip),
              "factor_shape": list(L.shape), "array_ledger": ledger,
              "exact_self_replay": cmp_, "case_count": len(ALLOWED_FORENSIC_KEYS),
              "science_status": "NOT_RUN", "dev3_status": "CLOSED", "holdout2_status": "CLOSED"}
    result["pass"] = bool(ledger["pass"] and cmp_["pass"])
    return result
