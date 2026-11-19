"""Empirical polarization LUT h_emp(psi, el, beta) learned from Full-only station sweeps (plan amendment 01, A2).
h = sum_{q,j,m} theta_qjm f_q(psi) B_j(el) g_m(beta)
  f_q : Fourier basis in psi, order K (2K+1 functions)
  B_j : cubic B-spline in el (J functions, uniform interior knots over the training el range; el clamped outside)
  g_m : beta harmonics, M=1 -> {1, cos b, sin b} (Corridor), M=2 adds {cos 2b, sin 2b} (Office)
Fit: Huber IRLS with a tiny ridge. Analytic derivatives give a = dh/dpsi and the (x, y) Jacobian through el(rho), beta."""
import numpy as np
from scipy.interpolate import BSpline


class EmpLUT:
    def __init__(self, anchor, K=4, J=6, M=1, dh=2.65 - 0.45, ridge=1e-6, huber=1.345):
        self.anchor = np.asarray(anchor[:2], float); self.K, self.J, self.M, self.dh = K, J, M, dh
        self.ridge, self.huber = ridge, huber; self.theta = None

    # ---- geometry
    def geo(self, x, y):
        dx, dy = np.asarray(x) - self.anchor[0], np.asarray(y) - self.anchor[1]
        rho = np.hypot(dx, dy); el = np.arctan2(self.dh, rho); beta = np.arctan2(dy, dx)
        return dx, dy, rho, el, beta

    # ---- bases
    def fpsi(self, psi, d=0):
        cols = [np.ones_like(psi) if d == 0 else np.zeros_like(psi)]
        for k in range(1, self.K + 1):
            if d == 0: cols += [np.cos(k * psi), np.sin(k * psi)]
            else: cols += [-k * np.sin(k * psi), k * np.cos(k * psi)]
        return np.stack(cols, 1)
    def gbeta(self, b, d=0):
        cols = [np.ones_like(b) if d == 0 else np.zeros_like(b)]
        for m in range(1, self.M + 1):
            if d == 0: cols += [np.cos(m * b), np.sin(m * b)]
            else: cols += [-m * np.sin(m * b), m * np.cos(m * b)]
        return np.stack(cols, 1)
    def _spl(self, lo, hi):
        n_int = self.J - 4; inner = np.linspace(lo, hi, n_int + 2)[1:-1]
        self.knots = np.r_[[lo] * 4, inner, [hi] * 4]; self.lo, self.hi = lo, hi
    def bel(self, el, d=0):
        e = np.clip(el, self.lo, self.hi); out = np.empty((len(e), self.J))
        for j in range(self.J):
            c = np.zeros(self.J); c[j] = 1.; s = BSpline(self.knots, c, 3, extrapolate=False)
            out[:, j] = (s(e) if d == 0 else s.derivative()(e))
        out = np.nan_to_num(out)
        if d == 1: out[(el < self.lo) | (el > self.hi)] = 0.
        return out
    def design(self, psi, el, beta, dpsi=0, del_=0, dbeta=0):
        F, Bm, G = self.fpsi(psi, dpsi), self.bel(el, del_), self.gbeta(beta, dbeta)
        return np.einsum("nq,nj,nm->nqjm", F, Bm, G).reshape(len(psi), -1)

    # ---- fit / eval
    def fit(self, x, y, psi, s, iters=30):
        _, _, _, el, beta = self.geo(x, y); self._spl(el.min(), el.max())
        X = self.design(psi, el, beta); w = np.ones(len(s)); lam = self.ridge * np.trace(X.T @ X) / X.shape[1]
        for _ in range(iters):
            Xw = X * w[:, None]; th = np.linalg.solve(X.T @ Xw + lam * np.eye(X.shape[1]), Xw.T @ s)
            r = s - X @ th; sc = 1.4826 * np.median(np.abs(r - np.median(r))) + 1e-12; c = self.huber * sc
            w_new = np.where(np.abs(r) <= c, 1., c / np.abs(r))
            if np.max(np.abs(w_new - w)) < 1e-6: w = w_new; break
            w = w_new
        self.theta = th; self.el_range_deg = (float(np.degrees(self.lo)), float(np.degrees(self.hi))); return self
    def eval(self, x, y, psi):
        dx, dy, rho, el, beta = self.geo(x, y); psi = np.asarray(psi, float)
        s = self.design(psi, el, beta) @ self.theta
        ds_dpsi = self.design(psi, el, beta, dpsi=1) @ self.theta
        ds_del = self.design(psi, el, beta, del_=1) @ self.theta
        ds_db = self.design(psi, el, beta, dbeta=1) @ self.theta
        r2 = np.maximum(rho**2, 1e-12); del_drho = -self.dh / (r2 + self.dh**2)
        dx_ = ds_del * del_drho * dx / np.sqrt(r2) + ds_db * (-dy / r2)
        dy_ = ds_del * del_drho * dy / np.sqrt(r2) + ds_db * (dx / r2)
        return s, dx_, dy_, ds_dpsi
    def s_fn(self):
        def fn(states, case):
            st = np.asarray(states, float); s, dx, dy, dp = self.eval(st[:, 0], st[:, 1], st[:, 2])
            return s, np.c_[dx, dy, dp]
        return fn
    def to_dict(self):
        return dict(anchor=self.anchor.tolist(), K=self.K, J=self.J, M=self.M, dh=self.dh, knots=self.knots.tolist(),
                    lo=float(self.lo), hi=float(self.hi), theta=self.theta.tolist())
    @classmethod
    def from_dict(cls, d):
        o = cls(d["anchor"], d["K"], d["J"], d["M"], d["dh"]); o.knots = np.array(d["knots"]); o.lo, o.hi = d["lo"], d["hi"]
        o.theta = np.array(d["theta"]); return o
