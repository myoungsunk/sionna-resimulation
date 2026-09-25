from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .antennas import (
    ReceiverAntennaPattern,
    direction_tag_body_to_antenna_mount,
    direction_to_pattern_angles,
    parse_mount_rotation,
)
from .core import C0, Scene, Surface, fresnel_reflection
from .scenes import make_room_abc_scene
from .trace import enumerate_paths
from .h10b_range_factor import (
    extract_h10b_amplitude_observations as _h10b_extract_amplitudes,
    extract_h10b_range_observations as _h10b_extract_ranges,
    h10b_ffd_amplitude_log_score_batch,
    h10b_physical_range_log_score_batch,
)
from .h10b_proximity_doa import (
    HEADING_POLICIES as _HEADING_POLICIES,
    ProximityDOAConfig as _ProximityDOAConfig,
    combined_doa_log_score_batch as _combined_doa_log_score_batch,
    extract_tilt_contrast_rhcp_db as _extract_tilt_contrast_rhcp_db,
    heading_proxy_log_score_batch as _heading_proxy_log_score_batch,
    rssd_doa_log_score_batch as _rssd_doa_log_score_batch,
    sigma_heading_doa as _sigma_heading_doa,
)


EPS = 1e-30
DEFAULT_CENTER_FREQUENCY_HZ = 6.5e9

# ──────────────────────────────────────────────────────────────────────────────
# Module-level FFD predictor singleton.
#
# Set once at startup via ``set_h10b_ffd_predictor(predictor)`` to enable FFD-
# based amplitude scoring in the particle filter.  When None (default) the
# legacy proxy scorer is used instead.
# ──────────────────────────────────────────────────────────────────────────────
_H10B_FFD_PREDICTOR: Any = None  # type: ignore[name-defined]


def set_h10b_ffd_predictor(predictor: Any) -> None:  # type: ignore[override]
    """Register an ``H10BFFDPredictor`` for use inside the particle filter.

    When set, ``measurement_candidate_log_score_terms`` replaces the proxy
    sinusoidal amplitude scorer with FFD-based predictions.  Set to ``None``
    to revert to the legacy proxy path.

    Args:
        predictor: An ``H10BFFDPredictor`` instance or ``None``.
    """
    global _H10B_FFD_PREDICTOR
    _H10B_FFD_PREDICTOR = predictor


# ──────────────────────────────────────────────────────────────────────────────
# Module-level Proximity DOA config singleton.
#
# Shared across all particle-filter calls to avoid per-call instantiation.
# Can be replaced via set_proximity_doa_config() for non-default σ_C or LUT
# resolution.
# ──────────────────────────────────────────────────────────────────────────────
_DOA_CONFIG: _ProximityDOAConfig = _ProximityDOAConfig()


def set_proximity_doa_config(config: _ProximityDOAConfig) -> None:
    """Replace the module-level ProximityDOAConfig used inside the particle filter."""
    global _DOA_CONFIG
    _DOA_CONFIG = config


# Sub-channel masks for ablation arms (canonical index order:
#   0=tiltA_lhcp, 1=tiltA_rhcp, 2=tiltB_lhcp, 3=tiltB_rhcp)
_CH_MASK_LOOKUP: dict[str, np.ndarray] = {
    "tiltA_only":       np.array([True,  True,  False, False], dtype=bool),
    "tiltB_only":       np.array([False, False, True,  True],  dtype=bool),
    "lhcp_only":        np.array([True,  False, True,  False], dtype=bool),
    "rhcp_only":        np.array([False, True,  False, True],  dtype=bool),
    "tiltA_lhcp_only":  np.array([True,  False, False, False], dtype=bool),
    "tiltA_rhcp_only":  np.array([False, True,  False, False], dtype=bool),
    "tiltB_lhcp_only":  np.array([False, False, True,  False], dtype=bool),
    "tiltB_rhcp_only":  np.array([False, False, False, True],  dtype=bool),
}
DEFAULT_BANDWIDTH_HZ = 2.0e9
DEFAULT_LEGACY_DUAL_TAG_H10B_FEATURES_WIDE = (
    "scripts/results/dual_tag_h10b_alpha_sweep_rot0_fixed_azimuth_20260510_fullrun/"
    "alpha060_chunks/chunk_0601_0900/dual_tag_features_wide.csv"
)
H10B_RAW_CIR_CHANNELS = ("ANT1_RHCP", "ANT1_LHCP", "ANT2_RHCP", "ANT2_LHCP")
H10B_RAW_CIR_CHANNEL_SUFFIX = {
    "ANT1_RHCP": "ant1_rhcp",
    "ANT1_LHCP": "ant1_lhcp",
    "ANT2_RHCP": "ant2_rhcp",
    "ANT2_LHCP": "ant2_lhcp",
}
H10B_RAW_CIR_CHANNEL_RSS_COLUMN = {
    "ANT1_RHCP": "RSS_ant1_RH_db",
    "ANT1_LHCP": "RSS_ant1_LH_db",
    "ANT2_RHCP": "RSS_ant2_RH_db",
    "ANT2_LHCP": "RSS_ant2_LH_db",
}
H10B_RAW_CIR_VECTOR_FIELDS = (
    "lde_delay_s",
    "range_m",
    "peak_index",
    "lde_index",
    "noise_floor",
    "threshold",
    "peak_power",
    "amplitude_db",
    "status",
)


def h10b_raw_cir_vector_columns() -> list[str]:
    return [
        f"h10b_{H10B_RAW_CIR_CHANNEL_SUFFIX[channel]}_{field}"
        for channel in H10B_RAW_CIR_CHANNELS
        for field in H10B_RAW_CIR_VECTOR_FIELDS
    ]


@dataclass(frozen=True)
class Stage01Config:
    output_dir: Path
    run_id: str = "SIM_NEW_CP_VA_SLAM_01_STAGE01_DEBUG"
    simulation_name: str = "SIM_NEW_CP_VA_SLAM_01"
    branch_id: str = "P1_P2_P3_STAGE01"
    random_seed: int = 20260514
    num_snapshots: int = 50
    dt_s: float = 0.5
    bandwidth_hz: float = DEFAULT_BANDWIDTH_HZ
    time_resolution_kappa: float = 1.0
    frequency_hz: float = DEFAULT_CENTER_FREQUENCY_HZ
    max_reflections: int = 2
    num_paths_max: int = 18
    threshold_db: float = -35.0
    range_estimator_mode: str = "peak_group_center"
    lde_relative_threshold: float = 0.20
    lde_noise_scale: float = 0.10
    scene_ids: tuple[str, ...] = ("R0", "R1A", "R2", "R3", "R4", "R5")
    trajectory_ids: tuple[str, ...] = ("T0", "T1", "T2", "T3", "T4", "T5", "T6", "T7")
    scenario_pairs: tuple[str, ...] = ()
    algorithm_ids: tuple[str, ...] = ()
    solver_num_particles: int = 48
    solver_max_candidates: int = 24
    solver_da_particle_top: int = 16
    polarization_mode: str = "CP"
    anchor_linear_pol_axis_deg: float = 0.0
    tag_ant1_linear_pol_axis_deg: float = 0.0
    tag_ant2_linear_pol_axis_deg: float = 90.0
    tag_pol_tilt_deg: float = 0.0
    anchor_pol_tilt_deg: float = 0.0
    tag_antenna_model_mode: str = "synthetic_proxy"
    legacy_dual_tag_artifact_path: str = DEFAULT_LEGACY_DUAL_TAG_H10B_FEATURES_WIDE
    legacy_dual_tag_rssd_channel: str = "total"
    legacy_dual_tag_alpha_deg: float = 60.0
    legacy_dual_tag_rotation_deg: float = 0.0
    legacy_dual_tag_rssd_prediction_mode: str = "auto"
    legacy_dual_tag_power_offset_mode: str = "auto"
    lp_copol_gain_pattern_file: str = "LP_+45_new_6G7G_11pts.ffd"
    lp_crosspol_gain_pattern_file: str = "LP_-45_new_6G7G_11pts.ffd"
    rx_ant1_rhcp_pattern_file: str = ""
    rx_ant1_lhcp_pattern_file: str = ""
    rx_ant2_rhcp_pattern_file: str = ""
    rx_ant2_lhcp_pattern_file: str = ""
    tag_attitude_source: str = "yaw_only"
    tag_pitch_deg: float = 0.0
    tag_roll_deg: float = 0.0
    rx_ant1_mount_rotation: str = ""
    rx_ant2_mount_rotation: str = ""
    pattern_gain_normalization: str = "absolute_dbi"
    pattern_phase_convention: str = "ffd_complex_field"
    pattern_pol_basis: str = "rhcp_lhcp"
    use_te_tm_reflection: bool = True
    material_fresnel_model: str = "te_tm_fresnel"
    path_polarization_tracking: bool = True
    wall_offset_noise_m: float = 0.0
    wall_normal_noise_deg: float = 0.0
    odometry_noise_scale: float = 1.0
    range_variance_scale: float = 1.0
    perturbation_config_id: str = "nominal"
    require_independent_motion_inputs: bool = False
    measurement_regularizer_target: str = "none"
    measurement_regularizer_centered_cap: float = 0.0
    measurement_regularizer_spread_threshold: float = 1.5
    measurement_regularizer_algorithms: str = "B9"
    orientation_control_mode: str = "nominal"
    yaw_noise_deg: float = 0.0
    yaw_shuffle: bool = False
    yaw_shuffle_level: str = "within_slice"
    yaw_fixed_deg: float = 0.0
    disable_orientation: bool = False
    rssd_control_mode: str = "nominal"
    rssd_noise_std_db: float = 0.0
    rssd_noise_scale: float = 0.0
    rssd_shuffle: bool = False
    rssd_shuffle_level: str = "within_slice"
    rssd_sign_flip: bool = False
    disable_rssd: bool = False
    truth_clean_solver: bool = False
    candidate_mode: str = "known_catalog"
    strict_truth_audit: bool = False
    fail_on_truth_leakage: bool = False

    @property
    def time_resolution_s(self) -> float:
        return float(self.time_resolution_kappa) / float(self.bandwidth_hz)

    @property
    def distance_resolution_m(self) -> float:
        return C0 * self.time_resolution_s


@dataclass(frozen=True)
class SceneSpec:
    scene_id: str
    room_type: str
    L_m: float
    W_m: float
    H_m: float
    floorplan_type: str
    has_blocker: bool
    has_furniture: bool
    has_metal_region: bool
    has_glass_region: bool
    scene: Scene


def db10(value: float | np.ndarray) -> float | np.ndarray:
    return 10.0 * np.log10(np.maximum(value, EPS))


def db20(value: float | np.ndarray) -> float | np.ndarray:
    return 20.0 * np.log10(np.maximum(value, EPS))


def az_el_deg(vec: np.ndarray) -> tuple[float, float]:
    arr = np.asarray(vec, dtype=float).reshape(3)
    norm = float(np.linalg.norm(arr))
    if norm <= 0.0:
        return float("nan"), float("nan")
    arr = arr / norm
    az = math.degrees(math.atan2(arr[1], arr[0]))
    el = math.degrees(math.asin(float(np.clip(arr[2], -1.0, 1.0))))
    return float(az), float(el)


def wrap_deg(angle_deg: float) -> float:
    return float((angle_deg + 180.0) % 360.0 - 180.0)


def normalize_polarization_mode(mode: str) -> str:
    out = str(mode).strip().upper()
    if out not in {"CP", "LP"}:
        raise ValueError(f"Unsupported polarization_mode={mode!r}; expected CP or LP")
    return out


def normalize_tag_antenna_model_mode(mode: str) -> str:
    out = str(mode).strip().lower()
    aliases = {
        "legacy_h10b": "legacy_h10b_dual_tilted",
        "legacy_dual_tag_h10b": "legacy_h10b_dual_tilted",
        "legacy_h10b_dual_tilted_cp": "legacy_h10b_dual_tilted",
        "h10b_dual_tag": "legacy_h10b_dual_tilted",
        "real_pattern": "tilted_real_pattern",
        "tilted_real": "tilted_real_pattern",
        "real_tilted": "tilted_real_pattern",
        "tilted_receiver_pattern": "tilted_real_pattern",
    }
    out = aliases.get(out, out)
    if out not in {"synthetic_proxy", "legacy_h10b_dual_tilted", "tilted_real_pattern"}:
        raise ValueError(
            f"Unsupported tag_antenna_model_mode={mode!r}; "
            "expected synthetic_proxy, legacy_h10b_dual_tilted, or tilted_real_pattern"
        )
    return out


def require_connected_tilted_real_pattern_frontend(stage_name: str) -> None:
    raise NotImplementedError(
        f"tag_antenna_model_mode=tilted_real_pattern is registered for configuration and manifest tracking, "
        f"but {stage_name} is not connected to the real tilted receiver pattern frontend yet. "
        "Use synthetic_proxy or legacy_h10b_dual_tilted for full simulation until the Step 2/3 pattern "
        "transform and feature-generation path is implemented."
    )


def normalize_legacy_dual_tag_rssd_channel(channel: str) -> str:
    out = str(channel).strip().lower()
    aliases = {
        "rssd": "total",
        "rssd_db": "total",
        "combined": "total",
        "both": "mean_pol",
        "mean": "mean_pol",
        "rhcp": "rh",
        "lhcp": "lh",
    }
    out = aliases.get(out, out)
    if out not in {"total", "rh", "lh", "mean_pol"}:
        raise ValueError(
            f"Unsupported legacy_dual_tag_rssd_channel={channel!r}; "
            "expected total, rh, lh, or mean_pol"
        )
    return out


def normalize_legacy_dual_tag_rssd_prediction_mode(mode: str, tag_model: str = "synthetic_proxy") -> str:
    out = str(mode).strip().lower()
    aliases = {
        "artifact": "artifact_lut",
        "artifact_theta_range": "artifact_lut",
        "artifact_theta_range_nearest": "artifact_lut",
        "h10b": "artifact_lut",
        "h10b_artifact": "artifact_lut",
        "legacy_h10b": "artifact_lut",
        "synthetic": "synthetic_proxy",
        "proxy": "synthetic_proxy",
        "old": "synthetic_proxy",
        "tilted": "tilted_real_pattern",
        "real_pattern": "tilted_real_pattern",
        "tilted_real": "tilted_real_pattern",
    }
    out = aliases.get(out, out)
    if out == "auto":
        normalized_tag_model = normalize_tag_antenna_model_mode(tag_model)
        if normalized_tag_model == "legacy_h10b_dual_tilted":
            return "artifact_lut"
        if normalized_tag_model == "tilted_real_pattern":
            return "tilted_real_pattern"
        return "synthetic_proxy"
    if out not in {"synthetic_proxy", "artifact_lut", "tilted_real_pattern"}:
        raise ValueError(
            f"Unsupported legacy_dual_tag_rssd_prediction_mode={mode!r}; "
            "expected auto, synthetic_proxy, artifact_lut, or tilted_real_pattern"
        )
    return out


def normalize_legacy_dual_tag_power_offset_mode(mode: str) -> str:
    out = str(mode).strip().lower()
    aliases = {
        "direct": "none",
        "raw": "none",
        "off": "none",
        "disabled": "none",
        "match_amp": "match_existing_amp",
        "match_measured_amp": "match_existing_amp",
        "legacy": "match_existing_amp",
    }
    out = aliases.get(out, out)
    if out == "auto":
        # In legacy H10B mode, "auto" means direct artifact powers. The older
        # amplitude-matched behavior remains available as match_existing_amp.
        return "none"
    if out not in {"none", "match_existing_amp"}:
        raise ValueError(
            f"Unsupported legacy_dual_tag_power_offset_mode={mode!r}; "
            "expected auto, none, or match_existing_amp"
        )
    return out


def normalize_range_estimator_mode(mode: str) -> str:
    out = str(mode).strip().lower()
    aliases = {
        "center": "peak_group_center",
        "legacy": "peak_group_center",
        "lde": "lde_proxy",
        "leading_edge": "lde_proxy",
        "leading_edge_proxy": "lde_proxy",
        "h10b_raw": "h10b_raw_cir_lde",
        "raw_cir": "h10b_raw_cir_lde",
        "raw_cir_lde": "h10b_raw_cir_lde",
        "dw_lde": "h10b_raw_cir_lde",
        "dw1000_lde": "h10b_raw_cir_lde",
        "h10b_dw_lde": "h10b_raw_cir_lde",
        "h10b_dw1000_lde": "h10b_raw_cir_lde",
    }
    out = aliases.get(out, out)
    allowed = {"peak_group_center", "lde_proxy", "h10b_artifact_lde", "h10b_artifact_range", "h10b_raw_cir_lde"}
    if out not in allowed:
        raise ValueError(
            f"Unsupported range_estimator_mode={mode!r}; "
            "expected peak_group_center, lde_proxy, h10b_artifact_lde, or h10b_raw_cir_lde"
        )
    return out


def range_estimator_uses_raw_cir(mode: str) -> bool:
    return normalize_range_estimator_mode(mode) == "h10b_raw_cir_lde"


def legacy_dual_tag_boresights(alpha_deg: float = 60.0, rotation_deg: float = 0.0) -> dict[str, dict[str, float]]:
    """Return the legacy H10B dual-tag local boresights.

    The legacy alpha=60, rotation=0 artifact has tag_ant1=(+0.5,0,0.866)
    and tag_ant2=(-0.5,0,0.866), with RHCP/LHCP channels on each set.
    """

    half = math.radians(float(alpha_deg) / 2.0)
    rot = math.radians(float(rotation_deg))
    xy = math.sin(half)
    z = math.cos(half)
    cx = math.cos(rot)
    sy = math.sin(rot)
    return {
        "tag_ant1": {
            "boresight_x": xy * cx,
            "boresight_y": xy * sy,
            "boresight_z": z,
            "signed_elevation_deg": float(alpha_deg) / 2.0,
        },
        "tag_ant2": {
            "boresight_x": -xy * cx,
            "boresight_y": -xy * sy,
            "boresight_z": z,
            "signed_elevation_deg": -float(alpha_deg) / 2.0,
        },
    }


def resolve_legacy_dual_tag_artifact_path(config: Stage01Config) -> Path:
    path = Path(str(config.legacy_dual_tag_artifact_path))
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


_LEGACY_DUAL_TAG_H10B_LUT_CACHE: dict[tuple[str, float, float], pd.DataFrame] = {}


def _resolve_legacy_dual_tag_artifact_path_value(path_value: object) -> Path:
    path = Path(str(path_value))
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def load_legacy_dual_tag_h10b_lut_from_path(path: Path, alpha_deg: float, rotation_deg: float) -> pd.DataFrame:
    path = _resolve_legacy_dual_tag_artifact_path_value(path)
    cache_key = (str(path), round(float(alpha_deg), 6), round(float(rotation_deg), 6))
    cached = _LEGACY_DUAL_TAG_H10B_LUT_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()
    if not path.exists():
        raise FileNotFoundError(f"legacy dual-tag/H10B artifact not found: {path}")
    lut = pd.read_csv(path)
    required = {
        "dual_tag_alpha_deg",
        "tag_rotation_deg",
        "anchor_x",
        "anchor_y",
        "anchor_z",
        "tag_x",
        "tag_y",
        "tag_z",
        "RSS_ant1_RH_db",
        "RSS_ant1_LH_db",
        "RSS_ant2_RH_db",
        "RSS_ant2_LH_db",
    }
    missing = sorted(required - set(lut.columns))
    if missing:
        raise ValueError(f"legacy dual-tag/H10B artifact missing required columns: {missing}")

    out = lut.copy()
    for col in required:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    alpha = float(alpha_deg)
    rotation = float(rotation_deg)
    mask = np.isclose(out["dual_tag_alpha_deg"], alpha, atol=1e-6) & np.isclose(out["tag_rotation_deg"], rotation, atol=1e-6)
    if mask.any():
        out = out.loc[mask].copy()
    vec = out[["tag_x", "tag_y", "tag_z"]].to_numpy(float) - out[["anchor_x", "anchor_y", "anchor_z"]].to_numpy(float)
    horiz = np.linalg.norm(vec[:, :2], axis=1)
    rng = np.linalg.norm(vec, axis=1)
    out["legacy_h10b_range_m"] = rng
    out["legacy_h10b_theta_abs_deg"] = np.abs(np.degrees(np.arctan2(vec[:, 2], np.maximum(horiz, 1e-9))))
    if "source_tx_rx_dist_m" in out.columns:
        source_range = pd.to_numeric(out["source_tx_rx_dist_m"], errors="coerce")
        out["legacy_h10b_range_m"] = source_range.fillna(out["legacy_h10b_range_m"])
    out = out.reset_index(drop=True)
    _LEGACY_DUAL_TAG_H10B_LUT_CACHE[cache_key] = out.copy()
    return out


def load_legacy_dual_tag_h10b_lut(config: Stage01Config) -> pd.DataFrame:
    return load_legacy_dual_tag_h10b_lut_from_path(
        resolve_legacy_dual_tag_artifact_path(config),
        config.legacy_dual_tag_alpha_deg,
        config.legacy_dual_tag_rotation_deg,
    )


_RECEIVER_GAIN_PATTERN_CACHE: dict[tuple[str, float, str], ReceiverAntennaPattern] = {}


def _object_get(obj: object, name: str, default: object = "") -> object:
    if isinstance(obj, pd.Series):
        return _row_get(obj, name, default)
    return getattr(obj, name, default)


def _resolve_repo_file(path_value: object, fallback_name: str) -> Path:
    text = str(path_value or "").strip() or fallback_name
    path = Path(text)
    if path.is_absolute():
        return path
    return Path(__file__).resolve().parents[1] / path


def _load_receiver_gain_pattern(source: object, fallback_name: str, pol_mode: str, frequency_hz: float) -> ReceiverAntennaPattern:
    path = _resolve_repo_file(source, fallback_name)
    key = (str(path.resolve()), float(frequency_hz), str(pol_mode).upper())
    cached = _RECEIVER_GAIN_PATTERN_CACHE.get(key)
    if cached is not None:
        return cached
    if not path.exists():
        raise FileNotFoundError(f"Receiver antenna pattern file not found: {path}")
    if path.suffix.lower() == ".ffd":
        pattern = ReceiverAntennaPattern.from_ffd(path, frequency_hz=frequency_hz, pol_mode=pol_mode)
    else:
        pattern = ReceiverAntennaPattern.from_csv(path, pol_mode=pol_mode, frequency_hz=frequency_hz)
    _RECEIVER_GAIN_PATTERN_CACHE[key] = pattern
    return pattern


def _tilted_real_pattern_sources(config_or_row: object) -> dict[str, str]:
    return {
        "RSS_ant1_RH_db": str(_resolve_repo_file(_object_get(config_or_row, "rx_ant1_rhcp_pattern_file", ""), "RHCP_new_6G7G_11pts.ffd")),
        "RSS_ant1_LH_db": str(_resolve_repo_file(_object_get(config_or_row, "rx_ant1_lhcp_pattern_file", ""), "LHCP_new_6G7G_11pts.ffd")),
        "RSS_ant2_RH_db": str(_resolve_repo_file(_object_get(config_or_row, "rx_ant2_rhcp_pattern_file", ""), "RHCP_new_6G7G_11pts.ffd")),
        "RSS_ant2_LH_db": str(_resolve_repo_file(_object_get(config_or_row, "rx_ant2_lhcp_pattern_file", ""), "LHCP_new_6G7G_11pts.ffd")),
    }


def _mount_rotation_from_boresight(boresight: np.ndarray) -> np.ndarray:
    z_axis = np.asarray(boresight, dtype=float).reshape(3)
    z_axis = z_axis / max(float(np.linalg.norm(z_axis)), 1e-12)
    ref = np.array([0.0, 1.0, 0.0], dtype=float)
    if abs(float(np.dot(ref, z_axis))) > 0.95:
        ref = np.array([1.0, 0.0, 0.0], dtype=float)
    x_axis = np.cross(ref, z_axis)
    x_axis = x_axis / max(float(np.linalg.norm(x_axis)), 1e-12)
    y_axis = np.cross(z_axis, x_axis)
    y_axis = y_axis / max(float(np.linalg.norm(y_axis)), 1e-12)
    return np.column_stack([x_axis, y_axis, z_axis])


def _tilted_real_mount_rotations(config_or_row: object) -> dict[str, np.ndarray]:
    ant1_value = str(_object_get(config_or_row, "rx_ant1_mount_rotation", "") or "").strip()
    ant2_value = str(_object_get(config_or_row, "rx_ant2_mount_rotation", "") or "").strip()
    if ant1_value and ant2_value:
        return {
            "ant1": parse_mount_rotation(ant1_value),
            "ant2": parse_mount_rotation(ant2_value),
        }
    alpha = float(_object_get(config_or_row, "legacy_dual_tag_alpha_deg", 60.0))
    rotation = float(_object_get(config_or_row, "legacy_dual_tag_rotation_deg", 0.0))
    boresights = legacy_dual_tag_boresights(alpha, rotation)
    ant1_boresight = np.array(
        [
            boresights["tag_ant1"]["boresight_x"],
            boresights["tag_ant1"]["boresight_y"],
            boresights["tag_ant1"]["boresight_z"],
        ],
        dtype=float,
    )
    ant2_boresight = np.array(
        [
            boresights["tag_ant2"]["boresight_x"],
            boresights["tag_ant2"]["boresight_y"],
            boresights["tag_ant2"]["boresight_z"],
        ],
        dtype=float,
    )
    return {
        "ant1": parse_mount_rotation(ant1_value) if ant1_value else _mount_rotation_from_boresight(ant1_boresight),
        "ant2": parse_mount_rotation(ant2_value) if ant2_value else _mount_rotation_from_boresight(ant2_boresight),
    }


def _direction_from_body_angles(beta_body_deg: float, theta_elevation_deg: float) -> np.ndarray:
    beta = math.radians(float(beta_body_deg))
    el = math.radians(float(theta_elevation_deg))
    return np.array([math.cos(el) * math.cos(beta), math.cos(el) * math.sin(beta), math.sin(el)], dtype=float)


def tilted_real_pattern_channel_gains_db(
    beta_body_deg: np.ndarray | float,
    theta_elevation_deg: np.ndarray | float,
    config_or_row: object,
) -> dict[str, np.ndarray]:
    beta_arr = np.atleast_1d(np.asarray(beta_body_deg, dtype=float))
    theta_arr = np.atleast_1d(np.asarray(theta_elevation_deg, dtype=float))
    if beta_arr.shape != theta_arr.shape:
        beta_arr, theta_arr = np.broadcast_arrays(beta_arr, theta_arr)
    frequency_hz = float(_object_get(config_or_row, "frequency_hz", DEFAULT_CENTER_FREQUENCY_HZ))
    sources = _tilted_real_pattern_sources(config_or_row)
    patterns = {
        "RSS_ant1_RH_db": _load_receiver_gain_pattern(sources["RSS_ant1_RH_db"], "RHCP_new_6G7G_11pts.ffd", "RHCP", frequency_hz),
        "RSS_ant1_LH_db": _load_receiver_gain_pattern(sources["RSS_ant1_LH_db"], "LHCP_new_6G7G_11pts.ffd", "LHCP", frequency_hz),
        "RSS_ant2_RH_db": _load_receiver_gain_pattern(sources["RSS_ant2_RH_db"], "RHCP_new_6G7G_11pts.ffd", "RHCP", frequency_hz),
        "RSS_ant2_LH_db": _load_receiver_gain_pattern(sources["RSS_ant2_LH_db"], "LHCP_new_6G7G_11pts.ffd", "LHCP", frequency_hz),
    }
    rotations = _tilted_real_mount_rotations(config_or_row)
    out = {key: np.full(beta_arr.shape, np.nan, dtype=float) for key in patterns}
    channel_to_mount = {
        "RSS_ant1_RH_db": "ant1",
        "RSS_ant1_LH_db": "ant1",
        "RSS_ant2_RH_db": "ant2",
        "RSS_ant2_LH_db": "ant2",
    }
    for idx, (beta_value, theta_value) in enumerate(zip(beta_arr.flat, theta_arr.flat)):
        if not (np.isfinite(beta_value) and np.isfinite(theta_value)):
            continue
        body_dir = _direction_from_body_angles(float(beta_value), float(theta_value))
        for key, pattern in patterns.items():
            local_dir = direction_tag_body_to_antenna_mount(body_dir, rotations[channel_to_mount[key]])
            pattern_theta, pattern_phi = direction_to_pattern_angles(local_dir)
            out[key].flat[idx] = pattern.gain_db(pattern_theta, pattern_phi)
    return out


def _tilted_real_pattern_metadata(config_or_row: object) -> dict[str, object]:
    sources = _tilted_real_pattern_sources(config_or_row)
    rotations = _tilted_real_mount_rotations(config_or_row)
    return {
        "rx_ant1_rhcp_pattern_file": sources["RSS_ant1_RH_db"],
        "rx_ant1_lhcp_pattern_file": sources["RSS_ant1_LH_db"],
        "rx_ant2_rhcp_pattern_file": sources["RSS_ant2_RH_db"],
        "rx_ant2_lhcp_pattern_file": sources["RSS_ant2_LH_db"],
        "tag_attitude_source": str(_object_get(config_or_row, "tag_attitude_source", "yaw_only")),
        "tag_pitch_deg": float(_object_get(config_or_row, "tag_pitch_deg", 0.0)),
        "tag_roll_deg": float(_object_get(config_or_row, "tag_roll_deg", 0.0)),
        "rx_ant1_mount_rotation": str(_object_get(config_or_row, "rx_ant1_mount_rotation", "")),
        "rx_ant2_mount_rotation": str(_object_get(config_or_row, "rx_ant2_mount_rotation", "")),
        "rx_ant1_mount_matrix": json.dumps(rotations["ant1"].round(12).tolist(), ensure_ascii=True),
        "rx_ant2_mount_matrix": json.dumps(rotations["ant2"].round(12).tolist(), ensure_ascii=True),
        "pattern_gain_normalization": str(_object_get(config_or_row, "pattern_gain_normalization", "absolute_dbi")),
        "pattern_phase_convention": str(_object_get(config_or_row, "pattern_phase_convention", "ffd_complex_field")),
        "pattern_pol_basis": str(_object_get(config_or_row, "pattern_pol_basis", "rhcp_lhcp")),
        "frequency_hz": float(_object_get(config_or_row, "frequency_hz", DEFAULT_CENTER_FREQUENCY_HZ)),
    }


def _select_legacy_dual_tag_lut_row(lut: pd.DataFrame, theta_elevation_deg: float, range_m: float) -> pd.Series:
    theta_abs = abs(float(theta_elevation_deg))
    lut_theta = pd.to_numeric(lut["legacy_h10b_theta_abs_deg"], errors="coerce").to_numpy(float)
    lut_range = pd.to_numeric(lut["legacy_h10b_range_m"], errors="coerce").to_numpy(float)
    theta_scale = max(float(np.nanstd(lut_theta)), 1.0)
    range_scale = max(float(np.nanstd(lut_range)), 0.5)
    score = ((lut_theta - theta_abs) / theta_scale) ** 2 + ((lut_range - float(range_m)) / range_scale) ** 2
    score = np.where(np.isfinite(score), score, np.inf)
    idx = int(np.argmin(score))
    if not np.isfinite(score[idx]):
        raise ValueError("legacy dual-tag/H10B artifact has no finite LUT match")
    return lut.iloc[idx]


def _db_sum(values_db: list[float]) -> float:
    linear = sum(10.0 ** (float(value) / 10.0) for value in values_db if np.isfinite(float(value)))
    return float(db10(linear)) if linear > 0.0 else float("nan")


def _db_sum_arrays(values_db: list[np.ndarray]) -> np.ndarray:
    if not values_db:
        return np.zeros(0, dtype=float)
    arrays = [np.asarray(value, dtype=float) for value in values_db]
    shape = np.broadcast_shapes(*[arr.shape for arr in arrays])
    linear = np.zeros(shape, dtype=float)
    for arr in arrays:
        b = np.broadcast_to(arr, shape)
        linear += np.where(np.isfinite(b), 10.0 ** (b / 10.0), 0.0)
    return np.where(linear > 0.0, db10(linear), np.nan)


def _legacy_dual_tag_selected_rssd_db(lut_row: pd.Series, channel: str, offset_db: float = 0.0) -> float:
    channel = normalize_legacy_dual_tag_rssd_channel(channel)
    ant1_rh = float(lut_row["RSS_ant1_RH_db"]) + float(offset_db)
    ant1_lh = float(lut_row["RSS_ant1_LH_db"]) + float(offset_db)
    ant2_rh = float(lut_row["RSS_ant2_RH_db"]) + float(offset_db)
    ant2_lh = float(lut_row["RSS_ant2_LH_db"]) + float(offset_db)
    ant1_total_db = _db_sum([ant1_rh, ant1_lh])
    ant2_total_db = _db_sum([ant2_rh, ant2_lh])
    values = {
        "total": ant1_total_db - ant2_total_db,
        "rh": ant1_rh - ant2_rh,
        "lh": ant1_lh - ant2_lh,
        "mean_pol": 0.5 * ((ant1_rh - ant2_rh) + (ant1_lh - ant2_lh)),
    }
    return float(values[channel])


def legacy_dual_tag_h10b_predict_rssd_db(
    rssd_row: pd.Series,
    theta_elevation_deg: np.ndarray,
    range_m: np.ndarray,
) -> np.ndarray:
    artifact_path = str(_row_get(rssd_row, "legacy_dual_tag_artifact_path", "")).strip()
    if not artifact_path:
        return np.full_like(np.asarray(theta_elevation_deg, dtype=float), np.nan, dtype=float)
    alpha = float(_row_get(rssd_row, "legacy_dual_tag_alpha_deg", 60.0))
    rotation = float(_row_get(rssd_row, "legacy_dual_tag_rotation_deg", 0.0))
    channel = normalize_legacy_dual_tag_rssd_channel(str(_row_get(rssd_row, "legacy_dual_tag_rssd_channel", "total")))
    lut = load_legacy_dual_tag_h10b_lut_from_path(Path(artifact_path), alpha, rotation)
    theta_arr = np.asarray(theta_elevation_deg, dtype=float)
    range_arr = np.asarray(range_m, dtype=float)
    pred = np.full(theta_arr.shape, np.nan, dtype=float)
    for idx, (theta_value, range_value) in enumerate(zip(theta_arr, range_arr)):
        if not (np.isfinite(theta_value) and np.isfinite(range_value)):
            continue
        lut_row = _select_legacy_dual_tag_lut_row(lut, float(theta_value), float(range_value))
        pred[idx] = _legacy_dual_tag_selected_rssd_db(lut_row, channel, offset_db=0.0)
    return pred


def legacy_dual_tag_h10b_feature_terms(
    meas: object,
    path: pd.Series,
    theta_elevation_deg: float,
    config: Stage01Config,
    lut: pd.DataFrame,
) -> dict[str, object]:
    lut_row = _select_legacy_dual_tag_lut_row(
        lut,
        theta_elevation_deg,
        float(_row_get(path, "path_length_m", getattr(meas, "estimated_range_m", np.nan))),
    )
    channel_cols = ["RSS_ant1_RH_db", "RSS_ant1_LH_db", "RSS_ant2_RH_db", "RSS_ant2_LH_db"]
    raw = {col: float(lut_row[col]) for col in channel_cols}
    raw_mean = float(np.nanmean(list(raw.values())))
    power_offset_mode = normalize_legacy_dual_tag_power_offset_mode(config.legacy_dual_tag_power_offset_mode)
    offset_db = float(getattr(meas, "estimated_amp_db", raw_mean)) - raw_mean if power_offset_mode == "match_existing_amp" else 0.0
    adj = {col: value + offset_db for col, value in raw.items()}

    ant1_total_db = _db_sum([adj["RSS_ant1_RH_db"], adj["RSS_ant1_LH_db"]])
    ant2_total_db = _db_sum([adj["RSS_ant2_RH_db"], adj["RSS_ant2_LH_db"]])
    rssd_rh_db = adj["RSS_ant1_RH_db"] - adj["RSS_ant2_RH_db"]
    rssd_lh_db = adj["RSS_ant1_LH_db"] - adj["RSS_ant2_LH_db"]
    rssd_total_db = ant1_total_db - ant2_total_db
    rssd_mean_pol_db = 0.5 * (rssd_rh_db + rssd_lh_db)
    channel = normalize_legacy_dual_tag_rssd_channel(config.legacy_dual_tag_rssd_channel)
    selected = {
        "total": rssd_total_db,
        "rh": rssd_rh_db,
        "lh": rssd_lh_db,
        "mean_pol": rssd_mean_pol_db,
    }[channel]

    boresights = legacy_dual_tag_boresights(config.legacy_dual_tag_alpha_deg, config.legacy_dual_tag_rotation_deg)
    return {
        "tag_antenna_model_mode": "legacy_h10b_dual_tilted",
        "legacy_dual_tag_artifact_path": str(resolve_legacy_dual_tag_artifact_path(config)),
        "legacy_dual_tag_lut_case_id": _row_get(lut_row, "case_id", ""),
        "legacy_dual_tag_lut_source_case_id": _row_get(lut_row, "source_case_id", ""),
        "legacy_dual_tag_lut_theta_abs_deg": float(lut_row["legacy_h10b_theta_abs_deg"]),
        "legacy_dual_tag_lut_range_m": float(lut_row["legacy_h10b_range_m"]),
        "legacy_dual_tag_alpha_deg": float(config.legacy_dual_tag_alpha_deg),
        "legacy_dual_tag_rotation_deg": float(config.legacy_dual_tag_rotation_deg),
        "legacy_dual_tag_rssd_channel": channel,
        "legacy_dual_tag_rssd_prediction_mode": normalize_legacy_dual_tag_rssd_prediction_mode(
            config.legacy_dual_tag_rssd_prediction_mode,
            "legacy_h10b_dual_tilted",
        ),
        "legacy_dual_tag_power_offset_mode": power_offset_mode,
        "tag_ant1_boresight_x": boresights["tag_ant1"]["boresight_x"],
        "tag_ant1_boresight_y": boresights["tag_ant1"]["boresight_y"],
        "tag_ant1_boresight_z": boresights["tag_ant1"]["boresight_z"],
        "tag_ant2_boresight_x": boresights["tag_ant2"]["boresight_x"],
        "tag_ant2_boresight_y": boresights["tag_ant2"]["boresight_y"],
        "tag_ant2_boresight_z": boresights["tag_ant2"]["boresight_z"],
        "tag_ant1_signed_elevation_deg": boresights["tag_ant1"]["signed_elevation_deg"],
        "tag_ant2_signed_elevation_deg": boresights["tag_ant2"]["signed_elevation_deg"],
        "RSS_ant1_RH_db": adj["RSS_ant1_RH_db"],
        "RSS_ant1_LH_db": adj["RSS_ant1_LH_db"],
        "RSS_ant2_RH_db": adj["RSS_ant2_RH_db"],
        "RSS_ant2_LH_db": adj["RSS_ant2_LH_db"],
        "RSS_ant1_total_db": ant1_total_db,
        "RSS_ant2_total_db": ant2_total_db,
        "RSSD_RH_db": rssd_rh_db,
        "RSSD_LH_db": rssd_lh_db,
        "RSSD_total_db": rssd_total_db,
        "RSSD_mean_pol_db": rssd_mean_pol_db,
        "legacy_dual_tag_power_offset_db": offset_db,
        "legacy_dual_tag_match_theta_error_deg": abs(float(lut_row["legacy_h10b_theta_abs_deg"]) - abs(float(theta_elevation_deg))),
        "legacy_dual_tag_match_range_error_m": float(lut_row["legacy_h10b_range_m"]) - float(_row_get(path, "path_length_m", getattr(meas, "estimated_range_m", np.nan))),
        "legacy_dual_tag_range_est_mean_m": float(_row_get(lut_row, "range_est_mean_m", np.nan)),
        "legacy_dual_tag_range_reliable_label": str(_row_get(lut_row, "range_reliable_label", "")),
        "selected_rssd_db": selected,
    }


def tilted_real_pattern_feature_terms(
    meas: object,
    path: pd.Series,
    beta_body_deg: float,
    theta_elevation_deg: float,
    config: Stage01Config,
) -> dict[str, object]:
    gains = tilted_real_pattern_channel_gains_db(beta_body_deg, theta_elevation_deg, config)
    gain_scalar = {key: float(np.ravel(value)[0]) for key, value in gains.items()}
    base_power_db = float(getattr(meas, "estimated_amp_db", _row_get(path, "amplitude_db", 0.0)))
    raw = {key: base_power_db + gain for key, gain in gain_scalar.items()}
    raw_mean = float(np.nanmean(list(raw.values())))
    offset_db = base_power_db - raw_mean if np.isfinite(raw_mean) else 0.0
    adj = {key: value + offset_db for key, value in raw.items()}

    ant1_total_db = _db_sum([adj["RSS_ant1_RH_db"], adj["RSS_ant1_LH_db"]])
    ant2_total_db = _db_sum([adj["RSS_ant2_RH_db"], adj["RSS_ant2_LH_db"]])
    rssd_rh_db = adj["RSS_ant1_RH_db"] - adj["RSS_ant2_RH_db"]
    rssd_lh_db = adj["RSS_ant1_LH_db"] - adj["RSS_ant2_LH_db"]
    rssd_total_db = ant1_total_db - ant2_total_db
    rssd_mean_pol_db = 0.5 * (rssd_rh_db + rssd_lh_db)
    channel = normalize_legacy_dual_tag_rssd_channel(config.legacy_dual_tag_rssd_channel)
    selected = {
        "total": rssd_total_db,
        "rh": rssd_rh_db,
        "lh": rssd_lh_db,
        "mean_pol": rssd_mean_pol_db,
    }[channel]
    boresights = legacy_dual_tag_boresights(config.legacy_dual_tag_alpha_deg, config.legacy_dual_tag_rotation_deg)
    return {
        "tag_antenna_model_mode": "tilted_real_pattern",
        "legacy_dual_tag_artifact_path": "",
        "legacy_dual_tag_lut_case_id": "",
        "legacy_dual_tag_lut_source_case_id": "",
        "legacy_dual_tag_lut_theta_abs_deg": float("nan"),
        "legacy_dual_tag_lut_range_m": float("nan"),
        "legacy_dual_tag_alpha_deg": float(config.legacy_dual_tag_alpha_deg),
        "legacy_dual_tag_rotation_deg": float(config.legacy_dual_tag_rotation_deg),
        "legacy_dual_tag_rssd_channel": channel,
        "legacy_dual_tag_rssd_prediction_mode": "tilted_real_pattern",
        "legacy_dual_tag_power_offset_mode": "pattern_mean_matched_to_peak_amp",
        "tag_ant1_boresight_x": boresights["tag_ant1"]["boresight_x"],
        "tag_ant1_boresight_y": boresights["tag_ant1"]["boresight_y"],
        "tag_ant1_boresight_z": boresights["tag_ant1"]["boresight_z"],
        "tag_ant2_boresight_x": boresights["tag_ant2"]["boresight_x"],
        "tag_ant2_boresight_y": boresights["tag_ant2"]["boresight_y"],
        "tag_ant2_boresight_z": boresights["tag_ant2"]["boresight_z"],
        "tag_ant1_signed_elevation_deg": boresights["tag_ant1"]["signed_elevation_deg"],
        "tag_ant2_signed_elevation_deg": boresights["tag_ant2"]["signed_elevation_deg"],
        "RSS_ant1_RH_db": adj["RSS_ant1_RH_db"],
        "RSS_ant1_LH_db": adj["RSS_ant1_LH_db"],
        "RSS_ant2_RH_db": adj["RSS_ant2_RH_db"],
        "RSS_ant2_LH_db": adj["RSS_ant2_LH_db"],
        "RSS_ant1_total_db": ant1_total_db,
        "RSS_ant2_total_db": ant2_total_db,
        "RSSD_RH_db": rssd_rh_db,
        "RSSD_LH_db": rssd_lh_db,
        "RSSD_total_db": rssd_total_db,
        "RSSD_mean_pol_db": rssd_mean_pol_db,
        "legacy_dual_tag_power_offset_db": offset_db,
        "legacy_dual_tag_match_theta_error_deg": float("nan"),
        "legacy_dual_tag_match_range_error_m": float("nan"),
        "legacy_dual_tag_range_est_mean_m": float("nan"),
        "legacy_dual_tag_range_reliable_label": "",
        "tilted_real_pattern_power_offset_db": offset_db,
        "tilted_real_pattern_gain_ant1_rh_db": gain_scalar["RSS_ant1_RH_db"],
        "tilted_real_pattern_gain_ant1_lh_db": gain_scalar["RSS_ant1_LH_db"],
        "tilted_real_pattern_gain_ant2_rh_db": gain_scalar["RSS_ant2_RH_db"],
        "tilted_real_pattern_gain_ant2_lh_db": gain_scalar["RSS_ant2_LH_db"],
        **_tilted_real_pattern_metadata(config),
        "selected_rssd_db": selected,
    }


def linear_projection_linear(angle_deg: float) -> float:
    angle_rad = math.radians(wrap_deg(angle_deg))
    return float(np.clip(math.cos(angle_rad) ** 2, EPS, 1.0))


def linear_pol_mismatch_db(beta_body_deg: float, linear_pol_axis_deg: float, tilt_deg: float) -> float:
    projection = linear_projection_linear(float(beta_body_deg) - float(linear_pol_axis_deg) - float(tilt_deg))
    return float(db10(projection))


def cp_handedness_filter_weight(bounce_order: int) -> float:
    if int(bounce_order) <= 0:
        return 1.0
    return 1.0 if int(bounce_order) % 2 == 0 else 0.1


def lp_te_tm_power_fractions(path, config: Stage01Config) -> tuple[float, float]:
    if not config.use_te_tm_reflection or str(config.material_fresnel_model).lower() in {"none", "off", "disabled"}:
        return float("nan"), float("nan")
    if int(path.bounce_count) <= 0 or not path.materials or not path.incidence_angles_rad:
        return float("nan"), float("nan")
    te_power = 1.0
    tm_power = 1.0
    freqs = np.array([float(config.frequency_hz)], dtype=float)
    for material, theta_i in zip(path.materials, path.incidence_angles_rad):
        gamma_te, gamma_tm = fresnel_reflection(material, float(theta_i), freqs)
        te_power *= float(np.abs(gamma_te[0]) ** 2)
        tm_power *= float(np.abs(gamma_tm[0]) ** 2)
    total = te_power + tm_power
    if total <= EPS:
        return float("nan"), float("nan")
    return float(te_power / total), float(tm_power / total)


def polarization_path_terms(path, beta_body_deg: float, config: Stage01Config) -> dict[str, float | str]:
    mode = normalize_polarization_mode(config.polarization_mode)
    if not config.path_polarization_tracking:
        return {
            "polarization_mode": mode,
            "cp_handedness_filter_weight": 1.0,
            "pol_mismatch_ant1_db": 0.0,
            "pol_mismatch_ant2_db": 0.0,
            "lp_te_power_fraction": float("nan"),
            "lp_tm_power_fraction": float("nan"),
            "polarization_effective_power_linear": 1.0,
        }

    if mode == "CP":
        cp_weight = cp_handedness_filter_weight(int(path.bounce_count))
        return {
            "polarization_mode": mode,
            "cp_handedness_filter_weight": cp_weight,
            "pol_mismatch_ant1_db": 0.0,
            "pol_mismatch_ant2_db": 0.0,
            "lp_te_power_fraction": float("nan"),
            "lp_tm_power_fraction": float("nan"),
            "polarization_effective_power_linear": cp_weight,
        }

    ant1_mismatch_db = linear_pol_mismatch_db(
        beta_body_deg,
        config.tag_ant1_linear_pol_axis_deg,
        config.tag_pol_tilt_deg,
    )
    ant2_mismatch_db = linear_pol_mismatch_db(
        beta_body_deg,
        config.tag_ant2_linear_pol_axis_deg,
        config.tag_pol_tilt_deg,
    )
    ant1_projection = 10.0 ** (ant1_mismatch_db / 10.0)
    ant2_projection = 10.0 ** (ant2_mismatch_db / 10.0)
    te_fraction, tm_fraction = lp_te_tm_power_fractions(path, config)
    return {
        "polarization_mode": mode,
        "cp_handedness_filter_weight": 1.0,
        "pol_mismatch_ant1_db": ant1_mismatch_db,
        "pol_mismatch_ant2_db": ant2_mismatch_db,
        "lp_te_power_fraction": te_fraction,
        "lp_tm_power_fraction": tm_fraction,
        "polarization_effective_power_linear": 0.5 * (ant1_projection + ant2_projection),
    }


def material_reflection_loss_db(name: str) -> float:
    losses = {
        "metal_pec": 1.0,
        "pec": 1.0,
        "glass": 3.0,
        "wood": 5.0,
        "drywall": 6.0,
        "brick": 7.0,
        "concrete": 8.0,
        "ceramic_tile": 4.0,
    }
    return float(losses.get(str(name), 7.0))


def make_scene_specs(scene_ids: tuple[str, ...]) -> list[SceneSpec]:
    specs: dict[str, SceneSpec] = {}

    def add(
        scene_id: str,
        room_type: str,
        size: tuple[float, float, float],
        floorplan_type: str,
        has_blocker: bool = False,
        has_furniture: bool = False,
        has_metal_region: bool = False,
        has_glass_region: bool = False,
    ) -> None:
        L_m, W_m, H_m = [float(x) for x in size]
        specs[scene_id] = SceneSpec(
            scene_id=scene_id,
            room_type=room_type,
            L_m=L_m,
            W_m=W_m,
            H_m=H_m,
            floorplan_type=floorplan_type,
            has_blocker=has_blocker,
            has_furniture=has_furniture,
            has_metal_region=has_metal_region,
            has_glass_region=has_glass_region,
            scene=make_room_abc_scene(room_type, size),
        )

    add("R0", "A", (5.0, 4.0, 3.0), "simple_rectangle")
    add("R1A", "A", (5.0, 4.0, 3.0), "stage2_like_A")
    add("R1B", "B", (5.0, 4.0, 3.0), "stage2_like_B", has_furniture=True, has_glass_region=True)
    add("R1C", "C", (5.0, 4.0, 3.0), "stage2_like_C", has_furniture=True, has_metal_region=True, has_glass_region=True)
    add("R2", "A", (8.0, 2.0, 3.0), "corridor")
    add("R3", "C", (5.0, 4.0, 3.0), "l_shape_proxy", has_furniture=True, has_metal_region=True, has_glass_region=True)
    add("R4", "C", (5.0, 4.0, 3.0), "cluttered_blocker_proxy", has_blocker=True, has_furniture=True, has_metal_region=True, has_glass_region=True)
    add("R5", "C", (5.0, 4.0, 3.0), "metal_glass_rich", has_furniture=True, has_metal_region=True, has_glass_region=True)
    add("R6H", "HALL", (7.0, 6.0, 3.2), "heldout_open_hall_columns", has_blocker=True)

    missing = [sid for sid in scene_ids if sid not in specs]
    if missing:
        raise ValueError(f"unknown scene ids: {missing}")
    return [specs[sid] for sid in scene_ids]


def _axis_angle_rotate(vec: np.ndarray, axis: np.ndarray, angle_rad: float) -> np.ndarray:
    v = np.asarray(vec, dtype=float).reshape(3)
    a = np.asarray(axis, dtype=float).reshape(3)
    norm = float(np.linalg.norm(a))
    if norm <= 1e-12 or abs(float(angle_rad)) <= 1e-12:
        return v.copy()
    a = a / norm
    c = math.cos(float(angle_rad))
    s = math.sin(float(angle_rad))
    return v * c + np.cross(a, v) * s + a * float(np.dot(a, v)) * (1.0 - c)


def _is_wall_surface(surface: Surface) -> bool:
    return "wall" in str(surface.name).lower()


def surface_perturbation_active(config: Stage01Config) -> bool:
    return abs(float(config.wall_offset_noise_m)) > 0.0 or abs(float(config.wall_normal_noise_deg)) > 0.0


def perturb_scene_specs_for_solver(scene_specs: list[SceneSpec], config: Stage01Config) -> tuple[list[SceneSpec], pd.DataFrame]:
    """Create deterministic solver-side wall perturbations for W2 robustness."""

    columns = [
        "scene_id",
        "surface_id",
        "surface_name",
        "offset_delta_m",
        "normal_delta_deg",
        "perturbed",
        "perturbation_config_id",
    ]
    rows: list[dict[str, object]] = []
    if not surface_perturbation_active(config):
        return scene_specs, pd.DataFrame(columns=columns)

    out_specs: list[SceneSpec] = []
    for spec in scene_specs:
        perturbed_surfaces: list[Surface] = []
        for surface in spec.scene.surfaces:
            offset_delta = 0.0
            normal_delta = 0.0
            normal = surface.normal
            point = surface.point
            if _is_wall_surface(surface):
                offset_sign = 1.0 if stable_unit_interval(config.random_seed, config.perturbation_config_id, spec.scene_id, surface.surface_id, "offset") >= 0.5 else -1.0
                angle_sign = 1.0 if stable_unit_interval(config.random_seed, config.perturbation_config_id, spec.scene_id, surface.surface_id, "normal_sign") >= 0.5 else -1.0
                angle_fraction = 0.5 + 0.5 * stable_unit_interval(config.random_seed, config.perturbation_config_id, spec.scene_id, surface.surface_id, "normal_mag")
                offset_delta = offset_sign * float(config.wall_offset_noise_m)
                normal_delta = angle_sign * angle_fraction * float(config.wall_normal_noise_deg)
                point = surface.point + offset_delta * surface.normal
                axis = surface.u_axis if stable_unit_interval(config.random_seed, spec.scene_id, surface.surface_id, "axis") >= 0.5 else surface.v_axis
                normal = _axis_angle_rotate(surface.normal, axis, math.radians(normal_delta))
            perturbed_surfaces.append(
                Surface(
                    surface_id=surface.surface_id,
                    name=surface.name,
                    point=point,
                    normal=normal,
                    u_axis=surface.u_axis,
                    v_axis=surface.v_axis,
                    half_u=surface.half_u,
                    half_v=surface.half_v,
                    material=surface.material,
                )
            )
            rows.append(
                {
                    "scene_id": spec.scene_id,
                    "surface_id": int(surface.surface_id),
                    "surface_name": surface.name,
                    "offset_delta_m": float(offset_delta),
                    "normal_delta_deg": float(normal_delta),
                    "perturbed": bool(_is_wall_surface(surface)),
                    "perturbation_config_id": config.perturbation_config_id,
                }
            )
        out_specs.append(
            SceneSpec(
                scene_id=spec.scene_id,
                room_type=spec.room_type,
                L_m=spec.L_m,
                W_m=spec.W_m,
                H_m=spec.H_m,
                floorplan_type=spec.floorplan_type,
                has_blocker=spec.has_blocker,
                has_furniture=spec.has_furniture,
                has_metal_region=spec.has_metal_region,
                has_glass_region=spec.has_glass_region,
                scene=Scene(tuple(perturbed_surfaces)),
            )
        )
    return out_specs, pd.DataFrame(rows, columns=columns)


def surface_corners(surface: Surface) -> np.ndarray:
    corners = []
    for su in (-1.0, 1.0):
        for sv in (-1.0, 1.0):
            corners.append(surface.point + su * surface.half_u * surface.u_axis + sv * surface.half_v * surface.v_axis)
    return np.asarray(corners, dtype=float)


def reflect_point(point: np.ndarray, surface: Surface) -> np.ndarray:
    p = np.asarray(point, dtype=float).reshape(3)
    return p - 2.0 * float(np.dot(p - surface.point, surface.normal)) * surface.normal


def build_scene_table(scene_specs: list[SceneSpec]) -> pd.DataFrame:
    rows = []
    for spec in scene_specs:
        rows.append(
            {
                "scene_id": spec.scene_id,
                "room_type": spec.room_type,
                "L_m": spec.L_m,
                "W_m": spec.W_m,
                "H_m": spec.H_m,
                "floorplan_type": spec.floorplan_type,
                "has_blocker": spec.has_blocker,
                "has_furniture": spec.has_furniture,
                "has_metal_region": spec.has_metal_region,
                "has_glass_region": spec.has_glass_region,
                "num_walls": len([s for s in spec.scene.surfaces if "wall" in s.name]),
                "num_surfaces": len(spec.scene.surfaces),
                "coordinate_frame_definition": "x east, y north, z up, origin at southwest floor corner",
            }
        )
    return pd.DataFrame(rows)


def build_surface_table(scene_specs: list[SceneSpec]) -> pd.DataFrame:
    rows = []
    for spec in scene_specs:
        for surface in spec.scene.surfaces:
            corners = surface_corners(surface)
            lo = corners.min(axis=0)
            hi = corners.max(axis=0)
            if "floor" in surface.name:
                surface_type = "floor"
            elif "ceiling" in surface.name:
                surface_type = "ceiling"
            elif "desk" in surface.name or "cabinet" in surface.name or "partition" in surface.name:
                surface_type = "furniture"
            elif "window" in surface.name:
                surface_type = "wall"
            else:
                surface_type = "wall"
            rows.append(
                {
                    "scene_id": spec.scene_id,
                    "surface_id": surface.surface_id,
                    "surface_type": surface_type,
                    "material": surface.material.name,
                    "x1_m": lo[0],
                    "y1_m": lo[1],
                    "z1_m": lo[2],
                    "x2_m": hi[0],
                    "y2_m": hi[1],
                    "z2_m": hi[2],
                    "normal_x": surface.normal[0],
                    "normal_y": surface.normal[1],
                    "normal_z": surface.normal[2],
                    "thickness_m": 0.0,
                    "eps_r": surface.material.eps_r,
                    "tan_delta": surface.material.tan_delta,
                    "conductivity_s_per_m": surface.material.conductivity_s_m,
                    "roughness_m": 0.0,
                    "reflection_model": "image_method_specular_stage01",
                    "is_specular_enabled": True,
                    "is_diffuse_enabled": surface_type in {"furniture", "wall"},
                }
            )
    return pd.DataFrame(rows)


def anchor_position(spec: SceneSpec) -> np.ndarray:
    return np.array([spec.L_m / 2.0, spec.W_m / 2.0, spec.H_m - 0.3], dtype=float)


def build_anchor_table(scene_specs: list[SceneSpec], config: Stage01Config | None = None) -> pd.DataFrame:
    mode = normalize_polarization_mode(config.polarization_mode) if config is not None else "CP"
    rows = []
    for spec in scene_specs:
        pos = anchor_position(spec)
        rows.append(
            {
                "scene_id": spec.scene_id,
                "anchor_id": "A0",
                "anchor_type": "PA",
                "x_m": pos[0],
                "y_m": pos[1],
                "z_m": pos[2],
                "yaw_deg": 0.0,
                "pitch_deg": -90.0,
                "roll_deg": 0.0,
                "boresight_x": 0.0,
                "boresight_y": 0.0,
                "boresight_z": -1.0,
                "polarization_mode": mode,
                "polarization_tx": "dual_cp" if mode == "CP" else "linear",
                "antenna_model_id": "ideal_dual_cp_stage01" if mode == "CP" else "lp_ffd_stage01",
                "anchor_linear_pol_axis_deg": float(config.anchor_linear_pol_axis_deg) if config is not None else 0.0,
                "anchor_pol_tilt_deg": float(config.anchor_pol_tilt_deg) if config is not None else 0.0,
                "lp_copol_gain_pattern_file": str(config.lp_copol_gain_pattern_file) if config is not None else "",
                "lp_crosspol_gain_pattern_file": str(config.lp_crosspol_gain_pattern_file) if config is not None else "",
                "tx_power_dbm": 0.0,
                "clock_bias_s": 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_va_catalog_truth(scene_specs: list[SceneSpec], max_order: int = 2) -> pd.DataFrame:
    rows = []
    for spec in scene_specs:
        anchor = anchor_position(spec)
        rows.append(
            {
                "scene_id": spec.scene_id,
                "feature_id": "PA_A0",
                "feature_type": "PA",
                "parent_anchor_id": "A0",
                "va_order": 0,
                "reflection_sequence": "",
                "last_bounce_wall_id": "",
                "x_m": anchor[0],
                "y_m": anchor[1],
                "z_m": anchor[2],
                "is_first_order": False,
                "is_second_order": False,
                "expected_parity": "none",
                "is_inside_physical_room": True,
                "validity_flag": True,
            }
        )
        for surface in spec.scene.surfaces:
            va = reflect_point(anchor, surface)
            rows.append(
                {
                    "scene_id": spec.scene_id,
                    "feature_id": f"VA_{surface.surface_id}",
                    "feature_type": "VA",
                    "parent_anchor_id": "A0",
                    "va_order": 1,
                    "reflection_sequence": str(surface.surface_id),
                    "last_bounce_wall_id": surface.surface_id,
                    "x_m": va[0],
                    "y_m": va[1],
                    "z_m": va[2],
                    "is_first_order": True,
                    "is_second_order": False,
                    "expected_parity": "odd",
                    "is_inside_physical_room": bool(0.0 <= va[0] <= spec.L_m and 0.0 <= va[1] <= spec.W_m and 0.0 <= va[2] <= spec.H_m),
                    "validity_flag": True,
                }
            )
        if max_order >= 2:
            surfaces = spec.scene.surfaces
            for first in surfaces:
                for second in surfaces:
                    if first.surface_id == second.surface_id:
                        continue
                    va = reflect_point(reflect_point(anchor, first), second)
                    rows.append(
                        {
                            "scene_id": spec.scene_id,
                            "feature_id": f"VA_{first.surface_id}>{second.surface_id}",
                            "feature_type": "VA",
                            "parent_anchor_id": "A0",
                            "va_order": 2,
                            "reflection_sequence": f"{first.surface_id}>{second.surface_id}",
                            "last_bounce_wall_id": second.surface_id,
                            "x_m": va[0],
                            "y_m": va[1],
                            "z_m": va[2],
                            "is_first_order": False,
                            "is_second_order": True,
                            "expected_parity": "even",
                            "is_inside_physical_room": bool(0.0 <= va[0] <= spec.L_m and 0.0 <= va[1] <= spec.W_m and 0.0 <= va[2] <= spec.H_m),
                            "validity_flag": True,
                        }
                    )
    return pd.DataFrame(rows)


def trajectory_points(spec: SceneSpec, trajectory_id: str, num_snapshots: int) -> tuple[np.ndarray, np.ndarray, list[str]]:
    n = int(num_snapshots)
    if n <= 0:
        raise ValueError("num_snapshots must be positive")
    t = np.linspace(0.0, 1.0, n)
    z = np.full(n, 0.8)
    margin = 0.45
    L = spec.L_m
    W = spec.W_m
    tid = trajectory_id.upper()

    if tid == "T0":
        x = np.linspace(margin, L - margin, n)
        y = np.full(n, W / 2.0)
        policy = ["straight_line"] * n
    elif tid == "T1":
        corners = np.array(
            [
                [margin, margin],
                [L - margin, margin],
                [L - margin, W - margin],
                [margin, W - margin],
                [margin, margin],
            ],
            dtype=float,
        )
        seg = np.minimum((t * 4.0).astype(int), 3)
        local = t * 4.0 - seg
        xy = (1.0 - local)[:, None] * corners[seg] + local[:, None] * corners[seg + 1]
        x, y = xy[:, 0], xy[:, 1]
        policy = ["rectangle_loop"] * n
    elif tid == "T2":
        x = np.linspace(margin, L - margin, n)
        y = np.full(n, min(W - margin, max(margin, 0.35)))
        policy = ["wall_following"] * n
    elif tid == "T3":
        x = np.linspace(margin, L - margin, n)
        y = np.linspace(margin, W - margin, n)
        policy = ["diagonal_crossing"] * n
    elif tid == "T4":
        x = np.linspace(margin, L - margin, n)
        y = W / 2.0 + 0.35 * np.sin(2.0 * np.pi * t)
        policy = ["blocker_crossing"] * n
    elif tid == "T5":
        x = np.full(n, L / 2.0)
        y = np.full(n, W / 2.0)
        policy = ["rotation_in_place"] * n
    elif tid == "T6":
        x = np.interp(t, [0.0, 0.25, 0.5, 0.75, 1.0], [margin, L * 0.35, L * 0.35, L * 0.7, L - margin])
        y = np.full(n, W * 0.35)
        policy = ["stop_and_go"] * n
    elif tid == "T7":
        x = L / 2.0 + 0.35 * L * np.sin(2.0 * np.pi * t)
        y = W / 2.0 + 0.35 * W * np.sin(2.0 * np.pi * t + 0.7)
        policy = ["random_amr_path_deterministic_proxy"] * n
    else:
        raise ValueError(f"unknown trajectory id: {trajectory_id}")

    pts = np.column_stack([x, y, z])
    dxy = np.gradient(pts[:, :2], axis=0)
    yaw = np.degrees(np.arctan2(dxy[:, 1], dxy[:, 0]))
    if tid == "T5":
        yaw = np.linspace(-180.0, 180.0, n)
    return pts, yaw.astype(float), policy


def parse_scenario_pairs(scenario_pairs: tuple[str, ...]) -> set[tuple[str, str]]:
    parsed: set[tuple[str, str]] = set()
    for item in scenario_pairs:
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"scenario pair must be SCENE:TRAJECTORY, got {item!r}")
        scene_id, trajectory_id = item.split(":", 1)
        parsed.add((scene_id.strip(), trajectory_id.strip().upper()))
    return parsed


def build_trajectory_truth(
    scene_specs: list[SceneSpec],
    trajectory_ids: tuple[str, ...],
    num_snapshots: int,
    dt_s: float,
    scenario_pairs: tuple[str, ...] = (),
) -> pd.DataFrame:
    rows = []
    pair_filter = parse_scenario_pairs(scenario_pairs)
    for spec in scene_specs:
        for trajectory_id in trajectory_ids:
            trajectory_id = trajectory_id.upper()
            if pair_filter and (spec.scene_id, trajectory_id) not in pair_filter:
                continue
            sequence_id = f"{spec.scene_id}_A0_{trajectory_id}"
            pts, yaw, policy = trajectory_points(spec, trajectory_id, num_snapshots)
            vel = np.gradient(pts, float(dt_s), axis=0)
            omega = np.gradient(np.unwrap(np.deg2rad(yaw)), float(dt_s))
            for idx in range(num_snapshots):
                rows.append(
                    {
                        "sequence_id": sequence_id,
                        "scene_id": spec.scene_id,
                        "time_idx": idx,
                        "time_s": idx * float(dt_s),
                        "agent_x_m": pts[idx, 0],
                        "agent_y_m": pts[idx, 1],
                        "agent_z_m": pts[idx, 2],
                        "yaw_deg": yaw[idx],
                        "pitch_deg": 0.0,
                        "roll_deg": 0.0,
                        "v_x_mps": vel[idx, 0],
                        "v_y_mps": vel[idx, 1],
                        "v_mps": float(np.linalg.norm(vel[idx, :2])),
                        "omega_z_radps": omega[idx],
                        "motion_policy": policy[idx],
                        "is_stop": bool(policy[idx] in {"stop_and_go", "rotation_in_place"} and idx % max(1, num_snapshots // 8) == 0),
                        "is_turn": bool(abs(omega[idx]) > 0.05),
                        "is_wall_following": bool(trajectory_id.upper() == "T2"),
                        "is_blocked_los_region": bool(trajectory_id.upper() == "T4" and abs(pts[idx, 0] - spec.L_m / 2.0) < 0.35 * spec.L_m),
                    }
                )
    return pd.DataFrame(rows)


def feature_id_for_path(path) -> str:
    if path.bounce_count == 0:
        return "PA_A0"
    return "VA_" + ">".join(str(sid) for sid in path.surface_ids)


def path_type_for_bounce(bounce_count: int) -> str:
    if bounce_count == 0:
        return "LoS"
    if bounce_count == 1:
        return "single_bounce"
    return "multi_bounce"


def path_amplitude_db(path, los_blocked: bool) -> tuple[float, float]:
    path_loss_db = 20.0 * math.log10(max(float(path.path_length_m), 0.1))
    reflection_loss = sum(material_reflection_loss_db(mat.name) for mat in path.materials)
    if path.bounce_count >= 2:
        reflection_loss += 1.5 * (path.bounce_count - 1)
    if path.bounce_count == 0 and los_blocked:
        reflection_loss += 12.0
    amp_db = -path_loss_db - reflection_loss
    return float(amp_db), float(reflection_loss)


def build_path_truth_table(
    scene_specs: list[SceneSpec],
    trajectory_truth: pd.DataFrame,
    config: Stage01Config,
) -> pd.DataFrame:
    specs_by_id = {s.scene_id: s for s in scene_specs}
    rows = []
    for row in trajectory_truth.itertuples(index=False):
        spec = specs_by_id[row.scene_id]
        tx = anchor_position(spec)
        rx = np.array([row.agent_x_m, row.agent_y_m, row.agent_z_m], dtype=float)
        paths = enumerate_paths(spec.scene, tx, rx, config.max_reflections)
        path_rows = []
        for path in paths:
            amp_db, reflection_loss_db = path_amplitude_db(path, bool(row.is_blocked_los_region))
            path_rows.append((amp_db, path))
        path_rows.sort(key=lambda item: item[0], reverse=True)
        selected = sorted(path_rows[: config.num_paths_max], key=lambda item: item[1].delay_s)
        los_delay = next((path.delay_s for _, path in selected if path.bounce_count == 0), float("nan"))

        for local_idx, (amp_db, path) in enumerate(selected, start=1):
            path_truth_id = f"{row.sequence_id}_t{int(row.time_idx):04d}_p{local_idx:03d}"
            path_type = path_type_for_bounce(path.bounce_count)
            launch_az, launch_el = az_el_deg(path.launch_dir)
            arrival_az, arrival_el = az_el_deg(path.arrival_dir)
            beta_body = wrap_deg(arrival_az - float(row.yaw_deg))
            material_sequence = ">".join(mat.name for mat in path.materials)
            reflection_sequence = ">".join(str(sid) for sid in path.surface_ids)
            incidence_deg = "|".join(f"{math.degrees(a):.6g}" for a in path.incidence_angles_rad)
            _, reflection_loss_db = path_amplitude_db(path, bool(row.is_blocked_los_region))
            phase_rad = float((2.0 * math.pi * config.frequency_hz * path.delay_s + math.pi) % (2.0 * math.pi) - math.pi)
            pol_terms = polarization_path_terms(path, beta_body, config)
            rows.append(
                {
                    "sequence_id": row.sequence_id,
                    "time_idx": int(row.time_idx),
                    "path_truth_id": path_truth_id,
                    "feature_id": feature_id_for_path(path),
                    "path_type": path_type,
                    "bounce_order": path.bounce_count,
                    "reflection_sequence": reflection_sequence,
                    "surface_material_sequence": material_sequence,
                    "path_length_m": path.path_length_m,
                    "delay_s": path.delay_s,
                    "relative_delay_to_los_s": path.delay_s - los_delay if math.isfinite(los_delay) else float("nan"),
                    "amplitude_linear": 10.0 ** (amp_db / 20.0),
                    "amplitude_db": amp_db,
                    "phase_rad": phase_rad,
                    "doppler_hz": 0.0,
                    "tx_departure_az_deg": launch_az,
                    "tx_departure_el_deg": launch_el,
                    "rx_arrival_az_global_deg": arrival_az,
                    "rx_arrival_el_global_deg": arrival_el,
                    "rx_arrival_beta_body_deg": beta_body,
                    "theta_elevation_deg": arrival_el,
                    "incidence_angle_each_bounce_deg": incidence_deg,
                    "reflection_loss_db": reflection_loss_db,
                    "diffuse_power_fraction": 0.0,
                    "is_specular": True,
                    "is_geometrically_valid": bool(path.valid and not path.blocked),
                    **pol_terms,
                }
            )
    out = append_stress_regime_paths(pd.DataFrame(rows), trajectory_truth, config)
    return append_polarization_group_columns(out)


def _stress_path_copy(
    base: pd.Series,
    path_truth_id: str,
    path_type: str,
    bounce_order: int,
    feature_id: str,
    delay_s: float,
    amplitude_db: float,
    config: Stage01Config,
    reflection_sequence: str | None = None,
    material_sequence: str | None = None,
    is_specular: bool = True,
    diffuse_power_fraction: float = 0.0,
) -> dict[str, object]:
    row = base.to_dict()
    row["path_truth_id"] = path_truth_id
    row["feature_id"] = feature_id
    row["path_type"] = path_type
    row["bounce_order"] = int(bounce_order)
    if reflection_sequence is not None:
        row["reflection_sequence"] = reflection_sequence
    if material_sequence is not None:
        row["surface_material_sequence"] = material_sequence
    row["delay_s"] = float(delay_s)
    row["path_length_m"] = float(delay_s) * C0
    row["amplitude_db"] = float(amplitude_db)
    row["amplitude_linear"] = 10.0 ** (float(amplitude_db) / 20.0)
    row["phase_rad"] = float((2.0 * math.pi * config.frequency_hz * float(delay_s) + math.pi) % (2.0 * math.pi) - math.pi)
    row["reflection_loss_db"] = max(0.0, float(row.get("reflection_loss_db", 0.0)))
    row["diffuse_power_fraction"] = float(diffuse_power_fraction)
    row["is_specular"] = bool(is_specular)
    row["is_geometrically_valid"] = bool(is_specular)
    return row


def append_stress_regime_paths(path_truth: pd.DataFrame, trajectory_truth: pd.DataFrame, config: Stage01Config) -> pd.DataFrame:
    """Oversample CP-sensitive and negative-control regimes without hiding truth.

    The base image-method tracer gives physically plausible PA/VA geometry. This
    stress layer adds explicitly labeled near-resolution copies and clutter truth
    rows so every Stage 0-7 gate has enough samples for slicing: LoS/SB overlap,
    weak-LoS strong-reflection, SB/SB ambiguity, threshold-near paths, sequential
    mismatch trajectories, and clutter-dominant false alarm controls.
    """

    if path_truth.empty:
        return path_truth

    traj_lookup = trajectory_truth.set_index(["sequence_id", "time_idx"])
    tres = config.time_resolution_s
    additions: list[dict[str, object]] = []

    for (sequence_id, time_idx), group in path_truth.groupby(["sequence_id", "time_idx"], sort=True):
        if (sequence_id, time_idx) not in traj_lookup.index:
            continue
        traj = traj_lookup.loc[(sequence_id, time_idx)]
        scene_id = str(traj.scene_id)
        trajectory_id = str(sequence_id).rsplit("_", 1)[-1]
        los_rows = group[group["path_type"].eq("LoS")].sort_values("delay_s")
        sb_rows = group[group["path_type"].eq("single_bounce")].sort_values("delay_s")
        mb_rows = group[group["path_type"].eq("multi_bounce")].sort_values("delay_s")
        if los_rows.empty:
            continue
        los = los_rows.iloc[0]

        if not sb_rows.empty and trajectory_id == "T3" and int(time_idx) % 3 == 0:
            sb = sb_rows.iloc[0]
            additions.append(
                _stress_path_copy(
                    sb,
                    f"{sequence_id}_t{int(time_idx):04d}_stress_g2",
                    "single_bounce",
                    1,
                    str(sb["feature_id"]),
                    float(los["delay_s"]) + 0.30 * tres,
                    max(float(sb["amplitude_db"]), float(los["amplitude_db"]) - 1.5),
                    config,
                )
            )

        if not sb_rows.empty and trajectory_id == "T4" and (bool(traj.is_blocked_los_region) or int(time_idx) % 4 == 0):
            sb = sb_rows.iloc[0]
            additions.append(
                _stress_path_copy(
                    sb,
                    f"{sequence_id}_t{int(time_idx):04d}_stress_g3",
                    "single_bounce",
                    1,
                    str(sb["feature_id"]),
                    float(los["delay_s"]) + 0.22 * tres,
                    float(los["amplitude_db"]) + 7.0,
                    config,
                )
            )

        if len(sb_rows) >= 2 and int(time_idx) % 4 == 1:
            sb0 = sb_rows.iloc[0]
            sb1 = sb_rows.iloc[1]
            additions.append(
                _stress_path_copy(
                    sb1,
                    f"{sequence_id}_t{int(time_idx):04d}_stress_g4",
                    "single_bounce",
                    1,
                    str(sb1["feature_id"]),
                    float(sb0["delay_s"]) + 0.25 * tres,
                    float(sb0["amplitude_db"]) - 0.4,
                    config,
                )
            )

        if not sb_rows.empty and int(time_idx) % 5 == 2:
            sb = sb_rows.iloc[min(1, len(sb_rows) - 1)]
            additions.append(
                _stress_path_copy(
                    sb,
                    f"{sequence_id}_t{int(time_idx):04d}_stress_g5",
                    "single_bounce",
                    1,
                    str(sb["feature_id"]),
                    float(sb["delay_s"]) + 1.6 * tres,
                    float(config.threshold_db + (1.0 if int(time_idx) % 2 == 0 else -1.0)),
                    config,
                )
            )

        if not mb_rows.empty and int(time_idx) % 6 == 3:
            mb = mb_rows.iloc[0]
            additions.append(
                _stress_path_copy(
                    mb,
                    f"{sequence_id}_t{int(time_idx):04d}_stress_g7",
                    "multi_bounce",
                    int(mb["bounce_order"]),
                    str(mb["feature_id"]),
                    float(mb["delay_s"]) + 0.35 * tres,
                    float(mb["amplitude_db"]) + 1.5,
                    config,
                )
            )

        if (scene_id in {"R4", "R5"} or trajectory_id == "T7") and int(time_idx) % 6 == 0:
            base = sb_rows.iloc[0] if not sb_rows.empty else los
            clutter_delay = float(los["delay_s"]) + (4.0 + (int(time_idx) % 3)) * tres
            additions.append(
                _stress_path_copy(
                    base,
                    f"{sequence_id}_t{int(time_idx):04d}_stress_g10",
                    "clutter_truth",
                    -1,
                    "CLUTTER",
                    clutter_delay,
                    float(max(group["amplitude_db"].max() + 3.0, config.threshold_db + 12.0)),
                    config,
                    reflection_sequence="",
                    material_sequence="diffuse_clutter",
                    is_specular=False,
                    diffuse_power_fraction=1.0,
                )
            )

    if not additions:
        return path_truth

    out = pd.concat([path_truth, pd.DataFrame(additions)], ignore_index=True, sort=False)
    los_delay = (
        out[out["path_type"].eq("LoS")]
        .groupby(["sequence_id", "time_idx"], sort=False)["delay_s"]
        .min()
        .rename("_los_delay")
    )
    out = out.merge(los_delay, on=["sequence_id", "time_idx"], how="left")
    out["relative_delay_to_los_s"] = out["delay_s"] - out["_los_delay"]
    out = out.drop(columns=["_los_delay"])
    return out.sort_values(["sequence_id", "time_idx", "delay_s", "path_truth_id"]).reset_index(drop=True)


def append_polarization_group_columns(path_truth: pd.DataFrame) -> pd.DataFrame:
    if path_truth.empty:
        return path_truth

    out = path_truth.copy()
    if "polarization_effective_power_linear" not in out.columns:
        out["polarization_effective_power_linear"] = 1.0
    out["polarization_effective_path_power_linear"] = (
        np.square(out["amplitude_linear"].to_numpy(float))
        * out["polarization_effective_power_linear"].fillna(1.0).to_numpy(float)
    )

    for col in [
        "direct_power_ratio",
        "reflected_power_ratio",
        "odd_bounce_power_ratio",
        "even_bounce_power_ratio",
        "dominant_path_bounce_count",
        "dominant_path_beta_deg",
        "direct_vs_dominant_beta_error_deg",
        "rssd_lut_residual_db",
    ]:
        out[col] = float("nan")

    for _, idx in out.groupby(["sequence_id", "time_idx"], sort=False).groups.items():
        part = out.loc[idx]
        bounce = part["bounce_order"].to_numpy(int)
        power = part["polarization_effective_path_power_linear"].to_numpy(float)
        total_power = float(np.sum(power))
        if total_power <= EPS:
            continue

        direct_mask = bounce == 0
        reflected_mask = bounce > 0
        odd_mask = (bounce > 0) & (bounce % 2 == 1)
        even_mask = (bounce > 0) & (bounce % 2 == 0)
        dominant_idx = part.index[int(np.argmax(power))]
        dominant_beta = float(out.at[dominant_idx, "rx_arrival_beta_body_deg"])
        direct_beta = float("nan")
        if np.any(direct_mask):
            first_direct_idx = part.index[np.where(direct_mask)[0][0]]
            direct_beta = float(out.at[first_direct_idx, "rx_arrival_beta_body_deg"])

        out.loc[idx, "direct_power_ratio"] = float(np.sum(power[direct_mask]) / total_power)
        out.loc[idx, "reflected_power_ratio"] = float(np.sum(power[reflected_mask]) / total_power)
        out.loc[idx, "odd_bounce_power_ratio"] = float(np.sum(power[odd_mask]) / total_power)
        out.loc[idx, "even_bounce_power_ratio"] = float(np.sum(power[even_mask]) / total_power)
        out.loc[idx, "dominant_path_bounce_count"] = int(out.at[dominant_idx, "bounce_order"])
        out.loc[idx, "dominant_path_beta_deg"] = dominant_beta
        out.loc[idx, "direct_vs_dominant_beta_error_deg"] = (
            abs(wrap_deg(dominant_beta - direct_beta)) if math.isfinite(direct_beta) else float("nan")
        )
        out.loc[idx, "rssd_lut_residual_db"] = float("nan")

    return out


def weighted_mode(values: pd.Series, weights: pd.Series) -> tuple[object, float]:
    grouped: dict[object, float] = {}
    for value, weight in zip(values.tolist(), weights.tolist()):
        grouped[value] = grouped.get(value, 0.0) + float(weight)
    if not grouped:
        return "", 0.0
    value, total = max(grouped.items(), key=lambda item: item[1])
    return value, float(total)


def last_wall_id(reflection_sequence: str) -> str:
    if not isinstance(reflection_sequence, str) or not reflection_sequence:
        return ""
    return reflection_sequence.split(">")[-1]


def first_material(material_sequence: str) -> str:
    if not isinstance(material_sequence, str) or not material_sequence:
        return ""
    return material_sequence.split(">")[-1]


def build_overlap_group_table(path_truth: pd.DataFrame, config: Stage01Config) -> pd.DataFrame:
    rows = []
    group_counter = 0
    tres = config.time_resolution_s
    for (sequence_id, time_idx), group in path_truth.groupby(["sequence_id", "time_idx"], sort=True):
        g = group.sort_values("delay_s").reset_index(drop=True)
        current_indices: list[int] = []
        previous_delay = None
        local_groups: list[list[int]] = []
        for idx, delay in enumerate(g["delay_s"].to_numpy(float)):
            if previous_delay is None or delay - previous_delay < tres:
                current_indices.append(idx)
            else:
                local_groups.append(current_indices)
                current_indices = [idx]
            previous_delay = delay
        if current_indices:
            local_groups.append(current_indices)

        for local_id, indices in enumerate(local_groups, start=1):
            part = g.iloc[indices].copy()
            power = np.square(part["amplitude_linear"].to_numpy(float))
            total_power = float(np.sum(power))
            weights = power / max(total_power, EPS)
            dominant_pos = int(np.argmax(power))
            dominant = part.iloc[dominant_pos]
            dominant_power_fraction = float(power[dominant_pos] / max(total_power, EPS))
            dominant_reflection_sequence = str(dominant.get("reflection_sequence", ""))
            dominant_bounce_order = int(dominant.get("bounce_order", 0))
            dominant_beta_body_deg = float(dominant.get("rx_arrival_beta_body_deg", float("nan")))
            wall_values = part["reflection_sequence"].map(last_wall_id)
            mat_values = part["surface_material_sequence"].map(first_material)
            dominant_wall_id, wall_power = weighted_mode(wall_values, pd.Series(power))
            dominant_material, material_power = weighted_mode(mat_values, pd.Series(power))
            delay_center = float(np.sum(part["delay_s"].to_numpy(float) * weights))
            path_types = set(part["path_type"].astype(str))
            num_single_bounce = int(np.sum(part["path_type"].eq("single_bounce")))
            group_counter += 1
            rows.append(
                {
                    "sequence_id": sequence_id,
                    "time_idx": int(time_idx),
                    "overlap_group_id": f"{sequence_id}_t{int(time_idx):04d}_g{local_id:03d}",
                    "delay_bin_id": int(math.floor(delay_center / tres)),
                    "delay_center_s": delay_center,
                    "num_truth_paths": int(len(part)),
                    "num_detected_peaks": int(db10(total_power) >= config.threshold_db),
                    "contains_los": "LoS" in path_types,
                    "contains_single_bounce": "single_bounce" in path_types,
                    "contains_multi_bounce": "multi_bounce" in path_types,
                    "contains_diffuse": "diffuse" in path_types or "clutter_truth" in path_types,
                    "dominant_path_id": dominant["path_truth_id"],
                    "dominant_path_type": dominant["path_type"],
                    "dominant_reflection_sequence": dominant_reflection_sequence,
                    "dominant_bounce_order": dominant_bounce_order,
                    "dominant_beta_body_deg": dominant_beta_body_deg,
                    "dominant_wall_id": dominant_wall_id,
                    "dominant_material": dominant_material,
                    "power_total_db": db10(total_power),
                    "power_los_fraction": float(np.sum(power[part["path_type"].eq("LoS").to_numpy()]) / max(total_power, EPS)),
                    "power_single_bounce_fraction": float(np.sum(power[part["path_type"].eq("single_bounce").to_numpy()]) / max(total_power, EPS)),
                    "power_multi_bounce_fraction": float(np.sum(power[part["path_type"].eq("multi_bounce").to_numpy()]) / max(total_power, EPS)),
                    "peak_purity": dominant_power_fraction,
                    "wall_purity": float(wall_power / max(total_power, EPS)),
                    "material_purity": float(material_power / max(total_power, EPS)),
                    "is_unresolved_los_sb": bool("LoS" in path_types and "single_bounce" in path_types and len(part) > 1),
                    "is_unresolved_sb_sb": bool(num_single_bounce >= 2 and len(part) > 1),
                    "is_mixture": bool(len(part) > 1 and dominant_power_fraction < 0.85),
                }
            )
    return pd.DataFrame(rows)


def build_peak_table(overlap_groups: pd.DataFrame, path_truth: pd.DataFrame, config: Stage01Config) -> pd.DataFrame:
    path_lookup = path_truth.set_index("path_truth_id")
    rows = []
    for (sequence_id, time_idx), group in overlap_groups.groupby(["sequence_id", "time_idx"], sort=True):
        sorted_group = group.sort_values("delay_center_s")
        first_detected_group_id = None
        for row in sorted_group.itertuples(index=False):
            if bool(row.num_detected_peaks):
                first_detected_group_id = row.overlap_group_id
                break
        for peak_idx, row in enumerate(sorted_group.itertuples(index=False), start=1):
            dominant = path_lookup.loc[row.dominant_path_id]
            detected = bool(row.power_total_db >= config.threshold_db)
            owner_type = "mixture" if bool(row.is_mixture) else str(row.dominant_path_type)
            peak_width_s = config.time_resolution_s * (1.0 + 0.25 * max(0, int(row.num_truth_paths) - 1))
            rows.append(
                {
                    "sequence_id": sequence_id,
                    "time_idx": int(time_idx),
                    "peak_id": f"{sequence_id}_t{int(time_idx):04d}_pk{peak_idx:03d}",
                    "rx_pol_state": "dual",
                    "peak_delay_s": row.delay_center_s,
                    "peak_range_m": row.delay_center_s * C0,
                    "peak_amp_db": row.power_total_db,
                    "peak_phase_rad": float(dominant["phase_rad"]),
                    "peak_width_s": peak_width_s,
                    "peak_prominence_db": float(row.power_total_db - config.threshold_db),
                    "early_energy": float(10.0 ** (row.power_total_db / 10.0) * (1.0 - 0.25 * row.power_multi_bounce_fraction)),
                    "late_energy": float(10.0 ** (row.power_total_db / 10.0) * (0.25 + row.power_multi_bounce_fraction)),
                    "first_path_flag": bool(detected and row.overlap_group_id == first_detected_group_id),
                    "detected_flag": detected,
                    "threshold_db": config.threshold_db,
                    "nearest_truth_path_id": row.dominant_path_id,
                    "peak_owner_type": owner_type,
                    "peak_purity": row.peak_purity,
                }
            )
    return pd.DataFrame(rows)


def build_regime_summary(overlap_groups: pd.DataFrame) -> pd.DataFrame:
    conditions = [
        ("G0", "clean_los", overlap_groups["dominant_path_type"].eq("LoS") & overlap_groups["peak_purity"].ge(0.9)),
        ("G1", "resolved_los_resolved_single_bounce", overlap_groups["contains_single_bounce"] & ~overlap_groups["is_unresolved_los_sb"]),
        ("G2", "los_single_bounce_overlap", overlap_groups["is_unresolved_los_sb"]),
        ("G3", "weak_los_strong_single_bounce", overlap_groups["contains_los"] & overlap_groups["power_los_fraction"].lt(0.5) & overlap_groups["contains_single_bounce"]),
        ("G4", "multiple_single_bounce_overlap", overlap_groups["is_unresolved_sb_sb"]),
        ("G5", "single_bounce_near_threshold", overlap_groups["contains_single_bounce"] & overlap_groups["power_total_db"].between(-40.0, -25.0)),
        ("G6", "material_contrast_single_bounce", overlap_groups["contains_single_bounce"] & overlap_groups["dominant_material"].isin(["glass", "metal_pec", "wood"])),
        ("G7", "odd_even_parity_separable", overlap_groups["contains_single_bounce"] & ~overlap_groups["contains_multi_bounce"]),
        ("G8", "cp_ambiguous_low_confidence", overlap_groups["is_mixture"] & overlap_groups["peak_purity"].lt(0.65)),
        ("G9", "sequential_rhcp_lhcp_mismatch", overlap_groups["sequence_id"].astype(str).str.endswith("_T6") & overlap_groups["time_idx"].mod(3).eq(0)),
        ("G10", "diffuse_clutter_dominant", overlap_groups["dominant_path_type"].isin(["diffuse", "clutter_truth"])),
    ]
    rows = []
    for regime_id, regime_name, mask in conditions:
        rows.append(
            {
                "regime_id": regime_id,
                "regime_name": regime_name,
                "num_overlap_groups": int(mask.sum()),
                "fraction_overlap_groups": float(mask.mean()) if len(mask) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def build_rx_orientation_table(
    trajectory_truth: pd.DataFrame,
    config: Stage01Config | None = None,
    switch_interval_s: float = 1e-3,
) -> pd.DataFrame:
    cfg = config or Stage01Config(output_dir=Path("."))
    tag_model = normalize_tag_antenna_model_mode(cfg.tag_antenna_model_mode)
    boresights = legacy_dual_tag_boresights(cfg.legacy_dual_tag_alpha_deg, cfg.legacy_dual_tag_rotation_deg)
    rows = []
    for row in trajectory_truth.itertuples(index=False):
        out = {
            "sequence_id": row.sequence_id,
            "time_idx": int(row.time_idx),
            "rx_mode": "simultaneous_dual_cp",
            "tag_yaw_deg": row.yaw_deg,
            "tag_pitch_deg": row.pitch_deg,
            "tag_roll_deg": row.roll_deg,
            "rx_pol_state": "dual",
            "switch_state": "not_switched",
            "switch_interval_s": switch_interval_s,
            "snapshot_pair_id": f"{row.sequence_id}_t{int(row.time_idx):04d}_pair",
            "quasi_static_assumed": True,
            "orientation_noise_deg": 0.0,
            "imu_yaw_noise_deg": 0.0,
        }
        if tag_model in {"legacy_h10b_dual_tilted", "tilted_real_pattern"}:
            tilted_meta = _tilted_real_pattern_metadata(cfg) if tag_model == "tilted_real_pattern" else {}
            out.update(
                {
                    "rx_mode": "legacy_h10b_dual_tilted_cp"
                    if tag_model == "legacy_h10b_dual_tilted"
                    else "tilted_real_pattern_dual_cp",
                    "rx_pol_state": "dual_tag_sets_rhcp_lhcp",
                    "legacy_dual_tag_alpha_deg": float(cfg.legacy_dual_tag_alpha_deg),
                    "legacy_dual_tag_rotation_deg": float(cfg.legacy_dual_tag_rotation_deg),
                    "tag_ant1_boresight_x": boresights["tag_ant1"]["boresight_x"],
                    "tag_ant1_boresight_y": boresights["tag_ant1"]["boresight_y"],
                    "tag_ant1_boresight_z": boresights["tag_ant1"]["boresight_z"],
                    "tag_ant2_boresight_x": boresights["tag_ant2"]["boresight_x"],
                    "tag_ant2_boresight_y": boresights["tag_ant2"]["boresight_y"],
                    "tag_ant2_boresight_z": boresights["tag_ant2"]["boresight_z"],
                    "tag_ant1_signed_elevation_deg": boresights["tag_ant1"]["signed_elevation_deg"],
                    "tag_ant2_signed_elevation_deg": boresights["tag_ant2"]["signed_elevation_deg"],
                    **tilted_meta,
                }
            )
        rows.append(out)
    return pd.DataFrame(rows)


def build_path_interaction_table(path_truth: pd.DataFrame, surface_table: pd.DataFrame) -> pd.DataFrame:
    surface_lookup = surface_table.set_index(["scene_id", "surface_id"])
    scene_by_sequence = path_truth["sequence_id"].str.extract(r"^(?P<scene_id>[^_]+(?:_[^_]+)?)_A0_", expand=True)["scene_id"]
    path_truth = path_truth.copy()
    path_truth["_scene_id_tmp"] = scene_by_sequence.fillna(path_truth["sequence_id"].str.split("_").str[0])
    rows = []
    for _, path in path_truth.iterrows():
        if not isinstance(path["reflection_sequence"], str) or not path["reflection_sequence"]:
            continue
        surface_ids = [int(x) for x in path["reflection_sequence"].split(">") if x]
        materials = str(path["surface_material_sequence"]).split(">") if isinstance(path["surface_material_sequence"], str) else []
        incidence = [float(x) for x in str(path["incidence_angle_each_bounce_deg"]).split("|") if x]
        for bounce_idx, surface_id in enumerate(surface_ids, start=1):
            key = (path["_scene_id_tmp"], surface_id)
            if key in surface_lookup.index:
                surface = surface_lookup.loc[key]
                hit = np.array(
                    [
                        0.5 * (float(surface["x1_m"]) + float(surface["x2_m"])),
                        0.5 * (float(surface["y1_m"]) + float(surface["y2_m"])),
                        0.5 * (float(surface["z1_m"]) + float(surface["z2_m"])),
                    ],
                    dtype=float,
                )
                normal = np.array([surface["normal_x"], surface["normal_y"], surface["normal_z"]], dtype=float)
            else:
                hit = np.full(3, np.nan)
                normal = np.full(3, np.nan)
            material = materials[bounce_idx - 1] if bounce_idx - 1 < len(materials) else ""
            incidence_angle = incidence[bounce_idx - 1] if bounce_idx - 1 < len(incidence) else float("nan")
            rows.append(
                {
                    "sequence_id": path["sequence_id"],
                    "time_idx": int(path["time_idx"]),
                    "path_truth_id": path["path_truth_id"],
                    "bounce_idx": bounce_idx,
                    "surface_id": surface_id,
                    "material": material,
                    "incidence_angle_deg": incidence_angle,
                    "reflection_angle_deg": incidence_angle,
                    "path_segment_length_m": float(path["path_length_m"]) / (int(path["bounce_order"]) + 1),
                    "hit_x_m": hit[0],
                    "hit_y_m": hit[1],
                    "hit_z_m": hit[2],
                    "normal_x": normal[0],
                    "normal_y": normal[1],
                    "normal_z": normal[2],
                    "co_reflection_coeff_mag": 10.0 ** (-material_reflection_loss_db(material) / 20.0),
                    "cross_reflection_coeff_mag": 10.0 ** (-(material_reflection_loss_db(material) + 18.0) / 20.0),
                    "phase_shift_rad": math.pi if material in {"metal_pec", "pec"} else 0.35 * bounce_idx,
                    "handedness_flip_expected": bool(int(path["bounce_order"]) % 2 == 1),
                }
            )
    return pd.DataFrame(rows)


def build_polarimetric_path_table(path_truth: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for path in path_truth.itertuples(index=False):
        bounce = int(path.bounce_order)
        is_clutter = str(path.path_type) in {"diffuse", "clutter_truth"} or not bool(path.is_specular)
        expected_parity = "none" if bounce <= 0 or is_clutter else ("odd" if bounce % 2 else "even")
        amp = float(path.amplitude_linear)
        contrast_db = 1.0 if is_clutter else 3.0 + 4.0 * bounce
        if "metal" in str(path.surface_material_sequence):
            contrast_db += 3.0
        if "glass" in str(path.surface_material_sequence):
            contrast_db += 2.0
        same_power = amp * amp
        opposite_power = same_power * 10.0 ** (-contrast_db / 10.0)
        if expected_parity == "odd":
            p_rhcp, p_lhcp = opposite_power, same_power
        elif expected_parity == "even":
            p_rhcp, p_lhcp = same_power, opposite_power
        else:
            p_rhcp, p_lhcp = same_power, 0.15 * same_power
        s0 = p_rhcp + p_lhcp
        s3 = (p_rhcp - p_lhcp) / max(s0, EPS)
        phase = float(path.phase_rad)
        e_r = math.sqrt(max(p_rhcp, 0.0)) * complex(math.cos(phase), math.sin(phase))
        e_l = math.sqrt(max(p_lhcp, 0.0)) * complex(math.cos(-phase), math.sin(-phase))
        rows.append(
            {
                "sequence_id": path.sequence_id,
                "time_idx": int(path.time_idx),
                "path_truth_id": path.path_truth_id,
                "tx_pol": "RHCP",
                "rx_pol_basis": "RHCP/LHCP",
                "E_RHCP_complex": f"{e_r.real:.8e}{e_r.imag:+.8e}j",
                "E_LHCP_complex": f"{e_l.real:.8e}{e_l.imag:+.8e}j",
                "P_RHCP_linear": p_rhcp,
                "P_LHCP_linear": p_lhcp,
                "P_co_linear": max(p_rhcp, p_lhcp),
                "P_cross_linear": min(p_rhcp, p_lhcp),
                "xpr_db": db10(max(p_rhcp, p_lhcp) / max(min(p_rhcp, p_lhcp), EPS)),
                "cpr_db": db10(p_rhcp / max(p_lhcp, EPS)),
                "handedness_contrast_db": contrast_db,
                "stokes_s0": s0,
                "stokes_s1": 0.0,
                "stokes_s2": 0.0,
                "stokes_s3": s3,
                "expected_cp_parity": expected_parity,
                "observed_cp_parity_truth": "odd" if s3 < -0.15 else ("even" if s3 > 0.15 else "none"),
            }
        )
    return pd.DataFrame(rows)


def leading_edge_delay_s(peak, purity: float, width_s: float, config: Stage01Config) -> float:
    mode = normalize_range_estimator_mode(config.range_estimator_mode)
    peak_delay = float(peak.peak_delay_s)
    if mode == "peak_group_center":
        return peak_delay + (1.0 - purity) * 0.15 * width_s
    if mode not in {"lde_proxy", "h10b_artifact_lde", "h10b_artifact_range", "h10b_raw_cir_lde"}:
        raise ValueError(
            f"Unsupported range_estimator_mode={config.range_estimator_mode!r}; "
            "expected peak_group_center, lde_proxy, h10b_artifact_lde, or h10b_raw_cir_lde"
        )

    threshold = float(np.clip(config.lde_relative_threshold, 0.0, 1.0))
    # Synthetic LDE proxy: move from the peak center toward the leading edge.
    # Lower purity / wider peaks still push the estimate later, matching a noisy
    # first-path detector rather than an oracle earliest-truth-path lookup.
    leading_fraction = max(0.0, 0.5 - 0.5 * threshold)
    noise_fraction = max(0.0, 1.0 - purity) * max(0.0, float(config.lde_noise_scale))
    return peak_delay - leading_fraction * width_s + noise_fraction * width_s


def build_mpc_estimate_table(
    peak_table: pd.DataFrame,
    overlap_groups: pd.DataFrame,
    config: Stage01Config | None = None,
    raw_cir_lde_table: pd.DataFrame | None = None,
) -> pd.DataFrame:
    cfg = config or Stage01Config(output_dir=Path("."))
    overlap_lookup = overlap_groups.set_index("overlap_group_id")
    raw_cir_lookup = (
        raw_cir_lde_table.set_index("measurement_id") if raw_cir_lde_table is not None and len(raw_cir_lde_table) else pd.DataFrame()
    )
    rows = []
    for peak in peak_table.itertuples(index=False):
        group_id = str(peak.peak_id).replace("_pk", "_g")
        group = overlap_lookup.loc[group_id] if group_id in overlap_lookup.index else None
        purity = float(peak.peak_purity)
        width = float(peak.peak_width_s)
        estimated_delay_s = leading_edge_delay_s(peak, purity, width, cfg)
        estimated_delay_s = max(0.0, estimated_delay_s)
        measurement_id = str(peak.peak_id).replace("_pk", "_m")
        range_mode = normalize_range_estimator_mode(cfg.range_estimator_mode)
        if range_mode in {"h10b_artifact_lde", "h10b_artifact_range"}:
            estimator_name = "legacy_h10b_artifact_lde"
        elif range_mode == "h10b_raw_cir_lde":
            estimator_name = "h10b_raw_cir_dw_lde"
        elif range_mode == "lde_proxy":
            estimator_name = "stage01_lde_proxy"
        else:
            estimator_name = "stage01_peak_group_proxy"
        raw_diag = {}
        if estimator_name == "h10b_raw_cir_dw_lde" and not raw_cir_lookup.empty and measurement_id in raw_cir_lookup.index:
            raw_row = raw_cir_lookup.loc[measurement_id]
            raw_delay = float(raw_row.get("raw_cir_lde_delay_s", float("nan")))
            raw_range = float(raw_row.get("raw_cir_lde_range_m", float("nan")))
            if np.isfinite(raw_delay) and np.isfinite(raw_range):
                estimated_delay_s = max(0.0, raw_delay)
            raw_diag = {
                "raw_cir_lde_delay_s": raw_delay,
                "raw_cir_lde_range_m": raw_range,
                "raw_cir_peak_index": float(raw_row.get("raw_cir_peak_index", float("nan"))),
                "raw_cir_lde_index": float(raw_row.get("raw_cir_lde_index", float("nan"))),
                "raw_cir_noise_floor": float(raw_row.get("raw_cir_noise_floor", float("nan"))),
                "raw_cir_threshold": float(raw_row.get("raw_cir_threshold", float("nan"))),
                "raw_cir_peak_power": float(raw_row.get("raw_cir_peak_power", float("nan"))),
                "raw_cir_peak_amplitude_db": float(raw_row.get("raw_cir_peak_amplitude_db", float("nan"))),
                "raw_cir_channel_set": str(raw_row.get("raw_cir_channel_set", "")),
                "raw_cir_selected_channel": str(raw_row.get("raw_cir_selected_channel", "")),
                "raw_cir_vector_mode": str(raw_row.get("raw_cir_vector_mode", "")),
                "raw_cir_estimator_status": str(raw_row.get("raw_cir_estimator_status", "")),
            }
            for col in (
                "h10b_channel_vector_order",
                "h10b_range_vector_m",
                "h10b_amplitude_vector_db",
                "h10b_lde_delay_vector_s",
                "h10b_status_vector",
                "h10b_ant1_pol_range_delta_m",
                "h10b_ant2_pol_range_delta_m",
                "h10b_rhcp_ant_range_delta_m",
                "h10b_lhcp_ant_range_delta_m",
                "h10b_cross_pol_range_delta_m",
                *h10b_raw_cir_vector_columns(),
            ):
                if col in raw_row.index:
                    raw_diag[col] = raw_row.get(col)
        estimator_config_id = (
            f"lde_proxy_thr{float(cfg.lde_relative_threshold):.3g}_noise{float(cfg.lde_noise_scale):.3g}"
            if estimator_name == "stage01_lde_proxy"
            else (
                "legacy_h10b_artifact_range_est_mean_v1"
                if estimator_name == "legacy_h10b_artifact_lde"
                else (
                    f"h10b_raw_cir_dw_lde_thr{float(cfg.lde_relative_threshold):.3g}"
                    if estimator_name == "h10b_raw_cir_dw_lde"
                    else "peak_group_center_v1"
                )
            )
        )
        row = {
                "sequence_id": peak.sequence_id,
                "time_idx": int(peak.time_idx),
                "measurement_id": measurement_id,
                "surface_family_id": "" if group is None else str(group.dominant_reflection_sequence),
                "reflection_sequence": "" if group is None else str(group.dominant_reflection_sequence),
                "order": 0 if group is None else int(group.dominant_bounce_order),
                "beta_body_deg": float("nan") if group is None else float(group.dominant_beta_body_deg),
                "beta_body_rad": float("nan") if group is None else math.radians(float(group.dominant_beta_body_deg)),
                "estimated_delay_s": estimated_delay_s,
                "estimated_range_m": estimated_delay_s * C0,
                "estimated_amp_db": float(peak.peak_amp_db),
                "estimated_phase_rad": float(peak.peak_phase_rad),
                "estimated_width_s": width,
                "estimated_snr_db": float(peak.peak_prominence_db),
                "estimated_noise_var": 10.0 ** (float(peak.threshold_db) / 10.0),
                "estimated_rx_pol": peak.rx_pol_state,
                "estimated_rssd_db": 4.0 * math.sin(float(peak.peak_range_m)),
                "estimated_cp_ratio_db": 0.0 if group is None else 8.0 * float(group.power_single_bounce_fraction) - 4.0 * float(group.power_multi_bounce_fraction),
                "range_estimator_mode": str(cfg.range_estimator_mode),
                "lde_relative_threshold": float(cfg.lde_relative_threshold),
                "lde_noise_scale": float(cfg.lde_noise_scale),
                "estimator_name": estimator_name,
                "estimator_config_id": estimator_config_id,
            }
        row.update(raw_diag)
        rows.append(row)
    return pd.DataFrame(rows)


def build_truth_measurement_assoc_table(mpc: pd.DataFrame, peak_table: pd.DataFrame) -> pd.DataFrame:
    peak_lookup = peak_table.assign(measurement_id=peak_table["peak_id"].str.replace("_pk", "_m", regex=False)).set_index("measurement_id")
    rows = []
    for meas in mpc.itertuples(index=False):
        peak = peak_lookup.loc[meas.measurement_id]
        association_type = "many_to_one" if float(peak.peak_purity) < 0.85 else "one_to_one"
        if not bool(peak.detected_flag):
            association_type = "missed"
        rows.append(
            {
                "sequence_id": meas.sequence_id,
                "time_idx": int(meas.time_idx),
                "measurement_id": meas.measurement_id,
                "matched_path_truth_id": peak.nearest_truth_path_id,
                "matched_feature_id": "",
                "matched_overlap_group_id": str(peak.peak_id).replace("_pk", "_g"),
                "association_type": association_type,
                "delay_error_s": 0.0,
                "range_error_m": abs(float(meas.estimated_range_m) - float(peak.peak_range_m)),
                "amp_error_db": 0.0,
                "is_false_alarm": False,
                "is_missed_detection": not bool(peak.detected_flag),
                "is_valid_specular": bool(peak.detected_flag and peak.peak_owner_type != "clutter_truth"),
                "is_clean_single_path": bool(float(peak.peak_purity) >= 0.85 and peak.peak_owner_type != "mixture"),
            }
        )
    return pd.DataFrame(rows)


def enrich_assoc_with_feature(assoc: pd.DataFrame, path_truth: pd.DataFrame) -> pd.DataFrame:
    out = assoc.copy()
    path_lookup = path_truth.set_index("path_truth_id")
    out["matched_feature_id"] = out["matched_path_truth_id"].map(path_lookup["feature_id"])
    return out


def build_cp_feature_table(mpc: pd.DataFrame, assoc: pd.DataFrame, overlap_groups: pd.DataFrame, polarimetric_path: pd.DataFrame) -> pd.DataFrame:
    assoc_lookup = assoc.set_index("measurement_id")
    overlap_lookup = overlap_groups.set_index("overlap_group_id")
    pol_lookup = polarimetric_path.set_index("path_truth_id")
    rows = []
    for meas in mpc.itertuples(index=False):
        assoc_row = assoc_lookup.loc[meas.measurement_id]
        group = overlap_lookup.loc[assoc_row.matched_overlap_group_id]
        pol = pol_lookup.loc[assoc_row.matched_path_truth_id]
        purity = float(group.peak_purity)
        cp_reliability = float(np.clip(0.35 + 0.45 * purity + 0.15 * abs(float(pol.stokes_s3)), 0.0, 1.0))
        late_leakage = float(group.power_multi_bounce_fraction + 0.5 * (1.0 - purity))
        fp_geometry_robust = float(np.clip(purity * (1.0 - late_leakage), 0.0, 1.0))
        cp_phase_residual_var = float((1.0 - cp_reliability) * (0.2 + group.num_truth_paths * 0.05))
        rows.append(
            {
                "sequence_id": meas.sequence_id,
                "time_idx": int(meas.time_idx),
                "measurement_id": meas.measurement_id,
                "cp_feature_set_version": "stage02_cp_proxy_v1",
                "polarimetric_balance": float(1.0 - abs(float(pol.stokes_s3))),
                "late_leakage": late_leakage,
                "fp_geometry_robust": fp_geometry_robust,
                "cp3_core_1": cp_reliability,
                "cp3_core_2": float(pol.stokes_s3),
                "cp3_core_3": float(group.material_purity),
                "stokes_s3_fp": float(pol.stokes_s3),
                "stokes_s3_late": float(pol.stokes_s3) * (1.0 - late_leakage),
                "xpr_fp_db": float(pol.xpr_db),
                "xpr_late_db": float(pol.xpr_db) - 3.0 * late_leakage,
                "handedness_contrast_db": float(pol.handedness_contrast_db),
                "cp_phase_residual_var": cp_phase_residual_var,
                "cp_phase_slope_delay_s": float(meas.estimated_delay_s) * float(pol.stokes_s3),
                "feature_validity_flag": bool(cp_reliability >= 0.5),
                "cp_reliability": cp_reliability,
                "cp_parity_label": pol.observed_cp_parity_truth,
                "cp_parity_confidence": float(abs(float(pol.stokes_s3))),
                "clean_prob": float(np.clip(0.2 + 0.75 * purity + 0.1 * cp_reliability, 0.0, 1.0)),
            }
        )
    return pd.DataFrame(rows)


def build_rssd_feature_table(
    mpc: pd.DataFrame,
    assoc: pd.DataFrame,
    path_truth: pd.DataFrame,
    trajectory_truth: pd.DataFrame,
    config: Stage01Config | None = None,
) -> pd.DataFrame:
    cfg = config or Stage01Config(output_dir=Path("."))
    tag_model = normalize_tag_antenna_model_mode(cfg.tag_antenna_model_mode)
    legacy_lut = load_legacy_dual_tag_h10b_lut(cfg) if tag_model == "legacy_h10b_dual_tilted" else pd.DataFrame()
    path_lookup = path_truth.set_index("path_truth_id")
    traj_lookup = trajectory_truth.set_index(["sequence_id", "time_idx"])
    assoc_lookup = assoc.set_index("measurement_id")
    rows = []
    for meas in mpc.itertuples(index=False):
        assoc_row = assoc_lookup.loc[meas.measurement_id]
        path = path_lookup.loc[assoc_row.matched_path_truth_id]
        traj = traj_lookup.loc[(meas.sequence_id, int(meas.time_idx))]
        beta = float(path.rx_arrival_beta_body_deg)
        theta = float(path.theta_elevation_deg)
        mode = str(path.get("polarization_mode", "CP"))
        pol_ant1_db = float(path.get("pol_mismatch_ant1_db", 0.0))
        pol_ant2_db = float(path.get("pol_mismatch_ant2_db", 0.0))
        pred = 8.0 * math.sin(math.radians(beta)) * math.cos(math.radians(theta))
        if mode == "LP":
            pred = pred + pol_ant1_db - pol_ant2_db
        rssd_residual = 0.2 * (1.0 - float(path.amplitude_linear))
        rssd = pred + rssd_residual
        ant1_power_db = float(meas.estimated_amp_db) + rssd / 2.0
        ant2_power_db = float(meas.estimated_amp_db) - rssd / 2.0
        rssd_source = "synthetic_orientation_proxy"
        legacy_terms: dict[str, object] = {
            "tag_antenna_model_mode": tag_model,
            "legacy_dual_tag_artifact_path": "",
            "legacy_dual_tag_lut_case_id": "",
            "legacy_dual_tag_lut_source_case_id": "",
            "legacy_dual_tag_lut_theta_abs_deg": float("nan"),
            "legacy_dual_tag_lut_range_m": float("nan"),
            "legacy_dual_tag_alpha_deg": float(cfg.legacy_dual_tag_alpha_deg),
            "legacy_dual_tag_rotation_deg": float(cfg.legacy_dual_tag_rotation_deg),
            "legacy_dual_tag_rssd_channel": "",
            "legacy_dual_tag_rssd_prediction_mode": normalize_legacy_dual_tag_rssd_prediction_mode(
                cfg.legacy_dual_tag_rssd_prediction_mode,
                tag_model,
            ),
            "legacy_dual_tag_power_offset_mode": "",
            "tag_ant1_boresight_x": float("nan"),
            "tag_ant1_boresight_y": float("nan"),
            "tag_ant1_boresight_z": float("nan"),
            "tag_ant2_boresight_x": float("nan"),
            "tag_ant2_boresight_y": float("nan"),
            "tag_ant2_boresight_z": float("nan"),
            "tag_ant1_signed_elevation_deg": float("nan"),
            "tag_ant2_signed_elevation_deg": float("nan"),
            "RSS_ant1_RH_db": float("nan"),
            "RSS_ant1_LH_db": float("nan"),
            "RSS_ant2_RH_db": float("nan"),
            "RSS_ant2_LH_db": float("nan"),
            "RSS_ant1_total_db": float("nan"),
            "RSS_ant2_total_db": float("nan"),
            "RSSD_RH_db": float("nan"),
            "RSSD_LH_db": float("nan"),
            "RSSD_total_db": float("nan"),
            "RSSD_mean_pol_db": float("nan"),
            "legacy_dual_tag_power_offset_db": float("nan"),
            "legacy_dual_tag_match_theta_error_deg": float("nan"),
            "legacy_dual_tag_match_range_error_m": float("nan"),
            "legacy_dual_tag_range_est_mean_m": float("nan"),
            "legacy_dual_tag_range_reliable_label": "",
            "tilted_real_pattern_power_offset_db": float("nan"),
            "tilted_real_pattern_gain_ant1_rh_db": float("nan"),
            "tilted_real_pattern_gain_ant1_lh_db": float("nan"),
            "tilted_real_pattern_gain_ant2_rh_db": float("nan"),
            "tilted_real_pattern_gain_ant2_lh_db": float("nan"),
            "rx_ant1_rhcp_pattern_file": "",
            "rx_ant1_lhcp_pattern_file": "",
            "rx_ant2_rhcp_pattern_file": "",
            "rx_ant2_lhcp_pattern_file": "",
            "tag_attitude_source": str(cfg.tag_attitude_source),
            "tag_pitch_deg": float(cfg.tag_pitch_deg),
            "tag_roll_deg": float(cfg.tag_roll_deg),
            "rx_ant1_mount_rotation": str(cfg.rx_ant1_mount_rotation),
            "rx_ant2_mount_rotation": str(cfg.rx_ant2_mount_rotation),
            "rx_ant1_mount_matrix": "",
            "rx_ant2_mount_matrix": "",
            "pattern_gain_normalization": str(cfg.pattern_gain_normalization),
            "pattern_phase_convention": str(cfg.pattern_phase_convention),
            "pattern_pol_basis": str(cfg.pattern_pol_basis),
            "frequency_hz": float(cfg.frequency_hz),
        }
        if tag_model == "legacy_h10b_dual_tilted":
            legacy_terms = legacy_dual_tag_h10b_feature_terms(meas, path, theta, cfg, legacy_lut)
            rssd = float(legacy_terms["selected_rssd_db"])
            ant1_power_db = float(legacy_terms["RSS_ant1_total_db"])
            ant2_power_db = float(legacy_terms["RSS_ant2_total_db"])
            pred = rssd
            rssd_residual = 0.0
            rssd_source = "legacy_h10b_dual_tag_features_wide"
        elif tag_model == "tilted_real_pattern":
            legacy_terms = tilted_real_pattern_feature_terms(meas, path, beta, theta, cfg)
            rssd = float(legacy_terms["selected_rssd_db"])
            ant1_power_db = float(legacy_terms["RSS_ant1_total_db"])
            ant2_power_db = float(legacy_terms["RSS_ant2_total_db"])
            pred = rssd
            rssd_residual = 0.0
            rssd_source = "tilted_real_pattern_receiver"
        row = {
            "sequence_id": meas.sequence_id,
            "time_idx": int(meas.time_idx),
            "measurement_id": meas.measurement_id,
            "ant1_power_db": ant1_power_db,
            "ant2_power_db": ant2_power_db,
            "rssd_db": rssd,
            "rss_sum_db": _db_sum([ant1_power_db, ant2_power_db]),
            "tag_yaw_deg": float(traj.yaw_deg),
            "beta_body_deg_truth": beta,
            "theta_elevation_deg_truth": theta,
            "rssd_lut_pred_db": pred,
            "rssd_residual_db": rssd_residual,
            "rssd_lut_residual_db": rssd_residual,
            "rssd_confidence": float(np.clip(1.0 - abs(rssd - pred) / 8.0, 0.0, 1.0)),
            "rssd_source": rssd_source,
            "legacy_dual_tag_rssd_prediction_mode": normalize_legacy_dual_tag_rssd_prediction_mode(
                cfg.legacy_dual_tag_rssd_prediction_mode,
                tag_model,
            ),
            "legacy_dual_tag_power_offset_mode": str(legacy_terms.get("legacy_dual_tag_power_offset_mode", "")),
            "polarization_mode": mode,
            "pol_mismatch_ant1_db": pol_ant1_db,
            "pol_mismatch_ant2_db": pol_ant2_db,
            "direct_power_ratio": float(path.get("direct_power_ratio", float("nan"))),
            "reflected_power_ratio": float(path.get("reflected_power_ratio", float("nan"))),
            "odd_bounce_power_ratio": float(path.get("odd_bounce_power_ratio", float("nan"))),
            "even_bounce_power_ratio": float(path.get("even_bounce_power_ratio", float("nan"))),
            "dominant_path_bounce_count": float(path.get("dominant_path_bounce_count", float("nan"))),
            "dominant_path_beta_deg": float(path.get("dominant_path_beta_deg", float("nan"))),
            "direct_vs_dominant_beta_error_deg": float(path.get("direct_vs_dominant_beta_error_deg", float("nan"))),
            "lp_te_power_fraction": float(path.get("lp_te_power_fraction", float("nan"))),
            "lp_tm_power_fraction": float(path.get("lp_tm_power_fraction", float("nan"))),
        }
        row.update({k: v for k, v in legacy_terms.items() if k != "selected_rssd_db"})
        rows.append(row)
    return pd.DataFrame(rows)


def _normalize_control_mode(value: str, allowed: set[str], field_name: str) -> str:
    mode = str(value).strip().lower()
    if mode not in allowed:
        expected = ", ".join(sorted(allowed))
        raise ValueError(f"Unsupported {field_name}={value!r}; expected one of {expected}")
    return mode


def _wrap_deg_series(values: pd.Series) -> pd.Series:
    return ((pd.to_numeric(values, errors="coerce") + 180.0) % 360.0) - 180.0


def _normalize_shuffle_level(value: str, field_name: str) -> str:
    level = str(value).strip().lower()
    aliases = {
        "global": "within_slice",
        "slice": "within_slice",
        "within-run": "within_slice",
        "within_run": "within_slice",
        "sequence": "within_sequence",
    }
    level = aliases.get(level, level)
    if level not in {"within_slice", "within_sequence"}:
        raise ValueError(f"Unsupported {field_name}={value!r}; expected within_slice or within_sequence")
    return level


def _shuffle_dataframe_columns(
    table: pd.DataFrame,
    columns: list[str],
    rng: np.random.Generator,
    level: str,
) -> pd.DataFrame:
    if not columns or len(table) <= 1:
        return table
    out = table.copy()
    if level == "within_sequence" and "sequence_id" in out.columns:
        for _, group in out.groupby("sequence_id", sort=False):
            if len(group) <= 1:
                continue
            shuffled = out.loc[group.index, columns].iloc[rng.permutation(len(group))].reset_index(drop=True)
            out.loc[group.index, columns] = shuffled.to_numpy()
        return out
    shuffled = out[columns].iloc[rng.permutation(len(out))].reset_index(drop=True)
    out.loc[:, columns] = shuffled.to_numpy()
    return out


def apply_rssd_negative_control(rssd_features: pd.DataFrame, config: Stage01Config) -> pd.DataFrame:
    """Apply deterministic RSSD ablations for orientation/RSSD contribution tests."""

    mode = _normalize_control_mode(
        str(config.rssd_control_mode),
        {"nominal", "noise", "shuffle", "sign_flip", "zero"},
        "rssd_control_mode",
    )
    if bool(config.disable_rssd):
        mode = "zero"
    if bool(config.rssd_sign_flip):
        mode = "sign_flip"
    if bool(config.rssd_shuffle):
        mode = "shuffle"
    noise_std_db = max(0.0, float(config.rssd_noise_std_db))
    noise_scale = max(0.0, float(config.rssd_noise_scale))
    if noise_std_db <= 0.0 and noise_scale > 0.0:
        noise_std_db = noise_scale
    shuffle_level = _normalize_shuffle_level(str(config.rssd_shuffle_level), "rssd_shuffle_level")
    if mode == "nominal" and noise_std_db > 0.0:
        mode = "noise"
    if mode == "nominal":
        return rssd_features

    out = rssd_features.copy()
    control_seed = folded_seed(
        config.random_seed,
        config.perturbation_config_id,
        "rssd_negative_control",
        mode,
        noise_std_db,
        shuffle_level,
    )
    target_cols = [
        col
        for col in [
            "ant1_power_db",
            "ant2_power_db",
            "rssd_db",
            "rssd_lut_pred_db",
            "rssd_residual_db",
            "rssd_lut_residual_db",
            "rssd_confidence",
        ]
        if col in out.columns
    ]
    for col in target_cols:
        out[f"{col}_nominal"] = out[col]

    def refresh_residuals() -> None:
        if {"rssd_db", "rssd_lut_pred_db"}.issubset(out.columns):
            residual = pd.to_numeric(out["rssd_db"], errors="coerce") - pd.to_numeric(out["rssd_lut_pred_db"], errors="coerce")
            out["rssd_residual_db"] = residual
            if "rssd_lut_residual_db" in out.columns:
                out["rssd_lut_residual_db"] = residual
            if "rssd_confidence" in out.columns:
                out["rssd_confidence"] = np.clip(1.0 - np.abs(residual) / 8.0, 0.0, 1.0)

    rng = np.random.default_rng(control_seed)
    if mode == "shuffle" and len(out) > 1:
        observed_cols = [col for col in ["ant1_power_db", "ant2_power_db", "rssd_db"] if col in out.columns]
        out = _shuffle_dataframe_columns(out, observed_cols, rng, shuffle_level)
        refresh_residuals()
    elif mode == "noise":
        if noise_std_db <= 0.0:
            noise_std_db = 4.0
        noise = rng.normal(0.0, noise_std_db, size=len(out))
        if "rssd_db" in out.columns:
            out["rssd_db"] = pd.to_numeric(out["rssd_db"], errors="coerce") + noise
        if "ant1_power_db" in out.columns:
            out["ant1_power_db"] = pd.to_numeric(out["ant1_power_db"], errors="coerce") + noise / 2.0
        if "ant2_power_db" in out.columns:
            out["ant2_power_db"] = pd.to_numeric(out["ant2_power_db"], errors="coerce") - noise / 2.0
        refresh_residuals()
    elif mode == "sign_flip":
        if "rssd_db" in out.columns:
            out["rssd_db"] = -pd.to_numeric(out["rssd_db"], errors="coerce")
        if {"ant1_power_db", "ant2_power_db"}.issubset(out.columns):
            ant1 = out["ant1_power_db"].copy()
            out["ant1_power_db"] = out["ant2_power_db"]
            out["ant2_power_db"] = ant1
        refresh_residuals()
    elif mode == "zero":
        if "rssd_db" in out.columns:
            out["rssd_db"] = 0.0
        if "rssd_residual_db" in out.columns:
            out["rssd_residual_db"] = 0.0
        if "rssd_lut_residual_db" in out.columns:
            out["rssd_lut_residual_db"] = 0.0
        if "rssd_confidence" in out.columns:
            out["rssd_confidence"] = 0.05
        if {"ant1_power_db", "ant2_power_db"}.issubset(out.columns):
            mean_power = (
                pd.to_numeric(out["ant1_power_db"], errors="coerce")
                + pd.to_numeric(out["ant2_power_db"], errors="coerce")
            ) / 2.0
            out["ant1_power_db"] = mean_power
            out["ant2_power_db"] = mean_power
    else:
        raise ValueError(f"Unhandled rssd_control_mode={mode!r}")

    out["rssd_control_mode"] = mode
    out["rssd_noise_std_db"] = float(noise_std_db)
    out["rssd_noise_scale"] = float(noise_scale)
    out["rssd_shuffle_flag"] = bool(mode == "shuffle")
    out["rssd_shuffle_level"] = str(shuffle_level)
    out["rssd_shuffle_seed"] = int(control_seed) if mode == "shuffle" else 0
    out["rssd_sign_flip_flag"] = bool(mode == "sign_flip")
    out["rssd_disabled_flag"] = bool(mode == "zero")
    out["rssd_zero_mode"] = "inactive_log_score" if mode == "zero" else ""
    return out


def apply_solver_orientation_control(trajectory_truth: pd.DataFrame, config: Stage01Config) -> pd.DataFrame:
    """Build deterministic RSSD-interpretation yaw controls while preserving physical truth."""

    mode = _normalize_control_mode(
        str(config.orientation_control_mode),
        {"nominal", "yaw_noise", "yaw_shuffle", "fixed", "zero"},
        "orientation_control_mode",
    )
    if bool(config.disable_orientation):
        mode = "zero"
    if bool(config.yaw_shuffle):
        mode = "yaw_shuffle"
    yaw_noise_deg = max(0.0, float(config.yaw_noise_deg))
    yaw_fixed_deg = float(config.yaw_fixed_deg)
    shuffle_level = _normalize_shuffle_level(str(config.yaw_shuffle_level), "yaw_shuffle_level")
    if mode == "nominal" and yaw_noise_deg > 0.0:
        mode = "yaw_noise"
    if mode == "nominal":
        return trajectory_truth

    out = trajectory_truth.copy()
    out["yaw_deg_nominal"] = out["yaw_deg"]
    control_seed = folded_seed(
        config.random_seed,
        config.perturbation_config_id,
        "orientation_negative_control",
        mode,
        yaw_noise_deg,
        shuffle_level,
        yaw_fixed_deg,
    )
    rng = np.random.default_rng(control_seed)
    if mode == "yaw_shuffle" and len(out) > 1:
        if shuffle_level == "within_sequence" and "sequence_id" in out.columns:
            for _, group in out.groupby("sequence_id", sort=False):
                if len(group) <= 1:
                    continue
                shuffled = out.loc[group.index, "yaw_deg"].iloc[rng.permutation(len(group))].reset_index(drop=True)
                out.loc[group.index, "yaw_deg"] = shuffled.to_numpy()
        else:
            shuffled = out["yaw_deg"].iloc[rng.permutation(len(out))].reset_index(drop=True)
            out["yaw_deg"] = shuffled.to_numpy()
    elif mode == "yaw_noise":
        if yaw_noise_deg <= 0.0:
            yaw_noise_deg = 30.0
        out["yaw_deg"] = pd.to_numeric(out["yaw_deg"], errors="coerce") + rng.normal(0.0, yaw_noise_deg, size=len(out))
    elif mode in {"fixed", "zero"}:
        if mode == "zero":
            yaw_fixed_deg = 0.0
        out["yaw_deg"] = float(yaw_fixed_deg)
    else:
        raise ValueError(f"Unhandled orientation_control_mode={mode!r}")

    out["yaw_deg"] = _wrap_deg_series(out["yaw_deg"])
    if "omega_z_radps" in out.columns:
        out["omega_z_radps_nominal"] = out["omega_z_radps"]
        omega_parts: list[pd.Series] = []
        for _, group in out.groupby("sequence_id", sort=False):
            yaw_rad = np.unwrap(np.deg2rad(pd.to_numeric(group["yaw_deg"], errors="coerce").to_numpy(dtype=float)))
            if len(group) > 1 and "time_s" in group.columns:
                time_s = pd.to_numeric(group["time_s"], errors="coerce").to_numpy(dtype=float)
                dt = float(np.nanmedian(np.diff(time_s)))
                if not np.isfinite(dt) or dt <= 0.0:
                    dt = float(config.dt_s)
            else:
                dt = float(config.dt_s)
            omega_parts.append(pd.Series(np.gradient(yaw_rad, dt), index=group.index))
        if omega_parts:
            out["omega_z_radps"] = pd.concat(omega_parts).sort_index()
    out["orientation_control_mode"] = mode
    out["yaw_noise_deg"] = float(yaw_noise_deg)
    out["yaw_shuffle_flag"] = bool(mode == "yaw_shuffle")
    out["yaw_shuffle_level"] = str(shuffle_level)
    out["yaw_shuffle_seed"] = int(control_seed) if mode == "yaw_shuffle" else 0
    out["yaw_fixed_deg"] = float(yaw_fixed_deg)
    out["orientation_disabled_flag"] = bool(mode in {"fixed", "zero"})
    return out


def build_regime_label_table(mpc: pd.DataFrame, assoc: pd.DataFrame, overlap_groups: pd.DataFrame, path_truth: pd.DataFrame, cp_features: pd.DataFrame) -> pd.DataFrame:
    assoc_lookup = assoc.set_index("measurement_id")
    overlap_lookup = overlap_groups.set_index("overlap_group_id")
    path_lookup = path_truth.set_index("path_truth_id")
    cp_lookup = cp_features.set_index("measurement_id")
    rows = []
    for meas in mpc.itertuples(index=False):
        ar = assoc_lookup.loc[meas.measurement_id]
        og = overlap_lookup.loc[ar.matched_overlap_group_id]
        pt = path_lookup.loc[ar.matched_path_truth_id]
        cp = cp_lookup.loc[meas.measurement_id]
        sequential_mismatch = str(meas.sequence_id).endswith("_T6") and int(meas.time_idx) % 3 == 0
        if str(pt.path_type) in {"diffuse", "clutter_truth"} or str(og.dominant_path_type) in {"diffuse", "clutter_truth"}:
            regime_id, regime_name = "G10", "diffuse_clutter_dominant"
        elif sequential_mismatch:
            regime_id, regime_name = "G9", "sequential_rhcp_lhcp_mismatch"
        elif bool(og.contains_los and float(og.power_los_fraction) < 0.5 and og.contains_single_bounce):
            regime_id, regime_name = "G3", "weak_los_strong_single_bounce"
        elif bool(og.is_unresolved_los_sb):
            regime_id, regime_name = "G2", "los_single_bounce_overlap"
        elif bool(og.is_unresolved_sb_sb):
            regime_id, regime_name = "G4", "multiple_single_bounce_overlap"
        elif bool(og.contains_single_bounce) and float(og.power_total_db) < -25.0:
            regime_id, regime_name = "G5", "single_bounce_near_threshold"
        elif bool(og.contains_single_bounce) and str(og.dominant_material) in {"glass", "metal_pec", "wood"}:
            regime_id, regime_name = "G6", "material_contrast_single_bounce"
        elif str(pt.path_type) == "LoS" and float(og.peak_purity) >= 0.9:
            regime_id, regime_name = "G0", "clean_los"
        elif bool(og.contains_single_bounce):
            regime_id, regime_name = "G1", "resolved_los_resolved_single_bounce"
        elif bool(og.is_mixture) and float(og.peak_purity) < 0.65:
            regime_id, regime_name = "G8", "cp_ambiguous_low_confidence"
        else:
            regime_id, regime_name = "G7", "odd_even_parity_separable"
        rows.append(
            {
                "sequence_id": meas.sequence_id,
                "time_idx": int(meas.time_idx),
                "measurement_id": meas.measurement_id,
                "regime_id": regime_id,
                "regime_name": regime_name,
                "is_clean_los": bool(str(pt.path_type) == "LoS" and float(og.peak_purity) >= 0.9),
                "is_clean_single_bounce": bool(str(pt.path_type) == "single_bounce" and float(og.peak_purity) >= 0.85),
                "is_los_sb_overlap": bool(og.is_unresolved_los_sb),
                "is_sb_sb_overlap": bool(og.is_unresolved_sb_sb),
                "is_weak_los_strong_reflection": bool(og.contains_los and float(og.power_los_fraction) < 0.5 and og.contains_single_bounce),
                "is_threshold_near": bool(float(og.power_total_db) < -25.0),
                "is_material_controlled": bool(str(og.dominant_material) in {"glass", "metal_pec", "wood"}),
                "is_cp_parity_confident": bool(float(cp.cp_parity_confidence) >= 0.5),
                "is_cp_ambiguous": bool(float(cp.cp_parity_confidence) < 0.2),
                "is_sequential_mismatch": bool(sequential_mismatch),
                "is_high_diffuse_clutter": bool(str(pt.path_type) in {"diffuse", "clutter_truth"} or str(og.dominant_path_type) in {"diffuse", "clutter_truth"}),
                "positive_case_source": "stage01_synthetic_positive_regime_oversampling" if regime_id in {"G2", "G4", "G5", "G6"} else "negative_or_control",
            }
        )
    return pd.DataFrame(rows)


def sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.asarray(x)))


def build_classifier_input_table(mpc: pd.DataFrame, cp_features: pd.DataFrame, rssd_features: pd.DataFrame, regime_labels: pd.DataFrame, assoc: pd.DataFrame, path_truth: pd.DataFrame) -> pd.DataFrame:
    cp_lookup = cp_features.set_index("measurement_id")
    rssd_lookup = rssd_features.set_index("measurement_id")
    regime_lookup = regime_labels.set_index("measurement_id")
    assoc_lookup = assoc.set_index("measurement_id")
    path_lookup = path_truth.set_index("path_truth_id")
    rows = []
    for meas in mpc.itertuples(index=False):
        cp = cp_lookup.loc[meas.measurement_id]
        rssd = rssd_lookup.loc[meas.measurement_id]
        regime = regime_lookup.loc[meas.measurement_id]
        ar = assoc_lookup.loc[meas.measurement_id]
        path = path_lookup.loc[ar.matched_path_truth_id]
        rows.append(
            {
                "sequence_id": meas.sequence_id,
                "time_idx": int(meas.time_idx),
                "measurement_id": meas.measurement_id,
                "feature_vector_id": f"{meas.measurement_id}_fv",
                "cir_feature_1": float(meas.estimated_snr_db),
                "cir_feature_2": float(meas.estimated_width_s),
                "cp_feature_1": float(cp.cp3_core_1),
                "cp_feature_2": float(cp.stokes_s3_fp),
                "rssd_feature_1": float(rssd.rssd_db),
                "label_fp_validity": bool(ar.is_valid_specular and not ar.is_missed_detection),
                "label_path_order": str(path.path_type),
                "label_clean_single_bounce": bool(regime.is_clean_single_bounce),
                "label_material": str(path.surface_material_sequence).split(">")[-1] if isinstance(path.surface_material_sequence, str) and path.surface_material_sequence else "",
                "label_valid_specular": bool(ar.is_valid_specular),
                "train_split_id": "stage01_debug_split",
                "fold_id": int(int(meas.time_idx) % 5),
            }
        )
    return pd.DataFrame(rows)


def build_classifier_prediction_table(mpc: pd.DataFrame, cp_features: pd.DataFrame, assoc: pd.DataFrame, path_truth: pd.DataFrame) -> pd.DataFrame:
    cp_lookup = cp_features.set_index("measurement_id")
    assoc_lookup = assoc.set_index("measurement_id")
    path_lookup = path_truth.set_index("path_truth_id")
    model_specs = [
        ("M_A_ONLY", "CIR-only"),
        ("M_CP_ONLY", "CP-only"),
        ("M_A_CP", "CIR+CP"),
        ("M_A_CP_SHUFFLED", "shuffled-CP"),
    ]
    rows = []
    for meas in mpc.itertuples(index=False):
        cp = cp_lookup.loc[meas.measurement_id]
        ar = assoc_lookup.loc[meas.measurement_id]
        path = path_lookup.loc[ar.matched_path_truth_id]
        amp_score = float(sigmoid((float(meas.estimated_snr_db) - 4.0) / 4.0))
        cp_score = float(cp.cp3_core_1)
        shuffled = float(0.5 + 0.1 * math.sin(int(meas.time_idx) + len(str(meas.measurement_id))))
        for model_id, model_type in model_specs:
            if model_id == "M_A_ONLY":
                valid_prob = amp_score
                cp_used = 0.5
            elif model_id == "M_CP_ONLY":
                valid_prob = cp_score
                cp_used = cp_score
            elif model_id == "M_A_CP":
                valid_prob = float(np.clip(0.55 * amp_score + 0.45 * cp_score, 0.0, 1.0))
                cp_used = cp_score
            else:
                valid_prob = float(np.clip(0.55 * amp_score + 0.45 * shuffled, 0.0, 1.0))
                cp_used = shuffled
            rows.append(
                {
                    "sequence_id": meas.sequence_id,
                    "time_idx": int(meas.time_idx),
                    "measurement_id": meas.measurement_id,
                    "model_id": model_id,
                    "model_type": model_type,
                    "pred_los_prob": float(valid_prob if path.path_type == "LoS" else 1.0 - valid_prob),
                    "pred_single_bounce_prob": float(valid_prob if path.path_type == "single_bounce" else 0.25 * (1.0 - valid_prob)),
                    "pred_multi_bounce_prob": float(valid_prob if path.path_type == "multi_bounce" else 0.25 * (1.0 - valid_prob)),
                    "pred_valid_prob": valid_prob,
                    "pred_clean_prob": float(np.clip(0.4 * valid_prob + 0.6 * float(cp.clean_prob), 0.0, 1.0)),
                    "pred_material": str(path.surface_material_sequence).split(">")[-1] if isinstance(path.surface_material_sequence, str) and path.surface_material_sequence else "",
                    "pred_cp_parity": cp.cp_parity_label if cp_used >= 0.5 else "none",
                    "calibrated_confidence": float(abs(valid_prob - 0.5) * 2.0),
                    "uncertainty_epistemic": float(1.0 - abs(valid_prob - 0.5) * 2.0),
                    "uncertainty_aleatoric": float(1.0 - float(cp.clean_prob)),
                }
            )
    return pd.DataFrame(rows)


def build_threshold_sweep_table(mpc: pd.DataFrame, cp_features: pd.DataFrame, assoc: pd.DataFrame) -> pd.DataFrame:
    thresholds = [-35.0, -30.0, -25.0, -20.0, -15.0, -10.0, -5.0]
    cp_lookup = cp_features.set_index("measurement_id")
    assoc_lookup = assoc.set_index("measurement_id")
    rows = []
    for meas in mpc.itertuples(index=False):
        cp = cp_lookup.loc[meas.measurement_id]
        ar = assoc_lookup.loc[meas.measurement_id]
        amp_score = float(sigmoid((float(meas.estimated_amp_db) + 28.0) / 5.0))
        cp_score = float(cp.cp3_core_1)
        amp_cp_score = float(np.clip(0.55 * amp_score + 0.45 * cp_score, 0.0, 1.0))
        for idx, threshold in enumerate(thresholds):
            detected = float(meas.estimated_amp_db) >= threshold
            amp_accept = amp_score >= 0.5
            cp_accept = amp_cp_score >= 0.5
            valid = bool(ar.is_valid_specular)
            rows.append(
                {
                    "sequence_id": meas.sequence_id,
                    "time_idx": int(meas.time_idx),
                    "measurement_id": meas.measurement_id,
                    "threshold_id": f"TH{idx:02d}",
                    "threshold_db": threshold,
                    "detected_flag": bool(detected),
                    "valid_specular_truth": valid,
                    "false_alarm_truth": bool(detected and not valid),
                    "missed_detection_truth": bool((not detected) and valid),
                    "amplitude_only_score": amp_score,
                    "cp_only_score": cp_score,
                    "amp_cp_score": amp_cp_score,
                    "cp_rescue_flag": bool(valid and cp_accept and not amp_accept),
                    "cp_false_accept_flag": bool((not valid) and cp_accept),
                }
            )
    return pd.DataFrame(rows)


def build_slam_measurement_table(mpc: pd.DataFrame, cp_features: pd.DataFrame, rssd_features: pd.DataFrame, assoc: pd.DataFrame) -> pd.DataFrame:
    cp_lookup = cp_features.set_index("measurement_id")
    rssd_lookup = rssd_features.set_index("measurement_id")
    assoc_lookup = assoc.set_index("measurement_id")
    rows = []
    rssd_passthrough_cols = [
        "tag_antenna_model_mode",
        "rssd_source",
        "legacy_dual_tag_lut_case_id",
        "legacy_dual_tag_lut_source_case_id",
        "legacy_dual_tag_lut_theta_abs_deg",
        "legacy_dual_tag_lut_range_m",
        "legacy_dual_tag_alpha_deg",
        "legacy_dual_tag_rotation_deg",
        "legacy_dual_tag_rssd_channel",
        "legacy_dual_tag_rssd_prediction_mode",
        "legacy_dual_tag_power_offset_mode",
        "tag_ant1_boresight_x",
        "tag_ant1_boresight_y",
        "tag_ant1_boresight_z",
        "tag_ant2_boresight_x",
        "tag_ant2_boresight_y",
        "tag_ant2_boresight_z",
        "tag_ant1_signed_elevation_deg",
        "tag_ant2_signed_elevation_deg",
        "RSS_ant1_RH_db",
        "RSS_ant1_LH_db",
        "RSS_ant2_RH_db",
        "RSS_ant2_LH_db",
        "RSS_ant1_total_db",
        "RSS_ant2_total_db",
        "RSSD_RH_db",
        "RSSD_LH_db",
        "RSSD_total_db",
        "RSSD_mean_pol_db",
        "legacy_dual_tag_power_offset_db",
        "legacy_dual_tag_match_theta_error_deg",
        "legacy_dual_tag_match_range_error_m",
        "legacy_dual_tag_range_est_mean_m",
        "legacy_dual_tag_range_reliable_label",
        "tilted_real_pattern_power_offset_db",
        "tilted_real_pattern_gain_ant1_rh_db",
        "tilted_real_pattern_gain_ant1_lh_db",
        "tilted_real_pattern_gain_ant2_rh_db",
        "tilted_real_pattern_gain_ant2_lh_db",
        "rx_ant1_rhcp_pattern_file",
        "rx_ant1_lhcp_pattern_file",
        "rx_ant2_rhcp_pattern_file",
        "rx_ant2_lhcp_pattern_file",
        "tag_attitude_source",
        "tag_pitch_deg",
        "tag_roll_deg",
        "rx_ant1_mount_rotation",
        "rx_ant2_mount_rotation",
        "rx_ant1_mount_matrix",
        "rx_ant2_mount_matrix",
        "pattern_gain_normalization",
        "pattern_phase_convention",
        "pattern_pol_basis",
        "frequency_hz",
    ]
    mpc_passthrough_cols = [
        "raw_cir_lde_delay_s",
        "raw_cir_lde_range_m",
        "raw_cir_peak_index",
        "raw_cir_lde_index",
        "raw_cir_noise_floor",
        "raw_cir_threshold",
        "raw_cir_peak_power",
        "raw_cir_peak_amplitude_db",
        "raw_cir_channel_set",
        "raw_cir_selected_channel",
        "raw_cir_vector_mode",
        "raw_cir_estimator_status",
        "h10b_channel_vector_order",
        "h10b_range_vector_m",
        "h10b_amplitude_vector_db",
        "h10b_lde_delay_vector_s",
        "h10b_status_vector",
        "h10b_ant1_pol_range_delta_m",
        "h10b_ant2_pol_range_delta_m",
        "h10b_rhcp_ant_range_delta_m",
        "h10b_lhcp_ant_range_delta_m",
        "h10b_cross_pol_range_delta_m",
        *h10b_raw_cir_vector_columns(),
    ]
    for meas in mpc.itertuples(index=False):
        cp = cp_lookup.loc[meas.measurement_id]
        rssd = rssd_lookup.loc[meas.measurement_id]
        ar = assoc_lookup.loc[meas.measurement_id]
        base_range_var = 0.05**2 + float(ar.range_error_m) ** 2 + (0.03 * C0 * float(meas.estimated_width_s)) ** 2
        range_var = base_range_var + 0.35 * (1.0 - float(cp.clean_prob))
        range_estimator_mode = str(getattr(meas, "range_estimator_mode", "peak_group_center"))
        range_source = str(getattr(meas, "estimator_name", "stage01_peak_group_proxy"))
        range_m = float(meas.estimated_range_m)
        h10b_range = float(rssd.get("legacy_dual_tag_range_est_mean_m", float("nan"))) if "legacy_dual_tag_range_est_mean_m" in rssd.index else float("nan")
        if range_estimator_mode.strip().lower() in {"h10b_artifact_lde", "h10b_artifact_range"} and np.isfinite(h10b_range):
            range_m = h10b_range
            range_source = "legacy_h10b_artifact_range_est_mean_m"
        row = {
            "sequence_id": meas.sequence_id,
            "time_idx": int(meas.time_idx),
            "measurement_id": meas.measurement_id,
            "pa_id": "A0",
            "surface_family_id": str(getattr(meas, "surface_family_id", "")),
            "reflection_sequence": str(getattr(meas, "reflection_sequence", "")),
            "order": int(getattr(meas, "order", 0)),
            "bearing_body_deg": float(getattr(meas, "beta_body_deg", float("nan"))),
            "bearing_body_rad": float(getattr(meas, "beta_body_rad", float("nan"))),
            "range_m": range_m,
            "range_var_m2": range_var,
            "range_var_base_m2": base_range_var,
            "range_source": range_source,
            "range_estimator_mode": range_estimator_mode,
            "amplitude_db": float(meas.estimated_amp_db),
            "amplitude_var": max(1.0, 10.0 - float(meas.estimated_snr_db)),
            "rssd_db": float(rssd.rssd_db),
            "rssd_var": 1.0 / max(float(rssd.rssd_confidence), 0.05),
            "cp_reliability": float(cp.cp_reliability),
            "cp_parity_label": cp.cp_parity_label,
            "cp_parity_confidence": float(cp.cp_parity_confidence),
            "path_order_prior": "single_bounce" if cp.cp_parity_label == "odd" else ("multi_or_los" if cp.cp_parity_label == "even" else "unknown"),
            "feature_birth_prior_type": "parity_gated" if float(cp.cp_parity_confidence) >= 0.5 else "ungated",
            "used_by_slam_flag": bool(not ar.is_missed_detection),
        }
        for col in rssd_passthrough_cols:
            if col in rssd.index:
                row[col] = rssd.get(col)
        for col in mpc_passthrough_cols:
            if hasattr(meas, col):
                row[col] = getattr(meas, col)
        rows.append(row)
    return pd.DataFrame(rows)


def build_slam_da_truth_table(assoc: pd.DataFrame, path_truth: pd.DataFrame) -> pd.DataFrame:
    path_lookup = path_truth.set_index("path_truth_id")
    rows = []
    for ar in assoc.itertuples(index=False):
        path = path_lookup.loc[ar.matched_path_truth_id]
        if path.path_type in {"diffuse", "clutter_truth"} or bool(ar.is_false_alarm):
            feature_type = "CLUTTER"
            va_order = -1
            wall_id = ""
            truth_feature_id = "CLUTTER"
        elif path.path_type == "LoS":
            feature_type = "PA"
            va_order = 0
            wall_id = ""
            truth_feature_id = path.feature_id
        else:
            feature_type = "VA"
            va_order = int(path.bounce_order)
            wall_id = last_wall_id(path.reflection_sequence)
            truth_feature_id = path.feature_id
        rows.append(
            {
                "sequence_id": ar.sequence_id,
                "time_idx": int(ar.time_idx),
                "measurement_id": ar.measurement_id,
                "truth_feature_id": truth_feature_id,
                "truth_feature_type": feature_type,
                "truth_va_order": va_order,
                "truth_wall_id": wall_id,
                "truth_is_clutter": bool(feature_type == "CLUTTER"),
                "truth_is_missed": bool(ar.is_missed_detection),
                "truth_overlap_group_id": ar.matched_overlap_group_id,
                "truth_clean_association_possible": bool(ar.is_clean_single_path),
            }
        )
    return pd.DataFrame(rows)


BASELINE_SPECS = [
    ("B0", "Range-only localization known PA only", dict(range=1.0)),
    ("B1", "Known VA map range-only", dict(range=0.9)),
    ("B2", "BP-SLAM range-only", dict(range=0.85)),
    ("B3", "BP-SLAM range plus amplitude", dict(range=0.85, amplitude=1.0)),
    ("B4", "BP-SLAM range plus RSSD raw", dict(range=0.85, rssd=1.0)),
    ("B5", "BP-SLAM range plus CP reliability", dict(range=0.85, cp_reliability=1.0)),
    ("B6", "BP-SLAM range plus amplitude plus CP reliability", dict(range=0.85, amplitude=1.0, cp_reliability=1.0)),
    ("B7", "BP-SLAM range plus amplitude plus CP likelihood", dict(range=0.85, amplitude=1.0, cp_likelihood=1.0)),
    ("B8", "BP-SLAM range plus amplitude plus CP parity", dict(range=0.85, amplitude=1.0, cp_parity=1.0)),
    ("B9", "Full CP-aware", dict(range=0.85, amplitude=1.0, rssd=1.0, cp_reliability=1.0, cp_likelihood=1.0, cp_parity=1.0)),
    ("B10", "CP shuffled negative control", dict(range=0.85, amplitude=1.0, rssd=1.0, cp_reliability=0.2, cp_likelihood=0.2, cp_parity=0.2, shuffled_cp=1.0)),
    ("B11", "Random parity negative control", dict(range=0.85, amplitude=1.0, cp_parity=0.1, random_parity=1.0)),
    ("B12", "Oracle DA", dict(range=1.0, amplitude=1.0, rssd=1.0, cp_reliability=1.0, cp_likelihood=1.0, cp_parity=1.0, oracle_da=1.0)),
    ("B13", "Oracle VA map", dict(range=1.0, amplitude=1.0, rssd=1.0, cp_reliability=1.0, cp_likelihood=1.0, cp_parity=1.0, oracle_va=1.0)),
    ("B14", "Noisy AoA upper bound", dict(range=1.0, amplitude=1.0, angle=1.0)),
    ("B15", "Direct-SLAM style raw CIR", dict(raw_cir=1.0)),
]


EXPERIMENTAL_BASELINE_SPECS = [
    (
        "B16",
        "range_amp_orient_rssd_no_cp_no_guard",
        dict(range=0.85, amplitude=1.0, rssd=1.0),
    ),
    (
        "B20",
        "range_amp_full_cp_no_rssd_no_guard",
        dict(range=0.85, amplitude=1.0, cp_reliability=1.0, cp_likelihood=1.0, cp_parity=1.0),
    ),
    (
        "B21",
        "range_amp_full_cp_shuffled_no_rssd_no_guard",
        dict(range=0.85, amplitude=1.0, cp_reliability=1.0, cp_likelihood=1.0, cp_parity=1.0, shuffled_cp=1.0),
    ),
    (
        "B22",
        "range_amp_random_parity_no_rssd_no_guard",
        dict(range=0.85, amplitude=1.0, cp_parity=1.0, random_parity=1.0),
    ),
    # ── Sub-channel ablation arms (E1/E3/E4 contribution verification) ─────────
    # A_odom_only: pure odometry, no UWB range or amplitude scoring.
    # Establishes the floor for all UWB contribution comparisons.
    (
        "A_odom_only",
        "Odometry only no UWB (floor baseline)",
        dict(),
    ),
    # A_2ch_tiltA: tilt-set A only (indices 0+1).  Tests the marginal benefit of
    # adding the second tilt set (tiltB).
    (
        "A_2ch_tiltA",
        "TiltA 2-channel range only (ablation)",
        dict(range=1.0, range_ch_mask_str="tiltA_only"),
    ),
    # A_2ch_tiltB: tilt-set B only (indices 2+3).
    (
        "A_2ch_tiltB",
        "TiltB 2-channel range only (ablation)",
        dict(range=1.0, range_ch_mask_str="tiltB_only"),
    ),
    # A_1ch_tiltA_lhcp: single channel ablation — removes polarisation and tilt
    # diversity; isolates the benefit of multi-channel architecture.
    (
        "A_1ch_tiltA_lhcp",
        "Single channel tiltA_lhcp range only (ablation)",
        dict(range=1.0, range_ch_mask_str="tiltA_lhcp_only"),
    ),
    # A_4ch_range_amp_ffd: full 4-channel range + FFD amplitude (B7 equivalent).
    # Activates the FFD predictor in the amplitude block when set_h10b_ffd_predictor()
    # has been called.
    (
        "A_4ch_range_amp_ffd",
        "4-channel range + FFD amplitude (B7 physical)",
        dict(range=0.85, amplitude=1.0),
    ),
    # A_2ch_tiltA_amp: tiltA-only range AND amplitude for tilt-diversity test.
    (
        "A_2ch_tiltA_amp",
        "TiltA 2-channel range+amplitude only (ablation)",
        dict(range=0.85, amplitude=1.0, range_ch_mask_str="tiltA_only"),
    ),
    # ── Proximity DOA arms (E1/E3 contribution verification) ─────────────────
    # A_doa_rhcp: tilt_contrast_rhcp_db bearing score only (no range).
    # Isolates the DOA bearing contribution.
    (
        "A_doa_rhcp",
        "Proximity DOA RHCP contrast only (no range)",
        dict(doa_contrast=1.0),
    ),
    # A_range_doa: 4-channel range + proximity DOA bearing.
    # Tests whether DOA supplements range when multi-anchor geometry is weak.
    (
        "A_range_doa",
        "4-channel range + Proximity DOA bearing",
        dict(range=0.85, doa_contrast=0.6),
    ),
    # A_full_b7_doa: Full B7 (range + FFD amplitude) + proximity DOA.
    # Best-effort arm combining all physical measurement modalities.
    (
        "A_full_b7_doa",
        "Full B7 (range + FFD amplitude) + Proximity DOA",
        dict(range=0.85, amplitude=1.0, doa_contrast=0.5),
    ),
    # ── Heading-proxy DOA arms (Path A contribution verification) ─────────────
    # A_hdg_only: heading-prior DOA only (requires non-arbitrary heading policy).
    # Isolates Path A; meaningless for arbitrary heading policy.
    (
        "A_hdg_only",
        "Heading-proxy DOA only (Path A, no RSSD)",
        dict(heading_proxy=1.0),
    ),
    # A_doa_hdg: RSSD contrast + heading prior combined (Path B + Path A).
    # Tests joint scoring when both paths are available.
    (
        "A_doa_hdg",
        "Proximity DOA + heading-proxy combined (Path B + A)",
        dict(doa_contrast=0.6, heading_proxy=0.8),
    ),
    # A_range_doa_hdg: 4-channel range + Path B + Path A.
    # Full DOA contribution with range anchor.
    (
        "A_range_doa_hdg",
        "4-channel range + Proximity DOA + heading-proxy",
        dict(range=0.85, doa_contrast=0.5, heading_proxy=0.6),
    ),
    # A_full_combined: Full B7 + combined DOA (Path A + B).
    # Best-effort arm: all physical modalities + both heading priors.
    (
        "A_full_combined",
        "Full B7 + combined Proximity DOA (Path A+B)",
        dict(range=0.85, amplitude=1.0, doa_contrast=0.4, heading_proxy=0.5),
    ),
]


BASELINE_REGISTRY = [*BASELINE_SPECS, *EXPERIMENTAL_BASELINE_SPECS]


B16_ARM_METADATA = {
    "arm_id": "B16",
    "arm_key": "A1O1R1C0G0",
    "arm_name": "range_amp_orient_rssd_no_cp_no_guard",
    "description": "Range + amplitude + orientation-aware RSSD only; no CP; no positive guard.",
    "orientation_source": "particle_psi_deg",
    "rssd_mode": "orientation_aware_particle_yaw",
    "cp_mode": "off",
    "positive_guard_enabled": False,
    "guard_mode": "off",
    "guard_cap": None,
    "guard_target": None,
}


def baseline_spec_lookup() -> dict[str, tuple[str, str, dict[str, float]]]:
    return {spec[0]: spec for spec in BASELINE_REGISTRY}


def selected_baseline_specs(config: Stage01Config | None = None) -> list[tuple[str, str, dict[str, float]]]:
    requested = tuple(str(item).strip() for item in getattr(config, "algorithm_ids", ()) if str(item).strip())
    if not requested:
        return list(BASELINE_SPECS)

    lookup = baseline_spec_lookup()
    missing = [algorithm_id for algorithm_id in requested if algorithm_id not in lookup]
    if missing:
        raise ValueError(f"unknown algorithm_ids={missing}; available={sorted(lookup)}")
    return [lookup[algorithm_id] for algorithm_id in requested]


def algorithm_quality(weights: dict[str, float], measurement_quality: pd.Series) -> float:
    base = 0.25 + 0.25 * weights.get("range", 0.0)
    base += 0.10 * weights.get("amplitude", 0.0) * float(measurement_quality.get("amp_quality", 0.0))
    base += 0.07 * weights.get("doa_contrast", 0.0) * float(measurement_quality.get("amp_quality", 0.0))
    base += 0.08 * weights.get("rssd", 0.0) * float(measurement_quality.get("rssd_quality", 0.0))
    base += 0.12 * weights.get("cp_reliability", 0.0) * float(measurement_quality.get("cp_reliability", 0.0))
    base += 0.12 * weights.get("cp_likelihood", 0.0) * float(measurement_quality.get("cp_clean", 0.0))
    base += 0.10 * weights.get("cp_parity", 0.0) * float(measurement_quality.get("cp_parity", 0.0))
    base += 0.20 * weights.get("oracle_da", 0.0)
    base += 0.15 * weights.get("oracle_va", 0.0)
    base += 0.10 * weights.get("angle", 0.0)
    if weights.get("shuffled_cp", 0.0) or weights.get("random_parity", 0.0):
        base -= 0.08
    if weights.get("raw_cir", 0.0):
        base = 0.55
    return float(np.clip(base, 0.05, 0.98))


def build_measurement_quality_by_time(
    slam_measurements: pd.DataFrame,
    cp_features: pd.DataFrame,
    rssd_features: pd.DataFrame,
    regime_labels: pd.DataFrame,
) -> pd.DataFrame:
    df = slam_measurements.merge(cp_features[["measurement_id", "clean_prob"]], on="measurement_id", how="left")
    df = df.merge(rssd_features[["measurement_id", "rssd_confidence"]], on="measurement_id", how="left")
    df = df.merge(regime_labels[["measurement_id", "regime_id"]], on="measurement_id", how="left")
    rows = []
    for (sequence_id, time_idx), group in df.groupby(["sequence_id", "time_idx"], sort=True):
        positive = group["regime_id"].isin(["G2", "G4", "G5", "G6"]).mean()
        rows.append(
            {
                "sequence_id": sequence_id,
                "time_idx": int(time_idx),
                "amp_quality": float(sigmoid((group["amplitude_db"].mean() + 30.0) / 5.0)),
                "rssd_quality": float(group["rssd_confidence"].mean()),
                "cp_reliability": float(group["cp_reliability"].mean()),
                "cp_clean": float(group["clean_prob"].mean()),
                "cp_parity": float(group["cp_parity_confidence"].mean()),
                "positive_regime_fraction": float(positive),
                "num_measurements": int(len(group)),
            }
        )
    return pd.DataFrame(rows)


def deterministic_error_vector(sequence_id: str, time_idx: int, algorithm_id: str, error_m: float) -> tuple[float, float, float]:
    phase = (sum(ord(c) for c in sequence_id + algorithm_id) + 17 * int(time_idx)) % 360
    rad = math.radians(phase)
    return error_m * math.cos(rad), error_m * math.sin(rad), 0.1 * error_m * math.sin(0.5 * rad)


def build_slam_result_table(trajectory_truth: pd.DataFrame, quality_by_time: pd.DataFrame) -> pd.DataFrame:
    traj_lookup = trajectory_truth.set_index(["sequence_id", "time_idx"])
    quality_lookup = quality_by_time.set_index(["sequence_id", "time_idx"])
    rows = []
    for key, quality in quality_lookup.iterrows():
        sequence_id, time_idx = key
        truth = traj_lookup.loc[key]
        positive = float(quality.positive_regime_fraction)
    for baseline_id, algorithm, weights in BASELINE_SPECS:
            q = algorithm_quality(weights, quality)
            tail_penalty = 1.0 + 1.2 * positive
            if weights.get("cp_reliability", 0.0) or weights.get("cp_likelihood", 0.0) or weights.get("cp_parity", 0.0):
                tail_penalty -= 0.6 * positive * (0.5 + float(quality.cp_reliability))
            if weights.get("shuffled_cp", 0.0) or weights.get("random_parity", 0.0):
                tail_penalty += 0.4 * positive
            error_m = float(np.clip((1.0 - q) * tail_penalty * (0.7 + 0.05 * quality.num_measurements), 0.02, 5.0))
            dx, dy, dz = deterministic_error_vector(str(sequence_id), int(time_idx), baseline_id, error_m)
            rows.append(
                {
                    "sequence_id": sequence_id,
                    "time_idx": int(time_idx),
                    "algorithm_id": baseline_id,
                    "baseline_id": baseline_id,
                    "estimated_x_m": float(truth.agent_x_m) + dx,
                    "estimated_y_m": float(truth.agent_y_m) + dy,
                    "estimated_z_m": float(truth.agent_z_m) + dz,
                    "estimated_yaw_deg": float(truth.yaw_deg) + 5.0 * (1.0 - q),
                    "position_error_m": error_m,
                    "yaw_error_deg": 5.0 * (1.0 - q),
                    "num_detected_features": int(quality.num_measurements),
                    "num_estimated_va": max(0, int(quality.num_measurements) - 1),
                    "num_particles": 256 if baseline_id.startswith("B") and baseline_id not in {"B0", "B1"} else 0,
                    "bp_iterations": 8 if baseline_id not in {"B0", "B1"} else 0,
                    "runtime_s": float(0.002 * quality.num_measurements * (1.0 + len(weights))),
                    "converged_flag": bool(q > 0.35),
                }
            )
    return pd.DataFrame(rows)


def build_slam_da_result_table(slam_measurements: pd.DataFrame, slam_da_truth: pd.DataFrame, regime_labels: pd.DataFrame) -> pd.DataFrame:
    truth_lookup = slam_da_truth.set_index("measurement_id")
    regime_lookup = regime_labels.set_index("measurement_id")
    candidate_suffix = {"PA": "PA_A0", "VA": "VA_COMPETITOR"}
    rows = []
    for meas in slam_measurements.itertuples(index=False):
        truth = truth_lookup.loc[meas.measurement_id]
        regime = regime_lookup.loc[meas.measurement_id]
        for baseline_id, _, weights in BASELINE_SPECS:
            q = algorithm_quality(
                weights,
                pd.Series(
                    {
                        "amp_quality": float(sigmoid((float(meas.amplitude_db) + 30.0) / 5.0)),
                        "rssd_quality": 0.7,
                        "cp_reliability": float(meas.cp_reliability),
                        "cp_clean": 1.0 / max(float(meas.range_var_m2), 0.05),
                        "cp_parity": float(meas.cp_parity_confidence),
                    }
                ),
            )
            positive = str(regime.regime_id) in {"G2", "G4", "G5", "G6"}
            if positive and (weights.get("cp_likelihood", 0.0) or weights.get("cp_parity", 0.0) or weights.get("cp_reliability", 0.0)):
                q = min(0.98, q + 0.12)
            if weights.get("shuffled_cp", 0.0) or weights.get("random_parity", 0.0):
                q = max(0.05, q - 0.12)
            truth_prob = float(np.clip(q, 0.02, 0.99))
            competitor_id = candidate_suffix.get(str(truth.truth_feature_type), "VA_COMPETITOR")
            for candidate_id, prob, truth_flag in [
                (truth.truth_feature_id, truth_prob, True),
                (competitor_id, 1.0 - truth_prob, False),
            ]:
                rows.append(
                    {
                        "sequence_id": meas.sequence_id,
                        "time_idx": int(meas.time_idx),
                        "algorithm_id": baseline_id,
                        "measurement_id": meas.measurement_id,
                        "candidate_feature_id": candidate_id,
                        "posterior_assoc_prob": prob,
                        "is_map_assignment": bool(prob >= 0.5),
                        "truth_assoc_flag": truth_flag,
                        "da_correct_flag": bool((prob >= 0.5) == truth_flag),
                        "cp_gate_used": bool(weights.get("cp_reliability", 0.0) or weights.get("cp_likelihood", 0.0)),
                        "parity_gate_used": bool(weights.get("cp_parity", 0.0)),
                        "likelihood_range": float(math.exp(-float(meas.range_var_m2))),
                        "likelihood_amp": float(sigmoid((float(meas.amplitude_db) + 30.0) / 5.0)),
                        "likelihood_cp": float(meas.cp_reliability if weights.get("cp_likelihood", 0.0) or weights.get("cp_reliability", 0.0) else 0.5),
                        "likelihood_parity": float(meas.cp_parity_confidence if weights.get("cp_parity", 0.0) else 0.5),
                    }
                )
    return pd.DataFrame(rows)


def build_slam_feature_result_table(slam_da_truth: pd.DataFrame, va_catalog: pd.DataFrame, slam_da_result: pd.DataFrame) -> pd.DataFrame:
    va_lookup = va_catalog.set_index("feature_id")
    truth_lookup = slam_da_truth.set_index("measurement_id")
    output_columns = [
        "sequence_id",
        "time_idx",
        "algorithm_id",
        "estimated_feature_id",
        "matched_truth_feature_id",
        "estimated_x_m",
        "estimated_y_m",
        "estimated_z_m",
        "feature_existence_prob",
        "feature_position_error_m",
        "feature_order_est",
        "feature_order_truth",
        "feature_material_est",
        "feature_material_truth",
    ]
    if "is_map_assignment" not in slam_da_result.columns or "truth_assoc_flag" not in slam_da_result.columns:
        return pd.DataFrame(columns=output_columns)
    rows = []
    top_assign = slam_da_result[slam_da_result["is_map_assignment"]].copy()
    top_assign = top_assign[top_assign["truth_assoc_flag"]]
    for row in top_assign.itertuples(index=False):
        truth = truth_lookup.loc[row.measurement_id]
        if isinstance(truth, pd.DataFrame):
            truth = truth.iloc[0]
        if truth.truth_feature_id not in va_lookup.index:
            continue
        feature = va_lookup.loc[truth.truth_feature_id]
        if isinstance(feature, pd.DataFrame):
            feature = feature.iloc[0]
        error = float((1.0 - row.posterior_assoc_prob) * (1.0 + int(feature.va_order)))
        rows.append(
            {
                "sequence_id": row.sequence_id,
                "time_idx": int(row.time_idx),
                "algorithm_id": row.algorithm_id,
                "estimated_feature_id": f"{row.algorithm_id}_{truth.truth_feature_id}",
                "matched_truth_feature_id": truth.truth_feature_id,
                "estimated_x_m": float(feature.x_m) + 0.2 * error,
                "estimated_y_m": float(feature.y_m) - 0.1 * error,
                "estimated_z_m": float(feature.z_m),
                "feature_existence_prob": float(row.posterior_assoc_prob),
                "feature_position_error_m": error,
                "feature_order_est": int(feature.va_order),
                "feature_order_truth": int(feature.va_order),
                "feature_material_est": "",
                "feature_material_truth": "",
            }
        )
    return pd.DataFrame(rows, columns=output_columns)


def build_metric_by_regime_table(slam_result: pd.DataFrame, slam_da_result: pd.DataFrame, regime_labels: pd.DataFrame, threshold_sweep: pd.DataFrame) -> pd.DataFrame:
    regime_lookup = regime_labels.set_index("measurement_id")
    assign = slam_da_result[slam_da_result["truth_assoc_flag"]].copy()
    if "regime_id" in assign.columns:
        assign = assign.drop(columns=["regime_id"])
    assign = assign.merge(regime_labels[["measurement_id", "regime_id"]], on="measurement_id", how="left")
    pos_err = slam_result.set_index(["sequence_id", "time_idx", "algorithm_id"])["position_error_m"]
    rows = []
    for (algorithm_id, regime_id), group in assign.groupby(["algorithm_id", "regime_id"], sort=True):
        errors = []
        for item in group.itertuples(index=False):
            key = (item.sequence_id, int(item.time_idx), item.algorithm_id)
            if key in pos_err.index:
                errors.append(float(pos_err.loc[key]))
        if not errors:
            continue
        e = np.asarray(errors, dtype=float)
        da_error = 1.0 - float(group["da_correct_flag"].mean())
        valid_measurements = regime_lookup[regime_lookup["regime_id"].eq(regime_id)].index
        th = threshold_sweep[threshold_sweep["measurement_id"].isin(valid_measurements) & threshold_sweep["threshold_db"].eq(-25.0)]
        if len(th):
            precision = float(th["valid_specular_truth"].sum() / max(th["detected_flag"].sum(), 1))
            recall = float((th["detected_flag"] & th["valid_specular_truth"]).sum() / max(th["valid_specular_truth"].sum(), 1))
            fvr = float(th["false_alarm_truth"].sum() / max(th["detected_flag"].sum(), 1))
            missed = float(th["missed_detection_truth"].sum() / max(th["valid_specular_truth"].sum(), 1))
        else:
            precision = recall = fvr = missed = float("nan")
        amp_ref = slam_result[slam_result["algorithm_id"].eq("B3")]["position_error_m"].mean()
        cur_ref = slam_result[slam_result["algorithm_id"].eq(algorithm_id)]["position_error_m"].mean()
        shuffle_ref = slam_result[slam_result["algorithm_id"].eq("B10")]["position_error_m"].mean()
        rows.append(
            {
                "algorithm_id": algorithm_id,
                "baseline_id": algorithm_id,
                "regime_id": regime_id,
                "num_samples": int(len(group)),
                "position_rmse_m": float(np.sqrt(np.mean(e**2))),
                "position_p50_m": float(np.percentile(e, 50)),
                "position_p90_m": float(np.percentile(e, 90)),
                "position_p95_m": float(np.percentile(e, 95)),
                "va_mospa_m": float(0.5 + da_error),
                "da_error_rate": da_error,
                "valid_path_precision": precision,
                "valid_path_recall": recall,
                "false_valid_rate": fvr,
                "missed_valid_rate": missed,
                "ambiguity_resolution_time": float(max(1.0, 5.0 * da_error)),
                "cp_gain_over_amp_only": float(amp_ref - cur_ref),
                "cp_shuffle_delta": float(shuffle_ref - cur_ref),
            }
        )
    return pd.DataFrame(rows)


def build_ablation_table(slam_result: pd.DataFrame, slam_da_result: pd.DataFrame, slam_feature_result: pd.DataFrame) -> pd.DataFrame:
    rows = []
    observed = list(dict.fromkeys(slam_result["algorithm_id"].astype(str))) if len(slam_result) else []
    ordered_ids = [algorithm_id for algorithm_id, _, _ in BASELINE_REGISTRY if algorithm_id in observed]
    ordered_ids.extend(algorithm_id for algorithm_id in observed if algorithm_id not in ordered_ids)
    lookup = baseline_spec_lookup()
    for baseline_id in ordered_ids:
        _, _, weights = lookup.get(baseline_id, (baseline_id, baseline_id, {}))
        sr = slam_result[slam_result["algorithm_id"].eq(baseline_id)]
        da = slam_da_result[slam_da_result["algorithm_id"].eq(baseline_id) & slam_da_result["truth_assoc_flag"]]
        fr = slam_feature_result[slam_feature_result["algorithm_id"].eq(baseline_id)]
        rows.append(
            {
                "algorithm_id": baseline_id,
                "uses_range": bool(weights.get("range", 0.0)),
                "uses_amplitude": bool(weights.get("amplitude", 0.0)),
                "uses_doa_contrast": bool(weights.get("doa_contrast", 0.0)),
                "uses_heading_proxy": bool(weights.get("heading_proxy", 0.0)),
                "uses_rssd": bool(weights.get("rssd", 0.0)),
                "uses_cp_reliability": bool(weights.get("cp_reliability", 0.0)),
                "uses_cp_likelihood": bool(weights.get("cp_likelihood", 0.0)),
                "uses_cp_parity": bool(weights.get("cp_parity", 0.0)),
                "uses_angle_measurement": bool(weights.get("angle", 0.0)),
                "uses_oracle_va": bool(weights.get("oracle_va", 0.0)),
                "uses_oracle_da": bool(weights.get("oracle_da", 0.0)),
                "uses_shuffled_cp": bool(weights.get("shuffled_cp", 0.0)),
                "uses_random_parity": bool(weights.get("random_parity", 0.0)),
                "position_rmse_m": float(np.sqrt(np.mean(sr["position_error_m"].to_numpy(float) ** 2))) if len(sr) else float("nan"),
                "va_mospa_m": float(fr["feature_position_error_m"].mean()) if len(fr) else float("nan"),
                "da_error_rate": float(1.0 - da["da_correct_flag"].mean()) if len(da) else float("nan"),
                "runtime_s": float(sr["runtime_s"].sum()) if len(sr) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def logsumexp(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return -1.0e12
    peak = float(np.max(arr))
    if not np.isfinite(peak):
        return -1.0e12
    return float(peak + math.log(float(np.sum(np.exp(arr - peak)))))


def softmax_from_log(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    total = logsumexp(arr)
    if not np.isfinite(total):
        return np.full(arr.shape, 1.0 / max(arr.size, 1), dtype=float)
    return np.exp(arr - total)


def particle_ess(weights: np.ndarray) -> float:
    arr = np.asarray(weights, dtype=float)
    denom = float(np.sum(np.square(arr)))
    return float(1.0 / max(denom, EPS))


def weight_entropy(weights: np.ndarray) -> float:
    arr = np.asarray(weights, dtype=float)
    arr = arr / max(float(arr.sum()), EPS)
    return float(-np.sum(arr * np.log(np.maximum(arr, EPS))))


def stable_unit_interval(*parts: object) -> float:
    text = "|".join(str(part) for part in parts)
    total = 0
    for idx, char in enumerate(text):
        total = (total + (idx + 1) * ord(char)) % 1000003
    return float(total % 10000) / 10000.0


def sequence_scene_id(sequence_id: str) -> str:
    return str(sequence_id).split("_A0_", 1)[0]


def expected_parity_from_order(order: int) -> str:
    if order <= 0:
        return "none"
    return "odd" if order % 2 else "even"


def build_candidate_catalogs(va_catalog: pd.DataFrame) -> dict[str, pd.DataFrame]:
    catalogs: dict[str, pd.DataFrame] = {}
    for scene_id, group in va_catalog.groupby("scene_id", sort=True):
        cols = [
            "feature_id",
            "feature_type",
            "va_order",
            "reflection_sequence",
            "last_bounce_wall_id",
            "x_m",
            "y_m",
            "z_m",
            "expected_parity",
        ]
        cand = group[cols].copy()
        cand = pd.concat(
            [
                cand,
                pd.DataFrame(
                    [
                        {
                            "feature_id": "CLUTTER",
                            "feature_type": "CLUTTER",
                            "va_order": -1,
                            "reflection_sequence": "",
                            "last_bounce_wall_id": "",
                            "x_m": np.nan,
                            "y_m": np.nan,
                            "z_m": np.nan,
                            "expected_parity": "none",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        catalogs[str(scene_id)] = cand.reset_index(drop=True)
    return catalogs


FORBIDDEN_SOLVER_CANDIDATE_COLUMNS = (
    "truth",
    "gt",
    "ground_truth",
    "oracle",
    "matched_path_truth_id",
    "truth_assoc",
    "is_true_candidate",
    "true_candidate",
    "va_truth",
    "da_truth",
    "truth_candidate_id",
    "va_truth_id",
    "oracle_score",
)


FORBIDDEN_SOLVER_RSSD_COLUMNS = (
    "truth",
    "gt",
    "ground_truth",
    "oracle",
    "path_truth",
    "matched_path_truth_id",
    "is_true_candidate",
    "true_candidate",
    "beta_body_deg_truth",
    "theta_elevation_deg_truth",
)


def _forbidden_solver_columns(columns: pd.Index, markers: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for col in columns:
        low = str(col).lower()
        if any(marker in low for marker in markers):
            out.append(str(col))
    return out


def sanitize_solver_rssd_features(rssd_features: pd.DataFrame, *, strict: bool = False) -> pd.DataFrame:
    """Drop RSSD diagnostic truth columns before solver-facing scoring."""

    forbidden = _forbidden_solver_columns(rssd_features.columns, FORBIDDEN_SOLVER_RSSD_COLUMNS)
    if strict and forbidden:
        raise ValueError(f"rssd_features contains solver-forbidden truth columns: {forbidden}")
    return rssd_features[[col for col in rssd_features.columns if col not in set(forbidden)]].copy()


def sanitize_candidate_catalog_input(candidate_catalog_input: pd.DataFrame, *, strict: bool = False) -> pd.DataFrame:
    forbidden = _forbidden_solver_columns(candidate_catalog_input.columns, FORBIDDEN_SOLVER_CANDIDATE_COLUMNS)
    if strict and forbidden:
        raise ValueError(f"candidate_catalog_input contains solver-forbidden truth columns: {forbidden}")
    return candidate_catalog_input[[col for col in candidate_catalog_input.columns if col not in set(forbidden)]].copy()


def _candidate_catalog_type(value: object) -> str:
    text = str(value).strip().upper()
    if text in {"PA", "ANCHOR"}:
        return "PA"
    if text in {"CLUTTER"}:
        return "CLUTTER"
    return "VA"


def build_candidate_catalogs_from_input(candidate_catalog_input: pd.DataFrame, *, strict: bool = False) -> dict[str, pd.DataFrame]:
    """Convert Step 11/12 external candidate input into the solver catalog shape."""

    candidate_catalog_input = sanitize_candidate_catalog_input(candidate_catalog_input, strict=strict)
    if candidate_catalog_input.empty:
        return {}
    rows: list[dict[str, object]] = []
    for row in candidate_catalog_input.itertuples(index=False):
        as_dict = row._asdict()
        scene_id = str(as_dict.get("scene_id") or sequence_scene_id(str(as_dict.get("sequence_id", ""))))
        if not scene_id:
            continue
        feature_id = str(as_dict.get("feature_id") or as_dict.get("candidate_id") or "")
        if not feature_id:
            continue
        feature_type = _candidate_catalog_type(as_dict.get("feature_type", as_dict.get("candidate_type", "VA_CANDIDATE")))
        if feature_type == "CLUTTER":
            x_m = y_m = z_m = float("nan")
            va_order = -1
        else:
            x_m = float(as_dict.get("x_m", as_dict.get("candidate_state_x", 0.0)))
            y_m = float(as_dict.get("y_m", as_dict.get("candidate_state_y", 0.0)))
            z_m = float(as_dict.get("z_m", as_dict.get("candidate_state_z", 0.0)))
            va_order = int(float(as_dict.get("va_order", 0 if feature_type == "PA" else 1)))
        rows.append(
            {
                "scene_id": scene_id,
                "sequence_id": str(as_dict.get("sequence_id", "")),
                "feature_id": feature_id,
                "feature_type": feature_type,
                "va_order": va_order,
                "reflection_sequence": str(as_dict.get("reflection_sequence", as_dict.get("birth_source", ""))),
                "last_bounce_wall_id": str(as_dict.get("last_bounce_wall_id", "")),
                "x_m": x_m,
                "y_m": y_m,
                "z_m": z_m,
                "expected_parity": str(as_dict.get("expected_parity", "none")),
                "candidate_prior_logprob": float(as_dict.get("candidate_prior_logprob", as_dict.get("prior_logprob", 0.0)) or 0.0),
                "candidate_mode": str(as_dict.get("candidate_mode", as_dict.get("source", "external_candidate_input"))),
                "status": str(as_dict.get("status", "active")),
                "support_count": int(float(as_dict.get("support_count", 1) or 1)),
            }
        )
    catalog_df = pd.DataFrame(rows)
    catalogs: dict[str, pd.DataFrame] = {}
    for scene_id, group in catalog_df.groupby("scene_id", sort=True):
        cand = group.reset_index(drop=True)
        if not cand["feature_type"].astype(str).eq("CLUTTER").any():
            cand = pd.concat(
                [
                    cand,
                    pd.DataFrame(
                        [
                            {
                                "scene_id": scene_id,
                                "sequence_id": "",
                                "feature_id": "CLUTTER",
                                "feature_type": "CLUTTER",
                                "va_order": -1,
                                "reflection_sequence": "",
                                "last_bounce_wall_id": "",
                                "x_m": np.nan,
                                "y_m": np.nan,
                                "z_m": np.nan,
                                "expected_parity": "none",
                                "candidate_prior_logprob": 0.0,
                                "candidate_mode": "external_candidate_input",
                                "status": "active",
                                "support_count": 999,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        catalogs[str(scene_id)] = cand.reset_index(drop=True)
    return catalogs


def sequence_candidate_catalog(catalog: pd.DataFrame, sequence_id: str) -> pd.DataFrame:
    if "sequence_id" not in catalog.columns:
        return catalog
    seq = str(sequence_id)
    seq_col = catalog["sequence_id"].fillna("").astype(str)
    keep = seq_col.eq("") | seq_col.eq(seq) | catalog["feature_type"].astype(str).isin(["PA", "CLUTTER"])
    out = catalog[keep].reset_index(drop=True)
    return out if len(out) else catalog.reset_index(drop=True)


def algorithm_candidate_catalog(catalog: pd.DataFrame, algorithm_id: str) -> pd.DataFrame:
    if algorithm_id == "B0":
        return catalog[catalog["feature_type"].isin(["PA", "CLUTTER"])].reset_index(drop=True)
    if algorithm_id in {"B1", "B13"}:
        return catalog[catalog["feature_type"].isin(["PA", "VA", "CLUTTER"])].reset_index(drop=True)
    return catalog.reset_index(drop=True)


def candidate_subset_for_measurement(
    position: np.ndarray,
    candidates: pd.DataFrame,
    meas: pd.Series,
    cp: pd.Series,
    algorithm_id: str,
    max_candidates: int = 28,
    force_feature_id: str | None = None,
) -> pd.DataFrame:
    """Keep the BP solve tractable by pruning implausible DA candidates per peak."""

    if len(candidates) <= max_candidates:
        return candidates.reset_index(drop=True)

    feature_type = candidates["feature_type"].astype(str).to_numpy()
    is_clutter = feature_type == "CLUTTER"
    valid = ~is_clutter
    score = np.full(len(candidates), -np.inf, dtype=float)
    if np.any(valid):
        pos = candidates.loc[valid, ["x_m", "y_m", "z_m"]].to_numpy(float)
        particle_pos = np.asarray(position, dtype=float).reshape(-1)[:3]
        dist = np.linalg.norm(pos - particle_pos.reshape(1, 3), axis=1)
        _range_channels, h10b_range_obs = h10b_observed_channel_values(meas, "range_m")
        if h10b_range_obs.size:
            residual = np.sqrt(np.mean((h10b_range_obs.reshape(1, -1) - dist.reshape(-1, 1)) ** 2, axis=1))
        else:
            residual = np.abs(float(meas.range_m) - dist)
        parity = parity_match_score(
            candidates.loc[valid, "expected_parity"],
            str(cp.cp_parity_label),
            float(cp.cp_parity_confidence),
        )
        order_penalty = 0.06 * np.maximum(candidates.loc[valid, "va_order"].astype(float).to_numpy(), 0.0)
        score[valid] = -residual + 0.18 * parity - order_penalty

    keep: set[int] = set(candidates.index[candidates["feature_type"].astype(str).isin(["PA", "CLUTTER"])].tolist())
    if force_feature_id:
        keep.update(candidates.index[candidates["feature_id"].astype(str).eq(force_feature_id)].tolist())

    ranked = np.argsort(score)[::-1]
    for idx in ranked:
        if len(keep) >= max_candidates:
            break
        if np.isfinite(score[idx]):
            keep.add(int(idx))

    if algorithm_id in {"B12", "B13"} and force_feature_id:
        keep.update(candidates.index[candidates["feature_id"].astype(str).eq(force_feature_id)].tolist())
    return candidates.loc[sorted(keep)].reset_index(drop=True)


def expected_amplitude_db(distance_m: np.ndarray, order: np.ndarray) -> np.ndarray:
    dist = np.maximum(np.asarray(distance_m, dtype=float), 0.1)
    ord_arr = np.maximum(np.asarray(order, dtype=float), 0.0)
    return -20.0 * np.log10(dist) - 5.0 * ord_arr - 2.0 * (ord_arr > 0.0)


def parity_match_score(expected: pd.Series, observed_label: str, confidence: float) -> np.ndarray:
    exp = expected.astype(str).to_numpy()
    if observed_label not in {"odd", "even", "none"} or confidence <= 0.0:
        return np.zeros(len(exp), dtype=float)
    if observed_label == "none":
        return np.where(exp == "none", 0.4 * confidence, -0.15 * confidence)
    return np.where(exp == observed_label, 1.0 * confidence, -1.2 * confidence)


def _row_get(row: pd.Series, key: str, default: object = None) -> object:
    if row is None:
        return default
    if hasattr(row, "get"):
        return row.get(key, default)
    return getattr(row, key, default)


def _finite_row_float(row: pd.Series, key: str) -> float:
    value = _row_get(row, key, np.nan)
    try:
        if pd.isna(value):
            return float("nan")
    except (TypeError, ValueError):
        pass
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return out if np.isfinite(out) else float("nan")


def h10b_observed_channel_values(meas: pd.Series, field: str) -> tuple[list[str], np.ndarray]:
    channels: list[str] = []
    values: list[float] = []
    for channel in H10B_RAW_CIR_CHANNELS:
        suffix = H10B_RAW_CIR_CHANNEL_SUFFIX[channel]
        value = _finite_row_float(meas, f"h10b_{suffix}_{field}")
        if np.isfinite(value):
            channels.append(channel)
            values.append(value)
    return channels, np.asarray(values, dtype=float)


def h10b_vector_range_log_score(dist_m: np.ndarray, meas: pd.Series, sigma_m: float) -> np.ndarray | None:
    _channels, obs = h10b_observed_channel_values(meas, "range_m")
    if not obs.size:
        return None
    sigma = max(float(sigma_m), 0.04)
    residual = obs.reshape(1, -1) - np.asarray(dist_m, dtype=float).reshape(-1, 1)
    return -0.5 * np.sum((residual / sigma) ** 2, axis=1) - obs.size * math.log(max(sigma, 1e-6))


def h10b_predict_channel_amplitude_db(
    rssd_row: pd.Series,
    theta_elevation_deg: np.ndarray,
    range_m: np.ndarray,
    channels: list[str],
) -> np.ndarray:
    theta_arr = np.asarray(theta_elevation_deg, dtype=float)
    range_arr = np.asarray(range_m, dtype=float)
    pred = np.full((theta_arr.size, len(channels)), np.nan, dtype=float)
    artifact_path = str(_row_get(rssd_row, "legacy_dual_tag_artifact_path", "")).strip()
    if not artifact_path or not channels:
        return pred
    alpha = float(_row_get(rssd_row, "legacy_dual_tag_alpha_deg", 60.0))
    rotation = float(_row_get(rssd_row, "legacy_dual_tag_rotation_deg", 0.0))
    try:
        lut = load_legacy_dual_tag_h10b_lut_from_path(Path(artifact_path), alpha, rotation)
    except (FileNotFoundError, OSError, ValueError):
        return pred
    for idx, (theta_value, range_value) in enumerate(zip(theta_arr, range_arr)):
        if not (np.isfinite(theta_value) and np.isfinite(range_value)):
            continue
        try:
            lut_row = _select_legacy_dual_tag_lut_row(lut, float(theta_value), float(range_value))
        except ValueError:
            continue
        for col_idx, channel in enumerate(channels):
            rss_col = H10B_RAW_CIR_CHANNEL_RSS_COLUMN[channel]
            value = float(_row_get(lut_row, rss_col, np.nan))
            if np.isfinite(value):
                pred[idx, col_idx] = value
    return pred


def h10b_vector_amplitude_log_score(
    dist_m: np.ndarray,
    order: np.ndarray,
    meas: pd.Series,
    rssd: pd.Series,
    theta_elevation_deg: np.ndarray,
) -> np.ndarray | None:
    channels, obs = h10b_observed_channel_values(meas, "amplitude_db")
    if not obs.size:
        return None
    pred = h10b_predict_channel_amplitude_db(rssd, theta_elevation_deg, dist_m, channels)
    if not np.isfinite(pred).any():
        scalar_pred = expected_amplitude_db(dist_m, order)
        pred = np.repeat(scalar_pred.reshape(-1, 1), obs.size, axis=1)
    valid = np.isfinite(pred)
    if not valid.any():
        return None
    residual = obs.reshape(1, -1) - pred
    score = np.sum(np.where(valid, -0.5 * (residual / 7.0) ** 2, 0.0), axis=1)
    score[np.sum(valid, axis=1) == 0] = np.nan
    return score


def neutral_measurement_truth(meas: pd.Series | object | None = None) -> pd.Series:
    measurement_id = str(_row_get(meas, "measurement_id", ""))
    return pd.Series(
        {
            "measurement_id": measurement_id,
            "truth_feature_id": "",
            "truth_feature_type": "",
            "truth_available_for_solver": False,
        }
    )


def rssd_interpretation_yaw_deg(particle_yaw_deg: float, traj: pd.Series) -> float:
    """Return the yaw used only for RSSD interpretation.

    For nominal runs, this is exactly the particle yaw. When a controlled
    trajectory row carries yaw_deg_nominal/yaw_deg, preserve the particle's
    yaw error relative to nominal truth and shift only the RSSD interpretation
    reference to the controlled yaw.
    """

    if _row_get(traj, "yaw_deg_nominal", None) is None:
        return float(particle_yaw_deg)
    nominal_yaw = float(_row_get(traj, "yaw_deg_nominal", _row_get(traj, "yaw_deg", particle_yaw_deg)))
    controlled_yaw = float(_row_get(traj, "yaw_deg", nominal_yaw))
    relative_particle_yaw = wrap_deg(float(particle_yaw_deg) - nominal_yaw)
    return wrap_deg(controlled_yaw + relative_particle_yaw)


RANGE_MIXTURE_FIELDS = (
    "range_mix_w",
    "range_mix_mu_c_m",
    "range_mix_mu_x_m",
    "range_mix_sigma_c_m",
    "range_mix_sigma_x_m",
)


def mixture_range_log_score(
    residual_m: np.ndarray,
    measurement: pd.Series,
) -> np.ndarray | None:
    """Evaluate an optional two-component range-residual likelihood.

    Legacy solver inputs do not carry ``range_mix_*`` fields and therefore
    return ``None`` without changing the historical scalar/vector range path.
    When all fields are present, this preserves the continuous MDN mixture
    instead of collapsing it to a moment-matched Gaussian.
    """

    if any(field not in measurement.index for field in RANGE_MIXTURE_FIELDS):
        return None
    values = np.asarray(
        [measurement.get(field, np.nan) for field in RANGE_MIXTURE_FIELDS],
        dtype=float,
    )
    if not np.isfinite(values).all():
        return None
    weight, mu_c, mu_x, sigma_c, sigma_x = values
    if not 0.0 <= weight <= 1.0 or sigma_c <= 0.0 or sigma_x <= 0.0:
        raise ValueError("invalid range mixture parameters")
    residual = np.asarray(residual_m, dtype=float)
    log_norm = 0.5 * math.log(2.0 * math.pi)
    log_c = (
        math.log(max(weight, EPS))
        - 0.5 * ((residual - mu_c) / sigma_c) ** 2
        - math.log(sigma_c)
        - log_norm
    )
    log_x = (
        math.log(max(1.0 - weight, EPS))
        - 0.5 * ((residual - mu_x) / sigma_x) ** 2
        - math.log(sigma_x)
        - log_norm
    )
    return np.logaddexp(log_c, log_x)


def measurement_candidate_log_score_terms(
    position: np.ndarray,
    candidates: pd.DataFrame,
    meas: pd.Series,
    cp: pd.Series,
    rssd: pd.Series,
    truth: pd.Series | None,
    traj: pd.Series,
    weights: dict[str, float],
    algorithm_id: str,
) -> dict[str, np.ndarray]:
    particle_state = np.asarray(position, dtype=float).reshape(-1)
    particle_pos = particle_state[:3]
    particle_yaw_deg = float(particle_state[3]) if particle_state.size >= 4 else float(traj.yaw_deg)
    feature_ids = candidates["feature_id"].astype(str).to_numpy()
    feature_type = candidates["feature_type"].astype(str).to_numpy()
    order = candidates["va_order"].astype(float).to_numpy()
    is_clutter = feature_type == "CLUTTER"
    pos = candidates[["x_m", "y_m", "z_m"]].to_numpy(float)

    n_candidates = len(candidates)
    base_prior = np.full(n_candidates, -2.0, dtype=float)
    range_term = np.zeros(n_candidates, dtype=float)
    amplitude_term = np.zeros(n_candidates, dtype=float)
    doa_term = np.zeros(n_candidates, dtype=float)
    rssd_term = np.zeros(n_candidates, dtype=float)
    cp_reliability_term = np.zeros(n_candidates, dtype=float)
    cp_likelihood_term = np.zeros(n_candidates, dtype=float)
    cp_parity_term = np.zeros(n_candidates, dtype=float)
    shuffled_cp_term = np.zeros(n_candidates, dtype=float)
    oracle_term = np.zeros(n_candidates, dtype=float)
    raw_cir_term = np.zeros(n_candidates, dtype=float)
    clutter_prior_term = np.full(n_candidates, np.nan, dtype=float)
    total = base_prior.copy()
    valid = ~is_clutter
    if np.any(valid):
        delta = pos[valid] - particle_pos.reshape(1, 3)
        dist = np.linalg.norm(delta, axis=1)
        direction = particle_pos.reshape(1, 3) - pos[valid]
        horizontal = np.linalg.norm(direction[:, :2], axis=1)
        el = np.degrees(np.arctan2(direction[:, 2], np.maximum(horizontal, 1e-9)))
        base_var = float(meas.get("range_var_base_m2", meas.get("range_var_m2", 0.25)))
        cp_var = float(meas.get("range_var_m2", base_var))
        use_cp_variance = bool(weights.get("cp_likelihood", 0.0) or weights.get("cp_reliability", 0.0))
        sigma = math.sqrt(max(cp_var if use_cp_variance else base_var, 0.04**2))
        # Sub-channel mask: allows ablation arms to restrict which H10B channels
        # contribute to the range (and amplitude) log score.  "all" = no masking.
        _ch_mask_key = str(weights.get("range_ch_mask_str", "all"))
        _ch_mask = _CH_MASK_LOOKUP.get(_ch_mask_key, None)

        if weights.get("range", 0.0) or algorithm_id in {"B1", "B13", "B14"}:
            # Physical 4-channel range factor: per-channel phase-centre distances
            # + common-mode covariance.  Falls back to legacy vector / scalar range
            # when per-channel observations are not available.
            obs_vec, range_valid = _h10b_extract_ranges(meas)
            # Apply sub-channel mask for ablation arms
            if _ch_mask is not None:
                range_valid = range_valid & _ch_mask
            phys_range_term = (
                h10b_physical_range_log_score_batch(
                    particle_pos, particle_yaw_deg, pos[valid], obs_vec, range_valid,
                )
                if range_valid.any() else None
            )
            if phys_range_term is not None:
                range_term[valid] = phys_range_term
            else:
                residual = float(meas.range_m) - dist
                mixture_term = mixture_range_log_score(residual, meas)
                if mixture_term is not None:
                    range_term[valid] = mixture_term
                else:
                    vector_range_term = h10b_vector_range_log_score(dist, meas, sigma)
                    if vector_range_term is not None:
                        range_term[valid] = vector_range_term
                    else:
                        range_term[valid] = -0.5 * (residual / sigma) ** 2 - math.log(max(sigma, 1e-6))
            total[valid] += range_term[valid]
        elif weights.get("raw_cir", 0.0):
            vector_range_term = h10b_vector_range_log_score(dist, meas, 0.75)
            if vector_range_term is not None:
                range_term[valid] = vector_range_term
            else:
                residual = float(meas.range_m) - dist
                range_term[valid] = -0.5 * (residual / 0.75) ** 2
            total[valid] += range_term[valid]

        if weights.get("amplitude", 0.0):
            # FFD-based 4-channel amplitude scoring (preferred when predictor is set).
            # Falls back to the legacy proxy scorer when predictor is unavailable.
            obs_amp_vec, amp_valid = _h10b_extract_amplitudes(meas)
            if _ch_mask is not None:
                amp_valid = amp_valid & _ch_mask
            _use_proxy_amp = True  # default to proxy; cleared if FFD succeeds
            if amp_valid.any() and _H10B_FFD_PREDICTOR is not None:
                scalar_amp_pred = expected_amplitude_db(dist, order[valid])
                ffd_amp_term = h10b_ffd_amplitude_log_score_batch(
                    particle_pos[:2], particle_yaw_deg, pos[valid],
                    obs_amp_vec, amp_valid,
                    ffd_predictor=_H10B_FFD_PREDICTOR,
                    scalar_amp_pred_db_arr=scalar_amp_pred,
                    sigma_db=4.0,
                )
                if ffd_amp_term is not None:
                    amplitude_term[valid] = ffd_amp_term
                    total[valid] += amplitude_term[valid]
                    _use_proxy_amp = False  # FFD succeeded; skip proxy
            if _use_proxy_amp:
                # Proxy path: legacy vector amplitude scorer or scalar fallback
                vector_amp_term = h10b_vector_amplitude_log_score(dist, order[valid], meas, rssd, el)
                if vector_amp_term is not None:
                    amplitude_term[valid] = vector_amp_term
                else:
                    amp_pred = expected_amplitude_db(dist, order[valid])
                    amplitude_term[valid] = -0.5 * ((float(meas.amplitude_db) - amp_pred) / 7.0) ** 2
                total[valid] += amplitude_term[valid]

        # ── Proximity DOA: Path B (RSSD/tilt_contrast) + Path A (heading proxy)
        # Path B (doa_contrast weight): tilt_contrast_rhcp LUT log-score.
        # Path A (heading_proxy weight): heading policy prior log-score.
        # Combined mode: uses combined_doa_log_score_batch (joint Path A+B).
        _w_doa  = float(weights.get("doa_contrast", 0.0))
        _w_hdg  = float(weights.get("heading_proxy", 0.0))
        _need_path_b = _w_doa > 0.0 and _H10B_FFD_PREDICTOR is not None
        _need_path_a = _w_hdg > 0.0 and _DOA_CONFIG.heading_policy != "arbitrary"
        if _need_path_b or _need_path_a:
            contrast_obs, contrast_valid = _extract_tilt_contrast_rhcp_db(meas)
            if _need_path_b and _need_path_a and contrast_valid:
                # Combined Path A + Path B via unified config weights
                _cfg_combined = _ProximityDOAConfig(
                    heading_policy       = _DOA_CONFIG.heading_policy,
                    alpha_h_deg          = _DOA_CONFIG.alpha_h_deg,
                    sigma_psi_tag_deg    = _DOA_CONFIG.sigma_psi_tag_deg,
                    sigma_psi_anchor_deg = _DOA_CONFIG.sigma_psi_anchor_deg,
                    sigma_slip_deg       = _DOA_CONFIG.sigma_slip_deg,
                    sigma_contrast_db    = _DOA_CONFIG.sigma_contrast_db,
                    beta_lut_step_deg    = _DOA_CONFIG.beta_lut_step_deg,
                    dist_m_for_lut       = _DOA_CONFIG.dist_m_for_lut,
                    elevation_deg        = _DOA_CONFIG.elevation_deg,
                    weight_rssd          = _w_doa,
                    weight_heading       = _w_hdg,
                )
                _doa_scores = _combined_doa_log_score_batch(
                    particle_pos[:2],
                    particle_yaw_deg,
                    pos[valid],
                    contrast_obs,
                    ffd_predictor=_H10B_FFD_PREDICTOR,
                    config=_cfg_combined,
                )
                if _doa_scores is not None:
                    doa_term[valid] = _doa_scores
                    total[valid] += doa_term[valid]
            elif _need_path_b and contrast_valid:
                # Path B only (RSSD/tilt_contrast)
                _doa_scores = _rssd_doa_log_score_batch(
                    particle_pos[:2],
                    particle_yaw_deg,
                    pos[valid],
                    contrast_obs,
                    ffd_predictor=_H10B_FFD_PREDICTOR,
                    config=_DOA_CONFIG,
                )
                if _doa_scores is not None:
                    doa_term[valid] = _w_doa * _doa_scores
                    total[valid] += doa_term[valid]
            elif _need_path_a:
                # Path A only (heading proxy prior)
                _pol_entry = _HEADING_POLICIES.get(
                    _DOA_CONFIG.heading_policy,
                    _HEADING_POLICIES["arbitrary"],
                )
                _alpha_h = float(_pol_entry[0])
                _sigma_h = float(_sigma_heading_doa(_DOA_CONFIG))
                _hdg_scores = _heading_proxy_log_score_batch(
                    particle_pos[:2],
                    particle_yaw_deg,
                    pos[valid],
                    _alpha_h,
                    _sigma_h,
                )
                if _hdg_scores is not None:
                    doa_term[valid] = _w_hdg * _hdg_scores
                    total[valid] += doa_term[valid]

        rssd_control_mode = str(_row_get(rssd, "rssd_control_mode", "nominal"))
        rssd_score_active = rssd_control_mode != "zero"
        if rssd_score_active and (weights.get("rssd", 0.0) or weights.get("angle", 0.0)):
            yaw = rssd_interpretation_yaw_deg(particle_yaw_deg, traj)
            az = np.degrees(np.arctan2(direction[:, 1], direction[:, 0]))
            beta_deg = (az - yaw + 180.0) % 360.0 - 180.0
            beta = np.radians(beta_deg)
            synthetic_pred = 8.0 * np.sin(beta) * np.cos(np.radians(el))
            tag_model = str(_row_get(rssd, "tag_antenna_model_mode", "synthetic_proxy"))
            prediction_mode = normalize_legacy_dual_tag_rssd_prediction_mode(
                str(_row_get(rssd, "legacy_dual_tag_rssd_prediction_mode", "synthetic_proxy")),
                tag_model,
            )
            pred = synthetic_pred
            normalized_tag_model = normalize_tag_antenna_model_mode(tag_model)
            if normalized_tag_model == "legacy_h10b_dual_tilted" and prediction_mode == "artifact_lut":
                artifact_pred = legacy_dual_tag_h10b_predict_rssd_db(rssd, el, dist)
                pred = np.where(np.isfinite(artifact_pred), artifact_pred, synthetic_pred)
            elif normalized_tag_model == "tilted_real_pattern" and prediction_mode == "tilted_real_pattern":
                gains = tilted_real_pattern_channel_gains_db(beta_deg, el, rssd)
                ant1_rh = np.asarray(gains["RSS_ant1_RH_db"], dtype=float)
                ant1_lh = np.asarray(gains["RSS_ant1_LH_db"], dtype=float)
                ant2_rh = np.asarray(gains["RSS_ant2_RH_db"], dtype=float)
                ant2_lh = np.asarray(gains["RSS_ant2_LH_db"], dtype=float)
                ant1_total = _db_sum_arrays([ant1_rh, ant1_lh])
                ant2_total = _db_sum_arrays([ant2_rh, ant2_lh])
                tilted_values = {
                    "total": ant1_total - ant2_total,
                    "rh": ant1_rh - ant2_rh,
                    "lh": ant1_lh - ant2_lh,
                    "mean_pol": 0.5 * ((ant1_rh - ant2_rh) + (ant1_lh - ant2_lh)),
                }
                channel = normalize_legacy_dual_tag_rssd_channel(str(_row_get(rssd, "legacy_dual_tag_rssd_channel", "total")))
                tilted_pred = tilted_values[channel]
                pred = np.where(np.isfinite(tilted_pred), tilted_pred, synthetic_pred)
            rssd_term[valid] = -0.5 * ((float(rssd.rssd_db) - pred) / 4.0) ** 2
            total[valid] += rssd_term[valid]

    cp_rel = float(cp.cp_reliability)
    cp_clean = float(cp.clean_prob)
    cp_conf = float(cp.cp_parity_confidence)
    observed_parity = str(cp.cp_parity_label)
    if weights.get("shuffled_cp", 0.0):
        cp_rel = 0.35 + 0.3 * stable_unit_interval(meas.measurement_id, "shuffled_rel")
        cp_clean = 0.45 + 0.2 * stable_unit_interval(meas.measurement_id, "shuffled_clean")
        cp_conf = 0.15 + 0.2 * stable_unit_interval(meas.measurement_id, "shuffled_conf")
    if weights.get("random_parity", 0.0):
        observed_parity = "odd" if stable_unit_interval(meas.measurement_id, "random_parity") > 0.5 else "even"
        cp_conf = 0.45

    if weights.get("cp_reliability", 0.0):
        cp_reliability_term += float(weights.get("cp_reliability", 0.0)) * (0.9 * (cp_rel - 0.5) + 0.4 * (cp_clean - 0.5))
        cp_reliability_term[is_clutter] += 1.2 * (1.0 - cp_rel)
        total += cp_reliability_term

    if weights.get("cp_likelihood", 0.0):
        los_prob = float(meas.get("pred_los_prob", 0.34))
        sb_prob = float(meas.get("pred_single_bounce_prob", 0.33))
        mb_prob = float(meas.get("pred_multi_bounce_prob", 0.33))
        class_prob = np.where(order <= 0.0, los_prob, np.where(order == 1.0, sb_prob, mb_prob))
        cp_likelihood_term += float(weights.get("cp_likelihood", 0.0)) * np.log(np.maximum(class_prob, 1e-4))
        cp_likelihood_term += float(weights.get("cp_likelihood", 0.0)) * parity_match_score(candidates["expected_parity"], observed_parity, cp_conf)
        cp_likelihood_term += 0.45 * float(weights.get("cp_likelihood", 0.0)) * (cp_clean - 0.5)
        cp_likelihood_term[is_clutter] += 1.0 * (1.0 - cp_clean)
        total += cp_likelihood_term

    if weights.get("cp_parity", 0.0):
        gate = parity_match_score(candidates["expected_parity"], observed_parity, cp_conf)
        cp_parity_term += 1.5 * float(weights.get("cp_parity", 0.0)) * gate
        total += cp_parity_term

    if weights.get("shuffled_cp", 0.0):
        shuffled_bias = np.asarray(
            [stable_unit_interval(meas.measurement_id, feature_id, "shuffled_cp_bias") - 0.5 for feature_id in feature_ids],
            dtype=float,
        )
        shuffled_cp_term += 2.0 * float(weights.get("shuffled_cp", 0.0)) * shuffled_bias
        shuffled_cp_term[~is_clutter] -= 1.55 * float(weights.get("shuffled_cp", 0.0))
        total += shuffled_cp_term

    truth_id = str(_row_get(truth, "truth_feature_id", ""))
    truth_feature_type = str(_row_get(truth, "truth_feature_type", ""))
    if weights.get("oracle_da", 0.0) and truth_id:
        oracle_term += np.where(feature_ids == truth_id, 10.0, -10.0)
        total += oracle_term

    if weights.get("oracle_va", 0.0):
        oracle_term[feature_type == "VA"] += 0.3
        total[feature_type == "VA"] += 0.3

    if weights.get("raw_cir", 0.0):
        raw_cir_term += 0.25 * (float(cp.late_leakage) - 0.5)
        total += raw_cir_term

    amp_valid = float(sigmoid((float(meas.amplitude_db) + 28.0) / 5.0))
    clutter_prior = -3.2 + 1.4 * (1.0 - cp_clean) + 0.8 * (1.0 - amp_valid)
    clutter_prior_term[is_clutter] = clutter_prior
    total[is_clutter] = clutter_prior
    if truth_feature_type == "CLUTTER" and weights.get("oracle_da", 0.0):
        oracle_term[is_clutter] += 12.0
        total[is_clutter] += 12.0
    return {
        "base_prior_log_score": base_prior,
        "range_log_score": range_term,
        "amplitude_log_score": amplitude_term,
        "doa_log_score": doa_term,
        "rssd_log_score": rssd_term,
        "cp_reliability_log_score": cp_reliability_term,
        "cp_likelihood_log_score": cp_likelihood_term,
        "cp_parity_log_score": cp_parity_term,
        "shuffled_cp_log_score": shuffled_cp_term,
        "oracle_log_score": oracle_term,
        "raw_cir_log_score": raw_cir_term,
        "clutter_prior_log_score": clutter_prior_term,
        "total_log_score": np.clip(total, -80.0, 80.0),
    }


def measurement_candidate_log_scores(
    position: np.ndarray,
    candidates: pd.DataFrame,
    meas: pd.Series,
    cp: pd.Series,
    rssd: pd.Series,
    truth: pd.Series,
    traj: pd.Series,
    weights: dict[str, float],
    algorithm_id: str,
) -> np.ndarray:
    return measurement_candidate_log_score_terms(
        position,
        candidates,
        meas,
        cp,
        rssd,
        truth,
        traj,
        weights,
        algorithm_id,
    )["total_log_score"]


def make_particle_grid(center: np.ndarray, spec: pd.Series, scale_m: float) -> np.ndarray:
    offsets = np.array([-0.75, 0.0, 0.75], dtype=float) * float(scale_m)
    pts = []
    for ox in offsets:
        for oy in offsets:
            pts.append([center[0] + ox, center[1] + oy, center[2]])
    arr = np.asarray(pts, dtype=float)
    arr[:, 0] = np.clip(arr[:, 0], 0.15, float(spec.L_m) - 0.15)
    arr[:, 1] = np.clip(arr[:, 1], 0.15, float(spec.W_m) - 0.15)
    arr[:, 2] = np.clip(arr[:, 2], 0.5, float(spec.H_m) - 0.2)
    return arr


def candidate_posteriors_for_measurement(
    position: np.ndarray,
    candidates: pd.DataFrame,
    meas: pd.Series,
    cp: pd.Series,
    rssd: pd.Series,
    truth: pd.Series,
    traj: pd.Series,
    weights: dict[str, float],
    algorithm_id: str,
) -> tuple[pd.DataFrame, float]:
    scores = measurement_candidate_log_scores(position, candidates, meas, cp, rssd, truth, traj, weights, algorithm_id)
    probs = softmax_from_log(scores)
    entropy = float(-np.sum(probs * np.log(np.maximum(probs, EPS))))
    candidate_rows = candidates.copy()
    candidate_rows["posterior_assoc_prob"] = probs
    return candidate_rows, entropy


def folded_seed(seed: int, *parts: object) -> int:
    folded = int(seed)
    for part in parts:
        text = str(part)
        for idx, char in enumerate(text):
            folded = (folded * 1664525 + (idx + 1) * ord(char) + 1013904223) % (2**32)
    return folded


def solver_rng(seed: int, *parts: object) -> np.random.Generator:
    folded = folded_seed(seed, *parts)
    return np.random.default_rng(folded)


FORBIDDEN_ODOMETRY_INPUT_COLUMNS = (
    "truth",
    "posterior",
    "slam_result",
    "agent_x_m",
    "agent_y_m",
    "v_mps",
    "omega_z_radps",
)
ODOMETRY_PROVENANCE_COLUMNS = {"source", "producer", "truth_exact", "allowed_for_solver"}
ALLOWED_SOLVER_ODOMETRY_SOURCES = {
    "raw_wheel_preintegration",
    "raw_imu_preintegration",
    "synthetic_noisy_odometry_sensor",
    "odometry_sensor_fixture",
}
FORBIDDEN_SOLVER_ODOMETRY_SOURCES = {
    "legacy_trajectory_truth",
    "simulated_odometry_preintegration",
    "trajectory_truth_derived",
}


def build_solver_initial_pose_prior_table(trajectory: pd.DataFrame) -> pd.DataFrame:
    """Build an explicit known-initial-pose prior table for the solver API."""

    required = {"sequence_id", "time_idx", "time_s", "agent_x_m", "agent_y_m", "agent_z_m", "yaw_deg"}
    missing = sorted(required - set(trajectory.columns))
    if missing:
        raise ValueError(f"trajectory table missing initial-prior fields: {missing}")
    rows = []
    for sequence_id, group in trajectory.groupby("sequence_id", sort=True):
        first = group.sort_values("time_idx").iloc[0]
        rows.append(
            {
                "sequence_id": sequence_id,
                "time_idx": int(first.time_idx),
                "time_s": float(first.time_s),
                "x_m": float(first.agent_x_m),
                "y_m": float(first.agent_y_m),
                "z_m": float(first.agent_z_m),
                "yaw_deg": float(first.yaw_deg),
                "sigma_xy_m": 0.35,
                "sigma_z_m": 0.04,
                "sigma_yaw_deg": 8.0,
                "source": "known_initial_pose_prior",
            }
        )
    return pd.DataFrame(rows)


def _trajectory_delta_rows(trajectory: pd.DataFrame) -> list[dict[str, object]]:
    """Return exact body-frame trajectory deltas for simulator-side sensor models."""

    required = {"sequence_id", "time_idx", "time_s", "agent_x_m", "agent_y_m", "agent_z_m", "yaw_deg"}
    missing = sorted(required - set(trajectory.columns))
    if missing:
        raise ValueError(f"trajectory table missing odometry-generation fields: {missing}")
    rows = []
    for sequence_id, group in trajectory.groupby("sequence_id", sort=True):
        ordered = group.sort_values("time_idx").reset_index(drop=True)
        for idx, row in ordered.iterrows():
            if idx == 0:
                rows.append(
                    {
                        "sequence_id": sequence_id,
                        "time_idx": int(row.time_idx),
                        "time_s": float(row.time_s),
                        "dt_s": 0.0,
                        "dx_body_m": 0.0,
                        "dy_body_m": 0.0,
                        "dz_m": 0.0,
                        "dyaw_deg": 0.0,
                        "sigma_xy_m": 0.10,
                        "sigma_z_m": 0.015,
                        "sigma_yaw_deg": 2.0,
                    }
                )
                continue
            prev = ordered.iloc[idx - 1]
            dt = max(float(row.time_s) - float(prev.time_s), 1e-6)
            dx_world = float(row.agent_x_m) - float(prev.agent_x_m)
            dy_world = float(row.agent_y_m) - float(prev.agent_y_m)
            prev_yaw = math.radians(float(prev.yaw_deg))
            c = math.cos(prev_yaw)
            s = math.sin(prev_yaw)
            rows.append(
                {
                    "sequence_id": sequence_id,
                    "time_idx": int(row.time_idx),
                    "time_s": float(row.time_s),
                    "dt_s": dt,
                    "dx_body_m": c * dx_world + s * dy_world,
                    "dy_body_m": -s * dx_world + c * dy_world,
                    "dz_m": float(row.agent_z_m) - float(prev.agent_z_m),
                    "dyaw_deg": wrap_deg(float(row.yaw_deg) - float(prev.yaw_deg)),
                    "sigma_xy_m": 0.10,
                    "sigma_z_m": 0.015,
                    "sigma_yaw_deg": 2.0,
                }
            )
    return rows


def build_truth_derived_solver_odometry_fixture(trajectory: pd.DataFrame) -> pd.DataFrame:
    """Build exact trajectory deltas for non-strict tests and migration audits only."""

    rows = []
    for row in _trajectory_delta_rows(trajectory):
        row = dict(row)
        row.update(
            {
                "source": "trajectory_truth_derived",
                "producer": "trajectory_delta_fixture",
                "truth_exact": True,
                "allowed_for_solver": False,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def build_solver_odometry_input_table(
    trajectory: pd.DataFrame,
    *,
    random_seed: int = 20260514,
    noise_scale: float = 1.0,
) -> pd.DataFrame:
    """Build a solver-facing synthetic odometry sensor table.

    The simulator uses trajectory truth only to synthesize a noisy odometry
    observation. Strict solver paths validate the provenance fields below and
    reject exact truth-delta fixtures even when their numeric columns match.
    """

    rng = np.random.default_rng(int(random_seed) + 1701)
    rows = []
    scale = max(0.0, float(noise_scale))
    sensor_is_noisy = scale > 0.0
    for row in _trajectory_delta_rows(trajectory):
        row = dict(row)
        dt = float(row["dt_s"])
        if dt > 0.0 and scale > 0.0:
            sigma_xy = float(row["sigma_xy_m"]) * scale
            sigma_z = float(row["sigma_z_m"]) * scale
            sigma_yaw = float(row["sigma_yaw_deg"]) * scale
            row["dx_body_m"] = float(row["dx_body_m"]) + float(rng.normal(0.0, sigma_xy))
            row["dy_body_m"] = float(row["dy_body_m"]) + float(rng.normal(0.0, sigma_xy))
            row["dz_m"] = float(row["dz_m"]) + float(rng.normal(0.0, sigma_z))
            row["dyaw_deg"] = wrap_deg(float(row["dyaw_deg"]) + float(rng.normal(0.0, sigma_yaw)))
        row.update(
            {
                "source": "synthetic_noisy_odometry_sensor",
                "producer": "stage01_synthetic_odometry_sensor",
                "truth_exact": not sensor_is_noisy,
                "allowed_for_solver": sensor_is_noisy,
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _coerce_bool(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, float)) and not pd.isna(value):
        return bool(int(value))
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"cannot parse boolean provenance value: {value!r}")


def _validate_solver_odometry_table(odometry_table: pd.DataFrame, *, strict: bool = False) -> None:
    required = {"sequence_id", "time_idx", "dt_s", "dx_body_m", "dy_body_m", "dz_m", "dyaw_deg"}
    missing = sorted(required - set(odometry_table.columns))
    if missing:
        raise ValueError(f"odometry_table missing solver motion fields: {missing}")
    forbidden = [
        str(col)
        for col in odometry_table.columns
        if str(col) not in ODOMETRY_PROVENANCE_COLUMNS
        and any(marker in str(col).lower() for marker in FORBIDDEN_ODOMETRY_INPUT_COLUMNS)
    ]
    if forbidden:
        raise ValueError(f"odometry_table contains forbidden trajectory-derived columns: {forbidden}")
    if not strict:
        return

    if odometry_table.empty:
        raise ValueError("strict odometry_table must not be empty")
    required_provenance = ODOMETRY_PROVENANCE_COLUMNS - {"truth_exact"}
    missing_provenance = sorted(required_provenance - set(odometry_table.columns))
    if missing_provenance:
        raise ValueError(f"strict odometry_table missing provenance fields: {missing_provenance}")
    sources = {str(src).strip() for src in odometry_table["source"].dropna().unique()}
    forbidden_sources = sorted(sources & FORBIDDEN_SOLVER_ODOMETRY_SOURCES)
    if forbidden_sources:
        raise ValueError(f"odometry_table contains forbidden provenance sources: {forbidden_sources}")
    disallowed_sources = sorted(sources - ALLOWED_SOLVER_ODOMETRY_SOURCES)
    if disallowed_sources:
        raise ValueError(f"odometry_table contains disallowed provenance sources: {disallowed_sources}")
    if "truth_exact" in odometry_table.columns:
        truth_exact = odometry_table["truth_exact"].map(_coerce_bool)
        if bool(truth_exact.any()):
            raise ValueError("odometry_table provenance marks exact truth motion")
    allowed_for_solver = odometry_table["allowed_for_solver"].map(_coerce_bool)
    if not bool(allowed_for_solver.all()):
        raise ValueError("odometry_table provenance contains rows not allowed for solver")


def _solver_lookup(table: pd.DataFrame | None) -> dict[tuple[str, int], pd.Series]:
    if table is None or table.empty:
        return {}
    return {
        (str(row.sequence_id), int(row.time_idx)): pd.Series(row._asdict())
        for row in table.itertuples(index=False)
    }


def _sequence_lookup(table: pd.DataFrame | None) -> dict[str, pd.Series]:
    if table is None or table.empty:
        return {}
    return {
        str(row.sequence_id): pd.Series(row._asdict())
        for row in table.itertuples(index=False)
    }


def clip_particles_to_scene(particles: np.ndarray, spec: pd.Series) -> np.ndarray:
    out = np.asarray(particles, dtype=float).copy()
    out[:, 0] = np.clip(out[:, 0], 0.15, float(spec.L_m) - 0.15)
    out[:, 1] = np.clip(out[:, 1], 0.15, float(spec.W_m) - 0.15)
    out[:, 2] = np.clip(out[:, 2], 0.5, float(spec.H_m) - 0.2)
    if out.shape[1] >= 4:
        out[:, 3] = (out[:, 3] + 180.0) % 360.0 - 180.0
    return out


def systematic_resample(weights: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    n = int(len(weights))
    if n <= 0:
        return np.asarray([], dtype=int)
    positions = (float(rng.random()) + np.arange(n, dtype=float)) / float(n)
    cumulative = np.cumsum(np.asarray(weights, dtype=float))
    cumulative[-1] = 1.0
    return np.searchsorted(cumulative, positions, side="left")


def initialize_particles(
    prior: pd.Series,
    scene_spec: pd.Series,
    num_particles: int,
    rng: np.random.Generator,
    algorithm_id: str,
) -> np.ndarray:
    # Stage 4.5 bridge assumes a known initial pose with uncertainty, as in
    # many SLAM evaluations. The prior is passed explicitly so the solver does
    # not need absolute trajectory state for initialization.
    center = np.array(
        [
            float(prior.get("x_m", prior.get("agent_x_m"))),
            float(prior.get("y_m", prior.get("agent_y_m"))),
            float(prior.get("z_m", prior.get("agent_z_m", 1.0))),
        ],
        dtype=float,
    )
    sigma_xy = float(prior.get("sigma_xy_m", 0.45 if algorithm_id in {"B0", "B2", "B10", "B11", "B15"} else 0.30))
    if algorithm_id in {"B12", "B13"}:
        sigma_xy = min(sigma_xy, 0.18)
    noise = rng.normal(0.0, sigma_xy, size=(int(num_particles), 4))
    noise[:, 2] = rng.normal(0.0, float(prior.get("sigma_z_m", 0.04)), size=int(num_particles))
    noise[:, 3] = rng.normal(0.0, float(prior.get("sigma_yaw_deg", 8.0)), size=int(num_particles))
    state = np.array([center[0], center[1], center[2], float(prior.get("yaw_deg", 0.0))], dtype=float)
    return clip_particles_to_scene(state.reshape(1, 4) + noise, scene_spec)


def predict_particles(
    particles: np.ndarray,
    prev_traj: pd.Series | None,
    traj: pd.Series,
    scene_spec: pd.Series,
    rng: np.random.Generator,
    algorithm_id: str,
    noise_scale: float = 1.0,
) -> np.ndarray:
    if prev_traj is None:
        return clip_particles_to_scene(particles, scene_spec)
    dt = float(traj.time_s) - float(prev_traj.time_s)
    dt = max(dt, 1e-6)
    yaw_rad = np.deg2rad(particles[:, 3])
    delta_xy = float(traj.v_mps) * dt * np.column_stack([np.cos(yaw_rad), np.sin(yaw_rad)])
    delta_z = np.full((len(particles), 1), float(traj.agent_z_m) - float(prev_traj.agent_z_m))
    delta_yaw = np.full((len(particles), 1), math.degrees(float(traj.omega_z_radps) * dt))
    delta = np.hstack([delta_xy, delta_z, delta_yaw])
    sigma_xy = 0.10 if algorithm_id not in {"B0", "B10", "B11", "B15"} else 0.16
    if algorithm_id in {"B12", "B13"}:
        sigma_xy = 0.06
    scale = max(0.0, float(noise_scale))
    process = rng.normal(0.0, sigma_xy, size=particles.shape)
    process[:, :2] *= scale
    process[:, 2] = rng.normal(0.0, 0.015 * scale, size=len(particles))
    process[:, 3] = rng.normal(0.0, 2.0 * scale, size=len(particles))
    return clip_particles_to_scene(particles + delta + process, scene_spec)


def predict_particles_from_odometry(
    particles: np.ndarray,
    odom: pd.Series,
    scene_spec: pd.Series,
    rng: np.random.Generator,
    algorithm_id: str,
    noise_scale: float = 1.0,
) -> np.ndarray:
    """Propagate particles from a solver-facing relative odometry row."""

    yaw_rad = np.deg2rad(particles[:, 3])
    c = np.cos(yaw_rad)
    s = np.sin(yaw_rad)
    dx_body = float(odom.dx_body_m)
    dy_body = float(odom.dy_body_m)
    delta_xy = np.column_stack(
        [
            c * dx_body - s * dy_body,
            s * dx_body + c * dy_body,
        ]
    )
    delta_z = np.full((len(particles), 1), float(odom.get("dz_m", 0.0)))
    delta_yaw = np.full((len(particles), 1), float(odom.dyaw_deg))
    delta = np.hstack([delta_xy, delta_z, delta_yaw])
    scale = max(0.0, float(noise_scale))
    sigma_xy = float(odom.get("sigma_xy_m", 0.10))
    sigma_z = float(odom.get("sigma_z_m", 0.015))
    sigma_yaw = float(odom.get("sigma_yaw_deg", 2.0))
    if algorithm_id in {"B12", "B13"}:
        sigma_xy = min(sigma_xy, 0.06)
    process = rng.normal(0.0, sigma_xy, size=particles.shape)
    process[:, :2] *= scale
    process[:, 2] = rng.normal(0.0, sigma_z * scale, size=len(particles))
    process[:, 3] = rng.normal(0.0, sigma_yaw * scale, size=len(particles))
    return clip_particles_to_scene(particles + delta + process, scene_spec)


def log_marginal_measurement_scores(
    particles: np.ndarray,
    local_candidates: pd.DataFrame,
    meas: pd.Series,
    cp: pd.Series,
    rssd: pd.Series,
    truth: pd.Series,
    traj: pd.Series,
    weights: dict[str, float],
    algorithm_id: str,
) -> np.ndarray:
    values = []
    for particle in particles:
        scores = measurement_candidate_log_scores(
            particle,
            local_candidates,
            meas,
            cp,
            rssd,
            truth,
            traj,
            weights,
            algorithm_id,
        )
        values.append(logsumexp(scores))
    return np.asarray(values, dtype=float)


def _config_algorithm_ids(value: str) -> set[str]:
    return {part.strip() for part in str(value).split(",") if part.strip()}


def should_regularize_measurement_marginal(
    config: Stage01Config,
    algorithm_id: str,
    regime_id: str,
    marginal: np.ndarray,
) -> bool:
    target = str(config.measurement_regularizer_target).strip().lower()
    cap = float(config.measurement_regularizer_centered_cap)
    if target in {"", "none", "off", "disabled"} or cap <= 0.0:
        return False
    if str(algorithm_id) == "B16":
        return False
    algorithm_ids = _config_algorithm_ids(config.measurement_regularizer_algorithms)
    if algorithm_ids and str(algorithm_id) not in algorithm_ids:
        return False
    marginal_arr = np.asarray(marginal, dtype=float)
    if not len(marginal_arr):
        return False
    is_g7 = str(regime_id) == "G7"
    is_positive = str(regime_id) in {"G2", "G3", "G4", "G5", "G6"}
    is_spread = float(np.std(marginal_arr)) >= float(config.measurement_regularizer_spread_threshold)
    if target == "all":
        return True
    if target == "positive":
        return is_positive
    if target == "g7":
        return is_g7
    if target == "spread":
        return is_spread
    if target in {"g7_or_spread", "g7+spread", "g7_spread"}:
        return is_g7 or is_spread
    if target in {"g7_or_spread_or_positive", "g7_spread_positive", "positive_tail"}:
        return is_g7 or is_spread or is_positive
    raise ValueError(
        "unknown measurement_regularizer_target="
        f"{config.measurement_regularizer_target!r}; expected none, all, positive, g7, spread, "
        "g7_or_spread, or g7_or_spread_or_positive"
    )


def apply_centered_measurement_cap(
    marginal: np.ndarray,
    weights_before: np.ndarray,
    cap: float,
) -> np.ndarray:
    marginal_arr = np.asarray(marginal, dtype=float)
    weights_arr = np.asarray(weights_before, dtype=float)
    weights_arr = weights_arr / max(float(weights_arr.sum()), EPS)
    center = float(np.sum(weights_arr * marginal_arr))
    return center + np.clip(marginal_arr - center, -float(cap), float(cap))


def aggregate_da_posterior_over_particles(
    particles: np.ndarray,
    particle_weights: np.ndarray,
    local_candidates: pd.DataFrame,
    meas: pd.Series,
    cp: pd.Series,
    rssd: pd.Series,
    truth: pd.Series,
    traj: pd.Series,
    weights: dict[str, float],
    algorithm_id: str,
) -> tuple[pd.DataFrame, float]:
    logw = np.log(np.maximum(np.asarray(particle_weights, dtype=float), EPS))
    per_particle = []
    per_particle_terms: dict[str, list[np.ndarray]] = {}
    for particle in particles:
        terms = measurement_candidate_log_score_terms(
            particle,
            local_candidates,
            meas,
            cp,
            rssd,
            truth,
            traj,
            weights,
            algorithm_id,
        )
        per_particle.append(terms["total_log_score"])
        for key, value in terms.items():
            per_particle_terms.setdefault(key, []).append(
                np.asarray(value, dtype=float)
            )
    matrix = np.vstack(per_particle)
    candidate_logp = np.asarray([logsumexp(logw + matrix[:, idx]) for idx in range(matrix.shape[1])])
    probs = softmax_from_log(candidate_logp)
    entropy = float(-np.sum(probs * np.log(np.maximum(probs, EPS))))
    candidate_rows = local_candidates.copy()
    candidate_rows["posterior_assoc_prob"] = probs
    for key, values in per_particle_terms.items():
        stacked = np.vstack(values)
        candidate_rows[key] = np.sum(np.asarray(particle_weights, dtype=float)[:, None] * stacked, axis=0)
    candidate_rows["total_log_score"] = candidate_logp
    return candidate_rows, entropy


def aggregate_da_posterior_over_particles_legacy(
    particles: np.ndarray,
    particle_weights: np.ndarray,
    local_candidates: pd.DataFrame,
    meas: pd.Series,
    cp: pd.Series,
    rssd: pd.Series,
    truth: pd.Series,
    traj: pd.Series,
    weights: dict[str, float],
    algorithm_id: str,
) -> tuple[pd.DataFrame, float]:
    logw = np.log(np.maximum(np.asarray(particle_weights, dtype=float), EPS))
    per_particle = []
    for particle in particles:
        per_particle.append(
            measurement_candidate_log_scores(
                particle,
                local_candidates,
                meas,
                cp,
                rssd,
                truth,
                traj,
                weights,
                algorithm_id,
            )
        )
    matrix = np.vstack(per_particle)
    candidate_logp = np.asarray([logsumexp(logw + matrix[:, idx]) for idx in range(matrix.shape[1])])
    probs = softmax_from_log(candidate_logp)
    entropy = float(-np.sum(probs * np.log(np.maximum(probs, EPS))))
    candidate_rows = local_candidates.copy()
    candidate_rows["posterior_assoc_prob"] = probs
    return candidate_rows, entropy


def _solve_slam_ablation_legacy_grid(
    trajectory_truth: pd.DataFrame,
    scene_table: pd.DataFrame,
    va_catalog: pd.DataFrame,
    slam_measurements: pd.DataFrame,
    slam_da_truth: pd.DataFrame,
    regime_labels: pd.DataFrame,
    cp_features: pd.DataFrame,
    rssd_features: pd.DataFrame,
    config: Stage01Config | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    traj_lookup = trajectory_truth.set_index(["sequence_id", "time_idx"])
    scene_lookup = scene_table.set_index("scene_id")
    cp_lookup = cp_features.set_index("measurement_id")
    rssd_lookup = rssd_features.set_index("measurement_id")
    truth_lookup = slam_da_truth.set_index("measurement_id")
    regime_lookup = regime_labels.set_index("measurement_id")
    catalogs = build_candidate_catalogs(va_catalog)
    measurement_groups = slam_measurements[slam_measurements["used_by_slam_flag"]].groupby(["sequence_id", "time_idx"], sort=True)

    slam_rows: list[dict[str, object]] = []
    da_rows: list[dict[str, object]] = []
    posterior_rows: list[list[float]] = []
    trace_rows: list[dict[str, object]] = []

    active_specs = selected_baseline_specs(config)
    for alg_idx, (algorithm_id, algorithm_name, weights) in enumerate(active_specs):
        prev_est: dict[str, np.ndarray] = {}
        for key, traj in traj_lookup.iterrows():
            sequence_id, time_idx = key
            scene_id = sequence_scene_id(str(sequence_id))
            scene_spec = scene_lookup.loc[scene_id]
            base_catalog = catalogs[scene_id]
            candidates = algorithm_candidate_catalog(base_catalog, algorithm_id)
            meas_group = (
                measurement_groups.get_group((sequence_id, time_idx)).reset_index(drop=True)
                if (sequence_id, time_idx) in measurement_groups.groups
                else pd.DataFrame(columns=slam_measurements.columns)
            )
            truth_pos = np.array([traj.agent_x_m, traj.agent_y_m, traj.agent_z_m], dtype=float)
            if sequence_id in prev_est:
                center = prev_est[sequence_id] + np.array([traj.v_x_mps, traj.v_y_mps, 0.0], dtype=float) * 0.5
            else:
                bias = 0.35 + 0.08 * (1.0 - float(weights.get("range", 0.0)))
                phase = 2.0 * math.pi * stable_unit_interval(sequence_id, algorithm_id, "init")
                center = truth_pos + np.array([bias * math.cos(phase), bias * math.sin(phase), 0.0])
            scale = 0.55 if algorithm_id in {"B0", "B2", "B10", "B11"} else 0.38
            if weights.get("oracle_da", 0.0) or weights.get("oracle_va", 0.0):
                scale = 0.25
            particles = make_particle_grid(center, scene_spec, scale)
            measurement_records = []
            for meas in meas_group.itertuples(index=False):
                meas_s = pd.Series(meas._asdict())
                cp = cp_lookup.loc[meas.measurement_id]
                rssd = rssd_lookup.loc[meas.measurement_id]
                truth = truth_lookup.loc[meas.measurement_id]
                if isinstance(truth, pd.DataFrame):
                    truth = truth.iloc[0]
                force_id = str(truth.truth_feature_id) if weights.get("oracle_da", 0.0) or weights.get("oracle_va", 0.0) else None
                local_candidates = candidate_subset_for_measurement(
                    center,
                    candidates,
                    meas_s,
                    cp,
                    algorithm_id,
                    force_feature_id=force_id,
                )
                measurement_records.append((meas_s, cp, rssd, truth, local_candidates))

            particle_scores = []
            particle_entropies = []
            for particle in particles:
                motion_sigma = max(0.25, scale)
                logp = -0.5 * float(np.sum((particle - center) ** 2)) / (motion_sigma**2)
                entropies = []
                for meas_s, cp, rssd, truth, local_candidates in measurement_records:
                    scores = measurement_candidate_log_scores(particle, local_candidates, meas_s, cp, rssd, truth, traj, weights, algorithm_id)
                    logp += logsumexp(scores)
                    probs = softmax_from_log(scores)
                    entropies.append(float(-np.sum(probs * np.log(np.maximum(probs, EPS)))))
                particle_scores.append(logp)
                particle_entropies.append(float(np.mean(entropies)) if entropies else 0.0)

            particle_scores_arr = np.asarray(particle_scores, dtype=float)
            particle_weights = softmax_from_log(particle_scores_arr)
            estimate = np.sum(particles * particle_weights[:, None], axis=0)
            prev_est[str(sequence_id)] = estimate
            error_m = float(np.linalg.norm(estimate - truth_pos))
            ess = float(1.0 / np.sum(np.square(particle_weights)))
            top_particle_idx = np.argsort(particle_weights)[-9:]
            sequence_numeric_id = sum((idx + 1) * ord(ch) for idx, ch in enumerate(str(sequence_id))) % 1000000
            for particle_idx in top_particle_idx:
                posterior_rows.append(
                    [
                        float(alg_idx),
                        float(sequence_numeric_id),
                        float(time_idx),
                        float(particle_idx),
                        float(particles[particle_idx, 0]),
                        float(particles[particle_idx, 1]),
                        float(particles[particle_idx, 2]),
                        float(particle_scores_arr[particle_idx]),
                        float(particle_weights[particle_idx]),
                    ]
                )

            mean_entropy = 0.0
            for meas_s, cp, rssd, truth, local_candidates in measurement_records:
                cand_post, entropy = candidate_posteriors_for_measurement(estimate, local_candidates, meas_s, cp, rssd, truth, traj, weights, algorithm_id)
                mean_entropy += entropy
                truth_id = str(truth.truth_feature_id)
                top = cand_post.sort_values("posterior_assoc_prob", ascending=False).head(6)
                if truth_id not in set(top["feature_id"].astype(str)):
                    truth_row = cand_post[cand_post["feature_id"].astype(str).eq(truth_id)]
                    if len(truth_row):
                        top = pd.concat([top, truth_row.head(1)], ignore_index=True)
                top_feature = str(cand_post.sort_values("posterior_assoc_prob", ascending=False).iloc[0]["feature_id"])
                for cand in top.itertuples(index=False):
                    prob = float(cand.posterior_assoc_prob)
                    row = {
                        "sequence_id": sequence_id,
                        "time_idx": int(time_idx),
                        "algorithm_id": algorithm_id,
                        "measurement_id": meas_s.measurement_id,
                        "candidate_feature_id": cand.feature_id,
                        "posterior_assoc_prob": prob,
                        "is_map_assignment": bool(str(cand.feature_id) == top_feature),
                        "truth_assoc_flag": bool(str(cand.feature_id) == truth_id),
                        "da_correct_flag": bool(top_feature == truth_id),
                        "cp_gate_used": bool(weights.get("cp_reliability", 0.0) or weights.get("cp_likelihood", 0.0)),
                        "parity_gate_used": bool(weights.get("cp_parity", 0.0)),
                        "likelihood_range": float(math.exp(-min(float(meas_s.get("range_var_base_m2", 1.0)), 50.0))),
                        "likelihood_amp": float(sigmoid((float(meas_s.amplitude_db) + 30.0) / 5.0)),
                        "likelihood_cp": float(cp.cp_reliability if weights.get("cp_likelihood", 0.0) or weights.get("cp_reliability", 0.0) else 0.5),
                        "likelihood_parity": float(cp.cp_parity_confidence if weights.get("cp_parity", 0.0) else 0.5),
                        "num_candidates_considered": int(len(local_candidates)),
                        "da_entropy": entropy,
                        "regime_id": regime_lookup.loc[meas_s.measurement_id].regime_id if meas_s.measurement_id in regime_lookup.index else "",
                    }
                    da_rows.append(row)

            mean_entropy = mean_entropy / max(len(meas_group), 1)
            slam_rows.append(
                {
                    "sequence_id": sequence_id,
                    "time_idx": int(time_idx),
                    "algorithm_id": algorithm_id,
                    "baseline_id": algorithm_id,
                    "estimated_x_m": float(estimate[0]),
                    "estimated_y_m": float(estimate[1]),
                    "estimated_z_m": float(estimate[2]),
                    "estimated_yaw_deg": float(traj.yaw_deg),
                    "position_error_m": error_m,
                    "yaw_error_deg": 0.0,
                    "num_detected_features": int(len(meas_group)),
                    "num_estimated_va": int(max(0, len(candidates[candidates["feature_type"].eq("VA")]))),
                    "num_particles": int(len(particles)),
                    "bp_iterations": 4 if algorithm_id not in {"B0", "B1"} else 1,
                    "runtime_s": float(0.0007 * max(1, len(meas_group)) * len(candidates) * len(particles)),
                    "converged_flag": bool(np.isfinite(error_m) and ess >= 2.0),
                    "posterior_ess": ess,
                    "mean_da_entropy": mean_entropy,
                    "solver_name": "lightweight_particle_bp_stress_solver_v1",
                }
            )
            trace_rows.append(
                {
                    "algorithm_id": algorithm_id,
                    "algorithm_name": algorithm_name,
                    "sequence_id": sequence_id,
                    "time_idx": int(time_idx),
                    "num_measurements": int(len(meas_group)),
                    "num_candidates": int(len(candidates)),
                    "num_particles": int(len(particles)),
                    "posterior_ess": ess,
                    "mean_da_entropy": mean_entropy,
                    "position_error_m": error_m,
                    "log_evidence": float(logsumexp(particle_scores_arr)),
                }
            )

    slam_result = pd.DataFrame(slam_rows)
    slam_da_result = pd.DataFrame(da_rows)
    slam_feature_result = build_slam_feature_result_table(slam_da_truth, va_catalog, slam_da_result)
    posterior_particles = pd.DataFrame(
        posterior_rows,
        columns=[
            "algorithm_index",
            "sequence_hash",
            "time_idx",
            "particle_idx",
            "x_m",
            "y_m",
            "z_m",
            "log_weight_unnormalized",
            "posterior_weight",
        ],
    )
    bp_trace = pd.DataFrame(trace_rows)
    return slam_result, slam_da_result, slam_feature_result, posterior_particles, bp_trace


def circular_mean_deg(values_deg: np.ndarray, weights: np.ndarray) -> float:
    angles = np.deg2rad(np.asarray(values_deg, dtype=float))
    w = np.asarray(weights, dtype=float)
    s = float(np.sum(w * np.sin(angles)))
    c = float(np.sum(w * np.cos(angles)))
    return float((math.degrees(math.atan2(s, c)) + 180.0) % 360.0 - 180.0)


def attach_cp_class_probs(meas_s: pd.Series, cp_class_lookup: pd.DataFrame | None) -> pd.Series:
    if cp_class_lookup is None or meas_s.measurement_id not in cp_class_lookup.index:
        meas_s["pred_los_prob"] = 0.34
        meas_s["pred_single_bounce_prob"] = 0.33
        meas_s["pred_multi_bounce_prob"] = 0.33
        return meas_s
    pred = cp_class_lookup.loc[meas_s.measurement_id]
    if isinstance(pred, pd.DataFrame):
        pred = pred.iloc[0]
    meas_s["pred_los_prob"] = float(pred.pred_los_prob)
    meas_s["pred_single_bounce_prob"] = float(pred.pred_single_bounce_prob)
    meas_s["pred_multi_bounce_prob"] = float(pred.pred_multi_bounce_prob)
    return meas_s


def solve_slam_ablation(
    trajectory_truth: pd.DataFrame,
    scene_table: pd.DataFrame,
    va_catalog: pd.DataFrame,
    slam_measurements: pd.DataFrame,
    slam_da_truth: pd.DataFrame | None = None,
    regime_labels: pd.DataFrame | None = None,
    cp_features: pd.DataFrame | None = None,
    rssd_features: pd.DataFrame | None = None,
    classifier_prediction: pd.DataFrame | None = None,
    config: Stage01Config | None = None,
    *,
    initial_pose_prior: pd.DataFrame | None = None,
    odometry_table: pd.DataFrame | None = None,
    rssd_orientation_trajectory: pd.DataFrame | None = None,
    candidate_catalog_input: pd.DataFrame | None = None,
    candidate_mode: str | None = None,
    truth_clean_solver: bool | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Stage 4.5/5 known-catalog particle + soft DA bridge solver.

    This is intentionally not unknown-feature BP-SLAM. It uses
    va_catalog_truth.csv as the PA/VA candidate catalog, propagates a 2.5D AMR
    particle posterior [px, py, psi] with fixed tag height, marginalizes
    measurement likelihoods over candidate features, and then marginalizes DA
    posterior over the particle posterior.
    """

    cfg = config or Stage01Config(output_dir=Path("."))
    # slam_da_truth=None is the truth-free API: behave identically to truth_clean=True.
    # regime_labels / cp_features / rssd_features are required even in truth-free mode
    # (they carry measurement-derived features, not ground-truth).  The signature
    # accepts None only because Python requires defaults on all args after an arg with
    # a default (slam_da_truth=None).  Raise early if they are omitted.
    if regime_labels is None:
        raise ValueError("regime_labels is required by solve_slam_ablation")
    if cp_features is None:
        raise ValueError("cp_features is required by solve_slam_ablation")
    if rssd_features is None:
        raise ValueError("rssd_features is required by solve_slam_ablation")

    truth_clean = bool(cfg.truth_clean_solver if truth_clean_solver is None else truth_clean_solver)
    if slam_da_truth is None:
        truth_clean = True  # no truth provided → operate in truth-clean mode
    active_candidate_mode = str(candidate_mode or cfg.candidate_mode or "known_catalog")
    num_particles = max(8, int(cfg.solver_num_particles))
    max_candidates = max(4, int(cfg.solver_max_candidates))
    da_particle_top = max(4, min(int(cfg.solver_da_particle_top), num_particles))

    if odometry_table is not None:
        _validate_solver_odometry_table(odometry_table, strict=cfg.require_independent_motion_inputs)
    if cfg.require_independent_motion_inputs and (initial_pose_prior is None or odometry_table is None):
        raise ValueError("independent motion inputs require initial_pose_prior and odometry_table")

    if truth_clean:
        rssd_features = sanitize_solver_rssd_features(rssd_features, strict=cfg.fail_on_truth_leakage)
    if candidate_catalog_input is not None:
        candidate_catalog_input = sanitize_candidate_catalog_input(
            candidate_catalog_input,
            strict=cfg.fail_on_truth_leakage,
        )

    scene_lookup = scene_table.set_index("scene_id")
    cp_lookup = cp_features.set_index("measurement_id")
    rssd_lookup = rssd_features.set_index("measurement_id")
    # truth_clean is True if slam_da_truth is None (set above); safe to skip .set_index
    truth_lookup = {} if truth_clean else slam_da_truth.set_index("measurement_id")
    regime_lookup = regime_labels.set_index("measurement_id")
    prior_lookup = _sequence_lookup(initial_pose_prior)
    odom_lookup = _solver_lookup(odometry_table)
    rssd_orientation_lookup = _solver_lookup(rssd_orientation_trajectory)
    motion_source = "odometry_table" if odom_lookup else "legacy_trajectory_truth"
    catalogs = (
        build_candidate_catalogs_from_input(candidate_catalog_input, strict=cfg.fail_on_truth_leakage)
        if candidate_catalog_input is not None
        else build_candidate_catalogs(va_catalog)
    )
    if len(slam_measurements):
        used_mask = slam_measurements["used_by_slam_flag"].astype(bool)
        used_measurements = slam_measurements[used_mask]
    else:
        used_measurements = slam_measurements.copy()
    measurement_groups = (
        used_measurements.groupby(["sequence_id", "time_idx"], sort=True)
        if len(used_measurements)
        else None
    )
    cp_class_lookup = None
    if classifier_prediction is not None and len(classifier_prediction):
        part = classifier_prediction[classifier_prediction["model_id"].eq("M_A_CP")]
        if len(part):
            cp_class_lookup = part.set_index("measurement_id")

    slam_rows: list[dict[str, object]] = []
    da_rows: list[dict[str, object]] = []
    posterior_rows: list[list[float]] = []
    trace_rows: list[dict[str, object]] = []

    active_specs = selected_baseline_specs(cfg)
    for alg_idx, (algorithm_id, algorithm_name, weights) in enumerate(active_specs):
        for sequence_id, seq_traj in trajectory_truth.groupby("sequence_id", sort=True):
            seq_traj = seq_traj.sort_values("time_idx").reset_index(drop=True)
            scene_id = sequence_scene_id(str(sequence_id))
            scene_spec = scene_lookup.loc[scene_id]
            base_catalog = catalogs[scene_id]
            if candidate_catalog_input is not None:
                base_catalog = sequence_candidate_catalog(base_catalog, str(sequence_id))
            candidates = algorithm_candidate_catalog(base_catalog, algorithm_id)
            rng = solver_rng(cfg.random_seed, algorithm_id, sequence_id, active_candidate_mode, "pf")
            if prior_lookup:
                if str(sequence_id) not in prior_lookup:
                    raise ValueError(f"initial_pose_prior missing sequence_id={sequence_id}")
                initial_prior = prior_lookup[str(sequence_id)]
            else:
                if cfg.require_independent_motion_inputs:
                    raise ValueError("initial_pose_prior is required when independent motion inputs are enforced")
                initial_prior = seq_traj.iloc[0]
            particles = initialize_particles(initial_prior, scene_spec, num_particles, rng, algorithm_id)
            particle_weights = np.full(num_particles, 1.0 / num_particles, dtype=float)
            prev_traj = None

            for traj in seq_traj.itertuples(index=False):
                time_idx = int(traj.time_idx)
                traj_s = pd.Series(traj._asdict())
                rssd_traj_s = rssd_orientation_lookup.get((str(sequence_id), time_idx), traj_s)
                if prev_traj is None:
                    particles = clip_particles_to_scene(particles, scene_spec)
                elif odom_lookup:
                    odom_key = (str(sequence_id), time_idx)
                    if odom_key not in odom_lookup:
                        raise ValueError(f"odometry_table missing sequence_id={sequence_id} time_idx={time_idx}")
                    particles = predict_particles_from_odometry(
                        particles,
                        odom_lookup[odom_key],
                        scene_spec,
                        rng,
                        algorithm_id,
                        noise_scale=cfg.odometry_noise_scale,
                    )
                else:
                    if cfg.require_independent_motion_inputs:
                        raise ValueError("odometry_table is required when independent motion inputs are enforced")
                    particles = predict_particles(
                        particles,
                        prev_traj,
                        traj_s,
                        scene_spec,
                        rng,
                        algorithm_id,
                        noise_scale=cfg.odometry_noise_scale,
                    )
                prior_logw = np.log(np.maximum(particle_weights, EPS))
                meas_group = (
                    measurement_groups.get_group((sequence_id, time_idx)).reset_index(drop=True)
                    if measurement_groups is not None and (sequence_id, time_idx) in measurement_groups.groups
                    else pd.DataFrame(columns=slam_measurements.columns)
                )

                predicted_mean = np.sum(particles * particle_weights[:, None], axis=0)
                truth_pos = np.array([traj.agent_x_m, traj.agent_y_m, traj.agent_z_m], dtype=float)
                guard_target = str(cfg.measurement_regularizer_target).strip().lower()
                guard_cap = float(cfg.measurement_regularizer_centered_cap)
                guard_algorithm_ids = _config_algorithm_ids(cfg.measurement_regularizer_algorithms)
                guard_enabled_for_algorithm = (
                    guard_target not in {"", "none", "off", "disabled"}
                    and guard_cap > 0.0
                    and str(algorithm_id) != "B16"
                    and (not guard_algorithm_ids or str(algorithm_id) in guard_algorithm_ids)
                )
                measurement_records = []
                guard_trace_records = []
                num_regularized_updates = 0
                logw = prior_logw.copy()
                for meas in meas_group.itertuples(index=False):
                    meas_s = attach_cp_class_probs(pd.Series(meas._asdict()), cp_class_lookup)
                    cp = cp_lookup.loc[meas.measurement_id]
                    rssd = rssd_lookup.loc[meas.measurement_id]
                    if not truth_clean and meas.measurement_id in truth_lookup.index:
                        truth = truth_lookup.loc[meas.measurement_id]
                        if isinstance(truth, pd.DataFrame):
                            truth = truth.iloc[0]
                    else:
                        truth = neutral_measurement_truth(meas_s)
                    regime_id = (
                        str(regime_lookup.loc[meas.measurement_id].regime_id)
                        if meas.measurement_id in regime_lookup.index
                        else ""
                    )
                    truth_feature_id = str(_row_get(truth, "truth_feature_id", ""))
                    force_id = truth_feature_id if truth_feature_id and (weights.get("oracle_da", 0.0) or weights.get("oracle_va", 0.0)) else None
                    local_candidates = candidate_subset_for_measurement(
                        predicted_mean,
                        candidates,
                        meas_s,
                        cp,
                        algorithm_id,
                        max_candidates=max_candidates,
                        force_feature_id=force_id,
                    )
                    marginal = log_marginal_measurement_scores(
                        particles,
                        local_candidates,
                        meas_s,
                        cp,
                        rssd,
                        truth,
                        rssd_traj_s,
                        weights,
                        algorithm_id,
                    )
                    weights_before_update = softmax_from_log(logw)
                    marginal_pre = marginal.copy()
                    logw_pre_update = logw + marginal_pre
                    weights_after_pre = softmax_from_log(logw_pre_update)
                    guard_active = should_regularize_measurement_marginal(cfg, algorithm_id, regime_id, marginal_pre)
                    if guard_active:
                        marginal = apply_centered_measurement_cap(marginal_pre, weights_before_update, guard_cap)
                        num_regularized_updates += 1
                    else:
                        marginal = marginal_pre
                    logw_post_update = logw + marginal
                    weights_after_post = softmax_from_log(logw_post_update)
                    clip_vec = marginal_pre - marginal
                    guard_clip_amount = float(np.max(np.abs(clip_vec))) if len(clip_vec) else 0.0
                    estimate_before = np.sum(particles * weights_before_update[:, None], axis=0)
                    estimate_before[3] = circular_mean_deg(particles[:, 3], weights_before_update)
                    estimate_after = np.sum(particles * weights_after_post[:, None], axis=0)
                    estimate_after[3] = circular_mean_deg(particles[:, 3], weights_after_post)
                    pre_top_id = ""
                    post_top_id = ""
                    pre_top_prob = np.nan
                    post_top_prob = np.nan
                    pre_margin = np.nan
                    post_margin = np.nan
                    if guard_enabled_for_algorithm:
                        pre_cand_post, _ = aggregate_da_posterior_over_particles(
                            particles,
                            weights_after_pre,
                            local_candidates,
                            meas_s,
                            cp,
                            rssd,
                            truth,
                            rssd_traj_s,
                            weights,
                            algorithm_id,
                        )
                        post_cand_post, _ = aggregate_da_posterior_over_particles(
                            particles,
                            weights_after_post,
                            local_candidates,
                            meas_s,
                            cp,
                            rssd,
                            truth,
                            rssd_traj_s,
                            weights,
                            algorithm_id,
                        )
                        pre_ranked = pre_cand_post.sort_values("posterior_assoc_prob", ascending=False)
                        post_ranked = post_cand_post.sort_values("posterior_assoc_prob", ascending=False)
                        if len(pre_ranked):
                            pre_top_id = str(pre_ranked.iloc[0]["feature_id"])
                            pre_top_prob = float(pre_ranked.iloc[0]["posterior_assoc_prob"])
                            pre_margin = float(
                                pre_top_prob
                                - (float(pre_ranked.iloc[1]["posterior_assoc_prob"]) if len(pre_ranked) > 1 else 0.0)
                            )
                        if len(post_ranked):
                            post_top_id = str(post_ranked.iloc[0]["feature_id"])
                            post_top_prob = float(post_ranked.iloc[0]["posterior_assoc_prob"])
                            post_margin = float(
                                post_top_prob
                                - (float(post_ranked.iloc[1]["posterior_assoc_prob"]) if len(post_ranked) > 1 else 0.0)
                            )
                    guard_trace_records.append(
                        {
                            "measurement_id": str(meas_s.measurement_id),
                            "guard_mode": "off" if not guard_enabled_for_algorithm else "centered_cap",
                            "guard_enabled": bool(guard_enabled_for_algorithm),
                            "guard_target": str(cfg.measurement_regularizer_target),
                            "guard_cap": guard_cap,
                            "guard_active": bool(guard_active),
                            "guard_clip_amount": guard_clip_amount,
                            "pre_guard_total_score": float(logsumexp(logw_pre_update)),
                            "post_guard_total_score": float(logsumexp(logw_post_update)),
                            "pre_guard_marginal_score": float(np.sum(weights_before_update * marginal_pre)),
                            "post_guard_marginal_score": float(np.sum(weights_before_update * marginal)),
                            "pre_guard_top1_candidate": pre_top_id,
                            "post_guard_top1_candidate": post_top_id,
                            "pre_guard_top1_prob": pre_top_prob,
                            "post_guard_top1_prob": post_top_prob,
                            "pre_guard_posterior_margin": pre_margin,
                            "post_guard_posterior_margin": post_margin,
                            "particle_ESS_before": particle_ess(weights_before_update),
                            "particle_ESS_after": particle_ess(weights_after_post),
                            "weight_entropy_before": weight_entropy(weights_before_update),
                            "weight_entropy_after": weight_entropy(weights_after_post),
                            "position_error_before_update": float(np.linalg.norm(estimate_before[:3] - truth_pos)),
                            "position_error_after_update": float(np.linalg.norm(estimate_after[:3] - truth_pos)),
                            "range_log_score": float("nan"),
                            "amplitude_log_score": float("nan"),
                            "rssd_log_score": float("nan"),
                            "cp_reliability_log_score": float("nan"),
                            "cp_likelihood_log_score": float("nan"),
                            "cp_parity_log_score": float("nan"),
                            "total_log_score": float("nan"),
                        }
                    )
                    logw += marginal
                    measurement_records.append((meas_s, cp, rssd, truth, local_candidates, rssd_traj_s))

                posterior_weights = softmax_from_log(logw)
                ess = particle_ess(posterior_weights)
                estimate = np.sum(particles * posterior_weights[:, None], axis=0)
                estimate[3] = circular_mean_deg(particles[:, 3], posterior_weights)
                error_m = float(np.linalg.norm(estimate[:3] - truth_pos))
                yaw_error = abs(wrap_deg(float(estimate[3]) - float(traj.yaw_deg)))
                top_particle_idx = np.argsort(posterior_weights)[-min(16, num_particles):]
                sequence_numeric_id = sum((idx + 1) * ord(ch) for idx, ch in enumerate(str(sequence_id))) % 1000000
                for particle_idx in top_particle_idx:
                    posterior_rows.append(
                        [
                            float(alg_idx),
                            float(sequence_numeric_id),
                            float(time_idx),
                            float(particle_idx),
                            float(particles[particle_idx, 0]),
                            float(particles[particle_idx, 1]),
                            float(particles[particle_idx, 2]),
                            float(particles[particle_idx, 3]),
                            float(logw[particle_idx]),
                            float(posterior_weights[particle_idx]),
                        ]
                    )

                mean_entropy = 0.0
                da_top_idx = np.argsort(posterior_weights)[-da_particle_top:]
                da_particles = particles[da_top_idx]
                da_weights = posterior_weights[da_top_idx]
                da_weights = da_weights / max(float(da_weights.sum()), EPS)
                for meas_s, cp, rssd, truth, local_candidates, rssd_traj_s in measurement_records:
                    cand_post, entropy = aggregate_da_posterior_over_particles(
                        da_particles,
                        da_weights,
                        local_candidates,
                        meas_s,
                        cp,
                        rssd,
                        truth,
                        rssd_traj_s,
                        weights,
                        algorithm_id,
                    )
                    mean_entropy += entropy
                    truth_id = str(_row_get(truth, "truth_feature_id", ""))
                    ranked = cand_post.sort_values("posterior_assoc_prob", ascending=False)
                    top = ranked.head(6)
                    if truth_id and truth_id not in set(top["feature_id"].astype(str)):
                        truth_row = cand_post[cand_post["feature_id"].astype(str).eq(truth_id)]
                        if len(truth_row):
                            top = pd.concat([top, truth_row.head(1)], ignore_index=True)
                    top_feature = str(ranked.iloc[0]["feature_id"])
                    cp_gate = bool(weights.get("cp_reliability", 0.0) or weights.get("cp_likelihood", 0.0))
                    parity_gate = bool(weights.get("cp_parity", 0.0))
                    for cand in top.itertuples(index=False):
                        prob = float(cand.posterior_assoc_prob)
                        row = {
                            "sequence_id": sequence_id,
                            "time_idx": time_idx,
                            "algorithm_id": algorithm_id,
                            "measurement_id": meas_s.measurement_id,
                            "candidate_feature_id": cand.feature_id,
                            "candidate_feature_type": getattr(cand, "feature_type", ""),
                            "candidate_va_order": float(getattr(cand, "va_order", np.nan)),
                            "candidate_expected_parity": getattr(cand, "expected_parity", ""),
                            "posterior_assoc_prob": prob,
                            "is_map_assignment": bool(str(cand.feature_id) == top_feature),
                            "truth_assoc_flag": bool(truth_id and str(cand.feature_id) == truth_id),
                            "da_correct_flag": bool(truth_id and top_feature == truth_id),
                            "cp_gate_used": cp_gate,
                            "parity_gate_used": parity_gate,
                            "likelihood_range": float(math.exp(-min(float(meas_s.get("range_var_base_m2", 1.0)), 50.0))),
                            "likelihood_amp": float(sigmoid((float(meas_s.amplitude_db) + 30.0) / 5.0)),
                            "likelihood_cp": float(cp.cp_reliability if cp_gate else 0.5),
                            "likelihood_parity": float(cp.cp_parity_confidence if parity_gate else 0.5),
                            "base_prior_log_score": float(getattr(cand, "base_prior_log_score", 0.0)),
                            "range_log_score": float(getattr(cand, "range_log_score", 0.0)),
                            "amplitude_log_score": float(getattr(cand, "amplitude_log_score", 0.0)),
                            "rssd_log_score": float(getattr(cand, "rssd_log_score", 0.0)),
                            "cp_reliability_log_score": float(getattr(cand, "cp_reliability_log_score", 0.0)),
                            "cp_likelihood_log_score": float(getattr(cand, "cp_likelihood_log_score", 0.0)),
                            "cp_parity_log_score": float(getattr(cand, "cp_parity_log_score", 0.0)),
                            "shuffled_cp_log_score": float(getattr(cand, "shuffled_cp_log_score", 0.0)),
                            "oracle_log_score": float(getattr(cand, "oracle_log_score", 0.0)),
                            "raw_cir_log_score": float(getattr(cand, "raw_cir_log_score", 0.0)),
                            "clutter_prior_log_score": float(getattr(cand, "clutter_prior_log_score", np.nan)),
                            "total_log_score": float(getattr(cand, "total_log_score", 0.0)),
                            "positive_guard_clip": 0.0,
                            "num_candidates_considered": int(len(local_candidates)),
                            "da_entropy": entropy,
                            "regime_id": regime_lookup.loc[meas_s.measurement_id].regime_id if meas_s.measurement_id in regime_lookup.index else "",
                        }
                        da_rows.append(row)

                mean_entropy = mean_entropy / max(len(measurement_records), 1)
                guard_active_count = int(sum(1 for row in guard_trace_records if row["guard_active"]))
                guard_trace_count = int(len(guard_trace_records))
                guard_active_ratio = float(guard_active_count / max(guard_trace_count, 1))

                def _guard_values(key: str) -> list[float]:
                    vals: list[float] = []
                    for row in guard_trace_records:
                        value = row.get(key, np.nan)
                        try:
                            fval = float(value)
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(fval):
                            vals.append(fval)
                    return vals

                def _guard_mean(key: str) -> float:
                    vals = _guard_values(key)
                    return float(np.mean(vals)) if vals else float("nan")

                def _guard_max(key: str) -> float:
                    vals = _guard_values(key)
                    return float(np.max(vals)) if vals else 0.0

                guard_representative = (
                    max(guard_trace_records, key=lambda row: float(row.get("guard_clip_amount", 0.0)))
                    if guard_trace_records
                    else {}
                )
                guard_clip_amount_mean = _guard_mean("guard_clip_amount")
                guard_clip_amount_max = _guard_max("guard_clip_amount")
                pre_guard_total_score = _guard_mean("pre_guard_total_score")
                post_guard_total_score = _guard_mean("post_guard_total_score")
                pre_guard_marginal_score = _guard_mean("pre_guard_marginal_score")
                post_guard_marginal_score = _guard_mean("post_guard_marginal_score")
                pre_guard_top1_candidate = str(guard_representative.get("pre_guard_top1_candidate", ""))
                post_guard_top1_candidate = str(guard_representative.get("post_guard_top1_candidate", ""))
                pre_guard_top1_prob = _guard_mean("pre_guard_top1_prob")
                post_guard_top1_prob = _guard_mean("post_guard_top1_prob")
                pre_guard_posterior_margin = _guard_mean("pre_guard_posterior_margin")
                post_guard_posterior_margin = _guard_mean("post_guard_posterior_margin")
                particle_ess_before_update = _guard_mean("particle_ESS_before")
                particle_ess_after_update = _guard_mean("particle_ESS_after")
                weight_entropy_before_update = _guard_mean("weight_entropy_before")
                weight_entropy_after_update = _guard_mean("weight_entropy_after")
                position_error_before_update = _guard_mean("position_error_before_update")
                position_error_after_update = _guard_mean("position_error_after_update")
                guard_mode = "off" if not guard_enabled_for_algorithm else "centered_cap"
                slam_rows.append(
                    {
                        "sequence_id": sequence_id,
                        "time_idx": time_idx,
                        "algorithm_id": algorithm_id,
                        "baseline_id": algorithm_id,
                        "estimated_x_m": float(estimate[0]),
                        "estimated_y_m": float(estimate[1]),
                        "estimated_z_m": float(estimate[2]),
                        "estimated_yaw_deg": float(estimate[3]),
                        "position_error_m": error_m,
                        "yaw_error_deg": yaw_error,
                        "num_detected_features": int(len(meas_group)),
                        "num_estimated_va": int(max(0, len(candidates[candidates["feature_type"].eq("VA")]))),
                        "num_particles": num_particles,
                        "bp_iterations": 1,
                        "runtime_s": float(0.00018 * max(1, len(meas_group)) * len(candidates) * num_particles),
                        "converged_flag": bool(np.isfinite(error_m) and ess >= 1.5),
                        "posterior_ess": ess,
                        "mean_da_entropy": mean_entropy,
                        "solver_name": "known_catalog_particle_soft_da_v0_1",
                        "motion_source": motion_source,
                        "candidate_mode": active_candidate_mode,
                        "truth_clean_solver": bool(truth_clean),
                        "measurement_regularizer_target": str(cfg.measurement_regularizer_target),
                        "measurement_regularizer_centered_cap": float(cfg.measurement_regularizer_centered_cap),
                        "measurement_regularizer_updates": int(num_regularized_updates),
                        "guard_mode": guard_mode,
                        "guard_enabled": bool(guard_enabled_for_algorithm),
                        "guard_active_count": guard_active_count,
                        "guard_active_ratio": guard_active_ratio,
                        "guard_clip_amount_mean": guard_clip_amount_mean,
                        "guard_clip_amount_max": guard_clip_amount_max,
                        "pre_guard_total_score": pre_guard_total_score,
                        "post_guard_total_score": post_guard_total_score,
                        "pre_guard_marginal_score": pre_guard_marginal_score,
                        "post_guard_marginal_score": post_guard_marginal_score,
                        "particle_ESS_before": particle_ess_before_update,
                        "particle_ESS_after": particle_ess_after_update,
                        "weight_entropy_before": weight_entropy_before_update,
                        "weight_entropy_after": weight_entropy_after_update,
                    }
                )
                trace_rows.append(
                    {
                        "algorithm_id": algorithm_id,
                        "algorithm_name": algorithm_name,
                        "sequence_id": sequence_id,
                        "time_idx": time_idx,
                        "num_measurements": int(len(meas_group)),
                        "num_candidates": int(len(candidates)),
                        "num_particles": num_particles,
                        "posterior_ess": ess,
                        "mean_da_entropy": mean_entropy,
                        "position_error_m": error_m,
                        "log_evidence": float(logsumexp(logw)),
                        "motion_source": motion_source,
                        "candidate_mode": active_candidate_mode,
                        "truth_clean_solver": bool(truth_clean),
                        "measurement_regularizer_target": str(cfg.measurement_regularizer_target),
                        "measurement_regularizer_centered_cap": float(cfg.measurement_regularizer_centered_cap),
                        "measurement_regularizer_updates": int(num_regularized_updates),
                        "guard_mode": guard_mode,
                        "guard_enabled": bool(guard_enabled_for_algorithm),
                        "guard_target": str(cfg.measurement_regularizer_target),
                        "guard_cap": guard_cap,
                        "guard_active_count": guard_active_count,
                        "guard_active_ratio": guard_active_ratio,
                        "guard_clip_amount_mean": guard_clip_amount_mean,
                        "guard_clip_amount_max": guard_clip_amount_max,
                        "pre_guard_total_score": pre_guard_total_score,
                        "post_guard_total_score": post_guard_total_score,
                        "pre_guard_marginal_score": pre_guard_marginal_score,
                        "post_guard_marginal_score": post_guard_marginal_score,
                        "pre_guard_top1_candidate": pre_guard_top1_candidate,
                        "post_guard_top1_candidate": post_guard_top1_candidate,
                        "pre_guard_top1_prob": pre_guard_top1_prob,
                        "post_guard_top1_prob": post_guard_top1_prob,
                        "pre_guard_posterior_margin": pre_guard_posterior_margin,
                        "post_guard_posterior_margin": post_guard_posterior_margin,
                        "particle_ESS_before": particle_ess_before_update,
                        "particle_ESS_after": particle_ess_after_update,
                        "weight_entropy_before": weight_entropy_before_update,
                        "weight_entropy_after": weight_entropy_after_update,
                        "resampled_flag": True,
                        "position_error_before_update": position_error_before_update,
                        "position_error_after_update": position_error_after_update,
                        "range_log_score": _guard_mean("range_log_score"),
                        "amplitude_log_score": _guard_mean("amplitude_log_score"),
                        "rssd_log_score": _guard_mean("rssd_log_score"),
                        "cp_reliability_log_score": _guard_mean("cp_reliability_log_score"),
                        "cp_likelihood_log_score": _guard_mean("cp_likelihood_log_score"),
                        "cp_parity_log_score": _guard_mean("cp_parity_log_score"),
                        "total_log_score": _guard_mean("total_log_score"),
                    }
                )

                # Bootstrap filter time update: resample posterior before the
                # next odometry prediction. This removes the old truth-centered
                # deterministic grid behavior.
                resample_idx = systematic_resample(posterior_weights, rng)
                jitter_scale = max(0.0, float(cfg.odometry_noise_scale))
                particles = particles[resample_idx]
                particles[:, :2] += rng.normal(0.0, 0.025 * jitter_scale, size=(num_particles, 2))
                particles[:, 3] += rng.normal(0.0, 0.6 * jitter_scale, size=num_particles)
                particles = clip_particles_to_scene(particles, scene_spec)
                particle_weights = np.full(num_particles, 1.0 / num_particles, dtype=float)
                prev_traj = traj_s

    slam_result = pd.DataFrame(slam_rows)
    slam_da_result = pd.DataFrame(da_rows)
    if truth_clean:
        slam_feature_result = pd.DataFrame(
            columns=[
                "algorithm_id",
                "feature_id",
                "feature_type",
                "posterior_support",
                "truth_clean_solver",
                "evaluation_required",
            ]
        )
    else:
        slam_feature_result = build_slam_feature_result_table(slam_da_truth, va_catalog, slam_da_result)
    posterior_particles = pd.DataFrame(
        posterior_rows,
        columns=[
            "algorithm_index",
            "sequence_hash",
            "time_idx",
            "particle_idx",
            "x_m",
            "y_m",
            "z_m",
            "psi_deg",
            "log_weight_unnormalized",
            "posterior_weight",
        ],
    )
    bp_trace = pd.DataFrame(trace_rows)
    return slam_result, slam_da_result, slam_feature_result, posterior_particles, bp_trace


def write_solver_h5(output_dir: Path, posterior_particles: pd.DataFrame, bp_trace: pd.DataFrame) -> None:
    import h5py

    output_dir.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_dir / "posterior_particles.h5", "w") as h5:
        h5.create_dataset("posterior_particle_table", data=posterior_particles.to_numpy(float))
        h5.create_dataset(
            "columns",
            data=np.asarray(posterior_particles.columns.astype(str), dtype="S"),
        )
    numeric_trace = bp_trace[
        [
            "time_idx",
            "num_measurements",
            "num_candidates",
            "num_particles",
            "posterior_ess",
            "mean_da_entropy",
            "position_error_m",
            "log_evidence",
        ]
    ].to_numpy(float)
    with h5py.File(output_dir / "bp_message_trace.h5", "w") as h5:
        h5.create_dataset("bp_message_trace_numeric", data=numeric_trace)
        h5.create_dataset(
            "numeric_columns",
            data=np.asarray(
                [
                    "time_idx",
                    "num_measurements",
                    "num_candidates",
                    "num_particles",
                    "posterior_ess",
                    "mean_da_entropy",
                    "position_error_m",
                    "log_evidence",
                ],
                dtype="S",
            ),
        )


def build_claim_gate_summary(
    ablation: pd.DataFrame,
    metric_by_regime: pd.DataFrame,
    classifier_prediction: pd.DataFrame,
    classifier_input: pd.DataFrame,
) -> pd.DataFrame:
    rows = []
    def value(table: pd.DataFrame, algorithm: str, column: str) -> float:
        part = table[table["algorithm_id"].eq(algorithm)]
        return float(part[column].iloc[0]) if len(part) else float("nan")

    b3_da = value(ablation, "B3", "da_error_rate")
    b9_da = value(ablation, "B9", "da_error_rate")
    b10_da = value(ablation, "B10", "da_error_rate")
    b3_rmse = value(ablation, "B3", "position_rmse_m")
    b9_rmse = value(ablation, "B9", "position_rmse_m")
    b10_rmse = value(ablation, "B10", "position_rmse_m")
    b3_mospa = value(ablation, "B3", "va_mospa_m")
    b9_mospa = value(ablation, "B9", "va_mospa_m")

    rows.append({"gate_id": "GATE_DA_B9_LT_B3", "metric": "da_error_rate", "reference": b3_da, "proposed": b9_da, "negative_control": b10_da, "delta_vs_reference": b3_da - b9_da, "delta_vs_negative_control": b10_da - b9_da, "pass": bool(b9_da < b3_da and b9_da < b10_da)})
    rows.append({"gate_id": "GATE_RMSE_B9_LT_B3", "metric": "position_rmse_m", "reference": b3_rmse, "proposed": b9_rmse, "negative_control": b10_rmse, "delta_vs_reference": b3_rmse - b9_rmse, "delta_vs_negative_control": b10_rmse - b9_rmse, "pass": bool(b9_rmse < b3_rmse and b9_rmse < b10_rmse)})
    rows.append({"gate_id": "GATE_VA_MOSPA_B9_LT_B3", "metric": "va_mospa_m", "reference": b3_mospa, "proposed": b9_mospa, "negative_control": float("nan"), "delta_vs_reference": b3_mospa - b9_mospa, "delta_vs_negative_control": float("nan"), "pass": bool(b9_mospa < b3_mospa)})

    positive = metric_by_regime[metric_by_regime["regime_id"].isin(["G2", "G3", "G4", "G5", "G6"])]
    b3_p95 = positive[positive["algorithm_id"].eq("B3")]["position_p95_m"].mean()
    b9_p95 = positive[positive["algorithm_id"].eq("B9")]["position_p95_m"].mean()
    b10_p95 = positive[positive["algorithm_id"].eq("B10")]["position_p95_m"].mean()
    rows.append({"gate_id": "GATE_POSITIVE_REGIME_P95", "metric": "positive_regime_position_p95_m", "reference": float(b3_p95), "proposed": float(b9_p95), "negative_control": float(b10_p95), "delta_vs_reference": float(b3_p95 - b9_p95), "delta_vs_negative_control": float(b10_p95 - b9_p95), "pass": bool(b9_p95 < b3_p95 and b9_p95 < b10_p95)})

    pred = classifier_prediction.merge(
        classifier_input[["measurement_id", "label_valid_specular"]],
        on="measurement_id",
        how="left",
    )
    pred["accepted"] = pred["pred_valid_prob"].ge(0.5)
    model_stats = []
    for model_id, group in pred.groupby("model_id"):
        valid = group["pred_valid_prob"].notna()
        accepted = group.loc[valid, "accepted"]
        truth_valid = group.loc[valid, "label_valid_specular"].astype(bool)
        recall = float((accepted & truth_valid).sum() / max(truth_valid.sum(), 1))
        fvr = float((accepted & ~truth_valid).sum() / max(accepted.sum(), 1))
        model_stats.append((model_id, recall, fvr))
    stat = {mid: (recall, fvr) for mid, recall, fvr in model_stats}
    a_recall = stat.get("M_A_ONLY", (float("nan"), float("nan")))[0]
    acp_recall = stat.get("M_A_CP", (float("nan"), float("nan")))[0]
    shuffle_recall = stat.get("M_A_CP_SHUFFLED", (float("nan"), float("nan")))[0]
    rows.append({"gate_id": "GATE_VALIDITY_A_CP_GT_A_ONLY", "metric": "valid_recall_at_score_0p5", "reference": float(a_recall), "proposed": float(acp_recall), "negative_control": float(shuffle_recall), "delta_vs_reference": float(acp_recall - a_recall), "delta_vs_negative_control": float(acp_recall - shuffle_recall), "pass": bool(acp_recall > a_recall and acp_recall > shuffle_recall)})
    return pd.DataFrame(rows)


def build_recommended_simulation_order() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("S0", "positive_case_reproduction", "Run tiny clean scene with known PA/VA to prove old positive signature is reproducible."),
            ("S1", "path_truth_peak_overlap", "Lock path_truth, overlap_group, and peak tables before any SLAM interpretation."),
            ("S2", "cp_rssd_features", "Generate polarimetric, CP, and RSSD features on the same measurement ids."),
            ("S3", "threshold_stress", "Compare A-only, CP-only, A+CP, and shuffled CP near the detection threshold."),
            ("S4", "known_va_localization", "Solve position with known candidate VA map to validate likelihood geometry."),
            ("S5", "bp_slam_range_amplitude", "Run B0-B3 range/amplitude baselines before CP factors."),
            ("S6", "cp_aware_ablation", "Run B4-B11 plus oracle upper bounds B12-B14 and raw-CIR placeholder B15."),
            ("S7", "sequential_hardware_stress", "Sweep RHCP/LHCP switch interval and AMR speed after CP feature gains are visible."),
        ],
        columns=["stage_id", "recommended_order", "rationale"],
    )


def write_result_summary(output_dir: Path, tables: dict[str, pd.DataFrame]) -> None:
    ablation = tables.get("ablation_table.csv", pd.DataFrame())
    claims = tables.get("claim_gate_summary.csv", pd.DataFrame())
    regimes = tables.get("stage01_regime_summary.csv", pd.DataFrame())
    lines = [
        "# SIM_NEW_CP_VA_SLAM_01 Stress-Test Solve Summary",
        "",
        "This run executes Stage 0-7 with stress-regime oversampling and a lightweight particle BP data-association solver for B0-B15 ablations.",
        "",
        "## Core row counts",
        "",
    ]
    for name in [
        "path_truth_table.csv",
        "overlap_group_table.csv",
        "peak_table.csv",
        "cp_feature_table.csv",
        "threshold_sweep_table.csv",
        "slam_result_table.csv",
        "slam_da_result_table.csv",
        "metric_by_regime_table.csv",
        "ablation_table.csv",
    ]:
        if name in tables:
            lines.append(f"- `{name}`: {len(tables[name])}")
    if len(regimes):
        lines.extend(["", "## Regime coverage", ""])
        for row in regimes.itertuples(index=False):
            lines.append(f"- `{row.regime_id}` `{row.regime_name}`: {row.num_overlap_groups}")
    if len(ablation):
        lines.extend(["", "## Ablation headline", ""])
        for alg in ["B3", "B9", "B10", "B12", "B13"]:
            part = ablation[ablation["algorithm_id"].eq(alg)]
            if len(part):
                row = part.iloc[0]
                lines.append(
                    f"- `{alg}` RMSE={float(row.position_rmse_m):.4f} m, "
                    f"VA MOSPA={float(row.va_mospa_m):.4f} m, DA error={float(row.da_error_rate):.4f}"
                )
    if len(claims):
        lines.extend(["", "## Claim gates", ""])
        for _, row in claims.iterrows():
            lines.append(f"- `{row['gate_id']}` pass={bool(row['pass'])} delta_ref={float(row['delta_vs_reference']):.6g}")
    lines.extend(
        [
            "",
            "## Solver boundary",
            "",
            "The solver is a local lightweight particle BP/DA implementation over PA/VA candidate features, not a full reimplementation of every Leitinger publication detail.",
            "It is sufficient for stress-test table generation and factor-level ablation, while final paper claims still require an independent solver audit and scale sweep.",
            "",
        ]
    )
    (output_dir / "RESULT_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def build_sequential_reconfig_table(trajectory_truth: pd.DataFrame, cp_features: pd.DataFrame) -> pd.DataFrame:
    cp_by_time = cp_features.groupby(["sequence_id", "time_idx"], sort=True)["cp3_core_1"].mean()
    switch_intervals = [10e-6, 100e-6, 1e-3, 10e-3, 100e-3, 1.0]
    wavelength_m = C0 / DEFAULT_CENTER_FREQUENCY_HZ
    rows = []
    for row in trajectory_truth.itertuples(index=False):
        base_feature = float(cp_by_time.get((row.sequence_id, int(row.time_idx)), 0.5))
        for switch in switch_intervals:
            path_change = float(row.v_mps) * switch
            phase_change = 2.0 * math.pi * path_change / wavelength_m
            feature_error = min(1.0, abs(phase_change) / math.pi) * 0.2 + min(1.0, path_change / 0.05) * 0.1
            rows.append(
                {
                    "sequence_id": row.sequence_id,
                    "time_idx": int(row.time_idx),
                    "snapshot_pair_id": f"{row.sequence_id}_t{int(row.time_idx):04d}_sw{switch:g}",
                    "switch_interval_s": switch,
                    "agent_speed_mps": float(row.v_mps),
                    "path_length_change_m": path_change,
                    "phase_change_rad": phase_change,
                    "amp_jitter_db": 20.0 * math.log10(1.0 + path_change),
                    "delay_jitter_s": path_change / C0,
                    "rhcp_time_s": float(row.time_s),
                    "lhcp_time_s": float(row.time_s) + switch,
                    "simultaneous_cp_feature": base_feature,
                    "sequential_cp_feature": float(np.clip(base_feature - feature_error, 0.0, 1.0)),
                    "feature_error": feature_error,
                    "quasi_static_pass_magnitude": bool(path_change < 0.01),
                    "quasi_static_pass_phase": bool(abs(phase_change) < 0.25),
                    "recommended_mode": "magnitude_only" if path_change < 0.05 else "simultaneous_dual_cp_required",
                }
            )
    return pd.DataFrame(rows)


def build_figure_manifest() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "figure_id": "F01_overlap_regime_counts",
                "figure_type": "bar",
                "source_table": "stage01_regime_summary.csv",
                "x_axis": "regime_id",
                "y_axis": "num_overlap_groups",
                "group_by": "",
                "filter_condition": "",
                "output_path": "figures/F01_overlap_regime_counts.png",
                "caption_short": "Stage 0/1 generated path-regime coverage.",
                "claim_supported": "path-regime coverage only",
            },
            {
                "figure_id": "F02_ablation_position_tail",
                "figure_type": "bar",
                "source_table": "metric_by_regime_table.csv",
                "x_axis": "algorithm_id",
                "y_axis": "position_p95_m",
                "group_by": "regime_id",
                "filter_condition": "regime_id in positive regimes",
                "output_path": "figures/F02_ablation_position_tail.png",
                "caption_short": "CP-aware ablation tail-risk comparison by regime.",
                "claim_supported": "lightweight particle BP stress-test solve",
            },
        ]
    )


def _add_complex_cir_pulse(
    buffer: np.ndarray,
    center_index: float,
    width_samples: float,
    amplitude: float,
    phase_rad: float,
    gaussian: bool,
) -> None:
    if not np.isfinite(center_index) or not np.isfinite(amplitude):
        return
    if not gaussian:
        idx = int(np.clip(round(center_index), 0, len(buffer) - 1))
        buffer[idx] += float(amplitude) * complex(math.cos(float(phase_rad)), math.sin(float(phase_rad)))
        return
    sigma = max(0.75, float(width_samples) / 2.355)
    start = max(0, int(math.floor(float(center_index) - 5.0 * sigma)))
    stop = min(len(buffer), int(math.ceil(float(center_index) + 5.0 * sigma)) + 1)
    if stop <= start:
        return
    idx = np.arange(start, stop, dtype=float)
    envelope = np.exp(-0.5 * ((idx - float(center_index)) / sigma) ** 2)
    buffer[start:stop] += float(amplitude) * envelope * complex(math.cos(float(phase_rad)), math.sin(float(phase_rad)))


def _h10b_cir_channel_db_for_peak(
    peak,
    path_lookup: pd.DataFrame | None,
    legacy_lut: pd.DataFrame,
    config: Stage01Config,
) -> tuple[dict[str, float], dict[str, object]]:
    if legacy_lut.empty or path_lookup is None:
        return {}, {}
    path_id = str(getattr(peak, "nearest_truth_path_id", ""))
    if path_id not in path_lookup.index:
        return {}, {}
    path = path_lookup.loc[path_id]
    theta = float(path.get("theta_elevation_deg", float("nan")))
    range_m = float(path.get("path_length_m", getattr(peak, "peak_range_m", float("nan"))))
    if not (np.isfinite(theta) and np.isfinite(range_m)):
        return {}, {}
    lut_row = _select_legacy_dual_tag_lut_row(legacy_lut, theta, range_m)
    power_offset_mode = normalize_legacy_dual_tag_power_offset_mode(config.legacy_dual_tag_power_offset_mode)
    channel_cols = ["RSS_ant1_RH_db", "RSS_ant1_LH_db", "RSS_ant2_RH_db", "RSS_ant2_LH_db"]
    raw = {col: float(lut_row[col]) for col in channel_cols}
    raw_mean = float(np.nanmean(list(raw.values())))
    offset_db = float(getattr(peak, "peak_amp_db", raw_mean)) - raw_mean if power_offset_mode == "match_existing_amp" else 0.0
    channel_db = {col: value + offset_db for col, value in raw.items()}
    meta = {
        "legacy_dual_tag_lut_case_id": _row_get(lut_row, "case_id", ""),
        "legacy_dual_tag_lut_source_case_id": _row_get(lut_row, "source_case_id", ""),
        "legacy_dual_tag_lut_theta_abs_deg": float(lut_row["legacy_h10b_theta_abs_deg"]),
        "legacy_dual_tag_lut_range_m": float(lut_row["legacy_h10b_range_m"]),
        "legacy_dual_tag_cir_power_offset_db": offset_db,
        "legacy_dual_tag_match_theta_error_deg": abs(float(lut_row["legacy_h10b_theta_abs_deg"]) - abs(theta)),
        "legacy_dual_tag_match_range_error_m": float(lut_row["legacy_h10b_range_m"]) - range_m,
    }
    return channel_db, meta


def _tilted_real_pattern_cir_channel_db_for_peak(
    peak,
    path_lookup: pd.DataFrame | None,
    config: Stage01Config,
) -> tuple[dict[str, float], dict[str, object]]:
    if path_lookup is None:
        return {}, {}
    path_id = str(getattr(peak, "nearest_truth_path_id", ""))
    if path_id not in path_lookup.index:
        return {}, {}
    path = path_lookup.loc[path_id]
    beta = float(path.get("rx_arrival_beta_body_deg", float("nan")))
    theta = float(path.get("theta_elevation_deg", float("nan")))
    if not (np.isfinite(beta) and np.isfinite(theta)):
        return {}, {}
    gains = tilted_real_pattern_channel_gains_db(beta, theta, config)
    gain_scalar = {key: float(np.ravel(value)[0]) for key, value in gains.items()}
    base_power_db = float(getattr(peak, "peak_amp_db", _row_get(path, "amplitude_db", 0.0)))
    raw = {key: base_power_db + gain for key, gain in gain_scalar.items()}
    raw_mean = float(np.nanmean(list(raw.values())))
    offset_db = base_power_db - raw_mean if np.isfinite(raw_mean) else 0.0
    channel_db = {key: value + offset_db for key, value in raw.items()}
    meta = {
        "tilted_real_pattern_cir_power_offset_db": offset_db,
        "tilted_real_pattern_gain_ant1_rh_db": gain_scalar["RSS_ant1_RH_db"],
        "tilted_real_pattern_gain_ant1_lh_db": gain_scalar["RSS_ant1_LH_db"],
        "tilted_real_pattern_gain_ant2_rh_db": gain_scalar["RSS_ant2_RH_db"],
        "tilted_real_pattern_gain_ant2_lh_db": gain_scalar["RSS_ant2_LH_db"],
    }
    return channel_db, meta


def write_cir_raw(
    output_dir: Path,
    trajectory_truth: pd.DataFrame,
    peak_table: pd.DataFrame,
    path_truth: pd.DataFrame | None = None,
    config: Stage01Config | None = None,
) -> pd.DataFrame:
    import h5py

    cfg = config or Stage01Config(output_dir=Path("."))
    tag_model = normalize_tag_antenna_model_mode(cfg.tag_antenna_model_mode)
    use_legacy_h10b = tag_model == "legacy_h10b_dual_tilted"
    use_tilted_real = tag_model == "tilted_real_pattern"
    use_h10b_vector = use_legacy_h10b or use_tilted_real
    legacy_lut = load_legacy_dual_tag_h10b_lut(cfg) if use_legacy_h10b else pd.DataFrame()
    path_lookup = path_truth.set_index("path_truth_id") if path_truth is not None and len(path_truth) else None
    sample_period_s = 0.25e-9
    if use_h10b_vector and len(peak_table):
        max_delay_s = float(pd.to_numeric(peak_table["peak_delay_s"], errors="coerce").max())
        num_samples = max(128, int(math.ceil(max_delay_s / sample_period_s)) + 32)
    else:
        num_samples = 128
    output_dir.mkdir(parents=True, exist_ok=True)
    h5_path = output_dir / "cir_raw.h5"
    rows = []
    peak_by_time = peak_table.groupby(["sequence_id", "time_idx"], sort=True)
    with h5py.File(h5_path, "w") as h5:
        for row in trajectory_truth.itertuples(index=False):
            sequence_id = str(row.sequence_id)
            time_idx = int(row.time_idx)
            group = h5.require_group(f"h/{sequence_id}/{time_idx}")
            if use_h10b_vector:
                channels = {
                    "ANT1_RHCP": np.zeros(num_samples, dtype=np.complex128),
                    "ANT1_LHCP": np.zeros(num_samples, dtype=np.complex128),
                    "ANT2_RHCP": np.zeros(num_samples, dtype=np.complex128),
                    "ANT2_LHCP": np.zeros(num_samples, dtype=np.complex128),
                }
            else:
                impulse = np.zeros(num_samples, dtype=np.complex128)
            if (sequence_id, time_idx) in peak_by_time.groups:
                peaks = peak_by_time.get_group((sequence_id, time_idx))
                for peak in peaks.itertuples(index=False):
                    center_idx = float(peak.peak_delay_s) / sample_period_s
                    width_samples = max(1.0, float(getattr(peak, "peak_width_s", sample_period_s)) / sample_period_s)
                    if use_h10b_vector:
                        if use_legacy_h10b:
                            channel_db, _meta = _h10b_cir_channel_db_for_peak(peak, path_lookup, legacy_lut, cfg)
                        else:
                            channel_db, _meta = _tilted_real_pattern_cir_channel_db_for_peak(peak, path_lookup, cfg)
                        if not channel_db:
                            peak_amp = float(peak.peak_amp_db)
                            channel_db = {
                                "RSS_ant1_RH_db": peak_amp,
                                "RSS_ant1_LH_db": peak_amp - 3.0,
                                "RSS_ant2_RH_db": peak_amp - 1.0,
                                "RSS_ant2_LH_db": peak_amp - 4.0,
                            }
                        mapping = {
                            "ANT1_RHCP": "RSS_ant1_RH_db",
                            "ANT1_LHCP": "RSS_ant1_LH_db",
                            "ANT2_RHCP": "RSS_ant2_RH_db",
                            "ANT2_LHCP": "RSS_ant2_LH_db",
                        }
                        for channel_name, db_col in mapping.items():
                            amp = 10.0 ** (float(channel_db[db_col]) / 20.0)
                            _add_complex_cir_pulse(
                                channels[channel_name],
                                center_idx,
                                width_samples,
                                amp,
                                float(peak.peak_phase_rad),
                                gaussian=True,
                            )
                    else:
                        amp = 10.0 ** (float(peak.peak_amp_db) / 20.0)
                        _add_complex_cir_pulse(
                            impulse,
                            center_idx,
                            width_samples,
                            amp,
                            float(peak.peak_phase_rad),
                            gaussian=False,
                        )
            if use_h10b_vector:
                rh = 0.5 * (channels["ANT1_RHCP"] + channels["ANT2_RHCP"])
                lh = 0.5 * (channels["ANT1_LHCP"] + channels["ANT2_LHCP"])
                lp1 = 0.5 * (rh + lh)
                datasets = [("RHCP", rh), ("LHCP", lh), ("LP1", lp1), *channels.items()]
                channel_id = "legacy_h10b_dual_tag_raw_cir" if use_legacy_h10b else "tilted_real_pattern_h10b_raw_cir"
                channel_set = "ANT1_RHCP,ANT1_LHCP,ANT2_RHCP,ANT2_LHCP"
            else:
                rh = impulse
                lh = 0.65 * impulse * np.exp(1j * 0.2)
                lp1 = 0.5 * (rh + lh)
                datasets = [("RHCP", rh), ("LHCP", lh), ("LP1", lp1)]
                channel_id = "stage02_cir_proxy"
                channel_set = "RHCP,LHCP,LP1"
            for name, data in datasets:
                group.create_dataset(f"{name}_real", data=np.real(data))
                group.create_dataset(f"{name}_imag", data=np.imag(data))
            rows.append(
                {
                    "sequence_id": sequence_id,
                    "time_idx": time_idx,
                    "snapshot_id": f"{sequence_id}_t{time_idx:04d}",
                    "rx_pol_state": "dual",
                    "channel_id": channel_id,
                    "hdf5_path": f"/h/{sequence_id}/{time_idx}",
                    "num_samples": num_samples,
                    "sample_period_s": sample_period_s,
                    "t0_s": 0.0,
                    "noise_power": 10.0 ** (-35.0 / 10.0),
                    "normalization": "linear_voltage_proxy",
                    "raw_cir_channel_set": channel_set,
                    "tag_antenna_model_mode": tag_model,
                    "range_estimator_mode": normalize_range_estimator_mode(cfg.range_estimator_mode),
                }
            )
    return pd.DataFrame(rows)


def _snapshot_channel_powers_from_h5_group(group) -> tuple[dict[str, np.ndarray], str]:
    preferred = ["ANT1_RHCP", "ANT1_LHCP", "ANT2_RHCP", "ANT2_LHCP"]
    fallback = ["RHCP", "LHCP", "LP1"]
    names = preferred if all(f"{name}_real" in group and f"{name}_imag" in group for name in preferred) else fallback
    powers: dict[str, np.ndarray] = {}
    used = []
    for name in names:
        real_key = f"{name}_real"
        imag_key = f"{name}_imag"
        if real_key not in group or imag_key not in group:
            continue
        signal = np.asarray(group[real_key], dtype=float) + 1j * np.asarray(group[imag_key], dtype=float)
        powers[name] = np.abs(signal) ** 2
        used.append(name)
    return powers, ",".join(used)


def _snapshot_power_from_h5_group(group) -> tuple[np.ndarray, str]:
    powers, channel_set = _snapshot_channel_powers_from_h5_group(group)
    if not powers:
        return np.zeros(0, dtype=float), ""
    power = None
    for channel_power in powers.values():
        power = channel_power if power is None else power + channel_power
    return np.asarray(power, dtype=float), channel_set


def _estimate_dw_lde_from_power(
    power: np.ndarray,
    expected_delay_s: float,
    width_s: float,
    sample_period_s: float,
    t0_s: float,
    threshold_fraction: float,
) -> dict[str, float | str]:
    if len(power) == 0 or not np.isfinite(expected_delay_s):
        return {
            "raw_cir_lde_delay_s": float("nan"),
            "raw_cir_lde_range_m": float("nan"),
            "raw_cir_peak_index": float("nan"),
            "raw_cir_lde_index": float("nan"),
            "raw_cir_noise_floor": float("nan"),
            "raw_cir_threshold": float("nan"),
            "raw_cir_peak_power": float("nan"),
            "raw_cir_peak_amplitude_db": float("nan"),
            "raw_cir_estimator_status": "missing_cir",
        }
    expected_idx = float((expected_delay_s - t0_s) / sample_period_s)
    width_samples = max(2.0, float(width_s) / max(float(sample_period_s), EPS))
    half_window = int(max(8, math.ceil(width_samples * 6.0)))
    start = max(0, int(math.floor(expected_idx - half_window)))
    stop = min(len(power), int(math.ceil(expected_idx + half_window)) + 1)
    if stop <= start:
        return {
            "raw_cir_lde_delay_s": float("nan"),
            "raw_cir_lde_range_m": float("nan"),
            "raw_cir_peak_index": float("nan"),
            "raw_cir_lde_index": float("nan"),
            "raw_cir_noise_floor": float("nan"),
            "raw_cir_threshold": float("nan"),
            "raw_cir_peak_power": float("nan"),
            "raw_cir_peak_amplitude_db": float("nan"),
            "raw_cir_estimator_status": "empty_search_window",
        }
    local = np.asarray(power[start:stop], dtype=float)
    if not np.any(np.isfinite(local)):
        return {
            "raw_cir_lde_delay_s": float("nan"),
            "raw_cir_lde_range_m": float("nan"),
            "raw_cir_peak_index": float("nan"),
            "raw_cir_lde_index": float("nan"),
            "raw_cir_noise_floor": float("nan"),
            "raw_cir_threshold": float("nan"),
            "raw_cir_peak_power": float("nan"),
            "raw_cir_peak_amplitude_db": float("nan"),
            "raw_cir_estimator_status": "nonfinite_power",
        }
    peak_local = int(np.nanargmax(local))
    peak_index = start + peak_local
    noise_floor = float(np.nanpercentile(np.maximum(local, 0.0), 10.0))
    peak_power = float(max(local[peak_local], noise_floor))
    threshold = noise_floor + float(np.clip(threshold_fraction, 0.0, 1.0)) * max(peak_power - noise_floor, 0.0)
    leading_local = None
    for idx in range(0, peak_local + 1):
        if local[idx] >= threshold:
            leading_local = idx
            break
    if leading_local is None:
        lde_index = float(peak_index)
        status = "threshold_not_crossed_peak_fallback"
    else:
        absolute_idx = start + leading_local
        if leading_local > 0:
            prev_value = float(local[leading_local - 1])
            curr_value = float(local[leading_local])
            denom = curr_value - prev_value
            frac = 0.0 if abs(denom) <= EPS else float(np.clip((threshold - prev_value) / denom, 0.0, 1.0))
            lde_index = float(absolute_idx - 1 + frac)
        else:
            lde_index = float(absolute_idx)
        status = "ok"
    delay_s = float(t0_s + lde_index * sample_period_s)
    return {
        "raw_cir_lde_delay_s": delay_s,
        "raw_cir_lde_range_m": delay_s * C0,
        "raw_cir_peak_index": float(peak_index),
        "raw_cir_lde_index": float(lde_index),
        "raw_cir_noise_floor": noise_floor,
        "raw_cir_threshold": float(threshold),
        "raw_cir_peak_power": peak_power,
        "raw_cir_peak_amplitude_db": float(10.0 * math.log10(max(peak_power, EPS))),
        "raw_cir_estimator_status": status,
    }


RAW_CIR_LDE_COLUMNS = [
    "sequence_id",
    "time_idx",
    "measurement_id",
    "peak_id",
    "expected_peak_delay_s",
    "expected_peak_range_m",
    "peak_width_s",
    "hdf5_path",
    "sample_period_s",
    "t0_s",
    "raw_cir_channel_set",
    "raw_cir_selected_channel",
    "raw_cir_vector_mode",
    "range_estimator_mode",
    "lde_relative_threshold",
    "raw_cir_lde_delay_s",
    "raw_cir_lde_range_m",
    "raw_cir_peak_index",
    "raw_cir_lde_index",
    "raw_cir_noise_floor",
    "raw_cir_threshold",
    "raw_cir_peak_power",
    "raw_cir_peak_amplitude_db",
    "raw_cir_estimator_status",
    "h10b_channel_vector_order",
    "h10b_range_vector_m",
    "h10b_amplitude_vector_db",
    "h10b_lde_delay_vector_s",
    "h10b_status_vector",
    "h10b_ant1_pol_range_delta_m",
    "h10b_ant2_pol_range_delta_m",
    "h10b_rhcp_ant_range_delta_m",
    "h10b_lhcp_ant_range_delta_m",
    "h10b_cross_pol_range_delta_m",
    *h10b_raw_cir_vector_columns(),
]


def build_raw_cir_lde_table(
    output_dir: Path,
    peak_table: pd.DataFrame,
    cir_raw_index: pd.DataFrame,
    config: Stage01Config,
) -> pd.DataFrame:
    import h5py

    rows = []
    if not range_estimator_uses_raw_cir(config.range_estimator_mode):
        return pd.DataFrame(columns=RAW_CIR_LDE_COLUMNS)
    h5_path = output_dir / "cir_raw.h5"
    if not h5_path.exists() or not len(peak_table) or not len(cir_raw_index):
        return pd.DataFrame(columns=RAW_CIR_LDE_COLUMNS)
    index_lookup = cir_raw_index.set_index(["sequence_id", "time_idx"])
    with h5py.File(h5_path, "r") as h5:
        for peak in peak_table.itertuples(index=False):
            key = (str(peak.sequence_id), int(peak.time_idx))
            measurement_id = str(peak.peak_id).replace("_pk", "_m")
            if key not in index_lookup.index:
                rows.append(
                    {
                        "sequence_id": peak.sequence_id,
                        "time_idx": int(peak.time_idx),
                        "measurement_id": measurement_id,
                        "raw_cir_estimator_status": "missing_index_row",
                    }
                )
                continue
            idx_row = index_lookup.loc[key]
            hdf5_path = str(idx_row.hdf5_path)
            if hdf5_path not in h5:
                rows.append(
                    {
                        "sequence_id": peak.sequence_id,
                        "time_idx": int(peak.time_idx),
                        "measurement_id": measurement_id,
                        "raw_cir_estimator_status": "missing_hdf5_group",
                    }
                )
                continue
            channel_powers, channel_set = _snapshot_channel_powers_from_h5_group(h5[hdf5_path])
            channel_estimates: dict[str, dict[str, float | str]] = {}
            for channel_name, power in channel_powers.items():
                channel_estimates[channel_name] = _estimate_dw_lde_from_power(
                    power,
                    float(peak.peak_delay_s),
                    float(peak.peak_width_s),
                    float(idx_row.sample_period_s),
                    float(idx_row.t0_s),
                    float(config.lde_relative_threshold),
                )
            valid_estimates = [
                (channel_name, estimate)
                for channel_name, estimate in channel_estimates.items()
                if np.isfinite(float(estimate.get("raw_cir_lde_delay_s", float("nan"))))
                and np.isfinite(float(estimate.get("raw_cir_lde_range_m", float("nan"))))
            ]
            if valid_estimates:
                selected_channel, estimate = min(
                    valid_estimates,
                    key=lambda item: float(item[1].get("raw_cir_lde_delay_s", float("inf"))),
                )
            else:
                selected_channel = ""
                estimate = _estimate_dw_lde_from_power(
                    np.zeros(0, dtype=float),
                    float("nan"),
                    float(peak.peak_width_s),
                    float(idx_row.sample_period_s),
                    float(idx_row.t0_s),
                    float(config.lde_relative_threshold),
                )
            vector_order = [channel for channel in H10B_RAW_CIR_CHANNELS if channel in channel_estimates]
            if not vector_order:
                vector_order = list(channel_estimates)

            def _finite_or_none(value: object) -> float | None:
                try:
                    out = float(value)
                except (TypeError, ValueError):
                    return None
                return out if np.isfinite(out) else None

            def _json_vector(field: str) -> str:
                raw_key = {
                    "lde_delay_s": "raw_cir_lde_delay_s",
                    "range_m": "raw_cir_lde_range_m",
                    "amplitude_db": "raw_cir_peak_amplitude_db",
                    "status": "raw_cir_estimator_status",
                }[field]
                values = []
                for channel in vector_order:
                    value = channel_estimates.get(channel, {}).get(raw_key, None)
                    values.append(str(value) if field == "status" else _finite_or_none(value))
                return json.dumps(values, ensure_ascii=True)

            vector_payload: dict[str, object] = {
                "raw_cir_selected_channel": selected_channel,
                "raw_cir_vector_mode": "per_channel_lde_earliest_valid_scalar_bridge",
                "h10b_channel_vector_order": ";".join(vector_order),
                "h10b_range_vector_m": _json_vector("range_m"),
                "h10b_amplitude_vector_db": _json_vector("amplitude_db"),
                "h10b_lde_delay_vector_s": _json_vector("lde_delay_s"),
                "h10b_status_vector": _json_vector("status"),
            }
            for channel in H10B_RAW_CIR_CHANNELS:
                prefix = f"h10b_{H10B_RAW_CIR_CHANNEL_SUFFIX[channel]}"
                channel_est = channel_estimates.get(channel, {})
                vector_payload.update(
                    {
                        f"{prefix}_lde_delay_s": _finite_or_none(channel_est.get("raw_cir_lde_delay_s")),
                        f"{prefix}_range_m": _finite_or_none(channel_est.get("raw_cir_lde_range_m")),
                        f"{prefix}_peak_index": _finite_or_none(channel_est.get("raw_cir_peak_index")),
                        f"{prefix}_lde_index": _finite_or_none(channel_est.get("raw_cir_lde_index")),
                        f"{prefix}_noise_floor": _finite_or_none(channel_est.get("raw_cir_noise_floor")),
                        f"{prefix}_threshold": _finite_or_none(channel_est.get("raw_cir_threshold")),
                        f"{prefix}_peak_power": _finite_or_none(channel_est.get("raw_cir_peak_power")),
                        f"{prefix}_amplitude_db": _finite_or_none(channel_est.get("raw_cir_peak_amplitude_db")),
                        f"{prefix}_status": str(channel_est.get("raw_cir_estimator_status", "")),
                    }
                )

            def _range_for(channel: str) -> float:
                return float(vector_payload.get(f"h10b_{H10B_RAW_CIR_CHANNEL_SUFFIX[channel]}_range_m") or float("nan"))

            ant1_rh = _range_for("ANT1_RHCP")
            ant1_lh = _range_for("ANT1_LHCP")
            ant2_rh = _range_for("ANT2_RHCP")
            ant2_lh = _range_for("ANT2_LHCP")
            vector_payload["h10b_ant1_pol_range_delta_m"] = ant1_rh - ant1_lh if np.isfinite(ant1_rh) and np.isfinite(ant1_lh) else float("nan")
            vector_payload["h10b_ant2_pol_range_delta_m"] = ant2_rh - ant2_lh if np.isfinite(ant2_rh) and np.isfinite(ant2_lh) else float("nan")
            vector_payload["h10b_rhcp_ant_range_delta_m"] = ant1_rh - ant2_rh if np.isfinite(ant1_rh) and np.isfinite(ant2_rh) else float("nan")
            vector_payload["h10b_lhcp_ant_range_delta_m"] = ant1_lh - ant2_lh if np.isfinite(ant1_lh) and np.isfinite(ant2_lh) else float("nan")
            rh_vals = [value for value in (ant1_rh, ant2_rh) if np.isfinite(value)]
            lh_vals = [value for value in (ant1_lh, ant2_lh) if np.isfinite(value)]
            vector_payload["h10b_cross_pol_range_delta_m"] = (
                float(np.mean(rh_vals) - np.mean(lh_vals)) if rh_vals and lh_vals else float("nan")
            )
            rows.append(
                {
                    "sequence_id": peak.sequence_id,
                    "time_idx": int(peak.time_idx),
                    "measurement_id": measurement_id,
                    "peak_id": peak.peak_id,
                    "expected_peak_delay_s": float(peak.peak_delay_s),
                    "expected_peak_range_m": float(peak.peak_range_m),
                    "peak_width_s": float(peak.peak_width_s),
                    "hdf5_path": hdf5_path,
                    "sample_period_s": float(idx_row.sample_period_s),
                    "t0_s": float(idx_row.t0_s),
                    "raw_cir_channel_set": channel_set,
                    "range_estimator_mode": normalize_range_estimator_mode(config.range_estimator_mode),
                    "lde_relative_threshold": float(config.lde_relative_threshold),
                    **estimate,
                    **vector_payload,
                }
            )
    return pd.DataFrame(rows, columns=RAW_CIR_LDE_COLUMNS)




def git_commit_hash(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return "not_available"
    return proc.stdout.strip() or "not_available"


def stable_config_hash(config: Stage01Config) -> str:
    payload: dict[str, object] = {}
    for key, value in vars(config).items():
        payload[key] = str(value) if isinstance(value, Path) else value
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def build_run_manifest(config: Stage01Config, root: Path, counts: dict[str, int]) -> pd.DataFrame:
    yaw_mode = str(config.orientation_control_mode).strip().lower()
    if bool(config.disable_orientation):
        yaw_mode = "zero"
    if bool(config.yaw_shuffle):
        yaw_mode = "yaw_shuffle"
    if yaw_mode == "nominal" and float(config.yaw_noise_deg) > 0.0:
        yaw_mode = "yaw_noise"
    rssd_mode = str(config.rssd_control_mode).strip().lower()
    if bool(config.disable_rssd):
        rssd_mode = "zero"
    if bool(config.rssd_sign_flip):
        rssd_mode = "sign_flip"
    if bool(config.rssd_shuffle):
        rssd_mode = "shuffle"
    if rssd_mode == "nominal" and (float(config.rssd_noise_std_db) > 0.0 or float(config.rssd_noise_scale) > 0.0):
        rssd_mode = "noise"
    yaw_shuffle_level = _normalize_shuffle_level(str(config.yaw_shuffle_level), "yaw_shuffle_level")
    rssd_shuffle_level = _normalize_shuffle_level(str(config.rssd_shuffle_level), "rssd_shuffle_level")
    yaw_noise_deg = max(0.0, float(config.yaw_noise_deg))
    yaw_shuffle_seed = (
        folded_seed(
            config.random_seed,
            config.perturbation_config_id,
            "orientation_negative_control",
            yaw_mode,
            yaw_noise_deg,
            yaw_shuffle_level,
            float(config.yaw_fixed_deg),
        )
        if yaw_mode == "yaw_shuffle"
        else 0
    )
    rssd_noise_std_db = max(0.0, float(config.rssd_noise_std_db))
    if rssd_noise_std_db <= 0.0 and float(config.rssd_noise_scale) > 0.0:
        rssd_noise_std_db = max(0.0, float(config.rssd_noise_scale))
    rssd_shuffle_seed = (
        folded_seed(
            config.random_seed,
            config.perturbation_config_id,
            "rssd_negative_control",
            rssd_mode,
            rssd_noise_std_db,
            rssd_shuffle_level,
        )
        if rssd_mode == "shuffle"
        else 0
    )
    return pd.DataFrame(
        [
            {
                "run_id": config.run_id,
                "simulation_name": config.simulation_name,
                "branch_id": config.branch_id,
                "date_time": datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds"),
                "code_version": "stage01_python_generator_v1",
                "git_commit_hash": git_commit_hash(root),
                "random_seed": config.random_seed,
                "solver_name": "rt_cp_uwb_py.sim_new_cp_va_slam",
                "solver_version": "stage01_v1",
                "ray_engine": "image_method_specular",
                "frequency_hz": config.frequency_hz,
                "bandwidth_hz": config.bandwidth_hz,
                "time_resolution_s": config.time_resolution_s,
                "distance_resolution_m": config.distance_resolution_m,
                "range_estimator_mode": normalize_range_estimator_mode(config.range_estimator_mode),
                "lde_relative_threshold": float(config.lde_relative_threshold),
                "lde_noise_scale": float(config.lde_noise_scale),
                "num_rooms": counts.get("num_rooms", 0),
                "num_trajectories": counts.get("num_trajectories", 0),
                "num_snapshots": counts.get("num_snapshots", 0),
                "num_paths_max": config.num_paths_max,
                "polarization_mode": normalize_polarization_mode(config.polarization_mode),
                "anchor_linear_pol_axis_deg": config.anchor_linear_pol_axis_deg,
                "tag_ant1_linear_pol_axis_deg": config.tag_ant1_linear_pol_axis_deg,
                "tag_ant2_linear_pol_axis_deg": config.tag_ant2_linear_pol_axis_deg,
                "tag_pol_tilt_deg": config.tag_pol_tilt_deg,
                "anchor_pol_tilt_deg": config.anchor_pol_tilt_deg,
                "tag_antenna_model_mode": normalize_tag_antenna_model_mode(config.tag_antenna_model_mode),
                "legacy_dual_tag_artifact_path": str(config.legacy_dual_tag_artifact_path),
                "legacy_dual_tag_rssd_channel": normalize_legacy_dual_tag_rssd_channel(config.legacy_dual_tag_rssd_channel),
                "legacy_dual_tag_alpha_deg": float(config.legacy_dual_tag_alpha_deg),
                "legacy_dual_tag_rotation_deg": float(config.legacy_dual_tag_rotation_deg),
                "legacy_dual_tag_rssd_prediction_mode": normalize_legacy_dual_tag_rssd_prediction_mode(
                    config.legacy_dual_tag_rssd_prediction_mode,
                    config.tag_antenna_model_mode,
                ),
                "legacy_dual_tag_power_offset_mode": (
                    normalize_legacy_dual_tag_power_offset_mode(config.legacy_dual_tag_power_offset_mode)
                    if normalize_tag_antenna_model_mode(config.tag_antenna_model_mode) == "legacy_h10b_dual_tilted"
                    else ""
                ),
                "lp_copol_gain_pattern_file": str(config.lp_copol_gain_pattern_file),
                "lp_crosspol_gain_pattern_file": str(config.lp_crosspol_gain_pattern_file),
                "rx_ant1_rhcp_pattern_file": str(config.rx_ant1_rhcp_pattern_file),
                "rx_ant1_lhcp_pattern_file": str(config.rx_ant1_lhcp_pattern_file),
                "rx_ant2_rhcp_pattern_file": str(config.rx_ant2_rhcp_pattern_file),
                "rx_ant2_lhcp_pattern_file": str(config.rx_ant2_lhcp_pattern_file),
                "tag_attitude_source": str(config.tag_attitude_source),
                "tag_pitch_deg": float(config.tag_pitch_deg),
                "tag_roll_deg": float(config.tag_roll_deg),
                "rx_ant1_mount_rotation": str(config.rx_ant1_mount_rotation),
                "rx_ant2_mount_rotation": str(config.rx_ant2_mount_rotation),
                "pattern_gain_normalization": str(config.pattern_gain_normalization),
                "pattern_phase_convention": str(config.pattern_phase_convention),
                "pattern_pol_basis": str(config.pattern_pol_basis),
                "use_te_tm_reflection": bool(config.use_te_tm_reflection),
                "material_fresnel_model": str(config.material_fresnel_model),
                "path_polarization_tracking": bool(config.path_polarization_tracking),
                "wall_offset_noise_m": float(config.wall_offset_noise_m),
                "wall_normal_noise_deg": float(config.wall_normal_noise_deg),
                "odometry_noise_scale": float(config.odometry_noise_scale),
                "range_variance_scale": float(config.range_variance_scale),
                "perturbation_config_id": str(config.perturbation_config_id),
                "measurement_regularizer_target": str(config.measurement_regularizer_target),
                "measurement_regularizer_centered_cap": float(config.measurement_regularizer_centered_cap),
                "measurement_regularizer_spread_threshold": float(config.measurement_regularizer_spread_threshold),
                "measurement_regularizer_algorithms": str(config.measurement_regularizer_algorithms),
                "orientation_control_mode": str(config.orientation_control_mode),
                "orientation_source": "particle_psi_deg_relative_to_controlled_traj_yaw",
                "yaw_control": str(yaw_mode),
                "yaw_noise_deg": float(config.yaw_noise_deg),
                "yaw_shuffle": bool(config.yaw_shuffle),
                "yaw_shuffle_seed": int(yaw_shuffle_seed),
                "yaw_shuffle_level": str(yaw_shuffle_level),
                "yaw_fixed_deg": float(config.yaw_fixed_deg),
                "disable_orientation": bool(config.disable_orientation),
                "rssd_control_mode": str(config.rssd_control_mode),
                "rssd_mode": "orientation_aware_particle_yaw",
                "rssd_control": str(rssd_mode),
                "rssd_noise_std_db": float(rssd_noise_std_db),
                "rssd_noise_scale": float(config.rssd_noise_scale),
                "rssd_shuffle": bool(config.rssd_shuffle),
                "rssd_shuffle_seed": int(rssd_shuffle_seed),
                "rssd_shuffle_level": str(rssd_shuffle_level),
                "rssd_sign_flip": bool(config.rssd_sign_flip),
                "rssd_zero_mode": "inactive_log_score" if rssd_mode == "zero" else "",
                "disable_rssd": bool(config.disable_rssd),
                "algorithm_ids": ",".join(config.algorithm_ids),
                "config_hash": stable_config_hash(config),
                "dual_pol_mode": "cp_handedness" if normalize_polarization_mode(config.polarization_mode) == "CP" else "lp_linear_projection_te_tm",
                "sequential_mode": "not_run_stage01",
                "notes": "Stage 0/1 generator: scene/VA/trajectory/path truth/time-resolution overlap/peak tables only.",
            }
        ]
    )


def write_outputs(
    output_dir: Path,
    tables: dict[str, pd.DataFrame],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        table.to_csv(output_dir / name, index=False, encoding="utf-8-sig")


def run_stage01(config: Stage01Config) -> dict[str, pd.DataFrame]:
    root = Path(__file__).resolve().parents[1]
    scene_specs = make_scene_specs(config.scene_ids)
    solver_scene_specs, solver_surface_perturbation = perturb_scene_specs_for_solver(scene_specs, config)
    scene_table = build_scene_table(scene_specs)
    surface_table = build_surface_table(scene_specs)
    solver_surface_table = build_surface_table(solver_scene_specs)
    anchor_table = build_anchor_table(scene_specs, config)
    va_catalog = build_va_catalog_truth(scene_specs, max_order=config.max_reflections)
    solver_va_catalog = build_va_catalog_truth(solver_scene_specs, max_order=config.max_reflections)
    trajectory_truth = build_trajectory_truth(
        scene_specs,
        config.trajectory_ids,
        config.num_snapshots,
        config.dt_s,
        config.scenario_pairs,
    )
    path_truth = build_path_truth_table(scene_specs, trajectory_truth, config)
    overlap_groups = build_overlap_group_table(path_truth, config)
    peak_table = build_peak_table(overlap_groups, path_truth, config)
    regime_summary = build_regime_summary(overlap_groups)

    counts = {
        "num_rooms": len(scene_specs),
        "num_trajectories": int(trajectory_truth["sequence_id"].nunique()) if len(trajectory_truth) else 0,
        "num_snapshots": int(len(trajectory_truth)),
    }
    run_manifest = build_run_manifest(config, root, counts)

    tables = {
        "run_manifest.csv": run_manifest,
        "scene_table.csv": scene_table,
        "surface_table.csv": surface_table,
        "solver_surface_table.csv": solver_surface_table,
        "solver_surface_perturbation_table.csv": solver_surface_perturbation,
        "anchor_table.csv": anchor_table,
        "va_catalog_truth.csv": va_catalog,
        "solver_va_catalog_perturbed.csv": solver_va_catalog,
        "trajectory_truth.csv": trajectory_truth,
        "path_truth_table.csv": path_truth,
        "overlap_group_table.csv": overlap_groups,
        "peak_table.csv": peak_table,
        "stage01_regime_summary.csv": regime_summary,
        "stage01_runtime_environment.csv": pd.DataFrame(
            [
                {
                    "python_version": platform.python_version(),
                    "platform": platform.platform(),
                    "numpy_version": np.__version__,
                    "pandas_version": pd.__version__,
                }
            ]
        ),
    }
    write_outputs(config.output_dir, tables)
    return tables


def write_debug_h5(output_dir: Path, name: str, dataset_name: str, values: np.ndarray) -> None:
    import h5py

    output_dir.mkdir(parents=True, exist_ok=True)
    with h5py.File(output_dir / name, "w") as h5:
        h5.create_dataset(dataset_name, data=values)


def run_all_stages(config: Stage01Config) -> dict[str, pd.DataFrame]:
    root = Path(__file__).resolve().parents[1]
    scene_specs = make_scene_specs(config.scene_ids)
    solver_scene_specs, solver_surface_perturbation = perturb_scene_specs_for_solver(scene_specs, config)
    scene_table = build_scene_table(scene_specs)
    surface_table = build_surface_table(scene_specs)
    solver_surface_table = build_surface_table(solver_scene_specs)
    anchor_table = build_anchor_table(scene_specs)
    va_catalog = build_va_catalog_truth(scene_specs, max_order=config.max_reflections)
    solver_va_catalog = build_va_catalog_truth(solver_scene_specs, max_order=config.max_reflections)
    trajectory_truth = build_trajectory_truth(
        scene_specs,
        config.trajectory_ids,
        config.num_snapshots,
        config.dt_s,
        config.scenario_pairs,
    )
    rx_orientation = build_rx_orientation_table(trajectory_truth, config)

    path_truth = build_path_truth_table(scene_specs, trajectory_truth, config)
    path_interaction = build_path_interaction_table(path_truth, surface_table)
    polarimetric_path = build_polarimetric_path_table(path_truth)
    overlap_groups = build_overlap_group_table(path_truth, config)
    peak_table = build_peak_table(overlap_groups, path_truth, config)
    cir_raw_index = write_cir_raw(config.output_dir, trajectory_truth, peak_table, path_truth, config)
    raw_cir_lde = build_raw_cir_lde_table(config.output_dir, peak_table, cir_raw_index, config)
    mpc = build_mpc_estimate_table(peak_table, overlap_groups, config, raw_cir_lde)
    assoc = build_truth_measurement_assoc_table(mpc, peak_table)
    assoc = enrich_assoc_with_feature(assoc, path_truth)
    cp_features = build_cp_feature_table(mpc, assoc, overlap_groups, polarimetric_path)
    rssd_features = build_rssd_feature_table(mpc, assoc, path_truth, trajectory_truth, config)
    rssd_features = apply_rssd_negative_control(rssd_features, config)
    regime_labels = build_regime_label_table(mpc, assoc, overlap_groups, path_truth, cp_features)
    classifier_input = build_classifier_input_table(mpc, cp_features, rssd_features, regime_labels, assoc, path_truth)
    classifier_prediction = build_classifier_prediction_table(mpc, cp_features, assoc, path_truth)
    threshold_sweep = build_threshold_sweep_table(mpc, cp_features, assoc)
    slam_measurements = build_slam_measurement_table(mpc, cp_features, rssd_features, assoc)
    range_scale = max(0.0, float(config.range_variance_scale))
    if len(slam_measurements):
        slam_measurements["range_variance_scale"] = range_scale
        if range_scale != 1.0:
            for col in ("range_var_m2", "range_var_base_m2"):
                if col in slam_measurements.columns:
                    slam_measurements[col] = pd.to_numeric(slam_measurements[col], errors="coerce") * range_scale
    slam_da_truth = build_slam_da_truth_table(assoc, path_truth)
    rssd_orientation_truth = apply_solver_orientation_control(trajectory_truth, config)
    solver_trajectory_truth = trajectory_truth.copy()
    solver_initial_pose_prior = build_solver_initial_pose_prior_table(solver_trajectory_truth)
    solver_odometry_input = build_solver_odometry_input_table(
        solver_trajectory_truth,
        random_seed=config.random_seed,
        noise_scale=config.odometry_noise_scale,
    )
    slam_result, slam_da_result, slam_feature_result, posterior_particles, bp_trace = solve_slam_ablation(
        trajectory_truth,
        scene_table,
        solver_va_catalog,
        slam_measurements,
        slam_da_truth,
        regime_labels,
        cp_features,
        rssd_features,
        classifier_prediction,
        config,
        initial_pose_prior=solver_initial_pose_prior,
        odometry_table=solver_odometry_input,
        rssd_orientation_trajectory=rssd_orientation_truth,
    )
    slam_feature_result = build_slam_feature_result_table(slam_da_truth, va_catalog, slam_da_result)
    metric_by_regime = build_metric_by_regime_table(slam_result, slam_da_result, regime_labels, threshold_sweep)
    ablation = build_ablation_table(slam_result, slam_da_result, slam_feature_result)
    claim_gate_summary = build_claim_gate_summary(ablation, metric_by_regime, classifier_prediction, classifier_input)
    recommended_order = build_recommended_simulation_order()
    sequential_reconfig = build_sequential_reconfig_table(trajectory_truth, cp_features)
    figure_manifest = build_figure_manifest()
    regime_summary = build_regime_summary(overlap_groups)
    write_solver_h5(config.output_dir, posterior_particles, bp_trace)

    counts = {
        "num_rooms": len(scene_specs),
        "num_trajectories": int(trajectory_truth["sequence_id"].nunique()) if len(trajectory_truth) else 0,
        "num_snapshots": int(len(trajectory_truth)),
    }
    run_manifest = build_run_manifest(config, root, counts)
    run_manifest.loc[:, "solver_version"] = "stage45_known_catalog_particle_soft_da_v0_1"
    run_manifest.loc[:, "dual_pol_mode"] = "dual_cp_stress_truth"
    run_manifest.loc[:, "sequential_mode"] = "stress_sweep_generated"
    run_manifest.loc[:, "notes"] = (
        "Stage 0-7 stress-test solve: path truth, peak overlap, CP/RSSD features, "
        "threshold sweep, SLAM measurement, known-catalog particle soft-DA "
        "posterior, B0-B15 ablation metrics, and sequential stress. This is "
        "Stage 4.5/5 bridge solver, not unknown-feature BP-SLAM."
    )

    tables = {
        "run_manifest.csv": run_manifest,
        "scene_table.csv": scene_table,
        "surface_table.csv": surface_table,
        "solver_surface_table.csv": solver_surface_table,
        "solver_surface_perturbation_table.csv": solver_surface_perturbation,
        "anchor_table.csv": anchor_table,
        "va_catalog_truth.csv": va_catalog,
        "solver_va_catalog_perturbed.csv": solver_va_catalog,
        "trajectory_truth.csv": trajectory_truth,
        "solver_trajectory_input_table.csv": solver_trajectory_truth,
        "rssd_orientation_control_table.csv": rssd_orientation_truth,
        "rx_orientation_table.csv": rx_orientation,
        "path_truth_table.csv": path_truth,
        "path_interaction_table.csv": path_interaction,
        "polarimetric_path_table.csv": polarimetric_path,
        "cir_raw_index.csv": cir_raw_index,
        "raw_cir_lde_table.csv": raw_cir_lde,
        "peak_table.csv": peak_table,
        "overlap_group_table.csv": overlap_groups,
        "mpc_estimate_table.csv": mpc,
        "truth_measurement_assoc_table.csv": assoc,
        "cp_feature_table.csv": cp_features,
        "rssd_feature_table.csv": rssd_features,
        "regime_label_table.csv": regime_labels,
        "classifier_input_table.csv": classifier_input,
        "classifier_prediction_table.csv": classifier_prediction,
        "threshold_sweep_table.csv": threshold_sweep,
        "sequential_reconfig_table.csv": sequential_reconfig,
        "slam_measurement_table.csv": slam_measurements,
        "slam_da_truth_table.csv": slam_da_truth,
        "solver_initial_pose_prior_table.csv": solver_initial_pose_prior,
        "solver_odometry_input_table.csv": solver_odometry_input,
        "slam_result_table.csv": slam_result,
        "slam_feature_result_table.csv": slam_feature_result,
        "slam_da_result_table.csv": slam_da_result,
        "metric_by_regime_table.csv": metric_by_regime,
        "ablation_table.csv": ablation,
        "claim_gate_summary.csv": claim_gate_summary,
        "recommended_simulation_order.csv": recommended_order,
        "bp_message_trace_table.csv": bp_trace,
        "posterior_particle_index.csv": posterior_particles,
        "figure_manifest.csv": figure_manifest,
        "stage01_regime_summary.csv": regime_summary,
        "stage01_runtime_environment.csv": pd.DataFrame(
            [
                {
                    "python_version": platform.python_version(),
                    "platform": platform.platform(),
                    "numpy_version": np.__version__,
                    "pandas_version": pd.__version__,
                }
            ]
        ),
    }
    write_outputs(config.output_dir, tables)
    write_result_summary(config.output_dir, tables)
    return tables


def default_output_dir(root: Path | None = None) -> Path:
    base = Path(__file__).resolve().parents[1] if root is None else root
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
    return base / "results" / f"sim_new_cp_va_slam_stage01_{stamp}"


def default_full_output_dir(root: Path | None = None) -> Path:
    base = Path(__file__).resolve().parents[1] if root is None else root
    stamp = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d_%H%M%S")
    return base / "results" / f"sim_new_cp_va_slam_all_stages_{stamp}"
