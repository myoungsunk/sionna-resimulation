"""Build G1 RF pose tables and ordered observations from the pinned TB3 inputs."""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import sqlite3
import struct
from collections import defaultdict
from pathlib import Path

import numpy as np

from build_tb3_scene import ANCHORS, HALF_WIDTHS, lane_y, sha256, write_json

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/tb3_motion_20261004_20261111"
INPUTS = {
    "teach": "trackA/teach/teach.json",
    "repeat": "trackA/repeat_20261004_141119/repeat.json",
    "bag": "corridor_5p07m/bag/bag_0.db3",
    "receipt": "corridor_5p07m/receipt.json",
    "replay": "corridor_5p07m/replay.json",
}
STEP_M, STEP_DEG, POSE_TOL = 0.02, 2.5, 1e-6
C3_RADIUS_M = 0.40
X0_M = 6.0
TB3_ANGLES = [-60, -30, 0, 30, 60]


def verified_inputs(raw: Path) -> dict:
    expected = dict((path, digest) for digest, path in
                    (line.split(maxsplit=1) for line in
                     (raw / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines() if line.strip()))
    files = {name: raw / rel for name, rel in INPUTS.items()}
    for name, path in files.items():
        if sha256(path) != expected[INPUTS[name]]:
            raise ValueError(f"Input checksum mismatch: {path}")
    return files


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def wrap_deg(angle):
    return (angle + 180.0) % 360.0 - 180.0


def rotate(x, y, theta):
    c, s = math.cos(theta), math.sin(theta)
    return c * x - s * y, s * x + c * y


def add_pose(reference, relative):
    x, y, yaw = reference
    dx, dy = rotate(*relative[:2], yaw)
    return x + dx, y + dy, yaw + relative[2]


def observation(pose, protocol, motion, *, station=None, planned=None, achieved=None,
                source=None, selected=None, segment=None):
    x, y, yaw = pose
    return dict(x=float(x), y=float(y), yaw_body_deg=wrap_deg(float(yaw)),
                protocol=protocol, motion=motion, station_id=station,
                planned_rel_deg=planned, achieved_rel_deg=achieved, source_label=source,
                selected_5pt=selected, segment=segment)


def sweeps(teach, repeat, lane):
    if teach["status"] != "COMPLETE" or repeat["status"] != "COMPLETE":
        raise ValueError("Both trackA acquisitions must be complete")
    taught, repeated = teach["stations"], repeat["stations"]
    station_ids = [f"P{i:03d}" for i in range(1, 19)]
    if any([s["station_id"] for s in run] != station_ids for run in (taught, repeated)):
        raise ValueError("Unexpected trackA station IDs or order")

    result = {"P-A_TEACH": [], "P-A_REPEAT": []}
    base_poses = []
    for t, r in zip(taught, repeated):
        station = t["station_id"]
        along, lateral, yaw = t["base"]["line_pose"]
        ref = (X0_M + along, lane + lateral, yaw)
        base_poses.append((*ref[:2], math.degrees(yaw)))
        align = r["align"][-1]
        if not align["icp"]["usable"] or not r["base_after"]["icp"]["usable"]:
            raise ValueError(f"Unusable REPEAT alignment at {station}")
        repeat_base = add_pose(ref, align["observed_correction"])
        for key, base, base_label in (
            ("P-A_TEACH", ref, t["base"]["label"]), ("P-A_REPEAT", repeat_base, align["label"])
        ):
            rows = result[key]
            base_yaw = math.degrees(base[2])
            rows.append(observation((*base[:2], base_yaw), "base", "stationary",
                                    station=station, planned=0.0, achieved=0.0, source=base_label))
            observed = sorted(t["angles"], key=lambda angle: angle["order"]) if key == "P-A_TEACH" else r["angles"]
            if [angle["angle_deg"] for angle in observed] != TB3_ANGLES:
                raise ValueError(f"Unexpected sweep order at {station}: {key}")
            for angle in observed:
                planned = angle["angle_deg"]
                if key == "P-A_TEACH":
                    attempts = [(angle["label"], angle["achieved_rel_deg"])]
                else:
                    tries = angle["tries"]
                    if not tries[-1]["icp"]["usable"]:
                        raise ValueError(f"Unusable final sweep observation at {station}, {planned}")
                    target_yaw = yaw + math.radians(angle["teach_rel_yaw_deg"])
                    attempts = [
                        (attempt["label"], wrap_deg(math.degrees(
                            target_yaw + attempt["icp"]["pose"][2] - base[2])))
                        for attempt in tries
                    ]
                for index, (label, achieved) in enumerate(attempts):
                    rows.append(observation((*base[:2], base_yaw + achieved), "tb3_5pt",
                                            "in_place", station=station, planned=planned,
                                            achieved=achieved, source=label,
                                            selected=index == len(attempts) - 1))
            if key == "P-A_TEACH":
                after = math.degrees(t["base_after"]["odom"][2] - t["base"]["odom"][2])
                label = t["base_after"]["label"]
            else:
                after = math.degrees(yaw + r["base_after"]["icp"]["pose"][2] - base[2])
                label = r["base_after"]["label"]
            rows.append(observation((*base[:2], base_yaw + after), "base_after", "in_place",
                                    station=station, planned=0.0, achieved=wrap_deg(after), source=label))
            for i in range(-24, 25):
                offset = i * STEP_DEG
                rows.append(observation((*base[:2], base_yaw + offset), "dense49", "in_place",
                                        station=station, planned=offset, achieved=offset))
    return result, base_poses


def intervals(length, limit):
    return max(1, math.ceil(length / limit - 1e-12))


def straight_samples(start, end, *, include_start=False):
    length = math.dist(start[:2], end[:2])
    count = intervals(length, STEP_M)
    yaw_delta = wrap_deg(end[2] - start[2])
    for index in range(0 if include_start else 1, count + 1):
        f = index / count
        yield (start[0] + f * (end[0] - start[0]), start[1] + f * (end[1] - start[1]),
               start[2] + f * yaw_delta)


def transit(bases):
    rows = []
    for index, (start, end) in enumerate(itertools.pairwise(bases), 1):
        rows.extend(observation(pose, "transit", "straight", station=f"P{index:03d}", segment=index)
                    for pose in straight_samples(start, end, include_start=index == 1))
    return rows


def read_cdr_odometry(blob: bytes):
    # CDR encapsulation, ROS Header (Time + string), child_frame_id, then Pose.
    if blob[:2] not in (b"\x00\x00", b"\x00\x01"):
        raise ValueError("Expected ROS 2 CDR1 Odometry")
    order = "<" if blob[1] else ">"
    offset = 12
    for _ in range(2):
        offset += (4 - (offset - 4) % 4) % 4
        size = struct.unpack_from(order + "I", blob, offset)[0]
        if size == 0 or offset + 4 + size > len(blob) or blob[offset + 3 + size] != 0:
            raise ValueError("Invalid CDR frame ID")
        offset += 4 + size
    offset += (8 - (offset - 4) % 8) % 8
    x, y, _, qx, qy, qz, qw = struct.unpack_from(order + "7d", blob, offset)
    if not all(map(math.isfinite, (x, y, qx, qy, qz, qw))) or abs(
        qx*qx + qy*qy + qz*qz + qw*qw - 1
    ) > 1e-6:
        raise ValueError("Invalid odometry pose or quaternion")
    yaw = math.atan2(2 * (qw * qz + qx * qy), 1 - 2 * (qy*qy + qz*qz))
    return x, y, yaw


def load_pb(files):
    receipt, replay = read_json(files["receipt"]), read_json(files["replay"])
    if replay["state"] != "PASS_GEOMETRY_REPLAY" or replay["input_sha256"] != sha256(files["bag"]):
        raise ValueError("P-B replay and bag provenance differ")
    if replay["receipt_sha256"] != sha256(files["receipt"]) or receipt["odom_scale"] != 0.96756:
        raise ValueError("P-B receipt provenance or odom scale mismatch")
    origin, scale = receipt["drive_origin_odom"], receipt["odom_scale"]
    length = receipt["drive_along_m"]
    if abs(length - replay["recorded_distance_m"]) > 1e-9:
        raise ValueError("P-B distance disagrees with the replay")
    with sqlite3.connect(files["bag"].resolve().as_uri() + "?mode=ro", uri=True) as db:
        (topic_id,) = db.execute(
            "SELECT id FROM topics WHERE name='/odom' AND type='nav_msgs/msg/Odometry' "
            "AND serialization_format='cdr'"
        ).fetchone()
        intervals_ns = [(segment["drive_start_ns"], segment["drive_stop_ns"])
                        for segment in receipt["segments"]]
        recorded = [read_cdr_odometry(blob) for start, stop in intervals_ns for (blob,) in db.execute(
            "SELECT data FROM messages WHERE topic_id=? AND timestamp BETWEEN ? AND ? ORDER BY timestamp,id",
            (topic_id, start, stop))]
    travelled = [(0.0, 0.0, 0.0)]
    for x, y, yaw in recorded:
        along, lateral = rotate((x - origin[0]) * scale, (y - origin[1]) * scale, -origin[2])
        if along > travelled[-1][0] + 1e-9:
            travelled.append((along, lateral, wrap_deg(math.degrees(yaw - origin[2]))))
    if abs(travelled[-1][0] - length) > 0.002:
        raise ValueError("P-B bag does not reach the recorded endpoint")
    along, lateral, yaw = np.array(travelled).T
    grid = np.r_[np.arange(0.0, length, STEP_M), length]
    stations = [p["recorded_along_m"] for p in replay["checkpoints"]] + [length]
    wall_y = [p["alignment"]["lateral_m"] for p in replay["checkpoints"]] + [
        replay["end_alignment"]["lateral_m"]]
    if any(b <= a for a, b in itertools.pairwise(stations)):
        raise ValueError("P-B replay checkpoints are not ordered")
    # Replace odom lateral at the wall checkpoints and keep within-interval odom deviations.
    offsets = np.array(wall_y) - np.interp(stations, along, lateral)
    corrected_y = np.interp(grid, along, lateral) + np.interp(grid, stations, offsets)
    return list(zip(grid, corrected_y, np.interp(grid, along, yaw)))


class Route:
    def __init__(self, x, y, yaw=0.0):
        self.rows = [observation((x, y, yaw), "route", "start", segment=0)]
        self.segment = 0

    @property
    def pose(self):
        row = self.rows[-1]
        return row["x"], row["y"], row["yaw_body_deg"]

    def add(self, samples, motion):
        self.segment += 1
        self.rows.extend(observation(pose, "route", motion, segment=self.segment)
                         for pose in samples)

    def turn(self, angle):
        x, y, heading = self.pose
        count = intervals(abs(angle), STEP_DEG)
        self.add(((x, y, heading + angle * i / count) for i in range(1, count + 1)), "in_place")

    def line(self, x, y):
        start = self.pose
        self.add(straight_samples(start, (x, y, start[2])), "straight")

    def arc(self, angle, radius):
        x, y, heading = self.pose
        sign = math.copysign(1, angle)
        offset = rotate(0, sign * radius, math.radians(heading))
        cx, cy = x + offset[0], y + offset[1]
        count = max(intervals(abs(angle), STEP_DEG), intervals(radius * abs(math.radians(angle)), STEP_M))

        def samples():
            for index in range(1, count + 1):
                yaw = heading + angle * index / count
                dx, dy = rotate(0, -sign * radius, math.radians(yaw))
                yield cx + dx, cy + dy, yaw
        self.add(samples(), "arc")


def zigzag(lane):
    center = lane - 0.40
    theta = math.atan(0.60)
    heading = math.degrees(theta)
    tangent = C3_RADIUS_M * math.tan(theta)
    route = Route(4.0, center)
    route.turn(heading)
    for vertex in range(12):
        sign = (-1) ** vertex
        x, y = 4.5 + vertex, center + sign * 0.30
        dx, dy = rotate(tangent, 0, sign * theta)
        route.line(x - dx, y - dy)
        route.arc(-2 * sign * heading, C3_RADIUS_M)
    route.line(16.0, center)
    route.turn(-heading)
    return route.rows


def passive_routes(lane):
    c1 = Route(6.0, lane - 0.8)
    for x, y in [(12.0, lane - 0.8), (12.0, lane), (6.0, lane), (6.0, lane - 0.8)]:
        c1.line(x, y)
        c1.turn(90.0)
    c2 = Route(3.0, lane)
    c2.line(17.0, lane)
    c2.turn(180.0)
    c2.line(3.0, lane)
    c4 = Route(6.0, lane)
    c4.line(12.0, lane)
    c4.turn(-90.0)
    c4.line(12.0, lane - 0.4)
    c4.turn(-90.0)
    c4.line(6.0, lane - 0.4)
    c4.turn(90.0)
    c4.line(6.0, lane - 0.8)
    c4.turn(90.0)
    c4.line(12.0, lane - 0.8)
    return {"C1": c1.rows, "C2": c2.rows, "C3": zigzag(lane), "C4": c4.rows}


def matching_poses(row, poses, buckets):
    x, y, yaw = (row[key] for key in ("x", "y", "yaw_body_deg"))
    cell = math.floor(x / POSE_TOL), math.floor(y / POSE_TOL)
    matches = []
    for dx, dy in itertools.product((-1, 0, 1), repeat=2):
        for i in buckets.get((cell[0] + dx, cell[1] + dy), ()):
            p = poses[i]
            if math.hypot(p["x"] - x, p["y"] - y) <= POSE_TOL and abs(
                wrap_deg(p["yaw_body_deg"] - yaw)
            ) <= POSE_TOL:
                matches.append(i)
    return cell, matches


def rf_pose_table(sets):
    poses, samples = [], []
    buckets = defaultdict(list)
    for name, rows in sets.items():
        along, total_yaw = 0.0, 0.0
        previous_by_series = {}
        for index, row in enumerate(rows):
            series = "dense49" if row["protocol"] == "dense49" else "main"
            previous = previous_by_series.get(series)
            if series == "main" and previous is not None:
                along += math.hypot(row["x"] - previous["x"], row["y"] - previous["y"])
                total_yaw += abs(wrap_deg(row["yaw_body_deg"] - previous["yaw_body_deg"]))
            cell, matches = matching_poses(row, poses, buckets)
            if matches:
                pose_id = min(matches)
            else:
                pose_id = len(poses)
                poses.append(dict(pose_id=pose_id, x=row["x"], y=row["y"], yaw_body_deg=row["yaw_body_deg"]))
                buckets[cell].append(pose_id)
            samples.append(dict(set=name, sequence_index=index, series=series, along=along,
                                cum_abs_dtheta_deg=total_yaw, pose_id=pose_id, **row))
            previous_by_series[series] = row
    return poses, samples


def rf_tasks(poses):
    by_tag = defaultdict(list)
    for p in poses:
        by_tag[f"x{p['x']:.4f}_y{p['y']:.4f}"].append(p)
    tasks = []
    for index, (tag, group) in enumerate(sorted(by_tag.items())):
        x, y = group[0]["x"], group[0]["y"]
        if any(math.hypot(p["x"] - x, p["y"] - y) > POSE_TOL for p in group):
            raise ValueError(f"Method B position tag collision at {tag}")
        tasks.append(dict(task_id=index, tag=tag, x=x, y=y,
                          antenna_yaw_deg=sorted({p["yaw_body_deg"] for p in group}),
                          pose_ids=[p["pose_id"] for p in group]))
    return tasks


def build_poses(out: Path, files: dict):
    out.mkdir(parents=True, exist_ok=False)
    teach, repeat = read_json(files["teach"]), read_json(files["repeat"])
    pb = load_pb(files)
    for geometry in HALF_WIDTHS:
        lane = lane_y(geometry)
        sets, bases = sweeps(teach, repeat, lane)
        sets["P-A_PRIME"] = transit(bases)
        sets["P-B"] = [observation((X0_M + x, lane + y, yaw), "route", "straight")
                       for x, y, yaw in pb]
        sets.update(passive_routes(lane))
        poses, samples = rf_pose_table(sets)
        tasks = rf_tasks(poses)
        for anchor in ANCHORS:
            directory = out / f"{geometry}_{anchor}"
            directory.mkdir()
            write_json(directory / "rf_poses.json", poses)
            write_json(directory / "rf_tasks.json", tasks)
            write_json(directory / "SAMPLES.json", samples)
            with (directory / "TIMELINE.csv").open("x", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=samples[0].keys())
                writer.writeheader()
                writer.writerows(samples)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--raw", default=RAW, type=Path)
    args = parser.parse_args()
    build_poses(args.out, verified_inputs(args.raw))
