"""[lut5 copy: full column-out fix] Station-sweep-only block SWB (no FFD in construction; DIAGNOSTIC). RT Corridor station sweeps (40 x-columns, 5 y-lines, 36 yaws).
 1. per station: keep psi harmonics k <= 4 (rfft of the 36-yaw sweep).
 2. reference polarisation angle chi_ref (per anchor side and y line):
      rho < 3 m : measured chi_full (multipath small)
      rho >= 6 m: chi of the same-line +-3 column average (heading part averages out)
      3-6 m     : quadratic in rho fitted to the two sets above (LoS-free interpolation)
    scatter = chi_full - chi_ref - dbar, dbar = Gaussian-kernel (0.75 m in rho) mean of chi_full - chi_ref over 3-6 m stations of the same side
 3. station block curve:
      rho < 3 m : filtered s_full
      3-6 m     : filtered s_full rotated back by the station scatter only (keeps the smooth, reproducible part dbar)
      rho >= 6 m: filtered average over +-3 columns x 5 lines (same side)
    mode "los": also rotate back dbar (LoS-like curve, for comparison with FFD only)
 4. continuous block: harmonic coefficients cubic-spline in x per line, linear in y; psi analytic. Jacobian analytic.
 5. variance table: x-column-out residual (block rebuilt without that column) -> c1 a^2 + c0 per bin [0,3,6,10)."""
import numpy as np, pandas as pd
from scipy.interpolate import CubicSpline
from scipy.optimize import nnls
VARIANT = "allraw"; K = 19; EDG = np.array([0., 3., 6., 10.]); AX = 10.0
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz")
XS = np.sort(SW.x_eval.round(3).unique()); YS = np.sort(SW.y_eval.round(2).unique()); PS = np.sort(SW.yaw_deg.unique()); PSI = np.radians(PS)
ix = np.searchsorted(XS, SW.x_eval.round(3)); iy = np.searchsorted(YS, SW.y_eval.round(2)); ip = np.searchsorted(PS, SW.yaw_deg)
F = np.full((len(XS), len(YS), 36), np.nan); F[ix, iy, ip] = SW.s_fp.values
RHO = np.hypot(XS[:, None] - AX, YS[None, :]); SIDE = np.sign(XS - AX); SIDE[SIDE == 0] = 1
kk = np.arange(K); wrap = lambda a: (a + np.pi / 2) % np.pi - np.pi / 2
def coef(s): return np.fft.rfft(s)[:K]
def chi_of(c): z = c[2]; return 0.5 * np.angle(-1j * z) if False else chi_from_samples(np.fft.irfft(np.r_[c, np.zeros(19 - K)][:19], n=36))
def chi_from_samples(s): a = 2 * np.mean(s * np.cos(2 * PSI)); b = 2 * np.mean(s * np.sin(2 * PSI)); return 0.5 * np.arctan2(a, -b)
def rot(c, d):  # coefficients of s(psi - d)
    return c * np.exp(-1j * kk * d)
def avg_curve(i, j, k=3, lines="same", drop=()):
    cols = [q for q in range(i - k, i + k + 1) if 0 <= q < len(XS) and SIDE[q] == SIDE[i] and q not in drop]; rows = range(len(YS)) if lines == "all" else [j]
    return np.mean([F[q, r] for q in cols for r in rows], axis=0)
