from __future__ import annotations

import math

import numpy as np

from .channel import ifft_to_cir, orient_tensor

CANONICAL_FEATURE_NAMES = [
    "gamma_cp_1_freq_avg",
    "gamma_cp_2_freq_db",
    "gamma_cp_3_fp_only",
    "gamma_cp_6_phase_circvar",
    "a_fp_2_peak_to_total",
    "a_fp_6_fp_to_2nd_peak",
    "rms_delay_spread",
    "mean_excess_delay",
    "max_excess_delay",
    "fp_to_total_ratio",
    "rise_time_fp",
    "fp_kurtosis",
    "kurtosis_total",
    "skewness_total",
    "energy_concentration_50ns",
    "num_significant_peaks",
    "peak_to_avg_ratio",
    "k_factor_estimate",
]

CP16_FEATURE_NAMES = [
    "xpr_fp_db",
    "xpr_late_db",
    "xpr_all_db",
    "s3_fp",
    "s3_late",
    "s3_all",
    "delta_tau_l_given_r_s",
    "delta_p_l_given_r_db",
    "f_r_fp",
    "f_l_fp",
    "delta_f_l_minus_r_fp",
    "lambda_l_late_fraction",
    "gamma_anchor_linear",
    "gamma_delay_linear",
    "cp_phase_slope_delay_s",
    "cp_phase_residual_circvar",
]

# LP-basis (H/V) features computed from the same CP channel pair via unitary transform.
# Physics: for RHCP TX, both LoS and odd-bounce produce |H_H|^2 ≈ |H_V|^2 (XPR_HV ≈ 0 dB).
# Exception: Brewster-angle odd-bounce → reflected wave is LP (H-only) → XPR_HV >> 0 dB.
LP3_FEATURE_NAMES = [
    "xpr_hv_fp_db",   # 10·log10(e_H_fp / e_V_fp) — LP XPR at FP window
    "s3_hv_fp",       # (e_H_fp − e_V_fp)/(e_H_fp + e_V_fp) — LP Stokes S3 at FP
    "tau_hv_onset_s", # t(H_fp) − t(V_fp) — LP FP timing difference
]

# L2b coherent LP: cross-coherence Re/Im(h_H · h_V*) at FP window.
# Physics: requires simultaneous dual-LP RX to preserve phase; switched single-RX loses Im.
# Both features ≈ 0 for RHCP TX in LoS-dominated FP window (h_H ≈ h_V, Im ≈ 0).
# Stokes S3 in LP basis = −2·Im(h_H·h_V*) — here captured as im_hv_xp_fp.
LP2B_FEATURE_NAMES = [
    "re_hv_xp_fp",  # Re(Σ h_H·h_V*) / (e_H_fp + e_V_fp) — normalised cross-coherence, real part
    "im_hv_xp_fp",  # Im(Σ h_H·h_V*) / (e_H_fp + e_V_fp) — normalised cross-coherence, imag part
]

LP_L2B_FEATURE_NAMES = LP3_FEATURE_NAMES + LP2B_FEATURE_NAMES
S0_COMBINED_TIMING_NAMES = [
    "t_s0_fp_s",
    "t_s0_peak_s",
]


def _col(x) -> np.ndarray:
    return np.asarray(x).reshape(-1)


def compute_s0_combined_cp_timing(
    H_same: np.ndarray,
    H_rev: np.ndarray,
    freqs: np.ndarray,
    window_type: str = "hann",
    fp_method: str = "leading_edge",
) -> dict:
    """Reproduce the frozen-source S0 detector from the two CP branches.

    The 40-room frozen CP and CIR models were trained on ``t_s0_fp_s`` from
    ``sqrt(|h_same|^2 + |h_rev|^2)``.  This is not the first path of a
    separately simulated LP antenna channel.  The combined magnitude is
    invariant to exchanging the two CP branch labels, while the CP features
    themselves still require an independently frozen same/rev convention.
    """

    missing = {name: float("nan") for name in S0_COMBINED_TIMING_NAMES}
    if H_same is None or H_rev is None:
        return missing
    h_same, t_axis = ifft_to_cir(H_same, freqs, window_type)
    h_rev, _ = ifft_to_cir(H_rev, freqs, window_type)
    h_same = _col(h_same)
    h_rev = _col(h_rev)
    t_axis = _col(t_axis)
    if len(h_same) == 0 or len(h_same) != len(h_rev) or len(t_axis) != len(h_same):
        return missing
    h_s0_amp = np.sqrt(np.abs(h_same) ** 2 + np.abs(h_rev) ** 2)
    idx_s0, t_s0_fp_s, _ = extract_first_path(
        h_s0_amp, t_axis, fp_method
    )
    if idx_s0 < 0 or not np.isfinite(t_s0_fp_s):
        return missing
    return {
        "t_s0_fp_s": float(t_s0_fp_s),
        "t_s0_peak_s": float(t_axis[int(np.argmax(h_s0_amp))]),
    }


