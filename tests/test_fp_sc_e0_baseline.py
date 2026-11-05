"""Substantive negative and mathematical controls for E0 stored-array checks."""
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from qclean_uwb.fp_sc.e0_baseline import (BlockedInput, covariance_check,
                                        difference, joint_update, payload,
                                        stored_arithmetic)


class BaselineArithmeticTest(unittest.TestCase):
    def test_exact_linear_conditioning_and_rejection(self):
        prior = np.zeros((2, 4)); prior[1, 2] = 4.0
        P = np.broadcast_to(np.eye(4), (2, 4, 4)).copy()
        H = np.zeros((2, 2, 4)); H[:, 0, 0] = 1.0; H[:, 1, 2] = 1.0
        noise = np.broadcast_to(np.eye(2), (2, 2, 2)).copy()
        result = joint_update(prior, P, H, np.array([[2.0, 0.2], [2.0, 0.2]]), noise, np.array([True, False]))
        np.testing.assert_allclose(result["x"][0], [1.0, 0.0, 0.1, 0.0], atol=1e-15)
        np.testing.assert_array_equal(result["P"][0], np.diag([0.5, 1.0, 0.5, 1.0]))
        np.testing.assert_array_equal(result["x"][1], prior[1])
        np.testing.assert_array_equal(result["P"][1], P[1])
        np.testing.assert_array_equal(result["K"][1], np.zeros((4, 2)))

    def test_non_boolean_acceptance_and_indefinite_noise_rejected(self):
        args = (np.zeros((1, 4)), np.eye(4)[None], np.zeros((1, 2, 4)), np.zeros((1, 2)), np.eye(2)[None])
        with self.assertRaisesRegex(ValueError, "BOOLEAN_MASK"):
            joint_update(*args, np.array([1]))
        bad_noise = np.diag([-1.0, 1.0])[None]
        with self.assertRaisesRegex(ValueError, "COVARIANCE_INVALID"):
            joint_update(*args[:-1], bad_noise, np.array([False]))

    def test_lfs_pointer_is_not_a_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "small.npz"
            path.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abcdef\nsize 99\n")
            with self.assertRaisesRegex(BlockedInput, "LFS_POINTER"):
                payload(path)

    def test_nonfinite_and_asymmetry_do_not_pass(self):
        self.assertFalse(difference(np.array([np.nan]), np.array([np.nan]))["passed"])
        bad = np.eye(4)[None]; bad[0, 0, 1] = 0.01
        self.assertFalse(covariance_check(bad)["passed"])

    @staticmethod
    def one_packet():
        # Closed-form range-only Jacobian at (13,4,0), with an independently
        # determined 3D range; polarization row is zero by construction.
        prior = np.array([[13.0, 4.0, 0.0, 0.0]])
        geometry = np.sqrt(25.0 + 2.2**2)
        H = np.array([[[3.0 / geometry, 4.0 / geometry, 0.0, 0.0], [0.0, 0.0, 0.0, 0.0]]])
        h = np.array([[geometry - 0.5315983906250129, 0.0]])
        base_noise = np.eye(2)[None]
        sigma = float(np.interp(5.0, [0, 1.5, 3, 6, 10], [.011, .020, .050, .120, .240]))
        noise = base_noise.copy(); noise[:, 1, 1] += sigma**2
        packet = dict(z=h.copy(), muMB=np.zeros((1, 2)), muBASE=np.zeros((1, 2)),
                      R=base_noise, P0=np.eye(4), D=np.zeros(1), t=np.zeros(1), pose_id=np.array([0]))
        # With rejection, posterior is exactly prior and K is exactly zero;
        # this tests correctness without manufacturing a production result.
        trace = dict(x=prior.copy(), P=np.eye(4)[None], prior=prior, Pprior=np.eye(4)[None], h=h, H=H,
                     mu=np.zeros((1, 2)), Rvar=noise.copy(), Reff=noise.copy(), K=np.zeros((1, 4, 2)),
                     nu=np.zeros((1, 2)), S=H @ H.swapaxes(-1, -2) + noise,
                     sigma_b=np.array([sigma]), rho_before=np.array([5.0]), weight=np.ones(1), nis=np.zeros(1), d0=np.zeros(1),
                     mask=np.array([False]), t=np.zeros(1), pose_id=np.array([0]))
        return packet, trace

    def test_corrupted_gain_or_posterior_is_detected(self):
        packet, trace = self.one_packet()
        self.assertEqual(stored_arithmetic(packet, trace, 1)["status"], "PASS_STORED_ARITHMETIC")
        for field, index in (("K", (0, 0, 0)), ("P", (0, 0, 0)), ("x", (0, 0))):
            bad = copy.deepcopy(trace); bad[field][index] += 0.001
            check = stored_arithmetic(packet, bad, 1)
            self.assertEqual(check["status"], "FAIL_STORED_ARITHMETIC", field)

    def test_pose_alignment_failure_is_not_silently_reindexed(self):
        packet, trace = self.one_packet()
        trace["pose_id"] = np.array([1])
        with self.assertRaisesRegex(ValueError, "JOIN_MISMATCH"):
            stored_arithmetic(packet, trace, 1)


if __name__ == "__main__":
    unittest.main()
