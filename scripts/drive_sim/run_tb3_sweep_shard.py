"""Trace one set of guarded F1 XY tasks for both full-yaw sweep mounts."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from pathlib import Path
import sys
import time

import numpy as np

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write
from run_tb3_production import (
    CASES, F1_SHA, FFD_SHA, FINITE_FACE_G6_SHA, FINITE_FACE_RUNTIME_SHA,
    FINITE_FACE_SOURCE_SHA, G0_SHA, G7_SHA, REFERENCE_SHA, case_inputs,
    frozen_settings, utc_now, verify,
)

MOUNTS = (0, 45)
ANGLES = ("theta_t", "phi_t", "theta_r", "phi_r")


def write_mount(out, ids, freq, delays, angles, coefficients, h_full, packs, codes, objects):
    from tb3_paths_near import write_paths_near

    out.mkdir()
    if not np.isfinite(h_full).all() or not np.isfinite(coefficients).all():
        raise ValueError(f"Nonfinite channel at {out}")
    phase = np.exp(-2j * np.pi * freq[None, :] * delays[:, None])
    np.save(out / "POSE_IDS.npy", ids)
    np.save(out / "H_full.npy", h_full)
    np.save(out / "H_LoS.npy", coefficients * phase[..., None, None])
    shape = (len(ids), len(freq))
    np.savez_compressed(
        out / "PATHS_LoS.npz", pose_id=ids, a=coefficients, freqs_hz=freq,
        tau=np.broadcast_to(delays[:, None], shape), counts=np.ones(shape, dtype=np.int64),
        interactions=np.zeros(shape, dtype=np.int64),
        **{name: np.broadcast_to(angles[:, i, None], shape) for i, name in enumerate(ANGLES)},
    )
    write_paths_near(out, packs, freq, codes, object_ids=objects, native_direct=True)


def trace_digest(trace):
    """Hash the ordered path geometry, Jones arrays and node coverage."""
    digest = hashlib.sha256()
    for key in ("jones", "tau", "ang", "present", "node_freq_hz", "interactions", "objects"):
        array = np.ascontiguousarray(trace[key])
        digest.update(f"{key}:{array.dtype.str}:{array.shape}\n".encode("ascii"))
        digest.update(array.data)
    return digest.hexdigest()


def generate(core, scene_entry, anchor_id, scene_root, poses, tasks, production, out, batch_xy):
    from run_tb3_g8_pilot import capture_trace
    from tb3_finite_face_guard import FiniteFaceGuard
    from tb3_g6_face_match import load_faces
    from tb3_native_los import native_direct_fields
    from tb3_paths_near import h_and_near_for_poses

    anchor = scene_entry["anchors_xyz_m"][anchor_id]
    factory, loader = geometry_adapter(core, scene_entry | {"anchors_xyz_m": {"A": anchor}}, scene_root)
    setup = factory(anchor_x_m=anchor[0])
    if not all(check["passed"] for check in setup.validate()):
        raise ValueError("Invalid validated production corridor")
    scene, _ = loader(setup, None)
    rt, mi = core.rt, core.mi
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0]*3))
    scene.add(rt.Receiver("rx", position=setup.robot_position(*setup.example_xy_m[0]).tolist(),
                          orientation=[0.0]*3))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(core.Ports([core.IsoPort(0), core.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))
    solver = rt.PathSolver()
    guard = FiniteFaceGuard(solver, mi, scene, load_faces(scene, scene_entry, scene_root),
                            anchor, anchor, rt.constants.InteractionType)
    objects = {int(obj.object_id): name for name, obj in scene.objects.items()}
    codes = {name: int(getattr(rt.constants.InteractionType, name))
             for name in ("NONE", "SPECULAR", "DIFFUSE", "REFRACTION", "DIFFRACTION")
             if hasattr(rt.constants.InteractionType, name)}
    native_banks = core.C.load_banks()
    banks = [core.P.Bank(bank) for bank in native_banks]
    freq = banks[0].freqs_hz
    if len(freq) != production["channel_bins"] or any(
        not np.array_equal(freq, bank["freqs_hz"]) for bank in native_banks
    ):
        raise ValueError("Inconsistent frozen frequency grid")
    ports = core.C.make_ports(native_banks)
    bins = core.node_bins(len(freq), str(production["base_nodes"]))
    tx = np.asarray(scene.transmitters["tx"].position).reshape(3)
    ids = np.array(sorted(pose_id for task in tasks for pose_id in task["pose_ids"]), dtype=np.int64)
    by_id = {pose_id: row for row, pose_id in enumerate(ids)}
    shape = (len(ids), len(freq), 2, 2)
    coeff = {mount: np.empty(shape, dtype=np.complex128) for mount in MOUNTS}
    full = {mount: np.empty(shape, dtype=np.complex128) for mount in MOUNTS}
    packs = {mount: [] for mount in MOUNTS}
    delays = np.empty(len(ids), dtype=np.float64)
    angles = np.empty((len(ids), len(ANGLES)), dtype=np.float64)
    receipts = []
    timings = dict(trace_s=0.0, native_field_s=0.0, apply_s=0.0, save_s=0.0)

    for offset in range(0, len(tasks), batch_xy):
        selected = tasks[offset:offset + batch_xy]
        batch, batch_poses, receivers = [], [], []
        for task in selected:
            before = time.monotonic()
            guard.set_receiver((task["x"], task["y"], scene_entry["rx_z_m"]))
            counts = {}
            trace, nodes = capture_trace(
                core, scene, solver, production["solver"], freq, bins, task, setup,
                observe_bin=lambda node: counts.update({node: len(guard.rejected)}),
            )
            elapsed = time.monotonic() - before
            timings["trace_s"] += elapsed
            direct = np.flatnonzero((trace["interactions"] == codes["NONE"]).all(axis=1))
            if (len(direct) != 1 or nodes.tolist() != list(bins)
                    or counts.keys() != set(nodes) or not trace["present"].all()):
                raise ValueError(f"Incomplete guarded trace at {task['tag']}")
            start = len(batch_poses)
            batch_poses.extend(poses[pose_id] for pose_id in task["pose_ids"])
            receiver = np.asarray(scene.receivers["rx"].position).reshape(3).copy()
            receivers.extend([receiver] * len(task["pose_ids"]))
            rows = [by_id[pose_id] for pose_id in task["pose_ids"]]
            receipts.append(dict(
                tag=task["tag"], task_id=task["task_id"], pose_ids=task["pose_ids"],
                node_bins=nodes.tolist(), solver_calls=len(nodes), trace_s=elapsed,
                n_full_paths=len(trace["tau"]), trace_sha256=trace_digest(trace),
                mounts_deg=list(MOUNTS), pre_field_rejections=sum(counts.values()),
                pre_field_rejections_by_node=[
                    dict(bin=node, count=count) for node, count in sorted(counts.items()) if count
                ],
            ))
            batch.append((task, trace, int(direct[0]), slice(start, len(batch_poses)), rows, receipts[-1]))

        started = time.monotonic()
        # Run one native direct-field batch for both mounts; these are field
        # evaluations on known direct segments and do not call the path solver.
        mounted = [
            {"yaw_body_deg": pose["yaw_body_deg"] + mount}
            for mount in MOUNTS for pose in batch_poses
        ]
        native, native_delays = native_direct_fields(
            core, tx, receivers * len(MOUNTS), mounted, 0, native_banks, ports,
        )
        n = len(batch_poses)
        native = native.reshape((len(MOUNTS), n, *shape[1:]))
        native_delays = native_delays.reshape((len(MOUNTS), n))
        timings["native_field_s"] += time.monotonic() - started

        started = time.monotonic()
        for task, trace, direct, part, rows, receipt in batch:
            delay = trace["tau"][direct]
            if np.max(np.abs(native_delays[:, part] - delay)) > 2e-13:
                raise ValueError(f"Native delay differs from the F1 direct path at {task['tag']}")
            delays[rows] = delay
            angles[rows] = trace["ang"][:, direct]
            for mount, fields in zip(MOUNTS, native, strict=True):
                channels, near = h_and_near_for_poses(
                    trace, banks, batch_poses[part], mount_deg=mount, none_event=codes["NONE"],
                    direct_coefficients=fields[part],
                )
                full[mount][rows] = channels
                coeff[mount][rows] = fields[part]
                packs[mount].append(near)
            receipt["n_near_paths"] = len(near["pose_id"]) // len(rows)
        timings["apply_s"] += time.monotonic() - started
        print(f"{offset + len(selected)}/{len(tasks)} shared guarded XY", flush=True)

    started = time.monotonic()
    for mount in MOUNTS:
        write_mount(out / f"mount{mount}", ids, freq, delays, angles, coeff[mount],
                    full[mount], packs[mount], codes, objects)
    write(out / "TRACE_RECEIPTS.json", receipts)
    timings["save_s"] += time.monotonic() - started
    return ids, receipts, timings


def main():
    import resource

    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("sweep-inputs", "inputs", "g7", "source", "reference", "ffd-manifest",
                   "production", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--field-batch-xy", type=int, default=16)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--task-id", type=int, action="append",
                        help="Select explicit tasks for a canary instead of a production shard")
    args = parser.parse_args()
    started_utc, started = utc_now(), time.monotonic()
    scene, anchor, *_ = case_inputs(args.inputs, args.g7, args.case)
    case_root = args.sweep_inputs / "poses" / args.case
    manifest_path = args.sweep_inputs / "SWEEP_MANIFEST.json"
    sweep = read(manifest_path)
    if sweep["mount_deg"] != list(MOUNTS) or sweep["planned_rel_deg"] != list(range(-180, 181, 10)):
        raise ValueError("Sweep mount or angle contract differs")
    case_digests = {
        name: sweep["output_sha256"][f"poses/{args.case}/{name}"]
        for name in ("rf_poses.json", "rf_tasks.json", "SCENE_ENTRY.json")
    }
    for name, digest in case_digests.items():
        verify(case_root / name, digest)
    if read(case_root / "SCENE_ENTRY.json") != scene:
        raise ValueError(f"Sweep scene differs from frozen production: {args.case}")
    poses = read(case_root / "rf_poses.json")
    tasks = read(case_root / "rf_tasks.json")
    if ([pose["pose_id"] for pose in poses] != list(range(len(poses)))
            or [task["task_id"] for task in tasks] != list(range(len(tasks)))
            or Counter(pose_id for task in tasks for pose_id in task["pose_ids"])
            != Counter(range(len(poses)))
            or any(len(task["pose_ids"]) != 36 for task in tasks)
            or len({(task["x"], task["y"]) for task in tasks}) != len(tasks)):
        raise ValueError(f"Sweep poses or task coverage differ: {args.case}")
    for task in tasks:
        if any((poses[i]["x"], poses[i]["y"]) != (task["x"], task["y"]) for i in task["pose_ids"]):
            raise ValueError(f"Sweep poses differ from the traced XY: {task['tag']}")
    if not 0 <= args.shard_index < args.shard_count <= len(tasks) or args.field_batch_xy < 1:
        raise ValueError("Invalid shard index/count or field batch size")
    if args.task_id is None:
        tasks = tasks[args.shard_index::args.shard_count]
    else:
        if (args.shard_count != 1 or len(set(args.task_id)) != len(args.task_id)
                or not all(0 <= task_id < len(tasks) for task_id in args.task_id)):
            raise ValueError("Invalid explicit canary task selection")
        tasks = [tasks[task_id] for task_id in sorted(args.task_id)]
    production, reference = frozen_settings(args)
    core, _, versions = load_runtime(args.source)
    for name, digest in FINITE_FACE_SOURCE_SHA.items():
        verify(Path(__file__).with_name(name), digest)
    rt_solvers = Path(core.rt.__file__).parent / "path_solvers"
    for name, digest in FINITE_FACE_RUNTIME_SHA.items():
        verify(rt_solvers / name, digest)
    args.out.mkdir(parents=True, mode=0o700, exist_ok=False)
    ids, receipts, timings = generate(
        core, scene, anchor, args.inputs / "scene", poses, tasks, production,
        args.out, args.field_batch_xy,
    )
    artifact_names = [str(path.relative_to(args.out)) for path in sorted(args.out.rglob("*"))
                      if path.is_file()]
    sources = ("run_tb3_sweep_shard.py", "run_tb3_production.py", "run_tb3_g1_pilot.py",
               "run_tb3_g8_pilot.py", "tb3_native_los.py", "tb3_paths_near.py")
    write(args.out / "MANIFEST.json", dict(
        status="PASS", scope="SWEEP_CANARY" if args.task_id else "FULL_SWEEP", case=args.case,
        question_ids=["G1-RT-TB3-001", "G1-RT-TB3-002"], role="IMPLEMENTER",
        code_commit=args.code_commit, mounts_deg=list(MOUNTS), shared_trace=True,
        engine={key: value for key, value in production.items() if key != "mount_deg"} | {
            "finite_face_guard": dict(stage="PRE_FIELD", g6_result_sha256=FINITE_FACE_G6_SHA,
                                      runtime_sha256=FINITE_FACE_RUNTIME_SHA),
        },
        g0_manifest_sha256=G0_SHA, g7_manifest_sha256=G7_SHA,
        production_sha256=F1_SHA, reference_sha256=REFERENCE_SHA, ffd_manifest_sha256=FFD_SHA,
        governance=reference["governance"],
        sweep_manifest_sha256=sha(manifest_path), sweep_case_input_sha256=case_digests,
        source_sha256={name: sha(Path(__file__).with_name(name)) for name in sources}
        | FINITE_FACE_SOURCE_SHA,
        shard_index=args.shard_index, shard_count=args.shard_count, trace_positions=len(tasks),
        poses=len(ids), near_pose_count=len(ids),
        solver_calls=sum(receipt["solver_calls"] for receipt in receipts),
        extra_export_solver_calls=0, native_field_batch_positions=args.field_batch_xy,
        started_utc=started_utc, finished_utc=utc_now(), wall_s=time.monotonic()-started,
        timings=timings, command=[sys.executable, *sys.argv], runtime_versions=versions,
        peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        output_sha256={name: sha(args.out / name) for name in artifact_names},
        output_bytes={name: (args.out / name).stat().st_size for name in artifact_names},
    ))


if __name__ == "__main__":
    main()
