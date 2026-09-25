"""E6 robustness split utilities for the H10B SLAM experiment framework.

Provides three types of out-of-distribution (OOD) splits:

  1. channel_dropout     — Randomly zero one H10B channel per measurement.
                           Tests graceful degradation when a channel fails.
                           Pure code-level augmentation; needs no new data.

  2. leave_heading_out   — Hold out all measurements within a specific heading
                           bin (default: 8 × 45° bins).  Tests whether the
                           SLAM backend generalises to unseen approach angles.

  3. leave_material_out  — Hold out measurements from one wall material.
                           Uses the simulation framework: each material variant
                           is a separate Scene with different eps_r.

All functions return pandas DataFrames so they integrate directly with the
existing profile export / solver pipeline.

Claim boundary
--------------
  split indices derived from simulated trajectories and RT geometry.
  Not derived from measured AMR material labels.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .core import Material, Scene
from .materials import materials_library
from .scenes import make_room_abc_scene


# ──────────────────────────────────────────────────────────────────────────────
#  1. Channel dropout augmentation
# ──────────────────────────────────────────────────────────────────────────────

#: Canonical H10B amplitude column names (canonical suffix form).
H10B_AMPLITUDE_COLS: tuple[str, ...] = (
    "h10b_tiltA_lhcp_amplitude_db",
    "h10b_tiltA_rhcp_amplitude_db",
    "h10b_tiltB_lhcp_amplitude_db",
    "h10b_tiltB_rhcp_amplitude_db",
)

#: Canonical H10B range column names.
H10B_RANGE_COLS: tuple[str, ...] = (
    "h10b_tiltA_lhcp_range_m",
    "h10b_tiltA_rhcp_range_m",
    "h10b_tiltB_lhcp_range_m",
    "h10b_tiltB_rhcp_range_m",
)


def channel_dropout_augment(
    df: pd.DataFrame,
    *,
    amp_cols: tuple[str, ...] | list[str] = H10B_AMPLITUDE_COLS,
    range_cols: tuple[str, ...] | list[str] = H10B_RANGE_COLS,
    n_dropout: int = 1,
    seed: int = 42,
    dropout_col: str = "dropout_channel_idx",
) -> pd.DataFrame:
    """Randomly zero exactly *n_dropout* H10B channel(s) per row.

    Sets the amplitude and range columns for the dropped channel(s) to NaN.
    Simulates a hardware channel failure or blocked antenna element.

    Args:
        df:          Input DataFrame (not modified in-place; copy returned).
        amp_cols:    Amplitude column names to null out.
        range_cols:  Range column names to null out.
        n_dropout:   Number of channels to drop per row (default 1).
        seed:        RNG seed for reproducibility.
        dropout_col: Name of the new column recording which channel index
                     was dropped.

    Returns:
        Augmented copy with NaN channels and a ``dropout_channel_idx`` column.
    """
    out = df.copy()
    rng = np.random.default_rng(int(seed))

    amp_c = [c for c in amp_cols if c in out.columns]
    rng_c = [c for c in range_cols if c in out.columns]
    n_ch = max(len(amp_c), len(rng_c), 4)
    dropped_idx: list[int] = []

    for i in range(len(out)):
        idxs = rng.choice(n_ch, size=int(n_dropout), replace=False).tolist()
        dropped_idx.append(idxs[0] if len(idxs) == 1 else -1)  # record first drop
        for ch_idx in idxs:
            if ch_idx < len(amp_c):
                out.at[out.index[i], amp_c[ch_idx]] = float("nan")
            if ch_idx < len(rng_c):
                out.at[out.index[i], rng_c[ch_idx]] = float("nan")

    out[dropout_col] = dropped_idx
    return out


def channel_dropout_split(
    df: pd.DataFrame,
    *,
    amp_cols: tuple[str, ...] | list[str] = H10B_AMPLITUDE_COLS,
    range_cols: tuple[str, ...] | list[str] = H10B_RANGE_COLS,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (nominal, dropout_augmented) pair for E6 channel-dropout split.

    Args:
        df:         Full dataset.
        amp_cols:   Amplitude columns to augment.
        range_cols: Range columns to augment.
        seed:       RNG seed.

    Returns:
        (train_df, test_df):
          train_df = original df with all 4 channels intact.
          test_df  = dropout-augmented copy (one channel zeroed per row).
    """
    return df.copy(), channel_dropout_augment(df, amp_cols=amp_cols, range_cols=range_cols, seed=seed)


