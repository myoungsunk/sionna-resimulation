from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np

from .antennas import ReceiverAntennaPattern
from .core import C0, Material, PathRecord, fresnel_reflection, normalize
from .materials import materials_library


FC_HZ = 6.5e9
BW_HZ = 500e6
RHO_RD_THRESHOLD = 0.33
LP_LE_THRESHOLDS = (0.15, 0.20, 0.25, 0.30, 0.40, 0.50)
DS1V3_LOCK_MIN_CO_SEPARATION_DB = 3.0
DS1V3_LOCK_MAX_ARRIVAL_AR_DB = 6.0
DS1V3_LOCK_MIN_TAIL_REDUCTION = 0.10
DS1V3_LOCK_MIN_P95_REDUCTION_M = 0.05
DS1V4_BUILD_MAX_INCIDENCE_DEG = 70.0
DS1V4_BUILD_MIN_ENDPOINT_MARGIN_M = 0.30
DS1V4_BUILD_MAX_FIXTURE_PLATE_SPAN_M = 1.50
DS1V4_BUILD_MIN_DELTA_D_M = 0.05
DS1V4_U_PRESERVE_TOL_M = 1.0e-3
DS1_DIRECT_XPR_IDEAL_DB = 45.0
DS1_DIRECT_XPR_AEDT_DB = 15.76
DS1_PHASE_MODES = ("ensemble_stress", "physical_delay", "coherent_upper", "aedt_fitted")


@dataclass(frozen=True)
class DS1Config:
    materials: tuple[str, ...] = ("absorber", "drywall", "glass", "metal")
    distances_m: tuple[float, ...] = (2.0, 4.0, 8.0)
    u_values: tuple[float, ...] = (0.03, 0.06, 0.10, 0.18, 0.30, 0.50, 0.75, 0.95, 1.00, 1.25, 1.50, 2.00)
    n_phi_phase1: int = 16
    n_phi_phase3: int = 64
    top_k: int = 10
    frequency_hz: float = FC_HZ
    bandwidth_hz: float = BW_HZ
    pattern_mode: str = "auto"
    detector_primary: str = "DW1000_LDE_EMULATOR"
    model_scope: str = "noise_aware_image_method_go_plus_optional_hfss_pattern_not_full_wave_channel"
    phase2_wall_tilts_deg: tuple[float, ...] = (-15.0, -7.5, 0.0, 7.5, 15.0)
    phase2_at_asymmetry_frac: tuple[float, ...] = (-0.60, -0.30, 0.0, 0.30, 0.60)
    phase2_seed_k: int = 0
    snr_db_values: tuple[float, ...] = (20.0, 30.0, 40.0)
    primary_snr_db: float = 30.0
    n_noise_phase1: int = 16
    n_noise_phase3: int = 32
    noise_seed: int = 20260618
    denominator_floor_mode: str = "direct_only_noise_floor"
    primary_rank_metric: str = "E_mit_conservative_db"
    compare_run_root: str = ""
    geometry_shard_index: int = 0
    geometry_shard_count: int = 1
    phase2_shard_index: int = 0
    phase2_shard_count: int = 1
    direct_xpr_mode: str = "ideal_45dB"
    direct_xpr_db: float = DS1_DIRECT_XPR_IDEAL_DB
    direct_co_gain_db: float = 0.0
    direct_cross_gain_db: float = 0.0
    direct_phase_offset_co_m: float = 0.0
    direct_phase_offset_cross_m: float = 0.0
    phase_mode: str = "ensemble_stress"

    def subset(self) -> "DS1Config":
        return replace(
            self,
            materials=("drywall", "metal"),
            distances_m=(2.0, 8.0),
            u_values=(0.10, 0.75, 1.25),
            n_phi_phase1=8,
            n_phi_phase3=16,
            snr_db_values=(20.0, 30.0),
            primary_snr_db=30.0,
            n_noise_phase1=4,
            n_noise_phase3=8,
            phase2_seed_k=0,
            top_k=min(4, self.top_k),
            direct_xpr_mode=self.direct_xpr_mode,
            direct_xpr_db=self.direct_xpr_db,
            direct_co_gain_db=self.direct_co_gain_db,
            direct_cross_gain_db=self.direct_cross_gain_db,
            direct_phase_offset_co_m=self.direct_phase_offset_co_m,
            direct_phase_offset_cross_m=self.direct_phase_offset_cross_m,
            phase_mode=self.phase_mode,
        )


@dataclass(frozen=True)
class DS1Geometry:
    geometry_id: str
    material_key: str
    material: Material
    D_m: float
    u: float
    s_m: float
    theta_deg: float
    delta_d_m: float
    actual_delta_d_m: float
    actual_u: float
    u_preservation_error_m: float
    u_preservation_pass: bool
    d0_m: float
    dr_m: float
    rho: float
    gamma_eff_abs: float
    designed_state: str
    wall_tilt_deg: float = 0.0
    at_asymmetry_frac: float = 0.0
    at_normal_offset_m: float = 0.0
    reflection_valid: bool = True
    diagnostic_note: str = ""


@dataclass(frozen=True)
class _DS1Layout:
    anchor: np.ndarray
    tag: np.ndarray
    reflector: np.ndarray
    wall_point: np.ndarray
    wall_normal: np.ndarray
    direct_length_m: float
    reflected_length_m: float
    incidence_angle_deg: float
    at_normal_offset_m: float
    reflection_valid: bool


@dataclass(frozen=True)
class _NonidealityProfile:
    profile_id: str = "ideal"
    axial_ratio_db: float = 0.0
    switch_iso_db: float = 45.0
    gain_mismatch_db: float = 0.0
    group_delay_ps: float = 0.0

    @property
    def xpol_degradation_db(self) -> float:
        iso_term = max(0.0, 45.0 - float(self.switch_iso_db)) * 0.25
        return float(float(self.axial_ratio_db) + iso_term + 0.5 * float(self.gain_mismatch_db))

    @property
    def snr_penalty_db(self) -> float:
        return float(0.5 * float(self.gain_mismatch_db) + min(float(self.group_delay_ps) / 100.0, 3.0))

    @property
    def delay_bias_m(self) -> float:
        return float(C0 * float(self.group_delay_ps) * 1.0e-12)

    @property
    def pulse_width_scale(self) -> float:
        return float(1.0 + min(float(self.group_delay_ps) / 500.0, 0.25))


@dataclass(frozen=True)
class DirectCalibration:
    mode: str = "ideal_45dB"
    co_gain_db: dict[str, float] = field(default_factory=dict)
    cross_leakage_db: dict[str, float] = field(default_factory=dict)
    phase_offset_m: dict[str, float] = field(default_factory=dict)

    def co_gain(self, channel: str = "cp_co") -> float:
        return _cal_value(self.co_gain_db, channel, 0.0)

    def xpr_db(self, channel: str = "cp_cross") -> float:
        return _cal_value(self.cross_leakage_db, channel, DS1_DIRECT_XPR_IDEAL_DB)

    def phase_offset(self, channel: str = "cp_co") -> float:
        return _cal_value(self.phase_offset_m, channel, 0.0)


@dataclass(frozen=True)
class PatternBundle:
    mode: str
    loaded: bool
    sources: dict[str, str]
    load_notes: tuple[str, ...]
    patterns: dict[str, ReceiverAntennaPattern]
    circular_definition: str = "e_theta_plus_j_e_phi"
    fresnel_co_definition: str = "difference"
    convention_status: str = "not_applicable"

    def amplitude_ratio(
        self,
        channel: str,
        tx_dir_ref: np.ndarray,
        rx_look_ref: np.ndarray,
        tx_dir_direct: np.ndarray,
        rx_look_direct: np.ndarray,
        tx_boresight: np.ndarray,
        rx_boresight: np.ndarray,
    ) -> float:
        if not self.loaded:
            return 1.0
        key = "lp" if channel == "lp" else channel
        pattern = self.patterns.get(key)
        if pattern is None:
            return 1.0
        tx_ref = _pattern_gain_db(pattern, tx_dir_ref, tx_boresight)
        rx_ref = _pattern_gain_db(pattern, rx_look_ref, rx_boresight)
        tx_direct = _pattern_gain_db(pattern, tx_dir_direct, tx_boresight)
        rx_direct = _pattern_gain_db(pattern, rx_look_direct, rx_boresight)
        return float(10.0 ** ((tx_ref + rx_ref - tx_direct - rx_direct) / 20.0))

    @property
    def polarization_resolved(self) -> bool:
        return self.mode == "ffd_polarization_resolved"


def direct_calibration_from_config(config: DS1Config) -> DirectCalibration:
    mode = _normalize_direct_xpr_mode(config.direct_xpr_mode)
    direct_xpr_db = float(config.direct_xpr_db)
    if mode in {"aedt", "aedt_s0_calibrated"} and math.isclose(direct_xpr_db, DS1_DIRECT_XPR_IDEAL_DB):
        direct_xpr_db = DS1_DIRECT_XPR_AEDT_DB
    return DirectCalibration(
        mode=mode,
        co_gain_db={
            "default": float(config.direct_co_gain_db),
            "cp_co": float(config.direct_co_gain_db),
            "cp_co_lhcp_lhcp": float(config.direct_co_gain_db),
            "cp_cross": float(config.direct_cross_gain_db),
            "cp_cross_lhcp_rhcp": float(config.direct_cross_gain_db),
        },
        cross_leakage_db={
            "default": direct_xpr_db,
            "cp_cross": direct_xpr_db,
            "cp_cross_lhcp_rhcp": direct_xpr_db,
        },
        phase_offset_m={
            "default": float(config.direct_phase_offset_co_m),
            "cp_co": float(config.direct_phase_offset_co_m),
            "cp_co_lhcp_lhcp": float(config.direct_phase_offset_co_m),
            "cp_cross": float(config.direct_phase_offset_cross_m),
            "cp_cross_lhcp_rhcp": float(config.direct_phase_offset_cross_m),
        },
    )


def _cal_value(values: dict[str, float], channel: str, default: float) -> float:
    if channel in values:
        return float(values[channel])
    if "default" in values:
        return float(values["default"])
    return float(default)


def _normalize_direct_xpr_mode(mode: str) -> str:
    normalized = str(mode).strip().lower().replace("-", "_")
    aliases = {
        "ideal": "ideal",
        "ideal_45": "ideal_45db",
        "ideal_45db": "ideal_45db",
        "ideal_45_db": "ideal_45db",
        "aedt": "aedt",
        "aedt_s0": "aedt_s0_calibrated",
        "aedt_s0_calibrated": "aedt_s0_calibrated",
        "measured": "measured",
    }
    if normalized not in aliases:
        raise ValueError("direct_xpr_mode must be ideal, ideal_45dB, aedt, aedt_s0_calibrated, or measured")
    return aliases[normalized]


def _normalize_phase_mode(mode: str) -> str:
    normalized = str(mode).strip().lower().replace("-", "_")
    if normalized not in DS1_PHASE_MODES:
        raise ValueError(f"phase_mode must be one of {', '.join(DS1_PHASE_MODES)}")
    return normalized


def material_table() -> dict[str, Material]:
    lib = materials_library()
    out = {
        "absorber": Material(name="absorber", eps_r=1.25, tan_delta=0.85, xpol_coupling_db=18.0),
        "drywall": lib["drywall"],
        "glass": lib["glass"],
        "metal": lib["metal_pec"],
        "metal_pec": lib["metal_pec"],
        "pec": lib["metal_pec"],
        "concrete": lib["concrete"],
    }
    return out