def build_station_coefs(mode="block", F_=None, drop=()):
    """drop: x-column indices removed BEFORE every operation (references, averages, smoothing, spline)."""
    F_ = F if F_ is None else F_; C = np.zeros((len(XS), len(YS), K), complex); CHI = np.zeros((len(XS), len(YS))); REF = np.zeros_like(CHI)
    for j in range(len(YS)):
        for sd in (-1, 1):
            cols = [i for i in range(len(XS)) if SIDE[i] == sd and i not in drop]; xr, cr = [], []
            for i in cols:
                CHI[i, j] = chi_from_samples(F_[i, j]); r = RHO[i, j]
                if 1 <= r < 3: xr.append(r); cr.append(CHI[i, j])
                elif r >= 6: xr.append(r); cr.append(chi_from_samples(avg_curve(i, j, drop=drop)))
            cr = np.unwrap(2 * np.array(cr)) / 2; b = np.polyfit(xr, cr, 2)
            for i in cols:
                r = RHO[i, j]
                REF[i, j] = CHI[i, j] if r < 3 else (chi_from_samples(avg_curve(i, j, drop=drop)) if r >= 6 else np.polyval(b, r))
    D = wrap(CHI - REF); keepc = np.array([i not in drop for i in range(len(XS))]); mid = (RHO >= 3) & (RHO < 6) & keepc[:, None]; dbar = np.zeros_like(D)
    for i in range(len(XS)):
        for j in range(len(YS)):
            if not mid[i, j]: continue
            m = mid & (SIDE[:, None] == SIDE[i]); wt = np.exp(-0.5 * ((RHO - RHO[i, j]) / 0.75)**2) * m; dbar[i, j] = np.sum(wt * D) / np.sum(wt)
    for i in range(len(XS)):
        if i in drop: continue
        for j in range(len(YS)):
            r = RHO[i, j]
            if VARIANT == "allavg": c = coef(avg_curve(i, j, 3, "all", drop=drop))
            elif VARIANT == "allraw": c = coef(F_[i, j])
            elif r < 3: c = coef(F_[i, j])
            elif r < 6: c = rot(coef(F_[i, j]), -(D[i, j] - dbar[i, j]) - (dbar[i, j] if mode == "los" else 0.))
            else: c = coef(avg_curve(i, j, 3, "all", drop=drop))
            C[i, j] = c
    return C, dict(chi=CHI, ref=REF, d=D, dbar=dbar)
class SWB:
    def __init__(self, mode="block", drop_col=None):
        C, self.info = build_station_coefs(mode, drop=(() if drop_col is None else (drop_col,))); keep = np.ones(len(XS), bool)
        if drop_col is not None: keep[drop_col] = False
        Y = np.concatenate([C.real, C.imag], axis=2)[keep]        # (ncol, 5 lines, 2K)
        self.sp = CubicSpline(XS[keep], Y, axis=0); self.dsp = self.sp.derivative()
    def _coef(self, x, y):
        V = self.sp(x); dV = self.dsp(x)                            # (n, 5, 2K)
        yy = np.clip(y, YS[0], YS[-1]); j = np.clip(np.searchsorted(YS, yy) - 1, 0, len(YS) - 2); t = (yy - YS[j]) / (YS[j + 1] - YS[j])
        n = np.arange(len(x)); A0, A1 = V[n, j], V[n, j + 1]; c = A0 + t[:, None] * (A1 - A0); cx = dV[n, j] + t[:, None] * (dV[n, j + 1] - dV[n, j])
        cy = (A1 - A0) / (YS[j + 1] - YS[j])[:, None] * ((y >= YS[0]) & (y <= YS[-1]))[:, None]
        z = lambda q: q[:, :K] + 1j * q[:, K:]; return z(c), z(cx), z(cy)
    def eval(self, x, y, psi):
        x, y, psi = map(lambda v: np.atleast_1d(np.asarray(v, float)), (x, y, psi)); c, cx, cy = self._coef(x, y)
        e = np.exp(1j * kk[None] * (psi[:, None] + np.pi)); w = np.r_[1., 2 * np.ones(K - 2), 1.][None] / 36
        s = np.sum(w * np.real(c * e), 1); sx = np.sum(w * np.real(cx * e), 1); sy = np.sum(w * np.real(cy * e), 1); sp = np.sum(w * np.real(1j * kk[None] * c * e), 1)
        return s, sx, sy, sp
    def s_fn(self):
        def fn(states, case):
            st = np.asarray(states, float); s, sx, sy, sp = self.eval(st[:, 0], st[:, 1], st[:, 2]); return s, np.c_[sx, sy, sp]
        return fn
def column_out_table():
    """x-column-out residuals at all stations -> c1, c0 per distance bin; returns table and residual arrays."""
    E = np.zeros_like(F); A = np.zeros_like(F)
    for i in range(len(XS)):
        B = SWB(drop_col=i)
        for j in range(len(YS)):
            s, _, _, sp = B.eval(np.full(36, XS[i]), np.full(36, YS[j]), PSI); E[i, j] = F[i, j] - s; A[i, j] = sp
    b = np.clip(np.searchsorted(EDG, RHO, side="right") - 1, 0, 2); tab = dict(edges=list(EDG), c1=[], c0=[])
    for q in range(3):
        e = E[b == q].ravel(); a = A[b == q].ravel(); lo = np.abs(a) < .3; c0 = float(np.mean(e[lo]**2)); c1 = float(nnls((a**2)[:, None], e**2 - c0)[0][0])
        tab["c1"].append(c1); tab["c0"].append(c0)
    return tab, E, A
