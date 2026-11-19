"""Check two in-between frequency bins per production trace position."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from run_tb3_g1_pilot import geometry_adapter, load_runtime, read, sha, write


def choose_bins(case, tag, node_bins, bin_count, seed):
    import numpy as np

    key = f"{seed}/{case}/{tag}".encode()
    entropy = int.from_bytes(hashlib.sha256(key).digest()[:16], "big")
    interior = np.setdiff1d(np.arange(bin_count), node_bins)
    return sorted(np.random.default_rng(entropy).choice(interior, size=2, replace=False).tolist())


def check_bins(trace, np, scene, solver, cfg, freqs, data, bins):
    node_bins = data["node_bins"]
    present = data["present"]
    reference_tau = data["tau"]
    reference_dirs = trace.P.path_directions(*data["ang"])
    if present.shape != (len(node_bins), len(reference_tau)) or not present.any(axis=0).all():
        raise ValueError("Invalid production path presence mask")
    # This is the support used by interp_jones, including any bisection nodes.
    first = node_bins[present.argmax(axis=0)]
    last = node_bins[len(node_bins) - 1 - present[::-1].argmax(axis=0)]
    rows = []
    for fi in bins:
        coeffs, tau, angles = trace._solve(scene, solver, cfg, freqs, fi)
        expected = np.flatnonzero((first <= fi) & (fi <= last))
        match, extra = trace.P.match_partial(reference_tau[expected], reference_dirs[expected],
                                             tau, trace.P.path_directions(*angles),
                                             tol=trace.ANGLE_TOL_RAD)
        missing = expected[match < 0]
        amps = np.linalg.norm(coeffs, axis=(0, 1))
        total = np.linalg.norm(amps)
        rows.append(dict(bin=fi, freq_hz=float(freqs[fi]), expected_count=len(expected), traced_count=len(tau),
                         missing=[dict(path_index=int(i), delay_ns=float(reference_tau[i] * 1e9)) for i in missing],
                         extra=[dict(delay_ns=float(tau[i] * 1e9),
                                     relative_amp=float(amps[i] / total) if total > 0 else 0.0) for i in extra]))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True, help="G0 scene and pinned REFERENCE.json")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--case", required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--traces", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--audit-seed", type=int, default=20261113)
    parser.add_argument("--bins", type=int, nargs=2, help="Explicit bins for a targeted diagnostic")
    args = parser.parse_args()

    trace, np, versions = load_runtime(args.source)
    ref = read(args.inputs / "REFERENCE.json")
    for name, digest in ref["method_b_sha256"].items():
        if sha(args.source / name) != digest:
            raise ValueError(f"Method B input changed: {name}")
    geom, anchor = args.case.split("_")
    root = args.inputs / "scene"
    scene_manifest = root / "SCENE_MANIFEST.json"
    entry = read(scene_manifest)["geometries"][geom]
    for item in entry["material_bindings"]:
        if sha(root / item["ply"]) != item["ply_sha256"]:
            raise ValueError(f"G0 mesh changed: {item['ply']}")
    entry = dict(entry, anchors_xyz_m={"A": entry["anchors_xyz_m"][anchor]})
    factory, loader = geometry_adapter(trace, entry, root)
    setup = factory(anchor_x_m=entry["anchors_xyz_m"]["A"][0])
    scene, _ = loader(setup, None)
    scene.add(trace.rt.Transmitter("tx", position=setup.anchor_position.tolist()))
    scene.add(trace.rt.Receiver("rx", position=setup.robot_position(*setup.example_xy_m[0]).tolist()))
    for field in ("tx_array", "rx_array"):
        setattr(scene, field, trace.rt.AntennaArray(trace.Ports([trace.IsoPort(0), trace.IsoPort(1)]),
                                                    trace.mi.Point3f(0, 0, 0)))
    cfg = ref["block_c_solver"]
    if read(args.source / ref["solver_path"])["solver"] != cfg:
        raise ValueError("Production solver differs from BLOCK_C")
    banks = trace.C.load_banks()
    freqs = banks[0]["freqs_hz"]
    if len(freqs) != 257:
        raise ValueError("Expected the 257-bin production grid")
    solver = trace.rt.PathSolver()
    tasks = read(args.tasks)
    if not tasks or len({task["tag"] for task in tasks}) != len(tasks):
        raise ValueError("Expected nonempty tasks with unique position tags")
    positions = {}
    for task in tasks:
        tag, x, y = task["tag"], task["x"], task["y"]
        path = args.traces / f"{tag}_trace.npz"
        receipt_path = path.with_name(f"{path.stem}_receipt.json")
        receipt = read(receipt_path)
        if receipt["solver"] != cfg or receipt["status"] != "OK" or receipt["tag"] != tag:
            raise ValueError(f"Unexpected production trace receipt: {tag}")
        with np.load(path, allow_pickle=False) as data:
            node_bins = data["node_bins"]
            if (str(data["status"]) != "OK" or float(data["x"]) != x or float(data["y"]) != y
                    or not np.isin(np.arange(0, 257, 16), node_bins).all()
                    or not np.array_equal(freqs[node_bins], data["node_freq_hz"])
                    or not np.all(np.diff(node_bins) > 0)):
                raise ValueError(f"Unexpected production trace: {tag}")
            bins = args.bins or choose_bins(args.case, tag, node_bins, len(freqs), args.audit_seed)
            if len(set(bins)) != 2 or any(fi <= 0 or fi >= len(freqs) - 1 or fi in node_bins for fi in bins):
                raise ValueError(f"Expected two distinct in-between bins: {tag}")
            scene.receivers["rx"].position = trace.mi.Point3f(*setup.robot_position(x, y).tolist())
            rows = check_bins(trace, np, scene, solver, cfg, freqs, data, bins)
        positions[tag] = dict(trace_sha256=sha(path), receipt_sha256=sha(receipt_path), rows=rows)
    flagged = [tag for tag, value in positions.items() if any(r["missing"] or r["extra"] for r in value["rows"])]
    write(args.out, dict(kind="PRODUCTION_IN_BETWEEN_BIN_CHECK", case=args.case, solver=cfg, versions=versions,
                         runner_sha256=sha(Path(__file__)), scene_sha256=sha(scene_manifest), tasks_sha256=sha(args.tasks),
                         reference_sha256=sha(args.inputs / "REFERENCE.json"),
                         audit_seed=args.audit_seed, explicit_bins=args.bins, positions=positions,
                         flagged_positions=flagged))
    print(f"{args.case}: {len(flagged)}/{len(positions)} positions flagged", flush=True)


if __name__ == "__main__":
    main()
