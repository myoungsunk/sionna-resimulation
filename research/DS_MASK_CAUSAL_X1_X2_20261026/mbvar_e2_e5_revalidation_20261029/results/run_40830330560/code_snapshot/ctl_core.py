"""Shared core for the MB_VAR control-correction experiments (PROTOCOL_CONTROLS_KO.md).

Filter arithmetic is identical to pol_bias_model/exp_pb.run for the 4-state arms (parity-checked):
  sigma_b uses the posterior BEFORE prediction, Joseph update, same Q, same predict().
Additions are hooks only: per-channel update masks, alternative z, additive mean, arbitrary R, own gate,
partial replay from a given prior.  Truth enters only through scoring / diagnostics / semi-synthetic z.
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PB_DIR = HERE.parent / "pol_bias_model"
sys.path.insert(0, str(PB_DIR))
import exp_pb as PB  # noqa: E402

C = PB.C
from core import predict, wrap  # noqa: E402

CASES = ["R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"]
SEEDS = list(range(10))
GATE = PB.GATE_JOINT
THRS = {"p95": 5.991464547107979, "p99": 9.210340371976184, "p999": 13.815510557964274}
SIG_R, SIG_V = PB.SIG_R, PB.SIG_V
WINDOWS = [(30, 60), (60, 120), (120, 180), (180, 240), (240, 1e9)]
RHO_BINS = [0, 1.5, 3, 6, 10, 1e9]
OUT = Path(os.environ.get("CTL_OUT", HERE / "out"))
REF_D2 = HERE.parent / "mbvar_premodel_diag_20261029/results/D2_GATE_SCORES.csv"


def sig(r):
    return float(np.interp(r, SIG_R, SIG_V))


_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = C.base_model()
    return _MODEL


# ----------------------------------------------------------------------------- data
_REF = {}


def ref_trace(case):
    if case not in _REF:
        _REF[case] = C.load_control(case, "B0")
    return _REF[case]


def load(case, seed=0, bias="B0"):
    """Packets are seed/bias independent; controls, x0 and the BASE mask are regenerated per seed."""
    m = model(); spec = C.CASES[case]; ref = ref_trace(case); jb, jm = ref["jb"], ref["jm"]
    t = ref["t_s"]; gt = ref["truth_scoring_only"]
    z = ref["nu"][:, jb] + ref["h"][:, jb] + ref["mu"][:, jb]
    ds, gy, dt, x0 = PB.build_controls(t, gt[:, :3], bias, seed)
    chk = {}
    if seed == 0 and bias == "B0":
        dss, gys, _ = C.controls_from(ref["x"][:, jb], ref["prior"][:, jb], t)
        chk["controls_ds_vs_trace"] = float(np.max(np.abs(ds[1:] - dss[1:])))
        chk["controls_gyro_vs_trace"] = float(np.max(np.abs(gy[1:] - gys[1:])))
        if max(chk.values()) > 1e-10:
            raise RuntimeError(f"PARITY_FAIL controls {chk}")
    muB = ref["mu"][:, jb]; muM = ref["mu"][:, jm]; R0 = ref["R"][:, jb]
    P0 = ref["Pprior"][0, jb]
    acc = PB.gated_mask(z, muB, R0, ds, gy, dt, np.r_[x0, 0.0], P0, spec, m)
    if seed == 0 and bias == "B0":
        chk["mask_vs_trace_mismatch"] = int(np.sum(acc != ref["acc"][:, jb].astype(bool)))
        if chk["mask_vs_trace_mismatch"]:
            raise RuntimeError("MASK_PARITY_FAIL")
    hg, Hg = m.batch(np.c_[gt[:, :3], np.zeros(len(t))], spec)
    a = np.array(spec["anchor"][:2])
    fin = np.isfinite(z).all(1)
    return dict(case=case, seed=seed, bias=bias, t=t, gt=gt, z=z, R0=R0, acc=acc & fin, fin=fin, ds=ds, gy=gy, dt=dt,
                x0=np.r_[x0, 0.0], P0=P0, spec=spec, anchor=a, hg=hg, Hg=Hg, mu=dict(BB=muB, MB=muM),
                b_true=math.radians(PB.BIAS_LEVELS[bias]), rho_true=np.hypot(gt[:, 0] - a[0], gt[:, 1] - a[1]),
                checks=chk)


# ----------------------------------------------------------------------------- R builders
def R_orig(k, R0k, sg, rh, x):
    return R0k.copy()


def R_var(k, R0k, sg, rh, x):
    R = R0k.copy(); R[1, 1] += sg ** 2
    return R


def R_scaled(base, scale_rr=1.0, scale_ss=1.0, scale_all=1.0, scale_R0_only=None):
    def f(k, R0k, sg, rh, x):
        if scale_R0_only is not None:            # 06a8a09 RSC: m*R0 (+ sigma^2 if VAR)
            R = R0k * scale_R0_only
            if base is R_var:
                R = R.copy(); R[1, 1] += sg ** 2
            return R
        R = base(k, R0k, sg, rh, x) * scale_all
        R[0, 0] *= scale_rr; R[1, 1] *= scale_ss
        return R
    return f


# ----------------------------------------------------------------------------- filter
def run(D, bg, Rfn, *, use=None, gate=None, z=None, mu_add=None, k0=0, k1=None, x_init=None, P_init=None):
    """use: bool (n,2) channel-update permission for fixed-gate operation (default: BASE mask on both).
    gate: None (fixed) or dict(Rfn=..., thr=...) -> own joint NIS gate decides; both channels updated.
    Returns X, PX, log dict.  k0/x_init/P_init: continue from the POSTERIOR (x, P) at k0-1."""
    m = model(); mu = D["mu"][bg]; n = len(D["t"]); a = D["anchor"]; zz = D["z"] if z is None else z
    k1 = n if k1 is None else k1
    if use is None:
        use = np.c_[D["acc"], D["acc"]]
    X = np.full((n, 4), np.nan); PX = np.full((n, 4, 4), np.nan)
    L = dict(xp=np.full((n, 4), np.nan), Pp=np.full((n, 4, 4), np.nan), nu=np.full((n, 2), np.nan),
             S=np.full((n, 2, 2), np.nan), HPH=np.full((n, 2, 2), np.nan), Ru=np.full((n, 2, 2), np.nan),
             hx=np.full((n, 2), np.nan), H=np.full((n, 2, 4), np.nan), nis=np.full(n, np.nan),
             mu_used=np.full((n, 2), np.nan), upd=np.zeros((n, 2), bool))
    if k0 == 0:
        x = D["x0"].copy(); P = D["P0"].copy()
    else:                                   # x_init/P_init = POSTERIOR at k0-1 (exact continuation)
        x = x_init.copy(); P = P_init.copy()
    for k in range(k0, k1):
        rh = math.hypot(x[0] - a[0], x[1] - a[1]); sg = sig(rh)
        if k:
            dsk, gyk, dtk = float(D["ds"][k]), float(D["gy"][k]), float(D["dt"][k])
            q = np.diag([2e-5 * abs(dsk), math.radians(0.015) ** 2 * dtk, 0.0])
            x, P, _, _ = predict(x, P, dsk, gyk, dtk, q)
        if D["fin"][k]:
            h, H = m.batch(x[None], D["spec"]); h = h[0]; H = H[0]
            Rk = Rfn(k, D["R0"][k], sg, rh, x)
            muk = mu[k] if mu_add is None else mu[k] + mu_add(k, x, h, H)
            v = zz[k] - h - muk
            HPH = H @ P @ H.T
            S_ = HPH + Rk; S_ = 0.5 * (S_ + S_.T)
            nis = float(v @ np.linalg.solve(S_, v))
            L["xp"][k] = x; L["Pp"][k] = P; L["nu"][k] = v; L["S"][k] = S_; L["HPH"][k] = HPH; L["Ru"][k] = Rk
            L["hx"][k] = h; L["H"][k] = H; L["nis"][k] = nis; L["mu_used"][k] = muk
            if gate is None:
                ur, us = bool(use[k, 0]), bool(use[k, 1])
            else:
                Rg = gate["Rfn"](k, D["R0"][k], sg, rh, x)
                Sg = HPH + Rg; Sg = 0.5 * (Sg + Sg.T)
                ok = float(v @ np.linalg.solve(Sg, v)) <= gate["thr"]
                ur = us = ok
            rows = [i for i, u in ((0, ur), (1, us)) if u]
            if rows:
                Hs = H[rows]; Rs = Rk[np.ix_(rows, rows)]; vs = v[rows]
                Ss = Hs @ P @ Hs.T + Rs; Ss = 0.5 * (Ss + Ss.T)
                K = np.linalg.solve(Ss, Hs @ P).T
                y = x + K @ vs; y[2] = wrap(y[2])
                A_ = np.eye(4) - K @ Hs; Pn = A_ @ P @ A_.T + K @ Rs @ K.T
                x = y; P = 0.5 * (Pn + Pn.T)
                L["upd"][k] = [ur, us]
        X[k] = x; PX[k] = P
    return X, PX, L


# ----------------------------------------------------------------------------- scoring
def state_err(D, X):
    e = np.c_[D["gt"][:, :3], np.full(len(X), D["b_true"])] - X
    e[:, 2] = np.angle(np.exp(1j * e[:, 2]))
    return e


def scores(D, X, PX):
    t, gt, a = D["t"], D["gt"], D["anchor"]; s = t >= 30 - 1e-9
    e = state_err(D, X)
    sp = np.sqrt(PX[:, 2, 2]); zpsi = e[:, 2] / sp
    nees2 = np.einsum("ni,ni->n", e[:, :2], np.linalg.solve(PX[:, :2, :2], e[:, :2][..., None])[..., 0])
    nees3 = np.einsum("ni,ni->n", e[:, :3], np.linalg.solve(PX[:, :3, :3], e[:, :3][..., None])[..., 0])
    nees4 = np.einsum("ni,ni->n", e, np.linalg.solve(PX, e[..., None])[..., 0])
    ur = (gt[:, :2] - a); ur = ur / np.linalg.norm(ur, axis=1, keepdims=True); ut = np.c_[-ur[:, 1], ur[:, 0]]
    dp = X[:, :2] - gt[:, :2]
    er = np.einsum("ni,ni->n", dp, ur); et = np.einsum("ni,ni->n", dp, ut)
    d3 = np.linalg.norm(np.c_[X[:, :2] - a, np.full(len(t), D["spec"]["robot_z_m"] - D["spec"]["anchor"][2])], axis=1)
    d3t = np.linalg.norm(np.c_[gt[:, :2] - a, np.full(len(t), D["spec"]["robot_z_m"] - D["spec"]["anchor"][2])], axis=1)
    h2 = e[s, 2] ** 2; top = np.sort(h2)[::-1][: max(1, int(round(0.05 * s.sum())))]
    return dict(head_rmse=float(np.degrees(np.sqrt(np.mean(h2)))), head_bias=float(np.degrees(np.mean(e[s, 2]))),
                head_maxabs=float(np.degrees(np.max(np.abs(e[s, 2])))), head_top5_share=float(top.sum() / h2.sum()),
                xy_rmse_cm=float(100 * np.sqrt(np.mean(np.sum(e[s, :2] ** 2, 1)))),
                rad_rmse_cm=float(100 * np.sqrt(np.mean(er[s] ** 2))), tan_rmse_cm=float(100 * np.sqrt(np.mean(et[s] ** 2))),
                range_rmse_cm=float(100 * np.sqrt(np.mean((d3 - d3t)[s] ** 2))),
                head_z_rms=float(np.sqrt(np.mean(zpsi[s] ** 2))),
                head_cov68=float(np.mean(np.abs(zpsi[s]) < 0.9945)), head_cov95=float(np.mean(np.abs(zpsi[s]) < 1.96)),
                head_cov99=float(np.mean(np.abs(zpsi[s]) < 2.5758)),
                nees_xy=float(np.mean(nees2[s])), nees_xy_p50=float(np.median(nees2[s])), nees_xy_p95=float(np.quantile(nees2[s], .95)),
                xy_cov95=float(np.mean(nees2[s] < 5.991)), nees3=float(np.mean(nees3[s])), nees4=float(np.mean(nees4[s])))


# ----------------------------------------------------------------------------- residual summaries
def residuals(D, bg, L, z=None):
    zz = D["z"] if z is None else z
    # RF residual vs model at truth, relative to the mean the filter actually used
    eps = zz - D["hg"] - np.where(np.isnan(L["mu_used"]), D["mu"][bg], L["mu_used"])
    dh = D["hg"] - L["hx"]
    e = np.c_[D["gt"][:, :3], np.full(len(D["t"]), D["b_true"])] - L["xp"]
    e[:, 2] = np.angle(np.exp(1j * e[:, 2]))
    He = np.einsum("nij,nj->ni", L["H"], e)
    ell = dh - He
    return eps, dh, He, ell, e


def acf_stats(x, dt=0.2):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if len(x) < 20:
        return dict(lag1=np.nan, l1e_s=np.nan, l05_s=np.nan, neff_ar1=np.nan, neff_geyer=np.nan)
    x = x - x.mean(); v = float(np.dot(x, x))
    if v <= 0:
        return dict(lag1=np.nan, l1e_s=np.nan, l05_s=np.nan, neff_ar1=np.nan, neff_geyer=np.nan)
    nmax = len(x) // 2
    r = np.array([np.dot(x[:-l], x[l:]) / v if l else 1.0 for l in range(nmax)])
    def first(th):
        idx = np.flatnonzero(r[1:] < th)
        return float((idx[0] + 1) * dt) if len(idx) else float("inf")      # inf = right-censored
    r1 = min(max(r[1], -0.99), 0.99)
    # Geyer initial positive sequence
    s = 0.0; k = 0
    while 2 * k + 2 < len(r):
        g = r[2 * k] + r[2 * k + 1]
        if g <= 0:
            break
        s += g; k += 1
    tau = -1 + 2 * s if s > 0 else 1.0
    return dict(lag1=float(r[1]), l1e_s=first(math.exp(-1)), l05_s=first(0.5), neff_ar1=float(len(x) * (1 - r1) / (1 + r1)),
                neff_geyer=float(len(x) / max(tau, 1e-9)))


def summarize(D, bg, L, sets=("S_all", "S_base"), windows=True, z=None):
    """C0 summaries per component, sample set and (optionally) window."""
    eps, dh, He, ell, e = residuals(D, bg, L, z)
    t = D["t"]; base = (t >= 30 - 1e-9) & D["fin"] & np.isfinite(L["nis"])
    masks = {"S_all": base, "S_base": base & D["acc"], "S_used": base & L["upd"].any(1)}
    rows = []
    wins = [("all", 30, 1e9)] + ([(f"{lo}-{min(hi, 9999):g}", lo, hi) for lo, hi in WINDOWS] if windows else [])
    for sname in sets:
        for wname, lo, hi in wins:
            m = masks[sname] & (t >= lo - 1e-9) & (t < hi)
            if m.sum() < 5:
                continue
            for j, comp in enumerate("rs"):
                nu = L["nu"][m, j]; ep = eps[m, j]; d = dh[m, j]; h_ = He[m, j]; l_ = ell[m, j]
                R = L["Ru"][m, j, j]; HPH = L["HPH"][m, j, j]; S = L["S"][m, j, j]
                E_nu2 = float(np.mean(nu ** 2))
                row = dict(set=sname, window=wname, comp=comp, n=int(m.sum()), E_nu2=E_nu2, E_eps2=float(np.mean(ep ** 2)),
                           E_dh2=float(np.mean(d ** 2)), E_2cross=float(np.mean(2 * ep * d)),
                           sum_check=float(abs(E_nu2 - np.mean(ep ** 2) - np.mean(d ** 2) - np.mean(2 * ep * d))),
                           E_He2=float(np.mean(h_ ** 2)), E_ell2=float(np.mean(l_ ** 2)), E_2He_ell=float(np.mean(2 * h_ * l_)),
                           E_R=float(np.mean(R)), E_HPH=float(np.mean(HPH)), E_S=float(np.mean(S)),
                           mr_eps2_R=float(np.mean(ep ** 2) / np.mean(R)), rm_eps2_R=float(np.mean(ep ** 2 / R)),
                           mr_dh2_HPH=float(np.mean(d ** 2) / np.mean(HPH)), rm_dh2_HPH=float(np.mean(d ** 2 / HPH)),
                           mr_He2_HPH=float(np.mean(h_ ** 2) / np.mean(HPH)), ell_share=float(np.mean(l_ ** 2) / max(np.mean(d ** 2), 1e-30)),
                           mr_nu2_S=float(E_nu2 / np.mean(S)), cross_share=float(np.mean(2 * ep * d) / E_nu2),
                           corr_eps_dh=float(np.corrcoef(ep, d)[0, 1]) if np.std(ep) > 0 and np.std(d) > 0 else np.nan,
                           mean_eps=float(np.mean(ep)), rms_eps=float(np.sqrt(np.mean(ep ** 2))))
                # lag-1 cross correlation corr(eps_k, dh_{k+1}) on consecutive packets of the mask
                idx = np.flatnonzero(m); nxt = idx[1:][np.diff(idx) == 1]; prv = nxt - 1
                if len(nxt) > 10:
                    row["corr_eps_k_dh_k1"] = float(np.corrcoef(eps[prv, j], dh[nxt, j])[0, 1])
                if wname == "all":
                    row.update({f"acf_{k}": v for k, v in acf_stats(ep).items()})
                rows.append(row)
    return rows


# ----------------------------------------------------------------------------- strata / permutation (E4)
def strata(D):
    """rho_true bin (5) x travel-direction sector vs anchor bearing (4) x |dh_s/dpsi| tercile (3); case-internal."""
    gt = D["gt"]; a = D["anchor"]
    rb = np.digitize(D["rho_true"], RHO_BINS[1:-1])
    bearing = np.arctan2(a[1] - gt[:, 1], a[0] - gt[:, 0])
    rel = np.angle(np.exp(1j * (bearing - gt[:, 2])))
    sec = np.floor((rel + np.pi) / (np.pi / 2)).astype(int).clip(0, 3)
    sens = np.abs(D["Hg"][:, 1, 2])
    q = np.quantile(sens[D["acc"]], [1 / 3, 2 / 3]) if D["acc"].any() else [0, 0]
    ter = np.digitize(sens, q)
    return rb, sec, ter


def stratum_ids(D, sel, min_n=20):
    """Hierarchical merge: drop sector, then tercile, then (if needed) everything within rho bin."""
    rb, sec, ter = strata(D)
    lab = np.full(len(rb), -1, dtype=object); merges = []
    full = {}
    for k in np.flatnonzero(sel):
        full.setdefault((rb[k], sec[k], ter[k]), []).append(k)
    for key, ks in full.items():
        if len(ks) >= min_n:
            for k in ks:
                lab[k] = key
    rest = [k for k in np.flatnonzero(sel) if lab[k] == -1]
    lvl2 = {}
    for k in rest:
        lvl2.setdefault((rb[k], ter[k]), []).append(k)
    rest2 = []
    for key, ks in lvl2.items():
        if len(ks) >= min_n:
            for k in ks:
                lab[k] = ("m_sec",) + key
            merges.append(dict(level="sector", key=str(key), n=len(ks)))
        else:
            rest2 += ks
    lvl3 = {}
    for k in rest2:
        lvl3.setdefault(rb[k], []).append(k)
    for key, ks in lvl3.items():
        for k in ks:
            lab[k] = ("m_all", key)
        merges.append(dict(level="sector+tercile", key=str(key), n=len(ks), below_min=len(ks) < min_n))
    return lab, merges


def permute_eps(D, eps, sel, block_s, rng, mode="perm"):
    """Return eps_tilde (n,2) with pairs moved only within strata of `sel` packets.
    mode perm/block: chunk each stratum's time-ordered members into blocks of k packets, permute block order.
    mode signflip: keep positions, flip (eps - stratum mean) sign per block."""
    lab, merges = stratum_ids(D, sel)
    out = eps.copy(); k = max(1, int(round(block_s / 0.2)))
    groups = {}
    for i in np.flatnonzero(sel):
        groups.setdefault(lab[i], []).append(i)
    for key, idx in groups.items():
        idx = np.array(sorted(idx)); blocks = [idx[j:j + k] for j in range(0, len(idx), k)]
        if mode == "signflip":
            m_ = eps[idx].mean(0)
            for b in blocks:
                sgn = rng.choice([-1.0, 1.0])
                out[b] = m_ + sgn * (eps[b] - m_)
        else:
            order = rng.permutation(len(blocks))
            src = np.concatenate([blocks[o] for o in order])
            out[idx] = eps[src]
    return out, merges, lab


def manipulation_check(eps, eps_t, lab, sel, mode):
    ok = True; worst = 0.0
    groups = {}
    for i in np.flatnonzero(sel):
        groups.setdefault(lab[i], []).append(i)
    for idx in groups.values():
        a, b = eps[idx], eps_t[idx]
        if mode == "signflip":
            # covariance of deviations from the stratum mean is preserved exactly; the mean is not
            da = a - a.mean(0); db = b - a.mean(0)
            worst = max(worst, float(np.max(np.abs(da.T @ da - db.T @ db)) / max(np.max(np.abs(da.T @ da)), 1e-30)))
        else:
            for j in range(2):
                if not np.array_equal(np.sort(a[:, j]), np.sort(b[:, j])):
                    ok = False
            pa = sorted(map(tuple, a)); pb = sorted(map(tuple, b))
            if pa != pb:
                ok = False
    s = np.flatnonzero(sel)
    lag1 = acf_stats(eps_t[s, 1])["lag1"]; lag1r = acf_stats(eps_t[s, 0])["lag1"]
    # stratum-demeaned lag-1: the design preserves stratum means, so decorrelation is checked on deviations
    dm = eps_t.copy()
    for idx in groups.values():
        dm[idx] = eps_t[idx] - eps[idx].mean(0)
    return dict(pairs_preserved=ok, signflip_rel_cov_dev=worst, lag1_s=lag1, lag1_r=lag1r,
                lag1_s_dm=acf_stats(dm[s, 1])["lag1"], lag1_r_dm=acf_stats(dm[s, 0])["lag1"])


# ----------------------------------------------------------------------------- training data (E2/E3)
def mb_residual_table(seed=0):
    """All finite packets of every case with MB residual, truth distance and BASE-mask flag (seed 0 mask)."""
    rows = []
    for c in CASES:
        D = load(c, seed)
        eps = D["z"] - D["hg"] - D["mu"]["MB"]
        f = D["fin"]
        rows.append(pd.DataFrame(dict(case=c, route=c[:2], k=np.flatnonzero(f), t=D["t"][f], rho=D["rho_true"][f],
                                      er=eps[f, 0], es=eps[f, 1], base=D["acc"][f])))
    return pd.concat(rows, ignore_index=True)


KNOTS = np.array([0.75, 2.25, 4.5, 8.0, 12.0])


def hat_w(r, j, knots=KNOTS):
    kn = knots[j]; lo = knots[j - 1] if j else None; hi = knots[j + 1] if j + 1 < len(knots) else None
    w = np.zeros_like(r, float)
    left = r <= kn; right = ~left
    w[left] = 1.0 if lo is None else np.clip((r[left] - lo) / (kn - lo), 0, 1)
    w[right] = 1.0 if hi is None else np.clip((hi - r[right]) / (hi - kn), 0, 1)
    return w


def cov_table(df):
    """Hat-basis raw second moments per knot: E[er^2], E[es^2], E[er es] -> (rr, ss, corr)."""
    out = []
    r = df.rho.to_numpy()
    for j in range(len(KNOTS)):
        w = hat_w(r, j)
        if w.sum() < 10:
            out.append((np.nan, np.nan, np.nan)); continue
        rr = float(np.sum(w * df.er ** 2) / w.sum()); ss = float(np.sum(w * df.es ** 2) / w.sum())
        rs = float(np.sum(w * df.er * df.es) / w.sum())
        out.append((rr, ss, float(np.clip(rs / math.sqrt(rr * ss), -0.95, 0.95))))
    out = np.array(out)
    for c in range(3):
        bad = np.isnan(out[:, c])
        if bad.any():
            out[bad, c] = np.interp(KNOTS[bad], KNOTS[~bad], out[~bad, c])
    return out


def cov_interp(tab, rho):
    return tuple(float(np.interp(rho, KNOTS, tab[:, c])) for c in range(3))


def ridge_fit(X, y, alpha=30.0):
    mu = X.mean(0); sd = X.std(0); sd[sd == 0] = 1.0
    Z = (X - mu) / sd; ym = y.mean()
    beta = np.linalg.solve(Z.T @ Z + alpha * np.eye(Z.shape[1]), Z.T @ (y - ym))
    return dict(mu=mu, sd=sd, beta=beta, b0=ym)


def ridge_pred(m, X):
    return m["b0"] + ((X - m["mu"]) / m["sd"]) @ m["beta"]


def online_features(x, h, H, anchor):
    """Features available online from the filter prior only."""
    rh = math.hypot(x[0] - anchor[0], x[1] - anchor[1])
    bearing = math.atan2(anchor[1] - x[1], anchor[0] - x[0]); rel = math.atan2(math.sin(bearing - x[2]), math.cos(bearing - x[2]))
    return np.array([rh, rh ** 2, h[1], H[1, 2], abs(H[1, 2]), math.cos(rel), math.sin(rel), H[0, 0] ** 2 + H[0, 1] ** 2])


def jdump(path, obj):
    Path(path).write_text(json.dumps(obj, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o)))
