"""Known-z 2D localization utilities for Paper 2 replay experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd


RANGE_COLUMN_CANDIDATES = (
    "range_m",
    "range_meas_rt_fp_m",
    "range_meas_proxy_m",
    "true_geometry_range_m",
    "true_range_m",
)


@dataclass(frozen=True)
class SolveResult:
    status: str
    pose_est_xy: np.ndarray
    pose_est_xyz: np.ndarray
    pose_error_2d_m: float
    pose_error_3d_m: float
    range_residual_rmse_m: float
    mean_abs_range_residual_m: float
    n_valid_anchors: int
    iterations: int
    covariance_xy: np.ndarray
    residuals_m: np.ndarray


@dataclass(frozen=True)
class EkfUpdateResult:
    state: np.ndarray
    covariance: np.ndarray
    residual: float
    innovation_covariance: float
    nis: float
    kalman_gain: np.ndarray
    status: str


@dataclass(frozen=True)
class FactorGraphResult:
    status: str
    poses_xy: np.ndarray
    residual_rmse_m: float
    iterations: int
    final_step_norm: float


def parse_xyz(text: object) -> np.ndarray:
    """Parse an `x;y;z` value or array-like object into a float vector of size 3."""

    if isinstance(text, np.ndarray):
        values = text.astype(float).ravel().tolist()
    elif isinstance(text, (list, tuple)):
        values = [float(v) for v in list(text)]
    elif isinstance(text, str):
        values = []
        for part in text.replace(",", ";").split(";")[:3]:
            try:
                values.append(float(part.strip()))
            except ValueError:
                values.append(float("nan"))
    else:
        try:
            values = [float(text)]
        except (TypeError, ValueError):
            values = [float("nan")]
    while len(values) < 3:
        values.append(float("nan"))
    return np.asarray(values[:3], dtype=float)


def _as_observation_frame(observations: pd.DataFrame | Sequence[Mapping[str, object]]) -> pd.DataFrame:
    if isinstance(observations, pd.DataFrame):
        return observations.copy()
    return pd.DataFrame(list(observations))


def _numeric(values: object) -> pd.Series:
    return pd.to_numeric(values, errors="coerce")


def _find_range_column(df: pd.DataFrame) -> str | None:
    for col in RANGE_COLUMN_CANDIDATES:
        if col in df.columns:
            return col
    return None


def safe_rmse(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return float(np.sqrt(np.mean(values**2))) if len(values) else float("nan")


def range_predict(pose_xy_or_xyz: Sequence[float] | np.ndarray, anchor_xyz: Sequence[float] | np.ndarray, known_z: float | None = None) -> float:
    pose = np.asarray(pose_xy_or_xyz, dtype=float).ravel()
    anchor = np.asarray(anchor_xyz, dtype=float).ravel()
    if len(anchor) < 3:
        raise ValueError("anchor_xyz must have at least 3 values")
    if len(pose) == 2:
        if known_z is None:
            raise ValueError("known_z is required for a 2D pose")
        pose3 = np.asarray([pose[0], pose[1], known_z], dtype=float)
    elif len(pose) >= 3:
        pose3 = pose[:3].astype(float)
    else:
        raise ValueError("pose must have at least 2 values")
    return float(np.linalg.norm(pose3 - anchor[:3].astype(float)))


def compute_nis(residual: float, innovation_covariance: float) -> float:
    residual = float(residual)
    innovation_covariance = float(innovation_covariance)
    if not np.isfinite(residual) or not np.isfinite(innovation_covariance) or innovation_covariance <= 0:
        return float("nan")
    return float((residual * residual) / innovation_covariance)


def _initial_xy(anchors: np.ndarray, init: Sequence[float] | np.ndarray | None) -> np.ndarray:
    if init is not None:
        arr = np.asarray(init, dtype=float).ravel()
        if len(arr) >= 2 and np.isfinite(arr[:2]).all():
            return arr[:2].copy()
    return np.asarray([float(np.mean(anchors[:, 0])), float(np.mean(anchors[:, 1]))], dtype=float)


def _covariance_from_jacobian(jac: np.ndarray, weights: np.ndarray, residual: np.ndarray) -> np.ndarray:
    if len(residual) < 3:
        return np.full((2, 2), np.nan)
    w = np.maximum(np.asarray(weights, dtype=float), 1e-12)
    normal = jac.T @ (w[:, None] * jac)
    dof = max(len(residual) - 2, 1)
    sigma2 = float(np.sum(w * residual * residual) / dof)
    try:
        return np.linalg.pinv(normal) * sigma2
    except np.linalg.LinAlgError:
        return np.full((2, 2), np.nan)


def solve_known_z_wls(
    observations: pd.DataFrame | Sequence[Mapping[str, object]],
    weights: Sequence[float] | np.ndarray | None = None,
    init: Sequence[float] | np.ndarray | None = None,
    max_iter: int = 40,
    tol: float = 1e-7,
) -> SolveResult:
    """Solve known-z 2D WLS from range observations to three or more anchors."""

    df = _as_observation_frame(observations)
    if "anchor_pose_xyz" not in df.columns or "tag_pose_xyz" not in df.columns:
        return _failed_solve("FAIL_MISSING_GEOMETRY")
    range_col = _find_range_column(df)
    if range_col is None:
        return _failed_solve("FAIL_MISSING_RANGE")

    anchors = np.vstack([parse_xyz(v) for v in df["anchor_pose_xyz"]])
    tag_xyz = parse_xyz(df["tag_pose_xyz"].iloc[0])
    ranges = _numeric(df[range_col]).to_numpy(dtype=float)
    if weights is None:
        if "measurement_variance_nominal" in df.columns:
            variance = _numeric(df["measurement_variance_nominal"]).to_numpy(dtype=float)
            weights_arr = np.where(np.isfinite(variance) & (variance > 0), 1.0 / variance, 1.0)
        else:
            weights_arr = np.ones(len(df), dtype=float)
    else:
        weights_arr = np.asarray(weights, dtype=float).ravel()
        if len(weights_arr) != len(df):
            return _failed_solve("FAIL_WEIGHT_LENGTH")

    valid = np.isfinite(anchors).all(axis=1) & np.isfinite(ranges) & np.isfinite(weights_arr)
    anchors = anchors[valid]
    ranges = ranges[valid]
    weights_arr = np.maximum(weights_arr[valid].astype(float), 1e-12)
    if len(ranges) < 3 or not np.isfinite(tag_xyz).all():
        return _failed_solve("FAIL_INSUFFICIENT_VALID_RANGES")

    known_z = float(tag_xyz[2])
    xy = _initial_xy(anchors, init)
    status = "OK"
    iterations = 0
    jac = np.empty((0, 2), dtype=float)
    residual = np.empty(0, dtype=float)
    for iterations in range(1, max_iter + 1):
        dx = xy[0] - anchors[:, 0]
        dy = xy[1] - anchors[:, 1]
        dz = known_z - anchors[:, 2]
        pred = np.sqrt(dx**2 + dy**2 + dz**2)
        pred = np.maximum(pred, 1e-12)
        residual = ranges - pred
        jac = np.column_stack([dx / pred, dy / pred])
        sqrt_w = np.sqrt(weights_arr)
        a = jac * sqrt_w[:, None]
        b = residual * sqrt_w
        try:
            step, *_ = np.linalg.lstsq(a, b, rcond=None)
        except np.linalg.LinAlgError:
            status = "FAIL_SINGULAR"
            break
        if not np.isfinite(step).all():
            status = "FAIL_NONFINITE"
            break
        xy = xy + step
        if float(np.linalg.norm(step)) < tol:
            break

    dx = xy[0] - anchors[:, 0]
    dy = xy[1] - anchors[:, 1]
    dz = known_z - anchors[:, 2]
    pred = np.sqrt(dx**2 + dy**2 + dz**2)
    residual = ranges - pred
    pose_est_xyz = np.asarray([xy[0], xy[1], known_z], dtype=float)
    covariance = _covariance_from_jacobian(jac, weights_arr, residual)
    return SolveResult(
        status=status,
        pose_est_xy=xy.copy(),
        pose_est_xyz=pose_est_xyz,
        pose_error_2d_m=float(math.hypot(xy[0] - tag_xyz[0], xy[1] - tag_xyz[1])),
        pose_error_3d_m=float(np.linalg.norm(pose_est_xyz - tag_xyz)),
        range_residual_rmse_m=safe_rmse(residual),
        mean_abs_range_residual_m=float(np.mean(np.abs(residual))),
        n_valid_anchors=int(len(ranges)),
        iterations=int(iterations),
        covariance_xy=covariance,
        residuals_m=residual.copy(),
    )


def _failed_solve(status: str) -> SolveResult:
    return SolveResult(
        status=status,
        pose_est_xy=np.asarray([np.nan, np.nan], dtype=float),
        pose_est_xyz=np.asarray([np.nan, np.nan, np.nan], dtype=float),
        pose_error_2d_m=float("nan"),
        pose_error_3d_m=float("nan"),
        range_residual_rmse_m=float("nan"),
        mean_abs_range_residual_m=float("nan"),
        n_valid_anchors=0,
        iterations=0,
        covariance_xy=np.full((2, 2), np.nan),
        residuals_m=np.asarray([], dtype=float),
    )


def ekf_predict(
    state: Sequence[float] | np.ndarray,
    covariance: Sequence[Sequence[float]] | np.ndarray,
    odometry: Sequence[float] | np.ndarray,
    q_motion: float | Sequence[Sequence[float]] | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    state_arr = np.asarray(state, dtype=float).ravel()
    cov = np.asarray(covariance, dtype=float)
    odom = np.asarray(odometry, dtype=float).ravel()
    if len(state_arr) != 2 or cov.shape != (2, 2) or len(odom) != 2:
        raise ValueError("known-z EKF predict expects 2D state, 2x2 covariance, and 2D odometry")
    if np.isscalar(q_motion):
        q = np.eye(2) * float(q_motion)
    else:
        q = np.asarray(q_motion, dtype=float)
        if q.shape != (2, 2):
            raise ValueError("q_motion must be scalar or 2x2 matrix")
    return state_arr + odom, cov + q


def ekf_update_range(
    state: Sequence[float] | np.ndarray,
    covariance: Sequence[Sequence[float]] | np.ndarray,
    anchor_xyz: Sequence[float] | np.ndarray,
    range_m: float,
    r_var: float,
    known_z: float,
) -> EkfUpdateResult:
    state_arr = np.asarray(state, dtype=float).ravel()
    cov = np.asarray(covariance, dtype=float)
    anchor = np.asarray(anchor_xyz, dtype=float).ravel()
    if len(state_arr) != 2 or cov.shape != (2, 2) or len(anchor) < 3:
        return _failed_update(state_arr, cov, "FAIL_SHAPE")
    r_var = float(r_var)
    if not np.isfinite(r_var) or r_var <= 0:
        return _failed_update(state_arr, cov, "FAIL_R_VAR")

    dx = state_arr[0] - anchor[0]
    dy = state_arr[1] - anchor[1]
    dz = float(known_z) - anchor[2]
    pred = float(np.sqrt(dx * dx + dy * dy + dz * dz))
    if not np.isfinite(pred) or pred <= 1e-12:
        return _failed_update(state_arr, cov, "FAIL_PREDICT")
    h = np.asarray([dx / pred, dy / pred], dtype=float)
    residual = float(range_m) - pred
    s = float(h @ cov @ h.T + r_var)
    if not np.isfinite(s) or s <= 0:
        return _failed_update(state_arr, cov, "FAIL_INNOVATION")
    k = (cov @ h.T) / s
    updated_state = state_arr + k * residual
    i = np.eye(2)
    updated_cov = (i - np.outer(k, h)) @ cov @ (i - np.outer(k, h)).T + np.outer(k, k) * r_var
    return EkfUpdateResult(
        state=updated_state,
        covariance=updated_cov,
        residual=residual,
        innovation_covariance=s,
        nis=compute_nis(residual, s),
        kalman_gain=k,
        status="OK",
    )


def _failed_update(state: np.ndarray, covariance: np.ndarray, status: str) -> EkfUpdateResult:
    return EkfUpdateResult(
        state=np.asarray(state, dtype=float).copy(),
        covariance=np.asarray(covariance, dtype=float).copy(),
        residual=float("nan"),
        innovation_covariance=float("nan"),
        nis=float("nan"),
        kalman_gain=np.full(2, np.nan),
        status=status,
    )


def pose_error_metrics(estimates: Sequence[Sequence[float]] | np.ndarray, truth: Sequence[Sequence[float]] | np.ndarray) -> dict[str, float]:
    est = np.asarray(estimates, dtype=float)
    gt = np.asarray(truth, dtype=float)
    if est.ndim == 1:
        est = est.reshape(1, -1)
    if gt.ndim == 1:
        gt = gt.reshape(1, -1)
    n = min(len(est), len(gt))
    if n == 0:
        return {key: float("nan") for key in ["rmse_m", "p50_m", "p90_m", "p95_m", "final_error_m"]}
    diff = est[:n, :2] - gt[:n, :2]
    err = np.sqrt(np.sum(diff * diff, axis=1))
    err = err[np.isfinite(err)]
    if len(err) == 0:
        return {key: float("nan") for key in ["rmse_m", "p50_m", "p90_m", "p95_m", "final_error_m"]}
    return {
        "rmse_m": float(np.sqrt(np.mean(err * err))),
        "p50_m": float(np.quantile(err, 0.50)),
        "p90_m": float(np.quantile(err, 0.90)),
        "p95_m": float(np.quantile(err, 0.95)),
        "final_error_m": float(err[-1]),
    }


def batch_factor_graph_solve(
    initial_poses_xy: Sequence[Sequence[float]] | np.ndarray,
    odometry: Sequence[Sequence[float]] | np.ndarray,
    range_factors: Sequence[Mapping[str, object]],
    max_iter: int = 20,
    tol: float = 1e-7,
) -> FactorGraphResult:
    """Lightweight known-z 2D batch Gauss-Newton solver for synthetic checks."""

    poses = np.asarray(initial_poses_xy, dtype=float).copy()
    if poses.ndim != 2 or poses.shape[1] != 2:
        return FactorGraphResult("FAIL_POSE_SHAPE", poses, float("nan"), 0, float("nan"))
    odom = np.asarray(odometry, dtype=float)
    if len(poses) > 1 and (odom.ndim != 2 or odom.shape[1] != 2 or len(odom) != len(poses) - 1):
        return FactorGraphResult("FAIL_ODOMETRY_SHAPE", poses, float("nan"), 0, float("nan"))

    status = "OK"
    final_step_norm = float("nan")
    residual_vec = np.asarray([], dtype=float)
    iterations = 0
    for iterations in range(1, max_iter + 1):
        residuals: list[float] = []
        jac_rows: list[np.ndarray] = []
        for idx, delta in enumerate(odom):
            residual = poses[idx + 1] - poses[idx] - delta
            for dim in range(2):
                row = np.zeros(poses.size, dtype=float)
                row[idx * 2 + dim] = -1.0
                row[(idx + 1) * 2 + dim] = 1.0
                jac_rows.append(row)
                residuals.append(float(residual[dim]))
        for factor in range_factors:
            pose_idx = int(factor["pose_index"])
            anchor = parse_xyz(factor["anchor_pose_xyz"])
            known_z = float(factor["known_z"])
            meas = float(factor["range_m"])
            sigma = float(factor.get("sigma_m", 1.0))
            if pose_idx < 0 or pose_idx >= len(poses) or sigma <= 0:
                continue
            dx = poses[pose_idx, 0] - anchor[0]
            dy = poses[pose_idx, 1] - anchor[1]
            dz = known_z - anchor[2]
            pred = max(float(np.sqrt(dx * dx + dy * dy + dz * dz)), 1e-12)
            row = np.zeros(poses.size, dtype=float)
            row[pose_idx * 2] = (dx / pred) / sigma
            row[pose_idx * 2 + 1] = (dy / pred) / sigma
            jac_rows.append(row)
            residuals.append((pred - meas) / sigma)
        if not jac_rows:
            return FactorGraphResult("FAIL_NO_FACTORS", poses, float("nan"), iterations, float("nan"))
        jac = np.vstack(jac_rows)
        residual_vec = np.asarray(residuals, dtype=float)
        try:
            step, *_ = np.linalg.lstsq(jac, -residual_vec, rcond=None)
        except np.linalg.LinAlgError:
            status = "FAIL_SINGULAR"
            break
        if not np.isfinite(step).all():
            status = "FAIL_NONFINITE"
            break
        poses = poses + step.reshape(poses.shape)
        final_step_norm = float(np.linalg.norm(step))
        if final_step_norm < tol:
            break

    return FactorGraphResult(
        status=status,
        poses_xy=poses,
        residual_rmse_m=safe_rmse(residual_vec),
        iterations=int(iterations),
        final_step_norm=final_step_norm,
    )
