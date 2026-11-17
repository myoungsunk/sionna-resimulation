"""Synthetic scoring-CLI checks; no native RF or trajectory inputs are used."""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

import m7_score_run as runner
from m7_report import summarize_all
from m7_spec import ARMS, FIXED_SEEDS, MAIN_CONDITIONS, SEEDS, STRESS, expected_cells
from test_m7_report import comparison


class ScoreRunTests(unittest.TestCase):
    def test_independent_cholesky_and_wrapping(self):
        trace = dict(x=np.array([[1., 2., 2*np.pi + .1, 0.], [0., 0., 0., 0.]]),
                     P=np.repeat(np.diag([1., 4., .01, 1.])[None], 2, axis=0))
        rows = runner.independent_rows(trace, np.zeros((2, 3)))
        self.assertAlmostEqual(rows[0, 0], np.degrees(.1)**2)
        self.assertAlmostEqual(rows[0, 1], 50000.)
        self.assertAlmostEqual(rows[0, 2], 3.)
        np.testing.assert_array_equal(rows[:, 3:], np.ones((2, 3)))
        point = runner.independent_point(rows)
        self.assertAlmostEqual(point["mean_nees3"], 1.5)
        self.assertEqual(point["n"], 2)
        trace["P"][0, 0, 0] = -1.
        with self.assertRaises(np.linalg.LinAlgError):
            runner.independent_rows(trace, np.zeros((2, 3)))

    def test_grid_and_illegal_group_keys(self):
        self.assertEqual(len(runner.expected_groups()), 70)
        self.assertEqual(runner.group_key("B0/own/seed29"), dict(condition="B0", mode="own", seed=29))
        for key in ("B0/fixed/seed15", f"{STRESS}/fixed/seed10", "B0/own/seed30"):
            with self.assertRaises(ValueError):
                runner.group_key(key)

    def test_window_diagnostic_uncertainty_and_y_budget(self):
        t = np.array([0., 80., 100., 120., 140., 160.])
        x = np.zeros((6, 4))
        x[:, 1] = .02
        trace = dict(t=t, x=x, P=np.repeat(np.diag([1., 1., .01, .01])[None], 6, axis=0),
                     b_theta=np.full(6, .02), s_infl=np.full(6, 3.), distance=np.full(6, 4.),
                     mask=np.ones(6, bool))
        packet = dict(dt=np.r_[0., np.diff(t)])
        result = runner._window_diagnostic(trace, np.zeros((6, 3)), packet, np.zeros(6), 80., 120.)
        self.assertEqual(result["series"]["time_s"], [80., 100., 120.])
        self.assertAlmostEqual(result["window_summary"]["y_rmse_cm"], 2.)
        self.assertAlmostEqual(result["window_summary"]["median_heading_sd_deg"], np.degrees(.1))
        self.assertAlmostEqual(result["window_summary"]["median_b_theta_deg"], np.degrees(.02))
        self.assertEqual(result["window_summary"]["median_s_infl"], 3.)

    def test_hold_contract_does_not_start_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            contract = Path(tmp) / "RUN_CONTRACT.json"
            contract.write_text(json.dumps(dict(authorization=dict(scoring="HOLD"))), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "GO"):
                runner._contract(contract)

    def test_alias_receipt_reuse_and_contract_hash_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            contract = root / "contract.json"
            contract.write_text("{}", encoding="utf-8")
            identity = runner.record(contract)
            input_path = root / "synthetic_input.npz"
            input_path.write_bytes(b"synthetic-only")
            inp = runner.record(input_path)
            cell = next(c for c in expected_cells() if c["condition"] == "B0" and c["mode"] == "fixed"
                        and c["seed"] == 10 and c["route"] == "R2" and c["arm"] == "H0")
            base = next(c for c in expected_cells() if c["id"] == cell["trace_alias_of"])
            directory = root.joinpath("cells", *base["id"].split("/"))
            directory.mkdir(parents=True)
            trace_path = directory / "trace.npz"
            trace_path.write_bytes(b"synthetic-trace-only")
            base_receipt = dict(status="PASS_EXECUTION", exit_code=0, cell=base, input=inp, contract=identity,
                                executed=True, trace_alias_of=None, trace=runner.record(trace_path))
            runner.write_new(directory / "EXECUTION.json", base_receipt)
            alias_dir = root.joinpath("cells", *cell["id"].split("/"))
            alias_dir.mkdir(parents=True)
            alias = dict(base_receipt, cell=cell, executed=False, trace_alias_of=base["id"],
                         alias_receipt=runner.record(directory / "EXECUTION.json"))
            path = alias_dir / "EXECUTION.json"
            runner.write_new(path, alias)
            actual, pin = runner._cell_receipt(root, cell, identity, inp)
            self.assertEqual(actual["trace"], base_receipt["trace"])
            self.assertEqual(pin, runner.record(path))
            wrong_identity = dict(identity, sha256="0" * 64)
            with self.assertRaises(ValueError):
                runner._cell_receipt(root, cell, wrong_identity, inp)
            trace_path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                runner._cell_receipt(root, cell, identity, inp)

    def test_csv_tables_complete_and_zero_reference_undefined(self):
        groups = []
        for condition in MAIN_CONDITIONS:
            groups.extend(comparison(seed, condition) for seed in SEEDS)
            groups.extend(comparison(seed, condition, "fixed") for seed in FIXED_SEEDS)
        groups.extend(comparison(seed, STRESS) for seed in SEEDS)
        # Enrich only the fields supplied by the real score adapter, not the scorer.
        for result in groups:
            result["endpoint"] = {route: {arm: dict(heading_signed_deg=.1, heading_abs_deg=.1, xy_error_cm=1.)
                                          for arm in ARMS} for route in ("R2", "R4", "R5")}
        rows = runner.comparison_table(groups)
        self.assertEqual(len(rows), 70 * 4 * 7)
        self.assertEqual(len(runner._csv_text(rows).splitlines()), len(rows) + 1)
        self.assertEqual(next(r for r in rows if r["condition"] == STRESS)["report_only"], True)
        summary = summarize_all(groups)
        counts = runner.count_table(summary)
        self.assertEqual(len(counts), (3 * 3 + 2 * 2) * 7)
        self.assertTrue(any(r["subset"] == "seed15_29" and r["denominator"] == 15 for r in counts))
        result = groups[0]
        for group in result["scores"]["point"].values():
            group["H0"]["xy_rmse_cm"] = 0.
        zero = runner.comparison_table([result])
        self.assertIsNone(next(r for r in zero if r["arm"] == "H3")["xy_rmse_cm_improvement_vs_H0_pct"])


if __name__ == "__main__":
    unittest.main()
