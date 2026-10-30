"""P2_S1V3 (AMENDMENT-008): the S1V2 design on DEV2 with input receipts, post-fit covariance conventions and a P-free
convergence class.

  s1v3.py run --fields 10,11 --split DEV2 --out D
  s1v3.py aggregate --shards D --split DEV2 --out D        (env S0V2_RESULTS_DIR)

The estimator E (filters.batch_map_v2_ms), its MAP state, basin and cost are unchanged (A8-2). P and the convergence class
are re-evaluated at the fixed estimate theta_hat (A8-3, A8-4). Inputs are drawn exactly as in S1V2 (same RNG keys).
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a8_jac as AJ  # noqa: E402
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import s0_math as S0  # noqa: E402
import s0v2 as S0V2  # noqa: E402
import s1_mc as M  # noqa: E402
import s1v2 as V  # noqa: E402
import world as Wd  # noqa: E402

STATES = S0.STATES; N = V.N; P0M = M.P0
RHO, TAU, N_DIR = 0.01, 0.01, 8                     # A8-4 probe: radius (prior-scaled), cost tolerance (chi^2), direction pairs
SPREAD_MAX = 0.05                                   # A8-3 KINK_P_UNCERTAIN threshold
EKF_ARMS = tuple(a for a in V.LH_ARMS if not a.endswith("_BATCH"))
_R64 = np.random.default_rng(12345).standard_normal(2 * N)


def lock_v3():
    lk = S0V2.lock_v2()
    if "AMENDMENT-008" not in lk.get("applied_amendment_locks", []):
        raise SystemExit("ERR_CONTRACT_DRAFT: AMENDMENT-008 lock not FROZEN/applied")
    return lk


def sig_fp(S):
    """Covariance fingerprint: trace, Frobenius norm, S @ r (fixed r)."""
    return np.r_[np.trace(S), np.linalg.norm(S), S @ _R64]


def key_seed(*k):
    return int(hashlib.sha256("|".join(map(str, k)).encode()).hexdigest()[:15], 16)


def pose_keys_sha(w):
    return hashlib.sha256("\n".join(Wd.pose_key("FFD_ONLY_P0", "A", *p) for p in w["poses"]).encode()).hexdigest()


def make_inputs(S, root, f, cn, w, sn, pf):
    """Exactly the S1V2 inputs: z from V.draw; x0 then control noise from rng(root,0,f,4,j,sensor) (as V.run_arms)."""
    eps, Up, Ut = V.draw(S, root, f, cn, w, sn, pf); z = w["htrue"] + eps
    sr = M.rng(root, 0, f, 4, w["j"], sn)
    x0 = w["Xtrue"][0] + np.linalg.cholesky(P0M) @ sr.standard_normal(4); x0[2] = float(FL.wrap(x0[2]))
    vn = sr.standard_normal((N, 2)) * np.sqrt(w["q"]); ds_m = w["ds"] + vn[:, 0]; gy_m = w["dth"] + vn[:, 1]
    return dict(eps=eps, Up=Up, Ut=Ut, z=z, x0=x0, vn=vn, ds_m=ds_m, gy_m=gy_m)


def arm_models(S, w, cn):
    Sig = S["Sig"][(w["role"], cn)]; d = {"IID_BATCH": S0.blockdiag(Sig), "ORACLE_CORR_BATCH": Sig}
    if w["role"] in ("REV60", "FWD60") and cn in S0V2.XMODEL:
        d["XMODEL_BATCH"] = S["Sig"][(w["role"], S0V2.XMODEL[cn])]
    return Sig, d


def _mats(Sm, ds_m, dts):
    qv = np.array([[FL.Q_DS * abs(ds_m[k]), FL.Q_GY * dts[k]] for k in range(len(ds_m))])
    return np.linalg.cholesky(0.5 * (Sm + Sm.T)), np.linalg.cholesky(P0M), qv


def post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, theta, T):
    """A8-3: for every Jacobian convention, P = J (A'A)^-1 J' at the fixed theta. Returns per-method rotated end diag,
    PD flags, cond(A'A), the analytic Newton decrement, cost, rel_spread and KINK_P_UNCERTAIN."""
    Lm, L0, qv = _mats(Sm, ds_m, dts); mu = np.zeros_like(z); th0, thv = theta; out = {}; dg = {}; pd_ok = True; gn = {}
    for m in AJ.METHODS:
        c, X, A, b, J = FL._v2_parts(AJ.h_batch_for(m, hb), z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, th0, thv)
        Nm = A.T @ A; Nm = 0.5 * (Nm + Nm.T); ev = np.linalg.eigvalsh(Nm); gn[m] = np.linalg.solve(Nm, A.T @ b)
        Pe = J[-1] @ np.linalg.inv(Nm) @ J[-1].T; Pe = 0.5 * (Pe + Pe.T); pev = np.linalg.eigvalsh(Pe)
        ok = bool(ev[0] > 0 and pev[0] > 0); pd_ok &= ok
        dg[m] = np.diag(T @ Pe @ T.T)
        out.update({f"P_{m}_{a}": float(dg[m][i]) for i, a in enumerate(STATES)})
        out[f"pd_{m}"] = ok; out[f"cond_{m}"] = float(ev[-1] / ev[0]) if ev[0] > 0 else float("inf")
        if m == "A":
            g = A.T @ b; out["dec_A_fixed"] = float(g @ np.linalg.solve(Nm, g)); out["cost_fixed"] = c; out["_PA_end"] = Pe; out["_X"] = X
    ref = dg[AJ.PRIMARY]
    out["rel_spread"] = float(max(np.max(np.abs(dg[m] - ref) / ref) for m in AJ.METHODS))
    out["KINK_P_UNCERTAIN"] = bool(out["rel_spread"] > SPREAD_MAX or not pd_ok)
    out["_gn_steps"] = gn
    return out


GN_ALPHAS = (1.0, 0.5, 0.1, 0.01)                  # A8-4 line probes along each convention's Gauss-Newton step


def probe_min_dcost(hb, z, Sm, ds_m, gy_m, dts, x0, theta, seed, gn_steps, rho=RHO, n_dir=N_DIR):
    """A8-4 objective probe at theta (no P involved):
      (i) line probes theta + alpha * s_m for every Jacobian convention m (s_m its Gauss-Newton step), alpha in GN_ALPHAS;
      (ii) 2*n_dir random +- directions of radius rho in prior-scaled coordinates (x0 / sqrt diag P0, v_k / sqrt q_k).
    Returns (min cost change, label of the minimising probe, its theta displacement)."""
    Lm, L0, qv = _mats(Sm, ds_m, dts); mu = np.zeros_like(z); th0, thv = theta; n = len(z)
    scale = np.r_[np.sqrt(np.diag(P0M)), np.sqrt(qv[1:].reshape(-1))]
    c0, _ = FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, th0, thv, jac=False)

    def dc(d):
        x1 = th0 + d[:4]; x1[2] = FL.wrap(x1[2]); v1 = thv.copy(); v1[1:] = thv[1:] + d[4:].reshape(n - 1, 2)
        return FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, x1, v1, jac=False)[0] - c0
    best = (np.inf, "", None)
    for m, s in gn_steps.items():
        for a in GN_ALPHAS:
            v = dc(a * s)
            if v < best[0]:
                best = (v, f"gn_{m}_{a:g}", a * s)
    r = np.random.default_rng(seed)
    for i in range(n_dir):
        u = r.standard_normal(len(scale)); d = rho * scale * u / np.linalg.norm(u)
        for sg, lab in ((1.0, "+"), (-1.0, "-")):
            v = dc(sg * d)
            if v < best[0]:
                best = (v, f"rand{i}{lab}", sg * d)
    return float(best[0]), best[1], best[2]


