"""Bias-aware FFD blocks (DIAGNOSTIC, corridor anchor B, mount 0). Extends lut3/bv_block.BV.
Per station (36 yaw): d = chi(s_full) - chi(h_ref) (2-psi phase), k = 1 - L(s_full)/L(h_ref) (2-psi amplitude).
Field modes (per anchor side, function of rho):
  "zero"  : d = k = 0
  "smooth": Gaussian kernel 0.75 m over stations (= BV)
  "bin"   : bin mean over stations of the same bin [0,3), [3,6), [6,10), joined by logistic transitions (width TW m)
Block: m(x, y, psi) = (1 - k) h_ref(x, y, psi - d) + off(rho, side)
  off: "none" | "bin" (bin x side mean of s_full - (1-k) h_ref(psi - d) over stations, same logistic join)
Jacobian: (1 - k) dh_ref (rho-derivatives of the fields neglected, as in BV)."""
import numpy as np, pandas as pd
from scipy.optimize import nnls
import bv_block as BVM

EDG = BVM.EDG; RG = BVM.RG; TW = 0.15


def _binfield(rho_st, v):
    """piecewise-constant bin means of v over RG with logistic joins at 3 m and 6 m"""
    b = np.clip(np.searchsorted(EDG, rho_st, side="right") - 1, 0, 2)
    mu = np.array([v[b == i].mean() if np.any(b == i) else 0. for i in range(3)])
    s1 = 1 / (1 + np.exp(-(RG - 3.) / TW)); s2 = 1 / (1 + np.exp(-(RG - 6.) / TW))
    return mu[0] * (1 - s1) + mu[1] * (s1 - s2) + mu[2] * s2, mu


class BB(BVM.BV):
    def __init__(self, ref_fn, case, SW, field="bin", off="none"):
        super().__init__(ref_fn, case, SW, zero=(field == "zero"))
        self.field, self.offmode, self.binmeans = field, off, {}
        if field == "bin":
            for sd in (-1, 1):
                q = self.st[self.st.side == sd]
                gd, md = _binfield(q.rho.values, q.d.values); gk, mk = _binfield(q.rho.values, q.k.values)
                self.grid[sd] = (gd, gk); self.binmeans[sd] = dict(d_deg=np.degrees(md).tolist(), k=mk.tolist())
        self.offgrid = {sd: np.zeros(len(RG)) for sd in (-1, 1)}
        if off == "bin":
            X = np.c_[SW.x_eval, SW.y_eval, np.radians(SW.yaw_deg), np.zeros(len(SW))]
            m0, _ = self._s_noff()(X, case); e = SW.s_fp.values - m0; sd_ = BVM.side_of(SW.x_eval.values)
            for sd in (-1, 1):
                q = sd_ == sd; g, mo = _binfield(SW.rho.values[q], e[q]); self.offgrid[sd] = g
                self.binmeans.setdefault(sd, {})["off"] = mo.tolist()

    def _s_noff(self):
        return BVM.BV.s_fn(self)

    def s_fn(self):
        base = self._s_noff()
        def fn(states, case):
            m, J = base(states, case)
            if self.offmode == "none":
                return m, J
            st = np.asarray(states, float); rho = np.hypot(st[:, 0] - BVM.ANCHOR[0], st[:, 1] - BVM.ANCHOR[1]); sd = BVM.side_of(st[:, 0])
            o = np.empty(len(rho))
            for s in (-1, 1):
                k = sd == s; o[k] = np.interp(rho[k], RG, self.offgrid[s])
            return m + o, J
        return fn


def fitB(e, a):
    lo = np.abs(a) < .3; c0 = float(np.mean(e[lo] ** 2)); c1 = float(nnls((a ** 2)[:, None], e ** 2 - c0)[0][0]); return c1, c0


def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi


def kr_one(Xt, yt, mu0, q, prm, maxn=150):
    lx, ly, lp, nug = prm
    d = np.abs(Xt[:, 0] - q[0]) / lx + np.abs(Xt[:, 1] - q[1]) / ly + np.abs(wrap(Xt[:, 2] - q[2])) / lp
    idx = np.argpartition(d, maxn)[:maxn] if len(d) > maxn else np.arange(len(d)); Xi = Xt[idx]
    K = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
    w = np.linalg.solve((1 - nug) * K + nug * np.eye(len(idx)), (1 - nug) * np.exp(-d[idx])); return mu0 + w @ (yt[idx] - mu0)


def near_kriging_table(block, SW, case, prm):
    """BVK-style: labels e = s_full - m at stations; near-bin (rho < 3 m) table from LOSO kriging residual; mid/far from block.table."""
    X = np.c_[SW.x_eval, SW.y_eval, np.radians(SW.yaw_deg), np.zeros(len(SW))]; m, J = block.s_fn()(X, case); a = J[:, 2]; e = SW.s_fp.values - m
    b = np.clip(np.searchsorted(EDG, SW.rho.values, side="right") - 1, 0, 2); b0 = b == 0
    pos = (SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str)).to_numpy(); X3 = np.c_[SW.x_eval, SW.y_eval, np.radians(SW.yaw_deg)]
    mu = np.full(len(e), np.nan)
    for st in np.unique(pos[b0]):
        te = pos == st; tr = (~te) & b0; Xt, yt = X3[tr], e[tr]; m0 = yt.mean()
        for i in np.flatnonzero(te): mu[i] = kr_one(Xt, yt, m0, X3[i], prm)
    T = block.table(SW); c1, c0 = fitB((e - mu)[b0], a[b0]); T["c1"][0], T["c0"][0] = c1, c0
    return T, e, dict(near_label_rms=float(np.sqrt(np.mean(e[b0] ** 2))), near_loso_rms=float(np.sqrt(np.mean((e - mu)[b0] ** 2))))
