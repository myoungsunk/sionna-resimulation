"""Offline-only checks for manual execution; no RF, EKF or external scheduler.

The E1-01 bridge preserves the real production and separate-review evidence.
It NEVER converts a descriptive or self-checked result into a scientific PASS.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import json
import re

import numpy as np

from .contracts import (
    ContractError, DEPENDENCIES, OPTIONAL, Policy, STAGES, authorize,
    digest, prerequisite, rooted, sha256, verify_files, write_json,
)
from .study import validate_trajectory_grid


MODEL_STAGES = {"E3-04", "E4-01", "E4-02", "E4-03", "E5-01", "E5-02", "E5-03"}
STREAM_STAGES = {"E4-01", "E4-02", "E4-03", "E5-01", "E5-02", "E5-03"}
EXACT_METADATA = {
    "case_id", "route", "bias", "channel", "sensor_seed",
    "split", "noise_variance", "corpus", "environment_id",
}


def _verified_index(directory: Path) -> dict:
    registry = directory / "ARTIFACT_HASHES.json"
    data = json.loads(registry.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ContractError("EMPTY_E1_ARTIFACT_REGISTRY")
    for relative, expected in data.items():
        p = (directory / relative).resolve()
        if not p.is_relative_to(directory.resolve()) or not p.is_file():
            raise ContractError("INVALID_E1_ARTIFACT_PATH:" + relative)
        if not re.fullmatch(r"[a-f0-9]{64}", expected) or sha256(p) != expected:
            raise ContractError("E1_ARTIFACT_SHA_MISMATCH:" + relative)
    return data


def adopt_e1(root: Path, run_dir: Path, reviewer_dir: Path, output_file: Path) -> dict:
    """Create a *HOLD*, never PASS, E1 prerequisite receipt from actual evidence.

    This is a format bridge, not scientific authorization. It verifies production
    output hashes and reviewer output hashes but does not rerun the RF math.
    """
    root = root.resolve()
    run_dir, reviewer_dir, output_file = run_dir.resolve(), reviewer_dir.resolve(), output_file.resolve()
    if not run_dir.is_relative_to(root) or not reviewer_dir.is_relative_to(root) or not output_file.is_relative_to(root):
        raise ContractError("E1_BRIDGE_PATHS_MUST_BE_INSIDE_REPOSITORY")
    if output_file.exists():
        raise FileExistsError("E1_BRIDGE_REFUSES_OVERWRITE")
    run_manifest = run_dir / "RUN_MANIFEST.json"
    review_json = reviewer_dir / "E1_RESULT_REVIEW.json"
    review_index = reviewer_dir / "ARTIFACT_HASHES.json"
    production_index = run_dir / "ARTIFACT_HASHES.json"
    production = json.loads(run_manifest.read_text(encoding="utf-8"))
    review = json.loads(review_json.read_text(encoding="utf-8"))
    _verified_index(run_dir)
    _verified_index(reviewer_dir)
    if (production.get("stage") != "E1-01"
            or production.get("status") != "COMPLETED_PENDING_SEPARATE_RESULT_REVIEW"
            or production.get("actual_waveforms") != 6320
            or production.get("actual_packet_mode_rows") != 12640):
        raise ContractError("E1_PRODUCTION_NOT_FULLY_COMPLETED")
    if (review.get("status") != "PASS_CANDIDATE_AVAILABILITY_REPRODUCTION"
            or review.get("waveforms_recomputed") != 6320
            or review.get("packet_mode_rows_recomputed") != 12640
            or review.get("production_run_manifest_sha256") != sha256(run_manifest)
            or review.get("production_artifact_index_sha256") != sha256(production_index)
            or review.get("external_independent_accept") is not False):
        raise ContractError("E1_SEPARATE_REVIEW_NOT_EVIDENCE_BOUND_PASS")
    source = {
        "production_manifest": str(run_manifest.relative_to(root)),
        "production_artifact_index": str(production_index.relative_to(root)),
        "separate_review": str(review_json.relative_to(root)),
        "separate_review_index": str(review_index.relative_to(root)),
    }
    receipt = dict(
        schema="FP_SC_E1_01_LOCAL_BRIDGE_V1", study_id="FP-SC-001",
        stage="E1-01", execution_status="COMPLETE", numerical_qa_pass=True,
        scientific_gate="HOLD_RESULT_REVIEW",
        claimed_E1_02_through_E5_GO=False,
        origin="PRODUCTION_AND_SEPARATE_REVIEW_SHA_VERIFIED_NO_INDEPENDENT_SCIENCE_ACCEPT",
        source_files={key: {"path": rel, "sha256": sha256(root / rel)}
                      for key, rel in source.items()},
        observed_gate=review.get("observed_gate"),
        external_independent_accept=False,
    )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("x", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write("\n")
    return receipt


def preflight(root: Path, manifest_path: Path, approval_path: Path,
              stages: list[str], code_files: list[str], sources_required: tuple[str, ...]) -> tuple[dict, dict, dict]:
    """Verify all predictable manual-run dependencies before creating output."""
    root = root.resolve()
    manifest, approval = authorize(root, manifest_path, approval_path, stages, code_files)
    if set(manifest.get("baseline_sources", {})) != set(sources_required):
        raise ContractError("BASELINE_SOURCE_LOCK_INCOMPLETE")
    verify_files(root, manifest["baseline_sources"])
    if not {"LP_plus45_bank.npz", "LP_minus45_bank.npz"} <= set(manifest["input_files"]):
        raise ContractError("FFD_BANK_NOT_IN_INPUT_LOCK")
    if stages != [s for s in STAGES if s in set(stages)]:
        raise ContractError("STAGES_NOT_IN_TOPOLOGICAL_ORDER")
    cases, configs = manifest.get("cases", {}), manifest.get("stage_config", {})
    locked = manifest["input_files"]
    used = set()
    previous = {}
    for stage, relative in manifest.get("prerequisite_receipts", {}).items():
        if stage not in STAGES and stage != "E1-01":
            raise ContractError("UNKNOWN_PREREQUISITE_STAGE:" + str(stage))
        if relative not in locked:
            raise ContractError("PREREQUISITE_RECEIPT_NOT_LOCKED:" + stage)
        r = json.loads(rooted(root, relative).read_text(encoding="utf-8"))
        if r.get("stage") != stage or r.get("study_id") != "FP-SC-001":
            raise ContractError("PREREQUISITE_RECEIPT_IDENTITY_MISMATCH:" + stage)
        # If the native E1 receipt has been bridged, verify its original
        # immutable evidence again, not merely the editable wrapper file.
        if r.get("schema") == "FP_SC_E1_01_LOCAL_BRIDGE_V1":
            for item in r["source_files"].values():
                if item["path"] not in locked or sha256(rooted(root, item["path"])) != item["sha256"]:
                    raise ContractError("E1_BRIDGE_SOURCE_NOT_LOCKED_OR_DRIFTED")
            if r.get("scientific_gate") != "HOLD_RESULT_REVIEW" or r.get("external_independent_accept") is not False:
                raise ContractError("E1_BRIDGE_CANNOT_ASSERT_SCIENTIFIC_PASS")
        previous[stage] = r
    ordered = set()
    for stage in stages:
        if stage not in configs or not isinstance(configs[stage], dict):
            raise ContractError("MISSING_STAGE_CONFIGURATION:" + stage)
        cfg = configs[stage]
        ids = cfg.get("case_ids")
        if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
            raise ContractError("EMPTY_OR_DUPLICATE_STAGE_CASES:" + stage)
        for parent in DEPENDENCIES[stage]:
            if parent not in previous and parent not in ordered:
                raise ContractError("MISSING_PREREQUISITE_BEFORE_RUN:" + parent)
        if all(parent in previous for parent in DEPENDENCIES[stage]):
            prerequisite(stage, previous, approval)
        stage_meta = []
        for cid in ids:
            if cid not in cases or not isinstance(cases[cid], dict):
                raise ContractError("UNDECLARED_STAGE_CASE:" + str(cid))
            s = cases[cid]
            if set(s) != {"online_npz", "evaluator_npz", "expected_rows", "metadata"}:
                raise ContractError("BAD_CASE_SPEC:" + cid)
            if set(s["metadata"]) != EXACT_METADATA or s["metadata"]["case_id"] != cid:
                raise ContractError("BAD_CASE_METADATA:" + cid)
            if type(s["expected_rows"]) is not int or s["expected_rows"] <= 0:
                raise ContractError("BAD_CASE_ROW_COUNT:" + cid)
            for name in ("online_npz", "evaluator_npz"):
                if s[name] not in locked:
                    raise ContractError("UNLOCKED_CASE_PAYLOAD:" + cid + ":" + name)
            if stage in STREAM_STAGES:
                # Read only the small identity arrays: no CFR, FFD or EKF math.
                # Catch malformed, offset or truncated timelines before a
                # 120/240-trajectory run writes its first output.
                online = rooted(root, s["online_npz"])
                try:
                    with np.load(online, allow_pickle=False) as source:
                        t = source["t"]
                        ids_array = source["pose_id"]
                        if (t.shape != (s["expected_rows"],)
                                or ids_array.shape != t.shape
                                or ids_array.dtype.kind not in "iu"
                                or not np.isfinite(t).all()
                                or abs(float(t[0])) > 1e-12
                                or np.any(np.diff(t) <= 0)
                                or np.any(np.diff(ids_array) <= 0)):
                            raise ContractError("BAD_STREAMED_TIMELINE:" + cid)
                except (OSError, KeyError, ValueError) as exc:
                    raise ContractError("BAD_STREAMED_NPZ_HEADER:" + cid) from exc
            stage_meta.append(SimpleNamespace(**s["metadata"], t=np.array([0.0])))
            used.add(cid)
            if stage in MODEL_STAGES:
                source = manifest.get("outer_fold_models_by_case" if stage == "E4-03" else "models_by_case", {})
                generated = "E3-03" in ordered and cid in configs["E3-03"]["case_ids"] and stage != "E4-03"
                if not generated and source.get(cid) not in locked:
                    raise ContractError("MODEL_NOT_PREPARED_OR_LOCKED:" + stage + ":" + cid)
                if not generated:
                    try:
                        model_set = json.loads(rooted(root, source[cid]).read_text(encoding="utf-8"))
                    except (OSError, ValueError) as exc:
                        raise ContractError("MODEL_JSON_INVALID:" + stage + ":" + cid) from exc
                    active_sha = (Policy(**manifest["outer_fold_policies"][s["metadata"]["route"]]["policy"]).sha
                                  if stage == "E4-03" else Policy(**manifest["policy"]).sha)
                    if not isinstance(model_set, dict) or set(model_set) != {"F00", "F01", "F11"}:
                        raise ContractError("MODEL_SET_INCOMPLETE:" + stage + ":" + cid)
                    for extractor, model in model_set.items():
                        body = dict(model)
                        model_sha = body.pop("sha256", None)
                        domain = {key: s["metadata"][key] for key in ("bias", "channel", "noise_variance")}
                        if (digest(body) != model_sha
                                or model.get("target_route") != s["metadata"]["route"]
                                or model.get("extractor") != extractor
                                or model.get("policy_sha") != active_sha
                                or model.get("measurement_domain") != domain):
                            raise ContractError("MODEL_SHA_OR_DOMAIN_MISMATCH:" + stage + ":" + cid + ":" + extractor)
        validate_trajectory_grid(stage_meta, stage)
        if stage == "E3-03":
            training = cfg.get("calibration_case_ids")
            if not isinstance(training, list) or not training or len(training) != len(set(training)):
                raise ContractError("INVALID_CALIBRATION_CASE_LIST")
            for cid in training:
                if cid not in cases:
                    raise ContractError("UNDECLARED_CALIBRATION_CASE:" + cid)
                s = cases[cid]
                if s["metadata"]["split"] not in {"TRAIN", "CAL"}:
                    raise ContractError("CALIBRATION_SPLIT_INVALID:" + cid)
                for name in ("online_npz", "evaluator_npz"):
                    if s[name] not in locked:
                        raise ContractError("UNLOCKED_CALIBRATION_PAYLOAD:" + cid)
        if stage in {"E5-01", "E5-02"} and not cfg.get("hardware_id"):
            raise ContractError("E5_HARDWARE_ID_MISSING")
        if stage == "E4-03":
            for c in stage_meta:
                fold = manifest.get("outer_fold_policies", {}).get(c.route)
                if (not isinstance(fold, dict) or c.route in fold.get("training_routes", [])
                        or not fold.get("full_pipeline_holdout_reviewed")
                        or fold.get("policy_sha256") != Policy(**fold["policy"]).sha):
                    raise ContractError("OUTER_FOLD_POLICY_NOT_READY:" + c.route)
        if stage == "E5-03":
            path = manifest.get("external_environment_contract")
            if path not in locked:
                raise ContractError("EXTERNAL_ENVIRONMENT_CONTRACT_NOT_LOCKED")
            domain = json.loads(rooted(root, path).read_text(encoding="utf-8"))
            if (not domain.get("new_data_reviewed") or
                    set(domain["evaluation_domain_ids"]) & set(domain["development_domain_ids"]) or
                    any(c.corpus != "external" or c.environment_id not in domain["evaluation_domain_ids"]
                        for c in stage_meta)):
                raise ContractError("EXTERNAL_DOMAIN_CONTRACT_INVALID")
        ordered.add(stage)
    return manifest, approval, {
        "status": "PASS_LOCAL_PREFLIGHT_NO_SCIENCE",
        "stages": list(stages), "distinct_stage_cases": len(used),
        "streaming_stages": [s for s in stages if s in STREAM_STAGES],
        "inputs_sha_verified": True,
        "source_sha_verified": True,
        "prerequisite_science_pass_inferred": False,
        "waveforms_computed": 0,
        "external_independent_accept": False,
    }
