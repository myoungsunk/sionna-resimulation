"""A17: filter-consistency diagnosis (calib) and held-out evaluation (heldout).  Definitions: S0/PREREG_AMENDMENTS.md A17.

  python scripts/drive_sim/consistency_diagnostics.py calib   --s1 S1 --h-dir S2 --lut-dir S4 --out DEV_RESULTS/CONSISTENCY_CALIB.json  [--seeds 10]
  python scripts/drive_sim/consistency_diagnostics.py heldout --s1 S1 --h-dir S2 --lut-dir S4 --calib DEV_RESULTS/CONSISTENCY_CALIB.json --out DEV_RESULTS/CONSISTENCY_HELDOUT.json
Calibration set: lateral 0.35, seeds 1000..1009.  Held-out set: lateral 0.0, seeds 0..9.  Local R1 development H stores only.

Implementation choices fixed before any result: the autocorrelation used for kappa is the uncentred second-moment one, rho_k = sum r_i r_{i+k} / sum r_i^2
(it matches the rms sigma_mismatch the filter uses); the centred autocorrelation is reported next to it.  E1/E2 range = true range + offset + N(0, 0.05^2 + 0.149^2/12 + 0.05^2).
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import filters as F  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

PERIODS = (None, 20.0)
BASE_ALL = ("odom_imu", "gyro_only", "range_s_P0", "range_s_P1_T20")
BASE_S = ("range_s_P0", "range_s_P1_T20")
RANGE_VAR = 0.05 ** 2 + 0.149 ** 2 / 12.0 + 0.05 ** 2
CAL_SEED0, CAL_LAT, TEST_LAT = 1000, 0.35, 0.0
LAGS = (1, 2, 5, 10, 25)
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


# ------------------------------------------------------------------ variants
def synth_obs(white_sigma):
    def f(obs, world, rng):
        truth = world.truth
        lut = _G["lut"]
        s0 = s_model(lut, _G["anchor"], _G["robot_z"], truth[:, 0], truth[:, 1], truth[:, 2], world.mount_deg)
        tap_var = 6.0 * obs["noise_var"]
        p1, p2 = obs["power"][:, 0], obs["power"][:, 1]
        thermal = np.array([F.thermal_var_s(a, b, tap_var) if tap_var > 0 and np.isfinite(a) and np.isfinite(b) else 0.0 for a, b in zip(p1, p2)])
        s = s0 + np.sqrt(np.maximum(thermal, 0.0)) * rng.standard_normal(len(s0)) + white_sigma * rng.standard_normal(len(s0))
        a = np.asarray(_G["anchor"])
        d = np.sqrt((truth[:, 0] - a[0]) ** 2 + (truth[:, 1] - a[1]) ** 2 + (a[2] - _G["robot_z"]) ** 2)
        obs = dict(obs)
        obs["s"] = np.where(obs["detected"], s, np.nan)
        obs["range_m"] = d + obs["range_offset"] + np.sqrt(RANGE_VAR) * rng.standard_normal(len(d))
        return obs
    return f


def no_wheelbase_error(drift):
    return dict(drift, e_b=0.0)


def no_odom_heading(cfg, base):
    if base["name"] in BASE_S:
        cfg.use_odom_heading = False
    return cfg


VARIANTS = {"E0": {}, "E1": dict(obs_transform=synth_obs(0.0)), "E2": dict(obs_transform=synth_obs(0.18)), "E3": dict(drift_transform=no_wheelbase_error),
            "E4": dict(cfg_transform=no_odom_heading)}


def work_calib(args):
    var, lat, mount, seed, drift, si = args
    rows, _ = E.run_unit(_G["worlds"][(lat, mount)], _G["lut"], sensor=S.SensorNoise(), mismatch_sigma=0.18, anchor_xyz=_G["anchor"], robot_z=_G["robot_z"],
                         range_offset=_G["range_offset"], snr_db=_G["snr"][si], snr_idx=si, drift_idx=drift, seed=seed, compare_filters=False, **VARIANTS[var])
    keep = BASE_ALL if var == "E0" else BASE_S
    return [dict(r, variant=var) for r in rows if r["baseline"] in keep]


def work_heldout(args):
    var, mount, seed, drift, si = args
    v = _G["variants"][var]
    cfgt = (lambda cfg, base: (setattr(cfg, "s_var_inflation", v["kappa"]), cfg)[1])
    rows, _ = E.run_unit(_G["worlds"][(TEST_LAT, mount)], _G["lut"], sensor=S.SensorNoise(), mismatch_sigma=v["sigma"], anchor_xyz=_G["anchor"], robot_z=_G["robot_z"],
                         range_offset=_G["range_offset"], snr_db=_G["snr"][si], snr_idx=si, drift_idx=drift, seed=seed, compare_filters=False, cfg_transform=cfgt)
    keep = BASE_ALL if var == "V0" else BASE_S
    return [dict(r, variant=var) for r in rows if r["baseline"] in keep]


# ------------------------------------------------------------------ residual statistics (part B)
def acf(r, lags, centred):
    r = np.asarray(r, float)
    if centred:
        r = r - r.mean()
    den = float(np.sum(r * r))
    return {k: float(np.sum(r[:-k] * r[k:]) / den) for k in lags}


def residual_stats(a):
    out = {}
    pooled = []
    for mount in (0.0, 45.0):
        w = worlds_for(a, CAL_LAT, mount)[None]
        meas = O.observe(w.h, w.freqs, None, None)["s"]
        tr = w.truth
        lut_s = s_model(_G["lut"], _G["anchor"], _G["robot_z"], tr[:, 0], tr[:, 1], tr[:, 2], mount)
        keep = (w.t >= E.EXCLUDE_S) & np.isfinite(meas)
        r = (meas - lut_s)[keep]
        pooled.append(r)
        raw, cen = acf(r, LAGS, False), acf(r, LAGS, True)
        # kappa: first lag with rho <= 0 or 50, truncated; sum of the uncentred correlations
        full = acf(r, tuple(range(1, 51)), False)
        k_end = next((k for k in range(1, 51) if full[k] <= 0.0), 50)
        kappa = max(1.0, 1.0 + 2.0 * sum(full[k] for k in range(1, k_end)))
        out[f"m{mount:g}"] = dict(n=int(keep.sum()), mean=float(r.mean()), std=float(r.std()), rms=float(np.sqrt(np.mean(r ** 2))), acf_uncentred=raw, acf_centred=cen,
                                  kappa=float(kappa), kappa_last_lag=int(k_end - 1))
    r = np.concatenate(pooled)
    out["pooled"] = dict(n=int(r.size), rms=float(np.sqrt(np.mean(r ** 2))), kappa_mean_of_mounts=float(np.mean([out["m0"]["kappa"], out["m45"]["kappa"]])))
    return out


# ------------------------------------------------------------------ summaries
COLS = ["nees_mean", "nees_cov95", "heading_cov95", "heading_rmse_deg", "pos_rmse_m"]


def summarize(df):
    d = df[df.error.fillna("") == ""]
    g = d.groupby(["variant", "baseline", "mount_deg"])
    t = g[COLS].mean().join(g[["heading_rmse_deg", "pos_rmse_m"]].median().add_suffix("_median")).join(g.size().rename("n"))
    return t.reset_index()


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
        stats = residual_stats(a)
        _G["worlds"] = {(CAL_LAT, m): worlds_for(a, CAL_LAT, m) for m in (0.0, 45.0)}
        units = [(v, CAL_LAT, m, CAL_SEED0 + s, d, si) for v in VARIANTS for m in (0.0, 45.0) for d in (0, 1, 2) for si in range(2) for s in range(a.seeds)]
        rows = []
        with mp.get_context("fork").Pool(a.nproc) as pool:
            for i, r in enumerate(pool.imap(work_calib, units, chunksize=1)):
                rows += r
                if i % 20 == 0:
                    print("units", i, "/", len(units), flush=True)
        df = pd.DataFrame(rows)
        df.to_csv(a.out.with_suffix(".csv"), index=False)
        t = summarize(df)
        print(t.round(3).to_string(index=False))
        a.out.write_text(json.dumps(dict(definition="A17 calibration set", residual_stats=stats, table=t.to_dict("records")), indent=1))
    else:
        cal = json.loads(a.calib.read_text())["residual_stats"]
        sigma_cal, kappa_cal = cal["pooled"]["rms"], cal["pooled"]["kappa_mean_of_mounts"]
        variants = dict(V0=dict(sigma=0.18, kappa=1.0), V1=dict(sigma=sigma_cal, kappa=1.0), V2=dict(sigma=sigma_cal, kappa=kappa_cal))
        _G["variants"] = variants
        _G["worlds"] = {(TEST_LAT, m): worlds_for(a, TEST_LAT, m) for m in (0.0, 45.0)}
        units = [(v, m, s, d, si) for v in variants for m in (0.0, 45.0) for d in (0, 1, 2) for si in range(2) for s in range(a.seeds)]
        rows = []
        with mp.get_context("fork").Pool(a.nproc) as pool:
            for i, r in enumerate(pool.imap(work_heldout, units, chunksize=1)):
                rows += r
                if i % 20 == 0:
                    print("units", i, "/", len(units), flush=True)
        df = pd.DataFrame(rows)
        df.to_csv(a.out.with_suffix(".csv"), index=False)
        t = summarize(df)
        print(variants)
        print(t.round(3).to_string(index=False))
        a.out.write_text(json.dumps(dict(definition="A17 held-out set", variants=variants, table=t.to_dict("records")), indent=1))


if __name__ == "__main__":
    main()
