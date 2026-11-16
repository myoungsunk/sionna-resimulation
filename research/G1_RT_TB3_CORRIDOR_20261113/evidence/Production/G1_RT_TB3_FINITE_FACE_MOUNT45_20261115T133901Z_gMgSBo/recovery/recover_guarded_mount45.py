"""Resume only failed work in this guarded +45 generation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import sys

from run_tb3_production import CASES, read, sha, utc_now, write
from run_tb3_production_batch import command, run


PLAN = {"G-T1_A": (), "G-T1_B": (5, 8, 10), "G-T1_C": (3, 4, 13, 15, 16)}
COVERAGE = ("poses", "main_poses", "diagnostic_new_poses", "trace_positions", "near_poses",
            "solver_batch_calls", "extra_export_solver_calls")
BYTES = ("payload_bytes", "h_bytes", "near_path_bytes", "los_path_bytes")
FOLDERS = ("H", "paths", "poses")
CODE_COMMIT = "a2dff24f603c2460fcf7cabf5597cbf0da7ad551"


def output_entry(out, case):
    manifest = out / "H" / case / "MANIFEST.json"
    data = read(manifest)
    sizes = data["output_bytes"]
    if data["status"] != "PASS" or data["mount_deg"] != 45:
        raise ValueError(f"Invalid recovered assembly for {case}")
    return {key: data[key] for key in (*COVERAGE, "anchor_xyz", "robot_z", "mount_deg", "shape",
                                      "los_H_sha256", "full_H_sha256", "samples_sha256")} | dict(
        H=f"H/{case}/H_full.npy", H_LoS=f"H/{case}/H_LoS.npy",
        rf_poses=f"poses/{case}/rf_poses.json", samples=f"poses/{case}/SAMPLES.json",
        manifest=manifest.relative_to(out).as_posix(), manifest_sha256=sha(manifest),
        payload_bytes=sum(sizes.values()), h_bytes=sum(n for f, n in sizes.items() if f.endswith(".npy")),
        near_path_bytes=sizes[f"paths/{case}/PATHS_NEAR.npz"],
        los_path_bytes=sizes[f"paths/{case}/PATHS_LoS.npz"],
    )


def recover(root):
    out, recovery, source = root / "results", root / "recovery", Path("/ref")
    initial = recovery / "initial_attempt"
    generation = read(initial / "GENERATION_RESULT.json")
    cases = read(initial / "CASES.json")
    expected_failures = {(case, index) for case, indices in PLAN.items() for index in indices} | {("G-T1_A", None)}
    observed_failures = {(x["case"], x.get("shard")) for x in generation["failures"]}
    if (generation["status"] != "INCOMPLETE" or generation["finite_face_guard"] is not True
            or observed_failures != expected_failures or set(cases) != set(CASES) - PLAN.keys()
            or sha(out / "GENERATION_RESULT.json") != sha(initial / "GENERATION_RESULT.json")
            or sha(out / "CASES.json") != generation["cases_sha256"]
            or sha(out / "seal/SEAL_MANIFEST.json") != sha(initial / "SEAL_MANIFEST.json")
            or sha(out / "seal/ACCESS_LOG.jsonl") != sha(initial / "ACCESS_LOG.jsonl")):
        raise ValueError("Initial guarded +45 run does not match the recorded failures")
    for case, entry in cases.items():
        if sha(out / entry["manifest"]) != entry["manifest_sha256"]:
            raise ValueError(f"Completed manifest differs for {case}")
    for case, ids in PLAN.items():
        present = {int(p.parent.name) for p in (root / "shards" / case).glob("*/MANIFEST.json")}
        if present != set(range(18)) - set(ids):
            raise ValueError(f"Unexpected shard receipts for {case}")

    # Build the retry jobs from the frozen use of the same shard runner.
    code = root / "code"
    g0, g7 = root / "g0", root / "g7"
    staged = recovery / "reassembled"
    jobs = []
    for case, indices in PLAN.items():
        for index in indices:
            label = f"{index:03d}"
            dest = recovery / "retry_shards" / case / label
            jobs.append((case, label, dest, [
                sys.executable, "-u", str(code / "run_tb3_production.py"),
                "--inputs", str(g0), "--g7", str(g7), "--source", str(source),
                "--reference", str(root / "frozen/REFERENCE.json"),
                "--ffd-manifest", str(root / "frozen/FFD_RESTORE_MANIFEST.json"),
                "--production", str(root / "config/PRODUCTION_F1.json"),
                "--case", case, "--shard-index", str(index), "--shard-count", "18",
                "--out", str(dest), "--code-commit", CODE_COMMIT, "--finite-face-guard",
            ]))
    write(recovery / "RETRY_COMMANDS.json", [cmd for _, _, _, cmd in jobs])

    def trace(case, label, dest, cmd):
        run(cmd, recovery / "retry_logs" / f"{case}_{label}.log")
        if read(dest / "MANIFEST.json")["status"] != "PASS":
            raise ValueError(f"Retry shard failed verification: {case}/{label}")
        print(f"Retried {case} {label}", flush=True)

    def merge(case):
        cmd = command("merge_tb3_production.py", "--inputs", g0, "--g7", g7,
                      "--case", case, "--shards", root / "shards" / case, "--out", staged)
        run(cmd, recovery / "retry_logs" / f"{case}_merge.log")
        print(f"Reassembled {case}", flush=True)

    with ThreadPoolExecutor(max_workers=9) as pool:
        merge_a = pool.submit(merge, "G-T1_A")
        retries = [pool.submit(trace, *job) for job in jobs]
        for future in retries:
            future.result()
        merge_a.result()

    for case, label, dest, _ in jobs:
        original = root / "shards" / case / label
        archived = initial / "partial_shards" / case / label
        archived.parent.mkdir(parents=True, exist_ok=True)
        original.rename(archived)
        dest.rename(original)
    with ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(merge, ("G-T1_B", "G-T1_C")):
            pass

    cases.update({case: output_entry(staged, case) for case in PLAN})
    write(recovery / "CASES.final.json", dict(sorted(cases.items())))
    history = {
        "initial_result_sha256": sha(initial / "GENERATION_RESULT.json"),
        "retry_commands_sha256": sha(recovery / "RETRY_COMMANDS.json"),
        "original_successful_shards": 156,
        "retried_shards": len(jobs),
        "reassembled_cases": list(PLAN),
    }
    started = datetime.fromisoformat((root / "PRODUCTION_START_UTC.txt").read_text().strip())
    finished = utc_now()
    write(recovery / "GENERATION_RESULT.final.json", dict(
        status="PASS", stage=generation["stage"], finished_utc=finished,
        wall_s=(datetime.fromisoformat(finished) - started).total_seconds(),
        cases=len(cases), failures=[],
        totals={key: sum(entry[key] for entry in cases.values()) for key in (*COVERAGE, *BYTES)},
        cases_sha256=sha(recovery / "CASES.final.json"),
        finite_face_guard=True, g6_result_sha256=generation["g6_result_sha256"], recovery=history,
    ))
    for case in PLAN:
        for folder in FOLDERS:
            target = out / folder / case
            if target.exists():
                archived = initial / "partial_assembly" / folder / case
                archived.parent.mkdir(parents=True, exist_ok=True)
                target.rename(archived)
            (staged / folder / case).rename(target)
    (recovery / "CASES.final.json").replace(out / "CASES.json")
    (recovery / "GENERATION_RESULT.final.json").replace(out / "GENERATION_RESULT.json")


if __name__ == "__main__":
    recover(Path("/run"))
