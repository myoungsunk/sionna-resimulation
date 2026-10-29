"""Stage runner for PROTOCOL_CONTROLS_KO.md (one shard = stage x case x part).

  REFLECT_ROOT=<inputs> CTL_OUT=<out> python3 run_stage.py --stage A   --case R5_aA_m0
                                                       --stage E1  --case R5_aA_m0 --part s0|sx
                                                       --stage E4  --case R5_aA_m0 --part s0|sx
                                                       --stage E23 --case R5_aA_m0
                                                       --stage E6  --case R5_aA_m0
Every stage first checks seed-0 parity of the untouched arms against exp_pb.run (state diff <= 1e-10).
"""
from __future__ import annotations

import argparse
import math
import time
import traceback

import numpy as np
import pandas as pd

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctl_core as K  # noqa: E402

SMOKE = os.environ.get("CTL_SMOKE") == "1"          # local smoke test only: fewer seeds / m / reps
if SMOKE:
    K.SEEDS = [0, 1]

ARMS = {"BB_ORIG": ("BB", K.R_orig), "MB_ORIG": ("MB", K.R_orig), "MB_VAR": ("MB", K.R_var)}
CASE_ID = {c: i for i, c in enumerate(K.CASES)}


def tag(D, **kw):
    return dict(case=D["case"], route=D["case"][:2], anchor=D["case"][4], seed=D["seed"], **kw)


def s_summary(D, bg, L, z=None, prefix=""):
    """Compact S_base/all-window summary columns (s and r)."""
    out = {}
    for r in K.summarize(D, bg, L, sets=("S_base",), windows=False, z=z):
        c = r["comp"]
        for k in ("mr_eps2_R", "rm_eps2_R", "mr_dh2_HPH", "rm_dh2_HPH", "cross_share", "corr_eps_dh", "ell_share",
                  "mr_nu2_S", "acf_lag1"):
            if k in r:
                out[f"{prefix}{c}_{k}"] = r[k]
    return out


def parity(D):
    """Seed-0 parity of the published arms vs exp_pb.run (exact arithmetic)."""
    Dp = dict(t=D["t"], gt=D["gt"], z=D["z"], R=D["R0"], acc=D["acc"], ds=D["ds"], gy=D["gy"], dt=D["dt"], x0=D["x0"],
              P0=D["P0"], spec=D["spec"], anchor=D["anchor"], hg=D["hg"])
    out = {}
    for arm, (bg, Rf) in ARMS.items():
        mode = "var" if arm.endswith("VAR") else "orig"
        Xp, _, _, _ = K.PB.run(Dp, D["mu"][bg], dict(mode=mode), K.model())
        X, _, _ = K.run(D, bg, Rf)
        out[f"parity_{arm}"] = float(np.max(np.abs(X - Xp)))
        if out[f"parity_{arm}"] > 1e-10:
            raise RuntimeError(f"PARITY_FAIL {arm} {out[f'parity_{arm}']}")
    return out


# ============================================================================ stage A (C0 + E5)
def stage_A(case):
    rows_s, rows_sum, rows_info, rows_step, checks = [], [], [], [], {}
    T = K.mb_residual_table(0)
    cov_all = K.cov_table(T[T.route != case[:2]])
    for seed in K.SEEDS:
        D = K.load(case, seed)
        if seed == 0:
            checks.update(D["checks"]); checks.update(parity(D))
        logs = {}
        for arm, (bg, Rf) in ARMS.items():
            X, PX, L = K.run(D, bg, Rf); logs[arm] = (X, PX, L)
            rows_s.append(tag(D, arm=arm, **K.scores(D, X, PX)))
            for r in K.summarize(D, bg, L):
                rows_sum.append(tag(D, arm=arm, **r))
        if seed == 0:
            np.savez_compressed(K.OUT / f"A_LOG_{case}_s0.npz", **{f"{a}_{k}": np.asarray(v, np.float32)
                                for a, (X, PX, L) in logs.items() if a != "BB_ORIG"
                                for k, v in dict(X=X, PX=PX, xp=L["xp"], Pp=L["Pp"], nu=L["nu"], HPH=L["HPH"], Ru=L["Ru"],
                                                 hx=L["hx"], H=L["H"], upd=L["upd"]).items()},
                                t=D["t"], gt=D["gt"], z=D["z"], hg=D["hg"], acc=D["acc"])
            rows_info += e5_info(D, logs)
            rows_step += e5_onestep(D, logs, cov_all)
    pd.DataFrame(rows_s).to_csv(K.OUT / f"A_SCORES_{case}.csv", index=False, float_format="%.8g")
    pd.DataFrame(rows_sum).to_csv(K.OUT / f"A_SUMMARY_{case}.csv", index=False, float_format="%.8g")
    pd.DataFrame(rows_info).to_csv(K.OUT / f"E5_INFO_{case}.csv", index=False, float_format="%.8g")
    pd.DataFrame(rows_step).to_csv(K.OUT / f"E5_ONESTEP_{case}.csv", index=False, float_format="%.8g")
    return checks


