"""Hand-derived synthetic checks; no RF corpus or scientific metric execution."""
from dataclasses import FrozenInstanceError, replace
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from qclean_uwb.fp_sc.candidates import CandidateConfig, _groups, generate_candidates, generate_pools


def cir(first, second=None):
    result = np.zeros((1028, 2), dtype="complex128")
    result[:len(first), 0] = first
    if second is not None:
        result[:len(second), 1] = second
    return result


RUNNER_SPEC = importlib.util.spec_from_file_location("fp_sc_e1_runner_test",
    Path(__file__).resolve().parents[1] / "scripts/fp_sc_e1.py")
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)


class CandidateTests(unittest.TestCase):
    def test_amplitude_edge_and_one_port_null(self):
        pools = generate_pools(cir([0, .1, .2, .3, .7, 1, .5, .1, 0]))
        for pool in pools.values():
            self.assertEqual(pool["raw"]["tap"], 3)
            self.assertTrue(pool["raw"]["valid"])
            self.assertEqual(pool["candidate_taps"], [2, 3, 4])
            self.assertEqual(pool["supported_taps"], [2, 3, 4])
            self.assertTrue(all(candidate["signed_s"] == 1 for candidate in pool["candidates"]))
        # A 30%-power threshold would cross at .7, which is deliberately different.
        self.assertNotEqual(pools["TWO_PORT_UNION"]["raw"]["tap"], 4)

    def test_other_rx_adds_lobe_with_same_global_normalization(self):
        waveform = cir([0, .1, .2, .3, .7, 1, .5, .1, 0], [0, .4, 1, .4, 0, 0, 0, 0, 0])
        pools = generate_pools(waveform)
        self.assertEqual(pools["STRONGEST_ONLY"]["raw"]["rx"], 0)
        self.assertEqual(pools["STRONGEST_ONLY"]["candidate_taps"], [2, 3, 4])
        self.assertEqual(pools["TWO_PORT_UNION"]["candidate_taps"], [1, 2, 3, 4])
        self.assertEqual(pools["STRONGEST_ONLY"]["numeric_amplitude_floor"],
                         pools["TWO_PORT_UNION"]["numeric_amplitude_floor"])
        weak = cir([0, .1, .2, .3, .7, 1, .5, .1, 0])
        weak[20:23, 1] = [.01, .05, .01]
        result = generate_candidates(weak)
        self.assertNotIn(21, result["supported_taps"])
        lobe = next(l for l in result["lobes"] if l["rx"] == 1)
        self.assertEqual(lobe["reason"], "BELOW_PROMINENCE")

    def test_local_valley_is_distinct_from_prominence_basin(self):
        result = generate_candidates(cir([0, .1, .7, .5, .9, .3, 0]))
        lobe = next(l for l in result["lobes"] if l["peak_tap"] == 4)
        self.assertEqual(lobe["left_prominence_minimum"], 0)
        self.assertEqual(lobe["left_local_valley"], 3)
        self.assertEqual(lobe["reason"], "UNRESOLVED_LOCAL_LEADING_EDGE")
        self.assertEqual(lobe["candidate_taps"], [])

    def test_plateau_earliest_peak_and_no_whole_window_expansion(self):
        result = generate_candidates(cir([0, .2, .4, 1, 1, .4, .1, 0]))
        self.assertEqual(result["candidate_taps"], [1, 2, 3])
        lobe = result["lobes"][0]
        self.assertEqual((lobe["peak_tap"], lobe["plateau_end"]), (3, 4))
        self.assertEqual(len(lobe["candidate_taps"]), 3)

    def test_boundary_peak_logged_but_only_fallback(self):
        waveform = cir([1, .4, .1, 0, .1, .4, .8, .1, 0])
        waveform[-2:, 1] = .9
        result = generate_candidates(waveform)
        self.assertIn(0, result["candidate_taps"])
        self.assertNotIn(0, result["supported_taps"])
        boundary = [l for l in result["lobes"] if l["boundary"]]
        self.assertEqual(len(boundary), 2)
        self.assertTrue(all(l["reason"] == "BOUNDARY_PEAK_NOT_CANDIDATE" for l in boundary))
        self.assertTrue(all(l["prominence"] == 0 and not l["candidate_taps"] for l in boundary))
        self.assertFalse(any(l["rx"] == 1 and not l["boundary"] for l in result["lobes"]))

    def test_zero_signal_metadata_and_empty_pools(self):
        for pool in generate_pools(cir([])).values():
            self.assertEqual(pool["raw"]["tap"], 0)
            self.assertEqual(pool["raw"]["rx"], 0)
            self.assertEqual(pool["raw"]["range_m"], 0)
            self.assertIsNone(pool["raw"]["signed_s"])
            self.assertFalse(pool["raw"]["valid"])
            self.assertEqual(pool["candidate_taps"], [])
            self.assertEqual(pool["lobes"], [])

    def test_nonfinite_no_arbitrary_argmax_and_no_labels(self):
        waveform = cir([0, .2, .5, 1, .5, 0])
        waveform[0, 1] = np.nan
        pool = generate_candidates(waveform)
        self.assertIsNone(pool["raw"]["tap"])
        self.assertIsNone(pool["raw"]["rx"])
        self.assertFalse(pool["usable"])
        self.assertEqual(pool["candidate_taps"], [])
        labels = runner.classify(pool, {"tap": 3, "valid": True})
        self.assertTrue(labels["original_invalid"])
        self.assertFalse(labels["wrong"])
        self.assertFalse(labels["large_error"])
        self.assertTrue(labels["raw_preserved"])

    def test_prominence_threshold_is_inclusive(self):
        waveform = cir([0, .3, 1, .3, 0])
        waveform[20:23, 1] = [0, .06, 0]
        result = generate_candidates(waveform)
        lobe = next(l for l in result["lobes"] if l["rx"] == 1)
        self.assertTrue(lobe["eligible"])
        self.assertIn(21, result["supported_taps"])

    def test_noise_floor_can_remove_candidate_support(self):
        result = generate_candidates(cir([0, .1, .2, .3, .7, 1, .5, .1, 0]),
            config=replace(CandidateConfig(), noise_var_per_bin=.01))
        self.assertTrue(result["raw"]["valid"])
        self.assertGreater(result["noise_amplitude_floor"], .9)
        self.assertEqual(result["candidate_taps"], [3])
        self.assertEqual(result["supported_taps"], [])

    def test_overflow_preserves_every_tap_including_fallback(self):
        waveform = cir([2, .1, 0])
        for offset in range(20, 320, 10):
            waveform[offset:offset + 6, 0] = [0, .2, .4, 1, .4, 0]
        result = generate_candidates(waveform)
        self.assertEqual(len(result["candidate_taps"]), 91)
        self.assertEqual(len(result["supported_taps"]), 90)
        self.assertTrue(result["overflow"])
        self.assertFalse(result["usable"])
        self.assertIn(0, result["candidate_taps"])
        label = runner.classify(result, {"tap": 22, "valid": True})
        self.assertTrue(label["reference_in_supported"])
        self.assertFalse(label["reference_usable"])

    def test_basin_groups_require_positive_overlap_and_are_transitive(self):
        lobes = [dict(lobe_id="a", rx=0, peak_tap=2, left_local_valley=0, right_local_valley=4, eligible=True),
                 dict(lobe_id="b", rx=0, peak_tap=6, left_local_valley=4, right_local_valley=8, eligible=True)]
        self.assertEqual(_groups(lobes), {"a": 0, "b": 1})
        bridge = dict(lobe_id="c", rx=1, peak_tap=4, left_local_valley=3, right_local_valley=5, eligible=True)
        self.assertEqual(_groups([*lobes, bridge]), {"a": 0, "b": 0, "c": 0})
        self.assertEqual(_groups([*lobes, {**bridge, "eligible": False}]), {"a": 0, "b": 1})

    def test_pure_causal_api_and_input_immutability(self):
        waveform = cir([0, .1, .2, .3, .7, 1, .5, .1, 0])
        original = waveform.copy()
        pool = generate_candidates(waveform)
        runner.classify(pool, {"tap": 3, "valid": True})
        runner.classify(pool, {"tap": 900, "valid": False})
        self.assertEqual(pool["pool_hash"], generate_candidates(waveform)["pool_hash"])
        np.testing.assert_array_equal(waveform, original)
        with self.assertRaises(TypeError):
            generate_candidates(waveform, prior=np.zeros(4))
        with self.assertRaises(TypeError):
            generate_candidates(waveform, reference_tap=3)
        with self.assertRaises(FrozenInstanceError):
            CandidateConfig().eta_prominence = .03

    def test_malformed_inputs_and_config_fail_closed(self):
        for bad in (np.zeros((1028, 2)), np.zeros((12, 2), complex), np.zeros((1028, 3), complex)):
            with self.assertRaises(ValueError):
                generate_pools(bad)
        with self.assertRaises(ValueError):
            generate_candidates(cir([]), mode="UNKNOWN")
        for config in (replace(CandidateConfig(), eta_prominence=np.nan),
                       replace(CandidateConfig(), neighbor_radius_taps=5),
                       replace(CandidateConfig(), noise_var_per_bin=-1)):
            with self.assertRaises(ValueError):
                generate_pools(cir([]), config)


