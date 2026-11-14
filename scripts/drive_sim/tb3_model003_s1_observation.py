"""G1-MODEL-003 §S1 ranging and selected-tap polarization observations."""
from __future__ import annotations

import math

import numpy as np


C_M_S = 299792458.0
RULES = ("O30", "O20", "O10", "O30_M0P5", "O30_M1", "O30_SUBTAP")
LEADING_EDGE = {"O30": 0.3, "O20": 0.2, "O10": 0.1}


def channel_to_cir(h_clean, observation, *, noise_var=None, rng=None, tx=0):
    """Use the frozen Hann/4× IFFT and per-bin complex Gaussian noise.

    Form the CIR once per batch and SNR, then share it across all ranging rules.
    Channels have shape (packets, frequency bins, 2 Rx ports, Tx ports).
    """
    h = np.asarray(h_clean)
    if h.ndim != 4 or h.shape[1] < 2 or h.shape[2] != 2 or not 0 <= tx < h.shape[3]:
        raise ValueError("Expected a batched RF channel with both Rx ports and the selected Tx")
    h = h[..., tx]
    if noise_var is not None and (not math.isfinite(noise_var) or noise_var < 0):
        raise ValueError("Complex noise variance must be finite and nonnegative")
    if noise_var:
        if rng is None:
            raise ValueError("Noisy observations need an explicit random generator")
        sigma = math.sqrt(noise_var / 2.0)
        h = h + sigma * (rng.standard_normal(h.shape) + 1j * rng.standard_normal(h.shape))
    return observation.cir_batch(h)


def range_candidates(cir, df_hz, *, threshold=0.0, rules=RULES):
    """Return tap, range and detection for each rule using only the CIR envelope.

    Index is the integer leading-edge crossing and tap is the corrected sample
    coordinate. Finite nonzero CIRs retain both coordinates below the detection
    threshold. Zero or nonfinite CIRs return index -1 and tap NaN.
    """
    cir = np.asarray(cir)
    if cir.ndim != 3 or cir.shape[1] < 2 or cir.shape[2] != 2:
        raise ValueError("Expected CIR shape (packets, taps, 2 Rx ports)")
    if not math.isfinite(df_hz) or df_hz <= 0 or not math.isfinite(threshold) or threshold < 0:
        raise ValueError("Invalid RF bin spacing or detection threshold")
    rules = tuple(rules)
    if len(set(rules)) != len(rules) or any(rule not in RULES for rule in rules):
        raise ValueError("Unknown or duplicate ranging rule")

    magnitude = np.abs(cir)
    finite = np.isfinite(magnitude).all(axis=(1, 2))
    magnitude[~finite] = 0.0
    branch = magnitude.max(axis=1).argmax(axis=1)
    strongest = np.take_along_axis(magnitude, branch[:, None, None], axis=2)[:, :, 0]
    peak = strongest.max(axis=1)
    valid = finite & (peak > 0)
    detected = valid & (peak >= threshold)
    crossings = {}
    result = {}
    for rule in rules:
        level = LEADING_EDGE.get(rule, 0.3)
        if level not in crossings:
            hits = strongest >= (level * peak)[:, None]
            crossings[level] = hits.argmax(axis=1)
        crossing = crossings[level]
        tap = crossing.astype(float)
        if rule == "O30_M0P5":
            tap = np.maximum(tap - 0.5, 0.0)
        elif rule == "O30_M1":
            tap = np.maximum(tap - 1.0, 0.0)
        elif rule == "O30_SUBTAP":
            rows = np.arange(len(cir))
            prior = np.maximum(crossing - 1, 0)
            below, above = strongest[rows, prior], strongest[rows, crossing]
            # At tap 0 the bracket is outside the sampled time axis.
            offset = np.divide(level * peak - below, above - below, out=np.zeros(len(cir)),
                               where=crossing > 0)
            tap = prior + offset
        delay = np.where(detected, tap / (cir.shape[1] * df_hz), np.nan)
        result[rule] = dict(tap=np.where(valid, tap, np.nan), index=np.where(valid, crossing, -1),
                            delay_s=delay, range_m=delay * C_M_S, detected=detected.copy(),
                            peak=np.where(finite, peak, np.nan))
    return result


