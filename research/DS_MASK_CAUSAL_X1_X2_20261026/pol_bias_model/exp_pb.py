"""Polarization-bias modelling in the original EKF: variance, state, sliding window.  One shard = one (case, gyro-bias level).

  python exp_pb.py --case R4_aA_m0 --bias L1

Inputs (REFLECT_ROOT, from reflect_model/fetch_inputs.sh): FFD banks, code subset, E1 CONTROL traces (B0, L2).
Packets (z, mu_B, mu_M, R, truth) are identical for every gyro-bias level (verified for B0 vs L2: z 2e-16, mu/R identical).
The acceptance mask A_B is NOT: it is the NIS gate (GATE_JOINT = 9.2103) of the BASE (mu_B) filter and moves with the
gyro bias (R2_aA_m0: 8 packets, R5_aA_m0: 1 packet differ between B0 and L2).  It is therefore regenerated per level by
running the gated BASE filter; this reproduces the stored B0 and L2 masks exactly on all 14 stored conditions.
Controls for B0/L0/L1/L2 are regenerated with the original sensor generator (r2_bias_replay.build_positive_bias_controls,
seed 0) and checked against the stored B0/L2 traces.

Arms (background mu: BB = mu_B, MB = mu_M = Delta-s correction):
  {BB,MB}_ORIG       original filter (parity with the stored trace for B0/L2)
  {BB,MB}_VAR        R_ss += sig(rho_hat)^2                         (polarization error as distance-dependent variance)
  {BB,MB}_GM03       5th state b_s, Gauss-Markov over distance, L = 0.3 m
  {BB,MB}_GM1Y20     5th state b_s, L = 1 m, decorrelates with yaw change (Psi = 20 deg)
  {BB,MB}_WIN05Y10   5th state b_s constant inside a window; window closes after 0.5 m or 10 deg yaw change
  {BB,MB}_WIN1Y5     same, 1 m or 5 deg
  {BB,MB}_ORPOL      oracle: polarization error removed from z_s (truth used; upper bound, not a method)
sig(rho_hat) = interp([0,1.5,3,6,10] m -> [0.011,0.02,0.05,0.12,0.24]); rho_hat from the filter's own predicted state.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "reflect_model"))
import common as C  # noqa: E402

sys.path.insert(0, str(C.REPO / "research/EKF4_RANGE_S_STAGED_20261014"))
from core import predict, wrap  # noqa: E402
from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate, motion_increments, rng  # noqa: E402

BIAS_LEVELS = {"B0": 0.0, "L0": 0.01, "L1": 0.05, "L2": 0.20}           # deg/s, positive gyro bias
INITIAL_POSE_STD = np.array([0.1, 0.1, math.radians(5.0)])
SIG_R = np.array([0.0, 1.5, 3.0, 6.0, 10.0]); SIG_V = np.array([0.011, 0.02, 0.05, 0.12, 0.24])
ARMS = []
for bg in ("BB", "MB"):
    ARMS += [(f"{bg}_ORIG", bg, dict(mode="orig")), (f"{bg}_VAR", bg, dict(mode="var")),
             (f"{bg}_GM03", bg, dict(mode="gm", L=0.3)), (f"{bg}_GM1Y20", bg, dict(mode="gm", L=1.0, Psi=20.0)),
             (f"{bg}_WIN05Y10", bg, dict(mode="win", W=0.5, Y=10.0)), (f"{bg}_WIN1Y5", bg, dict(mode="win", W=1.0, Y=5.0)),
             (f"{bg}_ORPOL", bg, dict(mode="orpol")),
             # data-built variance tables (build_sig_tables.py -> sig_tables.json); looked up with the filter's own state
             (f"{bg}_VARM", bg, dict(mode="vartab", kind="1d_mount", loro=False)),
             (f"{bg}_VARM_LORO", bg, dict(mode="vartab", kind="1d_mount", loro=True)),
             (f"{bg}_VAR2D", bg, dict(mode="vartab", kind="2d", loro=False)),
             (f"{bg}_VAR2D_LORO", bg, dict(mode="vartab", kind="2d", loro=True))]


def sig(r):
    return float(np.interp(r, SIG_R, SIG_V))


def sig_table(tab, rho, shat):
    """1D: interp over rho;  2D: bin lookup over (rho, |s_hat|) where s_hat = predicted s at the filter state."""
    if "r" in tab:
        return float(np.interp(rho, tab["r"], tab["sig"]))
    i = min(np.searchsorted(tab["rho_edges"], rho, side="right") - 1, len(tab["sig"]) - 1)
    j = min(np.searchsorted(tab["shat_edges"], shat, side="right") - 1, len(tab["sig"][0]) - 1)
    return float(tab["sig"][max(i, 0)][max(j, 0)])


def resolve_table(cfg, case_id):
    tabs = json.loads((HERE / "sig_tables.json").read_text())
    mount = case_id.split("_")[-1]; route = case_id[:2]
    key = (f"1D_{mount}" if cfg["kind"] == "1d_mount" else "2D") + (f"_LORO_{route}" if cfg["loro"] else "")
    return tabs[key], key


def build_controls(t, pose, level, seed=0):
    """Original sensor simulation (r2_bias_replay.build_positive_bias_controls); truth never enters the filter."""
    b = BIAS_LEVELS[level]
    ds, dth = motion_increments(t, pose, convention="legacy-euler")
    if level == "B0":
        cfg = SensorV2Config(level=1, condition="noise_pair", common_scale=0.0, bias_rw_rad_s_sqrt_s=0.0)
        inputs, off = generate(t, ds, dth, cfg, seed)
    else:
        cfg = SensorV2Config(level=["L0", "L1", "L2"].index(level), condition="all", slip_mode="off", common_scale=0.0, bias_rw_rad_s_sqrt_s=0.0)
        inputs, off = generate(t, ds, dth, cfg, seed, parameters={"gyro_bias": math.radians(b), "gyro_sf": 0.0,
                                                                  "wheel_asymmetry": 0.0, "wheelbase": 0.0, "common_scale": 0.0})
    if np.max(np.abs(np.asarray(off["true_bias_rad_s"]) - math.radians(b))) > 1e-14:
        raise RuntimeError("SENSOR_TRUE_BIAS_NOT_FROZEN")
    x0 = np.asarray(pose[0] + rng(seed, "initial").standard_normal(3) * INITIAL_POSE_STD)
    x0[2] = float(wrap(x0[2]))
    return np.asarray(inputs["ds_odom"]), np.asarray(inputs["dtheta_gyro"]), np.asarray(inputs["dt_s"]), x0


GATE_JOINT = 9.210340371976184


def gated_mask(z, mu, R, ds, gy, dt, x0, P0, spec, model):
    """Acceptance mask A_B of the original BASE filter (joint NIS gate); reproduces stored E1 masks exactly."""
    x = x0.copy(); P = P0.copy(); acc = np.zeros(len(z), bool)
    for k in range(len(z)):
        if k:
            q = np.diag([2e-5 * abs(ds[k]), math.radians(0.015) ** 2 * dt[k], 0.0])
            x, P, _, _ = predict(x, P, float(ds[k]), float(gy[k]), float(dt[k]), q)
        h, H = model.batch(x[None], spec); h = h[0]; H = H[0]
        v = z[k] - h - mu[k]; S_ = H @ P @ H.T + R[k]
        if np.isfinite(z[k]).all() and float(v @ np.linalg.solve(S_, v)) <= GATE_JOINT:
            K = np.linalg.solve(S_, H @ P).T; y = x + K @ v; y[2] = wrap(y[2])
            A_ = np.eye(4) - K @ H; P = A_ @ P @ A_.T + K @ R[k] @ K.T; P = 0.5 * (P + P.T); x = y; acc[k] = True
    return acc


def run(D, mu, cfg, model):
    mode = cfg["mode"]; n = len(D["t"]); a = D["anchor"]
    stateful = mode in ("gm", "win")
    nx = 5 if stateful else 4
    x = np.r_[D["x0"], 0.0] if stateful else D["x0"].copy()
    P = np.zeros((nx, nx)); P[:4, :4] = D["P0"]
    if stateful:
        P[4, 4] = sig(math.hypot(x[0] - a[0], x[1] - a[1])) ** 2
    X = np.zeros((n, 4)); PX = np.zeros((n, 4, 4)); B = np.zeros(n)
    dist = dyaw = 0.0; nwin = 1
    for k in range(n):
        rh = math.hypot(x[0] - a[0], x[1] - a[1]); sg = sig(rh)
        if k:
            ds, gy, dt = float(D["ds"][k]), float(D["gy"][k]), float(D["dt"][k])
            q = np.diag([2e-5 * abs(ds), math.radians(0.015) ** 2 * dt, 0.0])
            y4, P44, F, _ = predict(x[:4], P[:4, :4], ds, gy, dt, q)
            if not stateful:
                x, P = y4, P44
            else:
                Pn = np.zeros((5, 5)); Pn[:4, :4] = P44
                if mode == "gm":
                    phi = math.exp(-abs(ds) / cfg["L"] - (abs(gy) / math.radians(cfg["Psi"]) if cfg.get("Psi") else 0.0))
                    Pn[:4, 4] = F @ P[:4, 4] * phi; Pn[4, 4] = phi ** 2 * P[4, 4] + sg ** 2 * (1 - phi ** 2); xb = phi * x[4]
                else:
                    Pn[:4, 4] = F @ P[:4, 4]; Pn[4, 4] = P[4, 4]; xb = x[4]
                    dist += abs(ds); dyaw += gy
                    if dist > cfg["W"] or abs(dyaw) > math.radians(cfg["Y"]):
                        xb = 0.0; Pn[:4, 4] = 0.0; Pn[4, 4] = sg ** 2; dist = dyaw = 0.0; nwin += 1
                Pn[4, :4] = Pn[:4, 4]
                x = np.r_[y4, xb]; P = 0.5 * (Pn + Pn.T)
        if D["acc"][k]:
            h, H = model.batch(x[None, :4], D["spec"]); h = h[0]; H = H[0]
            z = D["z"][k].copy(); Rk = D["R"][k].copy()
            if mode == "orpol":
                z[1] = D["hg"][k, 1] + mu[k, 1]
            if mode == "var":
                Rk[1, 1] += sg ** 2
            if mode == "vartab":
                Rk[1, 1] += sig_table(cfg["table"], rh, abs(float(h[1]))) ** 2
            if stateful:
                Ha = np.c_[H, [0.0, 1.0]]; hh = h + np.r_[0.0, x[4]]
            else:
                Ha = H; hh = h
            v = z - hh - mu[k]
            S_ = Ha @ P @ Ha.T + Rk; S_ = 0.5 * (S_ + S_.T)
            K = np.linalg.solve(S_, Ha @ P).T
            y = x + K @ v; y[2] = wrap(y[2])
            A_ = np.eye(nx) - K @ Ha; Pn = A_ @ P @ A_.T + K @ Rk @ K.T
            x = y; P = 0.5 * (Pn + Pn.T)
        X[k] = x[:4]; PX[k] = P[:4, :4]; B[k] = x[4] if stateful else 0.0
    return X, PX, B, nwin


def scores(D, X, PX):
    t, gt = D["t"], D["gt"]; s = t >= 30 - 1e-9
    e = gt[:, :3] - X[:, :3]; e[:, 2] = np.angle(np.exp(1j * e[:, 2]))
    sp = np.sqrt(PX[:, 2, 2]); zpsi = e[:, 2] / sp
    nees = np.einsum("ni,ni->n", e[:, :2], np.linalg.solve(PX[:, :2, :2], e[:, :2][..., None])[..., 0])
    a = D["anchor"]; d3 = np.linalg.norm(np.c_[X[:, :2] - a, np.full(len(t), D["spec"]["robot_z_m"] - D["spec"]["anchor"][2])], axis=1)
    d3t = np.linalg.norm(np.c_[gt[:, :2] - a, np.full(len(t), D["spec"]["robot_z_m"] - D["spec"]["anchor"][2])], axis=1)
    return dict(head_rmse=float(np.degrees(np.sqrt(np.mean(e[s, 2] ** 2)))), head_bias=float(np.degrees(np.mean(e[s, 2]))),
                xy_rmse_cm=float(100 * np.sqrt(np.mean(np.sum(e[s, :2] ** 2, 1)))), range_rmse_cm=float(100 * np.sqrt(np.mean((d3 - d3t)[s] ** 2))),
                head_z_rms=float(np.sqrt(np.mean(zpsi[s] ** 2))), head_cov95=float(np.mean(np.abs(zpsi[s]) < 1.96)),
                nees_xy=float(np.mean(nees[s])), xy_cov95=float(np.mean(nees[s] < 5.991)))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--case", required=True); ap.add_argument("--bias", required=True)
    ap.add_argument("--arms", default="all")
    ap.add_argument("--sig", default=None, help="override sigma table 'r0,r1,..:s0,s1,..' (e.g. mount-specific)")
    ap.add_argument("--sig-scale", type=float, default=1.0)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    global SIG_R, SIG_V
    if a.sig:
        rs, ss = a.sig.split(":"); SIG_R = np.array([float(v) for v in rs.split(",")]); SIG_V = np.array([float(v) for v in ss.split(",")])
    SIG_V = SIG_V * a.sig_scale
    model = C.base_model()
    checks = {}
    stored = {}
    pk_path = HERE / "packets" / f"PACKETS_{a.case}.npz"
    if a.case in C.CASES:
        spec = C.CASES[a.case]
        ref = C.load_control(a.case, "B0")                      # packets are bias-level independent
        jb, jm = ref["jb"], ref["jm"]
        t = ref["t_s"]; gt = ref["truth_scoring_only"]
        z = ref["nu"][:, jb] + ref["h"][:, jb] + ref["mu"][:, jb]
        muB, muM, R = ref["mu"][:, jb], ref["mu"][:, jm], ref["R"][:, jb]; P0 = ref["Pprior"][0, jb]; accB0 = ref["acc"][:, jb].astype(bool)
        if pk_path.exists():                                     # regenerated packets must equal the stored E1 inputs
            pk = np.load(pk_path)
            for nm, mine, theirs in (("z", pk["z"], z), ("mu_B", pk["mu_B"], muB), ("mu_M", pk["mu_M"], muM), ("R", pk["R"], R)):
                checks[f"packets_regen_{nm}"] = float(np.max(np.abs(mine - theirs)))
    else:                                                        # new mount-45 case: regenerated packets (m45_gen/)
        pk = np.load(pk_path)
        spec = dict(anchor=tuple(float(v) for v in pk["anchor"]), robot_z_m=0.45, mount_deg=float(pk["mount_deg"]))
        t = pk["t_s"]; gt = pk["truth_scoring_only"]; z = pk["z"]; muB, muM, R = pk["mu_B"], pk["mu_M"], pk["R"]
        P0 = np.diag(np.r_[INITIAL_POSE_STD ** 2, math.radians(0.1) ** 2]); accB0 = None; jb = jm = 0
    ds, gy, dt, x0 = build_controls(t, gt[:, :3], a.bias)
    if a.case in C.CASES and a.bias in ("B0", "L2"):
        tr = C.load_control(a.case, a.bias); stored = tr
        for nm, src in (("mu", "mu"), ("R", "R")):
            checks[f"packets_{nm}_equal_B0"] = float(np.max(np.abs(tr[src].astype(float) - ref[src].astype(float))))
        dss, gys, _ = C.controls_from(tr["x"][:, jb], tr["prior"][:, jb], t)
        checks["controls_ds_vs_trace"] = float(np.max(np.abs(ds[1:] - dss[1:])))
        checks["controls_gyro_vs_trace"] = float(np.max(np.abs(gy[1:] - gys[1:])))
        checks["x0_vs_trace"] = float(np.max(np.abs(np.r_[x0, 0.0] - tr["prior"][0, jb])))
    for kk, v in checks.items():
        if kk.startswith(("packets_", "controls_", "x0_")) and v > 1e-10:
            raise RuntimeError(f"PARITY_FAIL {kk}={v}")
    acc = gated_mask(z, muB, R, ds, gy, dt, np.r_[x0, 0.0], P0, spec, model)
    if stored:
        checks["mask_vs_trace_mismatch"] = float(np.sum(acc != stored["acc"][:, jb].astype(bool)))
        if checks["mask_vs_trace_mismatch"] > 0:
            raise RuntimeError(f"MASK_PARITY_FAIL {checks['mask_vs_trace_mismatch']}")
    if accB0 is not None:
        checks["mask_changed_vs_B0"] = float(np.sum(acc != accB0))
    checks["accept_fraction"] = float(acc.mean())
    hg, _ = model.batch(np.c_[gt[:, :3], np.zeros(len(t))], spec)
    D = dict(t=t, gt=gt, z=z, R=R, acc=acc, ds=ds, gy=gy, dt=dt,
             x0=np.r_[x0, 0.0], P0=P0, spec=spec, anchor=np.array(spec["anchor"][:2]), hg=hg)
    mus = dict(BB=muB, MB=muM)
    es = z[:, 1] - hg[:, 1]
    rows = []
    for name, bg, cfg in ARMS:
        if a.arms != "all" and name not in a.arms.split(","):
            continue
        if cfg["mode"] == "vartab":
            cfg = dict(cfg); cfg["table"], cfg["table_key"] = resolve_table(cfg, a.case)
        t0 = time.time(); X, PX, B, nwin = run(D, mus[bg], cfg, model)
        r = dict(sig_tag=a.tag or "m0table", case=a.case, mount=spec["mount_deg"], anchor=a.case[4], route=a.case[:2], bias=a.bias, arm=name, background=bg,
                 method=name.split("_", 1)[1], nwin=nwin, sec=round(time.time() - t0, 1), table=cfg.get("table_key", ""))
        r.update(scores(D, X, PX))
        if cfg["mode"] in ("gm", "win"):
            acc = D["acc"]; esm = es - mus[bg][:, 1]
            r["b_corr"] = float(np.corrcoef(B[acc], esm[acc])[0, 1]); r["b_resid_rms"] = float(np.sqrt(np.mean((esm - B)[acc] ** 2)))
            r["es_rms"] = float(np.sqrt(np.mean(esm[acc] ** 2)))
        if cfg["mode"] == "orig" and stored:
            r["parity_vs_trace"] = float(np.max(np.abs(X - stored["x"][:, jb if bg == "BB" else jm])))
            if r["parity_vs_trace"] > 1e-8:
                raise RuntimeError(f"ORIG_PARITY_FAIL {name} {r['parity_vs_trace']}")
        rows.append(r); print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
    tag = f"{a.case}_{a.bias}" + (f"_{a.tag}" if a.tag else "")
    C.OUT.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(C.OUT / f"PB_SCORES_{tag}.csv", index=False)
    (C.OUT / f"PB_META_{tag}.json").write_text(json.dumps(dict(case=a.case, bias=a.bias, checks=checks, arms=[n for n, _, _ in ARMS],
                                                              sig_table=dict(r=SIG_R.tolist(), sig=SIG_V.tolist())), indent=1))


if __name__ == "__main__":
    main()
