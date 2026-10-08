"""Validation of ray-tracing sweep outputs (one folder per tag position): files, contract, internal consistency and LoS.

Used for the office run (strict) and for auditing the corridor runs. Nothing here needs Sionna or Mitsuba.
A position is ``valid`` only if no issue is reported; a receipt alone is never enough.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

NPZ_KEYS = ("H", "yaw_deg", "bin_index", "freqs_hz", "path_counts", "offsets", "tau_cat", "a_cat", "interactions_cat", "objects_cat",
            "robot_xy_m", "anchor_m", "robot_antenna_m", "ports")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Expect:
    """What a run was asked to produce."""
    yaw_deg: list
    bin_stride: int
    freq_grid_hz: np.ndarray
    solver: dict
    adapter_sha256: str
    bank_sha256: dict                      # {"LP_plus45_bank.npz": sha, ...}
    anchor_m: list
    setup_config_sha256: str | None = None
    runner_sha256: str | None = None       # None: do not compare (audit of results made by older runner versions)
    materials: list | None = None          # [(object, itu_type, thickness_m)] in the order of the receipt, None: skip
    los_expected: object = None            # callable (x, y) -> bool, or None
    require_scene_files: int | None = None
    scenario: str | None = None
    npz_optional: tuple = ()               # npz keys that older runner versions did not store (audit of legacy outputs only)
    notes: list = field(default_factory=list)


def _close(a, b, tol=1e-9) -> bool:
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=0, atol=tol)) and np.shape(a) == np.shape(b)


def check_position(folder: Path, tag: str, xy: tuple, exp: Expect) -> list:
    """Return the list of issues for one position folder (empty list = valid)."""
    issues = []
    folder = Path(folder)
    need = {"receipt": folder / f"{tag}_receipt.json", "H": folder / f"{tag}_H.npy", "npz": folder / f"{tag}_sweep.npz", "snapshot": folder / "SETUP_SNAPSHOT.json"}
    for k, p in need.items():
        if not p.exists():
            issues.append(f"missing file: {p.name}")
    if issues:
        return issues
    try:
        rc = json.loads(need["receipt"].read_text())
    except Exception as e:  # noqa: BLE001
        return [f"receipt unreadable: {e}"]
    for key in ("robot_xy_m", "yaws", "n_bins", "bin_stride", "pathsolver_calls", "solver", "adapter_sha256", "bank_sha256", "mean_paths", "versions"):
        if key not in rc:
            issues.append(f"receipt lacks '{key}'")
    if issues:
        return issues
    n_yaw = len(exp.yaw_deg)
    bins = list(range(0, len(exp.freq_grid_hz), exp.bin_stride))
    if not _close(rc["robot_xy_m"], xy, 1e-9):
        issues.append(f"receipt position {rc['robot_xy_m']} != requested {list(xy)}")
    if not _close(rc["yaws"], exp.yaw_deg):
        issues.append("receipt yaws differ from the requested yaw list")
    if rc["bin_stride"] != exp.bin_stride or rc["n_bins"] != len(bins):
        issues.append(f"receipt bin_stride/n_bins {rc['bin_stride']}/{rc['n_bins']} != requested {exp.bin_stride}/{len(bins)}")
    if rc["pathsolver_calls"] != n_yaw * len(bins):
        issues.append(f"receipt pathsolver_calls {rc['pathsolver_calls']} != {n_yaw * len(bins)}")
    if rc["solver"] != exp.solver:
        issues.append("receipt solver configuration differs from CONFIG.json")
    if rc["adapter_sha256"] != exp.adapter_sha256:
        issues.append("adapter hash differs")
    if rc["bank_sha256"] != exp.bank_sha256:
        issues.append("antenna bank hashes differ from the bank manifest")
    if exp.runner_sha256 and rc.get("runner_sha256") != exp.runner_sha256:
        issues.append("runner hash differs from the current runner")
    if exp.scenario and rc.get("scenario") not in (None, exp.scenario):
        issues.append(f"receipt scenario {rc.get('scenario')} != {exp.scenario}")
    snap = json.loads(need["snapshot"].read_text())
    if exp.setup_config_sha256 and snap.get("config_sha256") != exp.setup_config_sha256:
        issues.append("SETUP_SNAPSHOT config hash differs from the planned setup")
    if exp.setup_config_sha256 and rc.get("setup_config_sha256") not in (None, exp.setup_config_sha256):
        issues.append("receipt setup hash differs from the planned setup")
    if exp.materials is not None:
        got = [(m["object"], m["itu_type"], float(m["thickness_m"])) for m in rc.get("materials", [])]
        if sorted(got) != sorted((n, i, float(t)) for n, i, t in exp.materials):
            issues.append("material bindings differ from the planned objects")
    if exp.require_scene_files is not None and len(list((folder / "scene").glob("*.ply"))) != exp.require_scene_files:
        issues.append(f"scene has {len(list((folder / 'scene').glob('*.ply')))} PLY files, expected {exp.require_scene_files}")
    # ---- H.npy -----------------------------------------------------------------------------
    try:
        H = np.load(need["H"])
    except Exception as e:  # noqa: BLE001
        return issues + [f"H.npy unreadable: {e}"]
    if H.shape != (n_yaw, len(bins), 2, 2):
        issues.append(f"H shape {H.shape} != {(n_yaw, len(bins), 2, 2)}")
    elif not np.iscomplexobj(H) or not np.isfinite(H).all():
        issues.append("H is not complex/finite")
    elif (np.abs(H).reshape(n_yaw, len(bins), 4).max(-1) == 0).any():
        issues.append("H has all-zero channels")
    # ---- sweep.npz -------------------------------------------------------------------------
    try:
        z = np.load(need["npz"])
        missing = [k for k in NPZ_KEYS if k not in z.files and k not in exp.npz_optional]
    except Exception as e:  # noqa: BLE001
        return issues + [f"sweep.npz unreadable: {e}"]
    if missing:
        return issues + [f"sweep.npz lacks {missing}"]
    if z["H"].shape == H.shape and not np.allclose(z["H"], H, rtol=0, atol=1e-12):
        issues.append("sweep.npz H differs from H.npy")
    elif z["H"].shape != H.shape:
        issues.append("sweep.npz H shape differs from H.npy")
    if not _close(z["yaw_deg"], exp.yaw_deg):
        issues.append("npz yaw_deg differs from the requested list")
    if not np.array_equal(z["bin_index"], np.array(bins)):
        issues.append("npz bin_index differs from the requested bins")
    elif not _close(z["freqs_hz"], exp.freq_grid_hz[bins], 1e-3):
        issues.append("npz freqs_hz differ from the bank frequency grid")
    counts, offsets = z["path_counts"], z["offsets"]
    if counts.shape != (n_yaw, len(bins)) or offsets.shape != (n_yaw * len(bins) + 1,):
        issues.append("npz path_counts/offsets shapes are inconsistent with the request")
    else:
        if not np.array_equal(np.diff(offsets), counts.T.ravel()):
            issues.append("npz offsets do not match path_counts")
        n_tot = int(offsets[-1])
        if not (z["tau_cat"].size == z["a_cat"].shape[-1] == z["interactions_cat"].shape[1] == n_tot and ("objects_cat" not in z.files or z["objects_cat"].shape[1] == n_tot)):
            issues.append("npz concatenated path arrays disagree with offsets")
        elif exp.los_expected is not None:
            zero = (z["interactions_cat"] == 0).all(axis=0).astype(np.int64)
            cs = np.concatenate([[0], np.cumsum(zero)])
            los_per_call = cs[offsets[1:]] - cs[offsets[:-1]]
            want = bool(exp.los_expected(*xy))
            if not ((los_per_call > 0) == want).all():
                issues.append(f"LoS path presence disagrees with the geometric expectation (expected {'clear' if want else 'blocked'}) in {int(((los_per_call > 0) != want).sum())} calls")
    if not _close(z["robot_xy_m"], xy, 1e-9):
        issues.append("npz robot_xy_m differs from the requested position")
    if not _close(z["anchor_m"], exp.anchor_m, 1e-9):
        issues.append("npz anchor_m differs from the planned anchor")
    return issues


def check_run(run_dir: Path, positions: list, tag_fn, exp: Expect, ignore_dirs=("logs", "_superseded", "geom_check")) -> dict:
    """All requested positions valid, none duplicated, none unexpected."""
    run_dir = Path(run_dir)
    out = dict(positions={}, duplicates=[], unexpected=[])
    seen = {}
    for xy in positions:
        tag = tag_fn(*xy)
        if tag in seen:
            out["duplicates"].append(tag)
        seen[tag] = xy
    for tag, xy in seen.items():
        folder = run_dir / tag
        out["positions"][tag] = ["missing folder"] if not folder.exists() else check_position(folder, tag, xy, exp)
    for p in sorted(run_dir.iterdir()) if run_dir.exists() else []:
        if p.is_dir() and p.name not in seen and p.name not in ignore_dirs:
            out["unexpected"].append(p.name)
    out["n_requested"] = len(seen)
    out["n_valid"] = sum(1 for v in out["positions"].values() if not v)
    out["ok"] = out["n_valid"] == len(seen) and not out["duplicates"] and not out["unexpected"]
    return out
