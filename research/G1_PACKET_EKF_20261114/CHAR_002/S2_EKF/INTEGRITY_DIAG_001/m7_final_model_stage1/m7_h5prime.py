"""Offline H5P donor fit using M6's pinned block/ratio calculation at sigma=0.

Pure helpers are testable with synthetic arrays. The file entry point requires
an explicit, hash-pinned donor_fit GO contract; no fit runs at import time.
"""
import hashlib
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np

from m7_spec import ROUTES

EDGES = (0., 1.5, 3., 6., 10.)
CASE_KEYS = ("t", "mask", "prior_distance", "raw_s", "a_ref", "arc", "yaw_arc")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(record):
    path = Path(record["path"])
    if sha(path) != record["sha256"]:
        raise ValueError(f"Source/input hash mismatch: {path}")
    return path


def load_characterizer(record):
    path = checked(record)
    spec = importlib.util.spec_from_file_location("m7_frozen_m6_characterize", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepared_cases(cases):
    if set(cases) != set(ROUTES):
        raise ValueError("Expected exactly the frozen R2/R4/R5 donor cases")
    prepared = {}
    for route in ROUTES:
        data = {key: np.asarray(cases[route][key]) for key in CASE_KEYS}
        t = data["t"]
        if t.ndim != 1 or len(t) < 2 or not np.all(np.diff(t) > 0.):
            raise ValueError(f"Invalid donor time grid: {route}")
        if any(value.shape != t.shape or value.dtype.kind not in "biuf"
               or not np.isfinite(value).all() for value in data.values()):
            raise ValueError(f"Invalid/nonfinite donor arrays: {route}")
        if data["mask"].dtype.kind != "b":
            raise ValueError(f"Donor mask must be boolean: {route}")
        if (np.any(data["prior_distance"] < 0.) or any(np.any(np.diff(data[key]) < 0.)
                                                       for key in ("arc", "yaw_arc"))):
            raise ValueError(f"Invalid donor distance or motion order: {route}")
        center = np.asarray(cases[route]["route_mean_s"])
        if center.ndim != 0 or center.dtype.kind not in "iuf" or not np.isfinite(center):
            raise ValueError(f"Invalid D3 route center: {route}")
        data["route_mean_s"] = float(center)
        data["block"] = np.floor((t - t[0]) / 10.).astype(int)
        prepared[route] = data
    return prepared


def fit_h5_prime(cases, characterizer):
    """Use the original M6 fitter, changing only its GM subtraction sigma to zero.

All donors and eligibility rules remain fixed. This function is offline; its
output must be frozen before any held-out M7 replay is scored.
"""
    constants = {"ROUTES": ROUTES, "DISTANCE_EDGES_M": EDGES,
                 "BLOCK_SECONDS": 10., "MIN_BLOCKS": 2, "MIN_PAIRS": 10,
                 "KERNEL_DISTANCE_M": 1., "KERNEL_YAW_RAD": np.deg2rad(10.),
                 "PAIR_LAG_SECONDS": (.4, 5.)}
    for key, expected in constants.items():
        if getattr(characterizer, key) != expected:
            raise ValueError(f"Frozen M6 fitting rule differs: {key}")
    prepared = _prepared_cases(cases)
    zero_sigma = {"folds": {route: {"sigma_rad": 0.} for route in ROUTES}}
    result = characterizer._hybrid(prepared, zero_sigma)
    for held in ROUTES:
        fold = result["folds"][held]
        if len(fold["q_s"]) != 4 or len(fold["supported_bins"]) != 4:
            raise ValueError("Unexpected H5P bin grid")
        values = np.asarray(fold["q_s"], float)
        supported = np.asarray(fold["supported_bins"])
        if (not np.isfinite(values).all() or np.any(values < 0.) or supported.dtype.kind != "b"
                or np.any(values[~supported] != 0.)):
            raise ValueError("Invalid H5P q_s table")
        donors = set(ROUTES) - {held}
        if any(set(row["donors"]) != donors for row in fold["bins"]):
            raise ValueError("Holdout leaked into its donor fold")
    return dict(arm="H5P", classification="OFFLINE_DONOR_ONLY", sigma_rad=0.,
                distance_edges_m=list(EDGES), fit=result,
                method="M6 pair/block means, pooled numerator/denominator; GM subtraction zero",
                claim_limit="H5 failure does not establish that b_theta is necessary")


def execute_h5_prime(contract_path, output_dir):
    """Actual donor evidence path. No execution is authorized by a draft contract."""
    contract_path = Path(contract_path)
    contract = json.loads(contract_path.read_text(encoding="utf-8-sig"))
    if contract.get("authorization", {}).get("donor_fit") != "GO":
        raise ValueError("donor_fit GO is absent; actual fitting remains on HOLD")
    own = [record for record in contract["sources"]
           if Path(record["path"]).resolve() == Path(__file__).resolve()]
    if len(own) != 1:
        raise ValueError("Contract must pin the exact H5P implementation once")
    for record in contract["sources"]:
        checked(record)
    fit_spec = contract["h5prime"]
    if fit_spec["method"] != "M6_SIGMA_ZERO_LORO":
        raise ValueError("Unrecognized H5P contract method")
    if set(fit_spec["donor_cases"]) != set(ROUTES):
        raise ValueError("Incomplete H5P donor sources")
    module = load_characterizer(fit_spec["characterizer_source"])
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise FileExistsError("H5P evidence directory must be empty")
    started = datetime.now(timezone.utc).isoformat()
    receipt = dict(status="FAIL_EXECUTION", exit_code=1, started_utc=started,
                   command=[sys.executable, *sys.argv], contract_sha256=sha(contract_path), outputs={})
    try:
        cases = {}
        for route in ROUTES:
            with np.load(checked(fit_spec["donor_cases"][route]), allow_pickle=False) as data:
                cases[route] = {key: data[key].copy() for key in (*CASE_KEYS, "route_mean_s")}
        result = fit_h5_prime(cases, module)
        path = out / "H5P_DONOR_FIT.json"
        with path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
        receipt.update(status="PASS_EXECUTION", exit_code=0,
                       outputs={path.name: sha(path)}, classification="OFFLINE_DONOR_ONLY")
    except BaseException as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        with (out / "EXECUTION.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(receipt, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
    return result
