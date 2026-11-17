"""Pure synthetic passage/nominal-information checks; no actual run files."""
import unittest

import numpy as np

import m7_passages as passages
from m7_spec import ARMS


class PassageTests(unittest.TestCase):
    def trace(self, arm="H3"):
        t = np.arange(0., 62., 2.)
        n = len(t)
        x = np.zeros((n, 4))
        x[:, 0], x[:, 1], x[:, 2], x[:, 3] = t/10., .2, .03, np.radians(.05)
        p = np.repeat(np.diag([.1, .2, .01, .001])[None], n, axis=0)
        h = np.repeat(np.array([[1., 2., 3., 0.], [-1., 4., -2., 0.]])[None], n, axis=0)
        r = np.repeat(np.array([[2., .6], [.6, 3.]])[None], n, axis=0)
        if arm == "H1":
            h, r = h[:, :1], r[:, :1, :1]
        mask = np.arange(n) % 2 == 0
        if arm == "H0":
            mask[:] = False
        return dict(t=t, pose_id=np.arange(n), metadata_arm=np.array(arm), mask=mask,
                    x=x, P=p, prior=x-.01, Pprior=p*2., H=h, Reff=r,
                    b_g=x[:, 3], b_g_prior=x[:, 3]-.001,
                    b_theta=np.full(n, .02), b_theta_prior=np.full(n, .01),
                    q_s=np.full(n, .005), distance=np.linspace(1., 5., n), s_infl=np.full(n, 4.))

    @staticmethod
    def definitions():
        return [dict(time_s=time, MIRROR_FAIL=False, PRE_PASS_OVERCONFIDENT=None)
                for time in (15., 35., 55.)]

    def test_correlated_range_first_decomposition_matches_full_inverse(self):
        trace = self.trace()
        use = (trace["t"] >= 10.) & (trace["t"] <= 30.)
        result = passages.local_information(trace, use)
        accepted = int(np.sum(use & trace["mask"]))
        expected = accepted * trace["H"][0].T @ np.linalg.solve(trace["Reff"][0], trace["H"][0])
        np.testing.assert_allclose(result["total"]["matrix"], expected)
        np.testing.assert_allclose(np.array(result["range_first"]["matrix"]) +
                                   np.array(result["conditional_polarization"]["matrix"]), expected)
        self.assertAlmostEqual(result["total"]["J_ypsi"], expected[1, 2])
        self.assertEqual(result["accepted"], accepted)
        self.assertIn("not marginalized", result["claim_limit"])

    def test_range_only_and_dr_are_explicit(self):
        trace = self.trace("H1")
        result = passages.local_information(trace, np.ones(len(trace["t"]), bool))
        self.assertEqual(result["channel_count"], 1)
        self.assertIsNone(result["conditional_polarization"]["J_yy"])
        np.testing.assert_allclose(result["total"]["matrix"], result["range_first"]["matrix"])
        trace = self.trace("H0")
        result = passages.local_information(trace, np.ones(len(trace["t"]), bool))
        self.assertEqual(result["status"], "NOT_APPLICABLE_DR")
        self.assertIsNone(result["total"]["J_psipsi"])
        trace["mask"][0] = True
        with self.assertRaises(ValueError):
            passages.local_information(trace, np.ones(len(trace["t"]), bool))

    def test_nearest_ties_entry_states_and_clipped_window(self):
        trace = self.trace()
        result = passages.passage_diagnostics(trace, self.definitions())
        self.assertEqual(result[0]["snapshots"]["start"]["time_s"], 4.)
        self.assertEqual(result[0]["snapshots"]["passage"]["time_s"], 14.)
        self.assertEqual(result[0]["observed_window_s"], [6., 24.])
        self.assertEqual(result[2]["snapshots"]["end"]["time_s"], 60.)
        self.assertEqual(result[2]["requested_window_s"], [45., 65.])
        self.assertAlmostEqual(result[0]["snapshots"]["start"]["b_g_deg_s"], .05)
        self.assertEqual(result[0]["observation_summaries"]["q_s"]["median"], .005)
        np.testing.assert_array_equal(result[0]["snapshots"]["start"]["posterior_nav_P_diagonal"],
                                      [.1, .2, .01, .001])

    def test_invalid_passage_grid_covariance_and_shape_rejected(self):
        for values in (self.definitions()[:2], [dict(time_s=x) for x in (15., 15., 55.)]):
            with self.assertRaises(ValueError):
                passages.passage_diagnostics(self.trace(), values)
        trace = self.trace()
        trace["Reff"][0, 0, 0] = -1.
        with self.assertRaises(np.linalg.LinAlgError):
            passages.local_information(trace, np.ones(len(trace["t"]), bool))
        trace = self.trace("H1")
        trace["H"] = np.repeat(trace["H"], 2, axis=1)
        with self.assertRaises(ValueError):
            passages.local_information(trace, np.ones(len(trace["t"]), bool))

    def test_csv_complete_three_passes_per_arm(self):
        result = dict(condition="B0", mode="own", seed=10,
                      arms={arm: passages.passage_diagnostics(self.trace(arm), self.definitions()) for arm in ARMS})
        rows = passages.passage_table([result])
        self.assertEqual(len(rows), 21)
        self.assertEqual(next(row for row in rows if row["arm"] == "H0")["nominal_total_J_yy"], None)
        self.assertIn("start_P_y_prior", rows[0])
        self.assertIn("start_psi_rad", rows[0])


if __name__ == "__main__":
    unittest.main()
