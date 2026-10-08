"""A21: position-dependent s mismatch variance.  Definitions: S0/PREREG_AMENDMENTS.md A21.

  python scripts/drive_sim/distance_sigma_experiment.py calib   --s1 S1 --h-dir S2 --lut-dir S4 --out DEV_RESULTS/DISTANCE_SIGMA_CALIB.json
  python scripts/drive_sim/distance_sigma_experiment.py heldout --s1 S1 --h-dir S2 --lut-dir S4 --calib DEV_RESULTS/DISTANCE_SIGMA_CALIB.json --out DEV_RESULTS/DISTANCE_SIGMA_HELDOUT.json
Calibration: R1 lateral 0.35 (noise-free residual).  Held-out: lateral 0.0, seeds 0..9.  Local R1 development H stores only.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

CAL_LAT, TEST_LAT, N_BINS = 0.35, 0.0, 5
BASE_S = ("range_s_P0", "range_s_P1_T20")
PERIODS = (None, 20.0)
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def setup_globals(a):
    setup = CorridorSetup()
    doc = json.loads((a.lut_dir / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(a.lut_dir / "hs_lut_2deg.npy")))
    with np.load(ROOT / "LP_plus45_bank.npz") as z:
        freqs = z["freqs_hz"]
    _G.update(lut=lut, freqs=freqs, anchor=tuple(setup.anchor_position), robot_z=setup.robot_antenna_z_m, range_offset=doc["range_bias"]["mean_m"], snr=[30.0, 10.0])
    E.POS_PROCESS_STD = 0.01


def worlds_for(a, lat, mount):
    h = np.load(a.h_dir / f"H_y{lat:g}_m{mount:g}.npy", mmap_mode="r")
    return {p: E.make_world(a.s1 / f"timeline_y{lat:g}_T{tag(p)}.csv", h, _G["freqs"], lat, mount, p) for p in PERIODS}


def rank(x):
    return pd.Series(np.asarray(x, float)).rank().to_numpy()


def spearman(a, b):
    return float(np.corrcoef(rank(a), rank(b))[0, 1])


def partial_spearman(y, x, z):
    ry, rx, rz = rank(y), rank(x), rank(z)
    A = np.column_stack([np.ones_like(rz), rz])
    res = lambda v: v - A @ np.linalg.lstsq(A, v, rcond=None)[0]  # noqa: E731
    return float(np.corrcoef(res(ry), res(rx))[0, 1])


def calibrate(a):
    recs = []
    for mount in (0.0, 45.0):
        w = worlds_for(a, CAL_LAT, mount)[None]
        obs = O.observe(w.h, w.freqs, None, None, return_h=True)
        tr = w.truth
        lut_s = s_model(_G["lut"], _G["anchor"], _G["robot_z"], tr[:, 0], tr[:, 1], tr[:, 2], mount)
        rho = np.hypot(tr[:, 0] - _G["anchor"][0], tr[:, 1] - _G["anchor"][1])
        geo = np.degrees(np.arctan2(rho, _G["anchor"][2] - _G["robot_z"]))
        _, en = O.rx_energy_s(obs["h_noisy"], 0.0)
        q = obs["power"].sum(1) / np.maximum(en.sum(1), 1e-300)
        keep = (w.t >= E.EXCLUDE_S) & np.isfinite(obs["s"])
        recs.append(pd.DataFrame(dict(r=(obs["s"] - lut_s)[keep], geo=geo[keep], q=q[keep], mount=mount)))
    d = pd.concat(recs, ignore_index=True)
    d["bin"] = pd.qcut(d.geo, N_BINS, labels=False)
    tab = d.groupby("bin").agg(n=("r", "size"), geo_lo=("geo", "min"), geo_hi=("geo", "max"), geo_center=("geo", "mean"), rms=("r", lambda x: float(np.sqrt((x ** 2).mean()))),
                               q_median=("q", "median")).reset_index()
    diag = dict(n=int(len(d)), rms=float(np.sqrt((d.r ** 2).mean())), table=tab.to_dict("records"), spearman_abs_r_vs_geo=spearman(d.r.abs(), d.geo),
                spearman_abs_r_vs_q=spearman(d.r.abs(), d.q), spearman_q_vs_geo=spearman(d.q, d.geo), partial_spearman_abs_r_vs_q_given_geo=partial_spearman(d.r.abs(), d.q, d.geo),
                partial_spearman_abs_r_vs_geo_given_q=partial_spearman(d.r.abs(), d.geo, d.q))
    diag["sigma_table"] = dict(knots_theta_geo_deg=[float(v) for v in tab.geo_center], sigma=[float(v) for v in tab.rms])
    return diag


def work(args):
    var, mount, seed, drift, si = args
    table = _G["tables"][var]
    cfgt = (lambda cfg, base: (setattr(cfg, "s_sigma_table", table), cfg)[1]) if table is not None else None
    rows, _ = E.run_unit(_G["worlds"][(TEST_LAT, mount)], _G["lut"], sensor=S.SensorNoise(), mismatch_sigma=0.18, anchor_xyz=_G["anchor"], robot_z=_G["robot_z"],
                         range_offset=_G["range_offset"], snr_db=_G["snr"][si], snr_idx=si, drift_idx=drift, seed=seed, compare_filters=False, cfg_transform=cfgt)
    return [dict(r, variant=var) for r in rows if r["baseline"] in BASE_S]


COLS = ["nees_mean", "nees_cov95", "heading_cov95", "heading_rmse_deg", "pos_rmse_m"]


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("calib", "heldout"):
        p = sub.add_parser(name)
        p.add_argument("--s1", type=Path, required=True)
        p.add_argument("--h-dir", type=Path, required=True)
        p.add_argument("--lut-dir", type=Path, required=True)
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--seeds", type=int, default=10)
        p.add_argument("--nproc", type=int, default=4)
        if name == "heldout":
            p.add_argument("--calib", type=Path, required=True)
    a = ap.parse_args()
    setup_globals(a)
    pd.set_option("display.width", 220, "display.max_rows", 200)
    if a.cmd == "calib":
        diag = calibrate(a)
        print(json.dumps({k: v for k, v in diag.items() if k != "table"}, indent=1))
        print(pd.DataFrame(diag["table"]).round(3).to_string(index=False))
        a.out.write_text(json.dumps(dict(definition="A21 calibration", **diag), indent=1))
        return
    cal = json.loads(a.calib.read_text())["sigma_table"]
    _G["tables"] = dict(V0=None, V3=(tuple(cal["knots_theta_geo_deg"]), tuple(cal["sigma"])))
    _G["worlds"] = {(TEST_LAT, m): worlds_for(a, TEST_LAT, m) for m in (0.0, 45.0)}
    units = [(v, m, s, d, si) for v in _G["tables"] for m in (0.0, 45.0) for d in (0, 1, 2) for si in range(2) for s in range(a.seeds)]
    rows = []
    with mp.get_context("fork").Pool(a.nproc) as pool:
        for i, r in enumerate(pool.imap(work, units, chunksize=1)):
            rows += r
            if i % 20 == 0:
                print("units", i, "/", len(units), flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(a.out.with_suffix(".csv"), index=False)
    ok = df[df.error.fillna("") == ""]
    g = ok.groupby(["variant", "baseline", "mount_deg"])
    t = g[COLS].mean().join(g[["heading_rmse_deg", "pos_rmse_m"]].median().add_suffix("_median")).join(g.size().rename("n")).reset_index()
    key = ["mount_deg", "drift", "snr_db", "seed", "baseline"]
    v0 = ok[ok.variant == "V0"].set_index(key)
    v3 = ok[ok.variant == "V3"].set_index(key)
    j = v3[["heading_rmse_deg"]].join(v0[["heading_rmse_deg"]], lsuffix="_v3", rsuffix="_v0", how="inner").reset_index()
    j["d"] = j.heading_rmse_deg_v3 - j.heading_rmse_deg_v0
    paired = j.groupby(["baseline", "mount_deg"]).agg(median_delta=("d", "median"), better=("d", lambda s: float((s < 0).mean())), worse=("d", lambda s: float((s > 0).mean())), n=("d", "size")).reset_index()
    t["acceptable"] = (t.nees_mean <= 6.0) & (t.nees_cov95 >= 0.90)
    print(t.round(3).to_string(index=False))
    print(paired.round(3).to_string(index=False))
    a.out.write_text(json.dumps(dict(definition="A21 held-out", sigma_table=cal, table=t.to_dict("records"), paired_vs_v0=paired.to_dict("records")), indent=1))


if __name__ == "__main__":
    main()
