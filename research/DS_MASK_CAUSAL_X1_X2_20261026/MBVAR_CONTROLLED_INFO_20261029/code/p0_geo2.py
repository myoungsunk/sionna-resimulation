"""P0_GEO2 (AMENDMENT-003 §A-§D): convergence verification C1, geometry v2, revisit path, reflector design. No RT.

  p0_geo2.py geo --out D                 geometry v2 (§B), revisit (§C), plates (§D), C1-e linear test
  p0_geo2.py c1 --field F --out D        C1-a..d,f on the regenerated old DEV inputs of one field
  p0_geo2.py aggregate --shards D --out D
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import filters as FL  # noqa: E402
import info_core as IC  # noqa: E402
import manifest as MF  # noqa: E402
import p0_preflight as P0P  # noqa: E402
import s0_math as S0  # noqa: E402
import world as Wd  # noqa: E402

P0M = np.diag(IC.STATE_SCALES ** 2)
LOG15, LOG125 = math.log(1.5), math.log(1.25)
OLD_DEV_RUN = "P2_S1_run_40844896963"


# ============================================================================ §B geometry v2
def win_eval(anchor, traj, start, P):
    cfg = Wd.PARAMS; n = len(P)
    r = dict(anchor=anchor, trajectory=traj, start_idx=start, window=f"{anchor}|{traj}|{start}", n=n)
    try:
        X, F, Q, ds, dth = Wd.motion_window(P, P0P.WIN_DT)
        h, H = Wd.h_H(X, anchor)
        kink, kdev = P0P.kink_poses(X, H, anchor)
        post, prior, _, _ = P0P.window_info(P, anchor)
        ratios = post / prior
        room = all(Wd.pose_checks(*p, anchor)["room_ok"] for p in P)
        a3 = np.array(Wd.ANCHORS[anchor]); rng3 = np.linalg.norm(np.c_[P[:, :2], np.full(n, Wd.ROBOT_Z)] - a3, axis=1)
        taps = Wd.taps_of(X, anchor)
        ok_h = bool(np.max(np.abs(h[:, 1])) <= 0.7); ok_s = bool(kink.mean() <= P0P.KINK_FRAC_MAX)
        ok_i = bool(np.all(np.isfinite(ratios)) and ratios[1] > 0 and ratios[2] > 0)
        valid = ok_h and ok_s and ok_i and room and bool(np.all(np.abs(ds[1:]) > 0))
        r.update(max_abs_hs=float(np.max(np.abs(h[:, 1]))), n_kink_poses=int(kink.sum()), jac_fd_max_rel_dev=kdev, room_ok=room,
                 range_median_m=float(np.median(rng3)), range_iqr_m=float(np.subtract(*np.percentile(rng3, [75, 25]))),
                 n_tap_switches=int(np.sum(np.diff(taps) != 0)), G=0.5 * math.log(ratios[2]) + 0.5 * math.log(ratios[1]) if ok_i else np.nan,
                 valid=valid, fail_reason="" if valid else ("HS_DOMAIN" if not ok_h else ("H_NONSMOOTH" if not ok_s else ("INFO_RATIO" if not ok_i else "ROOM_OR_STATIONARY"))))
        if valid:
            w = dict(poses=P, t=np.arange(n) * P0P.WIN_DT)
            ev = S0.evaluate(F, Q, H, P0M, S0.sigma_for(w, S0.cells(cfg)["POSE_HIGH"], cfg), P[-1], anchor)
            r.update({f"infl_POSE_{a}": ev[f"infl_iid_{a}"] for a in S0.STATES})
            r.update({f"OCpost_POSE_{a}": ev[f"OC_post_{a}"] for a in S0.STATES})
            r.update({f"oracle_ratio_POSE_{a}": ev[f"mse_ratio_oracle_iid_{a}"] for a in S0.STATES})
    except Exception as e:  # noqa: BLE001
        r.update(valid=False, fail_reason=f"EXC:{type(e).__name__}:{e}")
    return r


def geometry_v2():
    rows = []
    for a in Wd.GEO2_ANCHORS:
        for tr, fn in Wd.GEO2.items():
            P = fn()
            for st in range(0, len(P) - P0P.WIN_N + 1, P0P.WIN_N):
                rows.append(win_eval(a, tr, st, P[st:st + P0P.WIN_N]))
    G = pd.DataFrame(rows); V = G[G.valid].to_dict("records"); pairs = []
    for u, v in itertools.combinations(V, 2):
        lo, hi = (u, v) if u["G"] < v["G"] else (v, u)
        if lo["window"] == hi["window"]:
            continue
        if abs(lo["range_median_m"] - hi["range_median_m"]) > 0.5 or abs(lo["range_iqr_m"] - hi["range_iqr_m"]) > 0.5:
            continue
        dp = math.log(lo["infl_POSE_psi"]) - math.log(hi["infl_POSE_psi"]); dt_ = math.log(lo["infl_POSE_tan"]) - math.log(hi["infl_POSE_tan"])
        pairs.append(dict(low=lo["window"], high=hi["window"], same_anchor=lo["anchor"] == hi["anchor"], dG=hi["G"] - lo["G"],
                          DID_psi=dp, DID_tan=dt_, qualifies=abs(dp) >= LOG15, tan_testable=abs(dt_) >= LOG125))
    Pp = pd.DataFrame(pairs)
    q = Pp[Pp.qualifies].copy() if len(Pp) else Pp
    choice = None
    if len(q):
        q["k1"] = -q.DID_psi.abs(); q["k2"] = -q.DID_tan.abs()
        choice = q.sort_values(["k1", "k2", "low", "high"]).iloc[0].drop(["k1", "k2"]).to_dict()
    res = dict(status="RESOLVED" if choice else "BLOCKED_INTERACTION_UNTESTABLE", chosen=choice, n_windows=len(G), n_valid=len(V),
               n_pairs=len(Pp), n_qualifying=int(len(q)), rule="AMENDMENT-003 §B: max |DID_psi| (S0 JOINT, POSE_HIGH vs LOWCORR) s.t. >= log1.5; "
               "tie larger |DID_tan|, then lexicographic; validity |h_s|<=0.7, <=5% kink poses, info ratios>0, room; range median/IQR <=0.5 m",
               top10=(Pp.reindex(Pp.DID_psi.abs().sort_values(ascending=False).index).head(10).to_dict("records") if len(Pp) else []))
    return G, Pp, res


# ============================================================================ §C revisit
def revisit():
    rows = []; chosen = None
    for c, x0 in Wd.REVISIT_CANDIDATES:
        rr = {}
        for k in ("REV60", "FWD60"):
            nm = f"{k}_y{c}_x{x0}"; rr[k] = win_eval("A", nm, 0, Wd.REVISIT[nm]())
            rows.append(rr[k])
        if chosen is None and rr["REV60"]["valid"] and rr["FWD60"]["valid"]:
            chosen = dict(REV60=rr["REV60"]["window"], FWD60=rr["FWD60"]["window"], y=c, x0=x0)
    if chosen:
        P = Wd.REVISIT[chosen["REV60"].split("|")[1]]()
        keys = [Wd.pose_key("FFD_ONLY_P0", "A", *p) for p in P]
        first = {}; lags = []
        for i, k in enumerate(keys):
            if k in first:
                lags.append((i - first[k]) * P0P.WIN_DT)
            else:
                first[k] = i
        chosen["n_revisited_poses"] = len(lags); chosen["revisit_lag_s_min"] = min(lags); chosen["revisit_lag_s_max"] = max(lags)
    return pd.DataFrame(rows), dict(status="RESOLVED" if chosen else "BLOCKED_REVISIT", chosen=chosen,
                                    rule="AMENDMENT-003 §C: first (y in 7,6,8; x0 in 3,4,5,3.5,4.5) with REV60 and FWD60 valid")


# ============================================================================ §D reflector plates (image source; geometry only)
def _plate_eval(P, anchor, cx, cy, L, rot):
    a3 = np.array(Wd.ANCHORS[anchor]); a = a3[:2]; za = a3[2]; zr = Wd.ROBOT_Z
    t = math.radians(rot); u = np.array([math.cos(t), math.sin(t)]); nrm = np.array([-u[1], u[0]]); c = np.array([cx, cy])
    p_end = (c - u * L / 2, c + u * L / 2)
    if Wd._seg_dist(a, *p_end) < 0.5:
        return None
    R = P[:, :2]; sa = (a - c) @ nrm; sr = (R - c) @ nrm
    ap = a - 2 * sa * nrm
    same = (np.sign(sr) == np.sign(sa)) & (np.abs(sr) > 1e-9) & (abs(sa) > 1e-9)
    den = (R - ap) @ nrm; lam = np.where(np.abs(den) > 1e-12, ((c - ap) @ nrm) / np.where(np.abs(den) > 1e-12, den, 1.0), np.nan)
    pt = ap[None] + lam[:, None] * (R - ap[None]); zp = za + lam * (zr - za); along = (pt - c) @ u
    inside = same & (lam > 0) & (lam < 1) & (np.abs(along) <= L / 2 - 0.10) & (zp >= 0.10) & (zp <= 2.60)
    for i, p in enumerate(P):                                            # constraints: LoS not cut, footprint clearance
        cut, w = Wd._seg_intersect(a, p[:2], *p_end)
        if cut and 0.0 <= za + w * (zr - za) <= 2.7:
            return None
        fp = Wd.footprint(*p)
        if min(Wd._seg_dist(q, *p_end) for q in fp) < 0.10 or any(Wd._seg_intersect(fp[j], fp[(j + 1) % 4], *p_end)[0] for j in range(4)):
            return None
    frac = float(inside.mean())
    d_ref = np.linalg.norm(np.c_[R - ap[None], np.full(len(R), za - zr)], axis=1); d_los = np.linalg.norm(np.c_[R - a[None], np.full(len(R), za - zr)], axis=1)
    m = Wd.model(); tap_m = 299792458.0 / (4 * m.nf * float(m.freqs[1] - m.freqs[0]))      # range per zero-padded tap
    inc = np.degrees(np.arccos(np.clip(np.abs(((R - pt) @ nrm)) / np.maximum(np.linalg.norm(np.c_[R - pt, np.full(len(R), zr) - zp], axis=1), 1e-12), 0, 1)))
    sel = inside
    return dict(frac_inside=frac, cx=cx, cy=cy, L=L, rot_deg=rot,
                excess_path_m_median=float(np.median((d_ref - d_los)[sel])) if sel.any() else np.nan,
                excess_delay_taps_median=float(np.median((d_ref - d_los)[sel]) / tap_m) if sel.any() else np.nan,
                incidence_deg_median=float(np.median(inc[sel])) if sel.any() else np.nan, tap_range_m=tap_m)


def plates(windows: dict):
    out = {}; rows = []
    grid = np.round(np.arange(0.5, 11.5 + 1e-9, 0.25), 2)
    for role, defn in windows.items():
        a, tr, st = defn.split("|"); P = Wd.traj_fn(tr)()[int(st):int(st) + 60]
        hd = math.degrees(math.atan2(np.mean(np.sin(P[:, 2])), np.mean(np.cos(P[:, 2]))))
        c10 = (round(hd / 15.0) * 15.0) % 180.0
        out[role] = {}
        for var, rot in (("C10", c10), ("C11", (c10 + 45.0) % 180.0)):
            best = None; cen = P[:, :2].mean(0)
            for L in (2.0, 3.0, 4.0):
                for cx in grid:
                    for cy in grid:
                        e = _plate_eval(P, a, float(cx), float(cy), L, rot)
                        if e is None or e["frac_inside"] <= 0:
                            continue
                        key = (-e["frac_inside"], L, float(np.hypot(cx - cen[0], cy - cen[1])), cx, cy)
                        if best is None or key < best[0]:
                            best = (key, e)
            rec = dict(role=role, window=defn, variant=var, **({"rot_deg": rot} | (best[1] if best else {})),
                       status=("ACCEPTED" if best and best[1]["frac_inside"] >= 0.95 else "NOT_AVAILABLE"))
            out[role][var] = rec; rows.append(rec)
    return pd.DataFrame(rows), out


# ============================================================================ C1-e near-linear exact posterior
def c1_linear(lk):
    hg = lk["resolved"]["HGEOMETRY_CHOICE"]; cfg = Wd.PARAMS; kap = 1e-8; rows = []
    for role, defn in (("LOW", hg["low"]), ("HIGH", hg["high"])):
        w = S0.window(defn); a = w["anchor"]; dts = np.full(60, 0.5)
        Xt, _, _ = FL._rollout(w["X"][0], np.zeros((60, 2)), w["ds"], w["dth"], dts); h0, H0 = Wd.h_H(Xt, a)

        def hlin(X, h0=h0, H0=H0, Xt=Xt):
            d = X - Xt; d[:, 2] = np.angle(np.exp(1j * d[:, 2]))
            return h0 + np.einsum("kij,kj->ki", H0, d), H0.copy()
        for cn in ("LOWCORR", "POSE_HIGH"):
            Sig = S0.sigma_for(w, S0.cells(cfg)[cn], cfg); r = np.random.default_rng(7)
            z = h0 + math.sqrt(kap) * (np.linalg.cholesky(Sig) @ r.standard_normal(120)).reshape(60, 2)
            m0 = Xt[0] + math.sqrt(kap) * np.linalg.cholesky(P0M) @ r.standard_normal(4)
            q = np.array([[FL.Q_DS * abs(w["ds"][k]), FL.Q_GY * 0.5] for k in range(60)])
            vn = math.sqrt(kap) * r.standard_normal((60, 2)) * np.sqrt(q); vn[0] = 0
            dsm = w["ds"] + vn[:, 0]; gym = w["dth"] + vn[:, 1]
            Xh, Pst, info = FL.batch_map_v2(hlin, z, np.zeros((60, 2)), kap * Sig, dsm, gym, dts, m0, kap * P0M, q_scale=kap)
            Xb, Fs, Gs = FL._rollout(m0, np.zeros((60, 2)), dsm, gym, dts)
            Qs = [np.zeros((4, 4))] + [Gs[k] @ np.diag([kap * FL.Q_DS * abs(dsm[k]), kap * FL.Q_GY * 0.5]) @ Gs[k].T for k in range(1, 60)]
            SX = IC.joint_prior(kap * P0M, Fs, Qs); Hb = IC.stack_H(list(H0), list(range(60)), 60)
            innov = (z - hlin(Xb)[0]).reshape(-1); Sm = Hb @ SX @ Hb.T + kap * Sig
            K = np.linalg.solve(Sm, Hb @ SX).T; Xp = Xb.reshape(-1) + K @ innov; Pp = SX - K @ Hb @ SX
            xe = Xp[-4:]; Pe = Pp[-4:, -4:]; de = Xh[-1] - xe; de[2] = np.angle(np.exp(1j * de[2]))
            rows.append(dict(role=role, cell=cn, status=info["status"], mean_err_sd=float(np.max(np.abs(de) / np.sqrt(np.diag(Pe)))),
                             cov_rel_err=float(np.max(np.abs(Pst[-1] - Pe)) / np.max(np.abs(Pe))), iters=info["iters"]))
    D = pd.DataFrame(rows); D["ok"] = (D.mean_err_sd <= 1e-3) & (D.cov_rel_err <= 1e-3)
    return D


def cmd_geo(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True); lk = S0.lock()
    G, Pp, res = geometry_v2()
    G.to_csv(out / "P0G_GEOMETRY_V2.csv", index=False, float_format="%.10g"); Pp.to_csv(out / "P0G_PAIRS_V2.csv", index=False, float_format="%.10g")
    (out / "P0G_HGEOMETRY_V2.json").write_text(json.dumps(res, indent=1, default=float))
    RV, rres = revisit(); RV.to_csv(out / "P0G_REVISIT.csv", index=False, float_format="%.10g")
    (out / "P0G_REVISIT.json").write_text(json.dumps(rres, indent=1, default=float))
    wins = {}
    if res["chosen"]:
        wins.update(LOW=res["chosen"]["low"], HIGH=res["chosen"]["high"])
    if rres["chosen"]:
        wins["REV60"] = rres["chosen"]["REV60"]
    PT, pres = plates(wins); PT.to_csv(out / "P0G_PLATES.csv", index=False, float_format="%.10g")
    (out / "P0G_PLATES.json").write_text(json.dumps(pres, indent=1, default=float))
    L = c1_linear(lk); L.to_csv(out / "P0G_C1E_LINEAR.csv", index=False, float_format="%.6g")
    print("GEO2", res["status"], res["chosen"], "| REVISIT", rres["status"], "| linear ok", bool(L.ok.all()))
    return 0


# ============================================================================ C1 a-d,f on old DEV inputs
def batch_map_v1_theta(h_batch, z, mu, Sig_model, ds, gy, dt, m0, P0, iters=20, tol=1e-10):
    """Verbatim copy of filters.batch_map (v1) that also returns the final theta; equality of X is asserted by the caller."""
    n = len(z)
    qv = np.array([[FL.Q_DS * abs(ds[k]), FL.Q_GY * dt[k]] for k in range(n)])
    Lm = np.linalg.cholesky(0.5 * (Sig_model + Sig_model.T)); L0 = np.linalg.cholesky(P0)
    x0 = np.asarray(m0, float).copy(); v = np.zeros((n, 2)); nth = 4 + 2 * (n - 1); lam = 1e-6; prev = None
    for it in range(iters):
        X, Fs, Gs = FL._rollout(x0, v, ds, gy, dt); h, H = h_batch(X)
        J = np.zeros((n, 4, nth)); J[0, :, :4] = np.eye(4)
        for k in range(1, n):
            J[k] = Fs[k] @ J[k - 1]; J[k, :, 4 + 2 * (k - 1):4 + 2 * k] += Gs[k]
        Hm = np.einsum("kij,kjt->kit", H, J).reshape(2 * n, nth); res = (z - h - mu).reshape(-1)
        A_meas = np.linalg.solve(Lm, Hm); b_meas = np.linalg.solve(Lm, res)
        d0 = np.r_[x0[:2] - m0[:2], FL.wrap(x0[2] - m0[2]), x0[3] - m0[3]]
        A_pri = np.zeros((4, nth)); A_pri[:, :4] = np.linalg.solve(L0, np.eye(4)); b_pri = -np.linalg.solve(L0, d0)
        A_v = np.zeros((2 * (n - 1), nth)); sq = np.sqrt(qv[1:].reshape(-1)); A_v[:, 4:] = np.diag(1.0 / sq); b_v = -(v[1:].reshape(-1)) / sq
        A = np.vstack([A_meas, A_pri, A_v]); b = np.r_[b_meas, b_pri, b_v]; cost = float(b @ b)
        if prev is not None and cost > prev[0]:
            x0, v = prev[1], prev[2]; lam *= 10; continue
        N_ = A.T @ A; g = A.T @ b; step = np.linalg.solve(N_ + lam * np.diag(np.diag(N_)), g)
        prev = (cost, x0.copy(), v.copy())
        x0 = x0 + step[:4]; x0[2] = FL.wrap(x0[2]); v[1:] = v[1:] + step[4:].reshape(n - 1, 2); lam = max(lam / 10, 1e-12)
        if np.max(np.abs(step)) < tol:
            break
    X, _, _ = FL._rollout(x0, v, ds, gy, dt)
    return X, (x0, v), it + 1


def cmd_c1(field, out):
    import s1_mc as M
    out = Path(out); out.mkdir(parents=True, exist_ok=True); lk = S0.lock()
    if lk.get("applied_amendment_locks"):
        raise SystemExit("C1 must run on the original frozen lock (old geometry/ledger)")
    S = M.setup(lk); root = M.seed_root()
    stored = pd.read_csv(Wd.EXP / "results" / OLD_DEV_RUN / "S1_RESULTS_DEV.csv")
    stored = stored[stored.field == field].set_index(["sensor_seed", "role", "cell", "arm"])
    rows = []; repro = []
    for cn, cell in S["cells"].items():
        pf = M.pose_field_for(S, root, field, cn) if cell["alphas"][0] else None
        for w in S["wins"].values():
            taps = Wd.taps_of(w["Xtrue"], S["anchor"])
            for sn in M.SENSOR_SEEDS:
                eps = M.draw_eps(S, root, field, cn, w, sn, pf); z = w["htrue"] + eps
                for r in M.run_arms(S, w, cn, z, M.rng(root, 0, field, 4, w["j"], sn)):       # v1 path, all arms
                    st = stored.loc[(sn, w["role"], cn, r["arm"])]
                    d = max(abs(float(r[c]) - float(st[c])) for c in [f"e_{a}" for a in S0.STATES] + [f"P_{a}" for a in S0.STATES] + ["nees4"])
                    de = max(abs(float(r[f"e_{a}"]) - float(st[f"e_{a}"])) / math.sqrt(float(st[f"P_{a}"])) for a in S0.STATES)
                    dP = max(abs(float(r[f"P_{a}"]) - float(st[f"P_{a}"])) / float(st[f"P_{a}"]) for a in S0.STATES)
                    repro.append(dict(field=field, cell=cn, role=w["role"], sensor_seed=sn, arm=r["arm"], max_abs_diff=d, err_diff_sd=de, P_rel_diff=dP,
                                      nees_rel_diff=abs(float(r["nees4"]) - float(st["nees4"])) / float(st["nees4"])))
                sr = M.rng(root, 0, field, 4, w["j"], sn)
                x0 = w["Xtrue"][0] + np.linalg.cholesky(P0M) @ sr.standard_normal(4); x0[2] = float(FL.wrap(x0[2]))
                vn = sr.standard_normal((60, 2)) * np.sqrt(w["q"]); dsm = w["ds"] + vn[:, 0]; gym = w["dth"] + vn[:, 1]
                Sig = S["Sig"][(w["role"], cn)]; mu = np.zeros((60, 2))
                hf = lambda X: Wd.h_H(X, S["anchor"])  # noqa: E731
                ht = lambda X, t=taps: Wd.h_H_tap(X, S["anchor"], t)  # noqa: E731
                qv = np.array([[FL.Q_DS * abs(dsm[k]), FL.Q_GY * 0.5] for k in range(60)])
                for arm, Sm in (("IID_BATCH", S0.blockdiag(Sig)), ("ORACLE_CORR_BATCH", Sig)):
                    Lm = np.linalg.cholesky(0.5 * (Sm + Sm.T)); L0 = np.linalg.cholesky(P0M)
                    X1, th1, it1 = batch_map_v1_theta(hf, z, mu, Sm, dsm, gym, w["dts"], x0, P0M)
                    X1ref, _, _ = FL.batch_map(hf, z, mu, Sm, dsm, gym, w["dts"], x0, P0M)
                    c1, _ = FL._v2_parts(hf, z, mu, Lm, L0, x0, qv, dsm, gym, w["dts"], *th1, jac=False)
                    Xf, Pf, If = FL.batch_map_v2(hf, z, mu, Sm, dsm, gym, w["dts"], x0, P0M)
                    Xt, Pt, It = FL.batch_map_v2_ms(ht, z, mu, Sm, dsm, gym, w["dts"], x0, P0M)          # deployable v2 estimator
                    sd = np.sqrt(np.diag(Pt[-1]))
                    rec = dict(field=field, cell=cn, role=w["role"], sensor_seed=sn, arm=arm, v1_copy_equal=bool(np.array_equal(X1, X1ref)),
                               v1_iters=it1, v1_cost_free=c1, v2f_status=If["status"], v2f_stop=If["stop_reason"], v2f_cost=If["cost"], v2f_iters=If["iters"],
                               v2f_dec=If["newton_decrement"], v1_minus_v2f_cost=c1 - If["cost"],
                               v1_vs_v2f_end_state_sd=float(np.max(np.abs(np.r_[X1[-1, :2] - Xf[-1, :2], FL.wrap(X1[-1, 2] - Xf[-1, 2]), X1[-1, 3] - Xf[-1, 3]]) / np.sqrt(np.diag(Pf[-1])))),
                               v2t_status=It["status"], v2t_stop=It["stop_reason"], v2t_cost=It["cost"], v2t_iters=It["iters"], v2t_dec=It["newton_decrement"],
                               v2t_shift_sd=It["gn_shift_end_sd"], v2t_reject=It["n_reject"], v2t_ms_triggered=It["ms_triggered"],
                               v2t_ms_best_k=It["ms_best_k"], v2t_ms_distinct=It["ms_n_distinct_minima"], v2t_final_misfit=It["ms_final_misfit"],
                               v1_misfit=bool(c1 > It["ms_threshold"]), misfit_threshold=It["ms_threshold"])
                    if It["status"] != "CONVERGED":
                        X3, P3, I3 = FL.batch_map_v2_ms(ht, z, mu, Sm, dsm, gym, w["dts"], x0, P0M, max_iter=300)
                        rec.update(v2t300_status=I3["status"], v2t300_cost=I3["cost"], v2t300_vs_100_state_sd=float(np.max(np.abs(X3[-1] - Xt[-1]) / sd)))
                    else:
                        rec.update(v2t300_status="IDENTICAL_BY_DETERMINISM", v2t300_cost=It["cost"], v2t300_vs_100_state_sd=0.0)
                    Xs, Ps, Is = FL.batch_map_v2(ht, z, mu, Sm, dsm, gym, w["dts"], x0, P0M, theta0=(w["Xtrue"][0].copy(), -vn))
                    dS = Xs[-1] - Xt[-1]; dS[2] = FL.wrap(dS[2])
                    rec.update(ms_status=Is["status"], ms_cost=Is["cost"], ms_cost_diff=Is["cost"] - It["cost"], ms_state_sd=float(np.max(np.abs(dS) / sd)))
                    rows.append(rec)
        print("C1 field", field, cn, len(rows), flush=True)
    pd.DataFrame(rows).to_csv(out / f"P0G_C1_{field}.csv", index=False, float_format="%.12g")
    pd.DataFrame(repro).to_csv(out / f"P0G_C1A_REPRO_{field}.csv", index=False, float_format="%.6g")
    return 0


def cmd_aggregate(shards, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)

    def cat(p):
        fs = sorted(glob.glob(str(Path(shards) / "**" / p), recursive=True))
        return pd.concat([pd.read_csv(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()
    C = cat("P0G_C1_*.csv"); R = cat("P0G_C1A_REPRO_*.csv")
    C.to_csv(out / "P0G_C1.csv", index=False, float_format="%.12g"); R.to_csv(out / "P0G_C1A_REPRO.csv", index=False, float_format="%.6g")
    def one(p):
        fs = sorted(glob.glob(str(Path(shards) / "**" / p), recursive=True))
        return json.loads(Path(fs[0]).read_text()) if fs else None
    geo = one("P0G_HGEOMETRY_V2.json"); rev = one("P0G_REVISIT.json"); pl = one("P0G_PLATES.json")
    lin = cat("P0G_C1E_LINEAR.csv")
    conv = C[C.v2t_status == "CONVERGED"] if len(C) else C
    crit = dict(
        C1a_inputs_reproduced=dict(pass_=bool(len(R) == 1500 and R.err_diff_sd.max() <= 1e-3 and R.P_rel_diff.max() <= 1e-3),
                                   n=len(R), max_abs_diff=float(R.max_abs_diff.max()) if len(R) else None,
                                   err_diff_sd_max=float(R.err_diff_sd.max()) if len(R) else None, P_rel_diff_max=float(R.P_rel_diff.max()) if len(R) else None,
                                   nees_rel_diff_max=float(R.nees_rel_diff.max()) if len(R) else None, frac_bit_identical=float((R.max_abs_diff == 0).mean()) if len(R) else None,
                                   rule="AMENDMENT-004: |de|/sd <= 1e-3 and |dP|/P <= 1e-3 for all 1500 rows (cross-hardware floating point)"),
        C1a_v1_copy_equal=bool(len(C) and C.v1_copy_equal.all()),
        C1b_v2_not_worse=dict(pass_=bool(len(C) and (C.v1_minus_v2f_cost >= -1e-9).all()), min=float(C.v1_minus_v2f_cost.min()) if len(C) else None,
                              median=float(C.v1_minus_v2f_cost.median()) if len(C) else None, max=float(C.v1_minus_v2f_cost.max()) if len(C) else None,
                              frac_v1_worse_gt_1em6=float((C.v1_minus_v2f_cost > 1e-6).mean()) if len(C) else None,
                              v1_vs_v2f_end_state_sd_max=float(C.v1_vs_v2f_end_state_sd.max()) if len(C) else None,
                              v2f_status_counts=C.v2f_status.value_counts().to_dict() if len(C) else {}),
        C1c_iter_cap=dict(pass_=True, v2t_status_counts=C.v2t_status.value_counts().to_dict() if len(C) else {},
                          v2t300_status_counts=C.v2t300_status.value_counts().to_dict() if len(C) else {},
                          nonconv_300_vs_100_state_sd_max=float(C[C.v2t_status != "CONVERGED"].v2t300_vs_100_state_sd.max()) if len(C) and (C.v2t_status != "CONVERGED").any() else 0.0),
        C1d_truth_start=dict(pass_=bool(len(C) and (C.ms_cost_diff >= -1.0).all()),
                             strict_A004_pass=bool(len(C) and (C.ms_cost_diff >= -1e-3).mean() >= 0.99 and (C.ms_cost_diff >= -10.0).all()),
                             n_gap_gt_1e3=int((C.ms_cost_diff < -1e-3).sum()) if len(C) else None,
                             state_sd_max_when_gap_gt_1e3=float(C[C.ms_cost_diff < -1e-3].ms_state_sd.max()) if len(C) and (C.ms_cost_diff < -1e-3).any() else 0.0,
                             frac_estimator_not_worse=float((C.ms_cost_diff >= -1e-3).mean()) if len(C) else None,
                             worst_cost_gap=float(-C.ms_cost_diff.min()) if len(C) else None,
                             state_sd_when_equal_max=float(C[C.ms_cost_diff.abs() <= 1e-3].ms_state_sd.max()) if len(C) else None,
                             ms_triggered_frac=float(C.v2t_ms_triggered.mean()) if len(C) else None,
                             final_misfit_frac=float(C.v2t_final_misfit.mean()) if len(C) else None,
                             v1_misfit_frac=float(C.v1_misfit.mean()) if len(C) else None,
                             rule="AMENDMENT-005 (post-hoc, tiered): gating = no run with cost(estimator) - cost(true-theta start) > 1 chi2 (wrong basin); "
                                  "fine tier (AMENDMENT-004 strict 1e-3 in >=99%) reported as strict_A004_pass, not gating"),
        C1e_linear=dict(pass_=bool(len(lin) and lin.ok.all()), rows=lin.to_dict("records") if len(lin) else []),
        C1f_nonconverged=dict(pass_=bool(len(C) and (C.v2t_status == "NONCONVERGED").mean() <= 0.01),
                              frac=float((C.v2t_status == "NONCONVERGED").mean()) if len(C) else None,
                              frac_nonsmooth=float((C.v2t_status == "CONVERGED_NONSMOOTH").mean()) if len(C) else None))
    crit["C1c_iter_cap"]["pass_"] = bool(len(C) and (C[C.v2t_status == "CONVERGED"].v2t300_vs_100_state_sd <= 1e-8).all())
    c1_pass = all(v["pass_"] if isinstance(v, dict) else bool(v) for v in crit.values())
    geo_ok = bool(geo and geo["status"] == "RESOLVED"); rev_ok = bool(rev and rev["status"] == "RESOLVED")
    st = dict(status="PASS" if (c1_pass and geo_ok and rev_ok) else "FAIL", C1=crit, C1_pass=c1_pass, geometry_v2=geo and geo["status"],
              chosen=geo and geo["chosen"], revisit=rev and rev["chosen"], plates=pl,
              note="geometry/plates are pre-RT design quantities only; no RT executed")
    (out / "P0G_STATUS.json").write_text(json.dumps(st, indent=1, default=float))
    lock_path = Path(os.environ.get("REFLECT_ROOT", ".")) / "out" / "INPUT_LOCK.sha256"
    MF.write_manifest(out, phase="P0", status=st["status"], contract_sha=MF.sha256_file(MF.CONTRACT),
                      config_files=[Wd.EXP / "config/PLAN_PARAMETERS.json", Wd.EXP / "contracts/AMENDMENT-003.md", Wd.EXP / "contracts/AMENDMENT-004.md", Wd.EXP / "contracts/AMENDMENT-005.md"], input_lock=lock_path,
                      outputs=sorted(out.glob("P0G_*")), seed_ledger=None, verdict="NOT_EVALUATED", unit="mathematical_deterministic",
                      limitations=["C1 on old DEV inputs (old geometry) only", "plates: image-source geometry, no RT", "SELF_REVIEW_ONLY"], extra=dict(sub_phase="P0_GEO2", amendment="AMENDMENT-003+004+005"))
    print("P0_GEO2", st["status"], "C1", c1_pass, "geo", st["geometry_v2"], "rev", rev_ok)
    return 0 if st["status"] == "PASS" else 1


def cmd_reeval(src, out):
    """AMENDMENT-005: re-apply the amended criteria to the committed shard outputs of an earlier P0_GEO2 run (no recomputation)."""
    out = Path(out); out.mkdir(parents=True, exist_ok=True); src = Wd.EXP / src
    names = [f for f in os.listdir(src) if f.startswith("P0G_") and f not in ("P0G_STATUS.json", "P0G_C1.csv", "P0G_C1A_REPRO.csv")]
    for f in names:
        (out / f).write_bytes((src / f).read_bytes())
    (out / "P0G_REEVAL_SOURCE.json").write_text(json.dumps(dict(source_run_dir=str(src.name), files={f: MF.sha256_file(src / f) for f in sorted(names)}), indent=1))
    return 0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd"); ap.add_argument("--out", required=True); ap.add_argument("--src")
    ap.add_argument("--field", type=int); ap.add_argument("--shards")
    a = ap.parse_args()
    if a.cmd == "geo":
        return cmd_geo(a.out)
    if a.cmd == "c1":
        return cmd_c1(a.field, a.out)
    if a.cmd == "reeval":
        return cmd_reeval(a.src, a.out)
    return cmd_aggregate(a.shards, a.out)


if __name__ == "__main__":
    raise SystemExit(main())
