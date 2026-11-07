"""S3 observation chain for the single-port anchor: batched, noise-aware, numerically identical to the project chain.

Chain (same as ``qclean_uwb.features.fp_power.signed_s_single_tx``): Hann window, zero-pad to 4N taps, IFFT * N; the strongest of the
two RX branches of the selected TX column fixes the first-path tap (30 % leading edge); P1, P2 = |CIR[index, rx]|^2;
s = (P1 - P2) / (P1 + P2); range = delay * c.  Noise is added to H before the IFFT (complex Gaussian per bin and RX port).
"""
from __future__ import annotations

import math

import numpy as np

C0 = 299792458.0
LEADING_EDGE = 0.3


def hann(n: int) -> np.ndarray:
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n, dtype=float) / (n - 1))


def free_space_power(distance_m: float = 10.0, freq_hz: float = 6.5e9) -> float:
    """|H|^2 of a unit-gain free-space link (the SNR reference of the sweep)."""
    return (C0 / freq_hz / (4.0 * math.pi * distance_m)) ** 2


def noise_var_from_snr(snr_db: float, distance_m: float = 10.0, freq_hz: float = 6.5e9) -> float:
    """Per-bin complex noise variance such that a unit-gain free-space LoS link at ``distance_m`` has per-bin SNR ``snr_db``.

    Placeholder definition (assumption): the real co-pol gain of the FFD patterns is not included; report the realised SNR separately.
    """
    return free_space_power(distance_m, freq_hz) / 10.0 ** (snr_db / 10.0)


def detection_threshold(noise_var: float, n_branches: int = 2, n_taps: int = 1028, pfa: float = 1e-3) -> float:
    """Same union-bound rule as the production config (tap variance = 6 * noise_var): sqrt(6 var ln(N_tests / pfa))."""
    return math.sqrt(6.0 * noise_var * math.log(n_branches * n_taps / pfa))


def cir_batch(h_col: np.ndarray) -> np.ndarray:
    """h_col (B, n_bin, n_rx) -> CIR (B, 4*n_bin, n_rx)."""
    h = np.asarray(h_col, complex)
    n = h.shape[1]
    padded = np.zeros((h.shape[0], 4 * n, h.shape[2]), complex)
    padded[:, :n, :] = h * hann(n)[None, :, None]
    return np.fft.ifft(padded, axis=1) * n


def first_path_batch(cir: np.ndarray, df_hz: float) -> dict:
    """First-path index, delay, powers and signed s for a batch of CIRs (B, n_tap, 2)."""
    mag = np.abs(cir)
    peak_branch = mag.max(axis=1)                       # (B, rx)
    rx = peak_branch.argmax(axis=1)
    strongest = np.take_along_axis(mag, rx[:, None, None], axis=2)[:, :, 0]     # (B, n_tap)
    peak = strongest.max(axis=1)
    hits = strongest >= LEADING_EDGE * peak[:, None]
    index = hits.argmax(axis=1)
    power = np.abs(cir[np.arange(len(cir)), index, :]) ** 2                     # (B, 2)
    den = power.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(den > 0, (power[:, 0] - power[:, 1]) / den, np.nan)
    delay = index / (cir.shape[1] * df_hz)
    return dict(s=s, power=power, index=index, delay_s=delay, range_m=delay * C0, peak=peak)


def observe(h_clean: np.ndarray, freqs_hz: np.ndarray, noise_var: float | None, rng: np.random.Generator | None, tx: int = 0,
            threshold: float | None = None, return_h: bool = False) -> dict:
    """Observe a batch of clean channels h_clean (B, n_bin, n_rx, n_tx).  ``noise_var=None`` -> noise-free.

    Returns the first-path quantities plus ``detected`` (peak above the detection threshold); undetected samples have s = range = nan.
    """
    h = np.asarray(h_clean)[..., tx]
    if noise_var:
        sigma = math.sqrt(noise_var / 2.0)
        h = h + sigma * (rng.standard_normal(h.shape) + 1j * rng.standard_normal(h.shape))
    df = float(freqs_hz[1] - freqs_hz[0])
    out = first_path_batch(cir_batch(h), df)
    if threshold is None:
        threshold = detection_threshold(noise_var) if noise_var else 0.0
    out["detected"] = out["peak"] >= threshold
    for k in ("s", "range_m", "delay_s"):
        out[k] = np.where(out["detected"], out[k], np.nan)
    out["threshold"] = threshold
    if return_h:
        out["h_noisy"] = h
    return out


def realised_snr_db(h_clean: np.ndarray, noise_var: float, tx: int = 0) -> np.ndarray:
    """Per-sample mean per-bin SNR of the stronger RX port [dB] (diagnostic for the placeholder SNR definition)."""
    p = (np.abs(np.asarray(h_clean)[..., tx]) ** 2).mean(axis=1).max(axis=-1)
    return 10.0 * np.log10(p / noise_var)


def los_range_bias(freqs_hz: np.ndarray, d_min: float = 2.0, d_max: float = 16.0, step: float = 0.01) -> float:
    """Mean (chain range - true range) of a flat-spectrum LoS channel over a distance grid: the constant offset of the first-path range."""
    d = np.arange(d_min, d_max, step)
    h = np.exp(-2j * np.pi * freqs_hz[None, :] * d[:, None] / C0)[:, :, None] * np.ones((1, 1, 2))
    out = first_path_batch(cir_batch(h), float(freqs_hz[1] - freqs_hz[0]))
    return float(np.mean(out["range_m"] - d))


def rx_energy_s(h_col: np.ndarray, noise_var: float | None = 0.0):
    """Signed ratio of the total received power of the two RX ports: ``(E1 - E2) / (E1 + E2)``, ``E_i = sum_f |H_i(f)|^2``.

    ``h_col`` (B, n_bin, 2).  The expected thermal contribution ``n_bin * noise_var`` is subtracted from each energy (clipped at 0).
    Returns ``(s, E)`` with E of shape (B, 2).
    """
    h = np.asarray(h_col)
    e = (np.abs(h) ** 2).sum(axis=1) - (h.shape[1] * (noise_var or 0.0))
    e = np.maximum(e, 0.0)
    den = e.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(den > 0, (e[:, 0] - e[:, 1]) / den, np.nan)
    return s, e


def thermal_var_rx_s(e1: float, e2: float, noise_var: float, n_bin: int) -> float:
    """Delta-method variance of the rx-power ratio: Var(E_i) ~ 2 var E_i + n_bin var^2 (per-bin complex noise variance ``var``)."""
    tot = e1 + e2
    if tot <= 0:
        return float("inf")
    v1, v2 = 2.0 * noise_var * e1 + n_bin * noise_var ** 2, 2.0 * noise_var * e2 + n_bin * noise_var ** 2
    return 4.0 * (e2 ** 2 * v1 + e1 ** 2 * v2) / tot ** 4
