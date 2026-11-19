"""Assemble one complete output case from verified Snowball F1 shards."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from pathlib import Path
import sys
import time

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_production import (
    CASES, F1_SHA, FFD_SHA, G0_SHA, G7_SHA, NEAR_SETS, REFERENCE_SHA, case_inputs, utc_now, verify,
)


LOS_ANGLES = ("theta_t", "phi_t", "theta_r", "phi_r")
LOS_NAMES = {"pose_id", "a", "tau", "counts", "interactions", "freqs_hz", *LOS_ANGLES}
NEAR_NAMES = {
    "frequencies_hz", "pose_id", "path_index", "tau_s", "delay_m", "coefficients",
    "interaction_count", "interactions", "objects", "aod_az_el_rad", "aoa_az_el_rad", "is_los",
}
SHARD_FILES = {"H_full.npy", "H_LoS.npy", "POSE_IDS.npy", "PATHS_LoS.npz", "TRACE_RECEIPTS.json"}
NEAR_FILES = {"PATHS_NEAR.npz", "PATHS_NEAR_SCHEMA.json"}


def load_shards(root, case, tasks, near_ids):
    directories = sorted(path for path in root.iterdir() if path.is_dir())
    count = len(directories)
    if not count or [p.name for p in directories] != [f"{i:03d}" for i in range(count)]:
        raise ValueError("Expected exactly the shard folders 000, 001, ...")
    frozen = dict(g0_manifest_sha256=G0_SHA, g7_manifest_sha256=G7_SHA, production_sha256=F1_SHA,
                  ffd_manifest_sha256=FFD_SHA, reference_sha256=REFERENCE_SHA)
    invariant = ("engine", "code_commit", "source_sha256", "runtime_versions", "governance")
    for index, directory in enumerate(directories):
        manifest = read(directory / "MANIFEST.json")
        if (manifest["status"] != "PASS" or manifest["scope"] != "PRODUCTION"
                or manifest["case"] != case or (manifest["shard_index"], manifest["shard_count"]) != (index, count)
                or any(manifest[key] != digest for key, digest in frozen.items())):
            raise ValueError(f"Invalid production completion manifest: {directory}")
        selected = {key: manifest[key] for key in invariant}
        if index == 0:
            expected_settings = selected
        elif selected != expected_settings:
            raise ValueError(f"Runtime or production driver differs across shards: {directory}")
        expected_tasks = tasks[index::count]
        ids = np.array(sorted(i for task in expected_tasks for i in task["pose_ids"]), dtype=np.int64)
        selected_near_ids = near_ids.intersection(ids.tolist())
        expected_files = SHARD_FILES | (NEAR_FILES if selected_near_ids else set())
        if (set(manifest["output_sha256"]) != expected_files or manifest["poses"] != len(ids)
                or manifest["near_pose_count"] != len(selected_near_ids)
                or manifest["trace_positions"] != len(expected_tasks) or manifest["extra_export_solver_calls"]):
            raise ValueError(f"Incomplete or unexpected shard coverage: {directory}")
        for name, digest in manifest["output_sha256"].items():
            verify(directory / name, digest)
            if (directory / name).stat().st_size != manifest["output_bytes"][name]:
                raise ValueError(f"Size differs for {directory / name}")
        received_ids = np.load(directory / "POSE_IDS.npy", allow_pickle=False)
        if received_ids.dtype != np.int64 or not np.array_equal(received_ids, ids):
            raise ValueError(f"Invalid shard pose row order: {directory}")
        receipts = read(directory / "TRACE_RECEIPTS.json")
        for task, receipt in zip(expected_tasks, receipts, strict=True):
            if (any(task[key] != receipt[key] for key in ("tag", "task_id", "pose_ids"))
                    or not set(range(0, 257, 16)).issubset(receipt["node_bins"])
                    or receipt["node_bins"] != sorted(set(receipt["node_bins"]))
                    or len(receipt["node_bins"]) != receipt["solver_calls"]
                    or receipt["n_full_paths"] < 1):
                raise ValueError(f"Invalid production trace receipt: {directory}/{task['task_id']}")
        if sum(receipt["solver_calls"] for receipt in receipts) != manifest["solver_calls"]:
            raise ValueError(f"Solver call total differs: {directory}")
        yield directory, manifest, ids, selected_near_ids, receipts


def fill_los(target, directory, ids, frequencies, expected_h):
    with np.load(directory / "PATHS_LoS.npz", allow_pickle=False) as source:
        if (set(source.files) != LOS_NAMES or not np.array_equal(source["pose_id"], ids)
                or not np.array_equal(source["freqs_hz"], frequencies)):
            raise ValueError(f"LoS archive row or frequency axes differ: {directory}")
        delay, coeff = source["tau"], source["a"]
        rebuilt = coeff * np.exp(-2j * np.pi * frequencies[None, :] * delay)[..., None, None]
        if not np.array_equal(rebuilt, expected_h):
            raise ValueError(f"LoS archive does not reconstruct H_LoS exactly: {directory}")
        if np.any(source["counts"] != 1) or np.any(source["interactions"] != 0):
            raise ValueError(f"Expected exactly one interaction-free LoS path: {directory}")
        for field, output in target.items():
            data = source[field]
            if data.shape != (len(ids), *output.shape[1:]) or data.dtype != output.dtype or not np.isfinite(data).all():
                raise ValueError(f"Invalid LoS archive field {field}: {directory}")
            output[ids] = data


def load_near(directory, selected, expected_h_los, frequencies):
    with np.load(directory / "PATHS_NEAR.npz", allow_pickle=False) as pack:
        if set(pack.files) != NEAR_NAMES or not np.array_equal(pack["frequencies_hz"], frequencies):
            raise ValueError(f"Unrecognized PATHS_NEAR schema or frequency grid: {directory}")
        rows = {field: pack[field] for field in pack.files if field != "frequencies_hz"}
    pose, path = rows["pose_id"], rows["path_index"]
    tau, coeff, line = rows["tau_s"], rows["coefficients"], rows["is_los"]
    if (pose.dtype != np.int64 or line.dtype != bool or tau.dtype != np.float64
            or coeff.dtype != np.complex128 or coeff.shape != (len(pose), len(frequencies), 2, 2)
            or any(len(arr) != len(pose) or not np.isfinite(arr).all() for arr in rows.values())
            or set(pose.tolist()) != selected or sorted(pose[line].tolist()) != sorted(selected)
            or len(set(zip(pose.tolist(), path.tolist()))) != len(pose)):
        raise ValueError(f"Incomplete or invalid PATHS_NEAR pose rows: {directory}")
    rebuilt = coeff[line] * np.exp(-2j * np.pi * frequencies[None, :] * tau[line, None])[..., None, None]
    if not np.array_equal(rebuilt, expected_h_los[pose[line]]):
        raise ValueError(f"Serialized near LoS differs from the same F1 trace: {directory}")
    return rows


def write_pose_views(destination, g7_case, base, diagnostic, main_count):
    fields = list(dict.fromkeys(key for row in base + diagnostic for key in row))
    write(destination / "SAMPLES.json", base + diagnostic)
    with (destination / "TIMELINE.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(base + diagnostic)
    views = {}
    for view, name, rows in (("main", "G1-RT-TB3-001", base), ("diagnostic", "G1-RT-TB3-002", diagnostic)):
        views[view] = dict(question_id=name, sets=dict(Counter(row["set"] for row in rows)),
                           observation_count=len(rows), pose_ids=sorted({row["pose_id"] for row in rows}))
    if views["main"]["pose_ids"] != list(range(main_count)):
        raise ValueError("Baseline observations do not cover their original RF pose prefix")
    for name in ("rf_poses.json", "rf_tasks.json", "SCENE_ENTRY.json"):
        with (destination / name).open("xb") as stream:
            stream.write((g7_case / name).read_bytes())
    write(destination / "BATCH_VIEWS.json", views)


def write_path_summary(directory, receipts, rows):
    full_count, near_count = {}, {}
    for receipt in receipts:
        for pose in receipt["pose_ids"]:
            full_count[pose] = receipt["n_full_paths"]
            near_count[pose] = receipt["n_near_paths"]
    sets = {}
    for name in dict.fromkeys(row["set"] for row in rows):
        poses = {row["pose_id"] for row in rows if row["set"] == name}
        sets[name] = dict(poses=len(poses), full_path_count_histogram=dict(Counter(full_count[i] for i in poses)),
                          near_path_count_histogram=(dict(Counter(near_count[i] for i in poses))
                                                     if name in NEAR_SETS else None))
    write(directory / "PATH_SUMMARY.json", sets)


def merge(g0, g7, case, shards, out):
    started, started_utc = time.monotonic(), utc_now()
    scene, anchor, poses, tasks, baseline, diagnostic, main_count = case_inputs(g0, g7, case)
    near_ids = {row["pose_id"] for row in baseline + diagnostic if row["set"] in NEAR_SETS}
    h_dir, p_dir, m_dir = (out / folder / case for folder in ("H", "paths", "poses"))
    for folder in (h_dir, p_dir, m_dir):
        folder.mkdir(parents=True, mode=0o700)
    rows = len(poses)
    freqs = 257
    shape = (rows, freqs, 2, 2)
    h_full, h_los = (np.lib.format.open_memmap(h_dir / name, mode="w+", dtype=np.complex128, shape=shape)
                     for name in ("H_full.npy", "H_LoS.npy"))
    los = dict(a=np.empty(shape, np.complex128), tau=np.empty(shape[:2], np.float64),
               counts=np.empty(shape[:2], np.int64), interactions=np.empty(shape[:2], np.int64),
               **{name: np.empty(shape[:2], np.float64) for name in LOS_ANGLES})
    frequencies = None
    manifests, all_receipts, all_near = [], [], []
    schema = None
    for directory, manifest, ids, subset, receipts in load_shards(shards, case, tasks, near_ids):
        if frequencies is None:
            with np.load(directory / "PATHS_LoS.npz", allow_pickle=False) as source:
                frequencies = source["freqs_hz"]
            if (frequencies.dtype != np.float64 or frequencies.shape != (freqs,)
                    or not np.isfinite(frequencies).all() or np.any(np.diff(frequencies) <= 0)):
                raise ValueError("Invalid frozen production frequency grid")
        for name, target in (("H_full.npy", h_full), ("H_LoS.npy", h_los)):
            channel = np.load(directory / name, mmap_mode="r", allow_pickle=False)
            if (channel.shape != (len(ids), *shape[1:]) or channel.dtype != np.complex128
                    or not np.isfinite(channel).all()):
                raise ValueError(f"Invalid production channel shard: {directory / name}")
            target[ids] = channel
        fill_los(los, directory, ids, frequencies, h_los[ids])
        if subset:
            candidate = read(directory / "PATHS_NEAR_SCHEMA.json")
            if schema is None:
                schema = candidate
            elif candidate != schema:
                raise ValueError("Near-path schema differs across production shards")
            all_near.append(load_near(directory, subset, h_los, frequencies))
        all_receipts.extend(receipts)
        manifests.append(dict(manifest, manifest_sha256=sha(directory / "MANIFEST.json")))
    h_full.flush()
    h_los.flush()
    del h_full, h_los
    np.savez_compressed(p_dir / "PATHS_LoS.npz", pose_id=np.arange(rows, dtype=np.int64),
                        freqs_hz=frequencies, **los)
    del los
    if schema is None:
        raise ValueError("No PATHS_NEAR output for required poses")
    merged = {field: np.concatenate([pack[field] for pack in all_near]) for field in all_near[0]}
    del all_near
    order = np.lexsort((merged["path_index"], merged["pose_id"]))
    np.savez_compressed(p_dir / "PATHS_NEAR.npz", frequencies_hz=frequencies,
                        **{field: data[order] for field, data in merged.items()})
    del merged
    write(p_dir / "PATHS_NEAR_SCHEMA.json", schema)
    all_receipts.sort(key=lambda receipt: receipt["task_id"])
    write(p_dir / "TRACE_RECEIPTS.json", all_receipts)
    write_path_summary(p_dir, all_receipts, baseline + diagnostic)
    write_pose_views(m_dir, g7 / "poses" / case, baseline, diagnostic, main_count)
    files = [path for directory in (h_dir, p_dir, m_dir) for path in directory.iterdir()]
    hashes = {p.relative_to(out).as_posix(): sha(p) for p in sorted(files)}
    manifest = dict(
        case=case, status="PASS", phase="F1_PRODUCTION_ASSEMBLY", role="IMPLEMENTER",
        poses=rows, main_poses=main_count, diagnostic_new_poses=rows-main_count, shape=list(shape),
        layout="pose,frequency,rx(+45,-45),tx(+45,-45)", mount_deg=0,
        anchor_xyz=scene["anchors_xyz_m"][anchor], robot_z=scene["rx_z_m"],
        max_depth=0, full_max_depth=3, solver_batch_calls=sum(r["solver_calls"] for r in all_receipts),
        pose_frequency_evaluations=rows*freqs, extra_export_solver_calls=0,
        H_sha256=hashes[f"H/{case}/H_LoS.npy"], los_H_sha256=hashes[f"H/{case}/H_LoS.npy"],
        full_H_sha256=hashes[f"H/{case}/H_full.npy"], samples_sha256=hashes[f"poses/{case}/SAMPLES.json"],
        material_bindings=scene["material_bindings"], counts_all_one=True, all_finite=True,
        trace_positions=len(all_receipts), near_poses=len(near_ids), shards=manifests,
        started_utc=started_utc, finished_utc=utc_now(), wall_s=time.monotonic()-started,
        command=[sys.executable, *sys.argv], merge_code_sha256=sha(Path(__file__)),
        output_sha256=hashes, output_bytes={p.relative_to(out).as_posix(): p.stat().st_size for p in files},
    )
    write(h_dir / "MANIFEST.json", manifest)
    print(f"{case}: {rows} poses, {len(all_receipts)} XY, {sum(manifest['output_bytes'].values())} bytes", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for path in ("inputs", "g7", "shards", "out"):
        parser.add_argument("--" + path, type=Path, required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    args = parser.parse_args()
    merge(args.inputs, args.g7, args.case, args.shards, args.out)


if __name__ == "__main__":
    main()
