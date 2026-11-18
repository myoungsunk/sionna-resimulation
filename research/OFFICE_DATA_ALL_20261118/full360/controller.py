"""Frozen office runner controller. Container entry: python /work/controller.py.

No retries/resume: use a new output directory for every attempt. The source tree
must be mounted read-only at /work/source. Running children finish after a failure.
RUN_CONTRACT.json requires stations, unique_yaws_deg, worker_count, solver,
setup_config_sha256, bank_sha256, source_hashes (source-relative paths -> SHA256).
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import traceback
from types import SimpleNamespace

YAWS = list(range(-180, 180, 10))
CHUNKS = {"neg": YAWS[:18], "nonneg": YAWS[18:]}


def utc():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def validate_contract(contract):
    if contract["worker_count"] != 70 or contract["unique_yaws_deg"] != YAWS:
        raise ValueError("requires 70 workers and exactly -180..170 step 10")
    stations = contract["stations"]
    if len(stations) != 35:
        raise ValueError("requires 35 stations")
    seen = set()
    for i, station in enumerate(stations, 1):
        if station["station_id"] != f"S{i:02d}":
            raise ValueError("stations must be ordered S01..S35")
        xy = (station["x"], station["y"])
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) for v in xy) or xy in seen:
            raise ValueError("nonfinite or duplicate station coordinates")
        if not isinstance(station["los_clear"], bool):
            raise ValueError("los_clear must be boolean")
        seen.add(xy)
    solver = contract["solver"]
    for key, value in {"refraction": True, "samples_per_src": 100000,
                       "max_depth": 3, "seed": 20260924}.items():
        if solver.get(key) != value:
            raise ValueError(f"frozen solver mismatch: {key}")
    if not contract["source_hashes"] or not contract["bank_sha256"]:
        raise ValueError("source and bank hashes are required")
    return stations


def check_source(source, contract):
    checked = {}
    for relative, expected in contract["source_hashes"].items():
        path = (source / relative).resolve()
        if not path.is_relative_to(source.resolve()):
            raise ValueError(f"source path escapes tree: {relative}")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"source hash mismatch: {relative}")
        checked[relative] = actual
    return checked


def make_tasks(stations, work, source):
    tasks = []
    for i, station in enumerate(stations):
        for chunk, yaws in CHUNKS.items():
            tag = f"{station['station_id']}_{chunk}"
            folder = work / "traces" / station["station_id"] / chunk
            command = [sys.executable, str(source / "scripts/corridor_sionna_run.py"),
                       "--scenario", "office", "--out", str(folder), "--xy",
                       str(station["x"]), str(station["y"]), "--position", str(i),
                       "--tag", tag, "--yaws", *map(str, yaws),
                       "--bin-stride", "1", "--threads", "1"]
            tasks.append(dict(task_id=tag, station_id=station["station_id"],
                              chunk=chunk, yaws=yaws, command=command,
                              folder=str(folder), log=str(work / "logs" / f"{tag}.log"),
                              status="pending", exit_code=None))
    return tasks


def pose_tables(tasks, stations, work):
    poses, samples = [], []
    for station in stations:
        station_id = station["station_id"]
        index = {}
        for task in (t for t in tasks if t["station_id"] == station_id):
            raw = (Path(task["folder"]) / f"{task['task_id']}_sweep.npz").relative_to(work).as_posix()
            for local_index, yaw in enumerate(task["yaws"]):
                pose_id = f"{station_id}_yaw_{yaw:+04d}"
                row = dict(station_id=station_id, yaw_deg=yaw, x=station["x"],
                           y=station["y"], z_m=0.45, pose_id=pose_id, h_row=len(poses),
                           raw_trace_path=raw, local_yaw_index=local_index)
                poses.append(row)
                index[yaw] = row
        for sequence_index, yaw in enumerate(range(-180, 181, 10)):
            pose = index[-180 if yaw == 180 else yaw]
            samples.append(dict(sample_id=f"{station_id}_obs_{yaw:+04d}",
                                station_id=station_id, yaw_deg=yaw,
                                sequence_index=sequence_index,
                                pose_id=pose["pose_id"], h_row=pose["h_row"],
                                endpoint_alias=yaw == 180))
    if (len(poses) != 1260 or len(samples) != 1295 or
            len({p["pose_id"] for p in poses}) != 1260 or
            len({s["sample_id"] for s in samples}) != 1295):
        raise ValueError("pose/sample coverage or uniqueness failed")
    return poses, samples


def load_verifier(source, contract, stations):
    # Import once, and build the original expectation once for the entire site.
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("frozen_sweep_verify", source / "scripts/sweep_verify.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    setup, expectation = module.build_expect(SimpleNamespace(
        scenario="office", anchor_x=None, anchor_y=None, bin_stride=1,
        allow_runner_change=False))
    if expectation.solver != contract["solver"]:
        raise ValueError("solver differs from frozen contract")
    if expectation.setup_config_sha256 != contract["setup_config_sha256"]:
        raise ValueError("setup differs from frozen contract")
    if expectation.bank_sha256 != contract["bank_sha256"] or len(expectation.freq_grid_hz) != 257:
        raise ValueError("bank identity/frequency count mismatch")
    for name, expected in expectation.bank_sha256.items():
        if sha256(source / name) != expected:
            raise ValueError(f"bank bytes differ: {name}")
    if not all(item["passed"] for item in setup.validate()):
        raise ValueError("original setup.validate failed")
    for station in stations:
        if (not setup.position_allowed(station["x"], station["y"]) or
                bool(expectation.los_expected(station["x"], station["y"])) != station["los_clear"]):
            raise ValueError(f"station geometry mismatch: {station['station_id']}")
    return module, expectation


def run_tasks(tasks, work, source):
    lock, stop = threading.Lock(), threading.Event()

    def record():
        atomic_json(work / "TASKS.json", tasks)
        counts = {state: sum(t["status"] == state for t in tasks)
                  for state in ("pending", "running", "completed", "failed", "skipped")}
        atomic_json(work / "PROGRESS.json", dict(updated_utc=utc(), **counts,
                                                stop_new_tasks=stop.is_set()))

    def execute(task):
        started = time.monotonic()
        # Serialize the stop check and actual process creation, so no process
        # starts after a failure has been observed by this controller.
        with lock:
            if stop.is_set():
                task["status"] = "skipped"
                record()
                return
            task.update(status="running", started_utc=utc())
            try:
                Path(task["folder"]).mkdir(parents=True, exist_ok=False)
                log = Path(task["log"]).open("xb")
                env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1",
                           OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
                with log:
                    process = subprocess.Popen(task["command"], cwd=source, env=env,
                                               stdout=log, stderr=subprocess.STDOUT)
                task["pid"] = process.pid
            except Exception as error:
                stop.set()
                task.update(status="failed", error=repr(error), ended_utc=utc(),
                            elapsed_s=time.monotonic() - started)
                record()
                return
            record()
        code = process.wait()
        with lock:
            if code != 0:
                stop.set()
            task.update(exit_code=code, status="completed" if code == 0 else "failed",
                        ended_utc=utc(), elapsed_s=time.monotonic() - started)
            record()

    record()
    with ThreadPoolExecutor(max_workers=70) as pool:
        futures = [pool.submit(execute, task) for task in tasks]
        for future in as_completed(futures):
            future.result()


def verify_and_aggregate(tasks, stations, work, module, expectation):
    import numpy as np

    results = {}
    reference_versions = None
    for task in tasks:
        station = next(s for s in stations if s["station_id"] == task["station_id"])
        try:
            issues = module.check_position(Path(task["folder"]), task["task_id"],
                                           (station["x"], station["y"]),
                                           replace(expectation, yaw_deg=task["yaws"]))
            if task["status"] != "completed":
                issues.append(f"task status: {task['status']}")
            receipt_path = Path(task["folder"]) / f"{task['task_id']}_receipt.json"
            if receipt_path.exists():
                versions = json.loads(receipt_path.read_text()).get("versions")
                if reference_versions is None:
                    reference_versions = versions
                elif versions != reference_versions:
                    issues.append("runtime versions differ between chunks")
            if not issues:
                h = np.load(Path(task["folder"]) / f"{task['task_id']}_H.npy", allow_pickle=False)
                if h.dtype != np.dtype("complex128"):
                    issues.append(f"H dtype is {h.dtype}, expected complex128")
        except Exception as error:
            issues = [f"validation exception: {error!r}"]
        results[task["task_id"]] = issues
        atomic_json(work / "VALIDATION.json", dict(ok=False, tasks=results))
    if any(results.values()):
        raise ValueError("one or more original chunk validations failed; see VALIDATION.json")
    poses, samples = pose_tables(tasks, stations, work)
    full = np.lib.format.open_memmap(work / "H_full.npy", mode="w+", dtype=np.complex128,
                                    shape=(1260, 257, 2, 2))
    offset = 0
    for task in tasks:
        h = np.load(Path(task["folder"]) / f"{task['task_id']}_H.npy", allow_pickle=False)
        full[offset:offset + 18] = h
        if not np.array_equal(full[offset:offset + 18], h):
            raise ValueError("aggregate differs from chunk H")
        offset += 18
    full.flush()
    del full
    atomic_json(work / "rf_poses.json", poses)
    atomic_json(work / "SAMPLES.json", samples)
    validation = dict(ok=True, tasks=results, unique_rf_poses=1260, observations=1295,
                      duplicate_poses=0, duplicate_observations=0, h_shape=[1260, 257, 2, 2],
                      h_dtype="complex128", endpoint_aliases=35,
                      original_runcheck_thresholds_unchanged=True,
                      aggregate_exactly_equals_chunks=True)
    atomic_json(work / "VALIDATION.json", validation)
    return validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, default=Path("/work"))
    args = parser.parse_args()
    work = args.work.resolve()
    source = work / "source"
    # Persistent exclusive claim prevents accidental evidence replacement.
    (work / "CONTROLLER_CLAIM").mkdir(exist_ok=False)
    started, clock_start = utc(), time.monotonic()
    manifest = dict(started_utc=started, controller_sha256=sha256(__file__),
                    contract_sha256=sha256(work / "RUN_CONTRACT.json"),
                    command=sys.argv, source=str(source), failure_policy="no retry; running children finish")
    success, failure = False, None
    try:
        forbidden = ("traces", "TASKS.json", "PROGRESS.json", "H_full.npy",
                     "rf_poses.json", "SAMPLES.json", "VALIDATION.json", "RUN_SUCCESS.json",
                     "FAILURE.json", "RESULT_SHA256.json", "RUN_MANIFEST.json")
        if any((work / name).exists() for name in forbidden):
            raise FileExistsError("output evidence already exists; use a fresh run directory")
        atomic_json(work / "RUN_MANIFEST.json", manifest)
        contract = json.loads((work / "RUN_CONTRACT.json").read_text())
        stations = validate_contract(contract)
        manifest["source_hashes_start"] = check_source(source, contract)
        module, expectation = load_verifier(source, contract, stations)
        atomic_json(work / "RUN_MANIFEST.json", manifest)
        tasks = make_tasks(stations, work, source)
        if any(Path(task["log"]).exists() for task in tasks):
            raise FileExistsError("a task log already exists; use a fresh run directory")
        # Pilot logs may coexist; exclusive per-task creation still protects
        # every full-sweep log from replacement.
        (work / "logs").mkdir(exist_ok=True)
        (work / "traces").mkdir()
        run_tasks(tasks, work, source)
        verify_and_aggregate(tasks, stations, work, module, expectation)
        manifest["source_hashes_end"] = check_source(source, contract)
        if sha256(work / "RUN_CONTRACT.json") != manifest["contract_sha256"]:
            raise ValueError("RUN_CONTRACT changed during execution")
        success = True
    except Exception:
        failure = traceback.format_exc()
    manifest.update(ended_utc=utc(), elapsed_s=time.monotonic() - clock_start,
                    execution_and_validation_success=success)
    # The fresh-directory check must never overwrite an earlier run's evidence.
    if "output evidence already exists" in (failure or ""):
        print(failure, file=sys.stderr)
        return 1
    atomic_json(work / "RUN_MANIFEST.json", manifest)
    if not success:
        atomic_json(work / "FAILURE.json", dict(ok=False, error=failure, **manifest))
    hashes = {p.relative_to(work).as_posix(): sha256(p)
              for p in sorted(work.rglob("*"))
              if p.is_file() and not p.is_relative_to(source)
              and p.name not in ("RESULT_SHA256.json", "RUN_SUCCESS.json")}
    atomic_json(work / "RESULT_SHA256.json", hashes)
    if success:
        atomic_json(work / "RUN_SUCCESS.json", dict(ok=True, **manifest,
                    result_manifest_sha256=sha256(work / "RESULT_SHA256.json"),
                    claim="execution plus original runcheck validation; no scientific adoption claim"))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