POLISH_TOL, POLISH_MAX = 1e-3, 30                  # AMENDMENT-008 E' polish: accept probe descents > 1e-3 chi^2, <= 30 steps


def polish(hb, z, Sm, ds_m, gy_m, dts, x0, theta, seed):
    """E' (AMENDMENT-008 decision 2026-10-30): from theta, repeatedly take the best descending probe (GN steps of all six
    Jacobian conventions + random prior-scaled directions) while it lowers the cost by more than POLISH_TOL.
    Deterministic given the seed. Returns (theta', n_steps, total cost decrease, hit_cap)."""
    th0, thv = theta[0].copy(), theta[1].copy(); n = len(z); total = 0.0
    for k in range(POLISH_MAX):
        pf = post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, (th0, thv), np.eye(4))
        if pf["dec_A_fixed"] <= FL.V2_DEC_TOL:
            return (th0, thv), k, total, False
        dmin, _, d = probe_min_dcost(hb, z, Sm, ds_m, gy_m, dts, x0, (th0, thv), seed + k, pf["_gn_steps"])
        if not dmin < -POLISH_TOL:
            return (th0, thv), k, total, False
        th0 = th0 + d[:4]; th0[2] = FL.wrap(th0[2]); thv = thv.copy(); thv[1:] = thv[1:] + d[4:].reshape(n - 1, 2); total -= dmin
    return (th0, thv), POLISH_MAX, total, True


