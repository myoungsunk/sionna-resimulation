"""Synthetic runner provenance and immutable-output checks; no native/RF data."""
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from check_m7_replay import _synthetic_case
import m7_run as runner
from m7_spec import PLAN_COMMIT, PLAN_SHA256, expected_cells


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="m7_runner_synthetic_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.packet, self.env = _synthetic_case()
        self.online = self.root / "synthetic_online.npz"
        np.savez_compressed(self.online, **self.packet)
        index = {condition: {"10": {"R2": self.record(self.online)}}
                 for condition in ("B0", "L2_GYRO_ARW")}
        self.index = self.root / "INPUT_INDEX.json"
        self.index.write_text(json.dumps(index), encoding="utf-8")
        self.parent = self.root / "synthetic_parent.json"
        self.parent.write_text("{}", encoding="utf-8")
        self.checks = self.root / "SYNTHETIC_PREREQUISITES.json"
        self.checks.write_text(json.dumps(dict(status="PASS_M7_PRE_REPLAY_CHECKS",
                                              classification="SYNTHETIC_TEST_ONLY")), encoding="utf-8")
        self.mask = self.root / "synthetic_mask.npz"
        np.savez_compressed(self.mask, mask=np.arange(len(self.packet["t"])) % 2 == 0)
        table = [[0., 1.5, 3., 6., 10.], [.0001, .0002, .0003, .0004], [True]*4]
        source = Path(runner.__file__)
        plan = source.parent.parent / "PLAN_M7_FINAL_MODEL_STAGE1_KO.md"
        governance = source.parent.parent / "gm_theta_m6/inputs"
        self.contract = dict(plan=dict(path=str(plan), sha256=PLAN_SHA256, commit=PLAN_COMMIT),
            authorization=dict(replay="GO"), sources=[self.record(source.parent/name) for name in
                ("m7_run.py", "m7_replay.py", "m7_inputs.py", "m7_spec.py")],
            model_assets={"synthetic_test_asset": self.record(self.parent)},
            governance=[self.record(governance/name) for name in
                        ("COMMON_CONTRACT.md", "ROLE_IMPLEMENTER.md")], input_index=self.record(self.index),
            parent_contract=self.record(self.parent), prerequisite_checks=self.record(self.checks),
            parameters={"R2": dict(sigma_rad=math.radians(2.), q_table=table, qprime_table=table,
                                   sigma_b=[.005, .011, .024, .053, .120])},
            fixed_masks={"R2": dict(**self.record(self.mask), field="mask")},
            expected_cells=expected_cells())
        self.out = self.root / "output"

    @staticmethod
    def record(path):
        return dict(path=str(path), sha256=runner.sha(path))

    def run_arm(self, arm, mode="own", condition="B0"):
        return runner.run_cell(self.contract, f"{condition}/{mode}/seed10/R2/{arm}", self.out, self.env)

    def test_run_and_verified_reuse_and_corrupt_trace_rejection(self):
        receipt = self.run_arm("H3")
        self.assertEqual(receipt["status"], "PASS_EXECUTION")
        self.assertTrue(receipt["executed"])
        original = Path(receipt["trace"]["path"]).read_bytes()
        again = self.run_arm("H3")
        self.assertEqual(receipt, again)
        self.assertEqual(Path(receipt["trace"]["path"]).read_bytes(), original)
        Path(receipt["trace"]["path"]).write_bytes(original + b"corruption")
        with self.assertRaises(ValueError):
            self.run_arm("H3")

    def test_h0_fixed_is_alias_and_missing_source_rejected(self):
        with self.assertRaises(FileExistsError):
            self.run_arm("H0", "fixed")
        own = self.run_arm("H0")
        alias = self.run_arm("H0", "fixed")
        self.assertFalse(alias["executed"])
        self.assertEqual(own["trace"], alias["trace"])
        self.assertEqual(len(list(self.out.rglob("trace.npz"))), 1)
        self.assertEqual(self.run_arm("H0", "fixed"), alias)

    def test_fixed_mask_and_stress_condition(self):
        fixed = self.run_arm("H1", "fixed")
        with np.load(fixed["trace"]["path"], allow_pickle=False) as trace:
            np.testing.assert_array_equal(trace["mask"], np.arange(len(self.packet["t"])) % 2 == 0)
            self.assertEqual(trace["Reff"].shape[1:], (1, 1))
        stress = self.run_arm("H5P", condition="L2_GYRO_ARW_Q_B0_STRESS")
        with np.load(stress["trace"]["path"], allow_pickle=False) as trace:
            self.assertTrue(trace["metadata_report_only"].item())
            self.assertFalse(trace["metadata_q_matches_injection"].item())

    def test_hold_bad_prerequisites_bad_hash_and_online_extra_key_rejected(self):
        self.contract["authorization"]["replay"] = "HOLD"
        with self.assertRaises(ValueError):
            self.run_arm("H2")
        self.contract["authorization"]["replay"] = "GO"
        self.checks.write_text(json.dumps(dict(status="PASS_SYNTHETIC_IMPLEMENTATION_CHECKS")), encoding="utf-8")
        self.contract["prerequisite_checks"] = self.record(self.checks)
        with self.assertRaises(ValueError):
            self.run_arm("H2")
        self.checks.write_text(json.dumps(dict(status="PASS_M7_PRE_REPLAY_CHECKS")), encoding="utf-8")
        self.contract["prerequisite_checks"] = self.record(self.checks)
        self.online.write_bytes(b"changed input")
        with self.assertRaises(ValueError):
            self.run_arm("H2")
        np.savez_compressed(self.online, **self.packet, truth=np.zeros((len(self.packet["t"]), 3)))
        index = json.loads(self.index.read_text(encoding="utf-8"))
        index["B0"]["10"]["R2"] = self.record(self.online)
        self.index.write_text(json.dumps(index), encoding="utf-8")
        self.contract["input_index"] = self.record(self.index)
        with self.assertRaises(ValueError):
            self.run_arm("H2")
        self.assertFalse(self.out.exists())

    def test_failure_receipt_is_preserved_and_not_resumed_as_pass(self):
        with patch.object(runner, "replay", side_effect=ArithmeticError("synthetic failure")):
            with self.assertRaises(ArithmeticError):
                self.run_arm("H2")
        receipts = list(self.out.rglob("EXECUTION.json"))
        self.assertEqual(len(receipts), 1)
        failed = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(failed["status"], "FAIL_EXECUTION")
        with self.assertRaises(ValueError):
            self.run_arm("H2")
        self.assertEqual(json.loads(receipts[0].read_text(encoding="utf-8")), failed)

    def test_unknown_cell_and_cooperative_stop_rejected(self):
        with self.assertRaises(ValueError):
            self.run_arm("H2", condition="UNKNOWN")
        stop = self.root / "STOP"
        stop.touch()
        with patch.dict("os.environ", MANAGED_PROCESS_STOP_FILE=str(stop)):
            with self.assertRaises(InterruptedError):
                self.run_arm("H2")
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
