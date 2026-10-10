import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load():
    sys.path.insert(0, str(ROOT / "src"))
    spec = importlib.util.spec_from_file_location("structured_noise_control_under_test", ROOT / "scripts" / "drive_sim" / "structured_noise_control.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ar1_reproduces_mean_variance_and_lag1():
    m = load()
    rng = np.random.default_rng(3)
    x = np.concatenate([m.ar1(400, 0.05, 0.03, 0.9, rng) for _ in range(200)])
    runs = x.reshape(200, 400)
    assert abs(runs.mean() - 0.05) < 0.01
    assert abs(runs.var() - (0.03 + 0.0)) < 0.004
    c = runs - runs.mean(1, keepdims=True)
    lag1 = float((c[:, :-1] * c[:, 1:]).sum() / (c * c).sum())
    assert 0.8 < lag1 < 0.95            # the finite-length mean removal biases it slightly low


def test_block_bootstrap_keeps_marginal_and_local_structure_and_arm_table_is_complete():
    m = load()
    rng = np.random.default_rng(1)
    series = np.sin(np.linspace(0, 20, 600)) + 0.1 * rng.standard_normal(600)
    b = m.block_bootstrap(series, 1000, 50, rng)
    assert len(b) == 1000 and set(np.round(b, 12)) <= set(np.round(series, 12))      # every value is a value of the real series
    assert abs(np.corrcoef(b[:-1], b[1:])[0, 1]) > 0.9               # blocks keep the short-lag correlation
    assert m.make_transform("A0_real_real", {}) is None               # A0 is the untouched production observation
    assert set(m.ARMS) == {"A0_real_real", "A1_white_white", "A2_iidreal_white", "A3_ar1_white", "A4_blockboot_white", "A5_white_real", "A6_white_ar1", "A7_ar1_ar1"}
