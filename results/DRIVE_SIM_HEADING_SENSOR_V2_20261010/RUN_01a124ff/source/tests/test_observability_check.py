import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

from qclean_uwb.drivesim.hs_lut import HsLut

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("observability_check_under_test", ROOT / "scripts" / "drive_sim" / "observability_check.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ideal_lut(step=2.0):
    th = np.arange(0.0, 90.01, step)
    ph = np.arange(-180.0, 180.0, step)
    a = np.radians(ph)
    s = -np.cos(2.0 * (a[:, None] + a[None, :]))
    return HsLut(dict(theta_deg=th, phi_deg=ph, s=np.repeat(s[None], len(th), 0)))


def rows_straight(n=300, turn_at=150):
    rows = []
    x, yaw = 1.2, 0.0
    for k in range(n):
        if k and k >= turn_at and k < turn_at + 36:
            yaw += math.radians(5.0)
        elif k:
            x += 0.04 * math.cos(yaw)
        rows.append(dict(x=x, y=0.35 + 0.002 * math.sin(k / 9.0), yaw=yaw, drive_g=k, probe_id=-1))
    return rows


def test_information_rank_and_ambiguity_profile_on_a_synthetic_route():
    O = load()
    lut = ideal_lut()
    rows = rows_straight()
    anchor = (4.0, 0.0, 2.65)
    ev = {}
    for name, (ur, us) in {"odom": (False, False), "range": (True, False), "range_s": (True, True)}.items():
        info, Jx, _ = O.information(rows, lut, anchor, 0.45, 45.0, ur, us)
        assert np.allclose(info, info.T, atol=1e-6 * max(1.0, np.abs(info).max()))
        ev[name] = O.summarize_info(info, Jx, rows)
    # odometry alone says nothing about x0, y0, psi0 (three whitened eigenvalues ~ 0); adding s must make the information strictly better
    assert sorted(ev["odom"]["whitened_info_eigenvalues"])[0] < 1e-6 and sorted(ev["odom"]["whitened_info_eigenvalues"])[2] < 1e-6
    assert ev["range_s"]["heading_std_common_mean_deg"] < ev["range"]["heading_std_common_mean_deg"] < ev["odom"]["heading_std_common_mean_deg"]
    amb = O.ambiguity_profile(rows, lut, anchor, 0.45, 45.0)
    assert amb["local_minima"][0]["delta_psi0_deg"] == 0.0 and amb["local_minima"][0]["chi2"] == 0.0