def _safe_ratio(num: float, den: float) -> float:
    return float(num / den) if den > 0 else float("nan")


def _bounded(center: int, n: int, radius: int) -> np.ndarray:
    center = int(max(0, min(n - 1, center)))
    return np.arange(max(0, center - radius), min(n, center + radius + 1), dtype=int)


def _hint_to_index(value, n: int, one_based: bool = True) -> int | None:
    try:
        raw = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(raw):
        return None
    idx = int(round(raw)) - (1 if one_based else 0)
    if idx < 0 or idx >= int(n):
        return None
    return idx


def _kurtosis(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).reshape(-1)
    if x.size < 2:
        return float("nan")
    c = x - float(np.mean(x))
    s2 = float(np.mean(c**2))
    return float(np.mean(c**4) / (s2**2)) if s2 > 0 else float("nan")


def _skewness(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float).reshape(-1)
    if x.size < 2:
        return float("nan")
    c = x - float(np.mean(x))
    s2 = float(np.mean(c**2))
    return float(np.mean(c**3) / (s2 ** 1.5)) if s2 > 0 else float("nan")


def _local_peak_indices(mag: np.ndarray, min_height: float) -> list[int]:
    out = []
    for idx, val in enumerate(mag):
        left = -math.inf if idx == 0 else mag[idx - 1]
        right = -math.inf if idx == len(mag) - 1 else mag[idx + 1]
        if val >= min_height and val >= left and val > right:
            out.append(idx)
    return out


def extract_first_path(h_t: np.ndarray, t_axis: np.ndarray, method: str = "leading_edge") -> tuple[int, float, dict]:
    h = _col(h_t)
    mag = np.abs(h)
    if mag.size == 0 or float(np.max(mag)) <= 0:
        return -1, float("nan"), {"method": method, "peak_val": float("nan")}
    peak_idx = int(np.argmax(mag))
    if method.lower() in {"peak", "max_peak"}:
        idx = peak_idx
    elif method.lower() == "first_peak":
        threshold = 0.1 * float(np.max(mag))
        peaks = _local_peak_indices(mag, threshold)
        idx = int(peaks[0]) if peaks else peak_idx
    else:
        threshold = 0.3 * float(np.max(mag))
        hits = np.flatnonzero(mag >= threshold)
        idx = int(hits[0]) if hits.size else peak_idx
    return idx, float(_col(t_axis)[idx]), {"method": method, "peak_val": float(mag[peak_idx]), "threshold": float(threshold) if "threshold" in locals() else float("nan")}


# P9-1 (2026-08-07): 규약을 문자열 리터럴로 흩뿌리지 않는다. 여기가 유일한 정의다.
#   SAME   — 상호성상 옳은 규약. 새로 생성하는 모든 과학 산출에 쓴다.
#   LEGACY — 동결 산출 **재현 전용**. 새 산출에 쓰면 안 된다.
CP_BRANCH_SAME = "direct_compatible_rx_same_tx"
CP_BRANCH_LEGACY_FROZEN = "direct_compatible_rx_opposite_tx"

BRANCH_CONVENTIONS = {
    "direct_compatible_rx_opposite_tx",
    "direct_compatible_rx_same_tx",
}


def _circular_port_order(value, *, role: str) -> list[str] | None:
    """Return an explicit two-port R/L order, or ``None`` if it is ambiguous.

    Port labels are an authority boundary: guessing from a malformed order
    would silently turn a physical branch error into a feature sign flip.
    """
    if value is None:
        return None
    order = [str(x).strip().upper()[:1] for x in value]
    if len(order) != 2 or set(order) != {"R", "L"}:
        return None
    return order