# ──────────────────────────────────────────────────────────────────────────────
#  2. Leave-heading-out splits
# ──────────────────────────────────────────────────────────────────────────────

def heading_bin_labels(
    yaw_deg_series: pd.Series,
    n_bins: int = 8,
) -> pd.Series:
    """Assign each row a heading bin index in [0, n_bins).

    Bins are equal-width in [0°, 360°).  E.g. n_bins=8 → 45° per bin.

    Args:
        yaw_deg_series:  Series of yaw angles in degrees (any range).
        n_bins:          Number of equal-width heading bins.

    Returns:
        Series of int bin indices.
    """
    bin_width = 360.0 / n_bins
    normalised = yaw_deg_series.map(lambda y: float(y) % 360.0)
    return (normalised / bin_width).astype(int).clip(0, n_bins - 1)


def leave_heading_bin_out_splits(
    df: pd.DataFrame,
    *,
    yaw_col: str = "yaw_deg",
    n_bins: int = 8,
    bin_label_col: str = "heading_bin",
) -> Iterator[tuple[pd.DataFrame, pd.DataFrame, int]]:
    """Yield (train_df, test_df, held_out_bin_id) for each heading bin.

    Each iteration holds out one heading bin as the test set and trains on
    all remaining bins.  Produces n_bins folds.

    Args:
        df:            DataFrame with a yaw column.
        yaw_col:       Column name for yaw angle (degrees).
        n_bins:        Number of heading bins.
        bin_label_col: Column name for the bin label (added to df copy).

    Yields:
        (train_df, test_df, bin_id)
    """
    df = df.copy()
    df[bin_label_col] = heading_bin_labels(df[yaw_col], n_bins=n_bins)
    for bin_id in range(n_bins):
        train = df[df[bin_label_col] != bin_id].reset_index(drop=True)
        test  = df[df[bin_label_col] == bin_id].reset_index(drop=True)
        yield train, test, bin_id


def leave_heading_bin_out_export(
    df: pd.DataFrame,
    export_root: Path,
    *,
    yaw_col: str = "yaw_deg",
    n_bins: int = 8,
) -> list[dict[str, object]]:
    """Write leave-heading-out split CSV files and return a manifest.

    Writes ``<export_root>/heading_bin_{i}/train.csv`` and
    ``<export_root>/heading_bin_{i}/test.csv`` for each bin.

    Args:
        df:           Full dataset.
        export_root:  Root directory for output files.
        yaw_col:      Yaw column name.
        n_bins:       Number of heading bins.

    Returns:
        List of manifest dicts (one per fold).
    """
    root = Path(export_root)
    manifest = []
    for train, test, bin_id in leave_heading_bin_out_splits(df, yaw_col=yaw_col, n_bins=n_bins):
        fold_dir = root / f"heading_bin_{bin_id}"
        fold_dir.mkdir(parents=True, exist_ok=True)
        train.to_csv(fold_dir / "train.csv", index=False, encoding="utf-8-sig")
        test.to_csv(fold_dir / "test.csv",  index=False, encoding="utf-8-sig")
        manifest.append({
            "fold_type": "leave_heading_out",
            "held_out_bin": bin_id,
            "heading_range_deg": f"{bin_id * 360.0 / n_bins:.0f}–{(bin_id + 1) * 360.0 / n_bins:.0f}",
            "train_rows": len(train),
            "test_rows": len(test),
            "train_csv": str(fold_dir / "train.csv"),
            "test_csv": str(fold_dir / "test.csv"),
        })
    return manifest


# ──────────────────────────────────────────────────────────────────────────────
#  3. Leave-material-out splits
# ──────────────────────────────────────────────────────────────────────────────

