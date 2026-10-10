"""A22: route tests (R2/R4/R5 x anchors A/B) of the steered T10 probe and of position/angle-dependent s mismatch variance.  Definitions: PREREG_AMENDMENTS A22.

  python scripts/drive_sim/route_a22.py apply   --d D                         # H stores from the local Method-B traces (rf_b_apply.py)
  python scripts/drive_sim/route_a22.py diag    --d D --out DEV_RESULTS/A22_DIAG.json
  python scripts/drive_sim/route_a22.py steered --d D --out DEV_RESULTS/A22_STEERED.csv  [--cases R2A R4A ...]
  python scripts/drive_sim/route_a22.py sigma   --d D --out DEV_RESULTS/A22_SIGMA.csv
  python scripts/drive_sim/route_a22.py report  --kind steered|sigma --csv ... --out ...
D = results/DRIVE_SIM_20261007.  Development evidence (local H stores), not the Snowball production stores.
"""
from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from qclean_uwb.drivesim import rf_store as RS  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.drivesim.steered_probe import steer_rows  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

PY = sys.executable
ROUTES, ANCHORS = ("R2", "R4", "R5"), {"A": 4.0, "B": 10.0}
CASES = [f"{r}{a}" for r in ROUTES for a in ANCHORS]
MOUNTS = (0.0, 45.0)
ERR = {"S10e0": 0.0, "S10e5": 5.0, "S10em5": -5.0}
SIGMA_STORED_ROUTES = 0.16095229605409875
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def paths(d):
    d = Path(d)
    return dict(s1=d / "S1", s2=d / "DEV_LOCAL" / "S2", lut=d / "DEV_LOCAL" / "S4")


def hpath(P, case, mount):
    return P["s2"] / f"H_{case[:2]}_a{case[2]}_m{mount:g}.npy"


