"""First-path-power ratio |P1-P2| / |P1+P2| along the corridor yaw sweep.

P1, P2 = first-path power (CIR, project observation chain) of robot RX +45 / -45 for one
anchor TX port. Needs ``pos*/position_*_H.npy``; the LoS-only comparison also needs the
path-level ``position_*_sweep.npz`` when present.

  python scripts/corridor_analyze_fp.py --sweep-dir results/CORRIDOR_SWEEP_20261006
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from qclean_uwb.features.fp_power import first_path_power  # noqa: E402
from qclean_uwb.features.port_ratio import los_fp_power_ratio, port_difference_ratio  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

C0 = 299792458.0
TX = ("LP_plus45", "LP_minus45")
FREQ = 6250400000.0 + 1950000.0 * np.arange(257)


def sweep_fp(H):
    """H [yaw, bin, rx, tx] -> power [yaw, rx, tx], index [yaw], delay [yaw]."""
    out = [first_path_power(H[k], FREQ) for k in range(H.shape[0])]
    return np.array([o[0] for o in out]), np.array([o[1] for o in out]), np.array([o[2] for o in out])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sweep-dir", type=Path, default=ROOT / "results" / "CORRIDOR_SWEEP_20261006")
    args = ap.parse_args()
    setup = CorridorSetup()
    yaws = np.array(setup.yaw_sweep_deg)
    ideal = los_fp_power_ratio(yaws)
    series, rows, checks = [], [], []
    for pos, (x, y) in enumerate(setup.example_xy_m):
        H = np.load(args.sweep_dir / f"pos{pos}" / f"position_{pos}_H.npy")
        assert H.shape == (len(yaws), 257, 2, 2) and np.isfinite(H).all()
        P, idx, delay = sweep_fp(H)
        los_P = None
        npz = args.sweep_dir / f"pos{pos}" / f"position_{pos}_sweep.npz"
        if npz.exists():
            from corridor_analyze import los_only_H
            los_P, _, _ = sweep_fp(los_only_H(np.load(npz))[0])
        g = setup.link_geometry(x, y, 0.0)
        dt = 1.0 / (1028 * 1.95e6)
        checks.append(dict(position=pos, xy=[x, y], range_m=round(g["range_m"], 3), geometric_delay_ns=round(g["range_m"] / C0 * 1e9, 3),
                           first_path_index_min=int(idx.min()), first_path_index_max=int(idx.max()),
                           first_path_delay_ns_median=round(float(np.median(delay)) * 1e9, 3), tap_ns=round(dt * 1e9, 4),
                           delay_minus_geometric_taps_max=round(float(np.max(np.abs(delay - g["range_m"] / C0))) / dt, 2),
                           ratio_in_unit_interval=bool(np.all((P[:, 0] >= 0) & (P[:, 1] >= 0)))))
        for ti, tname in enumerate(TX):
            p1, p2 = P[:, 0, ti], P[:, 1, ti]
            ratio = port_difference_ratio(p1, p2)
            lr = port_difference_ratio(los_P[:, 0, ti], los_P[:, 1, ti]) if los_P is not None else None
            series.append(dict(position=pos, xy=[x, y], tx_port=tname, range_m=g["range_m"], yaw_deg=yaws.tolist(), ratio=ratio.tolist(),
                               ratio_los_only=None if lr is None else lr.tolist(), p1_db=(10 * np.log10(p1)).tolist(), p2_db=(10 * np.log10(p2)).tolist(),
                               first_path_index=idx.tolist()))
            for k, yaw in enumerate(yaws):
                rows.append(dict(position=pos, x_m=x, y_m=y, tx_port=tname, yaw_deg=yaw, fp_index=int(idx[k]), p1_fp_power=p1[k], p2_fp_power=p2[k],
                                 p1_db=10 * np.log10(p1[k]), p2_db=10 * np.log10(p2[k]), ratio=ratio[k],
                                 ratio_los_only="" if lr is None else lr[k], ratio_ideal=ideal[k]))
    p0 = [s for s in series if s["position"] == 0]
    dev = {s["tx_port"]: dict(max_abs_dev_full=float(np.max(np.abs(np.array(s["ratio"]) - ideal))),
                              max_abs_dev_los_only=None if s["ratio_los_only"] is None else float(np.max(np.abs(np.array(s["ratio_los_only"]) - ideal))))
           for s in p0}
    validation = dict(status="FP_POWER_RATIO_ANALYSED", metric="abs(P1-P2)/abs(P1+P2); P=|CIR[first_path_index]|^2 per RX port, Hann 1028-tap CIR, 30% leading edge on strongest of 4 branches, noise-free",
                      per_position=checks, on_axis_vs_ideal_abs_ratio_deviation=dev, ideal="abs(cos(2*yaw))",
                      notes=["No receiver noise added; clean H from PathSolver.", "LoS-only = H from interaction-free paths, own first-path detection."])
    out = args.sweep_dir
    with (out / "fp_ratio_table.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    (out / "fp_ratio_series.json").write_text(json.dumps(dict(series=series, ideal=dict(yaw_deg=yaws.tolist(), ratio=ideal.tolist())), indent=1))
    (out / "FP_VALIDATION.json").write_text(json.dumps(validation, indent=2))
    print(json.dumps(dict(rows=len(rows), deviation=dev, checks=[(c["position"], c["first_path_index_min"], c["first_path_index_max"], c["delay_minus_geometric_taps_max"]) for c in checks])))


if __name__ == "__main__":
    main()
