#!/usr/bin/env python3
"""Guarded production driver for DLP-R1B-CH4-001; never authorizes itself.

Shard mode calls unchanged r1b_native.acquire_pose only for an audited frozen
partition. Assemble mode rechecks original raw arrays and combines all 917
poses, including the eight hash-locked canary poses. It does not run new RF.
All output directories must be new. Scientific release remains audit pending.
"""
from __future__ import annotations

import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import sys
import time
import traceback

import numpy as np

import r1b_native as native

ROOT = native.ROOT
N_POSES = 917
PORT_LAYOUT = "[pose,frequency,rx(+45,-45),tx(+45,-45)]"
CREATED_OUTPUT = None


def need(value, reason):
    native.require(value, reason)


def canonical_spec_sha(plan):
    payload = {key: value for key, value in plan.items()
               if key not in ("production_audit", "production_spec_sha256")}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_record(path):
    path = Path(path).resolve()
    try:
        name = str(path.relative_to(ROOT))
    except ValueError:
        name = str(path)
    return dict(path=name, sha256=native.sha(path), bytes=path.stat().st_size)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def lineage(args, plan, audit):
    return dict(contract_id="DLP-R1B-CH4-001", contract_sha256=native.sha(args.contract),
                canary_qa_sha256=native.sha(args.canary_qa), production_plan_sha256=native.sha(args.production_plan),
                production_spec_sha256=canonical_spec_sha(plan),
                production_audit_sha256=plan["production_audit"]["sha256"],
                production_auditor_identity=audit["auditor_identity"],
                driver_sha256=native.sha(__file__),
                source_git_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip())


