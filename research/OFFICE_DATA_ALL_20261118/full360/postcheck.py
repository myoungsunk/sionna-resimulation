"""Read-only overlap and pose-table check; writes one exclusive report.

Run after controller completion: python /work/postcheck.py
Reference mount: /reference (the original full35_stride1 directory).
Byte hashes below describe C-order complex coefficient bytes, not NPY headers.
This check never changes controller receipts, thresholds, or reference data.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def check_tables(stations, poses, samples):
    """Check canonical row order as well as coverage and endpoint references."""
    issues = []
    if len(poses) != 1260 or len(samples) != 1295:
        return [f"table lengths {len(poses)}/{len(samples)} != 1260/1295"]
    if len({p["pose_id"] for p in poses}) != 1260:
        issues.append("pose_id duplicates")
    if len({s["sample_id"] for s in samples}) != 1295:
        issues.append("sample_id duplicates")
    endpoint_count = 0
    for si, station in enumerate(stations):
        sid = station["station_id"]
        station_poses = poses[si * 36:(si + 1) * 36]
        station_samples = samples[si * 37:(si + 1) * 37]
        for yi, (pose, yaw) in enumerate(zip(station_poses, range(-180, 180, 10))):
            chunk = "neg" if yi < 18 else "nonneg"
            expected_raw = f"traces/{sid}/{chunk}/{sid}_{chunk}_sweep.npz"
            if (pose["station_id"] != sid or pose["yaw_deg"] != yaw or
                    type(pose["h_row"]) is not int or pose["h_row"] != si * 36 + yi or
                    pose["x"] != station["x"] or pose["y"] != station["y"] or
                    pose["raw_trace_path"] != expected_raw or
                    type(pose["local_yaw_index"]) is not int or
                    pose["local_yaw_index"] != yi % 18):
                issues.append(f"{sid} pose mapping mismatch at yaw {yaw}")
        for sequence, (sample, yaw) in enumerate(zip(station_samples, range(-180, 181, 10))):
            endpoint = sequence == 36
            pose = station_poses[0 if endpoint else sequence]
            if (sample["station_id"] != sid or sample["yaw_deg"] != yaw or
                    type(sample["sequence_index"]) is not int or sample["sequence_index"] != sequence or
                    type(sample["h_row"]) is not int or sample["h_row"] != pose["h_row"] or
                    sample["pose_id"] != pose["pose_id"] or
                    type(sample["endpoint_alias"]) is not bool or sample["endpoint_alias"] != endpoint):
                issues.append(f"{sid} observation mapping mismatch at sequence {sequence}")
            endpoint_count += sample["endpoint_alias"] is True
    if endpoint_count != 35:
        issues.append(f"endpoint alias count {endpoint_count} != 35")
    return issues


def inspect(work, reference, report):
    import numpy as np

    for name in ("RUN_SUCCESS.json", "VALIDATION.json"):
        receipt = read_json(work / name)
        report["input_sha256"][name] = file_sha256(work / name)
        if receipt.get("ok") is not True:
            raise ValueError(f"{name} does not declare ok=true")
    contract = read_json(work / "RUN_CONTRACT.json")
    stations = contract["stations"]
    if (len(stations) != 35 or
            [s["station_id"] for s in stations] != [f"S{i:02d}" for i in range(1, 36)] or
            contract["unique_yaws_deg"] != list(range(-180, 180, 10))):
        raise ValueError("station order/count or yaw contract differs")
    for name in ("RUN_CONTRACT.json", "rf_poses.json", "SAMPLES.json", "H_full.npy"):
        report["input_sha256"][name] = file_sha256(work / name)
    poses, samples = read_json(work / "rf_poses.json"), read_json(work / "SAMPLES.json")
    table_issues = check_tables(stations, poses, samples)
    report["tables"] = dict(ok=not table_issues, issues=table_issues,
                            rf_pose_count=len(poses), observation_count=len(samples),
                            expected_endpoint_aliases=35, expected_sequence_indices=list(range(37)))
    report["issues"].extend(table_issues)
    full = np.load(work / "H_full.npy", allow_pickle=False, mmap_mode="r")
    if full.shape != (1260, 257, 2, 2) or full.dtype != np.dtype("complex128"):
        raise ValueError(f"H_full shape/dtype mismatch: {full.shape}/{full.dtype}")
    if not np.isfinite(full).all():
        raise ValueError("H_full contains nonfinite coefficients")
    combined_new, combined_original = hashlib.sha256(), hashlib.sha256()
    coefficient_count, maximum_difference = 0, 0.0
    all_equal, all_byte_equal = True, True
    for si, station in enumerate(stations):
        sid = station["station_id"]
        tag = f"office_x{float(station['x'])}_y{float(station['y'])}"
        path = reference / tag / f"{tag}_H.npy"
        result = dict(station_id=sid, reference_h_path=str(path),
                      new_h_rows=[si * 36 + 18, si * 36 + 35],
                      original_yaw_indices=list(range(18)), yaws_deg=list(range(0, 180, 10)))
        report["stations"].append(result)
        try:
            original = np.load(path, allow_pickle=False, mmap_mode="r")
            result["reference_file_sha256"] = file_sha256(path)
            if original.shape != (19, 257, 2, 2) or original.dtype != np.dtype("complex128"):
                raise ValueError(f"original H shape/dtype mismatch: {original.shape}/{original.dtype}")
            overlap = full[si * 36 + 18:(si + 1) * 36]
            old_overlap = original[:18]
            if not np.isfinite(old_overlap).all():
                raise ValueError("original overlap contains nonfinite coefficients")
            new_bytes, old_bytes = overlap.tobytes(order="C"), old_overlap.tobytes(order="C")
            new_sha = hashlib.sha256(new_bytes).hexdigest()
            old_sha = hashlib.sha256(old_bytes).hexdigest()
            combined_new.update(new_bytes)
            combined_original.update(old_bytes)
            equal = bool(np.array_equal(overlap, old_overlap))
            byte_equal = new_sha == old_sha
            difference = float(np.abs(overlap - old_overlap).max())
            if not np.isfinite(difference):
                raise ValueError("nonfinite difference between overlap coefficients")
            coefficient_count += int(overlap.size)
            maximum_difference = max(maximum_difference, difference)
            all_equal = all_equal and equal
            all_byte_equal = all_byte_equal and byte_equal
            result.update(ok=equal and byte_equal, array_equal=equal,
                          byte_sha_equal=byte_equal, new_coefficients_sha256=new_sha,
                          original_coefficients_sha256=old_sha, max_abs_diff=difference,
                          complex_coefficient_count=int(overlap.size))
            if not result["ok"]:
                report["issues"].append(f"{sid} original overlap differs")
        except Exception as error:
            result.update(ok=False, error=repr(error))
            report["issues"].append(f"{sid}: {error!r}")
            all_equal = all_byte_equal = False
    report["overlap"] = dict(array_equal=all_equal, byte_sha_equal=all_byte_equal,
                             complex_coefficient_count=coefficient_count,
                             expected_complex_coefficient_count=647640,
                             max_abs_diff=maximum_difference,
                             new_coefficients_sha256=combined_new.hexdigest(),
                             original_coefficients_sha256=combined_original.hexdigest(),
                             byte_hash_layout="station order, yaw 0..170, C-order complex128 coefficient bytes")
    if coefficient_count != 647640:
        report["issues"].append(f"overlap coefficient count {coefficient_count} != 647640")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path("/work"))
    parser.add_argument("--reference", type=Path, default=Path("/reference"))
    args = parser.parse_args()
    work, reference = args.work.resolve(), args.reference.resolve()
    target = work / "ORIGINAL_OVERLAP_CHECK.json"
    if target.exists():
        print(f"refusing to replace {target}", file=sys.stderr)
        return 2
    clock_start = time.monotonic()
    report = dict(status="FAIL", ok=False, started_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=file_sha256(__file__), command=sys.argv,
                  work=str(work), reference=str(reference), input_sha256={}, stations=[], issues=[],
                  scope="original 0..170 overlap equality and new pose/observation consistency")
    try:
        inspect(work, reference, report)
    except Exception as error:
        report["issues"].append(repr(error))
    report.update(ok=not report["issues"], status="FAIL" if report["issues"] else "PASS",
                  ended_utc=datetime.now(timezone.utc).isoformat(), elapsed_s=time.monotonic() - clock_start)
    # Exclusive creation protects any report written concurrently after the initial check.
    try:
        with target.open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except FileExistsError:
        print(f"refusing to replace {target}", file=sys.stderr)
        return 2
    print(json.dumps(dict(status=report["status"], report=str(target), issues=len(report["issues"]))))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
