"""A23 rev3: which properties of the real s / range error (bias, marginal shape, autocorrelation, state alignment, cross-correlation, distance / tap dependence) reproduce the NEES
inflation of the real RF observation?  Spec: results/DRIVE_SIM_20261007/REQUESTS/CAUSE_CHECK_SPEC_AND_DATA_REQUEST.md (rev3).

Order of use (each step is blocked unless the previous one passed):
  residuals   real noise-free residual series and statistics (no filter run)
  check-a0    runs ONLY the real-observation arm A0 for the requested key set and compares it with the stored S6 rows (required data); writes A0_CHECK.json
              (inference_valid true/false, exit code 2 when false).  Nothing else may run before this passes.
  run         the other arms; refuses to start without a valid A0_CHECK.json that has the same input / source / settings fingerprint and covers the requested keys
              (--allow-unchecked-a0 is a development override that marks the output NOT VALID FOR INFERENCE); A0 rows are reused, not recomputed
  report      per-drift tables first, then seed-paired comparisons restricted to seeds whose every compared arm completed every requested drift
No filter parameter, gate, prior or sigma is changed; every synthetic arm uses the same filter, R, sensor and drift draws as A0.
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
from dataclasses import asdict, replace
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
TOL = 1e-9                                                 # A0 vs S6 tolerance
METRICS = ("heading_rmse_deg", "pos_rmse_m", "nees_mean")  # the three metrics of the A0 / S6 comparison
KEYCOLS = ["route", "anchor", "lateral", "mount_deg", "drift", "snr_db", "seed"]
BASE = dict(name="range_s_P0", period=None, use_range=True, use_s=True, use_odom_heading=True)
ARMS = {                                                   # arm -> (s model, range model, tier, options)
    "A0_real_real": ("real", "real", 0, {}),
    "M0_Rmatched_Rmatched": ("Rmatched", "Rmatched", 0, {}),          # white, variance = the variance the filter is told (sigma_mismatch^2 for s, R_range for range)
    "W0_white_white": ("white", "white", 0, {}),                      # zero-mean white with the RMS of the real residual (second moment matched, no bias); NOT a model-matched control
    "S1_bias": ("bias", "white", 1, {}), "S2_ar0": ("ar0", "white", 1, {}), "S3_ar1": ("ar1", "white", 1, {}), "S4_iid": ("iid", "white", 1, {}),
    "S5_iid0": ("iid0", "white", 1, {}), "S6_realdem": ("realdem", "white", 1, {}), "S7_block": ("block", "white", 1, {}), "S8_real": ("real", "white", 1, {}),
    "R1_bias": ("white", "bias", 2, {}), "R2_ar0": ("white", "ar0", 2, {}), "R3_ar1": ("white", "ar1", 2, {}), "R4_iid": ("white", "iid", 2, {}),
    "R5_realdem": ("white", "realdem", 2, {}), "R6_distbin": ("white", "distbin", 2, {}), "R7_tapbin": ("white", "tapbin", 2, {}), "R8_real": ("white", "real", 2, {}),
    "J1_ar_indep": ("ar1", "ar1", 3, {}), "J2_ar_corr": ("ar1", "ar1", 3, {"corr": True}), "J3_joint_block": ("jblock", "jblock", 3, {}),
}
SOURCES = ["src/qclean_uwb/drivesim/filters.py", "src/qclean_uwb/drivesim/filters_aug.py", "src/qclean_uwb/drivesim/experiment.py", "src/qclean_uwb/drivesim/sensors.py", "src/qclean_uwb/drivesim/observation.py",
           "src/qclean_uwb/drivesim/hs_lut.py", "src/qclean_uwb/drivesim/trajectory.py", "src/qclean_uwb/drivesim/routes.py", "src/qclean_uwb/drivesim/pattern_apply.py",
           "src/qclean_uwb/scenarios/corridor.py", "scripts/drive_sim/structured_noise_control.py"]
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
    return dict(kind="route", route=case[:2], anchor=case[2], lateral=0.0)


def h_path(a, case, mount):
    c = parse_case(case)
    return a.h_dir / (f"H_y{c['lateral']:g}_m{mount:g}.npy" if c["kind"] == "R1" else f"H_{c['route']}_a{c['anchor']}_m{mount:g}.npy")


def timeline_path(a, case, period=None):
    c = parse_case(case)
    return a.s1 / (f"timeline_y{c['lateral']:g}_T{tag(period)}.csv" if c["kind"] == "R1" else f"routes/timeline_{c['route']}_T{tag(period)}.csv")


def poses_path(a, case):
    c = parse_case(case)
    return a.s1 / (f"rf_poses_y{c['lateral']:g}.json" if c["kind"] == "R1" else f"routes/rf_poses_{c['route']}.json")


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
    _G.update(lut=lut, freqs=freqs, range_offset=meta["range_bias"]["mean_m"], snr=[30.0], R_range=cfg.range_sigma ** 2 + cfg.range_quant_var + cfg.range_extra_sigma ** 2)
    E.POS_PROCESS_STD = 0.01


# ------------------------------------------------------------------ requested key set, fingerprint, manifest pieces
def requested_keys(cases, mounts, drifts, seeds, seed0, snr=30.0):
    rows = []
    for case in cases:
        c = parse_case(case)
        for m in mounts:
            for d in drifts:
                for s in range(seed0, seed0 + seeds):
                    rows.append(dict(route=c["route"], anchor=c["anchor"], lateral=float(c["lateral"]), mount_deg=float(m), drift=int(d), snr_db=float(snr), seed=int(s)))
    return pd.DataFrame(rows, columns=KEYCOLS)


def settings_snapshot(mismatch):
    cfg = F.FilterConfig()
    return dict(filter_config_defaults=asdict(cfg), sensor_noise=asdict(S.SensorNoise()), drift_levels=[asdict(x) for x in S.DRIFT_LEVELS], pos_process_std=E.POS_PROCESS_STD,
                exclude_s=E.EXCLUDE_S, snr_db=[30.0], mismatch_sigma=mismatch, applied_R=dict(range=cfg.range_sigma ** 2 + cfg.range_quant_var + cfg.range_extra_sigma ** 2, s_mismatch_var=mismatch ** 2),
                gate=cfg.gate, p0_std=list(cfg.p0_std),
                mask="evaluation mask = samples with t >= EXCLUDE_S (30 s); common stations additionally non-probe",
                seed_keys=dict(drift="[seed, drift, 1]", initial_state="[seed, 3]", sensor_inputs="[seed, drift, 2, period_code]", observation="(seed, snr_idx, period_code, round(lateral*100), mount[, route_code])",
                               synthetic_noise="[seed, drift, stream_id], stream ids 101..107"), snr_idx_mapping="S6 used SNR [30, 10] with snr_idx 0, 1; this tool uses SNR [30] with snr_idx 0")


def source_hashes():
    return {p: sha256(ROOT / p) for p in SOURCES if (ROOT / p).exists()}


def pose_correspondence(a, case):
    """timeline pose_id -> rf_poses entry: x, y, yaw must agree (1e-6) and the ids must index the H store."""
    poses = json.loads(poses_path(a, case).read_text())
    poses = poses if isinstance(poses, list) else poses["poses"]
    tl = pd.read_csv(timeline_path(a, case, None))
    ids = tl.pose_id.to_numpy()
    worst = 0.0
    for i, r in zip(ids, tl.itertuples()):
        p = poses[int(i)]
        worst = max(worst, abs(p["x"] - r.x), abs(p["y"] - r.y), abs(((p["yaw_body_deg"] - r.yaw_body_deg + 180.0) % 360.0) - 180.0))
    return dict(n_timeline=int(len(tl)), n_poses=len(poses), max_id=int(ids.max()), max_abs_diff=float(worst), ok=bool(worst <= 1e-6 and int(ids.max()) < len(poses)))


def input_snapshot(a, cases, mounts):
    out = dict(H={}, timelines={}, rf_poses={}, pose_correspondence={})
    for c in cases:
        for m in mounts:
            out["H"][f"{c}_m{m:g}"] = sha256(h_path(a, c, m))
        out["timelines"][c] = {tag(p): sha256(timeline_path(a, c, p)) for p in (None, 10.0, 20.0, 60.0) if timeline_path(a, c, p).exists()}
        out["rf_poses"][c] = sha256(poses_path(a, c))
        out["pose_correspondence"][c] = pose_correspondence(a, c)
    out["lut"], out["lut_meta"], out["freqs"] = sha256(a.lut), sha256(a.lut_meta), sha256(a.bank_freqs)
    if getattr(a, "s6_csv", None):
        out["s6_csv"] = {str(p): sha256(p) for p in a.s6_csv}
    return out


def fingerprint(inputs, sources, settings):
    """Global part only (LUT, LUT meta, frequency axis, source files, settings).  Per case-mount inputs (H store, timelines, rf_poses) are compared entry by entry in a0_gate."""
    core = dict(lut=inputs["lut"], lut_meta=inputs["lut_meta"], freqs=inputs["freqs"], sources=sources, settings=settings)
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def git_info():
    g = lambda *x: subprocess.run(["git", *x], capture_output=True, text=True, cwd=ROOT).stdout.strip()  # noqa: E731
    return dict(head=g("rev-parse", "HEAD"), branch=g("rev-parse", "--abbrev-ref", "HEAD"), dirty_files=g("status", "--porcelain").splitlines())


def base_manifest(a, cases, mounts, label):
    inputs = input_snapshot(a, cases, mounts)
    sources, settings = source_hashes(), settings_snapshot(a.mismatch_sigma)
    return dict(label=label, started_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), argv=sys.argv, args={k: str(v) for k, v in vars(a).items()}, git=git_info(),
                python=sys.version, numpy=np.__version__, pandas=pd.__version__, platform=platform.platform(), inputs=inputs, source_sha256=sources, settings=settings,
                fingerprint=fingerprint(inputs, sources, settings))


# ------------------------------------------------------------------ A0 vs S6 check (pure functions; unit-tested)
def normalize(df):
    df = df.copy()
    if "route" not in df.columns:                           # v1 R1 files predate the route / anchor columns
        df["route"], df["anchor"] = "R1", "A"
    for c in ("lateral", "mount_deg", "snr_db"):
        if c in df.columns:
            df[c] = df[c].astype(float).round(6)
    return df


def check_a0(a0, s6, requested, tol=TOL):
    """Compare A0 with the stored S6 rows on exactly the requested key set.  Any missing / duplicated / failed row, missing column or non-finite metric invalidates the check."""
    res = dict(n_requested=int(len(requested)), problems=[], inference_valid=False)
    need = KEYCOLS + ["baseline", "filter"] + list(METRICS)
    a0, s6 = normalize(a0), normalize(s6)
    for name, df in (("a0", a0), ("s6", s6)):
        miss = [c for c in need if c not in df.columns]
        if miss:
            res["problems"].append(dict(kind="missing_columns", side=name, columns=miss))
    if res["problems"]:
        return res
    req = normalize(requested)[KEYCOLS]
    subs = {}
    for name, df in (("a0", a0), ("s6", s6)):
        d = df[(df.baseline == "range_s_P0") & (df["filter"] == "ekf")].merge(req, on=KEYCOLS, how="inner")
        res[f"n_{name}_rows_on_requested"] = int(len(d))
        dup = d[d.duplicated(KEYCOLS, keep=False)]
        if len(dup):
            res["problems"].append(dict(kind="duplicate_keys", side=name, n=int(len(dup)), examples=dup[KEYCOLS].head(3).to_dict("records")))
        if "error" in d.columns:
            failed = d[d["error"].fillna("") != ""]
            if len(failed):
                res["problems"].append(dict(kind="failed_rows", side=name, n=int(len(failed)), examples=failed[KEYCOLS].head(3).to_dict("records")))
        have = d[KEYCOLS].drop_duplicates()
        absent = req.merge(have, on=KEYCOLS, how="left", indicator=True)
        absent = absent[absent["_merge"] == "left_only"]
        if len(absent):
            res["problems"].append(dict(kind="missing_keys", side=name, n=int(len(absent)), examples=absent[KEYCOLS].head(3).to_dict("records")))
        for c in METRICS:
            bad = ~np.isfinite(d[c].to_numpy(float))
            if bad.any():
                res["problems"].append(dict(kind="non_finite_metric", side=name, metric=c, n=int(bad.sum())))
        subs[name] = d
    if not res["problems"]:
        j = subs["a0"].merge(subs["s6"], on=KEYCOLS, suffixes=("_a0", "_s6"), validate="one_to_one")
        res["n_matched"] = int(len(j))
        for c in METRICS:
            diff = (j[f"{c}_a0"] - j[f"{c}_s6"]).abs()
            res[f"max_abs_diff_{c}"] = float(diff.max())
            if diff.max() > tol:
                worst = j.loc[diff.sort_values(ascending=False).index[:3], KEYCOLS].to_dict("records")
                res["problems"].append(dict(kind="metric_mismatch", metric=c, max_abs_diff=float(diff.max()), tol=tol, n_over=int((diff > tol).sum()), examples=worst))
    res["inference_valid"] = bool(not res["problems"] and res.get("n_matched") == len(req))
    return res


def a0_gate(check, manifest_now, run_keys, required_variant=None):
    """A valid A0 check with the same global fingerprint, the same per-case inputs and a key set that covers every key of this run."""
    if not check or not check.get("inference_valid"):
        return False, "A0_CHECK is missing or inference_valid is false"
    if required_variant is not None and check.get("filter_variant", "F0") != required_variant:
        return False, f"the A0 check was made with filter variant {check.get('filter_variant', 'F0')}, this run requires {required_variant}"
    if check.get("fingerprint") != manifest_now["fingerprint"]:
        return False, "LUT / frequency axis / source / settings fingerprint differs from the one that passed the A0 check"
    old = check.get("inputs", {})
    for part in ("H", "timelines", "rf_poses"):
        for k, v in manifest_now["inputs"][part].items():
            if old.get(part, {}).get(k) != v:
                return False, f"input {part}/{k} differs from the one that passed the A0 check"
    covered = set(map(tuple, check["requested"]))
    need = set(map(tuple, run_keys))
    if not need <= covered:
        return False, f"{len(need - covered)} keys of this run are not covered by the A0 check"
    return True, "ok"


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


def gen_noise(kind, model, n, tg, seed, drift, z_in, extras, jidx):
    """Noise added to LUT(truth) (s) or to the 3-D distance + offset (range).  z_in: the arm-independent innovation vector."""
    st = tg["s" if kind == "s" else "range"]
    ser_m = tg["r_s_m"] if kind == "s" else tg["r_r_m"]
    ser_f = tg["r_s_full"] if kind == "s" else tg["r_r_full"]
    rng = np.random.default_rng([seed, drift, 105 if kind == "s" else 106])
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
    if model in ("distbin", "tapbin"):
        key, b = ("dist", tg["dbin"]) if model == "distbin" else ("tap", tg["tbin"])
        mu, var = tg[f"{key}_mean"], tg[f"{key}_var"]
        return np.array([mu.get(int(k), st["mean"]) + math.sqrt(var.get(int(k), st["var"])) * z for k, z in zip(b, z_in)]) + extra
    raise ValueError(model)


def make_transform(arm, tg, seed, drift, rec):
    s_name, r_name, _, opts = ARMS[arm]

    def f(obs, world, rng_unused):
        n = len(world.rows)
        truth = world.truth
        ax, rz = _G["anchor"], _G["robot_z"]
        s0 = s_model(_G["lut"], ax, rz, truth[:, 0], truth[:, 1], truth[:, 2], world.mount_deg)
        d3 = np.sqrt((truth[:, 0] - ax[0]) ** 2 + (truth[:, 1] - ax[1]) ** 2 + (ax[2] - rz) ** 2)
        z_s, z_r, z_th, z_ex = (stream(seed, drift, t, n) for t in (101, 102, 103, 104))
        obs = dict(obs)
        jidx = block_index(n, BLOCK, len(tg["r_s_m"]), np.random.default_rng([seed, drift, 107])) if "jblock" in (s_name, r_name) else None
        z_r_eff, c_used, clipped = z_r, None, None
        if opts.get("corr"):
            ps, pr, rho = tg["s"]["phi"], tg["range"]["phi"], tg["corr_s_range"]
            c_raw = rho * (1.0 - ps * pr) / math.sqrt((1.0 - ps ** 2) * (1.0 - pr ** 2))
            c_used = float(np.clip(c_raw, -0.999, 0.999))
            clipped = bool(abs(c_raw) > 0.999)
            z_r_eff = c_used * z_s + math.sqrt(1.0 - c_used ** 2) * z_r
            rec.update(j2_target_corr=float(rho), j2_innovation_corr=c_used, j2_clipped=clipped)
        noise_s = noise_r = None
        if s_name != "real":
            noise_s = gen_noise("s", s_name, n, tg, seed, drift, z_s, z_ex, jidx)
            tap_var = 6.0 * obs["noise_var"]
            p1, p2 = obs["power"][:, 0], obs["power"][:, 1]
            thermal = np.array([F.thermal_var_s(x, y, tap_var) if tap_var > 0 and np.isfinite(x) and np.isfinite(y) else 0.0 for x, y in zip(p1, p2)])
            obs["s"] = np.where(obs["detected"], s0 + noise_s + np.sqrt(np.maximum(thermal, 0.0)) * z_th, np.nan)
        if r_name != "real":
            noise_r = gen_noise("range", r_name, n, tg, seed, drift, z_r_eff, z_ex, jidx)
            obs["range_m"] = d3 + obs["range_offset"] + noise_r
        e_s, e_r = obs["s"] - s0, obs["range_m"] - (d3 + obs["range_offset"])
        k = tg["keep"] & np.isfinite(e_s) & np.isfinite(e_r)
        rec.update(fed_s=stats_of(e_s[k]), fed_range=stats_of(e_r[k]), fed_corr=float(np.corrcoef(e_s[k], e_r[k])[0, 1]), fed_n=int(k.sum()))
        if noise_s is not None and noise_r is not None:             # before the thermal / extra additions: the correlation the generator itself produced
            rec["noise_corr_pre"] = float(np.corrcoef(noise_s[tg["keep"]], noise_r[tg["keep"]])[0, 1])
        rec["_e_s"], rec["_e_r"] = e_s, e_r
        return obs
    return f


# ------------------------------------------------------------------ A24 filter variants (measurement-bias states)
VARIANTS = ("F0", "F0aug", "F1", "F2", "F3")


def load_fit(path, which="primary"):
    """Frozen A24 fit parameters (fit_measurement_error_model.py output); ``which`` = primary | acf_variant."""
    fit = json.loads(Path(path).read_text())
    return dict(s=fit["s"][which]["fit"], r=fit["r"][which]["fit"], profile=fit.get("profile_s"), sha256=sha256(Path(path)), which=which)


def meas_state_for(variant, fit):
    if variant == "F0":
        return None
    if variant == "F0aug":
        return dict(aug_s=False, aug_r=False)
    pick = lambda d: dict(phi=d["phi"], var_beta=d["var_beta"], var_w=d["var_w"])  # noqa: E731
    ms = dict(aug_s=True, aug_r=variant in ("F2", "F3"), s=pick(fit["s"]), r=pick(fit["r"]))
    if variant == "F3":
        ms["s_profile"] = (fit["profile"]["theta_geo_knots_deg"], fit["profile"]["g"])
    return ms


def variant_info(a):
    info = dict(filter_variant=a.filter_variant)
    if getattr(a, "fit_params", None):
        fit = load_fit(a.fit_params, a.fit_variant)
        info["fit_params"] = dict(path=str(a.fit_params), sha256=fit["sha256"], which=fit["which"], s=fit["s"], r=fit["r"], profile=fit["profile"] if a.filter_variant == "F3" else None)
    return info


def make_cfg_transform(variant, fit):
    ms = meas_state_for(variant, fit)
    if ms is None:
        return None
    return lambda cfg, base: replace(cfg, meas_state=ms)


# ------------------------------------------------------------------ run machinery
def init_worker(argd):
    a = argparse.Namespace(**argd)
    setup(a)
    fit = load_fit(a.fit_params, a.fit_variant) if getattr(a, "fit_params", None) else None
    variant = getattr(a, "filter_variant", "F0")
    if variant in ("F1", "F2", "F3") and fit is None:
        raise SystemExit("FIT_PARAMS_REQUIRED: --fit-params is required for F1/F2/F3")
    _G.update(worlds={}, targets={}, sigma_mismatch=a.mismatch_sigma, trace_seeds=set(a.trace_seeds), out=a.out, variant=variant, ms=meas_state_for(variant, fit), cfg_transform=make_cfg_transform(variant, fit))
    for case in a.cases:
        for m in a.mounts:
            w = make_world(a, case, m)
            _G["worlds"][(case, m)] = w
            _G["targets"][(case, m)] = build_targets(case, m, w)[0]


def work(args):
    case, mount, arm, seed, drift = args
    g = _G
    ax, rz = anchor_of(case)
    g["anchor"], g["robot_z"] = ax, rz
    tg = g["targets"][(case, mount)]
    rec, trace, partial = {}, {}, {}
    detailed = seed in g["trace_seeds"]
    E.TRACE_PARTIAL = partial if detailed else None
    variant = g["variant"]

    def hook(world, out, err, nees, inputs, obs):
        if "beta_hat" in out and out["beta_hat"].shape[1]:                       # A24: eval-mask summary of the estimated bias states (all runs)
            ev = world.t >= E.EXCLUDE_S
            names = (["s"] if g["ms"] and g["ms"].get("aug_s") else []) + (["r"] if g["ms"] and g["ms"].get("aug_r") else [])
            for j, nm in enumerate(names):
                b, v = out["beta_hat"][ev, j], out["beta_var"][ev, j]
                rec[f"beta_{nm}_mean"], rec[f"beta_{nm}_rms"], rec[f"beta_{nm}_sd_mean"] = float(b.mean()), float(np.sqrt((b ** 2).mean())), float(np.sqrt(v).mean())
        if detailed:
            trace.update(est=out["est"], cov6=out["cov6"], err=err, nees=nees, t=world.t, truth=world.truth, s_log=np.array(out["stats"]["s_log"], float).reshape(-1, 8), r_log=np.array(out["stats"]["r_log"], float).reshape(-1, 8),
                         gyro=inputs["dtheta_gyro"], ds_odom=inputs["ds_odom"], dth_odom=inputs["dtheta_odom"], obs_s=obs["s"], obs_range=obs["range_m"], detected=obs["detected"], power=obs["power"])
            for k in ("beta_hat", "beta_var", "beta_cross"):
                if k in out:
                    trace[k] = out[k]

    E.TRACE_HOOK = hook
    try:
        rows, _ = E.run_unit({None: g["worlds"][(case, mount)]}, g["lut"], sensor=S.SensorNoise(), mismatch_sigma=g["sigma_mismatch"], anchor_xyz=ax, robot_z=rz,
                             range_offset=g["range_offset"], snr_db=g["snr"][0], snr_idx=0, drift_idx=drift, seed=seed, compare_filters=False, baselines=[BASE],
                             obs_transform=make_transform(arm, tg, seed, drift, rec), cfg_transform=g["cfg_transform"])
    finally:
        E.TRACE_HOOK = E.TRACE_PARTIAL = None
    rows = [dict(r, arm=arm, case=case, variant=variant) for r in rows]
    unit = {}
    if rec:
        unit = dict(case=case, mount_deg=mount, arm=arm, seed=seed, drift=drift, **{f"fed_s_{k}": rec["fed_s"][k] for k in ("mean", "var", "rms", "phi")},
                    **{f"fed_r_{k}": rec["fed_range"][k] for k in ("mean", "var", "rms", "phi")}, fed_corr_s_r=rec["fed_corr"], fed_n=rec["fed_n"],
                    noise_corr_pre=rec.get("noise_corr_pre"), variant=variant, **{k: v for k, v in rec.items() if k.startswith("beta_")}, j2_target_corr=rec.get("j2_target_corr"), j2_innovation_corr=rec.get("j2_innovation_corr"), j2_clipped=rec.get("j2_clipped"))
    if detailed and rec:
        tdir = Path(g["out"]) / "TRACES"
        tdir.mkdir(parents=True, exist_ok=True)
        name = tdir / f"{case}_m{mount:g}_{arm}_s{seed}_d{drift}.npz"
        failed = any(r.get("error") for r in rows)
        if failed and partial:                                   # keep the last valid state and the original error text
            np.savez_compressed(name, failed=True, error=str(rows[0].get("error")), k_done=partial.get("k_done", -1), est=partial["est"], cov6=partial["cov6"], e_s=rec["_e_s"], e_r=rec["_e_r"], keep=tg["keep"])
        elif trace:
            np.savez_compressed(name, failed=False, e_s=rec["_e_s"], e_r=rec["_e_r"], keep=tg["keep"], **trace)
    return rows, unit


def expand_arms(spec):
    names = []
    for s in spec:
        if s.startswith("tier"):
            k = int(s[4:])
            names += [n for n, v in ARMS.items() if v[2] == 0 or v[2] == k]
        elif s == "all":
            names += list(ARMS)
        else:
            if s not in ARMS:
                raise SystemExit(f"UNKNOWN_ARM {s}")
            names.append(s)
    return list(dict.fromkeys(names))


def resolve_inputs(a):
    a.cases, a.mounts = list(a.cases), [float(m) for m in a.mounts]
    missing = [(c, m) for c in a.cases for m in a.mounts if not h_path(a, c, m).exists()]
    if missing and not a.skip_missing:
        raise SystemExit(f"MISSING_H_STORES {[str(h_path(a, c, m)) for c, m in missing]} (--skip-missing runs the others and lists these as skipped)")
    cm = [(c, m) for c in a.cases for m in a.mounts if (c, m) not in missing]
    if not cm:
        raise SystemExit("NO_INPUTS: the requested case/mount set is empty")
    a.cases = sorted({c for c, _ in cm})
    a.mounts = sorted({m for _, m in cm})
    return cm, missing


def run_pool(a, units):
    argd = dict(vars(a))
    method = "fork" if "fork" in mp.get_all_start_methods() else "spawn"          # Windows: spawn; each worker rebuilds its own state in init_worker
    rows, ustats = [], []
    t0 = time.time()
    with mp.get_context(method).Pool(a.nproc, initializer=init_worker, initargs=(argd,)) as pool:
        for i, (r, u) in enumerate(pool.imap(work, units, chunksize=2)):
            rows += r
            if u:
                ustats.append(u)
            if i % 100 == 0:
                print("units", i, "/", len(units), f"{time.time() - t0:.0f}s", flush=True)
    return rows, ustats, round(time.time() - t0)


def cmd_check_a0(a):
    cm, missing = resolve_inputs(a)
    if a.filter_variant not in ("F0", "F0aug"):
        raise SystemExit("CHECK_A0_VARIANT: the A0 reproduction check is made with the stored filter (F0) or the augmentation switched off (F0aug)")
    if not a.s6_csv:
        raise SystemExit("S6_CSV_REQUIRED: the stored S6 rows are required data for the A0 check")
    setup(a)
    a.out.mkdir(parents=True, exist_ok=True)
    man = base_manifest(a, a.cases, a.mounts, "check-a0")
    man.update(variant_info(a))
    bad_pose = {c: v for c, v in man["inputs"]["pose_correspondence"].items() if not v["ok"]}
    req = requested_keys(a.cases, a.mounts, a.drifts, a.seeds, a.seed0)
    print(f"A0 check: {len(req)} requested keys = {len(a.cases)} cases x {len(a.mounts)} mounts x {len(a.drifts)} drifts x {a.seeds} seeds")
    if a.dry_run:
        return
    if bad_pose:
        res = dict(inference_valid=False, problems=[dict(kind="pose_correspondence", detail=bad_pose)])
    else:
        units = [(c, m, "A0_real_real", a.seed0 + s, d) for c, m in cm for d in a.drifts for s in range(a.seeds)]
        rows, ustats, secs = run_pool(a, units)
        a0 = pd.DataFrame(rows)
        a0.to_csv(a.out / "A0_ARMS.csv", index=False)
        pd.DataFrame(ustats).to_csv(a.out / "A0_UNIT_STATS.csv", index=False)
        s6 = pd.concat([pd.read_csv(p) for p in a.s6_csv], ignore_index=True)
        res = check_a0(a0, s6, req)
        res["seconds"] = secs
    res.update(filter_variant=a.filter_variant, fingerprint=man["fingerprint"], inputs=man["inputs"], requested=[list(r) for r in req.itertuples(index=False, name=None)], skipped=[f"{c}_m{m:g}" for c, m in missing])
    man["result"] = {k: v for k, v in res.items() if k != "requested"}
    (a.out / "A0_CHECK.json").write_text(json.dumps(res, indent=1, default=str))
    (a.out / "RUN_MANIFEST_check-a0.json").write_text(json.dumps(man, indent=1, default=str))
    print(json.dumps({k: v for k, v in res.items() if k not in ("requested", "inputs")}, indent=1, default=str)[:3000])
    if not res["inference_valid"]:
        print("A0_CHECK FAILED: inference_valid=false; no other arm may be run", file=sys.stderr)
        sys.exit(2)


def cmd_run(a):
    cm, missing = resolve_inputs(a)
    keep_a0 = a.filter_variant in ("F1", "F2", "F3")             # A24: A0 is also an arm of the augmented variants; F0 / F0aug A0 rows come from check-a0 only
    arms = [x for x in expand_arms(a.arms) if x != "A0_real_real" or keep_a0]
    if not arms:
        raise SystemExit("NO_ARMS_TO_RUN: A0 is produced by check-a0 only")
    units = [(c, m, arm, a.seed0 + s, d) for c, m in cm for arm in arms for d in a.drifts for s in range(a.seeds)]
    keys = [(r.route, r.anchor, float(r.lateral), float(r.mount_deg), int(r.drift), float(r.snr_db), int(r.seed)) for r in requested_keys(a.cases, a.mounts, a.drifts, a.seeds, a.seed0).itertuples()]
    print(f"cases x mounts: {cm}\narms ({len(arms)}): {arms}\nruns: {len(units)} = {len(cm)} case-mounts x {len(arms)} arms x {len(a.drifts)} drifts x {a.seeds} seeds", flush=True)
    setup(a)
    man = base_manifest(a, a.cases, a.mounts, a.label)
    man.update(variant_info(a))
    gate = "bypassed" if a.allow_unchecked_a0 else None
    if gate is None:
        p = a.out / "A0_CHECK.json"
        check = json.loads(p.read_text()) if p.exists() else None
        ok, why = a0_gate(check, man, keys, required_variant="F0" if a.filter_variant == "F0" else "F0aug")
        if not ok:
            raise SystemExit(f"A0_GATE_BLOCKED: {why}.  Run check-a0 first (same inputs, sources, settings and a key set that covers this run).")
        gate = "passed"
    man["a0_gate"] = gate
    if a.dry_run:
        return
    a.out.mkdir(parents=True, exist_ok=True)
    man.update(n_runs_planned=len(units), skipped=[f"{c}_m{m:g}" for c, m in missing])
    (a.out / f"RUN_MANIFEST_{a.label}.json").write_text(json.dumps(man, indent=1, default=str))
    rows, ustats, secs = run_pool(a, units)
    pd.DataFrame(rows).to_csv(a.out / f"ARMS_{a.label}.csv", index=False)
    pd.DataFrame(ustats).to_csv(a.out / f"ARM_UNIT_STATS_{a.label}.csv", index=False)
    man.update(finished_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), seconds=secs, n_rows=len(rows), n_failed=int(sum(1 for r in rows if r.get("error"))), requested_drifts=a.drifts,
               requested_seeds=[a.seed0, a.seed0 + a.seeds], inference_valid_a0_gate=bool(gate == "passed"))
    (a.out / f"RUN_MANIFEST_{a.label}.json").write_text(json.dumps(man, indent=1, default=str))
    init_worker(dict(vars(a)))
    tj = {f"{c}_m{m:g}": {k: v for k, v in _G["targets"][(c, m)].items() if k in ("s", "range", "corr_s_range", "dist_mean", "dist_var", "tap_mean", "tap_var")} for c, m in cm}
    (a.out / "ARM_TARGETS.json").write_text(json.dumps(tj, indent=1, default=str))


def cmd_residuals(a):
    cm, missing = resolve_inputs(a)
    setup(a)
    a.out.mkdir(parents=True, exist_ok=True)
    out = {}
    for case, m in cm:
        w = make_world(a, case, m)
        tg, rs = build_targets(case, m, w)
        tap = 299792458.0 / (4 * 257 * (_G["freqs"][1] - _G["freqs"][0]))
        sel = lambda lo, hi: tg["keep"] & (rs["d3"] >= lo) & (rs["d3"] < hi)  # noqa: E731
        out[f"{case}_m{m:g}"] = dict(s=tg["s"], range=tg["range"], corr_s_range=tg["corr_s_range"], tap_spacing_m=tap, R_range_filter=_G["R_range"],
                                     range_by_distance={k: dict(n=int(sel(lo, hi).sum()), mean=float(rs["r_r"][sel(lo, hi)].mean()) if sel(lo, hi).any() else None) for k, (lo, hi) in {"<5": (0, 5), "5-10": (5, 10), ">10": (10, 99)}.items()},
                                     range_by_tap_fraction={str(b): dict(n=int(((tg["tbin"] == b) & tg["keep"]).sum()), mean=float(rs["r_r"][(tg["tbin"] == b) & tg["keep"]].mean())) for b in range(4) if ((tg["tbin"] == b) & tg["keep"]).any()},
                                     skipped=[f"{c}_m{mm:g}" for c, mm in missing])
        np.savez_compressed(a.out / f"RESIDUAL_{case}_m{m:g}.npz", **{k: v for k, v in rs.items()})
        r = out[f"{case}_m{m:g}"]
        print(case, m, "s: mean %.4f rms %.4f lag1 %.3f | range: mean %.4f rms %.4f lag1 %.3f | corr %.3f | n %d" % (r["s"]["mean"], r["s"]["rms"], r["s"]["phi"], r["range"]["mean"], r["range"]["rms"], r["range"]["phi"], r["corr_s_range"], r["s"]["n"]), flush=True)
    (a.out / "RESIDUAL_STATS.json").write_text(json.dumps(out, indent=1))


# ------------------------------------------------------------------ report
def eligible_seeds(ok, case, mount, arms, drifts):
    """Seeds for which every listed arm completed every requested drift (pairing is only defined on those)."""
    sel = ok[(ok.case == case) & (ok.mount_deg == mount) & ok.arm.isin(arms)]
    cnt = sel.groupby(["arm", "seed"])["drift"].nunique().unstack("arm")
    full = cnt.reindex(columns=arms).fillna(0) >= len(drifts)
    return sorted(full.index[full.all(axis=1)].tolist()), cnt


def closure(arr, a0, w0, B=2000, rng_seed=20261008):
    n = len(arr)
    rng = np.random.default_rng(rng_seed)
    den_pt, den = a0.mean() - w0.mean(), []
    rat = []
    for _ in range(B):
        i = rng.integers(0, n, n)
        d = a0[i].mean() - w0[i].mean()
        den.append(d)
        rat.append((arr[i].mean() - w0[i].mean()) / d if d != 0 else np.nan)
    dlo, dhi = float(np.percentile(den, 2.5)), float(np.percentile(den, 97.5))
    out = dict(denominator=float(den_pt), denominator_ci=[dlo, dhi])
    if dlo > 0:                                                  # A0 is worse than W0 with an interval above 0: the closure of a degradation gap is defined
        out.update(status="defined", closure=float((arr.mean() - w0.mean()) / den_pt), closure_ci=[float(np.nanpercentile(rat, 2.5)), float(np.nanpercentile(rat, 97.5))])
        if out["closure"] > 1.0:
            out["note"] = "over_reproduced: this synthetic model reproduces a larger degradation than the real observation; it does not establish the cause"
    elif dhi < 0:
        out.update(status="not_applicable_negative_denominator", closure=None, closure_ci=None)
    else:
        out.update(status="withheld_denominator_interval_includes_0", closure=None, closure_ci=None)
    return out


def cmd_report(a):
    df = pd.concat([pd.read_csv(p) for p in a.csv], ignore_index=True)
    err = df["error"].fillna("") if "error" in df else pd.Series("", index=df.index)
    bad, ok = df[err != ""], df[(err == "") & (df["filter"] == "ekf")]
    dups = ok[ok.duplicated(["case", "mount_deg", "arm", "seed", "drift"], keep=False)]
    ok = ok.drop_duplicates(["case", "mount_deg", "arm", "seed", "drift"], keep="first")
    chk = json.loads(a.a0_check.read_text()) if a.a0_check and Path(a.a0_check).exists() else None
    drifts = [int(x) for x in a.drifts]
    valid = bool(chk and chk.get("inference_valid"))
    out = dict(definition="A23 rev3", inference_valid_a0=valid, n_rows=int(len(df)), n_failed=int(len(bad)), n_duplicate_keys_dropped=int(len(dups)), requested_drifts=drifts)
    print("A0 CHECK:", "VALID" if valid else "NOT VALID — results below must not be used for inference")
    out["failures"] = bad.groupby(["case", "mount_deg", "drift", "arm"]).size().reset_index(name="n").to_dict("records") if len(bad) else []
    out["failure_messages"] = bad["error"].value_counts().head(5).to_dict() if len(bad) else {}
    pd.set_option("display.width", 270, "display.max_rows", 900)
    cols = dict(n=("seed", "size"), nees=("nees_mean", "mean"), tail_lo=("nees_tail_lo", "mean"), tail_hi=("nees_tail_hi", "mean"), cov_pose=("nees_cov95", "mean"), cov_head=("heading_cov95", "mean"),
                head_rmse=("heading_rmse_deg", "median"), pos_rmse=("pos_rmse_m", "median"), nis_s_pre=("nis_s_eval_pre", "mean"), nis_s_acc=("nis_s_eval_acc", "mean"), s_rej=("s_reject_frac_eval", "mean"),
                nis_r_pre=("nis_r_eval_pre", "mean"), nis_r_acc=("nis_r_eval_acc", "mean"), r_rej=("r_reject_frac_eval", "mean"))
    cols = {k: v for k, v in cols.items() if v[0] in ok.columns}
    by_drift = ok.groupby(["case", "mount_deg", "drift", "arm"]).agg(**cols).reset_index()
    print(f"rows {len(df)}  failed {len(bad)}  duplicate-key rows dropped {len(dups)}")
    if len(bad):
        print(out["failures"][:10], out["failure_messages"])
    print("== PRIMARY: per drift ==")
    print(by_drift.round(3).to_string(index=False))
    out["per_drift"] = by_drift.to_dict("records")
    # per-drift paired closure (primary), then seed pairing over drifts (auxiliary)
    prim, aux, excluded = [], [], []
    for (case, m), g in ok.groupby(["case", "mount_deg"]):
        arms_here = sorted(g.arm.unique())
        if not {"A0_real_real", "W0_white_white"} <= set(arms_here):
            continue
        for arm in arms_here:
            trio = list(dict.fromkeys([arm, "A0_real_real", "W0_white_white"]))
            for d in drifts:
                gd = g[g.drift == d]
                for met, col in (("nees", "nees_mean"), ("head", "heading_rmse_deg")):
                    pv = gd.pivot(index="seed", columns="arm", values=col)
                    if not all(x in pv.columns for x in trio):
                        continue
                    pv = pv[trio].dropna()
                    if len(pv) >= 3:
                        prim.append(dict(case=case, mount_deg=m, drift=d, arm=arm, metric=met, n_seeds=int(len(pv)), arm_mean=float(pv[arm].mean()), minus_W0=float((pv[arm] - pv["W0_white_white"]).mean()),
                                         **closure(pv[arm].to_numpy(), pv["A0_real_real"].to_numpy(), pv["W0_white_white"].to_numpy())))
            seeds, cnt = eligible_seeds(g, case, m, trio, drifts)
            all_seeds = sorted(g[g.arm == arm].seed.unique())
            lost = sorted(set(all_seeds) - set(seeds))
            if lost:
                excluded.append(dict(case=case, mount_deg=m, arm=arm, excluded_seeds=[int(x) for x in lost], reason="not every compared arm completed every requested drift"))
            for met, col in (("nees", "nees_mean"), ("head", "heading_rmse_deg")):
                sm = g[g.seed.isin(seeds) & g.arm.isin(trio)].groupby(["arm", "seed"])[col].mean().unstack("arm")
                if len(sm) >= 3:
                    aux.append(dict(case=case, mount_deg=m, arm=arm, metric=met, n_seeds=int(len(sm)), arm_mean=float(sm[arm].mean()), **closure(sm[arm].to_numpy(), sm["A0_real_real"].to_numpy(), sm["W0_white_white"].to_numpy())))
    out["paired_closure_per_drift"], out["paired_closure_seed_mean_over_drifts"], out["excluded_seeds"] = prim, aux, excluded
    show = lambda rows: pd.DataFrame(rows)[[c for c in ("case", "mount_deg", "drift", "arm", "metric", "n_seeds", "arm_mean", "denominator", "status", "closure", "closure_ci") if c in (rows[0] if rows else {})]] if rows else pd.DataFrame()  # noqa: E731
    print("== PRIMARY: per-drift gap closure ((arm - W0)/(A0 - W0), seed-paired, bootstrap over seeds) ==")
    print(show(prim).round(3).to_string(index=False))
    print("== AUXILIARY: seeds averaged over drifts (only seeds complete for every compared arm and drift) ==")
    print(show(aux).round(3).to_string(index=False))
    if excluded:
        print("excluded seeds:", excluded[:10])
    for name, key in (("unit_stats", "fed_error_stats"),):
        if a.unit_stats:
            us = pd.concat([pd.read_csv(p) for p in a.unit_stats], ignore_index=True)
            num = [c for c in us.columns if c.startswith(("fed_", "noise_corr", "j2_")) and c != "fed_n" and us[c].dtype != object and us[c].dtype != bool]
            fed = us.groupby(["case", "mount_deg", "arm"])[num].mean().reset_index()
            out[key] = fed.to_dict("records")
            print("== fed-error statistics (thermal and extra noise included, t>=30 s); noise_corr_pre = generator correlation before the additions ==")
            print(fed.round(4).to_string(index=False))
    a.out.write_text(json.dumps(out, indent=1, default=str))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["residuals", "check-a0", "run", "report"])
    ap.add_argument("--s1", type=Path)
    ap.add_argument("--h-dir", type=Path)
    ap.add_argument("--lut", type=Path)
    ap.add_argument("--lut-meta", type=Path)
    ap.add_argument("--bank-freqs", type=Path, default=ROOT / "LP_plus45_bank.npz")
    ap.add_argument("--cases", nargs="+")
    ap.add_argument("--mounts", nargs="+", default=["0", "45"])
    ap.add_argument("--drifts", nargs="+", type=int, default=[0, 1, 2])
    ap.add_argument("--arms", nargs="+", default=["tier1"], help="arm names, tier0..tier3 (tier k = the three controls plus tier k), or all; A0 is never run here (check-a0)")
    ap.add_argument("--label", default="main")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--csv", type=Path, nargs="+")
    ap.add_argument("--unit-stats", type=Path, nargs="*")
    ap.add_argument("--a0-check", type=Path)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--s6-csv", type=Path, nargs="*")
    ap.add_argument("--seeds", type=int, default=50)
    ap.add_argument("--seed0", type=int, default=0)
    ap.add_argument("--nproc", type=int, default=4)
    ap.add_argument("--mismatch-sigma", type=float, default=0.16095229605409875)
    ap.add_argument("--trace-seeds", type=int, nargs="*", default=[], help="seeds (chosen before the run) whose full trace is saved")
    ap.add_argument("--skip-missing", action="store_true")
    ap.add_argument("--allow-unchecked-a0", action="store_true", help="development only: the output is marked NOT VALID FOR INFERENCE")
    ap.add_argument("--filter-variant", choices=VARIANTS, default="F0", help="A24: F0 stored filter | F0aug subclass with the augmentation off (gate) | F1 +beta_s | F2 +beta_s,beta_r | F3 F2 with the distance profile")
    ap.add_argument("--fit-params", type=Path, help="A24: frozen output of fit_measurement_error_model.py (required for F1-F3)")
    ap.add_argument("--fit-variant", choices=("primary", "acf_variant"), default="primary")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    {"residuals": cmd_residuals, "check-a0": cmd_check_a0, "run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
