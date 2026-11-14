"""Complete the G2b comparison from verified H arrays produced by its trace run."""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import run_g2b as g2b
from qclean_uwb.drivesim.rf_store import load_banks
from run_tb3_g1_pilot import read, sha, write


TRACE_RUN = Path("/trace-run")
RUN = Path("/evaluation")


def main():
    t0 = time.monotonic()
    source_output = TRACE_RUN / "output"
    manifest = read(TRACE_RUN / "MANIFEST.json")
    if (TRACE_RUN / "EXIT_CODE.txt").read_text().strip() != "1" or not (
            "ModuleNotFoundError: No module named 'rt_cp_uwb_py'" in (TRACE_RUN / "run.log").read_text()):
        raise ValueError("Could not verify the trace run's comparison-only failure")
    g2b.g2.verify(g2b.g2.SOURCE / g2b.FP_SOURCE, g2b.FP_SHA)
    g2b.g2.verify(TRACE_RUN / "run_g2b.py", manifest["runner_sha256"])
    g2b.g2.verify(TRACE_RUN / "launch.sh", manifest["launch_sha256"])
    g2b.g2.verify(g2b.G3C / "MANIFEST.json", g2b.G3C_MANIFEST_SHA)
    expected_solver = read(g2b.G3C / "MANIFEST.json")["solver_100k"]
    if manifest["solver"] != expected_solver or read(TRACE_RUN / "F1_SOLVER.json") != {"solver": expected_solver}:
        raise ValueError("F1 solver mismatch")
    paths = ("H_F1_50.npy", "H_F1_50.manifest.json", "H_reference_50.npy", "rf_poses.json",
             "rf_tasks.json", "scene.json", "SHARD_EXIT.json")
    old_digests = {}
    for line in (TRACE_RUN / "SHA256.txt").read_text().splitlines():
        digest, rel = line.split(maxsplit=1)
        old_digests[rel.removeprefix("./")] = digest
    for name in paths:
        g2b.g2.verify(source_output / name, old_digests[f"output/{name}"])
    for name in ("rf_poses.json", "rf_tasks.json", "scene.json", "H_reference_50.npy"):
        g2b.g2.verify(source_output / name, g2b.G2_DIGESTS[f"output/{name}"])
    poses = read(source_output / "rf_poses.json")
    tasks = read(source_output / "rf_tasks.json")
    if ([p["block_pose_id"] for p in poses] != manifest["block_pose_ids"] or len(poses) != 50
            or len(tasks) != 50 or any(read(source_output / "SHARD_EXIT.json"))):
        raise ValueError("Incomplete trace run")
    trace_calls = 0
    for task in tasks:
        tag = task["tag"]
        trace_rel = f"output/trace/{tag}_trace_receipt.json"
        g2b.g2.verify(TRACE_RUN / trace_rel, old_digests[trace_rel])
        receipt = read(TRACE_RUN / trace_rel)
        if receipt["tag"] != tag or receipt["status"] != "OK" or receipt["solver"] != expected_solver:
            raise ValueError(f"Failed F1 trace receipt for {tag}")
        trace_calls += receipt["pathsolver_calls"]
    h_f1 = np.load(source_output / "H_F1_50.npy", allow_pickle=False)
    h_ref = np.load(source_output / "H_reference_50.npy", allow_pickle=False)
    if any(h.shape != (50, 257, 2, 2) or h.dtype != np.complex128 or not np.isfinite(h).all()
           for h in (h_f1, h_ref)):
        raise ValueError("Invalid H array")
    freqs = load_banks()[0].freqs_hz
    rows, stats = g2b.compare(h_f1, h_ref, poses, freqs)
    _, self_comparison = g2b.compare(h_ref, h_ref, poses, freqs)
    if self_comparison["exactly_zero"] != 50:
        raise ValueError("Reference self-comparison failed")

    output = RUN / "output"
    output.mkdir()
    for name in paths:
        (output / name).write_bytes((source_output / name).read_bytes())
    stable = dict(
        run_manifest_sha256=sha(TRACE_RUN / "MANIFEST.json"),
        sealed_trace_run_sha256=sha(TRACE_RUN / "SHA256.txt"),
        evaluator_sha256=sha(Path(__file__)),
        launch_sha256=sha(RUN / "launch_compare.sh"),
        comparison_module_sha256=sha(TRACE_RUN / "run_g2b.py"),
        repair="Add /ref to PYTHONPATH for the frozen first-path module and reuse verified H arrays",
    )
    write(RUN / "MANIFEST.json", manifest | stable)
    write(output / "DELTA_S_ROWS.json", rows)
    source_start = datetime.fromisoformat((TRACE_RUN / "STARTED_UTC.txt").read_text().strip()).timestamp()
    source_finished = datetime.fromisoformat((TRACE_RUN / "FINISHED_UTC.txt").read_text().strip()).timestamp()
    source_wall = source_finished - source_start
    # Original runner did not save its monotonic timings after comparison raised.
    h_ready = (source_output / "H_F1_50.manifest.json").stat().st_mtime
    eval_s = time.monotonic()-t0
    result = dict(status="COMPLETE", stage="G2b", question_id=manifest["question_id"], case=manifest["case"],
                  paired_poses=len(rows), expected_poses=len(poses), abs_delta_s=stats,
                  worst_pose=max(rows, key=lambda row: row["abs_delta_s"]),
                  trace_positions=len(tasks), trace_calls=trace_calls, trace_s=None,
                  trace_run_wall_s=source_wall, h_ready_since_trace_launch_s=h_ready-source_start,
                  evaluation_s=eval_s, wall_s=source_wall+eval_s,
                  finished_utc=datetime.now(timezone.utc).isoformat(),
                  timing="Container launch to original trace/apply exit, plus monotonic comparison runtime; excludes time between invocations",
                  manifest_sha256=sha(RUN / "MANIFEST.json"), numerical_gate=None,
                  h_f1_sha256=sha(output / "H_F1_50.npy"), h_reference_sha256=sha(output / "H_reference_50.npy"))
    write(output / "G2B.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
