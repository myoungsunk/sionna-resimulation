"""Verify the bounded G6-regenerated release and its S1 eligibility evidence.

The old root is metadata-only: this verifier never opens old H or path payloads.
It reads new payloads only for the two regenerated cases, G4/G8, and seal hashes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import platform
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from validate_tb3_g4 import load_model, evaluate_case


TARGETS = {"G-T2_B": {1708: 52}, "G-T2_C": {1025: 46, 1840: 55, 2477: 56}}
REPLACED = set(TARGETS)
SEALED = ("G-T2_A", "G-T2_B", "G-T2_C", "G-V_A", "G-V_B", "G-V_C")
PRESERVED = tuple(case for case in SEALED if case not in REPLACED)
STRICT_TOL_S = 5e-14
GOVERNANCE_SHA256 = {
    "COMMON_CONTRACT.md": "a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
    "ROLE_IMPLEMENTER.md": "2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da",
}
METADATA_FILES = ("rf_poses.json", "rf_tasks.json", "TIMELINE.csv", "SAMPLES.json", "SCENE_ENTRY.json")
PAYLOADS = ("H/{case}/H_full.npy", "H/{case}/H_LoS.npy", "paths/{case}/PATHS_LoS.npz",
            "paths/{case}/PATHS_NEAR.npz")
SEAL_FILES = ("H/{case}/H_full.npy", "H/{case}/H_LoS.npy", "paths/{case}/PATHS_NEAR.npz")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_identity(archive_commit):
    if archive_commit is not None:
        require(re.fullmatch(r"[0-9a-f]{40}", archive_commit), "Invalid archived source revision")
        return dict(head=archive_commit, source="git archive")
    repo = Path(__file__).resolve().parents[2]
    def git(*args):
        result = subprocess.run(["git", "-C", str(repo), *args], check=True,
                                capture_output=True, text=True)
        return result.stdout.strip()
    return dict(repository=str(repo), branch=git("branch", "--show-current"),
                head=git("rev-parse", "HEAD"), dirty=bool(git("status", "--porcelain")))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def result_root(root: Path) -> Path:
    return root / "results" if not (root / "H").exists() and (root / "results").exists() else root


def case_metadata(root: Path, case: str):
    base = root / "poses" / case
    values = {}
    for name in METADATA_FILES:
        path = base / name
        if not path.is_file():
            raise FileNotFoundError(path)
        values[name] = file_sha(path)
    return values


def case_manifest(root: Path, case: str):
    path = root / "H" / case / "MANIFEST.json"
    value = read_json(path)
    require(value.get("case") == case and value.get("status") == "PASS",
            f"Invalid production case manifest: {path}")
    return path, value


def indexed_tasks(root: Path, case: str):
    poses = read_json(root / "poses" / case / "rf_poses.json")
    tasks = read_json(root / "poses" / case / "rf_tasks.json")
    require([p.get("pose_id") for p in poses] == list(range(len(poses))),
            f"Noncanonical RF pose IDs: {case}")
    require([t.get("task_id") for t in tasks] == list(range(len(tasks))),
            f"Noncanonical RF task IDs: {case}")
    require(all(sorted(set(t.get("pose_ids", []))) == t.get("pose_ids", []) for t in tasks),
            f"Invalid task pose references: {case}")
    require(sorted(i for task in tasks for i in task["pose_ids"]) == list(range(len(poses))),
            f"Tasks do not partition pose table: {case}")
    return poses, {t["task_id"]: t for t in tasks}


def receipt_map(root: Path, case: str):
    path = root / "paths" / case / "TRACE_RECEIPTS.json"
    rows = read_json(path)
    require(isinstance(rows, list) and rows, f"Missing trace receipts: {path}")
    by_id = {row.get("task_id"): row for row in rows}
    require(len(by_id) == len(rows) and None not in by_id,
            f"Duplicate or missing task IDs in receipts: {path}")
    return path, by_id


def validate_g6_input(path: Path):
    report = read_json(path)
    require(report.get("status") == "FAIL" and report.get("stage") == "G6_REVALIDATION",
            "G6 input must be the frozen failing revalidation")
    require(report.get("strict_tolerance_s") == STRICT_TOL_S and report.get("strict_failures") == 4,
            "Unexpected original G6 threshold or failure count")
    require(set(report.get("cases", {})) == set(
        f"{g}_{a}" for g in ("G-T1", "G-T2", "G-V") for a in "ABC"),
        "G6 report does not cover the frozen nine production cases")
    failures = {}
    for case, tasks in TARGETS.items():
        rows = report.get("cases", {}).get(case, {}).get("failures", [])
        failures[case] = {int(row["task_id"]): int(row["path_index"]) for row in rows}
        require(failures[case] == tasks, f"Unexpected G6 failure mapping for {case}: {failures[case]}")
    all_failures = [row for case in report["cases"].values() for row in case.get("failures", [])]
    require(sum(map(len, failures.values())) == len(all_failures) == 4,
            "G6 report has failures outside the four authorized regeneration paths")
    require(all(case.get("counts", {}).get("delay_exceeded") == 0
                for case in report["cases"].values()),
            "Original G6 has delay failures outside the four image-geometry cases")
    require(all(float(case.get("max_residual_s", math.inf)) <= STRICT_TOL_S
                for case in report["cases"].values()),
            "Original G6 retained-path residual exceeded the strict limit")
    return report


def validate_original_g9(path: Path):
    report = read_json(path)
    require(report.get("question_id") == "G1-RT-TB3-002"
            and report.get("consumed_by") == "G1-MODEL-003"
            and report.get("stage") == "G9" and report.get("status") == "PASS"
            and report.get("violations") == 0 and report.get("seal_status") == "SEALED",
            "Unexpected or failing original G9 receipt")
    require(isinstance(report.get("source_commit"), str)
            and report["source_commit"].startswith("8d56c1b"),
            "Original G9 receipt does not identify the frozen source revision")
    require("no UNSEAL entry" in report.get("checks", []),
            "Original G9 receipt lacks the no-UNSEAL check")
    return report


def verify_case_lineage(old_root: Path, new_root: Path, case: str):
    old_pose_hashes = case_metadata(old_root, case)
    new_pose_hashes = case_metadata(new_root, case)
    require(old_pose_hashes == new_pose_hashes,
            f"Old/new pose/task/timeline metadata changed for {case}")
    old_poses, old_tasks = indexed_tasks(old_root, case)
    new_poses, new_tasks = indexed_tasks(new_root, case)
    require(old_poses == new_poses and old_tasks == new_tasks,
            f"Old/new G0/G7 task identities differ for {case}")
    old_manifest_path, old_manifest = case_manifest(old_root, case)
    new_manifest_path, new_manifest = case_manifest(new_root, case)
    for field in ("anchor_xyz", "robot_z", "mount_deg", "shape", "poses", "main_poses",
                  "diagnostic_new_poses", "trace_positions", "near_poses", "g0_manifest_sha256",
                  "g7_manifest_sha256", "production_sha256", "reference_sha256", "ffd_manifest_sha256", "engine"):
        if field in old_manifest or field in new_manifest:
            require(old_manifest.get(field) == new_manifest.get(field),
                    f"Old/new production identity differs for {case}/{field}")
    require(set(old_manifest.get("output_sha256", {})) == set(new_manifest.get("output_sha256", {})),
            f"Merged output key coverage differs for {case}")
    shards_old = old_manifest.get("shards", [])
    shards_new = new_manifest.get("shards", [])
    require(bool(shards_old) and bool(shards_new), f"Missing shard provenance for {case}")
    def invariant(shards):
        return {(s.get("g0_manifest_sha256"), s.get("g7_manifest_sha256"),
                 s.get("production_sha256"), s.get("reference_sha256"),
                 s.get("ffd_manifest_sha256"), s.get("case")) for s in shards}
    require(invariant(shards_old) == invariant(shards_new) and len(invariant(shards_new)) == 1,
            f"Shard input identities differ for {case}")
    commits = {s.get("code_commit") for s in shards_new}
    require(len(commits) == 1 and all(isinstance(c, str) and c.startswith("e59ace6") for c in commits),
            f"Unexpected regeneration commit for {case}: {commits}")
    return old_pose_hashes, old_manifest_path, old_manifest, new_manifest_path, new_manifest, old_tasks


def compare_trace_receipts(old_root: Path, new_root: Path, case: str, tasks, g6):
    _, old_rows = receipt_map(old_root, case)
    _, new_rows = receipt_map(new_root, case)
    require(set(old_rows) == set(new_rows) == set(tasks), f"Receipt task-key coverage differs for {case}")
    expected_reject = TARGETS[case]
    rows = []
    max_residual = 0.0
    for task_id in sorted(tasks):
        old, new = old_rows[task_id], new_rows[task_id]
        for key in ("tag", "task_id", "pose_ids", "node_bins", "solver_calls"):
            require(old.get(key) == new.get(key) == tasks[task_id].get(key, old.get(key)),
                    f"Receipt/task identity mismatch {case}/{task_id}/{key}")
        require(old.get("node_bins") and old["solver_calls"] == len(old["node_bins"]),
                f"Invalid original node coverage: {case}/{task_id}")
        require(new.get("finite_face") is not None, f"Missing finite-face receipt: {case}/{task_id}")
        geom = new["finite_face"]
        rejected = geom.get("rejected", [])
        indexes = [int(item["canonical_index"]) for item in rejected]
        if task_id in expected_reject:
            require(indexes == [expected_reject[task_id]],
                    f"Unexpected rejected path index at {case}/{task_id}: {indexes}")
            require(g6["cases"][case]["failures"] and
                    expected_reject[task_id] == next(
                        int(f["path_index"]) for f in g6["cases"][case]["failures"]
                        if int(f["task_id"]) == task_id),
                    f"Rejected index does not match frozen G6 at {case}/{task_id}")
        else:
            require(indexes == [], f"Unexpected finite-face rejection at {case}/{task_id}: {indexes}")
        native_count = int(geom.get("native_paths", -1))
        require(native_count == int(old.get("n_full_paths", -2)),
                f"Native path count changed at {case}/{task_id}")
        require(int(new.get("n_full_paths", -1)) == native_count - len(indexes),
                f"Retained path count does not match exclusions at {case}/{task_id}")
        residual = float(geom.get("max_retained_delay_residual_s", math.inf))
        require(math.isfinite(residual) and residual <= STRICT_TOL_S,
                f"Strict retained delay tolerance failed at {case}/{task_id}: {residual}")
        max_residual = max(max_residual, residual)
        rows.append(dict(task_id=task_id, native_paths=native_count,
                         retained_paths=int(new["n_full_paths"]), rejected_path_indices=indexes,
                         max_retained_delay_residual_s=residual))
    return rows, max_residual


def verify_new_case_outputs(root: Path, case: str, manifest):
    output_hashes = manifest.get("output_sha256")
    output_bytes = manifest.get("output_bytes")
    require(isinstance(output_hashes, dict) and isinstance(output_bytes, dict),
            f"Case output hashes missing for {case}")
    checked = {}
    required = {pattern.format(case=case) for pattern in PAYLOADS}
    require(required.issubset(output_hashes), f"Required production output hashes missing: {case}")
    for rel, digest in output_hashes.items():
        require(rel.startswith((f"H/{case}/", f"paths/{case}/", f"poses/{case}/")),
                f"Unexpected cross-case output in {case} manifest: {rel}")
        path = root / rel
        require(isinstance(digest, str) and len(digest) == 64 and path.is_file() and not path.is_symlink(),
                f"Missing or unmanifested new output: {path}")
        actual = file_sha(path)
        require(actual == digest, f"Output SHA mismatch: {path}")
        require(output_bytes.get(rel) == path.stat().st_size, f"Output size mismatch: {path}")
        checked[rel] = actual
    return checked


def verify_seal_marker(seal_root: Path, results: Path, case: str, manifest_path: Path, manifest):
    marker_path = seal_root / "seal" / "cases" / f"{case}.json"
    marker = read_json(marker_path)
    require(marker.get("case") == case and marker.get("case_manifest_sha256") == file_sha(manifest_path),
            f"New case seal does not bind the merged manifest: {case}")
    expected = {name.format(case=case) for name in SEAL_FILES}
    files = marker.get("files", {})
    require(set(files) == expected, f"Unexpected new case seal coverage: {case}")
    checked = {}
    for rel, entry in files.items():
        path = results / rel
        require(path.is_file() and not path.is_symlink() and not (path.stat().st_mode & 0o222),
                f"Sealed output missing, symlinked, or writable: {path}")
        digest = file_sha(path)
        require(digest == entry.get("sha256") and digest == manifest["output_sha256"].get(rel),
                f"New seal hash differs from merged output: {path}")
        require(path.stat().st_size == entry.get("bytes") == manifest["output_bytes"].get(rel),
                f"New seal byte count mismatch: {path}")
        checked[rel] = dict(bytes=path.stat().st_size, sha256=digest)
    return marker_path, marker, checked


def verify_access_log(seal_root: Path):
    path = seal_root / "seal" / "ACCESS_LOG.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    seals = [row for row in rows if row.get("operation") == "SEAL_CASE"]
    require({row.get("case") for row in seals} == REPLACED and len(seals) == 2,
            "New access log does not show exactly the two authorized case seals")
    for row in seals:
        case = row["case"]
        require(set(row.get("paths", [])) == {name.format(case=case) for name in SEAL_FILES},
                f"Unexpected paths in new case seal log: {case}")
    denied = ("UNSEAL", "HEADING", "ACCURACY", "S4/", "checkpoint_rows")
    for row in rows:
        require("UNSEAL" not in str(row.get("operation", "")).upper(),
                f"Unexpected unseal operation recorded: {row.get('operation')}")
        for value in row.get("paths", []):
            require(not any(token in value.upper() for token in denied[1:]),
                    f"Unexpected sealed-evidence path access recorded: {value}")
            if value.startswith(("H/", "paths/", "poses/")):
                require(any(value.startswith(f"{prefix}/{case}/") for prefix in ("H", "paths", "poses")
                            for case in REPLACED),
                        f"Unexpected access outside regenerated cases: {value}")
    return path, rows


def load_supplemental_g3(paths):
    reports = {}
    for path in paths:
        item = read_json(path)
        case, task_id = item.get("case"), item.get("task_id")
        require(case in TARGETS and task_id in TARGETS[case], f"Unexpected supplemental G3 report: {path}")
        require((case, task_id) not in reports, f"Duplicate supplemental G3 report: {case}/{task_id}")
        require(item.get("question_id") == "G1-MODEL-003" and item.get("status") == "PASS",
                f"Supplemental G3 did not pass: {case}/{task_id}")
        expected_code = {name: file_sha(Path(__file__).with_name(name)) for name in
                         ("validate_tb3_g6_regeneration_g3.py", "tb3_g6_face_match.py", "tb3_g6_revalidate.py")}
        require(item.get("code_sha256") == expected_code,
                f"Supplemental G3 code hashes differ from this source tree: {case}/{task_id}")
        require(item.get("g3a_bins") == 257, f"G3a did not cover all 257 bins: {case}/{task_id}")
        b, c, energy = item.get("g3b_by_pose", []), item.get("g3c_by_pose", []), item.get("g3c_energy_by_bin", [])
        thresholds = item.get("thresholds", {})
        pose_ids = item.get("pose_ids", [])
        require(0 < len(b) == len(c) == len(pose_ids) == len(set(pose_ids)) and len(energy) == 257,
                f"Supplemental G3 pose/bin coverage incomplete: {case}/{task_id}")
        require(all(row.get("abs_ds", math.inf) <= thresholds.get("abs_ds_max", -1)
                    and row.get("fp_index_match", -1) >= thresholds.get("fp_index_match_min", 2)
                    and row.get("range_diff_m", math.inf) <= thresholds.get("range_diff_max_m", -1) for row in b),
                f"Supplemental G3b metrics do not meet their frozen limits: {case}/{task_id}")
        require(all(row.get("abs_ds", math.inf) <= 0.002 for row in c)
                and max(float(row[2]) for row in energy) < 0.01,
                f"Supplemental G3c metrics do not meet their frozen limits: {case}/{task_id}")
        for name in ("nominal257", "nominal17", "high257"):
            receipt = item.get("trace_receipts", {}).get(name, {})
            rejected = receipt.get("rejected", [])
            require(len(rejected) == 1 and int(rejected[0].get("canonical_index", -1)) == TARGETS[case][task_id],
                    f"Supplemental G3 {name} trace rejection differs from G6: {case}/{task_id}")
        reports[(case, task_id)] = dict(path=str(path.resolve()), sha256=file_sha(path), status="PASS",
                                       pose_ids=pose_ids, max_abs_ds_g3b=max(row["abs_ds"] for row in b),
                                       max_abs_ds_g3c=max(row["abs_ds"] for row in c),
                                       max_added_energy_fraction=max(float(row[2]) for row in energy))
    expected = {(case, task) for case, tasks in TARGETS.items() for task in tasks}
    require(set(reports) == expected, f"Supplemental G3 report coverage differs: {set(reports)}")
    return reports


def retained_seal_provenance(old_seal_root: Path, old_results: Path, new_seals):
    old_manifest_path = old_seal_root / "seal" / "SEAL_MANIFEST.json"
    old_seal = read_json(old_manifest_path)
    require(old_seal.get("status") == "SEALED" and set(old_seal.get("cases", {})) == set(SEALED),
            "Original six-case S4 seal metadata is incomplete")
    mapping = {}
    for case in SEALED:
        old_entry = old_seal["cases"][case]
        old_marker_path = old_seal_root / "seal" / "cases" / f"{case}.json"
        old_marker = read_json(old_marker_path)
        old_h_manifest = old_results / "H" / case / "MANIFEST.json"
        require(old_marker == old_entry and old_marker.get("case_manifest_sha256") == file_sha(old_h_manifest),
                f"Original seal metadata mismatch: {case}")
        if case in REPLACED:
            new_path, new_marker, new_files = new_seals[case]
            mapping[case] = dict(source="regenerated", original_case_seal_sha256=file_sha(old_marker_path),
                                 new_case_seal_sha256=file_sha(new_path),
                                 case_manifest_sha256=new_marker["case_manifest_sha256"], files=new_files)
        else:
            # Preserve hash provenance only; the old sealed payload is never opened.
            mapping[case] = dict(source="original_preserved", original_case_seal_sha256=file_sha(old_marker_path),
                                 case_manifest_sha256=old_marker["case_manifest_sha256"],
                                 files=old_marker["files"], payload_verified_in_this_run=False)
        if case in REPLACED:
            mapping[case]["original_files"] = old_marker["files"]
    old_log = old_seal_root / "seal" / "ACCESS_LOG.jsonl"
    old_log_rows = [json.loads(line) for line in old_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in old_log_rows:
        require("UNSEAL" not in str(row.get("operation", "")).upper(),
                f"Original seal log records unseal operation: {row.get('operation')}")
        for value in row.get("paths", []):
            require(not any(token in value.upper() for token in ("HEADING", "ACCURACY", "CHECKPOINT_ROWS", "S4/")),
                    f"Original seal log records disallowed path: {value}")
    return file_sha(old_manifest_path), file_sha(old_log), mapping


def run(args):
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    old_root, new_root = result_root(args.old_results_root), result_root(args.new_results_root)
    g6 = validate_g6_input(args.g6)
    g9 = validate_original_g9(args.g9)
    supplemental = load_supplemental_g3(args.supplemental_g3)
    per_case, new_seals, access = {}, {}, {}
    model, observation, banks, frequencies, source_hashes, bank_hashes = load_model(
        SimpleNamespace(model_source=args.model_source, banks_dir=args.banks_dir))
    from run_tb3_production import NEAR_SETS
    from tb3_paths_near import check_g8

    g4_started = dt.datetime.now(dt.timezone.utc).isoformat()
    for case in sorted(REPLACED):
        (pose_hashes, old_manifest_path, old_manifest, new_manifest_path, new_manifest,
         task_map) = verify_case_lineage(old_root, new_root, case)
        for (report_case, task_id), row in supplemental.items():
            if report_case == case:
                require(row["pose_ids"] == task_map[task_id]["pose_ids"],
                        f"Supplemental G3 pose IDs differ from production: {case}/{task_id}")
        row_checks, max_residual = compare_trace_receipts(old_root, new_root, case, task_map, g6)
        output_hashes = verify_new_case_outputs(new_root, case, new_manifest)
        new_seals[case] = verify_seal_marker(args.new_seal_root, new_root, case, new_manifest_path, new_manifest)
        old_h_hash = old_manifest.get("los_H_sha256") or old_manifest.get("H_sha256")
        require(isinstance(old_h_hash, str) and len(old_h_hash) == 64,
                f"Old metadata does not provide known H_LoS hash: {case}")
        new_h_hash = output_hashes[f"H/{case}/H_LoS.npy"]
        require(new_h_hash == old_h_hash, f"Regenerated H_LoS differs from original: {case}")
        new_g4 = evaluate_case(new_root, case, model, observation, banks, frequencies)
        require(new_g4["status"] == "PASS", f"G4 fails on regenerated case {case}")
        new_g4.pop("_delta_by_pose", None)
        samples = read_json(new_root / "poses" / case / "SAMPLES.json")
        pose_ids = sorted({int(row["pose_id"]) for row in samples if row["set"] in NEAR_SETS})
        require(len(pose_ids) == new_manifest["near_poses"], f"G8 export pose count differs: {case}")
        h_los = np.load(new_root / "H" / case / "H_LoS.npy", mmap_mode="r", allow_pickle=False)
        new_g8 = check_g8(new_root / "paths" / case / "PATHS_NEAR.npz",
                          h_los[pose_ids], pose_ids)
        require(new_g8["status"] == "PASS", f"G8 fails on regenerated case {case}")
        access[case] = dict(g4_h_los=f"H/{case}/H_LoS.npy", g4_paths_los=f"paths/{case}/PATHS_LoS.npz",
                            g8_h_los=f"H/{case}/H_LoS.npy", g8_paths_near=f"paths/{case}/PATHS_NEAR.npz")
        per_case[case] = dict(status="PASS", metadata_sha256=pose_hashes,
                              old_case_manifest_sha256=file_sha(old_manifest_path),
                              new_case_manifest_sha256=file_sha(new_manifest_path),
                              output_sha256=output_hashes, task_receipts=row_checks,
                              max_retained_delay_residual_s=max_residual,
                              old_h_los_sha256=old_h_hash, new_h_los_sha256=new_h_hash,
                              g4=new_g4, g8=new_g8, supplemental_g3={str(k[1]): v for k, v in supplemental.items() if k[0] == case})
    g4_finished = dt.datetime.now(dt.timezone.utc).isoformat()
    access_path, access_rows = verify_access_log(args.new_seal_root)
    old_seal_sha, old_access_sha, seal_mapping = retained_seal_provenance(
        args.old_seal_root, old_root, new_seals)
    require(g9.get("input_sha256", {}).get("SEAL_MANIFEST.json") == old_seal_sha,
            "Original G9 receipt does not bind the mounted original seal manifest")
    finished = dt.datetime.now(dt.timezone.utc).isoformat()
    report = dict(
        question_id="G1-MODEL-003", role="IMPLEMENTER", stage="G6_REGENERATED_RELEASE_VERIFICATION",
        status="PASS", s1_eligibility="PENDING_PARENT_PRIOR_GATE_LEDGER",
        interpretation="This verifier covers G6 regeneration, supplemental G3, new-case G4/G8 and six-case seal provenance; the parent must integrate prior G0–G8 and S0 evidence before declaring S1 eligible. No heading or accuracy output is computed.",
        g6=dict(status="PASS", original_status=g6["status"], original_strict_failures=g6["strict_failures"],
                strict_tolerance_s=STRICT_TOL_S, removed_indices=TARGETS,
                retained_max_residual_s=max(case["max_retained_delay_residual_s"] for case in per_case.values())),
        original_g9=dict(status="PASS", gate="G9", source_commit=g9["source_commit"],
                         sha256=file_sha(args.g9), path=str(args.g9.resolve())),
        supplemental_g3={f"{case}/{task}": row for (case, task), row in supplemental.items()},
        regenerated_cases=per_case,
        seal_provenance=dict(status="PASS", original_seal_manifest_sha256=old_seal_sha,
                             original_access_log_sha256=old_access_sha, cases=seal_mapping),
        access=dict(policy="new-case G4/G8 and seal/hash checks only; no old H/path payload read",
                    g4_start_utc=g4_started, g4_finish_utc=g4_finished,
                    g4_g8_payloads=access, new_access_log_sha256=file_sha(access_path),
                    new_access_log_entries=len(access_rows), old_payloads_opened=False,
                    heading_computed=False, accuracy_computed=False),
        inputs_sha256={"g6": file_sha(args.g6), "g9": file_sha(args.g9),
                       **{f"g3_{case}_{task}": row["sha256"] for (case, task), row in supplemental.items()}},
        governance_sha256=GOVERNANCE_SHA256,
        source_sha256={Path(__file__).name: file_sha(Path(__file__)),
                       "validate_tb3_g4.py": file_sha(Path(__file__).with_name("validate_tb3_g4.py")),
                       "tb3_paths_near.py": file_sha(Path(__file__).with_name("tb3_paths_near.py")),
                       "seal_tb3_production.py": file_sha(Path(__file__).with_name("seal_tb3_production.py"))},
        g1_model_source_sha256=source_hashes, ffd_bank_sha256=bank_hashes,
        execution=dict(host=platform.node(), python=sys.version.split()[0], numpy=np.__version__,
                       started_utc=started, finished_utc=finished, command=[sys.executable, *sys.argv],
                       git=git_identity(args.archive_commit)),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-commit")
    parser.add_argument("--old-results-root", type=Path, required=True,
                        help="Original results tree; metadata only, no old H/path payloads")
    parser.add_argument("--old-seal-root", type=Path, required=True,
                        help="Original production run root containing seal metadata")
    parser.add_argument("--new-results-root", type=Path, required=True,
                        help="Merged B/C regeneration results tree")
    parser.add_argument("--new-seal-root", type=Path, required=True,
                        help="Regeneration run root containing the two new case seals")
    parser.add_argument("--g6", type=Path, required=True, help="Latest original public G6 revalidation JSON")
    parser.add_argument("--g9", type=Path, required=True, help="Original G9 receipt")
    parser.add_argument("--supplemental-g3", type=Path, nargs=4, required=True,
                        help="Four per-task G3 supplemental JSONs")
    parser.add_argument("--model-source", type=Path, required=True)
    parser.add_argument("--banks-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    print(f"G6 regenerated release {report['status']}; S1 eligibility={report['s1_eligibility']}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
