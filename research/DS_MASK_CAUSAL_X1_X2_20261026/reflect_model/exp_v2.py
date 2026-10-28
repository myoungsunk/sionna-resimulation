"""V2: recursive EKF replay with the reflection-aware polarization observer.  Requires V1_DECISION.json (PASS or APPROXIMATE).

  python exp_v2.py [--cases all|primary] [--biases B0,L2] [--workers 4] [--fp-range]

Everything except the polarization observer (and, for the *_RS arms, R_ss) is the frozen E1 contract:
same controls (recovered exactly from the stored OFF_BB arm), same z, same mu_r, same A_B acceptance mask,
same joint 2x2 update with Joseph covariance.  The LOS arms must reproduce OFF_BB / OFF_MB to 1e-10 before
any REF arm of that condition is scored.

Arms
  LOS_BB / LOS_MB           original LOS observer, mu_s as stored              (parity with E1)
  REF_BB / REF_MB           reflection observer, mu_s = 0, R as stored         (primary)
  REF_BB_MUS / REF_MB_MUS   reflection observer, mu_s as stored                (does the learned mean double-count?)
  REF_BB_RS / REF_MB_RS     reflection observer, mu_s = 0, R_ss from V1 residual variance by estimated distance,
                            leave-one-route-out (the route itself never sets its own R)
  ORPOL_BB / ORPOL_MB       LOS observer, z_s := LOS model at GT + mu_s        (oracle reference, not deployable)
  REF_FPR (--fp-range)      reflection observer for s AND first-path range, mu_r = mu_s = 0 (exploratory)
"""
from __future__ import annotations

import argparse
import json
import math
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

import common as C

PARITY_TOL = 1e-10
RS_FLOOR = 0.01 ** 2
DECISION = dict(heading_improve_routes_min=5, mb_better_primary_min=2, max_route_worsening=0.10)


# ------------------------------------------------------------------ inputs
def prep(case: str, bias: str) -> dict:
    z = C.load_control(case, bias)
    jb, jm = z["jb"], z["jm"]
    t = z["t_s"]
    gt = z["truth_scoring_only"]
    acc = z["acc"][:, jb].astype(bool)
    if not (z["acc"][:, jm].astype(bool) == acc).all():
        raise RuntimeError("MASK_DIFFERS_BETWEEN_ARMS")
    zm = z["nu"][:, jb] + z["h"][:, jb] + z["mu"][:, jb]
    if np.nanmax(abs(zm - (z["nu"][:, jm] + z["h"][:, jm] + z["mu"][:, jm]))) > 1e-12:
        raise RuntimeError("MEASUREMENT_DIFFERS_BETWEEN_ARMS")
    if np.max(abs(z["R"][:, jb] - z["R"][:, jm])) > 0:
        raise RuntimeError("R_DIFFERS_BETWEEN_ARMS")
    ds, gy, dt = C.controls_from(z["x"][:, jb], z["prior"][:, jb], t)
    ds2, gy2, _ = C.controls_from(z["x"][:, jm], z["prior"][:, jm], t)
    if max(np.max(abs(ds - ds2)), np.max(abs(gy - gy2))) > 1e-12:
        raise RuntimeError("CONTROLS_DIFFER_BETWEEN_ARMS")
    case_d = C.CASES[case]
    a = np.array(case_d["anchor"][:2])
    rg = np.hypot(gt[:, 0] - a[0], gt[:, 1] - a[1])
    return dict(case=case, bias=bias, cfg=case_d, t=t, gt=gt, acc=acc, z=zm, muB=z["mu"][:, jb], muM=z["mu"][:, jm],
                R=z["R"][:, jb], ds=ds, gy=gy, dt=dt, x0=z["prior"][0, jb].copy(), P0=z["Pprior"][0, jb].copy(),
                ref_BB=z["x"][:, jb], ref_MB=z["x"][:, jm], a=a, rg=rg)


