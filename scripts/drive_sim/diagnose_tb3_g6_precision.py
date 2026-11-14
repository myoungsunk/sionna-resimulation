"""Recompute the two G6 residuals left after testing unmerged image candidates."""
from __future__ import annotations

import argparse
from math import dist, fsum
from pathlib import Path
from time import monotonic

import numpy as np
from scipy.constants import speed_of_light

from diagnose_tb3_g6_image import G6_SHA256, STRICT_TOL_S
from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write
from run_tb3_production import case_inputs, frozen_settings, utc_now, verify
from validate_tb3_g5 import mesh_triangles
from validate_tb3_g6 import traces_for_case

IMAGE_SHA256 = "e1341e1b1e8579b63cecd64031827760060cc590b8e8f8c0315c49f7c37bafa2"


def plane_hit(triangle, vertex):
    axes = np.flatnonzero(np.ptp(triangle, axis=0) == 0)
    if len(axes) != 1:
        raise ValueError("Expected an axis-aligned scene triangle")
    axis = int(axes[0])
    pos = float(triangle[0, axis])
    # Check triangle identity against the solver hit before using its exact PLY plane.
    p, q, r = triangle
    bary = np.linalg.lstsq(np.column_stack((q - p, r - p)), vertex - p, rcond=None)[0]
    projected = p + bary[0] * (q - p) + bary[1] * (r - p)
    error_m = dist(vertex, projected)
    if error_m > 1e-5 or min(*bary, 1.0 - sum(bary)) < -1e-5:
        raise ValueError(f"Native hit is outside its reported triangle: {vertex}, {triangle}")
    return axis, pos, error_m


def exact_reflection(tx, rx, reflections):
    # Images of the receiver after each reflector, in reverse encounter order.
    virtual = [np.asarray(rx, dtype=float)]
    for axis, pos, _ in reversed(reflections):
        image = virtual[-1].copy()
        image[axis] = 2 * pos - image[axis]
        virtual.append(image)

    points = [np.asarray(tx, dtype=float)]
    for (axis, pos, _), image in zip(reflections, reversed(virtual[1:]), strict=True):
        direction = image - points[-1]
        parameter = (pos - points[-1][axis]) / direction[axis]
        if not 0 < parameter < 1:
            raise ValueError("Unfolding did not intersect the next reflector within the segment")
        points.append(points[-1] + parameter * direction)
    points.append(np.array(rx))
    for (_, _, triangle), point in zip(reflections, points[1:-1], strict=True):
        plane_hit(triangle, point)
    unfolded = dist(tx, virtual[-1]) / speed_of_light
    folded = fsum(dist(a, b) for a, b in zip(points, points[1:])) / speed_of_light
    if abs(unfolded - folded) > 1e-20:
        raise ValueError("Folded and unfolded length differ")
    return unfolded, points


