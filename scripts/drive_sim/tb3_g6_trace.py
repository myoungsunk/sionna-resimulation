"""Trace G6 path delays on the frozen TB3 production scene without channel inputs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import monotonic

import numpy as np

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write
from run_tb3_production import CASES, case_inputs, frozen_settings, utc_now


def trace_task(core, scene, solver, config, freq, bins, task, setup, all_nodes):
    if all_nodes:
        from run_tb3_g8_pilot import capture_trace

        trace, nodes = capture_trace(core, scene, solver, config, freq, bins, task, setup)
        return trace["tau"], trace["status"], nodes, int((~trace["present"].all(axis=0)).sum())

    scene.receivers["rx"].position = core.mi.Point3f(*setup.robot_position(task["x"], task["y"]).tolist())
    scene.frequency = float(freq[bins[0]])
    result = solver(scene, **config)
    return np.asarray(result.tau).ravel().astype(np.float64), "OK", bins, 0


def select_tasks(selected, frozen, index, count):
    if not 0 <= index < count <= len(selected):
        raise ValueError("Invalid shard index/count for selection size")
    ids = [row["task_id"] for row in selected]
    if len(set(ids)) != len(ids) or any(type(i) is not int or not 0 <= i < len(frozen) for i in ids):
        raise ValueError("G6 selection has duplicate or unknown task IDs")
    for row in selected:
        task = frozen[row["task_id"]]
        if any(key in row and row[key] != task[key] for key in ("tag", "x", "y")):
            raise ValueError(f"Selection disagrees with frozen task {task['task_id']}")
    return [frozen[i] for i in ids[index::count]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("production-root", "source", "tasks", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--shard", default="0/1")
    parser.add_argument("--all-nodes", action="store_true")
    parser.add_argument("--receipts", type=Path, help="SHA-checked production TRACE_RECEIPTS.json")
    args = parser.parse_args()
    index, count = (int(part) for part in args.shard.split("/"))
    started_utc, started = utc_now(), monotonic()
    if args.all_nodes and args.receipts is None:
        parser.error("--all-nodes requires --receipts")
    root = args.production_root
    args.production = root / "config/PRODUCTION_F1.json"
    args.reference = root / "frozen/REFERENCE.json"
    args.ffd_manifest = root / "frozen/FFD_RESTORE_MANIFEST.json"
    production, _ = frozen_settings(args)
    entry, anchor_id, _, frozen, *_ = case_inputs(root / "g0", root / "g7", args.case)
    selected = select_tasks(read(args.tasks), frozen, index, count)
    input_hashes = {str(path): sha(path) for path in
                    (args.tasks, args.production, args.reference, args.ffd_manifest,
                     root / "g0/RUN_MANIFEST.json", root / "g7/RUN_MANIFEST.json")}
    receipts = {}
    if args.receipts:
        if args.receipts.name != "TRACE_RECEIPTS.json":
            raise ValueError("Expected production TRACE_RECEIPTS.json")
        generation = root / "results/GENERATION_RESULT.json"
        case_manifest = root / f"results/H/{args.case}/MANIFEST.json"
        gate = read(generation)
        cases = root / "results/CASES.json"
        if gate["status"] != "PASS" or sha(cases) != gate["cases_sha256"]:
            raise ValueError("Production generation receipt is invalid")
        case = read(cases)[args.case]
        if sha(case_manifest) != case["manifest_sha256"]:
            raise ValueError("Production case manifest is invalid")
        receipt_manifest = read(case_manifest)
        expected = receipt_manifest["output_sha256"][f"paths/{args.case}/TRACE_RECEIPTS.json"]
        if sha(args.receipts) != expected:
            raise ValueError("Production trace receipts are invalid")
        input_hashes |= {str(path): sha(path) for path in (args.receipts, generation, cases, case_manifest)}
        for row in read(args.receipts):
            task_id = row["task_id"]
            if task_id in receipts or row["tag"] != frozen[task_id]["tag"]:
                raise ValueError(f"Invalid production trace receipt at task {task_id}")
            receipts[task_id] = row
        if not {task["task_id"] for task in selected} <= receipts.keys():
            raise ValueError("Missing production trace receipts for selected tasks")

    core, _, versions = load_runtime(args.source)
    anchor = entry["anchors_xyz_m"][anchor_id]
    factory, loader = geometry_adapter(core, entry | {"anchors_xyz_m": {"A": anchor}}, root / "g0/scene")
    setup = factory(anchor_x_m=anchor[0])
    if not all(check["passed"] for check in setup.validate()):
        raise ValueError("Invalid validated production corridor")
    scene, _ = loader(setup, None)
    rt, mi = core.rt, core.mi
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0] * 3))
    scene.add(rt.Receiver("rx", position=setup.robot_position(*setup.example_xy_m[0]).tolist(),
                          orientation=[0.0] * 3))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(core.Ports([core.IsoPort(0), core.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))
    solver = rt.PathSolver()
    bank_path = args.source / "LP_plus45_bank.npz"
    with np.load(bank_path, allow_pickle=False) as bank:
        freq = bank["freqs_hz"]
    if freq.shape != (production["channel_bins"],) or not np.isfinite(freq).all():
        raise ValueError("Invalid frozen frequency grid")
    bins = core.node_bins(len(freq), str(production["base_nodes"])) if args.all_nodes else [0]
    tx = np.asarray(scene.transmitters["tx"].position).reshape(3).tolist()
    traced = mismatches = node_mismatches = absences = non_ok = solver_calls = 0
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        for task in selected:
            tau, status, nodes, absent = trace_task(core, scene, solver, production["solver"], freq,
                                                   bins, task, setup, args.all_nodes)
            if len(tau) == 0:
                status = "NO_PATHS"
            receipt = receipts.get(task["task_id"], {})
            expected_count = receipt.get("n_full_paths")
            expected_nodes = receipt.get("node_bins")
            node_bins = list(map(int, nodes))
            node_match = None if not args.all_nodes else node_bins == expected_nodes
            match = None if expected_count is None else expected_count == len(tau)
            rx = np.asarray(scene.receivers["rx"].position).reshape(3).tolist()
            row = dict(case=args.case, task_id=task["task_id"], tag=task["tag"], x=task["x"], y=task["y"],
                       pose_ids=task["pose_ids"], tx_xyz_m=tx, rx_xyz_m=rx, status=status,
                       node_bins=node_bins, absent_at_some_node_paths=absent,
                       production_path_count=expected_count, production_path_count_match=match,
                       production_node_bins=expected_nodes, production_node_bins_match=node_match,
                       tau_s=tau.tolist())
            stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
            traced += 1
            mismatches += int(match is False)
            node_mismatches += int(node_match is False)
            absences += absent
            non_ok += int(status != "OK")
            solver_calls += len(nodes)
            if traced == 1 or traced % 100 == 0 or traced == len(selected):
                print(f"{args.case}/{index}: {traced}/{len(selected)} positions", flush=True)
    manifest = dict(case=args.case, shard=args.shard, all_nodes=args.all_nodes, expected_bins=bins,
                    expected_frequencies_hz=[float(freq[b]) for b in bins], solver=production["solver"],
                    input_sha256=input_hashes, output_sha256=sha(args.out), code_sha256=sha(Path(__file__)),
                    runtime=versions, started_utc=started_utc, finished_utc=utc_now(),
                    wall_s=monotonic() - started, positions=traced, solver_calls=solver_calls,
                    non_ok_traces=non_ok, traces_with_different_production_count=mismatches,
                    traces_with_different_production_nodes=node_mismatches,
                    absent_at_some_node_paths=absences)
    write(args.out.with_suffix(".manifest.json"), manifest)


if __name__ == "__main__":
    main()
