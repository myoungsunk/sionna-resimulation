import unittest
import numpy as np
from conditional import GATE, joint_gate, update


class ConditionalTests(unittest.TestCase):
    def test_correlated_joint_gate(self):
        H = np.array([[1., 0., .1, 0.], [.2, 0., 1., 0.]])
        P = np.diag([.1, .2, .3, .04])
        R = np.array([[.1, .02], [.02, .2]])
        z = np.array([[.1, .2], [1., 3.], [0., 0.], [3., 1.]])
        expected = np.array([v @ np.linalg.inv(H @ P @ H.T+R) @ v for v in z])
        accepted, nis, _ = joint_gate(z, np.zeros(2), H, P, np.zeros(2), R)
        np.testing.assert_allclose(nis, expected, atol=1e-13)
        np.testing.assert_array_equal(accepted, expected <= GATE)

    def test_unmasked_gain_when_ff_rejected(self):
        x = np.zeros((1, 4)); P = np.eye(4)[None]
        H = np.array([[[1., 0., 0., 0.], [0., 0., 1., 0.]]])
        accepted = np.array([[False, True, False, True]])
        full = np.array([[10., .2]]); los = np.array([[0., .1]])
        before = [v.copy() for v in (x, P, H, accepted, full, los)]
        got = update(x, P, np.zeros((1, 2)), H, np.zeros((1, 2)),
                     np.eye(2)[None], accepted, full, los)
        np.testing.assert_array_equal(got['x'][0, 0], x[0])
        np.testing.assert_allclose(got['x'][0, 1], [0., 0., .1, 0.], atol=1e-15)
        np.testing.assert_allclose(got['K_star'][0], [[.5, 0.], [0., 0.], [0., .5], [0., 0.]])
        np.testing.assert_array_equal(got['P'][0, 0], P[0])
        np.testing.assert_allclose(got['P'][0, 1], np.diag([.5, 1., .5, 1.]))
        for a, b in zip((x, P, H, accepted, full, los), before):
            np.testing.assert_array_equal(a, b)

    def test_zero_residual_and_invalid_mask(self):
        gate, nis, _ = joint_gate(np.zeros((4, 2)), np.zeros(2), np.ones((2, 4)),
                                 np.eye(4), np.zeros(2), np.eye(2))
        np.testing.assert_array_equal(gate, np.ones(4, dtype=bool))
        np.testing.assert_array_equal(nis, np.zeros(4))
        with self.assertRaises(ValueError):
            update(np.zeros((1, 4)), np.eye(4)[None], np.zeros((1, 2)),
                   np.ones((1, 2, 4)), np.zeros((1, 2)), np.eye(2)[None],
                   np.ones((1, 4)), np.zeros((1, 2)), np.zeros((1, 2)))
        with self.assertRaises(ValueError):
            joint_gate(np.full((4, 2), np.nan), np.zeros(2), np.zeros((2, 4)),
                       np.eye(4), np.zeros(2), np.eye(2))
        with np.errstate(over='ignore'), self.assertRaises(ValueError):
            joint_gate(np.full((4, 2), 1e308), np.zeros(2), np.zeros((2, 4)),
                       np.eye(4), np.zeros(2), np.eye(2))

    def test_gate_sides_and_heading_wrap(self):
        root = np.sqrt(GATE)
        z = np.array([[root*(1-1e-10), 0.], [root*(1+1e-10), 0.], [0., 0.], [10., 0.]])
        gate, _, _ = joint_gate(z, np.zeros(2), np.zeros((2, 4)), np.eye(4),
                                np.zeros(2), np.eye(2))
        np.testing.assert_array_equal(gate, [True, False, True, False])
        x = np.array([[0., 0., np.pi-.01, 0.]])
        out = update(x, np.eye(4)[None], np.zeros((1, 2)),
                     np.array([[[1., 0., 0., 0.], [0., 0., 1., 0.]]]),
                     np.zeros((1, 2)), np.eye(2)[None], np.array([[True, False, True, False]]),
                     np.array([[0., .1]]), np.array([[0., .1]]))
        self.assertLess(out['x'][0, 0, 2], 0.)
        self.assertEqual(out['x'][0, 1, 2], x[0, 2])


if __name__ == '__main__':
    unittest.main()
