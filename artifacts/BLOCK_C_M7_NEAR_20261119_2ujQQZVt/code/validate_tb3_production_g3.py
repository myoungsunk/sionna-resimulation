"""Run RT v1.1 G3a/G3b/G3c on the prespecified diagnostic-arm XY sample."""
from __future__ import annotations

import argparse
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write
from run_tb3_production import CASES, case_inputs, frozen_settings, utc_now, verify
from tb3_diag_g3_plan import SAMPLE_POLICY, sample


ARMS = ("P-D", "P-E", "P-F")
N_BINS = 257
FROZEN_MODULES = (
    ("run_g3a", "g3a", "6bde953ce7aa2c989484d2509461f50b3f39b983f09a8d707164a92755179880"),
    ("run_g3c_trace", "g3c_trace", "83394ae2dce9999eabe6e4e730a87b51200b6665cd4f9149ed6730c02e9978e7"),
    ("run_g3c_evaluation", "g3c_evaluation", "f7fbf40b88d4ba94d29a2b27bce1feeaa5a625bdc14b38ea8604b9c9627b3712"),
    ("parity_gate", "parity", "6d015180eb56ea076e12880d2fc2d60361b6ba8bb0b8dac7cde5edbb5e887d45"),
)
PARITY_SOURCE_HASHES = {
    "src/qclean_uwb/features/fp_power.py": "6da23ff66372a106dfbea521cc176031169210fed226e38d7d2db55b21f7c86b",
    "results/DRIVE_SIM_20261007/S0/PREREG.json": "db28d1dd0dbb5a7c5695b0bb3ed630f5abaa10eb6c1eb48545c6b14c9a1a1d01",
}


def frozen_tools(args):
    modules = {}
    for name, attr, digest in FROZEN_MODULES:
        path = getattr(args, attr)
        verify(path, digest)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        modules[attr] = module
    modules["g3a"].self_check()
    modules["g3c_evaluation"].self_check()
    for name, digest in PARITY_SOURCE_HASHES.items():
        verify(args.source / name, digest)
    prereg = read(args.source / "results/DRIVE_SIM_20261007/S0/PREREG.json")
    thresholds = {key: info["value"] for key, info in
                  prereg["config"]["gates"]["G2p_B_node_interpolation"].items()}
    if (thresholds["abs_ds_max"], thresholds["fp_index_match_min"],
            thresholds["range_diff_max_m"]) != (0.002, 0.995, 0.002):
        raise ValueError("G3b thresholds differ from adopted RT v1.1")
    return modules, thresholds


def trace_all_bins(core, scene, solver, settings, frequencies, task, setup, path):
    rt, mi = core.rt, core.mi
    scene.receivers["rx"].position = mi.Point3f(*setup.robot_position(task["x"], task["y"]).tolist())
    tau, angles, events, objects, iso = [], [], [], [], []
    for fi, frequency in enumerate(frequencies):
        scene.frequency = float(frequency)
        result = solver(scene, **settings)
        delay = np.asarray(result.tau).ravel()
        n = len(delay)
        if not n:
            raise ValueError(f"No ray paths at {task['tag']}/{fi}")
        tau.append(delay)
        angles.append(np.stack([np.asarray(getattr(result, key)).ravel()
                                for key in ("theta_t", "phi_t", "theta_r", "phi_r")]))
        events.append(np.asarray(result.interactions).reshape(settings["max_depth"], n).T.copy())
        objects.append(np.asarray(result.objects).reshape(settings["max_depth"], n).T.copy())
        iso.append((np.asarray(result.a[0]) + 1j*np.asarray(result.a[1])).reshape(2, 2, n))
    offsets = np.array([0, *np.cumsum([len(arr) for arr in tau])])
    with path.open("xb") as stream:
        np.savez_compressed(stream, bin_offsets=offsets, node_bins=np.arange(N_BINS),
                            node_freq_hz=frequencies, task_id=task["task_id"], x=task["x"], y=task["y"],
                            tau=np.concatenate(tau), ang=np.concatenate(angles, axis=1),
                            interactions=np.concatenate(events), objects=np.concatenate(objects),
                            jones_iso=np.concatenate(iso, axis=2))
    return raw_record(core, offsets, np.concatenate(tau), np.concatenate(angles, axis=1),
                      np.concatenate(events), np.concatenate(objects), np.concatenate(iso, axis=2),
                      settings["max_depth"], path)