#: Canonical E6 material set (covers the eps_r range 2–10 from materials.py).
E6_MATERIAL_NAMES: tuple[str, ...] = (
    "drywall",
    "concrete",
    "brick",
    "glass",
    "wood",
    "ceramic_tile",
    "metal_pec",
)


def material_scene_variants(
    room_type: str = "A",
    room_size: tuple[float, float, float] = (7.0, 5.0, 3.0),
    material_names: list[str] | None = None,
) -> list[tuple[str, Scene]]:
    """Return a list of (material_name, Scene) pairs covering the E6 material set.

    Each scene is a single-material room built with ``make_room_abc_scene``.
    Useful for leave-material-out cross-validation where each scene represents
    a different propagation environment.

    Args:
        room_type:      Room geometry type ("A", "B", "C", "HALL").
        room_size:      (lx, ly, lz) room dimensions in metres.
        material_names: Subset of ``E6_MATERIAL_NAMES`` to include.

    Returns:
        List of (material_name, Scene) tuples.
    """
    lib = materials_library()
    mats = material_names or list(E6_MATERIAL_NAMES)
    return [(name, make_room_abc_scene(room_type, room_size, material=lib[name])) for name in mats if name in lib]


def leave_material_out_splits(
    df_by_material: dict[str, pd.DataFrame],
) -> Iterator[tuple[pd.DataFrame, pd.DataFrame, str]]:
    """Yield (train_df, test_df, held_out_material) for each material.

    Args:
        df_by_material: Dict mapping material_name → DataFrame.

    Yields:
        (train_df, test_df, held_out_material)
    """
    for held_out in df_by_material:
        train_parts = [df for mat, df in df_by_material.items() if mat != held_out]
        train = pd.concat(train_parts, ignore_index=True) if train_parts else pd.DataFrame()
        test  = df_by_material[held_out].copy().reset_index(drop=True)
        yield train, test, held_out


def leave_material_out_export(
    df_by_material: dict[str, pd.DataFrame],
    export_root: Path,
) -> list[dict[str, object]]:
    """Write leave-material-out split CSV files and return a manifest.

    Args:
        df_by_material: Dict mapping material_name → DataFrame.
        export_root:    Root directory for output files.

    Returns:
        List of manifest dicts (one per fold).
    """
    root = Path(export_root)
    manifest = []
    for train, test, held_out in leave_material_out_splits(df_by_material):
        fold_dir = root / f"leave_{held_out}_out"
        fold_dir.mkdir(parents=True, exist_ok=True)
        train.to_csv(fold_dir / "train.csv", index=False, encoding="utf-8-sig")
        test.to_csv(fold_dir / "test.csv",   index=False, encoding="utf-8-sig")
        manifest.append({
            "fold_type": "leave_material_out",
            "held_out_material": held_out,
            "train_materials": [m for m in df_by_material if m != held_out],
            "train_rows": len(train),
            "test_rows": len(test),
            "train_csv": str(fold_dir / "train.csv"),
            "test_csv": str(fold_dir / "test.csv"),
        })
    return manifest


# ──────────────────────────────────────────────────────────────────────────────
#  Introspection
# ──────────────────────────────────────────────────────────────────────────────

def e6_splits_manifest() -> dict[str, object]:
    """Return a provenance record describing the E6 split infrastructure."""
    return {
        "schema_version": "h10b_e6_splits_v1",
        "split_types": {
            "channel_dropout": {
                "method": "code_level_augmentation",
                "n_dropout": 1,
                "sim_required": False,
                "description": "One H10B channel NaN'd per measurement; no new data needed.",
            },
            "leave_heading_out": {
                "method": "heading_bin_stratification",
                "n_bins": 8,
                "bin_width_deg": 45.0,
                "sim_required": True,
                "description": "Hold out one 45°-wide heading bin; 8-fold CV.",
            },
            "leave_material_out": {
                "method": "material_scene_variants",
                "material_names": list(E6_MATERIAL_NAMES),
                "sim_required": True,
                "description": "Hold out one wall material; 7-fold CV over eps_r range 2–10.",
            },
        },
        "claim_boundary": (
            "split_labels_are_simulation_derived_not_measured_amr_material_labels"
        ),
    }
