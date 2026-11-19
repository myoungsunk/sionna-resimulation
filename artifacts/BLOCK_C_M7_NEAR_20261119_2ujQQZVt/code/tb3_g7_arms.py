"""Construct and validate the geometry-defined P-D and P-F arms of TB3-002."""
from __future__ import annotations

import itertools
import math
from collections import Counter, defaultdict

from build_tb3_poses import POSE_TOL, STEP_DEG, TB3_ANGLES, matching_poses, rf_tasks, wrap_deg
from build_tb3_scene import HALF_WIDTHS, wall_profile
from validate_tb3_g0 import AXIS_MIN, WALL_MIN, clearance


STATIONS = tuple(f"P{i:03d}" for i in range(1, 19))
PD_DISTANCES_M = (0.005, 0.01, 0.02, 0.05, 0.10)
PD_DIRECTIONS = {"+x": (1, 0), "-x": (-1, 0), "+y": (0, 1), "-y": (0, -1)}
PF_ANCHORS = ("A", "B")
PF_ANCHOR_Z_M = 2.40
PF_STANDOFF_M = 0.30
DENSE_ANGLES = tuple(i * STEP_DEG for i in range(-24, 25))


def teach_stations(samples):
    """Find the frozen base, selected achieved sweep, and dense grid per station."""
    rows = defaultdict(list)
    for row in samples:
        if row["set"] == "P-A_TEACH":
            rows[row["station_id"]].append(row)
    if tuple(rows) != STATIONS:
        raise ValueError("Frozen TEACH requires 18 ordered stations")
    stations = {}
    for station, group in rows.items():
        bases = [r for r in group if r["protocol"] == "base"]
        sweep = [r for r in group if r["protocol"] == "tb3_5pt" and r["selected_5pt"] is True]
        dense = [r for r in group if r["protocol"] == "dense49"]
        if (len(bases) != 1 or [r["planned_rel_deg"] for r in sweep] != TB3_ANGLES
                or tuple(r["planned_rel_deg"] for r in dense) != DENSE_ANGLES
                or [r["sequence_index"] for r in group] != sorted({r["sequence_index"] for r in group})):
            raise ValueError(f"Unexpected frozen TEACH observations at {station}")
        base = bases[0]
        for row in [*sweep, *dense]:
            if (math.hypot(row["x"] - base["x"], row["y"] - base["y"]) > POSE_TOL
                    or abs(wrap_deg(row["yaw_body_deg"] - base["yaw_body_deg"]
                                    - row["achieved_rel_deg"])) > 1e-9):
                raise ValueError(f"Inconsistent frozen TEACH yaw or rotation center at {station}")
        stations[station] = dict(base=base, tb3_5pt=sweep, dense49=dense)
    return stations


def teach_observation(source):
    """Copy observation data and preserve the original G0 pose and sample keys."""
    keys = ("x", "y", "yaw_body_deg", "protocol", "motion", "station_id",
            "planned_rel_deg", "achieved_rel_deg", "source_label", "selected_5pt", "segment")
    return {k: source[k] for k in keys} | dict(
        source_set="P-A_TEACH", source_pose_id=source["pose_id"],
        source_sequence_index=source["sequence_index"],
    )


def build_pd_rows(stations):
    """Apply every world-frame displacement to the frozen TEACH base XY."""
    rows = []
    for group in stations.values():
        for distance, (direction, (ux, uy)) in itertools.product(PD_DISTANCES_M, PD_DIRECTIONS.items()):
            x = group["base"]["x"] + distance * ux
            y = group["base"]["y"] + distance * uy
            for source in group["tb3_5pt"]:
                rows.append(teach_observation(source) | dict(
                    x=x, y=y, offset_m=distance, offset_direction=direction,
                ))
    return rows


def build_pf_rows(stations):
    """Reuse all 5+49 TEACH observations in a separate 0.30 m standoff store."""
    return [teach_observation(row) for group in stations.values()
            for row in (*group["tb3_5pt"], *group["dense49"])]


