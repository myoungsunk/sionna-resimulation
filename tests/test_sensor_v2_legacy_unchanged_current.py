"""Companion to tests/test_sensor_v2.py::test_01_legacy_regression (imported verbatim, so it is not edited).

That test compares the current legacy path with the frozen base 2337c33 over *every* key of ``stats``; the current code has additive logging
lists (``s_log``, ``r_log``, A23 rev2) that the frozen reference does not have, so it stops at the first such key.  This test makes the same
comparison over the keys of the frozen reference, asserts that the only extra keys are the additive logs, and also covers the A24
``meas_state = None`` path.  Estimates, covariances, counters and experiment metrics must be bit-identical.
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from test_sensor_v2 import frozen  # noqa: E402

from qclean_uwb.drivesim import experiment as E  # noqa: E402
from qclean_uwb.drivesim import filters as F  # noqa: E402
from qclean_uwb.drivesim import sensors as old  # noqa: E402


class LegacyUnchanged(unittest.TestCase):
    def test_legacy_path_bit_identical_to_frozen_base(self):
        legacy, lf, le = frozen("sensors.py", "frozen_sensors2"), frozen("filters.py", "frozen_filters2"), frozen("experiment.py", "frozen_experiment2")
        for seed in (0, 1, 5, 29, 101):
            ds = np.r_[0.0, np.full(180, 0.04)]
            th = np.r_[0.0, np.sin(np.arange(180)) * 0.04]
            cur = old.generate_inputs(ds, th, old.draw_drift(old.DRIFT_LEVELS[1], np.random.default_rng(seed)), old.SensorNoise(), 0.2, np.random.default_rng(seed + 100))
            orig = legacy.generate_inputs(ds, th, legacy.draw_drift(legacy.DRIFT_LEVELS[1], np.random.default_rng(seed)), legacy.SensorNoise(), 0.2, np.random.default_rng(seed + 100))
            for key in cur:
                np.testing.assert_array_equal(cur[key], orig[key])
            n = len(ds)
            obs = dict(detected=np.ones(n, bool), range_m=np.full(n, 4.2), s=np.zeros(n), power=np.ones((n, 2)))
            flags = dict(turn_phase=np.abs(th) > 0.03)
            for kind in ("ekf", "iekf", "ukf", "gsf"):
                args = dict(kind=kind, use_s=False, use_range=True)
                a = F.run_filter(F.FilterConfig(**args), None, cur, obs, flags, np.zeros(6))
                b = lf.run_filter(lf.FilterConfig(**args), None, orig, obs, flags, np.zeros(6))
                for key in ("est", "cov3"):
                    np.testing.assert_array_equal(a[key], b[key])
                self.assertLessEqual(set(a["stats"]) - set(b["stats"]), {"s_log", "r_log"})
                for key in b["stats"]:
                    np.testing.assert_array_equal(a["stats"][key], b["stats"][key])
            rows = [dict(t_s=k * 0.2, x=k * 0.04, y=0.0, yaw_body_deg=0.0, turn_phase=False, drive_g=k, probe_id=-1) for k in range(n)]
            world = E.World(rows, np.empty((n, 0, 2, 2)), np.empty(0), 0.0, 0.0, None)
            a = E.run_one(world, obs, cur, F.FilterConfig(use_s=False), None, np.zeros(6))
            b = le.run_one(world, obs, orig, F.FilterConfig(use_s=False), None, np.zeros(6))
            for key in ("heading_err_deg", "pos_err_m"):
                np.testing.assert_array_equal(a[key], b[key])
            for key in b["metrics"]:
                np.testing.assert_equal(a["metrics"][key], b["metrics"][key])


if __name__ == "__main__":
    unittest.main()
