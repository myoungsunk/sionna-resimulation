"""A23 rev2: which properties of the real s / range error (bias, marginal shape, autocorrelation, state alignment, cross-correlation, distance / tap dependence) reproduce the NEES
inflation of the real RF observation?  Spec: results/DRIVE_SIM_20261007/REQUESTS/CAUSE_CHECK_SPEC_AND_DATA_REQUEST.md (rev2).

  residuals  real noise-free residual series and their statistics (s: s_chain - LUT(truth); range: range_chain - (3-D distance + offset))
  run        observation arms through the unchanged EKF (range_s_P0); --dry-run prints the number of runs and stops
  report     per-drift tables, failures, seed-paired differences, gap-closure ratios with bootstrap intervals, A0-vs-S6 reproduction check, achieved fed-error statistics
No filter parameter, gate, prior or sigma is changed.  The real-observation arm A0 is the production observation; every synthetic arm uses the same filter, R, sensor and drift draws.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import platform
import subprocess
import sys
import time
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

LAGS = (1, 2, 5, 10, 25)
BLOCK = 50
EXTRA = 0.05                                               # the random UWB range component of the production observation (SensorNoise.range_sigma_m)
BASE = dict(name="range_s_P0", period=None, use_range=True, use_s=True, use_odom_heading=True)
# arm -> (s model, range model, tier, options)
ARMS = {
    "A0_real_real": ("real", "real", 0, {}),
    "M0_Rmatched_Rmatched": ("Rmatched", "Rmatched", 0, {}),          # white, variance = the variance the filter is told (sigma_mismatch^2 for s, R_range for range)
    "W0_white_white": ("white", "white", 0, {}),                      # zero-mean white with the RMS of the real residual (second moment matched, no bias)
    "S1_bias": ("bias", "white", 1, {}), "S2_ar0": ("ar0", "white", 1, {}), "S3_ar1": ("ar1", "white", 1, {}), "S4_iid": ("iid", "white", 1, {}),
    "S5_iid0": ("iid0", "white", 1, {}), "S6_realdem": ("realdem", "white", 1, {}), "S7_block": ("block", "white", 1, {}), "S8_real": ("real", "white", 1, {}),
    "R1_bias": ("white", "bias", 2, {}), "R2_ar0": ("white", "ar0", 2, {}), "R3_ar1": ("white", "ar1", 2, {}), "R4_iid": ("white", "iid", 2, {}),
    "R5_realdem": ("white", "realdem", 2, {}), "R6_distbin": ("white", "distbin", 2, {}), "R7_tapbin": ("white", "tapbin", 2, {}), "R8_real": ("white", "real", 2, {}),
    "J1_ar_indep": ("ar1", "ar1", 3, {}), "J2_ar_corr": ("ar1", "ar1", 3, {"corr": True}), "J3_joint_block": ("jblock", "jblock", 3, {}),
}
_G: dict = {}


def tag(v):
    return "none" if v is None else f"{v:g}"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def parse_case(case):
    if case.startswith("R1"):
        return dict(kind="R1", lateral=float(case[3:]), anchor="A", route="R1")
    return dict(kind="route", route=case[:2], anchor=case[2])


def h_path(a, case, mount):
    c = parse_case(case)
    return a.h_dir / (f"H_y{c['lateral']:g}_m{mount:g}.npy" if c["kind"] == "R1" else f"H_{c['route']}_a{c['anchor']}_m{mount:g}.npy")


def timeline_path(a, case, period=None):
    c = parse_case(case)
    return a.s1 / (f"timeline_y{c['lateral']:g}_T{tag(period)}.csv" if c["kind"] == "R1" else f"routes/timeline_{c['route']}_T{tag(period)}.csv")


def make_world(a, case, mount, period=None):
    c = parse_case(case)
    h = np.load(h_path(a, case, mount), mmap_mode="r")
    if c["kind"] == "R1":
        return E.make_world(timeline_path(a, case, period), h, _G["freqs"], c["lateral"], mount, period)
    return E.make_world(timeline_path(a, case, period), h, _G["freqs"], 0.0, mount, period, route=c["route"], anchor=c["anchor"])


def anchor_of(case):
    s = CorridorSetup(anchor_x_m=4.0 if parse_case(case)["anchor"] == "A" else 10.0)
    return tuple(s.anchor_position), s.robot_antenna_z_m


def setup(a):
    meta = json.loads(a.lut_meta.read_text())
    lut = HsLut(dict(theta_deg=np.array(meta["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["meta"]["phi_deg"][2]), s=np.load(a.lut)))
    if a.bank_freqs.suffix == ".npy":
        freqs = np.load(a.bank_freqs)
    else:
        with np.load(a.bank_freqs) as z:
            freqs = z["freqs_hz"]
    cfg = F.FilterConfig()
    _G.update(lut=lut, freqs=freqs, range_offset=meta["range_bias"]["mean_m"], snr=[30.0], R_range=cfg.range_sigma ** 2 + cfg.range_quant_var + cfg.range_extra_sigma ** 2,
              range_sigma_cfg=cfg.range_sigma)
    E.POS_PROCESS_STD = 0.01


# ------------------------------------------------------------------ real residual series and statistics
def acf(x, lags):
    x = np.asarray(x, float)
    x = x - x.mean()
    den = float(np.sum(x * x))
    return {str(k): float(np.sum(x[:-k] * x[k:]) / den) if den > 0 else float("nan") for k in lags}


def stats_of(x):
    x = np.asarray(x, float)
    return dict(n=int(x.size), mean=float(x.mean()), var=float(x.var()), rms=float(np.sqrt((x ** 2).mean())), phi=acf(x, (1,))["1"], acf=acf(x, LAGS))


def residual_series(case, mount, w):
    ax, rz = anchor_of(case)
    obs = O.observe(w.h, w.freqs, None, None)
    tr = w.truth
    lut_s = s_model(_G["lut"], ax, rz, tr[:, 0], tr[:, 1], tr[:, 2], mount)
    d3 = np.sqrt((tr[:, 0] - ax[0]) ** 2 + (tr[:, 1] - ax[1]) ** 2 + (ax[2] - rz) ** 2)
    return dict(r_s=obs["s"] - lut_s, r_r=obs["range_m"] - (d3 + _G["range_offset"]), d3=d3, t=w.t, delay_s=obs["delay_s"], index=obs["index"], lut_s=lut_s)


def build_targets(case, mount, w):
    rs = residual_series(case, mount, w)
    keep = (w.t >= E.EXCLUDE_S) & np.isfinite(rs["r_s"]) & np.isfinite(rs["r_r"])
    tap = 299792458.0 / (4 * 257 * (_G["freqs"][1] - _G["freqs"][0]))
    frac = ((rs["d3"] + _G["range_offset"]) / tap) % 1.0
    tbin = np.minimum((frac * 4).astype(int), 3)
    dbin = np.searchsorted([5.0, 10.0], rs["d3"])
    r_r, r_s = rs["r_r"], rs["r_s"]
    tg = dict(s=stats_of(r_s[keep]), range=stats_of(r_r[keep]), corr_s_range=float(np.corrcoef(r_s[keep], r_r[keep])[0, 1]), keep=keep,
              r_s_m=r_s[keep], r_r_m=r_r[keep], r_s_full=np.nan_to_num(r_s), r_r_full=np.nan_to_num(r_r), dbin=dbin, tbin=tbin, d3=rs["d3"])
    for name, b in (("dist", dbin), ("tap", tbin)):
        m, v = {}, {}
        for k in np.unique(b):
            sel = keep & (b == k)
            if sel.sum() >= 5:
                m[int(k)], v[int(k)] = float(r_r[sel].mean()), float(r_r[sel].var())
        tg[f"{name}_mean"], tg[f"{name}_var"] = m, v
    return tg, rs


# ------------------------------------------------------------------ noise generators (common random numbers across arms)
def stream(seed, drift, tagid, n):
    return np.random.default_rng([seed, drift, tagid]).standard_normal(n)


def ar1_from(z, mu, var, phi):
    n = len(z)
    x = np.empty(n)
    x[0] = math.sqrt(var) * z[0]
    sd = math.sqrt(max(var * (1.0 - phi ** 2), 0.0))
    for k in range(1, n):
        x[k] = phi * x[k - 1] + sd * z[k]
    return mu + x


def block_index(n, length, m, rng):
    idx = np.empty(n, int)
    pos = 0
    while pos < n:
        s0 = int(rng.integers(0, m))
        span = min(length, n - pos)
        idx[pos:pos + span] = (s0 + np.arange(span)) % m
        pos += span
    return idx


def gen_noise(kind, model, n, tg, seed, drift, z_in, extras, jidx, d_arrays):
    """Noise added to LUT(truth) (s) or to the 3-D distance + offset (range).  ``kind`` in {'s','range'}; z_in: the arm-independent innovation vector."""
    st = tg["s" if kind == "s" else "range"]
    ser_m = tg["r_s_m"] if kind == "s" else tg["r_r_m"]
    ser_f = tg["r_s_full"] if kind == "s" else tg["r_r_full"]
    tid = 105 if kind == "s" else 106
    rng = np.random.default_rng([seed, drift, tid])
    if model == "white":
        return z_in * (st["rms"] if kind == "s" else math.sqrt(st["rms"] ** 2 + EXTRA ** 2))
    if model == "Rmatched":
        return z_in * (_G["sigma_mismatch"] if kind == "s" else math.sqrt(_G["R_range"]))
    extra = EXTRA * extras if kind == "range" else 0.0
    if model == "bias":
        return st["mean"] + z_in * math.sqrt(st["var"]) + extra
    if model == "ar0":
        return ar1_from(z_in, 0.0, st["var"], st["phi"]) + extra
    if model == "ar1":
        return ar1_from(z_in, st["mean"], st["var"], st["phi"]) + extra
    if model == "iid":
        return ser_m[rng.integers(0, len(ser_m), n)] + extra
    if model == "iid0":
        return (ser_m - ser_m.mean())[rng.integers(0, len(ser_m), n)]
    if model == "realdem":
        return ser_f - st["mean"] + extra
    if model == "block":
        return ser_m[block_index(n, BLOCK, len(ser_m), rng)]
    if model == "jblock":
        return ser_m[jidx] + extra
    if model == "distbin":
        mu, var = tg["dist_mean"], tg["dist_var"]
        b = tg["dbin"]
        return np.array([mu.get(int(k), st["mean"]) + math.sqrt(var.get(int(k), st["var"])) * z for k, z in zip(b, z_in)]) + extra
    if model == "tapbin":
        mu, var = tg["tap_mean"], tg["tap_var"]
        b = tg["tbin"]
        return np.array([mu.get(int(k), st["mean"]) + math.sqrt(var.get(int(k), st["var"])) * z for k, z in zip(b, z_in)]) + extra
    raise ValueError(model)


def make_transform(arm, tg, seed, drift, rec):
    s_model_name, r_model_name, _, opts = ARMS[arm]

    def f(obs, world, rng_unused):
        n = len(world.rows)
        truth = world.truth
        ax, rz = _G["anchor"], _G["robot_z"]
        s0 = s_model(_G["lut"], ax, rz, truth[:, 0], truth[:, 1], truth[:, 2], world.mount_deg)
        d3 = np.sqrt((truth[:, 0] - ax[0]) ** 2 + (truth[:, 1] - ax[1]) ** 2 + (ax[2] - rz) ** 2)
        z_s, z_r = stream(seed, drift, 101, n), stream(seed, drift, 102, n)
        z_th, z_ex = stream(seed, drift, 103, n), stream(seed, drift, 104, n)
        obs = dict(obs)
        jidx = block_index(n, BLOCK, len(tg["r_s_m"]), np.random.default_rng([seed, drift, 107])) if "jblock" in (s_model_name, r_model_name) else None
        z_r_eff = z_r
        if opts.get("corr"):
            ps, pr, rho = tg["s"]["phi"], tg["range"]["phi"], tg["corr_s_range"]
            c = float(np.clip(rho * (1.0 - ps * pr) / math.sqrt((1.0 - ps ** 2) * (1.0 - pr ** 2)), -0.999, 0.999))
            z_r_eff = c * z_s + math.sqrt(1.0 - c * c) * z_r
        if s_model_name != "real":
            noise = gen_noise("s", s_model_name, n, tg, seed, drift, z_s, z_ex, jidx, None)
            tap_var = 6.0 * obs["noise_var"]
            p1, p2 = obs["power"][:, 0], obs["power"][:, 1]
            thermal = np.array([F.thermal_var_s(x, y, tap_var) if tap_var > 0 and np.isfinite(x) and np.isfinite(y) else 0.0 for x, y in zip(p1, p2)])
            obs["s"] = np.where(obs["detected"], s0 + noise + np.sqrt(np.maximum(thermal, 0.0)) * z_th, np.nan)
        if r_model_name != "real":
            obs["range_m"] = d3 + obs["range_offset"] + gen_noise("range", r_model_name, n, tg, seed, drift, z_r_eff, z_ex, jidx, None)
        e_s, e_r = obs["s"] - s0, obs["range_m"] - (d3 + obs["range_offset"])
        k = tg["keep"] & np.isfinite(e_s) & np.isfinite(e_r)
        rec.update(fed_s=stats_of(e_s[k]), fed_range=stats_of(e_r[k]), fed_corr=float(np.corrcoef(e_s[k], e_r[k])[0, 1]), fed_n=int(k.sum()))
        rec["_e_s"], rec["_e_r"] = e_s, e_r
        return obs
    return f


# ------------------------------------------------------------------ run
def init_worker(argd):
    a = argparse.Namespace(**argd)
    setup(a)
    _G.update(worlds={}, targets={}, sigma_mismatch=a.mismatch_sigma, save_traces=a.save_traces, out=a.out)
    for case in a.cases:
        for m in a.mounts:
            if not h_path(a, case, m).exists():
                continue
            w = make_world(a, case, m)
            _G["worlds"][(case, m)] = w
            _G["targets"][(case, m)] = build_targets(case, m, w)[0]


def work(args):
    case, mount, arm, seed, drift = args
    g = _G
    ax, rz = anchor_of(case)
    g["anchor"], g["robot_z"] = ax, rz
    tg = g["targets"][(case, mount)]
    rec = {}
    trace = {}
    if seed < g["save_traces"]:
        E.TRACE_HOOK = lambda world, out, err, nees: trace.update(est=out["est"][:, :6], cov3=out["cov3"], err=err, nees=nees, t=world.t, truth=world.truth)
    else:
        E.TRACE_HOOK = None
    try:
        rows, _ = E.run_unit({None: g["worlds"][(case, mount)]}, g["lut"], sensor=S.SensorNoise(), mismatch_sigma=g["sigma_mismatch"], anchor_xyz=ax, robot_z=rz,
                             range_offset=g["range_offset"], snr_db=g["snr"][0], snr_idx=0, drift_idx=drift, seed=seed, compare_filters=False, baselines=[BASE],
                             obs_transform=make_transform(arm, tg, seed, drift, rec))
    finally:
        E.TRACE_HOOK = None
    rows = [dict(r, arm=arm, case=case) for r in rows]
    unit = dict(case=case, mount_deg=mount, arm=arm, seed=seed, drift=drift,
                **{f"fed_s_{k}": rec["fed_s"][k] for k in ("mean", "var", "rms", "phi")}, **{f"fed_r_{k}": rec["fed_range"][k] for k in ("mean", "var", "rms", "phi")},
                fed_corr_s_r=rec["fed_corr"], fed_n=rec["fed_n"]) if rec else {}
    if trace and rec:
        tdir = Path(g["out"]) / "TRACES"
        tdir.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(tdir / f"{case}_m{mount:g}_{arm}_s{seed}_d{drift}.npz", e_s=rec["_e_s"], e_r=rec["_e_r"], keep=tg["keep"], **trace)
    return rows, unit


def expand_arms(spec):
    names = []
    for s in spec:
        if s.startswith("tier"):
            names += [k for k, v in ARMS.items() if v[2] <= int(s[4:]) and (int(s[4:]) == 0 or v[2] in (0, int(s[4:])))]
        elif s == "all":
            names += list(ARMS)
        else:
            if s not in ARMS:
                raise SystemExit(f"UNKNOWN_ARM {s}")
            names.append(s)
    return list(dict.fromkeys(names))


def cmd_run(a):
    a.cases, a.mounts = list(a.cases), [float(m) for m in a.mounts]
    arms = expand_arms(a.arms)
    missing = [(c, m) for c in a.cases for m in a.mounts if not h_path(a, c, m).exists()]
    if missing and not a.skip_missing:
        raise SystemExit(f"MISSING_H_STORES {[str(h_path(a, c, m)) for c, m in missing]} (use --skip-missing to run the others and list these as skipped)")
    cases = [(c, m) for c in a.cases for m in a.mounts if (c, m) not in missing]
    units = [(c, m, arm, a.seed0 + s, d) for c, m in cases for arm in arms for d in a.drifts for s in range(a.seeds)]
    print(f"cases x mounts: {cases}\narms ({len(arms)}): {arms}\nruns: {len(units)} = {len(cases)} case-mounts x {len(arms)} arms x {len(a.drifts)} drifts x {a.seeds} seeds", flush=True)
    if a.dry_run:
        return
    a.out.mkdir(parents=True, exist_ok=True)
    git = lambda *x: subprocess.run(["git", *x], capture_output=True, text=True, cwd=ROOT).stdout.strip()  # noqa: E731
    files = {str(h_path(a, c, m)): sha256(h_path(a, c, m)) for c, m in cases}
    files.update({str(p): sha256(p) for p in (a.lut, a.lut_meta, a.bank_freqs, Path(__file__))})
    manifest = dict(started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), argv=sys.argv, args={k: str(v) for k, v in vars(a).items()}, git_head=git("rev-parse", "HEAD"),
                    git_dirty=git("status", "--porcelain")[:2000], python=sys.version, numpy=np.__version__, pandas=pd.__version__, platform=platform.platform(), n_runs_planned=len(units),
                    skipped=[f"{c}_m{m:g}" for c, m in missing], input_sha256=files)
    (a.out / "RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    argd = dict(vars(a))
    method = "fork" if "fork" in mp.get_all_start_methods() else "spawn"          # Windows: spawn (workers rebuild their own state in init_worker)
    rows, ustats = [], []
    t0 = time.time()
    with mp.get_context(method).Pool(a.nproc, initializer=init_worker, initargs=(argd,)) as pool:
        for i, (r, u) in enumerate(pool.imap(work, units, chunksize=2)):
            rows += r
            if u:
                ustats.append(u)
            if i % 100 == 0:
                print("units", i, "/", len(units), f"{time.time() - t0:.0f}s", flush=True)
    pd.DataFrame(rows).to_csv(a.out / "ARMS.csv", index=False)
    pd.DataFrame(ustats).to_csv(a.out / "ARM_UNIT_STATS.csv", index=False)
    init_worker(argd)
    tj = {f"{c}_m{m:g}": {k: v for k, v in _G["targets"][(c, m)].items() if k in ("s", "range", "corr_s_range", "dist_mean", "dist_var", "tap_mean", "tap_var")} for c, m in cases}
    (a.out / "ARM_TARGETS.json").write_text(json.dumps(tj, indent=1, default=str))
    manifest.update(finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), seconds=round(time.time() - t0), n_rows=len(rows), n_failed=int(sum(1 for r in rows if r.get("error"))))
    (a.out / "RUN_MANIFEST.json").write_text(json.dumps(manifest, indent=1))


def cmd_residuals(a):
    setup(a)
    a.out.mkdir(parents=True, exist_ok=True)
    out = {}
    for case in a.cases:
        for m in [float(x) for x in a.mounts]:
            if not h_path(a, case, m).exists():
                print("skip (missing)", case, m)
                continue
            w = make_world(a, case, m)
            tg, rs = build_targets(case, m, w)
            tap = 299792458.0 / (4 * 257 * (_G["freqs"][1] - _G["freqs"][0]))
            sel = lambda lo, hi: tg["keep"] & (rs["d3"] >= lo) & (rs["d3"] < hi)  # noqa: E731
            out[f"{case}_m{m:g}"] = dict(s=tg["s"], range=tg["range"], corr_s_range=tg["corr_s_range"], tap_spacing_m=tap, R_range_filter=_G["R_range"],
                                         range_by_distance={k: dict(n=int(sel(lo, hi).sum()), mean=float(rs["r_r"][sel(lo, hi)].mean()) if sel(lo, hi).any() else None) for k, (lo, hi) in {"<5": (0, 5), "5-10": (5, 10), ">10": (10, 99)}.items()},
                                         range_by_tap_fraction={str(b): dict(n=int(((tg["tbin"] == b) & tg["keep"]).sum()), mean=float(rs["r_r"][(tg["tbin"] == b) & tg["keep"]].mean())) for b in range(4) if ((tg["tbin"] == b) & tg["keep"]).any()})
            np.savez_compressed(a.out / f"RESIDUAL_{case}_m{m:g}.npz", **{k: v for k, v in rs.items()})
            r = out[f"{case}_m{m:g}"]
            print(case, m, "s: mean %.4f rms %.4f lag1 %.3f | range: mean %.4f rms %.4f lag1 %.3f | corr %.3f | n %d" % (r["s"]["mean"], r["s"]["rms"], r["s"]["phi"], r["range"]["mean"], r["range"]["rms"], r["range"]["phi"], r["corr_s_range"], r["s"]["n"]), flush=True)
    (a.out / "RESIDUAL_STATS.json").write_text(json.dumps(out, indent=1))


# ------------------------------------------------------------------ report
def boot_ci(f, seeds_arr, B=2000, rng_seed=20261008):
    rng = np.random.default_rng(rng_seed)
    n = len(seeds_arr)
    vals = [f(rng.integers(0, n, n)) for _ in range(B)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def cmd_report(a):
    df = pd.read_csv(a.csv)
    err = df["error"].fillna("") if "error" in df else pd.Series("", index=df.index)
    bad = df[err != ""]
    ok = df[(err == "") & (df["filter"] == "ekf")]
    out = dict(definition="A23 rev2", n_rows=int(len(df)), n_failed=int(len(bad)))
    out["failures"] = bad.groupby(["case", "mount_deg", "drift", "arm"]).size().reset_index(name="n").to_dict("records") if len(bad) else []
    out["failure_messages"] = bad["error"].value_counts().head(5).to_dict() if len(bad) else {}
    pd.set_option("display.width", 260, "display.max_rows", 800)
    cols = dict(n=("seed", "size"), nees=("nees_mean", "mean"), cov_pose=("nees_cov95", "mean"), cov_head=("heading_cov95", "mean"), head_rmse=("heading_rmse_deg", "median"),
                pos_rmse=("pos_rmse_m", "median"), nis_s_pre=("nis_s_eval_pre", "mean"), nis_s_acc=("nis_s_eval_acc", "mean"), s_rej_eval=("s_reject_frac_eval", "mean"),
                nis_r_pre=("nis_r_eval_pre", "mean"), r_rej_eval=("r_reject_frac_eval", "mean"))
    cols = {k: v for k, v in cols.items() if v[0] in ok.columns}
    by_drift = ok.groupby(["case", "mount_deg", "drift", "arm"]).agg(**cols).reset_index()
    pooled = ok.groupby(["case", "mount_deg", "arm"]).agg(**cols).reset_index()
    print(f"rows {len(df)}  failed {len(bad)}")
    if len(bad):
        print(out["failures"][:10], out["failure_messages"])
    print("== per drift ==")
    print(by_drift.round(3).to_string(index=False))
    out["per_drift"], out["pooled"] = by_drift.to_dict("records"), pooled.to_dict("records")
    # seed-paired differences and gap closure (unit = seed; drifts of a seed are averaged first)
    seedm = ok.groupby(["case", "mount_deg", "arm", "seed"]).agg(nees=("nees_mean", "mean"), head=("heading_rmse_deg", "mean")).reset_index()
    paired = []
    for (case, m), g in seedm.groupby(["case", "mount_deg"]):
        piv = {met: g.pivot(index="seed", columns="arm", values=met) for met in ("nees", "head")}
        if not all(x in piv["nees"] for x in ("A0_real_real", "W0_white_white")):
            continue
        for arm in piv["nees"].columns:
            rec = dict(case=case, mount_deg=m, arm=arm)
            for met, pv in piv.items():
                d = pv[list(dict.fromkeys([arm, "A0_real_real", "W0_white_white"]))].dropna()
                if len(d) < 3:
                    continue
                arr, a0, w0 = d[arm].to_numpy(), d["A0_real_real"].to_numpy(), d["W0_white_white"].to_numpy()
                ratio = lambda idx: (arr[idx].mean() - w0[idx].mean()) / (a0[idx].mean() - w0[idx].mean())  # noqa: E731
                den = lambda idx: a0[idx].mean() - w0[idx].mean()  # noqa: E731
                allidx = np.arange(len(d))
                dlo, dhi = boot_ci(den, d.index.to_numpy())
                stable = dlo > 0 or dhi < 0
                lo, hi = boot_ci(ratio, d.index.to_numpy()) if stable else (float("nan"), float("nan"))
                rec.update({f"{met}_mean": float(arr.mean()), f"{met}_minus_W0": float((arr - w0).mean()), f"{met}_closure": float(ratio(allidx)) if stable else float("nan"),
                            f"{met}_closure_ci": [lo, hi], f"{met}_denominator_stable": bool(stable), f"{met}_n_seeds": int(len(d))})
            paired.append(rec)
    out["paired_closure"] = paired
    print("== seed-paired closure vs (A0 - W0); NaN = denominator CI includes 0 (unstable) ==")
    print(pd.DataFrame(paired)[[c for c in ("case", "mount_deg", "arm", "nees_mean", "nees_minus_W0", "nees_closure", "nees_closure_ci", "head_mean", "head_closure", "head_closure_ci") if c in pd.DataFrame(paired).columns]].round(3).to_string(index=False))
    # fed-error statistics actually used in the runs
    if a.unit_stats and Path(a.unit_stats).exists():
        us = pd.read_csv(a.unit_stats)
        fed = us.groupby(["case", "mount_deg", "arm"])[[c for c in us.columns if c.startswith("fed_") and c != "fed_n"]].mean().reset_index()
        out["fed_error_stats"] = fed.to_dict("records")
        print("== fed-error statistics (s, range; thermal and extra noise included; t>=30 s) ==")
        print(fed.round(4).to_string(index=False))
    # A0 vs stored S6 (same seed, drift, SNR 30)
    if a.s6_csv:
        s6 = pd.concat([pd.read_csv(p) for p in a.s6_csv], ignore_index=True)
        s6 = s6[(s6["filter"] == "ekf") & (s6.baseline == "range_s_P0") & (s6.snr_db == 30.0)]
        a0 = ok[ok.arm == "A0_real_real"].copy()
        a0["route"] = a0.case.str[:2]
        a0["anchor"] = a0.case.str[2]
        key = ["route", "anchor", "mount_deg", "drift", "seed"]
        if "lateral" in s6 and "lateral" in a0:
            pass
        j = a0.merge(s6, on=key, suffixes=("_a0", "_s6"))
        res = dict(n_a0=int(len(a0)), n_matched=int(len(j)))
        for col in ("heading_rmse_deg", "pos_rmse_m", "nees_mean"):
            if f"{col}_a0" in j and f"{col}_s6" in j:
                res[f"max_abs_diff_{col}"] = float((j[f"{col}_a0"] - j[f"{col}_s6"]).abs().max()) if len(j) else None
        res["pass_1e9"] = bool(len(j) > 0 and len(j) == len(a0) and all(v is not None and v <= 1e-9 for k, v in res.items() if k.startswith("max_abs")))
        out["a0_vs_s6"] = res
        print("== A0 vs stored S6 ==", res)
    a.out.write_text(json.dumps(out, indent=1, default=str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["residuals", "run", "report"])
    ap.add_argument("--s1", type=Path)
    ap.add_argument("--h-dir", type=Path)
    ap.add_argument("--lut", type=Path)
    ap.add_argument("--lut-meta", type=Path)
    ap.add_argument("--bank-freqs", type=Path, default=ROOT / "LP_plus45_bank.npz")
    ap.add_argument("--cases", nargs="+")
    ap.add_argument("--mounts", nargs="+", default=["0", "45"])
    ap.add_argument("--drifts", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--arms", nargs="+", default=["tier1"], help="arm names, tier0..tier3 (tier k = tier 0 plus tier k), or all")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--csv", type=Path)
    ap.add_argument("--unit-stats", type=Path)
    ap.add_argument("--s6-csv", type=Path, nargs="*")
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--seed0", type=int, default=0)
    ap.add_argument("--nproc", type=int, default=4)
    ap.add_argument("--mismatch-sigma", type=float, default=0.16095229605409875)
    ap.add_argument("--save-traces", type=int, default=0, help="save raw traces (estimates, covariance, errors, injected errors) for seeds below this value")
    ap.add_argument("--skip-missing", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    {"residuals": cmd_residuals, "run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
