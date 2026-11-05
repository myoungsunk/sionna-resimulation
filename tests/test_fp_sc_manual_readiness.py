"""Offline regression checks for manual FP-SC execution preparation.

No real SourceFFD, bank, RF, large EKF grid or hardware computation is run.
"""
from __future__ import annotations

from dataclasses import asdict
from itertools import product
from pathlib import Path
import json
import platform
import tempfile
import unittest

import numpy as np

from qclean_uwb.fp_sc.followup.audit import audit_directory
from qclean_uwb.fp_sc.followup.contracts import (
    ContractError, Policy, digest, sha256, write_json,
)
from qclean_uwb.fp_sc.followup.numerics import fit_residual_model
from qclean_uwb.fp_sc.followup.readiness import adopt_e1, preflight


class E101BridgeTest(unittest.TestCase):
    def fixture(self, root):
        run = root / "E1_RUN"
        review = root / "E1_REVIEW"
        run.mkdir()
        review.mkdir()
        write_json(run / "RUN_MANIFEST.json", dict(
            stage="E1-01", status="COMPLETED_PENDING_SEPARATE_RESULT_REVIEW",
            actual_waveforms=6320, actual_packet_mode_rows=12640))
        write_json(run / "SUMMARY.json", {"observed_gate": {"status": "NOT_SUPPORTED_STRATIFIED"}})
        write_json(run / "ARTIFACT_HASHES.json", {
            p.name: sha256(p) for p in run.iterdir() if p.name != "ARTIFACT_HASHES.json"})
        write_json(review / "E1_RESULT_REVIEW.json", dict(
            status="PASS_CANDIDATE_AVAILABILITY_REPRODUCTION",
            waveforms_recomputed=6320, packet_mode_rows_recomputed=12640,
            production_run_manifest_sha256=sha256(run / "RUN_MANIFEST.json"),
            production_artifact_index_sha256=sha256(run / "ARTIFACT_HASHES.json"),
            external_independent_accept=False,
            observed_gate={"status": "NOT_SUPPORTED_STRATIFIED"}))
        write_json(review / "ARTIFACT_HASHES.json", {
            p.name: sha256(p) for p in review.iterdir() if p.name != "ARTIFACT_HASHES.json"})
        return run, review

    def test_bridge_stays_hold_even_after_arithmetic_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, review = self.fixture(root)
            out = root / "receipts" / "E1_PARENT.json"
            result = adopt_e1(root, run, review, out)
            self.assertEqual(result["execution_status"], "COMPLETE")
            self.assertTrue(result["numerical_qa_pass"])
            self.assertEqual(result["scientific_gate"], "HOLD_RESULT_REVIEW")
            self.assertFalse(result["claimed_E1_02_through_E5_GO"])
            self.assertTrue(out.is_file())
            with self.assertRaises(FileExistsError):
                adopt_e1(root, run, review, out)

    def test_bridge_rejects_tampered_production(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, review = self.fixture(root)
            (run / "SUMMARY.json").write_text('{"changed":true}')
            with self.assertRaises(ContractError):
                adopt_e1(root, run, review, root / "E1_PARENT.json")

    def test_bridge_rejects_missing_separate_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run, review = self.fixture(root)
            record = json.loads((review / "E1_RESULT_REVIEW.json").read_text())
            record["status"] = "FAIL_CANDIDATE_AVAILABILITY_REPRODUCTION"
            write_json(review / "E1_RESULT_REVIEW.json", record)
            write_json(review / "ARTIFACT_HASHES.json", {
                "E1_RESULT_REVIEW.json": sha256(review / "E1_RESULT_REVIEW.json")})
            with self.assertRaises(ContractError):
                adopt_e1(root, run, review, root / "E1_PARENT.json")


class LocalPreflightTest(unittest.TestCase):
    def fixture(self, root):
        policy = Policy()
        (root / "code.py").write_text("# synthetic source only\n")
        (root / "source.py").write_text("# synthetic source only\n")
        (root / "LP_plus45_bank.npz").write_bytes(b"synthetic bank not real\n")
        (root / "LP_minus45_bank.npz").write_bytes(b"synthetic bank not real\n")
        np.savez(root / "case.npz", t=np.array([0., .2]), pose_id=np.array([0, 1], dtype=np.int64))
        (root / "evaluator.npz").write_bytes(b"synthetic evaluator not used by preflight\n")
        write_json(root / "parent.json", dict(
            study_id="FP-SC-001", stage="E3-04", execution_status="COMPLETE",
            numerical_qa_pass=True, scientific_gate="PASS", scope="SYNTHETIC_ONLY"))
        files = {
            p.name: sha256(p)
            for p in (root / "LP_plus45_bank.npz", root / "LP_minus45_bank.npz",
                      root / "case.npz", root / "evaluator.npz", root / "parent.json")
        }
        models = {}
        for route, bias, channel in product(("R2", "R4", "R5"), ("B0", "L2"), ("Full", "Native_LoS")):
            domain = dict(bias=bias, channel=channel, noise_variance=0.)
            source_route = "R2" if route != "R2" else "R4"
            model = {}
            residuals = np.array([[0., 0.], [.01, -.01], [-.01, .01], [0., 0.]])
            for extractor in ("F00", "F01", "F11"):
                model[extractor] = fit_residual_model(
                    residuals, ["unchanged"]*4, ["a", "b", "c", "d"], [source_route]*4,
                    target_route=route, split="TRAIN", extractor=extractor,
                    policy_sha=policy.sha, min_samples=2, domain=domain)
            name = f"model_{route}_{bias}_{channel}.json"
            write_json(root / name, model)
            files[name] = sha256(root / name)
            models[(route, bias, channel)] = name

        cases, matched, ids = {}, {}, []
        for route, bias, channel, seed in product(
                ("R2", "R4", "R5"), ("B0", "L2"), ("Full", "Native_LoS"), range(10)):
            cid = f"{route}_{bias}_{channel}_{seed}"
            ids.append(cid)
            metadata = dict(case_id=cid, route=route, bias=bias, channel=channel,
                            sensor_seed=seed, split="TRAIN", noise_variance=0.,
                            corpus="dynamic", environment_id="SYNTHETIC_DOMAIN")
            cases[cid] = dict(online_npz="case.npz", evaluator_npz="evaluator.npz",
                              expected_rows=2, metadata=metadata)
            matched[cid] = models[(route, bias, channel)]
        manifest = dict(
            schema="FP_SC_FOLLOWUP_STUDY_V1",
            code_files={"code.py":sha256(root / "code.py")},
            baseline_sources={"source.py":sha256(root / "source.py")},
            input_files=files,
            environment={"python":platform.python_version(), "numpy":np.__version__},
            policy=asdict(policy), policy_sha256=policy.sha,
            mapping_reviewed=True, seed_exposure_reviewed=False,
            cases=cases, stage_config={"E4-01":{"case_ids":ids}},
            prerequisite_receipts={"E3-04":"parent.json"}, models_by_case=matched)
        mp, ap = root / "manifest.json", root / "approval.json"
        write_json(mp, manifest)
        write_json(ap, dict(execute_science=True, manifest_sha256=sha256(mp),
                            code_lock_sha256=digest(manifest["code_files"]),
                            stages=["E4-01"], actor="SYNTHETIC_QA_ONLY",
                            issued_utc="2026-11-05T00:00:00Z"))
        return mp, ap

    def inspect(self, root, mp, ap):
        return preflight(root, mp, ap, ["E4-01"], ["code.py"], ("source.py",))[2]

    def test_streamed_120_grid_preflight_without_rf(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mp, ap = self.fixture(root)
            result = self.inspect(root, mp, ap)
            self.assertEqual(result["status"], "PASS_LOCAL_PREFLIGHT_NO_SCIENCE")
            self.assertEqual(result["distinct_stage_cases"], 120)
            self.assertEqual(result["waveforms_computed"], 0)
            self.assertEqual(result["streaming_stages"], ["E4-01"])

    def update_manifest(self, root, mp, ap, update):
        manifest = json.loads(mp.read_text())
        update(manifest)
        write_json(mp, manifest)
        approval = json.loads(ap.read_text())
        approval["manifest_sha256"] = sha256(mp)
        write_json(ap, approval)

    def test_grid_missing_case_blocked_before_science(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mp, ap = self.fixture(root)
            self.update_manifest(root, mp, ap,
                                 lambda x: x["stage_config"]["E4-01"]["case_ids"].pop())
            with self.assertRaises(ContractError):
                self.inspect(root, mp, ap)

    def test_unlocked_model_blocked_before_science(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mp, ap = self.fixture(root)
            def change(m):
                cid = m["stage_config"]["E4-01"]["case_ids"][0]
                del m["models_by_case"][cid]
            self.update_manifest(root, mp, ap, change)
            with self.assertRaises(ContractError):
                self.inspect(root, mp, ap)

    def test_bad_original_time_blocked_before_science(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mp, ap = self.fixture(root)
            np.savez(root / "case.npz", t=np.array([.2, .4]), pose_id=np.array([0, 1]))
            def change(m):
                m["input_files"]["case.npz"] = sha256(root / "case.npz")
            self.update_manifest(root, mp, ap, change)
            with self.assertRaises(ContractError):
                self.inspect(root, mp, ap)


class StableArtifactTest(unittest.TestCase):
    def test_gzip_json_hash_is_deterministic_and_readable(self):
        import gzip
        from qclean_uwb.fp_sc.followup.runner import _gzip_json
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            p1, p2 = root / "first.json.gz", root / "other.json.gz"
            value = {"x": [1, 2, 3], "record": {"valid": False}}
            _gzip_json(p1, value)
            _gzip_json(p2, value)
            self.assertEqual(sha256(p1), sha256(p2))
            with gzip.open(p1, "rt", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle), value)


class PartialAuditTest(unittest.TestCase):
    def test_failed_run_hashes_are_hold_not_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "RUN_MANIFEST.json", {"status": "FAILED_PRESERVED"})
            (root / "incomplete.csv").write_text("partial\n")
            write_json(root / "ARTIFACT_HASHES.json", {
                p.name: sha256(p) for p in root.iterdir()})
            result = audit_directory(root)
            self.assertEqual(result["status"], "HOLD_INCOMPLETE_RUN")
            self.assertFalse(result["numerical_science_pass"])

    def test_unindexed_file_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root / "RUN_MANIFEST.json", {"status": "COMPLETE_TECHNICAL_ONLY"})
            (root / "extra.txt").write_text("unindexed\n")
            write_json(root / "ARTIFACT_HASHES.json", {
                "RUN_MANIFEST.json": sha256(root / "RUN_MANIFEST.json")})
            with self.assertRaises(ValueError):
                audit_directory(root)


if __name__ == "__main__":
    unittest.main()
