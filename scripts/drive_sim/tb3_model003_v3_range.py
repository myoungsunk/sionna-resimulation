"""MODEL-003 v3 S3-R range models, independent of RF or truth input reads."""

from dataclasses import dataclass, field

import numpy as np

from tb3_model003_filter import GATE_RANGE, predict, range_model
from tb3_model003_v3_characterization import sigma_at
from tb3_model003_v3_filter import colored_transition, corrected_range, joseph_update


@dataclass(frozen=True)
class RangeModel:
    arm: str
    motion_dim: int
    anchor_xy: np.ndarray
    anchor_dz: float
    offset_m: float
    thermal_variance_m2: float
    white_variance_m2: float
    mean_knots_m: np.ndarray | None = field(default=None, kw_only=True)
    mean_bias_m: np.ndarray | None = field(default=None, kw_only=True)
    c2_range: dict | None = field(default=None, kw_only=True)
    length_m: float | None = field(default=None, kw_only=True)
    length_rad: float | None = field(default=None, kw_only=True)
    nugget: float = field(default=0.0, kw_only=True)
    c3_white: bool = field(default=False, kw_only=True)
    consider_variance_m2: float = field(default=0.0, kw_only=True)

    def __post_init__(self):
        if self.arm not in ("R4", "R-M", "R-MC") or self.motion_dim not in (4, 5):
            raise ValueError("Use a v3 range arm and the four- or five-state motion block")
        anchor = np.asarray(self.anchor_xy, dtype=float)
        sizes = [self.thermal_variance_m2, self.white_variance_m2, self.consider_variance_m2]
        if (anchor.shape != (2,) or not np.isfinite(anchor).all()
                or not np.isfinite([self.anchor_dz, self.offset_m, *sizes, self.nugget]).all()
                or min(sizes) < 0 or not 0 <= self.nugget < 1):
            raise ValueError("Invalid range anchor, variance or offset")
        if self.arm in ("R4", "R-M") and self.thermal_variance_m2 + self.white_variance_m2 <= 0:
            raise ValueError("The white range arms require positive measurement variance")
        if self.arm != "R4":
            knots = np.asarray(self.mean_knots_m, dtype=float)
            bias = np.asarray(self.mean_bias_m, dtype=float)
            if (knots.ndim != 1 or not knots.size or knots.shape != bias.shape
                    or not np.isfinite(knots).all() or not np.isfinite(bias).all()
                    or np.any(np.diff(knots) <= 0)):
                raise ValueError("R-M and R-MC require strictly ordered C6 knots and matching mean biases")
        if self.arm == "R-MC" and self.c2_range is None:
            raise ValueError("R-MC requires the conditional C2 range fit")
        if self.colored:
            lengths = np.asarray([self.length_m, self.length_rad], dtype=float)
            if not np.isfinite(lengths).all() or np.any(lengths <= 0):
                raise ValueError("Colored R-MC requires positive C3 lengths")
        if self.arm != "R-MC" and self.consider_variance_m2 != 0:
            raise ValueError("K_r belongs to R-MC only")

    @property
    def colored(self):
        return self.arm == "R-MC" and not self.c3_white

    @property
    def active_dim(self):
        return self.motion_dim + int(self.colored)

    @property
    def state_dim(self):
        return self.active_dim + int(self.arm == "R-MC")


def _conditional_variance(mean, model):
    distance, _ = range_model(mean, model.anchor_xy, model.anchor_dz)
    sigma, support = sigma_at(model.c2_range, distance)
    # Ranging continues outside C2 support with endpoint-clamped variance.
    return sigma**2, support


def initialize_range(mean, cov, model):
    """Set stationary c_r and static zero-mean K_r priors after the motion block."""
    mean = np.asarray(mean, dtype=float)
    if mean.shape[-1] != model.motion_dim or not np.isfinite(mean).all():
        raise ValueError("Range initialization takes a finite motion block only")
    prefix = mean.shape[:-1]
    cov = np.broadcast_to(cov, prefix + (model.motion_dim,) * 2)
    if not np.isfinite(cov).all():
        raise ValueError("Range initialization needs finite motion covariance")
    new_mean = np.zeros(prefix + (model.state_dim,))
    new_cov = np.zeros(prefix + (model.state_dim,) * 2)
    new_mean[..., :model.motion_dim] = mean
    new_cov[..., :model.motion_dim, :model.motion_dim] = cov
    if model.arm == "R-MC":
        new_cov[..., model.active_dim, model.active_dim] = model.consider_variance_m2
    if model.colored:
        variance, _ = _conditional_variance(new_mean, model)
        new_cov[..., model.motion_dim, model.motion_dim] = (1.0 - model.nugget) * variance
    return new_mean, new_cov


