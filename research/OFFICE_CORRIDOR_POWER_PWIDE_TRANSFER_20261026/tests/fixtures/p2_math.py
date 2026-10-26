# Verbatim functions from PJ_DS_GATED_20261021/strict_common.py
# Commit: 0686b23ceeefb696bc158b32b39f8077c564ef5d
import numpy as np
from types import SimpleNamespace
V=SimpleNamespace(MC=SimpleNamespace(wrap=lambda x:(np.asarray(x)+np.pi)%(2*np.pi)-np.pi))
G2=9.210340371976184; G1=6.6348966010212145; C1=3.841458820694124; C2=5.991464547107979
DEG=180/np.pi

def update(x, P, z, h, H, mu_u, mu_g, Rp, Re, ronly):
    """Per-arm EKF update. 2D: chi2_2(0.99) gate on (z-h-mu_g) with Rp, update with mu_u and Re (Joseph), identical to m_core.update.
    ronly: explicit range-only scalar update, chi2_1(0.99) gate on range innovation (mu_g) with Rp_rr."""
    J = len(x); xo = x.copy(); Po = P.copy(); nis = np.zeros(J); yes = np.zeros(J, bool)
    for j in range(J):
        if ronly[j]:
            Hr = H[j, 0:1, :]; hph = float(Hr @ P[j] @ Hr.T)
            vg = z[0] - h[j, 0] - mu_g[j, 0]; v = z[0] - h[j, 0] - mu_u[j, 0]
            nis[j] = vg * vg / (hph + Rp[j, 0, 0]); yes[j] = nis[j] <= G1
            if yes[j]:
                K = (P[j] @ Hr.T) / (hph + Re[j, 0, 0]); c = x[j] + K[:, 0] * v; c[2] = V.MC.wrap(c[2])
                A = np.eye(4) - K @ Hr; C = A @ P[j] @ A.T + Re[j, 0, 0] * (K @ K.T); xo[j] = c; Po[j] = .5 * (C + C.T)
        else:
            HP = H[j] @ P[j]; HPHt = HP @ H[j].T
            Sg = HPHt + Rp[j]; Sg = .5 * (Sg + Sg.T); vg = z - h[j] - mu_g[j]; v = z - h[j] - mu_u[j]
            nis[j] = float(vg @ np.linalg.solve(Sg, vg)); yes[j] = nis[j] <= G2
            if yes[j]:
                Se = HPHt + Re[j]; Se = .5 * (Se + Se.T); K = np.linalg.solve(Se, HP).T
                c = x[j] + K @ v; c[2] = V.MC.wrap(c[2]); A = np.eye(4) - K @ H[j]
                C = A @ P[j] @ A.T + K @ Re[j] @ K.T; xo[j] = c; Po[j] = .5 * (C + C.T)
    return xo, Po, nis, yes

def score_extra(X, C, t, truth, case):
    """Heading (1-D NEES, ref 1; 95% coverage) and position (2-D NEES, ref 2; 95% coverage) metrics, t>=30."""
    m = t >= 30; anc = np.asarray(case['anchor'], float); dz = anc[2] - float(case['robot_z_m'])
    dtrue = np.sqrt((truth[:, 0] - anc[0]) ** 2 + (truth[:, 1] - anc[1]) ** 2 + dz ** 2)
    uh = np.column_stack([truth[:, 0] - anc[0], truth[:, 1] - anc[1]]); uh /= np.linalg.norm(uh, axis=1, keepdims=True); ut = np.column_stack([-uh[:, 1], uh[:, 0]])
    out = []; ser = []
    for j in range(X.shape[1]):
        he = V.MC.wrap(X[:, j, 2] - truth[:, 2]); hs = C[:, j, 2, 2]; e = X[:, j, :2] - truth[:, :2]; Pxy = C[:, j, :2, :2]
        nx = np.einsum('ni,ni->n', e, np.linalg.solve(Pxy, e[..., None])[..., 0])
        dh = np.sqrt((X[:, j, 0] - anc[0]) ** 2 + (X[:, j, 1] - anc[1]) ** 2 + dz ** 2); rerr = dh - dtrue
        out.append({'heading_rmse_deg': float(np.sqrt(np.mean(he[m] ** 2)) * DEG), 'heading_mae_deg': float(np.mean(np.abs(he[m])) * DEG),
                    'heading_signed_bias_deg': float(np.mean(he[m]) * DEG), 'heading_nees_1d': float(np.mean(he[m] ** 2 / hs[m])),
                    'heading_cov95': float(np.mean(he[m] ** 2 / hs[m] <= C1)), 'heading_sigma_deg_mean': float(np.mean(np.sqrt(hs[m])) * DEG),
                    'anchor_range_rmse_cm': float(np.sqrt(np.mean(rerr[m] ** 2)) * 100), 'radial_rmse_cm': float(np.sqrt(np.mean(np.sum(e * uh, 1)[m] ** 2)) * 100),
                    'tangential_rmse_cm': float(np.sqrt(np.mean(np.sum(e * ut, 1)[m] ** 2)) * 100), 'xy_rmse_cm': float(np.sqrt(np.mean(np.sum(e ** 2, 1)[m])) * 100),
                    'xy_nees_2d': float(np.mean(nx[m])), 'xy_cov95': float(np.mean(nx[m] <= C2))})
        ser.append({'herr_deg': he * DEG, 'hsig_deg': np.sqrt(hs) * DEG, 'rerr_cm': rerr * 100, 'xy_nees': nx, 'xy_err_cm': np.sqrt(np.sum(e ** 2, 1)) * 100})
    return out, ser