def make_default_output_root(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return root / "results" / "designed_stress" / "DS1" / f"run_{stamp}"


def load_pattern_bundle(root: Path, mode: str = "auto") -> PatternBundle:
    mode_l = str(mode).lower()
    polar_modes = {"ffd-pol", "ffd_pol", "polarization_resolved", "polarization-resolved"}
    if mode_l not in {"auto", "analytic", "ffd", *polar_modes}:
        raise ValueError("pattern_mode must be auto, analytic, ffd, or ffd-pol")

    sources = {
        "cp_co": str(root / "RHCP_new_6G7G_11pts.ffd"),
        "cp_cross": str(root / "LHCP_new_6G7G_11pts.ffd"),
        "lp": str(root / "LP_x-axis_pol_6G7G_11pts_new.ffd"),
        "lp_cross_reference": str(root / "LP_y-axis_pol_6G7G_11pts_new.ffd"),
    }
    if mode_l == "analytic":
        return PatternBundle("analytic", False, sources, ("analytic_pattern_factors_only",), {})

    missing = [name for name, path in sources.items() if not Path(path).exists()]
    if missing:
        if mode_l == "ffd":
            raise FileNotFoundError(f"missing FFD pattern files for {', '.join(missing)}")
        return PatternBundle("analytic_fallback", False, sources, (f"missing FFD files: {', '.join(missing)}",), {})

    notes: list[str] = []
    patterns: dict[str, ReceiverAntennaPattern] = {}
    keys = ("cp_co", "cp_cross", "lp", "lp_cross_reference") if mode_l in polar_modes else ("cp_co", "cp_cross", "lp")
    for key in keys:
        path = sources[key]
        try:
            patterns[key] = ReceiverAntennaPattern.from_ffd(path, frequency_hz=None, pol_mode=key)
        except Exception as exc:
            if mode_l == "ffd" or mode_l in polar_modes:
                raise
            notes.append(f"{key} FFD load failed; analytic fallback: {exc}")
            return PatternBundle("analytic_fallback", False, sources, tuple(notes), {})
    if mode_l in polar_modes:
        lock = build_convention_lock(patterns, material_table()["metal"], FC_HZ)
        if lock["status"] != "PASS":
            raise ValueError(f"DS1v3 convention lock failed: {lock}")
        notes.append(
            "loaded HFSS FFD complex vector-field patterns; DS1v3 derives circular co/cross and axial-ratio response"
        )
        notes.append(
            f"convention={lock['circular_definition']}; fresnel_co={lock['fresnel_co_definition']}"
        )
        return PatternBundle(
            "ffd_polarization_resolved",
            True,
            sources,
            tuple(notes),
            patterns,
            str(lock["circular_definition"]),
            str(lock["fresnel_co_definition"]),
            str(lock["status"]),
        )
    notes.append("loaded first available frequency block from HFSS FFD total-field patterns")
    return PatternBundle("ffd_total_gain", True, sources, tuple(notes), patterns)


def build_convention_lock(patterns: dict[str, ReceiverAntennaPattern], pec_material: Material, frequency_hz: float) -> dict[str, float | str]:
    rhcp = patterns["cp_co"]
    lhcp = patterns["cp_cross"]
    candidates = ("e_theta_plus_j_e_phi", "e_theta_minus_j_e_phi")
    best: dict[str, float | str] | None = None
    for definition in candidates:
        rh_r, rh_l = rhcp.circular_components(0.0, 0.0, definition)
        lh_r, lh_l = lhcp.circular_components(0.0, 0.0, definition)
        rh_xpd = 20.0 * math.log10(max(abs(rh_r), 1.0e-15) / max(abs(rh_l), 1.0e-15))
        lh_xpd = 20.0 * math.log10(max(abs(lh_l), 1.0e-15) / max(abs(lh_r), 1.0e-15))
        score = min(rh_xpd, lh_xpd)
        candidate = {
            "circular_definition": definition,
            "rhcp_boresight_xpd_db": float(rh_xpd),
            "lhcp_boresight_xpd_db": float(lh_xpd),
            "rhcp_boresight_ar_db": float(rhcp.axial_ratio_db(0.0, 0.0, definition)),
            "lhcp_boresight_ar_db": float(lhcp.axial_ratio_db(0.0, 0.0, definition)),
            "score": float(score),
        }
        if best is None or score > float(best["score"]):
            best = candidate
    if best is None:
        raise ValueError("unable to evaluate circular convention candidates")

    gamma_te, gamma_tm = fresnel_reflection(pec_material, 0.0, np.asarray([frequency_hz], dtype=float))
    co_diff, cross_sum, gamma_eff = _fresnel_cp_split_values(complex(gamma_te[0]), complex(gamma_tm[0]), "difference")
    co_sum, cross_diff, _ = _fresnel_cp_split_values(complex(gamma_te[0]), complex(gamma_tm[0]), "sum")
    diff_ok = abs(co_diff) <= 1.0e-9 and abs(cross_sum) > 0.99
    sum_ok = abs(co_sum) <= 1.0e-9 and abs(cross_diff) > 0.99
    fresnel_def = "difference" if diff_ok else "sum" if sum_ok else "UNRESOLVED"
    status = "PASS" if float(best["score"]) >= 10.0 and fresnel_def != "UNRESOLVED" else "FAIL"
    best.update(
        {
            "status": status,
            "fresnel_co_definition": fresnel_def,
            "pec_normal_gamma_te": str(complex(gamma_te[0])),
            "pec_normal_gamma_tm": str(complex(gamma_tm[0])),
            "pec_normal_gamma_eff": float(gamma_eff),
            "pec_normal_co_abs": float(abs(co_diff if fresnel_def == "difference" else co_sum)),
            "pec_normal_cross_abs": float(abs(cross_sum if fresnel_def == "difference" else cross_diff)),
        }
    )
    return best


def build_geometries(config: DS1Config) -> list[DS1Geometry]:
    mats = material_table()
    out: list[DS1Geometry] = []
    for material_key in config.materials:
        if material_key not in mats:
            raise KeyError(f"unknown DS1 material {material_key!r}")
        mat = mats[material_key]
        for D_m in config.distances_m:
            for u in config.u_values:
                geom = make_geometry(material_key, mat, float(D_m), float(u), config.bandwidth_hz, config.frequency_hz)
                out.append(geom)
    return _shard_sequence(out, config.geometry_shard_index, config.geometry_shard_count)


def _shard_sequence(items: list, shard_index: int = 0, shard_count: int = 1) -> list:
    count = int(shard_count)
    index = int(shard_index)
    if count <= 1:
        return list(items)
    if index < 0 or index >= count:
        raise ValueError(f"shard_index must be in [0, {count - 1}], got {index}")
    return [item for i, item in enumerate(items) if i % count == index]


def make_geometry(
    material_key: str,
    material: Material,
    D_m: float,
    u: float,
    bandwidth_hz: float,
    frequency_hz: float,
    wall_tilt_deg: float = 0.0,
    at_asymmetry_frac: float = 0.0,
) -> DS1Geometry:
    delta_d = float(u) * C0 / float(bandwidth_hz)
    s, solver_note = _solve_s_for_target_delta(float(D_m), float(delta_d), float(wall_tilt_deg), float(at_asymmetry_frac))
    layout = _build_ds1_layout(float(D_m), float(s), float(wall_tilt_deg), float(at_asymmetry_frac))
    theta = layout.incidence_angle_deg
    dr = layout.reflected_length_m
    d0 = layout.direct_length_m
    actual_delta = float(dr - d0)
    actual_u = float(actual_delta * float(bandwidth_hz) / C0)
    u_error = float(actual_delta - delta_d)
    u_pass = bool(layout.reflection_valid and abs(u_error) <= max(DS1V4_U_PRESERVE_TOL_M, 0.01 * max(abs(delta_d), 1.0e-12)))
    gamma_te, gamma_tm = fresnel_reflection(material, math.radians(theta), np.asarray([frequency_hz], dtype=float))
    gamma_eff = math.sqrt((abs(complex(gamma_te[0])) ** 2 + abs(complex(gamma_tm[0])) ** 2) / 2.0)
    rho = (float(d0) / max(dr, 1.0e-12)) ** 2 * gamma_eff * gamma_eff
    state = "RD-LoS" if u < 1.0 and rho >= RHO_RD_THRESHOLD else "control_single_reflector"
    safe_mat = material_key.replace("_", "-")
    gid = f"{safe_mat}_D{D_m:g}_u{u:.3f}".replace(".", "p")
    if abs(float(wall_tilt_deg)) > 1.0e-12:
        gid += f"_wall{_signed_token(float(wall_tilt_deg))}"
    if abs(float(at_asymmetry_frac)) > 1.0e-12:
        gid += f"_at{_signed_token(float(at_asymmetry_frac))}"
    return DS1Geometry(
        geometry_id=gid,
        material_key=material_key,
        material=material,
        D_m=float(D_m),
        u=float(u),
        s_m=float(s),
        theta_deg=float(theta),
        delta_d_m=float(delta_d),
        actual_delta_d_m=float(actual_delta),
        actual_u=float(actual_u),
        u_preservation_error_m=float(u_error),
        u_preservation_pass=bool(u_pass),
        d0_m=float(d0),
        dr_m=float(dr),
        rho=float(rho),
        gamma_eff_abs=float(gamma_eff),
        designed_state=state,
        wall_tilt_deg=float(wall_tilt_deg),
        at_asymmetry_frac=float(at_asymmetry_frac),
        at_normal_offset_m=float(layout.at_normal_offset_m),
        reflection_valid=bool(layout.reflection_valid),
        diagnostic_note=str(solver_note),
    )


def _solve_s_for_target_delta(D_m: float, target_delta_m: float, wall_tilt_deg: float, at_asymmetry_frac: float) -> tuple[float, str]:
    target_dr = float(D_m) + float(target_delta_m)
    nominal_s_sq = max(target_dr * target_dr - float(D_m) * float(D_m), 0.0) / 4.0
    nominal_s = math.sqrt(nominal_s_sq)
    if abs(float(wall_tilt_deg)) <= 1.0e-12 and abs(float(at_asymmetry_frac)) <= 1.0e-12:
        return float(nominal_s), "u_fixed_closed_form"

    def value(s_val: float) -> tuple[float, _DS1Layout]:
        layout_val = _build_ds1_layout(float(D_m), float(s_val), float(wall_tilt_deg), float(at_asymmetry_frac))
        return float(layout_val.reflected_length_m - layout_val.direct_length_m - float(target_delta_m)), layout_val

    # A tilted infinite plane can have an invalid near-endpoint branch. Search broadly, then root only valid intervals.
    hi = max(float(D_m) * 8.0, nominal_s * 8.0, 1.0)
    grid = sorted(
        {
            1.0e-6,
            max(nominal_s, 1.0e-6),
            *[float(v) for v in np.geomspace(1.0e-5, hi, 240)],
            *[float(v) for v in np.linspace(1.0e-5, hi, 240)],
        }
    )
    samples: list[tuple[float, float, _DS1Layout]] = []
    for s_val in grid:
        try:
            f_val, layout_val = value(float(s_val))
        except Exception:
            continue
        if math.isfinite(f_val):
            samples.append((float(s_val), float(f_val), layout_val))

    roots: list[float] = []
    valid_samples = [item for item in samples if item[2].reflection_valid]
    for (s0, f0, l0), (s1, f1, l1) in zip(valid_samples, valid_samples[1:]):
        if f0 == 0.0:
            roots.append(s0)
            continue
        if f0 * f1 > 0.0:
            continue
        lo = s0
        hi_b = s1
        flo = f0
        for _ in range(80):
            mid = 0.5 * (lo + hi_b)
            fmid, lmid = value(mid)
            if not lmid.reflection_valid:
                lo = mid
                flo = fmid
                continue
            if abs(fmid) <= 1.0e-12:
                lo = hi_b = mid
                break
            if flo * fmid <= 0.0:
                hi_b = mid
            else:
                lo = mid
                flo = fmid
        roots.append(0.5 * (lo + hi_b))

    if roots:
        chosen = min(roots, key=lambda v: abs(float(v) - float(nominal_s)))
        return float(chosen), "u_fixed_numeric"

    if valid_samples:
        best_s, best_f, _best_layout = min(valid_samples, key=lambda item: (abs(item[1]), abs(item[0] - nominal_s)))
        return float(best_s), f"u_fixed_unreachable_nearest_valid_error_m={best_f:.6g}"

    return float(nominal_s), "u_fixed_unreachable_no_valid_reflection"


def _build_ds1_layout(D_m: float, s_m: float, wall_tilt_deg: float = 0.0, at_asymmetry_frac: float = 0.0) -> _DS1Layout:
    wall_tilt_rad = math.radians(float(wall_tilt_deg))
    wall_normal = normalize(np.asarray([math.sin(wall_tilt_rad), -math.cos(wall_tilt_rad), 0.0], dtype=float))
    max_offset = min(max(0.0, 0.45 * float(s_m)), max(0.0, 0.20 * float(D_m)))
    asym_frac = float(np.clip(float(at_asymmetry_frac), -0.95, 0.95))
    offset = asym_frac * max_offset

    nx = float(wall_normal[0])
    radicand = float(D_m) * float(D_m) - 4.0 * offset * offset * max(0.0, 1.0 - nx * nx)
    if radicand <= 1.0e-12:
        radicand = 1.0e-12
    x_sep = -2.0 * offset * nx + math.sqrt(radicand)

    anchor = np.asarray([0.0, 0.0, 0.0], dtype=float) - offset * wall_normal
    tag = np.asarray([x_sep, 0.0, 0.0], dtype=float) + offset * wall_normal
    wall_point = np.asarray([0.5 * x_sep, float(s_m), 0.0], dtype=float)
    reflector, valid = _specular_reflection_point(anchor, tag, wall_point, wall_normal)
    direct_len = float(np.linalg.norm(tag - anchor))
    reflected_len = float(np.linalg.norm(reflector - anchor) + np.linalg.norm(tag - reflector))
    launch = normalize(reflector - anchor)
    incidence = math.degrees(math.acos(float(np.clip(abs(float(np.dot(launch, wall_normal))), 0.0, 1.0))))
    return _DS1Layout(
        anchor=anchor,
        tag=tag,
        reflector=reflector,
        wall_point=wall_point,
        wall_normal=wall_normal,
        direct_length_m=direct_len,
        reflected_length_m=reflected_len,
        incidence_angle_deg=float(incidence),
        at_normal_offset_m=float(offset),
        reflection_valid=bool(valid),
    )


def _specular_reflection_point(anchor: np.ndarray, tag: np.ndarray, wall_point: np.ndarray, wall_normal: np.ndarray) -> tuple[np.ndarray, bool]:
    n = normalize(wall_normal)
    reflected_tag = np.asarray(tag, dtype=float) - 2.0 * float(np.dot(np.asarray(tag, dtype=float) - wall_point, n)) * n
    ray = reflected_tag - np.asarray(anchor, dtype=float)
    denom = float(np.dot(ray, n))
    if abs(denom) <= 1.0e-12:
        return np.asarray(wall_point, dtype=float), False
    t = float(np.dot(wall_point - np.asarray(anchor, dtype=float), n) / denom)
    point = np.asarray(anchor, dtype=float) + t * ray
    return point, bool(math.isfinite(t) and -1.0e-9 <= t <= 1.0 + 1.0e-9)


def build_path_records(geometry: DS1Geometry) -> tuple[PathRecord, PathRecord]:
    layout = _build_ds1_layout(geometry.D_m, geometry.s_m, geometry.wall_tilt_deg, geometry.at_asymmetry_frac)
    A = layout.anchor
    T = layout.tag
    M = layout.reflector
    direct_dir = normalize(T - A)
    direct = PathRecord(
        points=(A, T),
        surface_ids=(),
        surface_names=(),
        materials=(),
        bounce_count=0,
        path_length_m=layout.direct_length_m,
        delay_s=layout.direct_length_m / C0,
        launch_dir=direct_dir,
        arrival_dir=direct_dir,
        incidence_angles_rad=(),
        normals=(),
    )
    launch = normalize(M - A)
    arrival = normalize(T - M)
    reflected = PathRecord(
        points=(A, M, T),
        surface_ids=(1,),
        surface_names=("ds1_single_reflector",),
        materials=(geometry.material,),
        bounce_count=1,
        path_length_m=layout.reflected_length_m,
        delay_s=layout.reflected_length_m / C0,
        launch_dir=launch,
        arrival_dir=arrival,
        incidence_angles_rad=(math.radians(layout.incidence_angle_deg),),
        normals=(layout.wall_normal,),
        valid=bool(layout.reflection_valid),
    )
    return direct, reflected


def buildability_metrics(geometry: DS1Geometry) -> dict[str, float | str]:
    direct, reflected = build_path_records(geometry)
    anchor = np.asarray(direct.points[0], dtype=float)
    tag = np.asarray(direct.points[1], dtype=float)
    reflector = np.asarray(reflected.points[1], dtype=float)
    d_anchor_reflector = float(np.linalg.norm(reflector - anchor))
    d_reflector_tag = float(np.linalg.norm(tag - reflector))
    endpoint_margin = float(min(d_anchor_reflector, d_reflector_tag))
    auto_plate_width = float(max(2.0, float(geometry.D_m) + 2.0 * float(geometry.s_m) + 1.0))
    wavelength_m = float(C0 / FC_HZ)
    if reflected.valid and (d_anchor_reflector + d_reflector_tag) > 0.0:
        fresnel_radius_m = math.sqrt(max(0.0, wavelength_m * d_anchor_reflector * d_reflector_tag / (d_anchor_reflector + d_reflector_tag)))
        cos_incidence = max(1.0e-3, abs(math.cos(math.radians(float(geometry.theta_deg)))))
        fixture_plate_span = float(2.0 * fresnel_radius_m / cos_incidence)
    else:
        fresnel_radius_m = float("nan")
        fixture_plate_span = float("nan")
    actual_delta = float(reflected.path_length_m - direct.path_length_m)
    actual_u = float(actual_delta * BW_HZ / C0)
    reasons: list[str] = []
    if not reflected.valid:
        reasons.append("reflection_invalid")
    if not geometry.u_preservation_pass:
        reasons.append("u_not_preserved")
    if geometry.theta_deg > DS1V4_BUILD_MAX_INCIDENCE_DEG:
        reasons.append(f"incidence_deg>{DS1V4_BUILD_MAX_INCIDENCE_DEG:g}")
    if endpoint_margin < DS1V4_BUILD_MIN_ENDPOINT_MARGIN_M:
        reasons.append(f"endpoint_margin_m<{DS1V4_BUILD_MIN_ENDPOINT_MARGIN_M:g}")
    if math.isfinite(fixture_plate_span) and fixture_plate_span > DS1V4_BUILD_MAX_FIXTURE_PLATE_SPAN_M:
        reasons.append(f"fixture_plate_span_m>{DS1V4_BUILD_MAX_FIXTURE_PLATE_SPAN_M:g}")
    if actual_delta < DS1V4_BUILD_MIN_DELTA_D_M:
        reasons.append(f"actual_delta_d_m<{DS1V4_BUILD_MIN_DELTA_D_M:g}")
    status = "BUILDABLE" if not reasons else "UNBUILDABLE_REVIEW"
    return {
        "actual_delta_d_m": float(actual_delta),
        "actual_u": float(actual_u),
        "u_preservation_error_m": float(actual_delta - float(geometry.delta_d_m)),
        "u_preservation_pass": str(bool(geometry.u_preservation_pass)),
        "geometry_solver_status": str(geometry.diagnostic_note),
        "specular_endpoint_margin_m": float(endpoint_margin),
        "hfss_auto_plate_width_m": float(auto_plate_width),
        "fixture_fresnel_radius_m": float(fresnel_radius_m),
        "fixture_plate_span_m": float(fixture_plate_span),
        "buildability_max_incidence_deg": float(DS1V4_BUILD_MAX_INCIDENCE_DEG),
        "buildability_min_endpoint_margin_m": float(DS1V4_BUILD_MIN_ENDPOINT_MARGIN_M),
        "buildability_max_plate_width_m": float(DS1V4_BUILD_MAX_FIXTURE_PLATE_SPAN_M),
        "buildability_max_fixture_plate_span_m": float(DS1V4_BUILD_MAX_FIXTURE_PLATE_SPAN_M),
        "buildability_min_delta_d_m": float(DS1V4_BUILD_MIN_DELTA_D_M),
        "buildability_pass": str(status == "BUILDABLE"),
        "buildability_status": status,
        "buildability_reasons": ";".join(reasons) if reasons else "pass",
    }


def simulate_geometry(
    geometry: DS1Geometry,
    n_phi: int,
    pattern_bundle: PatternBundle | None = None,
    rho_scale: float = 1.0,
    theta_override_deg: float | None = None,
    include_samples: bool = False,
    snr_db: float = 30.0,
    n_noise: int = 16,
    noise_seed: int = 20260618,
    nonideality_profile: _NonidealityProfile | None = None,
    direct_calibration: DirectCalibration | None = None,
    phase_mode: str = "ensemble_stress",
) -> tuple[dict[str, float | str], list[dict[str, float | str]]]:
    pattern = pattern_bundle or PatternBundle("analytic", False, {}, (), {})
    profile = nonideality_profile or _NonidealityProfile()
    phase_mode_l = _normalize_phase_mode(phase_mode)
    direct_cal = direct_calibration or DirectCalibration()
    direct, reflected = build_path_records(geometry)
    theta_for_leakage = geometry.theta_deg if theta_override_deg is None else float(theta_override_deg)
    rho_eff = max(float(geometry.rho) * float(rho_scale), 0.0)
    phase_values = np.linspace(0.0, 2.0 * math.pi, int(n_phi), endpoint=False)
    n_noise_i = max(int(n_noise), 1)
    snr_eff_db = float(snr_db) - profile.snr_penalty_db

    lp_errors_by_threshold: dict[float, list[float]] = {thr: [] for thr in LP_LE_THRESHOLDS}
    lp_taps_by_threshold: dict[float, list[int]] = {thr: [] for thr in LP_LE_THRESHOLDS}
    lp_dw1000_errors: list[float] = []
    lp_dw1000_taps: list[int] = []
    co_errors: list[float] = []
    co_taps: list[int] = []
    co_le_errors: list[float] = []
    co_noise_floor_errors: list[float] = []
    xpr_late_scores: list[float] = []
    xpr_clean_scores: list[float] = []
    s3_late_scores: list[float] = []
    s3_clean_scores: list[float] = []
    sample_rows: list[dict[str, float | str]] = []

    channel_amp = _channel_reflection_amplitudes(
        geometry,
        reflected,
        direct,
        pattern,
        rho_eff,
        theta_for_leakage,
        xpol_degradation_db=profile.xpol_degradation_db,
    )
    direct_response = _direct_cross_response(pattern, direct, profile, direct_cal)
    direct_cross_amp = float(direct_response["direct_cross_amp"])
    direct_co_amp = float(direct_response["direct_co_amp"])
    direct_co_delay_bias_m = float(direct_response["direct_phase_offset_co_m"])
    direct_cross_delay_bias_m = float(direct_response["direct_phase_offset_cross_m"])

    for phi_idx, phi in enumerate(phase_values):
        for noise_idx in range(n_noise_i):
            lp_cir = _make_cir(
                geometry,
                channel_amp["lp"],
                float(phi),
                snr_db=snr_eff_db,
                rng=_rng_for(noise_seed, geometry.geometry_id, profile.profile_id, snr_db, phi_idx, noise_idx, "lp"),
                direct_amp=direct_co_amp,
                direct_delay_bias_m=direct_co_delay_bias_m,
                reflected_delay_bias_m=profile.delay_bias_m,
                pulse_width_scale=profile.pulse_width_scale,
            )
            co_cir = _make_cir(
                geometry,
                float(channel_amp.get("cp_co_phase_ensemble_amp", channel_amp["cp_co"])),
                float(phi),
                snr_db=snr_eff_db,
                rng=_rng_for(noise_seed, geometry.geometry_id, profile.profile_id, snr_db, phi_idx, noise_idx, "co"),
                direct_amp=direct_co_amp,
                direct_delay_bias_m=direct_co_delay_bias_m,
                reflected_delay_bias_m=profile.delay_bias_m,
                pulse_width_scale=profile.pulse_width_scale,
            )
            cross_cir = _make_cir(
                geometry,
                float(channel_amp.get("cp_cross_phase_ensemble_amp", channel_amp["cp_cross"])),
                float(phi),
                snr_db=snr_eff_db,
                rng=_rng_for(noise_seed, geometry.geometry_id, profile.profile_id, snr_db, phi_idx, noise_idx, "cross"),
                direct_amp=direct_cross_amp,
                direct_delay_bias_m=direct_cross_delay_bias_m,
                reflected_delay_bias_m=profile.delay_bias_m,
                pulse_width_scale=profile.pulse_width_scale,
            )
            co_floor_cir = _make_cir(
                geometry,
                0.0,
                0.0,
                snr_db=snr_eff_db,
                rng=_rng_for(noise_seed, geometry.geometry_id, profile.profile_id, snr_db, phi_idx, noise_idx, "co_floor"),
                direct_amp=direct_co_amp,
                direct_delay_bias_m=direct_co_delay_bias_m,
            )
            cross_clean_cir = _make_cir(
                geometry,
                0.0,
                0.0,
                snr_db=snr_eff_db,
                rng=_rng_for(noise_seed, geometry.geometry_id, profile.profile_id, snr_db, phi_idx, noise_idx, "cross_clean"),
                direct_amp=direct_cross_amp,
                direct_delay_bias_m=direct_cross_delay_bias_m,
            )

            for thr in LP_LE_THRESHOLDS:
                idx, err_m = _detect_error_m(geometry, lp_cir, "leading_edge", threshold=thr)
                lp_errors_by_threshold[thr].append(err_m)
                lp_taps_by_threshold[thr].append(idx)

            lp_dw_idx, lp_dw_err = _detect_error_m(geometry, lp_cir, "dw1000_lde")
            lp_dw1000_errors.append(lp_dw_err)
            lp_dw1000_taps.append(lp_dw_idx)

            co_idx, co_err = _detect_error_m(geometry, co_cir, "dw1000_lde")
            co_errors.append(co_err)
            co_taps.append(co_idx)
            _co_le_idx, co_le_err = _detect_error_m(geometry, co_cir, "leading_edge", threshold=0.30)
            co_le_errors.append(co_le_err)

            _floor_idx, floor_err = _detect_error_m(geometry, co_floor_cir, "dw1000_lde")
            co_noise_floor_errors.append(floor_err)

            xpr_late, s3_late = _cp_window_features(co_cir, cross_cir, geometry.dr_m)
            xpr_clean, s3_clean = _cp_window_features(co_floor_cir, cross_clean_cir, geometry.d0_m)
            xpr_late_scores.append(float(xpr_late))
            xpr_clean_scores.append(float(xpr_clean))
            s3_late_scores.append(float(s3_late))
            s3_clean_scores.append(float(s3_clean))

            if include_samples:
                sample_rows.append(
                    {
                        "geometry_id": geometry.geometry_id,
                        "phi_idx": phi_idx,
                        "noise_idx": noise_idx,
                        "phi_rad": float(phi),
                        "snr_db": float(snr_db),
                        "effective_snr_db": float(snr_eff_db),
                        "nonideality_profile": profile.profile_id,
                        "lp_le03_error_m": float(lp_errors_by_threshold[0.30][-1]),
                        "lp_dw1000_error_m": float(lp_dw_err),
                        "co_dw1000_error_m": float(co_err),
                        "co_noise_floor_error_m": float(floor_err),
                        "co_le03_error_m": float(co_le_err),
                        "xpr_late_db": float(xpr_late),
                        "xpr_clean_db": float(xpr_clean),
                        "s3_late": float(s3_late),
                        "s3_clean": float(s3_clean),
                    }
                )

    lp_vars = {thr: _variance(vals) for thr, vals in lp_errors_by_threshold.items()}
    best_thr = min(lp_vars, key=lambda thr: (lp_vars[thr], thr))
    lp_best_errors = lp_errors_by_threshold[best_thr]
    lp_best_taps = lp_taps_by_threshold[best_thr]
    var_lp_best = lp_vars[best_thr]
    var_lp_dw1000 = _variance(lp_dw1000_errors)
    var_co = _variance(co_errors)
    var_noise_floor = _variance(co_noise_floor_errors)
    denominator = max(var_co, var_noise_floor, 1.0e-12)
    e_mit_best_tuned = max(var_lp_best, var_noise_floor) / denominator
    e_mit_same_detector = max(var_lp_dw1000, var_noise_floor) / denominator
    e_mit = min(e_mit_best_tuned, e_mit_same_detector)
    e_mit_db = 10.0 * math.log10(max(e_mit, 1.0e-12))
    e_mit_legacy = (var_lp_best + 1.0e-9) / (var_co + 1.0e-9)
    worst_sample_idx = int(np.argmax(np.abs(np.asarray(lp_best_errors, dtype=float)))) if lp_best_errors else 0
    phi_worst_idx = int(min(len(phase_values) - 1, max(0, worst_sample_idx // n_noise_i))) if len(phase_values) else 0
    direct_tap = _direct_tap_index(geometry)
    hist = _mislock_histogram_from_errors(lp_best_errors, direct_tap, geometry)
    auc = auc_direction_agnostic(xpr_clean_scores + xpr_late_scores, [0] * len(xpr_clean_scores) + [1] * len(xpr_late_scores))
    tail_lp_03 = _tail_rate(lp_best_errors, 0.3)
    tail_co_03 = _tail_rate(co_errors, 0.3)
    p95_lp = _quantile_abs(lp_best_errors, 0.95)
    p95_co = _quantile_abs(co_errors, 0.95)
    lp_failure_db = 10.0 * math.log10(max(max(var_lp_best, var_noise_floor), 1.0e-15) / max(var_noise_floor, 1.0e-15))
    co_noise_margin_db = 10.0 * math.log10(max(max(var_co, var_noise_floor), 1.0e-15) / max(var_noise_floor, 1.0e-15))
    co_separation_margin_db = float(lp_failure_db - co_noise_margin_db)
    arrival_ar_db = float(channel_amp.get("arrival_axial_ratio_db", float("nan")))
    buildability = buildability_metrics(geometry)
    build_ok = str(buildability["buildability_pass"]).lower() == "true"
    lock_lp_ok = bool((tail_lp_03 - tail_co_03) >= DS1V3_LOCK_MIN_TAIL_REDUCTION and (p95_lp - p95_co) >= DS1V3_LOCK_MIN_P95_REDUCTION_M)
    lock_sep_ok = bool(math.isfinite(co_separation_margin_db) and co_separation_margin_db >= DS1V3_LOCK_MIN_CO_SEPARATION_DB)
    lock_ar_ok = bool(math.isfinite(arrival_ar_db) and arrival_ar_db <= DS1V3_LOCK_MAX_ARRIVAL_AR_DB)
    target_lock_pass = bool(lock_lp_ok and lock_sep_ok and build_ok and (lock_ar_ok or not pattern.polarization_resolved))
    lock_penalty = 0.0
    if not lock_lp_ok:
        lock_penalty += 20.0
    if not lock_sep_ok:
        lock_penalty += max(0.0, DS1V3_LOCK_MIN_CO_SEPARATION_DB - co_separation_margin_db)
    if pattern.polarization_resolved and not lock_ar_ok:
        lock_penalty += max(0.0, arrival_ar_db - DS1V3_LOCK_MAX_ARRIVAL_AR_DB)
    if not build_ok:
        lock_penalty += 40.0
    target_lock_score = float(e_mit_db - lock_penalty)
    rank_score = target_lock_score if pattern.polarization_resolved else e_mit_db

    metrics: dict[str, float | str] = {
        "geometry_id": geometry.geometry_id,
        "material": geometry.material_key,
        "D_m": geometry.D_m,
        "u": geometry.u,
        "s_m": geometry.s_m,
        "theta_deg": geometry.theta_deg,
        "theta_eval_deg": theta_for_leakage,
        "delta_d_m": geometry.delta_d_m,
        "actual_delta_d_m": buildability["actual_delta_d_m"],
        "actual_u": buildability["actual_u"],
        "u_preservation_error_m": buildability["u_preservation_error_m"],
        "u_preservation_pass": buildability["u_preservation_pass"],
        "geometry_solver_status": buildability["geometry_solver_status"],
        "d0_m": geometry.d0_m,
        "dr_m": geometry.dr_m,
        "rho": geometry.rho,
        "rho_eval": rho_eff,
        "gamma_eff_abs": geometry.gamma_eff_abs,
        "designed_state": geometry.designed_state,
        "wall_tilt_deg": geometry.wall_tilt_deg,
        "at_asymmetry_frac": geometry.at_asymmetry_frac,
        "at_normal_offset_m": geometry.at_normal_offset_m,
        "reflection_valid": str(bool(geometry.reflection_valid)),
        "pattern_mode": pattern.mode,
        "phase_mode": phase_mode_l,
        "phase_mode_valid_for_fixed_s21": "False",
        "phase_mode_fixed_s21_diagnostic_requested": str(phase_mode_l in {"physical_delay", "coherent_upper", "aedt_fitted"}),
        "phase_mode_fixed_s21_script": "scripts/run_ds1_v5_fixed_s21_replay.py",
        "direct_xpr_mode": direct_response["direct_xpr_mode"],
        "direct_xpr_db": direct_response["direct_xpr_db"],
        "direct_co_gain_db": direct_response["direct_co_gain_db"],
        "direct_cross_gain_db": direct_response["direct_cross_gain_db"],
        "direct_phase_offset_co_m": direct_response["direct_phase_offset_co_m"],
        "direct_phase_offset_cross_m": direct_response["direct_phase_offset_cross_m"],
        "direct_co_amp": direct_response["direct_co_amp"],
        "direct_floor_cross_amp": direct_response["direct_floor_cross_amp"],
        "direct_pattern_cross_amp": direct_response["direct_pattern_cross_amp"],
        "snr_db": float(snr_db),
        "effective_snr_db": float(snr_eff_db),
        "n_noise_realizations": n_noise_i,
        "noise_model": "complex_awgn_direct_path_snr",
        "noise_seed": int(noise_seed),
        "denominator_floor_mode": "direct_only_noise_floor",
        "nonideality_profile": profile.profile_id,
        "axial_ratio_db": profile.axial_ratio_db,
        "switch_iso_db": profile.switch_iso_db,
        "gain_mismatch_db": profile.gain_mismatch_db,
        "group_delay_ps": profile.group_delay_ps,
        "xpol_degradation_db": profile.xpol_degradation_db,
        "cp_leakage_model": channel_amp.get("cp_leakage_model", ""),
        "legacy_angle_xpol_db": channel_amp.get("legacy_angle_xpol_db", float("nan")),
        "fresnel_refl_cosense_abs": channel_amp.get("fresnel_refl_cosense_abs", float("nan")),
        "fresnel_refl_crosssense_abs": channel_amp.get("fresnel_refl_crosssense_abs", float("nan")),
        "fresnel_refl_cosense_db": channel_amp.get("fresnel_refl_cosense_db", float("nan")),
        "fresnel_refl_crosssense_db": channel_amp.get("fresnel_refl_crosssense_db", float("nan")),
        "arrival_axial_ratio_db": arrival_ar_db,
        "arrival_xpd_db": channel_amp.get("arrival_xpd_db", float("nan")),
        "antenna_rhcp_cross_to_co_db": channel_amp.get("antenna_rhcp_cross_to_co_db", float("nan")),
        "direct_cross_amp": direct_cross_amp,
        "cp_co_phase_ensemble_amp": channel_amp.get("cp_co_phase_ensemble_amp", channel_amp.get("cp_co", float("nan"))),
        "cp_cross_phase_ensemble_amp": channel_amp.get("cp_cross_phase_ensemble_amp", channel_amp.get("cp_cross", float("nan"))),
        "cp_co_physical_delay_coeff_re": channel_amp.get("cp_co_physical_delay_coeff_re", float("nan")),
        "cp_co_physical_delay_coeff_im": channel_amp.get("cp_co_physical_delay_coeff_im", float("nan")),
        "cp_cross_physical_delay_coeff_re": channel_amp.get("cp_cross_physical_delay_coeff_re", float("nan")),
        "cp_cross_physical_delay_coeff_im": channel_amp.get("cp_cross_physical_delay_coeff_im", float("nan")),
        "cp_co_complex_scaled_re": channel_amp.get("cp_co_complex_scaled_re", channel_amp.get("cp_co_physical_delay_coeff_re", float("nan"))),
        "cp_co_complex_scaled_im": channel_amp.get("cp_co_complex_scaled_im", channel_amp.get("cp_co_physical_delay_coeff_im", float("nan"))),
        "cp_cross_complex_scaled_re": channel_amp.get("cp_cross_complex_scaled_re", channel_amp.get("cp_cross_physical_delay_coeff_re", float("nan"))),
        "cp_cross_complex_scaled_im": channel_amp.get("cp_cross_complex_scaled_im", channel_amp.get("cp_cross_physical_delay_coeff_im", float("nan"))),
        "lp_best_threshold": best_thr,
        "var_lp_best_m2": var_lp_best,
        "var_lp_dw1000_m2": var_lp_dw1000,
        "var_co_dw1000_m2": var_co,
        "var_noise_floor_m2": var_noise_floor,
        "var_denominator_used_m2": denominator,
        "denominator_floor_active": str(bool(var_noise_floor >= var_co)),
        "E_mit_best_tuned": e_mit_best_tuned,
        "E_mit_same_detector": e_mit_same_detector,
        "E_mit_conservative": e_mit,
        "E_mit_conservative_db": e_mit_db,
        "E_mit_phase_ensemble": e_mit if phase_mode_l == "ensemble_stress" else float("nan"),
        "E_mit_phase_ensemble_db": e_mit_db if phase_mode_l == "ensemble_stress" else float("nan"),
        "E_mit_physical_delay": float("nan"),
        "E_mit_physical_delay_db": float("nan"),
        "E_mit_coherent_upper": float("nan"),
        "E_mit_coherent_upper_db": float("nan"),
        "E_mit_aedt_fitted": float("nan"),
        "E_mit_aedt_fitted_db": float("nan"),
        "E_mit": e_mit,
        "E_mit_db": e_mit_db,
        "E_mit_legacy_epsilon": e_mit_legacy,
        "tail_rate": _tail_rate(lp_best_errors, 1.0),
        "tail_rate_abs_gt_0p3m": tail_lp_03,
        "co_tail_rate": _tail_rate(co_errors, 1.0),
        "co_tail_rate_abs_gt_0p3m": tail_co_03,
        "tail_reduction_abs_gt_0p3m": float(tail_lp_03 - tail_co_03),
        "max_abs_error_m": _max_abs(lp_best_errors),
        "p95_abs_error_m": p95_lp,
        "p99_abs_error_m": _quantile_abs(lp_best_errors, 0.99),
        "co_p95_abs_error_m": p95_co,
        "noise_floor_p95_abs_error_m": _quantile_abs(co_noise_floor_errors, 0.95),
        "p95_reduction_m": float(p95_lp - p95_co),
        "lp_failure_over_noise_db": lp_failure_db,
        "co_noise_margin_db": co_noise_margin_db,
        "co_separation_margin_db": co_separation_margin_db,
        "target_lock_lp_failure_pass": str(lock_lp_ok),
        "target_lock_co_separation_pass": str(lock_sep_ok),
        "target_lock_arrival_ar_pass": str(lock_ar_ok),
        "target_lock_buildability_pass": str(build_ok),
        "target_lock_gate_pass": str(target_lock_pass),
        "target_lock_score": target_lock_score,
        "rank_score": rank_score,
        "specular_endpoint_margin_m": buildability["specular_endpoint_margin_m"],
        "hfss_auto_plate_width_m": buildability["hfss_auto_plate_width_m"],
        "fixture_fresnel_radius_m": buildability["fixture_fresnel_radius_m"],
        "fixture_plate_span_m": buildability["fixture_plate_span_m"],
        "buildability_max_incidence_deg": buildability["buildability_max_incidence_deg"],
        "buildability_min_endpoint_margin_m": buildability["buildability_min_endpoint_margin_m"],
        "buildability_max_plate_width_m": buildability["buildability_max_plate_width_m"],
        "buildability_max_fixture_plate_span_m": buildability["buildability_max_fixture_plate_span_m"],
        "buildability_min_delta_d_m": buildability["buildability_min_delta_d_m"],
        "buildability_pass": buildability["buildability_pass"],
        "buildability_status": buildability["buildability_status"],
        "buildability_reasons": buildability["buildability_reasons"],
        "phi_worst": float(phase_values[phi_worst_idx]) if len(phase_values) else 0.0,
        "E_id": auc,
        "mean_xpr_clean_db": float(np.mean(xpr_clean_scores)) if xpr_clean_scores else float("nan"),
        "mean_xpr_late_db": float(np.mean(xpr_late_scores)) if xpr_late_scores else float("nan"),
        "mean_s3_clean": float(np.mean(s3_clean_scores)) if s3_clean_scores else float("nan"),
        "mean_s3_late": float(np.mean(s3_late_scores)) if s3_late_scores else float("nan"),
        "mislock_fraction": 1.0 - float(hist.get("direct", 0) / max(sum(hist.values()), 1)),
        "mislock_direct": hist.get("direct", 0),
        "mislock_m1_advance": hist.get("m1_advance", 0),
        "mislock_late_jump": hist.get("late_jump", 0),
        "single_reflector_error_ceiling_m": _max_abs(lp_best_errors),
        "delta_scan_axis": "micro_position_phase",
        "delta_step_mm": (C0 / FC_HZ) / max(int(n_phi), 1) * 1000.0,
        "delta_span_mm": (C0 / FC_HZ) * 1000.0,
    }
    return metrics, sample_rows


def run_phase0(root: Path, output_root: Path, config: DS1Config, pattern_bundle: PatternBundle, command_line: str) -> list[Path]:
    phase_dir = output_root / "phase0"
    phase_dir.mkdir(parents=True, exist_ok=True)
    direct_calibration = direct_calibration_from_config(config)
    discovery = {
        "schema_version": "DS1_discovery.v1",
        "created_at_utc": _now_utc(),
        "command_line": command_line,
        "model_scope": config.model_scope,
        "geometry_generator": {
            "type": "single_reflector_image_method",
            "anchor": [0.0, 0.0, 0.0],
            "tag": ["D", 0.0, 0.0],
            "reflector": "infinite planar wall through nominal image point",
            "delta_d": "u*c/B",
            "s": "sqrt((D+delta_d)^2-D^2)/2",
            "phase2_wall_tilt": "plane normal rotated about z; A/T direct distance preserved",
            "phase2_asymmetric_anchor_tag": "opposite wall-normal A/T offsets with direct distance preserved",
        },
        "path_construction": "rt_cp_uwb_py.designed_stress.build_path_records",
        "jones_fresnel_path": "rt_cp_uwb_py.core.fresnel_reflection",
        "noise_model": {
            "type": "complex_awgn",
            "snr_db_values": list(config.snr_db_values),
            "primary_snr_db": config.primary_snr_db,
            "n_noise_phase1": config.n_noise_phase1,
            "n_noise_phase3": config.n_noise_phase3,
            "seed": config.noise_seed,
            "denominator_floor": config.denominator_floor_mode,
        },
        "direct_calibration": {
            "direct_xpr_mode": direct_calibration.mode,
            "direct_xpr_db": direct_calibration.xpr_db("cp_cross"),
            "direct_co_gain_db": config.direct_co_gain_db,
            "direct_cross_gain_db": config.direct_cross_gain_db,
            "direct_phase_offset_co_m": direct_calibration.phase_offset("cp_co"),
            "direct_phase_offset_cross_m": direct_calibration.phase_offset("cp_cross"),
        },
        "phase_mode": {
            "active": config.phase_mode,
            "allowed": list(DS1_PHASE_MODES),
            "warning": "E_mit_phase_ensemble must not be compared directly to fixed physical AEDT S21.",
        },
        "detectors": ["max_peak_subtap", "LE0.3_subtap", "DW1000_LDE_EMULATOR_subtap", "LP_DW1000_control", "oracle"],
        "feature_extractors": ["windowed_xpr_late_db", "windowed_s3_late", "locked_tap_histogram"],
        "materials": {key: _material_summary(mat) for key, mat in material_table().items() if key in set(config.materials) | {"concrete"}},
        "pattern_bundle": {
            "requested_mode": config.pattern_mode,
            "resolved_mode": pattern_bundle.mode,
            "loaded": pattern_bundle.loaded,
            "sources": pattern_bundle.sources,
            "notes": list(pattern_bundle.load_notes),
            "circular_definition": pattern_bundle.circular_definition,
            "fresnel_co_definition": pattern_bundle.fresnel_co_definition,
            "convention_status": pattern_bundle.convention_status,
        },
        "claim_boundary": [
            "simulation_only",
            "not_full_wave_channel_simulation",
            "not_measurement_supervised_accuracy",
            "does_not_claim_CP_directly_reduces_range_error",
        ],
    }
    json_path = phase_dir / "DS1_discovery.json"
    md_path = phase_dir / "DS1_discovery.md"
    write_json(json_path, discovery)
    md_path.write_text(_discovery_markdown(discovery), encoding="utf-8")
    outputs = [json_path, md_path]
    if pattern_bundle.polarization_resolved:
        lock = build_convention_lock(pattern_bundle.patterns, material_table()["metal"], config.frequency_hz)
        lock_json = phase_dir / "DS1v3_convention_lock.json"
        lock_md = phase_dir / "DS1v3_convention_lock.md"
        write_json(lock_json, lock)
        lock_md.write_text(_convention_lock_markdown(lock), encoding="utf-8")
        outputs.extend([lock_json, lock_md])
    return outputs


def run_phase1(output_root: Path, config: DS1Config, pattern_bundle: PatternBundle, include_samples: bool = False) -> tuple[list[dict[str, float | str]], list[Path]]:
    phase_dir = output_root / "phase1"
    phase_dir.mkdir(parents=True, exist_ok=True)
    direct_calibration = direct_calibration_from_config(config)
    rows: list[dict[str, float | str]] = []
    sweep_rows: list[dict[str, float | str]] = []
    samples: list[dict[str, float | str]] = []
    for geom in build_geometries(config):
        for snr_db in _snr_values(config):
            metrics, sample_rows = simulate_geometry(
                geom,
                config.n_phi_phase1,
                pattern_bundle,
                include_samples=include_samples and _is_primary_snr(config, snr_db),
                snr_db=snr_db,
                n_noise=config.n_noise_phase1,
                noise_seed=config.noise_seed,
                direct_calibration=direct_calibration,
                phase_mode=config.phase_mode,
            )
            sweep_rows.append(metrics)
            if _is_primary_snr(config, snr_db):
                rows.append(metrics)
                samples.extend(sample_rows)
    metrics_path = phase_dir / "phase1_geometry_metrics.csv"
    sweep_path = phase_dir / "phase1_snr_sweep_metrics.csv"
    write_csv(metrics_path, rows)
    write_csv(sweep_path, sweep_rows)
    outputs = [metrics_path, sweep_path]
    if samples:
        sample_path = phase_dir / "phase1_phase_samples.csv"
        write_csv(sample_path, samples)
        outputs.append(sample_path)
    outputs.extend(write_phase1_figures(phase_dir, rows))
    return rows, outputs


def run_phase2(output_root: Path, phase1_rows: list[dict[str, float | str]], config: DS1Config, pattern_bundle: PatternBundle) -> tuple[list[dict[str, float | str]], list[Path]]:
    phase_dir = output_root / "phase2"
    phase_dir.mkdir(parents=True, exist_ok=True)
    direct_calibration = direct_calibration_from_config(config)
    top = _top_rows(phase1_rows, config.phase2_seed_k) if int(config.phase2_seed_k) > 0 else list(phase1_rows)
    top = _shard_sequence(top, config.phase2_shard_index, config.phase2_shard_count)
    mats = material_table()
    rows: list[dict[str, float | str]] = []
    for base in top:
        geom = make_geometry(str(base["material"]), mats[str(base["material"])], float(base["D_m"]), float(base["u"]), config.bandwidth_hz, config.frequency_hz)
        for wall_tilt in config.phase2_wall_tilts_deg:
            if abs(float(wall_tilt)) <= 1.0e-12:
                continue
            tilted = make_geometry(
                geom.material_key,
                geom.material,
                geom.D_m,
                geom.u,
                config.bandwidth_hz,
                config.frequency_hz,
                wall_tilt_deg=float(wall_tilt),
            )
            metrics, _ = simulate_geometry(
                tilted,
                config.n_phi_phase1,
                pattern_bundle,
                snr_db=config.primary_snr_db,
                n_noise=config.n_noise_phase1,
                noise_seed=config.noise_seed,
                direct_calibration=direct_calibration,
                phase_mode=config.phase_mode,
            )
            metrics.update(
                {
                    "base_geometry_id": geom.geometry_id,
                    "sweep_axis": "wall_tilt_deg",
                    "sweep_value": float(wall_tilt),
                    "generator_type": "tilted_wall_image_method",
                    "diagnostic_status": "GEOMETRY_GENERATOR",
                }
            )
            rows.append(metrics)
        for asym_frac in config.phase2_at_asymmetry_frac:
            if abs(float(asym_frac)) <= 1.0e-12:
                continue
            asymmetric = make_geometry(
                geom.material_key,
                geom.material,
                geom.D_m,
                geom.u,
                config.bandwidth_hz,
                config.frequency_hz,
                at_asymmetry_frac=float(asym_frac),
            )
            metrics, _ = simulate_geometry(
                asymmetric,
                config.n_phi_phase1,
                pattern_bundle,
                snr_db=config.primary_snr_db,
                n_noise=config.n_noise_phase1,
                noise_seed=config.noise_seed,
                direct_calibration=direct_calibration,
                phase_mode=config.phase_mode,
            )
            metrics.update(
                {
                    "base_geometry_id": geom.geometry_id,
                    "sweep_axis": "at_normal_asymmetry_frac",
                    "sweep_value": float(asym_frac),
                    "generator_type": "asymmetric_anchor_tag_image_method",
                    "diagnostic_status": "GEOMETRY_GENERATOR",
                }
            )
            rows.append(metrics)
    out = phase_dir / "phase2_decoupled_sweeps.csv"
    write_csv(out, rows)
    return rows, [out]


def run_phase3(
    output_root: Path,
    phase1_rows: list[dict[str, float | str]],
    config: DS1Config,
    pattern_bundle: PatternBundle,
    phase2_rows: list[dict[str, float | str]] | None = None,
) -> tuple[list[dict[str, float | str]], list[Path]]:
    phase_dir = output_root / "phase3"
    phase_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows = [*phase1_rows, *(phase2_rows or [])]
    top = _top_rows(candidate_rows, config.top_k)
    mats = material_table()
    direct_calibration = direct_calibration_from_config(config)
    rows: list[dict[str, float | str]] = []
    samples: list[dict[str, float | str]] = []
    hist_rows: list[dict[str, float | str]] = []
    for base in top:
        geom = make_geometry(
            str(base["material"]),
            mats[str(base["material"])],
            float(base["D_m"]),
            float(base["u"]),
            config.bandwidth_hz,
            config.frequency_hz,
            wall_tilt_deg=float(base.get("wall_tilt_deg", 0.0)),
            at_asymmetry_frac=float(base.get("at_asymmetry_frac", 0.0)),
        )
        metrics, sample_rows = simulate_geometry(
            geom,
            config.n_phi_phase3,
            pattern_bundle,
            include_samples=True,
            snr_db=config.primary_snr_db,
            n_noise=config.n_noise_phase3,
            noise_seed=config.noise_seed,
            direct_calibration=direct_calibration,
            phase_mode=config.phase_mode,
        )
        metrics.update(
            {
                "base_geometry_id": base.get("base_geometry_id", base.get("geometry_id", geom.geometry_id)),
                "generator_type": base.get("generator_type", "baseline_image_method"),
                "sweep_axis": base.get("sweep_axis", "baseline"),
                "sweep_value": base.get("sweep_value", 0.0),
            }
        )
        rows.append(metrics)
        samples.extend(sample_rows)
        for key in ("direct", "m1_advance", "late_jump"):
            hist_rows.append(
                {
                    "geometry_id": geom.geometry_id,
                    "base_geometry_id": base.get("base_geometry_id", base.get("geometry_id", geom.geometry_id)),
                    "mislock_class": key,
                    "count": metrics.get(f"mislock_{key}", 0),
                    "n_phi": config.n_phi_phase3,
                }
            )
    metrics_path = phase_dir / "phase3_topk_metrics.csv"
    samples_path = phase_dir / "phase3_phase_samples.csv"
    hist_path = phase_dir / "phase3_locked_tap_histograms.csv"
    write_csv(metrics_path, rows)
    write_csv(samples_path, samples)
    write_csv(hist_path, hist_rows)
    outputs = [metrics_path, samples_path, hist_path]
    outputs.extend(write_phase3_figures(phase_dir, samples))
    return rows, outputs


def run_phase4(
    output_root: Path,
    phase3_rows: list[dict[str, float | str]],
    config: DS1Config,
    pattern_bundle: PatternBundle,
) -> tuple[list[dict[str, float | str]], list[Path]]:
    phase_dir = output_root / "phase4"
    phase_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, float | str]] = []
    mats = material_table()
    direct_calibration = direct_calibration_from_config(config)
    mild_profile = _NonidealityProfile("mild_nonideal", axial_ratio_db=3.0, switch_iso_db=35.0, gain_mismatch_db=0.5, group_delay_ps=20.0)
    severe_profile = _NonidealityProfile("severe_nonideal", axial_ratio_db=6.0, switch_iso_db=25.0, gain_mismatch_db=1.5, group_delay_ps=60.0)
    for row in phase3_rows:
        geom = make_geometry(
            str(row["material"]),
            mats[str(row["material"])],
            float(row["D_m"]),
            float(row["u"]),
            config.bandwidth_hz,
            config.frequency_hz,
            wall_tilt_deg=float(row.get("wall_tilt_deg", 0.0)),
            at_asymmetry_frac=float(row.get("at_asymmetry_frac", 0.0)),
        )
        mild_metrics, _ = simulate_geometry(
            geom,
            config.n_phi_phase3,
            pattern_bundle,
            snr_db=config.primary_snr_db,
            n_noise=config.n_noise_phase3,
            noise_seed=config.noise_seed,
            nonideality_profile=mild_profile,
            direct_calibration=direct_calibration,
            phase_mode=config.phase_mode,
        )
        severe_metrics, _ = simulate_geometry(
            geom,
            config.n_phi_phase3,
            pattern_bundle,
            snr_db=config.primary_snr_db,
            n_noise=config.n_noise_phase3,
            noise_seed=config.noise_seed,
            nonideality_profile=severe_profile,
            direct_calibration=direct_calibration,
            phase_mode=config.phase_mode,
        )
        adjusted = dict(row)
        adjusted["E_mit_ideal"] = float(row["E_mit"])
        adjusted["E_mit_measured_hi"] = float(mild_metrics["E_mit"])
        adjusted["E_mit_measured_lo"] = float(severe_metrics["E_mit"])
        adjusted["E_mit_db_ideal"] = float(row["E_mit_db"])
        adjusted["E_mit_db_measured_hi"] = float(mild_metrics["E_mit_db"])
        adjusted["E_mit_db_measured_lo"] = float(severe_metrics["E_mit_db"])
        adjusted["rank_score"] = float(severe_metrics["rank_score"])
        adjusted["tail_reduction_abs_gt_0p3m_measured_lo"] = float(severe_metrics["tail_reduction_abs_gt_0p3m"])
        adjusted["p95_reduction_m_measured_lo"] = float(severe_metrics["p95_reduction_m"])
        adjusted["var_co_dw1000_m2_measured_lo"] = float(severe_metrics["var_co_dw1000_m2"])
        adjusted["var_noise_floor_m2_measured_lo"] = float(severe_metrics["var_noise_floor_m2"])
        adjusted["co_separation_margin_db_measured_lo"] = float(severe_metrics.get("co_separation_margin_db", float("nan")))
        adjusted["arrival_axial_ratio_db_measured_lo"] = float(severe_metrics.get("arrival_axial_ratio_db", float("nan")))
        adjusted["target_lock_score_measured_lo"] = float(severe_metrics.get("target_lock_score", severe_metrics["rank_score"]))
        adjusted["target_lock_gate_pass_measured_lo"] = severe_metrics.get("target_lock_gate_pass", "False")
        adjusted["target_lock_buildability_pass_measured_lo"] = severe_metrics.get(
            "target_lock_buildability_pass", severe_metrics.get("buildability_pass", "False")
        )
        adjusted["buildability_pass_measured_lo"] = severe_metrics.get("buildability_pass", "False")
        adjusted["buildability_status_measured_lo"] = severe_metrics.get("buildability_status", "")
        adjusted["buildability_reasons_measured_lo"] = severe_metrics.get("buildability_reasons", "")
        adjusted["co_noise_margin_db_measured_lo"] = float(severe_metrics.get("co_noise_margin_db", float("nan")))
        adjusted["lp_failure_over_noise_db_measured_lo"] = float(severe_metrics.get("lp_failure_over_noise_db", float("nan")))
        adjusted["nonideality_status"] = "SIMULATED_NONIDEALITY_STRESS_NOT_MEASUREMENT"
        rows.append(adjusted)
    band_path = phase_dir / "phase4_nonideality_prediction_band.csv"
    write_csv(band_path, rows)
    return rows, [band_path]


def write_final_outputs(output_root: Path, phase1_rows: list[dict[str, float | str]], phase4_rows: list[dict[str, float | str]], config: DS1Config, command_line: str, outputs: list[Path]) -> list[Path]:
    targets = []
    ranked = sorted(
        phase4_rows,
        key=lambda r: (
            -_truthy_int(r.get("target_lock_gate_pass_measured_lo", r.get("target_lock_gate_pass", "True"))),
            -_truthy_int(r.get("buildability_pass_measured_lo", r.get("buildability_pass", "False"))),
            -float(r["rank_score"]),
            -float(r.get("tail_reduction_abs_gt_0p3m_measured_lo", r.get("tail_reduction_abs_gt_0p3m", 0.0))),
            -float(r.get("p95_reduction_m_measured_lo", r.get("p95_reduction_m", 0.0))),
            float(r["u"]),
        ),
    )
    for rank, row in enumerate(ranked[: config.top_k], start=1):
        targets.append(
            {
                "rank": rank,
                "geometry_id": row.get("geometry_id", ""),
                "m": row["material"],
                "s": row["s_m"],
                "D": row["D_m"],
                "theta_deg": row["theta_deg"],
                "u": row["u"],
                "actual_u": row.get("actual_u", ""),
                "rho": row["rho"],
                "wall_tilt_deg": row.get("wall_tilt_deg", 0.0),
                "at_asymmetry_frac": row.get("at_asymmetry_frac", 0.0),
                "at_normal_offset_m": row.get("at_normal_offset_m", 0.0),
                "generator_type": row.get("generator_type", "baseline_image_method"),
                "phi_worst": row["phi_worst"],
                "E_mit_ideal": row["E_mit_ideal"],
                "E_mit_measured_lo": row["E_mit_measured_lo"],
                "E_mit_measured_hi": row["E_mit_measured_hi"],
                "E_mit_db_ideal": row["E_mit_db_ideal"],
                "E_mit_db_measured_lo": row["E_mit_db_measured_lo"],
                "E_mit_db_measured_hi": row["E_mit_db_measured_hi"],
                "rank_score": row["rank_score"],
                "var_co_dw1000_m2": row["var_co_dw1000_m2"],
                "var_noise_floor_m2": row["var_noise_floor_m2"],
                "var_co_dw1000_m2_measured_lo": row["var_co_dw1000_m2_measured_lo"],
                "var_noise_floor_m2_measured_lo": row["var_noise_floor_m2_measured_lo"],
                "actual_delta_d_m": row.get("actual_delta_d_m", ""),
                "u_preservation_error_m": row.get("u_preservation_error_m", ""),
                "u_preservation_pass": row.get("u_preservation_pass", ""),
                "geometry_solver_status": row.get("geometry_solver_status", ""),
                "specular_endpoint_margin_m": row.get("specular_endpoint_margin_m", ""),
                "hfss_auto_plate_width_m": row.get("hfss_auto_plate_width_m", ""),
                "fixture_fresnel_radius_m": row.get("fixture_fresnel_radius_m", ""),
                "fixture_plate_span_m": row.get("fixture_plate_span_m", ""),
                "buildability_pass": row.get("buildability_pass", ""),
                "buildability_pass_measured_lo": row.get("buildability_pass_measured_lo", ""),
                "buildability_status": row.get("buildability_status", ""),
                "buildability_status_measured_lo": row.get("buildability_status_measured_lo", ""),
                "buildability_reasons": row.get("buildability_reasons", ""),
                "buildability_reasons_measured_lo": row.get("buildability_reasons_measured_lo", ""),
                "cp_leakage_model": row.get("cp_leakage_model", ""),
                "fresnel_refl_cosense_abs": row.get("fresnel_refl_cosense_abs", ""),
                "fresnel_refl_crosssense_abs": row.get("fresnel_refl_crosssense_abs", ""),
                "arrival_axial_ratio_db": row.get("arrival_axial_ratio_db", ""),
                "arrival_axial_ratio_db_measured_lo": row.get("arrival_axial_ratio_db_measured_lo", ""),
                "arrival_xpd_db": row.get("arrival_xpd_db", ""),
                "co_separation_margin_db": row.get("co_separation_margin_db", ""),
                "co_separation_margin_db_measured_lo": row.get("co_separation_margin_db_measured_lo", ""),
                "target_lock_gate_pass": row.get("target_lock_gate_pass", ""),
                "target_lock_gate_pass_measured_lo": row.get("target_lock_gate_pass_measured_lo", ""),
                "target_lock_buildability_pass": row.get("target_lock_buildability_pass", ""),
                "target_lock_buildability_pass_measured_lo": row.get("target_lock_buildability_pass_measured_lo", ""),
                "target_lock_score": row.get("target_lock_score", ""),
                "target_lock_score_measured_lo": row.get("target_lock_score_measured_lo", ""),
                "tail_reduction_abs_gt_0p3m": row["tail_reduction_abs_gt_0p3m"],
                "tail_reduction_abs_gt_0p3m_measured_lo": row["tail_reduction_abs_gt_0p3m_measured_lo"],
                "p95_reduction_m": row["p95_reduction_m"],
                "p95_reduction_m_measured_lo": row["p95_reduction_m_measured_lo"],
                "tail_rate": row["tail_rate_abs_gt_0p3m"],
                "delta_scan_axis": row["delta_scan_axis"],
                "delta_step_mm": row["delta_step_mm"],
                "delta_span_mm": row["delta_span_mm"],
                "ranking_basis": config.primary_rank_metric,
            }
        )
    target_path = output_root / "DS1_measurement_targets.csv"
    write_csv(target_path, targets)

    claimmap_path = output_root / "DS1_claimmap.md"
    claimmap_path.write_text(build_claimmap_markdown(phase1_rows, phase4_rows), encoding="utf-8")
    invalidation_path = output_root / "DS1_INVALIDATED_NOISELESS_OUTPUTS.md"
    invalidation_path.write_text(_invalidation_markdown(config), encoding="utf-8")

    compare_outputs: list[Path] = []
    if str(config.compare_run_root).strip():
        compare_outputs = write_ds1_optimum_compare(Path(config.compare_run_root), output_root, phase4_rows, targets)

    all_outputs = [*outputs, target_path, claimmap_path, invalidation_path, *compare_outputs]
    manifest = {
        "schema_version": "DS1_manifest.v1",
        "created_at_utc": _now_utc(),
        "command_line": command_line,
        "config": asdict(config),
        "claim_boundary": {
            "paper": "Paper 1 simulation",
            "q_clean": "not used here",
            "range_error_claim": "not claimed",
            "measurement_claim": "not claimed",
            "ds_family_role": "mechanism-degree map and measurement-target selection",
        },
        "input_files": _input_file_status(Path.cwd()),
        "output_files": [_path_payload(path) for path in all_outputs if path.exists()],
    }
    manifest_path = output_root / "DS1_manifest.json"
    write_json(manifest_path, manifest)
    return [target_path, claimmap_path, invalidation_path, *compare_outputs, manifest_path]


def write_ds1_optimum_compare(old_run_root: Path, new_run_root: Path, new_phase4_rows: list[dict[str, float | str]], new_targets: list[dict[str, object]]) -> list[Path]:
    old_phase4_path = old_run_root / "phase4" / "phase4_nonideality_prediction_band.csv"
    old_targets_path = old_run_root / "DS1_measurement_targets.csv"
    rows: list[dict[str, object]] = []
    if old_phase4_path.exists():
        old_phase4 = read_csv_rows(old_phase4_path)
        rows.append(_compare_row("compare_run_emit_rank1", old_phase4, "rank_score"))
    if old_targets_path.exists():
        old_targets = read_csv_rows(old_targets_path)
        if old_targets:
            rows.append(_compare_target_row("compare_run_target_rank1", old_targets[0]))
    rows.append(_compare_row("current_run_emit_rank1", new_phase4_rows, "E_mit_db_measured_lo"))
    if new_targets:
        rows.append(_compare_target_row("current_run_target_lock_rank1", new_targets[0]))
    outputs = [
        new_run_root / "DS1_optimum_compare.csv",
        new_run_root / "DS1v4_optimum_compare.csv",
        new_run_root / "DS1v3_optimum_compare.csv",
    ]
    for out in outputs:
        write_csv(out, rows)
    return outputs


def write_ds1v3_optimum_compare(old_run_root: Path, new_run_root: Path, new_phase4_rows: list[dict[str, float | str]], new_targets: list[dict[str, object]]) -> list[Path]:
    return write_ds1_optimum_compare(old_run_root, new_run_root, new_phase4_rows, new_targets)


def _compare_row(label: str, rows: list[dict[str, float | str]], score_key: str) -> dict[str, object]:
    if not rows:
        return {"comparison_role": label, "status": "MISSING"}
    best = max(rows, key=lambda r: float(r.get(score_key, r.get("rank_score", r.get("E_mit_db", -999.0)))))
    return {
        "comparison_role": label,
        "status": "PRESENT",
        "geometry_id": best.get("geometry_id", ""),
        "material": best.get("material", best.get("m", "")),
        "D_m": best.get("D_m", best.get("D", "")),
        "u": best.get("u", ""),
        "theta_deg": best.get("theta_deg", ""),
        "generator_type": best.get("generator_type", ""),
        "score_key": score_key,
        "score_value": best.get(score_key, best.get("rank_score", "")),
        "E_mit_db_measured_lo": best.get("E_mit_db_measured_lo", ""),
        "co_separation_margin_db_measured_lo": best.get("co_separation_margin_db_measured_lo", ""),
        "arrival_axial_ratio_db_measured_lo": best.get("arrival_axial_ratio_db_measured_lo", ""),
        "target_lock_gate_pass_measured_lo": best.get("target_lock_gate_pass_measured_lo", ""),
        "target_lock_buildability_pass_measured_lo": best.get("target_lock_buildability_pass_measured_lo", best.get("target_lock_buildability_pass", "")),
        "buildability_pass_measured_lo": best.get("buildability_pass_measured_lo", best.get("buildability_pass", "")),
        "buildability_status_measured_lo": best.get("buildability_status_measured_lo", best.get("buildability_status", "")),
        "buildability_reasons_measured_lo": best.get("buildability_reasons_measured_lo", best.get("buildability_reasons", "")),
        "actual_u": best.get("actual_u", ""),
        "actual_delta_d_m": best.get("actual_delta_d_m", ""),
        "u_preservation_error_m": best.get("u_preservation_error_m", ""),
        "u_preservation_pass": best.get("u_preservation_pass", ""),
        "geometry_solver_status": best.get("geometry_solver_status", ""),
        "fixture_plate_span_m": best.get("fixture_plate_span_m", ""),
        "hfss_auto_plate_width_m": best.get("hfss_auto_plate_width_m", ""),
    }


def _compare_target_row(label: str, row: dict[str, object]) -> dict[str, object]:
    return {
        "comparison_role": label,
        "status": "PRESENT",
        "geometry_id": row.get("geometry_id", ""),
        "material": row.get("m", row.get("material", "")),
        "D_m": row.get("D", row.get("D_m", "")),
        "u": row.get("u", ""),
        "theta_deg": row.get("theta_deg", ""),
        "generator_type": row.get("generator_type", ""),
        "score_key": "target_rank",
        "score_value": row.get("rank_score", ""),
        "E_mit_db_measured_lo": row.get("E_mit_db_measured_lo", ""),
        "co_separation_margin_db_measured_lo": row.get("co_separation_margin_db_measured_lo", ""),
        "arrival_axial_ratio_db_measured_lo": row.get("arrival_axial_ratio_db_measured_lo", ""),
        "target_lock_gate_pass_measured_lo": row.get("target_lock_gate_pass_measured_lo", ""),
        "target_lock_buildability_pass_measured_lo": row.get("target_lock_buildability_pass_measured_lo", row.get("target_lock_buildability_pass", "")),
        "buildability_pass_measured_lo": row.get("buildability_pass_measured_lo", row.get("buildability_pass", "")),
        "buildability_status_measured_lo": row.get("buildability_status_measured_lo", row.get("buildability_status", "")),
        "buildability_reasons_measured_lo": row.get("buildability_reasons_measured_lo", row.get("buildability_reasons", "")),
        "actual_u": row.get("actual_u", ""),
        "actual_delta_d_m": row.get("actual_delta_d_m", ""),
        "u_preservation_error_m": row.get("u_preservation_error_m", ""),
        "u_preservation_pass": row.get("u_preservation_pass", ""),
        "geometry_solver_status": row.get("geometry_solver_status", ""),
        "fixture_plate_span_m": row.get("fixture_plate_span_m", ""),
        "hfss_auto_plate_width_m": row.get("hfss_auto_plate_width_m", ""),
    }


def validate_discovery_outputs(output_root: Path) -> None:
    path = output_root / "phase0" / "DS1_discovery.json"
    if not path.exists():
        raise FileNotFoundError(f"missing discovery JSON: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ["geometry_generator", "jones_fresnel_path", "detectors", "feature_extractors", "materials", "pattern_bundle"]
    missing = [key for key in required if key not in data]
    if missing:
        raise ValueError(f"discovery output missing keys: {', '.join(missing)}")


def build_claimmap_markdown(phase1_rows: list[dict[str, float | str]], phase4_rows: list[dict[str, float | str]]) -> str:
    h1 = _verdict_h1(phase1_rows)
    h2 = _verdict_h2(phase1_rows)
    h3 = _verdict_h3(phase1_rows)
    h4 = _verdict_h4(phase4_rows)
    d1 = _verdict_d1(phase4_rows)
    rows = [h1, h2, h3, h4, d1]
    lines = [
        "# DS1 Claim Map",
        "",
        "Scope: simulation-only designed single-reflector stress family. This is not a full-wave channel simulation and not measurement accuracy evidence.",
        "",
        "| ID | Verdict | Evidence | Claim boundary |",
        "|---|---|---|---|",
    ]
    for item in rows:
        lines.append(f"| {item['id']} | {item['verdict']} | {item['evidence']} | {item['boundary']} |")
    lines.extend(
        [
            "",
            "Locked wording:",
            "- DS1 supports mechanism-degree target selection only.",
            "- Do not write that CP directly reduces range error.",
            "- DW1000_LDE is an emulator used for measurement-relevant detector stress, not device firmware validation.",
            "- Noise-free DS1 ranking outputs are superseded; use only noise-aware DS1 outputs.",
            "- FFD includes complex vector-field components (Re/Im Etheta, Ephi); DS1-v3 derives co/cross and axial-ratio antenna response from this vector field.",
            "- CP complex coefficients are preserved in `*_physical_delay_coeff_*`; amplitude-only `*_phase_ensemble_amp` is for phase-ensemble stress features.",
            "- DS1-v4 target lock adds u-preserving decoupled geometry and buildability gates; unbuildable high-score geometry is not measurement-ready evidence.",
            "- Antenna axial ratio is a simulation-FFD prediction, not a substitute for measured antenna calibration.",
            "- AEDT-calibrated `S_plate - S0` components must be described as finite-plate scattered components/operators, not isolated specular rays unless per-ray complex closure is available.",
            "- Phase 2 decoupled sweeps use tilted-wall and asymmetric-anchor/tag image-method generators; they remain simulation-only geometry stress evidence.",
            "",
        ]
    )
    return "\n".join(lines)


def _invalidation_markdown(config: DS1Config) -> str:
    direct_calibration = direct_calibration_from_config(config)
    return "\n".join(
        [
            "# DS1 Noiseless Output Invalidation",
            "",
            "Status: supersedes earlier noiseless DS1 optimum ranking and `DS1_measurement_targets.csv` files.",
            "",
            "Root cause:",
            "- Earlier DS1 CIRs were deterministic two-pulse responses without a detector noise floor.",
            "- co-CP DW1000_LDE frequently locked perfectly to the direct path, making `var_co_dw1000_m2 = 0`.",
            "- The old epsilon ratio `(var_lp + 1e-9)/(var_co + 1e-9)` inflated `E_mit` and dominated ranking.",
            "",
            "Current fix:",
            f"- Complex AWGN direct-path SNR sweep: {', '.join(f'{v:g} dB' for v in config.snr_db_values)}.",
            f"- Primary SNR: {config.primary_snr_db:g} dB.",
            f"- Phase 1 noise realizations per phase: {config.n_noise_phase1}.",
            f"- Phase 3/4 noise realizations per phase: {config.n_noise_phase3}.",
            "- Denominator floor: direct-only co-CP DW1000_LDE noise-floor variance.",
            "- `E_mit` is now conservative: min(best-tuned LP ratio, LP DW1000 same-detector ratio).",
            "- `E_mit_phase_ensemble` is the DS1 stress-statistic metric; `E_mit_physical_delay`, `E_mit_coherent_upper`, and `E_mit_aedt_fitted` are reserved for fixed-S21 diagnostics and are not ranking metrics here.",
            "- Ranking uses `E_mit_conservative_db` under severe simulated nonideality.",
            f"- Direct XPR mode: `{direct_calibration.mode}` with XPR `{direct_calibration.xpr_db('cp_cross'):g} dB`; direct phase offsets co/cross: `{direct_calibration.phase_offset('cp_co'):g}` / `{direct_calibration.phase_offset('cp_cross'):g}` m.",
            "- DS1-v3 deprecates the ad-hoc angle-leakage slope and uses Fresnel co/cross split plus vector-FFD antenna axial-ratio response when `pattern_mode=ffd-pol`.",
            "- DS1-v4 re-solves decoupled generator geometry to preserve actual `u` where possible and adds buildability gates for incidence, endpoint margin, auto plate width, and minimum controllable path excess.",
            "",
            "Claim boundary:",
            "- This remains simulation-only image-method/geometrical-optics evidence with optional HFSS FFD antenna pattern factors.",
            "- It is not full-wave channel simulation and not measurement validation.",
            "- Do not claim that CP directly reduces range error.",
            "",
        ]
    )


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key, "")) for key in fieldnames})


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_phase1_figures(phase_dir: Path, rows: list[dict[str, float | str]]) -> list[Path]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        note = phase_dir / "figures_unavailable.txt"
        note.write_text("matplotlib unavailable; phase1_geometry_metrics.csv is the response-surface artifact.\n", encoding="utf-8")
        return [note]
    fig_dir = phase_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for material in sorted({str(row["material"]) for row in rows}):
        sub = [row for row in rows if str(row["material"]) == material]
        x = [float(row["u"]) for row in sub]
        y = [float(row["theta_deg"]) for row in sub]
        c = [float(row["E_mit"]) for row in sub]
        plt.figure(figsize=(7, 4.5))
        sc = plt.scatter(x, y, c=c, s=55, cmap="viridis")
        plt.colorbar(sc, label="E_mit")
        plt.xlabel("u = delta_tau * B")
        plt.ylabel("theta_deg")
        plt.title(f"DS1 response surface: {material}")
        out = fig_dir / f"phase1_response_surface_{material}.png"
        plt.tight_layout()
        plt.savefig(out, dpi=160)
        plt.close()
        outputs.append(out)
    return outputs


