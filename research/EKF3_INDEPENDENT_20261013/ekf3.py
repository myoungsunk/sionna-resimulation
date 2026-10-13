"""Independent 2-D three-state EKF for paired DR / RF-s / range experiments.

State: x = [body_x_m, body_y_m, body_yaw_rad].  No DriveFilter inheritance,
6-state slice, online gyro calibration or truth information.  Units: m, rad.

An RF polarization s measurement is not an independent absolute-angle
measurement: its model may depend on x, y AND yaw.  An actual independent
absolute heading is supported only when explicitly certified by the caller.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

import numpy as np

ScalarModel = Callable[[np.ndarray], tuple[float, np.ndarray]]
CHI2_1_99 = 6.6348966010212145
CHI2_2_99 = 9.21034037197618


def wrap(angle: float) -> float:
    """Signed angular difference, in [-pi, pi)."""
    return float((angle + math.pi) % (2.0 * math.pi) - math.pi)


def sinc_with_derivative(v: float) -> tuple[float, float]:
    """Return sin(v)/v and its derivative, including well-conditioned zero."""
    if abs(v) < 1e-4:
        v2 = v * v
        return 1 - v2 / 6 + v2 * v2 / 120 - v2**3 / 5040, -v / 3 + v**3 / 30 - v**5 / 840
    return math.sin(v) / v, (v * math.cos(v) - math.sin(v)) / (v * v)


def _covariance(value: np.ndarray, n: int, *, name: str, positive: bool = False) -> np.ndarray:
    p = np.asarray(value, dtype=float)
    if p.shape != (n, n) or not np.isfinite(p).all():
        raise ValueError(f"{name}: expected a finite {n}x{n} matrix")
    if not np.allclose(p, p.T, atol=1e-12, rtol=1e-12):
        raise ValueError(f"{name}: nonsymmetric matrix")
    p = (p + p.T) / 2.0
    eigen = np.linalg.eigvalsh(p)
    # Only a floating point roundoff allowance: do not project/clamp covariance.
    tolerance = 1e-12 * max(1.0, float(np.linalg.norm(p, ord=2)))
    if eigen[0] < -tolerance or (positive and eigen[0] <= 0):
        raise ValueError(f"{name}: covariance not {'positive definite' if positive else 'PSD'}")
    return p


def _positive_variance(v: float, name: str) -> float:
    value = float(v)
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name}: expected finite positive variance")
    return value


def _is_missing(v: float | None) -> bool:
    return v is None or not np.isfinite(float(v))


@dataclass(frozen=True)
class FilterStep:
    name: str
    status: str
    prior_x: np.ndarray
    prior_P: np.ndarray
    post_x: np.ndarray
    post_P: np.ndarray
    innovation: np.ndarray | None = None
    predicted_measurement: np.ndarray | None = None
    H: np.ndarray | None = None
    R: np.ndarray | None = None
    S: np.ndarray | None = None
    K: np.ndarray | None = None
    NIS: float | None = None
    F: np.ndarray | None = None
    G: np.ndarray | None = None
    Q_input: np.ndarray | None = None
    Q_model: np.ndarray | None = None


class EKF3:
    """Three independent states; sensor prediction and update own full P3."""

    def __init__(self, x0: np.ndarray, P0: np.ndarray):
        x = np.asarray(x0, dtype=float)
        if x.shape != (3,) or not np.isfinite(x).all():
            raise ValueError("x0: expected finite (3,) state")
        self.x = x.copy()
        self.x[2] = wrap(self.x[2])
        self.P = _covariance(P0, 3, name="P0").copy()

    def clone(self) -> "EKF3":
        """Independent same-prior arm for one-step paired experiments."""
        return EKF3(self.x.copy(), self.P.copy())

    def _record(self, name: str, status: str, xp: np.ndarray, pp: np.ndarray, **kwargs) -> FilterStep:
        # Snapshots do not alias the evolving EKF arrays.
        return FilterStep(name, status, xp.copy(), pp.copy(), self.x.copy(), self.P.copy(), **kwargs)

    def predict(
        self,
        ds_odom_m: float,
        dtheta_gyro_rad: float,
        dt_s: float,
        *,
        k_distance_m: float = 2e-5,
        gyro_arw_rad_per_sqrt_s: float = math.radians(0.015),
        Q_input: np.ndarray | None = None,
        Q_model: np.ndarray | None = None,
    ) -> FilterStep:
        """SE(2) arc prediction with independently computed F3, G(3x2), Joseph-ready P3.

        Nominal input Q has Var(ds)=k_distance*abs(measured_ds),
        Var(dtheta)=(gyro ARW)^2 * dt.  Optional full 2x2 input covariance
        supersedes these values (e.g. independently validated correlation).
        """
        d, a, dt = map(float, (ds_odom_m, dtheta_gyro_rad, dt_s))
        if not all(map(math.isfinite, (d, a, dt))) or dt <= 0:
            raise ValueError("prediction requires finite increments and positive dt")
        if k_distance_m < 0 or gyro_arw_rad_per_sqrt_s < 0:
            raise ValueError("negative input-noise scale")
        qu = (
            _covariance(Q_input, 2, name="Q_input") if Q_input is not None else
            np.diag([k_distance_m * abs(d), gyro_arw_rad_per_sqrt_s**2 * dt])
        )
        qm = _covariance(Q_model, 3, name="Q_model") if Q_model is not None else np.zeros((3, 3))
        prior_x, prior_P = self.x.copy(), self.P.copy()
        half = a / 2.0
        sc, sc_der = sinc_with_derivative(half)
        phi = self.x[2] + half
        direction = np.array([math.cos(phi), math.sin(phi)])
        perp = np.array([-direction[1], direction[0]])
        f = np.eye(3)
        f[:2, 2] = d * sc * perp
        g = np.zeros((3, 2))
        g[:2, 0] = sc * direction
        g[:2, 1] = (d / 2.0) * (sc_der * direction + sc * perp)
        g[2, 1] = 1.0
        proposed_x = prior_x.copy()
        proposed_x[:2] += d * sc * direction
        proposed_x[2] = wrap(prior_x[2] + a)
        proposed_P = _covariance(f @ prior_P @ f.T + g @ qu @ g.T + qm, 3, name="predicted_P")
        self.x, self.P = proposed_x, proposed_P
        return self._record("predict", "applied", prior_x, prior_P, F=f, G=g, Q_input=qu, Q_model=qm)

    def _update(self, name: str, z: np.ndarray, h: np.ndarray, H: np.ndarray,
                R: np.ndarray, *, angular_indices: tuple[int, ...] = (),
                gate: bool = True) -> FilterStep:
        z = np.asarray(z, dtype=float).reshape(-1)
        h = np.asarray(h, dtype=float).reshape(-1)
        H = np.asarray(H, dtype=float)
        if z.size < 1 or h.shape != z.shape or H.shape != (len(z), 3):
            raise ValueError("inconsistent observation/model/Jacobian dimensions")
        if not (np.isfinite(z).all() and np.isfinite(h).all() and np.isfinite(H).all()):
            raise ValueError("nonfinite observation model")
        r = _covariance(R, len(z), name="R")
        prior_x, prior_P = self.x.copy(), self.P.copy()
        innovation = z - h
        for idx in angular_indices:
            innovation[idx] = wrap(innovation[idx])
        S = _covariance(H @ prior_P @ H.T + r, len(z), name="S", positive=True)
        # solve is more stable than explicitly inverting S
        sol = np.linalg.solve(S, innovation)
        NIS = float(innovation @ sol)
        K = np.linalg.solve(S, H @ prior_P).T
        threshold = CHI2_1_99 if len(z) == 1 else (CHI2_2_99 if len(z) == 2 else None)
        if threshold is None:
            raise ValueError("only one/two observation dimensions supported")
        status = "rejected_NIS" if gate and NIS > threshold else "applied"
        if status == "applied":
            candidate_x = prior_x + K @ innovation
            candidate_x[2] = wrap(candidate_x[2])
            A = np.eye(3) - K @ H
            candidate_P = _covariance(A @ prior_P @ A.T + K @ r @ K.T, 3, name="posterior_P")
            self.x, self.P = candidate_x, candidate_P
        return self._record(name, status, prior_x, prior_P,
                            innovation=innovation.copy(), predicted_measurement=h.copy(),
                            H=H.copy(), R=r.copy(), S=S.copy(), K=K.copy(), NIS=NIS)

    def update_heading(self, measured: float | None, variance: float,
                       *, s_model: ScalarModel | None = None,
                       kind: str = "direct_s", validated_absolute: bool = False,
                       gate: bool = True) -> FilterStep:
        """Update heading evidence. Default: raw RF s + full spatial s-model H.

        Use kind='absolute_heading' ONLY for independently calibrated heading
        measurements (NOT inverted s with a DR-selected LUT root).
        """
        xp, pp = self.x.copy(), self.P.copy()
        if _is_missing(measured):
            return self._record("heading", "skipped_missing", xp, pp)
        v = _positive_variance(variance, "heading variance")
        if kind == "direct_s":
            if s_model is None:
                raise ValueError("direct_s requires calibrated model(x)->(s, jacobian)")
            h, jac = s_model(self.x.copy())
            angular = ()
        elif kind == "absolute_heading":
            if not validated_absolute:
                raise ValueError("inverse-LUT/DR-dependent heading cannot be treated as independent")
            h, jac = self.x[2], np.array([0.0, 0.0, 1.0])
            angular = (0,)
        else:
            raise ValueError("invalid heading measurement kind")
        return self._update("heading", [float(measured)], [float(h)],
                            np.asarray(jac, dtype=float).reshape(1, 3), [[v]],
                            angular_indices=angular, gate=gate)

    def _range_prediction(self, anchor_xyz_m: tuple[float, float, float],
                          tag_height_m: float, range_offset_m: float) -> tuple[float, np.ndarray]:
        anchor = np.asarray(anchor_xyz_m, dtype=float)
        if anchor.shape != (3,) or not np.isfinite(anchor).all():
            raise ValueError("anchor must be finite xyz in metres")
        if not math.isfinite(tag_height_m) or not math.isfinite(range_offset_m):
            raise ValueError("invalid tag height or detector offset")
        delta = np.array([self.x[0] - anchor[0], self.x[1] - anchor[1], tag_height_m - anchor[2]])
        distance = float(np.linalg.norm(delta))
        if distance <= 1e-12:
            raise ValueError("range undefined: tag at anchor")
        return distance + range_offset_m, np.array([delta[0] / distance, delta[1] / distance, 0.0])

    def update_range(self, measured: float | None, variance_m2: float, *,
                     anchor_xyz_m: tuple[float, float, float], tag_height_m: float,
                     range_offset_m: float = -0.5315983906250129,
                     gate: bool = True) -> FilterStep:
        xp, pp = self.x.copy(), self.P.copy()
        if _is_missing(measured):
            return self._record("range", "skipped_missing", xp, pp)
        h, jac = self._range_prediction(anchor_xyz_m, tag_height_m, range_offset_m)
        var = _positive_variance(variance_m2, "range variance")
        return self._update("range", [float(measured)], [h], jac.reshape(1, 3),
                            [[var]], gate=gate)

    def update_joint(self, measured_s: float | None, measured_range: float | None,
                     variance_s: float, variance_range_m2: float, covariance_sr: float,
                     *, s_model: ScalarModel,
                     anchor_xyz_m: tuple[float, float, float], tag_height_m: float,
                     range_offset_m: float = -0.5315983906250129,
                     gate: bool = True) -> FilterStep:
        """Single joint 2D update with SAME-time R_sr, without double counting.

        If either sensor packet is missing, perform precisely one valid scalar
        update; if both missing do nothing.  A rejected joint innovation does
        not silently retry one channel: that would change the frozen policy.
        """
        ms, mr = not _is_missing(measured_s), not _is_missing(measured_range)
        if not ms and not mr:
            return self._record("joint", "skipped_missing", self.x, self.P)
        if not ms:
            return self.update_range(measured_range, variance_range_m2,
                                     anchor_xyz_m=anchor_xyz_m, tag_height_m=tag_height_m,
                                     range_offset_m=range_offset_m, gate=gate)
        if not mr:
            return self.update_heading(measured_s, variance_s, s_model=s_model,
                                       kind="direct_s", gate=gate)
        vs = _positive_variance(variance_s, "s variance")
        vr = _positive_variance(variance_range_m2, "range variance")
        cov = float(covariance_sr)
        if not math.isfinite(cov):
            raise ValueError("nonfinite s/r measurement covariance")
        R = _covariance([[vs, cov], [cov, vr]], 2, name="joint_R")
        h_s, jac_s = s_model(self.x.copy())
        h_r, jac_r = self._range_prediction(anchor_xyz_m, tag_height_m, range_offset_m)
        H = np.vstack([np.asarray(jac_s, dtype=float).reshape(3), jac_r])
        return self._update("joint", [float(measured_s), float(measured_range)],
                            [float(h_s), h_r], H, R, gate=gate)


def archived_direct_s_model(lut: object, *, anchor_xyz_m: tuple[float, float, float],
                            tag_height_m: float, mount_deg: float = 0.0) -> ScalarModel:
    """Read-only adapter to the archived hs_lut.s_model; no DriveFilter import.

    The upstream LUT/observer source MUST be frozen and audited separately.
    """
    from qclean_uwb.drivesim.hs_lut import s_model

    def model(x: np.ndarray) -> tuple[float, np.ndarray]:
        val, jac = s_model(lut, anchor_xyz_m, tag_height_m,
                           float(x[0]), float(x[1]), float(x[2]),
                           mount_deg, with_jac=True)
        return float(val), np.asarray(jac, dtype=float).reshape(3)

    return model
