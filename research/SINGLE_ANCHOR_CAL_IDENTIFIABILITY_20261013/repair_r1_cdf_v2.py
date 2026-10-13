"""Direct adaptive marginal CDF integration for the existing DR target.

Bias is integrated analytically. No marginal-density interpolation is used.
QUADPACK errors are diagnostic estimates, not certified mathematical bounds.
"""
from __future__ import annotations

import warnings
import time
import numpy as np
from scipy.integrate import quad, IntegrationWarning
from scipy.optimize import brentq
from scipy.special import ndtr
from repair_r1_dr import DRReference


def _cuts(left, right):
    return sorted(set([left, right] + [x for x in (-10., -6., 0., 6., 10.) if left < x < right]))


class AdaptiveCDF:
    def __init__(self, target, bound, epsabs, epsrel, shift, timeout_seconds=1800.):
        self.target, self.bound = target, float(bound)
        self.epsabs, self.epsrel, self.shift = float(epsabs), float(epsrel), float(shift)
        if not all(np.isfinite([bound, epsabs, epsrel, shift])) or min(bound, epsabs, epsrel) <= 0:
            raise ValueError("finite shift and positive bound/tolerances required")
        if bound * target.std[1] >= 1 or bound * target.std[2] >= 2:
            raise ValueError("integration box crosses kinematic support")
        if not np.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("positive finite timeout required")
        self.timeout_seconds = float(timeout_seconds)
        self.deadline = time.monotonic()+self.timeout_seconds
        self.evaluations = 0
        self.records = []
        self.cache = {}

    def _factors(self, sf, eps):
        if time.monotonic() >= self.deadline:
            raise TimeoutError(f"adaptive CDF exceeded {self.timeout_seconds:g} seconds after {self.evaluations} evaluations")
        self.evaluations += 1
        return self.target.integrated(sf, eps)

    def _bias_cuts(self, sf, q, left, right):
        # Locate conditional-CDF transitions explicitly. Model mu is continuous
        # within this support; segmented bracketing finds its sign-changing roots.
        cuts = _cuts(left, right)
        scan = np.linspace(left, right, 33)
        vals = [self._factors(sf, e)[1] - q for e in scan]
        roots = []
        for a, b, fa, fb in zip(scan[:-1], scan[1:], vals[:-1], vals[1:]):
            if fa == 0:
                roots.append(float(a))
            elif fa * fb < 0:
                roots.append(brentq(lambda e: self._factors(sf, e)[1] - q, a, b, xtol=1e-11))
        # Add transition shoulders; quad otherwise can miss an extremely narrow
        # Gaussian-CDF change immediately beside a root placed at an endpoint.
        for root in roots:
            _, _, variance = self._factors(sf, root)
            step = 1e-4
            lo, hi = max(left, root-step), min(right, root+step)
            slope = (self._factors(sf, hi)[1]-self._factors(sf, lo)[1])/(hi-lo)
            width = np.sqrt(variance)/abs(slope) if slope else 0.
            cuts += [root] + [root + n*width for n in (-8., -2., 2., 8.) if left < root+n*width < right]
        return sorted(set(cuts))

    def mass(self, axis=None, q=None):
        key = (axis, q)
        if key in self.cache:
            return self.cache[key]
        bound = self.bound
        sf_right = min(bound, q) if axis == 1 else bound
        eps_right = min(bound, q) if axis == 2 else bound
        if sf_right <= -bound or eps_right <= -bound:
            return 0., 0.
        inner_errors = []
        outer_cuts = _cuts(-bound, sf_right)
        def outer(sf):
            cuts = self._bias_cuts(sf, q, -bound, eps_right) if axis == 0 else _cuts(-bound, eps_right)
            def integrand(eps):
                ll, mu, var = self._factors(sf, eps)
                value = np.exp(ll-.5*(sf*sf+eps*eps)-np.log(2*np.pi)-self.shift)
                return value*ndtr((q-mu)/np.sqrt(var)) if axis == 0 else value
            value, error = 0., 0.
            for a, b in zip(cuts[:-1], cuts[1:]):
                v, e = quad(integrand, a, b, epsabs=self.epsabs/max(1,len(cuts)-1), epsrel=self.epsrel, limit=150)
                value += v; error += e
            inner_errors.append(error)
            return value
        value, error = 0., 0.
        start = self.evaluations
        for a, b in zip(outer_cuts[:-1], outer_cuts[1:]):
            v, e = quad(outer, a, b, epsabs=self.epsabs/max(1,len(outer_cuts)-1), epsrel=self.epsrel, limit=150)
            value += v; error += e
        estimated = error + (sf_right+bound)*max(inner_errors, default=0.)
        self.records.append(dict(axis=axis, threshold=q, scaled_mass=float(value),
                                 estimated_absolute_error=float(estimated),
                                 outer_error=float(error), maximum_inner_error=float(max(inner_errors,default=0.)),
                                 evaluations=self.evaluations-start))
        self.cache[key] = float(value), float(estimated)
        return self.cache[key]