def write_phase3_figures(phase_dir: Path, samples: list[dict[str, float | str]]) -> list[Path]:
    try:
        import matplotlib.pyplot as plt  # type: ignore
    except Exception:
        note = phase_dir / "figures_unavailable.txt"
        note.write_text("matplotlib unavailable; phase3_phase_samples.csv contains phase curves.\n", encoding="utf-8")
        return [note]
    fig_dir = phase_dir / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []
    for gid in sorted({str(row["geometry_id"]) for row in samples}):
        sub = [row for row in samples if str(row["geometry_id"]) == gid]
        phi = [float(row["phi_rad"]) for row in sub]
        lp = [float(row["lp_le03_error_m"]) for row in sub]
        co = [float(row["co_dw1000_error_m"]) for row in sub]
        plt.figure(figsize=(7, 4.5))
        plt.plot(phi, lp, label="LP LE0.3")
        plt.plot(phi, co, label="co-CP DW1000_LDE")
        plt.xlabel("phi_rel_rad")
        plt.ylabel("range detector error proxy (m)")
        plt.title(gid)
        plt.legend()
        out = fig_dir / f"phase3_phase_curve_{_safe_name(gid)}.png"
        plt.tight_layout()
        plt.savefig(out, dpi=160)
        plt.close()
        outputs.append(out)
    return outputs