def probe_power(hb, z, Sm, ds_m, gy_m, dts, x0, theta, seed, target=1.0):
    """C3 PROBE_POWER negative control: displace theta along a random prior-scaled direction until the cost rises by
    ~target chi^2 (in [0.5, 2] x target), then classify the displaced point. A powered probe must return NOT_CERTIFIED."""
    Lm, L0, qv = _mats(Sm, ds_m, dts); mu = np.zeros_like(z); th0, thv = theta; n = len(z)
    scale = np.r_[np.sqrt(np.diag(P0M)), np.sqrt(qv[1:].reshape(-1))]
    u = np.random.default_rng(seed).standard_normal(len(scale)); u = scale * u / np.linalg.norm(u)

    def disp(t):
        x1 = th0 + t * u[:4]; x1[2] = FL.wrap(x1[2]); v1 = thv.copy(); v1[1:] = thv[1:] + t * u[4:].reshape(n - 1, 2)
        return x1, v1
    c0 = FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, th0, thv, jac=False)[0]
    f = lambda t: FL._v2_parts(hb, z, mu, Lm, L0, x0, qv, ds_m, gy_m, dts, *disp(t), jac=False)[0] - c0  # noqa: E731
    lo, hi = 0.0, 1e-3
    while f(hi) < target and hi < 1e3:
        lo, hi = hi, 2 * hi
    for _ in range(30):
        if 0.5 * target <= f(hi) <= 2 * target:
            break
        mid = 0.5 * (lo + hi); (lo, hi) = (mid, hi) if f(mid) < target else (lo, mid)
    thd = disp(hi); rise = f(hi)
    pf = post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, thd, np.eye(4)); gn = pf.pop("_gn_steps")
    dmin, which, _ = probe_min_dcost(hb, z, Sm, ds_m, gy_m, dts, x0, thd, seed + 1, gn)
    return dict(pp_rise=float(rise), pp_dmin=dmin, pp_argmin=which, pp_class=class_v3(pf["dec_A_fixed"], dmin))


def class_v3(dec_A, dmin):
    if dec_A <= FL.V2_DEC_TOL:
        return "CONVERGED_SMOOTH"
    return "LOCAL_MIN_CERTIFIED" if dmin >= -TAU else "NOT_CERTIFIED"


def kink_count(X, taps):
    """Number of poses whose analytic H deviates from a 1e-6 central-FD H (pattern-cell kink within the FD stencil)."""
    h, H = Wd.h_H_tap(X, "A", taps); Hf = np.zeros_like(H)
    for j in range(4):
        d = np.zeros(4); d[j] = 1e-6
        Hf[:, :, j] = (Wd.h_H_tap(X + d, "A", taps)[0] - Wd.h_H_tap(X - d, "A", taps)[0]) / 2e-6
    return int((np.abs(Hf - H).max(axis=(1, 2)) / np.abs(H).max() > 1e-4).sum())


def dref_diff(Xa_end, Xb_end):
    d = np.asarray(Xa_end, float) - np.asarray(Xb_end, float); d[2] = FL.wrap(d[2])
    return float(np.max(np.abs(d) / D_REF))


D_REF = np.array([0.02, 0.02, math.radians(0.25), math.radians(0.01)])   # fixed external scale (2 cm, 2 cm, 0.25 deg, 0.01 deg/s)
POLISH_MAX_DREF, POLISH_MAX_DCOST = 2.0, 1.0                             # A8-2 scope bound on E -> E' (= C3 STATE_STABILITY max, NO_WRONG_BASIN tol)


