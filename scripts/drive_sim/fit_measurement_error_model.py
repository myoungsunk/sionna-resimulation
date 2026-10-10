"""A24 §2.2/2.3: deterministic maximum-likelihood fit of the Markov-bias measurement-error model to a training residual series.

Model (scalar, per variable):  y_k = beta_k + w_k,  beta_{k+1} = phi beta_k + eta_k,  w ~ N(0, var_w),  Var(eta) = var_beta (1 - phi^2),
beta_0 ~ N(0, var_beta) (stationary), no separate mean (a persistent mean is carried by the slow state).  Kalman-filter likelihood on the
un-demeaned series; several segments (leave-one-case-out) are fitted jointly with the recursion restarted per segment.

Parameterisation (logit phi on [0.50, 0.999], log var_beta, log var_w on [1e-8, 1]); optimiser L-BFGS-B; start values
phi0 = lag-1 autocorrelation of the demeaned series, var_beta0 = 0.8 ms, var_w0 = 0.2 ms with ms = un-demeaned mean square.
The "-acf" variant fixes phi = argmin_phi sum_{l=1..10} (rho_l - phi^l)^2 (rho = sample ACF of the demeaned series) and fits the two variances.
F3 profile: g(d) = ms_bin / ms_all over the distance bins <5, 5-10, >10 m, knots at the mean theta_geo of each bin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

PHI_LO, PHI_HI = 0.50, 0.999
V_LO, V_HI = 1e-8, 1.0
LAGS = (1, 2, 5, 10, 25)


def acf(x, lags=LAGS):
    x = np.asarray(x, float) - np.mean(x)
    den = float((x * x).sum())
    return {str(l): float((x[l:] * x[:-l]).sum() / den) for l in lags}


def kalman_negloglik(segments, phi, var_b, var_w):
    """Negative log-likelihood of the AR(1)+white model on a list of 1-D segments (stationary start, zero mean)."""
    nll = 0.0
    for y in segments:
        m, P = 0.0, var_b
        for yk in y:
            S = P + var_w
            e = yk - m
            nll += 0.5 * (math.log(2.0 * math.pi * S) + e * e / S)
            K = P / S
            m, P = m + K * e, P - K * P
            m, P = phi * m, phi * phi * P + var_b * (1.0 - phi * phi)
    return nll


def _unpack(theta, fixed_phi=None):
    if fixed_phi is None:
        lp, lb, lw = theta
        phi = PHI_LO + (PHI_HI - PHI_LO) / (1.0 + math.exp(-lp))
    else:
        lb, lw = theta
        phi = fixed_phi
    return phi, math.exp(lb), math.exp(lw)


def fit(segments, fixed_phi=None):
    from scipy.optimize import minimize
    allv = np.concatenate(segments)
    ms = float((allv ** 2).mean())
    rho1 = float(np.mean([acf(s, (1,))["1"] for s in segments]))
    phi0 = min(max(rho1, PHI_LO + 1e-3), PHI_HI - 1e-3)
    lb0, lw0 = math.log(0.8 * ms), math.log(0.2 * ms)
    lp0 = math.log((phi0 - PHI_LO) / (PHI_HI - phi0))
    x0 = [lb0, lw0] if fixed_phi is not None else [lp0, lb0, lw0]
    bnds = [(math.log(V_LO), math.log(V_HI))] * 2
    if fixed_phi is None:
        bnds = [(-30.0, 30.0)] + bnds
    res = minimize(lambda th: kalman_negloglik(segments, *_unpack(th, fixed_phi)), x0, method="L-BFGS-B", bounds=bnds)
    phi, vb, vw = _unpack(res.x, fixed_phi)
    return dict(phi=phi, var_beta=vb, var_w=vw, neg_loglik=float(res.fun), n=int(allv.size), converged=bool(res.success), iterations=int(res.nit),
                start=dict(phi=phi0, var_beta=0.8 * ms, var_w=0.2 * ms), mean_square=ms, at_bound=bool(phi >= PHI_HI - 1e-6 or vb <= V_LO * 1.001 or vw <= V_LO * 1.001))


def phi_from_acf(segments, max_lag=10):
    rho = np.mean([[acf(s, (l,))[str(l)] for l in range(1, max_lag + 1)] for s in segments], axis=0)
    grid = np.linspace(PHI_LO, PHI_HI, 4991)
    cost = ((rho[None, :] - grid[:, None] ** np.arange(1, max_lag + 1)[None, :]) ** 2).sum(1)
    return float(grid[int(cost.argmin())])


def model_acf(phi, vb, vw, lags=LAGS):
    return {str(l): float(vb * phi ** l / (vb + vw)) for l in lags}


def describe(segments, fitres):
    return dict(fit=fitres, sample_acf=acf(np.concatenate([s - s.mean() for s in segments])) if len(segments) == 1 else {k: float(np.mean([acf(s)[k] for s in segments])) for k in map(str, LAGS)},
                model_acf=model_acf(fitres["phi"], fitres["var_beta"], fitres["var_w"]))


def distance_profile(d3, r, h=2.2):
    """g(d) for F3: mean-square residual per distance bin over the overall mean square; knots in theta_geo [deg]."""
    d3, r = np.asarray(d3, float), np.asarray(r, float)
    bins = np.searchsorted([5.0, 10.0], d3)
    ms_all = float((r ** 2).mean())
    knots, g = [], []
    for b in range(3):
        sel = bins == b
        if sel.sum() < 5:
            continue
        knots.append(float(np.degrees(np.arccos(np.clip(h / d3[sel], -1, 1))).mean()))
        g.append(float((r[sel] ** 2).mean() / ms_all))
    order = np.argsort(knots)
    return dict(theta_geo_knots_deg=[knots[i] for i in order], g=[g[i] for i in order], bin_counts=[int((bins == b).sum()) for b in range(3)])


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_segments(paths, exclude_s=30.0):
    segs = {"s": [], "r": []}
    prof = None
    for p in paths:
        with np.load(p) as z:
            keep = (z["t"] >= exclude_s) & np.isfinite(z["r_s"]) & np.isfinite(z["r_r"])
            segs["s"].append(np.asarray(z["r_s"][keep], float))
            segs["r"].append(np.asarray(z["r_r"][keep], float))
            if len(paths) == 1:
                prof = distance_profile(z["d3"][keep], z["r_s"][keep])
    return segs, prof


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--residual", type=Path, nargs="+", required=True, help="RESIDUAL_<case>_m<mount>.npz (r_s, r_r, d3, t); several = leave-one-case-out concatenation")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--exclude-s", type=float, default=30.0)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"refusing to overwrite {a.out}")
    segs, prof = load_segments(a.residual, a.exclude_s)
    out = dict(spec="A24 section 2.2/2.3", label=a.label, exclude_s=a.exclude_s, inputs={str(p): sha256(p) for p in a.residual},
               script_sha256=sha256(Path(__file__)), bounds=dict(phi=[PHI_LO, PHI_HI], variance=[V_LO, V_HI]))
    for key in ("s", "r"):
        primary = fit(segs[key])
        phi_a = phi_from_acf(segs[key])
        acf_var = fit(segs[key], fixed_phi=phi_a)
        out[key] = dict(primary=describe(segs[key], primary), acf_variant=describe(segs[key], acf_var))
    out["profile_s"] = prof
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k]["primary"]["fit"] for k in ("s", "r")}, indent=1))


if __name__ == "__main__":
    main()
