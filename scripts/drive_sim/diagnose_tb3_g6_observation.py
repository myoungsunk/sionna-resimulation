"""G6-only paired sensitivity of signed s to exact image-law delays."""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from time import monotonic

import numpy as np

from diagnose_tb3_g6_image import G6_SHA256, STRICT_TOL_S
from diagnose_tb3_g6_precision import IMAGE_SHA256, exact_reflection, plane_hit
from run_tb3_g1_pilot import load_runtime, read, sha, write
from run_tb3_g8_pilot import capture_trace
from run_tb3_production import CASES, case_inputs, frozen_settings, utc_now, verify
from tb3_native_los import native_direct_fields
from tb3_paths_near import h_and_near_for_poses
from validate_tb3_g5 import mesh_triangles
from validate_tb3_g6 import traces_for_case
from validate_tb3_production_g3 import scene_runtime

GENERATION_SHA = "b05cae3dc9c26a62714e93931c1621c5c195844830b942b6bc738834b72e7c28"
SEAL_SHA = "4d755c9a016275f2ba51fee02e9908fe8cb2a27f32c187192f00bc957c45ee4a"
FP_SHA = "6da23ff66372a106dfbea521cc176031169210fed226e38d7d2db55b21f7c86b"
REPLAY_H_ATOL = 1e-15
G4_REFERENCE = 0.005


def production_inputs(root, case, pose_count):
    results = root / "results"
    generation_path = results / "GENERATION_RESULT.json"
    cases_path = results / "CASES.json"
    seal_path = results / "seal/SEAL_MANIFEST.json"
    verify(generation_path, GENERATION_SHA)
    verify(seal_path, SEAL_SHA)
    generation = read(generation_path)
    if generation["status"] != "PASS" or read(seal_path)["status"] != "SEALED":
        raise ValueError("Production or seal receipt does not match frozen state")
    verify(cases_path, generation["cases_sha256"])
    case_index = read(cases_path)[case]
    manifest_path = results / "H" / case / "MANIFEST.json"
    verify(manifest_path, case_index["manifest_sha256"])
    manifest = read(manifest_path)
    hashes = manifest["output_sha256"]
    h_relative = f"H/{case}/H_full.npy"
    h_path = results / h_relative
    receipts_path = results / "paths" / case / "TRACE_RECEIPTS.json"
    verify(receipts_path, hashes[f"paths/{case}/TRACE_RECEIPTS.json"])
    h_hash = hashes[h_relative]
    if case.startswith(("G-T2_", "G-V_")):
        sealed = read(seal_path)["cases"][case]
        if (sealed["case_manifest_sha256"] != case_index["manifest_sha256"]
                or sealed["files"][h_relative]["sha256"] != h_hash
                or h_path.stat().st_mode & 0o222):
            raise ValueError("H does not match the sealed case index")
    verify(h_path, h_hash)
    h = np.load(h_path, mmap_mode="r", allow_pickle=False)
    if h.dtype != np.complex128 or h.shape != (pose_count, 257, 2, 2):
        raise ValueError("Unexpected production H type or shape")
    receipt_rows = read(receipts_path)
    receipts = {r["task_id"]: r for r in receipt_rows}
    if len(receipts) != len(receipt_rows):
        raise ValueError("Duplicate production trace receipt")
    return h, receipts, {str(p): sha(p) for p in (manifest_path, receipts_path)} | {str(h_path): h_hash}


def trace_with_hits(core, scene, solver, config, frequencies, bins, task, setup):
    metadata = None

    def solve(scene, **kwargs):
        nonlocal metadata
        result = solver(scene, **kwargs)
        if metadata is None:
            tau = np.asarray(result.tau).ravel().astype(float)
            angles = np.stack([np.asarray(getattr(result, name)).ravel().astype(float)
                               for name in ("theta_t", "phi_t", "theta_r", "phi_r")])
            order = core.P.canonical_order(tau, *angles)
            depth, count = config["max_depth"], len(tau)
            events = np.asarray(result.interactions).reshape(depth, count).T[order]
            objects = np.asarray(result.objects).reshape(depth, count).T[order]
            primitives = np.asarray(result.primitives).reshape(depth, count).T[order]
            vertices = np.asarray(result.vertices).reshape(depth, count, 3).transpose(1, 0, 2)[order]
            metadata = tau[order], angles[:, order], events, objects, primitives, vertices
        return result

    trace, nodes = capture_trace(core, scene, solve, config, frequencies, bins, task, setup)
    tau, angles, events, objects, primitives, vertices = metadata
    none = core.rt.constants.InteractionType.NONE
    if (not np.array_equal(tau, trace["tau"]) or not np.array_equal(angles, trace["ang"])
            or not np.array_equal(events, trace["interactions"])
            or not np.array_equal(np.where(events == none, -1, objects), trace["objects"])):
        raise ValueError("First-node path geometry differs from the canonical production trace")
    return trace, nodes.tolist(), primitives, vertices


