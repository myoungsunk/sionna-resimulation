"""Yaw estimation with the analytic first-order multipath model as the a-priori template, plus robustness to model errors.

Template variants (all computed from coordinates + environment only; nothing is fitted to the measured curve):
  los          angle model, LoS only (previous best a-priori template)
  mp_all       LoS + analytic first-order reflections of all six surfaces
  mp_ceiling   LoS + ceiling only;  mp_ceiling_walls: LoS + ceiling + side walls
  mp_all with: material eps/sigma x0.8 and x1.2, wall position +-5 cm, robot coordinate error 0.1 / 0.25 / 0.5 m
Evaluation matches corridor_template_compare.py: nearest-to-true candidate (oracle), coarse prior +-15 deg, and whole-sweep matching.

  python scripts/corridor_multipath_template.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_case_check as cc  # noqa: E402
import corridor_multipath_model as mm  # noqa: E402
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

YAWS = sf.YAWS
DENSE = np.arange(0, 361) / 2.0           # 0..180 deg, 0.5 deg
OFFSETS = np.arange(-450, 451) / 10.0
rng = np.random.default_rng(20261006)


def template_signed(banks, setup, a_pos, r_pos, surfaces, mat_scale=1.0, wall_offset=0.0):
    """Signed ratio of the template on the 0.1 deg grid for both TX ports."""
    H = mm.channels(banks, setup, a_pos, r_pos, DENSE, surfaces=surfaces, material_scale=mat_scale, wall_offset_m=wall_offset)
    total = sum(H.values())
    idx = mm.detect_idx(total)
    c = sum(mm.tap_fields({g: h for g, h in H.items()}, idx).values())
    return {tn: np.interp(cc.GRID, DENSE, sf.signed(c, t)) for t, tn in enumerate(sf.TX)}


def oracle_errors(s_meas, curve):
    e = []
    for k, y in enumerate(YAWS):
        cand = cc.invert(abs(s_meas[k]), curve)
        e.append(float(cand[np.argmin(np.abs(cand - y))] - y))
    return np.array(e)


def prior_errors(s_meas, curve, prior_deg=15.0, draws=10):
    e = []
    for k, y in enumerate(YAWS):
        cand = cc.invert(abs(s_meas[k]), curve)
        for _ in range(draws):
            e.append(float(cand[np.argmin(np.abs(cand - (y + rng.uniform(-prior_deg, prior_deg))))] - y))
    return np.array(e)


def sweep_offset(r_meas, s_model_dense_wide):
    """Whole-sweep matching of |s_meas| to |template(yaw + delta)|, delta in +-45 deg (template known on -60..240)."""
    sse = [np.sum((r_meas - np.abs(np.interp(YAWS + d, WIDE, s_model_dense_wide))) ** 2) for d in OFFSETS]
    return float(OFFSETS[int(np.argmin(sse))])


WIDE = np.arange(-120, 481) / 2.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "results" / "CORRIDOR_SCAN_20261006" / "MULTIPATH_TEMPLATE.json")
    ap.add_argument("--skip-sweep", action="store_true")
    args = ap.parse_args()
    setup, banks = CorridorSetup(), sf.Banks()
    shift = json.loads((ROOT / "results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json").read_text())
    variants = {
        "los": dict(surfaces=()),
        "mp_ceiling": dict(surfaces=("ceiling",)),
        "mp_ceiling_walls": dict(surfaces=("ceiling", "wall_y_neg", "wall_y_pos")),
        "mp_all": dict(surfaces=tuple(mm.SURFACES)),
        "mp_all_material_x0.8": dict(surfaces=tuple(mm.SURFACES), mat_scale=0.8),
        "mp_all_material_x1.2": dict(surfaces=tuple(mm.SURFACES), mat_scale=1.2),
        "mp_all_wall_+5cm": dict(surfaces=tuple(mm.SURFACES), wall_offset=0.05),
        "mp_all_wall_-5cm": dict(surfaces=tuple(mm.SURFACES), wall_offset=-0.05),
    }
    err = {k: [] for k in list(variants) + ["ideal", "mp_all_coord_0.1m", "mp_all_coord_0.25m", "mp_all_coord_0.5m"]}
    pri = {k: [] for k in err}
    sweep = {k: [] for k in ("los", "mp_all")}
    curves = []
    for p in sorted(shift["positions"], key=lambda q: (q["x"], q["y"])):
        if p["off_boresight_deg"] < 1:
            continue
        z = np.load(ROOT / p["file"])
        a_pos, r_pos = z["anchor_m"], z["robot_antenna_m"]
        meas = {tn: np.array(p["tx"][tn]["s_full"]) for tn in sf.TX}
        tmpl = {name: template_signed(banks, setup, a_pos, r_pos, **kw) for name, kw in variants.items()}
        coord = {}
        for lvl in (0.1, 0.25, 0.5):
            acc = {tn: [] for tn in sf.TX}
            for ang in (0, 90, 180, 270):
                r2 = r_pos + np.array([lvl * np.cos(np.radians(ang)), lvl * np.sin(np.radians(ang)), 0.0])
                tt = template_signed(banks, setup, a_pos, r2, tuple(mm.SURFACES))
                for tn in sf.TX:
                    acc[tn].append(tt[tn])
            coord[lvl] = acc
        for tn in sf.TX:
            row = dict(x=p["x"], y=p["y"], tx=tn)
            for name in variants:
                cv = np.abs(tmpl[name][tn])
                e = oracle_errors(meas[tn], cv)
                err[name].append(e)
                pri[name].append(prior_errors(meas[tn], cv))
                row[f"rmse_{name}"] = float(np.sqrt(np.mean(e ** 2)))
            ideal = np.abs(np.cos(2 * cc.GP))
            err["ideal"].append(oracle_errors(meas[tn], ideal))
            pri["ideal"].append(prior_errors(meas[tn], ideal))
            for lvl in (0.1, 0.25, 0.5):
                es = [oracle_errors(meas[tn], np.abs(t)) for t in coord[lvl][tn]]
                err[f"mp_all_coord_{lvl}m"].append(np.concatenate(es))
                pri[f"mp_all_coord_{lvl}m"].append(np.concatenate([prior_errors(meas[tn], np.abs(t)) for t in coord[lvl][tn]]))
            if not args.skip_sweep:
                for name in ("los", "mp_all"):
                    kw = variants[name]
                    Hw = mm.channels(banks, setup, a_pos, r_pos, WIDE, surfaces=kw["surfaces"])
                    tot = sum(Hw.values())
                    c = sum(mm.tap_fields(Hw, mm.detect_idx(tot)).values())
                    sweep[name].append(sweep_offset(np.abs(meas[tn]), sf.signed(c, sf.TX.index(tn))))
            curves.append(row)
    summ = {}
    for k in err:
        a = np.concatenate([np.ravel(v) for v in err[k]])
        b = np.concatenate([np.ravel(v) for v in pri[k]])
        summ[k] = dict(rmse=float(np.sqrt(np.mean(a ** 2))), median_abs=float(np.median(np.abs(a))), within5=float(np.mean(np.abs(a) <= 5)), p90_abs=float(np.percentile(np.abs(a), 90)), max_abs=float(np.abs(a).max()),
                       prior15_rmse=float(np.sqrt(np.mean(b ** 2))), prior15_within5=float(np.mean(np.abs(b) <= 5)), prior15_wrong_branch=float(np.mean(np.abs(b) > 20)))
    sw = {k: dict(rmse=float(np.sqrt(np.mean(np.square(v)))), median_abs=float(np.median(np.abs(v))), max_abs=float(np.max(np.abs(v)))) for k, v in sweep.items() if v}
    args.out.write_text(json.dumps(dict(summary=summ, sweep_matching=sw, curves=curves, n_curves=len(curves)), indent=1))
    for k, v in summ.items():
        print(f"{k:24s} oracle RMSE {v['rmse']:5.2f} median {v['median_abs']:5.2f} within5 {v['within5']*100:3.0f}% max {v['max_abs']:5.1f} | prior+-15: RMSE {v['prior15_rmse']:5.2f} within5 {v['prior15_within5']*100:3.0f}% wrong {v['prior15_wrong_branch']*100:4.1f}%")
    print("sweep matching offset RMSE:", {k: round(v["rmse"], 2) for k, v in sw.items()})


if __name__ == "__main__":
    main()
