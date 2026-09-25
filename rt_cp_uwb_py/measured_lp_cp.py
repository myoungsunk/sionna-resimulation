#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Port of LABPC 2026-07-24 controlled VNA LP/CP analysis (labpc_vna_analysis.py).

Intentionally uses forward S21 as primary channel. S12 retained for audit only,
as VNA correction was OFF during acquisition. All functions are stateless callables
for integration with rt_cp_uwb_py pipeline.

Ported 2026-07-29 for measured CP-compact 3-feature validation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Mapping, MutableMapping, Sequence, Tuple
import json
import shutil
import zipfile

import numpy as np
from scipy.signal import correlate

C0 = 299_792_458.0
STATE_TAGS: Tuple[str, ...] = ("p10_p20", "p11_p20", "p10_p21", "p11_p21")


class AnalysisError(RuntimeError):
    """Raised when an input violates a hard analysis contract."""


@dataclass(frozen=True)
class SessionData:
    """Measured VNA session: frequency, 4 polarization states, metadata."""
    folder: Path
    frequency_hz: np.ndarray
    states: Mapping[str, np.ndarray]  # each [N, 2, 2], ABBA complex mean
    state_repeats: Mapping[str, Tuple[np.ndarray, ...]]
    headers: Mapping[str, str]
    start_time: datetime | None


@dataclass(frozen=True)
class BranchCalibration:
    """One-way branch ratio (alpha_t, alpha_r) from split-short standard."""
    frequency_hz: np.ndarray
    alpha_t: np.ndarray
    alpha_r: np.ndarray
    source_t: str
    source_r: str


def extract_zip_normalized(zip_path: Path, output_dir: Path) -> Path:
    """Extract ZIP, converting Windows backslashes to forward slashes."""
    zip_path = Path(zip_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            relative = info.filename.replace("\\", "/").lstrip("/")
            if not relative:
                continue
            target = output_dir / relative
            if relative.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink)
    return output_dir


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def read_touchstone(path: Path) -> Tuple[np.ndarray, np.ndarray, Dict[str, str]]:
    """Read 2-port Touchstone. Returns freq [Hz], S [N,2,2], headers dict.

    Supports RI (real/imag), MA (mag/deg), DB (dB/deg) formats.
    Touchstone 2-port order: S11, S21, S12, S22.
    """
    rows: list[list[float]] = []
    headers: Dict[str, str] = {}
    format_name = "MA"
    scale = 1.0
    unit_scale = {"HZ": 1.0, "KHZ": 1e3, "MHZ": 1e6, "GHZ": 1e9}

    with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("!"):
                if ":" in line:
                    key, value = line[1:].split(":", 1)
                    headers[key.strip()] = value.strip()
                continue
            if line.startswith("#"):
                tokens = line[1:].upper().split()
                for token in tokens:
                    if token in unit_scale:
                        scale = unit_scale[token]
                    elif token in {"RI", "MA", "DB"}:
                        format_name = token
                continue
            values = line.split()
            if len(values) >= 9:
                rows.append([float(item) for item in values[:9]])

    if not rows:
        raise AnalysisError(f"No Touchstone data rows in {path}")

    array = np.asarray(rows, dtype=float)
    frequency_hz = array[:, 0] * scale
    raw = array[:, 1:9].reshape(-1, 4, 2)
    if format_name == "RI":
        pairs = raw[..., 0] + 1j * raw[..., 1]
    else:
        magnitude = 10 ** (raw[..., 0] / 20) if format_name == "DB" else raw[..., 0]
        pairs = magnitude * np.exp(1j * np.deg2rad(raw[..., 1]))

    s_matrix = np.empty((len(frequency_hz), 2, 2), dtype=complex)
    s_matrix[:, 0, 0] = pairs[:, 0]  # S11
    s_matrix[:, 1, 0] = pairs[:, 1]  # S21
    s_matrix[:, 0, 1] = pairs[:, 2]  # S12
    s_matrix[:, 1, 1] = pairs[:, 3]  # S22
    return frequency_hz, s_matrix, headers


def _state_files(folder: Path, state_tag: str) -> list[Path]:
    """Find all s2p files matching state_tag."""
    return sorted(Path(folder).glob(f"*_{state_tag}.s2p"))