def signed_s_at_tap(cir, tap, detected=None):
    """Read the chosen tap on both Rx ports and interpolate complex CIRs before power."""
    cir = np.asarray(cir, dtype=complex)
    tap = np.asarray(tap, dtype=float)
    if cir.ndim != 3 or cir.shape[1] < 2 or cir.shape[2] != 2 or tap.shape != (len(cir),):
        raise ValueError("Inconsistent CIR and tap shapes")
    if detected is None:
        detected = np.isfinite(tap)
    else:
        detected = np.asarray(detected, dtype=bool)
    if detected.shape != tap.shape:
        raise ValueError("Inconsistent tap and detection shapes")
    result = np.full(len(tap), np.nan)
    chosen = tap[detected]
    if not np.isfinite(chosen).all() or np.any(chosen < 0) or np.any(chosen > cir.shape[1] - 1):
        raise ValueError("Detected taps must be within the sampled CIR")

    rows = np.flatnonzero(detected)
    left = chosen.astype(np.int64)
    right = np.minimum(left + 1, cir.shape[1] - 1)
    amplitude = cir[rows, left, :].copy()
    fractional = chosen != left
    weight = (chosen[fractional] - left[fractional])[:, None]
    amplitude[fractional] = ((1.0 - weight) * amplitude[fractional]
                             + weight * cir[rows[fractional], right[fractional], :])
    power = np.abs(amplitude) ** 2
    total = power.sum(axis=1)
    result[rows] = np.divide(power[:, 0] - power[:, 1], total, out=np.full(len(rows), np.nan),
                             where=np.isfinite(total) & (total > 0))
    return result


def self_check(observation):
    """Check hand-calculated crossings, invalid inputs and the frozen O30 chain."""
    cir = np.zeros((4, 5, 2), dtype=complex)
    cir[0, :, 0] = [0.1, 0.15, 0.25, 0.5j, 1.0]
    cir[0, 2:4, 1] = [0.1j, 0.15]
    cir[2, 0, 1] = 0.01
    cir[3, 2, 0] = np.nan
    result = range_candidates(cir, 2e6, threshold=0.1)
    np.testing.assert_allclose([result[rule]["tap"][0] for rule in RULES], [3, 2, 0, 2.5, 2, 2.2],
                               rtol=0, atol=1e-15)
    selected = result["O30_SUBTAP"]
    np.testing.assert_array_equal(selected["detected"], [True, False, False, False])
    np.testing.assert_array_equal(selected["index"], [3, -1, 0, -1])
    np.testing.assert_array_equal(selected["tap"], [2.2, np.nan, 0, np.nan])
    np.testing.assert_allclose(selected["range_m"], [2.2 * C_M_S / 1e7, np.nan, np.nan, np.nan])
    np.testing.assert_allclose(signed_s_at_tap(cir, selected["tap"], selected["detected"]),
                               [(0.05 - 0.0073) / (0.05 + 0.0073), np.nan, np.nan, np.nan])

    rng = np.random.default_rng(772946)
    shape = (3, 257, 2, 2)
    channel = rng.normal(size=shape) + 1j * rng.normal(size=shape)
    frequencies = 6.25e9 + np.arange(shape[1]) * 1.95e6
    np.testing.assert_raises(ValueError, channel_to_cir, channel, observation, noise_var=-1.0)
    np.testing.assert_raises(ValueError, channel_to_cir, channel, observation, noise_var=np.nan)
    np.testing.assert_raises(ValueError, channel_to_cir, channel, observation, noise_var=1.0)
    for noise_var in (None, observation.noise_var_from_snr(20.0)):
        baseline = observation.observe(channel, frequencies, noise_var, np.random.default_rng(1973),
                                       return_h=True)
        observed = channel_to_cir(channel, observation, noise_var=noise_var, rng=np.random.default_rng(1973))
        np.testing.assert_array_equal(observed, observation.cir_batch(baseline["h_noisy"]))
        o30 = range_candidates(observed, frequencies[1] - frequencies[0], threshold=baseline["threshold"],
                               rules=("O30",))["O30"]
        for name in ("index", "delay_s", "range_m", "detected", "peak"):
            np.testing.assert_array_equal(o30[name], baseline[name])
        np.testing.assert_array_equal(signed_s_at_tap(observed, o30["tap"], o30["detected"]), baseline["s"])
