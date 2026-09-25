"""H10B two-path proximity DOA estimator (heading-proxy + RSSD contrast).

Overview
--------
Two complementary paths jointly constrain the world-frame bearing
gamma_TA from the tag to the UWB anchor:

Path A --- Heading-proxy DOA
    When the AMR follows a heading policy with a *known* angular offset
    alpha_h relative to the anchor bearing, the tag heading psi_T serves
    as a geometric prior:

        gamma_TA_proxy = wrap(psi_T + alpha_h)

    Factor-graph residual (Section 6 of design):

        r_h = wrap( atan2(y_A - y_T, x_A - x_T) - psi_T - alpha_h )

    Reliability (Section 7):

        sigma_h^2 = sigma_psi^2 + sigma_policy^2 + sigma_psiA^2 + sigma_slip^2

    Supported heading policies (Section 2):

        radial_to_anchor  : AMR faces anchor        alpha_h =   0 deg
        radial_away       : AMR faces away           alpha_h = 180 deg
        anchor_on_left    : anchor on left side      alpha_h = +90 deg
        anchor_on_right   : anchor on right side     alpha_h = -90 deg
        arbitrary         : unknown relationship     alpha_h = ?   (Path A disabled)

Path B --- RSSD-based DOA  (tilt_contrast_rhcp)
    tilt_contrast_rhcp_db = tiltA_rhcp_amplitude_db - tiltB_rhcp_amplitude_db

    For body-frame bearing  beta = wrap(gamma_TA - psi_T):

        C(beta) = FFD_gain(tiltA_rhcp, beta) - FFD_gain(tiltB_rhcp, beta)

    LUT inversion: beta_est = argmin_beta |C_lut(beta) - C_obs|

    Note:  for a cosine-like contrast C(beta) ~ A*cos(beta), the Fisher
    information is *maximum at the zero-crossings* (beta ~ +/-90 deg,
    broadside geometry) where dC/dbeta is steepest.  The contrast peaks
    (beta=0/180 deg) have zero slope and are therefore unobservable by
    Path B alone.  This makes Path B and Path A *complementary*:
    heading prior is informative where RSSD is flat, and vice versa.

Combined objective (Section 4 of design)
-----------------------------------------
    For each candidate anchor position, predict beta_pred from geometry,
    then evaluate:

        log p = w_rho * [ -0.5 * (C_obs - C_pred(beta)) / sigma_C ]^2
              + w_h   * [ -0.5 * wrap(beta - alpha_h)   / sigma_h  ]^2

Branch selection (Section 5):
    When RSSD produces multiple solutions {beta_k}, select:

        k_best = argmin_k [ w_rho * C_rho(beta_k)
                           + w_h * wrap(beta_k - alpha_h)^2 / sigma_h^2 ]

NLoS regime: set weight_rssd low, weight_heading high.

Candidate circle position (Section 3):
    p(phi_A) = a + d*cos(theta_inc)*n_A
               + d*sin(theta_inc) * (e1*cos(phi_A) + e2*sin(phi_A))
    where phi_A = wrap(psi_rel + alpha_h + pi),  psi_rel = psi_T - psi_A

Claim boundary
--------------
FFD predictions are simulation-based; sigma defaults are physically
motivated but NOT calibrated against measured AMR data.
alpha_h is assumed *known* from the heading policy; arbitrary-heading
operation (alpha_h unknown) disables Path A entirely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


# ─────────────────────────────────────────────────────────────────────────────
#  Constants and heading-policy registry
# ─────────────────────────────────────────────────────────────────────────────

#: Canonical H10B channel indices (canonical order: tiltA_lhcp=0, tiltA_rhcp=1,
#: tiltB_lhcp=2, tiltB_rhcp=3)
_IDX_TILTA_RHCP: int = 1
_IDX_TILTB_RHCP: int = 3

PROXIMITY_DOA_SCHEMA_VERSION: str = "h10b_proximity_doa_v2"

#: Heading-policy registry.
#: Maps policy name -> (alpha_h_deg, sigma_policy_deg).
#:
#: alpha_h_deg   : known angular offset between tag heading psi_T and
#:                 world-frame bearing gamma_TA to the anchor (degrees).
#: sigma_policy_deg: uncertainty in alpha_h arising from imperfect
#:                   policy tracking (degrees).
HEADING_POLICIES: dict[str, tuple[float, float]] = {
    "radial_to_anchor":  (  0.0,  5.0),
    "radial_away":       (180.0,  5.0),
    "anchor_on_left":    ( 90.0,  8.0),
    "anchor_on_right":   (-90.0,  8.0),
    "arbitrary":         (  0.0, 360.0),  # sigma -> inf; Path A disabled
}

#: Default heading uncertainty components (degrees).
_DEFAULT_SIGMA_PSI_TAG_DEG:    float = 5.0
_DEFAULT_SIGMA_PSI_ANCHOR_DEG: float = 0.0   # 0 if anchor heading not used
_DEFAULT_SIGMA_SLIP_DEG:       float = 5.0

#: Module-level LUT cache for Path B.
#: Key: (id(ffd_predictor), step_deg, dist_m, elevation_deg)
_LUT_CACHE: dict[tuple[Any, ...], tuple[np.ndarray, np.ndarray]] = {}


# ─────────────────────────────────────────────────────────────────────────────
#  Configuration
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProximityDOAConfig:
    """Configuration for the two-path H10B proximity DOA estimator.

    Attributes are grouped into three sections:
      - Path B (RSSD / tilt_contrast_rhcp)
      - Path A (Heading-proxy)
      - Combined weights
    """

    # ── Path B: RSSD / tilt_contrast_rhcp ───────────────────────────────────

    sigma_contrast_db: float = 3.0
    """Noise std on tilt_contrast_rhcp_db (dB).
    sigma_C in the combined objective.  Default 3 dB."""

    beta_lut_step_deg: float = 1.0
    """Body-frame bearing LUT resolution (degrees)."""

    dist_m_for_lut: float = 3.0
    """Range used to build the LUT.  Only direction matters."""

    elevation_deg: float = 0.0
    """Tag-to-anchor elevation angle (degrees, 0 = horizontal)."""

    min_fisher_threshold: float = 0.02
    """Min Fisher I(beta) = (dC/dbeta)^2 / sigma_C^2 to declare
    RSSD DOA estimate valid (avoids broadside ambiguity)."""

    # ── Path A: Heading-proxy ────────────────────────────────────────────────

    heading_policy: str = "arbitrary"
    """Heading policy name.  See HEADING_POLICIES for valid values.
    'arbitrary' disables Path A entirely (sigma_h -> inf)."""

    alpha_h_deg: float = 0.0
    """Override alpha_h (degrees) when heading_policy = 'custom'.
    Ignored for named policies; use heading_policy instead."""

    sigma_psi_tag_deg: float = _DEFAULT_SIGMA_PSI_TAG_DEG
    """Tag yaw noise std (deg).  From IMU / odometry accuracy."""

    sigma_psi_anchor_deg: float = _DEFAULT_SIGMA_PSI_ANCHOR_DEG
    """Anchor heading noise std (deg).
    0 when anchor heading is not used in the DOA chain."""

    sigma_slip_deg: float = _DEFAULT_SIGMA_SLIP_DEG
    """Wheel-slip / motion noise std (deg).
    Increase during rotation or when wheel encoder is unreliable."""

    # ── Combined weights ─────────────────────────────────────────────────────

    weight_rssd: float = 1.0
    """w_rho: RSSD (tilt_contrast) path weight in the joint objective.
    Reduce to 0.1–0.3 in NLoS / Room C conditions."""

    weight_heading: float = 1.0
    """w_h: heading-proxy path weight in the joint objective.
    Do not increase merely because RSSD is unreliable; gate it by q-clean,
    explicit heading-policy validity, motion validity, and range consistency."""


# ─────────────────────────────────────────────────────────────────────────────
#  Result dataclasses
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HeadingProxyResult:
    """Result of Path A (heading-proxy DOA) estimation."""

    doa_world_deg: float
    """World-frame DOA to anchor: gamma_TA_proxy = wrap(psi_T + alpha_h)."""

    phi_A_proxy_deg: float
    """Anchor-frame azimuth on the candidate circle:
    phi_A_proxy = wrap(psi_rel + alpha_h + 180)   (psi_rel = psi_T - psi_A)."""

    sigma_h_deg: float
    """Total heading DOA uncertainty (degrees):
    sqrt(sigma_psi^2 + sigma_policy^2 + sigma_psiA^2 + sigma_slip^2)."""

    alpha_h_deg: float
    """Heading policy offset used (degrees)."""

    policy: str
    """Heading policy name used."""

    valid: bool
    """False when heading_policy = 'arbitrary' (sigma_h >= 360 deg)."""


@dataclass(frozen=True)
class RSSDDOAResult:
    """Result of Path B (tilt_contrast_rhcp LUT inversion) DOA estimation."""

    beta_body_deg: float
    """Estimated body-frame bearing to anchor (degrees, -180 .. +180)."""

    doa_world_deg: float
    """World-frame DOA = wrap(beta_body_deg + psi_T)."""

    contrast_obs_db: float
    """Observed tilt_contrast_rhcp_db (input)."""

    contrast_pred_db: float
    """Predicted contrast at beta_body_deg."""

    residual_db: float
    """contrast_obs - contrast_pred (dB)."""

    sigma_bearing_deg: float
    """Bearing uncertainty ~ sigma_C / |dC/dbeta|.
    Large near the contrast peaks (beta=0/180 deg)."""

    fisher_info: float
    """Fisher information I(beta) = (dC/dbeta)^2 / sigma_C^2."""

    valid: bool
    """True when fisher_info >= min_fisher_threshold."""

    n_ambiguous_roots: int
    """Number of beta values where |C_lut - C_obs| < 0.5*sigma_C."""


@dataclass(frozen=True)
class CombinedDOAResult:
    """Result of combined Path A + Path B DOA estimation."""

    beta_est_deg: float
    """Best-estimate body-frame bearing to anchor (degrees)."""

    doa_world_deg: float
    """World-frame DOA."""

    rssd_residual_db: float
    """Path B residual: contrast_obs - contrast_pred (dB)."""

    heading_residual_deg: float
    """Path A residual: wrap(beta_est - alpha_h) (degrees)."""

    rssd_log_score: float
    heading_log_score: float
    combined_log_score: float

    n_rssd_branches: int
    """Number of RSSD branches within 3*sigma_C of observation."""

    selected_branch_idx: int
    """Index (into branches list) of the selected RSSD branch."""

    source: str
    """'rssd_only' | 'heading_only' | 'combined'."""


# ─────────────────────────────────────────────────────────────────────────────
#  Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_180(angle_deg: float) -> float:
    """Wrap angle to (-180, +180]."""
    return ((float(angle_deg) + 180.0) % 360.0) - 180.0


def _get_float(payload: Any, key: str) -> float:
    """Safely read key from dict / pd.Series / attribute-accessible object."""
    if isinstance(payload, dict):
        v = payload.get(key)
    else:
        v = getattr(payload, key, None)
        if v is None and hasattr(payload, "get"):
            v = payload.get(key, None)
    if v is None:
        return math.nan
    try:
        fv = float(v)
        return fv if math.isfinite(fv) else math.nan
    except (TypeError, ValueError):
        return math.nan


# ─────────────────────────────────────────────────────────────────────────────
#  Path A helpers: heading-proxy DOA
# ─────────────────────────────────────────────────────────────────────────────

def _heading_policy_alpha_h(config: ProximityDOAConfig) -> tuple[float, float]:
    """Return (alpha_h_deg, sigma_policy_deg) for the config heading policy.

    For 'custom' policy uses config.alpha_h_deg with sigma_policy = 10 deg.
    """
    if config.heading_policy == "custom":
        return float(config.alpha_h_deg), 10.0
    entry = HEADING_POLICIES.get(config.heading_policy, HEADING_POLICIES["arbitrary"])
    return float(entry[0]), float(entry[1])


def sigma_heading_doa(config: ProximityDOAConfig) -> float:
    """Total heading DOA uncertainty sigma_h (degrees).

    Combines:
      sigma_h^2 = sigma_psi_tag^2 + sigma_policy^2 + sigma_psiA^2 + sigma_slip^2

    Returns 360.0 for 'arbitrary' heading policy.
    """
    _, sigma_policy = _heading_policy_alpha_h(config)
    return math.sqrt(
        config.sigma_psi_tag_deg   ** 2
        + sigma_policy             ** 2
        + config.sigma_psi_anchor_deg ** 2
        + config.sigma_slip_deg    ** 2
    )


def heading_proxy_estimate(
    tag_yaw_deg: float,
    *,
    config: ProximityDOAConfig = ProximityDOAConfig(),
    psi_anchor_deg: float = 0.0,
) -> HeadingProxyResult:
    """Compute Path A heading-proxy DOA estimate.

    Args:
        tag_yaw_deg:     Robot heading psi_T in world frame (degrees).
        config:          Proximity DOA configuration.
        psi_anchor_deg:  Anchor heading psi_A (degrees); used to compute
                         phi_A_proxy.  Set 0 if anchor heading is unknown.

    Returns:
        HeadingProxyResult with world-frame DOA, anchor-frame phi_A,
        sigma_h and validity flag.
    """
    alpha_h, sigma_pol = _heading_policy_alpha_h(config)
    sigma_h = sigma_heading_doa(config)
    valid = sigma_h < 180.0  # 'arbitrary' gives sigma_h >= 360

    # World-frame DOA to anchor: gamma_TA = wrap(psi_T + alpha_h)
    doa_world = _wrap_180(float(tag_yaw_deg) + alpha_h)

    # Anchor-frame azimuth: phi_A = wrap(psi_rel + alpha_h + 180)
    psi_rel = float(tag_yaw_deg) - float(psi_anchor_deg)
    phi_A = _wrap_180(psi_rel + alpha_h + 180.0)

    return HeadingProxyResult(
        doa_world_deg    = float(doa_world),
        phi_A_proxy_deg  = float(phi_A),
        sigma_h_deg      = float(sigma_h),
        alpha_h_deg      = float(alpha_h),
        policy           = config.heading_policy,
        valid            = bool(valid),
    )


def heading_proxy_residual(
    tag_xy: np.ndarray,
    tag_yaw_deg: float,
    anchor_xyz: np.ndarray,
    alpha_h_deg: float,
) -> float:
    """Factor-graph bearing residual for the heading-proxy prior (Path A).

    Implements Section 6 of the design:

        r_h = wrap( atan2(y_A - y_T, x_A - x_T) - psi_T - alpha_h )

    This is the angular difference between the *geometric* bearing from the
    tag to the anchor and the *predicted* bearing from the heading policy.

    Args:
        tag_xy:       [x_T, y_T] tag position (m).
        tag_yaw_deg:  Tag heading psi_T (degrees).
        anchor_xyz:   [x_A, y_A, z_A] anchor position (m).
        alpha_h_deg:  Heading policy offset alpha_h (degrees).

    Returns:
        r_h in degrees, in (-180, +180].  NaN if tag == anchor.
    """
    t = np.asarray(tag_xy, dtype=float)
    a = np.asarray(anchor_xyz, dtype=float)
    dx = float(a[0]) - float(t[0])
    dy = float(a[1]) - float(t[1])
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return math.nan
    gamma_TA = math.degrees(math.atan2(dy, dx))
    return _wrap_180(gamma_TA - float(tag_yaw_deg) - float(alpha_h_deg))


def heading_proxy_log_score_batch(
    tag_xy: np.ndarray,
    tag_yaw_deg: float,
    candidate_positions: np.ndarray,
    alpha_h_deg: float,
    sigma_h_deg: float,
) -> np.ndarray | None:
    """Particle-filter Gaussian log score for Path A heading-proxy DOA.

    For each candidate anchor position, computes the predicted body-frame
    bearing beta_pred = wrap(gamma_TA_pred - psi_T), then evaluates:

        log p = -0.5 * (wrap(beta_pred - alpha_h) / sigma_h)^2

    Args:
        tag_xy:              (2,) tag [x, y] in world frame (m).
        tag_yaw_deg:         Tag heading psi_T (degrees).
        candidate_positions: (N, 3) candidate [x, y, z] positions (m).
        alpha_h_deg:         Heading policy offset alpha_h (degrees).
        sigma_h_deg:         Total heading uncertainty sigma_h (degrees).

    Returns:
        (N,) log scores, or None if sigma_h >= 180 deg (heading policy
        is 'arbitrary' and the prior is uninformative).
    """
    sigma_h = max(float(sigma_h_deg), 0.1)
    if sigma_h >= 180.0:  # arbitrary policy: prior is flat
        return None

    cands = np.asarray(candidate_positions, dtype=float)
    N = len(cands)
    if N == 0:
        return None

    tag_x = float(tag_xy[0])
    tag_y = float(tag_xy[1])
    yaw   = float(tag_yaw_deg)
    ah    = float(alpha_h_deg)

    log_scores = np.empty(N, dtype=float)
    for i in range(N):
        dx = float(cands[i, 0]) - tag_x
        dy = float(cands[i, 1]) - tag_y
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            log_scores[i] = -0.5 * (180.0 / sigma_h) ** 2
            continue
        gamma_TA = math.degrees(math.atan2(dy, dx))
        # body-frame bearing
        beta_pred = _wrap_180(gamma_TA - yaw)
        # heading-proxy residual: wrap(beta_pred - alpha_h)
        r_h = _wrap_180(beta_pred - ah)
        log_scores[i] = -0.5 * (r_h / sigma_h) ** 2

    return log_scores


def heading_proxy_candidate_pos(
    anchor_xyz: np.ndarray,
    range_m: float,
    theta_inc_rad: float,
    phi_A_deg: float,
    *,
    n_A: np.ndarray | None = None,
) -> np.ndarray:
    """Compute tag candidate position on the candidate circle (Section 3).

    Implements:
        p(phi_A) = a + d*cos(theta)*n_A
                     + d*sin(theta)*(e1*cos(phi_A) + e2*sin(phi_A))

    For a ceiling-mounted (downward-facing) anchor the default is:
        n_A = [0, 0, -1],  e1 = [1, 0, 0],  e2 = [0, 1, 0]

    Args:
        anchor_xyz:    [x_A, y_A, z_A] anchor position (m).
        range_m:       Range measurement d (m).
        theta_inc_rad: Incidence angle theta_inc (radians).
        phi_A_deg:     Anchor-frame azimuth phi_A (degrees).
        n_A:           Anchor normal vector (3,); default = [0, 0, -1]
                       (ceiling anchor pointing down into room).

    Returns:
        (3,) estimated tag position [x_T, y_T, z_T] in world frame.
    """
    a = np.asarray(anchor_xyz, dtype=float).ravel()
    d = max(float(range_m), 0.01)
    theta = float(theta_inc_rad)
    phi_A_rad = math.radians(float(phi_A_deg))

    # Default normal and tangent basis
    if n_A is None:
        n = np.array([0.0, 0.0, -1.0])  # ceiling anchor
    else:
        n = np.asarray(n_A, dtype=float).ravel()
        nrm = float(np.linalg.norm(n))
        if nrm > 1e-9:
            n = n / nrm

    # Build orthonormal basis perpendicular to n
    # e1: first tangent vector (project world-x onto n's null space)
    world_x = np.array([1.0, 0.0, 0.0])
    e1 = world_x - float(np.dot(world_x, n)) * n
    e1_norm = float(np.linalg.norm(e1))
    if e1_norm < 1e-9:
        world_y = np.array([0.0, 1.0, 0.0])
        e1 = world_y - float(np.dot(world_y, n)) * n
        e1_norm = float(np.linalg.norm(e1))
    e1 = e1 / max(e1_norm, 1e-9)
    e2 = np.cross(n, e1)  # e2 = n x e1

    p = (a
         + d * math.cos(theta) * n
         + d * math.sin(theta) * (math.cos(phi_A_rad) * e1 + math.sin(phi_A_rad) * e2))
    return p


# ─────────────────────────────────────────────────────────────────────────────
#  Path B helpers: RSSD / tilt_contrast_rhcp LUT
# ─────────────────────────────────────────────────────────────────────────────

def build_tilt_contrast_rhcp_lut(
    ffd_predictor: Any,
    *,
    config: ProximityDOAConfig = ProximityDOAConfig(),
    amp_pred_db: float = -60.0,
    force_rebuild: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    """Pre-compute tilt_contrast_rhcp LUT over body-frame bearing (Path B).

    Uses ffd_predictor.predict_amplitude_vector_db_from_bearing with yaw_deg=0
    so that bearing_deg IS the body-frame angle beta directly.

    Returns:
        (beta_grid_deg, contrast_lut_db): both (M,) arrays.
        beta_grid_deg in [-180, 180) at config.beta_lut_step_deg resolution.

    Raises:
        ValueError: if ffd_predictor is None.
    """
    if ffd_predictor is None:
        raise ValueError("ffd_predictor must not be None to build contrast LUT")

    cache_key: tuple[Any, ...] = (
        id(ffd_predictor),
        float(config.beta_lut_step_deg),
        float(config.dist_m_for_lut),
        float(config.elevation_deg),
    )
    if not force_rebuild and cache_key in _LUT_CACHE:
        return _LUT_CACHE[cache_key]

    step = max(float(config.beta_lut_step_deg), 0.1)
    beta_grid = np.arange(-180.0, 180.0, step)
    M = len(beta_grid)
    contrast_lut = np.full(M, np.nan, dtype=float)

    for i, beta in enumerate(beta_grid):
        try:
            amp_vec = ffd_predictor.predict_amplitude_vector_db_from_bearing(
                float(amp_pred_db),
                bearing_deg=float(beta),   # = body-frame angle when yaw=0
                yaw_deg=0.0,
                elevation_deg=float(config.elevation_deg),
                dist_m=float(config.dist_m_for_lut),
            )
            arr = np.asarray(amp_vec, dtype=float)
            if arr.size >= 4:
                a = float(arr[_IDX_TILTA_RHCP])
                b = float(arr[_IDX_TILTB_RHCP])
                if math.isfinite(a) and math.isfinite(b):
                    contrast_lut[i] = a - b
        except Exception:
            pass

    _LUT_CACHE[cache_key] = (beta_grid, contrast_lut)
    return beta_grid, contrast_lut


def clear_lut_cache() -> None:
    """Clear the module-level LUT cache (e.g., after reloading FFD files)."""
    _LUT_CACHE.clear()


def _interp_lut(beta_deg: float, beta_grid: np.ndarray, contrast_lut: np.ndarray) -> float:
    """Linear interpolation on the circular bearing LUT."""
    n = len(beta_grid)
    if n == 0:
        return math.nan
    step = float(beta_grid[1] - beta_grid[0]) if n > 1 else 1.0
    b = _wrap_180(float(beta_deg))
    idx_f = (b - float(beta_grid[0])) / step
    idx_lo = int(math.floor(idx_f)) % n
    idx_hi = (idx_lo + 1) % n
    t = idx_f - math.floor(idx_f)
    v_lo = float(contrast_lut[idx_lo])
    v_hi = float(contrast_lut[idx_hi])
    if not math.isfinite(v_lo) and not math.isfinite(v_hi):
        return math.nan
    if not math.isfinite(v_lo):
        return v_hi
    if not math.isfinite(v_hi):
        return v_lo
    return v_lo + t * (v_hi - v_lo)


def _lut_deriv(
    beta_deg: float,
    beta_grid: np.ndarray,
    contrast_lut: np.ndarray,
    *,
    delta_deg: float = 2.0,
) -> float:
    """Numerical first derivative dC/dbeta (dB/deg)."""
    c_plus  = _interp_lut(beta_deg + delta_deg, beta_grid, contrast_lut)
    c_minus = _interp_lut(beta_deg - delta_deg, beta_grid, contrast_lut)
    if not math.isfinite(c_plus) or not math.isfinite(c_minus):
        return 0.0
    return (c_plus - c_minus) / (2.0 * delta_deg)


def rssd_doa_estimate(
    tilt_contrast_obs_db: float,
    tag_yaw_deg: float,
    *,
    ffd_predictor: Any,
    config: ProximityDOAConfig = ProximityDOAConfig(),
    beta_prior_deg: float | None = None,
) -> RSSDDOAResult:
    """Invert the tilt_contrast_rhcp LUT to estimate body-frame bearing (Path B).

    Finds beta_est = argmin_beta |C_lut(beta) - C_obs|, then converts to
    world-frame DOA via  gamma_TA = wrap(beta_est + psi_T).

    When beta_prior_deg is given (e.g., from Path A), the root closest to
    the prior is selected to resolve sign ambiguity.

    Claim boundary: FFD-based prediction; not calibrated against measured data.
    """
    if ffd_predictor is None:
        raise ValueError("ffd_predictor must not be None")

    beta_grid, contrast_lut = build_tilt_contrast_rhcp_lut(ffd_predictor, config=config)
    C_obs = float(tilt_contrast_obs_db)
    sigma_C = max(float(config.sigma_contrast_db), 0.1)

    valid_lut = np.isfinite(contrast_lut)
    abs_diff  = np.where(valid_lut, np.abs(contrast_lut - C_obs), np.inf)

    n_ambiguous = int(np.sum(abs_diff < 0.5 * sigma_C))
    best_idx    = int(np.argmin(abs_diff))
    beta_coarse = float(beta_grid[best_idx])

    # Disambiguation using prior
    if beta_prior_deg is not None and n_ambiguous > 1:
        cand_mask    = abs_diff < 3.0 * sigma_C
        cand_indices = np.where(cand_mask)[0]
        if len(cand_indices) > 0:
            prior_b  = _wrap_180(float(beta_prior_deg))
            best_c   = int(cand_indices[0])
            best_d   = abs(_wrap_180(float(beta_grid[cand_indices[0]]) - prior_b))
            for ci in cand_indices[1:]:
                d = abs(_wrap_180(float(beta_grid[ci]) - prior_b))
                if d < best_d:
                    best_d, best_c = d, int(ci)
            beta_coarse = float(beta_grid[best_c])
            best_idx    = best_c

    # Sub-degree parabolic refinement
    lo = max(best_idx - 1, 0)
    hi = min(best_idx + 1, len(beta_grid) - 1)
    if lo < best_idx < hi and valid_lut[lo] and valid_lut[hi]:
        fa = (float(contrast_lut[lo])       - C_obs) ** 2
        fb = (float(contrast_lut[best_idx]) - C_obs) ** 2
        fc = (float(contrast_lut[hi])       - C_obs) ** 2
        step  = float(beta_grid[1] - beta_grid[0])
        denom = 2.0 * (fa - 2.0 * fb + fc)
        if abs(denom) > 1e-9:
            offset = -step * (fc - fa) / (2.0 * denom)
            if abs(offset) < step:
                beta_coarse += offset

    beta_est   = _wrap_180(beta_coarse)
    doa_world  = _wrap_180(beta_est + float(tag_yaw_deg))
    c_pred     = _interp_lut(beta_est, beta_grid, contrast_lut)
    residual   = (C_obs - c_pred) if math.isfinite(c_pred) else math.nan

    dC         = _lut_deriv(beta_est, beta_grid, contrast_lut)
    if abs(dC) < 1e-9:
        fisher, sigma_bear = 0.0, math.inf
    else:
        fisher     = float((dC / sigma_C) ** 2)
        sigma_bear = abs(sigma_C / dC)

    return RSSDDOAResult(
        beta_body_deg      = float(beta_est),
        doa_world_deg      = float(doa_world),
        contrast_obs_db    = float(C_obs),
        contrast_pred_db   = float(c_pred),
        residual_db        = float(residual),
        sigma_bearing_deg  = float(sigma_bear),
        fisher_info        = float(fisher),
        valid              = float(fisher) >= float(config.min_fisher_threshold),
        n_ambiguous_roots  = int(n_ambiguous),
    )


def rssd_doa_log_score_batch(
    tag_xy: np.ndarray,
    tag_yaw_deg: float,
    candidate_positions: np.ndarray,
    tilt_contrast_obs_db: float,
    *,
    ffd_predictor: Any,
    config: ProximityDOAConfig = ProximityDOAConfig(),
) -> np.ndarray | None:
    """Particle-filter Gaussian log score for Path B (tilt_contrast_rhcp).

    For each candidate, predicts beta_pred from geometry then:

        log p = -0.5 * (C_obs - C_pred(beta_pred))^2 / sigma_C^2

    Note: this is the predict-compare direction; no LUT inversion per particle.

    Returns:
        (N,) log scores, or None if ffd_predictor is None or C_obs not finite.
    """
    if ffd_predictor is None:
        return None
    C_obs = float(tilt_contrast_obs_db)
    if not math.isfinite(C_obs):
        return None

    cands = np.asarray(candidate_positions, dtype=float)
    N = len(cands)
    if N == 0:
        return None

    sigma_C      = max(float(config.sigma_contrast_db), 0.1)
    large_penalty = -0.5 * (20.0 / sigma_C) ** 2
    tag_x, tag_y = float(tag_xy[0]), float(tag_xy[1])
    yaw           = float(tag_yaw_deg)

    beta_grid, contrast_lut = build_tilt_contrast_rhcp_lut(ffd_predictor, config=config)

    log_scores = np.empty(N, dtype=float)
    for i in range(N):
        dx = float(cands[i, 0]) - tag_x
        dy = float(cands[i, 1]) - tag_y
        if abs(dx) < 1e-6 and abs(dy) < 1e-6:
            log_scores[i] = large_penalty
            continue
        beta_pred = _wrap_180(math.degrees(math.atan2(dy, dx)) - yaw)
        C_pred    = _interp_lut(beta_pred, beta_grid, contrast_lut)
        if not math.isfinite(C_pred):
            log_scores[i] = large_penalty
            continue
        log_scores[i] = -0.5 * ((C_obs - C_pred) / sigma_C) ** 2

    return log_scores


# ─────────────────────────────────────────────────────────────────────────────
#  Combined Path A + Path B
# ─────────────────────────────────────────────────────────────────────────────

def combined_doa_log_score_batch(
    tag_xy: np.ndarray,
    tag_yaw_deg: float,
    candidate_positions: np.ndarray,
    tilt_contrast_obs_db: float,
    *,
    ffd_predictor: Any,
    config: ProximityDOAConfig = ProximityDOAConfig(),
) -> np.ndarray | None:
    """Joint Path A + Path B particle-filter log score.

    Computes:
        log p = w_rho  * rssd_log_score(candidate)
              + w_h    * heading_log_score(candidate)

    For each candidate, both paths predict independently and their scores
    are added (log-domain product of independent Gaussians).

    NLoS operation: set config.weight_rssd low (~0.2), config.weight_heading
    high (~1.0) so the heading prior guides the filter when RSSD is unreliable.

    Returns:
        (N,) combined log scores, or None if both paths are unavailable.
    """
    alpha_h, _ = _heading_policy_alpha_h(config)
    sigma_h     = sigma_heading_doa(config)

    # Path A
    w_h = float(config.weight_heading)
    path_a: np.ndarray | None = None
    if sigma_h < 180.0 and w_h > 0.0:
        path_a = heading_proxy_log_score_batch(
            tag_xy, tag_yaw_deg, candidate_positions, alpha_h, sigma_h,
        )

    # Path B
    w_rho = float(config.weight_rssd)
    path_b: np.ndarray | None = None
    if w_rho > 0.0:
        path_b = rssd_doa_log_score_batch(
            tag_xy, tag_yaw_deg, candidate_positions, tilt_contrast_obs_db,
            ffd_predictor=ffd_predictor, config=config,
        )

    if path_a is None and path_b is None:
        return None

    N = len(np.asarray(candidate_positions, dtype=float))
    result = np.zeros(N, dtype=float)
    if path_a is not None:
        result += w_h   * path_a
    if path_b is not None:
        result += w_rho * path_b
    return result


def combined_doa_residuals_optimizer(
    tag_pose_xy_yaw: np.ndarray,
    candidate_xyz: np.ndarray,
    tilt_contrast_obs_db: float,
    weight: float,
    sw: float,
    *,
    ffd_predictor: Any,
    config: ProximityDOAConfig = ProximityDOAConfig(),
) -> list[float]:
    """Step-19 whitened residuals for the combined Path A + Path B DOA factor.

    Returns up to two residuals:
      [0] rssd_residual  : w_rho * (C_obs - C_pred(beta)) / sigma_C  (Path B)
      [1] heading_residual: w_h   * wrap(beta - alpha_h)   / sigma_h  (Path A)

    Each residual is scaled by  sqrt(weight) * sw.

    Empty list returned if nothing is computable (no FFD predictor, no valid
    heading policy, or coincident tag-anchor positions).
    """
    w = float(weight)
    if w <= 0.0:
        return []

    pose = np.asarray(tag_pose_xy_yaw, dtype=float).ravel()
    tag_x   = float(pose[0])
    tag_y   = float(pose[1])
    tag_yaw = float(pose[2]) if pose.size >= 3 else 0.0
    cand    = np.asarray(candidate_xyz, dtype=float).ravel()
    dx      = float(cand[0]) - tag_x
    dy      = float(cand[1]) - tag_y
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return []

    gamma_TA  = math.degrees(math.atan2(dy, dx))
    beta_pred = _wrap_180(gamma_TA - tag_yaw)
    scale     = math.sqrt(max(w, 0.0)) * float(sw)
    residuals: list[float] = []

    # Path B: RSSD residual
    C_obs = float(tilt_contrast_obs_db)
    w_rho = float(config.weight_rssd)
    if (ffd_predictor is not None and math.isfinite(C_obs) and w_rho > 0.0):
        try:
            beta_grid, contrast_lut = build_tilt_contrast_rhcp_lut(
                ffd_predictor, config=config
            )
            C_pred = _interp_lut(beta_pred, beta_grid, contrast_lut)
            if math.isfinite(C_pred):
                sigma_C = max(float(config.sigma_contrast_db), 0.1)
                r_rho   = math.sqrt(w_rho) * scale * (C_obs - C_pred) / sigma_C
                residuals.append(r_rho)
        except Exception:
            pass

    # Path A: heading prior residual
    alpha_h, _ = _heading_policy_alpha_h(config)
    sigma_h    = sigma_heading_doa(config)
    w_h        = float(config.weight_heading)
    if sigma_h < 180.0 and w_h > 0.0:
        r_h = _wrap_180(beta_pred - alpha_h)
        r_heading = math.sqrt(w_h) * scale * r_h / max(sigma_h, 0.1)
        residuals.append(r_heading)

    return residuals


# ─────────────────────────────────────────────────────────────────────────────
#  Branch selection (Section 5 of design)
# ─────────────────────────────────────────────────────────────────────────────

def branch_select_by_heading_prior(
    beta_candidates_deg: list[float] | np.ndarray,
    rssd_cost_per_branch: list[float] | np.ndarray,
    alpha_h_deg: float,
    sigma_h_deg: float,
    weight_rssd: float = 1.0,
    weight_heading: float = 1.0,
) -> tuple[int, float]:
    """Select the best RSSD branch using the heading-prior as a tiebreaker.

    Implements Section 5 of the design:

        k_best = argmin_k [ w_rho * C_rho(beta_k)
                           + w_h  * wrap(beta_k - alpha_h)^2 / sigma_h^2 ]

    Args:
        beta_candidates_deg:  Body-frame bearing for each RSSD branch (degrees).
        rssd_cost_per_branch: C_rho(beta_k) for each branch (lower = better fit).
        alpha_h_deg:          Heading policy offset alpha_h (degrees).
        sigma_h_deg:          Total heading uncertainty sigma_h (degrees).
        weight_rssd:          w_rho.
        weight_heading:       w_h.

    Returns:
        (best_idx, best_cost): index of the selected branch and its total cost.
    """
    betas = np.asarray(beta_candidates_deg, dtype=float)
    costs = np.asarray(rssd_cost_per_branch, dtype=float)
    if len(betas) == 0:
        return (-1, math.inf)
    if len(betas) == 1:
        return (0, float(costs[0]))

    sigma_h = max(float(sigma_h_deg), 0.1)
    total_costs = np.empty(len(betas), dtype=float)
    for k, (beta, c_rho) in enumerate(zip(betas, costs)):
        r_h        = _wrap_180(float(beta) - float(alpha_h_deg))
        heading_cost = (r_h / sigma_h) ** 2
        total_costs[k] = float(weight_rssd) * float(c_rho) + float(weight_heading) * heading_cost

    best_idx = int(np.argmin(total_costs))
    return (best_idx, float(total_costs[best_idx]))


# ─────────────────────────────────────────────────────────────────────────────
#  Fisher information (Path B informativeness)
# ─────────────────────────────────────────────────────────────────────────────

def tilt_contrast_fisher_at_beta(
    beta_deg: float,
    ffd_predictor: Any,
    *,
    config: ProximityDOAConfig = ProximityDOAConfig(),
    delta_deg: float = 2.0,
) -> float:
    """Path B Fisher information I(beta) = (dC/dbeta)^2 / sigma_C^2.

    For a cosine-like contrast C(beta) = A*cos(beta):
      - I peaks at the zero crossings (beta ~ +/-90 deg, broadside geometry)
        where the slope dC/dbeta is maximum.
      - I = 0 at the contrast extremes (beta = 0/180 deg) where the slope is flat.

    This is complementary to Path A (heading prior), which is most informative
    at beta ~ alpha_h (where the AMR is expected to be).

    Returns 0.0 if ffd_predictor is None.
    """
    if ffd_predictor is None:
        return 0.0
    try:
        beta_grid, contrast_lut = build_tilt_contrast_rhcp_lut(ffd_predictor, config=config)
    except ValueError:
        return 0.0
    sigma_C = max(float(config.sigma_contrast_db), 0.1)
    dC = _lut_deriv(float(beta_deg), beta_grid, contrast_lut, delta_deg=delta_deg)
    return float((dC / sigma_C) ** 2)


def tilt_contrast_fisher_curve(
    ffd_predictor: Any,
    *,
    config: ProximityDOAConfig = ProximityDOAConfig(),
    delta_deg: float = 2.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Path B Fisher information I(beta) over the full [-180, 180) bearing range.

    Returns:
        (beta_grid_deg, fisher_curve): both (M,) arrays.
        Empty arrays if ffd_predictor is None.
    """
    if ffd_predictor is None:
        empty = np.empty(0, dtype=float)
        return empty, empty
    beta_grid, contrast_lut = build_tilt_contrast_rhcp_lut(ffd_predictor, config=config)
    sigma_C = max(float(config.sigma_contrast_db), 0.1)
    fisher_curve = np.array([
        (_lut_deriv(float(b), beta_grid, contrast_lut, delta_deg=delta_deg) / sigma_C) ** 2
        for b in beta_grid
    ])
    return beta_grid, fisher_curve


