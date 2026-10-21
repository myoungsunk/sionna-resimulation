"""Pure math for M1-M3 replay: gate with packet R, update with R_eff, bias-gain scaling."""
from __future__ import annotations
import numpy as np
from scipy.stats import chi2

G2 = float(chi2.ppf(.99, 2))
C1 = float(chi2.ppf(.95, 1))


def wrap(a):
    return (np.asarray(a) + np.pi) % (2 * np.pi) - np.pi


def update(x, P, z, h, H, mu, Rp, Re, kappa):
    """x (J,4), P (J,4,4), z (2,), h (J,2), H (J,2,4), mu (J,2), Rp/Re (J,2,2), kappa (J,)."""
    v = z[None] - h - mu
    HP = H @ P
    HPHt = HP @ np.swapaxes(H, -1, -2)
    Sg = HPHt + Rp; Sg = .5 * (Sg + np.swapaxes(Sg, -1, -2))
    nis = np.einsum('ni,ni->n', v, np.linalg.solve(Sg, v[..., None])[..., 0])
    yes = nis <= G2
    Se = HPHt + Re; Se = .5 * (Se + np.swapaxes(Se, -1, -2))
    K = np.swapaxes(np.linalg.solve(Se, HP), -1, -2)
    K[:, 3, 1] *= kappa
    cand = x + np.einsum('nij,nj->ni', K, v); cand[:, 2] = wrap(cand[:, 2])
    A = np.eye(4)[None] - K @ H
    C = A @ P @ np.swapaxes(A, -1, -2) + K @ Re @ np.swapaxes(K, -1, -2); C = .5 * (C + np.swapaxes(C, -1, -2))
    return np.where(yes[:, None], cand, x), np.where(yes[:, None, None], C, P), nis, yes, K


def score(X, C, t, truth, b_true):
    e = X[:, :, :3] - truth[:, None, :]; e[:, :, 2] = wrap(e[:, :, 2]); m = t >= 30
    h = e[m, :, 2]; s = C[m, :, 2, 2]; b = X[m, :, 3] - b_true
    out = []
    for j in range(X.shape[1]):
        out.append({'heading_rmse_deg': float(np.degrees(np.sqrt(np.mean(h[:, j] ** 2)))),
                    'heading_signed_bias_deg': float(np.degrees(h[:, j].mean())),
                    'heading95': float(np.mean(h[:, j] ** 2 / s[:, j] <= C1)),
                    'heading_nees': float(np.mean(h[:, j] ** 2 / s[:, j])),
                    'heading_sigma_deg_mean': float(np.degrees(np.sqrt(s[:, j])).mean()),
                    'xy_rmse_m': float(np.sqrt(np.mean(np.sum(e[m, j, :2] ** 2, axis=1)))),
                    'bias_rmse_dps': float(np.degrees(np.sqrt(np.mean(b[:, j] ** 2))))})
    return out


def lf(x, w):
    """Centred moving average with shrinking edges (same convention as D1)."""
    import pandas as pd
    return pd.Series(np.asarray(x, float)).rolling(w, center=True, min_periods=1).mean().to_numpy()