class RunnerTests(unittest.TestCase):
    def test_episode_breaks_on_pose_gaps_time_gaps_and_normal(self):
        rows = [dict(route="R4", channel="Full", mode="TWO_PORT_UNION", pose_id=p, t_s=t,
                     large_error=large, reference_usable=hit) for p, t, large, hit in
            [(1, 0., True, True), (2, .2, True, False), (3, .4, True, False),
             (5, .6, True, True), (6, 1.2, True, False), (7, 1.4, False, False)]]
        episodes = runner.error_episodes(rows)
        self.assertEqual([e["n_packets"] for e in episodes], [3, 1, 1])
        self.assertEqual(episodes[0]["longest_missing_run"], 2)
        self.assertEqual(episodes[0]["recall"], 1 / 3)

    def test_missing_or_rejected_guard_precedes_all_outputs_and_waveform_math(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "no_output"
            with patch.object(runner, "verify_e1_lock", side_effect=ValueError("NOT_FROZEN")):
                with patch.object(runner.observation, "cir_batch") as fft:
                    with self.assertRaisesRegex(ValueError, "NOT_FROZEN"):
                        runner.execute(Path(temp) / "lock.json", Path(temp) / "approval.json", output)
                    fft.assert_not_called()
            self.assertFalse(output.exists())

    def test_empty_denominator_is_not_perfect_recall(self):
        result = runner.counts([])
        self.assertEqual(result["large_error_status"], "NOT_TESTED")
        self.assertIsNone(result["large_error_reference_usable_recall"])


if __name__ == "__main__":
    unittest.main()
