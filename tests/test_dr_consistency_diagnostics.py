"""Unit tests for the DR EKF consistency diagnosis (research/DR_EKF_DIAGNOSIS_20261013).

Pure-math checks import dr_consistency directly. Checks that need the frozen sensor-v2 package run in a subprocess:
the frozen tree also defines a top-level `qclean_uwb` package, which must not collide with src/qclean_uwb here.
"""
import importlib.util
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

DIAG = Path(__file__).resolve().parents[1] / 'research' / 'DR_EKF_DIAGNOSIS_20261013'


def _load(name):
    spec = importlib.util.spec_from_file_location(name, DIAG / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DC = _load('dr_consistency')


def _spd(rng, n, scale=1.0):
    A = rng.standard_normal((n, n))
    return scale * (A @ A.T + n * np.eye(n))


def test_heading_conditional_split_adds_up_to_pose_nees():
    rng = np.random.default_rng(1)
    P = np.stack([_spd(rng, 3) for _ in range(50)])
    P[:, :2, 2] *= 0.9
    P[:, 2, :2] *= 0.9
    e = rng.standard_normal((50, 3))
    s = DC.heading_conditional_split(e, P)
    np.testing.assert_allclose(s['heading'] + s['cond_xy'], DC.nees(e, P), rtol=1e-10)


def test_split_expectations_one_and_two_for_consistent_samples():
    rng = np.random.default_rng(2)
    P = np.array([[4.0, 0.5, 1.9], [0.5, 1.0, 0.2], [1.9, 0.2, 1.0]])
    e = rng.multivariate_normal(np.zeros(3), P, size=200000)
    s = DC.heading_conditional_split(e, np.broadcast_to(P, (len(e), 3, 3)))
    assert abs(s['heading'].mean() - 1) < 0.02
    assert abs(s['cond_xy'].mean() - 2) < 0.03


def test_nees_nan_for_non_positive_definite():
    P = np.array([[[1.0, 0], [0, -1.0]], [[2.0, 0], [0, 2.0]]])
    out = DC.nees(np.array([[1.0, 1.0], [2.0, 2.0]]), P)
    assert np.isnan(out[0]) and out[1] == pytest.approx(4.0)


def test_whitened_moments_identity_when_matched():
    rng = np.random.default_rng(3)
    P = _spd(rng, 3)
    r = DC.mse_vs_predicted(np.zeros(3), P * 10, P * 10, 10)
    np.testing.assert_allclose(r['whitened_eig'], np.ones(3), atol=1e-10)
    assert r['bias_term'] == pytest.approx(0.0, abs=1e-12)
    assert r['var_term'] == pytest.approx(3.0)


def test_whitened_moments_bias_variance_split():
    rng = np.random.default_rng(4)
    P = _spd(rng, 3)
    ebar = np.array([0.3, -0.2, 0.1])
    M = P + np.outer(ebar, ebar)
    r = DC.mse_vs_predicted(ebar, M, P, 1)
    assert r['bias_term'] == pytest.approx(ebar @ np.linalg.solve(P, ebar))
    assert r['bias_term'] + r['var_term'] == pytest.approx(np.trace(np.linalg.solve(P, M)))


def test_long_lat_frame():
    e = np.array([[1.0, 0.0]])
    P = np.array([[[4.0, 0.0], [0.0, 1.0]]])
    np.testing.assert_allclose(DC.long_lat_z2(e, P, np.array([0.0])), [[0.25, 0.0]])
    np.testing.assert_allclose(DC.long_lat_z2(e, P, np.array([math.pi / 2])), [[0.0, 0.25]], atol=1e-15)


def test_first_persistent_exceedance():
    t = np.arange(0, 20, 1.0)
    s = np.zeros(20)
    s[3:5] = 5          # too short
    s[8:16] = 5         # 7 s above
    t0, k = DC.first_persistent_exceedance(s, t, 4.0, min_duration_s=5.0)
    assert (t0, k) == (8.0, 8)
    assert np.isnan(DC.first_persistent_exceedance(s, t, 6.0)[0])


def test_motion_phase_labels():
    ph = DC.motion_phase([0, 0, 0.04, 0.04], [0, 0.08, 0.0, 0.01], [0, 0.2, 0.2, 0.2])
    assert list(ph) == ['stop', 'spin', 'drive_straight', 'drive_curve']


def test_anees_band_shrinks_with_runs():
    lo1, hi1 = DC.anees_band(32)
    lo2, hi2 = DC.anees_band(300)
    assert lo1 < lo2 < 3 < hi2 < hi1
    assert hi2 == pytest.approx(3.28, abs=0.01)


def _run_isolated(code):
    r = subprocess.run([sys.executable, '-c', code], cwd=DIAG, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-3000:]
    return r.stdout


def test_vectorised_models_match_frozen_code():
    out = _run_isolated('''
import numpy as np, dr_harness as H
rng=np.random.default_rng(0)
X=rng.normal(size=(40,6))*np.array([1,1,3,1e-3,1e-2,1e-2])
worst=0.
for d,g in ((0.04,0.0),(0.0,0.087),(0.04,0.004),(0.04,1e-9),(0.04,0.5)):
    for known in (0.0,0.01):
        b=0.287/(1+known)
        ref=np.array([H.F.transition(x,d,g,0.2,b)[0] for x in X])
        hv=np.array([H.F.odometry_model(x,d,g,0.2,0.287,known)[0] for x in X])
        worst=max(worst,np.abs(H.transition_vec(X,d,g,0.2,b)-ref).max(),
                  np.abs(H.ParticleFilter._transition_rows(X.T.copy(),d,g,0.2,b).T-ref).max(),
                  np.abs(H.odometry_h_vec(X,d,g,0.2,0.287,known)-hv).max())
print(worst)
''')
    assert float(out.strip()) < 1e-12


def test_traced_wrapper_reproduces_r22_bitwise():
    out = _run_isolated('''
import sys, numpy as np, dr_harness as H
sys.path.insert(0,str(H.R22_DIR))
import r22_adr_decomposition as R22
_,nees,pe,he=R22.one(('B0','R4',1,6007))
r=H.run_one('B0','R4',1,6007)
E=r['E_post']
ok=(np.array_equal(r['diag_post']['nees_pose'].astype(np.float32),nees,equal_nan=True)
    and np.array_equal(np.hypot(E[:,0],E[:,1]).astype(np.float32),pe) and np.array_equal(E[:,2].astype(np.float32),he))
# reconstructed prediction equals the frozen filter's internal P^- (identity holds when no update is applied)
r2=H.run_one('ODOM_OFF','R4',1,6007)
same=np.array_equal(r2['P_pre'][1:],r2['P_post'][1:]) and np.array_equal(r2['E_pre'][1:],r2['E_post'][1:])
print(ok and same)
''')
    assert out.strip() == 'True'


def test_cubature_filter_agrees_with_ekf_when_nearly_linear():
    out = _run_isolated('''
import numpy as np, dr_harness as H
arm=H.ARMS['ORACLE_CAL']
inputs,ev,p,truth=H.make_world(arm,'R4',0,8001)
cfg=H.make_cfg(arm,0,p); p0=np.asarray(cfg.p0_std); x0=H.initial_state(arm,'R4',8001,p,p0)
xs,Ps,_,_,_=H.run_ekf(arm,cfg,inputs,x0)
ck=H.CubatureKF(cfg,x0,np.diag(p0**2))
for k in range(1,51): ck.step(inputs['ds_odom'][k],inputs['dtheta_gyro'][k],inputs['dtheta_odom'][k],inputs['dt_s'][k])
P=Ps['post'][50][:3,:3]; d=ck.x[:3]-xs['post'][50][:3]
print(float(d@np.linalg.solve(P,d)), float(np.abs(np.linalg.eigvalsh(np.linalg.solve(P,ck.P[:3,:3]))-1).max()))
''')
    # oracle calibration, 2 deg heading, first 10 s (~2 m): the propagation is nearly linear, so the cubature and
    # EKF moments agree (they separate later as the second-order along-track term grows)
    maha, eig_dev = (float(v) for v in out.split())
    assert maha < 0.01 and eig_dev < 0.01


def test_particle_filter_single_step_matches_independent_bootstrap():
    """Locally-optimal proposal + marginal likelihood (PF) vs a bootstrap importance sampler that only weights by the
    odometry-noise density. Exaggerated input noise makes the input-noise conditioning dominate; the negative control
    (conditioning switched off) must be clearly detected by the same comparison."""
    out = _run_isolated('''
import validate_dr_pf as V
r=V.v1_single_step(n_pf=100000, n_ref=1000000)
for k in ('drive','spin'):
    a=r[k]['pf_vs_reference']; print(a['whitened_mean_diff_sq'], a['cov_eig_min'], a['cov_eig_max'])
b=r['drive']['unconditioned_noise_vs_reference']; print(b['whitened_mean_diff_sq'], b['cov_eig_min'], b['cov_eig_max'])
''')
    lines = [[float(x) for x in ln.split()] for ln in out.strip().splitlines()]
    for mean_sq, lo, hi in lines[:2]:
        assert mean_sq < 0.005 and 0.96 < lo and hi < 1.04
    mean_sq, lo, hi = lines[2]
    assert mean_sq > 0.05 or hi > 1.3