def loro_rs(case: str):
    """R_ss(rho_hat) from V1 residual variance of the OTHER routes (pooled by distance bin, n-weighted)."""
    df = pd.read_csv(C.OUT / "V1_RS_BY_BIN.csv")
    route = case.split("_")[0]
    other = df[~df.case.str.startswith(route + "_")]
    table = []
    for (lo, hi), g in other.groupby(["bin_lo", "bin_hi"]):
        var = float(np.sum(g.n * (g.res_var + g.res_mean ** 2)) / max(g.n.sum(), 1))   # mean-square residual
        table.append((lo, hi, max(var, RS_FLOOR)))
    table.sort()

    def f(x, p, Rk):
        rho = math.hypot(x[0] - p["a"][0], x[1] - p["a"][1])
        R = Rk.copy()
        for lo, hi, v in table:
            if lo <= rho < hi:
                R[1, 1] = v
        return R
    return f, table


# ------------------------------------------------------------------ filter
def run(p, observer, mu_r, mu_s, Rfun=None, zs_override=None):
    """One recursive replay.  mu_r, mu_s: (n,) arrays.  Returns trajectories and per-packet diagnostics."""
    n = len(p["t"])
    x, P = p["x0"].copy(), p["P0"].copy()
    X = np.zeros((n, 4)); PR = np.zeros((n, 4)); NU = np.full((n, 2), np.nan); NIS_S = np.full(n, np.nan)
    for k in range(n):
        if k:
            x, P = C.predict_one(x, P, p["ds"][k], p["gy"][k], p["dt"][k])
        PR[k] = x
        if p["acc"][k]:
            zk = p["z"][k].copy()
            if zs_override is not None:
                zk[1] = zs_override[k]
            h, H = observer.batch(x[None], p["cfg"], gradient=True)
            h, H = h[0], H[0]
            Rk = p["R"][k] if Rfun is None else Rfun(x, p, p["R"][k])
            v = zk - h - np.array([mu_r[k], mu_s[k]])
            S = H @ P @ H.T + Rk
            S = 0.5 * (S + S.T)
            K = np.linalg.solve(S, H @ P).T
            x = x + K @ v
            x[2] = C.wrap(x[2])
            A = np.eye(4) - K @ H
            P = A @ P @ A.T + K @ Rk @ K.T
            P = 0.5 * (P + P.T)
            NU[k] = v
            NIS_S[k] = v[1] ** 2 / S[1, 1]
        X[k] = x
    if not np.isfinite(X).all():
        raise RuntimeError("NONFINITE_STATE")
    return dict(x=X, prior=PR, nu=NU, nis_s=NIS_S)


# ------------------------------------------------------------------ metrics
def score(p, o):
    t, gt, x = p["t"], p["gt"], o["x"]
    s = t >= 30 - 1e-9
    he = np.degrees(C.wrap(x[:, 2] - gt[:, 2]))
    xy = np.hypot(x[:, 0] - gt[:, 0], x[:, 1] - gt[:, 1])
    A3 = np.array(p["cfg"]["anchor"])
    zt = float(p["cfg"]["robot_z_m"])
    d_true = np.linalg.norm(np.column_stack([gt[:, :2], np.full(len(t), zt)]) - A3, axis=1)
    d_est = np.linalg.norm(np.column_stack([x[:, :2], np.full(len(t), zt)]) - A3, axis=1)
    out = dict(head_rmse=float(np.sqrt(np.mean(he[s] ** 2))), head_bias=float(np.mean(he[s])),
               xy_rmse_m=float(np.sqrt(np.mean(xy[s] ** 2))), range_rmse_cm=float(100 * np.sqrt(np.mean((d_est - d_true)[s] ** 2))),
               nis_s_mean=float(np.nanmean(o["nis_s"][s])))
    # first pass: post-60 s window, GT tangential axis
    eps = C.first_pass(p["rg"])
    if eps and len(eps[0]):
        ke = eps[0][-1]
        w = (t > t[ke]) & (t <= t[ke] + 60)
        ur = (gt[:, :2] - p["a"]) / np.maximum(p["rg"][:, None], 1e-9)
        ut = np.column_stack([-ur[:, 1], ur[:, 0]])
        et = np.sum((x[:, :2] - gt[:, :2]) * ut, axis=1)
        out.update(post60_head_mean=float(np.mean(he[w])), post60_tan_mean_cm=float(100 * np.mean(et[w])),
                   post60_xy_rmse_cm=float(100 * np.sqrt(np.mean(xy[w] ** 2))))
    return out


