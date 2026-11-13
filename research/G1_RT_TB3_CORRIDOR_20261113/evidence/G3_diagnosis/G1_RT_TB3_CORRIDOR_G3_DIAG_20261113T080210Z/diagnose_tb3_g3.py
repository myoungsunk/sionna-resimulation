
"""Localize the frozen G3 path gap without changing the original gate."""
import argparse
import hashlib
import sys
import time
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write


def solve_window(trace, setup, scene, solver, cfg, freqs, reference, bins):
    """Compare raw solver paths to a frozen path and locate validity losses."""
    import drjit as dr
    from sionna.rt.constants import InteractionType

    events = {getattr(InteractionType, k): k for k in ("NONE", "SPECULAR", "DIFFUSE", "REFRACTION", "DIFFRACTION")}
    names = {obj.object_id: name for name, obj in scene.objects.items()}
    stages = {}

    def observe(label, original):
        def wrapped(*args, **kwargs):
            buffer = original(*args, **kwargs)
            stages[label] = int(dr.count(buffer.valid))
            return buffer
        return wrapped

    for name in ("_image_method", "_field_calculator"):
        setattr(solver, name, observe(name, getattr(solver, name)))

    rows = []
    for fi in bins:
        stages.clear()
        scene.frequency = float(freqs[fi])
        path = solver(scene, **cfg)
        tau = np.asarray(path.tau).ravel()
        count = len(tau)
        angles = [np.asarray(getattr(path, k)).ravel() for k in ("theta_t", "phi_t", "theta_r", "phi_r")]
        dirs = trace.P.path_directions(*angles)
        dtau = np.abs(tau - reference["tau_s"])
        ddir = np.linalg.norm(dirs - reference["directions"], axis=1)
        closest = int(np.argmin(ddir + 1e9 * dtau))
        mask = (ddir <= trace.ANGLE_TOL_RAD) & (dtau <= 2e-13)
        matched = np.flatnonzero(mask)
        coefficients = np.asarray(path.a[0]) + 1j * np.asarray(path.a[1])
        coeff = coefficients.reshape(2, 2, count)
        interactions = np.asarray(path.interactions).reshape(cfg["max_depth"], count)
        objects = np.asarray(path.objects).reshape(cfg["max_depth"], count)
        primitives = np.asarray(path.primitives).reshape(cfg["max_depth"], count)
        vertices = np.asarray(path.vertices).reshape(cfg["max_depth"], count, 3)
        items = []
        for index in matched:
            sequence = []
            for d in range(cfg["max_depth"]):
                event = int(interactions[d, index])
                if event == InteractionType.NONE:
                    continue
                obj_id = int(objects[d, index])
                name = names.get(obj_id, str(obj_id))
                sequence.append(dict(event=events.get(event, str(event)), object=name,
                                     primitive=int(primitives[d, index]), vertex_m=vertices[d, index].tolist()))
            items.append(dict(tau_s=float(tau[index]), iso_matrix_norm=float(np.linalg.norm(coeff[:, :, index])),
                              sequence=sequence))
        rows.append(dict(bin=fi, freq_hz=float(freqs[fi]), raw_count=count, stages=dict(stages),
                         near_match_delay_s=float(dtau[closest]), near_match_angle_norm=float(ddir[closest]),
                         matched=items))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tag")
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    t0 = time.monotonic()
    source = Path("/ref")
    input_dir = args.root / "input"
    trace, _, versions = load_runtime(source)
    ref = read(input_dir / "REFERENCE.json")
    for name, expected in ref["method_b_sha256"].items():
        if sha(source / name) != expected:
            raise ValueError(f"Method B input changed: {name}")
    gate = read(args.root / "analysis/G3.json")
    case = "G-T2_A"
    if not any(r["case"] == case and r["tag"] == args.tag for r in gate["pooled"]["unusable"]):
        raise ValueError(f"Tag was not a G3 failure: {args.tag}")

    trace_ref = {}
    for arm in ("bin_by_bin", "node_interpolation"):
        base = args.root / "output" / case / arm / f"{args.tag}_trace"
        n = base.with_name(base.name + ".npz")
        json_file = base.with_name(base.name + "_receipt.json")
        receipt = read(json_file)
        with np.load(n, allow_pickle=False) as raw:
            trace_ref[arm] = dict(receipt=receipt, data={k: raw[k] for k in raw.files},
                                  sha256=sha(n), receipt_sha256=sha(json_file))
    base = trace_ref["bin_by_bin"]
    index, = base["receipt"]["complex_paths"]
    raw = base["data"]
    tau = raw["tau"][index]
    dirs = trace.P.path_directions(*raw["ang"])[index]
    freqs = raw["node_freq_hz"]
    define = dict(tau_s=float(tau), directions=dirs)
    bins = sorted(set(range(136, 147)) | {128, 144})
    entry = read(input_dir / "scene/SCENE_MANIFEST.json")["geometries"]["G-T2"]
    for item in entry["material_bindings"]:
        if sha(input_dir / "scene" / item["ply"]) != item["ply_sha256"]:
            raise ValueError(f"G0 mesh changed: {item['ply']}")
    factory, loader = geometry_adapter(trace, entry, input_dir / "scene")
    setup = factory(anchor_x_m=7.0)
    scene, _ = loader(setup, None)
    rt, mi = trace.rt, trace.mi
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(), orientation=[0.0, 0.0, 0.0]))
    scene.add(rt.Receiver("rx", position=setup.robot_position(base["receipt"]["x"], base["receipt"]["y"]).tolist(),
                          orientation=[0.0, 0.0, 0.0]))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, rt.AntennaArray(trace.Ports([trace.IsoPort(0), trace.IsoPort(1)]),
                                             mi.Point3f(0, 0, 0)))
    cfg = ref["block_c_solver"]
    rows = solve_window(trace, setup, scene, rt.PathSolver(), cfg, freqs, define, bins)
    # Directly quantify the numerical effect from the recorded matrices. The all-bin
    # branch already contains Jones=0 at absent bins, so no missing coefficient is interpolated.
    # This diagnostic intentionally leaves the frozen G3 trace status and verdict intact.
    from qclean_uwb.drivesim.rf_store import h_for_antenna_yaws, load_banks
    from qclean_uwb.features.fp_power import signed_s_single_tx

    sample = next(t for t in read(input_dir / f"cases/{case}.json") if t["tag"] == args.tag)
    yaws = [r["yaw_deg"] for r in sample["sampled_yaws"]]
    banks = load_banks()
    dense = h_for_antenna_yaws(raw | {"status": "OK"}, banks, yaws)
    sparse_data = trace_ref["node_interpolation"]["data"]
    sparse = h_for_antenna_yaws(sparse_data | {"status": "OK"}, banks, yaws)
    metric_rows = []
    for item, hd, hs in zip(sample["sampled_yaws"], dense, sparse):
        sd, _, idense, td = signed_s_single_tx(hd, freqs)
        ss, _, isparse, ts = signed_s_single_tx(hs, freqs)
        metric_rows.append(dict(**item, abs_ds=abs(sd - ss), same_fp_index=idense == isparse,
                                range_diff_m=abs(td - ts) * 299792458,
                                h_rel_l2=float(np.linalg.norm(hd - hs) / np.linalg.norm(hd))))
    result = dict(kind="POST_HOC_DIAGNOSTIC", original_gate=gate["status"], case=case, tag=args.tag,
                  versions=versions, script_sha256=sha(Path(__file__)), gate_sha256=sha(args.root / "analysis/G3.json"),
                  frozen_trace={name: {k: data[k] for k in ("sha256", "receipt_sha256")}
                                for name, data in trace_ref.items()},
                  target_path_index=index, delay_ns=float(tau * 1e9),
                  dense_absent_bins=np.flatnonzero(~raw["present"][:, index]).tolist(),
                  sparse_nodes=sparse_data["node_bins"].tolist(), raw_solver_window=rows,
                  post_hoc_paired_rows=metric_rows, wall_s=time.monotonic()-t0)
    write(args.out, result)
    print(args.tag, [(r["bin"], len(r["matched"]), r["stages"]) for r in rows], flush=True)


if __name__ == "__main__":
    main()