def image_delay(core, row, trace, primitives, vertices, object_meshes, tx, rx):
    index = row["path_index"]
    if trace["tau"][index] != row["solved_delay_s"]:
        raise ValueError("Image row differs from its canonical production path")
    reflections, names = [], []
    rt_type = core.rt.constants.InteractionType
    for event, obj, prim, vertex in zip(trace["interactions"][index], trace["objects"][index],
                                        primitives[index], vertices[index], strict=True):
        if event == rt_type.NONE:
            continue
        if event != rt_type.SPECULAR:
            raise ValueError("Unexpected non-specular path in image-law diagnostic")
        name, mesh = object_meshes[int(obj)]
        triangle = mesh[int(prim)]
        axis, pos, _ = plane_hit(triangle, vertex.astype(float))
        reflections.append((axis, pos, triangle))
        names.append(name)
    exact, _ = exact_reflection(tx, rx, reflections)
    return exact, ">".join(names) if names else "LOS"


def replay(args):
    start_utc, tick = utc_now(), monotonic()
    verify(args.g6 / "G6.json", G6_SHA256)
    verify(args.image_result, IMAGE_SHA256)
    verify(args.source / "src/qclean_uwb/features/fp_power.py", FP_SHA)
    original = read(args.g6 / "G6.json")
    image = read(args.image_result)
    if original["status"] != "FAIL" or original["strict_tolerance_s"] != STRICT_TOL_S:
        raise ValueError("The original strict G6 FAIL is required")
    selection_path = args.g6 / "selected/SELECTION.json"
    verify(selection_path, original["input_sha256"]["/run/selected/SELECTION.json"])
    selection = read(selection_path)
    index, count = map(int, args.shard.split("/"))
    by_task = defaultdict(list)
    for row in image["rows"]:
        if row["case"] == args.case:
            by_task[row["task_id"]].append(row)
    if not 0 <= index < count <= len(by_task):
        raise ValueError("Invalid replay shard")
    task_ids = sorted(by_task)[index::count]

    root = args.production_root
    args.production = root / "config/PRODUCTION_F1.json"
    args.reference = root / "frozen/REFERENCE.json"
    args.ffd_manifest = root / "frozen/FFD_RESTORE_MANIFEST.json"
    production, _ = frozen_settings(args)
    entry, anchor_id, poses, tasks, *_ = case_inputs(root / "g0", root / "g7", args.case)
    archived_checks = {}
    archived, _, missing, unexpected = traces_for_case(
        args.case, selection[args.case], args.g6 / "traces", archived_checks)
    if missing or unexpected or any(original["input_sha256"][f"/run/traces/{Path(p).name}"] != v
                                     for p, v in archived_checks.items()):
        raise ValueError("Original G6 trace archive is incomplete or changed")
    h_saved, receipts, inputs = production_inputs(root, args.case, len(poses))
    core, _, versions = load_runtime(args.source)
    from qclean_uwb.features.fp_power import signed_s_single_tx

    scene_root = root / "g0/scene"
    scene, solver, setup = scene_runtime(core, entry, anchor_id, scene_root)
    meshes = {b["object"]: np.asarray(mesh_triangles(scene_root / b["ply"]))
              for b in entry["material_bindings"]}
    object_meshes = {int(obj.object_id): (name, meshes[name]) for name, obj in scene.objects.items()}
    native_banks = core.C.load_banks()
    banks = [core.P.Bank(bank) for bank in native_banks]
    frequencies = banks[0].freqs_hz
    bins = core.node_bins(len(frequencies), str(production["base_nodes"]))
    ports = core.C.make_ports(native_banks)
    tx_native = np.asarray(scene.transmitters["tx"].position).reshape(3)
    tx = entry["anchors_xyz_m"][anchor_id]
    none = core.rt.constants.InteractionType.NONE
    mount = production["mount_deg"]
    station_rows, delta_s, path_rows = [], [], []
    exact_baseline_poses, index_changes, node_calls = 0, 0, 0
    max_h_replay_error = max_s_replay_error = 0.0
    for offset in range(0, len(task_ids), 64):
        batch, batch_poses, rx_pos = [], [], []
        for task_id in task_ids[offset:offset + 64]:
            task, old, receipt = tasks[task_id], archived[task_id], receipts[task_id]
            trace, nodes, primitives, vertices = trace_with_hits(
                core, scene, solver, production["solver"], frequencies, bins, task, setup)
            node_calls += len(nodes)
            if (receipt["tag"] != task["tag"] or receipt["pose_ids"] != task["pose_ids"]
                    or nodes != old["node_bins"] or nodes != receipt["node_bins"]
                    or len(trace["tau"]) != receipt["n_full_paths"] or not trace["present"].all()
                    or not np.array_equal(trace["tau"], old["tau_s"])):
                raise ValueError(f"Replay differs from frozen production and G6 trace: {task['tag']}")
            changed = trace["tau"].copy()
            for row in by_task[task_id]:
                rx = [task["x"], task["y"], entry["rx_z_m"]]
                if rx[:2] != row["xy"]:
                    raise ValueError("Diagnostic and frozen pose geometry differ")
                try:
                    exact, physical_sequence = image_delay(
                        core, row, trace, primitives, vertices, object_meshes, tx, rx)
                except (ValueError, ZeroDivisionError) as error:
                    raise ValueError(f"{args.case}/{task_id}/{row['path_index']}: {error}") from error
                changed[row["path_index"]] = exact
                path_rows.append(dict(task_id=task_id, path_index=row["path_index"],
                                      physical_sequence=physical_sequence,
                                      native_minus_image_s=row["solved_delay_s"] - exact,
                                      same_delay_as_nearest_candidate=abs(exact - row["nearest_image_delay_s"]) <= 1e-20))
            task_poses = [poses[i] for i in task["pose_ids"]]
            start = len(batch_poses)
            batch_poses.extend(task_poses)
            rx_native = np.asarray(scene.receivers["rx"].position).reshape(3).copy()
            rx_pos.extend([rx_native] * len(task_poses))
            batch.append((task, trace, changed, slice(start, len(batch_poses))))
        coeff, direct_delays = native_direct_fields(
            core, tx_native, rx_pos, batch_poses, mount, native_banks, ports)
        for task, trace, changed, section in batch:
            direct = np.flatnonzero((trace["interactions"] == none).all(axis=1))
            if len(direct) != 1 or np.max(np.abs(direct_delays[section] - trace["tau"][direct])) > 2e-13:
                raise ValueError("Native LoS field does not align with the production trace")
            options = dict(mount_deg=mount, none_event=none, export_pose_ids=set(),
                           direct_coefficients=coeff[section])
            baseline, _ = h_and_near_for_poses(trace, banks, batch_poses[section], **options)
            adjusted, _ = h_and_near_for_poses(trace | {"tau": changed}, banks,
                                               batch_poses[section], **options)
            saved = h_saved[task["pose_ids"]]
            h_error = float(np.max(np.abs(saved - baseline)))
            if not np.isfinite(h_error) or h_error > REPLAY_H_ATOL:
                raise ValueError(f"Baseline H does not reproduce production: {args.case}/{task['task_id']} ({h_error:g})")
            max_h_replay_error = max(max_h_replay_error, h_error)
            exact_baseline_poses += int(np.all(saved == baseline, axis=(1, 2, 3)).sum())
            station_delta = []
            for h0, h1, h2 in zip(saved, baseline, adjusted, strict=True):
                s0, _, fp0, _ = signed_s_single_tx(h0, frequencies, tx=0)
                s1, _, fp1, _ = signed_s_single_tx(h1, frequencies, tx=0)
                s2, _, fp2, _ = signed_s_single_tx(h2, frequencies, tx=0)
                if fp0 != fp1 or not np.isfinite([s0, s1, s2]).all():
                    raise ValueError("Nonfinite observation or misaligned replay first path")
                max_s_replay_error = max(max_s_replay_error, abs(s0 - s1))
                index_changes += int(fp0 != fp2)
                station_delta.append(abs(s2 - s0))
            delta_s.extend(station_delta)
            station_rows.append(dict(task_id=task["task_id"], pose_count=len(station_delta),
                                     max_abs_delta_s=max(station_delta)))
        print(f"{args.case}/{index}: {min(offset+64, len(task_ids))}/{len(task_ids)} positions", flush=True)

    write(args.out, dict(case=args.case, shard=args.shard, official_gate_status="FAIL",
                         purpose="Post-result G6 observation sensitivity, no heading-error computations",
                         script_sha256=sha(Path(__file__)), runtime=versions | {"mitsuba": core.mi.variant()},
                         start_utc=start_utc, finish_utc=utc_now(), wall_s=monotonic() - tick,
                         positions=len(task_ids), solver_calls=node_calls, poses=len(delta_s),
                         frequency_hz=[float(frequencies[0]), float(frequencies[-1])],
                         baseline_exact_poses=exact_baseline_poses, first_path_index_changes=index_changes,
                         max_h_replay_error=max_h_replay_error, max_s_replay_error=max_s_replay_error,
                         input_sha256=inputs, station_rows=station_rows, path_rows=path_rows,
                         abs_delta_s=delta_s))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("g6", "image-result", "production-root", "source", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--shard", required=True)
    replay(parser.parse_args())


if __name__ == "__main__":
    main()
