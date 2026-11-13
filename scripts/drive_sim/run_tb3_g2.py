
"""Recompute the frozen BLOCK_C regression sample with the G1 trace adapter."""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write

INPUT = Path("/input")
SOURCE = Path("/ref")
BLOCK = Path("/block")
CASE = BLOCK / "R2_aA_m0"
OUT = Path("/run-g2/output")


def verify(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Input checksum mismatch: {path}")


def prepare(config):
    ref = read(INPUT / "REFERENCE.json")
    for name, digest in ref["method_b_sha256"].items():
        verify(SOURCE / name, digest)
    for bank in read(INPUT / "FFD_RESTORE_MANIFEST.json")["banks"]:
        verify(SOURCE / bank["filename"], bank["sha256"])
    if read(SOURCE / ref["solver_path"])["solver"] != ref["block_c_solver"]:
        raise ValueError("Solver settings differ from BLOCK_C")
    for name, digest in config["block_sha256"].items():
        verify(BLOCK / name, digest)
    task_path = SOURCE / config["original_tasks"]
    verify(task_path, config["original_tasks_sha256"])

    manifest = read(CASE / "MANIFEST.json")
    bindings = [dict(item, ply=f"{item['object']}.ply") for item in manifest["material_bindings"]]
    for binding in bindings:
        verify(CASE / "scene" / binding["ply"], binding["ply_sha256"])
    write(OUT / "scene.json", dict(dimensions_m=config["corridor_m"],
                                 anchors_xyz_m={"A": manifest["anchor_xyz"]},
                                 rx_z_m=manifest["robot_z"], material_bindings=bindings))

    original = read(CASE / "SAMPLES.json")
    if [p["pose_id"] for p in original] != list(range(config["reference_shape"][0])):
        raise ValueError("BLOCK_C pose IDs do not match array row indices")
    ids = config["block_pose_ids"]
    if len(ids) != 50 or ids != sorted(set(ids)):
        raise ValueError("Expected 50 unique, ordered BLOCK_C pose IDs")
    new_ids = {old: i for i, old in enumerate(ids)}
    poses = [dict(original[old], pose_id=i, block_pose_id=old) for i, old in enumerate(ids)]
    tasks = []
    for task in read(task_path):
        mapped = [new_ids[i] for i in task["pose_ids"] if i in new_ids]
        if mapped:
            tasks.append(dict(task, task_id=len(tasks), block_task_id=task["task_id"],
                              pose_ids=mapped,
                              antenna_yaw_deg=sorted({poses[i]["yaw_body_deg"] for i in mapped})))
    if sorted(i for t in tasks for i in t["pose_ids"]) != list(range(50)):
        raise ValueError("Original trace tasks do not cover all selected poses exactly once")
    if len({t["tag"] for t in tasks}) != len(tasks):
        raise ValueError("Duplicate BLOCK_C trace tags")
    write(OUT / "rf_poses.json", poses)
    write(OUT / "rf_tasks.json", tasks)
    return tasks


def run_shard(shard):
    trace, _, versions = load_runtime(SOURCE)
    print(f"Runtime {versions}", flush=True)
    scene = read(OUT / "scene.json")
    trace.CorridorSetup, trace.C.build_scene = geometry_adapter(trace, scene, CASE / "scene")
    sys.argv = [trace.__file__, "--tasks", str(OUT / "rf_tasks.json"),
                "--out", str(OUT / "trace"), "--nodes", "17", "--threads", "1",
                "--anchor-x", "4", "--shard", shard]
    trace.main()


def trace_parallel(workers):
    jobs = []
    try:
        for i in range(workers):
            shard = f"{i}/{workers}"
            with (OUT / f"shard_{i}.log").open("x") as log:
                jobs.append(subprocess.Popen([sys.executable, "-u", __file__, shard],
                                             stdout=log, stderr=subprocess.STDOUT))
        codes = [job.wait() for job in jobs]
    finally:
        for job in jobs:
            if job.poll() is None:
                job.terminate()
                job.wait()
    write(OUT / "SHARD_EXIT.json", codes)
    if any(codes):
        raise RuntimeError(f"Trace shard exit codes: {codes}")


def compare(config, generated, np):
    ref = np.load(BLOCK / "FULL_RF/H_R2_aA_m0.npy", mmap_mode="r", allow_pickle=False)
    if tuple(config["reference_shape"]) != ref.shape or ref.dtype != np.complex128:
        raise ValueError(f"Unexpected BLOCK_C H shape or dtype: {ref.shape} {ref.dtype}")
    expected = ref[config["block_pose_ids"]]
    actual = np.load(generated, allow_pickle=False)
    if actual.shape != expected.shape or actual.dtype != expected.dtype:
        raise ValueError(f"Unexpected generated H shape or dtype: {actual.shape} {actual.dtype}")
    if not (np.isfinite(expected).all() and np.isfinite(actual).all()):
        raise ValueError("Non-finite complex channel values")
    np.save(OUT / "H_reference_50.npy", expected)
    absolute = np.abs(actual - expected)
    denom = np.abs(expected)
    nonzero = denom != 0
    relative = np.zeros_like(denom)
    np.divide(absolute, denom, out=relative, where=nonzero)
    zero_mismatch = ~nonzero & (absolute != 0)
    relative[zero_mismatch] = np.inf
    index = tuple(int(i) for i in np.unravel_index(relative.argmax(), relative.shape))
    max_rel = float(relative[index])
    return dict(status="PASS" if max_rel < config["strict_relative_threshold"] else "FAIL",
                max_relative_error=max_rel if np.isfinite(max_rel) else None,
                max_absolute_error=float(absolute.max()), zero_reference_entries=int((~nonzero).sum()),
                zero_reference_mismatches=int(zero_mismatch.sum()), equal_entries=int((actual == expected).sum()),
                bitwise_equal=actual.tobytes() == expected.tobytes(), entries=int(expected.size),
                worst_index=list(index), worst_block_pose_id=config["block_pose_ids"][index[0]],
                minimum_nonzero_reference_amplitude=float(denom[nonzero].min()) if np.any(nonzero) else None,
                generated_sha256=sha(generated), reference_subset_sha256=sha(OUT / "H_reference_50.npy"))


def main():
    start = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()
    OUT.mkdir(exist_ok=False)
    config = read(INPUT / "G2_CONTRACT.json")
    tasks = prepare(config)
    print(f"Tracing {len(tasks)} distinct original positions for 50 poses with {config['workers']} workers",
          flush=True)
    t_trace = time.monotonic()
    trace_parallel(config["workers"])
    trace_s = time.monotonic() - t_trace
    import numpy as np

    receipts = []
    for task in tasks:
        base = OUT / "trace" / f"{task['tag']}_trace"
        receipt = read(base.with_name(base.name + "_receipt.json"))
        with np.load(base.with_name(base.name + ".npz"), allow_pickle=False) as data:
            if (receipt["status"] != "OK" or str(data["status"]) != "OK"
                    or not np.isfinite(data["jones"]).all()
                    or float(data["x"]) != task["x"] or float(data["y"]) != task["y"]):
                raise RuntimeError(f"Invalid trace for {task['tag']}: {receipt}")
        receipts.append(receipt)
    t_apply = time.monotonic()
    generated = OUT / "H_regenerated_50.npy"
    subprocess.run([sys.executable, str(SOURCE / "scripts/drive_sim/rf_b_apply.py"),
                    "--poses", str(OUT / "rf_poses.json"), "--traces", str(OUT / "trace"),
                    "--mount", "0", "--out", str(generated)], check=True)
    apply_s = time.monotonic() - t_apply
    result = compare(config, generated, np)
    result.update(started_utc=start, finished_utc=datetime.now(timezone.utc).isoformat(),
                  wall_s=time.monotonic() - t0, trace_s=trace_s, apply_s=apply_s, poses=50,
                  trace_positions=len(tasks), workers=config["workers"],
                  trace_cpu_wall_sum_s=sum(r["elapsed_s"] for r in receipts),
                  strict_relative_threshold=config["strict_relative_threshold"],
                  contract_sha256=sha(INPUT / "G2_CONTRACT.json"),
                  trace_and_receipt_bytes=sum(p.stat().st_size for p in (OUT / "trace").iterdir() if p.is_file()))
    write(OUT / "G2.json", result)
    print(result, flush=True)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    if len(sys.argv) == 2:
        run_shard(sys.argv[1])
    else:
        sys.exit(main())
