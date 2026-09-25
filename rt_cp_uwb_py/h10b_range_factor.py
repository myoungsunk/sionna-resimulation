"""Physical H10B 4-channel range factor.

Models the per-channel phase-centre positions on the H10B tag body to produce
four distinct predicted ranges (one per antenna element), then evaluates the
residual under a common-mode covariance model that captures correlated ranging
errors (multipath bias, oscillator drift) shared across all channels.

Phase-centre geometry (tag body frame: x forward, y left, z up)
---------------------------------------------------------------
The H10B tag carries two tilt sets (tiltA at +alpha/2, tiltB at -alpha/2 from
the vertical z-axis, where alpha = 60 deg is the total opening angle).  Each
tilt set hosts two polarisation feeds (LHCP / RHCP) that share the same
physical antenna element, so tiltA_lhcp and tiltA_rhcp have the same
phase-centre.

With element half-length L and tilt half-angle alpha/2 = 30 deg:

  tiltA offset (body frame) = [+L*sin(30),  0,  L*cos(30)]
  tiltB offset (body frame) = [-L*sin(30),  0,  L*cos(30)]

Default L = 20 mm  ->  tiltA at [+10 mm, 0, +17 mm],
                        tiltB at [-10 mm, 0, +17 mm].

Common-mode covariance
----------------------
  Sigma = sigma_ind^2 * I + sigma_common^2 * 1 1^T

  sigma_ind    = 0.04 m  -- independent per-channel noise (thermal noise, ADC jitter)
  sigma_common = 0.06 m  -- correlated error shared across all channels
                            (common clock drift, shared multipath bias)

Claim boundary: geometry is modelled from tilt convention / tag datasheet
dimensions; not calibrated against measured AMR data.  The bias level
(sigma_common) is a plausible default, not derived from field measurements.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from rt_cp_uwb_py.h10b_channels import CANONICAL_H10B_CHANNELS, h10b_column_name
from rt_cp_uwb_py.h10b_vector_likelihood import build_common_mode_covariance


# ──────────────────────────────────────────────────────────────────────────────
#  Schema / module-level defaults
# ──────────────────────────────────────────────────────────────────────────────

H10B_RANGE_FACTOR_SCHEMA_VERSION: str = "h10b_range_factor_physical_v1"

H10B_DEFAULT_TILT_HALF_ANGLE_DEG: float = 30.0     # +/-30 deg from vertical
H10B_DEFAULT_ELEMENT_HALF_LENGTH_M: float = 0.020   # 20 mm half-element length
H10B_DEFAULT_TAG_HEIGHT_M: float = 0.80             # AMR tag mount height above floor
H10B_DEFAULT_SIGMA_IND_M: float = 0.04              # independent channel noise (m)
H10B_DEFAULT_SIGMA_COMMON_M: float = 0.06           # common-mode noise (m)


# ──────────────────────────────────────────────────────────────────────────────
#  Configuration dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class H10BPhaseCenterConfig:
    """Geometry and noise parameters for the physical H10B 4-channel range factor.

    This is an immutable, hashable dataclass so it can be created once and
    reused across many factor evaluations without allocation pressure.
    """

    tilt_half_angle_deg: float = H10B_DEFAULT_TILT_HALF_ANGLE_DEG
    element_half_length_m: float = H10B_DEFAULT_ELEMENT_HALF_LENGTH_M
    tag_height_m: float = H10B_DEFAULT_TAG_HEIGHT_M
    sigma_ind_m: float = H10B_DEFAULT_SIGMA_IND_M
    sigma_common_m: float = H10B_DEFAULT_SIGMA_COMMON_M

    def phase_center_offsets_body(self) -> np.ndarray:
        """Return (4, 3) phase-centre offsets in tag body frame (canonical channel order).

        Canonical order: [tiltA_lhcp, tiltA_rhcp, tiltB_lhcp, tiltB_rhcp].
        tiltA_lhcp and tiltA_rhcp share the tiltA phase-centre;
        tiltB_lhcp and tiltB_rhcp share the tiltB phase-centre.
        """
        a = math.radians(self.tilt_half_angle_deg)
        L = self.element_half_length_m
        tiltA = np.array([+L * math.sin(a), 0.0, L * math.cos(a)], dtype=float)
        tiltB = np.array([-L * math.sin(a), 0.0, L * math.cos(a)], dtype=float)
        return np.stack([tiltA, tiltA, tiltB, tiltB], axis=0)  # (4, 3)

    def range_covariance(self, n_valid: int) -> np.ndarray:
        """Return n_valid x n_valid common-mode range covariance matrix."""
        return build_common_mode_covariance(n_valid, self.sigma_ind_m, self.sigma_common_m)


# Module-level default config (immutable singleton)
_DEFAULT_CFG = H10BPhaseCenterConfig()


# ──────────────────────────────────────────────────────────────────────────────
#  Geometry helpers
# ──────────────────────────────────────────────────────────────────────────────

def _yaw_rot2d(yaw_deg: float) -> np.ndarray:
    """Return the 2x2 rotation matrix for a yaw (z-axis) rotation."""
    a = math.radians(float(yaw_deg))
    ca, sa = math.cos(a), math.sin(a)
    return np.array([[ca, -sa], [sa, ca]], dtype=float)


def phase_center_world_positions(
    tag_xy: np.ndarray,
    tag_yaw_deg: float,
    *,
    tag_height_m: float = H10B_DEFAULT_TAG_HEIGHT_M,
    config: H10BPhaseCenterConfig = _DEFAULT_CFG,
) -> np.ndarray:
    """Compute the four H10B phase-centre positions in the world frame.

    Args:
        tag_xy:       [x, y] tag body-centre position in world frame (m).
        tag_yaw_deg:  Tag yaw in world frame (degrees).
        tag_height_m: Height of the tag body centre above the floor (m).
                      Overrides ``config.tag_height_m`` if provided explicitly.
        config:       Phase-centre configuration.

    Returns:
        (4, 3) array of [x, y, z] phase-centre positions in world frame,
        in canonical channel order [tiltA_lhcp, tiltA_rhcp, tiltB_lhcp, tiltB_rhcp].
    """
    R2 = _yaw_rot2d(float(tag_yaw_deg))                   # (2, 2)
    offsets_body = config.phase_center_offsets_body()      # (4, 3)
    # Rotate xy part of body offsets into world frame
    xy_world = (R2 @ offsets_body[:, :2].T).T              # (4, 2)
    out = np.empty((4, 3), dtype=float)
    out[:, 0] = float(tag_xy[0]) + xy_world[:, 0]
    out[:, 1] = float(tag_xy[1]) + xy_world[:, 1]
    out[:, 2] = float(tag_height_m) + offsets_body[:, 2]   # z offset is yaw-invariant
    return out


# ──────────────────────────────────────────────────────────────────────────────
#  Range prediction
# ──────────────────────────────────────────────────────────────────────────────

def predict_h10b_range_vector(
    tag_xy: np.ndarray,
    tag_yaw_deg: float,
    candidate_pos: np.ndarray,
    *,
    tag_height_m: float = H10B_DEFAULT_TAG_HEIGHT_M,
    config: H10BPhaseCenterConfig = _DEFAULT_CFG,
) -> np.ndarray:
    """Predict per-channel ranges (m) from the four H10B phase centres to one candidate.

    Args:
        tag_xy:        [x, y] tag position in world frame (m).
        tag_yaw_deg:   Tag yaw in world frame (degrees).
        candidate_pos: [x, y, z] candidate position in world frame (m).
        tag_height_m:  Tag height above floor (m).
        config:        Phase-centre configuration.

    Returns:
        (4,) predicted ranges in canonical channel order.
    """
    pc = phase_center_world_positions(tag_xy, tag_yaw_deg, tag_height_m=tag_height_m, config=config)
    cand = np.asarray(candidate_pos, dtype=float).reshape(3)
    diffs = pc - cand.reshape(1, 3)       # (4, 3)
    return np.linalg.norm(diffs, axis=1)  # (4,)


def predict_h10b_range_matrix(
    tag_xy: np.ndarray,
    tag_yaw_deg: float,
    candidate_positions: np.ndarray,
    *,
    tag_height_m: float = H10B_DEFAULT_TAG_HEIGHT_M,
    config: H10BPhaseCenterConfig = _DEFAULT_CFG,
) -> np.ndarray:
    """Predict per-channel ranges (m) for a batch of N candidates.

    Args:
        tag_xy:               [x, y] tag position in world frame (m).
        tag_yaw_deg:          Tag yaw in world frame (degrees).
        candidate_positions:  (N, 3) candidate positions in world frame (m).
        tag_height_m:         Tag height above floor (m).
        config:               Phase-centre configuration.

    Returns:
        (N, 4) predicted ranges in canonical channel order.
    """
    pc = phase_center_world_positions(tag_xy, tag_yaw_deg, tag_height_m=tag_height_m, config=config)  # (4, 3)
    cands = np.asarray(candidate_positions, dtype=float)    # (N, 3)
    diffs = pc.reshape(1, 4, 3) - cands.reshape(-1, 1, 3)  # (N, 4, 3)  broadcast
    return np.linalg.norm(diffs, axis=2)                    # (N, 4)


# ──────────────────────────────────────────────────────────────────────────────
#  Observation extraction
# ──────────────────────────────────────────────────────────────────────────────

def _row_val(payload: Any, key: str) -> Any:
    """Safely retrieve *key* from a dict, pd.Series, or attribute-accessible object."""
    if isinstance(payload, dict):
        return payload.get(key)
    try:
        val = getattr(payload, key, None)
        if val is None and hasattr(payload, "get"):
            val = payload.get(key, None)
        return val
    except Exception:
        return None


def extract_h10b_range_observations(
    payload: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract 4-channel per-antenna range observations from a measurement payload.

    Tries canonical column names first (``h10b_tiltA_lhcp_range_m`` etc.), then
    falls back to legacy suffix names (``h10b_ant1_lhcp_range_m`` etc.).

    Args:
        payload: dict, pd.Series, or any attribute-accessible mapping that may
                 carry H10B range columns.

    Returns:
        obs_vec    (4,):  per-channel ranges (m) in canonical channel order.
                          NaN where the channel is absent or non-finite.
        valid_mask (4,):  True where obs_vec[i] is finite and positive.
    """
    obs = np.full(4, np.nan, dtype=float)
    for idx, ch in enumerate(CANONICAL_H10B_CHANNELS):
        for col in (
            h10b_column_name(ch.channel_id, "range_m"),                   # canonical
            h10b_column_name(ch.channel_id, "range_m", canonical=False),  # legacy
        ):
            val = _row_val(payload, col)
            if val is None:
                continue
            try:
                v = float(val)
                if math.isfinite(v) and v > 0.0:
                    obs[idx] = v
                    break
            except (TypeError, ValueError):
                continue
    return obs, np.isfinite(obs)


