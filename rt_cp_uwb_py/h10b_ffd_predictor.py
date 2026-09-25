from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from rt_cp_uwb_py.antennas import ReceiverAntennaPattern, direction_to_pattern_angles
from rt_cp_uwb_py.h10b_channels import CANONICAL_H10B_CHANNELS, CANONICAL_H10B_CHANNEL_ORDER
from rt_cp_uwb_py.h10b_vector_likelihood import h10b_contrast_vector_from_amplitude_vector


# H10B dual-tilt tag geometry defaults
# alpha = 60° total opening angle → each tilt is ±30° from vertical (z-axis)
# Matches legacy_dual_tag_alpha_deg = 60.0 convention
H10B_DEFAULT_TILT_HALF_ANGLE_DEG: float = 30.0

# Fixed AMR tag mounting height above floor
H10B_DEFAULT_TAG_HEIGHT_M: float = 0.8

# UWB band center frequency for FSPL computation
H10B_UWB_CENTER_FREQ_HZ: float = 6.5e9

# Maps canonical H10B channel IDs to their corresponding FFD antenna pattern files.
# tiltA carries LHCP/RHCP CP elements; tiltB carries LP±45° elements.
# Both tilt sets share the same physical patterns but are mounted at opposite
# pitch angles on the tag body, creating the tilt diversity needed for
# range-direction estimation.
H10B_CHANNEL_FFD_FILENAMES: dict[str, str] = {
    "tiltA_lhcp": "LHCP_new_6G7G_11pts.ffd",
    "tiltA_rhcp": "RHCP_new_6G7G_11pts.ffd",
    "tiltB_lhcp": "LP_+45_new_6G7G_11pts.ffd",
    "tiltB_rhcp": "LP_-45_new_6G7G_11pts.ffd",
}

# Tilt pitch (rotation about the tag-body y-axis) for each tilt set.
# tiltA tilts forward (+pitch), tiltB tilts backward (-pitch).
# These are set at H10B_DEFAULT_TILT_HALF_ANGLE_DEG and overridable via
# H10BFFDPredictor(tilt_half_angle_deg=...).
_TILT_SET_SIGN: dict[str, float] = {"tiltA": +1.0, "tiltB": -1.0}


def _pitch_rot(angle_deg: float) -> np.ndarray:
    """3×3 rotation matrix for pitch (y-axis) rotation by angle_deg degrees."""
    a = math.radians(float(angle_deg))
    ca, sa = math.cos(a), math.sin(a)
    return np.array(
        [[ca, 0.0, sa], [0.0, 1.0, 0.0], [-sa, 0.0, ca]],
        dtype=float,
    )


def _yaw_rot(yaw_deg: float) -> np.ndarray:
    """3×3 rotation matrix for yaw (z-axis) rotation by yaw_deg degrees."""
    a = math.radians(float(yaw_deg))
    ca, sa = math.cos(a), math.sin(a)
    return np.array(
        [[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]],
        dtype=float,
    )


