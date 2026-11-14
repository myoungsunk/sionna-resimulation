"""Trace the four frozen G6 recess mismatches inside Sionna's image method."""
from __future__ import annotations

import hashlib
import importlib
import inspect
import json
import linecache
import re
import sys
from pathlib import Path

import drjit as dr
import numpy as np

from run_tb3_g1_pilot import load_runtime
from run_tb3_g8_pilot import capture_trace
from run_tb3_production import case_inputs
from tb3_g6_face_match import load_faces
from tb3_g6_revalidate import trace_hits
from validate_tb3_production_g3 import scene_runtime


RUN = Path("/run")
INPUT = Path("/evidence")
PRODUCTION = Path("/production")
SOURCE = Path("/ref")
ARCHIVE = Path("/original")
IMAGE_SHA = "f1983dc1b5a6038f95788f331855f798552e216caa04c6361443ec0cc5015d2a"
REVALIDATION_SHA = "e17723bbd0b5cb835a396b89fa72def3c590359f86e6f427d08180e64affb767"
ORIGINAL_SHA = "b0da8458aacdcffc9800f413d65ed6da25a0a911190d818d862280c81e12fdef"


def load_hashed(path, expected):
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(f"Frozen file hash mismatch: {path}")
    return json.loads(payload)


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Instrumentation anchor is not unique: {old!r}")
    return source.replace(old, new)


class SymbolicCapture:
    """Collect float32 bits from one matched candidate in a symbolic loop."""

    def __init__(self):
        self.rows = {}

    def write(self, output):
        for line in output.splitlines():
            fields = re.fullmatch(r"g6 (\w+) ((?:\[[\d, ]+\] ?)+)", line.strip())
            if not fields:
                raise ValueError(f"Unexpected Dr.Jit capture: {line!r}")
            label, bits = fields.groups()
            columns = [[int(x) for x in re.findall(r"\d+", col)]
                       for col in re.findall(r"\[[^\]]+\]", bits)]
            self.rows.setdefault(label, []).extend(list(row) for row in zip(*columns, strict=True))


def instrument(module, lane, side_scale, origin_scale, fallback, sink):
    path = Path(inspect.getsourcefile(module))
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != IMAGE_SHA:
        raise ValueError("Unexpected Sionna image method source")
    source = payload.decode()
    header = "            # Compute the image of the current vertex with respect to the"
    source = replace_once(source, header, """            g6_image_input = source_images
""" + header)
    marker = "            # Use path vertices as a buffer to store the source images"
    source = replace_once(source, marker, """            g6_dump("images", specular & (dr.arange(mi.UInt, paths.buffer_size) == g6_lane),
                    depth, paths.get_shape(depth, specular), paths.get_primitive(depth, specular),
                    vecs=(vertex, normal, g6_image_input, source_images))
""" + marker)
    ray = """            ray = spawn_ray_to(vertex_offset,
                               offset_p(ray_target_offset, k, normal_image),
                               normal)"""
    source = replace_once(source, ray, """            g6_target = g6_offset(ray_target_offset, k, normal_image, g6_side_scale, depth)
            if g6_origin_scale == 1:
                ray = spawn_ray_to(vertex_offset, g6_target, normal)
            else:
                ray = spawn_ray_to(g6_offset(vertex_offset, g6_target - vertex_offset,
                                             normal, g6_origin_scale, depth), g6_target)""")
    marker = "            # Refractions don't affect path geometry, so they are always valid"
    source = replace_once(source, marker, """            g6_gap_sq = dr.squared_norm(exp_img_img - new_img_img)
            g6_dump("backtrack", valid_inter & (dr.arange(mi.UInt, paths.buffer_size) == g6_lane),
                    depth, expected_shape, expected_prim_ind, si_shape, si_scene.prim_index,
                    mi.UInt(hit_expected_prim), mi.UInt(valid_specular), mi.UInt(first_segment), mi.UInt(si_scene.is_valid()),
                    vecs=(vertex, normal, ray_target, normal_image, ray.o, ray.d, g6_target,
                          si_scene.p, si_scene.n), floats=(si_scene.t, ray.maxt, g6_gap_sq))
""" + marker)
    if not fallback:
        source = replace_once(source,
                              "| (dr.squared_norm(exp_img_img - new_img_img) < 1e-4)",
                              "| False")
    mi = module.mi

    def g6_dump(label, mask, *values, vecs, floats=()):
        float_bits = [dr.reinterpret_array(mi.UInt, x) for vec in vecs for x in (vec.x, vec.y, vec.z)]
        float_bits += [dr.reinterpret_array(mi.UInt, x) for x in floats]
        fmt = "g6 " + label + " " + " ".join(["{}"] * (len(values) + len(float_bits)))
        dr.print(fmt, *values, *float_bits, active=mask, limit=8, file=sink)

    def g6_offset(point, direction, normal, scale, depth):
        shifted = module.offset_p(point, direction, normal)
        if scale == 1:
            return shifted
        sidewall = dr.fma(scale, shifted - point, point)
        return dr.select(depth == 2, sidewall, shifted)

    filename = str(RUN / "instrumented_image_method.py")
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    namespace = dict(vars(module), g6_dump=g6_dump, g6_lane=lane, g6_side_scale=side_scale,
                     g6_origin_scale=origin_scale, g6_offset=g6_offset)
    exec(compile(source, filename, "exec"), namespace)
    return namespace["ImageMethod"]()


