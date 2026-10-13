"""Shared, NEW-ONLY EKF3 D6-D9 diagnostics; never writes frozen inputs.

The original EKF3, observer and sensor generator are imported read-only.  Truth
must enter scoring functions only, not any RF feature, variance predictor or
filter update.  D6-D9 are exploratory; NOT an independent scene confirmation.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Iterable

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
REPO = PROJECT.parents[1]
ARCHIVE = REPO / 'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'
sys.path.insert(0, str(ARCHIVE))
sys.path.insert(0, str(PROJECT))

from ekf3 import EKF3, wrap, sinc_with_derivative  # noqa: E402
from p3_compat import B_OLD, frozen_detector, tap_metres, corrected_ranges  # noqa: E402
from run_d0_d4 import (RR, RS, read_p0, checked_path, original_lut, P3_MODEL,
                       P3_SHA256, hash_file)  # noqa: E402
from qclean_uwb.drivesim import observation as OBS  # noqa: E402
from qclean_uwb.drivesim.hs_lut import s_model  # noqa: E402
from qclean_uwb.drivesim.sensor_v2 import (SensorV2Config, generate,
                                           rng as sensor_rng)  # noqa: E402
from qclean_uwb.drivesim.sensors import motion_increments  # noqa: E402
from run_d5_regimes import timelines  # noqa: E402

SOURCE_REVISION = '701b8d2c29a4b3b879c4e27096168d6be463559b'
PUBLISHED_BASELINE = '43f755b75a5ac83fd6e7e67c3ef8f1f0da579d5d'
THRESHOLD_3D_95 = 7.814727903251179
THRESHOLD_1D_95 = 3.841458820694124
GATE_1D_99 = 6.6348966010212145
GATE_2D_99 = 9.21034037197618
EVAL_START = 30.0


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def check_inputs(*, full_p0: bool = True) -> dict:
    """Fail closed.  Caller explicitly invokes this before any diagnostic run."""
    p0 = read_p0()
    if hash_file(P3_MODEL) != P3_SHA256:
        raise RuntimeError('P3 frozen LORO coefficient SHA mismatch')
    if full_p0:
        from p0_verify_inputs import run as preflight
        if preflight() != 0:
            raise RuntimeError('P0 frozen asset preflight failed')
    for case in p0['cases']:
        if not case['full_path'] or not case['los_path']:
            raise RuntimeError('Missing RF source paths')
    return p0


def spectrum(p0: dict) -> np.ndarray:
    path = checked_path(p0,
        'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/'
        'SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy')
    return np.load(path, allow_pickle=False)


def case_motion(p0: dict, case: dict, seed: int, level: int,
                condition: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict, dict]:
    t, truth, pose_ids = timelines(p0)[case['route']]
    ds, dyaw = motion_increments(t, truth, convention='legacy-euler')
    cfg = SensorV2Config(level=level, condition=condition, common_scale=0.,
                         bias_rw_rad_s_sqrt_s=0., slip_mode='time')
    meas, oracle = generate(t, ds, dyaw, cfg, seed)
    return t, truth, pose_ids, meas, oracle


def initial_state(truth0: np.ndarray, seed: int) -> np.ndarray:
    e = sensor_rng(seed, 'initial').standard_normal(3) * np.array(
        [.1, .1, math.radians(5.)])
    x = np.asarray(truth0, float).copy() + e
    x[2] = wrap(x[2])
    return x


def rf_case(p0: dict, case: dict, channel: str, freq: np.ndarray,
            pose_ids: np.ndarray) -> dict:
    """Exactly the same detector contract as D5 with verified P0 inputs."""
    from run_d5_regimes import observed_case
    return observed_case(p0, case, channel, freq, pose_ids)


def eval_covariance(e: np.ndarray, P: np.ndarray) -> tuple[float, float, bool]:
    P = np.asarray(P, float)
    e = np.asarray(e, float)
    if P.shape != (3, 3) or np.linalg.eigvalsh((P + P.T) / 2).min() <= 0:
        raise RuntimeError('Invalid 3D marginal pose covariance')
    n3 = float(e @ np.linalg.solve(P, e))
    nh = float(e[2]**2 / P[2, 2])
    return n3, nh, n3 <= THRESHOLD_3D_95


def arc(x: np.ndarray, ds: float, yaw_inc: float) -> np.ndarray:
    """SE(2) arc, exactly matching EKF3 nominal state transition."""
    half = .5 * yaw_inc
    sc, _ = sinc_with_derivative(half)
    direction = x[2] + half
    y = np.asarray(x, float).copy()
    y[0] += ds * sc * math.cos(direction)
    y[1] += ds * sc * math.sin(direction)
    y[2] = wrap(y[2] + yaw_inc)
    return y


def ut_propagate(x: np.ndarray, P: np.ndarray, ds: float, gyro: float,
                 dt: float, *, sigma_bias_rw: float = 0.) -> tuple[np.ndarray, np.ndarray]:
    """Augmented UT of state+input, with optional 4th gyro-bias state.

    This is *only* a prediction variant; original EKF3 measurement update
    and Joseph covariance are unchanged.  Circular yaw moments use sin/cos.
    UT covariance includes input variance in the same nominal units as EKF3.
    No test/score/ground truth is consumed here.
    """
    x = np.asarray(x, float)
    P = np.asarray(P, float)
    n_state = x.size
    if n_state not in (3, 4) or P.shape != (n_state, n_state) or dt <= 0:
        raise ValueError('Expected a 3- or 4-state Gaussian and positive dt')
    qin = np.diag([2e-5 * abs(ds), math.radians(.015)**2 * dt])
    joint = np.zeros((n_state + 2, n_state + 2))
    joint[:n_state, :n_state] = P
    joint[n_state:, n_state:] = qin
    mu = np.r_[x, ds, gyro]
    n = len(mu)
    # alpha=1, kappa=1 gives non-negative sigma weights and stable moments.
    lam = 1.
    ws = np.full(2*n + 1, 1. / (2*(n+lam)))
    wm = ws.copy()
    wm[0] = lam / (n+lam)
    wc = wm.copy()
    wc[0] += 2.  # beta=2, alpha=1
    # Degenerate input covariance is legal at stationary samples.
    eig, V = np.linalg.eigh((joint + joint.T) * .5)
    if eig.min() < -1e-9 * max(1., float(np.linalg.norm(joint, ord=2))):
        raise RuntimeError('UT negative covariance eigenvalue')
    L = V @ np.diag(np.sqrt(np.maximum(eig, 0) * (n + lam)))
    sigmas = [mu] + [mu + L[:, i] for i in range(n)] + [mu - L[:, i] for i in range(n)]
    y = []
    for v in sigmas:
        u = v[:n_state]
        b = u[3] if n_state == 4 else 0.
        nominal = arc(u[:3], float(v[n_state]), float(v[n_state+1] - b*dt))
        y.append(np.r_[nominal, b] if n_state == 4 else nominal)
    y = np.asarray(y)
    avg = np.sum(wm[:, None] * y, axis=0)
    avg[2] = math.atan2(float(wm @ np.sin(y[:, 2])),
                        float(wm @ np.cos(y[:, 2])))
    residual = y - avg
    residual[:, 2] = np.arctan2(np.sin(residual[:, 2]), np.cos(residual[:, 2]))
    cov = np.einsum('k,ki,kj->ij', wc, residual, residual)
    if n_state == 4:
        cov[3, 3] += sigma_bias_rw**2 * dt
    cov = .5*(cov + cov.T)
    if np.linalg.eigvalsh(cov).min() <= 0:
        raise RuntimeError('UT predicted covariance is not positive definite')
    return avg, cov


def range_h(x: np.ndarray, anchor: Iterable[float], tag_z: float) -> tuple[float, np.ndarray]:
    a = np.asarray(list(anchor), float)
    delta = np.array([x[0]-a[0], x[1]-a[1], tag_z-a[2]])
    r = float(np.linalg.norm(delta))
    if r <= 0:
        raise ValueError('Invalid range geometry')
    return r, np.array([delta[0]/r, delta[1]/r, 0.])


class DiagnosticFilter:
    """F0/F1 3-state and F2/F5 4-state bias variants; no oracle inputs.

    3-state exact baseline always uses the original EKF3 class.  4-state
    prediction/update is a stand-alone extension (not a patch to frozen EKF).
    """
    def __init__(self, x0: np.ndarray, *, nonlinear: bool = False,
                 bias_state: bool = False, bias_std_dps: float = .1,
                 bias_rw_dps_sqrt_s: float = 0.):
        self.nonlinear = nonlinear
        self.bias_state = bias_state
        self.bias_rw = math.radians(bias_rw_dps_sqrt_s)
        if bias_std_dps <= 0:
            raise ValueError('bias prior std must be positive')
        self.f = EKF3(x0, np.diag([.01, .01, math.radians(5.)**2])) if not bias_state else None
        if bias_state:
            self.x = np.r_[x0, 0.]
            self.P = np.diag([.01, .01, math.radians(5.)**2, math.radians(bias_std_dps)**2])

    @property
    def pose(self) -> np.ndarray:
        return self.x[:3] if self.bias_state else self.f.x

    @property
    def Ppose(self) -> np.ndarray:
        return self.P[:3, :3] if self.bias_state else self.f.P

    def predict(self, ds: float, gyro: float, dt: float) -> None:
        if not self.bias_state:
            if self.nonlinear:
                self.f.x, self.f.P = ut_propagate(self.f.x, self.f.P, ds, gyro, dt)
            else:
                self.f.predict(ds, gyro, dt)
            return
        if self.nonlinear:
            self.x, self.P = ut_propagate(self.x, self.P, ds, gyro, dt,
                                          sigma_bias_rw=self.bias_rw)
            return
        x, P = self.x, self.P
        a = float(gyro-x[3]*dt)
        half = a/2
        sc, sc_der = sinc_with_derivative(half)
        v = np.array([math.cos(x[2]+half), math.sin(x[2]+half)])
        perp = np.array([-v[1], v[0]])
        F = np.eye(4)
        F[:2, 2] = ds*sc*perp
        F[:2, 3] = -.5*dt*ds*(sc_der*v+sc*perp)
        F[2, 3] = -dt
        G = np.zeros((4, 2))
        G[:2, 0] = sc*v
        G[:2, 1] = .5*ds*(sc_der*v+sc*perp)
        G[2, 1] = 1.
        Q = np.diag([2e-5*abs(ds), math.radians(.015)**2*dt])
        predicted = F @ P @ F.T + G @ Q @ G.T
        predicted[3, 3] += self.bias_rw**2 * dt
        self.x = np.r_[arc(x[:3], ds, a), x[3]]
        self.P = (predicted+predicted.T)*.5

    def update(self, arm: str, measured_s: float | None,
               corrected_range_m: float | None,
               s_model_fun, anchor, tag_z: float,
               rs: float = RS, rr: float = RR,
               rsr: float = 0.) -> tuple[str, float | None]:
        if arm == 'D0':
            return 'DR_only', None
        finite_s = measured_s is not None and math.isfinite(float(measured_s))
        finite_r = corrected_range_m is not None and math.isfinite(float(corrected_range_m))
        hs, jac_s = s_model_fun(self.pose.copy())
        hr, jac_r = range_h(self.pose, anchor, tag_z)
        if not self.bias_state:
            if arm == 'A':
                z = self.f.update_heading(measured_s if finite_s else None, rs,
                                          s_model=s_model_fun)
            elif arm == 'B':
                z = self.f.update_range((corrected_range_m+B_OLD) if finite_r else None,
                                        rr, anchor_xyz_m=tuple(anchor), tag_height_m=tag_z,
                                        range_offset_m=B_OLD)
            elif arm == 'C':
                z = self.f.update_joint(measured_s if finite_s else None,
                                        (corrected_range_m+B_OLD) if finite_r else None,
                                        rs, rr, rsr, s_model=s_model_fun,
                                        anchor_xyz_m=tuple(anchor), tag_height_m=tag_z,
                                        range_offset_m=B_OLD)
            else:
                raise ValueError('Unknown arm')
            return z.status, z.NIS
        values, predictions, jac = [], [], []
        if arm in ('A', 'C') and finite_s:
            values.append(float(measured_s)); predictions.append(float(hs))
            jac.append(np.r_[np.asarray(jac_s, float), 0.])
        if arm in ('B', 'C') and finite_r:
            values.append(float(corrected_range_m)); predictions.append(hr)
            jac.append(np.r_[jac_r, 0.])
        if not jac:
            return 'missing', None
        y = np.asarray(values) - np.asarray(predictions)
        H = np.asarray(jac)
        if len(y) == 2:
            R = np.array([[rs, rsr], [rsr, rr]])
        elif arm == 'B' or (arm == 'C' and not finite_s):
            R = np.array([[rr]])
        else:
            R = np.array([[rs]])
        if min(np.linalg.eigvalsh(R)) <= 0:
            raise RuntimeError('Invalid conditional RF covariance')
        S = H @ self.P @ H.T + R
        NIS = float(y @ np.linalg.solve(S, y))
        if NIS > (GATE_1D_99 if len(y) == 1 else GATE_2D_99):
            return 'rejected_NIS', NIS
        K = np.linalg.solve(S, H @ self.P).T
        self.x = self.x + K @ y
        self.x[2] = wrap(self.x[2])
        A = np.eye(4)-K @ H
        self.P = A @ self.P @ A.T + K @ R @ K.T
        self.P = .5*(self.P+self.P.T)
        if np.linalg.eigvalsh(self.P).min() <= 0:
            raise RuntimeError('Bias-EKF posterior covariance invalid')
        return 'applied', NIS


def make_out(path: Path) -> Path:
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise RuntimeError('Refusing to write an empty diagnostic CSV: '+path.name)
    fields = list(rows[0])
    if any(set(row) != set(fields) for row in rows):
        raise RuntimeError('Inconsistent diagnostic CSV row schema')
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def finish(out: Path, stage: str, config: dict, files: list[Path],
           *, caveats: list[str] | None = None) -> None:
    receipt = dict(stage=stage, status='EXECUTED_EXPLORATORY_ONLY',
                   source_revision=SOURCE_REVISION,
                   published_base=PUBLISHED_BASELINE,
                   scientific_PASS=False,
                   independent_rf_scene=False,
                   config=config,
                   caveats=caveats or [],
                   sha256={f.name: file_sha(f) for f in files})
    (out/(stage+'_MANIFEST.json')).write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False), encoding='utf-8')