# ─────────────────────────────────────────────────────────────────────────────
#  Payload extraction
# ─────────────────────────────────────────────────────────────────────────────

def extract_tilt_contrast_rhcp_db(payload: Any) -> tuple[float, bool]:
    """Extract tilt_contrast_rhcp_db = tiltA_rhcp - tiltB_rhcp from payload.

    Tries canonical column names first, then legacy fallbacks.

    Returns:
        (contrast_db, valid): NaN + False if either channel is missing.
    """
    a_rhcp = _get_float(payload, "h10b_tiltA_rhcp_amplitude_db")
    b_rhcp = _get_float(payload, "h10b_tiltB_rhcp_amplitude_db")
    if not math.isfinite(a_rhcp):
        a_rhcp = _get_float(payload, "h10b_ant1_rhcp_amplitude_db")
    if not math.isfinite(b_rhcp):
        b_rhcp = _get_float(payload, "h10b_ant2_rhcp_amplitude_db")
    if math.isfinite(a_rhcp) and math.isfinite(b_rhcp):
        return (a_rhcp - b_rhcp), True
    return math.nan, False


# ─────────────────────────────────────────────────────────────────────────────
#  Provenance / manifest
# ─────────────────────────────────────────────────────────────────────────────

def proximity_doa_manifest(
    config: ProximityDOAConfig | None = None,
) -> dict[str, Any]:
    """Return a provenance record for artifact manifests and audit trails."""
    cfg = config or ProximityDOAConfig()
    alpha_h, sigma_pol = _heading_policy_alpha_h(cfg)
    sigma_h = sigma_heading_doa(cfg)
    return {
        "schema_version": PROXIMITY_DOA_SCHEMA_VERSION,
        "paths": {
            "path_A_heading_proxy": {
                "description": "AMR heading + known policy offset alpha_h as geometric DOA prior",
                "formula": "r_h = wrap(atan2(y_A-y_T, x_A-x_T) - psi_T - alpha_h)",
                "heading_policy": cfg.heading_policy,
                "alpha_h_deg": float(alpha_h),
                "sigma_h_deg": float(sigma_h),
                "sigma_components_deg": {
                    "sigma_psi_tag":    cfg.sigma_psi_tag_deg,
                    "sigma_policy":     float(sigma_pol),
                    "sigma_psi_anchor": cfg.sigma_psi_anchor_deg,
                    "sigma_slip":       cfg.sigma_slip_deg,
                },
                "enabled": sigma_h < 180.0,
            },
            "path_B_rssd_contrast": {
                "description": "tiltA_rhcp - tiltB_rhcp LUT inversion for body-frame bearing",
                "formula": "beta_est = argmin_beta |C_lut(beta) - C_obs|",
                "sigma_contrast_db": cfg.sigma_contrast_db,
                "beta_lut_step_deg": cfg.beta_lut_step_deg,
                "fisher_note": (
                    "Fisher info peaks at contrast zero-crossings (broadside);"
                    " complementary to Path A"
                ),
            },
        },
        "combined_weights": {
            "weight_rssd":    cfg.weight_rssd,
            "weight_heading": cfg.weight_heading,
            "nlos_recommendation": "reduce weight_rssd, increase weight_heading in NLoS",
        },
        "heading_policies": {
            k: {"alpha_h_deg": v[0], "sigma_policy_deg": v[1]}
            for k, v in HEADING_POLICIES.items()
        },
        "signal": (
            "tilt_contrast_rhcp_db = "
            "h10b_tiltA_rhcp_amplitude_db - h10b_tiltB_rhcp_amplitude_db"
        ),
        "candidate_circle_integration": {
            "function": "heading_proxy_candidate_pos",
            "formula": "p(phi_A) = a + d*cos(theta)*n_A + d*sin(theta)*(e1*cos(phi_A)+e2*sin(phi_A))",
            "phi_A_proxy": "wrap(psi_rel + alpha_h + 180)",
        },
        "branch_selection": {
            "function": "branch_select_by_heading_prior",
            "formula": "k_best = argmin_k [w_rho*C_rho(beta_k) + w_h*wrap(beta_k-alpha_h)^2/sigma_h^2]",
        },
        "claim_boundary": (
            "ffd_based_tilt_contrast_prediction_not_calibrated_against_measured_amr_data"
            "_sigma_defaults_are_physically_motivated_not_field_measured"
            "_alpha_h_assumed_known_from_heading_policy"
        ),
    }
