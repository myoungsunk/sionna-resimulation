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
            "robot_xy_m", "anchor_m", "robot_antenna_m", "ports", "H_layout")
H_LAYOUT = "[yaw, bin, rx_port(+45,-45), tx_port(+45,-45)]; offsets index flattened (bin-major, yaw-minor)"


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
    robot_position: object                 # callable (x, y) -> planned receiver xyz
    setup_config_sha256: str | None = None
    runner_sha256: str | None = None       # None: do not compare (audit of results made by older runner versions)
    materials: list | None = None          # [(object, itu_type, thickness_m)] in the order of the receipt, None: skip
    los_expected: object = None            # callable (x, y) -> bool, or None
    require_scene_files: int | None = None
    scenario: str | None = None
    npz_optional: tuple = ()               # npz keys that older runner versions did not store (audit of legacy outputs only)
    notes: list = field(default_factory=list)


def _close(a, b, tol=1e-9) -> bool:
    try:
        return np.shape(a) == np.shape(b) and bool(np.allclose(np.asarray(a, float), np.asarray(b, float), rtol=0, atol=tol))
    except (TypeError, ValueError):
        return False


def _check_paths(z, H, n_yaw, frequencies, xy, exp):
    """Validate structure before indexing; reproduce the runner's bin-major sum.

    The runner saves coefficients as complex64, but H before that conversion.
    Allow 2*eps32*sum(abs(a)) for storage rounding, plus a conservative
    floating-point summation bound. No fixed absolute floor masks weak channels.
    Keep the producer's delay dtype in the phase expression.
    """
    counts, offsets = z["path_counts"], z["offsets"]
    if (counts.shape != (n_yaw, len(frequencies)) or
            offsets.shape != (n_yaw * len(frequencies) + 1,) or
            counts.dtype.kind not in "iu" or offsets.dtype.kind not in "iu" or
            (counts < 0).any() or (offsets < 0).any() or offsets[0] != 0 or
            (offsets[1:] < offsets[:-1]).any() or
            not np.array_equal(np.diff(offsets), counts.T.ravel())):
        return ["npz path_counts/offsets violate integer, nonnegative, bin-major contract"]
    n = int(offsets[-1])
    a, tau, inter = z["a_cat"], z["tau_cat"], z["interactions_cat"]
    if (a.shape != (2, 2, n) or a.dtype.kind != "c" or
            tau.shape != (n,) or tau.dtype.kind != "f" or
            inter.ndim != 2 or inter.shape[1] != n or inter.dtype.kind not in "iu"):
        return ["npz concatenated path array shapes/dtypes disagree with offsets"]
    if "objects_cat" in z.files:
        obj = z["objects_cat"]
        if obj.shape != inter.shape or obj.dtype.kind not in "iu":
            return ["npz objects_cat shape/dtype differs from interactions_cat"]
    if not np.isfinite(a).all() or not np.isfinite(tau).all() or (tau < 0).any():
        return ["npz path coefficients/delays must be finite and delays nonnegative"]
    issues = []
    if H.shape == (n_yaw, len(frequencies), 2, 2):
        mismatch = 0
        for bi, freq in enumerate(frequencies):
            for yi in range(n_yaw):
                j = bi * n_yaw + yi
                start, stop = int(offsets[j]), int(offsets[j + 1])
                coef, delay = a[..., start:stop], tau[start:stop]
                phase = np.exp(-2j * np.pi * freq * delay)
                reconstructed = (coef * phase[None, None, :]).sum(-1)
                magnitude = np.abs(coef.astype(np.complex128)).sum(-1)
                eps = np.finfo(reconstructed.real.dtype).eps
                bound = (2 * np.finfo(np.float32).eps + 8 * max(1, stop-start) * eps) * magnitude
                if (not np.isfinite(reconstructed).all() or
                        not (np.abs(reconstructed - H[yi, bi]) <= bound).all()):
                    mismatch += 1
        if mismatch:
            issues.append(f"npz path reconstruction differs from H in {mismatch} calls")
    if exp.los_expected is not None:
        zero = (inter == 0).all(axis=0).astype(np.int64)
        cs = np.concatenate([[0], np.cumsum(zero)])
        los_per_call = cs[offsets[1:]] - cs[offsets[:-1]]
        want = bool(exp.los_expected(*xy))
        if not ((los_per_call > 0) == want).all():
            issues.append(f"LoS path presence disagrees with the geometric expectation (expected {'clear' if want else 'blocked'}) in {int(((los_per_call > 0) != want).sum())} calls")
    return issues


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
    if z["H"].shape == H.shape and (not np.iscomplexobj(z["H"]) or not np.array_equal(z["H"], H)):
        issues.append("sweep.npz H differs from H.npy")
    elif z["H"].shape != H.shape:
        issues.append("sweep.npz H shape differs from H.npy")
    if not _close(z["yaw_deg"], exp.yaw_deg):
        issues.append("npz yaw_deg differs from the requested list")
    if not np.array_equal(z["bin_index"], np.array(bins)):
        issues.append("npz bin_index differs from the requested bins")
    elif not _close(z["freqs_hz"], exp.freq_grid_hz[bins], 1e-3):
        issues.append("npz freqs_hz differ from the bank frequency grid")
    issues.extend(_check_paths(z, H, n_yaw, exp.freq_grid_hz[bins], xy, exp))
    if not np.array_equal(z["ports"], ["LP_plus45", "LP_minus45"]):
        issues.append("npz ports differ from the RX/TX port order")
    if "H_layout" in z.files and (z["H_layout"].shape != () or z["H_layout"].item() != H_LAYOUT):
        issues.append("npz H_layout differs from the RX/TX axis contract")
    if not _close(z["robot_antenna_m"], exp.robot_position(*xy), 1e-9):
        issues.append("npz robot_antenna_m differs from the planned receiver")
    if not _close(z["robot_xy_m"], xy, 1e-9):
        issues.append("npz robot_xy_m differs from the requested position")
    if not _close(z["anchor_m"], exp.anchor_m, 1e-9):
        issues.append("npz anchor_m differs from the planned anchor")
    z.close()
    return issues


def check_run(run_dir: Path, positions: list, tag_fn, exp: Expect, ignore_dirs=("logs", "_superseded", "geom_check", "slab_check")) -> dict:
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
