from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Iterable

import numpy as np

from .core import C0
from .designed_stress import (
    BW_HZ,
    DS1V3_LOCK_MAX_ARRIVAL_AR_DB,
    DS1V3_LOCK_MIN_CO_SEPARATION_DB,
    DS1V3_LOCK_MIN_P95_REDUCTION_M,
    DS1V3_LOCK_MIN_TAIL_REDUCTION,
    LP_LE_THRESHOLDS,
    PatternBundle,
    _NonidealityProfile,
    _channel_reflection_amplitudes,
    _cp_window_features,
    _detect_error_m,
    _direct_cross_amplitude,
    _direct_tap_index,
    _linear_crossing_dist,
    _max_abs,
    _mislock_histogram_from_errors,
    _pulse,
    _quantile_abs,
    _rng_for,
    _tail_rate,
    _variance,
    build_path_records,
    buildability_metrics,
    load_pattern_bundle,
    make_geometry,
    material_table,
    read_csv_rows,
    write_csv,
    write_json,
)


SCHEMA_VERSION = "DS1V5_MULTIPATH.v1"


@dataclass(frozen=True)
class DS1v5Config:
    source_run_root: str
    output_root: str
    pattern_mode: str = "ffd-pol"
    top_k: int = 20
    max_components_per_d: int = 24
    max_pairs: int = 0
    n_phi: int = 32
    n_noise: int = 24
    snr_db: float = 30.0
    noise_seed: int = 20260619
    shard_index: int = 0
    shard_count: int = 1
    allow_asymmetry: bool = False
    same_material_only: bool = False


@dataclass(frozen=True)
class MultipathComponent:
    geometry_id: str
    source_table: str
    source_rank: int
    source_score: float
    material: str
    D_m: float
    u: float
    wall_tilt_deg: float
    at_asymmetry_frac: float
    theta_deg: float
    actual_u: float
    actual_delta_d_m: float
    fixture_plate_span_m: float
    buildability_reasons: str


@dataclass(frozen=True)
class MultipathPair:
    pair_id: str
    component_a: MultipathComponent
    component_b: MultipathComponent
    source_score: float


def command_line_text() -> str:
    return " ".join(Path(arg).name if idx == 0 else str(arg) for idx, arg in enumerate(sys.argv))


