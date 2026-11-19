"""Generate and verify the G1 scene/pose artifacts through the offline G0 gate."""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import platform
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from build_tb3_poses import (
    C3_RADIUS_M, POSE_TOL, RAW, ROOT, STEP_DEG, STEP_M, TB3_ANGLES, build_poses,
    matching_poses, read_json, rotate, verified_inputs, wrap_deg,
)
from build_tb3_scene import (
    ANCHORS, HALF_WIDTHS, HEIGHT_M, LENGTH_M, RX_Z_M, build_scenes, sha256,
    wall_profile, write_json,
)

BODY_HALF = (0.281 / 2, 0.306 / 2)
BODY_RADIUS = math.hypot(*BODY_HALF)
WALL_MIN = 0.05
AXIS_MIN = 0.01  # Method B's existing check_anchor_axis_clearance threshold
SET_NAMES = {"P-A_TEACH", "P-A_REPEAT", "P-A_PRIME", "P-B", "C1", "C2", "C3", "C4"}
SPEC = ROOT / "research/G1_RT_TB3_CORRIDOR_20261113/SPEC_KO.md"


def point_segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    offset = (point[0] - start[0], point[1] - start[1])
    f = max(0.0, min(1.0, (offset[0]*dx + offset[1]*dy) / (dx*dx + dy*dy)))
    return math.hypot(offset[0] - f*dx, offset[1] - f*dy)


def wall_distance(start, end):
    """Distance from the wall segment to the axis-aligned rectangle in body coordinates."""
    enter, leave = 0.0, 1.0
    for a, b, half in zip(start, end, BODY_HALF):
        if a == b:
            if abs(a) > half:
                enter = math.inf
            continue
        left, right = sorted(((-half - a) / (b - a), (half - a) / (b - a)))
        enter, leave = max(enter, left), min(leave, right)
    if enter <= leave:
        return 0.0
    points = [math.hypot(*(max(abs(v) - half, 0.0) for v, half in zip(p, BODY_HALF)))
              for p in (start, end)]
    points.extend(point_segment_distance(corner, start, end)
                  for corner in itertools.product(*[(-d, d) for d in BODY_HALF]))
    return min(points)


def clearance(row, walls):
    x, y, yaw = row["x"], row["y"], math.radians(row["yaw_body_deg"])
    inside = sum((a[1] > y) != (b[1] > y) and x < a[0] + (b[0] - a[0]) *
                 (y - a[1]) / (b[1] - a[1]) for a, b in walls) % 2
    if not inside:
        return 0.0
    nearest = math.inf
    for a, b in walls:
        if point_segment_distance((x, y), a, b) - BODY_RADIUS < nearest:
            nearest = min(nearest, wall_distance(
                rotate(a[0] - x, a[1] - y, -yaw),
                rotate(b[0] - x, b[1] - y, -yaw)))
    return nearest


def mesh_checks(scene_dir, geometry, entry, walls, errors):
    bindings = entry["material_bindings"]
    names = {binding["object"] for binding in bindings}
    expected_names = {"floor", "ceiling", "end_x_min", "end_x_max", "wall_y_neg", "wall_y_pos"}
    if geometry == "G-T2":
        expected_names |= {"protrusion"} | {f"recess_{i}_{part}" for i in (1, 2)
                                              for part in ("wood", "floor", "soffit")}
    if names != expected_names or len(bindings) != len(names):
        errors.append(f"{geometry}: incorrect mesh object list")
    footprint = set()
    def edge(a, b):
        return tuple(sorted((tuple(np.round(a, 9)), tuple(np.round(b, 9)))))
    for binding in bindings:
        path = scene_dir / binding["ply"]
        name = binding["object"]
        if sha256(path) != binding["ply_sha256"]:
            errors.append(f"{path}: mesh checksum mismatch")
        material, thickness = "concrete", 0.20
        if name.startswith("recess_") and name.rsplit("_", 1)[-1] in {"wood", "soffit"}:
            material, thickness = "wood", 0.04
        elif name.startswith("wall_") and geometry != "G-V":
            material, thickness = "plasterboard", 0.0125
        if (binding["itu_type"], binding["thickness_m"]) != (material, thickness):
            errors.append(f"{path}: material or thickness mismatch")

        lines = path.read_text(encoding="ascii").splitlines()
        n_vertices, n_faces = int(lines[2].split()[2]), int(lines[6].split()[2])
        start = lines.index("end_header") + 1
        vertices = np.array([list(map(float, line.split())) for line in lines[start:start+n_vertices]])
        faces = [list(map(int, line.split())) for line in lines[start+n_vertices:]]
        if (lines[:2] != ["ply", "format ascii 1.0"] or not np.isfinite(vertices).all()
                or vertices.shape != (n_vertices, 3) or len(faces) != n_faces
                or any(f[0] != 3 or len(f) != 4 or min(f[1:]) < 0 or max(f[1:]) >= n_vertices
                       for f in faces)):
            errors.append(f"{path}: invalid BLOCK_C PLY structure")
            continue
        for i in range(0, n_vertices, 4):
            quad = vertices[i:i+4]
            if len(quad) != 4:
                errors.append(f"{path}: incomplete quadrilateral")
                break
            normal = np.cross(quad[1] - quad[0], quad[2] - quad[0])
            if not np.any(normal):
                errors.append(f"{path}: degenerate quadrilateral")
            if abs(normal[2]) > 1e-12 or not quad[:, 2].min() < RX_Z_M < quad[:, 2].max():
                continue
            # A vertical quad intersects the receiver-height plane in a line.
            a, b = sorted(set(map(tuple, quad[:, :2])))
            footprint.add(edge(a, b))
    if footprint != {edge(a, b) for a, b in walls}:
        errors.append(f"{geometry}: mesh cross section does not match the wall boundary")
    return len(bindings)


