"""Apply the sweep admission budget to active trace containers."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time

from launch_tb3_full_sweep_snowball import HOME, utc


def run(root):
    prefix = "tb3_sweep_" + root.name.rsplit("_", 1)[1].lower() + "_"
    worker = re.compile(re.escape(prefix) + r"g-(?:t1|t2|v)_[abc](?:_p-f)?_[01]_\d{3}")
    records = root / "RESOURCES.jsonl"
    previous_budget = None
    while not (root / "EXIT_CODE.txt").exists():
        status = json.loads(records.read_text().splitlines()[-1])
        if status["phase"] in ("pilot_trace", "generation"):
            names = subprocess.check_output(["docker", "ps", "--format", "{{.Names}}"],
                                            universal_newlines=True).splitlines()
            names = [name for name in names if worker.fullmatch(name)]
            if names:
                budget = status["allowed_workers"]
                try:
                    quotas = subprocess.check_output(
                        ["docker", "inspect", "--format", "{{.Name}} {{.HostConfig.NanoCpus}}", *names],
                        universal_newlines=True, stderr=subprocess.DEVNULL).splitlines()
                except subprocess.CalledProcessError:
                    time.sleep(2)
                    continue
                target = max(0.05, min(1, budget / len(names)))
                adjust = []
                for line in quotas:
                    name, quota = line.split()
                    current = int(quota) / 1e9
                    if current - target >= 0.08 or (previous_budget == budget and target - current >= 0.08):
                        adjust.append(name[1:])
                if adjust:
                    quota = "{:.4f}".format(target)
                    changed = subprocess.run(["docker", "update", "--cpus", quota, *adjust],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                             universal_newlines=True)
                    updated = sum(name in changed.stdout.splitlines() for name in adjust)
                    with (root / "RESOURCE_ACTIONS.log").open("a") as stream:
                        print("{} {} of {} workers set to {} CPU each; host budget {}; rc {}".format(
                            utc(), updated, len(names), quota, budget, changed.returncode), file=stream)
                previous_budget = budget
        time.sleep(20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    root = parser.parse_args().root.resolve(strict=True)
    if root.parent != HOME or not root.name.startswith("G1_RT_TB3_FULL_SWEEP_"):
        parser.error("Expected a dedicated Snowball sweep directory")
    run(root)


if __name__ == "__main__":
    main()
