"""Freeze the G1-RT-TB3-002 XY sample before any RF result is computed."""

from collections import defaultdict
from itertools import product

SAMPLE_POLICY = (
    "Transfer the frozen main G3 target of 195 XY to the G7 diagnostic arms. "
    "P-D: per anchor, one XY for every offset magnitude/direction pair, cycling "
    "through all 18 stations with anchor-dependent rotation. "
    "P-E: per case, P001/P009/P018 plus eight rotating stations, one XY and "
    "balanced revisit indices per station; all 18 stations across the nine cases. "
    "P-F: all 18 station XY per anchor. At each selected XY include all yaws of "
    "each selected diagnostic arm. No RF-dependent selection."
)
ARMS = ("P-D", "P-E", "P-F")
STATIONS = tuple(f"P{i:03d}" for i in range(1, 19))
OFFSET_CELLS = tuple(product((0.005, 0.01, 0.02, 0.05, 0.10), ("+x", "-x", "+y", "-y")))
GEOMETRIES = ("G-T1", "G-T2", "G-V")


def sample(poses, tasks, rows, case):
    geometry, anchor, *suffix = case.split("_")
    anchor_index = "ABC".index(anchor)
    task_by_pose = {pose_id: task for task in tasks for pose_id in task["pose_ids"]}
    groups = defaultdict(dict)
    for row in rows:
        arm = row["set"]
        station = row["station_id"]
        if arm == "P-D":
            key = (station, row["offset_m"], row["offset_direction"])
        elif arm == "P-E":
            key = (station, row["revisit_index"])
        elif arm == "P-F":
            key = (station,)
        else:
            raise ValueError(f"Unexpected G7 diagnostic arm: {arm}")
        task = task_by_pose[row["pose_id"]]
        group = groups[arm].setdefault(key, (task, {}))
        if task["task_id"] != group[0]["task_id"]:
            raise ValueError(f"{case}/{arm}/{key}: expected one XY for all arm yaw poses")
        group[1][row["pose_id"]] = None

    plan = {}
    if suffix:
        plan["P-F"] = [(station,) for station in STATIONS]
    else:
        if geometry == "G-T1":
            plan["P-D"] = [
                (STATIONS[(i + 6 * anchor_index) % 18], offset, direction)
                for i, (offset, direction) in enumerate(OFFSET_CELLS)
            ]
        case_index = GEOMETRIES.index(geometry) * 3 + anchor_index
        fixed = (STATIONS[0], STATIONS[8], STATIONS[-1])
        rotating = tuple(station for station in STATIONS if station not in fixed)
        stations = fixed + tuple(rotating[(2 * case_index + i) % len(rotating)] for i in range(8))
        plan["P-E"] = [(station, (i + case_index) % 3 + 1) for i, station in enumerate(stations)]

    if set(groups) != set(plan):
        raise ValueError(f"{case}: missing or unexpected G7 arm")
    selected = {}
    for arm, keys in plan.items():
        for key in keys:
            task, pose_ids = groups[arm][key]
            if len(pose_ids) != (54 if arm == "P-F" else 5):
                raise ValueError(f"{case}/{arm}/{key}: incomplete arm-yaw coverage")
            entry = selected.setdefault(task["task_id"], task | {"arms": {}})
            if arm in entry["arms"]:
                raise ValueError(f"{case}/{arm}/{key}: duplicate selected XY")
            entry["arms"][arm] = dict(
                selection=list(key),
                sampled_yaws=[dict(pose_id=pid, yaw_deg=poses[pid]["yaw_body_deg"]) for pid in pose_ids],
            )
    if len(selected) != sum(len(keys) for keys in plan.values()):
        raise ValueError(f"{case}: diagnostic arms share a selected XY, expected distinct XY")
    return list(selected.values())
