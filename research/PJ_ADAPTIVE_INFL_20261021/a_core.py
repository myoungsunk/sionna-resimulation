"""Causal innovation-whiteness estimator for adaptive COMMON inflation."""
from __future__ import annotations
from collections import deque
import numpy as np

W, L, ALPHA = 150, 50, 0.02
BARTLETT = 1.0 - np.arange(1, L + 1) / (L + 1)


class InnovACF:
    """Buffer of whitened innovations (accepted packets only)."""

    def __init__(self, w=W, lag=L):
        self.buf = deque(maxlen=w); self.L = lag

    def push(self, vt):
        self.buf.append(np.atleast_1d(np.asarray(vt, float)))

    def eta_raw(self):
        n = len(self.buf)
        if n < self.L + 10:
            return np.nan
        X = np.asarray(self.buf)
        den = float(np.sum(X * X)) / n
        if den <= 0:
            return np.nan
        rho = np.array([float(np.sum(X[t:] * X[:-t])) / (n - t) for t in range(1, self.L + 1)]) / den
        return 1.0 + 2.0 * float(BARTLETT[:self.L] @ rho)


def whiten(v, S):
    """Full 2-D whitening (rs) and scalar s whitening."""
    Lc = np.linalg.cholesky(S)
    rs = np.linalg.solve(Lc, v[..., None])[..., 0]
    s = v[..., 1] / np.sqrt(S[..., 1, 1])
    return rs, s


def step_eta(eta, raw, eta_max, alpha=ALPHA):
    if not np.isfinite(raw):
        return eta
    return float(np.clip(eta + alpha * (raw - eta), 1.0, eta_max))
