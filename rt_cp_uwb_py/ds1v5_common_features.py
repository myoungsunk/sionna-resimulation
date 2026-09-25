from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

import numpy as np
import pandas as pd

from .ds1v5_bridge_schema import ChannelFeatureConfig, ComplexChannelRecord, BridgeValidationError


def _band_mask(freq_hz: np.ndarray, config: ChannelFeatureConfig) -> np.ndarray:
    mask = np.ones_like(freq_hz, dtype=bool)
    if config.band_min_hz is not None:
        mask &= freq_hz >= float(config.band_min_hz)
    if config.band_max_hz is not None:
        mask &= freq_hz <= float(config.band_max_hz)
    if int(mask.sum()) < 2:
        raise BridgeValidationError("Configured band leaves fewer than two frequency samples")
    return mask


def _window(n: int, kind: str) -> np.ndarray:
    if kind.lower() in {"none", "rect", "rectangular"}:
        return np.ones(n)
    if kind.lower() == "hann":
        return np.hanning(n)
    raise BridgeValidationError(f"Unsupported CIR window={kind!r}")


def _phase_slope(freq_hz: np.ndarray, H_f: np.ndarray) -> tuple[float, float]:
    phase = np.unwrap(np.angle(H_f))
    mag = np.abs(H_f)
    weights = np.maximum(mag, np.nanmedian(mag) * 0.1)
    try:
        slope, intercept = np.polyfit(freq_hz, phase, 1, w=weights)
    except Exception:
        slope, intercept = float("nan"), float("nan")
    return float(slope), float(intercept)


def extract_features_from_complex_channel(
    H_f: np.ndarray,
    freq_hz: np.ndarray,
    channel_id: str,
    case_id: str,
    config: ChannelFeatureConfig | None = None,
) -> dict[str, float | int | str]:
    cfg = config or ChannelFeatureConfig()
    record = ComplexChannelRecord(
        case_id=str(case_id),
        channel_id=channel_id,
        freq_hz=freq_hz,
        H_f=H_f,
        source_kind="LOCAL_MOCK",
        source_id="feature_call",
    )
    freq = record.freq_hz
    H = record.H_f
    mask = _band_mask(freq, cfg)
    freq_b = freq[mask]
    H_b = H[mask]
    win = _window(len(H_b), cfg.cir_window)
    H_w = H_b * win
    cir = np.fft.ifft(H_w)
    power = np.abs(cir) ** 2
    total_energy = float(power.sum())
    eps = float(cfg.eps)
    peak_idx = int(np.argmax(power))
    peak_mag = float(np.abs(cir[peak_idx]))
    peak_to_total = float(power[peak_idx] / max(total_energy, eps))
    delay_bins = np.arange(len(power), dtype=float)
    centroid = float(np.sum(delay_bins * power) / max(total_energy, eps))
    spread_bins = float(np.sqrt(np.sum(((delay_bins - centroid) ** 2) * power) / max(total_energy, eps)))
    bandwidth = float(freq_b[-1] - freq_b[0])
    delay_bin_ns = float(1e9 / bandwidth) if bandwidth > 0 else float("nan")
    slope, intercept = _phase_slope(freq_b, H_b)
    group_delay_ns = float(-slope / (2.0 * np.pi) * 1e9) if np.isfinite(slope) else float("nan")
    mag = np.abs(H_b)
    return {
        "case_id": str(case_id),
        "channel_id": record.channel_id,
        "n_frequency": int(len(H_b)),
        "freq_min_hz": float(freq_b[0]),
        "freq_max_hz": float(freq_b[-1]),
        "cir_first_peak_index": peak_idx,
        "cir_first_peak_mag": peak_mag,
        "cir_total_energy": total_energy,
        "cir_delay_spread_bins": spread_bins,
        "cir_delay_spread_ns": float(spread_bins * delay_bin_ns) if np.isfinite(delay_bin_ns) else float("nan"),
        "cir_peak_to_total": peak_to_total,
        "fd_mean_mag": float(np.mean(mag)),
        "fd_rms_mag": float(np.sqrt(np.mean(mag**2))),
        "fd_max_mag": float(np.max(mag)),
        "fd_phase_slope_rad_per_hz": slope,
        "fd_phase_intercept_rad": intercept,
        "fd_group_delay_ns": group_delay_ns,
    }


def _prefix_features(row: Mapping[str, object], prefix: str) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in row.items():
        if key in {"case_id", "channel_id"}:
            continue
        out[f"{prefix}{key}"] = value
    return out


def _energy(record: ComplexChannelRecord, config: ChannelFeatureConfig) -> float:
    mask = _band_mask(record.freq_hz, config)
    return float(np.sum(np.abs(record.H_f[mask]) ** 2))


def _cir_power(record: ComplexChannelRecord, config: ChannelFeatureConfig) -> np.ndarray:
    mask = _band_mask(record.freq_hz, config)
    H_b = record.H_f[mask]
    return np.abs(np.fft.ifft(H_b * _window(len(H_b), config.cir_window))) ** 2


def _window_energy(power: np.ndarray, start: int, stop: int, eps: float) -> float:
    n = len(power)
    lo = max(0, min(n, start))
    hi = max(lo, min(n, stop))
    if hi <= lo:
        return float(eps)
    return float(np.sum(power[lo:hi]))


def _xpr_s3(co_energy: float, cross_energy: float, eps: float) -> tuple[float, float]:
    co_e = max(float(co_energy), eps)
    cross_e = max(float(cross_energy), eps)
    xpr = float(10.0 * np.log10(co_e / cross_e))
    s3 = float((co_e - cross_e) / max(co_e + cross_e, eps))
    return xpr, s3


