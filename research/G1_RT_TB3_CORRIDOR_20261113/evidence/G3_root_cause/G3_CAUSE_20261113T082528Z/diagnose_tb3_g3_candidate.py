"""Instrument the solver at the original G3 failures without changing the gate."""
import argparse
import time
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write


SHAPES = ("ceiling", "wall_y_neg", "recess_1_wood")


def inspect_window(trace, scene, cfg, freqs, runs):
    import drjit as dr
    from sionna.rt.constants import InteractionType

    expected = [scene.objects[name].object_id for name in SHAPES]
    specular = InteractionType.SPECULAR
    observations = {}

    def observe_buffer(buffer):
        shapes = np.asarray(buffer.shapes)
        interactions = np.asarray(buffer.interaction_types)
        valid = np.asarray(buffer.valid, dtype=bool).ravel()
        mask = np.all(shapes == expected, axis=1) & np.all(interactions == specular, axis=1)
        vertices = np.stack([np.asarray(getattr(buffer, f"vertices_{dim}"))[mask] for dim in "xyz"], axis=-1)
        return dict(total=len(valid), valid=int(valid.sum()), matching=int(mask.sum()),
                    matching_valid=int((mask & valid).sum()), vertices=vertices.tolist())

    solver = trace.rt.PathSolver()
    generate = solver._candidate_generator
    image_method = solver._image_method
    field = solver._field_calculator

    def candidate(*args, **kwargs):
        if candidate_bin is None:
            return generate(*args, **kwargs)
        evaluation_freq = float(scene.frequency[0])
        try:
            scene.frequency = float(freqs[candidate_bin])
            buffer = generate(*args, **kwargs)
            buffer.schedule()
            dr.eval()
            return buffer
        finally:
            scene.frequency = evaluation_freq

    def image(scene, paths, *args, **kwargs):
        observations["before_image"] = observe_buffer(paths)
        solved = image_method(scene, paths, *args, **kwargs)
        observations["after_image"] = observe_buffer(solved)
        return solved

    def calculate(*args, **kwargs):
        solved = field(*args, **kwargs)
        observations["after_field"] = observe_buffer(solved)
        return solved

    solver._candidate_generator = candidate
    solver._image_method = image
    solver._field_calculator = calculate

    rows = []
    for evaluation_bin, candidate_bin, refraction in runs:
        observations.clear()
        scene.frequency = float(freqs[evaluation_bin])
        result = solver(scene, **(cfg | {"refraction": refraction}))
        tau = np.asarray(result.tau).ravel()
        depth = cfg["max_depth"]
        objects = np.asarray(result.objects).reshape(depth, len(tau)).T
        events = np.asarray(result.interactions).reshape(depth, len(tau)).T
        matched = np.flatnonzero(np.all(objects == expected, axis=1) & np.all(events == specular, axis=1))
        coeff = (np.asarray(result.a[0]) + 1j * np.asarray(result.a[1])).reshape(2, 2, len(tau))
        rows.append(dict(evaluation_bin=evaluation_bin, candidate_bin=candidate_bin,
                         refraction=refraction, stages=dict(observations), total_paths=len(tau),
                         matched=[dict(delay_ns=float(tau[i] * 1e9),
                                       iso_matrix_norm=float(np.linalg.norm(coeff[:, :, i])))
                                  for i in matched]))
        print(evaluation_bin, candidate_bin, refraction,
              [s["matching"] for s in observations.values()], len(matched), flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("--root", type=Path, default=Path("/g3"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start = time.monotonic()
    root = args.root
    input_dir = root / "input"
    source = Path("/ref")
    trace, _, versions = load_runtime(source)
    ref = read(input_dir / "REFERENCE.json")
    for name, expected in ref["method_b_sha256"].items():
        if sha(source / name) != expected:
            raise ValueError(f"Method B input changed: {name}")
    case = "G-T2_A"
    gate_file = root / "analysis/G3.json"
    gate = read(gate_file)
    if not any(r["case"] == case and r["tag"] == args.tag for r in gate["pooled"]["unusable"]):
        raise ValueError(f"Tag was not a G3 failure: {args.tag}")
    frozen = root / "output" / case / "bin_by_bin" / f"{args.tag}_trace.npz"
    receipt_file = frozen.with_name(f"{frozen.stem}_receipt.json")
    receipt = read(receipt_file)
    target, = receipt["complex_paths"]
    with np.load(frozen, allow_pickle=False) as raw:
        freqs = raw["node_freq_hz"]
        target_tau = float(raw["tau"][target])
    entry = read(input_dir / "scene/SCENE_MANIFEST.json")["geometries"]["G-T2"]
    for item in entry["material_bindings"]:
        if sha(input_dir / "scene" / item["ply"]) != item["ply_sha256"]:
            raise ValueError(f"G0 mesh changed: {item['ply']}")

    factory, loader = geometry_adapter(trace, entry, input_dir / "scene")
    setup = factory(anchor_x_m=7.0)
    scene, _ = loader(setup, None)
    rt, mi = trace.rt, trace.mi
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0, 0.0, 0.0]))
    scene.add(rt.Receiver("rx", position=setup.robot_position(receipt["x"], receipt["y"]).tolist(),
                          orientation=[0.0, 0.0, 0.0]))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(trace.Ports([trace.IsoPort(0), trace.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))

    cfg = ref["block_c_solver"]
    runs = [(b, None, cfg["refraction"]) for b in range(138, 145)]
    runs.extend([(141, 138, True), (138, 141, True), (141, None, False)])
    rows = inspect_window(trace, scene, cfg, freqs, runs)
    write(args.out, dict(kind="POST_HOC_DIAGNOSTIC", question_id="G1-RT-TB3-001",
                         case=case, tag=args.tag, target_shapes=SHAPES, versions=versions,
                         target_delay_ns=target_tau * 1e9, original_gate=gate["status"],
                         gate_sha256=sha(gate_file), frozen_trace_sha256=sha(frozen),
                         frozen_receipt_sha256=sha(receipt_file), script_sha256=sha(Path(__file__)),
                         solver=cfg, window_freq_hz={b: float(freqs[b]) for b in range(138, 145)},
                         rows=rows, wall_s=time.monotonic() - start))


if __name__ == "__main__":
    main()