# ──────────────────────────────────────────────────────────────────────────────
#  Particle-filter log score  (batch over N candidates)
# ──────────────────────────────────────────────────────────────────────────────

def h10b_physical_range_log_score_batch(
    tag_pos: np.ndarray,
    tag_yaw_deg: float,
    candidate_positions: np.ndarray,
    obs_range_vec: np.ndarray,
    valid_mask: np.ndarray | None = None,
    *,
    config: H10BPhaseCenterConfig = _DEFAULT_CFG,
) -> np.ndarray | None:
    """Physical 4-channel range log score for a batch of N candidates.

    Computes per-candidate log P(obs | pose, candidate) under the common-mode
    covariance model, using per-channel predicted ranges that incorporate the
    antenna element phase-centre offsets.

    Args:
        tag_pos:             [x, y] or [x, y, z] tag position in world frame.
                             If 3 elements, ``tag_pos[2]`` is used as height;
                             otherwise ``config.tag_height_m`` applies.
        tag_yaw_deg:         Tag yaw in world frame (degrees).
        candidate_positions: (N, 3) candidate positions in world frame (m).
        obs_range_vec:       (4,) observed ranges (m), canonical channel order.
        valid_mask:          (4,) bool of finite/valid channels.  Derived from
                             ``np.isfinite(obs_range_vec)`` if None.
        config:              Phase-centre and noise configuration.

    Returns:
        (N,) log scores, or None if no valid observations are available.
    """
    tag_arr = np.asarray(tag_pos, dtype=float)
    tag_xy = tag_arr[:2]
    tag_h = float(tag_arr[2]) if tag_arr.size >= 3 else config.tag_height_m

    obs = np.asarray(obs_range_vec, dtype=float)
    mask = np.isfinite(obs) if valid_mask is None else np.asarray(valid_mask, dtype=bool) & np.isfinite(obs)
    n_valid = int(mask.sum())
    if n_valid == 0:
        return None

    cands = np.asarray(candidate_positions, dtype=float)  # (N, 3)
    if len(cands) == 0:
        return None

    # Predicted ranges per phase-centre: (N, 4)
    pred_matrix = predict_h10b_range_matrix(
        tag_xy, tag_yaw_deg, cands, tag_height_m=tag_h, config=config
    )

    # Subset to valid channels
    obs_valid = obs[mask]                         # (n_valid,)
    pred_valid = pred_matrix[:, mask]             # (N, n_valid)
    cov = config.range_covariance(n_valid)        # (n_valid, n_valid)

    try:
        cov_inv = np.linalg.inv(cov)
        _, log_det = np.linalg.slogdet(cov)
        log_det = float(log_det)
    except np.linalg.LinAlgError:
        cov_inv = np.linalg.pinv(cov)
        log_det = 0.0

    # Vectorised Mahalanobis distance: residuals (N, n_valid)
    residuals = obs_valid.reshape(1, -1) - pred_valid           # (N, n_valid)
    mahl = np.einsum("ni,ij,nj->n", residuals, cov_inv, residuals)  # (N,)
    normalisation = log_det + n_valid * math.log(2.0 * math.pi)
    return -0.5 * (mahl + normalisation)