def _cp_window_features(
    co: ComplexChannelRecord,
    cross: ComplexChannelRecord,
    config: ChannelFeatureConfig,
) -> dict[str, float | str]:
    co_power = _cir_power(co, config)
    cross_power = _cir_power(cross, config)
    eps = float(config.eps)
    fp_idx = int(np.argmax(co_power + cross_power))
    fp_start, fp_stop = fp_idx, fp_idx + 1
    late_start = min(len(co_power), fp_idx + 2)
    co_all = float(np.sum(co_power))
    cross_all = float(np.sum(cross_power))
    co_fp = _window_energy(co_power, fp_start, fp_stop, eps)
    cross_fp = _window_energy(cross_power, fp_start, fp_stop, eps)
    co_late = _window_energy(co_power, late_start, len(co_power), eps)
    cross_late = _window_energy(cross_power, late_start, len(cross_power), eps)
    xpr_all, s3_all = _xpr_s3(co_all, cross_all, eps)
    xpr_fp, s3_fp = _xpr_s3(co_fp, cross_fp, eps)
    xpr_late, s3_late = _xpr_s3(co_late, cross_late, eps)
    co_features = extract_features_from_complex_channel(co.H_f, co.freq_hz, co.channel_id, co.case_id, config)
    cross_features = extract_features_from_complex_channel(cross.H_f, cross.freq_hz, cross.channel_id, cross.case_id, config)
    co_group_delay = float(co_features.get("fd_group_delay_ns", float("nan")))
    cross_group_delay = float(cross_features.get("fd_group_delay_ns", float("nan")))
    delta_delay_s = float((cross_group_delay - co_group_delay) * 1e-9) if np.isfinite(co_group_delay + cross_group_delay) else float("nan")
    delta_p_l_given_r_db = float(10.0 * np.log10(max(cross_late, eps) / max(co_fp, eps)))
    return {
        "cp_xpr_fp_db": xpr_fp,
        "cp_xpr_late_db": xpr_late,
        "cp_xpr_all_db": xpr_all,
        "cp_s3_fp": s3_fp,
        "cp_s3_late": s3_late,
        "cp_s3_all": s3_all,
        "cp_delta_tau_l_given_r_s": delta_delay_s,
        "cp_delta_p_l_given_r_db": delta_p_l_given_r_db,
        "cp_f_r_fp": float(co_fp / max(co_all, eps)),
        "cp_f_l_fp": float(cross_fp / max(cross_all, eps)),
        "cp_delta_f_l_minus_r_fp": float(cross_fp / max(cross_all, eps) - co_fp / max(co_all, eps)),
        "cp_lambda_l_late_fraction": float(cross_late / max(cross_all, eps)),
        "cp_phase_slope_delay_s": delta_delay_s,
        "feature_family_status": "CP6_CP11_DIAGNOSTIC_FROM_COMPLEX_CHANNEL",
        "missing_feature_families": "",
    }


def extract_case_features(
    records: Iterable[ComplexChannelRecord],
    config: ChannelFeatureConfig | None = None,
) -> pd.DataFrame:
    cfg = config or ChannelFeatureConfig()
    by_case: dict[tuple[str, str, str], list[ComplexChannelRecord]] = defaultdict(list)
    for record in records:
        by_case[(record.case_id, record.source_kind, record.source_id)].append(record)

    rows: list[dict[str, object]] = []
    for (case_id, source_kind, source_id), case_records in sorted(by_case.items()):
        by_channel = {r.channel_id: r for r in case_records}
        first = case_records[0]
        row: dict[str, object] = {
            "case_id": case_id,
            "source_kind": source_kind,
            "source_id": source_id,
            "solve_id": first.solve_id,
            "phase_mode": first.phase_mode,
        }

        if "LP-LP" in by_channel:
            lp = by_channel["LP-LP"]
            lp_features = extract_features_from_complex_channel(lp.H_f, lp.freq_hz, lp.channel_id, lp.case_id, cfg)
            row.update(_prefix_features(lp_features, "cir_"))

        co = by_channel.get("RHCP-RHCP") or by_channel.get("LHCP-LHCP")
        cross = by_channel.get("RHCP-LHCP") or by_channel.get("LHCP-RHCP")
        if co is not None:
            co_features = extract_features_from_complex_channel(co.H_f, co.freq_hz, co.channel_id, co.case_id, cfg)
            row.update(_prefix_features(co_features, "cp_co_"))
        if cross is not None:
            cross_features = extract_features_from_complex_channel(cross.H_f, cross.freq_hz, cross.channel_id, cross.case_id, cfg)
            row.update(_prefix_features(cross_features, "cp_cross_"))
        if co is not None and cross is not None:
            co_energy = _energy(co, cfg)
            cross_energy = _energy(cross, cfg)
            denom = max(co_energy + cross_energy, cfg.eps)
            cp_features = _cp_window_features(co, cross, cfg)
            row.update(
                {
                    "cp_co_energy": co_energy,
                    "cp_cross_energy": cross_energy,
                    "cp_xpr_db": float(10.0 * np.log10(max(co_energy, cfg.eps) / max(cross_energy, cfg.eps))),
                    "cp_s3": float((co_energy - cross_energy) / denom),
                    "cp_cross_fraction": float(cross_energy / denom),
                }
            )
            row.update(cp_features)
        rows.append(row)
    return pd.DataFrame(rows)
