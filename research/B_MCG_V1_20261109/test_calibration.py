"""Decision-critical checks for the pre-registered calibration gate."""
import unittest
import numpy as np
from calibrate_policy import aggregate_quality, overlaps_other_pose_support, any_in_support, support_intervals


class CalibrationDecisionTests(unittest.TestCase):
    def sample(self):
        return {'full': np.array([[1., 2.], [4., 2.], [1., 1.]]),
                'skip': np.array([[3., 3.], [2., 1.], [1., 1.]]),
                'policy': np.array([[1.1, 2.02], [2., 1.], [1., 1.]]),
                'mask': np.ones(3, bool), 'beta': np.full((3, 2), .5)}

    def test_good_gain_budget_uses_only_baseline_beneficial_rows(self):
        q = aggregate_quality([self.sample()])
        self.assertTrue(q['eligible'])
        self.assertAlmostEqual(q['axes']['heading_deg2']['beneficial_lost_gain_ratio'], .05)
        self.assertAlmostEqual(q['axes']['xy_m2']['beneficial_lost_gain_ratio'], .02)

    def test_zero_beneficial_denominator_cannot_pass(self):
        c = self.sample(); c['skip'] = c['full'].copy()
        q = aggregate_quality([c])
        self.assertFalse(q['eligible'])
        self.assertIsNone(q['axes']['heading_deg2']['beneficial_lost_gain_ratio'])

    def test_empty_split_cannot_pass(self):
        q = aggregate_quality([{k: v[:0] for k, v in self.sample().items()}])
        self.assertFalse(q['eligible'])
        self.assertEqual(q['n'], 0)
        self.assertIn('NOT_ESTIMABLE_EMPTY_SPLIT', q['reasons'])

    def test_one_axis_gain_cannot_hide_other_axis_harm(self):
        c = self.sample(); c['policy'][:, 1] = c['full'][:, 1]+1.
        self.assertFalse(aggregate_quality([c])['eligible'])

    def test_pose_purge_wraps_yaw_and_checks_full_support(self):
        pose = np.array([[0., 0., np.radians(179)], [0., 0., 0.], [1., 0., np.radians(179)]])
        reference = np.array([[.1, 0., np.radians(-179)]])
        np.testing.assert_array_equal(overlaps_other_pose_support(pose, reference), [True, False, False])
        t = np.arange(31, dtype=float); lo, hi = support_intervals(t)
        flags = np.zeros(31, bool); flags[18] = True
        invalid = any_in_support(flags, lo, hi)
        self.assertTrue(invalid[8])  # future support endpoint is included
        self.assertTrue(invalid[23])  # history support endpoint is included
        self.assertFalse(invalid[7])
        self.assertFalse(invalid[24])


if __name__ == '__main__':
    unittest.main()
