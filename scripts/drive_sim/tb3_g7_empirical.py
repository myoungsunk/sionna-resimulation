"""Frozen station-base residuals and deterministic P-E revisit draws."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess

import numpy as np

from build_tb3_poses import wrap_deg
from tb3_g7_arms import STATIONS, teach_observation


SEED = 2026111402
REVISITS = 3
TRACKA = "data/raw/tb3_motion_20261004_20261111/trackA"
REPEAT_1004 = f"{TRACKA}/repeat_20261004_141119/repeat.json"
REPEAT_1113 = f"{TRACKA}/repeat_20261113_061314/repeat.json"
REPEAT_1113_COMMIT = "95ec6c068ce7413b308c4f7825df64b1b9bafb68"
REPEAT_1113_SHA = "004381dc56276e19f1f8d912c3c5dd739c0277191d6d531fcfb84b97485c2dd0"


def load_empirical_pool(root, g0):
    sources = (
        ("2026-10-04", REPEAT_1004, None, g0["input_sha256"][REPEAT_1004]),
        ("2026-11-13", REPEAT_1113, REPEAT_1113_COMMIT, REPEAT_1113_SHA),
    )
    pool, files = [], []
    for date, path, commit, expected_sha in sources:
        raw = (root / path).read_bytes() if commit is None else subprocess.check_output(
            ["git", "-C", str(root), "show", f"{commit}:{path}"],
        )
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_sha:
            raise ValueError(f"Repeat checksum mismatch for {date}")
        doc = json.loads(raw)
        stations = doc["stations"]
        if (doc["kind"] != "repeat" or doc["status"] != "COMPLETE"
                or not doc["created"].startswith(date)
                or tuple(s["station_id"] for s in stations) != STATIONS):
            raise ValueError(f"Incomplete or unexpected station coverage for {date}")
        files.append(dict(date=date, path=path, git_commit=commit, sha256=digest, stations=len(stations)))
        for station in stations:
            # Same observed REPEAT base displacement used by G0. The raw ICP
            # translation can include a component along a declared weak axis.
            final = station["align"][-1]
            xy = final["observed_correction"][:2]
            raw_pose = final["icp"]["pose"]
            yaw = float(raw_pose[2])
            if (not final["icp"]["usable"] or not all(math.isfinite(v) for v in (*xy, *raw_pose))
                    or yaw != final["observed_correction"][2] or len(xy) != 2):
                raise ValueError(f"Unusable final station base at {date}/{station['station_id']}")
            pool.append(dict(
                index=len(pool), date=date, station_id=station["station_id"],
                xy_m=xy, distance_m=math.hypot(*xy), yaw_rad=yaw,
                raw_icp_pose=raw_pose, weak_axis=final["icp"]["weak_axis"],
                source_label=final["label"],
            ))
    return pool, files


def sample_revisits(pool):
    """Draw a shared set of perturbations for controlled comparisons across cases."""
    rng = np.random.Generator(np.random.PCG64(SEED))
    visits = []
    for station in STATIONS:
        for visit in range(1, REVISITS + 1):
            distance_index = int(rng.integers(len(pool)))
            direction = float(rng.uniform(0, math.tau))
            yaw_index = int(rng.integers(len(pool)))
            visits.append(dict(
                station_id=station, revisit_index=visit, distance_index=distance_index,
                direction_rad=direction, yaw_index=yaw_index,
                distance_m=pool[distance_index]["distance_m"],
                yaw_delta_deg=math.degrees(pool[yaw_index]["yaw_rad"]),
            ))
    return visits


def build_pe_rows(stations, visits):
    rows = []
    for visit in visits:
        group = stations[visit["station_id"]]
        base = group["base"]
        d, angle = visit["distance_m"], visit["direction_rad"]
        for source in group["tb3_5pt"]:
            rows.append(teach_observation(source) | dict(
                x=base["x"] + d * math.cos(angle), y=base["y"] + d * math.sin(angle),
                yaw_body_deg=wrap_deg(source["yaw_body_deg"] + visit["yaw_delta_deg"]),
                revisit_index=visit["revisit_index"],
            ))
    return rows


def validate_pe_rows(stations, pool, visits, rows):
    if visits != sample_revisits(pool):
        raise ValueError("P-E empirical draws could not be replayed from their seed")
    max_xy, max_yaw = 0., 0.
    if len(rows) != 5 * len(visits):
        raise ValueError("P-E does not have five rows per revisit")
    for index, visit in enumerate(visits):
        group = stations[visit["station_id"]]
        base = group["base"]
        for row, source in zip(rows[5*index:5*index+5], group["tb3_5pt"], strict=True):
            reference = teach_observation(source)
            if (row["revisit_index"] != visit["revisit_index"]
                    or any(row[k] != reference[k] for k in reference.keys() - {"x", "y", "yaw_body_deg"})):
                raise ValueError(f"Wrong P-E observation provenance at draw {index}")
            delta_x, delta_y = row["x"] - base["x"], row["y"] - base["y"]
            distance = pool[visit["distance_index"]]["distance_m"]
            direction = visit["direction_rad"]
            xy_error = math.hypot(delta_x - distance * math.cos(direction),
                                  delta_y - distance * math.sin(direction))
            yaw_delta = math.degrees(pool[visit["yaw_index"]]["yaw_rad"])
            yaw_error = abs(wrap_deg(row["yaw_body_deg"] - source["yaw_body_deg"] - yaw_delta))
            if not math.isfinite(xy_error + yaw_error) or xy_error > 1e-12 or yaw_error > 1e-10:
                raise ValueError(f"P-E displacement or yaw replay mismatch at draw {index}")
            max_xy, max_yaw = max(max_xy, xy_error), max(max_yaw, yaw_error)
    return dict(observations=len(rows), revisits=len(visits),
                max_displacement_vector_error_m=max_xy, max_yaw_error_deg=max_yaw)