def estimate(w, Sm, inp, seed_key, max_iter=FL.V2_MAX_ITER):
    """E' = batch_map_v2_ms (E, unchanged) followed by the polish. Returns (X_E, info_E, theta', X', polish record)."""
    hb = lambda X, t=w["taps"]: Wd.h_H_tap(X, "A", t)  # noqa: E731
    z, x0, ds_m, gy_m, dts = inp["z"], inp["x0"], inp["ds_m"], inp["gy_m"], w["dts"]
    X, _, info = FL.batch_map_v2_ms(hb, z, np.zeros((N, 2)), Sm, ds_m, gy_m, dts, x0, P0M, max_iter=max_iter)
    if info["newton_decrement"] <= FL.V2_DEC_TOL:                       # smooth convergence: nothing to polish
        thp, nst, cap = info["theta"], 0, False
    else:
        thp, nst, _, cap = polish(hb, z, Sm, ds_m, gy_m, dts, x0, info["theta"], key_seed("POLISH", *seed_key))
    Lm, L0, qv = _mats(Sm, ds_m, dts)
    cp, Xp = FL._v2_parts(hb, z, np.zeros((N, 2)), Lm, L0, x0, qv, ds_m, gy_m, dts, thp[0], thp[1], jac=False)
    rec = dict(polish_steps=nst, polish_cost_decrease=float(info["cost"] - cp), polish_hit_cap=bool(cap),
               polish_E_vs_Ep_dref=dref_diff(X[-1], Xp[-1]))
    rec["polish_within_scope"] = bool(rec["polish_E_vs_Ep_dref"] <= POLISH_MAX_DREF and rec["polish_cost_decrease"] <= POLISH_MAX_DCOST)
    return X, info, thp, Xp, float(cp), rec


def eval_batch(w, arm, Sm, inp, seed_key):
    """E' + A8-3 + A8-4 for one batch arm. Returns (row dict, X', info_E, theta')."""
    hb = lambda X, t=w["taps"]: Wd.h_H_tap(X, "A", t)  # noqa: E731
    z, x0, ds_m, gy_m, dts = inp["z"], inp["x0"], inp["ds_m"], inp["gy_m"], w["dts"]
    XE, info, thp, Xp, cp, prec = estimate(w, Sm, inp, seed_key)
    T = IC.rotation_rt(w["Xtrue"][-1], Wd.ANCHORS["A"])
    pf = post_fit_P(hb, z, Sm, ds_m, gy_m, dts, x0, thp, T); gn = pf.pop("_gn_steps"); PA = pf.pop("_PA_end"); pf.pop("_X")
    dmin, which, _ = probe_min_dcost(hb, z, Sm, ds_m, gy_m, dts, x0, thp, key_seed("CLASS", *seed_key), gn)
    row = dict(arm=arm, status="OK", conv=info["status"], class_v3=class_v3(pf["dec_A_fixed"], dmin), probe_min_dcost=dmin, probe_argmin=which,
               stop_reason=info["stop_reason"], iters=info["iters"], n_accept=info["n_accept"], n_reject=info["n_reject"], n_used=N,
               cost_E=info["cost"], cost=cp, cost_start0=info["ms_cost_start0"], cost_descent=info["ms_cost_start0"] - cp,
               newton_decrement=info["newton_decrement"], gn_shift_end_sd=info["gn_shift_end_sd"], ms_triggered=info["ms_triggered"],
               ms_best_k=info["ms_best_k"], ms_n_distinct_minima=info["ms_n_distinct_minima"], ms_final_misfit=info["ms_final_misfit"],
               rescued=info["rescued"], kink_poses_at_E=kink_count(Xp, w["taps"]), **prec, **pf)
    row.update(V._row_from(w, Xp, PA, "A"))             # e_*, P_* (analytic convention at theta'), nees4, window errors
    row.update({f"xend_{i}": float(Xp[-1, i]) for i in range(4)}); row.update({f"xendE_{i}": float(XE[-1, i]) for i in range(4)})
    return row, Xp, info, thp


def ekf_rows(S, w, cn, z, sensor_rng):
    """The descriptive recursive arms of S1V2 (unchanged code path; batch arms are not re-run here)."""
    keep = V.LH_ARMS
    try:
        V.LH_ARMS = EKF_ARMS
        rr, ctl = V.run_arms(S, w, cn, z, sensor_rng)
    finally:
        V.LH_ARMS = keep
    return rr, ctl


def revisit_pairs(S):
    rev = S["wins"]["REV60"]; first = {}; pairs = []
    for i, k in enumerate(rev["key_idx"]):
        if k in first:
            pairs.append((first[k], i))
        else:
            first[k] = i
    return pairs