def select_circular_channels(
    H_f: np.ndarray,
    freqs: np.ndarray,
    tx_hand: str = "R",
    rx_port_order=("R", "L"),
    *,
    tx_port_order=None,
    branch_convention: str,
):
    """Select direct-compatible circular channels from an Nr x Nt x Nf tensor.

    ``direct_compatible_rx_opposite_tx`` is the legacy ideal/reference
    convention.  Full-FFD channels use the independently declared
    ``direct_compatible_rx_same_tx`` convention because their imported port
    fields are already labelled in the receiver-facing physical basis.  This
    is a branch selection, not a post-hoc feature sign flip.
    """
    H = orient_tensor(H_f, len(freqs))
    rx_order = _circular_port_order(rx_port_order, role="rx")
    tx_order = _circular_port_order(tx_port_order if tx_port_order is not None else rx_port_order, role="tx")
    tx = "L" if str(tx_hand).upper().startswith("L") else "R"
    if rx_order is None or tx_order is None or branch_convention not in BRANCH_CONVENTIONS:
        return None, None, {
            "selector_status": "INVALID_PORT_OR_BRANCH_AUTHORITY",
            "branch_convention": str(branch_convention),
        }
    opposite = "R" if tx == "L" else "L"
    same_hand = opposite if branch_convention == "direct_compatible_rx_opposite_tx" else tx
    reversed_hand = tx if same_hand == opposite else opposite
    try:
        tx_port = tx_order.index(tx)
        same_rx = rx_order.index(same_hand)
        rev_rx = rx_order.index(reversed_hand)
    except ValueError:
        return None, None, {}
    if tx_port >= H.shape[1] or same_rx >= H.shape[0] or rev_rx >= H.shape[0]:
        return None, None, {}
    meta = {
        "tx_hand": tx,
        "tx_port_order": ",".join(tx_order),
        "rx_port_order": ",".join(rx_order),
        "tx_port": tx_port + 1,
        "same_rx_port": same_rx + 1,
        "reversed_rx_port": rev_rx + 1,
        "same_hand": same_hand,
        "reversed_hand": reversed_hand,
        "same_rx_hand": same_hand,
        "reversed_rx_hand": reversed_hand,
        "selector_convention": branch_convention,
        "selector_status": "PASS",
    }
    return H[same_rx, tx_port, :].reshape(-1), H[rev_rx, tx_port, :].reshape(-1), meta


def compute_gamma_cp_variants(H_cp: np.ndarray, freqs: np.ndarray, idx_fp: int, tx_handedness: str = "R", window_type: str = "hann", *, tx_port_order=None, rx_port_order=("R", "L"), branch_convention: str) -> dict:
    H_same, H_rev, _ = select_circular_channels(
        H_cp, freqs, tx_handedness, rx_port_order,
        tx_port_order=tx_port_order, branch_convention=branch_convention,
    )
    if H_same is None:
        return {k: float("nan") for k in ["gamma_cp_1_freq_avg", "gamma_cp_2_freq_db", "gamma_cp_3_fp_only", "gamma_cp_4_total_energy", "gamma_cp_5_post_fp", "gamma_cp_6_phase_circvar", "gamma_cp_6_phase_consistency"]}
    h_same, _ = ifft_to_cir(H_same, freqs, window_type)
    h_rev, _ = ifft_to_cir(H_rev, freqs, window_type)
    h_same = _col(h_same)
    h_rev = _col(h_rev)
    idx = max(0, min(len(h_same) - 1, int(round(idx_fp))))
    fp_win = _bounded(idx, len(h_same), 2)
    post = np.arange(idx, len(h_same), dtype=int)
    ratio = np.divide(np.abs(H_rev), np.abs(H_same), out=np.full_like(np.abs(H_rev), np.nan, dtype=float), where=np.abs(H_same) > 0)
    phase_diff = np.angle(h_rev[fp_win]) - np.angle(h_same[fp_win])
    circvar = float(1.0 - abs(np.mean(np.exp(1j * phase_diff))))
    return {
        "gamma_cp_1_freq_avg": float(np.nanmean(ratio)),
        "gamma_cp_2_freq_db": float(20.0 * np.log10(_safe_ratio(float(np.mean(np.abs(H_rev))), float(np.mean(np.abs(H_same)))))),
        "gamma_cp_3_fp_only": _safe_ratio(float(abs(h_rev[idx])), float(abs(h_same[idx]))),
        "gamma_cp_4_total_energy": _safe_ratio(float(np.sum(np.abs(h_rev) ** 2)), float(np.sum(np.abs(h_same) ** 2))),
        "gamma_cp_5_post_fp": _safe_ratio(float(np.sum(np.abs(h_rev[post]) ** 2)), float(np.sum(np.abs(h_same[post]) ** 2))),
        "gamma_cp_6_phase_circvar": circvar,
        "gamma_cp_6_phase_consistency": circvar,
    }


