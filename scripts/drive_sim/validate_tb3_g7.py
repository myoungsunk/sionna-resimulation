"""Generate and validate the TB3-002 diagnostic poses without any RF work."""
from __future__ import annotations

import argparse
import csv
import itertools
import platform
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from build_tb3_poses import ROOT, read_json
from build_tb3_scene import ANCHORS, HALF_WIDTHS, sha256, wall_profile, write_json
from tb3_g7_arms import (
    PF_ANCHORS, build_arm_tables, build_pd_rows, build_pf_rows, pf_scene_entry, teach_stations,
    validate_arm_tables, validate_pd_rows, validate_pf_rows,
)
from tb3_g7_empirical import SEED, build_pe_rows, load_empirical_pool, sample_revisits, validate_pe_rows
from validate_tb3_g0 import AXIS_MIN, WALL_MIN, mesh_checks, utc_now


SPEC = ROOT / "research/G1_RT_TB3_CORRIDOR_20261113/SPEC_DIAG_KO.md"
G0_SHA = "48ebdcdde68f3d62ec1b00c3061440f9363313ef35577f409eb5b5c0b75c13b6"


def verify_g0(root):
    manifest_path = root / "RUN_MANIFEST.json"
    if sha256(manifest_path) != G0_SHA:
        raise ValueError("Frozen G0 manifest changed")
    manifest = read_json(manifest_path)
    for name, expected in manifest["output_sha256"].items():
        if sha256(root / name) != expected:
            raise ValueError(f"Frozen G0 evidence checksum mismatch: {name}")
    gate = read_json(root / "gates/G0.json")
    if gate["status"] != "PASS" or gate["violation_count"] != 0:
        raise ValueError("Frozen G0 did not pass")
    return manifest


def save_case(directory, geometry, anchor, scene, rows, original, checks):
    poses, observations, tasks = build_arm_tables(rows, baseline_poses=original)
    directory.mkdir(parents=True)
    write_json(directory / "rf_poses.json", poses)
    write_json(directory / "SAMPLES.json", observations)
    write_json(directory / "rf_tasks.json", tasks)
    write_json(directory / "SCENE_ENTRY.json", scene)
    csv_path = directory / "TIMELINE.csv"
    fields = list(dict.fromkeys(key for row in observations for key in row))
    with csv_path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(observations)

    poses = read_json(directory / "rf_poses.json")
    observations = read_json(directory / "SAMPLES.json")
    tasks = read_json(directory / "rf_tasks.json")
    if poses[:len(original)] != list(original):
        raise ValueError("G7 changed the frozen prefix of G0 RF pose IDs")
    with csv_path.open(encoding="utf-8", newline="") as stream:
        timeline = list(csv.DictReader(stream))
    expected_rows = [{key: "" if row.get(key) is None else str(row[key]) for key in fields}
                     for row in observations]
    if timeline != expected_rows:
        raise ValueError("JSON and CSV observations differ")
    stats = validate_arm_tables(
        geometry, anchor, read_json(directory / "SCENE_ENTRY.json"), poses, observations, tasks,
        baseline_count=len(original),
    )
    for arm, check in checks.items():
        arm_rows = [row for row in observations if row["set"] == arm]
        stats[arm] = check(arm_rows)
        stats[arm]["unique_pose_ids"] = len({row["pose_id"] for row in arm_rows})
        stats[arm]["reused_g0_observations"] = sum(row["pose_id"] < len(original) for row in arm_rows)
    return stats


