"""Trace the frozen BLOCK_C centerline sweep with guarded F1 and mount 0."""
from __future__ import annotations

import argparse
from collections import Counter
import os
from pathlib import Path
import resource
import sys
import time

import numpy as np

from run_tb3_g1_pilot import load_runtime, read, sha, write
from run_tb3_production import (
    F1_SHA, FINITE_FACE_G6_SHA, FINITE_FACE_RUNTIME_SHA,
    FINITE_FACE_SOURCE_SHA, utc_now, verify,
)
from run_tb3_sweep_shard import generate


def frozen_inputs(root, source):
    contract = read(root / "RUN_CONTRACT.json")
    hashes = contract["input_sha256"]
    required = {"SCENE_ENTRY.json", "rf_poses.json", "rf_tasks.json", "PRODUCTION_F1.json"}
    if not required.issubset(hashes):
        raise ValueError("The contract does not bind every required input")
    for name, digest in hashes.items():
        path = (root / name).resolve()
        if root.resolve() not in path.parents:
            raise ValueError(f"Input escapes the frozen root: {name}")
        verify(path, digest)
    verify(root / "PRODUCTION_F1.json", F1_SHA)
    production = read(root / "PRODUCTION_F1.json")
    if (production["status"] != "ADOPTED"
            or (production["base_nodes"], production["channel_bins"], production["mount_deg"])
            != (17, 257, 0)
            or production["solver"]["refraction"] is not False
            or production["solver"]["max_depth"] != 3
            or production["solver"]["samples_per_src"] != 100000):
        raise ValueError("The adopted F1 production envelope differs")
    if set(contract["ffd_sha256"]) != {"LP_plus45_bank.npz", "LP_minus45_bank.npz"}:
        raise ValueError("Both frozen LP FFD banks must be bound")
    for name, digest in contract["ffd_sha256"].items():
        verify(source / name, digest)
    for name, digest in contract.get("method_b_sha256", {}).items():
        verify(source / name, digest)

    scene = read(root / "SCENE_ENTRY.json")
    if (scene["dimensions_m"] != [20.0, 2.4, 2.7]
            or scene["anchors_xyz_m"] != {"B": [10.0, 0.0, 2.65]}
            or scene["rx_z_m"] != 0.45):
        raise ValueError("The frozen BLOCK_C geometry or anchor differs")
    expected_materials = {
        "floor": ("concrete", 0.20), "ceiling": ("concrete", 0.20),
        "end_x_min": ("concrete", 0.20), "end_x_max": ("concrete", 0.20),
        "wall_y_neg": ("plasterboard", 0.0125), "wall_y_pos": ("plasterboard", 0.0125),
    }
    bindings = scene["material_bindings"]
    if (len(bindings) != 6
            or {item["object"]: (item["itu_type"], item["thickness_m"])
                for item in bindings} != expected_materials):
        raise ValueError("The six original BLOCK_C material bindings differ")
    for item in bindings:
        name = "scene/" + item["ply"]
        if hashes.get(name) != item["ply_sha256"]:
            raise ValueError(f"Mesh is not bound by the run contract: {name}")
        verify(root / name, item["ply_sha256"])

    poses = read(root / "rf_poses.json")
    tasks = read(root / "rf_tasks.json")
    if ([p["pose_id"] for p in poses] != list(range(1440))
            or [t["task_id"] for t in tasks] != list(range(40))
            or Counter(i for t in tasks for i in t["pose_ids"]) != Counter(range(1440))):
        raise ValueError("Expected 40 stations partitioning 1440 physical RF poses")
    for index, task in enumerate(tasks):
        expected_x = round(1.20 + index * 0.45, 2)
        expected_ids = list(range(index * 36, (index + 1) * 36))
        if (task["pose_ids"] != expected_ids or task["y"] != 0
                or abs(task["x"] - expected_x) > 1e-12):
            raise ValueError(f"Station {index} is outside the exact centerline lattice")
        for pose_id, yaw in zip(expected_ids, range(-180, 180, 10), strict=True):
            pose = poses[pose_id]
            if ((pose["x"], pose["y"]) != (task["x"], task["y"])
                    or pose["yaw_body_deg"] != yaw):
                raise ValueError(f"Pose {pose_id} differs from its frozen station or yaw")
    return contract, scene, poses, tasks, production


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "source", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--field-batch-xy", type=int, default=2)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--task-id", type=int, action="append")
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.shard_count <= 40 or args.field_batch_xy < 1:
        parser.error("Invalid shard selection or field batch size")
    started_utc, started = utc_now(), time.monotonic()
    contract, scene, poses, tasks, production = frozen_inputs(args.inputs, args.source)
    if args.task_id is None:
        tasks = tasks[args.shard_index::args.shard_count]
    else:
        if (args.shard_count != 1 or len(set(args.task_id)) != len(args.task_id)
                or not all(0 <= i < 40 for i in args.task_id)):
            parser.error("Invalid explicit pilot task selection")
        tasks = [tasks[i] for i in sorted(args.task_id)]
    core, _, versions = load_runtime(args.source)
    for name, digest in FINITE_FACE_SOURCE_SHA.items():
        verify(Path(__file__).with_name(name), digest)
    rt_solvers = Path(core.rt.__file__).parent / "path_solvers"
    for name, digest in FINITE_FACE_RUNTIME_SHA.items():
        verify(rt_solvers / name, digest)
    args.out.mkdir(parents=True, mode=0o700, exist_ok=False)
    ids, receipts, timings = generate(
        core, scene, "B", args.inputs / "scene", poses, tasks, production,
        args.out, args.field_batch_xy, mounts=(0,),
    )
    expected_ids = sorted(i for task in tasks for i in task["pose_ids"])
    if not np.array_equal(ids, expected_ids):
        raise ValueError("Generated pose coverage differs from selected tasks")
    mount_root = args.out / "mount0"
    expected_shape = (len(ids), 257, 2, 2)
    for filename in ("H_full.npy", "H_LoS.npy"):
        data = np.load(mount_root / filename, allow_pickle=False)
        if (data.shape != expected_shape or data.dtype != np.complex128
                or not np.isfinite(data).all()):
            raise ValueError(f"Invalid generated channel: {filename}")
    from tb3_paths_near import check_g8
    serialized_los = check_g8(mount_root / "PATHS_NEAR.npz", data, ids)
    if serialized_los["status"] != "PASS":
        raise ValueError("Serialized PATHS_NEAR does not reconstruct H_LoS")
    write(args.out / "SERIALIZATION_G8.json", serialized_los)
    artifacts = [p for p in sorted(args.out.rglob("*")) if p.is_file()]
    sources = ("run_blockc_centerline_sweep.py", "run_tb3_sweep_shard.py",
               "run_tb3_production.py", "run_tb3_g1_pilot.py", "run_tb3_g8_pilot.py",
               "tb3_native_los.py", "tb3_paths_near.py", *FINITE_FACE_SOURCE_SHA)
    write(args.out / "MANIFEST.json", dict(
        status="PASS", role="IMPLEMENTER", question_id=contract.get("question_id"),
        scope="PILOT" if args.task_id else "CENTERLINE_SWEEP_SHARD",
        code_commit=args.code_commit, image=production["image"], mounts_deg=[0],
        scene="BLOCK_C", anchor_xyz_m=[10.0, 0.0, 2.65], rx_z_m=0.45,
        trace_positions=len(tasks), poses=len(ids), shape=list(expected_shape),
        solver_calls=sum(r["solver_calls"] for r in receipts), extra_export_solver_calls=0,
        shared_trace=True, engine=production,
        finite_face_guard=dict(stage="PRE_FIELD", g6_result_sha256=FINITE_FACE_G6_SHA,
                               runtime_sha256=FINITE_FACE_RUNTIME_SHA),
        run_contract_sha256=sha(args.inputs / "RUN_CONTRACT.json"),
        input_sha256=contract["input_sha256"], ffd_sha256=contract["ffd_sha256"],
        method_b_sha256=contract.get("method_b_sha256", {}),
        source_sha256={name: sha(Path(__file__).with_name(name)) for name in sources},
        governance=contract.get("governance", {}), runtime_versions=versions,
        shard_index=args.shard_index, shard_count=args.shard_count,
        selected_task_ids=[t["task_id"] for t in tasks], timings=timings,
        started_utc=started_utc, finished_utc=utc_now(), wall_s=time.monotonic()-started,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        command=[sys.executable, *sys.argv],
        thread_environment={k: os.environ.get(k) for k in
                            ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")},
        serialization_g8=serialized_los,
        output_sha256={p.relative_to(args.out).as_posix(): sha(p) for p in artifacts},
        output_bytes={p.relative_to(args.out).as_posix(): p.stat().st_size for p in artifacts},
    ))


if __name__ == "__main__":
    main()