def compute_a_fp_variants(h_t: np.ndarray, idx_fp: int, t_axis: np.ndarray) -> dict:
    h = _col(h_t)
    power = np.abs(h) ** 2
    total = float(np.sum(power))
    idx = max(0, min(len(h) - 1, int(idx_fp)))
    fp_win = _bounded(idx, len(h), 2)
    dt = float(np.median(np.diff(_col(t_axis)))) if len(t_axis) > 1 else 1.0
    mag = np.abs(h)
    idx10 = np.flatnonzero(mag[: idx + 1] >= 0.1 * mag[idx])
    idx90 = np.flatnonzero(mag[: idx + 1] >= 0.9 * mag[idx])
    rise = float((idx90[0] - idx10[0]) * dt) if idx10.size and idx90.size else float("nan")
    mask = np.ones(len(h), dtype=bool)
    mask[fp_win] = False
    candidates = np.flatnonzero(mask)
    second = int(candidates[np.argmax(mag[candidates])]) if candidates.size and np.max(mag[candidates]) > 0 else -1
    return {
        "a_fp_1_norm_energy": _safe_ratio(float(np.sum(power[fp_win])), total),
        "a_fp_2_peak_to_total": _safe_ratio(float(power[idx]), total),
        "a_fp_3_peak_to_max": _safe_ratio(float(mag[idx]), float(np.max(mag))),
        "a_fp_4_kurt_local": _kurtosis(mag[fp_win]),
        "a_fp_5_rise_time": rise,
        "a_fp_6_fp_to_2nd_peak": _safe_ratio(float(mag[idx]), float(mag[second])) if second >= 0 else float("nan"),
    }


def compute_cir_baseline(h_t: np.ndarray, t_axis: np.ndarray, idx_fp: int) -> dict:
    h = _col(h_t)
    t = _col(t_axis)
    power = np.abs(h) ** 2
    total = float(np.sum(power))
    idx = max(0, min(len(h) - 1, int(idx_fp)))
    fp_win = _bounded(idx, len(h), 2)
    tau = np.maximum(t - t[idx], 0.0)
    if total > 0:
        mean_excess = float(np.sum(tau * power) / total)
        rms = float(np.sqrt(max(np.sum(((tau - mean_excess) ** 2) * power) / total, 0.0)))
    else:
        mean_excess = rms = float("nan")
    significant = power >= 0.1 * float(np.max(power))
    mag = np.abs(h)
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 1.0
    idx10 = np.flatnonzero(mag[: idx + 1] >= 0.1 * mag[idx])
    idx90 = np.flatnonzero(mag[: idx + 1] >= 0.9 * mag[idx])
    return {
        "rms_delay_spread": rms,
        "mean_excess_delay": mean_excess,
        "max_excess_delay": float(np.max(tau[significant])) if np.any(significant) else float("nan"),
        "fp_to_total_ratio": _safe_ratio(float(np.sum(power[fp_win])), total),
        "rise_time_fp": float((idx90[0] - idx10[0]) * dt) if idx10.size and idx90.size else float("nan"),
        "fp_kurtosis": _kurtosis(mag[fp_win]),
        "kurtosis_total": _kurtosis(mag),
        "skewness_total": _skewness(mag),
        "energy_concentration_50ns": _safe_ratio(float(np.sum(power[tau <= 50e-9])), total),
        "num_significant_peaks": len(_local_peak_indices(mag, 0.1 * float(np.max(mag)))),
        "peak_to_avg_ratio": _safe_ratio(float(np.max(power)), float(np.mean(power))),
        "k_factor_estimate": _safe_ratio(float(np.sum(power[fp_win])), float(total - np.sum(power[fp_win]))),
    }