def run_ds1v5_multipath_search(config: DS1v5Config, command_line: str | None = None) -> dict[str, object]:
    source_run = Path(config.source_run_root).resolve()
    output_root = Path(config.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    pattern = load_pattern_bundle(Path.cwd(), config.pattern_mode)
    components = load_components(source_run, config)
    pairs = build_pairs(components, config)
    pairs = _shard_sequence(pairs, config.shard_index, config.shard_count)

    rows: list[dict[str, object]] = []
    sample_profiles = [
        _NonidealityProfile("ideal"),
        _NonidealityProfile("severe_nonideal", axial_ratio_db=6.0, switch_iso_db=25.0, gain_mismatch_db=1.5, group_delay_ps=60.0),
    ]
    for idx, pair in enumerate(pairs, start=1):
        ideal = simulate_pair(pair, pattern, config, sample_profiles[0])
        severe = simulate_pair(pair, pattern, config, sample_profiles[1])
        row = dict(ideal)
        row.update(
            {
                "rank_source_order": int(idx),
                "E_mit_measured_lo": severe["E_mit"],
                "E_mit_db_measured_lo": severe["E_mit_db"],
                "rank_score_measured_lo": severe["rank_score"],
                "target_lock_score_measured_lo": severe["target_lock_score"],
                "target_lock_gate_pass_measured_lo": severe["target_lock_gate_pass"],
                "target_lock_lp_failure_pass_measured_lo": severe["target_lock_lp_failure_pass"],
                "target_lock_co_separation_pass_measured_lo": severe["target_lock_co_separation_pass"],
                "target_lock_arrival_ar_pass_measured_lo": severe["target_lock_arrival_ar_pass"],
                "co_separation_margin_db_measured_lo": severe["co_separation_margin_db"],
                "arrival_axial_ratio_db_measured_lo": severe["arrival_axial_ratio_db"],
                "tail_reduction_abs_gt_0p3m_measured_lo": severe["tail_reduction_abs_gt_0p3m"],
                "p95_reduction_m_measured_lo": severe["p95_reduction_m"],
                "var_co_dw1000_m2_measured_lo": severe["var_co_dw1000_m2"],
                "var_noise_floor_m2_measured_lo": severe["var_noise_floor_m2"],
            }
        )
        rows.append(row)

    rows = sorted(rows, key=_target_sort_key)
    candidate_path = output_root / "DS1v5_multipath_candidates.csv"
    target_path = output_root / "DS1v5_measurement_targets.csv"
    report_path = output_root / "DS1v5_multipath_report.md"
    manifest_path = output_root / "DS1v5_manifest.json"
    write_csv(candidate_path, rows)
    write_csv(target_path, rows[: max(int(config.top_k), 0)])
    report_path.write_text(_report_markdown(source_run, rows, config), encoding="utf-8")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "created_at_utc": _now_utc(),
        "command_line": command_line or command_line_text(),
        "config": asdict(config),
        "source_run_root": str(source_run),
        "component_count": len(components),
        "pair_count_after_shard": len(pairs),
        "candidate_count": len(rows),
        "target_count": min(len(rows), int(config.top_k)),
        "pattern_mode": pattern.mode,
        "output_files": [_path_record(path) for path in (candidate_path, target_path, report_path)],
        "claim_boundary": [
            "Paper 1 simulation search only",
            "bounded multipath fixture candidates are not measurement evidence",
            "not a full-wave channel solve",
            "does not claim CP directly reduces range error",
        ],
    }
    write_json(manifest_path, manifest)
    return {
        "output_root": str(output_root),
        "source_run_root": str(source_run),
        "component_count": len(components),
        "pair_count_after_shard": len(pairs),
        "candidate_count": len(rows),
        "target_count": min(len(rows), int(config.top_k)),
        "target_lock_pass_count": sum(_truthy(row.get("target_lock_gate_pass_measured_lo", "False")) for row in rows),
        "positive_measured_lo_count": sum(float(row.get("E_mit_db_measured_lo", -999.0)) > 0.0 for row in rows),
        "outputs": [str(candidate_path), str(target_path), str(report_path), str(manifest_path)],
    }


def load_components(source_run_root: Path, config: DS1v5Config) -> list[MultipathComponent]:
    rows: list[tuple[str, dict[str, str]]] = []
    for rel in ("phase2/phase2_decoupled_sweeps.csv", "phase1/phase1_geometry_metrics.csv"):
        path = source_run_root / rel
        if path.exists():
            rows.extend((rel, row) for row in read_csv_rows(path))
    mats = material_table()
    components: list[MultipathComponent] = []
    seen: set[str] = set()
    for source_table, row in rows:
        material = str(row.get("material", row.get("m", "")))
        if material not in mats:
            continue
        at_asym = _num(row, "at_asymmetry_frac", default=0.0)
        if not config.allow_asymmetry and abs(at_asym) > 1.0e-12:
            continue
        D_m = _num(row, "D_m", "D")
        u = _num(row, "u")
        wall_tilt = _num(row, "wall_tilt_deg", default=0.0)
        geom = make_geometry(material, mats[material], D_m, u, BW_HZ, 6.5e9, wall_tilt_deg=wall_tilt, at_asymmetry_frac=at_asym)
        build = buildability_metrics(geom)
        if str(build["buildability_pass"]).lower() != "true":
            continue
        gid = str(geom.geometry_id)
        if gid in seen:
            continue
        seen.add(gid)
        score = _component_score(row)
        components.append(
            MultipathComponent(
                geometry_id=gid,
                source_table=source_table,
                source_rank=int(float(row.get("rank", row.get("rank_source_order", len(components) + 1)) or len(components) + 1)),
                source_score=float(score),
                material=material,
                D_m=float(D_m),
                u=float(u),
                wall_tilt_deg=float(wall_tilt),
                at_asymmetry_frac=float(at_asym),
                theta_deg=float(geom.theta_deg),
                actual_u=float(build["actual_u"]),
                actual_delta_d_m=float(build["actual_delta_d_m"]),
                fixture_plate_span_m=float(build["fixture_plate_span_m"]),
                buildability_reasons=str(build["buildability_reasons"]),
            )
        )
    selected: list[MultipathComponent] = []
    for D_m in sorted({round(comp.D_m, 9) for comp in components}):
        pool = [comp for comp in components if abs(comp.D_m - D_m) <= 1.0e-9]
        pool = sorted(pool, key=lambda comp: (-comp.source_score, comp.material, comp.geometry_id))
        selected.extend(pool[: max(int(config.max_components_per_d), 1)])
    return selected


