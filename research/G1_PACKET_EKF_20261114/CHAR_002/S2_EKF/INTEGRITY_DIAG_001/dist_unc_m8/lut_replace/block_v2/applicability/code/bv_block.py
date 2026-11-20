"""Replacement block BV (DIAGNOSTIC). Built from station sweeps + a reference LoS model (FFD, or a perturbed FFD').
  per station: d_st = chi(s_full) - chi(h_ref)   (2-psi phase; nadir-referenced up to a global constant)
               k_st = 1 - L(s_full) / L(h_ref)   (2-psi amplitude ratio)
  smooth fields: dbar(rho, side), kbar(rho, side) = Gaussian-kernel (0.75 m in rho) mean over the stations on the same anchor side
  block: m(x, y, psi) = (1 - kbar) * h_ref(x, y, psi - dbar);  Jacobian (1 - kbar) * dh_ref (rho-derivatives of dbar, kbar neglected)
  variance table: eps = s_full - m at stations; per bin [0,3,6,10): c1 (sigma_theta^2) by nnls on a_m^2, c0 (sigma_res^2) from |a_m| < 0.3"""
import numpy as np, pandas as pd
from scipy.optimize import nnls
ANCHOR = np.array([10.0, 0.0]); EDG = np.array([0., 3., 6., 10.]); BW = 0.75; RG = np.arange(0, 10.01, 0.05)
PSI = np.radians(np.arange(-180, 180, 10.))
wrap = lambda a: (a + np.pi / 2) % np.pi - np.pi / 2
def chiL(s): c = 2 * np.mean(s * np.cos(2 * PSI)); d = 2 * np.mean(s * np.sin(2 * PSI)); return 0.5 * np.arctan2(c, -d), np.hypot(c, d)
def side_of(x): return np.where(np.asarray(x) >= ANCHOR[0], 1, -1)
class BV:
    def __init__(self, ref_fn, case, SW, zero=False):
        """ref_fn(states, case) -> (s, J[:, :3]); SW: station sweep table (x_eval, y_eval, yaw_deg, s_fp, rho)"""
        self.ref_fn, self.case = ref_fn, case
        SW = SW.sort_values(["x_eval", "y_eval", "yaw_deg"]); st = []
        for (x, y), g in SW.groupby([SW.x_eval.round(3), SW.y_eval.round(2)]):
            X = np.c_[g.x_eval, g.y_eval, np.radians(g.yaw_deg), np.zeros(len(g))]; h, _ = ref_fn(X, case)
            cf, lf = chiL(g.s_fp.values); cr, lr = chiL(h)
            st.append(dict(x=x, y=y, rho=g.rho.iloc[0], side=int(side_of(x)), d=wrap(cf - cr), k=1 - lf / lr))
        self.st = pd.DataFrame(st); self.grid = {}
        for sd in (-1, 1):
            q = self.st[self.st.side == sd]; W = np.exp(-0.5 * ((RG[:, None] - q.rho.values[None]) / BW)**2); W /= W.sum(1, keepdims=True)
            self.grid[sd] = (W @ q.d.values, W @ q.k.values) if not zero else (np.zeros(len(RG)), np.zeros(len(RG)))
    def fields(self, x, y):
        rho = np.hypot(np.asarray(x) - ANCHOR[0], np.asarray(y) - ANCHOR[1]); sd = side_of(x); d = np.empty(len(rho)); k = np.empty(len(rho))
        for s in (-1, 1):
            m = sd == s; d[m] = np.interp(rho[m], RG, self.grid[s][0]); k[m] = np.interp(rho[m], RG, self.grid[s][1])
        return d, k
    def s_fn(self):
        def fn(states, case):
            st = np.array(states, float, copy=True); d, k = self.fields(st[:, 0], st[:, 1]); st[:, 2] -= d
            h, J = self.ref_fn(st, case); return (1 - k) * h, J * (1 - k)[:, None]
        return fn
    def table(self, SW):
        X = np.c_[SW.x_eval, SW.y_eval, np.radians(SW.yaw_deg), np.zeros(len(SW))]; m, J = self.s_fn()(X, self.case); a = J[:, 2]; e = SW.s_fp.values - m
        b = np.clip(np.searchsorted(EDG, SW.rho.values, side="right") - 1, 0, 2); tab = dict(edges=list(EDG), c1=[], c0=[])
        for i in range(3):
            q = b == i; lo = q & (np.abs(a) < .3); c0 = float(np.mean(e[lo]**2)); c1 = float(nnls((a[q]**2)[:, None], e[q]**2 - c0)[0][0])
            tab["c1"].append(c1); tab["c0"].append(c0)
        return tab