def validate(g0_root, out):
    g0 = verify_g0(g0_root)
    scene_dir = g0_root / "scene"
    geometries = read_json(scene_dir / "SCENE_MANIFEST.json")["geometries"]
    if set(geometries) != set(HALF_WIDTHS):
        raise ValueError("Incomplete geometry manifest")
    mesh_counts, mesh_errors = {}, []
    for geometry, scene in geometries.items():
        lower = wall_profile(geometry, positive=False)
        upper = wall_profile(geometry, positive=True)
        boundary = [*lower, *reversed(upper), lower[0]]
        mesh_counts[geometry] = mesh_checks(scene_dir, geometry, scene,
                                            list(itertools.pairwise(boundary)), mesh_errors)
    if mesh_errors:
        raise ValueError("G0 mesh checks: " + " | ".join(mesh_errors))

    pool, repeat_files = load_empirical_pool(ROOT, g0)
    visits = sample_revisits(pool)
    pose_manifest_path = out / "POSE_MANIFEST.json"
    write_json(pose_manifest_path, dict(
        question_id="G1-RT-TB3-002", stage="G7", g0_manifest_sha256=G0_SHA,
        empirical_sources=repeat_files,
        xy_source="stations[].align[-1].observed_correction[:2]",
        yaw_source="stations[].align[-1].icp.pose[2]",
        empirical_pool=pool,
        xy_range_mm=[1000 * f(p["distance_m"] for p in pool) for f in (min, max)],
        cited_xy_range_mm=[0.3, 7.9],
        seed=SEED, bit_generator="NumPy PCG64", draws="with replacement, radius and yaw independently",
        direction="uniform on [0, 2pi), world XY; same 54 visits across all cases",
        revisits=visits,
    ))
    checks = read_json(pose_manifest_path)
    pool, visits = checks["empirical_pool"], checks["revisits"]
    cases, violations = {}, []
    for geometry, scene in geometries.items():
        for anchor in ANCHORS:
            case = f"{geometry}_{anchor}"
            frozen = g0_root / "poses" / case
            stations = teach_stations(read_json(frozen / "SAMPLES.json"))
            original = read_json(frozen / "rf_poses.json")
            rows = {"P-E": build_pe_rows(stations, visits)}
            arm_checks = {"P-E": lambda rows: validate_pe_rows(stations, pool, visits, rows)}
            if geometry == "G-T1":
                rows = {"P-D": build_pd_rows(stations)} | rows
                arm_checks["P-D"] = lambda rows: validate_pd_rows(stations, rows)
            try:
                cases[case] = save_case(out / "poses" / case, geometry, anchor, scene, rows,
                                        original, arm_checks)
            except ValueError as exc:
                violations.append(f"{case}: {exc}")
            if geometry == "G-T1" and anchor in PF_ANCHORS:
                case += "_P-F"
                try:
                    standoff_scene = pf_scene_entry(geometry, anchor, scene)
                    cases[case] = save_case(
                        out / "poses" / case, geometry, anchor, standoff_scene,
                        {"P-F": build_pf_rows(stations)}, (),
                        {"P-F": lambda rows: validate_pf_rows(stations, rows)},
                    )
                except ValueError as exc:
                    violations.append(f"{case}: {exc}")

    counts = Counter()
    for case in cases.values():
        counts.update(case["observations"])
    expected = {"P-D": 5400, "P-E": 2430, "P-F": 1944}
    if counts != expected:
        violations.append(f"Wrong observation coverage: {dict(counts)}")
    return dict(
        cases=cases, scene_mesh_counts=mesh_counts, observations_by_arm=dict(counts),
        expected_observations_by_arm=expected,
        new_rf_poses=sum(case["new_rf_poses"] for case in cases.values()),
        wall_threshold_m=WALL_MIN, anchor_axis_threshold_m=AXIS_MIN, violations=violations,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g0", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    start = utc_now()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    try:
        checks = validate(args.g0.resolve(), out)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as exc:
        checks = dict(cases={}, violations=[str(exc)])
    errors = checks["violations"]
    status = "FAIL" if errors else "PASS"
    report = dict(question_id="G1-RT-TB3-002", gate="G7", status=status,
                  violation_count=len(errors), **checks)
    write_json(out / "G7.json", report)
    g0_manifest = args.g0 / "RUN_MANIFEST.json"
    filenames = ("validate_tb3_g7.py", "tb3_g7_arms.py", "tb3_g7_empirical.py",
                 "validate_tb3_g0.py", "build_tb3_poses.py", "build_tb3_scene.py")
    write_json(out / "RUN_MANIFEST.json", dict(
        question_id="G1-RT-TB3-002", stage="G7", role="IMPLEMENTER",
        status=status, exit_code=int(bool(errors)), started_utc=start, finished_utc=utc_now(),
        command=[sys.executable, *sys.argv], host=platform.node(), python=platform.python_version(),
        numpy=np.__version__, base_commit=subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True,
        ).strip(),
        source_state="G7 implementation in working tree; executed file hashes below",
        diagnostic_spec_sha256=sha256(SPEC), g0_manifest_sha256=sha256(g0_manifest),
        governance=read_json(g0_manifest)["governance"],
        source_sha256={name: sha256(Path(__file__).parent / name) for name in filenames},
        output_sha256={p.relative_to(out).as_posix(): sha256(p) for p in sorted(out.rglob("*")) if p.is_file()},
    ))
    print(f"G7 {status}: {len(checks['cases'])} cases, {len(errors)} violations")
    for error in errors:
        print(error)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
