"""A23: does a structured (biased, autocorrelated) s / range error reproduce the NEES inflation of the real RF observation?  Spec: REQUESTS/CAUSE_CHECK_SPEC_AND_DATA_REQUEST.md.

  python scripts/drive_sim/structured_noise_control.py residuals --s1 S1 --h-dir S2 --lut S4/hs_lut_2deg.npy --lut-meta S4/hs_lut_meta.json --cases R2A R5B --out OUT
  python scripts/drive_sim/structured_noise_control.py run       (same arguments + --seeds 50 --nproc 4 --mismatch-sigma 0.16095229605409875)
  python scripts/drive_sim/structured_noise_control.py report    --csv OUT/ARMS.csv --out OUT/ARMS_REPORT.json
Cases: R2A, R2B, R4A, R4B, R5A, R5B (routes x anchor, files H_<route>_a<anchor>_m<mount>.npy) or R1y0 / R1y0.35 (H_y<lat>_m<mount>.npy).  Mounts 0 and 45.
No filter parameter is changed; the real-observation arm A0 is the production observation.
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
from qclean_uwb.drivesim import filters as F  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

MOUNTS = (0.0, 45.0)
LAGS = (1, 2, 5, 10, 25)
RANGE_EXTRA_SIGMA = 0.05                                  # the random UWB range component the production observation adds (SensorNoise.range_sigma_m)
RANGE_VAR_FILTER = 0.05 ** 2 + 0.149 ** 2 / 12.0 + 0.05 ** 2
BASE = dict(name="range_s_P0", period=None, use_range=True, use_s=True, use_odom_heading=True)
ARMS = {                                                   # arm -> (s model, range model)
    "A0_real_real": ("real", "real"),
    "A1_white_white": ("white", "white"),
    "A2_iidreal_white": ("iid_real", "white"),
    "A3_ar1_white": ("ar1", "white"),
    "A4_blockboot_white": ("block", "white"),
    "A5_white_real": ("white", "real"),
    "A6_white_ar1": ("white", "ar1"),
    "A7_ar1_ar1": ("ar1", "ar1"),
}
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def parse_case(case):
    if case.startswith("R1"):
        return dict(kind="R1", lateral=float(case[3:]), anchor="A", route="R1")
    return dict(kind="route", route=case[:2], anchor=case[2])


def make_world(a, case, mount, period=None):
    c = parse_case(case)
    if c["kind"] == "R1":
        h = np.load(a.h_dir / f"H_y{c['lateral']:g}_m{mount:g}.npy", mmap_mode="r")
        return E.make_world(a.s1 / f"timeline_y{c['lateral']:g}_T{tag(period)}.csv", h, _G["freqs"], c["lateral"], mount, period)
    h = np.load(a.h_dir / f"H_{c['route']}_a{c['anchor']}_m{mount:g}.npy", mmap_mode="r")
    return E.make_world(a.s1 / "routes" / f"timeline_{c['route']}_T{tag(period)}.csv", h, _G["freqs"], 0.0, mount, period, route=c["route"], anchor=c["anchor"])


def anchor_of(case):
    c = parse_case(case)
    s = CorridorSetup(anchor_x_m=4.0 if c["anchor"] == "A" else 10.0)
    return tuple(s.anchor_position), s.robot_antenna_z_m


def setup(a):
    meta = json.loads(a.lut_meta.read_text())
    lut = HsLut(dict(theta_deg=np.array(meta["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["meta"]["phi_deg"][2]), s=np.load(a.lut)))
    if a.bank_freqs.suffix == ".npy":                       # e.g. selected_raw/freqs_hz.npy
        freqs = np.load(a.bank_freqs)
    else:
        with np.load(a.bank_freqs) as z:
            freqs = z["freqs_hz"]
    _G.update(lut=lut, freqs=freqs, range_offset=meta["range_bias"]["mean_m"], snr=[30.0])
    E.POS_PROCESS_STD = 0.01


# ------------------------------------------------------------------ real residual series
def acf(x, lags, centred=True):
    x = np.asarray(x, float)
    x = x - x.mean() if centred else x
    den = float(np.sum(x * x))
    return {str(k): float(np.sum(x[:-k] * x[k:]) / den) for k in lags}


def residual_series(case, mount, w):
    """Noise-free chain residuals on the P0 timeline: s_chain - LUT(truth) and range_chain - (3-D distance + offset)."""
    ax, rz = anchor_of(case)
    obs = O.observe(w.h, w.freqs, None, None)
    tr = w.truth
    lut_s = s_model(_G["lut"], ax, rz, tr[:, 0], tr[:, 1], tr[:, 2], mount)
    d3 = np.sqrt((tr[:, 0] - ax[0]) ** 2 + (tr[:, 1] - ax[1]) ** 2 + (ax[2] - rz) ** 2)
    return dict(r_s=obs["s"] - lut_s, r_r=obs["range_m"] - (d3 + _G["range_offset"]), d3=d3, t=w.t, delay_s=obs["delay_s"], index=obs["index"], lut_s=lut_s)


def stats_of(x, keep):
    v = x[keep]
    return dict(n=int(v.size), mean=float(v.mean()), var=float(v.var()), rms=float(np.sqrt((v ** 2).mean())), phi=float(acf(v, (1,))["1"]), acf=acf(v, LAGS))


def cmd_residuals(a):
    setup(a)
    out = {}
    a.out.mkdir(parents=True, exist_ok=True)
    for case in a.cases:
        for m in MOUNTS:
            w = make_world(a, case, m)
            rs = residual_series(case, m, w)
            keep = (w.t >= E.EXCLUDE_S) & np.isfinite(rs["r_s"]) & np.isfinite(rs["r_r"])
            tap = 299792458.0 / (4 * 257 * (_G["freqs"][1] - _G["freqs"][0]))
            frac = ((rs["d3"] + _G["range_offset"]) / tap) % 1.0
            fbin = np.minimum((frac * 4).astype(int), 3)
            rec = dict(s=stats_of(rs["r_s"], keep), range=stats_of(rs["r_r"], keep), corr_s_range=float(np.corrcoef(rs["r_s"][keep], rs["r_r"][keep])[0, 1]),
                       range_by_distance={k: dict(n=int(((rs["d3"] >= lo) & (rs["d3"] < hi) & keep).sum()),
                                                  mean=float(rs["r_r"][(rs["d3"] >= lo) & (rs["d3"] < hi) & keep].mean()) if ((rs["d3"] >= lo) & (rs["d3"] < hi) & keep).any() else None,
                                                  rms=float(np.sqrt((rs["r_r"][(rs["d3"] >= lo) & (rs["d3"] < hi) & keep] ** 2).mean())) if ((rs["d3"] >= lo) & (rs["d3"] < hi) & keep).any() else None)
                                          for k, (lo, hi) in {"<5m": (0, 5), "5-10m": (5, 10), ">10m": (10, 99)}.items()},
                       range_by_tap_fraction={str(b): dict(n=int(((fbin == b) & keep).sum()), mean=float(rs["r_r"][(fbin == b) & keep].mean()), std=float(rs["r_r"][(fbin == b) & keep].std())) for b in range(4)
                                              if ((fbin == b) & keep).any()},
                       s_by_index_change=dict(changed_rms=float(np.sqrt((rs["r_s"][keep & np.r_[False, np.diff(rs["index"]) != 0]] ** 2).mean())) if (keep & np.r_[False, np.diff(rs["index"]) != 0]).any() else None,
                                              unchanged_rms=float(np.sqrt((rs["r_s"][keep & ~np.r_[False, np.diff(rs["index"]) != 0]] ** 2).mean()))),
                       filter_assumed_range_var=RANGE_VAR_FILTER)
            out[f"{case}_m{m:g}"] = rec
            np.savez_compressed(a.out / f"RESIDUAL_{case}_m{m:g}.npz", **{k: v for k, v in rs.items()})
            print(case, m, "s: mean %.3f rms %.3f phi %.2f | range: mean %.3f rms %.3f phi %.2f | corr %.2f" % (rec["s"]["mean"], rec["s"]["rms"], rec["s"]["phi"], rec["range"]["mean"], rec["range"]["rms"], rec["range"]["phi"], rec["corr_s_range"]), flush=True)
    (a.out / "RESIDUAL_STATS.json").write_text(json.dumps(out, indent=1))


# ------------------------------------------------------------------ synthetic observation arms
def ar1(n, mu, var, phi, rng):
    x = np.empty(n)
    x[0] = rng.standard_normal() * math.sqrt(var)
    sd = math.sqrt(max(var * (1.0 - phi ** 2), 0.0))
    for k in range(1, n):
        x[k] = phi * x[k - 1] + sd * rng.standard_normal()
    return mu + x


def block_bootstrap(series, n, block, rng):
    out = np.empty(n)
    pos = 0
    while pos < n:
        s0 = int(rng.integers(0, len(series)))
        idx = (s0 + np.arange(min(block, n - pos))) % len(series)
        out[pos:pos + len(idx)] = series[idx]
        pos += len(idx)
    return out


def make_transform(arm, st):
    s_model_name, r_model_name = ARMS[arm]
    if arm == "A0_real_real":
        return None

    def f(obs, world, rng):
        n = len(world.rows)
        truth = world.truth
        ax, rz = _G["anchor"], _G["robot_z"]
        mount = world.mount_deg
        s0 = s_model(_G["lut"], ax, rz, truth[:, 0], truth[:, 1], truth[:, 2], mount)
        d3 = np.sqrt((truth[:, 0] - ax[0]) ** 2 + (truth[:, 1] - ax[1]) ** 2 + (ax[2] - rz) ** 2)
        s_stat, r_stat, ser = st["s"], st["range"], st["series"]
        if s_model_name != "real":
            if s_model_name == "white":
                noise = rng.standard_normal(n) * s_stat["rms"]
            elif s_model_name == "iid_real":
                noise = rng.choice(ser["r_s"], size=n, replace=True)
            elif s_model_name == "ar1":
                noise = ar1(n, s_stat["mean"], s_stat["var"], s_stat["phi"], rng)
            elif s_model_name == "block":
                noise = block_bootstrap(ser["r_s"], n, 50, rng)
            tap_var = 6.0 * obs["noise_var"]
            p1, p2 = obs["power"][:, 0], obs["power"][:, 1]
            thermal = np.array([F.thermal_var_s(x, y, tap_var) if tap_var > 0 and np.isfinite(x) and np.isfinite(y) else 0.0 for x, y in zip(p1, p2)])
            obs = dict(obs)
            obs["s"] = np.where(obs["detected"], s0 + noise + np.sqrt(np.maximum(thermal, 0.0)) * rng.standard_normal(n), np.nan)
        if r_model_name != "real":
            obs = dict(obs)
            if r_model_name == "white":
                noise = rng.standard_normal(n) * math.sqrt(r_stat["rms"] ** 2 + RANGE_EXTRA_SIGMA ** 2)
            else:
                noise = ar1(n, r_stat["mean"], r_stat["var"], r_stat["phi"], rng) + RANGE_EXTRA_SIGMA * rng.standard_normal(n)
            obs["range_m"] = d3 + obs["range_offset"] + noise
        return obs
    return f


def work(args):
    case, mount, arm, seed, drift, si = args
    g = _G
    ax, rz = anchor_of(case)
    g["anchor"], g["robot_z"] = ax, rz
    key = (case, mount)
    rows, _ = E.run_unit({None: g["worlds"][key]}, g["lut"], sensor=S.SensorNoise(), mismatch_sigma=g["mismatch"], anchor_xyz=ax, robot_z=rz, range_offset=g["range_offset"],
                         snr_db=g["snr"][si], snr_idx=si, drift_idx=drift, seed=seed, compare_filters=False, baselines=[BASE], obs_transform=make_transform(arm, g["stats"][key]))
    return [dict(r, arm=arm, case=case) for r in rows]


def cmd_run(a):
    setup(a)
    _G.update(worlds={}, stats={}, mismatch=a.mismatch_sigma)
    for case in a.cases:
        for m in MOUNTS:
            w = make_world(a, case, m)
            _G["worlds"][(case, m)] = w
            rs = residual_series(case, m, w)
            keep = (w.t >= E.EXCLUDE_S) & np.isfinite(rs["r_s"]) & np.isfinite(rs["r_r"])
            _G["stats"][(case, m)] = dict(s=stats_of(rs["r_s"], keep), range=stats_of(rs["r_r"], keep), series=dict(r_s=rs["r_s"][keep], r_r=rs["r_r"][keep]))
    achieved = {}
    chk = np.random.default_rng(7)
    for (c, m), st in _G["stats"].items():
        n = len(_G["worlds"][(c, m)].rows)
        rec = {}
        for kind, key in (("s", "s"), ("range", "range")):
            ser = st["series"]["r_s" if kind == "s" else "r_r"]
            tgt = st[key]
            for name in ("white", "iid_real", "ar1", "block"):
                vals = []
                for _ in range(20):
                    if name == "white":
                        x = chk.standard_normal(n) * tgt["rms"]
                    elif name == "iid_real":
                        x = chk.choice(ser, size=n, replace=True)
                    elif name == "ar1":
                        x = ar1(n, tgt["mean"], tgt["var"], tgt["phi"], chk)
                    else:
                        x = block_bootstrap(ser, n, 50, chk)
                    vals.append((x.mean(), x.var(), float(np.sum((x - x.mean())[:-1] * (x - x.mean())[1:]) / np.sum((x - x.mean()) ** 2))))
                v = np.mean(vals, axis=0)
                rec[f"{kind}_{name}"] = dict(mean=float(v[0]), var=float(v[1]), lag1=float(v[2]))
        achieved[f"{c}_m{m:g}"] = rec
    (a.out / "ARM_ACHIEVED_STATS.json").parent.mkdir(parents=True, exist_ok=True)
    (a.out / "ARM_ACHIEVED_STATS.json").write_text(json.dumps(achieved, indent=1))
    units = [(c, m, arm, s, d, 0) for c in a.cases for m in MOUNTS for arm in ARMS for d in (0, 1, 2) for s in range(a.seeds)]
    rows = []
    with mp.get_context("fork").Pool(a.nproc) as pool:
        for i, r in enumerate(pool.imap(work, units, chunksize=2)):
            rows += r
            if i % 50 == 0:
                print("units", i, "/", len(units), flush=True)
    a.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(a.out / "ARMS.csv", index=False)
    json.dump({f"{c}_m{m:g}": {k: v for k, v in _G["stats"][(c, m)].items() if k != "series"} for c in a.cases for m in MOUNTS}, open(a.out / "ARM_TARGET_STATS.json", "w"), indent=1)


def cmd_report(a):
    df = pd.read_csv(a.csv)
    ok = df[(df["filter"] == "ekf") & (df.error.fillna("") == "")]
    g = ok.groupby(["case", "mount_deg", "arm"])
    t = g.agg(n=("seed", "size"), nees=("nees_mean", "mean"), cov_pose=("nees_cov95", "mean"), cov_head=("heading_cov95", "mean"), head_rmse=("heading_rmse_deg", "median"),
              pos_rmse=("pos_rmse_m", "median"), nis_s=("nis_s_mean", "mean"), s_rej=("s_reject_frac", "mean"), r_rej=("r_reject_frac", "mean")).reset_index()
    rows = []
    for (case, m), gg in t.groupby(["case", "mount_deg"]):
        a0, a1 = gg[gg.arm == "A0_real_real"].iloc[0], gg[gg.arm == "A1_white_white"].iloc[0]
        for r in gg.itertuples():
            gap_n = (r.nees - a1.nees) / (a0.nees - a1.nees) if a0.nees != a1.nees else float("nan")
            gap_h = (r.head_rmse - a1.head_rmse) / (a0.head_rmse - a1.head_rmse) if a0.head_rmse != a1.head_rmse else float("nan")
            rows.append(dict(case=case, mount_deg=m, arm=r.arm, n=r.n, nees=r.nees, cov_pose=r.cov_pose, cov_head=r.cov_head, head_rmse=r.head_rmse, pos_rmse=r.pos_rmse, nis_s=r.nis_s,
                             s_rej=r.s_rej, r_rej=r.r_rej, nees_gap_closed=float(gap_n), head_gap_closed=float(gap_h)))
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250, "display.max_rows", 500)
    print(out.round(3).to_string(index=False))
    a.out.write_text(json.dumps(dict(definition="A23", rows=rows), indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["residuals", "run", "report"])
    ap.add_argument("--s1", type=Path)
    ap.add_argument("--h-dir", type=Path)
    ap.add_argument("--lut", type=Path)
    ap.add_argument("--lut-meta", type=Path)
    ap.add_argument("--bank-freqs", type=Path, default=ROOT / "LP_plus45_bank.npz")
    ap.add_argument("--cases", nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--nproc", type=int, default=4)
    ap.add_argument("--mismatch-sigma", type=float, default=0.16095229605409875)
    a = ap.parse_args()
    {"residuals": cmd_residuals, "run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
