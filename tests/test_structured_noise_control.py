import importlib.util
import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]


def load():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location("structured_noise_control_under_test", ROOT / "scripts" / "drive_sim" / "structured_noise_control.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fake_targets(m, n=400):
    rng = np.random.default_rng(0)
    r_s = m.ar1_from(rng.standard_normal(n), 0.05, 0.03, 0.9)
    r_r = m.ar1_from(rng.standard_normal(n), 0.05, 0.015, 0.7)
    keep = np.ones(n, bool)
    return dict(s=m.stats_of(r_s), range=m.stats_of(r_r), corr_s_range=0.5, keep=keep, r_s_m=r_s, r_r_m=r_r, r_s_full=r_s, r_r_full=r_r,
                dbin=np.searchsorted([5.0, 10.0], np.linspace(1, 14, n)), tbin=np.arange(n) % 4, d3=np.linspace(1, 14, n),
                dist_mean={0: 0.0, 1: 0.05, 2: 0.1}, dist_var={0: 0.01, 1: 0.01, 2: 0.02}, tap_mean={k: 0.0 for k in range(4)}, tap_var={k: 0.01 for k in range(4)})


def test_ar1_reproduces_mean_variance_and_lag1():
    m = load()
    runs = np.array([m.ar1_from(np.random.default_rng(i).standard_normal(400), 0.05, 0.03, 0.9) for i in range(200)])
    assert abs(runs.mean() - 0.05) < 0.01 and abs(runs.var() - 0.03) < 0.004
    c = runs - runs.mean(1, keepdims=True)
    assert 0.8 < float((c[:, :-1] * c[:, 1:]).sum() / (c * c).sum()) < 0.95          # finite-length mean removal biases it slightly low


def test_arm_table_tiers_and_run_counts():
    m = load()
    assert len(m.ARMS) == 22 and set(a for a, v in m.ARMS.items() if v[2] == 0) == {"A0_real_real", "M0_Rmatched_Rmatched", "W0_white_white"}
    assert len(m.expand_arms(["tier0"])) == 3 and len(m.expand_arms(["tier1"])) == 11 and len(m.expand_arms(["tier2"])) == 11 and len(m.expand_arms(["tier3"])) == 6
    assert len(m.expand_arms(["all"])) == 22 and m.expand_arms(["tier1", "S1_bias"]) == m.expand_arms(["tier1"])
    with pytest.raises(SystemExit):
        m.expand_arms(["nope"])


def test_common_random_numbers_and_variance_models():
    m = load()
    m._G.update(sigma_mismatch=0.161, R_range=0.0068579)
    tg = fake_targets(m)
    z = m.stream(3, 1, 101, 400)
    assert np.allclose(m.stream(3, 1, 101, 400), z) and not np.allclose(m.stream(3, 2, 101, 400), z)          # drift enters the stream key
    w = m.gen_noise("s", "white", 400, tg, 3, 1, z, None, None, None)
    r = m.gen_noise("s", "Rmatched", 400, tg, 3, 1, z, None, None, None)
    assert np.allclose(w / tg["s"]["rms"], z) and np.allclose(r / 0.161, z)                                   # same innovations, different scale
    rr = m.gen_noise("range", "Rmatched", 400, tg, 3, 1, z, np.zeros(400), None, None)
    assert np.allclose(rr, z * math.sqrt(0.0068579))
    ar = m.gen_noise("s", "ar1", 400, tg, 3, 1, z, None, None, None)
    assert np.allclose(ar, m.ar1_from(z, tg["s"]["mean"], tg["s"]["var"], tg["s"]["phi"]))                  # the AR(1) arm is built from the same innovations


def test_joint_block_uses_one_index_for_both_series_and_correlated_innovations_hit_the_target():
    m = load()
    rng = np.random.default_rng(2)
    idx = m.block_index(1000, 50, 300, rng)
    assert idx.min() >= 0 and idx.max() < 300 and np.all(np.diff(idx[:50]) % 300 == 1)                        # contiguous circular blocks
    ps, pr, rho = 0.93, 0.80, 0.5
    c = rho * (1 - ps * pr) / math.sqrt((1 - ps ** 2) * (1 - pr ** 2))
    zs, zr = np.random.default_rng(5).standard_normal((2, 200000))
    zr_eff = c * zs + math.sqrt(1 - c * c) * zr
    xs, xr = m.ar1_from(zs, 0, 1, ps), m.ar1_from(zr_eff, 0, 1, pr)
    assert abs(float(np.corrcoef(xs, xr)[0, 1]) - rho) < 0.03
