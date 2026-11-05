"""Independent FP-SC-001 receiver arithmetic reference.

Written by /root/design_audit (same-session separate reviewer), from the
frozen receiver specification and source inspection.  No production receiver
or pilot is imported.  The implementation loops over frames and RX ports,
uses a scalar first-crossing search, and offers a direct-DFT spot checker.

The functions preserve baseline zero-signal/NaN behavior.  `detected` is the
source threshold decision; `reference_valid` is a separate evaluator flag and
must never overwrite source output.  Synthetic self-checks are not RF parity
or MB_VAR/filter validation.

Source contract: e38de517a21a43bb210c7e04c9fbd6517d8a95cf
Source receiver blob: 4182f97eb5b564e941786043dbc43eb78f8e84cf
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

C0 = 299792458.0
FRACTION = 0.30
DEFAULT_N_TEST_TAPS = 1028


def reference_hann(n: int) -> np.ndarray:
    if n < 2:
        raise ValueError("Hann grid needs at least two bins")
    phase = 2.0 * np.pi * np.arange(n, dtype=np.float64) / (n - 1)
    return 0.5 * (1.0 - np.cos(phase))


def reference_cir(h_col: np.ndarray) -> np.ndarray:
    """(frames, bins, 2 RX) -> (frames, 4*bins, 2 RX), IFFT times bins."""
    channels = np.asarray(h_col, dtype=np.complex128)
    if channels.ndim != 3 or channels.shape[2] != 2:
        raise ValueError("Expected selected-TX H with shape (frames,bins,2)")
    frames, bins, ports = channels.shape
    window = reference_hann(bins)
    result = np.empty((frames, 4 * bins, ports), dtype=np.complex128)
    for frame in range(frames):
        for port in range(ports):
            spectrum = np.zeros(4 * bins, dtype=np.complex128)
            spectrum[:bins] = channels[frame, :, port] * window
            result[frame, :, port] = np.fft.ifft(spectrum) * bins
    return result


def direct_dft_taps(h_frame: np.ndarray, tap_indices: np.ndarray) -> np.ndarray:
    """Independent inverse-DFT summation for chosen taps of one frame.

    This provides an arithmetic spot check without using numpy.fft.  It is
    not a substitute for checking every detector candidate/row.  The returned
    shape is (len(tap_indices), 2 RX).
    """
    h = np.asarray(h_frame, dtype=np.complex128)
    taps = np.asarray(tap_indices, dtype=np.int64)
    if h.ndim != 2 or h.shape[1] != 2 or taps.ndim != 1:
        raise ValueError("Expected H (bins,2), taps (n,)")
    bins = h.shape[0]
    if np.any(taps < 0) or np.any(taps >= 4 * bins):
        raise ValueError("Tap outside FFT grid")
    kernel = np.exp(2j * np.pi * taps[:, None] * np.arange(bins)[None, :] / (4 * bins))
    return (kernel @ (h * reference_hann(bins)[:, None])) / 4.0


def reference_first_path(cir: np.ndarray, df_hz: float) -> dict[str, np.ndarray]:
    """Apply the frozen 30%-amplitude detector with exact discrete rules."""
    values = np.asarray(cir, dtype=np.complex128)
    if values.ndim != 3 or values.shape[2] != 2:
        raise ValueError("Expected CIR (frames,taps,2)")
    if not math.isfinite(float(df_hz)) or df_hz <= 0:
        raise ValueError("Positive finite frequency spacing is required")
    frames, n_taps, _ = values.shape
    if n_taps == 0:
        raise ValueError("Empty tap grid")
    index = np.zeros(frames, dtype=np.int64)
    rx = np.zeros(frames, dtype=np.int64)
    peak = np.empty(frames, dtype=np.float64)
    power = np.empty((frames, 2), dtype=np.float64)
    ratio = np.empty(frames, dtype=np.float64)
    for frame in range(frames):
        amplitude = np.abs(values[frame])
        branch_peaks = np.asarray([np.max(amplitude[:, port]) for port in range(2)])
        # numpy.argmax intentionally preserves source tie and NaN semantics.
        selected_rx = int(np.argmax(branch_peaks))
        strong = amplitude[:, selected_rx]
        selected_peak = float(np.max(strong))
        selected_tap = 0  # baseline argmax on all-False mask returns zero
        for tap in range(n_taps):
            if strong[tap] >= FRACTION * selected_peak:
                selected_tap = tap
                break
        index[frame], rx[frame], peak[frame] = selected_tap, selected_rx, selected_peak
        p = np.abs(values[frame, selected_tap]) ** 2
        power[frame] = p
        denominator = float(p[0] + p[1])
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio[frame] = (p[0] - p[1]) / denominator if denominator > 0 else np.nan
    delay = index / (n_taps * float(df_hz))
    return {
        "index": index,
        "rx": rx,
        "peak": peak,
        "power": power,
        "s": ratio,
        "delay_s": delay,
        "range_m": delay * C0,
    }


def reference_noise_variance(snr_db: float, distance_m: float = 10.0,
                             freq_hz: float = 6.5e9) -> float:
    """Frozen unit-gain free-space per-bin variance, not realised SNR."""
    power = (C0 / freq_hz / (4.0 * math.pi * distance_m)) ** 2
    return power / 10.0 ** (snr_db / 10.0)


def reference_threshold(noise_var: float, n_branches: int = 2,
                        n_taps: int = DEFAULT_N_TEST_TAPS,
                        pfa: float = 1e-3) -> float:
    return math.sqrt(6.0 * noise_var * math.log(n_branches * n_taps / pfa))


def draw_original_noise(shape: tuple[int, ...], noise_var: float,
                        rng: np.random.Generator) -> np.ndarray:
    """Real full-array draw, then imaginary full-array draw, original order.

    The caller must freeze the exact batch shape and generator state.  Calling
    this per frame instead of once for the original batch changes the noise.
    """
    if not math.isfinite(noise_var) or noise_var < 0:
        raise ValueError("Invalid per-bin complex noise variance")
    sigma = math.sqrt(noise_var / 2.0)
    real = rng.standard_normal(shape)
    imaginary = rng.standard_normal(shape)
    return sigma * (real + 1j * imaginary)


def reference_observe(h_clean: np.ndarray, freqs_hz: np.ndarray,
                      noise_var: float | None = None,
                      rng: np.random.Generator | None = None,
                      tx: int = 0, threshold: float | None = None,
                      return_h: bool = False,
                      noise_array: np.ndarray | None = None) -> dict[str, Any]:
    """Independent observation chain, with optional already-frozen noise.

    Noise arrays are additive complex samples, not standard-normal xi.  A
    supplied noise array is added exactly once.  It and `rng` are exclusive.
    `reference_valid` requires finite positive support in addition to source
    `detected`; it does not impose positive power in both RX ports.
    """
    channels = np.asarray(h_clean)
    frequency = np.asarray(freqs_hz, dtype=np.float64)
    if channels.ndim != 4 or channels.shape[2] != 2:
        raise ValueError("Expected H (frames,bins,2 RX,n_tx)")
    if not 0 <= tx < channels.shape[3]:
        raise ValueError("TX outside input column range")
    if frequency.ndim != 1 or len(frequency) != channels.shape[1] or len(frequency) < 2:
        raise ValueError("Frequency grid does not match H bins")
    if not np.all(np.isfinite(frequency)):
        raise ValueError("Nonfinite frequency grid")
    df = float(frequency[1] - frequency[0])
    if df <= 0 or not np.allclose(np.diff(frequency), df, rtol=1e-12, atol=1e-8):
        raise ValueError("Frequency grid must be uniformly increasing")
    variance = float(noise_var or 0.0)
    if not math.isfinite(variance) or variance < 0:
        raise ValueError("Invalid noise variance")
    h = channels[..., tx]
    if noise_array is not None:
        if rng is not None:
            raise ValueError("Pass either frozen noise_array or rng, not both")
        additive_noise = np.asarray(noise_array)
        if additive_noise.shape != h.shape:
            raise ValueError("Noise array shape mismatch")
        h = h + additive_noise
    elif variance:
        if rng is None:
            raise ValueError("No RNG for positive noise variance")
        h = h + draw_original_noise(h.shape, variance, rng)
    out = reference_first_path(reference_cir(h), df)
    # Source uses detection_threshold's literal default 1028 even for other
    # input lengths.  The actual contract expects 257 bins/1028 taps.
    threshold_used = reference_threshold(variance) if threshold is None and variance else (0.0 if threshold is None else float(threshold))
    out["detected"] = out["peak"] >= threshold_used
    for key in ("s", "range_m", "delay_s"):
        out[key] = np.where(out["detected"], out[key], np.nan)
    out["threshold"] = threshold_used
    out["reference_valid"] = (
        out["detected"]
        & np.isfinite(out["s"])
        & np.isfinite(out["range_m"])
        & np.isfinite(out["peak"])
        & (out["peak"] > 0)
        & np.all(np.isfinite(out["power"]), axis=1)
        & (np.sum(out["power"], axis=1) > 0)
    )
    if return_h:
        out["h_noisy"] = h
    return out


def reference_los_range_bias(freqs_hz: np.ndarray, d_min: float = 2.0,
                             d_max: float = 16.0, step: float = 0.01) -> float:
    """Reproduce the flat-spectrum grid offset, not FFD direct-only bias."""
    frequency = np.asarray(freqs_hz, dtype=np.float64)
    distance = np.arange(d_min, d_max, step)
    h = np.exp(-2j * np.pi * frequency[None, :] * distance[:, None] / C0)
    two_rx = np.repeat(h[:, :, None], 2, axis=2)
    measured = reference_first_path(reference_cir(two_rx), frequency[1] - frequency[0])
    return float(np.mean(measured["range_m"] - distance))


def compare_arrays(expected: np.ndarray, actual: np.ndarray, *, name: str,
                   discrete: bool = False, scale: float = 1.0,
                   tolerance: float = 1e-10) -> dict[str, Any]:
    """Comparison with explicit finite/NaN/Inf parity and fixed unit scale."""
    a, b = np.asarray(expected), np.asarray(actual)
    record: dict[str, Any] = {"field": name, "expected_shape": list(a.shape),
                              "actual_shape": list(b.shape), "scale": scale,
                              "tolerance": 0.0 if discrete else tolerance}
    if a.shape != b.shape:
        return {**record, "status": "FAIL_SHAPE"}
    if scale <= 0 or not math.isfinite(scale) or tolerance < 0:
        raise ValueError("Invalid fixed comparison scale/tolerance")
    if discrete:
        mismatches = int(np.count_nonzero(a != b))
        return {**record, "n_elements": int(a.size), "mismatches": mismatches,
                "status": "PASS" if mismatches == 0 else "FAIL"}
    finite_a, finite_b = np.isfinite(a), np.isfinite(b)
    finite_mismatches = int(np.count_nonzero(finite_a != finite_b))
    nan_mismatches = int(np.count_nonzero(np.isnan(a) != np.isnan(b)))
    # Same-sign infinity is permitted only when present identically in source.
    infinity_mismatches = int(np.count_nonzero(np.isinf(a) != np.isinf(b)))
    common_inf = np.isinf(a) & np.isinf(b)
    infinity_mismatches += int(np.count_nonzero(a[common_inf] != b[common_inf]))
    finite = finite_a & finite_b
    difference = np.abs(a[finite] - b[finite])
    maximum = float(difference.max()) if difference.size else 0.0
    normalized = maximum / scale
    passed = not (finite_mismatches or nan_mismatches or infinity_mismatches) and normalized <= tolerance
    return {**record, "n_elements": int(a.size), "finite_pairs": int(np.count_nonzero(finite)),
            "nan_pairs": int(np.count_nonzero(np.isnan(a) & np.isnan(b))),
            "finite_mismatches": finite_mismatches, "nan_mismatches": nan_mismatches,
            "infinity_mismatches": infinity_mismatches, "max_abs": maximum,
            "max_normalized": normalized, "status": "PASS" if passed else "FAIL"}


def synthetic_self_check() -> dict[str, Any]:
    """Hand-constructed arithmetic cases; no scientific dataset is read."""
    checks: dict[str, bool] = {}
    c = np.zeros((1, 16, 2), dtype=np.complex128)
    c[0, 3, 0], c[0, 6, 0] = 0.31, 1.0
    out = reference_first_path(c, 1.95e6)
    checks["amplitude_30_not_power_30"] = bool(out["index"][0] == 3)
    checks["single_port_null_valid_signed_s"] = bool(out["s"][0] == 1.0)
    c[0, 6, 1] = 1.0
    out = reference_first_path(c, 1.95e6)
    checks["rx_tie_first_port"] = bool(out["rx"][0] == 0 and out["index"][0] == 3)
    zero = reference_observe(np.zeros((1, 257, 2, 1), complex), np.arange(257) * 1.95e6)
    checks["zero_source_detected_preserved"] = bool(zero["detected"][0] and zero["index"][0] == 0 and zero["range_m"][0] == 0)
    checks["zero_reference_invalid"] = bool(np.isnan(zero["s"][0]) and not zero["reference_valid"][0])
    h = np.asarray([[[1.0 + 0.2j, 0.0j], [0.5 - 0.1j, 0.2j], [0.4j, 0.3], [0.2, -0.1j]]])
    fft = reference_cir(h)[0]
    taps = np.arange(16)
    direct = direct_dft_taps(h[0], taps)
    checks["ifft_matches_direct_dft"] = bool(np.max(np.abs(fft - direct)) < 1e-14)
    checks["nan_parity_is_explicit"] = compare_arrays(np.array([np.nan]), np.array([0.0]), name="s")["status"] == "FAIL"
    checks["one_tap_mismatch_fails"] = compare_arrays(np.array([3]), np.array([4]), name="index", discrete=True)["status"] == "FAIL"
    return {"scope": "SYNTHETIC_ARITHMETIC_ONLY_NOT_RF_OR_FILTER_PARITY", "checks": checks,
            "status": "PASS" if all(checks.values()) else "FAIL"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="Run hand-constructed arithmetic checks only")
    args = parser.parse_args()
    if not args.self_check:
        parser.error("Import reference functions from a frozen E0 runner, or use --self-check")
    report = synthetic_self_check()
    report["checker_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    print(json.dumps(report, sort_keys=True, indent=2))
    raise SystemExit(0 if report["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