def build_pairs(components: list[MultipathComponent], config: DS1v5Config) -> list[MultipathPair]:
    pairs: list[MultipathPair] = []
    for D_m in sorted({round(comp.D_m, 9) for comp in components}):
        pool = [comp for comp in components if abs(comp.D_m - D_m) <= 1.0e-9]
        for comp_a, comp_b in combinations(pool, 2):
            if config.same_material_only and comp_a.material != comp_b.material:
                continue
            if abs(comp_a.actual_delta_d_m - comp_b.actual_delta_d_m) < 0.02:
                continue
            pair_id = _pair_id(comp_a, comp_b)
            pairs.append(MultipathPair(pair_id, comp_a, comp_b, comp_a.source_score + comp_b.source_score))
    pairs = sorted(pairs, key=lambda pair: (-pair.source_score, pair.pair_id))
    if int(config.max_pairs) > 0:
        pairs = pairs[: int(config.max_pairs)]
    return pairs


def simulate_pair(
    pair: MultipathPair,
    pattern: PatternBundle,
    config: DS1v5Config,
    profile: _NonidealityProfile,
) -> dict[str, object]:
    mats = material_table()
    geoms = [
        make_geometry(comp.material, mats[comp.material], comp.D_m, comp.u, BW_HZ, 6.5e9, comp.wall_tilt_deg, comp.at_asymmetry_frac)
        for comp in (pair.component_a, pair.component_b)
    ]
    direct, _ref0 = build_path_records(geoms[0])
    path_payloads = []
    arrival_ar_vals: list[float] = []
    arrival_xpd_vals: list[float] = []
    for geom in geoms:
        comp_direct, reflected = build_path_records(geom)
        channel = _channel_reflection_amplitudes(
            geom,
            reflected,
            comp_direct,
            pattern,
            max(float(geom.rho), 0.0),
            geom.theta_deg,
            xpol_degradation_db=profile.xpol_degradation_db,
        )
        path_payloads.append((geom, reflected, channel))
        arrival_ar_vals.append(float(channel.get("arrival_axial_ratio_db", float("nan"))))
        arrival_xpd_vals.append(float(channel.get("arrival_xpd_db", float("nan"))))
    direct_cross_amp = _direct_cross_amplitude(pattern, direct, profile)
    phase_values = np.linspace(0.0, 2.0 * math.pi, max(int(config.n_phi), 1), endpoint=False)
    n_noise = max(int(config.n_noise), 1)
    snr_eff_db = float(config.snr_db) - float(profile.snr_penalty_db)

    lp_errors_by_threshold: dict[float, list[float]] = {thr: [] for thr in LP_LE_THRESHOLDS}
    lp_dw1000_errors: list[float] = []
    co_errors: list[float] = []
    co_floor_errors: list[float] = []
    xpr_late_scores: list[float] = []
    xpr_clean_scores: list[float] = []
    s3_late_scores: list[float] = []
    s3_clean_scores: list[float] = []

    for phi_idx, phi in enumerate(phase_values):
        phases = _pair_phases(pair.pair_id, float(phi))
        for noise_idx in range(n_noise):
            lp_payload = _make_multipath_cir(
                geoms[0],
                path_payloads,
                "lp",
                phases,
                snr_eff_db,
                _rng_for(config.noise_seed, pair.pair_id, profile.profile_id, "lp", phi_idx, noise_idx),
                direct_amp=1.0,
                reflected_delay_bias_m=profile.delay_bias_m,
                pulse_width_scale=profile.pulse_width_scale,
            )
            co_payload = _make_multipath_cir(
                geoms[0],
                path_payloads,
                "cp_co",
                phases,
                snr_eff_db,
                _rng_for(config.noise_seed, pair.pair_id, profile.profile_id, "co", phi_idx, noise_idx),
                direct_amp=1.0,
                reflected_delay_bias_m=profile.delay_bias_m,
                pulse_width_scale=profile.pulse_width_scale,
            )
            cross_payload = _make_multipath_cir(
                geoms[0],
                path_payloads,
                "cp_cross",
                phases,
                snr_eff_db,
                _rng_for(config.noise_seed, pair.pair_id, profile.profile_id, "cross", phi_idx, noise_idx),
                direct_amp=direct_cross_amp,
                reflected_delay_bias_m=profile.delay_bias_m,
                pulse_width_scale=profile.pulse_width_scale,
            )
            co_floor_payload = _make_multipath_cir(
                geoms[0],
                [],
                "cp_co",
                (),
                snr_eff_db,
                _rng_for(config.noise_seed, pair.pair_id, profile.profile_id, "co_floor", phi_idx, noise_idx),
                direct_amp=1.0,
            )
            cross_clean_payload = _make_multipath_cir(
                geoms[0],
                [],
                "cp_cross",
                (),
                snr_eff_db,
                _rng_for(config.noise_seed, pair.pair_id, profile.profile_id, "cross_clean", phi_idx, noise_idx),
                direct_amp=direct_cross_amp,
            )
            for thr in LP_LE_THRESHOLDS:
                _idx, err = _detect_error_m(geoms[0], lp_payload, "leading_edge", threshold=thr)
                lp_errors_by_threshold[thr].append(err)
            _lp_idx, lp_dw_err = _detect_error_m(geoms[0], lp_payload, "dw1000_lde")
            _co_idx, co_err = _detect_error_m(geoms[0], co_payload, "dw1000_lde")
            _floor_idx, floor_err = _detect_error_m(geoms[0], co_floor_payload, "dw1000_lde")
            lp_dw1000_errors.append(lp_dw_err)
            co_errors.append(co_err)
            co_floor_errors.append(floor_err)
            feature_center = min(float(reflected.path_length_m) for _geom, reflected, _channel in path_payloads)
            xpr_late, s3_late = _cp_window_features(co_payload, cross_payload, feature_center)
            xpr_clean, s3_clean = _cp_window_features(co_floor_payload, cross_clean_payload, geoms[0].d0_m)
            xpr_late_scores.append(xpr_late)
            xpr_clean_scores.append(xpr_clean)
            s3_late_scores.append(s3_late)
            s3_clean_scores.append(s3_clean)

    lp_vars = {thr: _variance(vals) for thr, vals in lp_errors_by_threshold.items()}
    best_thr = min(lp_vars, key=lambda thr: (lp_vars[thr], thr))
    lp_best_errors = lp_errors_by_threshold[best_thr]
    var_lp_best = lp_vars[best_thr]
    var_lp_dw1000 = _variance(lp_dw1000_errors)
    var_co = _variance(co_errors)
    var_noise_floor = _variance(co_floor_errors)
    denominator = max(var_co, var_noise_floor, 1.0e-12)
    e_mit_best_tuned = max(var_lp_best, var_noise_floor) / denominator
    e_mit_same_detector = max(var_lp_dw1000, var_noise_floor) / denominator
    e_mit = min(e_mit_best_tuned, e_mit_same_detector)
    e_mit_db = 10.0 * math.log10(max(e_mit, 1.0e-12))
    tail_lp_03 = _tail_rate(lp_best_errors, 0.3)
    tail_co_03 = _tail_rate(co_errors, 0.3)
    p95_lp = _quantile_abs(lp_best_errors, 0.95)
    p95_co = _quantile_abs(co_errors, 0.95)
    lp_failure_db = 10.0 * math.log10(max(max(var_lp_best, var_noise_floor), 1.0e-15) / max(var_noise_floor, 1.0e-15))
    co_noise_margin_db = 10.0 * math.log10(max(max(var_co, var_noise_floor), 1.0e-15) / max(var_noise_floor, 1.0e-15))
    co_separation_margin_db = float(lp_failure_db - co_noise_margin_db)
    arrival_ar_db = _finite_max(arrival_ar_vals)
    arrival_xpd_db = _finite_min(arrival_xpd_vals)
    lock_lp_ok = bool((tail_lp_03 - tail_co_03) >= DS1V3_LOCK_MIN_TAIL_REDUCTION and (p95_lp - p95_co) >= DS1V3_LOCK_MIN_P95_REDUCTION_M)
    lock_sep_ok = bool(math.isfinite(co_separation_margin_db) and co_separation_margin_db >= DS1V3_LOCK_MIN_CO_SEPARATION_DB)
    lock_ar_ok = bool(math.isfinite(arrival_ar_db) and arrival_ar_db <= DS1V3_LOCK_MAX_ARRIVAL_AR_DB)
    target_lock_pass = bool(lock_lp_ok and lock_sep_ok and lock_ar_ok)
    penalty = 0.0
    if not lock_lp_ok:
        penalty += 20.0
    if not lock_sep_ok:
        penalty += max(0.0, DS1V3_LOCK_MIN_CO_SEPARATION_DB - co_separation_margin_db)
    if not lock_ar_ok:
        penalty += max(0.0, arrival_ar_db - DS1V3_LOCK_MAX_ARRIVAL_AR_DB)
    target_lock_score = float(e_mit_db - penalty)
    hist = _mislock_histogram_from_errors(lp_best_errors, _direct_tap_index(geoms[0]), geoms[0])
    reflected_lengths = [float(reflected.path_length_m) for _geom, reflected, _channel in path_payloads]
    actual_deltas = [float(length - geoms[0].d0_m) for length in reflected_lengths]
    fixture_spans = [pair.component_a.fixture_plate_span_m, pair.component_b.fixture_plate_span_m]
    endpoint_margins = [float(buildability_metrics(geom)["specular_endpoint_margin_m"]) for geom in geoms]
    auc = _auc_safe(xpr_clean_scores + xpr_late_scores, [0] * len(xpr_clean_scores) + [1] * len(xpr_late_scores))
    return {
        "schema_version": SCHEMA_VERSION,
        "pair_id": pair.pair_id,
        "component_a_id": pair.component_a.geometry_id,
        "component_b_id": pair.component_b.geometry_id,
        "component_a_material": pair.component_a.material,
        "component_b_material": pair.component_b.material,
        "D_m": pair.component_a.D_m,
        "u_a": pair.component_a.u,
        "u_b": pair.component_b.u,
        "actual_u_a": pair.component_a.actual_u,
        "actual_u_b": pair.component_b.actual_u,
        "actual_delta_a_m": actual_deltas[0],
        "actual_delta_b_m": actual_deltas[1],
        "delta_separation_m": abs(actual_deltas[0] - actual_deltas[1]),
        "theta_a_deg": pair.component_a.theta_deg,
        "theta_b_deg": pair.component_b.theta_deg,
        "wall_tilt_a_deg": pair.component_a.wall_tilt_deg,
        "wall_tilt_b_deg": pair.component_b.wall_tilt_deg,
        "fixture_plate_span_max_m": max(fixture_spans),
        "specular_endpoint_margin_min_m": min(endpoint_margins),
        "source_score_sum": pair.source_score,
        "nonideality_profile": profile.profile_id,
        "n_phi": int(config.n_phi),
        "n_noise": int(config.n_noise),
        "snr_db": float(config.snr_db),
        "pattern_mode": pattern.mode,
        "E_mit_best_tuned": e_mit_best_tuned,
        "E_mit_same_detector": e_mit_same_detector,
        "E_mit": e_mit,
        "E_mit_db": e_mit_db,
        "rank_score": target_lock_score,
        "target_lock_score": target_lock_score,
        "target_lock_gate_pass": str(target_lock_pass),
        "target_lock_lp_failure_pass": str(lock_lp_ok),
        "target_lock_co_separation_pass": str(lock_sep_ok),
        "target_lock_arrival_ar_pass": str(lock_ar_ok),
        "var_lp_best_m2": var_lp_best,
        "var_lp_dw1000_m2": var_lp_dw1000,
        "var_co_dw1000_m2": var_co,
        "var_noise_floor_m2": var_noise_floor,
        "lp_best_threshold": best_thr,
        "tail_rate_abs_gt_0p3m": tail_lp_03,
        "co_tail_rate_abs_gt_0p3m": tail_co_03,
        "tail_reduction_abs_gt_0p3m": float(tail_lp_03 - tail_co_03),
        "p95_abs_error_m": p95_lp,
        "co_p95_abs_error_m": p95_co,
        "p95_reduction_m": float(p95_lp - p95_co),
        "co_separation_margin_db": co_separation_margin_db,
        "arrival_axial_ratio_db": arrival_ar_db,
        "arrival_xpd_db": arrival_xpd_db,
        "E_id": auc,
        "mean_xpr_clean_db": float(np.mean(xpr_clean_scores)) if xpr_clean_scores else float("nan"),
        "mean_xpr_late_db": float(np.mean(xpr_late_scores)) if xpr_late_scores else float("nan"),
        "mislock_direct": hist.get("direct", 0),
        "mislock_m1_advance": hist.get("m1_advance", 0),
        "mislock_late_jump": hist.get("late_jump", 0),
        "single_reflector_error_ceiling_m": _max_abs(lp_best_errors),
        "claim_status": "SIMULATION_ONLY_NOT_MEASUREMENT_EVIDENCE",
    }