def load_locks(args):
    contract, rows = native.load_contract(args.contract)
    need("P1" in contract.get("authorized_stages", []), "NATIVE_PRODUCTION_PHASE_NOT_AUTHORIZED")
    canary = native.readj(args.canary_qa)
    contract_sha, canary_sha = native.sha(args.contract), native.sha(args.canary_qa)
    need(canary.get("status") == "PASS", "PRODUCTION_BLOCKED_CANARY_NOT_PASS")
    need(canary.get("contract_sha256") == contract_sha, "CANARY_CONTRACT_HASH_MISMATCH")
    canary_ids = contract["canary"]["pose_ids"]
    need(len(canary_ids) == 8 and canary.get("completed_pose_ids") == canary_ids,
         "EXACT_EIGHT_CANARY_POSES_REQUIRED")
    expected_checks = {"complete_8_preselected_poses", "complex_max", "complex_rms", "s_max", "s_rmse",
                       "tap_exact", "port_exact", "delay", "full_direct_present", "full_direct_los_parity",
                       "source_internal", "stable_jacobian"}
    need(expected_checks.issubset(canary.get("checks", {})) and all(canary.get("checks", {}).values()) and
         len(canary.get("records", [])) == 8,
         "CANARY_CHECKS_OR_RAW_RECORDS_INCOMPLETE")
    need([record["pose_id"] for record in canary["records"]] == canary_ids, "CANARY_RECORD_ORDER_MISMATCH")
    canary_rel = np.array([record["native_source_complex_relative"] for record in canary["records"]])
    canary_s = np.array([record["native_source_s_abs"] for record in canary["records"]])
    need(np.isfinite(canary_rel).all() and np.isfinite(canary_s).all() and
         np.sqrt(np.mean(canary_rel**2)) <= contract["tolerances"]["native_complex_relative_rms"] and
         np.sqrt(np.mean(canary_s**2)) <= contract["tolerances"]["native_s_rmse"],
         "CANARY_AGGREGATE_PARITY_NOT_PASS")
    plan = native.readj(args.production_plan)
    need(plan.get("status") == "FROZEN", "PRODUCTION_PLAN_NOT_FROZEN")
    need(plan.get("contract_sha256") == contract_sha and plan.get("canary_qa_sha256") == canary_sha,
         "PRODUCTION_PLAN_INPUT_HASH_MISMATCH")
    need(plan.get("runner_sha256") == native.sha(__file__), "PRODUCTION_DRIVER_NOT_EXACT_LOCKED_BYTES")
    spec_sha = canonical_spec_sha(plan)
    need(plan.get("production_spec_sha256") == spec_sha, "PRODUCTION_SPEC_HASH_MISMATCH")
    audit_spec = plan["production_audit"]
    audit_path = native.resolve(audit_spec["path"])
    need(native.sha(audit_path) == audit_spec["sha256"], "PRODUCTION_AUDIT_BYTES_CHANGED")
    audit = native.readj(audit_path)
    need(audit.get("status") == "PASS" and audit.get("separate_agent") is True,
         "DISTINCT_COMPUTATIONAL_PRODUCTION_AUDIT_REQUIRED")
    need(audit.get("role") in ("INDEPENDENT_AUDITOR", "INDEPENDENT_COMPUTATIONAL_AUDITOR") and
         isinstance(audit.get("auditor_identity"), str) and bool(audit["auditor_identity"]),
         "INDEPENDENT_AUDITOR_PROVENANCE_MISSING")
    for key, expected in [("production_spec_sha256", spec_sha), ("runner_sha256", native.sha(__file__)),
                          ("contract_sha256", contract_sha), ("canary_qa_sha256", canary_sha)]:
        need(audit.get(key) == expected, "PRODUCTION_AUDIT_BINDING_MISMATCH:" + key)
    if "implementer_identity" in plan:
        need(plan["implementer_identity"] != audit["auditor_identity"], "SAME_IMPLEMENTER_AND_AUDITOR")
    shards = plan["shards"]
    indices = [item["shard_index"] for item in shards]
    need(indices == list(range(len(shards))) and len(shards) > 0, "SHARD_INDICES_NOT_CANONICAL")
    selected = [pose for item in shards for pose in item["pose_ids"]]
    need(all(isinstance(pose, int) and 0 <= pose < N_POSES for pose in selected), "INVALID_PLANNED_POSE_ID")
    need(len(selected) == 909 and len(set(selected)) == 909 and
         set(selected) == set(range(N_POSES)) - set(canary_ids), "SHARDS_NOT_EXACT_909_CANARY_COMPLEMENT")
    need(all(item["pose_ids"] == sorted(item["pose_ids"]) and len(item["pose_ids"]) > 0 for item in shards),
         "SHARD_POSE_ORDER_OR_EMPTY_PARTITION")
    directories = [native.resolve(item["output_dir"]).resolve() for item in shards]
    assembly_dir = native.resolve(plan["assembly_dir"]).resolve()
    canary_dir = native.resolve(plan["canary_directory"]).resolve()
    need(len(set(directories)) == len(directories) and assembly_dir not in directories and
         canary_dir not in directories and assembly_dir != canary_dir, "OUTPUT_DIRECTORY_COLLISION_IN_PLAN")
    all_directories = [*directories, assembly_dir, canary_dir]
    need(not any(a != b and (a.is_relative_to(b) or b.is_relative_to(a))
                 for i, a in enumerate(all_directories) for b in all_directories[i+1:]),
         "FROZEN_OUTPUT_DIRECTORIES_MUST_NOT_NEST")
    need(Path(args.canary_qa).resolve().parent == canary_dir, "CANARY_DIRECTORY_NOT_BOUND_TO_QA")
    locked_raw = plan["canary_raw_files"]
    need(sorted(item["pose_id"] for item in locked_raw) == sorted(canary_ids), "CANARY_RAW_LOCK_INCOMPLETE")
    records_by_id = {record["pose_id"]: record for record in canary["records"]}
    for item in locked_raw:
        pose = item["pose_id"]
        path = native.resolve(item["path"]).resolve()
        record = records_by_id[pose]
        need(path == canary_dir / ("pose_%04d.npz" % pose), "CANARY_RAW_PATH_NOT_CANONICAL")
        need(item["sha256"] == record["raw_sha256"] == native.sha(path), "CANARY_RAW_HASH_MISMATCH")
        check_pose_metrics(contract, record)
    # The inherited initializer verifies these again before any solver call.
    for item in contract["inputs"]["banks"]:
        path = Path(args.banks) / Path(item["path"]).name
        need(native.sha(path) == item["sha256"], "PRODUCTION_FFD_BANK_HASH_MISMATCH")
    return contract, rows, canary, plan, audit


