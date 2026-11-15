"""DIAGNOSTIC_ONLY helpers for the G1-DIAG-003 D1–D3 comparisons."""

from __future__ import annotations

import numpy as np
from scipy.fft import irfft, next_fast_len, rfft


THINNING_INTERVALS = (1, 2, 5, 10, 20, 50)
OBSERVATIONS = ("range", "s")
DISTANCE_BIN_M = 0.25


def phase_configs():
    return tuple((m, p) for m in THINNING_INTERVALS for p in range(m))


def joint_mask(n, m, p):
    """Index the original zero-based packets, before evaluation or gate masking."""
    if (m, p) not in phase_configs():
        raise ValueError("unknown D2 interval or phase")
    return np.arange(n) % m == p


def phase_summary(rows, metrics):
    """Average pre-aggregated phases equally within a single condition."""
    expected = set(phase_configs())
    by_phase = {(int(row["m"]), int(row["p"])): row for row in rows}
    if set(by_phase) != expected or len(by_phase) != len(rows):
        raise ValueError("D2/D3 phases missing, duplicated, or unexpected")
    summaries = []
    for m in THINNING_INTERVALS:
        summary = {"m": m, "n_phases": m, "phase_weighting": "equal"}
        for metric in metrics:
            values = np.array([by_phase[m, p][metric] for p in range(m)], dtype=float)
            if not np.isfinite(values).all():
                raise ValueError(f"nonfinite phase metric: {metric}, m={m}")
            summary[metric] = {
                "mean": float(np.mean(values)),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
            }
        summaries.append(summary)
    return summaries


def heading_transport(transition, jacobian, gain, accepted, checkpoint_index):
    """G[seed, checkpoint, packet, channel] at the frozen J4 linearization.

    Rejected packets use zero effective gain and still propagate the prior's
    perturbation. Frame zero has identity transition because it has no predict.
    """
    n_seeds, n_frames = accepted.shape
    k_eff = np.where(accepted[..., None, None], gain, 0.0)
    a = (np.eye(4) - k_eff @ jacobian) @ transition
    if not np.array_equal(transition[:, 0], np.broadcast_to(np.eye(4), (n_seeds, 4, 4))):
        raise ValueError("frame zero must use identity transition")
    transport = np.empty((n_seeds, len(checkpoint_index), n_frames, 2))
    row = np.zeros((n_seeds, len(checkpoint_index), 4))
    for k in range(n_frames - 1, -1, -1):
        row[:, checkpoint_index == k, 2] = 1.0
        transport[:, :, k, :] = row @ k_eff[:, k]
        row = row @ a[:, k]
    return transport


def transferred_variances(transport, observation_error):
    """Full Toeplitz and frame-block-diagonal transported variances.

    A common denominator N gives a PSD block Toeplitz estimate using all
    zero-padded lags of the centered observation residual along one RF path.
    The quadratic form is the energy of the summed channel cross-correlations
    of the sensitivity row and centered residual, divided by N.
    """
    n = len(observation_error)
    centered = observation_error - observation_error.mean(axis=0)
    same_frame = centered.T @ centered / n
    nfft = next_fast_len(2 * n - 1, real=True)
    g_freq = rfft(transport, n=nfft, axis=-2)
    e_freq = rfft(centered, n=nfft, axis=0)
    convolved = irfft(np.sum(g_freq * e_freq.conj(), axis=-1), n=nfft, axis=-1)
    full = np.sum(convolved**2, axis=-1) / n
    diagonal = np.einsum("...ki,ij,...kj->...", transport, same_frame, transport,
                         optimize=True)
    return full, diagonal, same_frame


def _as_optional_list(values):
    return [float(v) if np.isfinite(v) else None for v in values]


