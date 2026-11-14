"""G3b: direct Method B nodes against the sealed F1 per-bin G3a raw traces."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

import run_tb3_g3 as g3
from run_tb3_g1_pilot import geometry_adapter, load_runtime


RUN = Path("/run_g3b")
REFERENCE = Path("/g3a")
INPUT = Path("/g3/input")
SOURCE = Path("/ref")
OUTPUT = RUN / "output"
CONFIG = RUN / "F1_SOLVER.json"
N_BINS = 257
NODES = np.arange(0, N_BINS, 16)
N_POSITIONS = 195
N_POSES = 5067
SHARDS = 4

G3A_SHA = {
    "G3A.json": "c50f1d325f3387841d3bb2995a6bd33f99505fa8696fbccfcb360dad0a39f386",
    "MANIFEST.json": "5f0fd8052aee05ef3c5e05a56c270b5fc8d25935926d7b755a83dc797f4ba140",
    "PREFLIGHT.json": "13e004f7fa2ca3f894a723a8fb7589c689b27c54739926ce3b4d848008235d77",
    "RAW_SHA256.txt": "7095c7805061a33a4a20e825b27408b2bf3d5224e352a2190d9a1af29f47ba7a",
}


def preflight():
    for name, digest in G3A_SHA.items():
        g3.verify(REFERENCE / name, digest)
    manifest = g3.read(REFERENCE / "MANIFEST.json")
    pre = g3.read(REFERENCE / "PREFLIGHT.json")
    result = g3.read(REFERENCE / "G3A.json")
    if (result["status"], result["completed_positions"], result["compared_bins"],
        result["invalid_bins"], result["mismatched_bins"]) != ("PASS", N_POSITIONS, N_POSITIONS*N_BINS, 0, 0):
        raise ValueError("G3a does not establish complete F1 reference coverage")

    for rel, digest in manifest["input_sha256"].items():
        g3.verify(INPUT / rel, digest)
    contract = g3.read(INPUT / "G3_CONTRACT.json")
    ref = g3.read(INPUT / "REFERENCE.json")
    if contract["arms"] != {"bin_by_bin": "all", "node_interpolation": "17"} or contract["mount_deg"] != 0:
        raise ValueError("G3 sample contract changed")
    for rel, digest in (ref["method_b_sha256"] | contract["source_sha256"]).items():
        g3.verify(SOURCE / rel, digest)
    for bank in g3.read(INPUT / "FFD_RESTORE_MANIFEST.json")["banks"]:
        g3.verify(SOURCE / bank["filename"], bank["sha256"])
    g3.verify(INPUT / "parity_gate.py", contract["parity_sha256"])
    meshes = g3.read(INPUT / "scene/SCENE_MANIFEST.json")["geometries"]
    for entry in meshes.values():
        for item in entry["material_bindings"]:
            g3.verify(INPUT / "scene" / item["ply"], item["ply_sha256"])

    trace, _, versions = load_runtime(SOURCE)
    solver = ref["block_c_solver"] | {"refraction": False}
    if solver != pre["solver"] or versions != pre["versions"] or ref["image"] != manifest["container_image"]:
        raise ValueError("F1 solver or runtime differs from G3a")
    freq = np.asarray(trace.C.load_banks()[0]["freqs_hz"])
    if not np.array_equal(freq, pre["freqs_hz"]) or trace.node_bins(len(freq), "17") != NODES.tolist():
        raise ValueError("Frequency grid changed")
    thresholds = {
        key: item["value"] for key, item in
        g3.read(SOURCE / contract["prereg_path"])["config"]["gates"][contract["threshold_key"]].items()
    }
    if thresholds != {"abs_ds_max": 0.002, "fp_index_match_min": 0.995, "range_diff_max_m": 0.002}:
        raise ValueError("Gate thresholds differ from RT v1.1")

    checksums = {}
    for line in (REFERENCE / "RAW_SHA256.txt").read_text().splitlines():
        digest, rel = line.split(maxsplit=1)
        if rel in checksums:
            raise ValueError(f"Duplicate G3a checksum: {rel}")
        checksums[rel] = digest
    expected = set()
    pose_count = 0
    for case, counts in contract["cases"].items():
        tasks = g3.read(INPUT / f"cases/{case}.json")
        poses = [p["pose_id"] for task in tasks for p in task["sampled_yaws"]]
        if (len(tasks) != counts["trace_positions"] or len({t["tag"] for t in tasks}) != len(tasks)
                or len(poses) != counts["poses"] or len(set(poses)) != len(poses)):
            raise ValueError(f"Frozen sample cardinality mismatch: {case}")
        pose_count += len(poses)
        expected.update(f"raw/{case}/{task['tag']}.{ext}" for task in tasks for ext in ("json", "npz"))
    if expected != checksums.keys() or len(expected) != 2*N_POSITIONS or pose_count != N_POSES:
        raise ValueError("G3a digests or G3b samples have incomplete coverage")
    for rel, digest in checksums.items():
        g3.verify(REFERENCE / rel, digest)

    g3.write(CONFIG, {"solver": solver})
    g3.write(RUN / "MANIFEST.json", dict(
        question_id="G1-RT-TB3-001", stage="G3b", role="IMPLEMENTER",
        branch=manifest["branch"], frozen_spec_commit=manifest["frozen_spec_commit"],
        frozen_spec_blob=manifest["frozen_spec_blob"], governance=manifest["governance"],
        execution_site="Snowball KMS", runtime_versions=versions, container_image=ref["image"],
        method_b_commit=ref["method_b_commit"], parity_sha256=contract["parity_sha256"],
        evaluator_sha256=g3.sha(Path(g3.__file__)), runner_sha256=g3.sha(Path(__file__)),
        launch_sha256=g3.sha(RUN / "launch.sh"), contract_sha256=g3.sha(INPUT / "G3_CONTRACT.json"),
        g3a_sha256=G3A_SHA, f1=solver, positions=N_POSITIONS, poses=N_POSES,
        base_node_bins=NODES.tolist(), thresholds=thresholds, shards_per_case=SHARDS,
        reference_conversion="F1 G3a raw per-bin ISO Jones assembled with frozen rf_b_trace._assemble",
    ))
    for case in contract["cases"]:
        for shard in range(SHARDS):
            print(case, f"{shard}/{SHARDS}")


def trace_shard(case, shard):
    trace, _, _ = load_runtime(SOURCE)
    geom, anchor = case.split("_")
    scene = g3.read(INPUT / "scene/SCENE_MANIFEST.json")["geometries"][geom]
    anchor_xyz = scene["anchors_xyz_m"][anchor]
    entry = dict(scene, anchors_xyz_m={"A": anchor_xyz})
    trace.CorridorSetup, trace.C.build_scene = geometry_adapter(trace, entry, INPUT / "scene")
    trace.C.SOLVER_SOURCE = CONFIG
    sys.argv = [trace.__file__, "--tasks", str(INPUT / "cases" / f"{case}.json"),
                "--out", str(OUTPUT / case / "node_interpolation"), "--nodes", "17",
                "--threads", "1", "--anchor-x", str(anchor_xyz[0]), "--shard", shard]
    trace.main()


def materialize_reference(trace, case, task, freq, solver):
    tag = task["tag"]
    source = REFERENCE / "raw" / case
    receipt = g3.read(source / f"{tag}.json")
    raw_path = source / f"{tag}.npz"
    xy = [task["x"], task["y"]]
    if (receipt["case"], receipt["tag"], receipt["task_id"], receipt["xy"], receipt["sampled_yaws"],
        receipt["solver"], receipt["bin_count"]) != (
            case, tag, task["task_id"], xy, task["sampled_yaws"], solver, N_BINS):
        raise ValueError(f"Unexpected G3a receipt: {case}/{tag}")
    bins = list(range(N_BINS))
    with np.load(raw_path, allow_pickle=False) as z:
        edges, iso, tau, ang = z["bin_offsets"], z["jones_iso"], z["tau"].astype(float), z["ang"].astype(float)
        if (not np.array_equal(z["node_bins"], bins) or not np.array_equal(z["node_freq_hz"], freq)
                or (float(z["x"]), float(z["y"]), int(z["task_id"])) != (*xy, task["task_id"])
                or edges.shape != (N_BINS+1,) or edges[0] != 0 or edges[-1] != len(tau)
                or not np.all(np.diff(edges) > 0) or iso.shape != (2, 2, len(tau)) or ang.shape != (4, len(tau))
                or not all(np.isfinite(arr).all() for arr in (iso, tau, ang))):
            raise ValueError(f"Unexpected G3a raw trace: {case}/{tag}")
    raw = {}
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        raw[i] = iso[:, :, lo:hi], tau[lo:hi], ang[:, lo:hi]
    delays, angles, _, jones, _, present = trace._assemble(raw, bins)
    status = "OK" if present.all() else "REFERENCE_METHOD_B_PATH_MATCH_INCOMPLETE"
    out = OUTPUT / case / "bin_by_bin"
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / f"{tag}_trace.npz", jones=jones, tau=delays, ang=np.array(angles),
                        node_bins=bins, node_freq_hz=freq, x=xy[0], y=xy[1], status=status, present=present)
    g3.write(out / f"{tag}_trace_receipt.json", dict(
        tag=tag, status=status, n_nodes=N_BINS, elapsed_s=receipt["elapsed_s"], unmatched_paths=0,
        screen_exceeded=False, source_raw_sha256=receipt["raw_sha256"], actual_new_solves=0,
    ))


def evaluate():
    started = time.monotonic()
    contract = g3.read(INPUT / "G3_CONTRACT.json")
    manifest = g3.read(RUN / "MANIFEST.json")
    ref_start = time.monotonic()
    trace, _, _ = load_runtime(SOURCE)
    freq = np.asarray(trace.C.load_banks()[0]["freqs_hz"])
    solver = manifest["f1"]
    counts = []
    for case in contract["cases"]:
        tasks = g3.read(INPUT / f"cases/{case}.json")
        out = OUTPUT / case / "node_interpolation"
        if {p.name for p in out.glob("*_trace.npz")} != {f"{t['tag']}_trace.npz" for t in tasks}:
            raise ValueError(f"Unexpected direct trace coverage: {case}")
        for task in tasks:
            tag = task["tag"]
            node = g3.read(out / f"{tag}_trace_receipt.json")
            with np.load(out / f"{tag}_trace.npz", allow_pickle=False) as z:
                indices = z["node_bins"]
                if (node["tag"] != tag or node["solver"] != solver or node["runner_sha256"] != g3.sha(Path(trace.__file__))
                        or node["pathsolver_calls"] != len(indices) or not np.isin(NODES, indices).all()
                        or np.any(np.diff(indices) <= 0) or not np.array_equal(z["node_freq_hz"], freq[indices])):
                    raise ValueError(f"Direct node trace setting or frequency mismatch: {case}/{tag}")
            counts.append(node["pathsolver_calls"])
            materialize_reference(trace, case, task, freq, solver)
    assembly_s = time.monotonic() - ref_start

    report_dir = RUN / "analysis"
    report_dir.mkdir()
    g3.INPUT, g3.SOURCE, g3.OUT = INPUT, SOURCE, OUTPUT
    result = g3.evaluate(contract, INPUT / "parity_gate.py", report_dir)
    completed = result["pooled"].get("n_poses", 0)
    if completed > N_POSES or (completed != N_POSES and result["status"] == "PASS"):
        raise ValueError("Impossible G3b coverage")
    result.update(
        question_id=manifest["question_id"], stage="G3b", expected_comparisons=N_POSES,
        completed_comparisons=completed, direct_trace_positions=len(counts),
        direct_trace_calls=sum(counts), adaptive_extra_calls=sum(counts) - len(NODES)*N_POSITIONS,
        reused_reference_trace_calls=N_POSITIONS*N_BINS,
        trace_wall_s=float((RUN / "TRACE_WALL_S.txt").read_text().strip()),
        reference_assembly_s=assembly_s, evaluation_wall_s=time.monotonic()-started,
        manifest_sha256=g3.sha(RUN / "MANIFEST.json"),
    )
    g3.write(RUN / "G3B.json", result)
    print(json.dumps({k: v for k, v in result["pooled"].items() if k != "worst_by_abs_ds"}), flush=True)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    if mode == "preflight":
        preflight()
    elif mode == "trace":
        trace_shard(*args)
    elif mode == "evaluate":
        sys.exit(evaluate())
    else:
        raise ValueError(f"Unknown mode: {mode}")