def candidate_rows(buf):
    def axis_reader(axis):
        return np.asarray(getattr(buf, "vertices_" + axis))[:, :3]
    return np.stack([axis_reader(axis) for axis in "xyz"], axis=-1)


def candidate_lane(buf, prior):
    target = np.asarray([v["native_point_m"] for v in prior["vertices"]], dtype=np.float32)
    points = candidate_rows(buf)
    match = np.flatnonzero(np.asarray(buf.valid) & np.all(points == target, axis=(1, 2)))
    if len(match) != 1:
        raise ValueError(f"Cannot bind canonical path vertices to a unique solver lane: {match}")
    return int(match[0])


def decode(rows, shape_names):
    layouts = {
        "images": (("depth", "sampled_shape", "sampled_primitive"),
                   ("sampled_hit_m", "normal", "source_image_in_m", "source_image_out_m"), ()),
        "backtrack": (("depth", "expected_shape", "expected_primitive", "hit_shape", "hit_primitive",
                       "hit_expected", "valid_specular", "first_segment", "hit_scene_valid"),
                      ("vertex_m", "normal", "target_m", "target_normal", "ray_o_m", "ray_d",
                       "offset_target_m", "hit_m", "hit_normal"), ("ray_hit_t_m", "ray_maxt_m", "fallback_gap_sq_m2")),
    }
    result = {}
    for label, (integer, vector, scalar) in layouts.items():
        entries = []
        for raw in rows.get(label, []):
            if len(raw) != len(integer) + 3 * len(vector) + len(scalar):
                raise ValueError("Missing captured coordinates")
            data = dict(zip(integer, raw[:len(integer)], strict=True))
            for key in integer:
                if key.endswith("_shape"):
                    data[key] = shape_names.get(data[key], data[key])
            values = np.asarray(raw[len(integer):], dtype=np.uint32).view(np.float32).astype(float)
            for i, key in enumerate(vector):
                data[key] = [float(x) if np.isfinite(x) else None for x in values[i*3:(i+1)*3]]
            for key, value in zip(scalar, values[3*len(vector):], strict=True):
                data[key] = float(value) if np.isfinite(value) else None
            entries.append(data)
        result[label] = sorted(entries, key=lambda row: row["depth"], reverse=label=="backtrack")
    return result


def archived_row(original, case, index):
    matches = []
    for path in sorted((ARCHIVE / "traces").glob(f"{case}_*.jsonl")):
        rows = load_hashed_lines(path, original["input_sha256"]["/run/traces/" + path.name])
        matches.extend(row for row in rows if row["task_id"] == index)
    if len(matches) != 1:
        raise ValueError("Unexpected frozen path archive coverage")
    return matches[0]


def load_hashed_lines(path, expected):
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError(f"Frozen file hash mismatch: {path}")
    return [json.loads(line) for line in payload.splitlines()]


