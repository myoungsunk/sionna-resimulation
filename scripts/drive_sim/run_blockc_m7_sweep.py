"""Run the original M7 BLOCK_C Method B trace and export same-trace channels."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

import numpy as np

from run_tb3_g1_pilot import load_runtime, read, sha, write
from run_tb3_g8_pilot import capture_trace


def verify(path, digest):
    if sha(path) != digest:
        raise ValueError(f"Frozen input or source checksum differs: {path}")


def checked_inputs(root, source):
    contract = read(root / "RUN_CONTRACT.json")
    for name, digest in contract["current_code_sha256"].items():
        if Path(name).name != name:
            raise ValueError("Code checksum keys must be script basenames")
        verify(Path(__file__).parent / name, digest)
    for name, digest in contract["input_sha256"].items():
        path = (root / name).resolve()
        if root.resolve() not in path.parents:
            raise ValueError(f"Input escapes root: {name}")
        verify(path, digest)
    if "M7_RT_CONFIG.json" not in contract["input_sha256"]:
        raise ValueError("The original M7 config must be bound in RUN_CONTRACT")
    for name, digest in contract["method_b_sha256"].items():
        verify(source / name, digest)
    for name, digest in contract["ffd_sha256"].items():
        verify(source / name, digest)
    return contract, read(root / "SCENE_ENTRY.json"), read(root / "M7_RT_CONFIG.json")


def generate(core, entry, poses, tasks, config, out, source):
    from qclean_uwb.drivesim.rf_store import h_for_antenna_yaws, load_banks
    from tb3_paths_near import check_g8, h_and_near_for_poses, write_paths_near

    setup = core.CorridorSetup(anchor_x_m=10.0)
    if (not all(check["passed"] for check in setup.validate())
            or entry["dimensions_m"] != [setup.length_m, setup.width_m, setup.height_m]
            or set(entry["anchors_xyz_m"]) != {"B"}
            or not np.allclose(entry["anchors_xyz_m"]["B"], setup.anchor_position, rtol=0, atol=1e-12)
            or entry["rx_z_m"] != float(setup.robot_position(0, 0)[2])):
        raise ValueError("Requested scene differs from the original M7 BLOCK_C setup")
    original_solver = read(core.C.SOLVER_SOURCE)["solver"]
    solver_config = config["solver"]
    if (solver_config != original_solver or solver_config.get("refraction") is not True
            or solver_config.get("samples_per_src") != 100000
            or solver_config.get("max_depth") != 3 or solver_config.get("seed") != 20260924):
        raise ValueError("Every solver setting must equal the frozen original M7 config")
    scene, bindings = core.C.build_scene(setup, out / "scene")
    fields = ("object", "itu_type", "thickness_m", "ply_sha256")
    expected = {item["object"]: {key: item[key] for key in fields} for item in entry["material_bindings"]}
    if {item["object"]: item for item in bindings} != expected:
        raise ValueError("Original generated BLOCK_C meshes or materials differ")
    rt, mi = core.rt, core.mi
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0]*3))
    scene.add(rt.Receiver("rx", position=setup.robot_position(*setup.example_xy_m[0]).tolist(),
                          orientation=[0.0]*3))
    for name in ("tx_array", "rx_array"):
        setattr(scene, name, rt.AntennaArray(core.Ports([core.IsoPort(0), core.IsoPort(1)]),
                                            mi.Point3f(0, 0, 0)))
    solver = rt.PathSolver()
    banks = load_banks(source)
    native_banks = core.C.load_banks()
    frequencies = np.asarray(banks[0].freqs_hz, dtype=np.float64)
    if len(frequencies) != 257 or not np.array_equal(frequencies, native_banks[0]["freqs_hz"]):
        raise ValueError("Original bank frequency grids differ")
    bins = core.node_bins(257, "17")
    by_id = {p["pose_id"]: p for p in poses}
    ids = np.array(sorted(i for task in tasks for i in task["pose_ids"]), dtype=np.int64)
    if not len(ids) or len(set(ids.tolist())) != len(ids) or not set(ids.tolist()) <= by_id.keys():
        raise ValueError("Tasks must cover unique existing RF pose IDs")
    row_by_id = {int(pose): row for row, pose in enumerate(ids)}
    shape = (len(ids), 257, 2, 2)
    full, los, coefficients = (np.empty(shape, np.complex128) for _ in range(3))
    delays = np.empty(len(ids), np.float64)
    angles = np.empty((len(ids), 4), np.float64)
    receipts, packs = [], []
    none = int(rt.constants.InteractionType.NONE)
    raw_dir = out / "trace"
    raw_dir.mkdir()
    for task in tasks:
        before = time.monotonic()
        selected = [by_id[i] for i in task["pose_ids"]]
        if any(p["x"] != task["x"] or p["y"] != task["y"] for p in selected):
            raise ValueError("RF pose coordinates do not match their trace task")
        audit = {}
        original = core.trace_position

        def observe_position(*args, **kwargs):
            result = original(*args, **kwargs)
            audit["counts"], audit["details"] = result[3], result[4]
            return result

        core.trace_position = observe_position
        try:
            trace, nodes = capture_trace(core, scene, solver, solver_config, frequencies, bins, task, setup)
        finally:
            core.trace_position = original
        details = audit["details"]
        names, unmatched = core.path_signature(
            trace["tau"], setup.anchor_position, setup.robot_position(task["x"], task["y"]),
            setup.length_m, setup.y_half, setup.height_m)
        raw = raw_dir / f"task_{task['task_id']:04d}_trace.npz"
        np.savez_compressed(raw, jones=trace["jones"], tau=trace["tau"], ang=trace["ang"],
                            node_bins=nodes, node_freq_hz=trace["node_freq_hz"], x=task["x"], y=task["y"],
                            signature=np.array(names), unmatched=unmatched, status=trace["status"],
                            flagged_bins=np.array([], int), path_counts=np.array(audit["counts"]),
                            present=trace["present"], max_dropped_rel_amp=details["max_dropped_rel_amp"],
                            interactions=trace["interactions"], objects=trace["objects"])
        channels, near = h_and_near_for_poses(trace, banks, selected, mount_deg=0,
                                              none_event=none, direct_coefficients=None)
        original_h = h_for_antenna_yaws(trace, banks, [p["yaw_body_deg"] for p in selected])
        if not np.array_equal(channels, original_h):
            raise ValueError("Same-trace export changed original M7 H synthesis")
        direct = np.flatnonzero((trace["interactions"] == none).all(axis=1))
        if len(direct) != 1 or not trace["present"][:, direct].all():
            raise ValueError("Expected one original LoS path at every adaptive node")
        for p in selected:
            row = row_by_id[p["pose_id"]]
            near_index = np.flatnonzero((near["pose_id"] == p["pose_id"]) & near["is_los"])
            if len(near_index) != 1:
                raise ValueError("Expected one serialized same-trace LoS row per pose")
            k = near_index[0]
            coefficients[row] = near["coefficients"][k]
            delays[row] = near["tau_s"][k]
            angles[row] = trace["ang"][:, direct[0]]
            los[row] = coefficients[row] * np.exp(-2j*np.pi*frequencies*delays[row])[:, None, None]
        full[[row_by_id[p["pose_id"]] for p in selected]] = channels
        packs.append(near)
        receipts.append(dict(task_id=task["task_id"], tag=task["tag"], pose_ids=task["pose_ids"],
                             node_bins=nodes.tolist(), solver_calls=len(nodes), mounts_deg=[0],
                             n_full_paths=len(trace["tau"]), n_near_paths=len(near["pose_id"])//len(selected),
                             raw_trace=raw.relative_to(out).as_posix(), raw_trace_sha256=sha(raw),
                             original_h_array_equal=True, dropped_audit=details["dropped_paths"],
                             max_dropped_rel_amp=details["max_dropped_rel_amp"],
                             wall_s=time.monotonic()-before))
        print(f"task {task['task_id']}: {len(nodes)} original solver calls", flush=True)
    mount = out / "mount0"
    mount.mkdir()
    for name, data in (("POSE_IDS.npy", ids), ("H_full.npy", full), ("H_LoS.npy", los)):
        if not np.isfinite(data).all():
            raise ValueError(f"Nonfinite output: {name}")
        np.save(mount / name, data)
    axis_shape = shape[:2]
    np.savez_compressed(mount / "PATHS_LoS.npz", pose_id=ids, a=coefficients, freqs_hz=frequencies,
                        tau=np.broadcast_to(delays[:, None], axis_shape),
                        counts=np.ones(axis_shape, np.int64), interactions=np.zeros(axis_shape, np.int64),
                        **{name: np.broadcast_to(angles[:, i, None], axis_shape)
                           for i, name in enumerate(("theta_t", "phi_t", "theta_r", "phi_r"))})
    codes = {name: int(getattr(rt.constants.InteractionType, name))
             for name in ("NONE", "SPECULAR", "DIFFUSE", "REFRACTION", "DIFFRACTION")
             if hasattr(rt.constants.InteractionType, name)}
    write_paths_near(mount, packs, frequencies, codes, native_direct=False,
                     object_ids={int(obj.object_id): name for name, obj in scene.objects.items()})
    g8 = check_g8(mount / "PATHS_NEAR.npz", los, ids)
    write(out / "SERIALIZATION_G8.json", g8)
    write(out / "TRACE_RECEIPTS.json", receipts)
    if g8["status"] != "PASS":
        raise ValueError("Same-trace LoS serialization failed")
    return ids, full, receipts, g8, bindings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("inputs", "source", "out"):
        parser.add_argument("--"+name, type=Path, required=True)
    for name in ("poses", "tasks", "baseline-H"):
        parser.add_argument("--"+name, type=Path)
    parser.add_argument("--baseline-pose-ids", type=int, nargs="+")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--task-id", type=int, action="append")
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()
    if not 0 <= args.shard_index < args.shard_count:
        parser.error("Invalid shard selection")
    started = time.monotonic()
    contract, entry, config = checked_inputs(args.inputs, args.source)
    if (args.code_commit != contract["code_commit"]
            or args.source_commit != contract["source_commit"]):
        raise ValueError("Declared commits differ from the frozen run contract")
    poses_path, tasks_path = args.poses or args.inputs/"rf_poses.json", args.tasks or args.inputs/"rf_tasks.json"
    poses, tasks = read(poses_path), read(tasks_path)
    if args.task_id is not None:
        if args.shard_count != 1 or len(set(args.task_id)) != len(args.task_id):
            parser.error("Explicit pilot tasks require shard_count=1 and unique IDs")
        tasks = [t for t in tasks if t["task_id"] in args.task_id]
        if len(tasks) != len(args.task_id):
            parser.error("Unknown pilot task ID")
    else:
        tasks = tasks[args.shard_index::args.shard_count]
    core, _, versions = load_runtime(args.source)
    args.out.mkdir(parents=True, exist_ok=False)
    ids, full, receipts, g8, bindings = generate(core, entry, poses, tasks, config, args.out, args.source)
    baseline = None
    if args.baseline_H is not None:
        if args.baseline_pose_ids is None or len(args.baseline_pose_ids) != len(ids):
            parser.error("Supply one baseline row ID for each generated pose, in sorted pose-ID order")
        previous = np.load(args.baseline_H, mmap_mode="r", allow_pickle=False)[args.baseline_pose_ids]
        if previous.shape != full.shape or not np.isfinite(previous).all():
            raise ValueError("Baseline H shape or finite-value check failed")
        baseline = dict(H_sha256=sha(args.baseline_H), pose_ids=args.baseline_pose_ids,
                        max_abs_delta_h=float(np.max(np.abs(previous-full))),
                        array_equal=bool(np.array_equal(previous, full)))
        write(args.out/"BASELINE_COMPARISON.json", baseline)
    files = [p for p in sorted(args.out.rglob("*")) if p.is_file()]
    passed = baseline is None or baseline["array_equal"]
    write(args.out/"MANIFEST.json", dict(
        status="PASS" if passed else "FAIL", scope="M7_CENTERLINE_SWEEP_SHARD",
        code_commit=args.code_commit, source_commit=args.source_commit, runtime_versions=versions,
        run_contract_sha256=sha(args.inputs/"RUN_CONTRACT.json"), input_sha256=contract["input_sha256"],
        method_b_sha256=contract["method_b_sha256"], ffd_sha256=contract["ffd_sha256"],
        config_sha256=sha(args.inputs/"M7_RT_CONFIG.json"), engine=config, material_bindings=bindings,
        pose_table_sha256=sha(poses_path), task_table_sha256=sha(tasks_path),
        shard_index=args.shard_index, shard_count=args.shard_count,
        selected_task_ids=[t["task_id"] for t in tasks], poses=len(ids), trace_positions=len(tasks),
        mounts_deg=[0], shared_trace=True, original_h_array_equal=True,
        solver_calls=sum(r["solver_calls"] for r in receipts), extra_export_solver_calls=0,
        finite_face_guard=False, native_los_override=False, post_filter=False,
        serialization_g8=g8, baseline_comparison=baseline, wall_s=time.monotonic()-started,
        command=[sys.executable, *sys.argv], runner_sha256=sha(Path(__file__)),
        output_sha256={p.relative_to(args.out).as_posix(): sha(p) for p in files},
        output_bytes={p.relative_to(args.out).as_posix(): p.stat().st_size for p in files}))
    if not passed:
        raise RuntimeError("Original M7 baseline parity failed; FAIL evidence preserved")


if __name__ == "__main__":
    main()
