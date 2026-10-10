"""Checks that the frozen sensor-v2 generator/filter reproduce the numbers and relations of the user's sensor-model design review
(10 m straight drive at 0.2 m/s; small-error relation between the wheel and gyro yaw increments; filter odometry model vs generator)."""
import math
import unittest

import numpy as np

from qclean_uwb.drivesim import sensor_v2 as V
from qclean_uwb.drivesim.filter_v2 import odometry_model

B = 0.287
T = np.arange(0, 50.0001, 0.2)
DS = np.r_[0, np.full(len(T) - 1, 0.04)]
DTH = np.zeros(len(T))


def gen(cond, params, seed=1):
    return V.generate(T, DS, DTH, V.SensorV2Config(condition=cond), seed, params)[0]


class ReviewConsistency(unittest.TestCase):
    def test_gyro_bias_rows(self):
        for b, head, lat in ((0.01, 0.50, 4.36), (0.05, 2.50, 21.81), (0.20, 10.00, 87.05)):
            p = V.integrate(DS, gen("gyro_bias", dict(gyro_bias=math.radians(b)))["dtheta_gyro"])
            self.assertAlmostEqual(math.degrees(p[-1, 2]), head, delta=0.01)
            self.assertAlmostEqual(100 * p[-1, 1], lat, delta=0.02)

    def test_wheel_ratio_rows(self):
        for e, head, lat in ((0.002, 3.99, 34.83), (0.005, 9.98, 86.89), (0.010, 19.96, 172.46)):
            i = gen("wheel_asymmetry", dict(wheel_asymmetry=e))
            p = V.integrate(i["ds_odom"], i["dtheta_odom"])
            self.assertAlmostEqual(math.degrees(p[-1, 2]), head, delta=0.01)
            self.assertAlmostEqual(100 * p[-1, 1], lat, delta=0.02)

    def test_gyro_white_noise_row(self):
        h, y = [], []
        for s in range(600):
            p = V.integrate(DS, gen("gyro_noise", {}, seed=s)["dtheta_gyro"])
            h.append(math.degrees(p[-1, 2]))
            y.append(100 * p[-1, 1])
        self.assertAlmostEqual(float(np.std(h)), 0.106, delta=0.106 * 0.08)
        self.assertAlmostEqual(float(np.std(y)), 1.07, delta=1.07 * 0.08)

    def test_yaw_increment_difference_relation_and_filter_model(self):
        cfg = V.SensorV2Config(condition="all", k_distance_m=0, k_yaw_rad=0, k_yaw_distance_rad2_m=0, gyro_N_rad_sqrt_s=0, slip_mode="off")
        for ds_v, th_v, par in ((0.04, 0.0, dict(gyro_bias=math.radians(0.2), gyro_sf=0.0, wheel_asymmetry=0.01, wheelbase=0.0)),
                                (0.0, 0.3, dict(gyro_bias=0.0, gyro_sf=0.015, wheel_asymmetry=0.0, wheelbase=0.01)),
                                (0.04, 0.05, dict(gyro_bias=math.radians(0.2), gyro_sf=-0.01, wheel_asymmetry=0.01, wheelbase=-0.01))):
            ds, th, t = np.r_[0, np.full(50, ds_v)], np.r_[0, np.full(50, th_v)], np.arange(51) * 0.2
            i, e = V.generate(t, ds, th, cfg, 3, dict(par))
            p = dict(zip(e["parameter_names"], e["true_parameters"]))
            lhs = (i["dtheta_odom"] - i["dtheta_gyro"])[1:]
            rhs = p["wheel_asymmetry"] / B * ds[1:] - (p["wheelbase"] + p["gyro_sf"]) * th[1:] - p["gyro_bias"] * 0.2
            self.assertLess(np.abs(lhs - rhs).max() / np.abs(lhs).mean(), 0.01)       # first-order relation of the review; second-order terms remain
            x = np.array([0, 0, 0, p["gyro_bias"], p["gyro_sf"], p["wheel_asymmetry"]])
            for known in (p["wheelbase"], 0.0):
                err = max(abs(i["dtheta_odom"][k] - odometry_model(x, i["ds_odom"][k], i["dtheta_gyro"][k], 0.2, B, known_eb=known)[0]) for k in range(1, 51))
                if known == p["wheelbase"]:
                    self.assertLess(err, 1e-12)                       # known e_b: the filter's odometry model is exact
                else:
                    self.assertAlmostEqual(err, abs(p["wheelbase"]) * abs(th_v), delta=0.02 * abs(p["wheelbase"]) * abs(th_v) + 1e-15)   # unknown e_b: mismatch ~ e_b * dtheta

    def test_slip_rate_and_scale(self):
        cfg = V.SensorV2Config()
        self.assertAlmostEqual(cfg.slip_rate_per_s, 0.0503, places=4)
        self.assertAlmostEqual(1 - math.exp(-cfg.slip_rate_per_s * 10.0), 0.395, places=3)
        self.assertAlmostEqual(cfg.manifest()["slip_std_rad"], math.radians(0.5) * math.sqrt(3), places=12)


if __name__ == "__main__":
    unittest.main()
