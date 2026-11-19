"""Build the 360-degree TB3 sweep from the frozen G0/G7 station inputs."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from itertools import combinations, product
from math import hypot
from pathlib import Path
import shutil
import sys

from run_tb3_g1_pilot import read, sha, write
from run_tb3_production import CASES, case_inputs, utc_now


MOUNTS_DEG = (0, 45)
RELATIVE_ANGLES_DEG = tuple(range(-180, 181, 10))
STATIONS = tuple(f"P{index:03d}" for index in range(1, 19))
MAIN_SETS = ("P-A_TEACH", "P-A_REPEAT")
OFFSETS_M = (0.005, 0.01, 0.02, 0.05, 0.10)
DIRECTIONS = ("+x", "-x", "+y", "-y")
POSITION_TOL_M = 1e-6
YAW_TOL_DEG = 1e-6


def wrap_degrees(yaw):
    return (yaw + 180.0) % 360.0 - 180.0


def source_groups(case, base_rows, diagnostic_rows):
    groups = defaultdict(list)
    for row in base_rows:
        if row["set"] in MAIN_SETS:
            groups[row["set"], row["station_id"], None, None, None].append(row)
    for row in diagnostic_rows:
        key = (row["set"], row["station_id"], row.get("offset_m"),
               row.get("offset_direction"), row.get("revisit_index"))
        groups[key].append(row)

    if case.endswith("_P-F"):
        expected = {("P-F", station, None, None, None) for station in STATIONS}
    else:
        expected = {(name, station, None, None, None)
                    for name, station in product(MAIN_SETS, STATIONS)}
        expected.update(("P-E", station, None, None, visit)
                        for station, visit in product(STATIONS, range(1, 4)))
        if case.startswith("G-T1_"):
            expected.update(("P-D", station, offset, direction, None)
                            for station, offset, direction in product(STATIONS, OFFSETS_M, DIRECTIONS))
    if groups.keys() != expected:
        raise ValueError(f"{case}: frozen station/offset/revisit coverage differs")
    return groups


def baseline_rows(case, poses, base_rows, diagnostic_rows):
    bases = []
    for key, rows in source_groups(case, base_rows, diagnostic_rows).items():
        name, station, offset, direction, visit = key
        protocols = Counter(row["protocol"] for row in rows)
        if name in MAIN_SETS:
            if protocols["base"] != 1 or protocols["dense49"] != 49 or protocols["tb3_5pt"] < 5:
                raise ValueError(f"{case} {key}: incomplete frozen P-A station sweep")
            reference = next(row for row in rows if row["protocol"] == "base")
        else:
            expected = {"tb3_5pt": 5, "dense49": 49} if name == "P-F" else {"tb3_5pt": 5}
            if protocols != expected or any(row["source_set"] != "P-A_TEACH" for row in rows):
                raise ValueError(f"{case} {key}: incomplete frozen diagnostic station sweep")
            reference = rows[0]
        x, y = reference["x"], reference["y"]
        yaw = wrap_degrees(reference["yaw_body_deg"] - reference["achieved_rel_deg"])
        for row in rows:
            pose = poses[row["pose_id"]]
            if (hypot(row["x"] - x, row["y"] - y) > POSITION_TOL_M
                    or hypot(row["x"] - pose["x"], row["y"] - pose["y"]) > POSITION_TOL_M
                    or abs(wrap_degrees(row["yaw_body_deg"] - pose["yaw_body_deg"])) > YAW_TOL_DEG):
                raise ValueError(f"{case} {key}: frozen observation pose or station center differs")
            if (row["protocol"] in {"tb3_5pt", "dense49"}
                    and abs(wrap_degrees(row["yaw_body_deg"] - row["achieved_rel_deg"] - yaw)) > YAW_TOL_DEG):
                raise ValueError(f"{case} {key}: inconsistent station zero yaw")
        bases.append(dict(base_id=len(bases), set=name, station_id=station, x=x, y=y,
                          baseline_body_yaw_deg=yaw,
                          source_pose_ids=[row["pose_id"] for row in rows],
                          source_sequence_indices=[row["sequence_index"] for row in rows],
                          offset_m=offset, offset_direction=direction, revisit_index=visit))

    for first, second in combinations(bases, 2):
        if hypot(first["x"] - second["x"], first["y"] - second["y"]) <= POSITION_TOL_M:
            raise ValueError(f"{case}: duplicate frozen station XY at base IDs "
                             f"{first['base_id']} and {second['base_id']}")
    return bases


def sweep_tables(bases):
    poses, tasks, samples = [], [], []
    set_sequence = Counter()
    for base in bases:
        name = base["set"]
        x, y = base["x"], base["y"]
        yaw_zero = base["baseline_body_yaw_deg"]
        # Add the mount in the field evaluator. The 0-degree-mount orientation
        # is stored here in the production interface's yaw_body_deg field.
        yaws = [wrap_degrees(yaw_zero + rel) for rel in RELATIVE_ANGLES_DEG[:-1]]
        ids = list(range(len(poses), len(poses) + len(yaws)))
        poses.extend(dict(pose_id=pose_id, x=x, y=y, yaw_body_deg=yaw)
                     for pose_id, yaw in zip(ids, yaws))
        base_id = base["base_id"]
        tasks.append(dict(task_id=base_id, tag=f"full_sweep_{base_id:04d}",
                          x=x, y=y, antenna_yaw_deg=yaws, pose_ids=ids))
        for ordinal, rel in enumerate(RELATIVE_ANGLES_DEG):
            direction = ordinal % len(ids)  # +180 and -180 are the same RF pose.
            samples.append(dict(
                set=name, sequence_index=set_sequence[name], series="full_sweep",
                along=0.0, cum_abs_dtheta_deg=ordinal * 10.0,
                pose_id=ids[direction], x=x, y=y, yaw_body_deg=yaws[direction],
                protocol="full360_10deg", motion="in_place", station_id=base["station_id"],
                planned_rel_deg=rel, achieved_rel_deg=rel, base_id=base_id,
                baseline_body_yaw_deg=yaw_zero, offset_m=base["offset_m"],
                offset_direction=base["offset_direction"], revisit_index=base["revisit_index"],
            ))
            set_sequence[name] += 1
    return poses, tasks, samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("g0", "g7", "compare-g0", "compare-g7", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()
    started = utc_now()
    args.out.mkdir(parents=True, exist_ok=False)
    input_hashes = {}
    governance = None
    for name, first, second in (("g0", args.g0, args.compare_g0), ("g7", args.g7, args.compare_g7)):
        manifests = [root / "RUN_MANIFEST.json" for root in (first, second)]
        digest = sha(manifests[0])
        if digest != sha(manifests[1]):
            raise ValueError(f"{name}: mount input manifest hashes differ")
        manifest = read(manifests[0])
        input_hashes[name] = {"RUN_MANIFEST.json": digest} | manifest["output_sha256"]
        if governance is not None and governance != manifest["governance"]:
            raise ValueError("G0 and G7 governance hashes differ")
        governance = manifest["governance"]

    cases, output_hashes = {}, {}
    for case in CASES:
        inputs = case_inputs(args.g0, args.g7, case)
        if inputs != case_inputs(args.compare_g0, args.compare_g7, case):
            raise ValueError(f"{case}: frozen mount inputs differ")
        _, _, frozen_poses, _, base_rows, diagnostic_rows, _ = inputs
        bases = baseline_rows(case, frozen_poses, base_rows, diagnostic_rows)
        poses, tasks, samples = sweep_tables(bases)
        out = args.out / "poses" / case
        out.mkdir(parents=True)
        for name, data in (("SWEEP_BASES.json", bases), ("rf_poses.json", poses),
                           ("rf_tasks.json", tasks), ("SAMPLES.json", samples)):
            write(out / name, data)
        with (out / "TIMELINE.csv").open("x", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(samples[0]))
            writer.writeheader()
            writer.writerows(samples)
        shutil.copyfile(args.g7 / "poses" / case / "SCENE_ENTRY.json", out / "SCENE_ENTRY.json")
        cases[case] = dict(n_bases=len(bases), n_poses=len(poses),
                           n_observations=len(samples), n_tasks=len(tasks),
                           bases_by_set=dict(Counter(base["set"] for base in bases)))
        output_hashes.update({path.relative_to(args.out).as_posix(): sha(path)
                              for path in sorted(out.iterdir())})
        print(f"{case}: {len(bases)} bases, {len(poses)} RF poses, {len(samples)} observations")

    write(args.out / "SWEEP_MANIFEST.json", dict(
        question_id="G1-RT-TB3-001/002", role="IMPLEMENTER", stage="full_sweep_inputs",
        status="PASS", code_commit=args.code_commit, command=sys.argv,
        started_utc=started, finished_utc=utc_now(), governance=governance,
        mount_deg=MOUNTS_DEG, planned_rel_deg=RELATIVE_ANGLES_DEG,
        position_tolerance_m=POSITION_TOL_M, yaw_tolerance_deg=YAW_TOL_DEG,
        source_sha256={Path(__file__).name: sha(Path(__file__)),
                       "run_tb3_production.py": sha(Path(__file__).with_name("run_tb3_production.py")),
                       "run_tb3_g1_pilot.py": sha(Path(__file__).with_name("run_tb3_g1_pilot.py"))},
        mount_input_roots={"0": [str(args.g0), str(args.g7)],
                           "45": [str(args.compare_g0), str(args.compare_g7)]},
        input_sha256=input_hashes, output_sha256=output_hashes, cases=cases,
    ))


if __name__ == "__main__":
    main()