def run_case(public, cfg, bound=40., epsabs=1e-8, epsrel=1e-8, shift=0., old_quantiles=None, timeout_seconds=1800.):
    """Compute normalization and nine direct-CDF quantiles in physical units.

    shift is purely a log-density scaling constant (e.g. previous log evidence).
    old_quantiles may be passed for API compatibility; they do not determine
    the integration domain or the returned quantiles.
    """
    target = DRReference(public, cfg)
    start=time.monotonic()
    engine = AdaptiveCDF(target, bound, epsabs, epsrel, shift, timeout_seconds)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", IntegrationWarning)
        norm, norm_error = engine.mass()
        if not np.isfinite(norm) or norm <= 0:
            raise ValueError("nonpositive/nonfinite integrated evidence; choose a suitable numeric shift")
        quantiles, cdf_errors = [], []
        for axis in range(3):
            row, errors = [], []
            for probability in (.025, .5, .975):
                lower, upper = -float(bound), float(bound)
                if axis == 0:
                    for _ in range(12):
                        if engine.mass(axis, lower)[0]/norm <= probability <= engine.mass(axis, upper)[0]/norm:
                            break
                        lower *= 2; upper *= 2
                    else:
                        raise ValueError("unable to bracket bias quantile")
                root = brentq(lambda x: engine.mass(axis,x)[0]/norm-probability,
                              lower,upper,xtol=1e-8,rtol=1e-10)
                mass, error = engine.mass(axis, root)
                row.append(root)
                errors.append(error/norm + mass*norm_error/norm**2)
            quantiles.append(row); cdf_errors.append(errors)
    logz = float(np.log(norm)+shift)
    return dict(bound=float(bound), epsabs=float(epsabs), epsrel=float(epsrel),
                timeout_seconds=float(timeout_seconds), elapsed_seconds=time.monotonic()-start,
                numeric_log_shift=float(shift), log_normalization=logz,
                scaled_normalization=norm, normalization_error_estimate=norm_error,
                normalization_relative_error_estimate=norm_error/norm,
                parameter_order=["bg_rad_s","sf","eps"],quantile_probabilities=[.025,.5,.975],
                marginal_quantiles=(np.array(quantiles)*target.std[:,None]).tolist(),
                standardized_quantiles=quantiles, quantile_cdf_error_estimates=cdf_errors,
                evaluation_count=engine.evaluations, integration_records=engine.records,
                integration_warnings=list(dict.fromkeys(str(w.message) for w in caught)),
                marginal_cdf_method="nested adaptive integration; analytic conditional bias CDF; explicit transition splits",
                reference_status="REFERENCE_NOT_VALIDATED",
                limitations=["QUADPACK error estimates are not rigorous upper bounds",
                             "sign-changing conditional transition roots found on segmented scan; tangential roots or paired crossings within a scan cell may be missed",
                             "finite sf/eps box requires independent posterior tail verification",
                             "conditional measured-input DR model only"])
