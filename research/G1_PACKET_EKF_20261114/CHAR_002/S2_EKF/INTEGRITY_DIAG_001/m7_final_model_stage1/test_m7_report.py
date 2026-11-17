"""Synthetic report aggregation tests; no experiment inputs are loaded."""
import copy
import unittest

from m7_assess import COVERAGE, assess_group, assess_seed
import m7_report as report
from m7_spec import ARMS, FIXED_SEEDS, MAIN_CONDITIONS, ROUTES, SEEDS, STRESS


def comparison(seed, condition="B0", mode="own", *, expensive=False, zero_dr=False):
    base = 1. if condition == "B0" else 2.
    points = {}
    for group in (*ROUTES, "pooled"):
        points[group] = {}
        for arm in ARMS:
            rmse = (0. if zero_dr and arm == "H0" else
                    base * (1.2 if expensive and arm == "H3" else 1.))
            points[group][arm] = dict(pose95_coverage=.96, heading95_coverage=.96,
                xy95_coverage=.96, heading_rmse_deg=rmse, xy_rmse_cm=rmse,
                mean_nees3=3., n=120 if group == "pooled" else 40)
    lower = {metric: .85 for metric in COVERAGE}
    assessed = {}
    for arm in ARMS:
        groups = {group: assess_group(points[group][arm], lower, points[group]["H2"],
                    pooled=group == "pooled", effective_blocks=10)
                  for group in (*ROUTES, "pooled")}
        assessed[arm] = assess_seed(seed, groups)
    bias = {route: {arm: {"bias_error_deg_s": dict(signed_mean=seed/100., rmse=seed/100.,
                abs_p95=seed/100., abs_max=seed/100., endpoint=-seed/100.),
                "sqrt_P_bg_deg_s": {stat: .5 for stat in report.BIAS_STATS},
                "normalized_error": {stat: seed/50. for stat in report.BIAS_STATS}}
                for arm in ARMS} for route in ROUTES}
    return dict(seed=seed, condition=condition, mode=mode, scores=dict(point=points),
                seed_assessments=assessed, bias=bias)


class ReportTests(unittest.TestCase):
    def test_counts_subsets_and_same_condition_reference(self):
        rows = [comparison(seed, "L2_GYRO_ARW", expensive=True) for seed in SEEDS]
        result = report.summarize_campaign(rows, "L2_GYRO_ARW")
        h3 = result["arms"]["H3"]
        self.assertEqual(h3["assessment"]["N_integrity"], 20)
        self.assertEqual(h3["assessment"]["N_accuracy"], 0)
        self.assertEqual(h3["assessment"]["N_joint"], 0)
        self.assertEqual(h3["cohorts"]["seed15_29"]["seed_denominator"], 15)
        self.assertEqual(h3["cohorts"]["seed10_14"]["seeds"], list(FIXED_SEEDS))
        cost = h3["cohorts"]["all_seeds"]["groups"]["R4"]["rmse_cost_vs_H2_percent"]["xy_rmse_cm"]
        self.assertAlmostEqual(cost["mean"], 20.)
        self.assertEqual(cost["seed_denominator"], 20)
        bias = h3["cohorts"]["seed15_29"]["bias_error_deg_s"]["R2"]["signed_mean"]
        self.assertAlmostEqual(bias["mean"], .22)
        self.assertEqual(bias["summary_unit"], "per_seed")

    def test_undefined_ratio_preserves_denominator(self):
        rows = [comparison(seed, zero_dr=seed == 10) for seed in SEEDS]
        result = report.summarize_campaign(rows, "B0")
        values = result["arms"]["H3"]["cohorts"]["all_seeds"]["groups"]["R5"]["rmse_improvement_percent"]["H0"]["xy_rmse_cm"]
        self.assertEqual((values["seed_denominator"], values["defined_count"], values["undefined_count"]), (20, 19, 1))
        self.assertAlmostEqual(values["mean"], 0.)

    def test_fixed_has_only_prior_used_subset_and_report_only(self):
        result = report.summarize_campaign([comparison(s, mode="fixed") for s in FIXED_SEEDS], "B0", "fixed")
        self.assertTrue(result["report_only"])
        h3 = result["arms"]["H3"]
        self.assertEqual(set(h3["cohorts"]), {"all_seeds", "seed10_14"})
        self.assertFalse(h3["assessment"]["CONDITION_PASS"])

    def test_bias_uncertainty_and_undefined_normalized_denominator(self):
        rows = [comparison(seed) for seed in SEEDS]
        rows[0]["bias"]["R2"]["H3"]["normalized_error"] = None
        result = report.summarize_campaign(rows, "B0")
        cohort = result["arms"]["H3"]["cohorts"]["all_seeds"]
        sd = cohort["sqrt_P_bg_deg_s"]["R2"]["rmse"]
        self.assertEqual(sd["mean"], .5)
        normalized = cohort["normalized_error"]["R2"]["rmse"]
        self.assertEqual((normalized["seed_denominator"], normalized["defined_count"],
                          normalized["undefined_count"]), (20, 19, 1))
        self.assertAlmostEqual(normalized["mean"], .4)
        self.assertTrue(result["arms"]["H3"]["assessment"]["CONDITION_PASS"])

    def test_missing_duplicate_identity_and_arm_rejected(self):
        original = [comparison(seed) for seed in SEEDS]
        bads = [original[:-1], original + [original[0]]]
        for field, bad in (("condition", "L2_GYRO_ARW"), ("mode", "fixed")):
            rows = copy.deepcopy(original)
            rows[0][field] = bad
            bads.append(rows)
        rows = copy.deepcopy(original)
        rows[0]["seed_assessments"].pop("H5P")
        bads.append(rows)
        for rows in bads:
            with self.assertRaises(ValueError):
                report.summarize_campaign(rows, "B0")

    def test_referenced_or_assessed_point_mismatch_rejected(self):
        for field in ("reference", "point"):
            rows = [comparison(seed) for seed in SEEDS]
            group = rows[0]["seed_assessments"]["H3"]["groups"]["R2"]
            group["reference_H2" if field == "reference" else "point"]["xy_rmse_cm"] = 4.
            with self.assertRaises(ValueError):
                report.summarize_campaign(rows, "B0")

    def test_full_campaign_grid_and_stress_exclusion(self):
        rows = []
        for condition in MAIN_CONDITIONS:
            rows += [comparison(seed, condition) for seed in SEEDS]
            rows += [comparison(seed, condition, "fixed") for seed in FIXED_SEEDS]
        # Expensive stress fails accuracy but must not alter primary M7_PASS.
        rows += [comparison(seed, STRESS, expensive=True) for seed in SEEDS]
        result = report.summarize_all(rows)
        self.assertEqual(result["comparison_groups"], 70)
        self.assertEqual(result["expected_plan_counts"], dict(cells=1470, physical_replays=1440, input_packets=120))
        self.assertTrue(result["overall_by_arm"]["H3"]["M7_PASS"])
        self.assertTrue(result["campaigns"][f"{STRESS}/own"]["report_only"])
        for bad in (rows[:-1], rows + [rows[0]]):
            with self.assertRaises(ValueError):
                report.summarize_all(bad)


if __name__ == "__main__":
    unittest.main()
