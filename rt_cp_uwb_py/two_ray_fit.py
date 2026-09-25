"""
Constrained two-ray fit in the frequency domain (analysis option "B-prime").

Why not a time gate
-------------------
At B = 500 MHz the Hann mainlobe half-width is 4.00 ns while the plate bounce
arrives only 1.49-3.61 ns after the LoS, so the two arrivals are inside one
mainlobe in 46/46 cases and no time window can separate them.

Why not reference subtraction
-----------------------------
Coherent removal of the plate-absent LoS_reference was tested and failed:
corr(predicted delay, residual peak delay) = -0.388, negative in every subset.
Cause is measured, not guessed -- 0724 kept a single face-to-face reference per
block while the cases pointed the antennas to theta_tx 40-75 deg, so the
reference direct path does not match the case direct path and subtracting it
INJECTS energy (median +7.6 dB, up to +16.4 dB) instead of cancelling.

What this module does instead
-----------------------------
Model the channel as exactly two rays and fix both delays from geometry:

    H(f) = A_los * exp(-j2*pi*f*tau0) + A_refl * exp(-j2*pi*f*(tau0 + tau_exc))

`tau_exc` comes from image theory on d and r and is NEVER fitted. Only the two
complex amplitudes are free (4 real unknowns against 257 complex samples), so
the system is heavily overdetermined. The single unknown timing term `tau0` --
cable plus system delay, common to both rays -- is found by a 1-D search that
minimises fit residual.

Conditioning is not assumed either: the two basis columns have normalised
coherence |sinc(tau_exc * B)|, which is 0.30 at the smallest delay in this set
and falls further as the delay grows, so the two amplitudes are separable. The
fit reports that coherence per case so a marginal geometry cannot hide.

The polarisation metrics are then read off A_refl alone, which carries the
plate contribution with the direct path already accounted for by A_los.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np

C0 = 299_792_458.0
EPS = 1e-30


def predicted_excess_delay_s(distance_m: float, offset_m: float) -> float:
    """Bounce path minus LoS path, from image theory. Never fitted."""
    d, r = float(distance_m), float(offset_m)
    return (float(np.sqrt(d * d + 4.0 * r * r)) - d) / C0


def _basis(freqs: np.ndarray, tau0: float, tau_exc: float) -> np.ndarray:
    ph = -2j * np.pi * freqs
    return np.stack([np.exp(ph * tau0), np.exp(ph * (tau0 + tau_exc))], axis=1)


def basis_coherence(freqs: np.ndarray, tau_exc: float) -> float:
    """|<m0,m1>| / (|m0||m1|). Near 1 means the two rays are inseparable."""
    m = _basis(np.asarray(freqs, float), 0.0, float(tau_exc))
    num = abs(np.vdot(m[:, 0], m[:, 1]))
    den = np.linalg.norm(m[:, 0]) * np.linalg.norm(m[:, 1])
    return float(num / (den + EPS))


@dataclass
class TwoRayFit:
    a_los_same: complex
    a_refl_same: complex
    a_los_rev: complex
    a_refl_rev: complex
    tau0_s: float
    tau_exc_s: float
    resid_frac_same: float      # ||y - Ma||^2 / ||y||^2
    resid_frac_rev: float
    coherence: float
    xpr_refl_db: float
    s3_refl: float
    xpr_los_db: float           # sanity: the direct-path XPR, ~ antenna boresight
    refl_to_los_db: float       # bounce strength relative to direct

    def as_row(self) -> dict:
        d = asdict(self)
        for k in ("a_los_same", "a_refl_same", "a_los_rev", "a_refl_rev"):
            v = d.pop(k)
            d[k + "_mag"] = float(abs(v))
            d[k + "_phase_rad"] = float(np.angle(v))
        return d


def _solve(freqs: np.ndarray, y: np.ndarray, tau0: float, tau_exc: float):
    m = _basis(freqs, tau0, tau_exc)
    a, *_ = np.linalg.lstsq(m, y, rcond=None)
    resid = y - m @ a
    return a, float(np.sum(np.abs(resid) ** 2))


def los_anchor_guess(h: np.ndarray, t: np.ndarray) -> float:
    """Time anchor for the direct ray: the CIR peak.

    NOT the leading edge. `extract_first_path(..., 'leading_edge')` fires on the
    rising flank of the Hann-broadened pulse and lands ~2 ns early -- larger
    than tau_exc itself. Anchoring there pushes the true LoS delay outside the
    search range, and the fit then satisfies the data by putting the SECOND
    basis vector on the direct path, so A_refl silently absorbs the LoS. That
    produced refl/los ratios of +17 to +41 dB (a bounce stronger than the
    direct path) before this was corrected.
    """
    h = np.asarray(h).reshape(-1)
    return float(np.asarray(t, dtype=float).reshape(-1)[int(np.argmax(np.abs(h) ** 2))])


def fit_two_ray(
    H_same: np.ndarray,
    H_rev: np.ndarray,
    freqs: np.ndarray,
    tau_exc_s: float,
    tau0_guess_s: float,
    search_halfwidth_s: float | None = None,
    n_search: int = 401,
) -> TwoRayFit:
    """Fit both polarisation channels sharing one system delay `tau0`.

    `tau0` is scanned; `tau_exc_s` is held at its geometric value throughout.
    Residuals of the two channels are summed, which weights the search by
    energy and so lets the high-SNR co-pol channel set the timing.

    The scan half-width defaults to 0.45 * tau_exc, deliberately under half the
    ray separation: the second basis vector then cannot reach the direct path
    for any tau0 in range, which removes the label-swap degeneracy by
    construction rather than by hoping the optimiser picks the right branch.
    """
    if search_halfwidth_s is None:
        search_halfwidth_s = 0.45 * float(tau_exc_s)
    f = np.asarray(freqs, dtype=float).reshape(-1)
    ys = np.asarray(H_same, dtype=complex).reshape(-1)
    yr = np.asarray(H_rev, dtype=complex).reshape(-1)

    grid = np.linspace(tau0_guess_s - search_halfwidth_s,
                       tau0_guess_s + search_halfwidth_s, int(n_search))
    best_tau, best_cost = float(grid[0]), np.inf
    for tau0 in grid:
        _, cs = _solve(f, ys, float(tau0), tau_exc_s)
        _, cr = _solve(f, yr, float(tau0), tau_exc_s)
        if cs + cr < best_cost:
            best_cost, best_tau = cs + cr, float(tau0)

    a_s, cost_s = _solve(f, ys, best_tau, tau_exc_s)
    a_r, cost_r = _solve(f, yr, best_tau, tau_exc_s)

    e_refl_s = float(abs(a_s[1]) ** 2)
    e_refl_r = float(abs(a_r[1]) ** 2)
    e_los_s = float(abs(a_s[0]) ** 2)
    e_los_r = float(abs(a_r[0]) ** 2)

    return TwoRayFit(
        a_los_same=complex(a_s[0]), a_refl_same=complex(a_s[1]),
        a_los_rev=complex(a_r[0]), a_refl_rev=complex(a_r[1]),
        tau0_s=best_tau, tau_exc_s=float(tau_exc_s),
        resid_frac_same=float(cost_s / (np.sum(np.abs(ys) ** 2) + EPS)),
        resid_frac_rev=float(cost_r / (np.sum(np.abs(yr) ** 2) + EPS)),
        coherence=basis_coherence(f, tau_exc_s),
        xpr_refl_db=float(10.0 * np.log10((e_refl_s + EPS) / (e_refl_r + EPS))),
        s3_refl=float((e_refl_s - e_refl_r) / (e_refl_s + e_refl_r + EPS)),
        xpr_los_db=float(10.0 * np.log10((e_los_s + EPS) / (e_los_r + EPS))),
        refl_to_los_db=float(10.0 * np.log10((e_refl_s + EPS) / (e_los_s + EPS))),
    )
