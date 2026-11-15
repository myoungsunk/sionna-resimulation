"""Re-evaluate the archived G3b and G3c paths at body yaw + 45 degrees."""
import importlib.util
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/run_m45")
B = Path("/g3b")
C = Path("/g3c")
INPUT = Path("/g3/input")
YAW = 'yaws = [p["yaw_deg"] for p in task["sampled_yaws"]]'
ROTATED = 'yaws = [p["yaw_deg"] + 45.0 for p in task["sampled_yaws"]]'


def stage(source, destination):
    script = source.read_text()
    if script.count(YAW) != 1:
        raise ValueError(f"Unexpected yaw expression in {source}")
    with destination.open("x") as out:
        out.write(script.replace(YAW, ROTATED))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare():
    stage(B / "run_tb3_g3.py", ROOT / "g3b_mount45.py")
    stage(C / "run_g3c_evaluation.py", ROOT / "g3c_mount45.py")
    c_run = ROOT / "c"
    c_run.mkdir()
    for name in ("MANIFEST.json", "raw", "RAW_SHA256.txt", "TRACE_EXIT_CODE.txt",
                 "launch_evaluation.sh", "launch_trace.sh", "run_g3c_trace.py",
                 "STARTED_UTC.txt", "TRACE_WALL_S.txt"):
        (c_run / name).symlink_to(C / name)


def replay_b():
    begin = time.monotonic()
    subprocess.run(["sha256sum", "--check", "--quiet", "OUTPUT_SHA256.txt"], cwd=B, check=True)
    b = load(ROOT / "g3b_mount45.py", "b_mount45")
    b.INPUT, b.OUT = INPUT, B / "output"
    cfg = b.read(INPUT / "G3_CONTRACT.json")
    out = ROOT / "b"
    out.mkdir()
    artifact = b.evaluate(cfg, INPUT / "parity_gate.py", out)
    b.write(out / "G3B_MOUNT45.json", artifact | {
        "mount_deg": 45, "channel": "RX body yaw + 45 degrees",
        "trace_digest_table_sha256": b.sha(B / "OUTPUT_SHA256.txt"),
        "contract_sha256": b.sha(INPUT / "G3_CONTRACT.json"),
        "frozen_evaluator_sha256": b.sha(B / "run_tb3_g3.py"),
        "mount45_evaluator_sha256": b.sha(ROOT / "g3b_mount45.py"),
        "wall_s": time.monotonic() - begin,
    })
    print(artifact["status"], {key: v for key, v in artifact["pooled"].items() if not isinstance(v, (list, dict))})
    return 0 if artifact["status"] == "PASS" else 2


def replay_c():
    begin = time.monotonic()
    c = load(ROOT / "g3c_mount45.py", "c_mount45")
    c.RUN = ROOT / "c"
    c.preflight()
    for case in c.g3a.task_table():
        c.evaluate_case(case)
        print(case, flush=True)
    status = c.summarize()
    receipt = c.read(c.RUN / "G3C.json")
    c.write(c.RUN / "G3C_MOUNT45.json", receipt | {
        "mount_deg": 45, "channel": "RX body yaw + 45 degrees",
        "source_evaluator_sha256": c.g3a.sha(C / "run_g3c_evaluation.py"),
        "mount45_evaluator_sha256": c.g3a.sha(ROOT / "g3c_mount45.py"),
        "wall_s_replay": time.monotonic() - begin,
    })
    return status


if __name__ == "__main__":
    sys.exit({"prepare": prepare, "g3b": replay_b, "g3c": replay_c}[sys.argv[1]]())