# ──────────────────────────────────────────────────────────────────────────────
#  Nonlinear-optimizer residuals  (Step19 least_squares backend)
# ──────────────────────────────────────────────────────────────────────────────

def h10b_physical_range_residuals_optimizer(
    tag_pose_xy_yaw: np.ndarray,
    candidate_xyz: np.ndarray,
    obs_range_vec: np.ndarray,
    valid_mask: np.ndarray,
    weight: float,
    sw: float,
    *,
    config: H10BPhaseCenterConfig = _DEFAULT_CFG,
) -> list[float]:
    """Compute Cholesky-whitened 4-channel range residuals for the Step19 optimizer.

    The returned residuals have identity covariance when the model is correct,
    so ``sum(r**2)`` equals the negative log-likelihood (up to a constant).
    This matches the expected residual contract for ``scipy.optimize.least_squares``.

    Args:
        tag_pose_xy_yaw: [x, y, yaw_deg] from the optimizer state vector.
        candidate_xyz:   [x, y, z] candidate state.
        obs_range_vec:   (4,) observed per-channel ranges (m), canonical order.
        valid_mask:      (4,) bool — True for valid channels.
        weight:          ARM factor weight (>= 0).
        sw:              Switch variable value (0-1).
        config:          Phase-centre and noise configuration.

    Returns:
        List of n_valid whitened residual floats.  Empty list if no valid channels
        or if all observations are masked out.
    """
    tag_xy = tag_pose_xy_yaw[:2]
    tag_yaw = float(tag_pose_xy_yaw[2])

    obs = np.asarray(obs_range_vec, dtype=float)
    mask = np.asarray(valid_mask, dtype=bool) & np.isfinite(obs)
    n_valid = int(mask.sum())
    if n_valid == 0:
        return []

    pred_vec = predict_h10b_range_vector(
        tag_xy, tag_yaw, candidate_xyz,
        tag_height_m=config.tag_height_m, config=config,
    )
    obs_v = obs[mask]
    pred_v = pred_vec[mask]
    residual = obs_v - pred_v                # (n_valid,)

    cov = config.range_covariance(n_valid)  # (n_valid, n_valid)
    try:
        L_chol = np.linalg.cholesky(cov)
        whitened = np.linalg.solve(L_chol, residual)   # (n_valid,)
    except np.linalg.LinAlgError:
        sigma_fb = max(float(config.sigma_ind_m), 1e-3)
        whitened = residual / sigma_fb

    scale = math.sqrt(max(float(weight), 0.0)) * float(sw)
    return [scale * float(v) for v in whitened]