def cmd_run(fields, split, out):
    lk = lock_v3(); M.check_code_lock(lk)
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    allowed = set(lk["splits"]["S_field"][split]); bad = [f for f in fields if f not in allowed]
    if bad:
        raise SystemExit(f"ERR_SPLIT_LEAK fields {bad} not in frozen {split}")
    root = M.seed_root(); S = V.setup(lk); rows = []; qa = []; seeds = []; rec = {}; pairs = revisit_pairs(S)
    for f in fields:
        for cn, cell in S["cells"].items():
            if not any(cn in w["cells"] for w in S["wins"].values()):
                continue
            pf = S["Lhalf"] @ M.rng(root, S0V2.CELL_ID_V2[cn], f, 1).standard_normal((S["Lhalf"].shape[1], 2)) if cell["alphas"][0] else None
            for w in S["wins"].values():
                if cn not in w["cells"]:
                    continue
                for sn in M.SENSOR_SEEDS:
                    inp = make_inputs(S, root, f, cn, w, sn, pf); z = inp["z"]
                    Sig, models = arm_models(S, w, cn); ev = inp["eps"].reshape(-1)
                    qa.append(dict(field=f, cell=cn, role=w["role"], sensor_seed=sn, check="mahalanobis_per_dim", value=float(ev @ np.linalg.solve(Sig, ev)) / (2 * N)))
                    if w["role"] == "REV60" and pairs:
                        if cell["alphas"][0]:
                            qa.append(dict(field=f, cell=cn, role="REV60", sensor_seed=sn, check="revisit_pose_identical_maxdiff",
                                           value=float(max(np.max(np.abs(inp["Up"][i] - inp["Up"][j])) for i, j in pairs))))
                        if cell["alphas"][1]:
                            qa.append(dict(field=f, cell=cn, role="REV60", sensor_seed=sn, check="revisit_time_differs_mindiff",
                                           value=float(min(np.max(np.abs(inp["Ut"][i] - inp["Ut"][j])) for i, j in pairs))))
                    kb = f"{f}|{w['role']}|{cn}|{sn}"
                    rec.update({f"{kb}|z": z, f"{kb}|ds_m": inp["ds_m"], f"{kb}|gy_m": inp["gy_m"], f"{kb}|x0": inp["x0"],
                                f"{kb}|taps": np.asarray(w["taps"]), f"{kb}|Sig_true_fp": sig_fp(Sig),
                                f"{kb}|pose_keys_sha": np.array(pose_keys_sha(w))})
                    base = dict(split=split, field=f, sensor_seed=sn, window=w["id"], role=w["role"], cell=cn)
                    seeds.append(dict(base, seed_root=root, cell_id=S0V2.CELL_ID_V2[cn], window_j=w["j"]))
                    if np.any(np.abs(z[:, 1]) > S["s1"]["physical_s_domain_abs_max"]) or not np.all(np.isfinite(z)):
                        rows.append(dict(base, arm="ALL", status="STOP_UNPHYSICAL_OBSERVATION")); continue
                    if w["role"] in ("LOW", "HIGH"):
                        rr, ctl = ekf_rows(S, w, cn, z, M.rng(root, 0, f, 4, w["j"], sn))
                        if not (np.array_equal(ctl["ds_m"], inp["ds_m"]) and np.array_equal(ctl["gy_m"], inp["gy_m"])):
                            raise SystemExit("ERR_INPUT_PATH: EKF and batch controls differ")
                        rows += [dict(base, **r) for r in rr]
                    for arm, Sm in models.items():
                        rec[f"{kb}|{arm}|Sig_model_fp"] = sig_fp(Sm)
                        try:
                            r = eval_batch(w, arm, Sm, inp, (f, w["role"], cn, sn, arm))[0]
                        except Exception as ex:  # noqa: BLE001
                            r = dict(arm=arm, status=f"FAILED:{type(ex).__name__}:{ex}")
                        rows.append(dict(base, **r))
        print("S1V3 field", f, "rows", len(rows), flush=True)
    tag = "_".join(map(str, fields))
    pd.DataFrame(rows).to_csv(out / f"S1V3_ROWS_{split}_{tag}.csv", index=False, float_format="%.17g")
    pd.DataFrame(qa).to_csv(out / f"S1V3_QA_{split}_{tag}.csv", index=False, float_format="%.17g")
    pd.DataFrame(seeds).to_csv(out / f"S1V3_SEEDS_{split}_{tag}.csv", index=False)
    with open(out / f"S1V3_INPUTS_{split}_{tag}.zip", "wb") as fh:       # NumPy savez archive; .zip keeps it out of git-LFS (*.npz)
        np.savez_compressed(fh, **rec)
    return 0


# ----------------------------------------------------------------------------- aggregate
def _bool(s):
    return s.astype(str).str.lower().isin(["true", "1"])


def with_P(rows, m):
    """Rows with the batch arms' P_* replaced by the method-m convention (EKF arms unchanged)."""
    r = rows.copy(); b = r.arm.astype(str).str.endswith("_BATCH") & (r.status == "OK")
    for a in STATES:
        r.loc[b, f"P_{a}"] = r.loc[b, f"P_{m}_{a}"]
    return r


