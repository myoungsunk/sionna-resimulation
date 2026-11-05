"""Hand-derived synthetic tests for the separate E1 scalar reviewer."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np

PATH = Path(__file__).resolve().parents[1] / "research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_SELECTIVE_CORRECTION_001/E1_20261105/audit/check_candidates.py"
SPEC = importlib.util.spec_from_file_location("fp_sc_candidate_checker_tests", PATH)
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def waveform(first, second=None):
    if second is None:
        second = np.zeros(len(first))
    return np.column_stack([first, second]).astype("complex128")


class CandidateCheckerTests(unittest.TestCase):
    def test_amplitude_edge_and_one_port_null(self):
        cir = waveform([0, .1, .2, .3, .7, 1, .5, .1, 0])
        result = checker.scalar_candidate_pools(cir)
        self.assertTrue(result["raw"]["valid"])
        self.assertEqual(result["raw"]["tap"], 3)
        for pool in result["pools"].values():
            self.assertEqual(pool["taps"], [2, 3, 4])
            self.assertEqual(pool["supported_taps"], [2, 3, 4])

    def test_other_port_adds_candidates_without_requiring_both_ports(self):
        cir = waveform([0, .1, .2, .3, .7, 1, .5, .1, 0], [0, .4, 1, .4, 0, 0, 0, 0, 0])
        result = checker.scalar_candidate_pools(cir)
        self.assertEqual(result["raw"]["rx"], 0)
        self.assertEqual(result["pools"]["STRONGEST_ONLY"]["taps"], [2, 3, 4])
        self.assertEqual(result["pools"]["TWO_PORT_UNION"]["taps"], [1, 2, 3, 4])

    def test_nearest_valley_prevents_edge_from_wider_prominence_basin(self):
        result = checker.scalar_candidate_pools(waveform([0, .1, .7, .5, .9, .3, 0]))
        peak = next(lobe for lobe in result["lobes"] if lobe["port"] == 0 and lobe["peak_index"] == 4)
        self.assertTrue(peak["significant"])
        self.assertFalse(peak["resolved"])
        self.assertEqual(peak["left_local_valley"], 3)
        self.assertEqual(peak["left_prominence_minimum"], 0)
        self.assertEqual(peak["generated_taps"], [])

    def test_plateau_earliest_peak_and_boundary_fallback(self):
        result = checker.scalar_candidate_pools(waveform([0, .2, .4, 1, 1, .4, .1, 0]))
        self.assertEqual(result["pools"]["TWO_PORT_UNION"]["taps"], [1, 2, 3])
        result = checker.scalar_candidate_pools(waveform([1, .4, .1, 0, .1, .4, .8, .1, 0]))
        pool = result["pools"]["TWO_PORT_UNION"]
        self.assertIn(0, pool["taps"])
        self.assertNotIn(0, pool["supported_taps"])
        self.assertEqual(pool["supported_taps"], [5, 6])

    def test_invalid_input_never_fabricates_pool_or_error_label(self):
        zero = checker.scalar_candidate_pools(np.zeros((9, 2), dtype="complex128"))
        self.assertEqual(zero["raw"]["tap"], 0)
        self.assertFalse(zero["raw"]["valid"])
        self.assertEqual(zero["pools"]["TWO_PORT_UNION"]["taps"], [])
        bad = np.zeros((9, 2), dtype="complex128")
        bad[3, 1] = np.nan
        result = checker.scalar_candidate_pools(bad)
        self.assertIsNone(result["raw"]["tap"])
        reference = checker.original_raw_fields(waveform([0, .1, .2, .3, .7, 1, .5, .1, 0]))
        label = checker.classify_availability(result, reference, "TWO_PORT_UNION")
        self.assertTrue(label["original_invalid"])
        self.assertFalse(label["wrong"])

    def test_grouping_is_strict_overlap_with_transitive_bridge(self):
        lobes = [dict(port=0, peak_index=2, left_local_valley=0, right_local_valley=4),
                 dict(port=0, peak_index=6, left_local_valley=4, right_local_valley=8)]
        self.assertEqual(checker.basin_components(lobes), [["rx0_peak2"], ["rx0_peak6"]])
        lobes.append(dict(port=1, peak_index=4, left_local_valley=3, right_local_valley=5))
        self.assertEqual(checker.basin_components(lobes), [["rx0_peak2", "rx0_peak6", "rx1_peak4"]])

    def test_episode_gaps_and_missing_runs(self):
        rows = [dict(pose_id=p, t_s=t, large_error=large, reference_usable=hit) for p, t, large, hit in
                [(1, 0., True, True), (2, .2, True, False), (3, .4, True, False),
                 (5, .6, True, True), (6, 1.2, True, False), (7, 1.4, False, False)]]
        episodes = checker.error_episodes(rows)
        self.assertEqual([episode["n_packets"] for episode in episodes], [3, 1, 1])
        self.assertEqual(episodes[0]["longest_missing_run"], 2)
        self.assertEqual(episodes[0]["recall"], 1 / 3)

    def test_static_review_rejects_future_data_and_io_dependencies(self):
        code = "from dataclasses import dataclass\n@dataclass(frozen=True)\nclass CandidateConfig:\n    value: float = 0.3\ndef generate_pools(cir, config):\n    return cir\ndef generate_candidates(cir, *, mode='x', config=None):\n    return generate_pools(cir, config)\n"
        detector = "def first_path_batch(cir, df_hz):\n    return cir\n"
        with tempfile.TemporaryDirectory() as directory:
            path, dependency = Path(directory) / "candidate.py", Path(directory) / "observation.py"
            path.write_text(code)
            dependency.write_text(detector)
            self.assertTrue(checker.review_causality(path, dependency)["passed"])
            path.write_text(code.replace("return cir", "return future[0]"))
            self.assertFalse(checker.review_causality(path, dependency)["passed"])
            path.write_text(code.replace("return cir", "return open('labels.csv').read()"))
            self.assertFalse(checker.review_causality(path, dependency)["passed"])

    def test_comparison_records_missing_or_nonfinite_numeric_evidence(self):
        result = checker.Comparisons()
        result.fields("missing", {}, {"denominator": 0.1})
        result.fields("nonfinite", {"denominator": "nan"}, {"denominator": 0.1})
        result.fields("exact", {"large_error": "True", "raw_tap": "4"}, {"large_error": True, "raw_tap": 4})
        self.assertEqual(result.mismatches, 2)
        self.assertFalse(result.record()["passed"])


if __name__ == "__main__":
    unittest.main()