def raw_record(core, offsets, tau, angles, events, objects, iso, depth, path):
    rt = core.rt
    count = len(tau)
    if (offsets.shape != (N_BINS + 1,) or offsets[0] != 0 or offsets[-1] != count
            or not np.all(np.diff(offsets) > 0) or iso.shape != (2, 2, count)
            or angles.shape != (4, count) or events.shape != (count, depth)
            or events.shape != objects.shape or np.any(tau < 0)
            or np.any(events == rt.constants.InteractionType.REFRACTION)
            or not all(np.isfinite(arr).all() for arr in (tau, angles, iso))):
        raise ValueError(f"Invalid F1 raw data: {path}")
    tau, angles = tau.astype(float), angles.astype(float)
    directions = core.P.path_directions(*angles)
    if not np.isfinite(directions).all():
        raise ValueError(f"Nonfinite F1 directions: {path}")
    none = rt.constants.InteractionType.NONE
    return dict(tau=tau, iso=iso, angles=angles, directions=directions,
                chain=np.concatenate((events, np.where(events == none, 0, objects)), axis=1),
                energy=np.sum(iso.real.astype(float)**2 + iso.imag.astype(float)**2, axis=(0, 1)),
                sections=[slice(lo, hi) for lo, hi in zip(offsets[:-1], offsets[1:])])


def baseline_channel(core, parity, raw, banks, yaws):
    """Reproduce G3b's strict all-node coverage and G3c's baseline synthesis."""
    by_bin = {i: (raw["iso"][:, :, section], raw["tau"][section], raw["angles"][:, section])
              for i, section in enumerate(raw["sections"])}
    tau, angles, _, jones, _, present = core._assemble(by_bin, list(range(N_BINS)))
    counts = np.array([section.stop-section.start for section in raw["sections"]])
    if not np.array_equal(present.sum(axis=1), counts):
        raise ValueError("All-bin Method B baseline failed to retain every observed path")
    h = parity.h_for_antenna_yaws(
        dict(status="OK", jones=jones, tau=tau, ang=np.array(angles),
             node_freq_hz=banks[0].freqs_hz, present=present), banks, yaws)
    return h, bool(present.all())


