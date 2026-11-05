"""DAG runner. Default operation is plan-only. No automatic RT or CI dispatch."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import argparse
import datetime as dt
import gzip
import json
import sys
import traceback
import gc
from types import SimpleNamespace
import numpy as np
from .contracts import (BASE_SHA, DEPENDENCIES, OPTIONAL, STAGES, ContractError, Policy,
                        authorize, digest, environment, jsonable, prerequisite, rooted,
                        sha256, verify_files, write_json)
from .data import export_archive, load_case
from .engine import OriginalAdapter
from .evaluation import paired_seed_bootstrap
from .study import (calibration_records, e1_detection, e2_confidence, e2_history, e2_select,
                    e3_observations, e3_one_step, e4_closed_loop, e5_runtime, fit_models,
                    labelled, select_policy_from_calibration, stress, validate_trajectory_grid)
from .selection import policy_grid
from .evaluation import selection_summary
from .readiness import STREAM_STAGES, adopt_e1, preflight

SOURCES_REQUIRED = (
    "src/qclean_uwb/fp_sc/candidates.py", "src/qclean_uwb/fp_sc/e0_baseline.py",
    "src/qclean_uwb/drivesim/observation.py", "src/qclean_uwb/drivesim/pattern_apply.py",
    "src/qclean_uwb/drivesim/hs_lut.py", "src/qclean_uwb/scenarios/corridor.py",
    "src/qclean_uwb/drivesim/sensor_v2.py", "src/qclean_uwb/drivesim/sensors.py",
    "research/FFD_P0P3_20261016/source_model.py", "research/FFD_P0P3_20261016/p0_initial.py",
    "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py", "research/EKF4_RANGE_S_STAGED_20261014/core.py",
    "research/MBVAR_PRR_001_20261103/S1/online.py",
    "research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104/FP_PRIOR_PILOT_001/pilot.py",
)


def code_paths(root: Path) -> list[str]:
    package = root / "src/qclean_uwb/fp_sc/followup"
    return sorted(str(p.relative_to(root)) for p in package.glob("*.py")) + ["scripts/fp_sc_followup.py"]


def plan() -> dict:
    return dict(status="CODE_ONLY_SCIENCE_NOT_RUN", base_sha=BASE_SHA, execute_science=False,
                steps=[dict(stage=s, prerequisites=DEPENDENCIES[s], optional=s in OPTIONAL) for s in STAGES],
                real_data_runs=0, new_RT_calls=0, requires=["reviewed policy/mapping", "actual SHA-locked inputs",
                    "fresh stage-specific authorization", "calibration provenance", "result review"],
                candidate_rule="unchanged E1-01", protected_originals="E0/E1-01/source code/results unchanged")


def _gzip_json(path: Path, value):
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(jsonable(value), f, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _load_models(root, case_id, manifest, cache):
    if case_id in cache:
        return cache[case_id]
    path = manifest.get("models_by_case", {}).get(case_id)
    if path is None or path not in manifest["input_files"]:
        raise ContractError("CALIBRATION_MODEL_NOT_LOCKED:"+case_id)
    return json.loads(rooted(root, path).read_text(encoding="utf-8"))


def _aggregate_e4(records, case_meta):
    """Never pool routes or sensor seeds. Report all A-versus-arm comparisons."""
    groups = {}
    for case_id, result in records.items():
        case = case_meta[case_id]
        group = f"{case.environment_id}:{case.route}:{case.bias}:{case.channel}"
        groups.setdefault(group, []).append((case, result))
    rows = []
    for group, entries in sorted(groups.items()):
        for arm in ("B", "C", "D", "E", "F"):
            for metric, absolute in (("heading_deg", .05), ("xy_m", .01)):
                aa, bb = {}, {}
                invalid = []
                for case, result in entries:
                    a = result["metrics"]["A"]["primary_t_ge_30"]
                    b = result["metrics"][arm]["primary_t_ge_30"]
                    if not a["n"] or not b["n"]:
                        invalid.append(case.case_id)
                        continue
                    aa[str(case.sensor_seed)] = a[metric]["rmse"]
                    bb[str(case.sensor_seed)] = b[metric]["rmse"]
                if invalid or not aa:
                    rows.append(dict(group=group, arm=arm, metric=metric, status="NOT_TESTED", missing=invalid))
                    continue
                ratios = [bb[s]/aa[s] for s in aa if aa[s] > 1e-12]
                absolute_pass = all(bb[s]-aa[s] <= absolute for s in aa if aa[s] <= 1e-12)
                r4full = entries[0][0].route == "R4" and entries[0][0].channel == "Full"
                cut = .90 if r4full and metric == "heading_deg" else 1.05
                med = float(np.median(ratios)) if ratios else None
                p90 = float(np.quantile(ratios, .90)) if ratios else None
                passed = absolute_pass and (not ratios or med <= cut and (r4full or p90 <= 1.20))
                rows.append(dict(group=group, arm=arm, metric=metric, seed_count=len(aa),
                                 median_ratio=med, p90_ratio=p90, absolute_near_zero_pass=absolute_pass,
                                 observed_numeric_pass=passed, paired=paired_seed_bootstrap(aa, bb),
                                 status="SAME_RF_CONDITIONAL_NOT_INDEPENDENT_ENVIRONMENT"))
    return dict(comparisons=rows, scientific_gate="HOLD_RESULT_REVIEW", uncertainty_restored_claim=False)


def run(root: Path, manifest_path: Path, approval_path: Path, output: Path, stages: list[str]):
    root = root.resolve()
    if Path(__file__).resolve().parents[4] != root:
        raise ContractError("EXECUTING_CODE_OUTSIDE_DECLARED_REPOSITORY")
    manifest, approval, preflight_receipt = preflight(
        root, manifest_path, approval_path, stages, code_paths(root), SOURCES_REQUIRED)
    if not output.resolve().is_relative_to(root) and not approval.get("external_output_allowed", False):
        raise ContractError("EXTERNAL_OUTPUT_PATH_NOT_APPROVED")
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="RUNNING", manifest_sha256=sha256(manifest_path), approval_sha256=sha256(approval_path),
                   code_lock_sha256=digest(manifest["code_files"]), environment=environment(),
                   local_preflight=preflight_receipt, stages={},
                   start_utc=dt.datetime.now(dt.timezone.utc).isoformat(), new_RT_calls=0,
                   external_independent_accept=False, actor_role="IMPLEMENTER_SELF_CHECK")
    write_json(output/"RUN_MANIFEST.json", receipt)
    try:
        prerequisites = {}
        for stage, path in manifest.get("prerequisite_receipts", {}).items():
            if path not in manifest["input_files"]:
                raise ContractError("PREREQUISITE_RECEIPT_NOT_LOCKED")
            prerequisites[stage] = json.loads(rooted(root, path).read_text(encoding="utf-8"))
            if prerequisites[stage].get("stage") != stage or prerequisites[stage].get("study_id") != "FP-SC-001":
                raise ContractError("PREREQUISITE_RECEIPT_IDENTITY_MISMATCH")
        adapter = OriginalAdapter(root)
        case_specs = manifest["cases"]
        cache, models, calibration = {}, {}, []
        policy = Policy(**manifest["policy"])
        for stage in stages:
            exploratory = prerequisite(stage, prerequisites, approval)
            cfg = manifest["stage_config"][stage]
            case_ids = cfg["case_ids"]
            if len(case_ids) != len(set(case_ids)) or not case_ids:
                raise ContractError("EMPTY_OR_DUPLICATE_STAGE_CASES")
            # E4/E5 may include 120/240 trajectories, each with multiple
            # full-size complex CFR arrays. Never preload/retain the entire grid.
            stream_stage = stage in STREAM_STAGES
            if stream_stage:
                cache.clear()
            stage_meta = {}
            for case_id in case_ids:
                if stream_stage:
                    metadata = case_specs[case_id]["metadata"]
                    stage_meta[case_id] = SimpleNamespace(**metadata, t=np.array([0.]))
                else:
                    if case_id not in cache:
                        cache[case_id] = load_case(root, case_specs[case_id], manifest["input_files"], adapter)
                    if cache[case_id][0].case_id != case_id:
                        raise ContractError("CASE_KEY_IDENTITY_MISMATCH")
                    stage_meta[case_id] = cache[case_id][0]
            if stage.startswith(("E1-", "E2-", "E3-")) and any(stage_meta[c].split == "SEALED" for c in case_ids):
                raise ContractError("SEALED_DATA_NOT_ALLOWED_IN_DEVELOPMENT_STAGES")
            # Metadata grid checked before calculation. Actual t[0] and the
            # complete timeline are checked when each streamed case is loaded.
            validate_trajectory_grid([stage_meta[c] for c in case_ids], stage)
            if stage == "E4-03":
                folds = manifest.get("outer_fold_policies", {})
                for case_id in case_ids:
                    case = stage_meta[case_id]
                    fold = folds.get(case.route)
                    if not fold or case.route in fold["training_routes"] or not fold.get("full_pipeline_holdout_reviewed"):
                        raise ContractError("ENTIRE_PIPELINE_ROUTE_HOLDOUT_NOT_REGISTERED")
                    if not fold.get("policy_sha256") or fold["policy_sha256"] != Policy(**fold["policy"]).sha:
                        raise ContractError("OUTER_POLICY_SHA_MISMATCH")
            if stage == "E5-03":
                path = manifest.get("external_environment_contract")
                if path not in manifest["input_files"]:
                    raise ContractError("EXTERNAL_ENVIRONMENT_CONTRACT_REQUIRED")
                domain = json.loads(rooted(root, path).read_text(encoding="utf-8"))
                if not domain.get("new_data_reviewed") or set(domain["evaluation_domain_ids"]) & set(domain["development_domain_ids"]):
                    raise ContractError("EXTERNAL_ENVIRONMENT_NOT_DISJOINT_OR_NOT_REVIEWED")
                if any(stage_meta[c].corpus != "external" or stage_meta[c].environment_id not in domain["evaluation_domain_ids"] for c in case_ids):
                    raise ContractError("OLD_CORRIDOR_IS_NOT_EXTERNAL_GENERALIZATION")
            folder = output/stage
            folder.mkdir(exist_ok=False)
            stage_receipt = dict(stage=stage, study_id="FP-SC-001", execution_status="RUNNING", numerical_qa_pass=False,
                                 scientific_gate="HOLD_RESULT_REVIEW", exploratory_after_nonpass=exploratory,
                                 case_ids=case_ids, policy_sha256=policy.sha, files={}, external_independent_accept=False)
            write_json(folder/"STAGE_RECEIPT.json", stage_receipt)
            e4_results = {}
            if stage == "E3-03":
                training_ids = cfg["calibration_case_ids"]
                if not training_ids or len(training_ids) != len(set(training_ids)):
                    raise ContractError("INVALID_CALIBRATION_CASE_LIST")
                for cid in training_ids:
                    if cid not in cache:
                        cache[cid] = load_case(root, case_specs[cid], manifest["input_files"], adapter)
                    cc, ee = cache[cid]
                    calibration.extend(calibration_records(cc, ee, adapter, policy))
                _gzip_json(folder/"CALIBRATION_RECORDS.json.gz", calibration)
            # Optional CAL-only bounded search. A winner is not silently installed
            # into this run: freeze its SHA in a subsequent execution contract.
            if stage == "E2-01" and cfg.get("cal_policy_search", False):
                if any(cache[c][0].split != "CAL" for c in case_ids):
                    raise ContractError("POLICY_SEARCH_MUST_BE_CAL_ONLY")
                search_results = {}
                expected = set(case_ids)
                for candidate in policy_grid(policy):
                    grouped = []
                    for cid in case_ids:
                        cc, ee = cache[cid]
                        rows, _ = labelled(cc, ee, adapter, candidate, "PM")
                        grouped.append(dict(stratum=cid, summary=selection_summary(rows)))
                    search_results[candidate.sha] = grouped
                selected = select_policy_from_calibration(search_results, split="CAL", expected_strata=expected)
                write_json(folder/"CAL_POLICY_SELECTION.json", selected)
                _gzip_json(folder/"CAL_POLICY_GRID.json.gz", search_results)
            for case_id in case_ids:
                if stream_stage:
                    case, ev = load_case(root, case_specs[case_id], manifest["input_files"], adapter)
                    if case.case_id != case_id or abs(float(case.t[0])) > 1e-12:
                        raise ContractError("STREAMED_CASE_IDENTITY_OR_T0_MISMATCH:" + case_id)
                else:
                    case, ev = cache[case_id]
                active_policy = policy
                if stage == "E4-03":
                    active_policy = Policy(**manifest["outer_fold_policies"][case.route]["policy"])
                matched = None
                if stage in {"E3-04", "E4-01", "E4-02", "E4-03", "E5-01", "E5-02", "E5-03"}:
                    if stage == "E4-03":
                        fold_manifest = dict(manifest,models_by_case=manifest.get("outer_fold_models_by_case",{}))
                        matched = _load_models(root, case_id, fold_manifest, {})
                    else:
                        matched = _load_models(root, case_id, manifest, models)
                if stage == "E1-02":
                    result = e1_detection(case, ev, adapter, active_policy)
                elif stage == "E1-03":
                    result = stress(case, ev, adapter, active_policy, detect_only=True)
                elif stage == "E2-01":
                    result = e2_select(case, ev, adapter, active_policy)
                elif stage == "E2-02":
                    result = e2_history(case, ev, adapter, active_policy)
                elif stage == "E2-03":
                    result = e2_confidence(case, ev, adapter, active_policy)
                elif stage == "E2-04":
                    result = stress(case, ev, adapter, active_policy)
                elif stage in {"E3-01", "E3-02"}:
                    result = e3_observations(case, ev, adapter, active_policy, decomposition=stage == "E3-02")
                elif stage == "E3-03":
                    result = fit_models(calibration, case, active_policy, min_samples=cfg.get("min_samples", 20))
                    models[case_id] = result
                    write_json(folder/(case_id+"_MODELS.json"), result)
                elif stage == "E3-04":
                    result = e3_one_step(case, ev, adapter, active_policy, matched)
                elif stage in {"E4-01", "E4-02", "E4-03", "E5-03"}:
                    result = e4_closed_loop(case, ev, adapter, active_policy, matched)
                    # The aggregation only needs metrics, not six full traces.
                    e4_results[case_id] = {"metrics": result["metrics"]}
                elif stage in {"E5-01", "E5-02"}:
                    sink_path = folder/(case_id+"_OUTPUTS.jsonl")
                    with sink_path.open("x", encoding="utf-8") as sink_file:
                        def sink(value):
                            sink_file.write(json.dumps(jsonable(value), allow_nan=False)+"\n")
                            sink_file.flush()
                        result = e5_runtime(case, adapter, active_policy, matched,
                                            hardware_id=cfg["hardware_id"], sink=sink, faults=stage == "E5-02")
                else:
                    raise ContractError("NO_STAGE_DISPATCHER")
                _gzip_json(folder/(case_id+".json.gz"), result)
                if stream_stage:
                    del result, case, ev
                    gc.collect()
            if e4_results:
                write_json(folder/"PAIRED_CLAIMS.json", _aggregate_e4(e4_results, stage_meta))
            stage_receipt.update(execution_status="COMPLETE", numerical_qa_pass=True,
                                 files={p.name: sha256(p) for p in sorted(folder.iterdir()) if p.name != "STAGE_RECEIPT.json"})
            write_json(folder/"STAGE_RECEIPT.json", stage_receipt)
            receipt["stages"][stage] = stage_receipt
            prerequisites[stage] = stage_receipt
            write_json(output/"RUN_MANIFEST.json", receipt)
        receipt["status"] = "COMPLETE_TECHNICAL_ONLY"
    except Exception as exc:
        receipt.update(status="FAILED_PRESERVED", error=f"{type(exc).__name__}:{exc}",
                       traceback=traceback.format_exc(),
                       end_utc=dt.datetime.now(dt.timezone.utc).isoformat())
        write_json(output/"RUN_MANIFEST.json", receipt)
        # A failed run remains failed, but its partial evidence can be checked
        # for byte tampering; audit.py explicitly refuses to certify it.
        write_json(output/"ARTIFACT_HASHES.json", {
            str(p.relative_to(output)): sha256(p) for p in sorted(output.rglob("*"))
            if p.is_file() and p.name != "ARTIFACT_HASHES.json"
        })
        raise
    receipt["end_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    write_json(output/"RUN_MANIFEST.json", receipt)
    write_json(output/"ARTIFACT_HASHES.json", {str(p.relative_to(output)): sha256(p)
               for p in sorted(output.rglob("*")) if p.is_file() and p.name != "ARTIFACT_HASHES.json"})
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan")
    audit_command=sub.add_parser("audit")
    audit_command.add_argument("--directory",required=True,type=Path)
    inspection = sub.add_parser("preflight")
    for name in ("repo", "manifest", "approval"):
        inspection.add_argument("--"+name, required=True, type=Path)
    inspection.add_argument("--stages", nargs="+", choices=STAGES, required=True)
    e1bridge = sub.add_parser("adopt-e1")
    for name in ("repo", "run-dir", "review-dir", "output"):
        e1bridge.add_argument("--"+name, required=True, type=Path)
    execute = sub.add_parser("run")
    for name in ("repo", "manifest", "approval", "output"):
        execute.add_argument("--"+name, required=True, type=Path)
    execute.add_argument("--stages", nargs="+", choices=STAGES, required=True)
    export = sub.add_parser("export-archive")
    for name in ("repo", "spec", "output"):
        export.add_argument("--"+name, required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            value = plan()
        elif args.command == "audit":
            from .audit import audit_directory
            value=audit_directory(args.directory)
        elif args.command == "export-archive":
            value = export_archive(args.repo, json.loads(args.spec.read_text(encoding="utf-8")), args.output)
        elif args.command == "preflight":
            value = preflight(args.repo, args.manifest, args.approval, args.stages,
                              code_paths(args.repo.resolve()), SOURCES_REQUIRED)[2]
        elif args.command == "adopt-e1":
            value = adopt_e1(args.repo, args.run_dir, args.review_dir, args.output)
        else:
            value = run(args.repo, args.manifest, args.approval, args.output, args.stages)
        print(json.dumps(jsonable(value), ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ContractError, FileExistsError, KeyError, TypeError, ValueError) as exc:
        print(f"BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
