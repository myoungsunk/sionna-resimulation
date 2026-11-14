"""G2b: report the F1 signed-s deltas on the original BLOCK_C G2 poses."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import run_tb3_g2 as g2
from run_tb3_g1_pilot import load_runtime, read, sha, write


RUN = Path("/run-g2")
OLD = Path("/g2")
G3C = Path("/g3c")
SOLVER = RUN / "F1_SOLVER.json"
G2_DIGESTS = {
    "input/G2_CONTRACT.json": "b4018f634dbca93336c219f0bcc060d00427d0eb935a302ca33fcdcc4c928f36",
    "input/REFERENCE.json": "1f0b9082a8b5fbf8aa43ebdb585808f3b288b49efe2db25dd56944e471199252",
    "input/run_tb3_g2.py": "e276fe8904ce5740522640084312fdefe3ff3ab7339c002e9e351e8d92a1cc34",
    "input/run_tb3_g1_pilot.py": "a8b086875196bbb778e68cd2821be08cd72fc34f83d0ef0fd116e3baa59dacf2",
    "input/FFD_RESTORE_MANIFEST.json": "0017f2171da5d3729e4ad91d0d44384937d83213640c347ff12dda53e763a96e",
    "output/G2.json": "125fdb677f80b34171bc30410465bd6a791f609f9f6cf61d75649c88252f7fd2",
    "output/H_reference_50.npy": "07bbb236fdc96e50b4a5f9d51e15db64f05c50630e3f67e61d4b08831d3d887f",
    "output/rf_poses.json": "4d1aff71ef44e38390b1b46f2c915356e4ce1e9ec4d379615dbcb3c11d683de4",
    "output/rf_tasks.json": "d47d52716174b3703828e932e86543fa25a0e3eeb41bd2d7356ace5ad46d2ac1",
    "output/scene.json": "8051ec74791f6f7d304d63e528b5fdae217b50eabfed46aa599ecc06d712a035",
}
G3C_MANIFEST_SHA = "e6357c87f5ef50cf22fbf94fc52bb19789eaafc8bacdae2aabdec4a8f9be558b"
FP_SOURCE = "src/qclean_uwb/features/fp_power.py"
FP_SHA = "6da23ff66372a106dfbea521cc176031169210fed226e38d7d2db55b21f7c86b"
NODES = np.arange(0, 257, 16)


def load_f1_runtime(source):
    trace, np_module, versions = load_runtime(source)
    trace.C.SOLVER_SOURCE = SOLVER
    return trace, np_module, versions


def verify_inputs(config):
    for rel, digest in G2_DIGESTS.items():
        g2.verify(OLD / rel, digest)
    g2.verify(G3C / "MANIFEST.json", G3C_MANIFEST_SHA)
    g2.verify(g2.SOURCE / FP_SOURCE, FP_SHA)
    historical = read(OLD / "output/G2.json")
    if (historical["status"], historical["bitwise_equal"], historical["poses"]) != ("PASS", True, 50):
        raise ValueError("The original G2 result does not establish the comparison baseline")
    ref = read(g2.INPUT / "REFERENCE.json")
    validated = read(G3C / "MANIFEST.json")
    solver = ref["block_c_solver"] | {"refraction": False}
    _, _, versions = load_runtime(g2.SOURCE)
    if (solver != validated["solver_100k"] or versions != validated["runtime_versions"]
            or ref["image"] != validated["container_image"] or solver["samples_per_src"] != 100_000):
        raise ValueError("G2b does not match the F1 settings validated in G3")

    original = np.load(g2.BLOCK / "FULL_RF/H_R2_aA_m0.npy", mmap_mode="r", allow_pickle=False)
    h_ref = np.load(OLD / "output/H_reference_50.npy", allow_pickle=False)
    if (original.shape != tuple(config["reference_shape"]) or h_ref.shape != (50, 257, 2, 2)
            or original.dtype != h_ref.dtype or h_ref.dtype != np.complex128
            or not np.isfinite(h_ref).all() or original[config["block_pose_ids"]].tobytes() != h_ref.tobytes()):
        raise ValueError("G2 reference subset differs from the original H")
    return ref, validated, solver, versions, h_ref


def trace_all(tasks, workers, solver, freqs, versions):
    def execute(worker):
        with (g2.OUT / f"shard_{worker}.log").open("x") as log:
            return subprocess.run(["nice", "-n", "5", sys.executable, "-u", __file__, f"{worker}/{workers}"],
                                  stdout=log, stderr=subprocess.STDOUT, check=False).returncode

    with ThreadPoolExecutor(max_workers=workers) as pool:
        codes = list(pool.map(execute, range(workers)))
    write(g2.OUT / "SHARD_EXIT.json", codes)
    if any(codes):
        raise RuntimeError(f"Trace shard exit codes: {codes}")
    seen = set()
    calls = 0
    for task in tasks:
        tag = task["tag"]
        prefix = g2.OUT / "trace" / f"{tag}_trace"
        receipt = read(prefix.with_name(prefix.name + "_receipt.json"))
        with np.load(prefix.with_name(prefix.name + ".npz"), allow_pickle=False) as trace:
            nodes = trace["node_bins"]
            if (receipt["tag"] != tag or receipt["status"] != "OK" or str(trace["status"]) != "OK"
                    or receipt["solver"] != solver
                    or receipt["versions"] != {k: v for k, v in versions.items() if k != "numpy"}
                    or receipt["n_nodes"] != len(nodes) or receipt["pathsolver_calls"] != len(nodes)
                    or not np.isin(NODES, nodes).all() or np.any(np.diff(nodes) <= 0)
                    or not np.array_equal(trace["node_freq_hz"], freqs[nodes])
                    or not np.isfinite(trace["jones"]).all()
                    or (float(trace["x"]), float(trace["y"])) != (task["x"], task["y"])):
                raise ValueError(f"Invalid F1 trace for {tag}")
        seen.add(prefix.name)
        calls += receipt["pathsolver_calls"]
    if {p.stem for p in (g2.OUT / "trace").glob("*_trace.npz")} != seen:
        raise ValueError("Unexpected F1 trace coverage")
    return calls


def compare(h_f1, h_ref, poses, freqs):
    from qclean_uwb.features.fp_power import signed_s_single_tx
    rows = []
    for pose, candidate, reference in zip(poses, h_f1, h_ref, strict=True):
        s_ref, _, index_ref, _ = signed_s_single_tx(reference, freqs, tx=0)
        s_f1, _, index_f1, _ = signed_s_single_tx(candidate, freqs, tx=0)
        rows.append(dict(block_pose_id=pose["block_pose_id"], yaw_deg=pose["yaw_body_deg"],
                         s_reference=s_ref, s_f1=s_f1, abs_delta_s=abs(s_f1-s_ref),
                         first_path_index_reference=index_ref, first_path_index_f1=index_f1))
    values = np.array([row["abs_delta_s"] for row in rows])
    if not np.isfinite(values).all() or len(values) != 50:
        raise ValueError("Incomplete or invalid signed-s comparison")
    p = np.quantile(values, [0, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1], method="linear")
    stats = {k: float(v) for k, v in zip(("min", "p25", "median", "p75", "p90", "p95", "p99", "max"), p)}
    stats.update(mean=float(values.mean()), rms=float(np.sqrt(np.mean(values**2))),
                 exactly_zero=int((values == 0).sum()))
    return rows, stats


def main():
    t0 = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()
    g2.OUT.mkdir(exist_ok=False)
    config = read(g2.INPUT / "G2_CONTRACT.json")
    tasks = g2.prepare(config)
    ref, f1_record, solver, versions, h_ref = verify_inputs(config)
    for name in ("scene.json", "rf_poses.json", "rf_tasks.json"):
        g2.verify(g2.OUT / name, G2_DIGESTS[f"output/{name}"])
    poses = read(g2.OUT / "rf_poses.json")
    if [r["block_pose_id"] for r in poses] != config["block_pose_ids"]:
        raise ValueError("Pose order changed")
    write(SOLVER, dict(solver=solver))
    (g2.OUT / "H_reference_50.npy").write_bytes((OLD / "output/H_reference_50.npy").read_bytes())
    from qclean_uwb.drivesim.rf_store import load_banks
    freqs = load_banks()[0].freqs_hz
    manifest = dict(
        question_id="G1-RT-TB3-001", stage="G2b", case=config["case"], role="IMPLEMENTER",
        branch=f1_record["branch"], frozen_spec_commit=f1_record["frozen_spec_commit"],
        frozen_spec_blob=f1_record["frozen_spec_blob"], governance=f1_record["governance"],
        method_b_commit=ref["method_b_commit"], runtime_versions=versions, container_image=ref["image"],
        g2_sha256=G2_DIGESTS, f1_reference_manifest_sha256=G3C_MANIFEST_SHA, fp_source_sha256=FP_SHA,
        runner_sha256=sha(Path(__file__)), launch_sha256=sha(RUN / "launch.sh"), solver=solver,
        workers=config["workers"], node_bins=NODES.tolist(), mount_deg=0, block_pose_ids=config["block_pose_ids"],
        metric="|signed_s_single_tx(H_F1, tx=0) - signed_s_single_tx(H_BLOCK_C, tx=0)|",
        quantiles="Linear quantiles over the 50 paired poses", numerical_gate=None,
    )
    write(RUN / "MANIFEST.json", manifest)
    print(f"Tracing {len(tasks)} original BLOCK_C locations with F1", flush=True)
    trace_start = time.monotonic()
    calls = trace_all(tasks, config["workers"], solver, freqs, versions)
    trace_s = time.monotonic() - trace_start
    generated = g2.OUT / "H_F1_50.npy"
    apply_start = time.monotonic()
    subprocess.run([sys.executable, str(g2.SOURCE / "scripts/drive_sim/rf_b_apply.py"),
                    "--poses", str(g2.OUT / "rf_poses.json"), "--traces", str(g2.OUT / "trace"),
                    "--mount", "0", "--out", str(generated)], check=True)
    apply_s = time.monotonic() - apply_start
    h_f1 = np.load(generated, allow_pickle=False)
    if h_f1.shape != h_ref.shape or h_f1.dtype != h_ref.dtype or not np.isfinite(h_f1).all():
        raise ValueError("F1 H has invalid shape, dtype, or values")
    rows, stats = compare(h_f1, h_ref, poses, freqs)
    identical_rows, identical = compare(h_ref, h_ref, poses, freqs)
    if identical["max"] != 0 or len(identical_rows) != 50:
        raise ValueError("Reference self-comparison failed")
    write(g2.OUT / "DELTA_S_ROWS.json", rows)
    result = dict(status="COMPLETE", stage="G2b", question_id=manifest["question_id"], case=config["case"],
                  paired_poses=len(rows), expected_poses=len(poses), abs_delta_s=stats,
                  worst_pose=max(rows, key=lambda row: row["abs_delta_s"]),
                  trace_positions=len(tasks), trace_calls=calls, trace_s=trace_s, apply_s=apply_s,
                  wall_s=time.monotonic()-t0, started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
                  manifest_sha256=sha(RUN / "MANIFEST.json"), numerical_gate=None,
                  h_f1_sha256=sha(generated), h_reference_sha256=sha(g2.OUT / "H_reference_50.npy"))
    write(g2.OUT / "G2B.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 2:
        g2.load_runtime = load_f1_runtime
        g2.run_shard(sys.argv[1])
    else:
        main()
