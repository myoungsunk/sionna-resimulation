"""Synthetic checks of A2's new-input identity and fail-closed loader guards."""
import copy
from pathlib import Path
import tempfile
import unittest

import numpy as np

from qclean_uwb.fp_sc.e0_baseline import array_sha256, sha256
from qclean_uwb.fp_sc.e0_rematerialized import (
    HISTORICAL_STATUS, _array_records, _historical_identity, _inside,
    _read_control_entry, _selected_ast, _validate_control_arrays,
)


def fixture():
    t = np.array([0.0, 0.2, 0.4], dtype="float64")
    return {"ds": np.array([0.0, 0.039, 0.041]), "gy": np.array([0.0, 0.02, -0.02]),
            "dt": np.r_[0.0, np.diff(t)], "x0": np.array([1.0, 2.0, 0.1]),
            "t": t, "pose_id": np.array([10, 20, 30], dtype="int64")}


class RematerializedControlsTests(unittest.TestCase):
    def test_grid_rejects_wrong_dt_duplicate_pose_and_nonfinite(self):
        values = fixture()
        _validate_control_arrays(values, 3)
        for change, error in ((lambda v: v["dt"].__setitem__(1, 0.3), "DT_TIME"),
                              (lambda v: v["pose_id"].__setitem__(1, 10), "DUPLICATE"),
                              (lambda v: v["gy"].__setitem__(1, np.nan), "FINITE")):
            bad = copy.deepcopy(values)
            change(bad)
            with self.assertRaisesRegex(ValueError, error):
                _validate_control_arrays(bad, 3)

    def test_historical_mismatch_is_retained_and_gyro_mismatch_blocks(self):
        values = fixture()
        expected = {k: array_sha256(values[k]) for k in ("ds", "gy", "dt", "x0")}
        expected["ds"] = "0" * 64
        status = _historical_identity(values, expected)
        self.assertEqual(status["status"], HISTORICAL_STATUS)
        self.assertFalse(status["exact_historical_array_matches"]["ds"])
        self.assertTrue(status["exact_historical_array_matches"]["gy"])
        bad = dict(expected, gy="0" * 64)
        with self.assertRaisesRegex(ValueError, "NON_DS"):
            _historical_identity(values, bad)
        expected["ds"] = array_sha256(values["ds"])
        with self.assertRaisesRegex(ValueError, "IDENTITY_CHANGED"):
            _historical_identity(values, expected)

    def test_payload_identity_and_packet_join_are_both_required(self):
        values = fixture()
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            path = repo / "controls.npz"
            np.savez_compressed(path, **values)
            entry = {"file": "controls.npz", "sha256": sha256(path), "size": path.stat().st_size,
                     "n": 3, "arrays": _array_records(values), "time_min_s": 0.0, "time_max_s": 0.4, "max_delta_t_s": 0.2}
            packet = {k: values[k].copy() for k in ("t", "pose_id")}
            loaded = _read_control_entry(repo, entry, packet)
            np.testing.assert_array_equal(loaded["ds"], values["ds"])
            packet["pose_id"][1] = 21
            with self.assertRaisesRegex(ValueError, "PACKET_JOIN"):
                _read_control_entry(repo, entry, packet)
            packet["pose_id"][1] = 20
            changed = copy.deepcopy(entry)
            changed["arrays"]["ds"]["dtype"] = "<f4"
            with self.assertRaisesRegex(ValueError, "ARRAY_IDENTITY"):
                _read_control_entry(repo, changed, packet)
            with path.open("ab") as handle:
                handle.write(b"corruption")
            with self.assertRaisesRegex(ValueError, "PAYLOAD_SHA256"):
                _read_control_entry(repo, entry, packet)

    def test_schema_and_repository_path_are_not_extensible(self):
        values = fixture()
        values["posterior"] = np.zeros((3, 4))
        with self.assertRaisesRegex(ValueError, "SCHEMA"):
            _validate_control_arrays(values, 3)
        with self.assertRaisesRegex(ValueError, "OUTSIDE"):
            _inside(Path("/tmp/repo"), "../controls.npz")
        with self.assertRaisesRegex(ValueError, "OUTSIDE"):
            _inside(Path("/tmp/repo"), "/tmp/controls.npz")

    def test_source_extraction_ignores_model_initialization(self):
        source = "raise RuntimeError('must not execute model setup')\nSCALE = 2\ndef chosen(v):\n    return SCALE*v\ndef other():\n    raise RuntimeError('not chosen')\n"
        tree = _selected_ast(source, ("chosen",), ("SCALE",))
        namespace = {}
        exec(compile(tree, "fixture", "exec"), namespace)
        self.assertEqual(namespace["chosen"](3), 6)
        self.assertNotIn("other", namespace)
        with self.assertRaisesRegex(ValueError, "AST_MISSING"):
            _selected_ast(source, ("missing",))


if __name__ == "__main__":
    unittest.main()