def _innovation_acf(innovation, distance_m):
    """Descriptive ACF across frames and traveled distance on the shared path."""
    n_seeds, n_frames, _ = innovation.shape
    centered = innovation - innovation.mean(axis=1, keepdims=True)
    nfft = next_fast_len(2 * n_frames - 1, real=True)
    series = rfft(centered, n=nfft, axis=1)
    acov = irfft(np.mean(np.abs(series) ** 2, axis=0) / n_frames,
                 n=nfft, axis=0)[:n_frames]
    variance = np.mean(centered**2, axis=(0, 1))
    acf = np.full_like(acov, np.nan)
    np.divide(acov, variance, out=acf, where=variance > 0)

    left, right = np.triu_indices(n_frames, k=1)
    distance_lag = distance_m[right] - distance_m[left]
    # An exact zero-distance group preserves repeated fixed-position packets.
    bins = np.where(distance_lag == 0, 0, np.ceil(distance_lag / DISTANCE_BIN_M)).astype(int)
    counts = np.bincount(bins, minlength=1)
    arrays = {}
    for col, channel in enumerate(OBSERVATIONS):
        if variance[col] > 0:
            cross = centered[..., col].T @ centered[..., col] / n_seeds
            numer = np.bincount(bins, weights=cross[left, right], minlength=len(counts))
            distance_rho = np.full(len(counts), np.nan)
            np.divide(numer, variance[col] * counts, out=distance_rho, where=counts > 0)
            crossing = np.flatnonzero(acf[1:, col] <= 0)
            max_lag = int(crossing[0]) if crossing.size else n_frames - 1
            f_factor = float(1.0 + 2.0 * np.sum(acf[1:max_lag + 1, col]))
        else:
            distance_rho = np.full(len(counts), np.nan)
            max_lag = None
            f_factor = None
        arrays[channel] = {
            "frame_rho": _as_optional_list(acf[:, col]),
            "distance_rho": _as_optional_list(distance_rho),
            "F": f_factor,
            "F_last_included_positive_frame_lag": max_lag,
        }
    return {
        "channel": arrays,
        "frame_lag": list(range(n_frames)),
        "frame_valid_packet_pairs_per_seed": list(range(n_frames, 0, -1)),
        "distance_bin_m": DISTANCE_BIN_M,
        "distance_bin_convention": "first bin exact zero; others (lower, upper] meters",
        "distance_bin_upper_m": (DISTANCE_BIN_M * np.arange(len(counts))).tolist(),
        "distance_valid_packet_pairs_per_seed": counts.tolist(),
        "seed_count": n_seeds,
        "rf_trajectory_count": 1,
        "centering": "subtract within-seed all-frame mean before pooling products",
        "frame_acf": "biased denominator N; normalized by mean lag-zero variance",
        "distance_acf": "mean pair product per bin; normalized by mean lag-zero variance",
        "F_note": "auxiliary sample-mean inflation from the initial consecutive positive frame lags",
    }