def check_tables(directory, geometry, anchor, walls, errors):
    poses = read_json(directory / "rf_poses.json")
    rows = read_json(directory / "SAMPLES.json")
    tasks = read_json(directory / "rf_tasks.json")
    with (directory / "TIMELINE.csv").open(encoding="utf-8", newline="") as stream:
        timeline = list(csv.DictReader(stream))
    if len(timeline) != len(rows) or any(
        csv_row != {key: "" if v is None else str(v) for key, v in row.items()}
        for csv_row, row in zip(timeline, rows)
    ):
        errors.append(f"{directory.name}: JSON and CSV observations differ")
    if not poses or [p["pose_id"] for p in poses] != list(range(len(poses))):
        errors.append(f"{directory.name}: invalid RF pose indices")
    if set(row["set"] for row in rows) != SET_NAMES:
        errors.append(f"{directory.name}: missing or unexpected observation sets")
    buckets = defaultdict(list)
    duplicate = 0
    x_anchor, y_anchor, z_anchor = ANCHORS[anchor]
    min_axis = (math.inf, None)
    for index, pose in enumerate(poses):
        if not all(math.isfinite(pose[k]) for k in ("x", "y", "yaw_body_deg")) or not (
            -180 <= pose["yaw_body_deg"] < 180
        ):
            errors.append(f"{directory.name}: invalid yaw or coordinates at pose {index}")
            continue
        cell, matches = matching_poses(pose, poses, buckets)
        duplicate += bool(matches)
        buckets[cell].append(index)
        axis = math.hypot(pose["x"] - x_anchor, pose["y"] - y_anchor)
        if axis < min_axis[0]:
            min_axis = (axis, index)
    if duplicate:
        errors.append(f"{directory.name}: {duplicate} duplicate RF poses")
    if not (0 < x_anchor < LENGTH_M and abs(y_anchor) < HALF_WIDTHS[geometry]
            and RX_Z_M < z_anchor < HEIGHT_M and abs(HEIGHT_M - z_anchor - 0.05) < 1e-12):
        errors.append(f"{directory.name}: anchor placement or ceiling standoff")
    if min_axis[0] < AXIS_MIN:
        errors.append(f"{directory.name}: anchor horizontal-axis clearance {min_axis[0]:.6f} m")

    groups = defaultdict(list)
    set_indices = defaultdict(list)
    refs = set()
    min_wall = {}
    motion_clearance_bound = math.inf
    previous = {}
    for row in rows:
        set_name, station = row["set"], row["station_id"]
        i = row["pose_id"]
        refs.add(i)
        if not isinstance(i, int) or not 0 <= i < len(poses):
            errors.append(f"{directory.name}: missing pose reference {i}")
            continue
        p = poses[i]
        if math.hypot(p["x"] - row["x"], p["y"] - row["y"]) > POSE_TOL or abs(
            wrap_deg(p["yaw_body_deg"] - row["yaw_body_deg"])
        ) > POSE_TOL:
            errors.append(f"{directory.name}: pose reference {i} does not match observation")
        groups[set_name, station].append(row)
        set_indices[set_name].append(row["sequence_index"])
        distance = clearance(row, walls)
        if set_name not in min_wall or distance < min_wall[set_name]["m"]:
            min_wall[set_name] = dict(m=distance, pose_id=i, sequence_index=row["sequence_index"])
        if distance < WALL_MIN:
            errors.append(f"{directory.name}: {set_name} index {row['sequence_index']} wall clearance {distance:.6f} m")

        if set_name in {"C1", "C2", "C3", "C4", "P-A_PRIME", "P-B"} and set_name in previous:
            last, last_clearance = previous[set_name]
            translation = math.hypot(row["x"] - last["x"], row["y"] - last["y"])
            angle = abs(wrap_deg(row["yaw_body_deg"] - last["yaw_body_deg"]))
            if set_name != "P-B" and (translation > STEP_M + 1e-9 or angle > STEP_DEG + 1e-9):
                errors.append(f"{directory.name}: step exceeds limit in {set_name}")
            if row["motion"] == "in_place" and translation > 1e-9:
                errors.append(f"{directory.name}: in-place rotation changes position")
            if row["motion"] == "arc":
                if not math.isclose(translation, 2 * C3_RADIUS_M * math.sin(math.radians(angle) / 2),
                                    rel_tol=0, abs_tol=1e-10):
                    errors.append(f"{directory.name}: C3 arc is not tangent-radius consistent")
                translation = C3_RADIUS_M * math.radians(angle)
            bound = min(last_clearance, distance) - (translation + BODY_RADIUS * math.radians(angle)) / 2
            motion_clearance_bound = min(motion_clearance_bound, bound)
            if bound < WALL_MIN:
                errors.append(f"{directory.name}: swept-body clearance bound {bound:.6f} m in {set_name}")
        previous[set_name] = (row, distance)

    if refs != set(range(len(poses))):
        errors.append(f"{directory.name}: RF pose references do not cover the table")
    for name, indices in set_indices.items():
        if indices != list(range(len(indices))):
            errors.append(f"{directory.name}: invalid sequence index in {name}")
    for (set_name, station), group in groups.items():
        indices = [row["sequence_index"] for row in group]
        if any(b <= a for a, b in itertools.pairwise(indices)):
            errors.append(f"{directory.name}: non-increasing sequence at {set_name}/{station}")
        if set_name in {"P-A_TEACH", "P-A_REPEAT"}:
            dense = [row for row in group if row["protocol"] == "dense49"]
            selected = [row["planned_rel_deg"] for row in group if row["selected_5pt"]]
            base = group[0]
            if (base["protocol"] != "base" or group[-50]["protocol"] != "base_after"
                    or [row["planned_rel_deg"] for row in dense] != [j * STEP_DEG for j in range(-24, 25)]
                    or len(dense) != 49 or dense[24]["pose_id"] != base["pose_id"]
                    or selected != TB3_ANGLES):
                errors.append(f"{directory.name}: invalid sweep structure at {set_name}/{station}")
            if any(abs(wrap_deg(row["yaw_body_deg"] - base["yaw_body_deg"] -
                                row["achieved_rel_deg"])) > 1e-9 for row in group):
                errors.append(f"{directory.name}: degree conversion mismatch at {set_name}/{station}")

    c3 = groups["C3", None]
    arc_segments = {row["segment"] for row in c3 if row["motion"] == "arc"}
    initial, final = c3[0], c3[-1]
    if (len(arc_segments) != 12 or initial["x"] != 4 or final["x"] != 16
            or abs(initial["y"] - final["y"]) > 1e-10
            or abs(initial["yaw_body_deg"]) > 1e-10 or abs(final["yaw_body_deg"]) > 1e-10):
        errors.append(f"{directory.name}: C3 vertex count or endpoint mismatch")

    task_refs = Counter()
    tags = set()
    for index, task in enumerate(tasks):
        tag = task["tag"]
        if tag in tags or task["task_id"] != index:
            errors.append(f"{directory.name}: duplicate trace key or wrong task index {tag}")
        tags.add(tag)
        for i in task["pose_ids"]:
            task_refs[i] += 1
            p = poses[i]
            if tag != f"x{p['x']:.4f}_y{p['y']:.4f}" or math.hypot(
                p["x"] - task["x"], p["y"] - task["y"]
            ) > POSE_TOL:
                errors.append(f"{directory.name}: trace task points to the wrong position {i}")
    if task_refs != Counter(range(len(poses))):
        errors.append(f"{directory.name}: trace task does not partition RF poses")

    return dict(rf_poses=len(poses), duplicate_poses=duplicate, observations=len(rows),
                reused_pose_references=len(rows) - len(poses), trace_positions=len(tasks),
                set_counts=dict(Counter(row["set"] for row in rows)), min_wall_clearance_by_set=min_wall,
                min_swept_wall_bound_m=motion_clearance_bound,
                min_anchor_axis_clearance_m=min_axis[0], min_anchor_axis_pose_id=min_axis[1],
                c3_arc_count=len(arc_segments))