def _channel_reflection_amplitudes(
    geometry: DS1Geometry,
    reflected: PathRecord,
    direct: PathRecord,
    pattern: PatternBundle,
    rho_eff: float,
    theta_for_leakage: float,
    xpol_degradation_db: float = 0.0,
) -> dict[str, float]:
    tx_dir_direct = direct.launch_dir
    rx_look_direct = -direct.arrival_dir
    tx_boresight = tx_dir_direct
    rx_boresight = rx_look_direct
    tx_dir_ref = reflected.launch_dir
    rx_look_ref = -reflected.arrival_dir

    base = math.sqrt(max(rho_eff, 0.0))
    lp_pat = pattern.amplitude_ratio("lp", tx_dir_ref, rx_look_ref, tx_dir_direct, rx_look_direct, tx_boresight, rx_boresight)
    if pattern.polarization_resolved:
        cp = _polarization_resolved_cp_amplitudes(
            geometry,
            reflected,
            direct,
            pattern,
            base,
            tx_dir_ref,
            rx_look_ref,
            tx_dir_direct,
            rx_look_direct,
            tx_boresight,
            rx_boresight,
            xpol_degradation_db=xpol_degradation_db,
        )
        return {"lp": float(base * lp_pat), **cp}

    xpol_db = max(3.0, _angle_adjusted_xpol_db(geometry.material, theta_for_leakage) - float(xpol_degradation_db))
    co_pat = pattern.amplitude_ratio("cp_co", tx_dir_ref, rx_look_ref, tx_dir_direct, rx_look_direct, tx_boresight, rx_boresight)
    cross_pat = pattern.amplitude_ratio("cp_cross", tx_dir_ref, rx_look_ref, tx_dir_direct, rx_look_direct, tx_boresight, rx_boresight)
    leakage = 10.0 ** (-xpol_db / 20.0)
    cross_factor = math.sqrt(max(1.0 - leakage * leakage, 0.0))
    return {
        "lp": float(base * lp_pat),
        "cp_co": float(base * leakage * co_pat),
        "cp_cross": float(base * cross_factor * cross_pat),
        "cp_co_phase_ensemble_amp": float(base * leakage * co_pat),
        "cp_cross_phase_ensemble_amp": float(base * cross_factor * cross_pat),
        "cp_co_physical_delay_coeff_re": float(base * leakage * co_pat),
        "cp_co_physical_delay_coeff_im": 0.0,
        "cp_cross_physical_delay_coeff_re": float(base * cross_factor * cross_pat),
        "cp_cross_physical_delay_coeff_im": 0.0,
        "cp_leakage_model": "legacy_angle_adjusted_xpol",
        "legacy_angle_xpol_db": float(xpol_db),
        "fresnel_refl_cosense_abs": float("nan"),
        "fresnel_refl_crosssense_abs": float("nan"),
        "arrival_axial_ratio_db": float("nan"),
        "arrival_xpd_db": float("nan"),
        "antenna_rhcp_cross_to_co_db": float("nan"),
    }


