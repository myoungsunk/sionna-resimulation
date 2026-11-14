import hashlib
import datetime as dt
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

RUN = Path("/run")
INPUT = Path("/production")
CASES = tuple(f"{g}_{a}" for g in ("G-T1", "G-T2", "G-V") for a in "ABC") + (
    "G-T1_A_P-F", "G-T1_B_P-F",
)
CODE_COMMIT = "f654dff1bd529a95ddf61fe98d2ea58ceb062dff"
PY = sys.executable
CODE = RUN / "code"
REQUIRED_ARMS = {"P-D": (60, 300), "P-E": (99, 495), "P-F": (36, 1944)}


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run_task(stage, case, task=None):
    label = f"{stage}_{case}" + (f"_{task}" if task is not None else "")
    cmd = [
        PY, "-u", str(CODE / "validate_tb3_production_g3.py"), "--stage", stage,
        "--case", case, "--out", str(RUN / "cases" / case), "--inputs", str(INPUT / "g0"),
        "--g7", str(INPUT / "g7"), "--source", "/ref", "--production", str(INPUT / "config" / "PRODUCTION_F1.json"),
        "--reference", str(INPUT / "frozen" / "REFERENCE.json"), "--ffd-manifest",
        str(INPUT / "frozen" / "FFD_RESTORE_MANIFEST.json"), "--code-commit", CODE_COMMIT,
        "--g3a", str(CODE / "run_g3a.py"), "--g3c-trace", str(CODE / "run_g3c_trace.py"),
        "--g3c-evaluation", str(CODE / "run_g3c_evaluation.py"), "--parity", str(CODE / "parity_gate.py"),
    ]
    if task is not None:
        cmd.extend(["--task-id", str(task)])
    with (RUN / "logs" / f"{label}.log").open("x", encoding="utf-8") as stream:
        code = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT, check=False).returncode
    return dict(case=case, task_id=task, exit_code=code)


def plans():
    return {case: read(RUN / "cases" / case / "SAMPLE_PLAN.json") for case in CASES}


def plan():
    for case in CASES:
        result = run_task("plan", case)
        if result["exit_code"]:
            raise RuntimeError(result)
    cases = plans()
    rows = {arm: [] for arm in REQUIRED_ARMS}
    for case, payload in cases.items():
        tasks = payload["tasks"]
        if len(tasks) != len({t["task_id"] for t in tasks}) or len(tasks) != len({(t["x"], t["y"]) for t in tasks}):
            raise ValueError(f"Duplicate XY or ID in {case}")
        for row in tasks:
            for arm, detail in row["arms"].items():
                rows[arm].append(detail)
    counts = {arm: (len(entries), sum(len(row["sampled_yaws"]) for row in entries))
              for arm, entries in rows.items()}
    if counts != REQUIRED_ARMS or len({r["selection"][0] for r in rows["P-D"]}) != 18 or len({
        r["selection"][0] for r in rows["P-E"]
    }) != 18 or len({r["selection"][1] for r in rows["P-E"]}) != 3:
        raise ValueError(f"Unexpected diagnostic sample coverage: {counts}")
    for filename in ("PRODUCTION_F1.json", "SPEC_DIAG_KO.md", "SPEC_V1_1_KO.md"):
        if not (INPUT / "config" / filename).is_file():
            raise FileNotFoundError(filename)
    manifest = dict(
        question_id="G1-RT-TB3-002", frozen_utc=utc(), role="IMPLEMENTER",
        data_scope="deterministic XY sample from P-D/P-E/P-F only",
        working_branch=os.environ["DIAG_BRANCH"], code_base_commit=CODE_COMMIT,
        policy=next(iter(cases.values()))["policy"], sample_counts=counts,
        case_plans={case: sha(RUN / "cases" / case / "SAMPLE_PLAN.json") for case in cases},
        cases={case: [row["task_id"] for row in payload["tasks"]] for case, payload in cases.items()},
        source_sha256={path.name: sha(path) for path in sorted(CODE.glob("*.py"))},
        input_sha256={p.relative_to(INPUT).as_posix(): sha(p) for p in (
            INPUT / "config" / "PRODUCTION_F1.json", INPUT / "config" / "SPEC_DIAG_KO.md",
            INPUT / "config" / "SPEC_V1_1_KO.md", INPUT / "g0" / "RUN_MANIFEST.json",
            INPUT / "g7" / "RUN_MANIFEST.json", INPUT / "frozen" / "REFERENCE.json",
            INPUT / "frozen" / "FFD_RESTORE_MANIFEST.json",
        )},
        computations=["G3a", "G3b", "G3c"], sealed_production_payload_mounted=False,
    )
    write(RUN / "SAMPLE_MANIFEST.json", manifest)
    print(f"Frozen plan: {counts}; {sum(t[0] for t in counts.values())} XY total", flush=True)


def stage(stage_name, max_workers):
    manifest = read(RUN / "SAMPLE_MANIFEST.json")
    for case, digest in manifest["case_plans"].items():
        if sha(RUN / "cases" / case / "SAMPLE_PLAN.json") != digest:
            raise ValueError(f"Frozen sample changed: {case}")
    for name, digest in manifest["source_sha256"].items():
        if sha(CODE / name) != digest:
            raise ValueError(f"Frozen worker code changed: {name}")
    joblist = [(case, task) for case, tasks in manifest["cases"].items() for task in tasks]
    tick, started = time.monotonic(), utc()
    print(f"{stage_name}: {len(joblist)} jobs on {max_workers} workers", flush=True)
    records = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(run_task, stage_name, case, task) for case, task in joblist]
        for i, future in enumerate(as_completed(futures), 1):
            rec = future.result()
            records.append(rec)
            if i % 12 == 0 or i == len(joblist) or rec["exit_code"]:
                print(f"{stage_name} {i}/{len(joblist)} {rec}", flush=True)
    write(RUN / f"{stage_name.upper()}_RUN.json", dict(stage=stage_name, started_utc=started,
          finished_utc=utc(), wall_s=time.monotonic()-tick, workers=max_workers,
          task_exits=sorted(records, key=lambda row: (row["case"], row["task_id"])),
          sample_manifest_sha256=sha(RUN / "SAMPLE_MANIFEST.json")))
    unknown = [r for r in records if r["exit_code"] not in (0, 2) or not (
        RUN / "cases" / r["case"] / "tasks" / str(r["task_id"]) / f"{stage_name.upper()}.json"
    ).is_file()]
    if unknown:
        print(f"{stage_name}: {len(unknown)} execution errors", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["plan"]:
        plan()
    elif len(sys.argv) == 3 and sys.argv[1] in ("g3a", "g3b", "g3c"):
        sys.exit(stage(sys.argv[1], int(sys.argv[2])))
    else:
        sys.exit("usage: batch plan | batch (g3a|g3b|g3c) <workers>")
