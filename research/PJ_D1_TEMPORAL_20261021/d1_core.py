"""D1 pure math: exact linear error decomposition, measurement-driven covariance,
surrogate propagation, ACF and coverage attribution. No I/O, no fitting."""
from __future__ import annotations
import numpy as np

CHI1_95 = 3.841458820694124
I4 = np.eye(4)


def wrap(a):
    return (np.asarray(a) + np.pi) % (2 * np.pi) - np.pi


def err(x, truth4):
    e = np.asarray(x) - truth4
    e[..., 2] = wrap(e[..., 2])
    return e


def decompose(F, K, H, a, w, u, em, ep, uf_lf):
    """Exact decomposition of posterior error ep (n,J,4).
    F (n,J,4,4) prediction Jacobian used from k-1 to k (F[0] unused)
    K (n,J,4,2), H (n,J,2,4), a (n,J) bool accepted, w (n,4) process residual,
    u (n,J,2) true measurement error minus model mean, em/ep prior/posterior error.
    uf_lf (n,J,2) low-frequency part of u.
    Returns dict of components (n,J,4) whose sum equals ep exactly, plus Aup, Ka."""
    n, J = a.shape
    Ka = np.where(a[..., None, None], K, 0.0)
    Aup = I4 - Ka @ H
    q = np.zeros((n, J, 4))
    for k in range(1, n):
        q[k] = em[k] - (np.einsum('jab,jb->ja', F[k], ep[k - 1]) - w[k][None])
    q[..., 2] = wrap(q[..., 2])
    ell = ep - (np.einsum('njab,njb->nja', Aup, em) + np.einsum('njab,njb->nja', Ka, u))
    ell[..., 2] = wrap(ell[..., 2])
    z = np.zeros((n, J, 4))
    uhf = u - uf_lf

    def inj_meas(x, ch):
        return Ka[..., :, ch] * x[..., ch][..., None]

    specs = {
        'INIT': (z, z, em[0]),
        'PROCESS': (-np.broadcast_to(w[:, None, :], (n, J, 4)), z, np.zeros((J, 4))),
        'LIN': (q, ell, np.zeros((J, 4))),
        'U_R_LF': (z, inj_meas(uf_lf, 0), np.zeros((J, 4))),
        'U_R_HF': (z, inj_meas(uhf, 0), np.zeros((J, 4))),
        'U_S_LF': (z, inj_meas(uf_lf, 1), np.zeros((J, 4))),
        'U_S_HF': (z, inj_meas(uhf, 1), np.zeros((J, 4))),
    }
    out = {}
    for name, (im, ip, init) in specs.items():
        c = np.empty((n, J, 4))
        prev = None
        for k in range(n):
            cm = init.copy() if k == 0 else np.einsum('jab,jb->ja', F[k], prev) + im[k]
            if k == 0:
                cm = cm + im[0]
            c[k] = np.einsum('jab,jb->ja', Aup[k], cm) + ip[k]
            prev = c[k]
        out[name] = c
    return out, Aup, Ka


def meas_cov(F, Aup, Ka, R):
    """Filter-believed covariance of the measurement-driven error part."""
    n, J = Aup.shape[:2]
    P = np.zeros((n, J, 4, 4))
    prev = np.zeros((J, 4, 4))
    for k in range(n):
        Pm = prev if k == 0 else F[k] @ prev @ np.swapaxes(F[k], -1, -2)
        Pk = Aup[k] @ Pm @ np.swapaxes(Aup[k], -1, -2) + Ka[k] @ R[k] @ np.swapaxes(Ka[k], -1, -2)
        P[k] = 0.5 * (Pk + np.swapaxes(Pk, -1, -2))
        prev = P[k]
    return P


def propagate_meas(F, Aup, Ka, U):
    """U (M,n,J,2) -> eps (M,n,J,4) measurement-driven error."""
    M, n, J = U.shape[:3]
    eps = np.empty((M, n, J, 4))
    prev = np.zeros((M, J, 4))
    for k in range(n):
        em = prev if k == 0 else np.einsum('jab,mjb->mja', F[k], prev)
        eps[:, k] = np.einsum('jab,mjb->mja', Aup[k], em) + np.einsum('jab,mjb->mja', Ka[k], U[:, k])
        prev = eps[:, k]
    return eps


def surrogates(ut, L, M, rng):
    """ut (n,J,2) whitened residual, L (n,J,2,2). Returns SHUFFLE, PHASE recoloured (M,n,J,2)."""
    n = ut.shape[0]
    perm = np.stack([rng.permutation(n) for _ in range(M)])
    sh = ut[perm]
    Fq = np.fft.rfft(ut, axis=0)
    nf = Fq.shape[0]
    ph = rng.uniform(0, 2 * np.pi, size=(M, nf))
    ph[:, 0] = 0.0
    if n % 2 == 0:
        ph[:, -1] = 0.0
    pr = np.fft.irfft(Fq[None] * np.exp(1j * ph)[:, :, None, None], n=n, axis=1)
    rec = lambda s: np.einsum('njab,mnjb->mnja', L, s)
    return rec(sh), rec(pr)


def acf_stats(x, dt, cutoff=0.05, max_s=30.0):
    """Non-centred normalised autocorrelation of 1-D series x (sampled at dt)."""
    x = np.asarray(x, float)
    n = len(x)
    m2 = float(np.mean(x * x))
    L = min(n - 1, int(round(max_s / dt)))
    r = np.array([np.mean(x[:n - k] * x[k:]) / m2 for k in range(L + 1)])
    xc = x - x.mean()
    lag1c = float(np.mean(xc[:-1] * xc[1:]) / np.mean(xc * xc))
    cut = np.argmax(r[1:] < cutoff) + 1 if np.any(r[1:] < cutoff) else L + 1
    tau = dt * (1 + 2 * float(np.sum(r[1:cut])))
    pick = {f'acf_{s:g}s': float(r[min(L, int(round(s / dt)))]) for s in (0.5, 1, 2, 5, 10)}
    return dict(mean=float(x.mean()), rms=float(np.sqrt(m2)), lag1_noncentred=float(r[1]),
                lag1_centred=lag1c, tau_int_s=tau, cutoff_lag_s=float(cut * dt), **pick)


def coverage(delta, sigma2):
    return float(np.mean(delta * delta / sigma2 <= CHI1_95))


def nees(delta, sigma2):
    return float(np.mean(delta * delta / sigma2))
