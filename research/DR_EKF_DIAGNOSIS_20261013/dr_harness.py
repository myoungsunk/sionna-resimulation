"""Harness for the DR (RF-off) EKF consistency diagnosis (plan: DIAGNOSIS_PLAN_KO.md).

* Imports the FROZEN sensor-v2 generator and 6-state EKF from RUN_01a124ff unchanged; the baseline arm calls
  `SensorV2Filter.step` itself. Predicted (pre-update) moments are reconstructed with the frozen `transition`
  and the F/G/Q the frozen step returns (same expression, so bitwise identical to the filter's internal P^-).
* Diagnostic variants (C removed, oracle Q) re-implement only the step body with the frozen model functions and
  are labelled DIAGNOSTIC; they are never candidates for a final model.
* Comparators for D5: an augmented-noise cubature Kalman filter (same model, shared-input correlation handled by
  sampling the input noise jointly) and a particle filter with the locally optimal input-noise proposal (adapted
  from research/V02_E1E6_20261012/run_e1e6.py:PF). With odometry updates off the particle filter has uniform
  weights and no resampling, i.e. it is plain nonlinear Monte Carlo moment propagation.
* Truth is used only for evaluation and for the explicitly named oracle arms.
"""
from __future__ import annotations

import hashlib
import json
import math
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict, replace
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FROZEN_SRC = ROOT / 'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src'
MOTION_DIR = ROOT / 'research/LOS_RANGE_RECAL_20261012/inputs_R2'
R22_DIR = ROOT / 'research/LOS_RANGE_RECAL_20261012'
if str(FROZEN_SRC) not in sys.path:
    sys.path.insert(0, str(FROZEN_SRC))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from qclean_uwb.drivesim import sensor_v2 as V, filter_v2 as F  # noqa: E402  (frozen)
from qclean_uwb.drivesim.filters import FilterConfig, CHI2_1_999  # noqa: E402
from qclean_uwb.drivesim.sensors import DRIFT_LEVELS  # noqa: E402
import dr_consistency as DC  # noqa: E402

