"""MODEL-003 v3 joint range and signed polarization EKF math."""

from dataclasses import KW_ONLY, dataclass

import numpy as np

from tb3_model003_filter import GATE_JOINT, GATE_RANGE, predict, range_model
from tb3_model003_v3_characterization import sigma_at
from tb3_model003_v3_filter import colored_transition, joseph_update, student_noise
from tb3_model003_v3_range import RangeModel, initialize_range, predict_range, range_measurement


@dataclass(frozen=True)
class JointModel:
    arm: str
    motion_dim: int
    anchor_xy: np.ndarray
    anchor_dz: float
    thermal_s_variance: float
    c2_s: dict
    _: KW_ONLY
    range_options: RangeModel | None = None
    length_m: float | None = None
    length_rad: float | None = None
    nugget: float = 0.0
    c3_white: bool = False
    site_corr: float = 0.0
    site_count: int = 0
    consider_s_variance: float = 0.0
    tail_df: float | None = None

    def __post_init__(self):
        _, *decorations = self.arm.split("+")
        anchor = np.asarray(self.anchor_xy, dtype=float)
        variances = [self.thermal_s_variance, self.consider_s_variance]
        if (self.base not in {"J4", "J-V", "J-C", "J-CS", "J-CI", "S-V", "S-C"}
                or len(decorations) != len(set(decorations)) or set(decorations) - {"K", "T"}
                or self.motion_dim not in (4, 5) or anchor.shape != (2,)
                or not np.isfinite(anchor).all() or not np.isfinite(self.anchor_dz)
                or not np.isfinite(variances).all() or min(variances) < 0
                or not 0 <= self.site_corr <= 1 or not 0 <= self.nugget < 1):
            raise ValueError("Invalid v3 polarization model")
        if self.base.startswith("S-"):
            if self.range_options is not None or decorations:
                raise ValueError("S-V and S-C do not take range models or suffixes")
        elif (self.range_options is None or self.range_options.motion_dim != self.motion_dim
              or not np.array_equal(self.range_options.anchor_xy, anchor)
              or self.range_options.anchor_dz != self.anchor_dz):
            raise ValueError("Joint arms need a range model with the same anchor and motion block")
        if self.colored_s:
            lengths = np.asarray([self.length_m, self.length_rad], dtype=float)
            if not np.isfinite(lengths).all() or np.any(lengths <= 0):
                raise ValueError("Colored polarization needs positive distance and yaw lengths")
        if self.base == "J-CS":
            if not isinstance(self.site_count, (int, np.integer)) or self.site_count <= 0:
                raise ValueError("J-CS needs previously indexed evaluation-path sites")
        elif self.site_count != 0 or self.site_corr != 0:
            raise ValueError("Only J-CS carries Schmidt site memory")
        if not self.has_s_consider and self.consider_s_variance != 0:
            raise ValueError("Only +K carries the fixed C5 polarization bias state")
        if "T" in decorations:
            if self.base not in {"J-C", "J-CS"} or self.tail_df is None or np.isnan(self.tail_df) or self.tail_df < 3:
                raise ValueError("Only J-C and J-CS allow the +T Student-t update with df >= 3")
        elif self.tail_df is not None:
            raise ValueError("Tail degrees of freedom require the +T arm")

    @property
    def base(self):
        return self.arm.split("+", 1)[0]

    @property
    def colored_s(self):
        return self.base in {"J-C", "J-CS", "S-C"} and not self.c3_white

    @property
    def s_color_column(self):
        return self.motion_dim if self.range_options is None else self.range_options.active_dim

    @property
    def active_dim(self):
        return self.s_color_column + int(self.colored_s)

    @property
    def has_range_consider(self):
        return self.range_options is not None and self.range_options.arm == "R-MC"

    @property
    def has_s_consider(self):
        return "K" in self.arm.split("+")[1:]

    @property
    def s_consider_column(self):
        return self.active_dim + int(self.has_range_consider)

    @property
    def site_start(self):
        return self.s_consider_column + int(self.has_s_consider)

    @property
    def state_dim(self):
        return self.site_start + self.site_count

    @property
    def range_indices(self):
        active = np.arange(self.range_options.active_dim)
        return np.r_[active, self.active_dim] if self.has_range_consider else active


def _s_variance(mean, model):
    distance, _ = range_model(mean, model.anchor_xy, model.anchor_dz)
    sigma, supported = sigma_at(model.c2_s, distance)
    return sigma**2, supported


def _s_color_target(variance, model):
    return variance * (1.0 - model.site_corr) * (1.0 - model.nugget)


