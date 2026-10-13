"""Independent DR posterior integration for the conditional measured-input model.

Gyro bias integrates analytically; scale and asymmetry use deterministic
Gauss-Legendre quadrature in prior-standardized coordinates. This establishes
neither the full physical generator likelihood nor absence of omitted modes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
from scipy.special import ndtr, logsumexp
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq
from numpy.polynomial.legendre import leggauss


class DRReference:
    def __init__(self, public, cfg):
        allowed = {"t_s", "dt_s", "ds_odom", "dtheta_gyro", "dtheta_odom", "range_m", "range_mask"}
        if set(public) != allowed:
            raise ValueError("exactly seven public observation keys required; no truth/pose")
        t = np.asarray(public["t_s"], float)
        if t.ndim != 1 or len(t) < 2 or not np.all(np.isfinite(t)) or np.any(np.diff(t) <= 0):
            raise ValueError("invalid acquisition times")
        arrays = []
        for k in ("dt_s", "ds_odom", "dtheta_gyro", "dtheta_odom"):
            a = np.asarray(public[k], float)
            if a.shape != t.shape or not np.all(np.isfinite(a)):
                raise ValueError(f"invalid {k}")
            arrays.append(a[1:])
        self.dt, self.d, self.g, self.o = arrays
        if not np.allclose(self.dt, np.diff(t), rtol=1e-10, atol=1e-12):
            raise ValueError("dt_s differs from timestamps")
        self.std = np.asarray(cfg["p0_std"], float)[3:]
        if self.std.shape != (3,) or np.any(self.std <= 0) or not np.all(np.isfinite(self.std)):
            raise ValueError("positive finite calibration prior scales required")
        self.b = float(cfg["wheel_base"])
        constants = np.array([cfg[k] for k in ("k_s", "k_theta", "k_stheta", "gyro_N_rad_sqrt_s")], float)
        if not np.isfinite(self.b) or self.b <= 0 or cfg.get("known_wheelbase_error", 0) != 0 or not np.all(np.isfinite(constants)) or np.any(constants < 0):
            raise ValueError("invalid wheelbase/noise model")
        ks, kt, kst, gn = constants
        self.qd = ks * abs(self.d)
        self.qg = gn**2 * self.dt
        self.qo = kt * abs(self.o) + kst * abs(self.d)

    def factors(self, sf, eps):
        den, level = 1 + sf, 1 - eps**2 / 4
        if den <= 0 or level <= 0:
            return None
        a = level * self.g / den + eps * self.d / self.b
        b = level * self.dt / den
        s = (eps / self.b)**2 * self.qd + (level / den)**2 * self.qg + self.qo
        if np.any(s <= 0) or not np.all(np.isfinite(s)):
            return None
        return self.o - a, b, s

    def direct_logdensity(self, z):
        """Normalized standard Gaussian calibration prior times DR likelihood."""
        z = np.asarray(z, float)
        if z.shape != (3,) or not np.all(np.isfinite(z)):
            return -np.inf
        bg, sf, eps = z * self.std
        f = self.factors(sf, eps)
        if f is None:
            return -np.inf
        y, b, s = f
        return float(-.5 * np.sum(np.log(2*np.pi*s) + (y+b*bg)**2/s)
                     -.5*(z@z + 3*np.log(2*np.pi)))

    def integrated(self, zsf, zeps):
        """Return log marginal likelihood and conditional standardized bg moments."""
        f = self.factors(zsf*self.std[1], zeps*self.std[2])
        if f is None:
            return -np.inf, 0., 0.
        y, b, s = f
        v = b*self.std[0]
        precision = 1 + np.sum(v*v/s)
        linear = np.sum(v*y/s)
        mu, var = -linear/precision, 1/precision
        # Evaluate at the conditional optimum to avoid cancellation in y'y-q²/P.
        residual = y+v*mu
        ll = -.5*(np.sum(np.log(2*np.pi*s)+residual**2/s)
                  +mu**2+np.log(precision))
        return float(ll), float(mu), float(var)


def _marginal_quantiles(nodes, density, left, right, endpoint_density):
    x = np.r_[left, nodes, right]
    y = np.r_[endpoint_density[0], density, endpoint_density[1]]
    interpolant = PchipInterpolator(x, y, extrapolate=False)
    primitive = interpolant.antiderivative()
    mass = float(primitive(right)-primitive(left))
    if mass <= 0 or not np.isfinite(mass):
        raise ValueError("marginal interpolation has zero/nonfinite mass")
    quantiles = [brentq(lambda v: (primitive(v)-primitive(left))/mass-p,
                         left, right, xtol=1e-12) for p in (.025, .5, .975)]
    return quantiles, mass


def run_case(public, cfg, order=192, bound=8.):
    """Serializable deterministic posterior summary; no automatic reference approval."""
    if int(order) != order or order < 8 or not np.isfinite(bound) or bound <= 0:
        raise ValueError("order >=8 and finite positive bound required")
    target = DRReference(public, cfg)
    gx, gw = leggauss(int(order)); nodes, weights = bound*gx, bound*gw
    logs = np.empty((order, order)); mus = np.empty_like(logs); variances = np.empty_like(logs)
    for i, sf in enumerate(nodes):
        for j, eps in enumerate(nodes):
            ll, mus[i,j], variances[i,j] = target.integrated(sf, eps)
            logs[i,j] = ll-.5*(sf*sf+eps*eps)-np.log(2*np.pi)
    log_weights = logs+np.log(weights)[:,None]+np.log(weights)[None,:]
    log_norm = float(logsumexp(log_weights))
    if not np.isfinite(log_norm):
        raise ValueError("zero/nonfinite evidence")
    w = np.exp(log_weights-log_norm)
    grid_sf, grid_eps = np.meshgrid(nodes, nodes, indexing="ij")
    conditional_means = np.stack([mus, grid_sf, grid_eps], axis=-1)
    mean_z = np.sum(w[...,None]*conditional_means, axis=(0,1))
    centered = conditional_means-mean_z
    cov_z = np.einsum("ij,ija,ijb->ab",w,centered,centered)
    cov_z[0,0] += np.sum(w*variances)
    active = w>0
    bg_mu, bg_sd, bg_w = mus[active], np.sqrt(variances[active]), w[active]
    lower = float(np.min(bg_mu-12*bg_sd)); upper = float(np.max(bg_mu+12*bg_sd))
    quant_bg = [brentq(lambda x: np.sum(bg_w*ndtr((x-bg_mu)/bg_sd))-p, lower, upper,
                       xtol=1e-12) for p in (.025,.5,.975)]
    shift = float(np.max(logs))
    density = np.exp(logs-shift)
    quantiles = [quant_bg]; interpolation_relative = []
    for axis in (0,1):
        marginal = density@weights if axis == 0 else weights@density
        edges = []
        for edge in (-bound,bound):
            edge_logs = []
            for other in nodes:
                sf, eps = (edge,other) if axis == 0 else (other,edge)
                ll, _, _ = target.integrated(sf,eps)
                edge_logs.append(ll-.5*(sf*sf+eps*eps)-np.log(2*np.pi)-shift)
            edges.append(float(weights@np.exp(edge_logs)))
        q, interpolated_mass = _marginal_quantiles(nodes,marginal,-bound,bound,edges)
        quantiles.append(q)
        interpolation_relative.append(float(abs(interpolated_mass/(weights@marginal)-1)))
    mean = mean_z*target.std; covariance = cov_z*np.outer(target.std,target.std)
    # sf>-1 and |eps|<2 are the same model support restriction as existing target.
    raw_sf_low = -1/target.std[1]; raw_eps = 2/target.std[2]
    ttail = float(ndtr(-bound))
    omitted_prior = 4*ttail-4*ttail**2
    log_likelihood_upper = float(-.5*np.sum(np.log(2*np.pi*target.qo))) if np.all(target.qo>0) else None
    log_tail_ratio = np.log(omitted_prior)+log_likelihood_upper-log_norm if log_likelihood_upper is not None and omitted_prior>0 else None
    tail_upper = float(np.exp(min(0.,log_tail_ratio))) if log_tail_ratio is not None else None
    return dict(order=int(order), bound=float(bound), parameter_order=["bg_rad_s","sf","eps"],
                log_normalization=log_norm,
                normalization=float(np.exp(log_norm)) if log_norm < 700 else None,
                normalization_note="use log_normalization for underflow/overflow-safe comparison",
                mean=mean.tolist(), covariance=covariance.tolist(),
                sd=np.sqrt(np.diag(covariance)).tolist(),
                quantile_probabilities=[.025,.5,.975],
                marginal_quantiles=(np.asarray(quantiles)*target.std[:,None]).tolist(),
                marginal_cdf_method="bg Gaussian mixture analytic CDF; sf/eps integrated nonnegative PCHIP marginal density",
                cdf_interpolation_mass_relative_error=interpolation_relative,
                box_omitted_prior_mass=omitted_prior,
                posterior_omitted_tail_upper_bound=tail_upper,
                posterior_tail_log_ratio_bound=log_tail_ratio,
                likelihood_log_upper_bound=log_likelihood_upper,
                posterior_tail_bound_method="outside Gaussian prior mass times global likelihood upper bound / inside evidence; S>=qo; bound unavailable if any qo=0",
                invalid_model_prior_mass=float(1-(1-ndtr(raw_sf_low))*(2*ndtr(raw_eps)-1)),
                support_note="bg integrated over entire real line; sf/eps finite standardized box and positive kinematic support",
                reference_status="REFERENCE_NOT_VALIDATED",
                limitations=["prior tail bound is not a posterior tail bound; require domain/refinement agreement",
                             "PCHIP quantiles need refinement checks separate from moment quadrature",
                             "conditional measured-input model only; no Range kernel validation",
                             "finite-box refinement cannot prove absence of isolated tail modes"])


def compare_cases(first, second):
    """Predeclared numerical evidence, independent of scientific sufficiency."""
    sd = np.asarray(second["sd"])
    delta_logz = abs(first["log_normalization"]-second["log_normalization"])
    quantile_delta = abs(np.asarray(first["marginal_quantiles"])-np.asarray(second["marginal_quantiles"]))
    qdiff = np.max(quantile_delta/sd[:,None], axis=1)
    mean_diff = abs(np.asarray(first["mean"])-second["mean"])/sd
    cov_a, cov_b = np.asarray(first["covariance"]),np.asarray(second["covariance"])
    cov_error = float(np.linalg.norm(cov_a-cov_b)/np.linalg.norm(cov_b))
    rel_z = float(np.expm1(min(delta_logz,700)))
    return dict(normalization_relative_difference=rel_z,
                mean_difference_sd=mean_diff.tolist(),quantile_difference_sd=qdiff.tolist(),
                covariance_relative_frobenius_difference=cov_error,
                numerical_pass=bool(rel_z<=1e-6 and np.max(qdiff)<=.01))


def main():
    p=argparse.ArgumentParser();p.add_argument("--public",required=True);p.add_argument("--config",required=True)
    p.add_argument("--output",required=True);p.add_argument("--order",type=int,default=192);p.add_argument("--bound",type=float,default=8.)
    a=p.parse_args()
    with np.load(a.public,allow_pickle=False) as data: public={k:data[k] for k in data.files}
    cfg=json.loads(Path(a.config).read_text(encoding="utf-8-sig"))
    result=run_case(public,cfg,a.order,a.bound)
    Path(a.output).write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")


if __name__=="__main__": main()
