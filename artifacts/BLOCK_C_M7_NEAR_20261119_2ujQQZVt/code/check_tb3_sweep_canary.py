"""Compare overlapping G-T1 canary yaws with both frozen guarded productions."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_sweep_shard import MOUNTS
from tb3_paths_near import G8_RELATIVE_LIMIT, check_g8


def select_overlaps(poses, pose_ids, old_poses):
    old_by_xy = defaultdict(list)
    for row in old_poses:
        old_by_xy[(row["x"], row["y"])].append(row)
    matched = {}
    for pose_id in pose_ids:
        pose = poses[pose_id]
        hits = [
            row["pose_id"] for row in old_by_xy[(pose["x"], pose["y"])]
            if abs((row["yaw_body_deg"] - pose["yaw_body_deg"] + 180) % 360 - 180) <= 1e-9
        ]
        if len(hits) > 1:
            raise ValueError(f"Ambiguous frozen match for sweep pose {pose_id}")
        if hits:
            matched[int(pose_id)] = hits[0]
    if not matched:
        raise ValueError("No reference poses at the canary's XY and yaw")
    return matched


def check_field(actual, reference):
    if actual.shape != reference.shape or not np.isfinite(actual).all() or not np.isfinite(reference).all():
        raise ValueError("Invalid or mismatched frozen and sweep RF arrays")
    error = float(np.max(np.abs(actual - reference)))
    scale = float(np.max(np.abs(reference)))
    normalized = error / scale if scale > 0 else error
    return dict(max_abs_error=error, max_normalized_error=normalized,
                exact=bool(np.array_equal(actual, reference)),
                passed=(normalized < G8_RELATIVE_LIMIT if scale > 0 else error == 0))


def check_near(actual_path, old_path, matched):
    with np.load(actual_path, allow_pickle=False) as sweep, np.load(old_path, allow_pickle=False) as old:
        if not np.array_equal(sweep["frequencies_hz"], old["frequencies_hz"]):
            raise ValueError("Frozen and sweep frequency grids differ")
        new_pose, new_path = sweep["pose_id"], sweep["path_index"]
        old_pose, old_index = old["pose_id"], old["path_index"]
        new_rows = {(int(pose), int(path)): i for i, (pose, path) in enumerate(zip(new_pose, new_path))
                    if pose in matched}
        old_ids = set(matched.values())
        old_rows = {(int(pose), int(path)): i for i, (pose, path) in enumerate(zip(old_pose, old_index))
                    if pose in old_ids}
        translated = [(matched[pose], path) for pose, path in new_rows]
        if set(translated) != old_rows.keys():
            raise ValueError("Frozen and sweep near-path identity differs")
        current_index = list(new_rows.values())
        reference_index = [old_rows[key] for key in translated]
        for name in ("tau_s", "delay_m", "interactions", "objects", "is_los",
                     "aod_az_el_rad", "aoa_az_el_rad"):
            if not np.array_equal(sweep[name][current_index], old[name][reference_index]):
                raise ValueError(f"Frozen and sweep near-path geometry differs on {name}")
        fields = check_field(sweep["coefficients"][current_index], old["coefficients"][reference_index])
    return fields | {"near_path_rows": len(current_index), "geometry_exact": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("sweep-inputs", "shard", "mount0-results", "mount45-results", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    shard_manifest = args.shard / "MANIFEST.json"
    manifest = read(shard_manifest)
    case = manifest["case"]
    if not case.startswith("G-T1_") or not manifest["shared_trace"] or manifest["status"] != "PASS":
        raise ValueError("Canary must be a completed shared-trace G-T1 shard")
    poses = read(args.sweep_inputs / "poses" / case / "rf_poses.json")
    receipts = read(args.shard / "TRACE_RECEIPTS.json")
    selected_poses = {pose for receipt in receipts for pose in receipt["pose_ids"]}
    report = {}
    for mount, prior in zip(MOUNTS, (args.mount0_results, args.mount45_results), strict=True):
        shard = args.shard / f"mount{mount}"
        ids = np.load(shard / "POSE_IDS.npy", allow_pickle=False)
        if set(ids.tolist()) != selected_poses:
            raise ValueError("Canary pose coverage differs from shared trace receipts")
        matched = select_overlaps(poses, ids, read(prior / "poses" / case / "rf_poses.json"))
        ids_to_rows = {pose: row for row, pose in enumerate(ids)}
        index = [ids_to_rows[pose] for pose in matched]
        old_index = list(matched.values())
        fields = {}
        for name in ("H_full.npy", "H_LoS.npy"):
            full = np.load(shard / name, mmap_mode="r", allow_pickle=False)
            reference = np.load(prior / "H" / case / name, mmap_mode="r", allow_pickle=False)
            fields[name] = check_field(full[index], reference[old_index])
        fields["PATHS_NEAR.npz"] = check_near(shard / "PATHS_NEAR.npz",
                                            prior / "paths" / case / "PATHS_NEAR.npz", matched)
        same_trace = check_g8(shard / "PATHS_NEAR.npz",
                              np.load(shard / "H_LoS.npy", allow_pickle=False), ids)
        report[str(mount)] = dict(passed=same_trace["status"] == "PASS" and
                                 all(record["passed"] for record in fields.values()),
                                 reference_run=str(prior), matched_poses=len(matched),
                                 fields=fields, same_trace_los=same_trace)
    passed = all(record["passed"] for record in report.values())
    write(args.out, dict(status="PASS" if passed else "FAIL", case=case,
                         verified_shard_sha256=sha(shard_manifest), mounts=report,
                         reference_overlap_limit=G8_RELATIVE_LIMIT))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
