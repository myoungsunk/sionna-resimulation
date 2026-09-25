"""Simulation-based channel-state label generator for the H10B E2 experiment.

Generates NoLoS / RD_LoS / LOS_clean labels (and q_clean proxy values) from
the existing ray-tracing infrastructure.  All labels are *simulation-derived*:
they characterise the propagation geometry as seen by the RT engine, not as
measured by a real AMR.

Label definitions (based on direct-path vs. reflected-path power ratio)
-----------------------------------------------------------------------
  LOS_clean:   direct path exists AND reflected power ratio > los_threshold_db.
               The scene is dominated by the direct path → q_clean ≈ 1.
  RD_LoS:      direct path exists BUT reflected paths are strong (ratio ≤
               los_threshold_db) OR a reflected path falls within the UWB
               first-path detection window (< range_bias_window_m extra delay).
               → q_clean ≈ 0.3–0.7
  NoLoS:       no unblocked direct path found.  Range measurement severely
               biased by NLOS → q_clean ≈ 0.

Claim boundary
--------------
  These labels are derived from the geometric ray-tracing model and Fresnel
  reflection coefficients — NOT from measured AMR channel impulse responses.
  The classifier trained on these labels is a sim2real transfer scenario.
  Allowed under the project claim boundary:
    "FFD-based prediction" and "RT-derived channel-state labels".
  Forbidden: claiming the classifier was validated on real AMR CIR data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from .core import C0, Material, Scene, fresnel_reflection
from .materials import materials_library
from .scenes import make_room_abc_scene
from .trace import enumerate_paths


# ──────────────────────────────────────────────────────────────────────────────
#  Module-level defaults
# ──────────────────────────────────────────────────────────────────────────────

SIM_LABEL_SCHEMA_VERSION: str = "h10b_sim_label_v1"

# Default UWB centre frequency for free-space path-loss calculation
_DEFAULT_FREQ_HZ: float = 6.5e9
_LAMBDA_M: float = C0 / _DEFAULT_FREQ_HZ

# Default classification thresholds
_DEFAULT_LOS_POWER_RATIO_DB: float = 12.0   # direct/reflected power ratio for LOS_clean
_DEFAULT_RANGE_BIAS_WINDOW_M: float = 0.30  # reflected path excess ≤ 0.3m → biases range

# Label strings
LABEL_LOS_CLEAN = "LOS_clean"
LABEL_RD_LOS = "RD_LoS"
LABEL_NLOS = "NoLoS"

# q_clean proxy values per label (midpoints; calibrated via isotonic regression later)
_QCLEAN_PROXY: dict[str, float] = {
    LABEL_LOS_CLEAN: 0.90,
    LABEL_RD_LOS: 0.45,
    LABEL_NLOS: 0.05,
}


# ──────────────────────────────────────────────────────────────────────────────
#  Propagation-state classification
# ──────────────────────────────────────────────────────────────────────────────

def _free_space_amplitude(path_len_m: float) -> float:
    """Free-space path amplitude |E| ∝ λ/(4π r)."""
    return _LAMBDA_M / (4.0 * math.pi * max(float(path_len_m), 0.01))


def _reflected_path_amplitude(path: Any) -> float:
    """Approximate scalar amplitude of a reflected path.

    Product of free-space amplitude and per-bounce Fresnel reflection magnitudes
    (average of TE and TM coefficients at the path incidence angle).
    """
    amp = _free_space_amplitude(path.path_length_m)
    freqs = np.array([_DEFAULT_FREQ_HZ])
    for mat, theta in zip(path.materials, path.incidence_angles_rad):
        g_te, g_tm = fresnel_reflection(mat, float(theta), freqs)
        # Average TE+TM |gamma| for a scalar single-value approximation
        refl = 0.5 * (abs(float(g_te[0].real)) + abs(float(g_tm[0].real)))
        amp *= refl
    return amp


def classify_propagation_state(
    paths: list[Any],
    *,
    los_power_ratio_threshold_db: float = _DEFAULT_LOS_POWER_RATIO_DB,
    range_bias_window_m: float = _DEFAULT_RANGE_BIAS_WINDOW_M,
) -> dict[str, Any]:
    """Classify a channel state from a list of PathRecord objects.

    Args:
        paths:                       Output of ``enumerate_paths()``.
        los_power_ratio_threshold_db:Minimum direct-to-strongest-reflected
                                     power ratio (dB) for LOS_clean.
        range_bias_window_m:         Maximum excess path length (m) for a
                                     reflected path to bias the first-path
                                     range estimate.

    Returns:
        dict with keys:
          label           str    "LOS_clean" | "RD_LoS" | "NoLoS"
          q_clean_proxy   float  Soft label ∈ [0, 1] (simulation proxy)
          has_direct      bool
          n_paths         int    total number of valid paths
          n_reflected     int
          direct_path_len_m    float | None
          power_ratio_db       float | None  direct/strongest-reflected
          n_reflected_in_bias_window  int    count within range_bias_window_m
    """
    direct = [p for p in paths if p.bounce_count == 0]
    reflected = [p for p in paths if p.bounce_count > 0]
    has_direct = len(direct) > 0

    if not has_direct:
        return {
            "label": LABEL_NLOS,
            "q_clean_proxy": _QCLEAN_PROXY[LABEL_NLOS],
            "has_direct": False,
            "n_paths": len(paths),
            "n_reflected": len(reflected),
            "direct_path_len_m": None,
            "power_ratio_db": None,
            "n_reflected_in_bias_window": len(reflected),
        }

    direct_path = direct[0]
    A_direct = _free_space_amplitude(direct_path.path_length_m)

    n_in_window = 0
    max_refl_amp = 0.0
    for rp in reflected:
        excess = rp.path_length_m - direct_path.path_length_m
        if excess < float(range_bias_window_m):
            n_in_window += 1
        A_r = _reflected_path_amplitude(rp)
        if A_r > max_refl_amp:
            max_refl_amp = A_r

    if max_refl_amp > 0.0:
        power_ratio_db = 20.0 * math.log10(max(A_direct / max_refl_amp, 1e-10))
    else:
        power_ratio_db = 40.0  # no reflected paths → high ratio

    is_los_clean = (
        power_ratio_db >= float(los_power_ratio_threshold_db)
        and n_in_window == 0
    )
    label = LABEL_LOS_CLEAN if is_los_clean else LABEL_RD_LOS

    # Soft q_clean proxy: interpolate from power ratio
    if is_los_clean:
        # Clamp at threshold; ramp up to 0.95 for very high ratios
        q = min(0.95, 0.80 + 0.15 * (power_ratio_db - los_power_ratio_threshold_db) / 10.0)
    else:
        # Power ratio below threshold; also penalise for paths in bias window
        bias_penalty = 0.10 * n_in_window
        q = max(0.05, min(0.70, 0.30 + 0.05 * power_ratio_db - bias_penalty))

    return {
        "label": label,
        "q_clean_proxy": float(q),
        "has_direct": True,
        "n_paths": len(paths),
        "n_reflected": len(reflected),
        "direct_path_len_m": float(direct_path.path_length_m),
        "power_ratio_db": float(power_ratio_db),
        "n_reflected_in_bias_window": n_in_window,
    }


# ──────────────────────────────────────────────────────────────────────────────
#  Grid label generation
# ──────────────────────────────────────────────────────────────────────────────

def simulate_channel_state_grid(
    scene: Scene,
    anchor_positions: np.ndarray,
    tag_xy_grid: np.ndarray,
    *,
    tag_height_m: float = 0.80,
    max_reflections: int = 2,
    los_power_ratio_threshold_db: float = _DEFAULT_LOS_POWER_RATIO_DB,
    range_bias_window_m: float = _DEFAULT_RANGE_BIAS_WINDOW_M,
) -> pd.DataFrame:
    """Generate RT-derived channel-state labels for a grid of (anchor, tag) pairs.

    Args:
        scene:               Scene object (from ``make_room_abc_scene`` etc.).
        anchor_positions:    (A, 3) array of anchor [x, y, z] positions.
        tag_xy_grid:         (T, 2) array of tag [x, y] positions.
        tag_height_m:        Tag height above floor (m).
        max_reflections:     Maximum reflection order for path enumeration.
        los_power_ratio_threshold_db: Classification threshold (dB).
        range_bias_window_m: Bias window for range distortion detection (m).

    Returns:
        DataFrame with columns:
          anchor_id, anchor_x_m, anchor_y_m, anchor_z_m,
          tag_x_m, tag_y_m, tag_z_m,
          geo_dist_m,
          label, q_clean_proxy, has_direct,
          n_paths, n_reflected, direct_path_len_m,
          power_ratio_db, n_reflected_in_bias_window
    """
    anchors = np.asarray(anchor_positions, dtype=float)
    if anchors.ndim == 1:
        anchors = anchors.reshape(1, 3)
    tags_xy = np.asarray(tag_xy_grid, dtype=float)
    if tags_xy.ndim == 1:
        tags_xy = tags_xy.reshape(1, 2)

    rows: list[dict[str, Any]] = []
    for a_idx, anchor in enumerate(anchors):
        for t_idx, txy in enumerate(tags_xy):
            tag_pos = np.array([txy[0], txy[1], float(tag_height_m)], dtype=float)
            paths = enumerate_paths(scene, anchor, tag_pos, max_reflections)
            geo_dist = float(np.linalg.norm(tag_pos - anchor))
            result = classify_propagation_state(
                paths,
                los_power_ratio_threshold_db=los_power_ratio_threshold_db,
                range_bias_window_m=range_bias_window_m,
            )
            rows.append({
                "anchor_id": a_idx,
                "anchor_x_m": float(anchor[0]),
                "anchor_y_m": float(anchor[1]),
                "anchor_z_m": float(anchor[2]),
                "tag_x_m": float(txy[0]),
                "tag_y_m": float(txy[1]),
                "tag_z_m": float(tag_height_m),
                "geo_dist_m": geo_dist,
                **result,
            })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
#  E2 training set builder
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class E2TrainingConfig:
    """Configuration for the E2 simulation-based training data generator."""

    room_type: str = "C"
    room_size: tuple[float, float, float] = (8.0, 6.0, 3.0)
    tag_height_m: float = 0.80
    anchor_height_m: float = 2.0
    n_tag_grid_x: int = 12
    n_tag_grid_y: int = 10
    n_yaw_samples: int = 8              # evenly spaced heading bins
    max_reflections: int = 2
    los_power_ratio_threshold_db: float = _DEFAULT_LOS_POWER_RATIO_DB
    range_bias_window_m: float = _DEFAULT_RANGE_BIAS_WINDOW_M
    random_seed: int = 20260611
    material_name: str | None = None    # None → use scene defaults (mixed materials)


def build_e2_training_set(
    config: E2TrainingConfig | None = None,
    *,
    scene: Scene | None = None,
    anchor_positions: np.ndarray | None = None,
    ffd_predictor: Any = None,
) -> pd.DataFrame:
    """Build a simulation-derived E2 training dataset.

    Generates a grid of (tag_position, tag_yaw, anchor) combinations,
    runs RT path enumeration for each, derives channel-state labels, and
    optionally attaches H10B FFD amplitude predictions as features.

    Args:
        config:           ``E2TrainingConfig`` (defaults used if None).
        scene:            Override scene (auto-built from config if None).
        anchor_positions: Override anchors (auto-placed if None).
        ffd_predictor:    Optional ``H10BFFDPredictor`` for feature generation.
                          When provided, 4-channel amplitude and contrast
                          features are added as columns.

    Returns:
        DataFrame suitable for E2 classifier training.  Key columns:
          tag_x_m, tag_y_m, yaw_deg, anchor_id,
          label, q_clean_proxy, power_ratio_db,
          [ffd_tiltA_lhcp_db, ..., ffd_pol_contrast_tiltA_db, ...] (if ffd_predictor)
    """
    cfg = config or E2TrainingConfig()
    lib = materials_library()

    # Build or use provided scene
    if scene is None:
        mat = lib[cfg.material_name] if cfg.material_name else None
        scene = make_room_abc_scene(cfg.room_type, cfg.room_size, material=mat)

    lx, ly, _ = cfg.room_size

    # Default anchor positions: 4 corners at anchor_height_m
    if anchor_positions is None:
        margin = 0.4
        anchor_positions = np.array([
            [margin, margin, cfg.anchor_height_m],
            [lx - margin, margin, cfg.anchor_height_m],
            [margin, ly - margin, cfg.anchor_height_m],
            [lx - margin, ly - margin, cfg.anchor_height_m],
        ], dtype=float)

    # Build tag grid (avoid walls)
    rng = np.random.default_rng(cfg.random_seed)
    margin = 0.3
    xs = np.linspace(margin, lx - margin, cfg.n_tag_grid_x)
    ys = np.linspace(margin, ly - margin, cfg.n_tag_grid_y)
    xv, yv = np.meshgrid(xs, ys)
    tag_xy = np.column_stack([xv.ravel(), yv.ravel()])

    # Yaw samples
    yaw_deg_list = np.linspace(0.0, 360.0, cfg.n_yaw_samples, endpoint=False).tolist()

    # Run RT grid labelling
    label_df = simulate_channel_state_grid(
        scene, anchor_positions, tag_xy,
        tag_height_m=cfg.tag_height_m,
        max_reflections=cfg.max_reflections,
        los_power_ratio_threshold_db=cfg.los_power_ratio_threshold_db,
        range_bias_window_m=cfg.range_bias_window_m,
    )

    # Cross with yaw samples
    yaw_df = pd.DataFrame({"yaw_deg": yaw_deg_list})
    label_df["_key"] = 1
    yaw_df["_key"] = 1
    df = label_df.merge(yaw_df, on="_key").drop(columns=["_key"])

    # Add FFD amplitude features if predictor supplied
    if ffd_predictor is not None:
        _add_ffd_features(df, ffd_predictor, tag_height_m=cfg.tag_height_m)

    # Metadata
    df["schema_version"] = SIM_LABEL_SCHEMA_VERSION
    df["room_type"] = cfg.room_type
    df["simulation_source"] = "rt_enumerate_paths_fresnel"

    return df.reset_index(drop=True)


def _add_ffd_features(df: pd.DataFrame, ffd_predictor: Any, tag_height_m: float) -> None:
    """Add H10B FFD amplitude and contrast columns to *df* in-place."""
    from .h10b_channels import CANONICAL_H10B_CHANNELS

    amp_cols = [f"ffd_{ch.channel_id}_db" for ch in CANONICAL_H10B_CHANNELS]
    for col in amp_cols:
        df[col] = np.nan

    for idx, row in df.iterrows():
        anchor = np.array([row["anchor_x_m"], row["anchor_y_m"], row["anchor_z_m"]], dtype=float)
        tag    = np.array([row["tag_x_m"], row["tag_y_m"], float(tag_height_m)], dtype=float)
        yaw    = float(row["yaw_deg"])
        try:
            pred = ffd_predictor.predict_amplitude_vector_db_3d(
                anchor_pos=anchor, tag_pos=tag, tag_yaw_deg=yaw
            )
            for j, col in enumerate(amp_cols):
                df.at[idx, col] = float(pred[j]) if np.isfinite(pred[j]) else np.nan
        except Exception:
            pass

    # Contrast features (pol and tilt differences)
    _safe = lambda a, b: (
        df[f"ffd_{a}_db"] - df[f"ffd_{b}_db"]
        if f"ffd_{a}_db" in df.columns and f"ffd_{b}_db" in df.columns
        else pd.Series(np.nan, index=df.index)
    )
    df["ffd_pol_contrast_tiltA_db"] = _safe("tiltA_rhcp", "tiltA_lhcp")
    df["ffd_pol_contrast_tiltB_db"] = _safe("tiltB_rhcp", "tiltB_lhcp")
    df["ffd_tilt_contrast_lhcp_db"] = _safe("tiltA_lhcp", "tiltB_lhcp")
    df["ffd_tilt_contrast_rhcp_db"] = _safe("tiltA_rhcp", "tiltB_rhcp")


# ──────────────────────────────────────────────────────────────────────────────
#  Convenience: multi-scene / multi-material dataset builder
# ──────────────────────────────────────────────────────────────────────────────

def build_e2_training_set_multi_material(
    config: E2TrainingConfig | None = None,
    *,
    material_names: list[str] | None = None,
    ffd_predictor: Any = None,
) -> pd.DataFrame:
    """Build E2 training data across multiple wall materials.

    Each material produces a separate scene so the classifier sees a range
    of channel conditions.  The ``material_name`` column can later be used
    as a stratification key for leave-material-out cross-validation.

    Args:
        config:         Base config (room_type, room_size, etc.).
        material_names: List of material names from ``materials_library()``.
                        Defaults to the canonical E6 material set.
        ffd_predictor:  Optional FFD predictor for amplitude features.

    Returns:
        Concatenated DataFrame with an extra ``material_name`` column.
    """
    cfg = config or E2TrainingConfig()
    lib = materials_library()
    mats = material_names or ["drywall", "concrete", "brick", "glass", "wood", "metal_pec"]
    dfs: list[pd.DataFrame] = []
    for mat_name in mats:
        mat_cfg = E2TrainingConfig(
            room_type=cfg.room_type,
            room_size=cfg.room_size,
            tag_height_m=cfg.tag_height_m,
            anchor_height_m=cfg.anchor_height_m,
            n_tag_grid_x=cfg.n_tag_grid_x,
            n_tag_grid_y=cfg.n_tag_grid_y,
            n_yaw_samples=cfg.n_yaw_samples,
            max_reflections=cfg.max_reflections,
            los_power_ratio_threshold_db=cfg.los_power_ratio_threshold_db,
            range_bias_window_m=cfg.range_bias_window_m,
            random_seed=cfg.random_seed,
            material_name=mat_name,
        )
        df_m = build_e2_training_set(mat_cfg, ffd_predictor=ffd_predictor)
        df_m["material_name"] = mat_name
        dfs.append(df_m)
    return pd.concat(dfs, ignore_index=True)
