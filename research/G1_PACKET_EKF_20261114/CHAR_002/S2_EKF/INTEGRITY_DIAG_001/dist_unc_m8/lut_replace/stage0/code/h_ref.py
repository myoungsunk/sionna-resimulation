"""Swappable polarization observation interface (Stage 0-B).
SwapS wraps the frozen native observer and replaces only the s row of the prediction and of the Jacobian:
  s_fn(states, case) -> (s (n,), dS/d(x, y, psi) (n, 3)).
The range row (and everything else) is the frozen native model. s_fn = None -> pass-through.
ffd_s_fn is the reference implementation (frozen FFD), used for the identity checks.
label_es(...) builds the reference-model residual label e_s = s_full - h_ref(x, y, psi) at station poses."""
import numpy as np


class SwapS:
    def __init__(self, base, s_fn=None):
        self.base, self.s_fn = base, s_fn

    def batch(self, states, case, gradient=True, return_diagnostics=False):
        out = self.base.batch(states, case, gradient=gradient, return_diagnostics=return_diagnostics)
        if self.s_fn is None: return out
        pred, J = out[0].copy(), (None if out[1] is None else out[1].copy())
        s, js = self.s_fn(np.asarray(states, float), case)
        pred[:, 1] = s
        if J is not None: J[:, 1, :3] = js
        return (pred, J) + tuple(out[2:])


def ffd_s_fn(base):
    def fn(states, case):
        pred, J = base.batch(states, case)[:2]
        return pred[:, 1].copy(), J[:, 1, :3].copy()
    return fn


def swap_env(env, s_fn):
    e = dict(env); m = SwapS(env["model"], s_fn); e["model"] = m
    if "native" in e: e["native"] = (e["core"], e["online"], m, e["spec"])
    return e


def label_es(s_full, x, y, psi_rad, s_fn, case, chunk=512):
    """reference-model residual at station poses (bias state 0)."""
    out = np.empty(len(s_full))
    for k in range(0, len(s_full), chunk):
        st = np.c_[x[k:k + chunk], y[k:k + chunk], psi_rad[k:k + chunk], np.zeros(len(x[k:k + chunk]))]
        out[k:k + chunk] = s_full[k:k + chunk] - s_fn(st, case)[0]
    return out
