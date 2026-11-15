"""A/B pilot on the four frozen G6 failures and five archived controls."""
from __future__ import annotations

from argparse import Namespace
import sys
from pathlib import Path
from time import monotonic

import numpy as np

from diagnose_tb3_g6_boundary import ORIGINAL_SHA, REVALIDATION_SHA, load_hashed, load_hashed_lines
from run_tb3_g1_pilot import load_runtime, sha, write
from run_tb3_production import case_inputs, frozen_settings, utc_now
from tb3_finite_face_guard import FiniteFaceGuard
from tb3_g6_face_match import EXACT_HIT_TOL_M, load_faces, match_path
from validate_tb3_production_g3 import scene_runtime


RUN = Path("/run")
PRODUCTION = Path("/production")
SOURCE = Path("/ref")
EVIDENCE = Path("/evidence")
BOUNDARY_SHA = "f678574ea2818f0ba10d0467f737b1af272027928ce1bc28aef134d83c2f4a2c"
STRICT_TOL_S = 5e-14
# Last entry is a connected-triangle seam control, with a three-bounce path.
CONTROLS = [
    ("G-T2_B", 1714, 52, "01", 1708),
    ("G-T2_C", 1027, 45, "00", 1025),
    ("G-T2_C", 1846, 55, "00", 1840),
    ("G-T2_C", 2471, 56, "03", 2477),
    ("G-T2_B", 1731, 23, "08", None),
]


def geometry_key(chain, points):
    return tuple(tuple(x) for x in chain), tuple(tuple(x) for x in points)


def snapshot(core, native, depth):
    tau = np.asarray(native.tau).ravel()
    n = len(tau)
    angles = np.stack([np.asarray(getattr(native, name)).ravel()
                       for name in ("theta_t", "phi_t", "theta_r", "phi_r")])
    a_real, a_imag = [np.asarray(a).reshape(2, 2, n) for a in native.a]
    events = np.asarray(native.interactions).reshape(depth, n).T
    objects = np.asarray(native.objects).reshape(depth, n).T
    primitives = np.asarray(native.primitives).reshape(depth, n).T
    points = np.asarray(native.vertices).reshape(depth, n, 3).transpose(1, 0, 2)
    if not all(np.isfinite(a).all() for a in (tau, angles, a_real, a_imag)):
        raise ValueError("Non-finite path delay, angle, or Jones coefficient")
    kind = core.rt.constants.InteractionType
    keys = []
    fields = {}
    for i, row in enumerate(events):
        count = int(np.count_nonzero(row != kind.NONE))
        if np.any(row[:count] != kind.SPECULAR) or np.any(row[count:] != kind.NONE):
            raise ValueError("Unexpected event or padding in F1")
        key = geometry_key(zip(map(int, objects[i, :count]), map(int, primitives[i, :count]), strict=True),
                           points[i, :count].tolist())
        if key in fields:
            raise ValueError("Duplicate physical path key")
        keys.append(key)
        fields[key] = (tau[i].tobytes(), angles[:, i].tobytes(),
                       a_real[:, :, i].tobytes(), a_imag[:, :, i].tobytes())
    order = core.P.canonical_order(tau.astype(float), *angles.astype(float))
    return fields, [keys[i] for i in order], tau[order].astype(float)


def timing(key, faces, tx, rx, recorded_tx, recorded_rx):
    chain, points = key
    hits = []
    for (obj, primitive), point in zip(chain, points, strict=True):
        triangles, patches = faces[obj]
        hits.append((primitive, triangles[primitive], patches[primitive], point))
    name, recorded, image, switches, _, error = match_path(tx, rx, recorded_tx, recorded_rx, hits)
    return name, (None if image is None else abs(recorded - image)), switches, error