def compute_lp3_from_cp_channels(
    H_same: np.ndarray,
    H_rev: np.ndarray,
    freqs: np.ndarray,
    window_type: str = "hann",
    fp_method: str = "leading_edge",
    fp_radius: int = 2,
    eps0: float = 1e-12,
) -> dict:
    """LP-basis (H/V) features from RHCP/LHCP channel pair via unitary transform.

    H_H = (H_same + H_rev) / √2
    H_V = j · (H_same − H_rev) / √2

    Returns LP3 (power-only) + L2b (cross-coherence) features.
    L2b: Re/Im(Σ h_H·h_V*) at FP window, normalised by total LP energy.

    Expected result for RHCP TX:
      Even-bounce (LoS): e_H ≈ e_V → xpr_hv ≈ 0 dB, s3_hv ≈ 0, Im(xp) ≈ 0
      Odd-bounce (NLoS): e_H ≈ e_V → xpr_hv ≈ 0 dB, s3_hv ≈ 0, Im(xp) ≈ 0
      Brewster angle:    Γ_pp → 0, reflected wave is H-LP → e_H >> e_V → xpr_hv >> 0 dB
    LP cannot distinguish LoS from odd-bounce via either power or coherence
    (LoS dominates FP window → dilutes any Brewster coherence signature).
    """
    nan_dict = {n: float("nan") for n in LP_L2B_FEATURE_NAMES}
    if H_same is None or H_rev is None:
        return nan_dict
    H_H = (H_same + H_rev) / np.sqrt(2.0)
    H_V = 1j * (H_same - H_rev) / np.sqrt(2.0)
    h_H, t = ifft_to_cir(H_H, freqs, window_type)
    h_V, _ = ifft_to_cir(H_V, freqs, window_type)
    h_H = _col(h_H)
    h_V = _col(h_V)
    idx_H, _, _ = extract_first_path(h_H, t, fp_method)
    idx_V, _, _ = extract_first_path(h_V, t, fp_method)
    if idx_H < 0:
        return nan_dict
    w_H = _bounded(idx_H, len(h_H), fp_radius)
    e_H_fp = float(np.sum(np.abs(h_H[w_H]) ** 2))
    e_V_fp = float(np.sum(np.abs(h_V[w_H]) ** 2))
    dt = float(np.median(np.diff(_col(t)))) if len(t) > 1 else 1.0
    tau_hv = float((idx_V - idx_H) * dt) if idx_V >= 0 else float("nan")
    # L2b: Hermitian cross-product at FP window, normalised by total LP energy
    xp_fp = complex(np.sum(h_H[w_H] * np.conj(h_V[w_H])))
    norm = e_H_fp + e_V_fp + eps0
    return {
        "xpr_hv_fp_db": float(10.0 * np.log10((e_H_fp + eps0) / (e_V_fp + eps0))),
        "s3_hv_fp": float((e_H_fp - e_V_fp) / norm),
        "tau_hv_onset_s": tau_hv,
        "re_hv_xp_fp": float(xp_fp.real / norm),
        "im_hv_xp_fp": float(xp_fp.imag / norm),
    }