def pf_scene_entry(geometry, anchor, entry):
    """Keep the baseline scene, antenna axis and RX height; adjust target TX Z."""
    if geometry != "G-T1" or anchor not in PF_ANCHORS:
        raise ValueError(f"P-F does not apply to {geometry}/{anchor}")
    x, y, original_z = entry["anchors_xyz_m"][anchor]
    length, width, height = entry["dimensions_m"]
    if (not math.isclose(height - PF_ANCHOR_Z_M, PF_STANDOFF_M, rel_tol=0, abs_tol=1e-12)
            or not math.isclose(height - original_z, 0.05, rel_tol=0, abs_tol=1e-12)
            or not 0 < x < length or not abs(y) < width / 2
            or not 0 < entry["rx_z_m"] < PF_ANCHOR_Z_M < height):
        raise ValueError(f"Inconsistent baseline anchor placement or P-F standoff at {geometry}/{anchor}")
    return dict(entry, anchors_xyz_m=dict(entry["anchors_xyz_m"]) | {anchor: [x, y, PF_ANCHOR_Z_M]})


def pose_buckets(poses):
    """Validate and index contiguous, physically unique RF pose IDs."""
    buckets = defaultdict(list)
    for i, pose in enumerate(poses):
        if (pose["pose_id"] != i or not all(math.isfinite(pose[k]) for k in ("x", "y", "yaw_body_deg"))
                or not -180 <= pose["yaw_body_deg"] < 180):
            raise ValueError(f"Invalid RF pose at row {i}")
        cell, same = matching_poses(pose, poses, buckets)
        if same:
            raise ValueError(f"Duplicate RF pose {i}: {same}")
        buckets[cell].append(i)
    return buckets


def build_arm_tables(rows_by_set, *, baseline_poses=()):
    """Allocate unique RF IDs, leaving any original IDs and observations intact.

    P-F must occupy a separate table and trace directory because its TX height
    differs. A normal-arm table can be preseeded with G0 pose IDs so repeat
    observations reference stored H by physical identity.
    """
    if "P-F" in rows_by_set and (len(rows_by_set) != 1 or baseline_poses):
        raise ValueError("P-F requires a separate RF pose table and trace store")
    poses = list(baseline_poses)
    buckets = pose_buckets(poses)
    samples = []
    for set_name, rows in rows_by_set.items():
        along, total_yaw, previous_main = 0.0, 0.0, None
        for sequence_index, row in enumerate(rows):
            series = "dense49" if row["protocol"] == "dense49" else "main"
            if series == "main":
                if previous_main is not None:
                    along += math.hypot(row["x"] - previous_main["x"], row["y"] - previous_main["y"])
                    total_yaw += abs(wrap_deg(row["yaw_body_deg"] - previous_main["yaw_body_deg"]))
                previous_main = row
            cell, equivalent = matching_poses(row, poses, buckets)
            if equivalent:
                pose_id = min(equivalent)
            else:
                pose_id = len(poses)
                poses.append(dict(pose_id=pose_id, x=row["x"], y=row["y"], yaw_body_deg=row["yaw_body_deg"]))
                buckets[cell].append(pose_id)
            samples.append(row | dict(set=set_name, sequence_index=sequence_index, series=series,
                                      along=along, cum_abs_dtheta_deg=total_yaw, pose_id=pose_id))
    return poses, samples, rf_tasks(poses)