def run_case(core, entry, anchor, scene, baseline, setup, faces, settings, freq, bins, task, old, target):
    case, index, path_index = target["case"], task["task_id"], target["path_index"]
    suspect = "prior" in target
    tx = entry["anchors_xyz_m"][anchor]
    rx = [task["x"], task["y"], entry["rx_z_m"]]
    scene.receivers["rx"].position = core.mi.Point3f(*setup.robot_position(*rx[:2]).tolist())
    recorded_tx = tuple(np.asarray(scene.transmitters["tx"].position).reshape(3).astype(float))
    recorded_rx = tuple(np.asarray(scene.receivers["rx"].position).reshape(3).astype(float))
    if (old["status"] != "OK" or old["absent_at_some_node_paths"] or
            [old[k] for k in ("case", "tag", "pose_ids")] != [case, task["tag"], task["pose_ids"]] or
            [old["x"], old["y"]] != rx[:2] or old["node_bins"] != bins or
            old["tx_xyz_m"] != list(recorded_tx) or old["rx_xyz_m"] != list(recorded_rx)):
        raise ValueError("Pilot pose or baseline node cover differs from the original G6 archive")

    guarded = core.rt.PathSolver()
    guard = FiniteFaceGuard(guarded, core.mi, scene, faces, tx, rx, core.rt.constants.InteractionType)
    max_delay = max_control = 0.0
    rows = []
    for b in bins:
        scene.frequency = float(freq[b])
        before, ordered, tau = snapshot(core, baseline(scene, **settings), settings["max_depth"])
        if b == 0:
            if not np.array_equal(tau, old["tau_s"]):
                raise ValueError(f"Baseline path ordering/delay differs from G6 at {case}/{index}")
            key = ordered[path_index]
            signature, residual, switches, error = timing(key, faces, tx, rx, recorded_tx, recorded_rx)
            if suspect:
                expected = target["prior"]
                if (list(key[1]) != [tuple(v["native_point_m"]) for v in expected["vertices"]] or
                        [p for _, p in key[0]] != [v["primitive"] for v in expected["vertices"]] or
                        error != expected["gate_error"]):
                    raise ValueError(f"Baseline path did not reproduce the boundary finding: {case}/{index}")
            else:
                archived = target["archived"]
                if (signature != archived[0] or switches != archived[3] or error is not None or
                        residual != abs(archived[1] - archived[2]) or residual > STRICT_TOL_S or
                        (target["paired_task_id"] is None and switches < 1)):
                    raise ValueError(f"Baseline did not reproduce the frozen normal control: {case}/{index}")

        after, _, _ = snapshot(core, guarded(scene, **settings), settings["max_depth"])
        rejected = {geometry_key(r["chain"], r["vertices_m"]): r["reason"] for r in guard.rejected}
        expected_removed = {key} if suspect else set()
        removed, extra = before.keys() - after.keys(), after.keys() - before.keys()
        changed = sum(before[k] != after[k] for k in before.keys() & after.keys())
        if (key not in before or removed != expected_removed or extra or changed or
                set(rejected) != expected_removed or len(guard.rejected) != len(expected_removed)):
            raise ValueError(f"Unexpected A/B result at {case}/{index}/{b}: target present={key in before}, "
                             f"removed={len(removed)}, added={len(extra)}, changed={changed}, "
                             f"pre-field rejected={guard.rejected}")
        for retained in after:
            _, residual, _, error = timing(retained, faces, tx, rx, recorded_tx, recorded_rx)
            if error is not None or residual > STRICT_TOL_S:
                raise ValueError(f"Retained path failed strict G6 check at {case}/{index}/{b}: {error}, {residual}")
            max_delay = max(max_delay, residual)
            if retained == key:
                max_control = max(max_control, residual)
        rows.append(dict(bin=b, frequency_hz=float(freq[b]), before=len(before), after=len(after),
                         pre_field_rejected=guard.rejected, retained_bitwise=len(after)))
    return dict(case=case, task_id=index, path_index=path_index, role="suspect" if suspect else "control",
                paired_task_id=target.get("paired_task_id"), rx_xyz_m=rx, face_sequence=signature,
                geometry_key=key, seam_switches_at_zero=switches, max_retained_delay_residual_s=max_delay,
                max_control_delay_residual_s=None if suspect else max_control, nodes=rows)