# ------------------------------------------------------------------ one condition
def condition(case: str, bias: str, variant: str, fp_range: bool):
    from refl_model import ReflectiveFFD
    t0 = time.time()
    base = C.base_model()
    depth, mode = int(variant[1]), variant.split("_", 1)[1]
    ref = ReflectiveFFD(base, max_depth=depth, material_mode=mode, range_mode="geometric")
    p = prep(case, bias)
    n = len(p["t"])
    zero = np.zeros(n)
    rows, parity = [], {}
    # parity first: stop this condition if the LOS replay does not reproduce E1
    for arm, mu_r, ref_x in (("LOS_BB", p["muB"][:, 0], p["ref_BB"]), ("LOS_MB", p["muM"][:, 0], p["ref_MB"])):
        o = run(p, base, mu_r, p["muB"][:, 1])
        err = float(np.max(abs(o["x"] - ref_x)))
        parity[arm] = err
        rows.append(dict(case=case, bias=bias, arm=arm, parity_err=err, **score(p, o)))
    if max(parity.values()) > PARITY_TOL:
        return rows, dict(case=case, bias=bias, status="PARITY_FAIL", parity=parity)
    Rrs, rs_table = loro_rs(case)
    # oracle polarization: LOS model at GT + stored mu_s
    hg, _ = base.batch(np.column_stack([p["gt"][:, :3], np.zeros(n)]), p["cfg"], gradient=False)
    zs_or = hg[:, 1] + p["muB"][:, 1]
    arms = []
    for tag, mu_r in (("BB", p["muB"][:, 0]), ("MB", p["muM"][:, 0])):
        arms += [(f"REF_{tag}", dict(observer=ref, mu_r=mu_r, mu_s=zero)),
                 (f"REF_{tag}_MUS", dict(observer=ref, mu_r=mu_r, mu_s=p["muB"][:, 1])),
                 (f"REF_{tag}_RS", dict(observer=ref, mu_r=mu_r, mu_s=zero, Rfun=Rrs)),
                 (f"ORPOL_{tag}", dict(observer=base, mu_r=mu_r, mu_s=p["muB"][:, 1], zs_override=zs_or))]
    if fp_range:
        ref_fp = ReflectiveFFD(base, max_depth=depth, material_mode=mode, range_mode="fp")
        arms.append(("REF_FPR", dict(observer=ref_fp, mu_r=zero, mu_s=zero)))
    for arm, kw in arms:
        o = run(p, **kw)
        rows.append(dict(case=case, bias=bias, arm=arm, **score(p, o)))
    return rows, dict(case=case, bias=bias, status="OK", parity=parity, rs_table=rs_table, sec=round(time.time() - t0, 1))


def decide(df: pd.DataFrame):
    """Pre-registered V2 decisions (see PROTOCOL_REFLECT.md)."""
    out = {}
    piv = df.pivot_table(index=["case", "bias"], columns="arm", values="head_rmse")
    xy = df.pivot_table(index=["case", "bias"], columns="arm", values="xy_rmse_m")
    for bias in sorted(df.bias.unique()):
        pv = piv.xs(bias, level="bias")
        xv = xy.xs(bias, level="bias")
        improve = int(((pv["REF_BB"] < pv["LOS_BB"]) & (pv["REF_MB"] < pv["LOS_MB"])).sum())
        worst = float(np.nanmax([(pv["REF_BB"] / pv["LOS_BB"]).max(), (pv["REF_MB"] / pv["LOS_MB"]).max()]) - 1)
        prim = [c for c in C.PRIMARY if c in pv.index]
        mb_better = int(sum((pv.loc[c, "REF_MB"] <= pv.loc[c, "REF_BB"]) and (xv.loc[c, "REF_MB"] <= xv.loc[c, "REF_BB"]) for c in prim))
        out[bias] = dict(D1_routes_improved=improve, D1_pass=improve >= DECISION["heading_improve_routes_min"],
                         D2_primary_mb_better=mb_better, D2_pass=mb_better >= DECISION["mb_better_primary_min"],
                         D3_worst_route_worsening=worst, D3_pass=worst <= DECISION["max_route_worsening"])
    return out