def _make_multipath_cir(
    reference_geometry,
    path_payloads,
    channel_key: str,
    phases: Iterable[float],
    snr_db: float | None,
    rng: np.random.Generator,
    direct_amp: float = 1.0,
    reflected_delay_bias_m: float = 0.0,
    pulse_width_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    resolution_m = C0 / BW_HZ
    step_m = resolution_m / 8.0
    centers = [reference_geometry.d0_m]
    centers.extend(float(reflected.path_length_m) + float(reflected_delay_bias_m) for _geom, reflected, _channel in path_payloads)
    start = max(0.0, min(centers) - 1.5 * resolution_m)
    stop = max(centers) + 1.5 * resolution_m
    dist = np.arange(start, stop + step_m, step_m, dtype=float)
    effective_resolution = resolution_m * max(float(pulse_width_scale), 0.25)
    cir = float(direct_amp) * _pulse(dist, reference_geometry.d0_m, effective_resolution).astype(np.complex128)
    for phase, (_geom, reflected, channel) in zip(phases, path_payloads):
        amp = float(channel[channel_key])
        center = float(reflected.path_length_m) + float(reflected_delay_bias_m)
        cir = cir + amp * np.exp(1j * float(phase)) * _pulse(dist, center, effective_resolution).astype(np.complex128)
    if snr_db is not None:
        noise_rms = abs(float(direct_amp)) * 10.0 ** (-float(snr_db) / 20.0)
        noise = (noise_rms / math.sqrt(2.0)) * (rng.normal(size=cir.shape) + 1j * rng.normal(size=cir.shape))
        cir = cir + noise.astype(np.complex128)
    return dist, cir


def _pair_phases(pair_id: str, phi: float) -> tuple[float, float]:
    digest = hashlib.sha256(pair_id.encode("utf-8")).digest()
    offset = (int.from_bytes(digest[:4], "little") / float(2**32)) * 2.0 * math.pi
    return float(phi), float((phi * math.sqrt(2.0) + offset) % (2.0 * math.pi))


def _component_score(row: dict[str, str]) -> float:
    for key in ("target_lock_score", "rank_score", "E_mit_db_measured_lo", "E_mit_db", "E_mit_conservative_db"):
        try:
            return float(row.get(key, "nan"))
        except (TypeError, ValueError):
            continue
    return -999.0


def _target_sort_key(row: dict[str, object]) -> tuple[int, float, float, float]:
    return (
        -int(_truthy(row.get("target_lock_gate_pass_measured_lo", "False"))),
        -float(row.get("rank_score_measured_lo", -999.0)),
        -float(row.get("E_mit_db_measured_lo", -999.0)),
        -float(row.get("tail_reduction_abs_gt_0p3m_measured_lo", 0.0)),
    )


def _pair_id(comp_a: MultipathComponent, comp_b: MultipathComponent) -> str:
    ordered = sorted([comp_a.geometry_id, comp_b.geometry_id])
    digest = hashlib.sha1("|".join(ordered).encode("utf-8")).hexdigest()[:10]
    return f"mp2_D{comp_a.D_m:g}_{comp_a.material}_{comp_b.material}_{digest}".replace(".", "p")


def _num(row: dict[str, str], *keys: str, default: float = float("nan")) -> float:
    for key in keys:
        if key in row and str(row[key]).strip() != "":
            return float(row[key])
    return float(default)


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "pass", "supported"}


