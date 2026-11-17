"""Synthetic paired-adapter checks; no actual trajectory/scoring/replay access."""
import unittest

import numpy as np

import m7_pairs as pairs
from m7_score_run import independent_point, independent_rows
from m7_report import METRICS
from m7_spec import ARMS, CONDITIONS, ROUTES, SEEDS


class PairedTests(unittest.TestCase):
    def fixture(self, seed=10):
        times = {r: np.arange(4, dtype=float) for r in ROUTES}
        truth = {r: np.zeros((4, 3)) for r in ROUTES}
        traces = {}
        for route in ROUTES:
            traces[route] = {}
            for index, (condition, mode) in enumerate(pairs.contexts(seed)):
                for arm in ARMS:
                    x = np.zeros((4, 4))
                    x[:, 0] = .01 * index
                    x[:, 3] = .001 * index
                    policy = CONDITIONS[condition]
                    traces[route][pairs.composite(condition, mode, arm)] = dict(
                        t=times[route], x=x, P=np.repeat(np.eye(4)[None], 4, axis=0),
                        mask=np.array([True, index % 2 == 0, False, True]),
                        q_supported=np.array([False, True, True, False]), q_bin=np.array([-1, 0, 0, 1]),
                        nis=np.arange(4, dtype=float) + index,
                        metadata_condition=np.array(condition), metadata_arm=np.array(arm),
                        metadata_rref_policy=np.array("own"),
                        metadata_gate_mode=np.array("own" if arm == "H0" else mode),
                        injected_gyro_N_deg_sqrt_s=np.full(4, policy["injected_N_deg_sqrt_s"]),
                        filter_gyro_N_deg_sqrt_s=np.full(4, policy["filter_N_deg_sqrt_s"]))
        return traces, truth, times

    def call(self, seed=10, fixture=None, broken_ci=False):
        traces, truth, times = fixture or self.fixture(seed)
        self.calls = []

        def block_scorer(rows, times, contrasts, blocks):
            self.calls.append(dict(rows=rows, contrasts=contrasts, blocks=blocks))
            point = {r: {key: independent_point(row) for key, row in by_key.items()}
                     for r, by_key in rows.items()}
            point["pooled"] = {key: independent_point(np.concatenate([rows[r][key] for r in ROUTES]))
                                for key in rows["R2"]}
            groups = {}
            for group in (*ROUTES, "pooled"):
                ci = {f"{target}-{base}": {metric: [point[group][target][metric] - point[group][base][metric] - .1,
                                                    point[group][target][metric] - point[group][base][metric] + .1]
                                             for metric in METRICS} for target, base in contrasts}
                if broken_ci:
                    ci.pop(next(iter(ci)))
                groups[group] = dict(reference_only=True, paired_ci95=ci)
            return dict(point=point, blocks={str(seconds): dict(by_group=groups) for seconds in blocks})

        return pairs.score_paired_traces(seed, traces, truth, times,
                                         from_trace=independent_rows, scores_with_blocks=block_scorer)

    def test_one_call_composite_grid_shared_indices_and_direction(self):
        result = self.call(10)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]["blocks"], (5, 10, 20))
        self.assertEqual(len(self.calls[0]["rows"]["R2"]), 35)
        self.assertEqual(len(self.calls[0]["contrasts"]), 28)
        self.assertIn(("L2_GYRO_ARW|own|H3", "B0|own|H3"), self.calls[0]["contrasts"])
        self.assertEqual(result["bootstrap_policy"]["repetitions"], 1500)
        self.assertEqual(result["bootstrap_policy"]["seed"], 20261115)
        rows = pairs.paired_table([result])
        first = next(row for row in rows if row["comparison"] == "B0_to_L2" and row["arm"] == "H3" and row["group"] == "R2")
        self.assertAlmostEqual(first["xy_rmse_cm_delta"], 1.)
        self.assertAlmostEqual(first["xy_rmse_cm_ci10_lower"], .9)
        self.assertEqual(first["direction"], "target minus baseline")

    def test_later_seed_has_only_own_conditions(self):
        result = self.call(15)
        self.assertEqual(len(self.calls[0]["rows"]["R2"]), 21)
        self.assertEqual(len(result["comparisons"]), 2)
        self.assertEqual(len(self.calls[0]["contrasts"]), 14)

    def test_gate_xor_and_support_counts(self):
        result = self.call()
        gate = result["gates"]["R4"]["B0_to_L2"]["H3"]
        self.assertEqual(gate["xor_count"], 1)
        self.assertEqual(gate["baseline_only_time_s"], [1.])
        self.assertEqual(gate["common_accepted"], 2)
        exposure = result["exposure"]["R2"]["B0|own|H3"]
        self.assertEqual(exposure["q_supported_all_rate"], .5)
        self.assertAlmostEqual(exposure["q_supported_accepted_rate"], 1/3)
        self.assertEqual(exposure["q_bin_all_counts"], {"-1": 1, "0": 2, "1": 1})
        fixture = self.fixture()
        fixture[0]["R2"]["B0|own|H3"]["mask"][:] = False
        exposure = pairs.exposure_summary(fixture[0]["R2"]["B0|own|H3"])
        self.assertIsNone(exposure["q_supported_accepted_rate"])

    def test_missing_context_q_policy_and_ci_rejected(self):
        fixture = self.fixture()
        fixture[0]["R2"].pop("B0|own|H3")
        with self.assertRaises(ValueError):
            self.call(fixture=fixture)
        fixture = self.fixture()
        fixture[0]["R2"]["L2_GYRO_ARW|own|H3"]["filter_gyro_N_deg_sqrt_s"][:] = .015
        with self.assertRaises(ValueError):
            self.call(fixture=fixture)
        with self.assertRaises(ValueError):
            self.call(broken_ci=True)

    def test_complete_paired_tables_and_seed_subsets(self):
        results = [self.call(seed) for seed in SEEDS]
        rows, gates = pairs.paired_table(results), pairs.gate_table(results)
        self.assertEqual(len(rows), 1400)
        self.assertEqual(len(gates), 1050)
        distributions = pairs.delta_distributions(rows)
        subset = next(row for row in distributions if row["comparison"] == "B0_to_L2"
                      and row["subset"] == "seed15_29" and row["arm"] == "H3" and row["group"] == "R2")
        self.assertEqual(subset["seed_denominator"], 15)
        self.assertFalse(any(row["subset"] == "seed15_29" and row["comparison"] == "B0_own_to_fixed" for row in distributions))
        for seed in (True, 9, 30, 10.):
            with self.assertRaises(ValueError):
                pairs.contexts(seed)


if __name__ == "__main__":
    unittest.main()