def diagnose_case(args, wanted, original, selection, core, production, frequencies):
    case = wanted["case"]
    root = args.production_root
    entry, anchor_id, _, tasks, *_ = case_inputs(root / "g0", root / "g7", case)
    checks = {}
    saved, _, missing, unexpected = traces_for_case(case, selection[case], args.g6 / "traces", checks)
    if missing or unexpected or any(original["input_sha256"][f"/run/traces/{Path(p).name}"] != v
                                    for p, v in checks.items()):
        raise ValueError("Incomplete or changed original G6 archive")
    index = wanted["task_id"]
    task = tasks[index]
    old = saved[index]
    xy = [task["x"], task["y"]]
    old_delays = np.asarray(old["tau_s"])
    if (old["tag"] != task["tag"] or [old["x"], old["y"]] != xy or xy != wanted["xy"]
            or old["status"] != "OK" or old["node_bins"][0] != 0
            or old["absent_at_some_node_paths"]):
        raise ValueError("Archived pose or node coverage differs")
    anchor = entry["anchors_xyz_m"][anchor_id]
    scene_root = root / "g0/scene"
    factory, loader = geometry_adapter(core, entry | {"anchors_xyz_m": {"A": anchor}}, scene_root)
    setup = factory(anchor_x_m=anchor[0])
    if not all(q["passed"] for q in setup.validate()):
        raise ValueError("Invalid frozen geometry")
    scene, bindings = loader(setup, None)
    rt, mi = core.rt, core.mi
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0] * 3))
    scene.add(rt.Receiver("rx", position=setup.robot_position(*xy).tolist(), orientation=[0.0] * 3))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(core.Ports([core.IsoPort(0), core.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))
    scene.frequency = float(frequencies[0])
    result = rt.PathSolver()(scene, **production["solver"])
    native_tau = np.asarray(result.tau).ravel()
    angles = [np.asarray(getattr(result, name)).ravel().astype(np.float64)
              for name in ("theta_t", "phi_t", "theta_r", "phi_r")]
    order = core.P.canonical_order(native_tau.astype(np.float64), *angles)
    path_index = wanted["path_index"]
    if (not np.array_equal(native_tau[order].astype(np.float64), old_delays)
            or old_delays[path_index] != wanted["solved_delay_s"]
            or np.count_nonzero(native_tau == old_delays[path_index]) != 1):
        raise ValueError("Cannot uniquely align rerun path to archived canonical delays")
    hit = order[path_index]
    npaths, depth = len(native_tau), production["solver"]["max_depth"]
    vertices = np.asarray(result.vertices)
    hits = vertices.reshape(depth, npaths, 3)[:, hit]
    events = np.asarray(result.interactions).reshape(depth, npaths)[:, hit]
    objects = np.asarray(result.objects).reshape(depth, npaths)[:, hit]
    primitives = np.asarray(result.primitives).reshape(depth, npaths)[:, hit]
    tx_native = np.asarray(scene.transmitters["tx"].position).reshape(3)
    rx_native = np.asarray(scene.receivers["rx"].position).reshape(3)
    if (native_tau.dtype != np.float32 or vertices.dtype != np.float32
            or tx_native.astype(float).tolist() != old["tx_xyz_m"]
            or rx_native.astype(float).tolist() != old["rx_xyz_m"]):
        raise ValueError("Unexpected native dtype or saved endpoints")
    object_names = {int(obj.object_id): name for name, obj in scene.objects.items()}
    meshes = {b["object"]: b["ply"] for b in bindings}
    rtype = rt.constants.InteractionType
    sequence, reflections, native_points = [], [], [tx_native]
    for event, object_id, primitive, vertex in zip(events, objects, primitives, hits, strict=True):
        if event == rtype.NONE:
            continue
        if event != rtype.SPECULAR:
            raise ValueError(f"Unexpected non-specular interaction: {event}")
        name = object_names[int(object_id)]
        triangle = np.asarray(mesh_triangles(scene_root / meshes[name])[int(primitive)])
        axis, pos, error = plane_hit(triangle, vertex.astype(float))
        sequence.append(dict(object=name, primitive=int(primitive), axis=axis, position_m=pos,
                             plane_projection_error_m=error, vertex_m=vertex.astype(float).tolist()))
        reflections.append((axis, pos, triangle))
        native_points.append(vertex)
    native_points.append(rx_native)
    if ">".join(b["object"] for b in sequence) != wanted["nearest_image"]:
        raise ValueError("Native hit sequence differs from the closest ideal image")
    exact, exact_points = exact_reflection(anchor, [*xy, entry["rx_z_m"]], reflections)
    exact_native_ends, _ = exact_reflection(tx_native, rx_native, reflections)
    if abs(exact - wanted["nearest_image_delay_s"]) > 1e-20:
        raise ValueError("Exact matching primitive sequence differs from legacy image delay")

    native = float(native_tau[hit])
    segments_64 = fsum(dist(a, b) for a, b in zip(native_points, native_points[1:])) / speed_of_light
    # For the final image with native endpoints, widen them before any coordinate arithmetic.
    return dict(case=case, task_id=index, path_index=path_index, xy=xy,
                original_class_delay_s=wanted["original_class_delay_s"],
                original_image_delay_s=wanted["nearest_image_delay_s"],
                native_delay_s=native, segments_64_delay_s=segments_64, exact_delay_s=exact,
                native_minus_segments_64_s=native - segments_64,
                segments_64_minus_exact_s=segments_64 - exact,
                exact_with_native_endpoints_s=exact_native_ends,
                segments_64_minus_exact_with_native_endpoints_s=segments_64 - exact_native_ends,
                exact_with_native_endpoints_minus_exact_s=exact_native_ends - exact,
                native_minus_exact_s=native - exact,
                native_delay_ulp_s=float(np.spacing(native_tau[hit])),
                all_canonical_delays_identical=len(old_delays),
                native_tau_dtype=str(native_tau.dtype), native_vertex_dtype=str(vertices.dtype),
                tx_exact_m=anchor, rx_exact_m=[*xy, entry["rx_z_m"]],
                tx_native_m=tx_native.astype(float).tolist(), rx_native_m=rx_native.astype(float).tolist(),
                sequence=sequence, exact_hit_vertices_m=[p.tolist() for p in exact_points[1:-1]],
                checked_archived_trace_files=len(checks))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("g6", "image-result", "production-root", "source", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    started, tick = utc_now(), monotonic()
    verify(args.g6 / "G6.json", G6_SHA256)
    verify(args.image_result, IMAGE_SHA256)
    original = read(args.g6 / "G6.json")
    image = read(args.image_result)
    if original["strict_tolerance_s"] != STRICT_TOL_S or image["threshold_s"] != STRICT_TOL_S:
        raise ValueError("Unexpected G6 threshold")
    verify(args.g6 / "selected/SELECTION.json", original["input_sha256"]["/run/selected/SELECTION.json"])
    selection = read(args.g6 / "selected/SELECTION.json")
    targets = [r for r in image["rows"] if not r["recovered_at_strict"]]
    if len(targets) != 2 or any(r["class_displacement_s"] for r in targets):
        raise ValueError("Unexpected unresolved path set")
    root = args.production_root
    args.production = root / "config/PRODUCTION_F1.json"
    args.reference = root / "frozen/REFERENCE.json"
    args.ffd_manifest = root / "frozen/FFD_RESTORE_MANIFEST.json"
    production, _ = frozen_settings(args)
    core, _, versions = load_runtime(args.source)
    bank_path = args.source / "LP_plus45_bank.npz"
    with np.load(bank_path, allow_pickle=False) as bank:
        frequencies = bank["freqs_hz"]
    if frequencies.shape != (production["channel_bins"],) or not np.isfinite(frequencies).all():
        raise ValueError("Invalid frozen frequency grid")
    rows = [diagnose_case(args, wanted, original, selection, core, production, frequencies)
            for wanted in targets]
    package = Path(core.rt.__file__).parent / "path_solvers"
    hashes = {p.name: sha(p) for p in (package / "paths.py", package / "field_calculator.py")}
    write(args.out, dict(question_id=original["question_id"], official_gate_status=original["status"],
                        threshold_s=STRICT_TOL_S, solver_calls=len(rows), bin_index=0,
                        frequency_hz=float(frequencies[0]), solver=production["solver"],
                        started_utc=started, finished_utc=utc_now(), wall_s=monotonic() - tick,
                        runtime=versions | {"mitsuba_variant": core.mi.variant()},
                        sha256=hashes | {p.name: sha(p) for p in (Path(__file__), args.production, bank_path)}
                        | {"G6.json": G6_SHA256, "G6_IMAGE_DIAGNOSTIC.json": IMAGE_SHA256},
                        rows=rows))


if __name__ == "__main__":
    main()
