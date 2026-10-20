#!/usr/bin/env python3
"""Plan/validate RF pose lists for the fixed existing corridor and office.
This script does NOT run Sionna, build H, or produce observed sensor data.
Must be run inside the pinned claude/office-e-layout based checkout.
"""
import argparse
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.scenarios.corridor import CorridorSetup
from qclean_uwb.scenarios.office import OfficeSetup

def angular_delta(target, current):
    return (target - current + 180.0) % 360.0 - 180.0

def validate_position(scene, x, y):
    if scene == "CORRIDOR_EXISTING":
        s = CorridorSetup()
        return s.robot_x_range_m[0] <= x <= s.robot_x_range_m[1] and abs(y) <= s.robot_y_limit_m + 1e-9
    if scene == "OFFICE_E_EXISTING":
        s = OfficeSetup()
        clearance = max(s.robot_body_lwh_m[:2]) / 2 + s.robot_clearance_m
        return s.is_free(x, y, clearance)
    raise ValueError("Unknown scene " + scene)

def generate(request, route):
    m = request["motion"]
    dt, v, omega = (float(m[key]) for key in ("dt_s", "v_mps", "yaw_rate_dps"))
    if not (0.0 < dt < 1.0 and 0 < v <= 0.4 and 0 < omega <= 45):
        raise ValueError("Invalid discretization/velocity")
    waypoints = route["waypoints_xy_m"]
    x, y = map(float, waypoints[0])
    dx, dy = waypoints[1][0] - x, waypoints[1][1] - y
    yaw = math.degrees(math.atan2(dy, dx))
    rows, t = [], 0.0

    def record(phase, force):
        nonlocal t
        if not validate_position(route["environment"], x, y):
            raise ValueError("Collision/clearance failed: %s %.6f %.6f" % (route["id"], x, y))
        rows.append(dict(
            route_id=route["id"], pose_id=len(rows), t_s=round(t, 6),
            x_m=round(x, 6), y_m=round(y, 6), z_m=float(m["z_m"]),
            yaw_body_deg=round(yaw % 360, 6),
            yaw_antenna_deg=round((yaw + m["mount_deg"]) % 360, 6),
            phase=phase, force_radio=int(force)))
        t += dt

    def rotate_to(target, phase):
        nonlocal yaw
        diff = angular_delta(target, yaw)
        count = math.ceil(abs(diff) / (omega * dt))
        for _ in range(count):
            yaw += diff / count
            record(phase, True)

    def scan():
        base = yaw
        for target in (base - 10, base + 10, base):
            rotate_to(target, "YAW_SCAN")

    record("START", True)
    if 0 in route.get("scan_at_waypoint_indices", []):
        scan()
    for ix, waypoint in enumerate(waypoints[1:], 1):
        targetx, targety = map(float, waypoint)
        ddx, ddy = targetx - x, targety - y
        length = math.hypot(ddx, ddy)
        if length == 0:
            raise ValueError("Repeated consecutive waypoint")
        rotate_to(math.degrees(math.atan2(ddy, ddx)), "IN_PLACE_TURN")
        beginx, beginy = x, y
        count = math.ceil(length / (v * dt))
        for j in range(1, count + 1):
            x = beginx + ddx * j / count
            y = beginy + ddy * j / count
            record("STRAIGHT", j == count)
        if ix in route.get("scan_at_waypoint_indices", []):
            scan()
        record("DWELL", True)
        record("DWELL", True)

    if math.hypot(x - waypoints[0][0], y - waypoints[0][1]) < 1e-8:
        target = math.degrees(math.atan2(
            waypoints[1][1] - waypoints[0][1], waypoints[1][0] - waypoints[0][0]))
        rotate_to(target, "FINAL_ORIENTATION_RESTORE")
    stride = int(m["rf_stride"])
    if stride < 1:
        raise ValueError("Invalid radio stride")
    for i, row in enumerate(rows):
        row["rf_sample"] = int(bool(row.pop("force_radio")) or i % stride == 0)
    if not all(rows[i + 1]["t_s"] > rows[i]["t_s"] for i in range(len(rows) - 1)):
        raise AssertionError("Nonmonotone clock")
    if not any(row["rf_sample"] for row in rows):
        raise AssertionError("Missing radio poses")
    return rows

def emit_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default=str(HERE / "01_ROUTE_REQUEST.json"))
    parser.add_argument("--out", default=str(HERE / "generated"))
    args = parser.parse_args()
    request = json.loads(Path(args.request).read_text(encoding="utf-8"))
    if request["schema"] != "POWERJOINT_M45_EXISTING_SCENES_REQUEST_V2":
        raise RuntimeError("Wrong request version")
    src = json.loads((ROOT / "results/OFFICE_SETUP_20261007/OFFICE_SETUP.json").read_text())
    if src["config_sha256"] != request["provenance"]["office_setup_sha256"]:
        raise RuntimeError("Office configuration changed")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report, cases = [], []
    for route in request["routes"]:
        arr = generate(request, route)
        path = out / (route["id"] + "_ROUTE_POSE.csv")
        emit_csv(path, arr)
        radio = [r for r in arr if r["rf_sample"]]
        radio_path = out / (route["id"] + "_RADIO_POSE.csv")
        emit_csv(radio_path, radio)
        record = {
            "id": route["id"], "scene": route["environment"],
            "frames_motion": len(arr), "frames_radio": len(radio),
            "duration_s": arr[-1]["t_s"], "anchors": route["anchors"],
            "pose_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "radio_sha256": hashlib.sha256(radio_path.read_bytes()).hexdigest()
        }
        report.append(record)
        for anchor in route["anchors"]:
            cases.append(dict(case_id=route["id"] + "_" + anchor + "_M45",
                              scene=route["environment"], anchor=anchor,
                              mount_deg=45, n_radio_frames=len(radio),
                              channels="FULL|DIRECT_LOS", status="NOT_RUN"))
    emit_csv(out / "CASE_MATRIX.csv", cases)
    preflight = {
        "status": "ROUTE_GEOMETRY_ONLY_PASS_NOT_RF",
        "scene_count": 2, "route_count": len(report), "route_anchor_cases": len(cases),
        "routes": report, "full_h_generated": False,
        "sensor_v2_generated": False,
        "independent_scene_claim": False
    }
    (out / "ROUTE_PREFLIGHT.json").write_text(
        json.dumps(preflight, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps(preflight, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
