"""Stage 2 deliberate reference-model errors FFD' (plan section 6). Each returns s_fn(states, case) -> (s, dS/d(x,y,psi)).
P1  : h'(x,y,psi) = h_FFD(x,y,psi+5deg) (Jacobian shifted with it)
P1m : -5 deg
P2  : +1 dB port gain imbalance, s' = (g(1+s) - (1-s)) / (g(1+s) + (1-s)), g = 10**0.1, J' = J * 4g / D**2
P3  : P1 then P2"""
import numpy as np
G = 10 ** 0.1


def make(base, kind):
    shift = {"P1": 5., "P1m": -5., "P2": 0., "P3": 5.}[kind]; gain = kind in ("P2", "P3")
    def fn(states, case):
        st = np.array(states, float, copy=True); st[:, 2] = st[:, 2] + np.radians(shift)
        pred, J = base.batch(st, case)[:2]; s, js = pred[:, 1].copy(), J[:, 1, :3].copy()
        if gain:
            D = G * (1 + s) + (1 - s); s2 = (G * (1 + s) - (1 - s)) / D; js = js * (4 * G / D**2)[:, None]; s = s2
        return s, js
    return fn


def at_stations(fn, x, y, psi, case, chunk=512):
    s = np.empty(len(x)); a = np.empty(len(x))
    for k in range(0, len(x), chunk):
        st = np.c_[x[k:k + chunk], y[k:k + chunk], psi[k:k + chunk], np.zeros(len(x[k:k + chunk]))]
        v, j = fn(st, case); s[k:k + chunk] = v; a[k:k + chunk] = j[:, 2]
    return s, a
