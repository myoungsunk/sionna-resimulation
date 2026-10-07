"""DRIVE_SIM S0 reference checks on stored corridor H (no Sionna needed except for loading banks).

1. FP-rule impact: old 4-branch rule vs single-port (TX column) rule on every stored position/yaw.
2. G1 (A-method reproducibility): a freshly computed pilot H vs the stored H of the same position/yaw/bin.

  python scripts/drive_sim_s0_reference_check.py --out results/DRIVE_SIM_20261007/S0/REFERENCE_CHECK.json \
      --pilot results/DRIVE_SIM_20261007/S0/pilot_t4/pilot_sweep.npz
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))
from qclean_uwb.features.fp_power import first_path_power, first_path_power_single_tx, signed_port_ratio  # noqa: E402

REF_DIRS = ["CORRIDOR_SWEEP_20261006", "CORRIDOR_SCAN_20261006", "CORRIDOR_SCAN2_20261007"]


def stored_positions():
    rows = []
    for d in REF_DIRS:
        for rec in sorted((ROOT / "results" / d).glob("*/*_receipt.json")):
            r = json.loads(rec.read_text())
            h = rec.with_name(rec.name.replace("_receipt.json", "_H.npy"))
            if h.exists():
                rows.append(dict(dir=d, tag=r.get("tag", rec.parent.name), xy=r["robot_xy_m"], yaws=r["yaws"], h=h, bin_stride=r.get("bin_stride", 1)))
    return rows


def stats(v):
    v = np.asarray(v, float)
    return dict(n=int(v.size), median=float(np.median(v)), p95=float(np.percentile(v, 95)), max=float(v.max()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pilot", type=Path, nargs="*", default=[])
    args = ap.parse_args()
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freq = z["freqs_hz"]
    rows = stored_positions()
    changed, ds, ds_all, per_tx = [], [], [], {0: [], 1: []}
    for r in rows:
        H = np.load(r["h"])
        for yi in range(H.shape[0]):
            h = H[yi]  # (bin, rx, tx)
            p4, i4, _ = first_path_power(h, freq)
            for tx in (0, 1):
                p1, i1, _ = first_path_power_single_tx(h, freq, tx)
                s_old = float(signed_port_ratio(p4[0, tx], p4[1, tx]))
                s_new = float(signed_port_ratio(p1[0], p1[1]))
                per_tx[tx].append((i4 != i1, abs(s_new - s_old)))
                ds_all.append(abs(s_new - s_old))
    out = dict(positions=len(rows), poses=sum(1 for _ in range(len(per_tx[0]))), freq_bins=int(freq.size),
               fp_rule_impact={f"tx{tx}": dict(fp_index_changed_fraction=float(np.mean([c for c, _ in v])),
                                              abs_delta_s=stats([d for _, d in v]),
                                              n_abs_delta_s_gt_1em3=int(sum(d > 1e-3 for _, d in v))) for tx, v in per_tx.items()},
               positions_list=[dict(tag=r["tag"], xy=r["xy"], n_yaw=len(r["yaws"])) for r in rows])
    g1 = []
    for pilot in args.pilot:
        with np.load(pilot) as z:
            Hn, yaws, bins, xy = z["H"], list(z["yaw_deg"]), z["bin_index"], z["robot_xy_m"].tolist()
        match = [r for r in rows if np.allclose(r["xy"], xy)]
        assert match, f"no stored reference for {xy}"
        Hr = np.load(match[0]["h"])
        for yi, yaw in enumerate(yaws):
            ref = Hr[match[0]["yaws"].index(float(yaw))][bins]
            d = np.linalg.norm((Hn[yi] - ref).reshape(len(bins), -1), axis=1) / np.linalg.norm(ref.reshape(len(bins), -1), axis=1)
            pose = float(np.linalg.norm(Hn[yi] - ref) / np.linalg.norm(ref))
            g1.append(dict(pilot=str(pilot), tag=match[0]["tag"], yaw_deg=float(yaw), n_bins=int(len(bins)),
                           per_bin_rel_err=stats(d), per_pose_rel_err=pose, passed_1e_6=bool(d.max() <= 1e-6)))
    out["G1_pilot_vs_stored"] = g1
    args.out.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("positions", "poses", "fp_rule_impact")}, indent=1))
    print(json.dumps(g1, indent=1))


if __name__ == "__main__":
    main()
