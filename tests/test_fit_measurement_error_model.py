import importlib.util
import math
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("scipy")
_spec = importlib.util.spec_from_file_location("fit_mod", Path(__file__).resolve().parents[1] / "scripts" / "drive_sim" / "fit_measurement_error_model.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def simulate(n, phi, vb, vw, seed):
    rng = np.random.default_rng(seed)
    b = np.empty(n)
    b[0] = math.sqrt(vb) * rng.standard_normal()
    for k in range(1, n):
        b[k] = phi * b[k - 1] + math.sqrt(vb * (1 - phi ** 2)) * rng.standard_normal()
    return b + math.sqrt(vw) * rng.standard_normal(n)


def test_likelihood_matches_dense_gaussian_formula():
    phi, vb, vw = 0.9, 0.03, 0.004
    y = simulate(40, phi, vb, vw, 1)
    idx = np.arange(40)
    C = vb * phi ** np.abs(idx[:, None] - idx[None, :]) + vw * np.eye(40)
    dense = 0.5 * (np.linalg.slogdet(2 * np.pi * C)[1] + y @ np.linalg.solve(C, y))
    assert M.kalman_negloglik([y], phi, vb, vw) == pytest.approx(dense, rel=1e-10)


def test_fit_recovers_known_parameters():
    segs = [simulate(3000, 0.93, 0.03, 0.004, s) for s in (2, 3, 4)]
    r = M.fit(segs)
    assert r["phi"] == pytest.approx(0.93, abs=0.02)
    assert r["var_beta"] == pytest.approx(0.03, rel=0.2)
    assert r["var_w"] == pytest.approx(0.004, rel=0.25)
    assert not r["at_bound"]


def test_acf_variant_and_distance_profile():
    y = simulate(4000, 0.9, 0.03, 0.001, 5)
    assert M.phi_from_acf([y]) == pytest.approx(0.9, abs=0.03)
    d3 = np.linspace(2.5, 14.0, 300)
    r = np.select([d3 > 10, d3 > 5], [0.3, 0.1], 0.03) * np.sign(np.sin(d3 * 50))
    p = M.distance_profile(d3, r)
    assert p["g"][2] > p["g"][1] > p["g"][0] and p["theta_geo_knots_deg"] == sorted(p["theta_geo_knots_deg"])