def _polarization_resolved_cp_coefficients(
    geometry: DS1Geometry,
    reflected: PathRecord,
    direct: PathRecord,
    pattern: PatternBundle,
    tx_dir_ref: np.ndarray,
    rx_look_ref: np.ndarray,
    tx_dir_direct: np.ndarray,
    rx_look_direct: np.ndarray,
    tx_boresight: np.ndarray,
    rx_boresight: np.ndarray,
    xpol_degradation_db: float = 0.0,
) -> dict[str, object]:
    del direct
    gamma_te, gamma_tm = fresnel_reflection(geometry.material, reflected.incidence_angles_rad[0], np.asarray([FC_HZ], dtype=float))
    refl_co, refl_cross, gamma_eff = _fresnel_cp_split_values(
        complex(gamma_te[0]),
        complex(gamma_tm[0]),
        pattern.fresnel_co_definition,
    )
    if gamma_eff > 1.0e-15:
        refl_co = refl_co / gamma_eff
        refl_cross = refl_cross / gamma_eff

    rhcp = pattern.patterns["cp_co"]
    lhcp = pattern.patterns["cp_cross"]
    rdef = pattern.circular_definition

    tx_r_co = _circular_component_ratio(rhcp, "R", tx_dir_ref, tx_dir_direct, tx_boresight, rdef)
    tx_r_cross = _circular_component_ratio(rhcp, "L", tx_dir_ref, tx_dir_direct, tx_boresight, rdef)
    rx_r_co = _circular_component_ratio(rhcp, "R", rx_look_ref, rx_look_direct, rx_boresight, rdef)
    rx_r_cross = _circular_component_ratio(rhcp, "L", rx_look_ref, rx_look_direct, rx_boresight, rdef)

    tx_l_co = _circular_component_ratio(lhcp, "L", tx_dir_ref, tx_dir_direct, tx_boresight, rdef)
    tx_l_cross = _circular_component_ratio(lhcp, "R", tx_dir_ref, tx_dir_direct, tx_boresight, rdef)
    rx_l_co = _circular_component_ratio(lhcp, "L", rx_look_ref, rx_look_direct, rx_boresight, rdef)
    rx_l_cross = _circular_component_ratio(lhcp, "R", rx_look_ref, rx_look_direct, rx_boresight, rdef)

    co_complex = refl_co * tx_r_co * rx_r_co + refl_cross * tx_r_cross * rx_r_cross
    cross_complex = refl_cross * tx_l_co * rx_l_co + refl_co * tx_l_cross * rx_l_cross

    # Keep Phase4 non-ideality stress as additional finite isolation leakage without replacing the physical chain.
    if float(xpol_degradation_db) > 0.0:
        leak = 10.0 ** (-max(3.0, DS1_DIRECT_XPR_IDEAL_DB - float(xpol_degradation_db)) / 20.0)
        co_complex = co_complex + leak * cross_complex

    arr_theta, arr_phi = _pattern_angles(rx_look_ref, rx_boresight)
    arrival_ar = rhcp.axial_ratio_db(arr_theta, arr_phi, rdef)
    arrival_xpd = rhcp.circular_xpd_db(arr_theta, arr_phi, "R", rdef)
    return {
        "cp_co_complex": complex(co_complex),
        "cp_cross_complex": complex(cross_complex),
        "cp_co_complex_re": float(np.real(co_complex)),
        "cp_co_complex_im": float(np.imag(co_complex)),
        "cp_cross_complex_re": float(np.real(cross_complex)),
        "cp_cross_complex_im": float(np.imag(cross_complex)),
        "cp_co_abs": float(abs(co_complex)),
        "cp_cross_abs": float(abs(cross_complex)),
        "cp_leakage_model": "fresnel_split_plus_vector_ffd_axial_ratio",
        "legacy_angle_xpol_db": float("nan"),
        "fresnel_refl_cosense_abs": float(abs(refl_co)),
        "fresnel_refl_crosssense_abs": float(abs(refl_cross)),
        "fresnel_refl_cosense_db": float(20.0 * math.log10(max(abs(refl_co), 1.0e-15))),
        "fresnel_refl_crosssense_db": float(20.0 * math.log10(max(abs(refl_cross), 1.0e-15))),
        "arrival_axial_ratio_db": float(arrival_ar),
        "arrival_xpd_db": float(arrival_xpd),
        "antenna_rhcp_cross_to_co_db": float(-arrival_xpd),
    }


