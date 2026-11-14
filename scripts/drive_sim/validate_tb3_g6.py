"""G6 path continuity with the frozen Method B test and TB3 mesh planes."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from itertools import pairwise, product
import json
from pathlib import Path
import time
from types import SimpleNamespace

import numpy as np

from run_tb3_g1_pilot import read, sha, write
from run_tb3_production import CASES, case_inputs, verify
from validate_tb3_g5 import mesh_triangles


CASES = CASES[:9]
ROUTES = ("P-A_TEACH", "P-A_REPEAT", "P-A_PRIME", "P-B", "C1", "C2", "C3", "C4")
PREREG = "results/DRIVE_SIM_20261007/S0/PREREG.json"
LEGACY = {
    PREREG: "db28d1dd0dbb5a7c5695b0bb3ed630f5abaa10eb6c1eb48545c6b14c9a1a1d01",
    "scripts/drive_sim/path_continuity.py": "26044ede98baf45382b3aa3dc8b24c7b064a6bcf6d6f4d11441498af2b3cb201",
    "src/qclean_uwb/drivesim/paths.py": "4436e140225330ab068bc3525edd6fd0d5e04e576ceb8c13fecc6c8ad635c1ed",
    "src/qclean_uwb/features/reflection_attribution.py": "76f3c8d1828044dbec9ef27525b4cf5aa12639568d9c4807edc750dc3c97c919",
}
RELAXED_TOL_S = 2e-13


def select(root, out):
    cases = {}
    for case in CASES:
        _, _, _, tasks, base, _, _ = case_inputs(root / "g0", root / "g7", case)
        by_pose = {pose: t["task_id"] for t in tasks for pose in t["pose_ids"]}
        routes = {}
        for name in ROUTES:
            sequence = [by_pose[r["pose_id"]] for r in base
                        if r["set"] == name and
                        (name not in ROUTES[:2] or r["protocol"] == "base")]
            if len(sequence) < 2 or (name in ROUTES[:2] and len(sequence) != 18):
                raise ValueError(f"Incomplete sequence for {case}/{name}")
            routes[name] = list(dict.fromkeys(sequence))
        needed = set(t for route in routes.values() for t in route)
        task_path = out / f"{case}.json"
        write(task_path, [t for t in tasks if t["task_id"] in needed])
        cases[case] = dict(routes=routes, positions=len(needed), selector_sha256=sha(task_path))
    write(out / "SELECTION.json", cases)
    print("G6 selection:", {c: v["positions"] for c, v in cases.items()}, flush=True)


def mesh_planes(entry, scene_root):
    """Get the infinite planes of the frozen axis-aligned reflection faces."""
    names, keys = {}, {}
    for item in entry["material_bindings"]:
        path = scene_root / item["ply"]
        verify(path, item["ply_sha256"])
        name = item["object"]
        planes = set()
        for triangle in mesh_triangles(path):
            triangle = np.array(triangle)
            axes = np.flatnonzero(np.ptp(triangle, axis=0) == 0)
            if len(axes) != 1:
                raise ValueError(f"Non-axis-aligned or degenerate triangle: {path}")
            axis = int(axes[0])
            planes.add((axis, float(triangle[0, axis])))
        for axis, position in sorted(planes):
            plane = (axis, position)
            label = name if len(planes) == 1 else f"{name}[{'xyz'[axis]}={position:g}]"
            keys[plane] = keys.get(plane, label)
            names[keys[plane]] = plane
    return names


def mirror_transforms(planes, order):
    """Precompute the affine images of the receiver for each surface sequence."""
    sequences, sign, translation = [()], [np.ones(3)], [np.zeros(3)]
    for depth in range(1, order + 1):
        for sequence in product(planes, repeat=depth):
            if any(a == b for a, b in pairwise(sequence)):
                continue
            s, b = np.ones(3), np.zeros(3)
            for name in reversed(sequence):
                axis, position = planes[name]
                s[axis] *= -1
                b[axis] = 2 * position - b[axis]
            sequences.append(sequence)
            sign.append(s)
            translation.append(b)
    return sequences, np.array(sign), np.array(translation)


def mesh_residuals(tau, tx, rx, transforms, legacy):
    sequences, sign, translation = transforms
    values = np.linalg.norm(sign * rx + translation - tx, axis=1) / legacy.C0
    class_delays, names = legacy.classes(dict(zip(sequences, values, strict=True)))
    distances = np.abs(tau[:, None] - class_delays[None, :])
    pick = distances.argmin(axis=1)
    return distances[np.arange(len(tau)), pick], pick, class_delays, names


def legacy_kernel(source):
    for rel, digest in LEGACY.items():
        verify(source / rel, digest)
    from qclean_uwb.drivesim.paths import _classes, path_residuals, signature_diff, TIE_S
    from qclean_uwb.features.reflection_attribution import C0, planes

    limits = read(source / PREREG)["config"]["gates"]["G3_path_continuity"]
    if limits["unmatched_paths_max"]["value"] != 0:
        raise ValueError("Unexpected frozen path continuity convention")
    return SimpleNamespace(classes=_classes, residuals=path_residuals, diff=signature_diff,
                           C0=C0, planes=planes, tie_s=TIE_S,
                           tol=limits["classify_paths_tol_s"]["value"])


def check_kernel(legacy):
    length, half_width, height = 20., .97, 2.7
    transforms = mirror_transforms(legacy.planes(length, half_width, height), 3)
    tx = np.array([7., 0., 2.65])
    for rx in (np.array([6., .47, .45]), np.array([10., 0., .45]), np.array([9.12, -.33, .45])):
        tau = np.linspace(5e-9, 150e-9, 251)
        expected = legacy.residuals(tau, tx, rx, length, half_width, height)
        actual = mesh_residuals(tau, tx, rx, transforms, legacy)
        if (not np.allclose(expected[0], actual[0], atol=1e-21, rtol=0)
                or not np.array_equal(expected[1], actual[1])
                or not np.allclose(expected[2], actual[2], atol=1e-21, rtol=0)
                or expected[3] != actual[3]):
            raise ValueError("Extended image-plane kernel disagrees with canonical rectangular kernel")
    # One specular bounce off a finite recess backwall; the two unfolded legs
    # reduce to the known horizontal separation for coincident TX/RX.
    local_wall = {"recess_back": (1, 1.16)}
    endpoint = np.array([6.32, .47, 1.2])
    tau = np.array([2 * (1.16 - .47) / legacy.C0])
    residual, pick, _, names = mesh_residuals(tau, endpoint, endpoint,
                                              mirror_transforms(local_wall, 3), legacy)
    if residual[0] > 1e-21 or names[pick[0]] != "recess_back":
        raise ValueError("Extended image-plane kernel fails the recess reflection fixture")


def traces_for_case(case, inputs, trace_dir, checks):
    rows = {}
    solver_calls = 0
    for trace_path in sorted(trace_dir.glob(f"{case}_*.jsonl")):
        manifest_path = trace_path.with_suffix(".manifest.json")
        manifest = read(manifest_path)
        verify(trace_path, manifest["output_sha256"])
        if (manifest["case"] != case or not manifest["all_nodes"]
                or manifest["expected_bins"] != list(range(0, 257, 16))
                or manifest["input_sha256"][f"/run/selected/{case}.json"] != inputs["selector_sha256"]):
            raise ValueError(f"Unexpected G6 trace source: {trace_path}")
        checks[str(trace_path)] = manifest["output_sha256"]
        checks[str(manifest_path)] = sha(manifest_path)
        with trace_path.open(encoding="utf-8") as stream:
            shard = [json.loads(line) for line in stream]
        if len(shard) != manifest["positions"] or sum(len(r["node_bins"]) for r in shard) != manifest["solver_calls"]:
            raise ValueError(f"Inconsistent shard coverage: {trace_path}")
        solver_calls += manifest["solver_calls"]
        for row in shard:
            task = row["task_id"]
            if task in rows or row["case"] != case:
                raise ValueError(f"Duplicate or misidentified trace in {trace_path}")
            rows[task] = row
    needed = set(t for seq in inputs["routes"].values() for t in seq)
    return rows, solver_calls, sorted(needed - rows.keys()), sorted(rows.keys() - needed)


def assess_case(case, entry, tasks, inputs, trace_dir, scene_root, legacy, checks):
    rows, calls, missing, unexpected = traces_for_case(case, inputs, trace_dir, checks)
    length, width, height = entry["dimensions_m"]
    anchor = entry["anchors_xyz_m"][case.split("_")[1]]
    transforms = None
    if case.startswith("G-T2_"):
        transforms = mirror_transforms(mesh_planes(entry, scene_root), 3)
    signatures, failures, not_ok, trace_mismatches = {}, [], [], []
    examined = strict = relaxed = absent = 0
    max_residual, min_gap = 0., float("inf")
    for task_id, row in sorted(rows.items()):
        task = tasks[task_id]
        tx, rx = np.array(anchor), np.array([task["x"], task["y"], entry["rx_z_m"]])
        if (row["tag"] != task["tag"] or [row["x"], row["y"]] != [task["x"], task["y"]]
                or row["pose_ids"] != task["pose_ids"]
                or not np.allclose(row["tx_xyz_m"], tx, atol=1e-6, rtol=0)
                or not np.allclose(row["rx_xyz_m"], rx, atol=1e-6, rtol=0)):
            raise ValueError(f"Wrong trace coordinates: {case}/{task_id}")
        absent += row["absent_at_some_node_paths"]
        if row["production_path_count_match"] is not True or row["production_node_bins_match"] is not True:
            trace_mismatches.append(task_id)
        tau = np.asarray(row["tau_s"])
        if row["status"] != "OK" or tau.ndim != 1 or not len(tau) or not np.isfinite(tau).all():
            not_ok.append(task_id)
            continue
        if transforms is None:
            residual, pick, cd, names = legacy.residuals(tau, tx, rx, length, width / 2, height)
        else:
            residual, pick, cd, names = mesh_residuals(tau, tx, rx, transforms, legacy)
        signatures[task_id] = sorted(names[i] for i in pick)
        examined += len(tau)
        n_strict = int((residual > legacy.tol).sum())
        n_relaxed = int((residual > RELAXED_TOL_S).sum())
        strict += n_strict
        relaxed += n_relaxed
        max_residual = max(max_residual, float(residual.max()))
        min_gap = min(min_gap, float(np.diff(cd).min()))
        if n_strict:
            failures.append(dict(task_id=task_id, xy=[task["x"], task["y"]],
                                 unmatched_strict=n_strict, unmatched_relaxed=n_relaxed,
                                 max_residual_s=float(residual.max()),
                                 paths=[dict(delay_s=float(tau[i]), residual_s=float(residual[i]),
                                             nearest_image=names[pick[i]]) for i in np.flatnonzero(residual > legacy.tol)]))
    routes = {}
    for name, order in inputs["routes"].items():
        changes = []
        for prev, curr in pairwise(order):
            a, b = signatures.get(prev), signatures.get(curr)
            if a is not None and b is not None and a != b:
                changes.append(dict(from_task=prev, to_task=curr, xy=[tasks[curr]["x"], tasks[curr]["y"]],
                                    **legacy.diff(a, b)))
        routes[name] = dict(positions=len(order), compared_adjacent_pairs=sum(
            a in signatures and b in signatures for a, b in pairwise(order)),
            set_change_count=len(changes), set_changes=changes)
    complete = not (missing or unexpected or not_ok or trace_mismatches)
    return dict(complete=complete, passed_strict=complete and strict == 0,
                passed_relaxed=complete and relaxed == 0, positions=len(signatures),
                solver_calls=calls, examined_paths=examined, unmatched_strict=strict,
                unmatched_relaxed=relaxed, max_residual_s=max_residual,
                min_distinct_image_class_gap_s=min_gap if signatures else None,
                missing_tasks=missing, unexpected_tasks=unexpected, status_not_ok=not_ok,
                production_trace_mismatches=trace_mismatches, paths_absent_at_some_node=absent,
                strict_unmatched_stations=failures, routes=routes)


def assess(args):
    started = time.monotonic()
    legacy = legacy_kernel(args.source)
    check_kernel(legacy)
    selection_path = args.selection / "SELECTION.json"
    g5 = read(args.g5)
    if g5["status"] != "PASS" or g5["gate"] != "G5":
        raise ValueError("G5 prerequisite missing")
    selection = read(selection_path)
    if set(selection) != set(CASES):
        raise ValueError("Incomplete G6 case selection")
    checks = {str(selection_path): sha(selection_path), str(args.g5): sha(args.g5)}
    g0, g7 = args.production / "g0", args.production / "g7"
    cases = {}
    for case in CASES:
        entry, _, _, tasks, *_ = case_inputs(g0, g7, case)
        details = selection[case]
        verify(args.selection / f"{case}.json", details["selector_sha256"])
        if set(details["routes"]) != set(ROUTES):
            raise ValueError(f"Missing G6 route: {case}")
        cases[case] = assess_case(case, entry, tasks, details, args.traces, g0 / "scene", legacy, checks)
    counts = {key: sum(row[key] for row in cases.values()) for key in (
        "positions", "solver_calls", "examined_paths", "unmatched_strict", "unmatched_relaxed",
        "paths_absent_at_some_node")}
    status = ("INCOMPLETE" if not all(c["complete"] for c in cases.values())
              else "PASS" if all(c["passed_strict"] for c in cases.values()) else "FAIL")
    result = dict(status=status, question_id="G1-RT-TB3-001", gate="G6", role="IMPLEMENTER",
                  metric="Method B multiset changes and unmatched image-delay classes",
                  code_base_commit=args.code_commit, matcher_sha256=sha(Path(__file__)),
                  legacy_sha256=LEGACY, strict_tolerance_s=legacy.tol, relaxed_tolerance_s=RELAXED_TOL_S,
                  image_class_tie_s=legacy.tie_s, image_kernel_check="PASS",
                  case_count=len(cases), route_count=len(cases)*len(ROUTES), totals=counts,
                  max_residual_s=max(c["max_residual_s"] for c in cases.values()),
                  adjacent_pairs=sum(r["compared_adjacent_pairs"] for c in cases.values() for r in c["routes"].values()),
                  adjacent_set_changes=sum(r["set_change_count"] for c in cases.values() for r in c["routes"].values()),
                  finished_utc=datetime.now(timezone.utc).isoformat(), wall_s=time.monotonic()-started,
                  input_sha256=checks, cases=cases)
    write(args.out, result)
    print(f"G6 {status}: {counts}, max {result['max_residual_s']:.6g} s, "
          f"{result['adjacent_set_changes']}/{result['adjacent_pairs']} adjacent set changes, "
          f"{result['wall_s']:.3f} s assessment", flush=True)
    return {"PASS": 0, "FAIL": 2, "INCOMPLETE": 3}[status]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--production", type=Path, required=True)
    sub = parser.add_subparsers(dest="mode", required=True)
    plan = sub.add_parser("select")
    plan.add_argument("--out", type=Path, required=True)
    plan.add_argument("--source", type=Path, required=True)
    run = sub.add_parser("assess")
    for key in ("source", "selection", "traces", "g5", "out"):
        run.add_argument(f"--{key}", type=Path, required=True)
    run.add_argument("--code-commit", required=True)
    args = parser.parse_args()
    if args.mode == "select":
        check_kernel(legacy_kernel(args.source))
        select(args.production, args.out)
        return 0
    return assess(args)


if __name__ == "__main__":
    raise SystemExit(main())
