"""Run the G1 pilot with G0 meshes and the pinned Method B installation."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import resource
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def prepare(inputs, out, source):
    g0 = read(inputs / "RUN_MANIFEST.json")
    for name, digest in g0["output_sha256"].items():
        if (inputs / name).is_file() and sha(inputs / name) != digest:
            raise ValueError(f"G0 checksum mismatch: {name}")
    gate = read(inputs / "gates/G0.json")
    if gate["status"] != "PASS" or gate["violation_count"]:
        raise ValueError("G0 gate did not pass")
    case = inputs / "poses/G-T1_A"
    scene = read(inputs / "scene/SCENE_MANIFEST.json")["geometries"]["G-T1"]
    for binding in scene["material_bindings"]:
        path = inputs / "scene" / binding["ply"]
        if sha(path) != binding["ply_sha256"] or sha(path) != g0["output_sha256"][f"scene/{binding['ply']}"]:
            raise ValueError(f"G0 mesh mismatch: {path}")
    rows = read(case / "SAMPLES.json")
    stations = ("P001", "P002", "P003")
    sets = ("P-A_TEACH", "P-A_REPEAT")
    selected = [r for r in rows if r["set"] in sets and r["station_id"] in stations]
    if {(r["set"], r["station_id"]) for r in selected} != {(s, p) for s in sets for p in stations}:
        raise ValueError("Pilot station selection is incomplete")
    original_ids = sorted({r["pose_id"] for r in selected})
    new_ids = {old: i for i, old in enumerate(original_ids)}
    poses = [dict(p, pose_id=new_ids[p["pose_id"]], g0_pose_id=p["pose_id"])
             for p in read(case / "rf_poses.json") if p["pose_id"] in new_ids]
    tasks = []
    for t in read(case / "rf_tasks.json"):
        ids = [new_ids[i] for i in t["pose_ids"] if i in new_ids]
        if ids:
            tasks.append(dict(t, task_id=len(tasks), g0_task_id=t["task_id"], pose_ids=ids,
                              antenna_yaw_deg=sorted({poses[i]["yaw_body_deg"] for i in ids})))
    if len(tasks) != 6 or sorted(i for t in tasks for i in t["pose_ids"]) != list(range(len(poses))):
        raise ValueError("Expected six trace locations covering the pilot poses")
    for filename, data in (("rf_poses.json", poses), ("rf_tasks.json", tasks), ("SAMPLES.json", selected)):
        write(out / filename, data)

    reference = read(inputs / "REFERENCE.json")
    for name, digest in reference["method_b_sha256"].items():
        if sha(source / name) != digest:
            raise ValueError(f"Reference implementation checksum mismatch: {name}")
    for bank in read(inputs / "FFD_RESTORE_MANIFEST.json")["banks"]:
        if sha(source / bank["filename"]) != bank["sha256"]:
            raise ValueError(f"FFD original checksum mismatch: {bank['filename']}")
    if read(source / reference["solver_path"])["solver"] != reference["block_c_solver"]:
        raise ValueError("Full trace solver settings differ from BLOCK_C receipts")
    return scene, poses, tasks, selected, gate, reference


def load_runtime(source):
    sys.path[:0] = [str(source / "scripts/drive_sim"), str(source / "scripts"), str(source / "src")]
    import drjit as dr
    import numpy as np
    import rf_b_trace as trace

    dr.set_thread_count(1)
    versions = {p: importlib.metadata.version(p) for p in ("sionna-rt", "mitsuba", "drjit", "numpy")}
    if {k: versions[k] for k in ("sionna-rt", "mitsuba", "drjit")} != {
        "sionna-rt": "2.0.1", "mitsuba": "3.8.0", "drjit": "1.3.1"
    }:
        raise ValueError(f"Unexpected RT package versions: {versions}")
    return trace, np, versions


def geometry_adapter(trace, scene_entry, scene_root):
    core, rt = trace.C, trace.rt
    length, width, height = scene_entry["dimensions_m"]
    ax, ay, az = scene_entry["anchors_xyz_m"]["A"]

    def setup(**kwargs):
        if kwargs != {"anchor_x_m": ax}:
            raise ValueError("Only the frozen pilot anchor is allowed")
        return core.CorridorSetup(length_m=length, width_m=width, height_m=height,
                                  anchor_x_m=ax, anchor_y_m=ay, anchor_standoff_m=height-az,
                                  robot_antenna_z_m=scene_entry["rx_z_m"])

    def load_scene(setup, destination):
        scene = rt.load_scene()
        bindings = scene_entry["material_bindings"]
        objects = []
        for item in bindings:
            name = item["object"]
            material = rt.ITURadioMaterial(name="rm_" + name, itu_type=item["itu_type"],
                                           thickness=item["thickness_m"])
            objects.append(rt.SceneObject(fname=str(scene_root / item["ply"]), name=name,
                                          radio_material=material))
        scene.edit(add=objects)
        return scene, bindings

    return setup, load_scene


def run_full(trace, setup, load_scene, out, anchor_x):
    trace.CorridorSetup = setup
    trace.C.build_scene = load_scene
    original = sys.argv
    sys.argv = [str(Path(trace.__file__)), "--tasks", str(out / "rf_tasks.json"),
                "--out", str(out / "trace"), "--nodes", "17", "--threads", "1",
                "--anchor-x", str(anchor_x)]
    try:
        t0 = time.monotonic()
        trace.main()
        return time.monotonic() - t0
    finally:
        sys.argv = original


def run_los(trace, np, setup, load_scene, poses, out):
    """Evaluate all 257 bins with the original BLOCK_C direct LoS path."""
    C, rt = trace.C, trace.rt
    cfg = dict(max_depth=0, los=True, specular_reflection=False, refraction=False,
               diffuse_reflection=False, diffraction=False, seed=42)
    t0 = time.monotonic()
    scene, _ = load_scene(setup, None)
    banks = C.load_banks()
    freqs = banks[0]["freqs_hz"]
    txp, rxp = C.make_ports(banks)
    scene.add(rt.Transmitter("tx", position=setup.anchor_position.tolist(),
                             orientation=C.euler(C.ANCHOR_ROTATION)))
    for i, p in enumerate(poses):
        scene.add(rt.Receiver(f"rx_{i}", position=setup.robot_position(p["x"], p["y"]).tolist(),
                              orientation=C.euler(setup.robot_rotation(p["yaw_body_deg"]))))
    solver = rt.PathSolver()
    shape = (len(poses), len(freqs))
    coeff = np.empty((*shape, 2, 2), dtype=np.complex128)
    h = np.empty_like(coeff)
    tau = np.empty(shape)
    angles = {name: np.empty(shape) for name in ("theta_t", "phi_t", "theta_r", "phi_r")}
    counts = np.ones(shape, dtype=int)
    for fi, f in enumerate(freqs):
        C.set_bin(scene, banks, txp, rxp, fi, f)
        paths = solver(scene, **cfg)
        a = (np.asarray(paths.a[0]) + 1j * np.asarray(paths.a[1])).reshape(len(poses), 2, 2, -1)
        delay = np.asarray(paths.tau).reshape(len(poses), -1)
        if a.shape[-1] != 1 or delay.shape[1] != 1 or np.any(delay < 0):
            raise ValueError(f"Expected one valid direct path at bin {fi}")
        coeff[:, fi] = a[:, :, :, 0]
        tau[:, fi] = delay[:, 0]
        h[:, fi] = (a * np.exp(-2j * np.pi * f * delay)[:, None, None, :]).sum(-1)
        for name in angles:
            angles[name][:, fi] = np.asarray(getattr(paths, name)).reshape(len(poses), -1)[:, 0]
        if fi % 64 == 0:
            print(f"LoS bin {fi + 1}/{len(freqs)}", flush=True)
    if not all(np.isfinite(a).all() for a in [h, tau, *angles.values()]):
        raise ValueError("Non-finite LoS output")
    np.save(out / "H_LoS.npy", h)
    np.savez_compressed(out / "PATHS_LoS.npz", a=coeff, tau=tau, counts=counts,
                        interactions=np.zeros_like(counts), **angles, freqs_hz=freqs)
    return dict(wall_s=time.monotonic() - t0, solver=cfg, bins=len(freqs),
                frequency_hz=[float(freqs[0]), float(freqs[-1])], paths_per_pose_bin=1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    start = datetime.now(timezone.utc).isoformat()
    args.out.mkdir(exist_ok=False)
    scene, poses, tasks, rows, gate, reference = prepare(args.inputs, args.out, args.source)
    trace, np, versions = load_runtime(args.source)
    anchor_x = scene["anchors_xyz_m"]["A"][0]
    setup, load_scene = geometry_adapter(trace, scene, args.inputs / "scene")
    wall_trace = run_full(trace, setup, load_scene, args.out, anchor_x)
    trace_stats = []
    for t in tasks:
        stem = f"{t['tag']}_trace"
        npz = args.out / "trace" / f"{stem}.npz"
        receipt = args.out / "trace" / f"{stem}_receipt.json"
        result = read(receipt)
        with np.load(npz) as z:
            if str(z["status"]) != result["status"] or not np.isfinite(z["jones"]).all():
                raise ValueError(f"Invalid trace output: {npz}")
        trace_stats.append({k: result[k] for k in (
            "tag", "status", "elapsed_s", "n_paths", "pathsolver_calls", "screen_exceeded",
            "max_dropped_rel_amp", "unmatched_paths")} | {
                "trace_bytes": npz.stat().st_size, "receipt_bytes": receipt.stat().st_size})

    usable = all(s["status"] == "OK" for s in trace_stats)
    apply_s = None
    if usable:
        begin = time.monotonic()
        subprocess.run([sys.executable, str(args.source / "scripts/drive_sim/rf_b_apply.py"),
                        "--poses", str(args.out / "rf_poses.json"), "--traces", str(args.out / "trace"),
                        "--mount", "0", "--out", str(args.out / "H_full.npy")],
                       check=True, cwd=args.source)
        apply_s = time.monotonic() - begin
        h = np.load(args.out / "H_full.npy", mmap_mode="r")
        if h.shape != (len(poses), 257, 2, 2) or not np.isfinite(h).all():
            raise ValueError("Invalid full-H output")
    los = run_los(trace, np, setup(anchor_x_m=anchor_x), load_scene, poses, args.out)
    write(args.out / "G1.json", dict(question_id="G1-RT-TB3-001", role="IMPLEMENTER",
          gate="G1", status="PASS" if usable else "TRACE_UNUSABLE", started_utc=start,
          finished_utc=datetime.now(timezone.utc).isoformat(), command=[sys.executable, *sys.argv],
          host="Snowball", cpu_workers=1, image=reference["image"], versions=versions,
          method_b_commit=reference["method_b_commit"], full_solver=reference["block_c_solver"],
          g0_manifest_sha256=sha(args.inputs / "RUN_MANIFEST.json"),
          input_sha256={p.relative_to(args.inputs).as_posix(): sha(p)
                        for p in sorted(args.inputs.rglob("*")) if p.is_file()},
          scope=dict(geometry="G-T1", anchor="A", stations=["P001", "P002", "P003"],
                     sets=["P-A_TEACH", "P-A_REPEAT"], positions=len(tasks), poses=len(poses),
                     observations=len(rows)),
          trace_wall_s=wall_trace, trace=trace_stats, apply_wall_s=apply_s, los=los,
          peak_python_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
          g0_totals=dict(cases=len(gate["cases"]), positions=sum(c["trace_positions"] for c in gate["cases"].values()),
                         poses=sum(c["rf_poses"] for c in gate["cases"].values())),
          outputs={p.relative_to(args.out).as_posix(): dict(bytes=p.stat().st_size, sha256=sha(p))
                   for p in sorted(args.out.rglob("*")) if p.is_file()}))
    print(f"G1 {'PASS' if usable else 'TRACE_UNUSABLE'}", flush=True)
    return 0 if usable else 2


if __name__ == "__main__":
    raise SystemExit(main())