def _polarization_resolved_cp_amplitudes(
    geometry: DS1Geometry,
    reflected: PathRecord,
    direct: PathRecord,
    pattern: PatternBundle,
    base: float,
    tx_dir_ref: np.ndarray,
    rx_look_ref: np.ndarray,
    tx_dir_direct: np.ndarray,
    rx_look_direct: np.ndarray,
    tx_boresight: np.ndarray,
    rx_boresight: np.ndarray,
    xpol_degradation_db: float = 0.0,
) -> dict[str, object]:
    coeffs = _polarization_resolved_cp_coefficients(
        geometry,
        reflected,
        direct,
        pattern,
        tx_dir_ref,
        rx_look_ref,
        tx_dir_direct,
        rx_look_direct,
        tx_boresight,
        rx_boresight,
        xpol_degradation_db=xpol_degradation_db,
    )
    return {
        **coeffs,
        "cp_co": float(base * float(coeffs["cp_co_abs"])),
        "cp_cross": float(base * float(coeffs["cp_cross_abs"])),
        "cp_co_phase_ensemble_amp": float(base * float(coeffs["cp_co_abs"])),
        "cp_cross_phase_ensemble_amp": float(base * float(coeffs["cp_cross_abs"])),
        "cp_co_physical_delay_coeff_re": float(base * float(coeffs["cp_co_complex_re"])),
        "cp_co_physical_delay_coeff_im": float(base * float(coeffs["cp_co_complex_im"])),
        "cp_cross_physical_delay_coeff_re": float(base * float(coeffs["cp_cross_complex_re"])),
        "cp_cross_physical_delay_coeff_im": float(base * float(coeffs["cp_cross_complex_im"])),
        "cp_co_complex_scaled_re": float(base * float(coeffs["cp_co_complex_re"])),
        "cp_co_complex_scaled_im": float(base * float(coeffs["cp_co_complex_im"])),
        "cp_cross_complex_scaled_re": float(base * float(coeffs["cp_cross_complex_re"])),
        "cp_cross_complex_scaled_im": float(base * float(coeffs["cp_cross_complex_im"])),
    }


