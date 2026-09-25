"""
Reflection-window CP metrics (analysis option "B").

Why this module exists
----------------------
The pre-registered first-path metric `xpr_fp_db` cannot test the reflector
hypothesis for this measurement set: the reflected path arrives 1.49-3.61 ns
after the LoS, while the Hann mainlobe half-width at B = 500 MHz is 4.00 ns.
The reflection is therefore inside the LoS mainlobe in every case, and the
+/-2-bin first-path window contains no reflector information at all (verified:
0/31 cases have the reflection inside that window; sim xpr_fp spans only
2.03 dB across the whole set, i.e. it is just the antenna boresight XPR).

Time-gating cannot fix this -- at this bandwidth the two arrivals are not
separable. So the LoS is removed at the source by coherent subtraction of a
plate-absent reference, and the CP metrics are then evaluated in a window
centred on the geometrically predicted reflection delay.

Both the measured and the simulated pipeline call the SAME functions here, so
the two sides cannot drift apart in window placement or energy definition.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

C0 = 299_792_458.0
EPS = 1e-30


def predicted_excess_delay_s(distance_m: float, offset_m: float) -> float:
    """Extra path length of the plate bounce, relative to the LoS.

    TX at (0,0,h), RX at (d,0,h), plate plane at y = -r.
    Image of TX across the plane is (0,-2r,h), so the bounce length is
    sqrt(d^2 + (2r)^2) and the excess over the LoS is that minus d.
    """
    d = float(distance_m)
    r = float(offset_m)
    return (float(np.sqrt(d * d + 4.0 * r * r)) - d) / C0


def bounded(center: int, n: int, radius: int) -> np.ndarray:
    """Mirror of features._bounded so windows match the sim contract exactly."""
    center = int(max(0, min(n - 1, center)))
    return np.arange(max(0, center - radius), min(n, center + radius + 1), dtype=int)


def reflection_window(t: np.ndarray, t_los_s: float, excess_s: float,
                      radius: int = 2) -> tuple[np.ndarray, int]:
    """+/-`radius` bins centred on the predicted reflection arrival."""
    t = np.asarray(t, dtype=float).reshape(-1)
    idx = int(np.argmin(np.abs(t - (float(t_los_s) + float(excess_s)))))
    return bounded(idx, len(t), radius), idx


@dataclass
class ReflectionMetrics:
    xpr_db: float
    s3: float
    idx_window_center: int
    t_window_center_s: float
    # subtraction diagnostics
    residual_to_case_db: float
    peak_offset_ns: float          # residual peak minus LoS peak
    predicted_offset_ns: float     # geometric prediction
    peak_error_ns: float           # measured minus predicted
    e_same: float
    e_rev: float


def residual_cp_metrics(
    h_same_case: np.ndarray, h_rev_case: np.ndarray,
    h_same_ref: np.ndarray, h_rev_ref: np.ndarray,
    t: np.ndarray, idx_los: int,
    excess_s: float, radius: int = 2,
) -> ReflectionMetrics:
    """Coherently remove the plate-absent reference, then window the bounce.

    `idx_los` is the first-path index taken from the REFERENCE channel, which
    contains the LoS alone and so gives an unambiguous time origin.
    """
    t = np.asarray(t, dtype=float).reshape(-1)
    hs = np.asarray(h_same_case).reshape(-1) - np.asarray(h_same_ref).reshape(-1)
    hr = np.asarray(h_rev_case).reshape(-1) - np.asarray(h_rev_ref).reshape(-1)

    e_case = float(np.sum(np.abs(h_same_case) ** 2))
    e_res = float(np.sum(np.abs(hs) ** 2))

    w, idx_c = reflection_window(t, float(t[idx_los]), excess_s, radius)
    e_s = float(np.sum(np.abs(hs[w]) ** 2))
    e_r = float(np.sum(np.abs(hr[w]) ** 2))

    idx_peak = int(np.argmax(np.abs(hs) ** 2))
    peak_off_ns = float((t[idx_peak] - t[idx_los]) * 1e9)
    pred_off_ns = float(excess_s * 1e9)

    return ReflectionMetrics(
        xpr_db=float(10.0 * np.log10((e_s + EPS) / (e_r + EPS))),
        s3=float((e_s - e_r) / (e_s + e_r + EPS)),
        idx_window_center=idx_c,
        t_window_center_s=float(t[idx_c]),
        residual_to_case_db=float(10.0 * np.log10((e_res + EPS) / (e_case + EPS))),
        peak_offset_ns=peak_off_ns,
        predicted_offset_ns=pred_off_ns,
        peak_error_ns=peak_off_ns - pred_off_ns,
        e_same=e_s,
        e_rev=e_r,
    )