def aggregate(v1):
    """Merge per-shard outputs (V2_SCORES_<tag>.csv, V2_META_<tag>.json) and apply the decisions."""
    parts = sorted(C.OUT.glob("V2_SCORES_*.csv"))
    if not parts:
        raise SystemExit("no V2 shards found")
    df = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    meta = [m for p in sorted(C.OUT.glob("V2_META_*.json")) for m in json.loads(p.read_text())]
    df.to_csv(C.OUT / "V2_SCORES.csv", index=False)
    ok = [m for m in meta if m["status"] == "OK"]
    okset = {(m["case"], m["bias"]) for m in ok}
    keep = df[[(c, b) in okset for c, b in zip(df.case, df.bias)]]
    res = dict(v1_status=v1["status"], variant=v1["chosen_variant"], conditions=len(meta), parity_ok=len(ok),
               parity_failures=[m for m in meta if m["status"] != "OK"],
               decisions=decide(keep) if len(keep) else None, meta=meta)
    (C.OUT / "V2_RESULT.json").write_text(json.dumps(res, indent=1, default=float))
    C.write_manifest("V2", dict(variant=v1["chosen_variant"], decision_rule=DECISION, shards=[p.name for p in parts]),
                     ["V2_SCORES.csv", "V2_RESULT.json"])
    print(json.dumps(res["decisions"], indent=1, default=float))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default="all", help="all | primary | one case id (e.g. R4_aA_m0)")
    ap.add_argument("--biases", default="B0,L2")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--fp-range", action="store_true")
    ap.add_argument("--aggregate", action="store_true", help="only merge existing shards and decide")
    a = ap.parse_args()
    v1 = json.loads((C.OUT / "V1_DECISION.json").read_text())
    if v1["status"] not in ("PASS", "APPROXIMATE"):
        raise SystemExit(f"V1 status {v1['status']}: V2 not run")
    if a.aggregate:
        return aggregate(v1)
    variant = v1["chosen_variant"]
    cases = list(C.CASES) if a.cases == "all" else list(C.PRIMARY) if a.cases == "primary" else [a.cases]
    if not set(cases) <= set(C.CASES):
        raise SystemExit(f"unknown case {a.cases}")
    tag = a.cases
    jobs = [(c, b, variant, a.fp_range) for c in cases for b in a.biases.split(",")]
    rows, meta = [], []
    if a.workers > 1:
        with ProcessPoolExecutor(a.workers) as ex:
            for r, m in ex.map(condition, *zip(*jobs)):
                rows += r; meta.append(m); print(m, flush=True)
    else:
        for j in jobs:
            r, m = condition(*j)
            rows += r; meta.append(m); print(m, flush=True)
    pd.DataFrame(rows).to_csv(C.OUT / f"V2_SCORES_{tag}.csv", index=False)
    (C.OUT / f"V2_META_{tag}.json").write_text(json.dumps(meta, indent=1, default=float))
    C.write_manifest(f"V2_{tag}", dict(variant=variant, cases=cases, biases=a.biases, fp_range=a.fp_range),
                     [f"V2_SCORES_{tag}.csv", f"V2_META_{tag}.json"])
    if a.cases in ("all", "primary"):
        aggregate(v1)


if __name__ == "__main__":
    main()