def _fresnel_cp_split_values(gamma_te: complex, gamma_tm: complex, co_definition: str) -> tuple[complex, complex, float]:
    gamma_eff = math.sqrt((abs(gamma_te) ** 2 + abs(gamma_tm) ** 2) / 2.0)
    diff = 0.5 * (gamma_te - gamma_tm)
    summ = 0.5 * (gamma_te + gamma_tm)
    if str(co_definition) == "difference":
        return diff, summ, float(gamma_eff)
    if str(co_definition) == "sum":
        return summ, diff, float(gamma_eff)
    raise ValueError(f"unsupported Fresnel CP split definition: {co_definition}")


def _circular_component_ratio(
    pattern: ReceiverAntennaPattern,
    hand: str,
    direction_world: np.ndarray,
    direct_direction_world: np.ndarray,
    boresight_world: np.ndarray,
    r_definition: str,
) -> complex:
    theta, phi = _pattern_angles(direction_world, boresight_world)
    d_theta, d_phi = _pattern_angles(direct_direction_world, boresight_world)
    right, left = pattern.circular_components(theta, phi, r_definition)
    d_right, d_left = pattern.circular_components(d_theta, d_phi, r_definition)
    comp = right if str(hand).upper().startswith("R") else left
    direct_comp = d_right if str(hand).upper().startswith("R") else d_left
    return complex(comp / (direct_comp if abs(direct_comp) > 1.0e-15 else 1.0e-15))


def _pattern_angles(direction_world: np.ndarray, boresight_world: np.ndarray) -> tuple[float, float]:
    local = _local_direction(direction_world, boresight_world)
    theta = math.degrees(math.acos(float(np.clip(local[2], -1.0, 1.0))))
    phi = math.degrees(math.atan2(float(local[1]), float(local[0])))
    return float(theta), float(phi)


def _direct_cross_amplitude(pattern: PatternBundle, direct: PathRecord, profile: _NonidealityProfile) -> float:
    return float(_direct_cross_response(pattern, direct, profile, DirectCalibration())["direct_cross_amp"])


def _direct_cross_response(
    pattern: PatternBundle,
    direct: PathRecord,
    profile: _NonidealityProfile,
    calibration: DirectCalibration,
) -> dict[str, float | str]:
    mode = _normalize_direct_xpr_mode(calibration.mode)
    direct_xpr_db = float(calibration.xpr_db("cp_cross"))
    if mode in {"ideal", "ideal_45db"}:
        direct_xpr_db = max(3.0, direct_xpr_db - profile.xpol_degradation_db)
    direct_xpr_db = max(3.0, float(direct_xpr_db))
    baseline = 10.0 ** (-direct_xpr_db / 20.0)
    co_gain = 10.0 ** (float(calibration.co_gain("cp_co")) / 20.0)
    cross_gain = 10.0 ** (float(calibration.co_gain("cp_cross")) / 20.0)
    pattern_leakage = 0.0
    if not pattern.polarization_resolved:
        amp = baseline
    else:
        tx_dir_direct = direct.launch_dir
        rx_look_direct = -direct.arrival_dir
        rhcp = pattern.patterns["cp_co"]
        lhcp = pattern.patterns["cp_cross"]
        rdef = pattern.circular_definition
        tx_theta, tx_phi = _pattern_angles(tx_dir_direct, tx_dir_direct)
        rx_theta, rx_phi = _pattern_angles(rx_look_direct, rx_look_direct)
        rh_r_tx, rh_l_tx = rhcp.circular_components(tx_theta, tx_phi, rdef)
        lh_r_rx, lh_l_rx = lhcp.circular_components(rx_theta, rx_phi, rdef)
        pattern_leakage = (abs(rh_l_tx) / max(abs(rh_r_tx), 1.0e-15)) * (abs(lh_r_rx) / max(abs(lh_l_rx), 1.0e-15))
        amp = max(pattern_leakage, baseline)
    return {
        "direct_xpr_mode": mode,
        "direct_xpr_db": float(direct_xpr_db),
        "direct_co_gain_db": float(calibration.co_gain("cp_co")),
        "direct_cross_gain_db": float(calibration.co_gain("cp_cross")),
        "direct_phase_offset_co_m": float(calibration.phase_offset("cp_co")),
        "direct_phase_offset_cross_m": float(calibration.phase_offset("cp_cross")),
        "direct_co_amp": float(co_gain),
        "direct_cross_amp": float(co_gain * cross_gain * amp),
        "direct_pattern_cross_amp": float(pattern_leakage),
        "direct_floor_cross_amp": float(baseline),
    }


def _rng_for(seed: int, *parts: object) -> np.random.Generator:
    text = "|".join([str(int(seed)), *[str(part) for part in parts]])
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    value = int.from_bytes(digest[:8], "little", signed=False)
    return np.random.default_rng(value)


def _make_cir(
    geometry: DS1Geometry,
    reflected_amp: float,
    phi_rad: float,
    snr_db: float | None = None,
    rng: np.random.Generator | None = None,
    direct_amp: float = 1.0,
    direct_delay_bias_m: float = 0.0,
    reflected_delay_bias_m: float = 0.0,
    pulse_width_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    resolution_m = C0 / BW_HZ
    step_m = resolution_m / 8.0
    direct_center_m = geometry.d0_m + float(direct_delay_bias_m)
    start = max(0.0, min(geometry.d0_m, direct_center_m) - 1.5 * resolution_m)
    stop = geometry.dr_m + abs(float(reflected_delay_bias_m)) + 1.5 * resolution_m
    dist = np.arange(start, stop + step_m, step_m, dtype=float)
    effective_resolution = resolution_m * max(float(pulse_width_scale), 0.25)
    direct = _pulse(dist, direct_center_m, effective_resolution)
    reflected = _pulse(dist, geometry.dr_m + float(reflected_delay_bias_m), effective_resolution)
    cir = (
        float(direct_amp) * direct.astype(np.complex128)
        + float(reflected_amp) * np.exp(1j * float(phi_rad)) * reflected.astype(np.complex128)
    )
    if snr_db is not None:
        generator = rng if rng is not None else np.random.default_rng(0)
        noise_rms = abs(float(direct_amp)) * 10.0 ** (-float(snr_db) / 20.0)
        noise = (noise_rms / math.sqrt(2.0)) * (
            generator.normal(size=cir.shape) + 1j * generator.normal(size=cir.shape)
        )
        cir = cir + noise.astype(np.complex128)
    return dist, cir


def _pulse(dist: np.ndarray, center: float, resolution_m: float) -> np.ndarray:
    x = (np.asarray(dist, dtype=float) - float(center)) / float(resolution_m)
    return np.sinc(x) * np.exp(-0.18 * x * x)


def _detect_error_m(
    geometry: DS1Geometry,
    cir_payload: tuple[np.ndarray, np.ndarray],
    detector: str,
    threshold: float | None = None,
) -> tuple[int, float]:
    dist, cir = cir_payload
    mag = np.abs(cir)
    if mag.size == 0 or float(np.nanmax(mag)) <= 0.0:
        return -1, float("nan")
    mode = detector.lower()
    if mode == "oracle":
        idx = _direct_tap_index(geometry, dist)
        err = float(dist[idx] - geometry.d0_m)
    elif mode in {"max_peak", "naive"}:
        idx = int(np.argmax(mag))
        err = float(_parabolic_peak_dist(dist, mag, idx) - geometry.d0_m)
    elif mode in {"leading_edge", "le0.3"}:
        thr = 0.30 if threshold is None else float(threshold)
        level = thr * float(np.max(mag))
        hits = np.flatnonzero(mag >= level)
        idx = int(hits[0]) if hits.size else int(np.argmax(mag))
        err = float(_linear_crossing_dist(dist, mag, idx, level) - geometry.d0_m)
    elif mode in {"dw1000_lde", "dw1000_lde_emulator"}:
        smooth = np.convolve(mag, np.asarray([0.20, 0.60, 0.20]), mode="same")
        med = float(np.median(smooth))
        mad = float(np.median(np.abs(smooth - med)))
        thr_val = max(0.18 * float(np.max(smooth)), med + 4.0 * mad)
        hits = np.flatnonzero(smooth >= thr_val)
        idx = int(hits[0]) if hits.size else int(np.argmax(smooth))
        err = float(_linear_crossing_dist(dist, smooth, idx, thr_val) - geometry.d0_m)
    else:
        raise ValueError(f"unknown detector {detector!r}")
    idx = max(0, min(len(dist) - 1, idx))
    return idx, err


def _linear_crossing_dist(dist: np.ndarray, mag: np.ndarray, idx: int, level: float) -> float:
    idx_i = max(0, min(len(dist) - 1, int(idx)))
    if idx_i <= 0:
        return float(dist[idx_i])
    y0 = float(mag[idx_i - 1])
    y1 = float(mag[idx_i])
    if y1 == y0:
        return float(dist[idx_i])
    frac = float(np.clip((float(level) - y0) / (y1 - y0), 0.0, 1.0))
    return float(float(dist[idx_i - 1]) + frac * (float(dist[idx_i]) - float(dist[idx_i - 1])))


def _parabolic_peak_dist(dist: np.ndarray, mag: np.ndarray, idx: int) -> float:
    idx_i = max(0, min(len(dist) - 1, int(idx)))
    if idx_i <= 0 or idx_i >= len(dist) - 1:
        return float(dist[idx_i])
    y0 = float(mag[idx_i - 1])
    y1 = float(mag[idx_i])
    y2 = float(mag[idx_i + 1])
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) <= 1.0e-12:
        return float(dist[idx_i])
    offset = 0.5 * (y0 - y2) / denom
    offset = float(np.clip(offset, -1.0, 1.0))
    step = float(dist[idx_i + 1] - dist[idx_i])
    return float(dist[idx_i] + offset * step)


def _cp_window_features(
    co_payload: tuple[np.ndarray, np.ndarray],
    cross_payload: tuple[np.ndarray, np.ndarray],
    center_m: float,
) -> tuple[float, float]:
    co_e = _window_energy(co_payload, center_m)
    cross_e = _window_energy(cross_payload, center_m)
    xpr = 10.0 * math.log10((co_e + 1.0e-15) / (cross_e + 1.0e-15))
    s3 = (co_e - cross_e) / (co_e + cross_e + 1.0e-15)
    return float(xpr), float(s3)


def _window_energy(payload: tuple[np.ndarray, np.ndarray], center_m: float) -> float:
    dist, cir = payload
    resolution_m = C0 / BW_HZ
    mask = np.abs(np.asarray(dist, dtype=float) - float(center_m)) <= 0.5 * resolution_m
    if not np.any(mask):
        return 0.0
    return float(np.sum(np.abs(np.asarray(cir, dtype=np.complex128)[mask]) ** 2))


def _direct_tap_index(geometry: DS1Geometry, dist: np.ndarray | None = None) -> int:
    if dist is None:
        dist, _ = _make_cir(geometry, 0.0, 0.0)
    return int(np.argmin(np.abs(np.asarray(dist, dtype=float) - geometry.d0_m)))


def _mislock_histogram(taps: Iterable[int], direct_tap: int, tolerance_taps: int = 1) -> dict[str, int]:
    hist = {"direct": 0, "m1_advance": 0, "late_jump": 0}
    for tap in taps:
        if int(tap) < int(direct_tap) - int(tolerance_taps):
            hist["m1_advance"] += 1
        elif int(tap) > int(direct_tap) + int(tolerance_taps):
            hist["late_jump"] += 1
        else:
            hist["direct"] += 1
    return hist


def _mislock_histogram_from_errors(errors_m: Iterable[float], direct_tap: int, geometry: DS1Geometry) -> dict[str, int]:
    del direct_tap
    tolerance_m = 0.5 * (C0 / BW_HZ)
    hist = {"direct": 0, "m1_advance": 0, "late_jump": 0}
    for err in errors_m:
        value = float(err)
        if abs(value) <= tolerance_m:
            hist["direct"] += 1
        elif value < -tolerance_m:
            hist["m1_advance"] += 1
        else:
            hist["late_jump"] += 1
    if geometry.delta_d_m <= tolerance_m and hist["late_jump"] == 0:
        return hist
    return hist


def auc_direction_agnostic(scores: list[float], labels: list[int]) -> float:
    auc = auc_binary(scores, labels)
    if math.isnan(auc):
        return float("nan")
    return float(max(auc, 1.0 - auc))


def auc_binary(scores: list[float], labels: list[int]) -> float:
    pos = [float(s) for s, y in zip(scores, labels) if int(y) == 1 and math.isfinite(float(s))]
    neg = [float(s) for s, y in zip(scores, labels) if int(y) == 0 and math.isfinite(float(s))]
    if not pos or not neg:
        return float("nan")
    wins = 0.0
    total = 0.0
    for p in pos:
        for n in neg:
            total += 1.0
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return float(wins / total)


