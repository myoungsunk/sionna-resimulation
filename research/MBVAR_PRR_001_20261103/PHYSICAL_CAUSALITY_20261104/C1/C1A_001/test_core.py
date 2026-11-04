"""Synthetic mathematical checks; no archived scientific inputs or scores."""
import unittest
import numpy as np
from core import update, wrap


class CoreTests(unittest.TestCase):
    def test_correlated_reference_and_no_mutation(self):
        rng = np.random.default_rng(442)
        a = rng.normal(size=(20, 4, 4)); p = a @ a.swapaxes(-1, -2) + np.eye(4)
        b = rng.normal(size=(20, 2, 2)); r = b @ b.swapaxes(-1, -2) + np.eye(2)
        x = rng.normal(size=(20, 4)); x[:, 2] = wrap(x[:, 2])
        h = rng.normal(size=(20, 2)); H = rng.normal(size=(20, 2, 4))
        mu = rng.normal(size=(20, 2)); z = rng.normal(size=(20, 2)); los = rng.normal(size=(20, 2))
        mask = np.arange(20) % 3 != 0
        inputs = (x, p, h, H, mu, r, mask, z, los)
        copies = [v.copy() for v in inputs]
        got = update(*inputs)
        for k in range(20):
            K = p[k] @ H[k].T @ np.linalg.inv(H[k] @ p[k] @ H[k].T + r[k]) if mask[k] else np.zeros((4, 2))
            A = np.eye(4)-K @ H[k]
            expectedP = A @ p[k] @ A.T + K @ r[k] @ K.T
            np.testing.assert_allclose(got['K'][k], K, atol=1e-12, rtol=1e-12)
            np.testing.assert_allclose(got['P'][k], expectedP, atol=1e-12, rtol=1e-12)
            for j, observation in enumerate((z[k], [los[k, 0], z[k, 1]], [z[k, 0], los[k, 1]], los[k])):
                expected = x[k]+K @ (observation-h[k]-mu[k]); expected[2] = wrap(expected[2])
                np.testing.assert_allclose(got['x'][k, j], expected, atol=1e-12, rtol=1e-12)
        for original, frozen in zip(inputs, copies):
            np.testing.assert_array_equal(original, frozen)

    def test_scalar_gain_and_heading_boundary(self):
        x = np.array([[0., 0., np.pi-.01, 0.]])
        H = np.array([[[1., 0., 0., 0.], [0., 0., 1., 0.]]])
        out = update(x, np.eye(4)[None], np.zeros((1, 2)), H,
                     np.zeros((1, 2)), np.eye(2)[None], np.array([True]),
                     np.array([[2., .1]]), np.array([[0., -.1]]))
        np.testing.assert_allclose(out['K'][0], [[.5, 0.], [0., 0.], [0., .5], [0., 0.]])
        self.assertLess(out['x'][0, 0, 2], 0.)
        np.testing.assert_allclose(out['u'][0, 3]-out['u'][0, 1]-out['u'][0, 2]+out['u'][0, 0], 0., atol=1e-15)

    def test_rejection_exact_prior(self):
        x = np.array([[1., 2., np.pi, 0.]])
        p = np.eye(4)[None]
        out = update(x, p, np.zeros((1, 2)), np.ones((1, 2, 4)), np.zeros((1, 2)),
                     np.eye(2)[None], np.array([False]), np.ones((1, 2)), np.zeros((1, 2)))
        for j in range(4):
            np.testing.assert_array_equal(out['x'][:, j], x)
        np.testing.assert_array_equal(out['P'], p)


if __name__ == '__main__':
    unittest.main()
