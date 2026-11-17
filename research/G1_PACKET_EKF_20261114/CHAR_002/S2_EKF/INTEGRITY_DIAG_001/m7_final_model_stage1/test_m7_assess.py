"""Data-free assessment regression tests; no sensor generation or file inputs."""
import copy
import json
import math
import unittest

import numpy as np

import m7_assess as a


def group(pooled=False, **changes):
    point = dict(pose95_coverage=.95, heading95_coverage=.95, xy95_coverage=.95,
                 mean_nees3=3., heading_rmse_deg=1., xy_rmse_cm=1.)
    point.update(changes.pop("point", {}))
    lower = dict.fromkeys(a.COVERAGE, .85)
    lower.update(changes.pop("lower", {}))
    return a.assess_group(point, lower, dict.fromkeys(a.RMSE, 1.), pooled=pooled, **changes)


def seed(seed_id, integrity=True, accuracy=True, mirrors=0):
    groups = {route: group(mirror_fail=mirrors if route == "R2" else 0) for route in a.ROUTES}
    groups["pooled"] = group(True, mirror_fail=mirrors)
    if not integrity:
        groups["R2"] = group(point={"pose95_coverage":.7}, mirror_fail=mirrors)
    if not accuracy:
        groups["R4"] = group(point={"xy_rmse_cm":1.251})
    return a.assess_seed(seed_id, groups)


class AssessmentTests(unittest.TestCase):
    def test_route_boundaries_and_each_coverage(self):
        row = group(point={k:.75 for k in a.COVERAGE}, lower={k:.60 for k in a.COVERAGE})
        self.assertTrue(row["joint_pass"])
        for key in a.COVERAGE:
            self.assertFalse(group(point={key:.749999})["integrity_pass"])
            self.assertFalse(group(lower={key:.599999})["integrity_pass"])
        self.assertTrue(group(point={k:1.25 for k in a.RMSE})["accuracy_pass"])
        self.assertFalse(group(point={"heading_rmse_deg":1.250001})["accuracy_pass"])

    def test_pooled_boundaries_and_no_xy_coverage_threshold(self):
        for nees in (1.5, 6.):
            self.assertTrue(group(True, point={"pose95_coverage":.90,"heading95_coverage":.90,
                                               "xy95_coverage":0.,"mean_nees3":nees,
                                               "heading_rmse_deg":1.10,"xy_rmse_cm":1.10},
                                  lower={"pose95_coverage":.80,"heading95_coverage":.80,
                                         "xy95_coverage":0.})["joint_pass"])
        for nees in (1.49999, 6.00001):
            self.assertFalse(group(True, point={"mean_nees3":nees})["integrity_pass"])
        self.assertFalse(group(True, point={"xy_rmse_cm":1.100001})["accuracy_pass"])

    def test_insufficient_blocks_and_reference_only_do_not_pass_integrity(self):
        for kwargs in ({"effective_blocks":7},{"reference_only":True}):
            row = group(**kwargs)
            self.assertFalse(row["integrity_pass"])
            self.assertTrue(row["accuracy_pass"])

    def test_seed_conjunction_and_mirror_count_not_double_counted(self):
        row = seed(10, mirrors=2)
        self.assertFalse(row["I_seed"])
        self.assertTrue(row["A_seed"])
        self.assertEqual(row["mirror_fail"],2)
        self.assertEqual(row["mirror_routes"],1)
        groups = row["groups"]
        groups["pooled"]["mirror_fail"] = 1
        with self.assertRaises(ValueError): a.assess_seed(10, groups)

    def test_joint_counts_are_intersection_not_minimum(self):
        rows = [seed(s, integrity=s not in (10,11),accuracy=s not in (12,13)) for s in range(10,30)]
        result = a.summarize_condition(rows,"B0","H3")
        self.assertEqual((result["N_integrity"],result["N_accuracy"],result["N_joint"]),(18,18,16))
        self.assertFalse(result["CONDITION_PASS"])
        self.assertTrue(result["CONDITION_INTEGRITY_PASS"])
        self.assertEqual(result["IA_seed_lists"]["I0_A1"],[10,11])
        self.assertEqual(result["subsets"]["seed10_14"]["denominator"],5)
        self.assertEqual(result["subsets"]["seed15_29"]["denominator"],15)
        self.assertNotIn("CONDITION_PASS",result["subsets"]["seed15_29"])

    def test_eighteen_joint_pass_but_one_mirror_vetoes_condition(self):
        rows = [seed(s, integrity=s not in (10,11)) for s in range(10,30)]
        self.assertTrue(a.summarize_condition(rows,"B0","H3")["CONDITION_PASS"])
        rows[0] = seed(10,mirrors=1)
        result = a.summarize_condition(rows,"B0","H3")
        self.assertEqual(result["N_joint"],18)
        self.assertFalse(result["CONDITION_PASS"])
        self.assertEqual(result["mirror_passage_events"],1)

    def test_stress_fixed_and_overall(self):
        rows = [seed(s) for s in range(10,30)]
        b0 = a.summarize_condition(rows,"B0","H3")
        l2 = a.summarize_condition(rows,"L2_GYRO_ARW","H3")
        stress = a.summarize_condition([seed(s,False,False) for s in range(10,30)],a.STRESS,"H3")
        fixed = a.summarize_condition(rows[:5],"B0","H3","fixed")
        self.assertFalse(fixed["CONDITION_PASS"])
        self.assertTrue(stress["report_only"])
        self.assertTrue(a.overall_m7([b0,l2,stress,fixed])["M7_PASS"])
        with self.assertRaises(ValueError): a.overall_m7([b0,stress])
        with self.assertRaises(ValueError): a.overall_m7([b0,l2,l2])
        mixed = copy.deepcopy(l2); mixed["arm"] = "H4"
        with self.assertRaises(ValueError): a.overall_m7([b0,mixed])
        json.dumps([b0,l2,stress,fixed],allow_nan=False)

    def test_missing_duplicate_nonfinite_rejected(self):
        rows = [seed(s) for s in range(10,30)]
        for bad in (rows[:-1],rows[:-1]+[rows[0]]):
            with self.assertRaises(ValueError): a.summarize_condition(bad,"B0","H3")
        with self.assertRaises(ValueError): group(point={"heading_rmse_deg":float('nan')})
        with self.assertRaises(ValueError): group(lower={"pose95_coverage":float('inf')})
        groups = seed(10)["groups"]; del groups["R5"]
        with self.assertRaises(ValueError): a.assess_seed(10,groups)
        bad = copy.deepcopy(rows)
        bad[0]["groups"]["R2"]["point"]["xy_rmse_cm"] = float('nan')
        with self.assertRaises(ValueError): a.summarize_condition(bad,"B0","H3")
        bad = copy.deepcopy(rows)
        bad[0]["groups"]["R2"]["point"]["xy_rmse_cm"] = 2.
        with self.assertRaises(ValueError): a.summarize_condition(bad,"B0","H3")

    def test_zero_reference_and_exact_cp(self):
        result = a.assess_group(dict(pose95_coverage=1.,heading95_coverage=1.,xy95_coverage=1.,
                                     heading_rmse_deg=0.,xy_rmse_cm=0.),dict.fromkeys(a.COVERAGE,1.),
                                dict.fromkeys(a.RMSE,0.))
        self.assertTrue(result["accuracy_pass"])
        self.assertIsNone(result["rmse_cost_percent"]["heading_rmse_deg"])
        lo,hi = a.clopper_pearson(0,20)
        self.assertEqual(lo,0.)
        self.assertAlmostEqual(hi,1-.025**(1/20),places=13)
        lo,hi = a.clopper_pearson(20,20)
        self.assertAlmostEqual(lo,.025**(1/20),places=13)
        self.assertEqual(hi,1.)
        self.assertAlmostEqual(a.clopper_pearson(10,20)[0],.27195784956079183,places=12)
        self.assertAlmostEqual(a.clopper_pearson(10,20)[1],.7280421504392082,places=12)