@dataclass
class H10BFFDPredictor:
    """FFD-based H10B 4-channel amplitude predictor.

    Replaces the proxy sinusoidal model in ``predict_h10b_amplitude_vector_db``
    with actual antenna pattern lookups from the four H10B FFD files.

    Coordinate convention
    ---------------------
    - World frame: x forward, y left, z up (standard indoor/AMR)
    - Tag body frame: aligned with world frame rotated by tag yaw only
      (2.5D AMR — no pitch/roll)
    - Antenna local frame: z along boresight; boresight = z-axis tilted by
      ``tilt_half_angle_deg`` about the body y-axis
    - FFD pattern convention: theta measured from +z (boresight-axis),
      phi azimuth around z per CST/HFSS convention

    The four H10B antenna elements and their tilt-set assignments::

        tiltA_lhcp → LHCP_new_6G7G_11pts.ffd, pitch = +tilt_half_angle_deg
        tiltA_rhcp → RHCP_new_6G7G_11pts.ffd, pitch = +tilt_half_angle_deg
        tiltB_lhcp → LP_+45_new_6G7G_11pts.ffd, pitch = -tilt_half_angle_deg
        tiltB_rhcp → LP_-45_new_6G7G_11pts.ffd, pitch = -tilt_half_angle_deg
    """

    ffd_root: Path
    tilt_half_angle_deg: float = H10B_DEFAULT_TILT_HALF_ANGLE_DEG
    tag_height_m: float = H10B_DEFAULT_TAG_HEIGHT_M
    channel_ffd_map: dict[str, str] = field(default_factory=lambda: dict(H10B_CHANNEL_FFD_FILENAMES))

    # Populated on post_init
    patterns: dict[str, ReceiverAntennaPattern] = field(default_factory=dict, init=False, repr=False)
    ffd_paths: dict[str, Path] = field(default_factory=dict, init=False, repr=False)
    _tilt_rots: dict[str, np.ndarray] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.ffd_root = Path(self.ffd_root)
        self._load_patterns()
        self._build_tilt_rotations()

    def _load_patterns(self) -> None:
        for channel_id, filename in self.channel_ffd_map.items():
            path = self.ffd_root / filename
            if not path.exists():
                continue
            pol_mode = channel_id.split("_", 1)[-1]  # "lhcp" or "rhcp"
            self.patterns[channel_id] = ReceiverAntennaPattern.from_ffd(path, pol_mode=pol_mode)
            self.ffd_paths[channel_id] = path

    def _build_tilt_rotations(self) -> None:
        for channel in CANONICAL_H10B_CHANNELS:
            sign = _TILT_SET_SIGN.get(channel.tilt_set, 0.0)
            self._tilt_rots[channel.channel_id] = _pitch_rot(sign * self.tilt_half_angle_deg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def available_channels(self) -> list[str]:
        return list(self.patterns)

    @property
    def is_fully_loaded(self) -> bool:
        return len(self.patterns) == 4

    @property
    def prediction_source(self) -> str:
        n = len(self.patterns)
        return "ffd_4ch_pattern" if n == 4 else f"ffd_partial_{n}ch_pattern"

    def predict_amplitude_vector_db_3d(
        self,
        anchor_pos: np.ndarray,
        tag_pos: np.ndarray,
        tag_yaw_deg: float,
        *,
        scalar_amp_pred_db: float | None = None,
    ) -> np.ndarray:
        """Predict 4-channel amplitude (dB) using actual FFD patterns.

        Returns a length-4 array in canonical channel order:
        ``[tiltA_lhcp, tiltA_rhcp, tiltB_lhcp, tiltB_rhcp]``.

        If *scalar_amp_pred_db* is provided the result is expressed as
        ``scalar_amp_pred_db + pattern_offset_i`` so that the channel mean
        tracks the scalar prediction and only the inter-channel shape comes
        from the FFD.  This matches the contract expected by
        ``compute_h10b_vector_uwb_diagnostic`` in the backend solver.
        """
        anchor = np.asarray(anchor_pos, dtype=float).reshape(3)
        tag = np.asarray(tag_pos, dtype=float).reshape(3)
        d_world = anchor - tag
        dist = float(np.linalg.norm(d_world))
        if dist < 1e-3:
            fill = float(scalar_amp_pred_db) if scalar_amp_pred_db is not None else -40.0
            return np.full(4, fill, dtype=float)

        # World → tag body frame (yaw only, no roll/pitch for 2.5D AMR)
        R_w2b = _yaw_rot(float(tag_yaw_deg)).T
        d_body = R_w2b @ (d_world / dist)

        gains_db = np.full(4, np.nan, dtype=float)
        for idx, ch in enumerate(CANONICAL_H10B_CHANNELS):
            pat = self.patterns.get(ch.channel_id)
            if pat is None:
                continue
            # Body → antenna local frame (inverse of tilt rotation)
            d_ant = self._tilt_rots[ch.channel_id].T @ d_body
            n = float(np.linalg.norm(d_ant))
            if n < 1e-9:
                continue
            theta_deg, phi_deg = direction_to_pattern_angles(d_ant / n)
            gains_db[idx] = pat.gain_db(theta_deg, phi_deg)

        if scalar_amp_pred_db is None:
            return gains_db

        # Re-centre around scalar prediction so contrast information is preserved
        # without changing the per-measurement amplitude level
        finite = np.isfinite(gains_db)
        if not finite.any():
            return np.full(4, float(scalar_amp_pred_db), dtype=float)
        mean_gain = float(np.nanmean(gains_db))
        offsets = np.where(finite, gains_db - mean_gain, 0.0)
        return np.full(4, float(scalar_amp_pred_db), dtype=float) + offsets

    def predict_amplitude_vector_db_from_bearing(
        self,
        amp_pred_db: float,
        bearing_deg: float,
        yaw_deg: float,
        *,
        elevation_deg: float = 0.0,
        dist_m: float = 3.0,
    ) -> np.ndarray:
        """Drop-in replacement for the proxy ``predict_h10b_amplitude_vector_db``.

        Reconstructs 3D geometry from world-frame bearing to the candidate,
        tag yaw, and an optional elevation angle.  When elevation is unknown
        (the normal 2.5D case), *elevation_deg=0* gives a horizontal LOS.

        Args:
            amp_pred_db: Scalar amplitude prediction (dB) for the candidate.
            bearing_deg: World-frame bearing from tag to candidate (degrees).
            yaw_deg: Tag yaw in the world frame (degrees).
            elevation_deg: Elevation angle from tag to candidate (degrees).
            dist_m: Approximate range to candidate (used only for direction).
        """
        b_rad = math.radians(float(bearing_deg))
        e_rad = math.radians(float(elevation_deg))
        cos_e = math.cos(e_rad)
        r = max(float(dist_m), 0.5)
        # Anchor position in world frame relative to tag origin
        anchor_world = np.array(
            [r * cos_e * math.cos(b_rad), r * cos_e * math.sin(b_rad), r * math.sin(e_rad)],
            dtype=float,
        )
        tag_pos = np.array([0.0, 0.0, 0.0], dtype=float)
        return self.predict_amplitude_vector_db_3d(
            anchor_world, tag_pos, float(yaw_deg), scalar_amp_pred_db=float(amp_pred_db)
        )

    def predict_contrast_vector_db_from_bearing(
        self,
        amp_pred_db: float,
        bearing_deg: float,
        yaw_deg: float,
        *,
        include_auxiliary_contrasts: bool = False,
        elevation_deg: float = 0.0,
        dist_m: float = 3.0,
    ) -> tuple[tuple[str, ...], np.ndarray]:
        """Predict H10B contrast vector (dB) using FFD patterns.

        Drop-in replacement for ``predict_h10b_contrast_vector_db``.
        Returns ``(contrast_order, contrast_vec)`` in canonical order.
        """
        amp_vec = self.predict_amplitude_vector_db_from_bearing(
            amp_pred_db, bearing_deg, yaw_deg,
            elevation_deg=elevation_deg, dist_m=dist_m,
        )
        return h10b_contrast_vector_from_amplitude_vector(
            amp_vec, include_auxiliary_contrasts=include_auxiliary_contrasts
        )

    # ------------------------------------------------------------------
    # Introspection / provenance
    # ------------------------------------------------------------------

    def manifest_dict(self) -> dict[str, Any]:
        """Return a provenance record suitable for artifact manifests."""
        return {
            "prediction_source": self.prediction_source,
            "ffd_root": str(self.ffd_root),
            "tilt_half_angle_deg": self.tilt_half_angle_deg,
            "tag_height_m": self.tag_height_m,
            "uwb_center_freq_hz": H10B_UWB_CENTER_FREQ_HZ,
            "loaded_channel_count": len(self.patterns),
            "loaded_channels": {
                ch: str(self.ffd_paths.get(ch, "MISSING"))
                for ch in CANONICAL_H10B_CHANNEL_ORDER
            },
            "missing_channels": [
                ch for ch in CANONICAL_H10B_CHANNEL_ORDER if ch not in self.patterns
            ],
            "claim_boundary": (
                "ffd_based_amplitude_prediction_not_calibrated_measured_amr_validation"
            ),
            "tilt_convention": "pitch_about_body_y_axis_tiltA_positive_tiltB_negative",
            "coord_convention": "world_x_forward_y_left_z_up_body_yaw_only",
        }

    def __repr__(self) -> str:
        return (
            f"H10BFFDPredictor(ffd_root={self.ffd_root!r}, "
            f"tilt_half_angle_deg={self.tilt_half_angle_deg}, "
            f"loaded={len(self.patterns)}/4)"
        )