def validate_arm_tables(geometry, anchor, scene, poses, samples, tasks, *, baseline_count=0):
    """Apply the G0 RF-table, pose-reference, clearance and sequencing checks.

    Base routes and scene meshes retain their existing G0 checks. No movement
    is specified between synthetic visits, so no path is inferred across the
    observations of different offset conditions or between stations.
    """
    pose_buckets(poses)
    if not samples or not 0 <= baseline_count <= len(poses):
        raise ValueError("Invalid additional observation table or G0 pose prefix")
    sets = {row["set"] for row in samples}
    if ("P-D" in sets and geometry != "G-T1") or (
        "P-F" in sets and (sets != {"P-F"} or baseline_count or geometry != "G-T1" or anchor not in PF_ANCHORS)
    ):
        raise ValueError(f"Diagnostic arm is outside its specified geometry or anchor at {geometry}/{anchor}")
    if tasks != rf_tasks(poses):
        raise ValueError("Trace tasks do not partition the RF pose table by XY")
    positive = wall_profile(geometry, positive=True)
    negative = wall_profile(geometry, positive=False)
    boundary = [*negative, *reversed(positive), negative[0]]
    walls = list(itertools.pairwise(boundary))
    ax, ay, az = scene["anchors_xyz_m"][anchor]
    length, width, height = scene["dimensions_m"]
    expected_standoff = PF_STANDOFF_M if "P-F" in sets else 0.05
    if (not 0 < ax < length or not abs(ay) < width / 2 or not 0 < scene["rx_z_m"] < az < height
            or not math.isclose(height - az, expected_standoff, rel_tol=0, abs_tol=1e-12)
            or not math.isclose(width / 2, HALF_WIDTHS[geometry], rel_tol=0, abs_tol=1e-12)):
        raise ValueError(f"Invalid geometry or anchor placement at {geometry}/{anchor}")
    min_axis = min(math.hypot(p["x"] - ax, p["y"] - ay) for p in poses)
    if min_axis < AXIS_MIN:
        raise ValueError(f"Method B anchor-axis clearance {min_axis:.6f} m at {geometry}/{anchor}")

    counts = Counter()
    references = set()
    min_wall = {}
    for row in samples:
        name, index = row["set"], row["sequence_index"]
        if index != counts[name]:
            raise ValueError(f"Unexpected sequence index {index} in {name}")
        counts[name] += 1
        pose_id = row["pose_id"]
        if not isinstance(pose_id, int) or not 0 <= pose_id < len(poses):
            raise ValueError(f"Unknown pose ID {pose_id} in {name}/{index}")
        pose = poses[pose_id]
        if (not all(math.isfinite(row[k]) for k in ("x", "y", "yaw_body_deg"))
                or not -180 <= row["yaw_body_deg"] < 180
                or math.hypot(pose["x"] - row["x"], pose["y"] - row["y"]) > POSE_TOL
                or abs(wrap_deg(pose["yaw_body_deg"] - row["yaw_body_deg"])) > POSE_TOL):
            raise ValueError(f"Pose mismatch {pose_id} in {name}/{index}")
        references.add(pose_id)
        distance = clearance(row, walls)
        if distance < WALL_MIN:
            raise ValueError(f"Wall clearance {distance:.6f} m in {name}/{index}")
        min_wall[name] = min(min_wall.get(name, math.inf), distance)
    if not set(range(baseline_count, len(poses))).issubset(references):
        raise ValueError("Unreferenced new RF pose IDs")
    return dict(observations=dict(counts), min_wall_clearance_m=min_wall, min_anchor_axis_clearance_m=min_axis,
                rf_poses=len(poses), new_rf_poses=len(poses) - baseline_count, trace_positions=len(tasks))


def validate_pd_rows(stations, rows):
    """Verify every specified displacement and all five recorded TEACH yaws."""
    groups = defaultdict(list)
    for row in rows:
        groups[row["station_id"], row["offset_m"], row["offset_direction"]].append(row)
    expected = set(itertools.product(STATIONS, PD_DISTANCES_M, PD_DIRECTIONS))
    if groups.keys() != expected:
        raise ValueError("P-D does not cover the required stations, distances and directions")
    max_offset_error = 0.0
    for (station, distance, direction), group in groups.items():
        base = stations[station]["base"]
        ux, uy = PD_DIRECTIONS[direction]
        for observed, source in zip(group, stations[station]["tb3_5pt"], strict=True):
            ref = teach_observation(source)
            if any(observed[k] != ref[k] for k in ref.keys() - {"x", "y"}):
                raise ValueError(f"P-D changed a TEACH yaw or provenance entry at {station}")
            dx, dy = observed["x"] - base["x"], observed["y"] - base["y"]
            offset_error = math.hypot(dx - distance * ux, dy - distance * uy)
            if not math.isfinite(offset_error) or offset_error > 1e-12:
                raise ValueError(f"P-D offset mismatch at {station}/{distance}/{direction}")
            max_offset_error = max(max_offset_error, offset_error)
    return dict(observations=len(rows), displacement_conditions=len(groups),
                max_displacement_vector_error_m=max_offset_error)


def validate_pf_rows(stations, rows):
    """Verify that the P-F receiver observations are identical to frozen TEACH."""
    source = [r for group in stations.values() for r in (*group["tb3_5pt"], *group["dense49"])]
    if len(rows) != len(STATIONS) * 54:
        raise ValueError("P-F must retain all 54 observations at every station")
    for row, reference in zip(rows, source, strict=True):
        ref = teach_observation(reference)
        if any(row[k] != v for k, v in ref.items()):
            raise ValueError(f"P-F changed a TEACH pose or its provenance at {row['station_id']}")
    return dict(observations=len(rows), matched_nominal_pose_ids=len({r["source_pose_id"] for r in rows}),
                anchor_height_m=PF_ANCHOR_Z_M, anchor_standoff_m=PF_STANDOFF_M)
