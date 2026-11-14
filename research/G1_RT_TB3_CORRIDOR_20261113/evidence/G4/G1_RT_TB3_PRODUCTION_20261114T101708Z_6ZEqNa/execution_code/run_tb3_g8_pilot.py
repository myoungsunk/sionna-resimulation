"""Generate F1 H and near-delay exports from one set of Method B solver calls."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import geometry_adapter, load_runtime, prepare, read, sha, write
from tb3_native_los import native_direct_coefficients
from tb3_paths_near import check_g8, h_and_near_for_poses, write_paths_near


LEGACY_PILOT_SHA = {
    "G1.json": "2509998f914323cb244e86539c665d46349e79e023410e004ff5dd65cb0f7583",
    "H_LoS.npy": "c35abb947e396b9bbc14456c2eac4bd03b56b37d8d5a952f9babc7dd9f2c2ce8",
    "rf_poses.json": "f7c93997d1a64fa124014c28de53ad2f2473374dfcfce7b59b517808d2bdc07b",
    "PATHS_LoS.npz": "f4f26e56a588684602c72f3bc96ee899274e000c188a7909a552df6c8b1db634",
}


def require_sha(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Input digest mismatch: {path}")


def capture_trace(core, scene, solver, config, frequencies, bins, task, setup):
    """Call the frozen tracer and capture interactions/objects alongside its ISO Jones."""
    original = core._solve
    depth = config["max_depth"]
    captured = {}

    def solve(scene, solver, config, frequencies, bin_index):
        scene.frequency = float(frequencies[bin_index])
        result = solver(scene, **config)
        iso = (np.asarray(result.a[0]) + 1j*np.asarray(result.a[1])).reshape(2, 2, -1)
        tau = np.asarray(result.tau).ravel().astype(np.float64)
        ang = [np.asarray(getattr(result, name)).ravel().astype(np.float64)
               for name in ("theta_t", "phi_t", "theta_r", "phi_r")]
        events = np.asarray(result.interactions).reshape(depth, len(tau)).T.copy()
        objects = np.asarray(result.objects).reshape(depth, len(tau)).T.copy()
        if bin_index in captured:
            raise ValueError(f"Unexpected second solve at bin {bin_index}")
        captured[bin_index] = tau, ang, events, objects
        return iso, tau, ang

    core._solve = solve
    try:
        jones, (tau, angles), status, counts, details = core.trace_position(
            scene, solver, config, frequencies, bins, task["x"], task["y"], setup)
    finally:
        core._solve = original
    if status != "OK":
        raise ValueError(f"{task['tag']}: {status}")
    node_ids = np.array(details["nodes"])
    if set(captured) != set(node_ids.tolist()):
        raise ValueError("Solver capture and Method B nodes differ")

    # Use the identical Method B geometric assignment. Refuse metadata that
    # would give one canonical Jones path two different interaction sequences.
    reference_dirs = core.P.path_directions(*angles)
    seen = np.zeros(len(tau), dtype=bool)
    none = core.rt.constants.InteractionType.NONE
    interactions = np.empty((len(tau), depth), dtype=np.int64)
    objects = np.empty_like(interactions)
    for i, node in enumerate(node_ids):
        raw_tau, raw_ang, raw_events, raw_objects = captured[node]
        index, extra = core.P.match_partial(tau, reference_dirs, raw_tau,
                                           core.P.path_directions(*raw_ang), tol=core.ANGLE_TOL_RAD)
        present = index >= 0
        if len(extra) or not np.array_equal(present, details["present"][i]) or present.sum() != counts[i]:
            raise ValueError(f"Unaligned path metadata at {task['tag']}/{node}")
        active = raw_events[index[present]].astype(np.int64)
        object_ids = np.where(active == none, -1, raw_objects[index[present]]).astype(np.int64)
        already = seen[present]
        if (not np.array_equal(interactions[present][already], active[already])
                or not np.array_equal(objects[present][already], object_ids[already])):
            raise ValueError(f"Conflicting metadata at {task['tag']}/{node}")
        interactions[present] = active
        objects[present] = object_ids
        seen |= present
    if not seen.all():
        raise ValueError("Canonical path is absent in every node")
    return dict(status=status, jones=jones, tau=tau, ang=np.array(angles), present=details["present"],
                node_freq_hz=frequencies[node_ids], interactions=interactions, objects=objects), node_ids


def generate_case(core, scene_entry, scene_root, poses, tasks, production, out, export_pose_ids, case_id,
                  *, native_direct=False):
    """Generate one case; the caller supplies the approved pose table and export IDs."""
    from qclean_uwb.drivesim.rf_store import h_for_antenna_yaws, load_banks

    pose_ids = [p["pose_id"] for p in poses]
    if (len(set(pose_ids)) != len(pose_ids) or not export_pose_ids
            or not export_pose_ids <= set(pose_ids)):
        raise ValueError("Invalid pose index or PATHS_NEAR scope")
    if sorted(i for task in tasks for i in task["pose_ids"]) != sorted(pose_ids):
        raise ValueError("Expected exactly one trace task for each physical pose")
    by_id = {p["pose_id"]: (i, p) for i, p in enumerate(poses)}
    anchor = scene_entry["anchors_xyz_m"]["A"]
    factory, loader = geometry_adapter(core, scene_entry, scene_root)
    setup = factory(anchor_x_m=anchor[0])
    if not all(x["passed"] for x in setup.validate()):
        raise ValueError("Invalid F1 corridor")
    scene, _ = loader(setup, None)
    rt, mi = core.rt, core.mi
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0]*3))
    scene.add(rt.Receiver("rx", position=setup.robot_position(*setup.example_xy_m[0]).tolist(),
                          orientation=[0.0]*3))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(core.Ports([core.IsoPort(0), core.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))
    solver = rt.PathSolver()
    banks = load_banks()
    freq = banks[0].freqs_hz
    native_banks = core.C.load_banks()
    if (len(freq) != production["channel_bins"]
            or not np.array_equal(freq, native_banks[0]["freqs_hz"])):
        raise ValueError("Inconsistent frozen frequency grid")
    ports = core.C.make_ports(native_banks) if native_direct else None
    bins = core.node_bins(len(freq), str(production["base_nodes"]))
    config = production["solver"]
    mount = production["mount_deg"]
    none = rt.constants.InteractionType.NONE
    object_ids = {int(obj.object_id): name for name, obj in scene.objects.items()}
    interaction_codes = {name: int(getattr(rt.constants.InteractionType, name))
                         for name in ("NONE", "SPECULAR", "DIFFUSE", "REFRACTION", "DIFFRACTION")
                         if hasattr(rt.constants.InteractionType, name)}
    h_full = np.empty((len(poses), len(freq), 2, 2), dtype=np.complex128)
    h_los_from_full_trace = np.empty_like(h_full)
    packs = []
    receipts = []
    peak_difference = 0.0
    for task in tasks:
        started = time.monotonic()
        trace, node_ids = capture_trace(core, scene, solver, config, freq, bins, task, setup)
        rows, task_poses = zip(*(by_id[i] for i in task["pose_ids"]), strict=True)
        yaws = [p["yaw_body_deg"] + mount for p in task_poses]
        chosen = [i for i, p in enumerate(task_poses) if p["pose_id"] in export_pose_ids]
        normal_h = h_for_antenna_yaws(trace, banks, yaws)
        # Extract the same recorded direct path through the frozen channel
        # synthesis independently of the PATHS_NEAR coefficient serializer.
        direct = np.flatnonzero((trace["interactions"] == none).all(axis=1))
        if len(direct) != 1 or not trace["present"][:, direct].all():
            raise ValueError(f"Expected exactly one LoS path at every node at {task['tag']}")
        los_trace = trace | dict(tau=trace["tau"][direct], ang=trace["ang"][:, direct],
                                 jones=trace["jones"][:, direct], present=trace["present"][:, direct])
        original_los = h_for_antenna_yaws(los_trace, banks, yaws)
        direct_los = original_los
        coefficients = None
        if native_direct:
            # The F1 trace must already contain exactly one direct path.
            tx = np.asarray(scene.transmitters["tx"].position).reshape(3)
            rx = np.asarray(scene.receivers["rx"].position).reshape(3)
            coefficients, native_delay = native_direct_coefficients(
                core, tx, rx, task_poses, mount, native_banks, ports)
            if abs(native_delay - trace["tau"][direct[0]]) > 2e-13:
                raise ValueError(f"Native endpoint delay and traced LoS disagree at {task['tag']}")
            phase = np.exp(-2j * np.pi * freq * trace["tau"][direct[0]])
            direct_los = coefficients * phase[None, :, None, None]
        full, near = h_and_near_for_poses(
            trace, banks, task_poses, mount_deg=mount, none_event=none,
            export_pose_ids={task_poses[i]["pose_id"] for i in chosen},
            direct_coefficients=coefficients,
        )
        if chosen:
            packs.append(near)
        expected_h = normal_h if coefficients is None else normal_h + (direct_los - original_los)
        peak_difference = max(peak_difference, float(np.max(np.abs(full - expected_h))))
        synthesis_ok = np.array_equal(full, expected_h) if coefficients is None else np.allclose(
            full, expected_h, rtol=0.0, atol=1e-15,
        )
        if not synthesis_ok:
            raise ValueError(f"H differs outside the expected direct contribution at {task['tag']}")
        h_full[list(rows)] = full
        h_los_from_full_trace[list(rows)] = direct_los
        receipts.append(dict(tag=task["tag"], task_id=task["task_id"], pose_ids=task["pose_ids"],
                             node_bins=node_ids.tolist(), solver_calls=len(node_ids),
                             n_full_paths=len(trace["tau"]), wall_s=time.monotonic()-started))
        print(f"{task['tag']} {len(node_ids)} solver calls, {len(task_poses)} poses", flush=True)
    if not np.isfinite(h_full).all() or not np.isfinite(h_los_from_full_trace).all():
        raise ValueError("Nonfinite generated channel")

    path_file = write_paths_near(out / "paths" / case_id, packs, freq, interaction_codes,
                                 object_ids=object_ids, native_direct=native_direct)
    np.save(out / "H_full.npy", h_full)
    np.save(out / "H_LoS_from_full_trace.npy", h_los_from_full_trace)
    write(out / "TRACE_RECEIPTS.json", receipts)
    return path_file, receipts, peak_difference


def main():
    parser = argparse.ArgumentParser(description="G8 pilot on the frozen G1 G-T1/A sample")
    for flag in ("inputs", "source", "out", "legacy-output", "production"):
        parser.add_argument("--" + flag, type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--diagnostic-spec-sha", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--native-direct-revalidation", dest="native_direct", action="store_true",
                      help="explicitly select the adopted G8 reference and direct-field computation")
    mode.add_argument("--legacy-g8", dest="native_direct", action="store_false",
                      help="reproduce the historical G8 calculation with the uncorrected G1 reference")
    parser.set_defaults(native_direct=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    args.out.mkdir()
    entry, poses, tasks, selected, gate, reference = prepare(args.inputs, args.out, args.source)
    prod = read(args.production)
    if (prod["status"] != "ADOPTED" or prod["solver"] != reference["block_c_solver"] | {"refraction": False}
            or prod["image"] != reference["image"] or prod["method_b_commit"] != reference["method_b_commit"]
            or (prod["base_nodes"], prod["channel_bins"], prod["mount_deg"]) != (17, 257, 0)):
        raise ValueError("Production F1 does not match validated RT v1.1")
    for file, digest in LEGACY_PILOT_SHA.items():
        require_sha(args.legacy_output / file, digest)
    require_sha(args.out / "rf_poses.json", LEGACY_PILOT_SHA["rf_poses.json"])
    original = read(args.legacy_output / "G1.json")
    if original["status"] != "PASS" or original["scope"]["poses"] != len(poses):
        raise ValueError("Invalid frozen G1 pilot LoS reference")
    for file, digest in original["input_sha256"].items():
        require_sha(args.inputs / file, digest)
    if len(poses) != 332 or len(tasks) != 6:
        raise ValueError("Unexpected G8 pilot scope")
    trace, _, versions = load_runtime(args.source)
    native_direct = args.native_direct
    near_path, receipts, peak = generate_case(
        trace, entry, args.inputs / "scene", poses, tasks, prod, args.out,
        {p["pose_id"] for p in poses}, "G-T1_A", native_direct=native_direct,
    )
    ids = [p["pose_id"] for p in poses]
    legacy_h_los = np.load(args.legacy_output / "H_LoS.npy", allow_pickle=False)
    np.save(args.out / "H_LoS_original_g1.npy", legacy_h_los)
    h_los_reference = legacy_h_los
    if native_direct:
        # Repair the numerical phase evaluation of the independent G1 LoS.
        # Its 257-bin native coefficients, delays, poses and geometry are frozen.
        with np.load(args.legacy_output / "PATHS_LoS.npz", allow_pickle=False) as legacy_paths:
            coeff, tau, freq = (legacy_paths[k] for k in ("a", "tau", "freqs_hz"))
        with np.load(near_path, allow_pickle=False) as near:
            if not np.array_equal(freq, near["frequencies_hz"]):
                raise ValueError("Frequency grid differs from frozen native G1 LoS")
        if (coeff.shape != legacy_h_los.shape or tau.shape != coeff.shape[:2]
                or coeff.dtype != np.complex128 or tau.dtype != np.float64):
            raise ValueError("Frozen native paths have unexpected dimensions or precision")
        h_los_reference = coeff * np.exp(-2j * np.pi * freq[None, :] * tau)[..., None, None]
    np.save(args.out / "H_LoS.npy", h_los_reference)
    same = check_g8(near_path, np.load(args.out / "H_LoS_from_full_trace.npy", allow_pickle=False), ids)
    gate = check_g8(near_path, np.load(args.out / "H_LoS.npy", allow_pickle=False), ids)
    status = "PASS" if same["status"] == gate["status"] == "PASS" else "FAIL"
    result = dict(question_id="G1-RT-TB3-002", stage="G8", scope="PILOT_ONLY", status=status,
                  geometry="G-T1", anchor="A", stations=["P001", "P002", "P003"],
                  observations=len(selected), trace_positions=len(tasks), poses=len(poses),
                  solver_calls=sum(r["solver_calls"] for r in receipts), extra_export_solves=0,
                  max_abs_H_difference_beyond_intended_direct_term=peak,
                  independent_g1_h_los_check=gate,
                  original_g1_h_los_check=check_g8(near_path, legacy_h_los, ids),
                  phase_repair="float64 frequency and delay" if native_direct else "none",
                  direct_coefficient_method="native field on F1 segment" if native_direct else "Method B Jones",
                  same_trace_h_los_check=same, near_export_bytes=near_path.stat().st_size,
                  wall_s=time.monotonic()-t0)
    write(args.out / "G8.json", result)
    write(args.out / "RUN_MANIFEST.json", dict(
        question_id=result["question_id"], stage="G8", role="IMPLEMENTER",
        scope=result["scope"], status=status, host="Snowball KMS", code_commit=args.code_commit,
        governance=read(args.inputs / "RUN_MANIFEST.json")["governance"],
        diagnostic_spec_sha256=args.diagnostic_spec_sha, production_sha256=sha(args.production),
        production=prod, runtime_versions=versions, legacy_pilot_sha256=LEGACY_PILOT_SHA,
        source_sha256=reference["method_b_sha256"], g0_manifest_sha256=sha(args.inputs / "RUN_MANIFEST.json"),
        input_sha256=original["input_sha256"],
        driver_sha256=sha(Path(__file__)), helper_sha256=sha(Path(__file__).with_name("tb3_paths_near.py")),
        direct_helper_sha256=sha(Path(__file__).with_name("tb3_native_los.py")),
        started_utc=started.isoformat(), finished_utc=datetime.now(timezone.utc).isoformat(),
        command=[sys.executable, *sys.argv],
        output_sha256={p.relative_to(args.out).as_posix(): sha(p) for p in sorted(args.out.rglob("*")) if p.is_file()}))
    print(f"G8 pilot {status}", flush=True)
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
