import math

import numpy as np
import pytest

from qclean_uwb.drivesim import steered_probe as SP
from qclean_uwb.drivesim.trajectory import TrajectoryConfig, build_samples


def test_target_is_the_nearest_45_mod_90_and_within_45_deg():
    for mount in (0.0, 45.0):
        for base in np.arange(-180.0, 180.0, 7.3):
            d = SP.target_offset_deg(base, mount)
            assert -45.0 <= d < 45.0
            assert math.isclose(((base + d + mount) - 45.0) % 90.0, 0.0, abs_tol=1e-9) or math.isclose(((base + d + mount) - 45.0) % 90.0, 90.0, abs_tol=1e-9)
    assert SP.target_offset_deg(0.0, 45.0) == pytest.approx(0.0)          # corridor heading with 45 deg mount is already optimal
    assert SP.target_offset_deg(0.0, 0.0) == pytest.approx(-45.0)         # 0 deg mount: nearest optimum (45 mod 90) is -45 or +45 -> -45 by the [-45, 45) convention
    assert SP.target_offset_deg(35.7, 0.0) == pytest.approx(9.3)


@pytest.mark.parametrize("base,mount,err", [(0.0, 0.0, 0.0), (0.0, 45.0, 0.0), (35.7, 0.0, 0.0), (-35.7, 0.0, 5.0), (90.0, 45.0, 10.0), (12.0, 0.0, -10.0)])
def test_offsets_have_36_samples_respect_the_rate_and_return_to_zero(base, mount, err):
    o = SP.steer_offsets_deg(base, mount, err)
    assert len(o) == 36 and o[-1] == pytest.approx(0.0)
    steps = np.abs(np.diff([0.0] + o))
    assert steps.max() <= 5.0 + 1e-9                                      # 25 deg/s at 5 Hz
    assert sum(1 for v in o if v == o[len(o) // 2]) >= 18 or o == [0.0] * 36


def test_steer_rows_keeps_everything_but_the_probe_yaw():
    mount = 0.0
    rows = [dict(r, yaw_body_deg=r["yaw_body_deg"]) for r in build_samples(TrajectoryConfig(probe_period_s=10.0))]
    new = SP.steer_rows(rows, mount)
    assert len(new) == len(rows)
    for a, b in zip(rows, new):
        for k in ("x", "y", "drive_g", "phase", "probe_id", "turn_phase"):
            assert a[k] == b[k]
        if a["probe_id"] < 0:
            assert a["yaw_body_deg"] == b["yaw_body_deg"]
    pr = [r for r in new if r["probe_id"] == 0]
    base = pr[0]["yaw_body_deg"] - pr[0]["probe_offset_deg"]
    assert (base + pr[17]["probe_offset_deg"] + mount - 45.0) % 90.0 == pytest.approx(0.0, abs=1e-6) or (base + pr[17]["probe_offset_deg"] + mount - 45.0) % 90.0 == pytest.approx(90.0, abs=1e-6)