def main():
    start, tick = utc_now(), monotonic()
    original = load_hashed(EVIDENCE/"G6.json", ORIGINAL_SHA)
    previous = load_hashed(EVIDENCE/"G6_REVALIDATION.json", REVALIDATION_SHA)
    boundary = load_hashed(EVIDENCE/"BOUNDARY_STAGES.json", BOUNDARY_SHA)
    targets = boundary["cases"]
    expected = {(c, f["task_id"], f["path_index"]) for c, row in previous["cases"].items() for f in row["failures"]}
    if (original["status"] != "FAIL" or previous["status"] != "FAIL" or boundary["gate_status"] != "FAIL" or
            any(v["strict_tolerance_s"] != STRICT_TOL_S for v in (original, previous, boundary)) or
            len(targets) != 4 or {(t["case"], t["task_id"], t["path_index"]) for t in targets} != expected):
        raise ValueError("Original G6 records, threshold, or four-case pilot scope changed")
    for case, index, path_index, shard, paired in CONTROLS:
        name = f"{case}_{shard}.jsonl"
        archive = load_hashed_lines(EVIDENCE/"controls"/name, previous["cases"][case]["trace_sha256"][name])
        control, = (row["paths"][path_index] for row in archive if row["task_id"] == index and row["case"] == case)
        if paired is not None:
            suspect, = (f for f in previous["cases"][case]["failures"] if f["task_id"] == paired)
            if control[0] != suspect["face_sequence"]:
                raise ValueError("Control does not reproduce the failed face sequence")
        targets.append(dict(case=case, task_id=index, path_index=path_index, paired_task_id=paired, archived=control))

    f1, reference = frozen_settings(Namespace(production=PRODUCTION/"config/PRODUCTION_F1.json",
                                             reference=PRODUCTION/"frozen/REFERENCE.json",
                                             ffd_manifest=PRODUCTION/"frozen/FFD_RESTORE_MANIFEST.json", source=SOURCE))
    core, _, versions = load_runtime(SOURCE)
    with np.load(SOURCE/"LP_plus45_bank.npz", allow_pickle=False) as bank:
        freq = bank["freqs_hz"]
    bins = list(core.node_bins(len(freq), str(f1["base_nodes"])))
    if not np.isfinite(freq).all() or bins != list(range(0, 257, 16)) or len(freq) != f1["channel_bins"]:
        raise ValueError("Unexpected F1 frequency grid")
    scene_root = PRODUCTION/"g0/scene"
    cases = []
    for case in ("G-T2_B", "G-T2_C"):
        entry, anchor, _, tasks, *_ = case_inputs(PRODUCTION/"g0", PRODUCTION/"g7", case)
        scene, baseline, setup = scene_runtime(core, entry, anchor, scene_root)
        faces = load_faces(scene, entry, scene_root)
        wanted = {t["task_id"]: t for t in targets if t["case"] == case}
        old_rows = {}
        for path in sorted((EVIDENCE/"traces").glob(f"{case}_*.jsonl")):
            archive = load_hashed_lines(path, original["input_sha256"][f"/run/traces/{path.name}"])
            for row in archive:
                index = row["task_id"]
                if index in wanted:
                    if index in old_rows:
                        raise ValueError("Duplicate original G6 row")
                    old_rows[index] = row
        for index, target in wanted.items():
            cases.append(run_case(core, entry, anchor, scene, baseline, setup, faces, f1["solver"],
                                  freq, bins, tasks[index], old_rows[index], target))
            print(f"{case}/{index}: {cases[-1]['role']} 17/17", flush=True)

    source_root = Path(core.rt.__file__).parent/"path_solvers"
    write(RUN/"FINITE_FACE_PILOT.json", dict(
        status="PASS", stage="G6_FINITE_FACE_PILOT", question_id="G1-RT-TB3-001", role="IMPLEMENTER",
        historical_g6_status="FAIL", strict_tolerance_s=STRICT_TOL_S, exact_hit_tolerance_m=EXACT_HIT_TOL_M,
        trace_code_commit=sys.argv[1], method_b_commit=reference["method_b_commit"], f1_solver=f1["solver"],
        runtime=versions | {"mitsuba_variant": core.mi.variant()},
        engine_sha256={name: sha(source_root/name) for name in
                       ("path_solver.py", "image_method.py", "field_calculator.py", "paths_buffer.py")},
        source_sha256={name: sha(Path("/code")/name) for name in
                       ("tb3_finite_face_guard.py", "pilot_tb3_finite_face_guard.py")},
        input_sha256={"G6.json": ORIGINAL_SHA, "G6_REVALIDATION.json": REVALIDATION_SHA, "BOUNDARY_STAGES.json": BOUNDARY_SHA},
        nodes=bins, positions=len(cases), solver_calls=2*len(cases)*len(bins),
        target_path_nodes_removed=sum(len(n["pre_field_rejected"]) for row in cases for n in row["nodes"]),
        control_path_nodes_retained=sum(len(row["nodes"]) for row in cases if row["role"] == "control"),
        retained_path_nodes_bitwise=sum(n["retained_bitwise"] for row in cases for n in row["nodes"]),
        max_retained_delay_residual_s=max(row["max_retained_delay_residual_s"] for row in cases),
        started_utc=start, finished_utc=utc_now(), pilot_wall_s=monotonic()-tick, cases=cases))


if __name__ == "__main__":
    main()