def decompose_d1(*, observation_error, innovation, transition, jacobian, gain,
                 accepted, heading_error_rad, heading_nees, checkpoint_index,
                 distance_m):
    """One case/bias/sign cohort; equally weighted seeds and checkpoints."""
    innovation = np.asarray(innovation, dtype=float)
    if innovation.ndim != 3 or innovation.shape[-1] != 2:
        raise ValueError("D1 needs [seed, packet, range/s] innovations")
    n_seeds, n_frames, _ = innovation.shape
    accepted = np.asarray(accepted)
    heading_error_rad = np.asarray(heading_error_rad, dtype=float)
    heading_nees = np.asarray(heading_nees, dtype=float)
    transition = np.asarray(transition, dtype=float)
    jacobian = np.asarray(jacobian, dtype=float)
    gain = np.asarray(gain, dtype=float)
    observation_error = np.asarray(observation_error, dtype=float)
    distance_m = np.asarray(distance_m, dtype=float)
    checkpoints = np.asarray(checkpoint_index)
    required = {
        "innovation": (innovation, (n_seeds, n_frames, 2)),
        "transition": (transition, (n_seeds, n_frames, 4, 4)),
        "jacobian": (jacobian, (n_seeds, n_frames, 2, 4)),
        "gain": (gain, (n_seeds, n_frames, 4, 2)),
        "accepted": (accepted, (n_seeds, n_frames)),
        "heading_error_rad": (heading_error_rad, (n_seeds, n_frames)),
        "heading_nees": (heading_nees, (n_seeds, n_frames)),
        "observation_error": (observation_error, (n_frames, 2)),
        "distance_m": (distance_m, (n_frames,)),
    }
    invalid = [name for name, (arr, shape) in required.items()
               if arr.shape != shape or not np.isfinite(arr).all()]
    if invalid:
        raise ValueError("invalid D1 inputs: " + ", ".join(invalid))
    if n_seeds < 1 or n_frames < 2 or accepted.dtype.kind != "b":
        raise ValueError("D1 requires a boolean accept mask and at least two packets")
    if checkpoints.ndim != 1 or checkpoints.size == 0 or checkpoints.dtype.kind not in "iu":
        raise ValueError("missing D1 evaluation checkpoint indices")
    if np.any(checkpoints < 0) or np.any(checkpoints >= n_frames):
        raise ValueError("D1 checkpoint index out of bounds")
    if np.any(np.diff(distance_m) < 0):
        raise ValueError("D1 expects cumulative traveled distance")
    if np.any(np.abs(heading_error_rad) > np.pi + 1e-12):
        raise ValueError("D1 heading errors must be wrapped radians")

    g = heading_transport(transition, jacobian, gain, accepted, checkpoints)
    v_full_by_site, v_diag_by_site, same_frame = transferred_variances(g, observation_error)
    v_full = float(np.mean(v_full_by_site))
    v_diag = float(np.mean(v_diag_by_site))
    error = heading_error_rad[:, checkpoints]
    mean = float(np.mean(error))
    mse = float(np.mean(error**2))
    centered_variance = float(np.mean((error - mean)**2))
    bias_sq = mean**2
    cross = v_full - v_diag
    components = {"bias_sq": bias_sq, "time_cross": cross,
                  "remaining_variance": centered_variance - cross}
    reconstructed = sum(components.values())
    if not np.isclose(reconstructed, mse, rtol=1e-12, atol=1e-15):
        raise RuntimeError("D1 heading MSE decomposition identity failed")
    shares = {name: value / mse if mse > 0 else None for name, value in components.items()}
    qualifying = [name for name, share in shares.items() if share is not None and share >= 0.60]
    reason = None
    if mse == 0:
        reason = "ZERO_MSE"
    elif components["remaining_variance"] < 0.0:
        reason = "NEGATIVE_REMAINING_VARIANCE"
    elif len(qualifying) > 1:
        reason = "MULTIPLE_COMPONENTS_REACH_60_PERCENT"
    classification = "유보" if reason else (qualifying[0] if qualifying else "혼합")
    return {
        "status": "DIAGNOSTIC_ONLY",
        "classification": classification,
        "deferred_reason": reason,
        "n_seeds": n_seeds,
        "n_rf_trajectories": 1,
        "n_packets": n_frames,
        "n_checkpoint_positions": len(checkpoints),
        "n_seed_checkpoint_pairs": int(error.size),
        "mean_error_rad": mean,
        "mse_rad2": mse,
        "centered_variance_rad2": centered_variance,
        "mse_reconstructed_rad2": reconstructed,
        "mse_reconstruction_error_rad2": reconstructed - mse,
        "components_rad2": components,
        "component_mse_shares": shares,
        "v_full_rad2": v_full,
        "v_diag_rad2": v_diag,
        "v_full_minus_realized_variance_rad2": v_full - centered_variance,
        "v_diag_minus_realized_variance_rad2": v_diag - centered_variance,
        "time_cross_sign": int(np.sign(cross)),
        "mean_heading_nees": float(np.mean(heading_nees[:, checkpoints])),
        "same_frame_observation_error_covariance_range_s": same_frame.tolist(),
        "covariance_estimator": "within-case globally centered biased block Toeplitz, "
                                "all packet lags with common denominator N, one RF path",
        "observation_error_valid_pairs_by_frame_lag": list(range(n_frames, 0, -1)),
        "innovation_acf": _innovation_acf(innovation, distance_m),
    }