# ──────────────────────────────────────────────────────────────────────────────
#  4-channel amplitude observations
# ──────────────────────────────────────────────────────────────────────────────

def extract_h10b_amplitude_observations(
    payload: Any,
) -> tuple[np.ndarray, np.ndarray]:
    """Extract 4-channel per-antenna amplitude observations (dB) from a measurement payload.

    Parallel to ``extract_h10b_range_observations``.  Tries canonical column
    names first (``h10b_tiltA_lhcp_amplitude_db`` etc.), then falls back to
    legacy suffix names.

    Args:
        payload: dict, pd.Series, or any attribute-accessible mapping.

    Returns:
        obs_vec    (4,):  per-channel amplitudes (dB), canonical channel order.
                          NaN where absent or non-finite.
        valid_mask (4,):  True where obs_vec[i] is finite (amplitude can be negative).
    """
    obs = np.full(4, np.nan, dtype=float)
    for idx, ch in enumerate(CANONICAL_H10B_CHANNELS):
        for col in (
            h10b_column_name(ch.channel_id, "amplitude_db"),
            h10b_column_name(ch.channel_id, "amplitude_db", canonical=False),
        ):
            val = _row_val(payload, col)
            if val is None:
                continue
            try:
                v = float(val)
                if math.isfinite(v):  # amplitude in dB can legitimately be negative
                    obs[idx] = v
                    break
            except (TypeError, ValueError):
                continue
    return obs, np.isfinite(obs)


