"""Generate one F1 production shard using the G0/G7 pose and scene tables."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

import numpy as np

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write


G0_SHA = "48ebdcdde68f3d62ec1b00c3061440f9363313ef35577f409eb5b5c0b75c13b6"
G7_SHA = "a1542122461b919f55ad2ce43314ba0a3732e0611a574fd51fa692e6b03e9830"
REFERENCE_SHA = "1f0b9082a8b5fbf8aa43ebdb585808f3b288b49efe2db25dd56944e471199252"
FFD_SHA = "0017f2171da5d3729e4ad91d0d44384937d83213640c347ff12dda53e763a96e"
F1_SHA = "fcd3ee9448640bcd29e0f031d06243a7cd5d8c6d7f80b1db49485ed7904017d8"
GEOMETRIES = ("G-T1", "G-T2", "G-V")
ANCHORS = ("A", "B", "C")
CASES = tuple(f"{g}_{a}" for g in GEOMETRIES for a in ANCHORS) + ("G-T1_A_P-F", "G-T1_B_P-F")
NEAR_SETS = {"P-A_TEACH", "P-A_REPEAT", "P-D", "P-E", "P-F"}
POSE_FILES = ("rf_poses.json", "rf_tasks.json", "SAMPLES.json", "TIMELINE.csv")
FIELD_BATCH_XY = 64


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def verify(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Frozen input digest mismatch: {path}")


def case_inputs(g0, g7, case):
    """Load the exact validated case, retaining baseline RF IDs."""
    if case not in CASES:
        raise ValueError(f"Unknown production case: {case}")
    geometry, anchor, *arm = case.split("_")
    verify(g0 / "RUN_MANIFEST.json", G0_SHA)
    verify(g7 / "RUN_MANIFEST.json", G7_SHA)
    g0_hashes = read(g0 / "RUN_MANIFEST.json")["output_sha256"]
    g7_hashes = read(g7 / "RUN_MANIFEST.json")["output_sha256"]
    for folder, names, hashes, root in (
        (f"poses/{geometry}_{anchor}", POSE_FILES, g0_hashes, g0),
        (f"poses/{case}", (*POSE_FILES, "SCENE_ENTRY.json"), g7_hashes, g7),
    ):
        for name in names:
            rel = f"{folder}/{name}"
            verify(root / rel, hashes[rel])
    for root, name, hashes in ((g0, "gates/G0.json", g0_hashes), (g7, "G7.json", g7_hashes)):
        verify(root / name, hashes[name])
        gate = read(root / name)
        if gate["status"] != "PASS" or gate["violation_count"]:
            raise ValueError(f"Input gate {name} did not pass")
    verify(g0 / "scene/SCENE_MANIFEST.json", g0_hashes["scene/SCENE_MANIFEST.json"])
    base_scene = read(g0 / "scene/SCENE_MANIFEST.json")["geometries"][geometry]
    for item in base_scene["material_bindings"]:
        verify(g0 / "scene" / item["ply"], item["ply_sha256"])
    baseline = g0 / "poses" / f"{geometry}_{anchor}"
    diagnostic = g7 / "poses" / case
    scene = read(diagnostic / "SCENE_ENTRY.json")
    px, py, pz = base_scene["anchors_xyz_m"][anchor]
    target = [px, py, 2.4 if arm else pz]
    if scene != (base_scene | {"anchors_xyz_m": base_scene["anchors_xyz_m"] | {anchor: target}}):
        raise ValueError(f"G7 changed the scene outside the approved geometry and anchor: {case}")
    poses = read(diagnostic / "rf_poses.json")
    tasks = read(diagnostic / "rf_tasks.json")
    base_poses = [] if arm else read(baseline / "rf_poses.json")
    base_rows = [] if arm else read(baseline / "SAMPLES.json")
    diagnostic_rows = read(diagnostic / "SAMPLES.json")
    if (poses[:len(base_poses)] != base_poses
            or [p["pose_id"] for p in poses] != list(range(len(poses)))
            or [t["task_id"] for t in tasks] != list(range(len(tasks)))
            or Counter(i for t in tasks for i in t["pose_ids"]) != Counter(range(len(poses)))):
        raise ValueError(f"G7 task partition or G0 pose prefix differs: {case}")
    if any(not 0 <= row["pose_id"] < len(poses) for row in base_rows + diagnostic_rows):
        raise ValueError(f"Observation references a nonexistent RF pose: {case}")
    return scene, anchor, poses, tasks, base_rows, diagnostic_rows, len(base_poses)


def frozen_settings(args):
    for path, digest in ((args.production, F1_SHA), (args.reference, REFERENCE_SHA),
                         (args.ffd_manifest, FFD_SHA)):
        verify(path, digest)
    production, reference = read(args.production), read(args.reference)
    for name, digest in reference["method_b_sha256"].items():
        verify(args.source / name, digest)
    for bank in read(args.ffd_manifest)["banks"]:
        verify(args.source / bank["filename"], bank["sha256"])
    if (production["status"] != "ADOPTED"
            or production["solver"] != (reference["block_c_solver"] | {"refraction": False})
            or read(args.source / reference["solver_path"])["solver"] != reference["block_c_solver"]
            or (production["base_nodes"], production["channel_bins"], production["mount_deg"]) != (17, 257, 0)):
        raise ValueError("Invalid adopted F1 configuration")
    return production, reference


def canary_selection(g1, base_rows, tasks):
    from run_tb3_g8_pilot import LEGACY_PILOT_SHA

    for name in ("PATHS_LoS.npz", "rf_poses.json"):
        verify(g1 / name, LEGACY_PILOT_SHA[name])
    rows = [row for row in base_rows if row["set"] in NEAR_SETS
            and row["station_id"] in {"P001", "P002", "P003"}]
    ids = sorted({row["pose_id"] for row in rows})
    if ids != [p["g0_pose_id"] for p in read(g1 / "rf_poses.json")]:
        raise ValueError("Canary pose set does not match the frozen G1 G8 inputs")
    selected = []
    for task in tasks:
        overlap = sorted(set(ids).intersection(task["pose_ids"]))
        if overlap:
            selected.append(task | {"pose_ids": overlap})
    if (len(ids), len(selected)) != (332, 6):
        raise ValueError("Canary scope changed")
    return selected, set(ids)


def check_canary(g1, path_los):
    with np.load(g1 / "PATHS_LoS.npz", allow_pickle=False) as expected:
        with np.load(path_los, allow_pickle=False) as actual:
            for key in ("a", "tau", "freqs_hz"):
                if actual[key].dtype != expected[key].dtype or not np.array_equal(actual[key], expected[key]):
                    error = float(np.max(np.abs(actual[key] - expected[key])))
                    raise ValueError(f"Batched native G8 canary differs on {key}: max abs {error}")


def generate_shard(core, scene_entry, anchor_id, scene_root, poses, tasks, near_ids, production, out):
    from qclean_uwb.drivesim.rf_store import load_banks
    from run_tb3_g8_pilot import capture_trace
    from tb3_native_los import native_direct_fields
    from tb3_paths_near import h_and_near_for_poses, write_paths_near

    solver_config = production["solver"]
    mount = production["mount_deg"]
    anchor = scene_entry["anchors_xyz_m"][anchor_id]
    adapter_entry = scene_entry | {"anchors_xyz_m": {"A": anchor}}
    factory, loader = geometry_adapter(core, adapter_entry, scene_root)
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
    banks = load_banks()
    native_banks = core.C.load_banks()
    freq = banks[0].freqs_hz
    if len(freq) != production["channel_bins"] or not np.array_equal(freq, native_banks[0]["freqs_hz"]):
        raise ValueError("Inconsistent frozen frequency grid")
    ports = core.C.make_ports(native_banks)
    bins = core.node_bins(len(freq), str(production["base_nodes"]))
    none = rt.constants.InteractionType.NONE
    object_ids = {int(obj.object_id): name for name, obj in scene.objects.items()}
    interaction_codes = {name: int(getattr(rt.constants.InteractionType, name))
                         for name in ("NONE", "SPECULAR", "DIFFUSE", "REFRACTION", "DIFFRACTION")
                         if hasattr(rt.constants.InteractionType, name)}
    ids = sorted(i for task in tasks for i in task["pose_ids"])
    by_id = {pose_id: row for row, pose_id in enumerate(ids)}
    batch_arrays = (len(ids), len(freq), 2, 2)
    h_full, h_los, los_coeff = (np.empty(batch_arrays, np.complex128) for _ in range(3))
    los_tau = np.empty(len(ids), np.float64)
    los_angles = np.empty((len(ids), 4), np.float64)
    tx = np.asarray(scene.transmitters["tx"].position).reshape(3)
    packs, receipts = [], []
    timings = dict(trace_s=0.0, native_field_s=0.0, apply_s=0.0, save_s=0.0)
    for offset in range(0, len(tasks), FIELD_BATCH_XY):
        batch = []
        batch_poses, receiver_positions = [], []
        for task in tasks[offset:offset+FIELD_BATCH_XY]:
            started = time.monotonic()
            trace, nodes = capture_trace(core, scene, solver, solver_config, freq, bins, task, setup)
            elapsed = time.monotonic() - started
            timings["trace_s"] += elapsed
            direct = np.flatnonzero((trace["interactions"] == none).all(axis=1))
            if len(direct) != 1 or not trace["present"][:, direct].all():
                raise ValueError(f"Expected exactly one traced LoS at every F1 node: {task['tag']}")
            task_poses = [poses[i] for i in task["pose_ids"]]
            start = len(batch_poses)
            batch_poses.extend(task_poses)
            receiver = np.asarray(scene.receivers["rx"].position).reshape(3)
            receiver_positions.extend([receiver] * len(task_poses))
            batch.append((task, trace, int(direct[0]), slice(start, len(batch_poses))))
            receipts.append(dict(tag=task["tag"], task_id=task["task_id"], pose_ids=task["pose_ids"],
                                 node_bins=nodes.tolist(), solver_calls=len(nodes),
                                 n_full_paths=len(trace["tau"]), n_near_paths=None, trace_s=elapsed))

        started = time.monotonic()
        coefficients, delays = native_direct_fields(
            core, tx, receiver_positions, batch_poses, mount, native_banks, ports)
        timings["native_field_s"] += time.monotonic() - started
        started = time.monotonic()
        for (task, trace, direct, section), receipt in zip(batch, receipts[offset:], strict=True):
            delay = trace["tau"][direct]
            if np.max(np.abs(delays[section] - delay)) > 2e-13:
                raise ValueError(f"Native endpoint delay differs from the F1 direct path: {task['tag']}")
            rows = [by_id[i] for i in task["pose_ids"]]
            selected = near_ids.intersection(task["pose_ids"])
            coeff = coefficients[section]
            full, near = h_and_near_for_poses(
                trace, banks, batch_poses[section], mount_deg=mount, none_event=none,
                export_pose_ids=selected, direct_coefficients=coeff)
            h_full[rows] = full
            h_los[rows] = coeff * np.exp(-2j * np.pi * freq * delay)[None, :, None, None]
            los_coeff[rows] = coeff
            los_tau[rows] = delay
            los_angles[rows] = trace["ang"][:, direct]
            if selected:
                packs.append(near)
                receipt["n_near_paths"] = len(near["pose_id"]) // len(selected)
        timings["apply_s"] += time.monotonic() - started
        print(f"{min(offset + FIELD_BATCH_XY, len(tasks))}/{len(tasks)} F1 XY positions", flush=True)

    started = time.monotonic()
    if not np.isfinite(h_full).all() or not np.isfinite(h_los).all():
        raise ValueError("Nonfinite production channel")
    np.save(out / "POSE_IDS.npy", np.array(ids, dtype=np.int64))
    np.save(out / "H_full.npy", h_full)
    np.save(out / "H_LoS.npy", h_los)
    los_shape = (len(ids), len(freq))
    np.savez_compressed(out / "PATHS_LoS.npz", pose_id=np.array(ids, dtype=np.int64),
                        a=los_coeff, tau=np.broadcast_to(los_tau[:, None], los_shape),
                        counts=np.ones(los_shape, dtype=np.int64),
                        interactions=np.zeros(los_shape, dtype=np.int64), freqs_hz=freq,
                        **{name: np.broadcast_to(los_angles[:, i, None], los_shape)
                           for i, name in enumerate(("theta_t", "phi_t", "theta_r", "phi_r"))})
    if packs:
        write_paths_near(out, packs, freq, interaction_codes, object_ids=object_ids, native_direct=True)
    write(out / "TRACE_RECEIPTS.json", receipts)
    timings["save_s"] += time.monotonic() - started
    return ids, receipts, timings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for path in ("inputs", "g7", "source", "production", "reference", "ffd-manifest", "out"):
        parser.add_argument("--" + path, type=Path, required=True)
    parser.add_argument("--case", choices=CASES, required=True)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--g8-canary", type=Path, metavar="G1_OUTPUT")
    args = parser.parse_args()
    started_utc, started = utc_now(), time.monotonic()
    scene, anchor, poses, tasks, base, diagnostic, main_count = case_inputs(
        args.inputs, args.g7, args.case)
    if not 0 <= args.shard_index < args.shard_count <= len(tasks):
        raise ValueError("Invalid shard index/count")
    near_ids = {row["pose_id"] for row in base + diagnostic if row["set"] in NEAR_SETS}
    tasks = tasks[args.shard_index::args.shard_count]
    if args.g8_canary:
        if args.case != "G-T1_A" or args.shard_count != 1:
            raise ValueError("G8 canary uses the unsharded G-T1_A pilot")
        tasks, near_ids = canary_selection(args.g8_canary, base, tasks)
    production, reference = frozen_settings(args)
    args.out.mkdir(parents=True, mode=0o700, exist_ok=False)
    core, _, versions = load_runtime(args.source)
    ids, receipts, timings = generate_shard(core, scene, anchor, args.inputs / "scene",
                                             poses, tasks, near_ids, production, args.out)
    if args.g8_canary:
        from tb3_paths_near import check_g8

        check_canary(args.g8_canary, args.out / "PATHS_LoS.npz")
        gate = check_g8(args.out / "PATHS_NEAR.npz", np.load(args.out / "H_LoS.npy", allow_pickle=False), ids)
        if gate["status"] != "PASS":
            raise ValueError("Batched G8 canary failed same-trace reconstruction")
        write(args.out / "CANARY.json", gate | {"native_g1_coefficient_delay_exact": True})
    write(args.out / "MANIFEST.json", dict(
        status="PASS", case=args.case, role="IMPLEMENTER", code_commit=args.code_commit,
        question_ids=["G1-RT-TB3-001", "G1-RT-TB3-002"], engine=production,
        scope="G8_CANARY" if args.g8_canary else "PRODUCTION",
        g0_manifest_sha256=G0_SHA, g7_manifest_sha256=G7_SHA, production_sha256=F1_SHA,
        reference_sha256=REFERENCE_SHA, ffd_manifest_sha256=FFD_SHA, governance=reference["governance"],
        source_sha256={name: sha(Path(__file__).with_name(name)) for name in
                       ("run_tb3_production.py", "run_tb3_g1_pilot.py", "run_tb3_g8_pilot.py",
                        "tb3_native_los.py", "tb3_paths_near.py")},
        shard_index=args.shard_index, shard_count=args.shard_count, trace_positions=len(tasks),
        poses=len(ids), main_poses=sum(i < main_count for i in ids),
        diagnostic_poses=sum(i >= main_count for i in ids), near_pose_count=len(near_ids.intersection(ids)),
        solver_calls=sum(receipt["solver_calls"] for receipt in receipts), extra_export_solver_calls=0,
        native_field_batch_positions=FIELD_BATCH_XY, started_utc=started_utc, finished_utc=utc_now(),
        wall_s=time.monotonic()-started, timings=timings, command=[sys.executable, *sys.argv],
        runtime_versions=versions,
        output_sha256={path.name: sha(path) for path in sorted(args.out.iterdir()) if path.is_file()},
        output_bytes={path.name: path.stat().st_size for path in sorted(args.out.iterdir()) if path.is_file()},
    ))


if __name__ == "__main__":
    main()
