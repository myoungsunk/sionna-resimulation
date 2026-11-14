"""Schedule the frozen F1 production envelope on Snowball."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from run_tb3_production import CASES, NEAR_SETS, case_inputs, sha, read, utc_now, write
from seal_tb3_production import SEALED_CASES, finalize, seal_case


def command(script, *args):
    return [sys.executable, "-u", str(Path(__file__).with_name(script)), *map(str, args)]


def run(cmd, path):
    with path.open("x", encoding="utf-8") as stream:
        subprocess.run(cmd, check=True, stdout=stream, stderr=subprocess.STDOUT)


def batch(args):
    root = args.root
    out = root / "results"
    g0, g7, config, shards = (root / name for name in ("g0", "g7", "config", "shards"))
    canary = root / args.driver / "CANARY.json"
    if not read(canary).get("native_g1_coefficient_delay_exact"):
        raise ValueError("The native field canary did not reproduce the frozen G1 inputs")
    out.mkdir(mode=0o700)
    shards.mkdir(mode=0o700)
    plan = {}
    for case in CASES:
        _, _, poses, tasks, main, extra, prefix = case_inputs(g0, g7, case)
        plan[case] = dict(positions=len(tasks), poses=len(poses), main_poses=prefix,
                          diagnostic_poses=len(poses)-prefix,
                          near_pose_count=len({r["pose_id"] for r in main + extra if r["set"] in NEAR_SETS}),
                          shards=1 if case.endswith("_P-F") else 18)
    space = shutil.disk_usage(root)
    if space.free < 10 * 2**30:
        raise RuntimeError(f"Insufficient production scratch space: {space.free} bytes")
    pilot = read(config / "G1_ESTIMATE.json")
    pilot_near_bytes = int((config / "G8_PILOT_NEAR_BYTES.txt").read_text())
    near_poses = sum(p["near_pose_count"] for p in plan.values())
    count = sum(p["poses"] for p in plan.values())
    estimate = dict(g1_pilot_sha256=sha(config / "G1_ESTIMATE.json"),
                    g1_pilot_pose_count=pilot["scope"]["poses"],
                    g8_pilot_near_bytes=pilot_near_bytes,
                    h_bytes=count*257*2*2*16*2,
                    near_path_estimate_bytes=round(pilot_near_bytes*near_poses/pilot["scope"]["poses"]),
                    los_path_estimate_bytes=round(pilot["production_estimate"]["los_paths_estimated_bytes"]
                                                  * count/pilot["g0_totals"]["poses"]),
                    near_pose_count=near_poses, scratch_reserved_for_planning_bytes=10*2**30,
                    home_free_bytes_prelaunch=space.free)
    started = time.monotonic()
    settings = read(config / "PRODUCTION_F1.json")
    write(out / "RUN_MANIFEST.json", dict(
        status="PLANNED", started_utc=utc_now(), role="IMPLEMENTER",
        question_ids=["G1-RT-TB3-001", "G1-RT-TB3-002"], execution_site="Snowball/KMS",
        code_base_commit=args.code_commit, source_state="production scripts hashed below",
        method_b_commit=settings["method_b_commit"], image=settings["image"], f1=settings,
        workers=args.workers, source_sha256={p.name: sha(p) for p in sorted((root / "code").glob("*.py"))},
        input_sha256={p.relative_to(root).as_posix(): sha(p) for p in [
            g0 / "RUN_MANIFEST.json", g7 / "RUN_MANIFEST.json", canary,
            *sorted(p for p in config.iterdir() if p.is_file()),
        ]}, governance=read(g0 / "RUN_MANIFEST.json")["governance"],
        command=[sys.executable, *sys.argv], storage_estimate=estimate, cases=plan,
    ))
    shutil.copytree(g0 / "scene", out / "scene")
    (out / "gates").mkdir()
    shutil.copyfile(g0 / "gates/G0.json", out / "gates/G0.json")
    shutil.copyfile(g7 / "G7.json", out / "gates/G7.json")
    shutil.copyfile(g7 / "POSE_MANIFEST.json", out / "POSE_MANIFEST.json")
    job_args = ("--inputs", g0, "--g7", g7, "--source", args.source,
                "--reference", root / "frozen/REFERENCE.json", "--ffd-manifest",
                root / "frozen/FFD_RESTORE_MANIFEST.json", "--production", config / "PRODUCTION_F1.json",
                "--code-commit", args.code_commit)
    for case in CASES:
        (shards / case).mkdir(mode=0o700)

    def trace(case, index):
        label = f"{index:03d}"
        path = root / "logs" / f"{case}_{label}.log"
        run(command("run_tb3_production.py", *job_args, "--case", case, "--shard-index", index,
                    "--shard-count", plan[case]["shards"], "--out", shards / case / label), path)
        return case, index

    def merge(case):
        run(command("merge_tb3_production.py", "--inputs", g0, "--g7", g7,
                    "--case", case, "--shards", shards / case, "--out", out),
            root / "logs" / f"{case}_merge.log")
        if case in SEALED_CASES:
            seal_case(out, case)
        print(f"Completed {case}", flush=True)
        return case

    remaining = {name: info["shards"] for name, info in plan.items()}
    failures, assembled = [], []
    order = tuple(c for c in CASES if c.endswith("_P-F")) + SEALED_CASES + tuple(
        c for c in CASES if c not in SEALED_CASES and not c.endswith("_P-F")
    )
    with ThreadPoolExecutor(max_workers=args.workers) as pool, ThreadPoolExecutor(max_workers=2) as merger:
        tracing = {pool.submit(trace, case, i): (case, i) for case in order for i in range(remaining[case])}
        merging = {}
        failed_cases = set()
        for future in as_completed(tracing):
            case, index = tracing[future]
            remaining[case] -= 1
            try:
                future.result()
                print(f"Traced {case} {index:03d}", flush=True)
            except (subprocess.CalledProcessError, OSError) as exc:
                failed_cases.add(case)
                failures.append(dict(case=case, shard=index, error=str(exc)))
                print(f"FAILED {case} {index:03d}; see shard log", flush=True)
            if not remaining[case] and case not in failed_cases:
                merging[merger.submit(merge, case)] = case
        for future in as_completed(merging):
            try:
                assembled.append(future.result())
            except (subprocess.CalledProcessError, OSError, ValueError) as exc:
                failures.append(dict(case=merging[future], stage="assembly_or_seal", error=str(exc)))
    if not set(SEALED_CASES).difference(assembled):
        finalize(out)
    cases = {}
    for case in sorted(assembled):
        manifest = out / "H" / case / "MANIFEST.json"
        data = read(manifest)
        cases[case] = {k: data[k] for k in (
            "poses", "main_poses", "diagnostic_new_poses", "trace_positions", "near_poses",
            "anchor_xyz", "robot_z", "mount_deg", "shape", "los_H_sha256", "full_H_sha256",
            "samples_sha256", "solver_batch_calls", "extra_export_solver_calls",
        )} | dict(
            H=f"H/{case}/H_full.npy", H_LoS=f"H/{case}/H_LoS.npy",
            rf_poses=f"poses/{case}/rf_poses.json", samples=f"poses/{case}/SAMPLES.json",
            manifest=manifest.relative_to(out).as_posix(), manifest_sha256=sha(manifest),
            payload_bytes=sum(data["output_bytes"].values()),
            h_bytes=sum(v for f, v in data["output_bytes"].items() if f.endswith(".npy")),
            near_path_bytes=data["output_bytes"][f"paths/{case}/PATHS_NEAR.npz"],
            los_path_bytes=data["output_bytes"][f"paths/{case}/PATHS_LoS.npz"],
        )
    write(out / "CASES.json", cases)
    status = "PASS" if len(cases) == len(CASES) and not failures else "INCOMPLETE"
    write(out / "GENERATION_RESULT.json", dict(
        status=status, stage="F1_GENERATION", finished_utc=utc_now(),
        wall_s=time.monotonic()-started, cases=len(cases), failures=failures,
        totals={key: sum(c[key] for c in cases.values()) for key in (
            "poses", "main_poses", "diagnostic_new_poses", "near_poses", "trace_positions",
            "solver_batch_calls", "extra_export_solver_calls", "payload_bytes", "h_bytes",
            "near_path_bytes", "los_path_bytes",
        )},
        cases_sha256=sha(out / "CASES.json"),
    ))
    return int(status != "PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--driver", default="canary01")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("worker count must be positive")
    sys.exit(batch(args))


if __name__ == "__main__":
    main()