def run_case(core, module, frequency, f1, prior, original):
    case, index = prior["case"], prior["task_id"]
    entry, anchor, _, tasks, *_ = case_inputs(PRODUCTION/"g0", PRODUCTION/"g7", case)
    scene, solver, setup = scene_runtime(core, entry, anchor, PRODUCTION/"g0/scene")
    task = tasks[index]
    faces = load_faces(scene, entry, PRODUCTION/"g0/scene")
    shapes = scene.mi_scene.shapes()
    shape_names = dict(zip(np.asarray(dr.reinterpret_array(core.mi.UInt, core.mi.ShapePtr(shapes))).tolist(),
                           [shape.id() for shape in shapes], strict=True))
    baseline_lanes = []
    sampled = []
    original_image = solver._image_method

    def capture_lane(**kwargs):
        before = candidate_rows(kwargs["paths"])
        solved = original_image(**kwargs)
        lane = candidate_lane(solved, prior)
        baseline_lanes.append(lane)
        sampled.append(before[lane].copy())
        return solved

    solver._image_method = capture_lane
    bins = core.node_bins(len(frequency), str(f1["base_nodes"]))
    trace, hits, nodes = trace_hits(core, scene, solver, f1["solver"], frequency, bins, task, setup, faces)
    archive = archived_row(original, case, index)
    if not np.array_equal(trace["tau"], archive["tau_s"]) or nodes != archive["node_bins"]:
        raise ValueError("Baseline path delays or nodes differ from archived G6")
    chain = hits[prior["path_index"]]
    if [point for _, _, _, point in chain] != [tuple(v["native_point_m"]) for v in prior["vertices"]]:
        raise ValueError("Baseline vertices differ from archived mismatch diagnostics")
    lane = baseline_lanes[0]

    variants = [
        ("instrumented_f1", 1., 1., True), ("no_primitive_fallback", 1., 1., False),
        ("quarter_target_offset", .25, 1., True), ("quarter_origin_offset", 1., .25, True),
        ("target_65_percent", .65, 1., True), ("target_85_percent", .85, 1., True),
        ("zero_target_offset", 0., 1., True),
        ("zero_origin_offset", 1., 0., True),
    ]
    results = {}
    for name, target_scale, origin_scale, fallback in variants:
        sink = SymbolicCapture()
        active_lanes = []

        def capture_variant(**kwargs):
            candidates = candidate_rows(kwargs["paths"])
            same = np.flatnonzero(np.all(candidates == sampled[0], axis=(1, 2)))
            if len(same) != 1:
                raise ValueError(f"Instrumented run did not reproduce the sampled candidate: {same}")
            active_lanes.append(int(same[0]))
            image = instrument(module, int(same[0]), target_scale, origin_scale, fallback, sink)
            return image(**kwargs)

        solver._image_method = capture_variant
        variant, _ = capture_trace(core, scene, solver, f1["solver"], frequency, [0], task, setup)
        if name == "instrumented_f1":
            for key in ("tau", "ang", "interactions", "objects", "present"):
                if not np.array_equal(variant[key], trace[key] if key != "present" else trace[key][:1]):
                    raise ValueError(f"Instrumentation changed baseline {key}")
        data = decode(sink.rows, shape_names)
        if [s["depth"] for s in data["images"]] != [1, 2, 3]:
            raise ValueError(f"Incomplete candidate image evidence: {name}")
        if name == "instrumented_f1":
            captured = [s["hit_m"] for s in data["backtrack"] if s["depth"] > 0]
            if captured != [v["native_point_m"] for v in reversed(prior["vertices"])]:
                raise ValueError("Instrumented candidate hits differ from archived mismatch")
        results[name] = data | {"path_count": len(variant["tau"]), "lane": active_lanes[0]}
    return dict(case=case, task_id=index, path_index=prior["path_index"], canonical_delays_verified=len(trace["tau"]),
                nodes=nodes, lane=lane, lane_by_node=baseline_lanes, prior=prior, variants=results)


def main():
    original = load_hashed(ARCHIVE/"G6.json", ORIGINAL_SHA)
    previous = load_hashed(INPUT/"G6_REVALIDATION.json", REVALIDATION_SHA)
    if original["status"] != "FAIL" or previous["status"] != "FAIL" or previous["strict_tolerance_s"] != 5e-14:
        raise ValueError("Unexpected frozen G6 contract")
    evidence = load_hashed(INPUT/"FINITE_FACE_DIAGNOSTICS.json",
                           "0097d6682c68d11b19f3852e84c931396713ac7c09fa8be113bcea20c24d9f7c")
    cases = evidence["cases"]
    expected = {(case, f["task_id"], f["path_index"])
                for case, c in previous["cases"].items() for f in c["failures"]}
    if len(cases) != 4 or {(r["case"], r["task_id"], r["path_index"]) for r in cases} != expected:
        raise ValueError("This diagnostic must cover all and only the four G6 mismatches")
    f1 = json.loads((PRODUCTION/"config/PRODUCTION_F1.json").read_text())
    core, _, versions = load_runtime(SOURCE)
    with np.load(SOURCE/"LP_plus45_bank.npz", allow_pickle=False) as bank:
        freq = bank["freqs_hz"]
    module = importlib.import_module("sionna.rt.path_solvers.image_method")
    cases = [run_case(core, module, freq, f1, row, original) for row in cases]
    result = dict(status="COMPLETE", stage="G6_BOUNDARY_DIAGNOSTIC", question_id="G1-RT-TB3-001",
                  role="IMPLEMENTER", gate_status="FAIL", strict_tolerance_s=5e-14,
                  runtime=versions, image_method_sha256=IMAGE_SHA, source_commit=sys.argv[1],
                  governance={"common": "a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
                              "implementer": "2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da"},
                  cases=cases)
    with (RUN/"BOUNDARY_STAGES.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
