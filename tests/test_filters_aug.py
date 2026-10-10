"""A24: augmented EKF (Markov-bias measurement states).  Unit-level sanity tests; they are not the A24 acceptance criteria."""
import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(__file__))
from test_drivesim_filters import ANCHOR, world  # noqa: E402

from qclean_uwb.drivesim import filters as F  # noqa: E402
from qclean_uwb.drivesim.filters_aug import AugmentedDriveFilter  # noqa: E402

MS = dict(aug_s=True, aug_r=True, s=dict(phi=0.93, var_beta=0.02, var_w=0.002), r=dict(phi=0.80, var_beta=0.008, var_w=0.003))


def _cfg(mount, ms=None, **kw):
    return F.FilterConfig(kind="ekf", mount_deg=mount, s_mismatch_sigma=0.02, noise_var_cir_tap=0.0, anchor_xyz=ANCHOR, range_quant_var=0.0,
                          range_extra_sigma=0.0, pos_process_std=0.01, meas_state=ms, **kw)


def _x0(truth):
    return np.array([truth[0, 0], truth[0, 1], truth[0, 2], 0.0, 0.0, 0.0])


def test_switched_off_is_bit_identical_to_stored_filter():
    rows, inputs, obs, flags, truth, lut, mount = world(20.0, 3)
    base = F.run_filter(_cfg(mount), lut, inputs, obs, flags, _x0(truth))
    off = F.run_filter(_cfg(mount, dict(aug_s=False, aug_r=False)), lut, inputs, obs, flags, _x0(truth))
    for k in ("est", "cov3", "cov6"):
        np.testing.assert_array_equal(base[k], off[k])
    for k in ("s_updates", "s_rejected", "r_updates", "r_rejected", "o_updates", "o_rejected"):
        assert base["stats"][k] == off["stats"][k]
    assert base["stats"]["s_log"] == off["stats"]["s_log"] and base["stats"]["r_log"] == off["stats"]["r_log"]


def test_constant_offset_in_s_is_absorbed_by_the_bias_state():
    rows, inputs, obs, flags, truth, lut, mount = world(20.0, 5, s_sigma=0.005)
    obs = dict(obs, s=obs["s"] + 0.12)
    ms = dict(aug_s=True, aug_r=False, s=dict(phi=0.999, var_beta=0.02, var_w=0.001))
    out = F.run_filter(_cfg(mount, ms), lut, inputs, obs, flags, _x0(truth))
    assert abs(out["beta_hat"][-300:, 0].mean() - 0.12) < 0.05
    ref = F.run_filter(_cfg(mount), lut, inputs, obs, flags, _x0(truth))
    err = lambda o: np.degrees(np.abs(F.wrap(o["est"][-300:, 2] - truth[-300:, 2]))).mean()  # noqa: E731
    assert err(out) <= err(ref) + 0.5


def test_covariance_symmetric_psd_and_gate_counts():
    rows, inputs, obs, flags, truth, lut, mount = world(20.0, 7)
    out = F.run_filter(_cfg(mount, MS), lut, inputs, obs, flags, _x0(truth))
    P = out["cov6"]
    assert np.abs(P - np.swapaxes(P, 1, 2)).max() < 1e-12
    assert np.linalg.eigvalsh(P).min() > -1e-10
    assert (out["beta_var"] >= 0).all() and out["beta_hat"].shape == (len(truth), 2)
    assert out["stats"]["s_updates"] > 0 and out["stats"]["r_updates"] > 0


def test_ar1_bias_noise_is_better_handled_by_matched_augmentation():
    """With s error = AR(1) bias generated from the filter's own parameters, the stored filter is over-confident and the augmented one is not."""
    phi, vb, vw = 0.93, 0.02, 0.002
    ms = dict(aug_s=True, aug_r=False, s=dict(phi=phi, var_beta=vb, var_w=vw))
    nees_ref, nees_aug = [], []
    for seed in range(10):
        rows, inputs, obs, flags, truth, lut, mount = world(20.0, 100 + seed, s_sigma=0.0)
        rng = np.random.default_rng(900 + seed)
        n = len(truth)
        b = np.empty(n)
        b[0] = math.sqrt(vb) * rng.standard_normal()
        for k in range(1, n):
            b[k] = phi * b[k - 1] + math.sqrt(vb * (1 - phi ** 2)) * rng.standard_normal()
        obs = dict(obs, s=obs["s"] + b + math.sqrt(vw) * rng.standard_normal(n))
        for cfg, store in ((_cfg(mount, None, s_mismatch_sigma=math.sqrt(vb + vw)) if False else _cfg(mount), nees_ref), (_cfg(mount, ms), nees_aug)):
            if cfg.meas_state is None:
                cfg.s_mismatch_sigma = math.sqrt(vb + vw)
            out = F.run_filter(cfg, lut, inputs, obs, flags, _x0(truth))
            e = out["est"][:, :3] - truth
            e[:, 2] = F.wrap(e[:, 2])
            keep = np.arange(n) >= 150
            store.append(np.mean([ei @ np.linalg.solve(P, ei) for ei, P in zip(e[keep], out["cov3"][keep])]))
    assert np.mean(nees_aug) < np.mean(nees_ref)
    assert np.mean(nees_aug) < 12.0                       # loose sanity bound (expected 3), not an acceptance criterion


def test_distance_profile_scales_bias_process_noise():
    cfg = _cfg(45.0, dict(aug_s=True, aug_r=False, s=dict(phi=0.9, var_beta=0.02, var_w=0.001), s_profile=([0.0, 90.0], [2.0, 2.0])))
    f = AugmentedDriveFilter(cfg, None, np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0]))
    assert f.comps[0].P[6, 6] == pytest.approx(0.04)
    f.comps[0].P[6, 6] = 0.0
    for _ in range(200):
        f.predict(0.0, 0.0)
    assert f.comps[0].P[6, 6] == pytest.approx(0.04, rel=1e-6)


def test_invalid_configuration_is_refused():
    with pytest.raises(ValueError):
        AugmentedDriveFilter(F.FilterConfig(kind="gsf", meas_state=MS), None, np.zeros(6))
    bad = dict(aug_s=True, s=dict(phi=1.2, var_beta=0.02, var_w=0.001))
    with pytest.raises(ValueError):
        AugmentedDriveFilter(F.FilterConfig(meas_state=bad), None, np.zeros(6))


def test_white_part_of_the_measurement_variances():
    rows, inputs, obs, flags, truth, lut, mount = world(20.0, 11)
    ms = dict(aug_s=True, aug_r=True, s=dict(phi=0.9, var_beta=0.02, var_w=0.003), r=dict(phi=0.8, var_beta=0.008, var_w=0.004))
    cfg = F.FilterConfig(kind="ekf", mount_deg=mount, anchor_xyz=ANCHOR, noise_var_cir_tap=0.0, range_sigma=0.05, meas_state=ms)
    out = F.run_filter(cfg, lut, inputs, obs, flags, _x0(truth))
    assert {round(e[5], 12) for e in out["stats"]["s_log"]} == {0.003}                        # thermal off -> var_w only
    assert {round(e[5], 12) for e in out["stats"]["r_log"]} == {round(0.05 ** 2 + 0.004, 12)}   # known random range noise + fitted white remainder