def check_pose_metrics(contract, record):
    tolerance = contract["tolerances"]
    scalar_checks = {
        "source_direct_relative": tolerance["source_direct_relative_max"],
        "native_source_complex_relative": tolerance["native_complex_relative_max"],
        "native_source_s_abs": tolerance["native_s_abs_max"],
        "native_source_detector_range_abs": tolerance["observer_abs"],
        "los_delay_abs_s": tolerance["los_delay_abs_s"],
        "full_direct_vs_separate_los_relative_max": tolerance["full_direct_relative_max"]}
    for key, threshold in scalar_checks.items():
        value = record.get(key)
        need(value is not None and np.isfinite(value) and value <= threshold,
             "PRODUCTION_POSE_PARITY_FAILED:" + key)
    need(record["native_source_tap_mismatch"] == 0 and record["native_source_port_mismatch"] == 0,
         "PRODUCTION_SOURCE_TAP_OR_PORT_MISMATCH")
    need(record["full_unique_direct_bins"] == native.N, "FULL_UNIQUE_DIRECT_RAY_MISSING")
    fd = record["fd"]
    need(len(fd) == 3 and {item["axis"] for item in fd} == {0, 1, 2}, "SOURCE_FD_CHECK_INCOMPLETE")
    need(all(item["status"] in ("PASS", "BOUNDARY_NOT_FD_PASS") for item in fd), "SOURCE_FD_FAILED")
    for mode in ("los", "full"):
        obs = record[mode]
        need(np.isfinite([obs["r_m"], obs["s"], obs["power_plus"], obs["power_minus"]]).all(),
             "NONFINITE_PRODUCTION_OBSERVATION")
        need(obs["power_plus"] >= 0 and obs["power_minus"] >= 0 and
             obs["power_plus"] + obs["power_minus"] > 0, "INVALID_SELECTED_TAP_POWER")
        need(abs(obs["s"]) <= 1. + 1e-12 and obs["observer_recompute_abs"] <= tolerance["observer_abs"],
             "PRODUCTION_OBSERVER_PARITY_FAILED")
    return True


def new_output(path):
    global CREATED_OUTPUT
    path = Path(path).resolve()
    need(not path.exists(), "APPEND_ONLY_OUTPUT_DIRECTORY_ALREADY_EXISTS")
    path.mkdir(parents=True)
    CREATED_OUTPUT = path
    return path


def run_shard(args, contract, rows, canary, plan, audit):
    need(args.shard_index is not None and 0 <= args.shard_index < len(plan["shards"]), "SHARD_INDEX_NOT_FROZEN")
    item = plan["shards"][args.shard_index]
    need(Path(args.out).resolve() == native.resolve(item["output_dir"]).resolve(), "SHARD_OUTPUT_NOT_FROZEN")
    out = new_output(args.out)
    binding = lineage(args, plan, audit)
    native.writej(out / "SHARD_STARTED.json", dict(**binding, shard_index=args.shard_index,
                  pose_ids=item["pose_ids"], status="STARTED", utc=now()))
    wall_start, cpu_start = time.monotonic(), time.process_time()
    records = []
    try:
        engine = native.initialize(contract, args.banks, out)
        for pose in item["pose_ids"]:
            record = native.acquire_pose(contract, rows[pose], engine, out)
            records.append(record)
            check_pose_metrics(contract, record)
            record["metrics_json_sha256"] = native.sha(out / ("pose_%04d.json" % pose))
            native.writej(out / ("PROGRESS_%04d.json" % len(records)),
                          dict(**binding, completed_pose_ids=[r["pose_id"] for r in records],
                               latest_record=record, elapsed_s=time.monotonic()-wall_start, status="IN_PROGRESS"))
        need([r["pose_id"] for r in records] == item["pose_ids"], "SHARD_POSE_ORDER_CHANGED")
        receipt = dict(**binding, status="PASS", shard_index=args.shard_index, pose_ids=item["pose_ids"],
                       completed_pose_count=len(records), actual_native_solver=True, no_new_RF_noise=True,
                       records=records, environment=file_record(out / "ENVIRONMENT.json"),
                       measured_cost=dict(wall_elapsed_s=time.monotonic()-wall_start,
                                          process_cpu_s=time.process_time()-cpu_start,
                                          acquisition_s=sum(r["acquisition_seconds"] for r in records),
                                          max_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024),
                       utc=now(), scientific_supported=False, independent_postrun_audit="PENDING")
        native.writej(out / "SHARD_RECEIPT.json", receipt)
        return receipt
    except Exception as error:
        partial = native.preserve_partial(out)
        native.writej(out / "SHARD_FAILURE.json", dict(**binding, status="HOLD_RF_PARITY",
                      shard_index=args.shard_index, exception=repr(error), traceback=traceback.format_exc(),
                      completed_records=records, retained_partial=partial,
                      elapsed_s=time.monotonic()-wall_start, utc=now()))
        raise