def _summ(dm):
    return dict(verdict=dm["verdict"], **{k: [r["verdict"] for r in dm[k]] for k in ("H1", "H2", "H3", "CAL", "H4", "H4_REPRO")})


def calibration(b):
    """A8-5: ORACLE arm, primary P: mean(e^2/P) (field bootstrap of the field means), coverage |e|/sqrt(P) <= 1.96."""
    out = []; lf = math.log(1.5)
    o = b[b.arm == "ORACLE_CORR_BATCH"].copy()
    o["grp"] = np.where(o.role.isin(["LOW", "HIGH"]), "LH", "RV"); o["kink"] = o.kink_poses_at_E.astype(float) > 0
    for (grp, kink), d in o.groupby(["grp", "kink"]):
        for a in ("tan", "psi"):
            P = d[f"P_{AJ.PRIMARY}_{a}"].astype(float); e = d[f"e_{a}"].astype(float)
            t = pd.DataFrame(dict(field=d.field, z2=e ** 2 / P, cov=(e.abs() / np.sqrt(P) <= 1.96).astype(float)))
            ft = t.groupby("field")[["z2"]].mean()
            if len(ft) >= 2:
                bb = M.boot([ft], lambda m: math.log(m[0]["z2"])); v = M.band_verdict(bb["lo"], bb["hi"], lf)
            else:
                bb = dict(est=math.log(ft.z2.mean()) if len(ft) else np.nan, lo=np.nan, hi=np.nan); v = "UNDETERMINED"
            out.append(dict(group=grp, kink_at_E=bool(kink), state=a, n_runs=len(d), n_fields=len(ft), mean_z2=math.exp(bb["est"]),
                            lo=math.exp(bb["lo"]), hi=math.exp(bb["hi"]), coverage95=float(t["cov"].mean()), verdict=v))
    return pd.DataFrame(out)


def requested_fields():
    return sorted(json.loads((Wd.EXP / "RUN_REQUEST.json").read_text())["field_ids"])


