"""Recompute recorded TB3 yaw, elapsed sweep times, and IMU summaries."""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path
import re

import numpy as np

from run_step1 import dump, wrap

MOTION = "data/raw/tb3_motion_20261004_20261111"
IMU = "data/raw/tb3_imu_allan_20261113T022519Z"
TEACH = f"{MOTION}/trackA/teach/teach.json"
REPEAT = f"{MOTION}/trackA/repeat_20261004_141119/repeat.json"


def read(path):
    return json.loads(path.read_bytes())


def stats(x):
    return dict(n=len(x), mean=float(np.mean(x)), sd_ddof1=float(np.std(x, ddof=1)),
                median=float(np.median(x)), min=float(np.min(x)), max=float(np.max(x)))


def times(path, kind):
    records = {}
    pattern = re.compile(r"^\[(\d+):(\d+):(\d+)\] " + kind + r" (P\d+) +[+-]?\d+(?:\.\d+)?deg\b")
    for line in path.read_text(encoding="utf-8").splitlines():
        m = pattern.match(line)
        if m:
            h, minutes, seconds = map(int, m.groups()[:3])
            records.setdefault(m.group(4), []).append(3600*h + 60*minutes + seconds)
    return {station: (events[-1] - events[0]) % 86400 for station, events in records.items() if len(events) >= 2}


def yaw(stations, selector):
    return np.degrees([selector(s)["odom"][2] for s in stations])


def make(root, receipt):
    teach = read(root / TEACH)["stations"]
    repeat = read(root / REPEAT)["stations"]
    ids = [s["station_id"] for s in teach]
    if ids != [s["station_id"] for s in repeat] or len(ids) != 18:
        raise ValueError("Expected 18 matched TB3 stations")
    start_t = yaw(teach, lambda s: s["base"])
    start_r = yaw(repeat, lambda s: s["align"][-1])
    end_t = yaw(teach, lambda s: s["base_after"])
    end_r = yaw(repeat, lambda s: s["base_after"])
    dt, dr = wrap(np.diff(start_t)), wrap(np.diff(start_r))
    residual = wrap(dr-dt)
    end_residual = wrap(wrap(np.diff(end_r))-dt)
    variants = {}
    for tk, ty in (("teach_base", start_t), ("teach_base_after", end_t)):
        for rk, ry in (("repeat_last_align", start_r), ("repeat_base_after", end_r)):
            variants[f"{tk}__{rk}"] = stats(wrap(wrap(np.diff(ry))-wrap(np.diff(ty))))
    log_t = times((root / TEACH).parent / "events.log", "TEACH")
    log_r = times((root / REPEAT).parent / "events.log", "REPEAT")
    samples_rel = f"{IMU}/imu_samples.csv.gz"
    with gzip.open(root / samples_rel, "rt", newline="", encoding="utf-8") as f:
        gyro = np.array([float(row["gyro_z"]) for row in csv.DictReader(f)])
    summary = read(root / IMU / "summary.json")
    if len(gyro) != summary["counts"]["/imu"]:
        raise ValueError("IMU sample count mismatch")
    straight = read(root / MOTION / "corridor_5p07m/receipt.json")
    replay = read(root / MOTION / "corridor_5p07m/replay.json")
    source_info = json.loads(receipt.read_text(encoding="utf-8-sig"))["inputs"]
    source_paths = [TEACH, REPEAT, f"{MOTION}/trackA/teach/events.log",
                    f"{MOTION}/trackA/repeat_20261004_141119/events.log", samples_rel,
                    f"{IMU}/summary.json", f"{IMU}/allan_variance.csv",
                    f"{MOTION}/corridor_5p07m/receipt.json", f"{MOTION}/corridor_5p07m/replay.json"]
    return dict(question_id="G1-FLOOR-001", inputs={p: source_info[p] for p in source_paths},
                method="signed circular differences of successive TEACH base and REPEAT last alignment odometry yaw",
                station_ids=ids, teach_increment_deg=dt.tolist(), repeat_increment_deg=dr.tolist(),
                teach_summary_deg=stats(dt), repeat_summary_deg=stats(dr), paired_delta_deg=stats(residual),
                paired_endpoint_variants=variants,
                spec_sigma_w_deg=.34, spec_paired_sd_deg=.48, spec_sigma_w_reproduced=False,
                alternate_sigma_w_deg=float(np.std(residual, ddof=1)/np.sqrt(2.)),
                alternate_sigma_note="Sensitivity only; assumes independent equal-variance increments across these two runs.",
                beta_uncal_deg=float((dt.mean()+dr.mean())/2), beta_uncal_spec_deg=2.05,
                beta_res_primary_deg=.45, between_run_sd_identified=False,
                sweep_return_teach=stats(wrap(end_t-start_t)), sweep_return_repeat=stats(wrap(end_r-start_r)),
                sweep_log_duration_proxy_s={"teach": log_t, "repeat": log_r},
                sweep_log_duration_proxy_summary_s={"teach": stats(list(log_t.values())), "repeat": stats(list(log_r.values()))},
                actual_stopped_duration_s=None,
                dwell_note="First to last timestamped angle event; includes angle travel and capture; second resolution.",
                static_imu={"gyro_z_rad_s": stats(gyro), "nonzero": int(np.count_nonzero(gyro)),
                            "mean_deg_s": float(np.degrees(gyro.mean())),
                            "span_s": summary["header_span_s"],
                            "allan_deviation_near_1s": summary["allan_deviation_near_1s"],
                            "raw_gyro_noise_identified": False, "spec_drift_deg_s": .0005,
                            "log_proxy_times_spec_drift_deg": .0005 * float(np.median(list(log_t.values())))},
                straight={"along_m": straight["drive_along_m"], "end_odom_cross_m": straight["drive_cross_m"],
                          "peak_abs_odom_cross_m": straight["maximum_abs_cross_m"],
                          "yaw_delta_odom_deg": float(wrap(np.degrees(straight["drive_end_odom"][2]
                                                                       - straight["drive_origin_odom"][2]))),
                          "replay_top_level_keys": list(replay), "kappa_identified": False})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    dump(a.out, make(a.inputs, a.receipt))


if __name__ == "__main__":
    main()

