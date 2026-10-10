"""S2 parity gates G2 / G2' (and G4) of method B against stored method-A channels.

  python scripts/drive_sim/parity_gate.py --traces-all DIR_BIN_BY_BIN --traces-nodes DIR_17_NODES --out PARITY_REPORT.json \
      [--g4-a-dir DIR_WITH_A_RUNS_AT_OUT_OF_RANGE_YAWS]

Reference = the stored ``*_H.npy`` of CORRIDOR_SWEEP_20261006 / CORRIDOR_SCAN_20261006 / CORRIDOR_SCAN2_20261007 (threads=1 runs, bit-reproduced in S0).
All chain quantities use the single-TX first-path rule (column 0 = TX +45).  Thresholds are read from S0/PREREG.json, not typed here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from drive_sim_s0_reference_check import stored_positions  # noqa: E402
from qclean_uwb.drivesim.rf_store import h_for_antenna_yaws, load_banks, load_trace, tag_of  # noqa: E402
from qclean_uwb.features.fp_power import signed_s_single_tx  # noqa: E402

C0 = 299792458.0
PREREG = ROOT / "results" / "DRIVE_SIM_20261007" / "S0" / "PREREG.json"


def chain(h, freqs):
    s, power, index, delay = signed_s_single_tx(h, freqs, tx=0)
    return s, index, delay * C0


def compare(h_b, h_ref, freqs):
    freqs = np.asarray(freqs)
    if freqs.ndim != 1 or len(freqs) < 2 or not np.isfinite(freqs).all() or not np.all(np.diff(freqs) > 0):
        raise ValueError("INVALID_FREQUENCIES")
    for name, h in (("candidate", h_b), ("reference", h_ref)):
        if np.shape(h) != (len(freqs), 2, 2) or not np.isfinite(h).all():
            raise ValueError(f"INVALID_H {name}: expected finite (n_freq, 2, 2)")
    if np.any(np.linalg.norm(h_ref.reshape(len(freqs), -1), axis=1) == 0):
        raise ValueError("ZERO_REFERENCE_POWER")
    pose = float(np.linalg.norm(h_b - h_ref) / np.linalg.norm(h_ref))
    per_bin = np.linalg.norm((h_b - h_ref).reshape(len(freqs), -1), axis=1) / np.linalg.norm(h_ref.reshape(len(freqs), -1), axis=1)
    sb, ib, rb = chain(h_b, freqs)
    sr, ir, rr = chain(h_ref, freqs)
    return dict(pose_rel_err=pose, per_bin_max=float(per_bin.max()), abs_ds=abs(sb - sr), fp_index_match=bool(ib == ir), range_diff_m=abs(rb - rr))


def summarize(rows, thr, prefix):
    if not rows:
        return dict(n_poses=0, thresholds=thr, checks=dict(nonempty=False), passed=False,
                    input_errors=["EMPTY_EVALUATION_SET"])
    keys = [pose_yaw_key(r["xy"], r["yaw_deg"]) for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_EVALUATION_POSE_YAW")
    numeric = ("pose_rel_err", "per_bin_max", "abs_ds", "range_diff_m")
    if any(not np.isfinite(r[k]) or r[k] < 0 for r in rows for k in numeric):
        raise ValueError("INVALID_COMPARISON_METRICS")
    if any(not isinstance(r["fp_index_match"], (bool, np.bool_)) for r in rows):
        raise ValueError("INVALID_FP_INDEX_MATCH")
    pose = np.array([r["pose_rel_err"] for r in rows])
    out = dict(n_poses=len(rows), pose_rel_err_median=float(np.median(pose)), pose_rel_err_max=float(pose.max()),
               per_bin_rel_err_max=float(max(r["per_bin_max"] for r in rows)), abs_ds_max=float(max(r["abs_ds"] for r in rows)),
               fp_index_match_fraction=float(np.mean([r["fp_index_match"] for r in rows])), range_diff_max_m=float(max(r["range_diff_m"] for r in rows)))
    checks = {}
    if "h_rel_err_median_max" in thr:
        checks["h_rel_err_median"] = out["pose_rel_err_median"] <= thr["h_rel_err_median_max"]
        checks["h_rel_err_max"] = out["pose_rel_err_max"] <= thr["h_rel_err_max"]
    checks["abs_ds_max"] = out["abs_ds_max"] <= thr["abs_ds_max"]
    checks["fp_index_match"] = out["fp_index_match_fraction"] >= thr["fp_index_match_min"]
    checks["range_diff_max_m"] = out["range_diff_max_m"] <= thr["range_diff_max_m"]
    out["thresholds"], out["checks"], out["passed"] = thr, checks, bool(all(checks.values()))
    worst = sorted(rows, key=lambda r: -r["abs_ds"])[:5]
    out["worst_by_abs_ds"] = [{k: (v if not isinstance(v, np.generic) else v.item()) for k, v in r.items()} for r in worst]
    return out


def coverage_checked(report: dict, missing: list, unusable: list) -> dict:
    """A15 (audit M01): a stored reference position without a usable trace is a failed gate, not a silently smaller sample."""
    report = dict(report)
    report["missing"], report["unusable"] = list(missing), list(unusable)
    report["checks"] = dict(report.get("checks", {}), coverage_complete=not missing and not unusable)
    report["passed"] = bool(report.get("passed", False) and not missing and not unusable)
    return report


AXIS_XY = (4.0, 0.0)       # anchor vertical axis; method B is degenerate exactly on it (S0 PREREG_AMENDMENTS A3)
AXIS_CLEARANCE_M = 0.01


def on_axis(xy) -> bool:
    return float(np.hypot(xy[0] - AXIS_XY[0], xy[1] - AXIS_XY[1])) < AXIS_CLEARANCE_M


def pose_yaw_key(xy, yaw):
    if len(xy) != 2 or not np.isfinite([*xy, yaw]).all():
        raise ValueError("INVALID_POSE_YAW")
    return (float(xy[0]), float(xy[1]), float(yaw))


def expected_manifest_keys(path):
    tasks = json.loads(Path(path).read_text())
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("EMPTY_OR_INVALID_G4_MANIFEST")
    keys, tags, ids = [], set(), set()
    for task in tasks:
        xy = [task["x"], task["y"]]
        yaws = task["antenna_yaw_deg"]
        tag = tag_of(*xy)
        if task["tag"] != tag or tag in tags or task["task_id"] in ids or not isinstance(yaws, list) or not yaws:
            raise ValueError("INVALID_OR_DUPLICATE_G4_TASK")
        tags.add(tag); ids.add(task["task_id"])
        keys.extend(pose_yaw_key(xy, yaw) for yaw in yaws)
    if len(keys) != len(set(keys)):
        raise ValueError("DUPLICATE_G4_MANIFEST_POSE_YAW")
    return set(keys)


def g4_coverage_checked(report, rows, expected):
    actual = [pose_yaw_key(r["xy"], r["yaw_deg"]) for r in rows]
    missing, unexpected = sorted(expected - set(actual)), sorted(set(actual) - expected)
    duplicate = len(actual) != len(set(actual))
    report = coverage_checked(report, missing, unexpected)
    report["duplicate_pose_yaw"] = duplicate
    report["expected_pose_yaw_count"] = len(expected)
    report["checks"]["unique_pose_yaw"] = not duplicate
    report["passed"] = bool(report["passed"] and expected and not duplicate)
    return report


def run_g4(a_dir, trace_dir, banks, freqs):
    rows = []
    for sub in sorted(p for p in a_dir.iterdir() if p.is_dir()):
        receipts, channels = list(sub.glob("*_receipt.json")), list(sub.glob("*_H.npy"))
        if len(receipts) != 1 or len(channels) != 1:
            raise ValueError(f"INVALID_G4_FILES {sub.name}: require exactly one receipt and H")
        r = json.loads(receipts[0].read_text())
        xy, yaws = r["robot_xy_m"], r["yaws"]
        if not isinstance(yaws, list) or not yaws or sub.name != tag_of(*xy):
            raise ValueError(f"INVALID_G4_RECEIPT {sub.name}")
        for yaw in yaws:
            pose_yaw_key(xy, yaw)
        ha = np.load(channels[0], allow_pickle=False)
        if ha.shape != (len(yaws), len(freqs), 2, 2) or not np.isfinite(ha).all():
            raise ValueError(f"INVALID_G4_H {sub.name}")
        trace = load_trace(Path(trace_dir) / f"{tag_of(*xy)}_trace.npz")
        hb = h_for_antenna_yaws(trace, banks, yaws)
        if hb.shape != ha.shape:
            raise ValueError(f"INVALID_G4_CANDIDATE_H {sub.name}")
        for yi, yaw in enumerate(yaws):
            rows.append(dict(tag=sub.name, xy=xy, yaw_deg=float(yaw), **compare(hb[yi], ha[yi], freqs)))
    return rows


def run_set(trace_dir, banks, refs, freqs):
    rows, missing, unusable = [], [], []
    if not refs:
        raise ValueError("EMPTY_REFERENCE_SET")
    keys = [pose_yaw_key(r["xy"], yaw) for r in refs for yaw in r["yaws"]]
    if not keys or len(keys) != len(set(keys)):
        raise ValueError("EMPTY_OR_DUPLICATE_REFERENCE_POSE_YAW")
    for r in refs:
        if on_axis(r["xy"]):
            continue
        tag = tag_of(*r["xy"])
        path = Path(trace_dir) / f"{tag}_trace.npz"
        if not path.exists():
            missing.append(tag)
            continue
        trace = load_trace(path)
        if trace["status"] != "OK":
            unusable.append(tag)
            continue
        Hs = np.load(r["h"])
        hb = h_for_antenna_yaws(trace, banks, r["yaws"])
        if Hs.shape != (len(r["yaws"]), len(freqs), 2, 2) or hb.shape != Hs.shape:
            raise ValueError(f"INVALID_REFERENCE_H_SHAPE {tag}")
        for yi, yaw in enumerate(r["yaws"]):
            row = compare(hb[yi], Hs[yi], freqs)
            rows.append(dict(tag=r["tag"], xy=r["xy"], yaw_deg=float(yaw), **row))
    return rows, missing, unusable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces-all", type=Path, help="bin-by-bin traces (rf_b_trace --nodes all) -> G2")
    ap.add_argument("--traces-nodes", type=Path, help="node-interpolated traces (e.g. --nodes 17) -> G2'")
    ap.add_argument("--g4-a-dir", type=Path, help="method-A runs at out-of-range yaws: <dir>/<tag>/<tag>_H.npy + receipt")
    ap.add_argument("--g4-manifest", type=Path, help="pre-execution G4 task manifest; exact expected pose/yaw set")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--g4-only", action="store_true", help="skip the stored-reference comparisons (used for the anchor-B check)")
    args = ap.parse_args()
    report = dict(prereg=str(PREREG.relative_to(ROOT)), input_errors=[])
    selected = []
    if not args.g4_only:
        if args.traces_all: selected.append("G2_bin_by_bin")
        if args.traces_nodes: selected.append("G2p_node_interpolation")
    if args.g4_a_dir: selected.append("G4_out_of_range_yaw")
    report["selected_gates"] = selected
    try:
        if not selected:
            raise ValueError("NO_GATES_SELECTED")
        if args.g4_only and not args.g4_a_dir:
            raise ValueError("G4_ONLY_REQUIRES_A_DIR")
        if args.g4_a_dir and (not args.g4_manifest or not (args.traces_all or args.traces_nodes)):
            raise ValueError("G4_REQUIRES_MANIFEST_AND_TRACES")
        if args.g4_manifest and not args.g4_a_dir:
            raise ValueError("G4_MANIFEST_WITHOUT_G4")
        expected = expected_manifest_keys(args.g4_manifest) if args.g4_a_dir else None
        gates = json.loads(PREREG.read_text())["config"]["gates"]
        thr = {k: {kk: vv["value"] for kk, vv in g.items()} for k, g in gates.items()}
        banks = load_banks()
        freqs = banks[0].freqs_hz
        refs = [] if args.g4_only else stored_positions()
        report.update(reference_positions=len(refs), excluded_on_anchor_axis=[r["tag"] for r in refs if on_axis(r["xy"])])
        for directory, name, threshold in ((args.traces_all, "G2_bin_by_bin", "G2_B_per_bin_trace"),
                                           (args.traces_nodes, "G2p_node_interpolation", "G2p_B_node_interpolation")):
            if directory and not args.g4_only:
                rows, miss, bad = run_set(directory, banks, refs, freqs)
                report[name] = coverage_checked(summarize(rows, thr[threshold], name), miss, bad)
        if args.g4_a_dir:
            rows = run_g4(args.g4_a_dir, args.traces_all or args.traces_nodes, banks, freqs)
            # Frozen G4 criteria say "same as G2", including when using node traces.
            g4 = g4_coverage_checked(summarize(rows, thr["G2_B_per_bin_trace"], "G4"), rows, expected)
            g4.update(threshold_source="S0/PREREG.json:G4 criteria same as G2",
                      trace_mode="bin_by_bin" if args.traces_all else "node_interpolation",
                      manifest=str(args.g4_manifest), manifest_sha256=hashlib.sha256(args.g4_manifest.read_bytes()).hexdigest(),
                      prereg_positions=gates["G4_out_of_range_yaw"]["positions"]["value"])
            report["G4_out_of_range_yaw"] = g4
    except (ValueError, TypeError, KeyError, IndexError, OSError, StopIteration) as exc:
        report["input_errors"].append(f"{type(exc).__name__}: {exc}")
    report["all_passed"] = bool(selected and not report["input_errors"] and
                                all(report.get(name, {}).get("passed", False) for name in selected))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, allow_nan=False))
    print(json.dumps(report, indent=1, allow_nan=False))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
