#!/usr/bin/env python3
"""Validate P0 frozen inputs without modifying sources or running an EKF."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


def digest(path):
    sha = hashlib.sha256()
    git = hashlib.sha1()
    size = path.stat().st_size
    git.update(b"blob " + str(size).encode("ascii") + b"\0")
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
            git.update(chunk)
    return sha.hexdigest(), git.hexdigest()


def run():
    here = Path(__file__).resolve().parent
    repo = here.parents[1]
    spec = json.loads((here / "P0_INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    errors = []
    for item in spec["assets"]:
        p = repo / item["path"]
        if not p.is_file():
            errors.append("MISSING " + item["path"])
            continue
        if p.stat().st_size != item["bytes"]:
            errors.append("SIZE " + item["path"])
            continue
        h, blob = digest(p)
        if item.get("sha256") and h != item["sha256"]:
            errors.append("SHA256 " + item["path"])
        if blob != item["git_blob_sha1"]:
            errors.append("BLOB " + item["path"])
        if p.suffix == ".npy" and "shape" in item:
            try:
                a = np.load(p, allow_pickle=False, mmap_mode="r")
                if list(a.shape) != item["shape"]:
                    errors.append("SHAPE " + item["path"])
            except Exception as exc:
                errors.append("NPY " + item["path"] + " " + str(exc))
    timelines = {}
    for info in spec["routes"]:
        p = repo / info["path"]
        if not p.is_file():
            continue
        with p.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        if len(rows) != info["samples"]:
            errors.append("TIMELINE_ROWS " + info["id"])
        try:
            if any(float(rows[i]["t_s"]) <= float(rows[i - 1]["t_s"]) for i in range(1, len(rows))):
                errors.append("NONMONOTONIC_TIME " + info["id"])
        except Exception:
            errors.append("TIME_PARSE " + info["id"])
        timelines[info["id"]] = rows
    for info in spec["cases"]:
        p = repo / info["samples_path"]
        if not p.is_file() or info["route"] not in timelines:
            continue
        try:
            samples = json.loads(p.read_text(encoding="utf-8"))
            by_id = {int(x["pose_id"]): x for x in samples}
            if len(by_id) != len(samples) or len(samples) != info["rf_count"]:
                errors.append("POSE_COUNT_OR_DUPLICATE " + info["id"])
            for row in timelines[info["route"]]:
                sid = int(row["pose_id"])
                match = by_id.get(sid)
                if match is None:
                    errors.append("POSE_MISSING " + info["id"] + ":" + str(sid))
                    break
                dx = abs(float(row["x"]) - float(match["x"]))
                dy = abs(float(row["y"]) - float(match["y"]))
                diff = (float(row["yaw_body_deg"]) - float(match["yaw_body_deg"]) + 180) % 360 - 180
                if max(dx, dy) > 1e-5 or abs(diff) > 1e-4:
                    errors.append("POSE_COORD " + info["id"] + ":" + str(sid))
                    break
        except Exception as exc:
            errors.append("POSE_PARSE " + info["id"] + " " + str(exc))
    result = {
        "status": "PASS_LOCAL_SHA256_SHAPE_POSE_PREFLIGHT" if not errors else "FAIL_INPUT_PRECHECK",
        "assets": len(spec["assets"]),
        "cases": len(spec["cases"]),
        "routes": len(timelines),
        "errors_first_100": errors[:100],
        "error_count": len(errors),
        "independent_3state_EKF_runs": 0,
        "scientific_PASS": False
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(run())
