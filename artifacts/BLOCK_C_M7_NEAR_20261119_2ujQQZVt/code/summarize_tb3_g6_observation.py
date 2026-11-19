"""Combine G6 observation replay shards with exact affected-path coverage."""
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import log10
from pathlib import Path
from statistics import median
import sys


def metrics(values):
    data = sorted(values)
    position = .9 * (len(data) - 1)
    lower = int(position)
    p90 = data[lower] + (position - lower) * (data[min(lower + 1, len(data)-1)] - data[lower])
    return dict(pose_count=len(data), median_abs_delta_s=median(data), p90_abs_delta_s=p90,
                max_abs_delta_s=data[-1], poses_exceeding_g4_context=sum(x > .005 for x in data))


def main():
    image_path, parts, out = map(Path, sys.argv[1:])
    image = json.loads(image_path.read_bytes())
    expected = {(r["case"], r["task_id"], r["path_index"]) for r in image["rows"]}
    input_sha256, part_sha256 = {}, {}
    runs, seen, stations, sequence = [], set(), set(), []
    by_case = defaultdict(list)
    for path in sorted(parts.glob("*.json")):
        raw = path.read_bytes()
        part_sha256[path.name] = sha256(raw).hexdigest()
        run = json.loads(raw)
        case = run["case"]
        for item in run["station_rows"]:
            key = case, item["task_id"]
            if key in stations:
                raise ValueError(f"Duplicate affected XY: {key}")
            stations.add(key)
        for row in run["path_rows"]:
            key = case, row["task_id"], row["path_index"]
            if key in seen:
                raise ValueError(f"Duplicate affected path: {key}")
            seen.add(key)
            sequence.append({"case": case, **row})
        by_case[case].extend(run["abs_delta_s"])
        for name, digest in run["input_sha256"].items():
            if input_sha256.setdefault(name, digest) != digest:
                raise ValueError(f"Inconsistent frozen input across shards: {name}")
        runs.append(run)
    if seen != expected or stations != {(r[0], r[1]) for r in expected}:
        raise ValueError("Incomplete or unexpected original G6 failure coverage")
    values = [v for case_values in by_case.values() for v in case_values]
    by_geometry = defaultdict(list)
    for case, group in by_case.items():
        by_geometry[case.split("_")[0]].extend(group)
    total = metrics(values)
    total["g4_context_limit"] = .005
    total["g4_context_ratio_to_max"] = .005 / total["max_abs_delta_s"] if total["max_abs_delta_s"] else None
    total["orders_below_g4_context"] = log10(total["g4_context_ratio_to_max"]) if total["g4_context_ratio_to_max"] else None
    result = dict(question_id=image["question_id"], official_gate_status="FAIL", threshold_s=image["threshold_s"],
                  purpose="Post-result G6 signed s sensitivity; G4 is a scale reference",
                  only_failed_paths_rephased=True, heading_error_computed=False,
                  positions=len(stations), paths=len(seen), poses=len(values),
                  frequency_hz=runs[0]["frequency_hz"], solver_calls=sum(r["solver_calls"] for r in runs),
                  total=total, by_case={k: metrics(v) for k, v in sorted(by_case.items())},
                  by_geometry={k: metrics(v) for k, v in sorted(by_geometry.items())},
                  same_delay_as_nearest_plane_candidate=sum(r["same_delay_as_nearest_candidate"] for r in sequence),
                  same_sequence_above_original_threshold=sum(abs(r["native_minus_image_s"]) > image["threshold_s"] for r in sequence),
                  max_abs_native_minus_exact_image_s=max(abs(r["native_minus_image_s"]) for r in sequence),
                  first_path_index_changes=sum(r["first_path_index_changes"] for r in runs),
                  baseline_exact_poses=sum(r["baseline_exact_poses"] for r in runs),
                  max_h_replay_error=max(r["max_h_replay_error"] for r in runs),
                  max_s_replay_error=max(r["max_s_replay_error"] for r in runs),
                  worker_wall_s=max(r["wall_s"] for r in runs),
                  finish_utc=datetime.now(timezone.utc).isoformat(),
                  input_sha256=input_sha256, part_sha256=part_sha256, path_rows=sequence)
    with out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(total), flush=True)


if __name__ == "__main__":
    main()