class BiasTests(unittest.TestCase):
    def trace(self):
        x = np.zeros((4,4)); x[:,3] = np.radians([1.,-2.,3.,-4.])
        p = np.tile(np.eye(4),(4,1,1)); p[:,3,3] = math.radians(2.)**2
        return dict(t=np.arange(4,dtype=float),x=x,P=p)

    def test_units_statistics_previous_posterior_and_window(self):
        row = a.bias_metrics(self.trace(),{"dt":np.array([0.,1.,1.,1.])},
                             gyro_error_increment=np.radians([0.,.1,.2,.3]))
        self.assertAlmostEqual(row["bias_error_deg_s"]["signed_mean"],-.5)
        self.assertAlmostEqual(row["bias_error_deg_s"]["rmse"],math.sqrt(7.5))
        self.assertAlmostEqual(row["bias_error_deg_s"]["abs_p95"],3.85)
        self.assertEqual(row["bias_error_deg_s"]["endpoint"],-4.)
        np.testing.assert_allclose(row["time_series"]["bias_heading_correction_cumulative_deg"],[0.,-1.,1.,-2.])
        self.assertAlmostEqual(row["direct_gyro_error_window_deg"],.6)
        self.assertAlmostEqual(row["normalized_error"]["signed_mean"],-.25)
        window = a.bias_metrics(self.trace(),{"dt":np.array([0.,1.,1.,1.])},(1.,2.))
        self.assertEqual(window["samples"],2)
        self.assertAlmostEqual(window["bias_error_deg_s"]["signed_mean"],.5)
        self.assertAlmostEqual(window["bias_heading_correction_window_deg"],1.)
        json.dumps(row,allow_nan=False)

    def test_invalid_and_zero_variance(self):
        trace = self.trace(); trace["P"][0,3,3] = 0.
        row = a.bias_metrics(trace)
        self.assertIsNone(row["normalized_error"])
        self.assertEqual(row["zero_variance_samples"],1)
        json.dumps(row,allow_nan=False)
        trace["P"][0,3,3] = -1.
        with self.assertRaises(ValueError): a.bias_metrics(trace)
        with self.assertRaises(ValueError): a.bias_metrics(self.trace(),window=(9.,10.))
        with self.assertRaises(ValueError): a.bias_metrics(self.trace(),{"dt":[0.,1.,2.,1.]})


if __name__ == "__main__":
    unittest.main()