def load_session(folder: Path, require_abba: bool = True) -> SessionData:
    """Load one acquisition folder and average repeated ABBA observations.

    Args:
        folder: Path containing p10_p20, p11_p20, p10_p21, p11_p21 s2p files.
        require_abba: If True, require >= 2 repeats per state (ABBA pattern).
                     If False, allow single-file states (0710 data).

    Returns:
        SessionData with averaged frequency domain 2×2 matrices.
    """
    folder = Path(folder)
    frequency_reference: np.ndarray | None = None
    states: MutableMapping[str, np.ndarray] = {}
    repeats: MutableMapping[str, Tuple[np.ndarray, ...]] = {}
    headers: Dict[str, str] = {}

    for tag in STATE_TAGS:
        files = _state_files(folder, tag)
        minimum = 2 if require_abba else 1
        if len(files) < minimum:
            raise AnalysisError(f"{folder}: state {tag} has {len(files)} file(s), expected >= {minimum}")
        matrices: list[np.ndarray] = []
        for index, file_path in enumerate(files):
            frequency_hz, s_matrix, file_headers = read_touchstone(file_path)
            if frequency_reference is None:
                frequency_reference = frequency_hz
                headers = file_headers
            elif frequency_hz.shape != frequency_reference.shape or not np.allclose(
                frequency_hz, frequency_reference, rtol=0.0, atol=1e-3
            ):
                raise AnalysisError(f"Frequency-grid mismatch in {file_path}")
            matrices.append(s_matrix)
        repeats[tag] = tuple(matrices)
        states[tag] = np.mean(matrices, axis=0)

    if frequency_reference is None:
        raise AnalysisError(f"No state data in {folder}")

    manifest_path = folder / "run_manifest.json"
    start_time: datetime | None = None
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            start_time = parse_iso_datetime(manifest.get("started_at_utc"))
        except (json.JSONDecodeError, OSError):
            start_time = None

    return SessionData(
        folder=folder,
        frequency_hz=frequency_reference,
        states=dict(states),
        state_repeats=dict(repeats),
        headers=headers,
        start_time=start_time,
    )