def synthetic_checks():
    """Verify gain transport and both quadratic forms with direct small examples."""
    rng = np.random.default_rng(20261114)
    n_seeds, n_frames = 2, 7
    observation_error = rng.normal(size=(n_frames, 2))
    observation_error[:, 1] += 0.6 * observation_error[:, 0]
    transition = np.broadcast_to(np.eye(4), (n_seeds, n_frames, 4, 4)).copy()
    transition[:, 1:] += rng.normal(scale=0.1, size=transition[:, 1:].shape)
    jacobian = rng.normal(scale=0.2, size=(n_seeds, n_frames, 2, 4))
    gain = rng.normal(scale=0.1, size=(n_seeds, n_frames, 4, 2))
    accepted = rng.random((n_seeds, n_frames)) > 0.2
    checkpoints = np.array([0, 3, 6])
    transport = heading_transport(transition, jacobian, gain, accepted, checkpoints)

    k, j = 1, 0
    pulse_effect = np.zeros(4)
    pulse_heading = []
    for step in range(n_frames):
        pulse_effect = transition[1, step] @ pulse_effect
        if accepted[1, step]:
            observation_pulse = np.zeros(2)
            if step == k:
                observation_pulse[j] = 1.0
            pulse_effect += gain[1, step] @ (observation_pulse - jacobian[1, step] @ pulse_effect)
        if step in checkpoints:
            pulse_heading.append(pulse_effect[2])
    np.testing.assert_allclose(transport[1, :, k, j], pulse_heading, atol=1e-14, rtol=0)

    e = observation_error - observation_error.mean(axis=0)
    lag = [e[delta:].T @ e[:n_frames-delta] / n_frames for delta in range(n_frames)]
    cov = np.block([[lag[i-j] if i >= j else lag[j-i].T for j in range(n_frames)]
                    for i in range(n_frames)])
    diag_cov = np.kron(np.eye(n_frames), lag[0])
    g = transport.reshape(n_seeds, len(checkpoints), 2 * n_frames)
    v_full, v_diag, _ = transferred_variances(transport, observation_error)
    dense_full = np.einsum("...i,ij,...j->...", g, cov, g)
    dense_diag = np.einsum("...i,ij,...j->...", g, diag_cov, g)
    np.testing.assert_allclose(v_full, dense_full, atol=1e-14, rtol=0)
    np.testing.assert_allclose(v_diag, dense_diag, atol=1e-14, rtol=0)
    # Independent frames with same-frame range/s covariance. Directly evaluate
    # G Σ G^T and zero its off-frame blocks; both projections must coincide.
    independent_cov = cov.copy()
    packet = np.repeat(np.arange(n_frames), 2)
    independent_cov[packet[:, None] != packet] = 0.0
    independent_full = np.einsum("...i,ij,...j->...", g, independent_cov, g)
    np.testing.assert_allclose(independent_full - dense_diag, 0.0, atol=1e-14, rtol=0)
    for m in THINNING_INTERVALS:
        hits = np.stack([joint_mask(19, m, p) for p in range(m)]).sum(axis=0)
        np.testing.assert_array_equal(hits, np.ones(19, dtype=int))
    return {
        "status": "PASS",
        "reverse_transport_max_abs_error": float(
            np.max(np.abs(transport[1, :, k, j] - np.asarray(pulse_heading)))),
        "dense_vs_fft_max_abs_error": float(np.max(np.abs(v_full - dense_full))),
        "diagonal_max_abs_error": float(np.max(np.abs(v_diag - dense_diag))),
        "independent_packet_cross_max_abs_error": float(np.max(np.abs(independent_full - dense_diag))),
        "phase_configs": len(phase_configs()),
    }