ROUTES = ('R2', 'R4', 'R5')
LEVELS = (0, 1, 2)
CELLS = tuple((r, lv) for r in ROUTES for lv in LEVELS)
DIAG_NAMESPACE = 20261013
P0_POSE = (0.03, 0.03, math.radians(2.0))
P0_CAL_DEFAULT = (math.radians(0.12), 0.0104, 0.0064)
ORACLE_CAL_STD = 1e-9          # relative to P0_CAL_DEFAULT; "known" calibration without a singular P
SNAPSHOT_TIMES = (0.0, 30.0, 60.0, 100.0, 150.0, 'end')
FROZEN_FILES = ('qclean_uwb/drivesim/filter_v2.py', 'qclean_uwb/drivesim/sensor_v2.py',
                'qclean_uwb/drivesim/filters.py', 'qclean_uwb/drivesim/sensors.py',
                'qclean_uwb/drivesim/hs_lut.py')


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for block in iter(lambda: fh.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def cell_name(route, level):
    return f'{route}_d{level}'


# ----------------------------------------------------------------------------- inputs
def _expected_motion_sha():
    out = {}
    for line in (MOTION_DIR / 'SHA256SUMS_CSV.txt').read_text().split('\n'):
        if line.strip():
            digest, name = line.split()
            out[name] = digest
    return out


def load_motion(route):
    import pandas as pd
    path = MOTION_DIR / f'MOTION_{route}.csv'
    digest = sha256(path)
    if digest != _expected_motion_sha()[path.name]:
        raise RuntimeError(f'motion input hash mismatch: {path}')
    d = pd.read_csv(path, float_precision='round_trip')
    t = d.t.to_numpy()
    m = dict(t=t, pose=d[['x', 'y', 'theta']].to_numpy(), ds=d.ds.to_numpy(), dtheta=d.dtheta.to_numpy(),
             sha256=digest, path=str(path.relative_to(ROOT)))
    m['dt'] = np.r_[0.0, np.diff(t)]
    m['phase'] = DC.motion_phase(m['ds'], m['dtheta'], m['dt'])
    m['since_spin'] = DC.time_since_last_spin(m['phase'], t)
    m['cum_dist'] = np.cumsum(np.abs(m['ds']))
    m['cum_rot'] = np.cumsum(np.abs(m['dtheta']))
    return m


MOT = {r: load_motion(r) for r in ROUTES}


def snapshot_indices(t):
    """Indices of SNAPSHOT_TIMES (a time beyond the route maps to its last sample, so R4 repeats 'end')."""
    out = []
    for s in SNAPSHOT_TIMES:
        out.append(len(t) - 1 if s == 'end' else min(int(np.searchsorted(t, s)), len(t) - 1))
    return np.array(out)


# ----------------------------------------------------------------------------- arms
@dataclass(frozen=True)
class Arm:
    """One intervention arm. world: generator variant; prior: filter calibration prior; estimator: ekf|ckf|pf."""
    name: str
    world: str = 'b0'                 # b0 | b0_clean | gauss_level | gauss_default | wheel_noise_only
    prior: str = 'default'            # default | level | oracle
    known_eb: bool = False            # oracle wheelbase error given to the filter (R2-2 F1)
    odom: bool = True
    update: str = 'frozen'            # frozen | noC (DIAGNOSTIC)
    q_source: str = 'measured'        # measured (frozen) | true (DIAGNOSTIC oracle)
    estimator: str = 'ekf'            # ekf | ckf | pf
    n_particles: int = 20000
    role: str = ''

    def describe(self):
        return asdict(self)


ARMS = {a.name: a for a in (
    Arm('B0', role='frozen baseline = R2-2 B0 = A2-1'),
    # A2 calibration-prior arms
    Arm('A2_2_PRIOR_MATCHED', prior='level', role='+-level world, Gaussian prior with matched mean/variance (= R2-2 F2)'),
    Arm('A2_2C_MATCHED_CLEAN', world='b0_clean', prior='level',
        role='A2-2 with the two terms the filter cannot represent removed from the world (wheelbase=0, slip off)'),
    Arm('A2_3_GAUSS_LEVEL', world='gauss_level', prior='level',
        role='model-matched world: calibration drawn from the filter prior (level sigma), wheelbase 0, slip off'),
    Arm('A2_3D_GAUSS_DEFAULT', world='gauss_default', prior='default',
        role='model-matched world with the default (code) calibration prior'),
    Arm('ORACLE_CAL', prior='oracle', known_eb=True, role='true calibration and wheelbase known (control, not a method)'),
    # A3 odometry / correlation arms
    Arm('ODOM_OFF', odom=False, role='B0 world, odometry heading update disabled'),
    Arm('ORACLE_CAL_ODOM_OFF', prior='oracle', known_eb=True, odom=False, role='oracle calibration, no odometry update'),
    Arm('NO_C', update='noC', role='DIAGNOSTIC: shared-input cross-covariance C removed from the update'),
    Arm('A2_3_ODOM_OFF', world='gauss_level', prior='level', odom=False,
        role='model-matched, prediction only (pure propagation linearisation test)'),
    Arm('A2_3D_ODOM_OFF', world='gauss_default', prior='default', odom=False,
        role='model-matched default prior, prediction only'),
    # A4 noise model arm
    Arm('Q_TRUE', q_source='true', role='DIAGNOSTIC oracle: Q from the true increments'),
    # wheel-noise-only puzzle (R2-2 G_wheel_noise): conservative prior yet over-confident
    Arm('WN_ONLY', world='wheel_noise_only', role='R2-2 G_wheel_noise reproduction'),
    Arm('WN_ONLY_ORACLE', world='wheel_noise_only', prior='oracle', role='wheel noise only, calibration known'),
    # D5 estimator comparisons (same worlds/priors as the EKF arms they pair with)
    Arm('CKF_B0', estimator='ckf', role='cubature KF, B0 world/prior'),
    Arm('CKF_A2_3', world='gauss_level', prior='level', estimator='ckf', role='cubature KF, model-matched'),
    Arm('CKF_A2_3D', world='gauss_default', prior='default', estimator='ckf', role='cubature KF, model-matched default prior'),
    Arm('CKF_WN_ONLY', world='wheel_noise_only', estimator='ckf', role='cubature KF, wheel noise only'),
    Arm('PF_B0', estimator='pf', role='particle filter (locally optimal proposal), B0 world/prior'),
    Arm('PF_A2_3', world='gauss_level', prior='level', estimator='pf', role='particle filter, model-matched'),
    Arm('PF_A2_3D', world='gauss_default', prior='default', estimator='pf', role='particle filter, model-matched default prior'),
    Arm('PF_WN_ONLY', world='wheel_noise_only', estimator='pf', role='particle filter, wheel noise only'),
    Arm('MC_A2_3_ODOM_OFF', world='gauss_level', prior='level', odom=False, estimator='pf',
        role='nonlinear MC propagation reference for A2_3_ODOM_OFF (uniform weights, no resampling)'),
    Arm('MC_A2_3D_ODOM_OFF', world='gauss_default', prior='default', odom=False, estimator='pf',
        role='nonlinear MC propagation reference for A2_3D_ODOM_OFF'),
    Arm('MC_ODOM_OFF', odom=False, estimator='pf', role='nonlinear MC propagation reference for ODOM_OFF'),
)}


def level_cal_std(level):
    L = DRIFT_LEVELS[level]
    return (math.radians(L.gyro_bias_dps), L.gyro_sf, L.wheel_ratio)


def make_world(arm, route, level, seed):
    """Frozen generator; the variant only overrides generated parameters / enabled terms."""
    m = MOT[route]
    cond, slip_mode, params = 'all', 'time', None
    if arm.world == 'b0':
        pass
    elif arm.world == 'b0_clean':
        slip_mode, params = 'off', dict(wheelbase=0.0)
    elif arm.world in ('gauss_level', 'gauss_default'):
        std = level_cal_std(level) if arm.world == 'gauss_level' else P0_CAL_DEFAULT
        z = np.random.default_rng([DIAG_NAMESPACE, int(seed), 11]).standard_normal(3)
        slip_mode = 'off'
        params = dict(gyro_bias=float(z[0] * std[0]), gyro_sf=float(z[1] * std[1]),
                      wheel_asymmetry=float(z[2] * std[2]), wheelbase=0.0)
    elif arm.world == 'wheel_noise_only':
        cond = 'wheel_noise'
    else:
        raise ValueError(arm.world)
    cfg = V.SensorV2Config(level=level, condition=cond, slip_mode=slip_mode)
    inputs, ev = V.generate(m['t'], m['ds'], m['dtheta'], cfg, seed, params)
    p = dict(zip([str(s) for s in ev['parameter_names']], [float(v) for v in ev['true_parameters']]))
    truth6 = np.column_stack([m['pose'], ev['true_bias_rad_s'], np.full(len(m['t']), p['gyro_sf']),
                              np.full(len(m['t']), p['wheel_asymmetry'])])
    return inputs, ev, p, truth6


def prior_std(arm, level):
    cal = {'default': P0_CAL_DEFAULT, 'level': level_cal_std(level),
           'oracle': tuple(ORACLE_CAL_STD * s for s in P0_CAL_DEFAULT)}[arm.prior]
    return np.array(P0_POSE + tuple(cal), float)


def make_cfg(arm, level, params):
    p0 = prior_std(arm, level)
    known = params['wheelbase'] if arm.known_eb else 0.0
    return FilterConfig(model_version='sensor-v2', kind='ekf', s_mode='direct', use_range=False, use_s=False,
                        anchor_xyz=(4.0, 0.0, 2.65), mount_deg=0., robot_z=0.45, bias_rw_std=0.,
                        known_wheelbase_error=known, p0_std=tuple(p0), use_odom_heading=arm.odom,
                        k_s=2e-5, k_theta=1e-4, k_stheta=1e-5, gyro_N_rad_sqrt_s=math.radians(.015))


def initial_state(arm, route, seed, params, p0):
    """Identical to r22_adr_decomposition.one(): pose drawn from the pose prior with the frozen 'initial' stream."""
    truth0 = MOT[route]['pose'][0]
    x0 = np.r_[truth0, 0., 0., 0.]
    x0[:3] += V.rng(seed, 'initial').normal(size=3) * np.asarray(p0[:3])
    if arm.prior == 'oracle':
        x0[3:] = [params['gyro_bias'], params['gyro_sf'], params['wheel_asymmetry']]
    return x0


# ----------------------------------------------------------------------------- EKF (frozen) and diagnostic variants
def _variant_step(f, d, g, o, dt, arm, q_true):
    """Re-implementation of SensorV2Filter.step with ONE diagnostic change (noC or oracle Q). Frozen functions only."""
    c = f.comps[0]
    cfg = f.cfg
    xp = c.x.copy()
    b = cfg.wheel_base / (1 + cfg.known_wheelbase_error)
    c.x, Fm, G = F.transition(xp, d, g, dt, b)
    if arm.q_source == 'true':
        Q = q_true
    else:
        Q = np.diag([cfg.k_s * abs(d), cfg.gyro_N_rad_sqrt_s ** 2 * dt, cfg.k_theta * abs(o) + cfg.k_stheta * abs(d)])
    c.P = Fm @ c.P @ Fm.T + G @ Q @ G.T
    h, H, B = F.odometry_model(xp, d, g, dt, cfg.wheel_base, cfg.known_wheelbase_error)
    C = np.zeros(6) if arm.update == 'noC' else -G @ Q @ B
    R = float(B @ Q @ B)
    y = o - h
    S = float(H @ c.P @ H + R + 2 * H @ C)
    status = 'disabled'
    if cfg.use_odom_heading:
        if S <= 1e-20:
            status = 'zero_variance'
        elif y * y / S > CHI2_1_999:
            status = 'rejected'
            f.stats['o_rejected'] += 1
        else:
            c.x, c.P, _ = F.correlated_update(c.x, c.P, H, y, R, C)
            status = 'applied'
            f.stats['o_updates'] += 1
    c.P[3, 3] += cfg.bias_rw_std ** 2 * dt
    return dict(innovation=y, R=R, S=S, status=status, H=H, C=C, Q=Q, F=Fm, G=G)


STATUS_CODE = {'initial': 0, 'applied': 1, 'rejected': 2, 'disabled': 3, 'zero_variance': 4}


def run_ekf(arm, cfg, inputs, x0, q_true=None, full_trace=False):
    f = F.SensorV2Filter(cfg, None, x0)
    n = len(inputs['ds_odom'])
    b = cfg.wheel_base / (1 + cfg.known_wheelbase_error)
    xs = dict(pre=np.empty((n, 6)), post=np.empty((n, 6)))
    Ps = dict(pre=np.empty((n, 6, 6)), post=np.empty((n, 6, 6)))
    zodom = np.full(n, np.nan)
    status = np.zeros(n, np.int8)
    trace = [] if full_trace else None
    c = f.comps[0]
    xs['pre'][0] = xs['post'][0] = c.x
    Ps['pre'][0] = Ps['post'][0] = c.P
    frozen = arm.update == 'frozen' and arm.q_source == 'measured'
    for k in range(1, n):
        d, g, o, dt = (inputs['ds_odom'][k], inputs['dtheta_gyro'][k], inputs['dtheta_odom'][k], inputs['dt_s'][k])
        xp, Pp = c.x.copy(), c.P.copy()
        rec = f.step(d, g, o, dt) if frozen else _variant_step(f, d, g, o, dt, arm, None if q_true is None else q_true[k])
        xm = F.transition(xp, d, g, dt, b)[0]
        Pm = rec['F'] @ Pp @ rec['F'].T + rec['G'] @ rec['Q'] @ rec['G'].T
        xs['pre'][k], Ps['pre'][k] = xm, Pm
        xs['post'][k], Ps['post'][k] = c.x, c.P
        zodom[k] = rec['innovation'] / math.sqrt(rec['S']) if rec['S'] > 0 else np.nan
        status[k] = STATUS_CODE[rec['status']]
        if full_trace:
            K = (Pm @ rec['H'] + rec['C']) / rec['S'] if rec['status'] == 'applied' else np.zeros(6)
            trace.append(dict(k=k, F=rec['F'], G=rec['G'], Q=rec['Q'], H=rec['H'], C=rec['C'], R=rec['R'],
                              S=rec['S'], K=K, innovation=rec['innovation'], status=rec['status']))
    return xs, Ps, zodom, status, trace


# ----------------------------------------------------------------------------- vectorised model (validated against frozen)
def transition_vec(x, d, g, dt, b):
    """Frozen `transition` mean map, vectorised over rows of x and (optionally) per-row d, g."""
    D = 1 + x[:, 4]
    a = (g - x[:, 3] * dt) / D
    u = d - x[:, 5] * b * a / 4
    half = a / 2
    small = np.abs(half) < 1e-5
    hs = np.where(small, 1.0, half)
    s = np.where(small, 1 - half ** 2 / 6 + half ** 4 / 120, np.sin(hs) / hs)
    ang = x[:, 2] + half
    out = x.copy()
    out[:, 0] += u * s * np.cos(ang)
    out[:, 1] += u * s * np.sin(ang)
    out[:, 2] = DC.wrap(x[:, 2] + a)
    return out


def odometry_h_vec(x, d, g, dt, b_nom, known_eb=0.):
    D = 1 + x[:, 4]
    b = b_nom / (1 + known_eb)
    eps = x[:, 5]
    a = (g - x[:, 3] * dt) / D
    L = 1 - eps ** 2 / 4
    return (L * a + eps * d / b) / (1 + known_eb)


def _sqrt_psd(P):
    try:
        return np.linalg.cholesky(P)
    except np.linalg.LinAlgError:
        w, Vv = np.linalg.eigh(0.5 * (P + P.T))
        return Vv * np.sqrt(w.clip(min=0))


class CubatureKF:
    """Third-degree cubature KF on [x(6), n_d, n_g, n_o]; joint predict+odometry update, same model/gate as EKF."""

    def __init__(self, cfg, x0, P0):
        self.cfg = cfg
        self.x = np.array(x0, float)
        self.P = np.array(P0, float)
        self.b = cfg.wheel_base / (1 + cfg.known_wheelbase_error)
        self.stats = dict(o_updates=0, o_rejected=0)

    def step(self, d, g, o, dt):
        cfg = self.cfg
        Q = np.array([cfg.k_s * abs(d), cfg.gyro_N_rad_sqrt_s ** 2 * dt, cfg.k_theta * abs(o) + cfg.k_stheta * abs(d)])
        S_aug = np.zeros((9, 9))
        S_aug[:6, :6] = _sqrt_psd(self.P)
        S_aug[6:, 6:] = np.diag(np.sqrt(Q))
        m_aug = np.r_[self.x, 0., 0., 0.]
        pts = m_aug + math.sqrt(9) * np.concatenate([S_aug.T, -S_aug.T])      # 18 points
        xprev, nd, ng, no = pts[:, :6], pts[:, 6], pts[:, 7], pts[:, 8]
        xn = transition_vec(xprev, d - nd, g - ng, dt, self.b)
        z = odometry_h_vec(xprev, d - nd, g - ng, dt, cfg.wheel_base, cfg.known_wheelbase_error) + no
        ref = transition_vec(self.x[None], np.array([d]), np.array([g]), dt, self.b)[0, 2]
        dpsi = DC.wrap(xn[:, 2] - ref)
        xbar = xn.mean(0)
        xbar[2] = DC.wrap(ref + dpsi.mean())
        dx = xn - xbar
        dx[:, 2] = DC.wrap(xn[:, 2] - xbar[2])
        zbar = z.mean()
        dz = z - zbar
        Pxx = dx.T @ dx / len(pts)
        Pxz = dx.T @ dz / len(pts)
        Pzz = float(dz @ dz / len(pts))
        pre = (xbar.copy(), 0.5 * (Pxx + Pxx.T))
        y = o - zbar
        status = 'disabled'
        x, P = pre[0].copy(), pre[1].copy()
        if cfg.use_odom_heading:
            if Pzz <= 1e-20:
                status = 'zero_variance'
            elif y * y / Pzz > CHI2_1_999:
                status = 'rejected'
                self.stats['o_rejected'] += 1
            else:
                K = Pxz / Pzz
                x = x + K * y
                x[2] = DC.wrap(x[2])
                P = P - Pzz * np.outer(K, K)
                P = 0.5 * (P + P.T)
                status = 'applied'
                self.stats['o_updates'] += 1
        self.x, self.P = x, P
        return dict(pre=pre, innovation=y, S=Pzz, status=status)


class ParticleFilter:
    """Particle filter with the locally optimal proposal for the shared input noise (n_d, n_g).

    Adapted from research/V02_E1E6_20261012/run_e1e6.py:PF (range update removed, wheelbase handling added,
    particles stored as contiguous rows X[6, N]). The odometry residual is exactly linear in the input noise given
    x_prev: y = o - h(x_prev, d, g) = B1 n_d + B2 n_g + n_o, so each particle is weighted by N(y; 0, S) and its
    (n_d, n_g) drawn from the Gaussian conditional (Matheron update). Resampling: systematic when ESS < N/2, then a
    Liu-West shrinkage kernel (a = 0.98) that preserves the cloud mean and covariance.
    With use_odom_heading=False there is no weighting or resampling (plain nonlinear Monte Carlo propagation).
    """
    JIT_A = 0.98

    def __init__(self, cfg, x0, P0, n_part, rng):
        self.cfg = cfg
        self.n = n_part
        self.rng = rng
        self.b_nom = cfg.wheel_base
        self.b = cfg.wheel_base / (1 + cfg.known_wheelbase_error)
        self.X = (np.asarray(x0, float)[:, None] + _sqrt_psd(np.asarray(P0, float)) @ rng.standard_normal((6, n_part)))
        self.lw = np.full(n_part, -math.log(n_part))
        self.stats = dict(o_updates=0, o_rejected=0, resamples=0, ess_min=float(n_part))

    @staticmethod
    def _transition_rows(X, d, g, dt, b):
        D = 1 + X[4]
        a = (g - X[3] * dt) / D
        u = d - X[5] * b * a / 4
        half = a / 2
        us = u * np.sinc(half / np.pi)
        ang = X[2] + half
        out = np.empty_like(X)
        out[0] = X[0] + us * np.cos(ang)
        out[1] = X[1] + us * np.sin(ang)
        out[2] = DC.wrap(X[2] + a)
        out[3:] = X[3:]
        return out

    def step(self, d, g, o, dt):
        c = self.cfg
        n, X, rng = self.n, self.X, self.rng
        ke = 1 + c.known_wheelbase_error
        Qd = c.k_s * abs(d)
        Qg = c.gyro_N_rad_sqrt_s ** 2 * dt
        Qo = c.k_theta * abs(o) + c.k_stheta * abs(d)
        z = rng.standard_normal((3, n))
        z1, z2 = z[0] * math.sqrt(Qd), z[1] * math.sqrt(Qg)
        if c.use_odom_heading:
            D = 1 + X[4]
            eps = X[5]
            L = 1 - eps ** 2 / 4
            h0 = (L * (g - X[3] * dt) / D + eps * d * ke / self.b_nom) / ke
            B1 = -eps / self.b_nom
            B2 = -L / D / ke
            S = B1 * B1 * Qd + B2 * B2 * Qg + Qo
            y = o - h0
            self.lw = self.lw - 0.5 * y * y / S - 0.5 * np.log(S)
            r = (y - (B1 * z1 + B2 * z2 + z[2] * math.sqrt(Qo))) / S
            nd = z1 + Qd * B1 * r
            ng = z2 + Qg * B2 * r
            self.stats['o_updates'] += 1
        else:
            nd, ng = z1, z2
        self.X = self._transition_rows(X, d - nd, g - ng, dt, self.b)
        if c.use_odom_heading:
            m = self.lw.max()
            self.lw -= m + math.log(np.exp(self.lw - m).sum())
            self._maybe_resample()
        return dict(status='applied' if c.use_odom_heading else 'disabled')

    def _maybe_resample(self):
        w = np.exp(self.lw)
        ess = 1.0 / np.sum(w * w)
        self.stats['ess_min'] = min(self.stats['ess_min'], float(ess))
        if ess >= self.n / 2:
            return
        self.stats['resamples'] += 1
        pos = (self.rng.random() + np.arange(self.n)) / self.n
        idx = np.minimum(np.searchsorted(np.cumsum(w), pos), self.n - 1)
        th = self.X[:, idx]
        ref = th[2, 0]
        th[2] = DC.wrap(th[2] - ref)
        m = th.mean(1, keepdims=True)
        Lc = _sqrt_psd(np.cov(th) + 1e-30 * np.eye(6))
        A = self.JIT_A
        new = A * th + (1 - A) * m + math.sqrt(1 - A * A) * (Lc @ self.rng.standard_normal((6, self.n)))
        new[2] = DC.wrap(new[2] + ref)
        self.X = new
        self.lw = np.full(self.n, -math.log(self.n))

    def mean_cov(self):
        w = np.exp(self.lw)
        X = self.X
        m = X @ w
        m[2] = math.atan2(w @ np.sin(X[2]), w @ np.cos(X[2]))
        dX = X - m[:, None]
        dX[2] = DC.wrap(X[2] - m[2])
        return m, (dX * w) @ dX.T


def run_sigma_or_particle(arm, cfg, inputs, x0, P0, seed):
    n = len(inputs['ds_odom'])
    xs = dict(pre=np.full((n, 6), np.nan), post=np.empty((n, 6)))
    Ps = dict(pre=np.full((n, 6, 6), np.nan), post=np.empty((n, 6, 6)))
    zodom = np.full(n, np.nan)
    status = np.zeros(n, np.int8)
    if arm.estimator == 'ckf':
        f = CubatureKF(cfg, x0, P0)
        xs['pre'][0] = xs['post'][0] = f.x
        Ps['pre'][0] = Ps['post'][0] = f.P
    else:
        f = ParticleFilter(cfg, x0, P0, arm.n_particles, np.random.default_rng([DIAG_NAMESPACE, int(seed), 7]))
        xs['post'][0], Ps['post'][0] = f.mean_cov()
    for k in range(1, n):
        rec = f.step(inputs['ds_odom'][k], inputs['dtheta_gyro'][k], inputs['dtheta_odom'][k], inputs['dt_s'][k])
        status[k] = STATUS_CODE[rec['status']]
        if arm.estimator == 'ckf':
            xs['pre'][k], Ps['pre'][k] = rec['pre']
            xs['post'][k], Ps['post'][k] = f.x, f.P
            zodom[k] = rec['innovation'] / math.sqrt(rec['S']) if rec['S'] > 0 else np.nan
        else:
            xs['post'][k], Ps['post'][k] = f.mean_cov()
    return xs, Ps, zodom, status, f.stats


# ----------------------------------------------------------------------------- one run -> diagnostics
def errors(truth6, xhat):
    e = truth6 - xhat
    e[:, 2] = DC.wrap(e[:, 2])
    return e


def true_q(inputs_unused, route, cfg):
    m = MOT[route]
    ds, dth, dt = m['ds'], m['dtheta'], m['dt']
    q = np.zeros((len(ds), 3, 3))
    q[:, 0, 0] = cfg.k_s * np.abs(ds)
    q[:, 1, 1] = cfg.gyro_N_rad_sqrt_s ** 2 * dt
    q[:, 2, 2] = cfg.k_theta * np.abs(dth) + cfg.k_stheta * np.abs(ds)
    return q


def run_one(arm_name, route, level, seed, full_trace=False):
    arm = ARMS[arm_name]
    inputs, ev, params, truth6 = make_world(arm, route, level, seed)
    cfg = make_cfg(arm, level, params)
    p0 = np.asarray(cfg.p0_std, float)
    x0 = initial_state(arm, route, seed, params, p0)
    stats, trace = {}, None
    if arm.estimator == 'ekf':
        qt = true_q(inputs, route, cfg) if arm.q_source == 'true' else None
        xs, Ps, zodom, status, trace = run_ekf(arm, cfg, inputs, x0, qt, full_trace)
    else:
        xs, Ps, zodom, status, stats = run_sigma_or_particle(arm, cfg, inputs, x0, np.diag(p0 ** 2), seed)
    psi_path = MOT[route]['pose'][:, 2]
    out = dict(seed=seed, params=params, zodom=zodom, status=status, stats=stats, trace=trace, x0=x0)
    for phase in ('pre', 'post'):
        if np.isnan(xs[phase][1:]).all():
            continue
        E = errors(truth6, xs[phase])
        out['E_' + phase] = E
        out['P_' + phase] = Ps[phase]
        out['diag_' + phase] = DC.per_run_diagnostics(E, Ps[phase], psi_path)
    return out


# ----------------------------------------------------------------------------- cell aggregation
PER_RUN_KEYS = ('nees_pose', 'nees_heading', 'nees_cond_xy', 'nees_xy', 'nees_cal', 'nees_full', 'z2_long', 'z2_lat',
                'z2_long_cond', 'z2_lat_cond', 'sigma_psi', 'cond_xy_min_sigma')


def _chunk_worker(task):
    arm_name, route, level, seeds = task
    n = len(MOT[route]['t'])
    snap = snapshot_indices(MOT[route]['t'])
    acc = {}
    runs = []
    for seed in seeds:
        r = run_one(arm_name, route, level, seed)
        for phase in ('pre', 'post'):
            if 'E_' + phase not in r:
                continue
            E, P = r['E_' + phase], r['P_' + phase]
            a = acc.setdefault(phase, dict(sum_e=np.zeros((n, 6)), sum_ee=np.zeros((n, 6, 6)), sum_P=np.zeros((n, 6, 6))))
            a['sum_e'] += E
            a['sum_ee'] += E[:, :, None] * E[:, None, :]
            a['sum_P'] += P
        runs.append(dict(seed=seed, params=r['params'], zodom=r['zodom'].astype(np.float32), status=r['status'],
                         stats=r['stats'],
                         E={ph: r['E_' + ph].astype(np.float32) for ph in ('pre', 'post') if 'E_' + ph in r},
                         P3={ph: r['P_' + ph][:, :3, :3].copy() for ph in ('pre', 'post') if 'E_' + ph in r},
                         diag={ph: {k: r['diag_' + ph][k].astype(np.float32) for k in PER_RUN_KEYS}
                               for ph in ('pre', 'post') if 'diag_' + ph in r},
                         P_snap=r['P_post'][snap]))
    return acc, runs


def run_cell(arm_name, route, level, seeds, procs=4, chunk=10):
    from multiprocessing import Pool
    tasks = [(arm_name, route, level, seeds[i:i + chunk]) for i in range(0, len(seeds), chunk)]
    acc_total, runs = {}, []
    with Pool(procs) as pool:
        for acc, rr in pool.imap(_chunk_worker, tasks):
            for ph, a in acc.items():
                tot = acc_total.setdefault(ph, {k: np.zeros_like(v) for k, v in a.items()})
                for k, v in a.items():
                    tot[k] += v
            runs.extend(rr)
    runs.sort(key=lambda r: r['seed'])
    return acc_total, runs


def cell_arrays(runs, acc):
    """Stack per-run results into arrays for saving/analysis."""
    out = dict(seeds=np.array([r['seed'] for r in runs]),
               param_names=np.array(list(runs[0]['params'])),
               params=np.array([list(r['params'].values()) for r in runs]),
               zodom=np.stack([r['zodom'] for r in runs]), status=np.stack([r['status'] for r in runs]),
               P_snap=np.stack([r['P_snap'] for r in runs]))
    for ph in ('pre', 'post'):
        if ph not in runs[0]['E']:
            continue
        out[f'E_{ph}'] = np.stack([r['E'][ph] for r in runs])
        out[f'P3_{ph}'] = np.stack([r['P3'][ph] for r in runs])
        for k in PER_RUN_KEYS:
            out[f'{k}_{ph}'] = np.stack([r['diag'][ph][k] for r in runs])
        for k, v in acc[ph].items():
            out[f'{k}_{ph}'] = v
    stats = [r['stats'] for r in runs if r['stats']]
    if stats:
        for k in stats[0]:
            out[f'est_{k}'] = np.array([s[k] for s in stats], float)
    return out


# ----------------------------------------------------------------------------- R2-2 compatible metrics
def r22_metrics(N, nees, t, pos_err=None, head_err=None):
    """Exactly the R2-2 `metrics` (t>=30, ensemble ANEES_k, chi2(3N)/N band, coverage, late 25%)."""
    from scipy.stats import chi2
    keep = t >= 30
    A = np.nanmean(nees[:, keep], axis=0)
    cut = int(0.75 * keep.sum())
    lo, hi = chi2.ppf([.025, .975], 3 * N) / N
    cov = float(np.nanmean(nees[:, keep] <= chi2.ppf(.95, 3)))
    per_run = np.nanmean(nees[:, keep], axis=1)
    out = dict(anees=float(np.nanmean(A)), anees_late25=float(np.nanmean(A[cut:])), coverage95=cov,
               frac_k_inside_chi2_interval=float(np.mean((A >= lo) & (A <= hi))),
               per_run_mean_nees_median=float(np.median(per_run)), per_run_mean_nees_mean=float(np.mean(per_run)),
               consistent=bool(2.4 <= np.nanmean(A) <= 3.6 and 0.92 <= cov <= 0.98 and 2.4 <= np.nanmean(A[cut:]) <= 3.6),
               direction='OVERCONFIDENT' if np.nanmean(A) > 3.6 else ('CONSERVATIVE' if np.nanmean(A) < 2.4 else 'IN_BAND'))
    if pos_err is not None:
        out['pos_rmse_m'] = float(np.sqrt(np.mean(pos_err[:, keep].astype(float) ** 2)))
        out['heading_rmse_deg'] = float(np.degrees(np.sqrt(np.mean(head_err[:, keep].astype(float) ** 2))))
    return out


def cell_summary(arr, route):
    t = MOT[route]['t']
    E = arr['E_post'].astype(float)
    nees = arr['nees_pose_post'].astype(np.float32).astype(float)
    m = r22_metrics(len(arr['seeds']), nees, t, np.hypot(E[:, :, 0], E[:, :, 1]).astype(np.float32), E[:, :, 2].astype(np.float32))
    keep = t >= 30
    for k in ('nees_heading', 'nees_cond_xy', 'nees_xy', 'z2_long', 'z2_lat', 'z2_long_cond', 'z2_lat_cond'):
        m[f'mean_{k}'] = float(np.nanmean(np.nanmean(arr[f'{k}_post'][:, keep].astype(float), axis=0)))
    m['mean_sigma_psi_end_deg'] = float(np.degrees(np.mean(arr['sigma_psi_post'][:, -1])))
    m['heading_rms_end_deg'] = float(np.degrees(np.sqrt(np.mean(E[:, -1, 2] ** 2))))
    st = arr['status'][:, 1:]
    m['odom_applied_frac'] = float(np.mean(st == STATUS_CODE['applied']))
    m['odom_rejected_frac'] = float(np.mean(st == STATUS_CODE['rejected']))
    z = arr['zodom'][:, 1:].astype(float)
    ok = st == STATUS_CODE['applied']
    if ok.any():
        zz = z[ok]
        m['odom_z_mean'] = float(np.mean(zz))
        m['odom_z_var'] = float(np.var(zz))
        zr = np.where(ok, z, np.nan)
        a, b_ = zr[:, :-1].ravel(), zr[:, 1:].ravel()
        good = np.isfinite(a) & np.isfinite(b_)
        m['odom_z_lag1'] = float(np.corrcoef(a[good], b_[good])[0, 1]) if good.sum() > 2 else float('nan')
    return m


# ----------------------------------------------------------------------------- provenance
def git_state():
    try:
        head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        dirty = bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain', '--', str(HERE)], text=True).strip())
    except Exception:  # pragma: no cover
        head, dirty = 'UNKNOWN', True
    return dict(head=head, research_dir_dirty=dirty)


def input_hashes(extra=()):
    files = {str((FROZEN_SRC / f).relative_to(ROOT)): sha256(FROZEN_SRC / f) for f in FROZEN_FILES}
    for r in ROUTES:
        files[MOT[r]['path']] = MOT[r]['sha256']
    for p in sorted(HERE.glob('*.py')):
        files[str(p.relative_to(ROOT))] = sha256(p)
    for p in extra:
        p = Path(p)
        files[str(p.relative_to(ROOT))] = sha256(p)
    return files


def write_manifest(out_dir, name, config, outputs, started, extra_inputs=()):
    import scipy
    cfg_text = json.dumps(config, sort_keys=True, default=str)
    doc = dict(name=name, command=' '.join([Path(sys.executable).name] + sys.argv), started_utc=started,
               finished_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), git=git_state(),
               python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
               config=config, config_sha256=hashlib.sha256(cfg_text.encode()).hexdigest(),
               inputs=input_hashes(extra_inputs),
               outputs={str(Path(p).relative_to(ROOT)): sha256(p) for p in outputs if Path(p).exists()})
    path = Path(out_dir) / f'MANIFEST_{name}.json'
    path.write_text(json.dumps(doc, indent=1, default=str))
    return path


def utc_now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
