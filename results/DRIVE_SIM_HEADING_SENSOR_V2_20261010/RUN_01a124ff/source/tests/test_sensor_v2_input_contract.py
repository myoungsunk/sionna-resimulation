import unittest
from dataclasses import replace
import numpy as np
from qclean_uwb.drivesim.sensor_v2 import SensorV2Config, generate
from qclean_uwb.drivesim.filter_v2 import run_filter_v2
from qclean_uwb.drivesim.filters import FilterConfig


class InputContractTests(unittest.TestCase):
    def test_nonfinite_configuration(self):
        for field in ('common_scale', 'gyro_N_rad_sqrt_s', 'slip_rate_per_s'):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(SensorV2Config(), **{field: float('nan')})

    def test_nonfinite_generator_inputs(self):
        for ds in ([0., float('nan')], [[0., .1]]):
            with self.assertRaises(ValueError):
                generate([0., .2], ds, [0., 0.], SensorV2Config(), 1)

    def test_nonfinite_true_parameter(self):
        with self.assertRaises(ValueError):
            generate([0., .2], [0., .1], [0., 0.], SensorV2Config(), 1,
                     {'gyro_bias': float('nan')})

    def test_filter_rejects_invalid_inputs(self):
        cfg = FilterConfig(model_version='sensor-v2', use_range=False, use_s=False)
        normal = dict(dt_s=np.array([0., .2]), ds_odom=np.zeros(2),
                      dtheta_gyro=np.zeros(2), dtheta_odom=np.zeros(2))
        for key in normal:
            for value in ([0., float('inf')], [0.]):
                bad = dict(normal, **{key: np.asarray(value)})
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    run_filter_v2(cfg, None, bad, {}, {}, np.zeros(6))
        with self.assertRaises(ValueError):
            run_filter_v2(cfg, None, normal, {}, {}, np.full(6, float('nan')))


if __name__ == '__main__':
    unittest.main()
