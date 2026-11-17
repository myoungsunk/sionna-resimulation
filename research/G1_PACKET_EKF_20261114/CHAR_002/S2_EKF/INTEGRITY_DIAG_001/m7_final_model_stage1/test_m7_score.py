"""Synthetic adapter checks only: no RF, trajectory, donor or native replay."""
import unittest

import numpy as np

import m7_score as scoring
from m7_spec import ARMS, CONDITIONS, ROUTES, STRESS


class ScoreAdapterTests(unittest.TestCase):
    def fixture(self, condition="B0", mode="own"):
        times = {route: np.arange(4, dtype=float) for route in ROUTES}
        truth = {route: np.zeros((4, 3)) for route in ROUTES}
        traces = {}
        for route in ROUTES:
            traces[route] = {}
            for number, arm in enumerate(ARMS):
                traces[route][arm] = dict(
                    t=times[route].copy(), x=np.zeros((4, 4)),
                    P=np.repeat(np.eye(4)[None], 4, axis=0),
                    mask=np.arange(4) % 2 == number % 2,
                    metadata_condition=np.array(condition), metadata_arm=np.array(arm),
                    metadata_gate_mode=np.array("own" if arm == "H0" else mode),
                    metadata_rref_policy=np.array("own"),
                    injected_gyro_N_deg_sqrt_s=np.full(4, CONDITIONS[condition]["injected_N_deg_sqrt_s"]),
                    filter_gyro_N_deg_sqrt_s=np.full(4, CONDITIONS[condition]["filter_N_deg_sqrt_s"]),
                    passage_count=scoring.PASSES[route])
        return traces, truth, times

    def call(self, condition="B0", mode="own", *, fixture=None, mirror=False, broken_blocks=False):
        traces, truth, times = fixture or self.fixture(condition, mode)
        self.captured = {}

        def from_trace(trace, reference):
            self.captured.setdefault("masks", []).append(tuple(trace["mask"]))
            return np.zeros((len(reference), 6))

        def branches(trace, reference, t):
            passages = [{"MIRROR_FAIL": bool(mirror and i == 0)}
                        for i in range(trace["passage_count"])]
            return dict(passages=passages, mirror_fail_count=sum(p["MIRROR_FAIL"] for p in passages))

        def blocks(rows, t, pairs, *, blocks):
            self.captured.update(rows=rows, pairs=pairs, block_lengths=blocks)
            point, by_group = {}, {}
            for group in (*ROUTES, "pooled"):
                point[group], ci = {}, {}
                for arm in ARMS:
                    # Distinct H0/H1 references must not replace the same-condition H2.
                    rmse = {"H0": 20., "H1": 10., "H2": 1., "H3": 2.}.get(arm, 1.)
                    point[group][arm] = dict(pose95_coverage=.96, heading95_coverage=.96,
                        xy95_coverage=.96, heading_rmse_deg=rmse, xy_rmse_cm=rmse, mean_nees3=3.)
                    point[group][arm]["n"] = 12 if group == "pooled" else 4
                    ci[arm] = {metric: [.85, .99] for metric in scoring.COVERAGE}
                by_group[group] = dict(absolute_ci95=ci, reference_only=False)
            full = {route: 10 for route in ROUTES}
            if broken_blocks:
                full.pop("R5")
            return dict(point=point, blocks={"10": dict(full_blocks=full, by_group=by_group)})

        return scoring.score_comparison(10, condition, mode, traces, truth, times,
            from_trace=from_trace, scores_with_blocks=blocks, branch_metrics=branches)

    def test_complete_grid_different_masks_and_accuracy_reference(self):
        result = self.call(condition="L2_GYRO_ARW")
        self.assertEqual(len(set(self.captured["masks"])), 2)
        self.assertEqual(self.captured["block_lengths"], (5, 10, 20))
        self.assertEqual(set(result["seed_assessments"]), set(ARMS))
        h3 = result["seed_assessments"]["H3"]
        self.assertTrue(h3["I_seed"])
        self.assertFalse(h3["A_seed"])
        self.assertFalse(h3["J_seed"])
        for group in (*ROUTES, "pooled"):
            self.assertEqual(h3["groups"][group]["reference_H2"]["xy_rmse_cm"], 1.)
        self.assertIn(("H5P", "H5"), self.captured["pairs"])
        self.assertIn(("H3", "H0"), self.captured["pairs"])
        self.assertEqual(len(self.captured["pairs"]), len(set(self.captured["pairs"])))
        self.assertEqual(result["bias"]["R2"]["H3"]["true_bg_deg_s"], 0.)

    def test_fixed_h0_own_metadata_alias_accepted(self):
        result = self.call(mode="fixed")
        self.assertEqual(result["mode"], "fixed")

    def test_stress_is_report_only(self):
        result = self.call(condition=STRESS)
        self.assertEqual(result["decision_role"], CONDITIONS[STRESS]["decision_role"])
        self.assertIn("Failure", result["H5_claim_limit"])

    def test_missing_route_or_arm_rejected(self):
        for target in ("route", "arm"):
            fixture = self.fixture()
            if target == "route":
                fixture[0].pop("R5")
            else:
                fixture[0]["R2"].pop("H5P")
            with self.subTest(target=target), self.assertRaises(ValueError):
                self.call(fixture=fixture)

    def test_relabelled_arm_condition_or_q_rejected(self):
        for field, bad in (("metadata_arm", np.array("H4")),
                           ("metadata_condition", np.array("L2_GYRO_ARW")),
                           ("filter_gyro_N_deg_sqrt_s", np.full(4, .06)),
                           ("injected_gyro_N_deg_sqrt_s", np.full(4, .06)),
                           ("metadata_rref_policy", np.array("scheduled")),
                           ("metadata_gate_mode", np.array("fixed"))):
            fixture = self.fixture()
            fixture[0]["R2"]["H3"][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.call(fixture=fixture)

    def test_bad_passages_and_bootstrap_route_loss_rejected(self):
        fixture = self.fixture()
        fixture[0]["R2"]["H3"]["passage_count"] = 1
        with self.assertRaises(ValueError):
            self.call(fixture=fixture)
        with self.assertRaises(ValueError):
            self.call(broken_blocks=True)

    def test_mirror_events_pooled_once(self):
        result = self.call(mirror=True)
        assessed = result["seed_assessments"]["H3"]
        self.assertEqual(assessed["mirror_fail"], 3)
        self.assertEqual(assessed["groups"]["pooled"]["mirror_fail"], 3)
        self.assertFalse(assessed["I_seed"])


if __name__ == "__main__":
    unittest.main()