def lp_matrix_s21(states: Mapping[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """Forward Jones matrix from S21 with experimentally verified crossed mapping.

    Authority: LABPC 2026-07-24 measurement setup.

    THE BRANCHES ARE DIAGONAL, NOT x/y.  The names below are XX/XY/YX/YY only
    because the CP synthesis in lp_to_cp is invariant to which orthogonal linear
    pair is used. The physical feeds sit at psi = 42.58 deg to the plate's TE/TM
    axes (Y1f complex-coherence estimator, |rho| = 0.988, 724 IQR 0.99 deg;
    C1b confirms it survives the branch calibration, shift -0.47 deg).
    Independently corroborated by the pattern lineage: RHCP_new/LHCP_new are
    algebraically -j(E_+45 +- j E_-45) from the LP+-45 files, residual 4e-11 (Y2a).

    WHY THE MAPPING IS "CROSSED".  port1 is the TX switch and port2 the RX switch
    (visible in same_side_correct below: b differs from a in port1 and is divided
    by alpha_t; c differs in port2 and is divided by alpha_r). So p1X_p2Y is
    H[rx=Y, tx=X], and the assignment written here,

        a = H[1,0]   b = H[1,1]   c = H[0,0]   d = H[0,1]

    is a RECEIVE-PORT SWAP relative to the naive a=H[0,0], b=H[0,1], c=H[1,0],
    d=H[1,1]. That swap, together with the RX-L sign flip in
    scripts/_cp_composites.py, is exactly the relabelling a 45-degree measurement
    basis requires: with it the composites reproduce the simulation's CP-port
    composites to 3e-11, without it they are 0.79 off and co/cross come out
    swapped (C3, enumerating all 8 assignments; C5 for the swap).

    So neither patch is a fudge -- but note C3 also found FOUR of the eight
    assignments reconcile equally well (port-swap degeneracy). This one is
    correct; it is not uniquely singled out by the data.

    Do not "fix" this to the naive mapping. C6 Test A checks the end result:
    LoS lands in co on both sides, measured +13.72 dB vs simulated +15.51 dB.
    """
    return {
        "a": states["p10_p21"][:, 1, 0],  # XX
        "b": states["p11_p21"][:, 1, 0],  # XY
        "c": states["p10_p20"][:, 1, 0],  # YX
        "d": states["p11_p20"][:, 1, 0],  # YY
    }


def to_time(
    frequency_hz: np.ndarray,
    response: np.ndarray,
    pad_factor: int = 32,
    kaiser_beta: float = 6.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Return periodic band-limited complex impulse response via IFFT."""
    count = len(frequency_hz)
    nfft = pad_factor * count
    window = np.kaiser(count, kaiser_beta)
    impulse = np.fft.ifft(response * window, n=nfft) * (nfft / count)
    time_s = np.arange(nfft) / (nfft * (frequency_hz[1] - frequency_hz[0]))
    return time_s, impulse


def periodic_delta(time_s: np.ndarray, center_s: float, period_s: float) -> np.ndarray:
    """Periodic distance from center, wrapping at ±period/2."""
    return (time_s - center_s + period_s / 2) % period_s - period_s / 2


def time_gate(
    frequency_hz: np.ndarray,
    response: np.ndarray,
    center_s: float,
    halfwidth_s: float,
    pad_factor: int = 16,
) -> np.ndarray:
    """Apply Gaussian time gate and return gated response on original frequency grid."""
    count = len(frequency_hz)
    nfft = pad_factor * count
    impulse = np.fft.ifft(response, n=nfft)
    time_s = np.arange(nfft) / (nfft * (frequency_hz[1] - frequency_hz[0]))
    period_s = 1.0 / (frequency_hz[1] - frequency_hz[0])
    delta = periodic_delta(time_s, center_s, period_s)
    sigma = halfwidth_s / 2.0
    gate = np.exp(-0.5 * (delta / sigma) ** 2)
    return np.fft.fft(impulse * gate, n=nfft)[:count]


def gate_matrix(
    frequency_hz: np.ndarray,
    matrix: Mapping[str, np.ndarray],
    center_s: float,
    halfwidth_s: float,
) -> Dict[str, np.ndarray]:
    """Apply time gate to all 4 components of Jones matrix."""
    return {
        key: time_gate(frequency_hz, value, center_s, halfwidth_s)
        for key, value in matrix.items()
    }


def main_tap_time(frequency_hz: np.ndarray, response: np.ndarray) -> float:
    """Peak time of frequency response via IFFT."""
    time_s, impulse = to_time(frequency_hz, response, pad_factor=16, kaiser_beta=0.0)
    return float(time_s[int(np.argmax(np.abs(impulse)))])


def _moving_average_complex(values: np.ndarray, bins: int) -> np.ndarray:
    """Complex moving average (convolution with rect kernel)."""
    if bins <= 1:
        return values
    kernel = np.ones(int(bins), dtype=float) / int(bins)
    return np.convolve(values, kernel, mode="same")


def alpha_from_reflective(
    frequency_hz: np.ndarray,
    q_y: np.ndarray,
    q_x: np.ndarray,
    gate: bool = True,
    gate_halfwidth_s: float = 2e-9,
    smooth_bins: int = 9,
) -> np.ndarray:
    """Estimate one-way branch ratio from same-side round-trip standard.

    Used for split-short calibration: q_x is TX short, q_y is RX short.
    Returns sqrt(q_y/q_x) in log-mag and unwrapped-phase space.
    """
    if gate:
        center_s = main_tap_time(frequency_hz, q_x)
        q_x = time_gate(frequency_hz, q_x, center_s, gate_halfwidth_s)
        q_y = time_gate(frequency_hz, q_y, center_s, gate_halfwidth_s)
    ratio = _moving_average_complex(q_y / np.where(np.abs(q_x) > 1e-30, q_x, 1e-30), smooth_bins)
    phase = np.unwrap(np.angle(ratio))
    phase -= 2 * np.pi * np.round(np.mean(phase) / (2 * np.pi))
    return np.sqrt(np.abs(ratio)) * np.exp(1j * phase / 2)


def branch_calibration_from_split_shorts(
    short_t: SessionData,
    short_r: SessionData,
) -> BranchCalibration:
    """Derive TX and RX branch calibration from split-short round-trip measurements.

    Authority: LABPC 2026-07-24 block-level (D900, D1350, D1800).
    """
    if short_t.frequency_hz.shape != short_r.frequency_hz.shape or not np.allclose(
        short_t.frequency_hz, short_r.frequency_hz, atol=1e-3, rtol=0.0
    ):
        raise AnalysisError("TX and RX short sessions use different frequency grids")
    frequency_hz = short_t.frequency_hz
    alpha_t = alpha_from_reflective(
        frequency_hz,
        short_t.states["p11_p20"][:, 0, 0],
        short_t.states["p10_p20"][:, 0, 0],
    )
    alpha_r_roundtrip = alpha_from_reflective(
        frequency_hz,
        short_r.states["p10_p21"][:, 1, 1],
        short_r.states["p10_p20"][:, 1, 1],
    )
    alpha_r = 1.0 / alpha_r_roundtrip
    return BranchCalibration(
        frequency_hz=frequency_hz,
        alpha_t=alpha_t,
        alpha_r=alpha_r,
        source_t=short_t.folder.name,
        source_r=short_r.folder.name,
    )


def complex_calibration_interpolate(
    first: np.ndarray,
    second: np.ndarray,
    weight: float,
) -> np.ndarray:
    """Interpolate branch ratios in log-magnitude and unwrapped phase."""
    weight = float(np.clip(weight, 0.0, 1.0))
    logmag_first = np.log(np.maximum(np.abs(first), 1e-30))
    logmag_second = np.log(np.maximum(np.abs(second), 1e-30))
    phase_first = np.unwrap(np.angle(first))
    relative = np.unwrap(np.angle(second * np.conj(first)))
    logmag = (1 - weight) * logmag_first + weight * logmag_second
    phase = phase_first + weight * relative
    return np.exp(logmag + 1j * phase)


def apply_branch_sign_anchor(
    los_matrix: Mapping[str, np.ndarray],
    alpha_t: np.ndarray,
    alpha_r: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, float | bool]]:
    """Resolve relative square-root sign using clean LoS product check.

    Returns: (corrected alpha_t, corrected alpha_r, diagnostic report).
    """
    product_residual = (los_matrix["d"] / np.where(np.abs(los_matrix["a"]) > 1e-30, los_matrix["a"], 1e-30)) / (
        alpha_t * alpha_r
    )
    phase = float(np.angle(np.mean(product_residual / np.maximum(np.abs(product_residual), 1e-30))))
    flipped = abs(phase) > np.pi / 2
    if flipped:
        alpha_t = -alpha_t
        product_residual = -product_residual
        phase = float(np.angle(np.mean(product_residual / np.maximum(np.abs(product_residual), 1e-30))))
    report = {
        "flipped_alpha_t": flipped,
        "median_product_magnitude_db": float(np.median(20 * np.log10(np.maximum(np.abs(product_residual), 1e-30)))),
        "circular_mean_phase_deg": float(np.degrees(phase)),
    }
    return alpha_t, alpha_r, report


def same_side_correct(
    matrix: Mapping[str, np.ndarray],
    alpha_t: np.ndarray,
    alpha_r: np.ndarray,
) -> Dict[str, np.ndarray]:
    """Apply branch calibration (one-way ratios) to same-side basis."""
    return {
        "a": matrix["a"],
        "b": matrix["b"] / alpha_t,
        "c": matrix["c"] / alpha_r,
        "d": matrix["d"] / (alpha_r * alpha_t),
    }


def lp_to_cp(matrix: Mapping[str, np.ndarray]) -> Dict[str, np.ndarray]:
    """LP-to-CP unitary transform for e^{+jwt} convention.

    Input: {a,b,c,d} = {XX, XY, YX, YY} after branch correction.
    Output: {RR, RL, LR, LL} = {RHCP, RHCP←LHCP, LHCP←RHCP, LHCP}.
    """
    a, b, c, d = matrix["a"], matrix["b"], matrix["c"], matrix["d"]
    return {
        "RR": 0.5 * ((a + d) + 1j * (c - b)),
        "RL": 0.5 * ((a - d) + 1j * (b + c)),
        "LR": 0.5 * ((a - d) - 1j * (b + c)),
        "LL": 0.5 * ((a + d) - 1j * (c - b)),
    }


def crop_response(
    frequency_hz: np.ndarray,
    response: np.ndarray,
    lower_hz: float,
    upper_hz: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Crop frequency response to [lower_hz, upper_hz]."""
    mask = (frequency_hz >= lower_hz) & (frequency_hz <= upper_hz)
    if mask.sum() < 2:
        raise AnalysisError("Requested crop contains fewer than two frequency samples")
    return frequency_hz[mask], response[mask]


def crop_matrix(
    frequency_hz: np.ndarray,
    matrix: Mapping[str, np.ndarray],
    lower_hz: float,
    upper_hz: float,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Crop all 4 Jones components to frequency range."""
    mask = (frequency_hz >= lower_hz) & (frequency_hz <= upper_hz)
    return frequency_hz[mask], {key: value[mask] for key, value in matrix.items()}


def energy(response: np.ndarray) -> float:
    """Total energy (sum of squared magnitudes)."""
    return float(np.sum(np.abs(response) ** 2))


def db10(numerator: float, denominator: float) -> float:
    """10·log10(numerator/denominator) ratio."""
    return float(10 * np.log10((numerator + 1e-30) / (denominator + 1e-30)))


def db20(numerator: float, denominator: float) -> float:
    """20·log10(numerator/denominator) ratio (amplitude)."""
    return float(20 * np.log10((numerator + 1e-30) / (denominator + 1e-30)))