def predict_range(mean, cov, distance_m, gyro_rad, dt_s, model, *,
                  angular_travel_rad=None, restart_pose=None):
    """Propagate c_r from odometry/gyro and evaluate its target at predicted geometry."""
    y, prior = predict(
        mean, cov, distance_m, gyro_rad, dt_s, motion_dim=model.motion_dim,
        angular_travel_rad=angular_travel_rad, restart_pose=restart_pose,
    )
    if model.colored:
        col = model.motion_dim
        conditional, _ = _conditional_variance(y, model)
        phi, process = colored_transition(
            distance_m, gyro_rad, model.length_m, model.length_rad, (1.0 - model.nugget) * conditional,
        )
        # This diagonal attenuation commutes with the motion-only prediction
        # and known frame transform. The colored process and motion inputs are independent.
        y[..., col] *= phi
        prior[..., col, :] *= phi[..., None]
        prior[..., :, col] *= phi[..., None]
        prior[..., col, col] += process
    return y, prior


def range_measurement(mean, observed, model):
    """Build the range row, with C6 evaluated only at observed range minus o.

    For R-MC the caller fits the within-anchor conditional C2 variance before
    C6-K. The supplied count-weighted C3 nugget is the independent fraction
    of that variance. The remaining fraction is c_r stationary variance.
    The C6-K variance is carried only by the static Schmidt state. A C3-white
    decision puts the full conditional variance in R and retains K_r.
    """
    nominal, jac = range_model(mean, model.anchor_xy, model.anchor_dz, model.offset_m)
    raw = np.broadcast_to(np.asarray(observed, dtype=float), nominal.shape)
    value = raw
    mean_outside = np.zeros(nominal.shape, dtype=bool)
    variance_outside = np.zeros(nominal.shape, dtype=bool)
    if model.arm != "R4":
        value, mean_outside = corrected_range(raw, model.offset_m, model.mean_knots_m, model.mean_bias_m)

    fraction = np.full(nominal.shape, 1.0)
    if model.arm == "R-MC":
        conditional, support = _conditional_variance(mean, model)
        variance_outside = ~support
        jac[..., model.active_dim] = 1.0
        nominal = nominal + mean[..., model.active_dim]
        if model.colored:
            nominal += mean[..., model.motion_dim]
            jac[..., model.motion_dim] = 1.0
            fraction.fill(model.nugget)
        variance = model.thermal_variance_m2 + fraction * conditional
    else:
        variance = np.full(nominal.shape, model.thermal_variance_m2 + model.white_variance_m2)
    return value - nominal, jac, variance, dict(
        mean_out_of_support=mean_outside, variance_out_of_support=variance_outside,
        measurement_variance_m2=variance, independent_c2_fraction=fraction,
    )


def update_range(mean, cov, observed, model):
    """Apply the marginal 99% scalar χ² gate, then Joseph/Schmidt update."""
    residual, jac, variance, details = range_measurement(mean, observed, model)
    jac = jac[..., None, :]
    innovation = (jac @ cov @ jac.swapaxes(-1, -2))[..., 0, 0] + variance
    available = np.isfinite(residual)
    if not np.isfinite(innovation[available]).all() or np.any(innovation[available] <= 0):
        raise ValueError("Range gate requires finite positive innovation variance")
    nis = np.full(residual.shape, np.nan)
    nis[available] = residual[available]**2 / innovation[available]
    accepted = available & (nis <= GATE_RANGE)
    result_mean, result_cov = mean.copy(), cov.copy()
    if accepted.any():
        result_mean[accepted], result_cov[accepted] = joseph_update(
            mean[accepted], cov[accepted], jac[accepted], variance[accepted, None, None],
            residual[accepted, None], model.active_dim,
        )
    details.update(nis=nis, innovation=residual, available=available, accepted=accepted,
                   rejected=available & ~accepted)
    return result_mean, result_cov, details