def initialize_joint(mean, cov, model):
    """Initialize the motion, active colored and fixed Schmidt blocks."""
    mean = np.asarray(mean, dtype=float)
    if mean.shape[-1] != model.motion_dim or not np.isfinite(mean).all():
        raise ValueError("Joint initialization needs the finite motion block only")
    prefix = mean.shape[:-1]
    cov = np.broadcast_to(cov, prefix + (model.motion_dim,) * 2)
    if not np.isfinite(cov).all():
        raise ValueError("Joint initialization needs finite motion covariance")
    state, prior = np.zeros(prefix + (model.state_dim,)), np.zeros(prefix + (model.state_dim,) * 2)
    if model.range_options is None:
        state[..., :model.motion_dim] = mean
        prior[..., :model.motion_dim, :model.motion_dim] = cov
    else:
        initial_state, initial_cov = initialize_range(mean, cov, model.range_options)
        indices = model.range_indices
        state[..., indices] = initial_state
        prior[..., indices[:, None], indices] = initial_cov
    if model.colored_s:
        s_variance, _ = _s_variance(state, model)
        col = model.s_color_column
        prior[..., col, col] = _s_color_target(s_variance, model)
    if model.has_s_consider:
        col = model.s_consider_column
        prior[..., col, col] = model.consider_s_variance
    if model.site_count:
        sites = np.arange(model.site_start, model.state_dim)
        prior[..., sites, sites] = 1.0
    return state, prior


def predict_joint(mean, cov, distance_m, gyro_rad, dt_s, model, *,
                  angular_travel_rad=None, restart_pose=None):
    """Propagate EKF motion and independent range/s colored processes."""
    if model.range_options is None:
        state, prior = predict(mean, cov, distance_m, gyro_rad, dt_s,
                               motion_dim=model.motion_dim, angular_travel_rad=angular_travel_rad,
                               restart_pose=restart_pose)
    else:
        state, prior = predict_range(mean, cov, distance_m, gyro_rad, dt_s, model.range_options,
                                     angular_travel_rad=angular_travel_rad, restart_pose=restart_pose)
    if model.colored_s:
        s_variance, _ = _s_variance(state, model)
        phi, process = colored_transition(distance_m, gyro_rad, model.length_m, model.length_rad,
                                          _s_color_target(s_variance, model))
        col = model.s_color_column
        state[..., col] *= phi
        prior[..., col, :] *= phi[..., None]
        prior[..., :, col] *= phi[..., None]
        prior[..., col, col] += process
    return state, prior


def _signed_s_row(mean, observed, expected, s_jacobian, s_m1r_variance, model, site_index):
    variance, supported = _s_variance(mean, model)
    shape = mean.shape[:-1]
    prediction = np.broadcast_to(np.asarray(expected, dtype=float), shape).copy()
    jac = np.zeros_like(mean)
    jac[..., :3] = s_jacobian
    if model.site_count:
        if site_index is None:
            raise ValueError("J-CS needs the frozen site index for this packet")
        sites = np.broadcast_to(site_index, shape)
        if sites.dtype.kind not in "iu" or np.any((sites < 0) | (sites >= model.site_count)):
            raise ValueError("J-CS site index is outside the frozen path map")
        columns = (model.site_start + sites)[..., None]
        loading = np.sqrt(variance * model.site_corr)[..., None]
        np.put_along_axis(jac, columns, loading, axis=-1)
        prediction += (np.take_along_axis(mean, columns, axis=-1) * loading)[..., 0]
    if model.has_s_consider:
        column = model.s_consider_column
        jac[..., column] = 1.0
        prediction += mean[..., column]
    independent = variance * (1.0 - model.site_corr)
    if model.colored_s:
        col = model.s_color_column
        jac[..., col] = 1.0
        prediction += mean[..., col]
        independent *= model.nugget
    elif model.base in {"J4", "J-CI"}:
        independent = np.full(shape, model.c2_s["white_variance"])
    marginal = np.broadcast_to(s_m1r_variance, shape)
    s_noise = model.thermal_s_variance + independent + marginal
    residual = np.broadcast_to(observed, shape) - prediction
    available = (supported & np.isfinite(residual) & np.isfinite(jac).all(axis=-1)
                 & np.isfinite(s_noise) & (marginal >= 0) & (s_noise >= 0))
    return residual, jac, s_noise, available, supported