def failure_window(D, X):
    e = K.state_err(D, X)[:, 2]; t = D["t"]; best = None
    for st in np.arange(30, t[-1] - 30 + 1e-9, 10.0):
        m = (t >= st) & (t < st + 30)
        v = float(np.mean(e[m] ** 2))
        if best is None or v > best[1]:
            best = (st, v)
    return best[0]


def e5_info(D, logs):
    rows = []; a = D["anchor"]; t = D["t"]
    for arm in ("MB_ORIG", "MB_VAR"):
        X, PX, L = logs[arm]
        fw = failure_window(D, X)
        wins = [(lo, min(hi, t[-1] + 1)) for lo, hi in K.WINDOWS] + [(fw, fw + 30)]
        for wi, (lo, hi) in enumerate(wins):
            m = (t >= lo) & (t < hi) & L["upd"].any(1)
            k0 = int(np.searchsorted(t, lo))
            if m.sum() < 3 or k0 >= len(t):
                continue
            I = np.zeros((4, 4))
            for k in np.flatnonzero(m):
                rws = [i for i in (0, 1) if L["upd"][k, i]]
                Hs = L["H"][k][rws]; Rs = L["Ru"][k][np.ix_(rws, rws)]
                I += Hs.T @ np.linalg.solve(Rs, Hs)
            km = np.flatnonzero(m)[len(np.flatnonzero(m)) // 2]
            ur = D["gt"][km, :2] - a; ur /= np.linalg.norm(ur)
            T4 = np.eye(4); T4[:2, :2] = np.array([ur, [-ur[1], ur[0]]])          # rows: radial, tangential
            P0 = L["Pp"][k0] if np.isfinite(L["Pp"][k0]).all() else PX[k0]
            Prt = T4 @ P0 @ T4.T; Irt = T4 @ I @ T4.T
            Dm = np.sqrt(np.diag(Prt)); In = Irt / np.outer(Dm, Dm)
            # H has no b_g column, so the direct information is singular in b_g; eigen-analysis on [rad, tan, psi]
            w, V = np.linalg.eigh(In[:3, :3])
            row = dict(case=D["case"], arm=arm, window=("FAIL" if wi == len(wins) - 1 else f"{lo:g}"), t_lo=lo, t_hi=hi,
                       n_upd=int(m.sum()), **{f"In_diag_{n}": float(In[i, i]) for i, n in enumerate(("rad", "tan", "psi", "bg"))},
                       **{f"eig{i}": float(w[i]) for i in range(3)}, cond3=float(w[2] / max(w[0], 1e-300)),
                       **{f"vmin_{n}": float(abs(V[i, 0])) for i, n in enumerate(("rad", "tan", "psi"))},
                       corr_tan_psi=float(In[1, 2] / math.sqrt(max(In[1, 1] * In[2, 2], 1e-300))))
            rows.append(row)
    return rows


def e5_onestep(D, logs, cov_all):
    rows = []; a = D["anchor"]
    z_perm = e4_eps_tilde(D, "PERM", 1.0, 0)[0]
    for arm in ("MB_ORIG", "MB_VAR"):
        bg, Rf = ARMS[arm]
        X, PX, L = logs[arm]
        st = failure_window(D, X); k0 = int(np.searchsorted(D["t"], st)); k1 = min(k0 + 20, len(D["t"]))
        def rs_cov(k, R0k, sg, rh, x, base=Rf):
            R = base(k, R0k, sg, rh, x); _, _, c = K.cov_interp(cov_all, rh)
            R = R.copy(); R[0, 1] = R[1, 0] = c * math.sqrt(R[0, 0] * R[1, 1]); return R
        trts = {"ID": dict(Rfn=Rf), "PERM": dict(Rfn=Rf, z=z_perm), "RSC_TOTAL_8": dict(Rfn=K.R_scaled(Rf, scale_all=8.0)),
                "COV_RS": dict(Rfn=rs_cov)}
        for name, kw in trts.items():
            Xr, PXr, Lr = K.run(D, bg, kw["Rfn"], z=kw.get("z"), k0=k0, k1=k1, x_init=X[k0 - 1], P_init=PX[k0 - 1])
            e = K.state_err(D, Xr)
            for j, k in enumerate(range(k0, k1)):
                ur = D["gt"][k, :2] - a; ur /= np.linalg.norm(ur); ut = np.array([-ur[1], ur[0]])
                rows.append(dict(case=D["case"], arm=arm, treat=name, t_start=st, step=j + 1, t=float(D["t"][k]),
                                 head_err_deg=float(np.degrees(e[k, 2])), tan_err_cm=float(-100 * ut @ e[k, :2]),
                                 head_sd_deg=float(np.degrees(math.sqrt(PXr[k, 2, 2])))))
    return rows


# ============================================================================ E1
def e1_treatments(D, part):
    idx = np.flatnonzero(D["acc"]); n = len(D["t"])
    ms = (2, 4, 8, 16) if part == "s0" else (4, 8)
    nrand = 20 if part == "s0" else 10
    if SMOKE:
        ms, nrand = (4,), 2
    cid = CASE_ID[D["case"]]
    for m in ms:
        for p in range(m):
            keep = np.zeros(n, bool); keep[idx[p::m]] = True
            yield dict(treat="DEC", m=m, rep=p, use=np.c_[keep, keep])
            yield dict(treat="THIN_S", m=m, rep=p, use=np.c_[D["acc"], keep])
            if part == "s0":
                yield dict(treat="THIN_R", m=m, rep=p, use=np.c_[keep, D["acc"]])
        cnt = int(round(len(idx) / m))
        for j in range(nrand):
            rng = np.random.default_rng([2026103000, j, cid, D["seed"], m])
            keep = np.zeros(n, bool); keep[np.sort(rng.choice(idx, cnt, replace=False))] = True
            yield dict(treat="RAND", m=m, rep=j, use=np.c_[keep, keep])
        yield dict(treat="RSC_TOTAL", m=m, rep=0, scale=dict(scale_all=float(m)))
        yield dict(treat="RSC_S", m=m, rep=0, scale=dict(scale_ss=float(m)))
        if part == "s0":
            yield dict(treat="RSC_BASE", m=m, rep=0, scale=dict(scale_R0_only=float(m)))


def stage_E1(case, part):
    seeds = [0] if part == "s0" else K.SEEDS[1:]
    rows = []; checks = {}
    for seed in seeds:
        D = K.load(case, seed)
        if seed == 0:
            checks.update(parity(D))
        for arm in ("MB_ORIG", "MB_VAR"):
            bg, Rf = ARMS[arm]
            X, PX, L = K.run(D, bg, Rf)
            rows.append(tag(D, arm=arm, treat="BASE", m=1, rep=0, n_upd_r=int(L["upd"][:, 0].sum()), n_upd_s=int(L["upd"][:, 1].sum()),
                            **K.scores(D, X, PX), **s_summary(D, bg, L)))
            for tr in e1_treatments(D, part):
                Rfn = K.R_scaled(Rf, **tr["scale"]) if "scale" in tr else Rf
                X, PX, L = K.run(D, bg, Rfn, use=tr.get("use"))
                rows.append(tag(D, arm=arm, treat=tr["treat"], m=tr["m"], rep=tr["rep"], n_upd_r=int(L["upd"][:, 0].sum()),
                                n_upd_s=int(L["upd"][:, 1].sum()), **K.scores(D, X, PX), **s_summary(D, bg, L)))
        print("E1", case, part, seed, len(rows), flush=True)
    pd.DataFrame(rows).to_csv(K.OUT / f"E1_{case}_{part}.csv", index=False, float_format="%.8g")
    return checks


# ============================================================================ E4
TRT_CODE = {"PERM": 1, "BLOCK": 2, "SIGNFLIP": 3}


def e4_eps_tilde(D, kind, L_s, rep):
    eps = D["z"] - D["hg"] - D["mu"]["MB"]
    rng = np.random.default_rng([2026103100, CASE_ID[D["case"]], D["seed"], rep, TRT_CODE[kind], int(round(L_s * 10))])
    mode = "signflip" if kind == "SIGNFLIP" else "perm"
    blk = 0.2 if kind == "PERM" else L_s
    et, merges, lab = K.permute_eps(D, eps, D["acc"], blk, rng, mode)
    z = D["z"].copy(); s = D["acc"]
    z[s] = D["hg"][s] + D["mu"]["MB"][s] + et[s]
    chk = K.manipulation_check(eps, et, lab, D["acc"], mode)
    return z, chk, merges


def stage_E4(case, part):
    seeds = [0] if part == "s0" else K.SEEDS[1:]
    rows = []; checks = {}; merges_out = None
    for seed in seeds:
        D = K.load(case, seed)
        if seed == 0:
            checks.update(parity(D))
        plan = [("ID", 0.0, 0)]
        nrep = 20 if part == "s0" else 5
        if SMOKE:
            nrep = 2
        plan += [("PERM", 0.2, r) for r in range(nrep)]
        plan += [("BLOCK", L, r) for L in (1.0, 2.0, 4.0, 8.0) for r in range(nrep)]
        if part == "s0":
            plan += [("SIGNFLIP", L, r) for L in (1.0, 2.0, 4.0, 8.0) for r in range(2 if SMOKE else 10)]
        for kind, Ls, rep in plan:
            if kind == "ID":
                eps = D["z"] - D["hg"] - D["mu"]["MB"]; z = D["z"].copy(); s = D["acc"]
                z[s] = D["hg"][s] + D["mu"]["MB"][s] + eps[s]
                chk = K.manipulation_check(eps, eps, K.stratum_ids(D, s)[0], s, "perm")
            else:
                z, chk, merges = e4_eps_tilde(D, kind, Ls, rep)
                if merges_out is None and seed == 0:
                    merges_out = merges
            masks = [("fixed", None)]
            if part == "s0" and kind in ("ID", "PERM", "BLOCK") and rep < 5:
                accR = K.PB.gated_mask(z, D["mu"]["BB"], D["R0"], D["ds"], D["gy"], D["dt"], D["x0"], D["P0"], D["spec"], K.model())
                masks.append(("regen", accR & D["fin"]))
            for mname, mk in masks:
                for arm in ("MB_ORIG", "MB_VAR"):
                    bg, Rf = ARMS[arm]
                    use = None if mk is None else np.c_[mk, mk]
                    X, PX, L = K.run(D, bg, Rf, z=z, use=use)
                    r = tag(D, arm=arm, treat=kind, L_s=Ls, rep=rep, mask=mname, n_upd=int(L["upd"][:, 0].sum()),
                            **{f"chk_{k}": v for k, v in chk.items()}, **K.scores(D, X, PX), **s_summary(D, bg, L, z=z))
                    if kind == "ID" and mname == "fixed":
                        X0, _, _ = K.run(D, bg, Rf)
                        r["id_state_diff"] = float(np.max(np.abs(X - X0)))
                    rows.append(r)
        print("E4", case, part, seed, len(rows), flush=True)
    pd.DataFrame(rows).to_csv(K.OUT / f"E4_{case}_{part}.csv", index=False, float_format="%.8g")
    if merges_out is not None:
        K.jdump(K.OUT / f"E4_MERGES_{case}.json", merges_out)
    return checks


# ============================================================================ E2 + E3
def train_mean_models(case, shuffle=False):
    Xs, ys = [], []
    for c in K.CASES:
        if c[:2] == case[:2]:
            continue
        D = K.load(c, 0)
        X, PX, L = K.run(D, "MB", K.R_orig)
        eps = D["z"] - D["hg"] - D["mu"]["MB"]
        for k in np.flatnonzero(D["fin"] & np.isfinite(L["nis"])):
            Xs.append(K.online_features(L["xp"][k], L["hx"][k], L["H"][k], D["anchor"])); ys.append(eps[k])
    Xs = np.array(Xs); ys = np.array(ys)
    if shuffle:
        ys = ys[np.random.default_rng(2026103200 + CASE_ID[case]).permutation(len(ys))]
    return [K.ridge_fit(Xs, ys[:, j]) for j in range(2)], len(ys)


def stage_E23(case):
    rows = []; acf_rows = []; checks = {}
    T = K.mb_residual_table(0); Tt = T[T.route != case[:2]]
    tabs = {"S_all": K.cov_table(Tt), "S_base": K.cov_table(Tt[Tt.base])}
    pd.DataFrame([dict(case=case, est=e, knot=kn, rr=v[0], ss=v[1], corr=v[2]) for e, tb in tabs.items()
                  for kn, v in zip(K.KNOTS, tb)]).to_csv(K.OUT / f"E3_COVTAB_{case}.csv", index=False, float_format="%.8g")
    means = {"MEAN_COND": train_mean_models(case), "MEAN_SHUF": train_mean_models(case, shuffle=True)}
    checks["mean_train_n"] = means["MEAN_COND"][1]

    def cov_R(base, which, tab):
        def f(k, R0k, sg, rh, x):
            R = base(k, R0k, sg, rh, x).copy(); rr, ss, c = K.cov_interp(tab, rh)
            if which in ("RR", "ALL"):
                R[0, 0] = rr
            if which in ("SS", "ALL"):
                R[1, 1] = ss
            if which in ("RS", "ALL"):
                R[0, 1] = R[1, 0] = c * math.sqrt(R[0, 0] * R[1, 1])
            return R
        return f

    for seed in K.SEEDS:
        D = K.load(case, seed)
        if seed == 0:
            checks.update(parity(D))
        for arm in ("MB_ORIG", "MB_VAR"):
            bg, Rf = ARMS[arm]
            X, PX, L = K.run(D, bg, Rf)
            rows.append(tag(D, arm=arm, family="BASE", treat="BASE", est="", **K.scores(D, X, PX), **s_summary(D, bg, L)))
            if seed == 0 and arm == "MB_ORIG":
                eps = D["z"] - D["hg"] - D["mu"]["MB"]; sel = D["fin"] & np.isfinite(L["nis"]) & (D["t"] >= 30)
                for nm, (mods, _) in [("NONE", (None, 0))] + list(means.items()):
                    if mods is None:
                        res = eps[sel]
                    else:
                        F = np.array([K.online_features(L["xp"][k], L["hx"][k], L["H"][k], D["anchor"]) for k in np.flatnonzero(sel)])
                        res = eps[sel] - np.c_[K.ridge_pred(mods[0], F), K.ridge_pred(mods[1], F)]
                    for j, comp in enumerate("rs"):
                        acf_rows.append(dict(case=case, model=nm, comp=comp, rms=float(np.sqrt(np.mean(res[:, j] ** 2))),
                                             mean=float(np.mean(res[:, j])), **K.acf_stats(res[:, j])))
            for nm, (mods, _) in means.items():
                def madd(k, x, h, H, mods=mods, a=D["anchor"]):
                    f = K.online_features(x, h, H, a)[None]
                    return np.array([K.ridge_pred(mods[0], f)[0], K.ridge_pred(mods[1], f)[0]])
                X, PX, L = K.run(D, bg, Rf, mu_add=madd)
                rows.append(tag(D, arm=arm, family="E2", treat=nm, est="", **K.scores(D, X, PX), **s_summary(D, bg, L)))
            whichs = ("RR", "SS", "RS", "ALL") if arm == "MB_ORIG" else ("RR", "RS")
            for est, tb in tabs.items():
                for w in whichs:
                    X, PX, L = K.run(D, bg, cov_R(Rf, w, tb))
                    rows.append(tag(D, arm=arm, family="E3", treat=f"COV_{w}", est=est, **K.scores(D, X, PX), **s_summary(D, bg, L)))
        print("E23", case, seed, len(rows), flush=True)
    pd.DataFrame(rows).to_csv(K.OUT / f"E23_{case}.csv", index=False, float_format="%.8g")
    pd.DataFrame(acf_rows).to_csv(K.OUT / f"E2_ACF_{case}.csv", index=False, float_format="%.8g")
    return checks



# ============================================================================ E6
def stage_E6(case):
    rows1, rows2, checks = [], [], {}
    for seed in K.SEEDS:
        D = K.load(case, seed)
        if seed == 0:
            checks.update(parity(D))
        a = D["anchor"]; eps = D["z"] - D["hg"] - D["mu"]["MB"]
        fixed = {}
        for upd, Rf in (("U0", K.R_orig), ("UV", K.R_var)):
            X, PX, L = K.run(D, "MB", Rf); fixed[upd] = (X, PX, L)
            rows2.append(tag(D, cell=f"FIXED_{upd}", thr="base", n_used=int(L["upd"][:, 0].sum()), t_div=np.nan, d_head_30s=np.nan,
                             **K.scores(D, X, PX), **s_summary(D, "MB", L)))
            # step 1: same prior, instantaneous gate decisions
            fin = D["fin"] & np.isfinite(L["nis"])
            ks = np.flatnonzero(fin)
            Xprev = np.vstack([D["x0"][None], X[:-1]])
            sg = np.array([K.sig(math.hypot(Xprev[k, 0] - a[0], Xprev[k, 1] - a[1])) for k in ks])
            R0 = D["R0"][ks]; RV = R0.copy(); RV[:, 1, 1] += sg ** 2
            S0 = L["HPH"][ks] + R0; SV = L["HPH"][ks] + RV; nu = L["nu"][ks]
            n0 = np.einsum("ni,ni->n", nu, np.linalg.solve(S0, nu[..., None])[..., 0])
            nV = np.einsum("ni,ni->n", nu, np.linalg.solve(SV, nu[..., None])[..., 0])
            base = D["acc"][ks]
            for th, thv in K.THRS.items():
                for g, nn, Rg in (("G0", n0, R0), ("GV", nV, RV)):
                    accg = nn <= thv
                    for lab, sel in (("new_acc", accg & ~base), ("new_rej", ~accg & base), ("common", accg & base)):
                        e_s = eps[ks][sel, 1]
                        rows1.append(tag(D, prior_from=upd, gate=g, thr=th, group=lab, n=int(sel.sum()),
                                         med_abs_eps_over_sqrtR0=float(np.median(np.abs(e_s) / np.sqrt(R0[sel, 1, 1]))) if sel.any() else np.nan,
                                         med_abs_eps_over_sqrtRV=float(np.median(np.abs(e_s) / np.sqrt(RV[sel, 1, 1]))) if sel.any() else np.nan,
                                         t_list=";".join(f"{v:.1f}" for v in D["t"][ks][sel][:30])))
        Xuv = fixed["UV"][0]; euv = K.state_err(D, Xuv)[:, 2]
        for th, thv in K.THRS.items():
            for g, Rg in (("G0", K.R_orig), ("GV", K.R_var)):
                for upd, Ru in (("U0", K.R_orig), ("UV", K.R_var)):
                    X, PX, L = K.run(D, "MB", Ru, gate=dict(Rfn=Rg, thr=thv))
                    diff = np.flatnonzero(L["upd"][:, 0] != D["acc"])
                    tdv = float(D["t"][diff[0]]) if len(diff) else np.nan
                    dh = np.nan
                    if len(diff):
                        w = (D["t"] >= tdv) & (D["t"] < tdv + 30)
                        e = K.state_err(D, X)[:, 2]
                        dh = float(np.degrees(np.sqrt(np.mean(e[w] ** 2)) - np.sqrt(np.mean(euv[w] ** 2))))
                    rows2.append(tag(D, cell=f"{g}{upd}", thr=th, n_used=int(L["upd"][:, 0].sum()), t_div=tdv, d_head_30s=dh,
                                     **K.scores(D, X, PX), **s_summary(D, "MB", L)))
        print("E6", case, seed, flush=True)
    pd.DataFrame(rows1).to_csv(K.OUT / f"E6_STEP1_{case}.csv", index=False, float_format="%.8g")
    pd.DataFrame(rows2).to_csv(K.OUT / f"E6_STEP2_{case}.csv", index=False, float_format="%.8g")
    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True); ap.add_argument("--case", required=True); ap.add_argument("--part", default="s0")
    a = ap.parse_args(); K.OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time(); status = "ok"; checks = {}
    try:
        fn = {"A": lambda: stage_A(a.case), "E1": lambda: stage_E1(a.case, a.part), "E4": lambda: stage_E4(a.case, a.part),
              "E23": lambda: stage_E23(a.case), "E6": lambda: stage_E6(a.case)}[a.stage]
        checks = fn()
    except Exception as e:  # noqa: BLE001
        status = f"FAILED: {type(e).__name__}: {e}"; traceback.print_exc()
    K.jdump(K.OUT / f"SHARD_{a.stage}_{a.case}_{a.part}.json", dict(stage=a.stage, case=a.case, part=a.part, status=status,
                                                                   sec=round(time.time() - t0, 1), checks=checks))
    print("STATUS", status, round(time.time() - t0, 1), flush=True)
    if status != "ok":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
