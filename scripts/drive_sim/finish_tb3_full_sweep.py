"""Assemble verified dual-mount sweep shards and run the frozen G4 check."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

import numpy as np

import validate_tb3_g4 as g4
from merge_tb3_production import LOS_ANGLES, fill_los, load_near, write_path_summary
from seal_tb3_production import SEALED_CASES, finalize, g4_access, seal_case, verify_seal


MOUNTS = (0, 45)
FILES = ("H_full.npy", "H_LoS.npy", "POSE_IDS.npy", "PATHS_LoS.npz",
         "PATHS_NEAR.npz", "PATHS_NEAR_SCHEMA.json")
POSE_FILES = ("rf_poses.json", "rf_tasks.json", "SCENE_ENTRY.json", "SAMPLES.json",
              "TIMELINE.csv", "SWEEP_BASES.json")
ANGLES = list(range(-180, 181, 10))
NODE_BINS = list(range(0, 257, 16))


def read(path):
    return json.loads(path.read_bytes())


def write(path, payload):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_inputs(inputs, case):
    source = inputs / "poses" / case
    manifest = read(inputs / "SWEEP_MANIFEST.json")
    if set(manifest["cases"]) != set(g4.CASES) or manifest["mount_deg"] != list(MOUNTS):
        raise ValueError("Sweep manifest has incorrect case or mount coverage")
    for filename in POSE_FILES:
        if sha(source / filename) != manifest["output_sha256"][f"poses/{case}/{filename}"]:
            raise ValueError(f"{case}: sweep input table changed: {filename}")
    poses = read(source / "rf_poses.json")
    tasks = read(source / "rf_tasks.json")
    rows = read(source / "SAMPLES.json")
    bases = read(source / "SWEEP_BASES.json")
    expected_by_set = ({"P-F": 18} if case.endswith("_P-F") else
                       {"P-A_TEACH": 18, "P-A_REPEAT": 18, "P-E": 54})
    if case.startswith("G-T1") and not case.endswith("_P-F"):
        expected_by_set["P-D"] = 360
    if (manifest["cases"][case]["bases_by_set"] != expected_by_set
            or len(bases) != sum(expected_by_set.values()) or len(tasks) != len(bases)):
        raise ValueError(f"{case}: wrong frozen base coverage")
    if [p["pose_id"] for p in poses] != list(range(len(poses))):
        raise ValueError(f"{case}: noncontiguous RF IDs")
    if [t["task_id"] for t in tasks] != list(range(len(tasks))):
        raise ValueError(f"{case}: noncontiguous trace task IDs")
    if sorted(i for task in tasks for i in task["pose_ids"]) != list(range(len(poses))):
        raise ValueError(f"{case}: trace task IDs do not partition all RF poses")
    if len(rows) != 37 * len(tasks) or len(poses) != 36 * len(tasks):
        raise ValueError(f"{case}: wrong sweep observation or RF pose count")
    for base, start in zip(bases, range(0, len(rows), 37), strict=True):
        group = rows[start:start+37]
        ids = [r["pose_id"] for r in group]
        if ([r["planned_rel_deg"] for r in group] != ANGLES
                or [r["achieved_rel_deg"] for r in group] != ANGLES
                or ids[0] != ids[-1] or len(set(ids)) != 36
                or any((row["base_id"], row["set"], row["station_id"]) !=
                       (base["base_id"], base["set"], base["station_id"]) for row in group)):
            raise ValueError(f"{case}: invalid 37-angle sweep at base {base['base_id']}")
        yaw = [poses[i]["yaw_body_deg"] for i in ids]
        for angle, value in zip(ANGLES, yaw, strict=True):
            if abs((value - base["baseline_body_yaw_deg"] - angle + 180) % 360 - 180) >= 1e-6:
                raise ValueError(f"{case}: RX sweep yaw does not follow the body yaw")
        if any((poses[i]["x"], poses[i]["y"]) != (base["x"], base["y"]) for i in ids):
            raise ValueError(f"{case}: sweep angles do not share their frozen position")
    if sorted({r["pose_id"] for r in rows}) != list(range(len(poses))):
        raise ValueError(f"{case}: incomplete observation pose references")
    return source, poses, tasks, rows


def assemble(args, case):
    source, poses, tasks, rows = validate_inputs(args.inputs, case)
    folders = sorted((args.shards / case).iterdir())
    if not folders or [p.name for p in folders] != [f"{i:03d}" for i in range(len(folders))]:
        raise ValueError(f"{case}: missing or unordered shard directories")
    selected = []
    receipts = []
    source_digest = sha(args.inputs / "SWEEP_MANIFEST.json")
    files = {"TRACE_RECEIPTS.json", *(f"mount{m}/{f}" for m in MOUNTS for f in FILES)}
    for index, folder in enumerate(folders):
        expected_tasks = tasks[index::len(folders)]
        ids = np.array(sorted(i for t in expected_tasks for i in t["pose_ids"]), dtype=np.int64)
        manifest_path = folder / "MANIFEST.json"
        manifest = read(manifest_path)
        if (manifest["status"] != "PASS" or manifest["scope"] != "FULL_SWEEP"
                or manifest["case"] != case or manifest["code_commit"] != args.code_commit
                or manifest["mounts_deg"] != list(MOUNTS) or not manifest["shared_trace"]
                or manifest["engine"]["finite_face_guard"]["stage"] != "PRE_FIELD"
                or manifest["sweep_manifest_sha256"] != source_digest
                or (manifest["shard_index"], manifest["shard_count"]) != (index, len(folders))
                or manifest["trace_positions"] != len(expected_tasks)
                or manifest["poses"] != len(ids) or manifest["near_pose_count"] != len(ids)
                or manifest["solver_calls"] != 17 * len(expected_tasks)
                or manifest["extra_export_solver_calls"] != 0
                or set(manifest["output_sha256"]) != files or set(manifest["output_bytes"]) != files):
            raise ValueError(f"Incomplete or mismatched shard manifest: {manifest_path}")
        for filename in sorted(files):
            path = folder / filename
            if (path.is_symlink() or path.stat().st_size != manifest["output_bytes"][filename]
                    or sha(path) != manifest["output_sha256"][filename]):
                raise ValueError(f"Shard artifact changed: {path}")
        shard_receipts = read(folder / "TRACE_RECEIPTS.json")
        for task, receipt in zip(expected_tasks, shard_receipts, strict=True):
            if (any(receipt[k] != task[k] for k in ("task_id", "pose_ids"))
                    or receipt["node_bins"] != NODE_BINS or receipt["solver_calls"] != 17
                    or receipt["n_full_paths"] < 1 or receipt["n_near_paths"] < 1):
                raise ValueError(f"{case}: incomplete F1 trace receipt for task {task['task_id']}")
        receipts.extend(shard_receipts)
        selected.append((folder, ids))
    receipts.sort(key=lambda x: x["task_id"])
    case_report = {}
    frequencies = None
    for mount in MOUNTS:
        root = args.out / f"mount{mount}"
        h_dir, p_dir, m_dir = (root / sub / case for sub in ("H", "paths", "poses"))
        for folder in (h_dir, p_dir, m_dir):
            folder.mkdir(parents=True, mode=0o700)
        shape = (len(poses), 257, 2, 2)
        keys = ("H_full.npy", "H_LoS.npy")
        h = {k: np.lib.format.open_memmap(h_dir / k, mode="w+", dtype=np.complex128, shape=shape)
             for k in keys}
        los = dict(a=np.empty(shape, np.complex128), tau=np.empty(shape[:2], np.float64),
                   counts=np.empty(shape[:2], np.int64), interactions=np.empty(shape[:2], np.int64),
                   **{key: np.empty(shape[:2], np.float64) for key in LOS_ANGLES})
        all_near = []
        schema = None
        for folder, ids in selected:
            directory = folder / f"mount{mount}"
            actual = np.load(directory / "POSE_IDS.npy", allow_pickle=False)
            if actual.dtype != np.int64 or not np.array_equal(actual, ids):
                raise ValueError(f"Invalid shard pose row order: {directory}")
            with np.load(directory / "PATHS_LoS.npz", allow_pickle=False) as pack:
                grid = pack["freqs_hz"]
            if (grid.dtype != np.float64 or grid.shape != (257,) or not np.isfinite(grid).all()
                    or np.any(np.diff(grid) <= 0)
                    or (frequencies is not None and not np.array_equal(grid, frequencies))):
                raise ValueError(f"Invalid/inconsistent frequency grid: {directory}")
            frequencies = grid
            for filename in keys:
                channel = np.load(directory / filename, mmap_mode="r", allow_pickle=False)
                if (channel.shape != (len(ids), *shape[1:]) or channel.dtype != np.complex128
                        or not np.isfinite(channel).all()):
                    raise ValueError(f"Invalid H shard: {directory / filename}")
                h[filename][ids] = channel
            fill_los(los, directory, ids, frequencies, h["H_LoS.npy"][ids])
            candidate = read(directory / "PATHS_NEAR_SCHEMA.json")
            if schema is not None and schema != candidate:
                raise ValueError(f"PATHS_NEAR schema varies within case {case}")
            schema = candidate
            all_near.append(load_near(directory, set(ids.tolist()), h["H_LoS.npy"], frequencies))
        for mapping in h.values():
            mapping.flush()
        del h, mapping
        np.savez_compressed(p_dir / "PATHS_LoS.npz", pose_id=np.arange(len(poses), dtype=np.int64),
                            freqs_hz=frequencies, **los)
        del los
        merged = {key: np.concatenate([part[key] for part in all_near]) for key in all_near[0]}
        del all_near
        order = np.lexsort((merged["path_index"], merged["pose_id"]))
        count_by_pose = np.bincount(merged["pose_id"], minlength=len(poses))
        expected_count = np.empty(len(poses), dtype=np.int64)
        for receipt in receipts:
            expected_count[receipt["pose_ids"]] = receipt["n_near_paths"]
        if not np.array_equal(count_by_pose, expected_count):
            raise ValueError(f"{case}: PATHS_NEAR coverage disagrees with shared trace receipts")
        geometry_keys = sorted(set(merged) - {"coefficients"})
        identity = hashlib.sha256()
        for key in geometry_keys:
            identity.update(merged[key][order].tobytes())
        geometry_digest = identity.hexdigest()
        np.savez_compressed(p_dir / "PATHS_NEAR.npz", frequencies_hz=frequencies,
                            **{key: value[order] for key, value in merged.items()})
        del merged
        write(p_dir / "PATHS_NEAR_SCHEMA.json", schema)
        write(p_dir / "TRACE_RECEIPTS.json", receipts)
        write_path_summary(p_dir, receipts, rows)
        for filename in POSE_FILES:
            shutil.copyfile(source / filename, m_dir / filename)
        files = sorted(f for folder in (h_dir, p_dir, m_dir) for f in folder.iterdir())
        record = dict(case=case, status="PASS", mount_deg=mount, poses=len(poses),
                      observation_rows=len(rows), trace_positions=len(tasks),
                      solver_calls_shared_between_mounts=17*len(tasks),
                      path_geometry_sha256=geometry_digest, shape=list(shape),
                      output_sha256={f.relative_to(root).as_posix(): sha(f) for f in files},
                      output_bytes={f.relative_to(root).as_posix(): f.stat().st_size for f in files})
        write(h_dir / "MANIFEST.json", record)
        case_report[f"mount{mount}"] = record
        if case in SEALED_CASES:
            seal_case(root, case)
            for folder, _ in selected:
                for filename in FILES:
                    path = folder / f"mount{mount}" / filename
                    path.chmod(path.stat().st_mode & ~0o222)
    if len({r["path_geometry_sha256"] for r in case_report.values()}) != 1:
        raise ValueError(f"{case}: shared PATHS_NEAR path geometry differs by mount")
    write(args.out / f"{case}.json", case_report)
    print(f"{case}: {len(tasks)} traces, {len(poses)} poses per mount", flush=True)


def check_g4(args, mount):
    started = time.monotonic()
    root = args.out / f"mount{mount}"
    g4.MOUNT_DEG = float(mount)
    args.results_root = root
    gate = root / "gates" / "G4.json"
    gate.parent.mkdir(exist_ok=True)
    finalize(root)
    g4_access(root, "START", Path(__file__), gate)
    try:
        report = g4.run(args)
        report["execution"]["elapsed_seconds"] = time.monotonic() - started
        write(gate, report)
    finally:
        g4_access(root, "FINISH", Path(__file__), gate)
        verify_seal(root, gate.with_name("SEAL_STORAGE_CHECK.json"))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "shards", "out", "model-source", "banks-dir"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--case", choices=g4.CASES)
    group.add_argument("--g4", action="store_true")
    group.add_argument("--pilot", choices=[case for case in g4.CASES if case.endswith("_P-F")])
    args = parser.parse_args()
    if args.case:
        assemble(args, args.case)
        return 0
    if args.pilot:
        model, observation, banks, freqs, _, _ = g4.load_model(args)
        reports = {}
        for mount in MOUNTS:
            g4.MOUNT_DEG = float(mount)
            report = g4.evaluate_case(args.out / f"mount{mount}", args.pilot, model,
                                      observation, banks, freqs)
            del report["_delta_by_pose"]
            reports[f"mount{mount}"] = report
        write(args.out / "PILOT_G4.json", reports)
        return int(any(r["status"] != "PASS" for r in reports.values()))
    results = {case: read(args.out / f"{case}.json") for case in g4.CASES}
    reports = {f"mount{mount}": check_g4(args, mount) for mount in MOUNTS}
    status = "PASS" if all(report["status"] == "PASS" for report in reports.values()) else "FAIL"
    write(args.out / "COMPLETION.json", dict(
        status=status, cases=len(results), solver_calls=sum(
            x["mount0"]["solver_calls_shared_between_mounts"] for x in results.values()),
        mount_reports={mount: dict(poses=sum(v[mount]["poses"] for v in results.values()),
                                  observation_rows=sum(v[mount]["observation_rows"] for v in results.values()),
                                  payload_bytes=sum(sum(v[mount]["output_bytes"].values()) for v in results.values()),
                                  g4_elapsed_s=report["execution"]["elapsed_seconds"],
                                  g4_status=report["status"],
                                  max_p90_abs_delta_s=max(
                                      row["p90_abs_delta_s"] for case in report["cases"].values()
                                      for row in case["gate_by_arm"].values()),
                                  max_abs_delta_s=max(
                                      case["unique_pose_metrics"]["max_abs_delta_s"]
                                      for case in report["cases"].values()))
                       for mount, report in reports.items()}))
    return int(status != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
