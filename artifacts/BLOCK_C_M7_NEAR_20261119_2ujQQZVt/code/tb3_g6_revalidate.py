"""Retrace original G6 positions and measure finite-face delay residuals."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from time import monotonic

import numpy as np

from diagnose_tb3_g6_image import G6_SHA256, STRICT_TOL_S
from diagnose_tb3_g6_observation import GENERATION_SHA
from run_tb3_g1_pilot import load_runtime, read, sha, write
from run_tb3_g8_pilot import capture_trace
from run_tb3_production import case_inputs, frozen_settings, utc_now, verify
from tb3_g6_face_match import check_geometry, load_faces, match_path
from tb3_g6_trace import select_tasks
from validate_tb3_g6 import CASES, traces_for_case
from validate_tb3_production_g3 import scene_runtime


def production_receipts(root, case, tasks, inputs):
    results = root / "results"
    generation_path = results / "GENERATION_RESULT.json"
    case_index = results / "CASES.json"
    case_manifest = results / "H" / case / "MANIFEST.json"
    path = results / "paths" / case / "TRACE_RECEIPTS.json"
    verify(generation_path, GENERATION_SHA)
    generation = read(generation_path)
    if generation["status"] != "PASS":
        raise ValueError("Production generation receipt must be PASS")
    verify(case_index, generation["cases_sha256"])
    verify(case_manifest, read(case_index)[case]["manifest_sha256"])
    receipt_sha = read(case_manifest)["output_sha256"][f"paths/{case}/TRACE_RECEIPTS.json"]
    verify(path, receipt_sha)
    rows = {}
    for row in read(path):
        index = row["task_id"]
        if index in rows or row["tag"] != tasks[index]["tag"] or row["pose_ids"] != tasks[index]["pose_ids"]:
            raise ValueError(f"Wrong production receipt at {case}/{index}")
        rows[index] = row
    inputs.update({str(p): sha(p) for p in (generation_path, case_index, case_manifest)} | {str(path): receipt_sha})
    return rows


def trace_hits(core, scene, solver, settings, frequencies, bins, task, setup, mesh_faces, observe=None):
    """Keep node-zero vertices and prove the ordered face identity across nodes."""
    metadata = []
    depth = settings["max_depth"]
    rt_type = core.rt.constants.InteractionType

    def solve(scene, **kwargs):
        native = solver(scene, **kwargs)
        if observe is not None:
            observe()
        delay = np.asarray(native.tau).ravel().astype(float)
        ang = np.stack([np.asarray(getattr(native, prop)).ravel().astype(float)
                        for prop in ("theta_t", "phi_t", "theta_r", "phi_r")])
        n = len(delay)
        events = np.asarray(native.interactions).reshape(depth, n).T
        objects = np.asarray(native.objects).reshape(depth, n).T
        primitives = np.asarray(native.primitives).reshape(depth, n).T
        vertices = None
        if not metadata:
            vertices = np.asarray(native.vertices)
            if vertices.dtype != np.float32:
                raise ValueError("Unexpected solver hit vertex dtype")
            vertices = vertices.reshape(depth, n, 3).transpose(1, 0, 2)
        metadata.append((delay, ang, events, objects, primitives, vertices))
        return native

    trace, nodes = capture_trace(core, scene, solve, settings, frequencies, bins, task, setup)
    if len(metadata) != len(nodes) or nodes.tolist() != list(bins) or not trace["present"].all():
        raise ValueError("Incomplete canonical path/node coverage")
    ref_delay = trace["tau"]
    ref_angles = trace["ang"]
    ref_events = trace["interactions"]
    ref_objects = trace["objects"]
    ref_dirs = core.P.path_directions(*ref_angles)
    first = metadata[0]
    order0 = core.P.canonical_order(first[0], *first[1])
    if not np.array_equal(first[0][order0], ref_delay) or not np.array_equal(first[1][:, order0], ref_angles):
        raise ValueError("Node zero geometry is not the canonical production ordering")
    hits = [[] for _ in ref_delay]
    index0 = first[4][order0]
    vertices = first[5][order0]
    for i in range(len(ref_delay)):
        for j, event in enumerate(ref_events[i]):
            if event == rt_type.NONE:
                if np.any(ref_events[i, j:] != rt_type.NONE):
                    raise ValueError("Padding precedes a path interaction")
                break
            if event != rt_type.SPECULAR:
                raise ValueError("F1 path includes a non-specular interaction")
            obj, primitive = int(ref_objects[i, j]), int(index0[i, j])
            triangles, faces = mesh_faces[obj]
            hits[i].append((primitive, triangles[primitive], faces[primitive], tuple(map(float, vertices[i, j]))))

    if sum(not h for h in hits) != 1:
        raise ValueError("Expected one LoS path at the frozen G6 position")
    for delay, ang, events, objects, primitives, _ in metadata[1:]:
        order, extra = core.P.match_partial(ref_delay, ref_dirs, delay, core.P.path_directions(*ang),
                                           tol=core.ANGLE_TOL_RAD)
        if (len(extra) or np.any(order < 0) or not np.array_equal(events[order], ref_events)
                or not np.array_equal(np.where(ref_events == rt_type.NONE, -1, objects[order]), ref_objects)):
            raise ValueError("Path metadata differs between production nodes")
        prim = primitives[order]
        for i, j in np.argwhere((prim != index0) & (ref_events != rt_type.NONE)):
            face = mesh_faces[int(ref_objects[i, j])][1][int(prim[i, j])]
            if face is not hits[i][j][2]:
                raise ValueError("Matched path changed finite reflection face across nodes")
    return trace, hits, nodes.tolist()


def run(args):
    start, tick = utc_now(), monotonic()
    check_geometry()
    original_path = args.original / "G6.json"
    verify(original_path, G6_SHA256)
    original = read(original_path)
    if original["status"] != "FAIL" or original["strict_tolerance_s"] != STRICT_TOL_S:
        raise ValueError("Unexpected original G6 gate/threshold")
    selection_path = args.original / "selected/SELECTION.json"
    selected_path = selection_path.parent / f"{args.case}.json"
    verify(selection_path, original["input_sha256"]["/run/selected/SELECTION.json"])
    selection = read(selection_path)[args.case]
    verify(selected_path, selection["selector_sha256"])
    archived_hashes = {}
    archived, _, missing, extra = traces_for_case(args.case, selection, args.original / "traces", archived_hashes)
    if missing or extra or any(original["input_sha256"][f"/run/traces/{Path(p).name}"] != v
                               for p, v in archived_hashes.items()):
        raise ValueError("Original archived trace coverage or SHA differs")
    root = args.production
    args.production = root / "config/PRODUCTION_F1.json"
    args.reference = root / "frozen/REFERENCE.json"
    args.ffd_manifest = root / "frozen/FFD_RESTORE_MANIFEST.json"
    production, reference = frozen_settings(args)
    entry, anchor_id, _, tasks, *_ = case_inputs(root / "g0", root / "g7", args.case)
    index, count = map(int, args.shard.split("/"))
    if args.task_id:
        wanted = sorted(set(args.task_id))
        if not set(wanted) <= archived.keys() or (index, count) != (0, 1):
            raise ValueError("Explicit smoke targets must belong to original selection and use shard 0/1")
        chosen = [tasks[i] for i in wanted]
    else:
        chosen = select_tasks(read(selected_path), tasks, index, count)
    inputs = {str(p): sha(p) for p in (
        original_path, selection_path, selected_path, args.production, args.reference, args.ffd_manifest,
        root / "g0/RUN_MANIFEST.json", root / "g7/RUN_MANIFEST.json")}
    receipts = production_receipts(root, args.case, tasks, inputs)
    core, _, versions = load_runtime(args.source)
    scene_root = root / "g0/scene"
    scene, solver, setup = scene_runtime(core, entry, anchor_id, scene_root)
    geometry = load_faces(scene, entry, scene_root)
    with np.load(args.source / "LP_plus45_bank.npz", allow_pickle=False) as bank:
        frequencies = bank["freqs_hz"]
    if frequencies.shape != (production["channel_bins"],) or not np.isfinite(frequencies).all():
        raise ValueError("Unexpected frozen frequency grid")
    bins = core.node_bins(len(frequencies), str(production["base_nodes"]))
    tx = tuple(entry["anchors_xyz_m"][anchor_id])
    tx_native = tuple(np.asarray(scene.transmitters["tx"].position).reshape(3).astype(float))
    guard = None
    code_paths = [Path(__file__), Path(__file__).with_name("tb3_g6_face_match.py")]
    if args.finite_face_prior:
        from tb3_finite_face_guard import FiniteFaceGuard
        from tb3_g6_guard_replay import INPUT_HASHES, archived_rows, load_prior, verify_rejections

        prior, boundary = load_prior(args.finite_face_prior, STRICT_TOL_S)
        prior_rows, prior_hashes = archived_rows(args.finite_face_prior, prior["cases"][args.case],
                                                args.case, index, count, chosen, bool(args.task_id))
        targets = boundary[args.case]
        inputs.update({str(args.finite_face_prior / name): digest for name, digest in INPUT_HASHES.items()})
        inputs.update(prior_hashes)
        guard = FiniteFaceGuard(solver, core.mi, scene, geometry, tx, tx, core.rt.constants.InteractionType)
        code_paths.extend(Path(__file__).with_name(name)
                          for name in ("tb3_finite_face_guard.py", "tb3_g6_guard_replay.py"))

    totals = Counter()
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        for k, task in enumerate(chosen, start=1):
            task_id = task["task_id"]
            old, receipt = archived[task_id], receipts[task_id]
            rx = task["x"], task["y"], entry["rx_z_m"]
            target = None
            removed = []
            observed = []
            observe = None
            if guard is not None:
                target = targets.get(task_id)
                removed = [] if target is None else [target["path_index"]]
                guard.set_receiver(rx)

                def observe():
                    observed.append(guard.rejected)

            trace, hits, nodes = trace_hits(core, scene, solver, production["solver"], frequencies,
                                           bins, task, setup, geometry, observe=observe)
            expected_tau = np.delete(old["tau_s"], removed) if removed else old["tau_s"]
            if (old["case"] != args.case or old["tag"] != task["tag"] or old["pose_ids"] != task["pose_ids"]
                    or [old["x"], old["y"]] != [task["x"], task["y"]] or old["status"] != "OK"
                    or nodes != old["node_bins"] or nodes != receipt["node_bins"]
                    or not np.array_equal(trace["tau"], expected_tau)
                    or len(hits) + len(removed) != receipt["n_full_paths"]
                    or old["absent_at_some_node_paths"]):
                raise ValueError(f"Native tau or coverage differs from original/production at {args.case}/{task_id}")
            rx_native = tuple(np.asarray(scene.receivers["rx"].position).reshape(3).astype(float))
            if list(tx_native) != old["tx_xyz_m"] or list(rx_native) != old["rx_xyz_m"]:
                raise ValueError(f"Native endpoints differ at {args.case}/{task_id}")
            rows = []
            for i, path in enumerate(hits):
                signature, segments, image, switches, plane_offset, error = match_path(tx, rx, tx_native, rx_native, path)
                residual = None if image is None else abs(segments - image)
                rows.append([signature, segments, image, switches, plane_offset, error])
                totals["image_geometry_unmatched"] += int(error is not None)
                totals["delay_exceeded"] += int(residual is not None and residual > STRICT_TOL_S)
                totals["primitive_seam_crossings"] += switches
            totals.update(positions=1, solver_calls=len(nodes), examined_paths=len(rows))
            record = dict(case=args.case, task_id=task_id, tag=task["tag"],
                          xy=[task["x"], task["y"]], node_bins=nodes, paths=rows)
            if guard is not None:
                entries = [dict(bin=node, paths=paths) for node, paths in zip(nodes, observed, strict=True) if paths]
                if len(observed) != len(nodes):
                    raise ValueError(f"Incomplete pre-field observations at {args.case}/{task_id}")
                pre_field, matched = verify_rejections(entries, nodes, target)
                archived_row = prior_rows[task_id]
                baseline = archived_row["paths"]
                if (any(record[k] != archived_row[k] for k in ("case", "task_id", "tag", "xy", "node_bins"))
                        or len(baseline) != receipt["n_full_paths"]
                        or rows != [row for i, row in enumerate(baseline) if i not in removed]):
                    raise ValueError(f"Retained geometry differs from archived corrected trace: {args.case}/{task_id}")
                if pre_field or removed:
                    record["guard"] = dict(removed_baseline_indices=removed, rejections=entries)
                totals.update(removed_paths=len(removed), removed_path_nodes=matched, pre_field_rejections=pre_field)
            stream.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
            if k == 1 or k % 100 == 0 or k == len(chosen):
                print(f"{args.case}/{index}: {k}/{len(chosen)} positions", flush=True)
    package = Path(core.rt.__file__).parent / "path_solvers"
    write(args.out.with_suffix(".manifest.json"), dict(
        case=args.case, shard=args.shard, smoke=bool(args.task_id), totals=dict(totals), node_bins=list(bins),
        strict_tolerance_s=STRICT_TOL_S, runtime=versions | {"mitsuba_variant": core.mi.variant()},
        solver=production["solver"], method_b_commit=reference["method_b_commit"],
        started_utc=start, finished_utc=utc_now(), wall_s=monotonic()-tick,
        input_sha256=inputs | archived_hashes, output_sha256=sha(args.out),
        finite_face_guard=guard is not None,
        code_sha256={p.name: sha(p) for p in (*code_paths, package / "field_calculator.py", package / "paths.py",
                                             package / "path_solver.py", package / "image_method.py")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("production", "source", "original", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--finite-face-prior", type=Path, help="Frozen prior replay records for the guard")
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--shard", required=True)
    parser.add_argument("--task-id", action="append", type=int, help="Explicit task IDs for a bounded smoke")
    run(parser.parse_args())


if __name__ == "__main__":
    main()
