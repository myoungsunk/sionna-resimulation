"""Office sweep block SWB-O (DIAGNOSTIC): 25 LoS stations, per-station 36-yaw curve with all 19 psi harmonics,
coefficients Delaunay-linear in (x, y) (nearest station outside the hull). psi analytic; d/dx, d/dy by central differences (h = 1 mm).
Variance table: leave-one-station-out residual (interpolant rebuilt without that station) -> c1 a^2 + c0 per bin [0,3,6,10)."""
import numpy as np, pandas as pd
from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
from scipy.optimize import nnls
O = "/home/claude/office"; A = np.array([5., 2.2]); K = 19; kk = np.arange(K); EDG = np.array([0., 3., 6., 10.])
S = pd.read_csv(f"{O}/OFFICE_SWEEP_FEATURES.csv.gz"); S = S[S.los].sort_values(["station", "yaw_deg"]).reset_index(drop=True)
ST = S.groupby("station").agg(x=("x_eval", "first"), y=("y_eval", "first"), rho=("rho", "first")).reset_index()
PSI = np.radians(np.sort(S.yaw_deg.unique()))
CUR = np.array([g.s_fp.to_numpy() for _, g in S.groupby("station")])          # (25, 36)
COEF = np.fft.rfft(CUR, axis=1)[:, :K]; W = np.r_[1., 2 * np.ones(K - 2), 1.] / 36
class SWBO:
    def __init__(self, drop=None):
        keep = np.ones(len(ST), bool)
        if drop is not None: keep[drop] = False
        P = ST[["x", "y"]].to_numpy()[keep]; V = np.c_[COEF.real, COEF.imag][keep]
        self.lin, self.near = LinearNDInterpolator(P, V), NearestNDInterpolator(P, V)
    def _c(self, x, y):
        q = np.c_[x, y]; V = self.lin(q); bad = np.isnan(V[:, 0])
        if bad.any(): V[bad] = self.near(q[bad])
        return V[:, :K] + 1j * V[:, K:]
    def _s(self, c, psi):
        e = np.exp(1j * kk[None] * (psi[:, None] + np.pi)); return np.sum(W * np.real(c * e), 1), np.sum(W * np.real(1j * kk[None] * c * e), 1)
    def eval(self, x, y, psi, h=1e-3):
        x, y, psi = (np.atleast_1d(np.asarray(v, float)) for v in (x, y, psi))
        s, sp = self._s(self._c(x, y), psi)
        sx = (self._s(self._c(x + h, y), psi)[0] - self._s(self._c(x - h, y), psi)[0]) / (2 * h)
        sy = (self._s(self._c(x, y + h), psi)[0] - self._s(self._c(x, y - h), psi)[0]) / (2 * h)
        return s, sx, sy, sp
    def s_fn(self):
        def fn(states, case):
            st = np.asarray(states, float); s, sx, sy, sp = self.eval(st[:, 0], st[:, 1], st[:, 2]); return s, np.c_[sx, sy, sp]
        return fn
def station_out_table():
    E, Aa, B = [], [], []
    for i in range(len(ST)):
        m = SWBO(drop=i); s, _, _, sp = m.eval(np.full(36, ST.x[i]), np.full(36, ST.y[i]), PSI)
        E.append(CUR[i] - s); Aa.append(sp); B.append(np.full(36, int(np.clip(np.searchsorted(EDG, ST.rho[i], side="right") - 1, 0, 2))))
    E, Aa, B = map(np.concatenate, (E, Aa, B)); tab = dict(edges=list(EDG), c1=[], c0=[])
    for q in range(3):
        e, a = E[B == q], Aa[B == q]; lo = np.abs(a) < .3; c0 = float(np.mean(e[lo]**2)); c1 = float(nnls((a**2)[:, None], e**2 - c0)[0][0]); tab["c1"].append(c1); tab["c0"].append(c0)
    return tab, E, B
if __name__ == "__main__":
    import json
    T, E, B = station_out_table(); json.dump(T, open("/home/claude/lut8/TABLE_SWBO.json", "w"))
    print(json.dumps(T)); print("station-out residual RMS by bin", [round(float(np.sqrt(np.mean(E[B == q]**2))), 4) for q in range(3)])
    m = SWBO(); x, y, p = 4.2, 3.1, 0.7; h = 1e-5; s0 = m.eval(x, y, p)
    print("dpsi fd", (m.eval(x, y, p + h)[0] - s0[0]) / h, s0[3])