def validate(out, scene_manifest):
    errors, cases, scenes = [], {}, {}
    for geometry in HALF_WIDTHS:
        polygon = wall_profile(geometry, positive=False) + list(reversed(wall_profile(geometry, positive=True)))
        walls = list(itertools.pairwise([*polygon, polygon[0]]))
        entry = scene_manifest["geometries"][geometry]
        scenes[geometry] = mesh_checks(out / "scene", geometry, entry, walls, errors)
        for anchor in ANCHORS:
            key = f"{geometry}_{anchor}"
            cases[key] = check_tables(out / "poses" / key, geometry, anchor, walls, errors)
    return dict(question_id="G1-RT-TB3-001", gate="G0", status="FAIL" if errors else "PASS",
                wall_threshold_m=WALL_MIN, anchor_axis_threshold_m=AXIS_MIN,
                pose_xy_tolerance_m=POSE_TOL, pose_yaw_tolerance_deg=POSE_TOL,
                scene_mesh_counts=scenes, cases=cases, violation_count=len(errors), violations=errors)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--raw", default=RAW, type=Path)
    parser.add_argument("--base-commit", required=True)
    parser.add_argument("--governance-sha", nargs=2, required=True, metavar=("COMMON", "IMPLEMENTER"))
    args = parser.parse_args()
    start = utc_now()
    files = verified_inputs(args.raw)
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = build_scenes(out / "scene")
    build_poses(out / "poses", files)
    report = validate(out, manifest)
    gates = out / "gates"
    gates.mkdir()
    write_json(gates / "G0.json", report)

    sources = [Path(__file__), Path(__file__).with_name("build_tb3_scene.py"),
               Path(__file__).with_name("build_tb3_poses.py"), SPEC, args.raw / "SHA256SUMS.txt", *files.values()]
    tracked_sources = {os.path.relpath(path, ROOT).replace(os.sep, "/"): sha256(path) for path in sources}
    config = dict(geometry={k: {p: v for p, v in g.items() if p != "material_bindings"}
                            for k, g in manifest["geometries"].items()},
                  step_m=STEP_M, step_deg=STEP_DEG, c3_radius_m=C3_RADIUS_M, c3_vertices=12,
                  pose_tolerance=POSE_TOL, wall_clearance_m=WALL_MIN, axis_clearance_m=AXIS_MIN,
                  spec_sha256=sha256(SPEC))
    result = dict(question_id="G1-RT-TB3-001", role="IMPLEMENTER", stage="G0", status=report["status"],
                  exit_code=int(bool(report["violations"])), started_utc=start, finished_utc=utc_now(),
                  command=[sys.executable, *sys.argv], base_commit=args.base_commit, source_state="local_changes",
                  method_b_reference="047cce2acb244ec2d7badc563345ccdd1f48613f",
                  governance=dict(zip(("COMMON_CONTRACT.md", "ROLE_IMPLEMENTER.md"), args.governance_sha)),
                  versions=dict(python=platform.python_version(), numpy=np.__version__, sqlite=sqlite3_version()),
                  config=config, config_sha256=hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
                  input_sha256=tracked_sources,
                  output_sha256={p.relative_to(out).as_posix(): sha256(p)
                                 for p in sorted(out.rglob("*")) if p.is_file()})
    write_json(out / "RUN_MANIFEST.json", result)
    print(f"G0 {report['status']}: {len(report['cases'])} cases, {report['violation_count']} violations")
    print(gates / "G0.json")
    return result["exit_code"]


def sqlite3_version():
    import sqlite3

    return sqlite3.sqlite_version


if __name__ == "__main__":
    raise SystemExit(main())
