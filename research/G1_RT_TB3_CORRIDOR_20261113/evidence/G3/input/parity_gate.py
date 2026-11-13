"""S2 parity gates G2 / G2' (and G4) of method B against stored method-A channels.

  python scripts/drive_sim/parity_gate.py --traces-all DIR_BIN_BY_BIN --traces-nodes DIR_17_NODES --out PARITY_REPORT.json \
      [--g4-a-dir DIR_WITH_A_RUNS_AT_OUT_OF_RANGE_YAWS]

Reference = the stored ``*_H.npy`` of CORRIDOR_SWEEP_20261006 / CORRIDOR_SCAN_20261006 / CORRIDOR_SCAN2_20261007 (threads=1 runs, bit-reproduced in S0).
All chain quantities use the single-TX first-path rule (column 0 = TX +45).  Thresholds are read from S0/PREREG.json, not typed here.
"""
from __future__ import annotations

import argparse
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
    pose = float(np.linalg.norm(h_b - h_ref) / np.linalg.norm(h_ref))
    per_bin = np.linalg.norm((h_b - h_ref).reshape(len(freqs), -1), axis=1) / np.linalg.norm(h_ref.reshape(len(freqs), -1), axis=1)
    sb, ib, rb = chain(h_b, freqs)
    sr, ir, rr = chain(h_ref, freqs)
    return dict(pose_rel_err=pose, per_bin_max=float(per_bin.max()), abs_ds=abs(sb - sr), fp_index_match=bool(ib == ir), range_diff_m=abs(rb - rr))


def summarize(rows, thr, prefix):
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


def run_set(trace_dir, banks, refs, freqs):
    rows, missing, unusable = [], [], []
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
        for yi, yaw in enumerate(r["yaws"]):
            row = compare(hb[yi], Hs[yi], freqs)
            rows.append(dict(tag=r["tag"], xy=r["xy"], yaw_deg=float(yaw), **row))
    return rows, missing, unusable


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--traces-all", type=Path, help="bin-by-bin traces (rf_b_trace --nodes all) -> G2")
    ap.add_argument("--traces-nodes", type=Path, help="node-interpolated traces (e.g. --nodes 17) -> G2'")
    ap.add_argument("--g4-a-dir", type=Path, help="method-A runs at out-of-range yaws: <dir>/<tag>/<tag>_H.npy + receipt")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--g4-only", action="store_true", help="skip the stored-reference comparisons (used for the anchor-B check)")
    args = ap.parse_args()
    gates = json.loads(PREREG.read_text())["config"]["gates"]
    thr = {k: {kk: vv["value"] for kk, vv in g.items()} for k, g in gates.items()}
    banks = load_banks()
    freqs = banks[0].freqs_hz
    refs = [] if args.g4_only else stored_positions()
    report = dict(prereg=str(PREREG.relative_to(ROOT)), reference_positions=len(refs),
                  excluded_on_anchor_axis=[r["tag"] for r in refs if on_axis(r["xy"])])
    if args.traces_all and not args.g4_only:
        rows, miss, bad = run_set(args.traces_all, banks, refs, freqs)
        report["G2_bin_by_bin"] = coverage_checked(summarize(rows, thr["G2_B_per_bin_trace"], "G2"), miss, bad) if rows else dict(missing=miss, unusable=bad, passed=False)
    if args.traces_nodes and not args.g4_only:
        rows, miss, bad = run_set(args.traces_nodes, banks, refs, freqs)
        report["G2p_node_interpolation"] = coverage_checked(summarize(rows, thr["G2p_B_node_interpolation"], "G2p"), miss, bad) if rows else dict(missing=miss, unusable=bad, passed=False)
    if args.g4_a_dir and (args.traces_nodes or args.traces_all):
        trace_dir = args.traces_all or args.traces_nodes
        rows = []
        for sub in sorted(p for p in args.g4_a_dir.iterdir() if p.is_dir()):
            rec = next(sub.glob("*_receipt.json"))
            r = json.loads(rec.read_text())
            Ha = np.load(next(sub.glob("*_H.npy")))
            trace = load_trace(Path(trace_dir) / f"{tag_of(*r['robot_xy_m'])}_trace.npz")
            hb = h_for_antenna_yaws(trace, banks, r["yaws"])
            for yi, yaw in enumerate(r["yaws"]):
                rows.append(dict(tag=sub.name, xy=r["robot_xy_m"], yaw_deg=float(yaw), **compare(hb[yi], Ha[yi], freqs)))
        g4 = {k: v["value"] for k, v in gates["G4_out_of_range_yaw"].items() if k == "positions"}
        report["G4_out_of_range_yaw"] = summarize(rows, thr["G2_B_per_bin_trace"] if args.traces_all else thr["G2p_B_node_interpolation"], "G4") | dict(positions=g4)
    report["all_passed"] = all(v.get("passed", False) for k, v in report.items() if isinstance(v, dict) and k.startswith("G"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: (v.get("passed"), v.get("checks")) if isinstance(v, dict) and "passed" in v else v for k, v in report.items()}, indent=1))


if __name__ == "__main__":
    main()