# ──────────────────────────────────────────────────────────────────────────────
#  FFD-based amplitude log score  (batch over N candidates)
# ──────────────────────────────────────────────────────────────────────────────

def h10b_ffd_amplitude_log_score_batch(
    tag_xy: np.ndarray,
    tag_yaw_deg: float,
    candidate_positions: np.ndarray,
    obs_amp_vec: np.ndarray,
    valid_mask: np.ndarray | None = None,
    *,
    ffd_predictor: Any,
    scalar_amp_pred_db_arr: np.ndarray | float | None = None,
    sigma_db: float = 4.0,
    tag_height_m: float = H10B_DEFAULT_TAG_HEIGHT_M,
) -> np.ndarray | None:
    """FFD-based 4-channel amplitude log score for a batch of N candidates.

    Uses ``H10BFFDPredictor.predict_amplitude_vector_db_3d`` to compute a
    4-channel pattern prediction for each candidate position, then evaluates
    the log score under an independent diagonal Gaussian model.

    The ``scalar_amp_pred_db_arr`` argument lets the FFD prediction be
    re-centred around the scalar (distance-based) amplitude prediction so that
    only the inter-channel *shape* comes from the FFD pattern and the overall
    amplitude level tracks the scalar model — matching the semantics expected
    by the backend solver.

    Args:
        tag_xy:                [x, y] tag position in world frame (m).
        tag_yaw_deg:           Tag yaw in world frame (degrees).
        candidate_positions:   (N, 3) candidate positions in world frame (m).
        obs_amp_vec:           (4,) observed amplitudes (dB), canonical channel order.
        valid_mask:            (4,) bool; derived from ``np.isfinite(obs_amp_vec)`` if None.
        ffd_predictor:         ``H10BFFDPredictor`` instance.  Returns None if None.
        scalar_amp_pred_db_arr:(N,) per-candidate scalar amplitude prediction (dB),
                               used to re-centre the FFD output.  If None, raw FFD
                               pattern gains are used directly.
        sigma_db:              Per-channel amplitude noise standard deviation (dB).
                               Default 4.0 dB.
        tag_height_m:          Tag body-centre height above floor (m).

    Returns:
        (N,) log scores, or None if ``ffd_predictor`` is None or no valid channels.

    Claim boundary:
        Prediction is FFD-pattern based (not proxy sinusoidal).  Not calibrated
        against measured AMR data.
    """
    if ffd_predictor is None:
        return None

    obs = np.asarray(obs_amp_vec, dtype=float)
    mask = np.isfinite(obs) if valid_mask is None else (
        np.asarray(valid_mask, dtype=bool) & np.isfinite(obs)
    )
    if not mask.any():
        return None

    cands = np.asarray(candidate_positions, dtype=float)
    N = len(cands)
    if N == 0:
        return None

    tag_arr = np.asarray(tag_xy, dtype=float)
    tag_pos_3d = np.array([float(tag_arr[0]), float(tag_arr[1]), float(tag_height_m)], dtype=float)
    tag_yaw = float(tag_yaw_deg)
    sigma = max(float(sigma_db), 0.5)
    obs_valid = obs[mask]           # (n_valid,)
    n_valid = int(mask.sum())

    # Build per-candidate scalar amplitude array
    if scalar_amp_pred_db_arr is None:
        scalar_arr: list[float | None] = [None] * N
    else:
        sa = np.asarray(scalar_amp_pred_db_arr, dtype=float)
        if sa.ndim == 0:
            scalar_arr = [float(sa)] * N
        else:
            scalar_arr = sa.tolist()

    log_scores = np.zeros(N, dtype=float)
    large_penalty = -float(n_valid) * 0.5 * (20.0 / sigma) ** 2
    for i in range(N):
        pred_vec = ffd_predictor.predict_amplitude_vector_db_3d(
            anchor_pos=cands[i],
            tag_pos=tag_pos_3d,
            tag_yaw_deg=tag_yaw,
            scalar_amp_pred_db=scalar_arr[i],
        )
        pred_valid = pred_vec[mask]
        finite_pred = np.isfinite(pred_valid)
        if not finite_pred.any():
            log_scores[i] = large_penalty
            continue
        resid = obs_valid - pred_valid
        log_scores[i] = float(np.sum(
            np.where(finite_pred, -0.5 * (resid / sigma) ** 2, 0.0)
        ))

    return log_scores