def col_observer(h_col):
    window = .5 - .5*np.cos(2*np.pi*np.arange(native.N)/(native.N-1))
    cir = np.fft.ifft(h_col * window[:, None], n=4*native.N, axis=0)*native.N
    magnitude = abs(cir)
    port = int(magnitude.max(axis=0).argmax())
    peak = magnitude[:, port].max()
    need(peak > 0 and np.isfinite(peak), "SOURCE_COL_HAS_NO_SIGNAL")
    tap = int(np.flatnonzero(magnitude[:, port] >= .3*peak)[0])
    power = abs(cir[tap])**2
    need(power.sum() > 0, "SOURCE_COL_ZERO_SELECTED_POWER")
    return dict(s=float((power[0]-power[1])/power.sum()), tap=tap, strong_port=port,
                r_m=float(tap*native.C/(4*native.N*1950000.))), cir


def validate_raw_pose(path, row, record, contract):
    """Recompute every preserved total H from native a/tau, without re-running RT."""
    need(native.sha(path) == record["raw_sha256"], "RAW_PER_POSE_SHA_CHANGED")
    with np.load(path, allow_pickle=False) as archive:
        data = {key: archive[key].copy() for key in archive.files}
    need(int(data["pose_id"]) == int(row["pose_id"]), "RAW_POSE_ID_MISMATCH")
    need(abs(float(data["t_s"]) - float(row["t_s"])) <= 1e-9, "RAW_TIMESTAMP_MISMATCH")
    xyz = np.array([float(row["x"]), float(row["y"]), .45])
    need(data["xyz_m"].shape == (3,) and max(abs(data["xyz_m"]-xyz)) <= 1e-6, "RAW_POSE_XYZ_MISMATCH")
    yaw_diff = (float(data["psi_rad"]) - np.radians(float(row["yaw_body_deg"])) + np.pi) % (2*np.pi) - np.pi
    need(abs(np.degrees(yaw_diff)) <= 1e-6, "RAW_YAW_MISMATCH")
    need(np.array_equal(data["anchor_xyz_m"], np.array([10., 0., 2.65])), "RAW_ANCHOR_NOT_B")
    freq = 6250400000. + 1950000.*np.arange(native.N)
    need(np.array_equal(data["freq_hz"], freq), "RAW_FREQUENCY_AXIS_MISMATCH")
    tolerance = contract["tolerances"]
    obs = {}
    path_sum_error = 0.
    direct_parity, direct_count = [], []
    los_delay_error = 0.
    geometric_delay = np.linalg.norm(xyz-np.array([10., 0., 2.65]))/native.C
    for mode in ("los", "full"):
        h = data["H_"+mode]
        need(h.shape == (native.N, 2, 2) and np.iscomplexobj(h) and np.isfinite(h).all(), "RAW_H_INVALID")
        observed, cir = native.observer(h)
        obs[mode] = observed
        need(data["CIR_"+mode].shape == cir.shape and np.isfinite(data["CIR_"+mode]).all(), "RAW_CIR_INVALID")
        need(float(np.max(abs(data["CIR_"+mode]-cir))) <= tolerance["observer_abs"], "RAW_CIR_PARITY_FAILED")
        for key in ("r_m", "s", "power_plus", "power_minus"):
            need(abs(observed[key]-record[mode][key]) <= tolerance["observer_abs"], "SAVED_OBSERVATION_NOT_RAW:"+key)
        need(observed["tap"] == record[mode]["tap"] and observed["strong_port"] == record[mode]["strong_port"],
             "SAVED_OBSERVER_BRANCH_OR_TAP_CHANGED")
        offsets = data[mode+"_path_offsets"]
        tau, amplitude = data[mode+"_tau_s"], data[mode+"_a"]
        interactions, objects = data[mode+"_interactions"], data[mode+"_objects"]
        counts = data[mode+"_path_counts"]
        need(offsets.shape == (native.N+1,) and offsets[0] == 0 and np.all(np.diff(offsets)>0), "RAW_PATH_OFFSETS_INVALID")
        need(counts.shape == (native.N,) and np.array_equal(counts, np.diff(offsets)), "RAW_PATH_COUNTS_MISMATCH")
        need(offsets[-1] == len(tau) and amplitude.shape == (2, 2, len(tau)) and
             interactions.ndim == objects.ndim == 2 and interactions.shape == objects.shape and
             interactions.shape[1] == len(tau), "RAW_PATH_ARRAY_AXES_INVALID")
        need(np.isfinite(tau).all() and np.isfinite(amplitude).all(), "RAW_PATH_ARRAY_NONFINITE")
        for fi in range(native.N):
            first, last = int(offsets[fi]), int(offsets[fi+1])
            delays = tau[first:last]
            contribution = amplitude[:, :, first:last]*np.exp(-2j*np.pi*freq[fi]*delays)[None, None, :]
            rebuilt = contribution.sum(axis=-1)
            path_sum_error = max(path_sum_error, float(np.max(abs(h[fi]-rebuilt))))
            if mode == "los":
                need(last-first == 1, "RAW_LOS_NOT_SINGLE_PATH")
                los_delay_error = max(los_delay_error, float(np.max(abs(delays-geometric_delay))))
            else:
                direct = (np.count_nonzero(interactions[:, first:last], axis=0) == 0)
                direct &= abs(delays-geometric_delay) <= tolerance["los_delay_abs_s"]
                direct_count.append(int(direct.sum()))
                need(direct.sum() == 1, "RAW_FULL_NOT_UNIQUE_DIRECT_PATH")
                direct_h = contribution[:, :, int(np.flatnonzero(direct)[0])]
                scale = np.linalg.norm(data["H_los"][fi])
                need(scale > 0, "RAW_LOS_ZERO_FREQUENCY_BIN")
                direct_parity.append(float(np.linalg.norm(direct_h-data["H_los"][fi])/scale))
    source_h, source_independent = data["source_physical_h"], data["source_independent_h"]
    need(source_h.shape == source_independent.shape == (native.N, 2) and
         np.isfinite(source_h).all() and np.isfinite(source_independent).all(), "RAW_SOURCE_ARRAY_INVALID")
    source_obs, _ = col_observer(source_h)
    need(np.linalg.norm(source_independent)>0 and np.linalg.norm(data["H_los"][:, :, 0])>0, "ZERO_SOURCE_REFERENCE")
    internal = float(np.linalg.norm(source_h-source_independent)/np.linalg.norm(source_independent))
    rel = float(np.linalg.norm(data["H_los"][:, :, 0]-source_h)/np.linalg.norm(data["H_los"][:, :, 0]))
    pred = data["source_model_h"]
    need(pred.shape == (2,) and np.isfinite(pred).all(), "RAW_SOURCE_MODEL_INVALID")
    need(abs(pred[1]-source_obs["s"]) <= tolerance["observer_abs"], "SOURCE_PHYSICAL_OBSERVER_PARITY_FAILED")
    need(abs(pred[0] - (np.linalg.norm(xyz-np.array([10.,0.,2.65])) + contract["replay"]["range_offset_m"])) <= 1e-12,
         "SOURCE_CONTINUOUS_RANGE_OFFSET_CHANGED")
    need(data["source_model_H"].shape == (2, 4) and np.isfinite(data["source_model_H"]).all(), "RAW_SOURCE_JACOBIAN_INVALID")
    need(np.array_equal(data["source_model_H"][:, 3], np.zeros(2)), "SOURCE_DIRECT_BIAS_DERIVATIVE_NONZERO")
    recomputed = {**record,
                  "source_direct_relative": internal, "native_source_complex_relative": rel,
                  "native_source_s_abs": abs(obs["los"]["s"]-float(pred[1])),
                  "native_source_tap_mismatch": int(obs["los"]["tap"] != source_obs["tap"]),
                  "native_source_port_mismatch": int(obs["los"]["strong_port"] != source_obs["strong_port"]),
                  "native_source_detector_range_abs": abs(obs["los"]["r_m"]-source_obs["r_m"]),
                  "los_delay_abs_s": los_delay_error, "full_unique_direct_bins": int(np.sum(np.array(direct_count)==1)),
                  "full_direct_vs_separate_los_relative_max": max(direct_parity),
                  "raw_path_sum_H_max_abs": path_sum_error}
    for mode in ("los", "full"):
        recomputed[mode] = {**record[mode], **obs[mode]}
    need(path_sum_error <= tolerance["observer_abs"], "RAW_PATH_SUM_H_PARITY_FAILED")
    check_pose_metrics(contract, recomputed)
    return data, recomputed


