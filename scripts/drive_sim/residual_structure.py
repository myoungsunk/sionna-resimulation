"""A19 exploratory: (a) structure of the LUT residual, (b) drive-segment slope versus the stored P0 error and the probe gain.  Definitions: PREREG_AMENDMENTS A19."""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402


def rows_of(path):
    return [dict(x=float(r["x"]), y=float(r["y"]), yaw=math.radians(float(r["yaw_body_deg"])), drive_g=int(r["drive_g"]), probe_id=int(r["probe_id"]))
            for r in csv.DictReader(Path(path).open())]


def part_a(a, lut, setup, freqs):
    recs = []
    for lat in (0.0, 0.35):
        for mount in (0.0, 45.0):
            h = np.load(a.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
            w = E.make_world(a.s1 / f"timeline_y{lat:g}_Tnone.csv", h, freqs, lat, mount, None)
            tr = w.truth
            meas = O.observe(w.h, w.freqs, None, None)["s"]
            sv, jac = s_model(lut, setup.anchor_position, setup.robot_antenna_z_m, tr[:, 0], tr[:, 1], tr[:, 2], mount, with_jac=True)
            rho = np.hypot(tr[:, 0] - setup.anchor_position[0], tr[:, 1] - setup.anchor_position[1])
            geo = np.degrees(np.arctan2(rho, setup.anchor_position[2] - setup.robot_antenna_z_m))
            keep = (w.t >= E.EXCLUDE_S) & np.isfinite(meas)
            yaw_a = (np.degrees(tr[:, 2]) + mount) % 180.0
            recs.append(pd.DataFrame(dict(r=(meas - sv)[keep], yaw_a=yaw_a[keep], slope=np.abs(jac[:, 2])[keep] * math.pi / 180.0, geo=geo[keep], mount=mount, lat=lat)))
    d = pd.concat(recs, ignore_index=True)
    out = dict(n=int(len(d)), rms=float(np.sqrt((d.r ** 2).mean())))
    d["yaw_bin"] = (d.yaw_a // 15 * 15).astype(int)
    g = d.groupby("yaw_bin").r.agg(n="size", rms=lambda x: float(np.sqrt((x ** 2).mean())), mean="mean")
    out["by_antenna_yaw_bin_deg"] = {int(k): dict(n=int(v.n), rms=float(v.rms), mean=float(v["mean"])) for k, v in g.iterrows()}
    sq = (d.r ** 2).groupby(d.yaw_bin).sum()
    out["worst_yaw_bin_share_of_squared_residual"] = float(sq.max() / sq.sum())
    for col in ("slope", "geo"):
        d[col + "_t"] = pd.qcut(d[col], 3, labels=["low", "mid", "high"])
        gg = d.groupby(col + "_t", observed=True).r.agg(n="size", rms=lambda x: float(np.sqrt((x ** 2).mean())))
        out[f"by_{col}_tercile"] = {str(k): dict(n=int(v.n), rms=float(v.rms), edge_hi=float(d[d[col + "_t"] == k][col].max())) for k, v in gg.iterrows()}
    out["corr_abs_r_vs_slope"] = float(np.corrcoef(d.r.abs(), d.slope)[0, 1])
    return out


def empirical(a):
    rows = []
    for f in sorted(Path(a.s6_r1).glob("results_y*_m*.csv")):
        d1 = pd.read_csv(f)
        if "route" not in d1:                       # v1 R1 files predate the route/anchor columns
            d1["route"], d1["anchor"] = "R1", "A"
        rows.append(d1)
    for f in sorted(Path(a.s6_routes).glob("results_R*_a*_m*.csv")):
        rows.append(pd.read_csv(f))
    d = pd.concat(rows, ignore_index=True)
    d = d[(d["filter"] == "ekf") & d.baseline.isin(["range_s_P0", "range_s_P1_T10"])]
    return d.groupby(["route", "anchor", "lateral", "mount_deg", "baseline"]).heading_rmse_deg.median().unstack("baseline").reset_index()


def part_b(a, lut):
    emp = empirical(a)
    recs = []
    cases = [("R1", "A", lat, a.s1 / f"timeline_y{lat:g}_Tnone.csv") for lat in (0.0, 0.35)]
    cases += [(r, an, 0.0, a.s1 / "routes" / f"timeline_{r}_Tnone.csv") for r in ("R2", "R4", "R5") for an in ("A", "B")]
    for route, an, lat, path in cases:
        setup = CorridorSetup(anchor_x_m=4.0 if an == "A" else 10.0)
        rows = rows_of(path)
        keep = np.array([r["probe_id"] < 0 and r["drive_g"] >= 150 for r in rows])
        x, y, yaw = (np.array([r[k] for r in rows]) for k in ("x", "y", "yaw"))
        for mount in (0.0, 45.0):
            _, jac = s_model(lut, setup.anchor_position, setup.robot_antenna_z_m, x, y, yaw, mount, with_jac=True)
            sl = np.abs(jac[:, 2])[keep] * math.pi / 180.0
            e = emp[(emp.route == route) & (emp.anchor == an) & (emp.mount_deg == mount) & ((emp.lateral == lat) | (route != "R1"))]
            if route != "R1":
                e = e.iloc[:1]
            recs.append(dict(route=route, anchor=an, lateral=lat, mount_deg=mount, mean_slope=float(sl.mean()), flat_share=float((sl < 0.01).mean()),
                             p0=float(e["range_s_P0"].iloc[0]), t10=float(e["range_s_P1_T10"].iloc[0])))
    d = pd.DataFrame(recs)
    d["gain"] = d.p0 - d.t10
    out = dict(cases=recs)
    for k in ("mean_slope", "flat_share"):
        out[f"spearman_{k}_vs_p0"] = float(d[k].corr(d.p0, method="spearman"))
        out[f"spearman_{k}_vs_gain"] = float(d[k].corr(d.gain, method="spearman"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--h-dir", type=Path, required=True)
    ap.add_argument("--lut-dir", type=Path, required=True)
    ap.add_argument("--s6-r1", type=Path, required=True)
    ap.add_argument("--s6-routes", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    meta = json.loads((a.lut_dir / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(meta["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["meta"]["phi_deg"][2]), s=np.load(a.lut_dir / "hs_lut_2deg.npy")))
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    setup = CorridorSetup()
    res = dict(definition="A19", a_residual_structure=part_a(a, lut, setup, freqs), b_drive_slope_vs_probe_need=part_b(a, lut))
    a.out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res["a_residual_structure"], indent=1)[:2500])
    print(json.dumps({k: v for k, v in res["b_drive_slope_vs_probe_need"].items() if k != "cases"}, indent=1))
    for c in res["b_drive_slope_vs_probe_need"]["cases"]:
        print(c["route"], c["anchor"], c["lateral"], int(c["mount_deg"]), "slope %.4f flat %.2f  P0 %.2f T10 %.2f" % (c["mean_slope"], c["flat_share"], c["p0"], c["t10"]))


if __name__ == "__main__":
    main()
