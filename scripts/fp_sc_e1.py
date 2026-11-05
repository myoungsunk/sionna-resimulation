#!/usr/bin/env python3
"""FP-SC-001 E1-01: fixed clean CIR candidate-availability experiment.

Preparation reads hashes and safe headers only. Actual waveform computation
requires the separate reviewed E1-01 execution lock and qualified H0 gate.
Nothing here replaces a first path, fits an error model, or runs an EKF.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import ExitStack
import csv
import datetime as dt
import gzip
import io
import json
from pathlib import Path
import sys
import traceback

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

import numpy as np
from qclean_uwb.drivesim import observation
from qclean_uwb.fp_sc.candidates import CandidateConfig, MODES, generate_pools
from qclean_uwb.fp_sc.contracts import environment, git_head, inspect_payload, sha256, write_json
from qclean_uwb.fp_sc.e1_contracts import FIXED, SCOPE, verify_e1_lock


PHYSICAL = Path("research/MBVAR_PRR_001_20261103/PHYSICAL_CAUSALITY_20261104")
STUDY = PHYSICAL / "FP_SELECTIVE_CORRECTION_001"
E1 = STUDY / "E1_20261105"
C1A = PHYSICAL / "C1/C1A_001"
G4 = PHYSICAL / "C3/G4_001/RUN_001"
RF = Path("results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C")
ROUTES = {"R2": 979, "R4": 742, "R5": 1415}
SOURCE_LENGTHS = {"R2": 1303, "R4": 922, "R5": 1883}
CHANNELS = ("Full", "Native_LoS")
CONFIG = CandidateConfig()

META_FIELDS = ["packet_uid", "corpus", "route", "coordinate", "condition_id", "yaw_deg", "pose_id", "t_s", "channel"]
PACKET_FIELDS = META_FIELDS + [
    "mode", "raw_tap", "raw_rx", "raw_valid", "raw_peak", "raw_denominator", "raw_signed_s",
    "raw_range_m", "raw_reason", "reference_tap", "reference_valid", "normal", "wrong",
    "one_tap_error", "large_error", "original_invalid", "unknown_reference", "candidate_count",
    "supported_count", "overflow", "reference_in_all", "reference_in_supported", "reference_usable",
    "raw_preserved", "pool_status", "noise_amplitude_floor", "numeric_amplitude_floor", "pool_hash"]
CANDIDATE_FIELDS = ["packet_uid", "mode", "tap", "is_raw", "supported", "power_plus", "power_minus",
    "denominator", "signed_s", "polarization_valid", "support_ports_json", "lobe_ids_json",
    "group_ids_json", "support_records_json"]
LOBE_FIELDS = ["packet_uid", "lobe_id", "rx", "port_peak_number", "peak_tap", "plateau_end", "boundary",
    "peak_amplitude", "prominence", "left_prominence_minimum", "right_prominence_minimum",
    "left_local_valley", "right_local_valley", "edge_tap", "candidate_taps_json", "eligible", "reason",
    "candidate_amplitude_floor"]
EPISODE_FIELDS = ["episode_id", "route", "channel", "mode", "start_pose_id", "end_pose_id", "start_t_s",
    "end_t_s", "n_packets", "n_recalled", "recall", "all_recalled", "any_recalled", "longest_missing_run"]


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def json_cell(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _conditions(repo):
    conditions = json.loads((repo / G4 / "CONDITIONS.json").read_text())
    ids = [c["condition_id"] for c in conditions]
    coordinates = defaultdict(list)
    for c in conditions:
        if not isinstance(c["condition_id"], str) or Path(c["condition_id"]).name != c["condition_id"]:
            raise ValueError("UNSAFE_G4_CONDITION_ID")
        coordinates[c["coordinate"]].append(c["yaw_index"])
    if len(ids) != 24 or len(set(ids)) != 24 or len(coordinates) != 6:
        raise ValueError("G4_CORPUS_ID_COUNT_MISMATCH")
    if any(sorted(yaws) != [0, 1, 2, 3] for yaws in coordinates.values()):
        raise ValueError("G4_COORDINATE_YAW_SCOPE_MISMATCH")
    # Archived CONDITIONS also contains old outcome summaries. Only these
    # identity/coordinate fields leave this metadata reader; current labels
    # are recomputed from direct spectra after candidate construction.
    return [{key: c[key] for key in ("condition_id", "coordinate", "yaw_index", "yaw_deg")}
            for c in conditions]


def input_paths(repo):
    paths = {str(RF / "freqs_hz.npy"), str(G4 / "CONDITIONS.json")}
    for route in ROUTES:
        paths.add(str(RF / "FULL_RF" / f"H_{route}_aB_m0.npy"))
        paths.add(str(RF / f"H_LoS_{route}_aB_m0.npy"))
        paths.add(str(C1A / "FROZEN_PACKETS/algorithm_input" / f"{route}_aB_m0_B0_Full.npz"))
    for condition in _conditions(repo):
        paths.add(str(G4 / condition["condition_id"] / "FIELDS_AND_WINDOWS.npz"))
    if len(paths) != 35:
        raise ValueError("E1_INPUT_SCOPE_COUNT_MISMATCH")
    return sorted(paths)


def validate_spec(spec):
    if spec.get("schema") != "FP_SC_E1_01_CANDIDATE_SPEC_V1" or spec.get("experiment_id") != "E1-01":
        raise ValueError("E1_WRONG_POLICY_SPEC")
    fixed = spec.get("fixed_generator", {})
    if any(fixed.get(k) != value for k, value in FIXED.items()):
        raise ValueError("E1_FIXED_GENERATOR_CHANGED")
    if fixed.get("denominator_power_floor") != 0.0:
        raise ValueError("E1_DENOMINATOR_RULE_CHANGED")
    if spec["corpus"]["dynamic"]["routes"] != ROUTES or spec["corpus"]["totals"]["expected_packet_mode_rows"] != 12640:
        raise ValueError("E1_POLICY_CORPUS_CHANGED")
    if spec["observed_gate_proposal"]["numerical_threshold"] != .95 or spec["observed_gate_proposal"]["E2_GO"] is not False:
        raise ValueError("E1_GATE_POLICY_CHANGED")


def prepare(spec_path, dest, checker=None):
    """Create review material without transforming waveforms or scoring labels."""
    spec = json.loads(Path(spec_path).read_text())
    validate_spec(spec)
    dest = Path(dest).resolve()
    if not dest.is_relative_to(REPO):
        raise ValueError("PREPARATION_DESTINATION_OUTSIDE_REPOSITORY")
    names = ("POLICY_SPEC.json", "INPUT_LOCK.json", "ENV_LOCK.json", "CODE_LOCK.json")
    if any((dest / name).exists() for name in names):
        raise FileExistsError("E1_PREPARATION_WOULD_OVERWRITE_DOCUMENT")
    entries = [inspect_payload(REPO, path) for path in input_paths(REPO)]
    blocked = [entry for entry in entries if not entry["status"].startswith("VERIFIED")]
    paths = {
        "src/qclean_uwb/__init__.py", "src/qclean_uwb/drivesim/__init__.py",
        "src/qclean_uwb/drivesim/observation.py", "src/qclean_uwb/fp_sc/__init__.py",
        "src/qclean_uwb/fp_sc/contracts.py", "src/qclean_uwb/fp_sc/e1_contracts.py",
        "src/qclean_uwb/fp_sc/candidates.py", "scripts/fp_sc_e1.py",
        "tests/test_fp_sc_candidates.py", "tests/test_fp_sc_e1_contracts.py",
        "tests/test_fp_sc_e1_candidate_checker.py",
    }
    checker_path = Path(checker).resolve() if checker else REPO / E1 / "audit/check_candidates.py"
    if not checker_path.is_relative_to(REPO):
        raise ValueError("CHECKER_OUTSIDE_REPOSITORY")
    paths.add(checker_path.relative_to(REPO).as_posix())
    code = {path: sha256(REPO / path) for path in sorted(paths)}
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "POLICY_SPEC.json").write_bytes(Path(spec_path).read_bytes())
    write_json(dest / "INPUT_LOCK.json", {
        "schema": "FP_SC_E1_01_INPUT_LOCK_V1", "source_commit": git_head(REPO),
        "files": entries, "blocked": blocked, "expected_file_count": 35,
        "verification": "Actual SHA256, byte count and safe array headers; no candidate/label metrics computed",
        "total_verified_bytes": sum(e.get("size_bytes", 0) for e in entries if e["status"].startswith("VERIFIED")),
    })
    write_json(dest / "ENV_LOCK.json", environment())
    write_json(dest / "CODE_LOCK.json", {"schema": "FP_SC_CODE_CONTENT_V1", "files": code})
    print(json_cell({"status": "PREPARED_NO_SCIENCE_EXECUTED", "inputs": len(entries),
                     "blocked": len(blocked), "code_files": len(code)}), flush=True)


def reference_observation(cir):
    """Evaluator-only native receiver reference; never passed to generator."""
    if cir.shape != (1028, 2) or not np.iscomplexobj(cir):
        raise ValueError("REFERENCE_CIR_SCHEMA")
    if not np.isfinite(cir).all():
        return {"tap": None, "valid": False}
    observed = observation.first_path_batch(cir[None], 1_950_000.0)
    peak = float(observed["peak"][0])
    denominator = float(observed["power"][0].sum())
    numeric_floor = CONFIG.numeric_epsilon_multiplier * np.finfo(float).eps * peak
    valid = bool(peak > 0 and peak >= numeric_floor and denominator > 0
                 and np.isfinite(observed["s"][0]) and np.isfinite(observed["range_m"][0]))
    return {"tap": int(observed["index"][0]), "valid": valid}


def classify(pool, reference):
    raw = pool["raw"]
    comparable = raw["valid"] and reference["valid"]
    delta = abs(raw["tap"] - reference["tap"]) if comparable else None
    in_all = bool(reference["valid"] and reference["tap"] in pool["candidate_taps"])
    supported = bool(reference["valid"] and reference["tap"] in pool["supported_taps"])
    preserved = raw["tap"] in pool["candidate_taps"] if raw["valid"] else not pool["candidate_taps"]
    return {
        "raw_tap": raw.get("tap"), "raw_rx": raw.get("rx"), "raw_valid": raw["valid"],
        "raw_peak": raw.get("peak"), "raw_denominator": raw.get("denominator"),
        "raw_signed_s": raw.get("signed_s"), "raw_range_m": raw.get("range_m"), "raw_reason": raw["reason"],
        "reference_tap": reference["tap"], "reference_valid": reference["valid"],
        "normal": comparable and delta == 0, "wrong": comparable and delta != 0,
        "one_tap_error": comparable and delta == 1, "large_error": comparable and delta >= 2,
        "original_invalid": reference["valid"] and not raw["valid"], "unknown_reference": not reference["valid"],
        "candidate_count": len(pool["candidate_taps"]), "supported_count": len(pool["supported_taps"]),
        "overflow": pool["overflow"], "reference_in_all": in_all, "reference_in_supported": supported,
        "reference_usable": bool(supported and not pool["overflow"] and raw["valid"]),
        "raw_preserved": bool(preserved), "pool_status": pool["status"],
        "noise_amplitude_floor": pool.get("noise_amplitude_floor"),
        "numeric_amplitude_floor": pool.get("numeric_amplitude_floor"), "pool_hash": pool["pool_hash"],
    }


def error_episodes(rows):
    """Maximal large-error runs with exact pose-adjacency/time-gap breaks."""
    episodes, current = [], []
    for row in rows:
        adjacent = (current and row["pose_id"] == current[-1]["pose_id"] + 1
                    and row["t_s"] - current[-1]["t_s"] <= .4)
        if current and (not row["large_error"] or not adjacent):
            episodes.append(current)
            current = []
        if row["large_error"]:
            current.append(row)
    if current:
        episodes.append(current)
    result = []
    for number, episode in enumerate(episodes):
        hits = [r["reference_usable"] for r in episode]
        missing, longest = 0, 0
        for hit in hits:
            missing = 0 if hit else missing + 1
            longest = max(longest, missing)
        first, last = episode[0], episode[-1]
        result.append({"episode_id": f'{first["route"]}:{first["channel"]}:{first["mode"]}:{number}',
            "route": first["route"], "channel": first["channel"], "mode": first["mode"],
            "start_pose_id": first["pose_id"], "end_pose_id": last["pose_id"],
            "start_t_s": first["t_s"], "end_t_s": last["t_s"], "n_packets": len(hits),
            "n_recalled": sum(hits), "recall": sum(hits) / len(hits),
            "all_recalled": all(hits), "any_recalled": any(hits), "longest_missing_run": longest})
    return result


def counts(rows):
    flags = ["raw_valid", "reference_valid", "normal", "wrong", "one_tap_error", "large_error",
             "original_invalid", "unknown_reference", "overflow", "reference_in_all",
             "reference_in_supported", "reference_usable", "raw_preserved"]
    result = {"n_packet_mode_rows": len(rows), **{key: sum(bool(r[key]) for r in rows) for key in flags}}
    large = [r for r in rows if r["large_error"]]
    for key in ("reference_in_all", "reference_in_supported", "reference_usable"):
        n = sum(r[key] for r in large)
        result["large_error_" + key] = n
        result["large_error_" + key + "_recall"] = n / len(large) if large else None
    result["large_error_status"] = "OBSERVED" if large else "NOT_TESTED"
    result["candidate_count_total"] = sum(r["candidate_count"] for r in rows)
    result["candidate_count_max"] = max((r["candidate_count"] for r in rows), default=0)
    result["supported_count_total"] = sum(r["supported_count"] for r in rows)
    return result


def summarize(rows):
    cells, populations, statics = defaultdict(list), defaultdict(list), defaultdict(list)
    for row in rows:
        cells[(row["corpus"], row["route"], row["channel"], row["mode"])].append(row)
        populations[(row["corpus"], row["channel"], row["mode"])].append(row)
        if row["corpus"] == "static_g4":
            statics[(row["coordinate"], row["channel"], row["mode"])].append(row)
    episodes = []
    for key, members in cells.items():
        if key[0] == "dynamic":
            episodes.extend(error_episodes(members))
    primary = counts(populations[("dynamic", "Full", "TWO_PORT_UNION")])
    route_primary = {route: counts(cells[("dynamic", route, "Full", "TWO_PORT_UNION")]) for route in ROUTES}
    observed = primary["large_error_reference_usable_recall"]
    numeric = observed is not None and observed >= .95
    stratified = all(value["large_error_reference_usable_recall"] >= .95
                     for value in route_primary.values() if value["large_error"])
    status = "INCONCLUSIVE_NO_LARGE_ERRORS" if observed is None else (
        "OBSERVED_THRESHOLD_MET" if numeric and stratified else (
        "NOT_SUPPORTED_STRATIFIED" if numeric else "OBSERVED_THRESHOLD_NOT_MET"))
    by_packet = defaultdict(dict)
    for row in rows:
        by_packet[row["packet_uid"]][row["mode"]] = row
    paired = defaultdict(lambda: {"waveforms": 0, "large_errors": 0,
        "both_usable": 0, "only_union_usable": 0, "only_strongest_usable": 0, "neither_usable": 0,
        "large_both_usable": 0, "large_only_union_usable": 0,
        "large_only_strongest_usable": 0, "large_neither_usable": 0})
    for modes in by_packet.values():
        if set(modes) != set(MODES):
            raise ValueError("PAIRED_MODE_ROW_MISSING")
        strong, union = modes["STRONGEST_ONLY"], modes["TWO_PORT_UNION"]
        result = paired[(union["corpus"], union["route"], union["channel"])]
        result["waveforms"] += 1
        label = ("both_usable" if strong["reference_usable"] and union["reference_usable"] else
                 "only_union_usable" if union["reference_usable"] else
                 "only_strongest_usable" if strong["reference_usable"] else "neither_usable")
        result[label] += 1
        if union["large_error"]:
            result["large_errors"] += 1
            result["large_" + label] += 1
    summary = {
        "schema": "FP_SC_E1_01_SUMMARY_V1", "stage": "E1-01", "role": "IMPLEMENTER_SELF_CHECK",
        "corpus_counts": {"dynamic_waveforms": 6272, "g4_waveforms": 48, "packet_mode_rows": len(rows)},
        "cells": [{"corpus": k[0], "route": k[1], "channel": k[2], "mode": k[3], **counts(v)} for k, v in sorted(cells.items())],
        "populations": [{"corpus": k[0], "channel": k[1], "mode": k[2], **counts(v)} for k, v in sorted(populations.items())],
        "primary_dynamic_full_two_port_union": primary, "primary_by_route": route_primary,
        "paired_availability": [{"corpus": k[0], "route": k[1], "channel": k[2], **value}
                                for k, value in sorted(paired.items())],
        "paired_availability_note": "The strongest tap set is a subset of the union, but the union may exceed the fixed usable-pool cap; paired usable losses therefore remain explicit.",
        "observed_gate": {"threshold": .95, "status": status, "overall_threshold_met": bool(numeric),
                          "nonempty_route_thresholds_met": bool(stratified), "statistical_support": "DESCRIPTIVE_ONLY"},
        "episodes": {"count": len(episodes), "all_recalled": sum(r["all_recalled"] for r in episodes),
                     "any_recalled": sum(r["any_recalled"] for r in episodes),
                     "longest_missing_run": max((r["longest_missing_run"] for r in episodes), default=0),
                     "denominator_note": "Episodes are reported separately per mode/channel; duplicate views are not independent RF observations."},
        "construction_checks": {"raw_preserved_all": all(r["raw_preserved"] for r in rows),
                                "expected_packet_mode_count": len(rows) == 12640},
        "claims": "Candidate availability only. No FP replacement, detection precision, polarization improvement, EKF improvement, noise robustness or environment-generalization claim.",
        "E1_02_E5_GO": False, "E2_GO": False, "external_independent_accept": False,
        "statistical_limits": "No IID packet confidence interval. These are exposed same-RF records; routes, temporal episodes and six static coordinate clusters are disclosed.",
    }
    static_summary = [{"coordinate": k[0], "channel": k[1], "mode": k[2],
                       "condition_ids": [r["condition_id"] for r in v], **counts(v)} for k, v in sorted(statics.items())]
    return summary, episodes, static_summary


def writer(stack, path, fields, compressed=False):
    if compressed:
        raw = stack.enter_context(path.open("xb"))
        compressed_stream = stack.enter_context(gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0))
        text_stream = stack.enter_context(io.TextIOWrapper(compressed_stream, encoding="utf-8", newline=""))
    else:
        text_stream = stack.enter_context(path.open("x", encoding="utf-8", newline=""))
    result = csv.DictWriter(text_stream, fieldnames=fields, extrasaction="raise")
    result.writeheader()
    return result


def _array(a, shape, dtype, label):
    if a.shape != shape or a.dtype != np.dtype(dtype) or not np.isfinite(a).all():
        raise ValueError("INVALID_ARRAY: " + label)
    return a


def execute(lock_path, approval_path, output):
    # Nothing that transforms any input waveform, computes a label, or writes
    # an output occurs before this stage-specific fail-closed guard succeeds.
    verification = verify_e1_lock(REPO, Path(lock_path), Path(approval_path))
    lock = json.loads(Path(lock_path).read_text())
    spec = json.loads((REPO / lock["policy_spec_file"]).read_text())
    validate_spec(spec)
    locked_paths = [entry["path"] for entry in json.loads((REPO / lock["input_lock_file"]).read_text())["files"]]
    if len(locked_paths) != 35 or set(locked_paths) != set(input_paths(REPO)):
        raise ValueError("E1_EXACT_INPUT_SET_MISMATCH")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"schema": "FP_SC_E1_01_RUN_MANIFEST_V1", "stage": "E1-01", "status": "RUNNING",
        "utc_start": utc_now(), "command_line": sys.argv, "role": "IMPLEMENTER",
        "implementation_commit": lock["implementation_commit"], "execution_commit": git_head(REPO),
        "execution_lock_sha256": sha256(lock_path), "approval_sha256": sha256(approval_path),
        "input_lock_sha256": sha256(REPO / lock["input_lock_file"]),
        "environment_lock_sha256": sha256(REPO / lock["environment_file"]),
        "policy_spec_sha256": sha256(REPO / lock["policy_spec_file"]),
        "code_lock_sha256": sha256(REPO / lock["code_lock_file"]),
        "qualified_H0_gate_sha256": sha256(REPO / lock["prerequisite_gate_file"]),
        "pre_execution": verification, "run_scope": SCOPE, "actual_waveforms": 0,
        "actual_packet_mode_rows": 0, "selector_runs": 0, "ekf_runs": 0, "new_rt": 0,
        "parameter_settings": 1, "external_independent_accept": False, "E1_02_E5_GO": False}
    write_json(output / "RUN_MANIFEST.json", manifest)
    failures, rows = [], []
    try:
        frequencies = np.load(REPO / RF / "freqs_hz.npy", allow_pickle=False)
        _array(frequencies, (257,), "float64", "frequencies")
        if not np.array_equal(frequencies, 6_250_400_000.0 + np.arange(257) * 1_950_000.0):
            raise ValueError("FREQUENCY_GRID_CHANGED")
        with ExitStack() as stack:
            packet_writer = writer(stack, output / "PACKET_CANDIDATE_COVERAGE.csv", PACKET_FIELDS)
            candidate_writer = writer(stack, output / "CANDIDATES.csv.gz", CANDIDATE_FIELDS, True)
            lobe_writer = writer(stack, output / "LOBE_RECORDS.csv.gz", LOBE_FIELDS, True)

            def process(meta, current_cir, reference_cir):
                pools = generate_pools(current_cir, CONFIG)
                # The reference is calculated only after both pure CIR pools
                # exist. It never enters a generator API or a pool hash.
                reference = reference_observation(reference_cir)
                for lobe in pools["TWO_PORT_UNION"]["lobes"]:
                    item = {key: lobe.get(key) for key in LOBE_FIELDS if key not in ("packet_uid", "candidate_taps_json")}
                    item.update(packet_uid=meta["packet_uid"], candidate_taps_json=json_cell(lobe["candidate_taps"]))
                    lobe_writer.writerow(item)
                for mode in MODES:
                    pool = pools[mode]
                    row = {**meta, "mode": mode, **classify(pool, reference)}
                    if not row["raw_preserved"]:
                        raise RuntimeError("ORIGINAL_FALLBACK_NOT_PRESERVED")
                    packet_writer.writerow(row)
                    rows.append(row)
                    for candidate in pool["candidates"]:
                        item = {key: candidate.get(key) for key in CANDIDATE_FIELDS if key not in (
                            "packet_uid", "mode", "support_ports_json", "lobe_ids_json", "group_ids_json", "support_records_json")}
                        item.update(packet_uid=meta["packet_uid"], mode=mode)
                        for key in ("support_ports", "lobe_ids", "group_ids", "support_records"):
                            item[key + "_json"] = json_cell(candidate[key])
                        candidate_writer.writerow(item)
                manifest["actual_waveforms"] += 1
                manifest["actual_packet_mode_rows"] += 2

            for route, count in ROUTES.items():
                print("START_DYNAMIC", route, flush=True)
                packet_path = REPO / C1A / "FROZEN_PACKETS/algorithm_input" / f"{route}_aB_m0_B0_Full.npz"
                with np.load(packet_path, allow_pickle=False) as packet:
                    pose_ids = packet["pose_id"].copy()
                    times = packet["t"].copy()
                _array(pose_ids, (count,), "int64", route + " pose_ids")
                _array(times, (count,), "float64", route + " times")
                if (pose_ids.min() < 0 or pose_ids.max() >= SOURCE_LENGTHS[route]
                        or np.any(np.diff(pose_ids) <= 0) or np.any(np.diff(times) <= 0)):
                    raise ValueError("POSE_TIME_ALIGNMENT_INVALID: " + route)
                full = np.load(REPO / RF / "FULL_RF" / f"H_{route}_aB_m0.npy", mmap_mode="r", allow_pickle=False)
                los = np.load(REPO / RF / f"H_LoS_{route}_aB_m0.npy", mmap_mode="r", allow_pickle=False)
                for label, h in (("Full", full), ("Native_LoS", los)):
                    if h.shape != (SOURCE_LENGTHS[route], 257, 2, 2) or h.dtype != np.dtype("complex128"):
                        raise ValueError("RAW_H_SCHEMA_MISMATCH: " + route + ":" + label)
                for start in range(0, count, 64):
                    ids = pose_ids[start:start + 64]
                    selected = {"Full": np.asarray(full[ids, :, :, 0]), "Native_LoS": np.asarray(los[ids, :, :, 0])}
                    if not all(np.isfinite(h).all() for h in selected.values()):
                        raise ValueError("NONFINITE_DYNAMIC_SPECTRUM: " + route)
                    cirs = {channel: observation.cir_batch(h) for channel, h in selected.items()}
                    for index, pose in enumerate(ids):
                        for channel in CHANNELS:
                            meta = {"packet_uid": f"dynamic:{route}:{int(pose)}:{channel}", "corpus": "dynamic",
                                "route": route, "coordinate": None, "condition_id": None, "yaw_deg": None,
                                "pose_id": int(pose), "t_s": float(times[start + index]), "channel": channel}
                            process(meta, cirs[channel][index], cirs["Native_LoS"][index])
                print("FINISH_DYNAMIC", route, "waveforms", count * 2, flush=True)
                write_json(output / "RUN_MANIFEST.json", manifest)

            for condition in _conditions(REPO):
                cid = condition["condition_id"]
                with np.load(REPO / G4 / cid / "FIELDS_AND_WINDOWS.npz", allow_pickle=False) as fields:
                    selected = {"Full": fields["full_spectrum"].copy(), "Native_LoS": fields["direct_spectrum"].copy()}
                for channel, h in selected.items():
                    _array(h, (257, 2), "complex128", cid + ":" + channel)
                cirs = {channel: observation.cir_batch(h[None])[0] for channel, h in selected.items()}
                for channel in CHANNELS:
                    meta = {"packet_uid": f"static_g4:{cid}:{channel}", "corpus": "static_g4", "route": None,
                        "coordinate": condition["coordinate"], "condition_id": cid, "yaw_deg": float(condition["yaw_deg"]),
                        "pose_id": None, "t_s": None, "channel": channel}
                    process(meta, cirs[channel], cirs["Native_LoS"])

        if manifest["actual_waveforms"] != 6320 or len(rows) != 12640:
            raise RuntimeError("E1_OUTPUT_SCOPE_COUNT_MISMATCH")
        if len({(r["packet_uid"], r["mode"]) for r in rows}) != len(rows):
            raise RuntimeError("DUPLICATE_PACKET_MODE_ID")
        summary, episodes, static_summary = summarize(rows)
        write_json(output / "SUMMARY.json", summary)
        write_json(output / "STATIC_COORDINATE_SUMMARY.json", static_summary)
        with (output / "EPISODES.csv").open("x", encoding="utf-8", newline="") as handle:
            episode_writer = csv.DictWriter(handle, fieldnames=EPISODE_FIELDS)
            episode_writer.writeheader()
            episode_writer.writerows(episodes)
        manifest["status"] = "COMPLETED_PENDING_SEPARATE_RESULT_REVIEW"
        manifest["observed_gate_status"] = summary["observed_gate"]["status"]
    except Exception as exc:
        failures.append({"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()})
        manifest["status"] = "FAILED_PARTIAL_OUTPUTS_PRESERVED"
        raise
    finally:
        manifest["utc_end"] = utc_now()
        manifest["failure_count"] = len(failures)
        write_json(output / "FAILURE_LEDGER.json", {"failures": failures, "excluded_input_rows": 0,
            "policy": "Fail closed on missing/malformed inputs; no post-hoc exclusion or retry with changed parameters."})
        write_json(output / "RUN_MANIFEST.json", manifest)
        hashes = {path.relative_to(output).as_posix(): sha256(path) for path in sorted(output.rglob("*"))
                  if path.is_file() and path.name != "ARTIFACT_HASHES.json"}
        write_json(output / "ARTIFACT_HASHES.json", hashes)
    print(json_cell({"status": manifest["status"], "packet_mode_rows": len(rows), "E2_GO": False}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--spec", type=Path, required=True)
    prep.add_argument("--dest", type=Path, default=REPO / E1)
    prep.add_argument("--checker", type=Path)
    run = commands.add_parser("run")
    run.add_argument("--lock", type=Path, required=True)
    run.add_argument("--approval", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    argsv = sys.argv[1:]
    if argsv and argsv[0] == "--lock":
        argsv = ["run", *argsv]
    args = parser.parse_args(argsv)
    if args.command == "prepare":
        prepare(args.spec, args.dest, args.checker)
    else:
        execute(args.lock, args.approval, args.output)


if __name__ == "__main__":
    main()
