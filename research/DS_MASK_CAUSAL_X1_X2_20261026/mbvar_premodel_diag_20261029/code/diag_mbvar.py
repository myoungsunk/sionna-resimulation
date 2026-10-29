"""MB_VAR pre-modelling diagnostics, mount 0 only (D1 generalization, D2 gate, D3 innovation vs RF residual).

Evidence only; no filter is tuned here.  Reuses exp_pb (research/ds-state-info-var-forensics-20261028) unchanged:
same packets, controls, BASE mask, predict(), measurement model and scoring.

  REFLECT_ROOT=<inputs> python3 -I diag_mbvar.py --out <dir>
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PB_DIR = Path(__file__).resolve().parents[2] / "pol_bias_model"
sys.path.insert(0, str(PB_DIR))
import exp_pb as PB  # noqa: E402

C = PB.C
from core import predict, wrap  # noqa: E402

CASES = ["R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"]
BIASES = ["B0", "L0", "L1", "L2"]
GATE = PB.GATE_JOINT
HAND = (PB.SIG_R.copy(), PB.SIG_V.copy())


# ----------------------------------------------------------------------------- data
def load(case, bias, model):
    spec = C.CASES[case]
    ref = C.load_control(case, "B0")
    jb, jm = ref["jb"], ref["jm"]
    t = ref["t_s"]; gt = ref["truth_scoring_only"]
    z = ref["nu"][:, jb] + ref["h"][:, jb] + ref["mu"][:, jb]
    ds, gy, dt, x0 = PB.build_controls(t, gt[:, :3], bias)
    acc = PB.gated_mask(z, ref["mu"][:, jb], ref["R"][:, jb], ds, gy, dt, np.r_[x0, 0.0], ref["Pprior"][0, jb], spec, model)
    hg, _ = model.batch(np.c_[gt[:, :3], np.zeros(len(t))], spec)
    a = np.array(spec["anchor"][:2])
    return dict(case=case, bias=bias, t=t, gt=gt, z=z, R=ref["R"][:, jb], acc=acc, ds=ds, gy=gy, dt=dt,
                x0=np.r_[x0, 0.0], P0=ref["Pprior"][0, jb], spec=spec, anchor=a, hg=hg,
                mu=dict(BB=ref["mu"][:, jb], MB=ref["mu"][:, jm]),
                rho_true=np.hypot(gt[:, 0] - a[0], gt[:, 1] - a[1]))


def sigf(r, tab):
    return float(np.interp(r, tab[0], tab[1]))


# ----------------------------------------------------------------------------- filter (orig / var, fixed or self gate)
def run(D, bg, mode, gate, tab=HAND, model=None):
    """mode: orig | var.  gate: fixed (BASE mask A_B, as exp_pb) | self (own joint NIS gate).
    Identical arithmetic to exp_pb.run for the 4-state arms; additionally logs every finite packet pre-gate."""
    mu = D["mu"][bg]; n = len(D["t"]); a = D["anchor"]
    x = D["x0"].copy(); P = D["P0"].copy()
    X = np.zeros((n, 4)); PX = np.zeros((n, 4, 4))
    L = dict(xp=np.full((n, 4), np.nan), Pp=np.full((n, 4, 4), np.nan), nu=np.full((n, 2), np.nan),
             S=np.full((n, 2, 2), np.nan), HPH=np.full((n, 2, 2), np.nan), Ru=np.full((n, 2, 2), np.nan),
             hx=np.full((n, 2), np.nan), nis=np.full(n, np.nan), used=np.zeros(n, bool))
    for k in range(n):
        rh = math.hypot(x[0] - a[0], x[1] - a[1]); sg = sigf(rh, tab)
        if k:
            dsk, gyk, dtk = float(D["ds"][k]), float(D["gy"][k]), float(D["dt"][k])
            q = np.diag([2e-5 * abs(dsk), math.radians(0.015) ** 2 * dtk, 0.0])
            x, P, _, _ = predict(x, P, dsk, gyk, dtk, q)
        zk = D["z"][k]
        if np.isfinite(zk).all():
            h, H = model.batch(x[None], D["spec"]); h = h[0]; H = H[0]
            Rk = D["R"][k].copy()
            if mode == "var":
                Rk[1, 1] += sg ** 2
            v = zk - h - mu[k]
            HPH = H @ P @ H.T
            S_ = HPH + Rk; S_ = 0.5 * (S_ + S_.T)
            nis = float(v @ np.linalg.solve(S_, v))
            L["xp"][k] = x; L["Pp"][k] = P; L["nu"][k] = v; L["S"][k] = S_; L["HPH"][k] = HPH; L["Ru"][k] = Rk
            L["hx"][k] = h; L["nis"][k] = nis
            use = bool(D["acc"][k]) if gate == "fixed" else nis <= GATE
            if use:
                K = np.linalg.solve(S_, H @ P).T
                y = x + K @ v; y[2] = wrap(y[2])
                A_ = np.eye(4) - K @ H; Pn = A_ @ P @ A_.T + K @ Rk @ K.T
                x = y; P = 0.5 * (Pn + Pn.T); L["used"][k] = True
        X[k] = x; PX[k] = P
    return X, PX, L


def scores(D, X, PX):
    return PB.scores(D, X, PX)


def longest_gap_s(t, used, finite):
    """Longest stretch (s) between consecutive used packets among finite packets."""
    tu = t[used & finite]
    if len(tu) < 2:
        return float("nan")
    return float(np.max(np.diff(np.r_[t[0], tu, t[-1]])))


# ----------------------------------------------------------------------------- D1: sigma table refit
def fit_sigma(rows: pd.DataFrame, knots=HAND[0], floor=0.005):
    """Hat-basis (same as np.interp) weighted estimate of sigma_b^2(knot) = E[eps_s^2 - R_ss | rho].
    rows: rho_true, eps_s (MB background), Rss (base).  Returns table usable by sigf."""
    vals = []
    for j, kn in enumerate(knots):
        lo = knots[j - 1] if j else kn; hi = knots[j + 1] if j + 1 < len(knots) else kn + 1e9
        r = rows.rho_true.to_numpy()
        w = np.where(r <= kn, (r - lo) / max(kn - lo, 1e-9), (hi - r) / max(hi - kn, 1e-9))
        if j == 0:
            w = np.where(r <= kn, 1.0, w)
        if j + 1 == len(knots):
            w = np.where(r >= kn, 1.0, w)
        w = np.clip(w, 0, 1)
        num = np.sum(w * (rows.eps_s.to_numpy() ** 2 - rows.Rss.to_numpy()))
        den = np.sum(w)
        v2 = num / den if den > 5 else np.nan
        vals.append(math.sqrt(max(v2, floor ** 2)) if np.isfinite(v2) else np.nan)
    vals = np.array(vals)
    # carry neighbours if a knot had too few samples
    if np.isnan(vals).any():
        idx = np.flatnonzero(~np.isnan(vals)); vals = np.interp(np.arange(len(vals)), idx, vals[idx])
    return (np.asarray(knots, float), vals)


# ----------------------------------------------------------------------------- D3 helpers
def acf_len(x, t, travel, thr=math.exp(-1)):
    """First lag where autocorrelation < 1/e; returned in s and m travelled (contiguous finite series)."""
    x = np.asarray(x, float); ok = np.isfinite(x)
    x = x[ok] - np.mean(x[ok]); tt = t[ok]; tr = travel[ok]
    v = np.dot(x, x)
    if v <= 0 or len(x) < 20:
        return np.nan, np.nan, np.nan
    for lag in range(1, len(x) // 2):
        r = np.dot(x[:-lag], x[lag:]) / v
        if r < thr:
            return float(np.median(tt[lag:] - tt[:-lag])), float(np.median(np.abs(tr[lag:] - tr[:-lag]))), float(np.dot(x[:-1], x[1:]) / v)
    return float("inf"), float("inf"), float(np.dot(x[:-1], x[1:]) / v)


def neff(x):
    """Effective sample size for the mean under AR(1)."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]; x = x - x.mean()
    r1 = np.dot(x[:-1], x[1:]) / max(np.dot(x, x), 1e-30)
    r1 = min(max(r1, -0.99), 0.99)
    return len(x) * (1 - r1) / (1 + r1)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True)
    args = ap.parse_args(); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    model = C.base_model()
    data = {(c, b): load(c, b, model) for c in CASES for b in BIASES}

    # ===================== D2: gate =====================
    gate_rows, pkt_rows = [], []
    runs = {}
    for (c, b), D in data.items():
        fin = np.isfinite(D["z"]).all(1)
        for bg in ("BB", "MB"):
            for mode in ("orig", "var"):
                arm = f"{bg}_{mode.upper()}"
                res = {}
                for gate in ("fixed", "self"):
                    X, PX, L = run(D, bg, mode, gate, model=model)
                    res[gate] = (X, PX, L); runs[(c, b, arm, gate)] = (X, PX, L)
                    s = scores(D, X, PX)
                    nis_all = L["nis"][fin]; used = L["used"]
                    e_s_true = D["z"][:, 1] - D["hg"][:, 1] - D["mu"][bg][:, 1]
                    row = dict(case=c, route=c[:2], anchor=c[4], bias=b, arm=arm, gate=gate, n_finite=int(fin.sum()),
                               n_used=int(used.sum()), accept_rate=float(used.sum() / fin.sum()),
                               longest_gap_s=longest_gap_s(D["t"], used, fin),
                               nis_mean_used=float(np.nanmean(L["nis"][used])),
                               nis_mean_all=float(np.nanmean(nis_all)),
                               nis_median_all=float(np.nanmedian(nis_all)),
                               frac_all_over_gate=float(np.mean(nis_all > GATE)),
                               frac_all_over_chi2_95=float(np.mean(nis_all > 5.991)),
                               frac_used_over_chi2_95=float(np.mean(L["nis"][used] > 5.991)))
                    row.update(s)
                    gate_rows.append(row)
                Lf, Ls = res["fixed"][2], res["self"][2]
                new_acc = Ls["used"] & ~D["acc"]; new_rej = ~Ls["used"] & D["acc"] & fin
                e_true = D["z"] - D["hg"] - D["mu"][bg]
                Rb = D["R"]
                ez_s = e_true[:, 1] / np.sqrt(Rb[:, 1, 1])
                pkt_rows.append(dict(case=c, bias=b, arm=arm, n_newly_accepted=int(new_acc.sum()), n_newly_rejected=int(new_rej.sum()),
                                     newly_acc_abs_eps_s_over_sqrtRss_median=float(np.median(np.abs(ez_s[new_acc]))) if new_acc.any() else np.nan,
                                     newly_rej_abs_eps_s_over_sqrtRss_median=float(np.median(np.abs(ez_s[new_rej]))) if new_rej.any() else np.nan,
                                     common_abs_eps_s_over_sqrtRss_median=float(np.median(np.abs(ez_s[Ls["used"] & D["acc"]]))),
                                     newly_acc_t=";".join(f"{v:.1f}" for v in D["t"][new_acc][:40]),
                                     newly_rej_t=";".join(f"{v:.1f}" for v in D["t"][new_rej][:40])))
    G = pd.DataFrame(gate_rows); G.to_csv(out / "D2_GATE_SCORES.csv", index=False, float_format="%.6g")
    pd.DataFrame(pkt_rows).to_csv(out / "D2_GATE_FLIPS.csv", index=False, float_format="%.6g")

    # parity: BB_ORIG self-gate must equal BASE mask exactly
    par = []
    for (c, b), D in data.items():
        Ls = runs[(c, b, "BB_ORIG", "self")][2]; fin = np.isfinite(D["z"]).all(1)
        par.append(dict(case=c, bias=b, bb_orig_self_vs_mask_mismatch=int(np.sum(Ls["used"] != (D["acc"] & fin))),
                        bb_orig_state_diff=float(np.max(np.abs(runs[(c, b, "BB_ORIG", "self")][0] - runs[(c, b, "BB_ORIG", "fixed")][0])))))
    pd.DataFrame(par).to_csv(out / "PARITY.csv", index=False)

    # ===================== D3: innovation decomposition (fixed gate, as published) =====================
    dec_rows, bin_rows, win_rows, acf_rows = [], [], [], []
    bins = [0, 1.5, 3, 6, 10, 99]
    for (c, b), D in data.items():
        fin = np.isfinite(D["z"]).all(1)
        travel = np.r_[0, np.cumsum(np.hypot(np.diff(D["gt"][:, 0]), np.diff(D["gt"][:, 1])))]
        for arm in ("BB_ORIG", "MB_ORIG", "BB_VAR", "MB_VAR"):
            bg = arm[:2]
            X, PX, L = runs[(c, b, arm, "fixed")]
            u = L["used"] & (D["t"] >= 30 - 1e-9)
            nu = L["nu"]; eps = D["z"] - D["hg"] - D["mu"][bg]        # RF residual vs model at truth
            dh = D["hg"] - L["hx"]                                       # exact: nu = eps + dh
            assert np.nanmax(np.abs(nu - (eps + dh))[L["used"]]) < 1e-9
            for j, comp in enumerate(("r", "s")):
                Rj = L["Ru"][:, j, j]; Rb = D["R"][:, j, j]; HPHj = L["HPH"][:, j, j]; Sj = L["S"][:, j, j]
                e2 = eps[u, j] ** 2; d2 = dh[u, j] ** 2; cr = 2 * eps[u, j] * dh[u, j]
                dec_rows.append(dict(case=c, route=c[:2], anchor=c[4], bias=b, arm=arm, comp=comp, n=int(u.sum()),
                                     E_nu2=float(np.mean(nu[u, j] ** 2)), E_S=float(np.mean(Sj[u])),
                                     E_eps2=float(np.mean(e2)), E_R_used=float(np.mean(Rj[u])), E_R_base=float(np.mean(Rb[u])),
                                     E_dh2=float(np.mean(d2)), E_HPH=float(np.mean(HPHj[u])), E_2cross=float(np.mean(cr)),
                                     ratio_nu2_S=float(np.mean(nu[u, j] ** 2) / np.mean(Sj[u])),
                                     ratio_eps2_R=float(np.mean(e2) / np.mean(Rj[u])),
                                     ratio_dh2_HPH=float(np.mean(d2) / np.mean(HPHj[u])),
                                     mean_eps=float(np.mean(eps[u, j])), mean_eps_over_sqrtR=float(np.mean(eps[u, j] / np.sqrt(Rj[u]))),
                                     neff_eps=float(neff(eps[u, j])),
                                     share_state_in_nu2=float(np.mean(d2) / np.mean(nu[u, j] ** 2)),
                                     share_rf_in_nu2=float(np.mean(e2) / np.mean(nu[u, j] ** 2))))
            # r-s correlation of RF residual vs model (R_rs = 0)
            if arm.endswith("ORIG"):
                e = eps[u]
                dec_rows[-1]["corr_eps_r_eps_s"] = float(np.corrcoef(e[:, 0], e[:, 1])[0, 1])
                dec_rows[-2]["corr_eps_r_eps_s"] = dec_rows[-1]["corr_eps_r_eps_s"]
            # distance-binned RF residual (all finite packets, no gate selection), B0 only
            if b == "B0" and arm in ("BB_ORIG", "MB_ORIG"):
                rr = D["rho_true"]
                for lo, hi in zip(bins[:-1], bins[1:]):
                    m = fin & (rr >= lo) & (rr < hi) & (D["t"] >= 30 - 1e-9)
                    if m.sum() < 5:
                        continue
                    for j, comp in enumerate(("r", "s")):
                        Rb = D["R"][m, j, j]
                        ev = eps[m, j]
                        sgv = np.array([sigf(v, HAND) for v in rr[m]])
                        bin_rows.append(dict(case=c, background=bg, comp=comp, rho_lo=lo, rho_hi=hi, n=int(m.sum()),
                                             neff=float(neff(ev)), mean_eps=float(np.mean(ev)), rms_eps=float(np.sqrt(np.mean(ev ** 2))),
                                             std_eps=float(np.std(ev)), sqrt_mean_Rbase=float(np.sqrt(np.mean(Rb))),
                                             sqrt_mean_Rvar=float(np.sqrt(np.mean(Rb + (sgv ** 2 if comp == "s" else 0)))),
                                             sigma_need=float(np.sqrt(max(np.mean(ev ** 2) - np.mean(Rb), 0))) if comp == "s" else np.nan,
                                             sigma_hand=float(np.mean(sgv)) if comp == "s" else np.nan,
                                             mean2_share=float(np.mean(ev) ** 2 / np.mean(ev ** 2))))
            # temporal persistence of eps_s (all finite packets)
            if b == "B0" and arm in ("BB_ORIG", "MB_ORIG"):
                for j, comp in enumerate(("r", "s")):
                    tl, ml, r1 = acf_len(np.where(fin, eps[:, j], np.nan), D["t"], travel)
                    acf_rows.append(dict(case=c, background=bg, comp=comp, acf_1e_s=tl, acf_1e_m=ml, lag1_r=r1,
                                         n=int(fin.sum()), neff=float(neff(eps[fin, j]))))
            # R5_aA time windows
            if c == "R5_aA_m0" and b == "B0":
                for lo, hi in ((30, 60), (60, 120), (120, 180), (180, 240), (240, 1e9)):
                    w = L["used"] & (D["t"] >= lo) & (D["t"] < hi)
                    j = 1
                    win_rows.append(dict(arm=arm, t_lo=lo, t_hi=min(hi, float(D["t"][-1])), n=int(w.sum()),
                                         s_E_nu2=float(np.mean(nu[w, j] ** 2)), s_E_S=float(np.mean(L["S"][w, j, j])),
                                         s_E_eps2=float(np.mean(eps[w, j] ** 2)), s_E_R=float(np.mean(L["Ru"][w, j, j])),
                                         s_E_dh2=float(np.mean(dh[w, j] ** 2)), s_E_HPH=float(np.mean(L["HPH"][w, j, j])),
                                         s_mean_eps=float(np.mean(eps[w, j])), r_E_eps2=float(np.mean(eps[w, 0] ** 2)),
                                         r_E_R=float(np.mean(L["Ru"][w, 0, 0])), r_E_dh2=float(np.mean(dh[w, 0] ** 2)),
                                         r_E_HPH=float(np.mean(L["HPH"][w, 0, 0])),
                                         rho_min=float(D["rho_true"][w].min()), rho_max=float(D["rho_true"][w].max())))
    pd.DataFrame(dec_rows).to_csv(out / "D3_DECOMPOSITION.csv", index=False, float_format="%.6g")
    pd.DataFrame(bin_rows).to_csv(out / "D3_EPS_BY_DISTANCE.csv", index=False, float_format="%.6g")
    pd.DataFrame(acf_rows).to_csv(out / "D3_EPS_TEMPORAL.csv", index=False, float_format="%.6g")
    pd.DataFrame(win_rows).to_csv(out / "D3_R5A_WINDOWS.csv", index=False, float_format="%.6g")

    # ===================== D1: sigma table generalization =====================
    # training rows: all finite packets, B0 (packets are bias-independent), MB background, true distance
    fit_rows = []
    for c in CASES:
        D = data[(c, "B0")]; fin = np.isfinite(D["z"]).all(1)
        eps = D["z"][:, 1] - D["hg"][:, 1] - D["mu"]["MB"][:, 1]
        fit_rows.append(pd.DataFrame(dict(case=c, route=c[:2], rho_true=D["rho_true"][fin], eps_s=eps[fin], Rss=D["R"][fin, 1, 1])))
    FR = pd.concat(fit_rows, ignore_index=True)
    tables = {"HAND": HAND, "ALLROUTES": fit_sigma(FR)}
    for held in ("R2", "R4", "R5"):
        tables[f"LORO_{held}"] = fit_sigma(FR[FR.route != held])
    pd.DataFrame([dict(table=k, **{f"sig@{r:g}m": v for r, v in zip(*tab)}) for k, tab in tables.items()]).to_csv(
        out / "D1_SIGMA_TABLES.csv", index=False, float_format="%.5g")
    g_rows = []
    for (c, b), D in data.items():
        for tname in ("HAND", "ALLROUTES", f"LORO_{c[:2]}", "NONE"):
            if tname == "NONE":
                X, PX, _ = runs[(c, b, "MB_ORIG", "fixed")]
            elif tname == "HAND":
                X, PX, _ = runs[(c, b, "MB_VAR", "fixed")]
            else:
                X, PX, _ = run(D, "MB", "var", "fixed", tab=tables[tname], model=model)
            g_rows.append(dict(case=c, route=c[:2], anchor=c[4], bias=b, table=tname.replace(f"_{c[:2]}", "") if tname.startswith("LORO") else tname,
                               **scores(D, X, PX)))
    pd.DataFrame(g_rows).to_csv(out / "D1_GENERALIZATION_SCORES.csv", index=False, float_format="%.6g")
    print("done", out)


if __name__ == "__main__":
    main()