def compute_rh_lh_cp16(
    H_f: np.ndarray,
    freqs: np.ndarray,
    window_type: str = "hann",
    fp_method: str = "leading_edge",
    tx_handedness: str = "R",
    rx_port_order=("R", "L"),
    tx_port_order=None,
    # P9-1: 아래는 전부 키워드 전용 — 규약을 위치로 넘기지 못하게 한다
    *,
    branch_convention: str,
    fp_radius: int = 2,
    late_guard: int = 2,
    eps0: float = 1e-12,
    idx_same_hint_1b=None,
    idx_rev_hint_1b=None,
    swap_same_rev: bool = False,
) -> dict:
    metrics = {
        name: float("nan")
        for name in CP16_FEATURE_NAMES
        + LP_L2B_FEATURE_NAMES
        + S0_COMBINED_TIMING_NAMES
    }
    H_same, H_rev, meta = select_circular_channels(
        H_f, freqs, tx_handedness, rx_port_order,
        tx_port_order=tx_port_order, branch_convention=branch_convention,
    )
    if H_same is None:
        return metrics
    metrics.update(
        compute_s0_combined_cp_timing(
            H_same,
            H_rev,
            freqs,
            window_type=window_type,
            fp_method=fp_method,
        )
    )
    # LP3: compute from canonical (pre-swap) channels so LP features are swap-invariant
    metrics.update(compute_lp3_from_cp_channels(
        H_same, H_rev, freqs, window_type, fp_method, fp_radius, eps0))
    # U8: CIR-level handedness inversion — swap co-pol and cross-pol channels
    if swap_same_rev and H_rev is not None:
        H_same, H_rev = H_rev, H_same
    h_same, t = ifft_to_cir(H_same, freqs, window_type)
    h_rev, _ = ifft_to_cir(H_rev, freqs, window_type)
    h_same = _col(h_same)
    h_rev = _col(h_rev)
    idx_same, _, _ = extract_first_path(h_same, t, fp_method)
    idx_rev, _, _ = extract_first_path(h_rev, t, fp_method)
    idx_same_hint = _hint_to_index(idx_same_hint_1b, len(h_same)) if idx_same_hint_1b is not None else None
    idx_rev_hint = _hint_to_index(idx_rev_hint_1b, len(h_rev)) if idx_rev_hint_1b is not None else None
    if idx_same_hint is not None:
        idx_same = idx_same_hint
    if idx_rev_hint is not None:
        idx_rev = idx_rev_hint
    if idx_same < 0 or idx_rev < 0:
        return metrics
    w_same = _bounded(idx_same, len(h_same), fp_radius)
    w_rev = _bounded(idx_rev, len(h_rev), fp_radius)
    late = np.arange(idx_same + late_guard + 1, len(h_same), dtype=int)
    if late.size == 0:
        late = np.array([len(h_same) - 1])
    e_same_fp = float(np.sum(np.abs(h_same[w_same]) ** 2))
    e_rev_fp_same = float(np.sum(np.abs(h_rev[w_same]) ** 2))
    e_rev_fp_rev = float(np.sum(np.abs(h_rev[w_rev]) ** 2))
    e_same_all = float(np.sum(np.abs(h_same) ** 2))
    e_rev_all = float(np.sum(np.abs(h_rev) ** 2))
    e_same_late = float(np.sum(np.abs(h_same[late]) ** 2))
    e_rev_late = float(np.sum(np.abs(h_rev[late]) ** 2))
    dt = float(np.median(np.diff(_col(t)))) if len(t) > 1 else 1.0
    phase_slope, circvar = _phase_metrics(H_same, H_rev, freqs, eps0)
    metrics.update({
        "xpr_fp_db": float(10.0 * np.log10((e_same_fp + eps0) / (e_rev_fp_same + eps0))),
        "xpr_late_db": float(10.0 * np.log10((e_same_late + eps0) / (e_rev_late + eps0))),
        "xpr_all_db": float(10.0 * np.log10((e_same_all + eps0) / (e_rev_all + eps0))),
        "s3_fp": float((e_same_fp - e_rev_fp_same) / (e_same_fp + e_rev_fp_same + eps0)),
        "s3_late": float((e_same_late - e_rev_late) / (e_same_late + e_rev_late + eps0)),
        "s3_all": float((e_same_all - e_rev_all) / (e_same_all + e_rev_all + eps0)),
        "delta_tau_l_given_r_s": float((idx_rev - idx_same) * dt),
        "delta_p_l_given_r_db": float(10.0 * np.log10((abs(h_same[idx_same]) ** 2 + eps0) / (abs(h_rev[idx_rev]) ** 2 + eps0))),
        "f_r_fp": float(e_same_fp / (e_same_all + eps0)),
        "f_l_fp": float(e_rev_fp_rev / (e_rev_all + eps0)),
        "delta_f_l_minus_r_fp": float(e_rev_fp_rev / (e_rev_all + eps0) - e_same_fp / (e_same_all + eps0)),
        "lambda_l_late_fraction": float(e_rev_late / (e_same_all + e_rev_all + eps0)),
        "gamma_anchor_linear": float((e_rev_fp_same + eps0) / (e_same_fp + eps0)),
        "gamma_delay_linear": float((e_rev_late + eps0) / (e_same_fp + eps0)),
        "cp_phase_slope_delay_s": phase_slope,
        "cp_phase_residual_circvar": circvar,
        "cp16_idx_same_fp": idx_same + 1,
        "cp16_idx_rev_fp": idx_rev + 1,
        "cp16_t_same_fp_s": float(_col(t)[idx_same]),
        "cp16_t_rev_fp_s": float(_col(t)[idx_rev]),
        "cp16_tx_hand": meta.get("tx_hand", ""),
        "cp16_tx_port_order": meta.get("tx_port_order", ""),
        "cp16_rx_port_order": meta.get("rx_port_order", ""),
        "cp16_branch_convention": meta.get("selector_convention", ""),
    })
    return metrics