def scene_runtime(core, scene_entry, anchor, scene_root):
    rt, mi = core.rt, core.mi
    anchor_xyz = scene_entry["anchors_xyz_m"][anchor]
    entry = scene_entry | {"anchors_xyz_m": {"A": anchor_xyz}}
    factory, loader = geometry_adapter(core, entry, scene_root)
    setup = factory(anchor_x_m=anchor_xyz[0])
    if not all(check["passed"] for check in setup.validate()):
        raise ValueError("Diagnostic G3 scene validation failed")
    scene, _ = loader(setup, None)
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0]*3))
    scene.add(rt.Receiver("rx", position=setup.robot_position(*setup.example_xy_m[0]).tolist(),
                          orientation=[0.0]*3))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(core.Ports([core.IsoPort(0), core.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))
    return scene, rt.PathSolver(), setup


def select_arms(values, selected):
    by_arm = {None: values}
    for arm in ARMS:
        indices = [i for i, task in enumerate(selected) if arm in task["arms"]]
        if indices:
            by_arm[arm] = [values[i] for i in indices]
    return by_arm


def evaluate_g3a(core, scene, solver, setup, settings, freq, selected, tools, out, timings):
    checks, outputs = [], []
    for task in selected:
        path = out / "raw" / f"{task['tag']}_100k.npz"
        tick = time.monotonic()
        raw = trace_all_bins(core, scene, solver, settings, freq, task, setup, path)
        timings["trace_s"] += time.monotonic() - tick
        outputs.append(path)
        ref = path_signature(raw, 0)
        mismatches, invalid = [], []
        for fi in range(N_BINS):
            missing, extra, ambiguous = tools["g3a"].match(*ref, *path_signature(raw, fi))
            if ambiguous:
                invalid.append(dict(bin=fi, reason="AMBIGUOUS_PATH_MATCH"))
            elif missing or extra:
                mismatches.append(dict(bin=fi, baseline_only=missing, bin_only=extra))
        checks.append(dict(tag=task["tag"], mismatches=mismatches, invalid=invalid))
        print(f"{task['tag']} G3a: {time.monotonic()-tick:.1f}s", flush=True)
    detail = out / "G3A_SIGNATURE_ROWS.json"
    write(detail, checks)
    outputs.append(detail)

    def summarize(rows):
        expected = N_BINS * len(rows)
        invalid = sum(len(row["invalid"]) for row in rows)
        mismatches = sum(len(row["mismatches"]) for row in rows)
        return dict(passed=invalid == mismatches == 0, positions=len(rows),
                    expected_bins=expected, compared_bins=expected-invalid,
                    invalid_bins=invalid, mismatched_bins=mismatches)

    return {arm: summarize(rows) for arm, rows in select_arms(checks, selected).items()}, outputs


def path_signature(raw, fi):
    return tuple(raw[key][raw["sections"][fi]] for key in ("tau", "directions", "chain"))


def load_baseline(core, path, freq, task, previous, settings):
    verify(path, previous["output_sha256"][path.relative_to(path.parent.parent).as_posix()])
    with np.load(path, allow_pickle=False) as saved:
        if (not np.array_equal(saved["node_bins"], np.arange(N_BINS))
                or not np.array_equal(saved["node_freq_hz"], freq)
                or (float(saved["x"]), float(saved["y"]), int(saved["task_id"])) !=
                    (task["x"], task["y"], task["task_id"])):
            raise ValueError(f"Unexpected 100k raw trace identity: {path}")
        return raw_record(core, saved["bin_offsets"], saved["tau"], saved["ang"],
                          saved["interactions"], saved["objects"], saved["jones_iso"],
                          settings["max_depth"], path)


def compare_energy(baseline, high, match):
    invalid, energy = [], []
    for fi in range(N_BINS):
        pair = match.match_matrix(*path_signature(baseline, fi), *path_signature(high, fi))
        try:
            added, removed, added_e, removed_e = match.energy_metrics(
                pair, baseline["energy"][baseline["sections"][fi]], high["energy"][high["sections"][fi]])
        except ValueError as exc:
            invalid.append(dict(bin=fi, reason=str(exc)))
            continue
        energy.append(dict(bin=fi, added_paths=added, removed_paths=removed,
                           added_energy=added_e, removed_energy=removed_e))
    return dict(invalid=invalid, energy=energy)


def evaluate_comparison(stage, core, scene, solver, setup, settings, freq, selected, tools, thresholds,
                        banks, out, previous, timings):
    from run_tb3_g8_pilot import capture_trace

    parity, g3c = tools["parity"], tools["g3c_evaluation"]
    outputs, all_rows, energy_results, unusable, solver_calls = [], [], [], [], 0
    nominal_nodes = core.node_bins(N_BINS, "17")
    for task in selected:
        tag = task["tag"]
        tick = time.monotonic()
        base = load_baseline(core, out / "raw" / f"{tag}_100k.npz", freq, task, previous, settings)
        timings["load_reference_s"] += time.monotonic() - tick
        unique_yaws = {p["pose_id"]: p["yaw_deg"] for selection in task["arms"].values()
                       for p in selection["sampled_yaws"]}
        pose_ids, yaws = list(unique_yaws), list(unique_yaws.values())

        tick = time.monotonic()
        if stage == "g3b":
            node, indices = capture_trace(core, scene, solver, settings, freq, nominal_nodes, task, setup)
            if not np.isin(nominal_nodes, indices).all() or np.any(np.diff(indices) <= 0):
                raise ValueError(f"Unexpected direct node coverage at {tag}")
            solver_calls += len(indices)
            path = out / "raw" / f"{tag}_17nodes.npz"
            with path.open("xb") as stream:
                np.savez_compressed(stream, **node, node_bins=indices)
        else:
            solver_calls += N_BINS
            path = out / "raw" / f"{tag}_400k.npz"
            high = trace_all_bins(core, scene, solver, settings | {"samples_per_src": 400_000},
                                  freq, task, setup, path)
        outputs.append(path)
        timings["trace_s"] += time.monotonic() - tick

        h_base, complete = baseline_channel(core, parity, base, banks, yaws)
        if stage == "g3b":
            if not complete:
                unusable.append(dict(tag=tag, reason="REFERENCE_METHOD_B_PATH_MATCH_INCOMPLETE"))
            candidate = parity.h_for_antenna_yaws(node, banks, yaws)
        else:
            energy_results.append(dict(tag=tag, **compare_energy(base, high, g3c)))
            candidate = g3c.channel_for_yaws(core, parity, high, banks, yaws)
        if not all(h.shape == (len(yaws), N_BINS, 2, 2) and np.isfinite(h).all()
                   for h in (h_base, candidate)):
            raise ValueError(f"Invalid Method B channel: {tag}")
        metrics = {}
        for pose_id, h, ref in zip(pose_ids, candidate, h_base, strict=True):
            row = parity.compare(h, ref, freq)
            if not np.isfinite([*row.values()]).all():
                raise ValueError(f"Nonfinite G3 parity measures: {tag}/{pose_id}")
            metrics[pose_id] = row
        all_rows.extend(dict(arm=arm, tag=tag, **pose, **metrics[pose["pose_id"]])
                        for arm, selection in task["arms"].items()
                        for pose in selection["sampled_yaws"])
        print(f"{tag} {stage}: {len(pose_ids)} yaws", flush=True)
    detail = out / f"{stage.upper()}_PARITY_ROWS.json"
    write(detail, all_rows)
    outputs.append(detail)
    if stage == "g3c":
        detail = out / "G3C_ENERGY_ROWS.json"
        write(detail, energy_results)
        outputs.append(detail)

    def summarize(arm):
        scope = {task["tag"] for task in selected if arm is None or arm in task["arms"]}
        raw_rows = [row for row in all_rows if arm is None or row["arm"] == arm]
        if len({(r["tag"], r["pose_id"]) for r in raw_rows}) != len(raw_rows):
            raise ValueError("A pose is duplicated across diagnostic arms in the comparison")
        expected = sum(len(entry["sampled_yaws"]) for task in selected
                       for name, entry in task["arms"].items() if arm is None or name == arm)
        if len(raw_rows) != expected:
            raise ValueError("Incomplete pose comparison accounting")
        metrics = dict(positions=len(scope), expected_comparisons=expected)
        if stage == "g3b":
            bad = [row for row in unusable if row["tag"] in scope]
            excluded = {row["tag"] for row in bad}
            used = [row for row in raw_rows if row["tag"] not in excluded]
            report = parity.summarize(used, thresholds, "G3b") if used else {"passed": False}
            report = parity.coverage_checked(report, [], bad)
            return metrics | report | dict(completed_comparisons=len(used))

        scoped = [row for row in energy_results if row["tag"] in scope]
        energy = [row for item in scoped for row in item["energy"]]
        invalid = sum(len(item["invalid"]) for item in scoped)
        expected_bins = N_BINS * len(scope)
        max_add = max((r["added_energy"] for r in energy), default=None)
        max_remove = max((r["removed_energy"] for r in energy), default=None)
        max_ds = max(r["abs_ds"] for r in raw_rows)
        passed = (invalid == 0 and len(energy) == expected_bins and max_add is not None
                  and max_add < g3c.ADDED_LIMIT and max_ds <= g3c.DS_LIMIT)
        return metrics | dict(passed=passed, completed_comparisons=len(raw_rows),
                              expected_bins=expected_bins, compared_bins=len(energy), invalid_bins=invalid,
                              max_added_energy_fraction=max_add, max_removed_energy_fraction=max_remove,
                              added_paths=sum(r["added_paths"] for r in energy),
                              removed_paths=sum(r["removed_paths"] for r in energy), abs_ds_max=max_ds,
                              thresholds=dict(added_energy_fraction_lt=g3c.ADDED_LIMIT, abs_ds_max=g3c.DS_LIMIT))

    timings["solver_calls"] = solver_calls
    present = {arm for task in selected for arm in task["arms"]}
    return {arm: summarize(arm) for arm in (None, *(a for a in ARMS if a in present))}, outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for path in ("inputs", "g7", "source", "production", "reference", "ffd-manifest", "out",
                 "g3a", "g3c-trace", "g3c-evaluation", "parity"):
        parser.add_argument("--" + path, type=Path, required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--stage", choices=("plan", "g3a", "g3b", "g3c"), required=True)
    parser.add_argument("--task-id", type=int)
    args = parser.parse_args()
    if args.stage == "plan" and args.task_id is not None:
        parser.error("--task-id is only used in trace stages")
    started, started_utc = time.monotonic(), utc_now()
    scene_entry, anchor, poses, tasks, _, diagnostic, _ = case_inputs(args.inputs, args.g7, args.case)
    selected = sample(poses, tasks, diagnostic, args.case)
    expected_arms = {"P-F"} if args.case.endswith("_P-F") else ({"P-D", "P-E"} if args.case.startswith("G-T1_") else {"P-E"})
    present_arms = {arm for task in selected for arm in task["arms"]}
    if present_arms != expected_arms:
        raise ValueError(f"Unexpected diagnostic arms for {args.case}: {sorted(present_arms)}")
    sample_plan = args.out / "SAMPLE_PLAN.json"
    plan = dict(question_id="G1-RT-TB3-002", case=args.case,
                policy=SAMPLE_POLICY,
                positions=len(selected), arm_positions=sum(len(t["arms"]) for t in selected), tasks=selected)
    if args.stage == "plan":
        args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
        write(sample_plan, plan | {"frozen_utc": utc_now()})
        return 0
    saved_plan = read(sample_plan)
    if any(saved_plan[key] != value for key, value in plan.items()):
        raise ValueError(f"Sample plan differs from frozen input: {sample_plan}")
    selected = saved_plan["tasks"]
    out = args.out
    if args.task_id is not None:
        selected = [task for task in selected if task["task_id"] == args.task_id]
        if len(selected) != 1:
            raise ValueError(f"{args.task_id} is not in the sample plan for {args.case}")
        out = args.out / "tasks" / str(args.task_id)

    production, reference = frozen_settings(args)
    settings = production["solver"]
    core, _, versions = load_runtime(args.source)
    tools, thresholds = frozen_tools(args)
    if tools["g3c_evaluation"].ADDED_LIMIT != 0.01 or tools["g3c_evaluation"].DS_LIMIT != 0.002:
        raise ValueError("Frozen G3c thresholds differ from adopted RT v1.1")
    banks = tools["parity"].load_banks()
    freq = banks[0].freqs_hz
    if len(freq) != N_BINS:
        raise ValueError("Unexpected diagnostic G3 frequency grid")
    scene, solver, setup = scene_runtime(core, scene_entry, anchor, args.inputs / "scene")
    shape_ids = {name: int(obj.object_id) for name, obj in scene.objects.items()}
    raw_dir = out / "raw"
    target = out / f"{args.stage.upper()}.json"
    if target.exists():
        raise FileExistsError(target)
    inputs = {"sample_plan": sha(sample_plan), "production": sha(args.production), "reference": sha(args.reference),
              "ffd_manifest": sha(args.ffd_manifest), "g0_manifest": sha(args.inputs / "RUN_MANIFEST.json"),
              "g7_manifest": sha(args.g7 / "RUN_MANIFEST.json")}
    timings = dict(trace_s=0.0, load_reference_s=0.0, solver_calls=N_BINS * len(selected))
    if args.stage == "g3a":
        raw_dir.mkdir(parents=True, mode=0o700)
        reports, outputs = evaluate_g3a(core, scene, solver, setup, settings, freq, selected, tools, out, timings)
    else:
        g3a_path = out / "G3A.json"
        previous = read(g3a_path)
        if (previous["stage"], previous["case"], previous["task_id"], previous["solver_100k"],
                previous["shape_ids"], previous["positions"], previous["input_sha256"]) != (
                "G3a", args.case, args.task_id, settings, shape_ids, len(selected), inputs):
            raise ValueError(f"Unexpected prior trace receipt: {g3a_path}")
        inputs["g3a_receipt"] = sha(g3a_path)
        reports, outputs = evaluate_comparison(args.stage, core, scene, solver, setup, settings, freq,
                                              selected, tools, thresholds, banks, out, previous, timings)
    status = "PASS" if all(report["passed"] for report in reports.values()) else "FAIL"
    wall_s = time.monotonic()-started
    write(target, dict(
        status=status, case=args.case, task_id=args.task_id, role="IMPLEMENTER",
        stage="G3" + args.stage[-1], question_id="G1-RT-TB3-002",
        positions=len(selected), pooled=reports.pop(None), arms=reports,
        solver_100k=settings,
        solver_400k=settings | {"samples_per_src": 400_000} if args.stage == "g3c" else None,
        shape_ids=shape_ids, timings=timings, code_commit=args.code_commit, governance=reference["governance"],
        runtime_versions=versions, started_utc=started_utc, finished_utc=utc_now(), wall_s=wall_s,
        command=[sys.executable, *sys.argv],
        source_sha256={name: digest for name, _, digest in FROZEN_MODULES}
        | {name: sha(Path(__file__).with_name(name)) for name in (
            "validate_tb3_production_g3.py", "tb3_diag_g3_plan.py", "run_tb3_g1_pilot.py",
            "run_tb3_production.py", "run_tb3_g8_pilot.py")},
        input_sha256=inputs, output_sha256={p.relative_to(out).as_posix(): sha(p) for p in outputs},
    ))
    print(f"{args.case}/{args.task_id} {args.stage} {status}, {wall_s:.1f}s", flush=True)
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