def cmd_aggregate(shards, split, out):
    lk = lock_v3(); M.check_code_lock(lk); out = Path(out); out.mkdir(parents=True, exist_ok=True)
    plan = lk["run_plan"]["S1V3"]; eff = lk["resolved"]["EFFECT_SIZE_RULES"]

    def cat(pat):
        fs = sorted(glob.glob(str(Path(shards) / "**" / pat), recursive=True))
        return pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame(columns=["field", "status", "check", "value", "arm", "class_v3", "conv"])
    rows = cat(f"S1V3_ROWS_{split}_*.csv"); qa = cat(f"S1V3_QA_{split}_*.csv"); seeds = cat(f"S1V3_SEEDS_{split}_*.csv")
    npzs = sorted(glob.glob(str(Path(shards) / "**" / f"S1V3_INPUTS_{split}_*.zip"), recursive=True))
    for f in npzs:
        (out / Path(f).name).write_bytes(Path(f).read_bytes())
    expected = requested_fields()
    rule_ok = expected == sorted(plan["fields"]) and set(expected) <= set(lk["splits"]["S_field"][split])
    got = sorted(int(x) for x in rows.field.unique()) if len(rows) else []
    rows.to_csv(out / f"S1V3_RESULTS_{split}.csv", index=False, float_format="%.17g"); seeds.to_csv(out / "SEED_LEDGER.csv", index=False)
    qa.to_csv(out / f"S1V3_QA_{split}.csv", index=False, float_format="%.17g")
    mm = qa[qa.check == "mahalanobis_per_dim"].groupby(["role", "cell"]).value.mean(); mtol = 4 * math.sqrt(2 / (2 * N)) / math.sqrt(max(len(got), 1))
    rp = qa[qa.check == "revisit_pose_identical_maxdiff"].value; rt = qa[qa.check == "revisit_time_differs_mindiff"].value
    b = rows[rows.arm.astype(str).str.endswith("_BATCH") & (rows.status == "OK")].copy()
    if len(b):
        b["KINK_P_UNCERTAIN"] = _bool(b.KINK_P_UNCERTAIN)
    g = b.groupby(["arm", "role", "cell"])
    nc_new = g.class_v3.apply(lambda c: (int((c == "NOT_CERTIFIED").sum()), len(c))) if len(b) else pd.Series(dtype=object)
    nc_old = g.conv.apply(lambda c: (int((c == "NONCONVERGED").sum()), len(c))) if len(b) else pd.Series(dtype=object)
    n_exp = len(expected) * len(M.SENSOR_SEEDS) * (2 * len(V.LH_CELLS) * len(V.LH_ARMS) + 2 * (len(S0V2.REV_CELLS) * 3 - 1))
    fail_new = {"|".join(k): f"{v[0]}/{v[1]}" for k, v in nc_new.items() if v[0] > 0.01 * v[1]}
    qaj = dict(fields_expected=expected, fields_got=got, request_field_rule_ok=bool(rule_ok), mahalanobis_tol=mtol,
               mahalanobis_mean={f"{k[0]}|{k[1]}": float(v) for k, v in mm.items()},
               revisit_pose_identical_max=float(rp.max()) if len(rp) else None, revisit_time_differs_min=float(rt.min()) if len(rt) else None,
               stops=int((rows.status == "STOP_UNPHYSICAL_OBSERVATION").sum()), failures=int(rows.status.astype(str).str.startswith("FAILED").sum()),
               n_rows=int(len(rows)), n_rows_expected=n_exp, n_input_receipt_files=len(npzs),
               NOT_CERTIFIED_rule="ORIGINAL per-cell rule on class v3: NOT_CERTIFIED <= 1% per (arm, window, cell); pooled reported only",
               NOT_CERTIFIED_cells_failing=fail_new, NOT_CERTIFIED_pooled_REPORTED=float((b.class_v3 == "NOT_CERTIFIED").mean()) if len(b) else None,
               OLD_A007_NONCONVERGED_cells_failing_REPORTED={"|".join(k): f"{v[0]}/{v[1]}" for k, v in nc_old.items() if v[0] > 0.01 * v[1]},
               class_v3_counts=b.class_v3.value_counts().to_dict() if len(b) else {}, old_class_counts=b.conv.value_counts().to_dict() if len(b) else {},
               primary_P_pd_all=bool(_bool(b[f"pd_{AJ.PRIMARY}"]).all()) if len(b) else False,
               KINK_P_UNCERTAIN_frac=float(b.KINK_P_UNCERTAIN.mean()) if len(b) else None,
               KINK_P_UNCERTAIN_by_arm=b.groupby("arm").KINK_P_UNCERTAIN.mean().to_dict() if len(b) else {},
               rel_spread_q50_q90_q99_max=[float(x) for x in b.rel_spread.quantile([0.5, 0.9, 0.99, 1.0])] if len(b) else [],
               cost_fixed_vs_E_max=float((b.cost_fixed - b.cost).abs().max()) if len(b) else None,
               A82_polish_rows=int((b.polish_steps > 0).sum()) if len(b) else None,
               A82_polish_all_within_scope=bool(((b.polish_E_vs_Ep_dref <= POLISH_MAX_DREF) & (b.polish_cost_decrease <= POLISH_MAX_DCOST)).all()) if len(b) else False,
               A82_polish_max_cost_decrease=float(b.polish_cost_decrease.max()) if len(b) else None,
               A82_polish_max_E_vs_Ep_dref=float(b.polish_E_vs_Ep_dref.max()) if len(b) else None,
               A82_polish_hit_cap_n=int(_bool(b.polish_hit_cap).sum()) if len(b) else None,
               A82_old_class_by_polish={f"{k[0]}->{k[1]}": int(v) for k, v in b.groupby(["conv", "class_v3"]).size().items()} if len(b) else {})
    qaj["pass"] = bool(got == expected and rule_ok and len(mm) and all(abs(v - 1) <= mtol for v in mm.values) and qaj["revisit_pose_identical_max"] == 0.0
                       and (qaj["revisit_time_differs_min"] or 0) > 0 and qaj["stops"] == 0 and qaj["failures"] == 0 and qaj["n_rows"] == n_exp
                       and not fail_new and qaj["primary_P_pd_all"] and qaj["A82_polish_all_within_scope"])
    (out / "S1V3_QA.json").write_text(json.dumps(qaj, indent=1, default=float))
    s0d = Path(os.environ["S0V2_RESULTS_DIR"]); s0m = json.loads((s0d / "MANIFEST.json").read_text())
    s0_ok = s0m.get("execution_status") == "PASS" and s0m.get("contract_sha256") == MF.sha256_file(MF.CONTRACT)
    pred = pd.read_csv(s0d / "S0V2_PREDICTIONS.csv").set_index(["role", "cell"]); did_pred = pd.read_csv(s0d / "S0V2_DID.csv")
    rvpred = pd.read_csv(s0d / "S0V2_REVISIT.csv").set_index(["role", "cell", "arm"]); sep_pred = pd.read_csv(s0d / "S0V2_SEP.csv")
    ok = qaj["pass"] and s0_ok
    CAL = calibration(b) if len(b) else pd.DataFrame(columns=["verdict"])
    CAL.to_csv(out / f"S1V3_A85_CALIBRATION_{split}.csv", index=False, float_format="%.6g")
    cal_fail = bool((CAL.verdict == "FAIL").any()); cal_und = bool((CAL.verdict == "UNDETERMINED").any())
    sens = {}; prim = None
    if ok:
        for m in AJ.METHODS:
            dm = V.decide_v2(with_P(rows, m), pred, did_pred, rvpred, sep_pred, eff); sens[m] = _summ(dm)
            if m == AJ.PRIMARY:
                prim = dm
        unc = rows.copy(); bb = unc.arm.astype(str).str.endswith("_BATCH") & (unc.status == "OK")
        unc = unc[~(bb & _bool(unc.KINK_P_UNCERTAIN.fillna(False)))]
        sens[f"{AJ.PRIMARY}_without_KINK_P_UNCERTAIN"] = _summ(V.decide_v2(with_P(unc, AJ.PRIMARY), pred, did_pred, rvpred, sep_pred, eff))
        for k in ("H1", "H2", "H3", "CAL", "SENS", "H4", "H4_REPRO"):
            pd.DataFrame(prim[k]).to_csv(out / f"S1V3_{k}_{split}_{AJ.PRIMARY}.csv", index=False, float_format="%.8g")
    multi = len({json.dumps(v, sort_keys=True) for v in sens.values()}) > 1
    res = dict(split=split, qa_pass=qaj["pass"], s0_reference=s0d.name, s0_reference_ok=s0_ok,
               A85_calibration_fail=cal_fail, A85_calibration_undetermined=cal_und,
               A86_outcome="MULTIPLE_RESULTS_NO_SINGLE_ADOPTION" if multi else ("CONSISTENT_ACROSS_CONVENTIONS" if sens else "NOT_EVALUATED"),
               A86_sensitivity=sens, primary_convention=AJ.PRIMARY, primary_convention_note="numerical convention, validated only by A8-5",
               scientific_verdict_track_S="NOT_EVALUATED (DEV2 pilot)", release="TECHNICAL_QA_ONLY (SELF_REVIEW_ONLY)",
               holdout2="NO-GO until independent re-audit of S1V3 + C3", p3="NO-GO")
    if ok and prim is not None and not cal_fail and not multi:
        pw = M.power(dict(H1=prim["H1"], CAL=prim["CAL"], H2=prim["H2"], H3=prim["H3"]), len(got), plan, eff)
        pd.DataFrame(pw.pop("rows")).to_csv(out / f"S1V3_POWER_{split}.csv", index=False, float_format="%.6g")
        pw["holdout2_fields_if_opened_after_reaudit"] = lk["splits"]["S_field"]["HOLDOUT2"][:pw["n_confirm"]]; res["power"] = pw
    else:
        res["power"] = "NOT_COMPUTED (requires QA pass, no A8-5 CALIBRATION_FAIL, no A8-6 multiplicity)"
    (out / f"S1V3_DECISION_{split}.json").write_text(json.dumps(res, indent=1, default=M._json))
    status = "PASS" if ok else "FAIL"
    MF.write_manifest(out, phase="P2_S1", status=status, contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json"] + [Wd.EXP / f"contracts/AMENDMENT-00{i}.md" for i in range(3, 9)],
                      input_lock=Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256", outputs=sorted(out.glob("S1V3_*")),
                      seed_ledger=out / "SEED_LEDGER.csv", verdict="NOT_EVALUATED", unit="field_realization",
                      limitations=["DEV2 pilot only", "post-fit P convention C10 is numerical; statistical validity only via A8-5",
                                   "synthetic additive noise on the FFD LOS model; not RF physics", "SELF_REVIEW_ONLY; TECHNICAL_QA_ONLY"],
                      extra=dict(sub_phase="P2_S1V3", amendment="AMENDMENT-008"))
    print("S1V3 aggregate", split, status, "| A8-5 fail", cal_fail, "| A8-6", res["A86_outcome"])
    return 0 if status == "PASS" else 1


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--fields"); ap.add_argument("--split", required=True)
    ap.add_argument("--out", required=True); ap.add_argument("--shards")
    a = ap.parse_args()
    if a.cmd == "run":
        return cmd_run([int(x) for x in a.fields.split(",") if x != ""], a.split, a.out)
    return cmd_aggregate(a.shards, a.split, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
