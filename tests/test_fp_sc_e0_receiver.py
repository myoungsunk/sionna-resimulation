"""Hand-constructed safety/math tests; these are not RF experiment results."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import numpy as np

from qclean_uwb.fp_sc.e0_receiver import (
    MissingPayload,
    geometric_range,
    range_accounting,
    receiver_snapshot,
    require_payload,
    run_flat_sweep,
    signed_error_stats,
    snapshot_from_cir,
    validate_frequencies,
    validate_pose_join,
)


FREQUENCIES = 6_250_400_000.0 + 1_950_000.0 * np.arange(257, dtype=np.float64)


class ReceiverMathTests(unittest.TestCase):
    def test_amplitude_threshold_is_not_power_threshold(self):
        cir = np.zeros((1, 1028, 2), dtype=np.complex128)
        cir[0, 7, 0] = .31
        cir[0, 12, 0] = 1.0
        cir[0, 7, 1] = .1j
        got = snapshot_from_cir(cir, 1_950_000.)
        self.assertEqual(int(got["index"][0]), 7)
        wrong_power_tap = np.flatnonzero(np.abs(cir[0, :, 0]) ** 2 >= .30)[0]
        self.assertEqual(int(wrong_power_tap), 12)
        expected = (.31 ** 2 - .1 ** 2) / (.31 ** 2 + .1 ** 2)
        self.assertAlmostEqual(float(got["s"][0]), expected, places=15)

    def test_rx_peak_tie_uses_first_port_and_first_crossing(self):
        cir = np.zeros((1, 1028, 2), dtype=np.complex128)
        cir[0, 3, 0] = .3
        cir[0, 8, 0] = 1.0
        cir[0, 2, 1] = .4
        cir[0, 11, 1] = 1.0j
        got = snapshot_from_cir(cir, 1_950_000.)
        self.assertEqual(int(got["rx"][0]), 0)
        self.assertEqual(int(got["index"][0]), 3)

    def test_single_port_polarization_null_is_valid(self):
        cir = np.zeros((2, 1028, 2), dtype=np.complex128)
        cir[0, 17, 0] = 2j
        cir[1, 18, 1] = 3.0
        got = snapshot_from_cir(cir, 1_950_000.)
        np.testing.assert_array_equal(got["s"], [1., -1.])
        np.testing.assert_array_equal(got["reference_valid"], [True, True])

    def test_zero_signal_keeps_source_behavior_but_is_not_valid(self):
        cir = np.zeros((1, 1028, 2), dtype=np.complex128)
        got = snapshot_from_cir(cir, 1_950_000.)
        self.assertTrue(bool(got["detected"][0]))
        self.assertEqual(int(got["index"][0]), 0)
        self.assertEqual(float(got["range_m"][0]), 0.)
        self.assertTrue(np.isnan(got["s"][0]))
        self.assertFalse(bool(got["reference_valid"][0]))

    def test_undetected_range_and_ratio_are_nan(self):
        cir = np.zeros((1, 1028, 2), dtype=np.complex128)
        cir[0, 8, 0] = .1
        got = snapshot_from_cir(cir, 1_950_000., threshold=.11)
        self.assertFalse(bool(got["detected"][0]))
        self.assertEqual(int(got["index"][0]), 8)
        self.assertTrue(np.isnan(got["range_m"][0]))
        self.assertTrue(np.isnan(got["s"][0]))

    def test_hann_ifft_scaling_has_known_dc_value(self):
        h = np.ones((1, 257, 2, 1), dtype=np.complex128)
        got = receiver_snapshot(h, FREQUENCIES)
        # Sum of 257-point symmetric Hann is 128.  IFFT /1028 then *257.
        self.assertAlmostEqual(float(got["cir"][0, 0, 0].real), 32.0, places=14)
        self.assertAlmostEqual(float(got["cir"][0, 0, 0].imag), 0.0, places=14)

    def test_noise_uses_whole_batch_real_then_imaginary_draw(self):
        h = np.zeros((3, 257, 2, 1), dtype=np.complex128)
        variance, seed = .02, 1847
        got = receiver_snapshot(h, FREQUENCIES, noise_var=variance, seed=seed)
        rng = np.random.default_rng(seed)
        expected = np.sqrt(variance / 2) * (rng.standard_normal((3, 257, 2)) + 1j * rng.standard_normal((3, 257, 2)))
        np.testing.assert_array_equal(got["h_noisy"], expected)
        chunk_rng = np.random.default_rng(seed)
        wrong = []
        for _ in range(3):
            wrong.append(np.sqrt(variance / 2) * (chunk_rng.standard_normal((257, 2)) + 1j * chunk_rng.standard_normal((257, 2))))
        self.assertFalse(np.array_equal(got["h_noisy"], np.asarray(wrong)))

    def test_invalid_units_dimensions_and_frequency_grid_rejected(self):
        h = np.ones((1, 257, 2, 1), dtype=np.complex128)
        with self.assertRaises(ValueError):
            receiver_snapshot(h, FREQUENCIES, noise_var=.1)
        with self.assertRaises(ValueError):
            receiver_snapshot(h, FREQUENCIES, tx=1)
        with self.assertRaises(ValueError):
            receiver_snapshot(h, FREQUENCIES, noise_var=-.1, seed=0)
        with self.assertRaises(ValueError):
            receiver_snapshot(h[..., 0], FREQUENCIES)
        bad = FREQUENCIES.copy()
        bad[5] += 1.
        with self.assertRaises(ValueError):
            validate_frequencies(bad)
        h[0, 2, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            receiver_snapshot(h, FREQUENCIES)


class RangeAndInputTests(unittest.TestCase):
    def test_exact_join_rejects_duplicate_time_drift_and_rf_overflow(self):
        left = {"pose_id": np.array([1, 2, 4]), "t": np.array([0., .2, .4])}
        np.testing.assert_array_equal(validate_pose_join(left, left, expected_count=3, rf_count=5), [1, 2, 4])
        for right in (
            {"pose_id": np.array([1, 2, 4]), "t": np.array([0., .2, .40000000001])},
            {"pose_id": np.array([1, 3, 4]), "t": left["t"]},
        ):
            with self.assertRaises(ValueError):
                validate_pose_join(left, right, expected_count=3)
        with self.assertRaises(ValueError):
            validate_pose_join({"pose_id": np.array([1, 1, 4]), "t": left["t"]}, None, expected_count=3)
        with self.assertRaises(ValueError):
            validate_pose_join(left, None, expected_count=3, rf_count=4)

    def test_range_convention_removes_mean_and_source_offset_once(self):
        got = range_accounting(np.array([9.4]), b_old=-.5,
                               original_z_r=np.array([9.7]), original_mu_r=np.array([.2]),
                               r_geo=np.array([10.]), r_state=np.array([10.1]), h_r=np.array([9.6]))
        self.assertAlmostEqual(float(got["r_corrected_archived_m"][0]), 10., places=14)
        self.assertAlmostEqual(float(got["z_r_minus_mu_r_m"][0]), 9.5, places=14)
        self.assertAlmostEqual(float(got["r_det_clean_minus_B_OLD_m"][0]), 9.9, places=14)
        self.assertAlmostEqual(float(got["clean_old_mu_mechanism_only_m"][0]), 9.7, places=14)
        self.assertAlmostEqual(float(got["h_r_minus_state_plus_B_OLD_m"][0]), 0., places=14)
        self.assertAlmostEqual(float(got["error_r_state_m"][0]), .1, places=14)

    def test_geometric_range_is_three_dimensional(self):
        value = geometric_range(np.array([[3., 4., 99.]]), anchor=[0., 0., 12.], robot_z_m=0.)
        np.testing.assert_array_equal(value, [13.])

    def test_unknown_samples_do_not_count_as_zero_error(self):
        stats = signed_error_stats(np.array([.03, np.nan, -.05]), .15)
        self.assertEqual(stats["valid"], 2)
        self.assertEqual(stats["invalid"], 1)
        self.assertEqual(stats["within_4cm_fraction"], .5)
        self.assertAlmostEqual(stats["rmse_m"], np.sqrt(.0017))

    def test_lfs_pointer_is_blocked_with_exact_payload_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "data.npz"
            digest = "a" * 64
            path.write_text(f"version https://git-lfs.github.com/spec/v1\noid sha256:{digest}\nsize 12345\n", encoding="ascii")
            with self.assertRaises(MissingPayload) as context:
                require_payload(path)
            self.assertEqual(context.exception.record()["expected_payload_sha256"], digest)
            self.assertEqual(context.exception.record()["expected_payload_bytes"], 12345)

    def test_sweep_refuses_existing_results_without_calculating(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "existing"
            path.mkdir()
            sentinel = path / "DO_NOT_REPLACE"
            sentinel.write_text("preserved", encoding="ascii")
            with self.assertRaises(FileExistsError):
                run_flat_sweep(FREQUENCIES, path, distances_m=np.array([2., 2.01]), b_old=-.5)
            self.assertEqual(sentinel.read_text(), "preserved")


if __name__ == "__main__":
    unittest.main()