def setup_globals(d):
    P = paths(d)
    doc = json.loads((P["lut"] / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(doc["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, doc["meta"]["phi_deg"][2]), s=np.load(P["lut"] / "hs_lut_2deg.npy")))
    banks = RS.load_banks()
    _G.update(P=P, lut=lut, banks=banks, freqs=banks[0].freqs_hz, range_offset=doc["range_bias"]["mean_m"], snr=[30.0, 10.0])
    E.POS_PROCESS_STD = 0.01


def anchor_of(case):
    s = CorridorSetup(anchor_x_m=ANCHORS[case[2]])
    return tuple(s.anchor_position), s.robot_antenna_z_m


def world(case, mount, period):
    P = _G["P"]
    h = np.load(hpath(P, case, mount), mmap_mode="r")
    return E.make_world(P["s1"] / "routes" / f"timeline_{case[:2]}_T{tag(period)}.csv", h, _G["freqs"], 0.0, mount, period, route=case[:2], anchor=case[2])


def have_case(case):
    return all(hpath(_G["P"], case, m).exists() for m in MOUNTS)


# ------------------------------------------------------------------ apply
def cmd_apply(a):
    P = paths(a.d)
    for case in a.cases or CASES:
        r, an = case[:2], case[2]
        tr = P["s2"] / f"traces_{r}_a{an}"
        n = len(list(tr.glob("*_trace.npz")))
        need = json.loads((P["s1"] / "routes" / "ROUTES_MANIFEST.json").read_text())["config"]["summary"][r]["rf_positions"]
        if n < need:
            print(case, "traces incomplete", n, "/", need, "- skipped", flush=True)
            continue
        for m in MOUNTS:
            out = hpath({"s2": P["s2"]}, case, m)
            if out.exists():
                continue
            subprocess.run([PY, str(ROOT / "scripts/drive_sim/rf_b_apply.py"), "--poses", str(P["s1"] / "routes" / f"rf_poses_{r}.json"), "--traces", str(tr), "--mount", f"{m:g}", "--out", str(out)], check=True)
            print(case, m, "H store written", flush=True)


# ------------------------------------------------------------------ residual features
def features_for(w, anchor_xyz, robot_z, mount, src):
    obs = O.observe(w.h, w.freqs, None, None)
    tr = w.truth
    lut_s = s_model(_G["lut"], anchor_xyz, robot_z, tr[:, 0], tr[:, 1], tr[:, 2], mount)
    rho = np.hypot(tr[:, 0] - anchor_xyz[0], tr[:, 1] - anchor_xyz[1])
    geo = np.degrees(np.arctan2(rho, anchor_xyz[2] - robot_z))
    nu = ((np.degrees(tr[:, 2]) + mount - 45.0 + 45.0) % 90.0) - 45.0
    keep = (w.t >= E.EXCLUDE_S) & np.isfinite(obs["s"])
    return pd.DataFrame(dict(r=(obs["s"] - lut_s)[keep], geo=geo[keep], nu=nu[keep], src=src, mount=mount))


def residual_frame(a):
    P = _G["P"]
    frames = []
    s = CorridorSetup()
    for lat in (0.0, 0.35):
        for m in MOUNTS:
            h = np.load(P["s2"] / f"H_y{lat:g}_m{m:g}.npy", mmap_mode="r")
            w = E.make_world(P["s1"] / f"timeline_y{lat:g}_Tnone.csv", h, _G["freqs"], lat, m, None)
            frames.append(features_for(w, tuple(s.anchor_position), s.robot_antenna_z_m, m, "R1"))
    for case in CASES:
        if not have_case(case):
            continue
        ax, rz = anchor_of(case)
        for m in MOUNTS:
            frames.append(features_for(world(case, m, None), ax, rz, m, case))
    return pd.concat(frames, ignore_index=True)


def rank(x):
    return pd.Series(np.asarray(x, float)).rank().to_numpy()


def spearman(a, b):
    return float(np.corrcoef(rank(a), rank(b))[0, 1])


def partial(y, x, z):
    A = np.column_stack([np.ones(len(z)), rank(z)])
    res = lambda v: v - A @ np.linalg.lstsq(A, v, rcond=None)[0]  # noqa: E731
    return float(np.corrcoef(res(rank(y)), res(rank(x)))[0, 1])


def cmd_diag(a):
    setup_globals(a.d)
    d = residual_frame(a)
    d["absr"], d["absnu"] = d.r.abs(), d.nu.abs()
    d["nubin"] = pd.cut(d.absnu, [-1, 15, 30, 45.01], labels=["0-15", "15-30", "30-45"])
    d["geobin"] = pd.qcut(d.geo, 5, labels=False)
    out = dict(n=int(len(d)), sources=d.src.value_counts().to_dict(), rms=float(np.sqrt((d.r ** 2).mean())),
               by_abs_nu=d.groupby("nubin", observed=True).r.agg(n="size", rms=lambda x: float(np.sqrt((x ** 2).mean()))).reset_index().to_dict("records"),
               by_geo=d.groupby("geobin").agg(n=("r", "size"), geo_center=("geo", "mean"), rms=("r", lambda x: float(np.sqrt((x ** 2).mean())))).reset_index().to_dict("records"),
               spearman_abs_r_vs_abs_nu=spearman(d.absr, d.absnu), spearman_abs_r_vs_geo=spearman(d.absr, d.geo), partial_abs_r_abs_nu_given_geo=partial(d.absr, d.absnu, d.geo),
               partial_abs_r_geo_given_abs_nu=partial(d.absr, d.geo, d.absnu))
    per = {}
    for src, g in d.groupby("src"):
        per[src] = dict(n=int(len(g)), rms=float(np.sqrt((g.r ** 2).mean())), rho_abs_nu=spearman(g.absr, g.absnu) if g.absnu.nunique() > 3 else None,
                        n_unique_nu=int(g.nu.round(0).nunique()))
    out["per_source"] = per
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(dict(definition="A22 A", **out), indent=1))
    d[["r", "geo", "nu", "src", "mount"]].round(6).to_csv(a.out.with_suffix(".residuals.csv"), index=False)
    print(json.dumps({k: v for k, v in out.items() if k not in ("per_source",)}, indent=1))
    print(pd.DataFrame(per).T.to_string())


# ------------------------------------------------------------------ steered (B)
def steered_worlds(case, mount):
    P = _G["P"]
    base = {None: world(case, mount, None), 10.0: world(case, mount, 10.0)}
    sweep = base[10.0]
    tr = [P["s2"] / f"traces_{case[:2]}_a{case[2]}"]

    def probe_h(rows):
        idx = [i for i, r in enumerate(rows) if r["probe_id"] >= 0]
        poses = [dict(x=rows[i]["x"], y=rows[i]["y"], yaw_body_deg=rows[i]["yaw_body_deg"], pose_id=k) for k, i in enumerate(idx)]
        h, _ = RS.assemble(poses, tr, _G["banks"], mount)
        return idx, h

    idx, hh = probe_h(sweep.rows)
    ref = np.asarray(sweep.h)[idx]
    check = float(np.max(np.linalg.norm((hh - ref).reshape(len(idx), -1), axis=1) / np.linalg.norm(ref.reshape(len(idx), -1), axis=1)))
    for key, err in ERR.items():
        rows = steer_rows(sweep.rows, mount, err)
        idx, hh = probe_h(rows)
        h = np.array(sweep.h)
        h[idx] = hh
        base[key] = E.World(rows, h, np.asarray(_G["freqs"], float), 0.0, mount, key, route=case[:2], anchor=case[2])
    return base, check


def work_steered(args):
    case, mount, seed, drift, si = args
    ax, rz = _G["anchors"][case]
    rows, _ = E.run_unit(_G["worlds"][(case, mount)], _G["lut"], sensor=S.SensorNoise(), mismatch_sigma=SIGMA_STORED_ROUTES, anchor_xyz=ax, robot_z=rz, range_offset=_G["range_offset"],
                         snr_db=_G["snr"][si], snr_idx=si, drift_idx=drift, seed=seed, compare_filters=False, baselines=_G["bases"])
    return rows


def cmd_steered(a):
    setup_globals(a.d)
    bases = [b for b in E.BASELINES if b["name"] in ("range_s_P0", "range_s_P1_T10")] + [
        dict(name=f"range_s_P1S_T10_{k}", period=k, use_range=True, use_s=True, use_odom_heading=True) for k in ERR]
    _G.update(bases=bases, worlds={}, anchors={})
    checks = {}
    cases = [c for c in (a.cases or CASES) if have_case(c)]
    for c in cases:
        _G["anchors"][c] = anchor_of(c)
        for m in MOUNTS:
            _G["worlds"][(c, m)], checks[f"{c}_m{m:g}"] = steered_worlds(c, m)
            print("worlds", c, m, "rebuild check %.2e" % checks[f"{c}_m{m:g}"], flush=True)
    units = [(c, m, s, d, si) for c in cases for m in MOUNTS for d in (0, 1, 2) for si in range(2) for s in range(a.seeds)]
    out = []
    with mp.get_context("fork").Pool(a.nproc) as pool:
        for i, r in enumerate(pool.imap(work_steered, units, chunksize=2)):
            out += r
            if i % 40 == 0:
                print("units", i, "/", len(units), flush=True)
    pd.DataFrame(out).to_csv(a.out, index=False)
    a.out.with_suffix(".checks.json").write_text(json.dumps(checks, indent=1))


def report_steered(a):
    df = pd.read_csv(a.csv)
    df = df[(df["filter"] == "ekf") & (df.error.fillna("") == "")]
    key = ["route", "anchor", "mount_deg", "drift", "snr_db", "seed"]
    sweep = df[df.baseline == "range_s_P1_T10"].set_index(key)
    rng = np.random.default_rng(20261008)
    rows = []

    def summarize(j, label, **ident):
        d = (j.heading_rmse_common_deg_x - j.heading_rmse_common_deg_sweep).to_numpy()
        med = np.median(rng.choice(d, size=(2000, len(d)), replace=True), axis=1)
        rows.append(dict(**ident, variant=label, n=int(len(d)), delta_median=float(np.median(d)), ci_lo=float(np.percentile(med, 2.5)), ci_hi=float(np.percentile(med, 97.5)),
                         better=float((d < 0).mean()), worse=float((d > 0).mean()), rmse_common_median=float(j.heading_rmse_common_deg_x.median()),
                         rmse_common_median_sweep=float(j.heading_rmse_common_deg_sweep.median()), nees_mean=float(j.nees_mean_x.mean()), nees_cov95=float(j.nees_cov95_x.mean())))

    for name in ("range_s_P1S_T10_S10e0", "range_s_P1S_T10_S10e5", "range_s_P1S_T10_S10em5", "range_s_P0"):
        j = df[df.baseline == name].set_index(key).join(sweep, lsuffix="_x", rsuffix="_sweep", how="inner")
        label = name.replace("range_s_", "")
        for m, g in j.groupby("mount_deg"):
            summarize(g, label, scope="pooled", route="all", anchor="all", mount_deg=float(m))
        for (r, an, m), g in j.groupby(["route", "anchor", "mount_deg"]):
            summarize(g, label, scope="case", route=r, anchor=an, mount_deg=float(m))
    out = pd.DataFrame(rows)
    pd.set_option("display.width", 250, "display.max_rows", 400)
    print(out[out.scope == "pooled"].round(3).to_string(index=False))
    print(out[(out.scope == "case") & (out.variant != "P0")].round(3).to_string(index=False))
    a.out.write_text(json.dumps(dict(definition="A22 B", rows=rows), indent=1))


# ------------------------------------------------------------------ sigma models (C)
def tables_from(cal):
    scalar = float(np.sqrt((cal.r ** 2).mean()))
    d = cal.copy()
    d["bin5"] = pd.qcut(d.geo, 5, labels=False, duplicates="drop")
    t5 = d.groupby("bin5").agg(c=("geo", "mean"), s=("r", lambda x: float(np.sqrt((x ** 2).mean())))).reset_index()
    knots, sig = tuple(float(v) for v in t5.c), tuple(float(v) for v in t5.s)
    q4 = np.quantile(d.geo, [0.25, 0.5, 0.75])
    d["g4"] = np.searchsorted(q4, d.geo)
    d["n3"] = np.searchsorted([15.0, 30.0], d.nu.abs())
    grid = np.full((4, 3), np.nan)
    counts = np.zeros((4, 3), int)
    for (i, j), g in d.groupby(["g4", "n3"]):
        counts[i, j] = len(g)
        if len(g) >= 50:
            grid[i, j] = float(np.sqrt((g.r ** 2).mean()))
    return scalar, (knots, sig), (tuple(float(v) for v in q4), (15.0, 30.0), grid.tolist(), knots, sig), counts.tolist()


def work_sigma(args):
    fold, var, case, mount, seed, drift, si = args
    scalar, t1, t2, _ = _G["tabs"][fold]
    ax, rz = _G["anchors"][case]

    def cfgt(cfg, base):
        if var == "V3":
            cfg.s_sigma_table = t1
        elif var == "V4":
            cfg.s_sigma_table2d = t2
        return cfg
    rows, _ = E.run_unit(_G["worlds"][(case, mount)], _G["lut"], sensor=S.SensorNoise(), mismatch_sigma=scalar, anchor_xyz=ax, robot_z=rz, range_offset=_G["range_offset"],
                         snr_db=_G["snr"][si], snr_idx=si, drift_idx=drift, seed=seed, compare_filters=False, cfg_transform=cfgt)
    return [dict(r, variant=var, fold=fold) for r in rows if r["baseline"] in ("range_s_P0", "range_s_P1_T20")]


def cmd_sigma(a):
    setup_globals(a.d)
    cases = [c for c in (a.cases or CASES) if have_case(c)]
    resid = residual_frame(a)
    _G.update(worlds={}, anchors={}, tabs={})
    for c in cases:
        _G["anchors"][c] = anchor_of(c)
        for m in MOUNTS:
            _G["worlds"][(c, m)] = {p: world(c, m, p) for p in (None, 20.0)}
    folds = sorted({c[:2] for c in cases})
    info = {}
    for f in folds:
        cal = resid[resid.src.map(lambda s: s[:2]) != f]
        _G["tabs"][f] = tables_from(cal)
        info[f] = dict(n_cal=int(len(cal)), scalar=_G["tabs"][f][0], table1d=_G["tabs"][f][1], table2d=dict(geo_edges=_G["tabs"][f][2][0], grid=_G["tabs"][f][2][2], counts=_G["tabs"][f][3]))
        print("fold", f, "scalar %.4f" % _G["tabs"][f][0], flush=True)
    units = [(f, v, c, m, s, d, si) for f in folds for v in ("V0", "V3", "V4") for c in cases if c[:2] == f for m in MOUNTS for d in (0, 1, 2) for si in range(2) for s in range(a.seeds)]
    out = []
    with mp.get_context("fork").Pool(a.nproc) as pool:
        for i, r in enumerate(pool.imap(work_sigma, units, chunksize=2)):
            out += r
            if i % 60 == 0:
                print("units", i, "/", len(units), flush=True)
    pd.DataFrame(out).to_csv(a.out, index=False)
    a.out.with_suffix(".tables.json").write_text(json.dumps(info, indent=1))


def report_sigma(a):
    df = pd.read_csv(a.csv)
    ok = df[(df["filter"] == "ekf") & (df.error.fillna("") == "")]
    g = ok.groupby(["route", "anchor", "variant", "baseline", "mount_deg"])
    t = g[["nees_mean", "nees_cov95", "heading_cov95"]].mean().join(g[["heading_rmse_deg", "pos_rmse_m"]].median().add_suffix("_median")).join(g.size().rename("n")).reset_index()
    key = ["route", "anchor", "mount_deg", "drift", "snr_db", "seed", "baseline"]
    v0 = ok[ok.variant == "V0"].set_index(key)
    pr = []
    for var in ("V3", "V4"):
        x = ok[ok.variant == var].set_index(key)
        j = x[["heading_rmse_deg"]].join(v0[["heading_rmse_deg"]], lsuffix="_v", rsuffix="_0", how="inner").reset_index()
        j["d"] = j.heading_rmse_deg_v - j.heading_rmse_deg_0
        p = j.groupby(["route", "anchor", "baseline", "mount_deg"]).agg(median_delta=("d", "median"), better=("d", lambda s: float((s < 0).mean())), n=("d", "size")).reset_index()
        p["variant"] = var
        pr.append(p)
    paired = pd.concat(pr)
    base = t[t.variant == "V0"].set_index(["route", "anchor", "baseline", "mount_deg"]).heading_rmse_deg_median
    t["rmse_ratio_vs_v0"] = [r.heading_rmse_deg_median / base[(r.route, r.anchor, r.baseline, r.mount_deg)] for r in t.itertuples()]
    t["acceptable_consistency"] = (t.nees_mean <= 6.0) & (t.nees_cov95 >= 0.90)
    t["usable_cell"] = t.acceptable_consistency & (t.rmse_ratio_vs_v0 <= 1.25)
    pd.set_option("display.width", 250, "display.max_rows", 400)
    print(t.round(3).to_string(index=False))
    print(paired.round(3).to_string(index=False))
    summ = t.groupby("variant").agg(cells=("n", "size"), acceptable=("acceptable_consistency", "sum"), usable=("usable_cell", "sum"), nees_mean_of_means=("nees_mean", "mean"), cov_mean=("nees_cov95", "mean")).reset_index()
    print(summ.round(3).to_string(index=False))
    a.out.write_text(json.dumps(dict(definition="A22 C", table=t.to_dict("records"), paired_vs_v0=paired.to_dict("records"), summary=summ.to_dict("records")), indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["apply", "diag", "steered", "sigma", "report"])
    ap.add_argument("--d", type=Path, default=Path("results/DRIVE_SIM_20261007"))
    ap.add_argument("--out", type=Path)
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--kind", choices=["steered", "sigma"])
    ap.add_argument("--cases", nargs="*")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--nproc", type=int, default=4)
    a = ap.parse_args()
    {"apply": cmd_apply, "diag": cmd_diag, "steered": cmd_steered, "sigma": cmd_sigma}.get(a.cmd, lambda x: (report_steered if x.kind == "steered" else report_sigma)(x))(a)


if __name__ == "__main__":
    main()