def h10b_ffd_amplitude_residuals_optimizer(
    tag_pose_xy_yaw: np.ndarray,
    candidate_xyz: np.ndarray,
    obs_amp_vec: np.ndarray,
    valid_mask: np.ndarray,
    weight: float,
    sw: float,
    *,
    ffd_predictor: Any,
    scalar_amp_pred_db: float | None = None,
    sigma_db: float = 4.0,
    tag_height_m: float = H10B_DEFAULT_TAG_HEIGHT_M,
) -> list[float]:
    """Whitened 4-channel FFD amplitude residuals for the Step19 least_squares optimizer.

    Args:
        tag_pose_xy_yaw:   [x, y, yaw_deg] from the optimizer state vector.
        candidate_xyz:     [x, y, z] candidate state.
        obs_amp_vec:       (4,) observed amplitudes (dB), canonical order.
        valid_mask:        (4,) bool — True for valid channels.
        weight:            ARM factor weight.
        sw:                Switch variable value (0–1).
        ffd_predictor:     ``H10BFFDPredictor`` instance.  Returns [] if None.
        scalar_amp_pred_db:Scalar amplitude prediction (dB) used to re-centre
                           the FFD pattern (per-candidate level tracking).
        sigma_db:          Per-channel amplitude noise std (dB).
        tag_height_m:      Tag height above floor (m).

    Returns:
        List of n_valid whitened residual floats; empty list if nothing valid.
    """
    if ffd_predictor is None:
        return []
    obs = np.asarray(obs_amp_vec, dtype=float)
    mask = np.asarray(valid_mask, dtype=bool) & np.isfinite(obs)
    if not mask.any():
        return []

    tag_xy = tag_pose_xy_yaw[:2]
    tag_yaw = float(tag_pose_xy_yaw[2]) if len(tag_pose_xy_yaw) >= 3 else 0.0
    tag_pos_3d = np.array([float(tag_xy[0]), float(tag_xy[1]), float(tag_height_m)], dtype=float)

    pred_vec = ffd_predictor.predict_amplitude_vector_db_3d(
        anchor_pos=np.asarray(candidate_xyz, dtype=float),
        tag_pos=tag_pos_3d,
        tag_yaw_deg=tag_yaw,
        scalar_amp_pred_db=scalar_amp_pred_db,
    )
    sigma = max(float(sigma_db), 0.5)
    scale = math.sqrt(max(float(weight), 0.0)) * float(sw)
    results: list[float] = []
    for i, active in enumerate(mask):
        if not active:
            continue
        pv = float(pred_vec[i])
        if not math.isfinite(pv):
            continue
        results.append(scale * (float(obs[i]) - pv) / sigma)
    return results


# ──────────────────────────────────────────────────────────────────────────────
#  Introspection / provenance
# ──────────────────────────────────────────────────────────────────────────────

def h10b_range_factor_manifest(config: H10BPhaseCenterConfig | None = None) -> dict[str, Any]:
    """Return a provenance record suitable for artifact manifests and audit trails."""
    cfg = config if config is not None else _DEFAULT_CFG
    return {
        "schema_version": H10B_RANGE_FACTOR_SCHEMA_VERSION,
        "model": "physical_phase_center_common_mode_covariance",
        "tilt_half_angle_deg": cfg.tilt_half_angle_deg,
        "element_half_length_m": cfg.element_half_length_m,
        "tag_height_m": cfg.tag_height_m,
        "sigma_ind_m": cfg.sigma_ind_m,
        "sigma_common_m": cfg.sigma_common_m,
        "channel_order": [ch.channel_id for ch in CANONICAL_H10B_CHANNELS],
        "phase_center_offsets_body_m": cfg.phase_center_offsets_body().tolist(),
        "amplitude_factor": {
            "model": "ffd_4ch_pattern_diagonal_gaussian",
            "sigma_db": 4.0,
            "prediction_source": "H10BFFDPredictor.predict_amplitude_vector_db_3d",
            "scalar_recentring": "scalar_amp_pred_db_offsets_pattern_mean",
        },
        "claim_boundary": (
            "geometry_modelled_from_tilt_convention_not_calibrated_against_measured_amr"
            "_ffd_amplitude_prediction_not_measured_pattern_validated"
        ),
    }
