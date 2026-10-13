"""Complete I2 S0 density contract for future joint kernels (no sampler)."""
import numpy as np


def full_log_density(target, parameter, latent):
    """Density w.r.t. d(rho) d(delta) d(whitened cal) d(latent).

    The legacy evaluate() is only the likelihood. It cannot be used alone
    for arbitrary joint parameter moves.
    """
    p, z = np.asarray(parameter, float), np.asarray(latent, float)
    if p.shape != (5,) or not np.all(np.isfinite(p)) or not np.all(np.isfinite(z)):
        return -np.inf
    ll = target.evaluate(p, z)
    if not np.isfinite(ll):
        return -np.inf
    lp = -.5 * (np.sum(p[2:]**2) + 3*np.log(2*np.pi))
    lp += -.5 * (np.sum(z**2) + z.size*np.log(2*np.pi))
    if target.table is not None:
        if not -np.pi <= p[1] < np.pi:
            return -np.inf
        lp += target.table.logpdf(p[0]) - np.log(2*np.pi)
    return float(ll + lp)


def log_rho_density(target, transformed, latent):
    """eta=log(rho); correct density includes Jacobian rho=exp(eta)."""
    if target.table is None:
        raise ValueError('log-rho coordinates require Range')
    q = np.asarray(transformed, float).copy()
    if q.shape != (5,) or not np.all(np.isfinite(q)):
        return -np.inf
    with np.errstate(over='ignore'):
        q[0] = np.exp(q[0])
    return full_log_density(target, q, latent) + float(transformed[0])


def mh_log_ratio(log_new, log_old, log_q_reverse=0., log_q_forward=0.):
    return log_new - log_old + log_q_reverse - log_q_forward
