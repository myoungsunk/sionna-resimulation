"""Rebuild the saved blocks from CSV only and compare with the original code at random poses (prints the max abs difference)."""
import sys, numpy as np, pandas as pd
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator, CubicSpline
d = sys.argv[1]; W = np.r_[1., 2 * np.ones(17), 1.] / 36; kk = np.arange(19)
def series(c, psi): return np.sum(W * np.real(c * np.exp(1j * kk[None] * (psi[:, None] + np.pi))), 1)
O = pd.read_csv(f"{d}/SWB_O_COEFS.csv"); st = O.groupby("station")[["x", "y"]].first(); Cc = np.stack([g.sort_values("k").pipe(lambda q: q.re.values + 1j * q.im.values) for _, g in O.groupby("station")])
V = np.c_[Cc.real, Cc.imag]; lin, near = LinearNDInterpolator(st.values, V), NearestNDInterpolator(st.values, V)
def swb_o(x, y, psi):
    q = np.c_[x, y]; v = lin(q); b = np.isnan(v[:, 0]); v[b] = near(q[b]); return series(v[:, :19] + 1j * v[:, 19:], psi)
Cr = pd.read_csv(f"{d}/SWB_C_COEFS.csv"); XS = np.sort(Cr.x.unique()); YS = np.sort(Cr.y.unique()); A = np.zeros((len(XS), len(YS), 19), complex)
A[Cr.col.values, Cr.line.values, Cr.k.values] = Cr.re.values + 1j * Cr.im.values; sp = CubicSpline(XS, np.concatenate([A.real, A.imag], 2), axis=0)
def swb_c_corr(x, y, psi):
    V_ = sp(x); yy = np.clip(y, YS[0], YS[-1]); j = np.clip(np.searchsorted(YS, yy) - 1, 0, len(YS) - 2); t = (yy - YS[j]) / (YS[j + 1] - YS[j]); n = np.arange(len(x))
    c = V_[n, j] + t[:, None] * (V_[n, j + 1] - V_[n, j]); return series(c[:, :19] + 1j * c[:, 19:], psi)
def swb_c(x, y, psi):
    rho = np.hypot(x - 5, y - 2.2); s = np.where(x >= 5, 1., -1.); return swb_c_corr(10 + s * rho, np.zeros_like(x), psi)
if __name__ == "__main__":
    sys.path.insert(0, "/home/claude/lut8"); sys.path.insert(0, "/home/claude/lut5"); import office_swb as OS, corr2office as C2
    rng = np.random.default_rng(1); x = rng.uniform(0.5, 9.5, 2000); y = rng.uniform(0.75, 11.25, 2000); psi = rng.uniform(-np.pi, np.pi, 2000)
    print("SWB-O max diff", np.abs(swb_o(x, y, psi) - OS.SWBO().eval(x, y, psi)[0]).max()); print("SWB-C max diff", np.abs(swb_c(x, y, psi) - C2.evalc(x, y, psi)[0]).max())