def _finite_max(values: Iterable[float]) -> float:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    return max(vals) if vals else float("nan")


def _finite_min(values: Iterable[float]) -> float:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    return min(vals) if vals else float("nan")


def _auc_safe(scores: list[float], labels: list[int]) -> float:
    try:
        from .designed_stress import auc_direction_agnostic

        return float(auc_direction_agnostic(scores, labels))
    except Exception:
        return float("nan")


def _shard_sequence(items: list, shard_index: int = 0, shard_count: int = 1) -> list:
    count = int(shard_count)
    index = int(shard_index)
    if count <= 1:
        return list(items)
    if index < 0 or index >= count:
        raise ValueError(f"shard_index must be in [0, {count - 1}], got {index}")
    return [item for i, item in enumerate(items) if i % count == index]


def _report_markdown(source_run: Path, rows: list[dict[str, object]], config: DS1v5Config) -> str:
    lock_count = sum(_truthy(row.get("target_lock_gate_pass_measured_lo", "False")) for row in rows)
    pos_count = sum(float(row.get("E_mit_db_measured_lo", -999.0)) > 0.0 for row in rows)
    top_lines = ["| rank | pair | components | E_mit_db_lo | lock | tail_red | p95_red |", "| ---: | --- | --- | ---: | --- | ---: | ---: |"]
    for rank, row in enumerate(rows[: max(int(config.top_k), 0)], start=1):
        top_lines.append(
            "| "
            + " | ".join(
                [
                    str(rank),
                    str(row.get("pair_id", "")),
                    f"{row.get('component_a_id', '')} + {row.get('component_b_id', '')}",
                    f"{float(row.get('E_mit_db_measured_lo', float('nan'))):.3f}",
                    str(row.get("target_lock_gate_pass_measured_lo", "")),
                    f"{float(row.get('tail_reduction_abs_gt_0p3m_measured_lo', float('nan'))):.3f}",
                    f"{float(row.get('p95_reduction_m_measured_lo', float('nan'))):.3f}",
                ]
            )
            + " |"
        )
    return "\n".join(
        [
            "# DS1-v5 Bounded Multipath Fixture Search",
            "",
            f"Source DS1-v4 run: `{source_run}`",
            "",
            "## Decision Scope",
            "",
            "This is a Paper 1 simulation search for measurement-friendly multipath fixture candidates. It is not measured evidence and not a full-wave channel solve.",
            "",
            "## Counts",
            "",
            f"- Candidate pairs evaluated in this shard/run: {len(rows)}",
            f"- Positive measured-lo E rows: {pos_count}",
            f"- Target-lock pass rows: {lock_count}",
            "",
            "## Top Candidates",
            "",
            *top_lines,
            "",
            "## Boundary",
            "",
            "- Do not claim that CP directly reduces range error.",
            "- Use these rows only as simulation candidates for fixture planning.",
            "- Keep DS1-v4 single-plane negative result separate from this DS1-v5 multipath search.",
            "",
        ]
    )


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _path_record(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else None,
        "sha256": _sha256(path) if path.exists() and path.is_file() else None,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()
