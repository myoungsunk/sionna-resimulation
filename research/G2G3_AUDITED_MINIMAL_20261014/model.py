"""Minimum mathematical model, NOT a validated full-pose G2/G3 estimator.

Inputs are observable DR summary/RF Range only. No truth or injected bias label.
Fault spread and RF component parameters are synthetic assumptions in CONTRACT.
Physical support: slant range r >= lower_slant_m. Range is used exactly once.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.special import log_ndtr, logsumexp


def norm_logpdf(x, mean, var):
    return -0.5 * (np.log(2.0 * np.pi * var) + (x-mean)**2 / var)


def infer(mu, sigma, observed, config):
    mu, sigma, observed = np.broadcast_arrays(
        np.asarray(mu, float), np.asarray(sigma, float), np.asarray(observed, float))
    if not (np.isfinite(mu).all() and np.isfinite(sigma).all() and
            np.isfinite(observed).all() and np.all(sigma > 0)):
        raise ValueError('HARD_EXECUTION_BLOCK: invalid input/units/std')
    p_fault = float(config['fault_prior_probability'])
    if not 0 < p_fault < 1:
        raise ValueError('HARD_EXECUTION_BLOCK: invalid prior weight')
    components = config['rf_components']
    if not np.isclose(sum(c['weight'] for c in components), 1.0, atol=1e-12):
        raise ValueError('HARD_EXECUTION_BLOCK: RF mixture weights do not normalize')
    lo = float(config['lower_slant_m'])
    logmass, means, variances, fi, ri, labels = [], [], [], [], [], []
    for fault, pd in ((False, 1.0-p_fault), (True, p_fault)):
        # Fault spread is additive independent variance, not replacement of P.
        vd = sigma**2 + (float(config['fault_radial_std_m'])**2 if fault else 0.0)
        logtd = log_ndtr((mu-lo)/np.sqrt(vd))
        for rf in components:
            vr = float(rf['std_m'])**2
            wr = float(rf['weight'])
            if vr <= 0 or wr <= 0:
                raise ValueError('HARD_EXECUTION_BLOCK: invalid RF component')
            zr = observed-float(rf['bias_m'])
            v = vd*vr/(vd+vr)
            m = (vr*mu+vd*zr)/(vd+vr)
            s = np.sqrt(v)
            a = (lo-m)/s
            logtp = log_ndtr(-a)
            lam = np.exp(-0.5*a*a-0.5*np.log(2*np.pi)-logtp)
            mt = m+s*lam
            vt = v*(1.0+a*lam-lam*lam)
            if np.any(vt < -1e-10) or not np.isfinite(vt).all():
                raise FloatingPointError('CASE_RESULT_INVALID: truncated covariance')
            vt = np.maximum(vt, 0.0)
            ev = norm_logpdf(observed, mu+float(rf['bias_m']), vd+vr) + logtp-logtd
            logmass.append(np.log(pd)+np.log(wr)+ev)
            means.append(mt)
            variances.append(vt)
            fi.append(fault and bool(rf['inlier']))
            ri.append(bool(rf['inlier']))
            labels.append(('fault/' if fault else 'normal/')+rf['name'])
    lm = np.stack(logmass, axis=-1)
    logz = logsumexp(lm, axis=-1)
    weights = np.exp(lm-logz[..., None])
    cm = np.stack(means, axis=-1)
    cv = np.stack(variances, axis=-1)
    avg = np.sum(weights*cm, axis=-1)
    var = np.sum(weights*(cv+(cm-avg[..., None])**2), axis=-1)
    pfi = np.sum(weights[..., np.asarray(fi, bool)], axis=-1)
    pri = np.sum(weights[..., np.asarray(ri, bool)], axis=-1)
    if not np.isfinite(avg).all() or np.any(var < 0):
        raise FloatingPointError('CASE_RESULT_INVALID: mixture moments')
    return dict(mean=avg, variance=var, weights=weights,
                component_means=cm, component_variances=cv,
                p_dr_fault_rf_inlier=pfi, p_rf_inlier=pri,
                log_evidence=logz, labels=labels)


def linear_joint(mu, P, H, z, R):
    """Information-form joint update, independent of sequential gain path."""
    mu, P, H, z, R = map(lambda v: np.asarray(v, float), (mu, P, H, z, R))
    invp = np.linalg.solve(P, np.eye(len(mu)))
    invr = np.linalg.solve(R, np.eye(len(z)))
    post_precision = invp + H.T @ invr @ H
    cov = np.linalg.solve(post_precision, np.eye(len(mu)))
    mean = np.linalg.solve(post_precision, invp@mu+H.T@invr@z)
    S = H@P@H.T+R
    residual = z-H@mu
    sign, ld = np.linalg.slogdet(S)
    if sign <= 0:
        raise ValueError('HARD_EXECUTION_BLOCK: non-PD innovation covariance')
    ev = -0.5*(len(z)*np.log(2*np.pi)+ld+residual@np.linalg.solve(S, residual))
    return mean, 0.5*(cov+cov.T), float(ev)


def scalar_joseph(mu, P, h, z, var):
    residual = float(z-h@mu)
    S = float(h@P@h+var)
    K = P@h/S
    mean = mu+K*residual
    A = np.eye(len(mu))-np.outer(K,h)
    cov = A@P@A.T+np.outer(K,K)*var
    return mean, 0.5*(cov+cov.T), float(norm_logpdf(residual, 0.0, S))


def linear_sequential(mu, P, H, z, R):
    """Range first, then conditional S. Correlated noise is decorrelated once."""
    mu, P, H, z, R = map(lambda v: np.asarray(v, float), (mu, P, H, z, R))
    mr, Pr, logzr = scalar_joseph(mu, P, H[0], z[0], R[0,0])
    alpha = R[1,0]/R[0,0]
    hs = H[1]-alpha*H[0]
    zs = z[1]-alpha*z[0]
    vs = R[1,1]-R[1,0]**2/R[0,0]
    if vs <= 0:
        raise ValueError('HARD_EXECUTION_BLOCK: conditional observation variance')
    m, C, logzs = scalar_joseph(mr, Pr, hs, zs, vs)
    return m, C, logzr+logzs