def spearman_approx(xs: Iterable[float], ys: Iterable[float]) -> tuple[float, float]:
    x = np.asarray([float(v) for v in xs], dtype=float)
    y = np.asarray([float(v) for v in ys], dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x = x[valid]
    y = y[valid]
    if len(x) < 4:
        return float("nan"), float("nan")
    rx = _ranks(x)
    ry = _ranks(y)
    r = float(np.corrcoef(rx, ry)[0, 1])
    if not math.isfinite(r) or abs(r) >= 1.0:
        return r, 0.0
    z = 0.5 * math.log((1.0 + r) / (1.0 - r)) * math.sqrt(max(len(x) - 3, 1))
    p = math.erfc(abs(z) / math.sqrt(2.0))
    return r, float(p)


def _ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i + 1
        while j < len(values) and values[order[j]] == values[order[i]]:
            j += 1
        rank = (i + j - 1) / 2.0 + 1.0
        ranks[order[i:j]] = rank
        i = j
    return ranks


def _verdict_h1(rows: list[dict[str, float | str]]) -> dict[str, str]:
    unres = [float(r["E_mit"]) for r in rows if float(r["u"]) < 1.0]
    res = [float(r["E_mit"]) for r in rows if float(r["u"]) >= 1.0]
    if not unres or not res:
        verdict = "NOT_ESTABLISHED"
        evidence = "missing resolvability strata"
    else:
        mu_unres = float(np.median(unres))
        mu_res = float(np.median(res))
        ratio = (mu_unres + 1.0e-9) / (mu_res + 1.0e-9)
        verdict = "SUPPORTED" if ratio >= 1.20 else "NOT_SUPPORTED"
        evidence = f"median E_mit u<1={mu_unres:.3g}, u>=1={mu_res:.3g}, ratio={ratio:.3g}"
    return {"id": "H1", "verdict": verdict, "evidence": evidence, "boundary": "resolvability mechanism only"}


def _verdict_h2(rows: list[dict[str, float | str]]) -> dict[str, str]:
    sub = [r for r in rows if float(r["u"]) < 1.0]
    r_val, p_val = spearman_approx([float(r["rho"]) for r in sub], [float(r["tail_rate"]) + float(r["E_mit"]) for r in sub])
    if math.isfinite(r_val) and abs(r_val) >= 0.8 and p_val < 0.05:
        verdict = "SUPPORTED"
    elif math.isfinite(r_val):
        verdict = "PARTIAL"
    else:
        verdict = "NOT_ESTABLISHED"
    evidence = f"Spearman rho-vs-tail/E_mit r={r_val:.3g}, p~{p_val:.3g}, n={len(sub)}"
    return {"id": "H2", "verdict": verdict, "evidence": evidence, "boundary": "reflection-strength diagnostic"}


def _verdict_h3(rows: list[dict[str, float | str]]) -> dict[str, str]:
    if any(str(r.get("cp_leakage_model", "")).startswith("fresnel_split") for r in rows):
        summaries: list[str] = []
        supported = 0
        finite = 0
        for material in sorted({str(r.get("material", "")) for r in rows}):
            sub = [r for r in rows if str(r.get("material", "")) == material]
            metric_key = "co_noise_margin_db" if any("co_noise_margin_db" in r for r in sub) else "E_mit"
            r_val, p_val = spearman_approx([float(r["theta_deg"]) for r in sub], [float(r.get(metric_key, "nan")) for r in sub])
            if math.isfinite(r_val):
                finite += 1
                if abs(r_val) >= 0.45:
                    supported += 1
            theta_star = _theta_star(sub, metric_key)
            summaries.append(f"{material}:r={r_val:.2g},theta*={theta_star:.1f}")
        if supported >= 2:
            verdict = "SUPPORTED_MATERIAL_CONDITIONED"
        elif finite:
            verdict = "PARTIAL_MATERIAL_CONDITIONED"
        else:
            verdict = "NOT_ESTABLISHED"
        evidence = "material-conditioned theta trends on physical leakage metric; " + "; ".join(summaries)
        return {
            "id": "H3",
            "verdict": verdict,
            "evidence": evidence,
            "boundary": "Fresnel plus FFD axial-ratio leakage trend; no measurement claim",
        }
    r_val, p_val = spearman_approx([float(r["theta_deg"]) for r in rows], [float(r["E_mit"]) for r in rows])
    if math.isfinite(r_val) and abs(r_val) >= 0.5 and p_val < 0.05:
        verdict = "PARTIAL"
    elif math.isfinite(r_val):
        verdict = "NOT_SUPPORTED"
    else:
        verdict = "NOT_ESTABLISHED"
    evidence = f"angle-vs-E_mit trend r={r_val:.3g}, p~{p_val:.3g}; exact breakpoint not claimed"
    return {"id": "H3", "verdict": verdict, "evidence": evidence, "boundary": "angle leakage trend; no exact Brewster claim"}


def _theta_star(rows: list[dict[str, float | str]], metric_key: str) -> float:
    valid = [r for r in rows if math.isfinite(float(r.get(metric_key, "nan")))]
    if not valid:
        return float("nan")
    best = max(valid, key=lambda r: float(r.get(metric_key, "nan")))
    return float(best.get("theta_deg", "nan"))


def _verdict_h4(rows: list[dict[str, float | str]]) -> dict[str, str]:
    ratios = [float(r["E_mit"]) for r in rows]
    db_vals = [float(r["E_mit_db"]) for r in rows if math.isfinite(float(r["E_mit_db"]))]
    med = float(np.median(ratios)) if ratios else float("nan")
    med_db = float(np.median(db_vals)) if db_vals else float("nan")
    floor_active = sum(1 for r in rows if str(r.get("denominator_floor_active", "")).lower() == "true")
    verdict = "SUPPORTED" if math.isfinite(med) and med > 1.5 else "NOT_SUPPORTED"
    evidence = f"median conservative E_mit={med:.3g} ({med_db:.3g} dB), floor_active={floor_active}/{len(rows)}"
    return {"id": "H4", "verdict": verdict, "evidence": evidence, "boundary": "noise-aware conservative mitigation, detector-emulator based"}


def _verdict_d1(rows: list[dict[str, float | str]]) -> dict[str, str]:
    late = sum(int(float(r.get("mislock_late_jump", 0))) for r in rows)
    adv = sum(int(float(r.get("mislock_m1_advance", 0))) for r in rows)
    direct = sum(int(float(r.get("mislock_direct", 0))) for r in rows)
    verdict = "SUPPORTED" if (late + adv + direct) > 0 else "NOT_ESTABLISHED"
    evidence = f"locked-tap classes direct={direct}, m1_advance={adv}, late_jump={late}"
    return {"id": "D1", "verdict": verdict, "evidence": evidence, "boundary": "single-reflector error ceiling only"}


def _top_rows(rows: list[dict[str, float | str]], top_k: int) -> list[dict[str, float | str]]:
    ranked = sorted(
        rows,
        key=lambda r: (
            -_truthy_int(r.get("target_lock_gate_pass", "False")),
            -_truthy_int(r.get("buildability_pass", "False")),
            -float(r.get("rank_score", r["E_mit_db"])),
            -float(r.get("tail_reduction_abs_gt_0p3m", 0.0)),
            -float(r.get("p95_reduction_m", 0.0)),
            float(r["u"]),
        ),
    )
    out: list[dict[str, float | str]] = []
    seen: set[str] = set()
    for row in ranked:
        key = str(row.get("geometry_id", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= int(top_k):
            break
    return out


def _snr_values(config: DS1Config) -> tuple[float, ...]:
    vals = [float(v) for v in config.snr_db_values]
    if not any(abs(v - float(config.primary_snr_db)) <= 1.0e-9 for v in vals):
        vals.append(float(config.primary_snr_db))
    return tuple(sorted(set(vals)))


def _is_primary_snr(config: DS1Config, value: float) -> bool:
    return abs(float(value) - float(config.primary_snr_db)) <= 1.0e-9


def _pattern_gain_db(pattern: ReceiverAntennaPattern, direction_world: np.ndarray, boresight_world: np.ndarray) -> float:
    local = _local_direction(direction_world, boresight_world)
    theta = math.degrees(math.acos(float(np.clip(local[2], -1.0, 1.0))))
    phi = math.degrees(math.atan2(float(local[1]), float(local[0])))
    return pattern.gain_db(theta, phi)


def _local_direction(direction_world: np.ndarray, boresight_world: np.ndarray) -> np.ndarray:
    b = normalize(np.asarray(boresight_world, dtype=float))
    h_ref = np.asarray([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(h_ref, b))) > 0.95:
        h_ref = np.asarray([0.0, 1.0, 0.0], dtype=float)
    h = h_ref - float(np.dot(h_ref, b)) * b
    h = normalize(h)
    v = normalize(np.cross(b, h))
    basis = np.column_stack([h, v, b])
    return basis.T @ normalize(np.asarray(direction_world, dtype=float))


def _angle_adjusted_xpol_db(material: Material, theta_deg: float) -> float:
    base = float(material.xpol_coupling_db)
    grazing_penalty = max(0.0, float(theta_deg) - 35.0) * 0.23
    return float(max(3.0, base - grazing_penalty))


def _nonideality_loss_fraction(theta_deg: float, axial_ratio_db: float, switch_iso_db: float, gain_mismatch_db: float, group_delay_ps: float) -> float:
    angle_term = min(max(float(theta_deg), 0.0), 89.0) / 89.0
    ar_term = min(float(axial_ratio_db) / 12.0, 0.60)
    iso_term = min(10.0 ** (-float(switch_iso_db) / 20.0) * 4.0, 0.25)
    gain_term = min(float(gain_mismatch_db) / 10.0, 0.20)
    gd_term = min(float(group_delay_ps) / 250.0, 0.25)
    return float(min(0.85, 0.10 + 0.20 * angle_term + ar_term + iso_term + gain_term + gd_term))


def _degrade_effect(ideal: float, loss_fraction: float) -> float:
    if not math.isfinite(float(ideal)):
        return float("nan")
    if ideal >= 1.0:
        return float(1.0 + (ideal - 1.0) * max(0.0, 1.0 - float(loss_fraction)))
    return float(ideal * (1.0 + 0.25 * float(loss_fraction)))


def _variance(values: Iterable[float]) -> float:
    arr = np.asarray([float(v) for v in values], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size <= 1:
        return 0.0
    return float(np.var(arr, ddof=1))


def _tail_rate(values: Iterable[float], threshold_m: float) -> float:
    arr = np.asarray([float(v) for v in values], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan")
    return float(np.mean(np.abs(arr) > float(threshold_m)))


def _max_abs(values: Iterable[float]) -> float:
    arr = np.asarray([float(v) for v in values], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan")
    return float(np.max(np.abs(arr)))


def _quantile_abs(values: Iterable[float], q: float) -> float:
    arr = np.asarray([float(v) for v in values], dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return float("nan")
    return float(np.quantile(np.abs(arr), float(q)))


def _csv_value(value: object) -> object:
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return f"{value:.12g}"
    return value


def _truthy_int(value: object) -> int:
    return 1 if str(value).strip().lower() in {"1", "true", "yes", "pass"} else 0


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)


def _signed_token(value: float) -> str:
    prefix = "p" if float(value) >= 0.0 else "m"
    return prefix + f"{abs(float(value)):.3f}".replace(".", "p").rstrip("0").rstrip("p")


def _material_summary(material: Material) -> dict[str, float | str]:
    return {
        "name": material.name,
        "kind": material.kind,
        "eps_r": material.eps_r,
        "tan_delta": material.tan_delta,
        "xpol_coupling_db": material.xpol_coupling_db,
    }


def _input_file_status(root: Path) -> list[dict[str, object]]:
    rels = [
        "PATH_REGISTRY.yaml",
        "EXPERIMENT_INVENTORY.csv",
        "RHCP_new_6G7G_11pts.ffd",
        "LHCP_new_6G7G_11pts.ffd",
        "LP_x-axis_pol_6G7G_11pts_new.ffd",
        "LP_y-axis_pol_6G7G_11pts_new.ffd",
    ]
    return [_path_payload(root / rel, rel) for rel in rels]


def _path_payload(path: Path, rel: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"path": rel or str(path), "exists": path.exists()}
    if path.exists() and path.is_file():
        payload["size_bytes"] = path.stat().st_size
        payload["sha256"] = sha256_file(path)
    return payload


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _discovery_markdown(discovery: dict) -> str:
    pattern = discovery["pattern_bundle"]
    lines = [
        "# DS1 Discovery",
        "",
        f"Created UTC: {discovery['created_at_utc']}",
        "",
        "## Verdict",
        "",
        "PASS: DS1 has a bounded image-method single-reflector generator, detector stack, material table, and pattern-source registry.",
        "",
        "## Interface Map",
        "",
        f"- Geometry generator: {discovery['path_construction']}",
        f"- Jones/Fresnel path: {discovery['jones_fresnel_path']}",
        f"- Pattern mode: requested `{pattern['requested_mode']}`, resolved `{pattern['resolved_mode']}`, loaded `{pattern['loaded']}`",
        f"- Direct XPR mode: `{discovery['direct_calibration']['direct_xpr_mode']}`, XPR `{float(discovery['direct_calibration']['direct_xpr_db']):.3g} dB`",
        f"- Direct phase offsets: co `{float(discovery['direct_calibration']['direct_phase_offset_co_m']):.6g} m`, cross `{float(discovery['direct_calibration']['direct_phase_offset_cross_m']):.6g} m`",
        f"- Phase mode: `{discovery['phase_mode']['active']}`",
        f"- Detectors: {', '.join(discovery['detectors'])}",
        f"- Feature extractors: {', '.join(discovery['feature_extractors'])}",
        "",
        "## Claim Boundaries",
        "",
    ]
    lines.extend(f"- {item}" for item in discovery["claim_boundary"])
    lines.extend(["", "## Pattern Sources", ""])
    for key, value in pattern["sources"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {note}" for note in pattern["notes"])
    lines.append("- E_mit_phase_ensemble is a stress-statistic output and must not be compared directly to fixed physical AEDT S21.")
    lines.append("")
    return "\n".join(lines)


def _convention_lock_markdown(lock: dict[str, float | str]) -> str:
    return "\n".join(
        [
            "# DS1v3 Convention Lock",
            "",
            f"Status: {lock.get('status', 'UNKNOWN')}",
            "",
            "## Adopted Conventions",
            "",
            f"- Antenna circular definition: `{lock.get('circular_definition', '')}`",
            f"- Fresnel co-sense definition: `{lock.get('fresnel_co_definition', '')}`",
            "",
            "## Antenna Boresight Checks",
            "",
            f"- RHCP file boresight XPD: `{float(lock.get('rhcp_boresight_xpd_db', float('nan'))):.3f} dB`",
            f"- LHCP file boresight XPD: `{float(lock.get('lhcp_boresight_xpd_db', float('nan'))):.3f} dB`",
            f"- RHCP file boresight AR: `{float(lock.get('rhcp_boresight_ar_db', float('nan'))):.3f} dB`",
            f"- LHCP file boresight AR: `{float(lock.get('lhcp_boresight_ar_db', float('nan'))):.3f} dB`",
            "",
            "## Fresnel PEC Normal Check",
            "",
            f"- PEC normal gamma_TE: `{lock.get('pec_normal_gamma_te', '')}`",
            f"- PEC normal gamma_TM: `{lock.get('pec_normal_gamma_tm', '')}`",
            f"- PEC normal co-sense abs: `{float(lock.get('pec_normal_co_abs', float('nan'))):.6g}`",
            f"- PEC normal cross-sense abs: `{float(lock.get('pec_normal_cross_abs', float('nan'))):.6g}`",
            "",
            "Claim language: FFD includes complex vector-field components (Re/Im Etheta, Ephi); the DS1-v2 fixed run used total-field gain, whereas DS1-v3 derives co/cross and axial-ratio antenna response from the vector field.",
            "",
        ]
    )


def _now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def command_line_text() -> str:
    return " ".join([Path(sys.argv[0]).name, *sys.argv[1:]])