def run_assemble(args, contract, rows, canary, plan, audit):
    need(args.shard_index is None, "ASSEMBLE_HAS_NO_SHARD_INDEX")
    need(Path(args.out).resolve() == native.resolve(plan["assembly_dir"]).resolve(), "ASSEMBLY_OUTPUT_NOT_FROZEN")
    # Validate every finished shard receipt before creating any combined output.
    binding = lineage(args, plan, audit)
    sources = []
    canary_dir = native.resolve(plan["canary_directory"])
    for record in canary["records"]:
        sources.append((record["pose_id"], canary_dir/record["raw_file"], record, "CANARY"))
    shard_receipts = []
    for item in plan["shards"]:
        directory = native.resolve(item["output_dir"])
        receipt_path = directory/"SHARD_RECEIPT.json"
        receipt = native.readj(receipt_path)
        need(receipt.get("status") == "PASS" and receipt.get("pose_ids") == item["pose_ids"], "SHARD_NOT_PASS_OR_WRONG_POSES")
        for key in ("contract_sha256", "canary_qa_sha256", "production_plan_sha256", "production_spec_sha256",
                    "production_audit_sha256", "driver_sha256"):
            need(receipt.get(key) == binding[key], "SHARD_RECEIPT_BINDING_CHANGED:"+key)
        need(receipt.get("shard_index") == item["shard_index"] and
             receipt.get("completed_pose_count") == len(item["pose_ids"]), "SHARD_RECEIPT_COUNT_MISMATCH")
        need([r["pose_id"] for r in receipt["records"]] == item["pose_ids"], "SHARD_RECORD_POSE_ORDER_MISMATCH")
        env_path = native.resolve(receipt["environment"]["path"])
        need(native.sha(env_path) == receipt["environment"]["sha256"], "SHARD_ENVIRONMENT_HASH_MISMATCH")
        for record in receipt["records"]:
            pose = record["pose_id"]
            need(record["raw_file"] == "pose_%04d.npz" % pose, "RAW_FILENAME_NOT_CANONICAL")
            json_path = directory/("pose_%04d.json" % pose)
            need(native.sha(json_path) == record["metrics_json_sha256"], "PER_POSE_METRICS_JSON_CHANGED")
            metrics = native.readj(json_path)
            need(metrics == {key: value for key, value in record.items() if key != "metrics_json_sha256"},
                 "PER_POSE_METRICS_NOT_RECEIPT_RECORD")
            check_pose_metrics(contract, record)
            sources.append((pose, directory/record["raw_file"], record, "SHARD_%d" % item["shard_index"]))
        shard_receipts.append({**file_record(receipt_path), "measured_cost": receipt["measured_cost"]})
    sources.sort(key=lambda item: item[0])
    need([item[0] for item in sources] == list(range(N_POSES)), "ASSEMBLY_NOT_EXACT_917_UNIQUE_POSES")
    out = new_output(args.out)
    native.writej(out/"ASSEMBLY_STARTED.json", dict(**binding, status="STARTED", utc=now()))
    dest = out/"data"
    dest.mkdir()
    wall_start, cpu_start = time.monotonic(), time.process_time()
    h_full = np.empty((N_POSES, native.N, 2, 2), dtype=np.complex128)
    h_los = np.empty_like(h_full)
    recomputed_metrics, raw_ledger, observation_rows = [], [], []
    try:
        for pose, path, record, origin in sources:
            data, metric = validate_raw_pose(path, rows[pose], record, contract)
            h_full[pose], h_los[pose] = data["H_full"], data["H_los"]
            recomputed_metrics.append(metric)
            raw_ledger.append({**file_record(path), "pose_id": pose, "origin": origin,
                               "contains_native_path_arrays": True})
            row = dict(pose_id=pose, t_s=float(rows[pose]["t_s"]), phase=rows[pose]["phase"], origin=origin,
                       direct_full_visible=metric["full_unique_direct_bins"] == native.N,
                       direct_los_visible=True)
            for key in ("source_direct_relative", "native_source_complex_relative", "native_source_s_abs",
                        "native_source_tap_mismatch", "native_source_port_mismatch", "los_delay_abs_s",
                        "full_direct_vs_separate_los_relative_max", "raw_path_sum_H_max_abs"):
                row[key] = metric[key]
            for mode in ("los", "full"):
                for key, value in metric[mode].items():
                    row[mode+"_"+key] = value
            observation_rows.append(row)
            if (pose+1) % 100 == 0 or pose == N_POSES-1:
                print("R1B_ASSEMBLY_RAW_VALIDATED", pose+1, flush=True)
        rel = np.array([r["native_source_complex_relative"] for r in recomputed_metrics])
        se = np.array([r["native_source_s_abs"] for r in recomputed_metrics])
        aggregate = dict(n_pose=N_POSES, complex_max=float(rel.max()), complex_rms=float(np.sqrt(np.mean(rel**2))),
                         s_max=float(se.max()), s_rmse=float(np.sqrt(np.mean(se**2))),
                         tap_mismatches=sum(r["native_source_tap_mismatch"] for r in recomputed_metrics),
                         port_mismatches=sum(r["native_source_port_mismatch"] for r in recomputed_metrics),
                         raw_path_sum_H_max_abs=max(r["raw_path_sum_H_max_abs"] for r in recomputed_metrics))
        tolerance = contract["tolerances"]
        passed = (aggregate["complex_max"] <= tolerance["native_complex_relative_max"] and
                  aggregate["complex_rms"] <= tolerance["native_complex_relative_rms"] and
                  aggregate["s_max"] <= tolerance["native_s_abs_max"] and
                  aggregate["s_rmse"] <= tolerance["native_s_rmse"] and
                  aggregate["tap_mismatches"] == aggregate["port_mismatches"] == 0)
        with (dest/"native_per_pose_observations_and_metrics.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(observation_rows[0]))
            writer.writeheader()
            writer.writerows(observation_rows)
        native.writej(out/"P1_AGGREGATE_SOURCE_PARITY.json", dict(status="PASS" if passed else "HOLD_RF_PARITY", **aggregate))
        native.writej(out/"P1_RAW_FILE_LEDGER.json", dict(**binding, files=raw_ledger, shard_receipts=shard_receipts))
        need(passed, "ALL_917_AGGREGATE_SOURCE_PARITY_FAILED")
        rf_path = dest/"native_full_los.npz"
        np.savez_compressed(rf_path, freq_hz=6250400000.+1950000.*np.arange(native.N), H_full=h_full, H_los=h_los,
                            t_s=np.array([float(row["t_s"]) for row in rows]),
                            x_m=np.array([float(row["x"]) for row in rows]),
                            y_m=np.array([float(row["y"]) for row in rows]),
                            psi_rad=np.radians([float(row["yaw_body_deg"]) for row in rows]),
                            pose_id=np.arange(N_POSES), phase=np.array([row["phase"] for row in rows]),
                            direct_full_visible=np.array([row["direct_full_visible"] for row in observation_rows], dtype=bool),
                            direct_los_visible=np.array([row["direct_los_visible"] for row in observation_rows], dtype=bool))
        cost = dict(assembly_wall_elapsed_s=time.monotonic()-wall_start, assembly_process_cpu_s=time.process_time()-cpu_start,
                    acquisition_seconds_sum_all_917=sum(r["acquisition_seconds"] for r in recomputed_metrics),
                    canary_measured_cost=canary["measured_cost"],
                    shard_wall_elapsed_s_sum=sum(r["measured_cost"]["wall_elapsed_s"] for r in shard_receipts),
                    shard_process_cpu_s_sum=sum(r["measured_cost"]["process_cpu_s"] for r in shard_receipts),
                    assembly_max_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024)
        manifest = dict(**binding, status="PASS", n_pose=N_POSES, paired_pose_count=N_POSES, missing_pose_count=0,
                        channels=["FULL", "LOS"], actual_native_solver=True, port_layout=PORT_LAYOUT,
                        rf_sha256=native.sha(rf_path), rf_file=file_record(rf_path),
                        original_pose_csv=contract["inputs"]["pose_csv"], reused_canary_pose_ids=contract["canary"]["pose_ids"],
                        newly_acquired_pose_count=909, aggregate_parity=aggregate, measured_cost=cost,
                        raw_files=raw_ledger, shard_receipts=shard_receipts,
                        path_arrays="Preserved in every original per-pose NPZ; offsets partition tau/a/interactions/objects by frequency",
                        direct_visibility_definition="Exactly one zero-interaction ray within frozen geometric-delay tolerance at every frequency",
                        scientific_supported=False, independent_postrun_audit="PENDING", utc=now())
        native.writej(dest/"channel_full_and_los_manifest.json", manifest)
        return manifest
    except Exception as error:
        native.writej(out/"ASSEMBLY_FAILURE.json", dict(**binding, status="HOLD_RF_PARITY", exception=repr(error),
                      traceback=traceback.format_exc(), completed_pose_ids=[r["pose_id"] for r in recomputed_metrics],
                      checked_raw_files=raw_ledger, original_per_pose_RF_preserved=True, utc=now()))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("shard", "assemble"))
    parser.add_argument("--contract", required=True)
    parser.add_argument("--canary-qa", required=True)
    parser.add_argument("--production-plan", required=True)
    parser.add_argument("--banks", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--shard-index", type=int)
    args = parser.parse_args()
    try:
        contract, rows, canary, plan, audit = load_locks(args)
        runner = run_shard if args.mode == "shard" else run_assemble
        receipt = runner(args, contract, rows, canary, plan, audit)
        print(json.dumps(dict(mode=args.mode, status=receipt["status"])), flush=True)
        return 0
    except Exception as error:
        print("R1B_PRODUCTION_HOLD", repr(error), file=sys.stderr)
        # A preflight failure never writes into an existing output directory.
        if CREATED_OUTPUT is not None and not any((CREATED_OUTPUT/name).exists() for name in
                                                  ("SHARD_FAILURE.json", "ASSEMBLY_FAILURE.json")):
            native.writej(CREATED_OUTPUT/"DRIVER_FAILURE.json", dict(status="HOLD", exception=repr(error),
                          traceback=traceback.format_exc(), driver_sha256=native.sha(__file__), utc=now()))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