def _phase_metrics(H_same: np.ndarray, H_rev: np.ndarray, freqs: np.ndarray, eps0: float) -> tuple[float, float]:
    ratio = H_rev.reshape(-1) / (H_same.reshape(-1) + eps0)
    valid = np.isfinite(ratio) & (np.abs(H_same.reshape(-1)) > eps0) & (np.abs(H_rev.reshape(-1)) > eps0)
    if int(np.sum(valid)) < 3:
        return float("nan"), float("nan")
    phase = np.unwrap(np.angle(ratio[valid]))
    f = np.asarray(freqs, dtype=float).reshape(-1)[valid]
    coeff = np.linalg.lstsq(np.column_stack([f, np.ones_like(f)]), phase, rcond=None)[0]
    residual = phase - (coeff[0] * f + coeff[1])
    return float(-coeff[0] / (2.0 * np.pi)), float(1.0 - abs(np.mean(np.exp(1j * residual))))


def extract_all_features(
    H_f: np.ndarray,
    freqs: np.ndarray,
    window_type: str = "hann",
    fp_method: str = "leading_edge",
    feature_schema: str = "canonical18",
    tx_handedness: str = "R",
    rx_port_order=("R", "L"),
    tx_port_order=None,
    # P9-1: 아래는 전부 키워드 전용 — 규약을 위치로 넘기지 못하게 한다
    *,
    branch_convention: str,
    idx_fp_hint_1b=None,
) -> dict:
    H = orient_tensor(H_f, len(freqs))
    H_primary = H[0, 0, :]
    h_primary, t = ifft_to_cir(H_primary, freqs, window_type)
    h_primary = _col(h_primary)
    idx, t_fp, info = extract_first_path(h_primary, t, fp_method)
    hint_idx = _hint_to_index(idx_fp_hint_1b, len(h_primary)) if idx_fp_hint_1b is not None else None
    if hint_idx is not None:
        idx = hint_idx
        t_fp = float(_col(t)[idx])
        info = {**info, "peak_val": float(abs(h_primary[idx])), "hint_used": True}
    feats = {
        "idx_fp": idx + 1 if idx >= 0 else -1,
        "t_fp_s": t_fp,
        "fp_peak_val": info["peak_val"],
        "fp_method": info["method"],
        "primary_tx_port": 1,
        "primary_rx_port": 1,
        "tx_handedness": tx_handedness,
    }
    if idx >= 0:
        feats.update(compute_gamma_cp_variants(
            H, freqs, idx, tx_handedness, window_type,
            tx_port_order=tx_port_order, rx_port_order=rx_port_order,
            branch_convention=branch_convention,
        ))
        feats.update(compute_a_fp_variants(h_primary, idx, t))
        feats.update(compute_cir_baseline(h_primary, t, idx))
    if feature_schema.lower() in {"canonical", "canonical18"}:
        keep = {"idx_fp", "t_fp_s", "fp_peak_val", "fp_method", "primary_tx_port", "primary_rx_port", "tx_handedness"} | set(CANONICAL_FEATURE_NAMES)
        feats = {k: v for k, v in feats.items() if k in keep}
    return feats