def _scalar_nis(cov, residual, jac, variance, available):
    nis = np.full(residual.shape, np.nan)
    row = jac[available]
    innovation = (row[:, None, :] @ cov[available] @ row[..., None])[:, 0, 0] + variance[available]
    if not np.isfinite(innovation).all() or np.any(innovation <= 0):
        raise ValueError("Scalar gate requires finite positive innovation variance")
    nis[available] = residual[available]**2 / innovation
    return nis


def update_joint(mean, cov, observed_range, observed_s, s_expected, s_jacobian, s_m1r_variance, model, *,
                 site_index=None):
    """Gate range first, then update with the accepted range/s measurement rows."""
    shape, width = mean.shape[:-1], mean.shape[-1]
    if width != model.state_dim:
        raise ValueError("Joint state does not match the declared arm layout")
    s_error, s_jac, s_var, s_avail, s_supported = _signed_s_row(
        mean, observed_s, s_expected, s_jacobian, s_m1r_variance, model, site_index,
    )
    r_error = np.full(shape, np.nan)
    r_jac = np.zeros_like(mean)
    r_var = np.full(shape, np.nan)
    r_details = dict(mean_out_of_support=np.zeros(shape, dtype=bool),
                     variance_out_of_support=np.zeros(shape, dtype=bool))
    if model.range_options is not None:
        ix = model.range_indices
        r_error, local_jac, r_var, r_details = range_measurement(
            mean[..., ix], observed_range, model.range_options,
        )
        r_jac[..., ix] = local_jac
    r_avail = np.isfinite(r_error)
    nis_r = _scalar_nis(cov, r_error, r_jac, r_var, r_avail)
    r_accept = r_avail & (nis_r <= GATE_RANGE)
    nis_s = _scalar_nis(cov, s_error, s_jac, s_var, s_avail)

    errors = np.stack((r_error, s_error), axis=-1)
    rows = np.stack((r_jac, s_jac), axis=-2)
    noise = np.zeros(shape + (2, 2))
    noise[..., 0, 0] = r_var
    noise[..., 1, 1] = s_var
    pair = r_accept & s_avail
    nis_pair = np.full(shape, np.nan)
    if pair.any():
        H, P = rows[pair], cov[pair]
        innovation = H @ P @ H.swapaxes(-1, -2) + noise[pair]
        np.linalg.cholesky(innovation)
        nu = errors[pair]
        nis_pair[pair] = np.sum(nu * np.linalg.solve(innovation, nu[..., None])[..., 0], axis=-1)

    weight = np.full(shape, np.nan)
    if model.tail_df is not None:
        # A missing/rejected ranging row has no bearing on the marginal s weight.
        noise[s_avail], weight[s_avail] = student_noise(
            cov[s_avail], rows[s_avail], noise[s_avail], errors[s_avail], model.tail_df,
        )
        if np.any(~np.isfinite(weight[s_avail]) | (weight[s_avail] <= 0)):
            raise ValueError("Student-t update produced an invalid weight")
        s_accept = s_avail
    else:
        s_accept = s_avail & np.where(r_accept, nis_pair <= GATE_JOINT, nis_s <= GATE_RANGE)

    posterior, postcov = mean.copy(), cov.copy()
    for mask, indices in ((r_accept & s_accept, (0, 1)),
                          (r_accept & ~s_accept, (0,)),
                          (~r_accept & s_accept, (1,))):
        if mask.any():
            ix = np.asarray(indices)
            ci = 0.5 if model.base == "J-CI" and 1 in indices else None
            posterior[mask], postcov[mask] = joseph_update(
                mean[mask], cov[mask], rows[mask][:, ix], noise[mask][:, ix[:, None], ix],
                errors[mask][:, ix], model.active_dim, ci_weight=ci,
            )
    s_gate_rejected = s_avail & ~s_accept
    s_effective_rejected = s_accept & (weight < 0.1)
    return posterior, postcov, dict(
        s_available=s_avail, s_unavailable=~s_avail, s_in_support=s_supported,
        s_accepted=s_accept, s_gate_rejected=s_gate_rejected,
        s_effective_rejected=s_effective_rejected, s_rejected=s_gate_rejected | s_effective_rejected,
        r_available=r_avail, r_accepted=r_accept, r_rejected=r_avail & ~r_accept,
        student_weight=weight, nis_range=nis_r, nis_s=nis_s, nis_joint=nis_pair,
        range_innovation=r_error, s_innovation=s_error,
        measurement_range_variance_m2=r_var, measurement_s_variance=noise[..., 1, 1],
        mean_out_of_support=r_details["mean_out_of_support"],
        range_variance_out_of_support=r_details["variance_out_of_support"],
    )
