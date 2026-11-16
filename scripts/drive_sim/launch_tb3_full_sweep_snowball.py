"""Run and monitor an isolated Snowball/KMS sweep in the frozen RT image."""
import argparse
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


IMAGE = "sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f"
BASE_COMMIT = "1b5888cb7464b494bf9f3095855fe00d4e811558"
HOME = Path("/home/KMS")
BASE0 = HOME / "G1_RT_TB3_FINITE_FACE_PRODUCTION_20261115T122037Z_HS1vMs"
BASE45 = HOME / "G1_RT_TB3_FINITE_FACE_MOUNT45_20261115T133901Z_gMgSBo"
SOURCE = HOME / "DRIVE_SIM_ROUTES_20261007_01a11669/source"
RUNTIME = HOME / "COOL_DIJKSTRA_20261007_01a11582/runtime_packages"
MODEL = HOME / "RUN2_20261113T072631Z/inputs/results/DRIVE_SIM_20261007/CAUSE_CHECK_A23_EXECUTION_20261010/retrieved/source"
PILOT = "G-T1_A_P-F"
GIB_KIB = 1024 ** 2
MONITOR_PERIOD_S = 20
RECORD_PERIOD_S = 2 * 60 * 60


def utc():
    return datetime.now(timezone.utc).isoformat()


def read(path):
    return json.loads(path.read_text())


def write(path, payload):
    with path.open("x") as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(data)
    return digest.hexdigest()


def host_cpu():
    return [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:9]]


def read_processes():
    output = {}
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            raw = (path / "stat").read_text()
            left, right = raw.index("("), raw.rindex(")")
            fields = raw[right+2:].split()
            rss = max(0, int(fields[21])) * (os.sysconf("SC_PAGE_SIZE") // 1024)
            output[int(path.name)] = (raw[left+1:right], path.stat().st_uid, fields[19],
                                      int(fields[11]) + int(fields[12]), rss)
        except (FileNotFoundError, PermissionError, ProcessLookupError, IndexError):
            continue
    return output


class ResourceMonitor:
    def __init__(self, root, prefix, maximum):
        self.root = root
        self.prefix = prefix
        self.maximum = maximum
        self.last_record = float("-inf")
        self.last_sample = float("-inf")
        self.last_budget = None
        self.budget = 0

    def check(self, phase, active, force=False):
        now = time.monotonic()
        if not force and now < self.last_sample + MONITOR_PERIOD_S:
            return self.budget
        self.last_sample = now
        modules = subprocess.check_output([
            "docker", "ps", "--no-trunc", "--format", "{{.ID}} {{.Names}}"
        ], universal_newlines=True).splitlines()
        container_ids = tuple(line.split()[0] for line in modules
                              if line.split()[1].startswith(self.prefix))
        before_cpu, before_procs = host_cpu(), read_processes()
        time.sleep(1)
        after_cpu, after_procs = host_cpu(), read_processes()
        counters = [b-a for a, b in zip(before_cpu, after_cpu)]
        idle = counters[3] / sum(counters)
        io_wait = counters[4] / sum(counters)
        logical = os.cpu_count()
        ticks_per_core = sum(counters) / logical
        ours_ticks = ours_rss = kms_other_rss = 0
        others = Counter()
        for pid, (name, uid, birth, ticks, rss) in after_procs.items():
            owned = False
            if container_ids and uid == os.getuid():
                try:
                    group = Path("/proc/{}/cgroup".format(pid)).read_text()
                    owned = any(cid in group for cid in container_ids)
                except (FileNotFoundError, PermissionError, ProcessLookupError):
                    pass
            previous = before_procs.get(pid)
            delta = ticks - previous[3] if previous and previous[2] == birth else 0
            if owned:
                ours_ticks += delta
                ours_rss += rss
            else:
                others[(uid, name)] += delta
                if uid == os.getuid():
                    kms_other_rss += rss
        ours_cores = ours_ticks / ticks_per_core
        other_cores = max(0.0, logical*(1-idle-io_wait) - ours_cores)
        mem = {}
        wanted = {"MemTotal", "MemAvailable", "SwapFree", "CommitLimit", "Committed_AS"}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            if key in wanted:
                mem[key] = int(value.split()[0])
        commit_free = mem["CommitLimit"] - mem["Committed_AS"]
        disk = {where: shutil.disk_usage(where).free for where in ("/", "/home/KMS", "/dev/shm")}
        # Reserve capacity for concurrent jobs and LLVM JIT mappings.
        bounds = {
            "cpu": math.floor(logical - other_cores - 24),
            "physical_ram": (mem["MemAvailable"] - 160*GIB_KIB + ours_rss) // (8*GIB_KIB),
            "commit": (commit_free - 96*GIB_KIB) // (8*GIB_KIB) + active,
            "home_space": self.maximum if disk["/home/KMS"] >= 45*1024**3 else 0,
            "io_wait": self.maximum if io_wait < 0.12 else max(1, active//2),
        }
        self.budget = max(0, min(self.maximum, *bounds.values()))
        if force or self.last_budget != self.budget or now >= self.last_record + RECORD_PERIOD_S:
            record = dict(utc=utc(), phase=phase, active_workers=active, allowed_workers=self.budget,
                          bounds=bounds, logical_cpu=logical, idle_pct=idle*100, iowait_pct=io_wait*100,
                          load_avg=list(os.getloadavg()), sweep_cpu_cores=ours_cores,
                          other_cpu_cores=other_cores, sweep_rss_kib=ours_rss,
                          kms_other_rss_kib=kms_other_rss, memory_kib=mem,
                          commit_free_kib=commit_free,
                          overcommit_mode=int(Path("/proc/sys/vm/overcommit_memory").read_text()),
                          disk_free_bytes=disk,
                          other_processes=[dict(uid=uid, command=name, logical_cores=ticks/ticks_per_core)
                                           for (uid, name), ticks in others.most_common(8) if ticks])
            with (self.root / "RESOURCES.jsonl").open("a") as stream:
                stream.write(json.dumps(record, allow_nan=False) + "\n")
            print("Resources {}: sweep {:.1f} CPU, other {:.1f} CPU, available RAM {:.0f} GiB, "
                  "commit headroom {:.0f} GiB, workers {}/{}".format(
                      phase, ours_cores, other_cores, mem["MemAvailable"]/GIB_KIB,
                      commit_free/GIB_KIB, active, self.budget), flush=True)
            self.last_record = now
            self.last_budget = self.budget
        return self.budget


class Run:
    def __init__(self, root, maximum):
        self.root = root
        self.sweep = read(root / "sweep_inputs/SWEEP_MANIFEST.json")
        self.prefix = "tb3_sweep_" + root.name.rsplit("_", 1)[1].lower() + "_"
        self.resources = ResourceMonitor(root, self.prefix, maximum)
        self.base_paths = [base / name for base in (BASE0, BASE45)
                           for name in ("results/seal/SEAL_MANIFEST.json",
                                        "results/seal/ACCESS_LOG.jsonl",
                                        "results/GENERATION_RESULT.json",
                                        "results/gates/G4.json",
                                        "g0/RUN_MANIFEST.json", "g7/RUN_MANIFEST.json")]
        self.original_hashes = {str(p): sha(p) for p in self.base_paths}

    def run_image(self, label, script, args, log, cpus=1, memory="12g", extra_mounts=()):
        code = self.root / "code"
        mounts = [(self.root, "/run", ""), (code, "/run/code", ":ro"),
                  (BASE0 / "g0", "/g0", ":ro"), (BASE0 / "g7", "/g7", ":ro"),
                  (BASE0 / "config", "/config", ":ro"), (BASE0 / "frozen", "/frozen", ":ro"),
                  (SOURCE, "/ref", ":ro"), (RUNTIME, "/runtime_packages", ":ro"),
                  (MODEL, "/model", ":ro"), *extra_mounts]
        command = ["docker", "run", "--rm", "--pull=never", "--network", "none",
                   "--name", self.prefix + label, "--cpus", str(cpus), "--cpu-shares", "128",
                   "--memory", memory, "--memory-swap", memory, "--user", "1001:1001", "--workdir", "/ref"]
        for host, target, mode in mounts:
            command.extend(("-v", "{}:{}{}".format(host, target, mode)))
        for name, value in dict(HOME="/run/cache", TMPDIR="/run/scratch", PYTHONDONTWRITEBYTECODE="1",
                                OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1",
                                PYTHONPATH="/run/code:/runtime_packages:/ref:/ref/src").items():
            command.extend(("-e", name + "=" + value))
        command.extend(("--entrypoint", "/usr/bin/nice", IMAGE, "-n", "15", "/opt/rt-env/bin/python",
                        "-u", "/run/code/" + script, *args))
        with log.open("x") as stream:
            stream.write(json.dumps(dict(utc=utc(), command=command)) + "\n")
            stream.flush()
            return subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)

    def start_shard(self, job, attempt_index):
        case, index, count = job
        label = "{}_{}_{:03d}".format(case, attempt_index, index).lower()
        attempt = self.root / "attempts" / label
        log = self.root / "logs" / (label + ".log")
        process = self.run_image(label, "run_tb3_sweep_shard.py",
                                 ["--sweep-inputs", "/run/sweep_inputs", "--inputs", "/g0",
                                  "--g7", "/g7", "--source", "/ref", "--reference", "/frozen/REFERENCE.json",
                                  "--ffd-manifest", "/frozen/FFD_RESTORE_MANIFEST.json", "--production",
                                  "/config/PRODUCTION_F1.json", "--out", "/run/attempts/" + label,
                                  "--case", case, "--shard-index", str(index), "--shard-count", str(count),
                                  "--field-batch-xy", "2", "--code-commit", BASE_COMMIT], log)
        return process, attempt, log

    def run_shards(self, jobs, phase, ceiling):
        pending = deque((job, 0) for job in jobs)
        active = {}
        failures = []
        while pending or active:
            budget = min(ceiling, self.resources.check(phase, len(active)))
            for job in list(active):
                process, attempt, log, index = active[job]
                exit_code = process.poll()
                if exit_code is None:
                    continue
                del active[job]
                case, shard, _ = job
                if exit_code == 0 and read(attempt / "MANIFEST.json")["status"] == "PASS":
                    if case.startswith(("G-T2_", "G-V_")):
                        for path in attempt.rglob("*"):
                            if path.is_file():
                                path.chmod(path.stat().st_mode & ~0o222)
                    attempt.rename(self.root / "shards" / case / "{:03d}".format(shard))
                    print("{} traced {} shard {:03d}".format(utc(), case, shard), flush=True)
                elif index == 0 and (exit_code == 137 or re.search(
                        "mmap.*Cannot allocate|bad_alloc|MemoryError|Out of memory",
                        log.read_text(errors="replace"))):
                    ceiling = max(1, ceiling // 2)
                    budget = min(ceiling, budget)
                    pending.append((job, 1))
                    print("{} retry {} after memory failure with ceiling {}".format(utc(), job, ceiling),
                          flush=True)
                else:
                    failures.append(dict(job=job, exit_code=exit_code, log=str(log)))
                    pending.clear()
            while not failures and pending and len(active) < budget:
                job, index = pending.popleft()
                active[job] = (*self.start_shard(job, index), index)
            if pending or active:
                time.sleep(2)
        if failures:
            write(self.root / (phase + "_FAILURE.json"), failures)
            raise RuntimeError("Trace worker failed; see {}_FAILURE.json".format(phase))

    def finish_image(self, label, args):
        while not self.resources.check(label + "_wait", 0):
            time.sleep(MONITOR_PERIOD_S)
        log = self.root / "logs" / (label + ".log")
        process = self.run_image(label, "finish_tb3_full_sweep.py", [
            "--inputs", "/run/sweep_inputs", "--shards", "/run/shards", "--out", "/run/results",
            "--model-source", "/model", "--banks-dir", "/ref", "--code-commit", BASE_COMMIT, *args,
        ], log, cpus=2, memory="24g")
        while process.poll() is None:
            self.resources.check(label, 1)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        if process.returncode:
            raise RuntimeError("{} failed; see {}".format(label, log))

    def compare_canary(self):
        mounts = [(base / "results" / sub / PILOT, "/prior{}/{}/{}".format(mount, sub, PILOT), ":ro")
                  for mount, base in ((0, BASE0), (45, BASE45)) for sub in ("H", "paths", "poses")]
        log = self.root / "logs" / "pilot_baseline_compare.log"
        process = self.run_image(
            "pilot_baseline_compare", "check_tb3_sweep_canary.py",
            ["--sweep-inputs", "/run/sweep_inputs", "--shard", "/run/shards/" + PILOT + "/000",
             "--mount0-results", "/prior0", "--mount45-results", "/prior45", "--out", "/run/CANARY.json"],
            log, extra_mounts=mounts)
        if process.wait():
            raise RuntimeError("Frozen G-T1 reference comparison failed; see {}".format(log))

    def execute(self):
        started = time.monotonic()
        self.resources.check("prelaunch", 0, force=True)
        cases = self.sweep["cases"]
        shards = {case: max(1, math.ceil(info["n_tasks"] / (6 if case.endswith("_P-F") else 18)))
                  for case, info in cases.items()}
        for case in cases:
            (self.root / "shards" / case).mkdir()
        (self.root / "attempts").mkdir()
        write(self.root / "RUN_MANIFEST.json", dict(
            role="IMPLEMENTER", question_ids=["G1-RT-TB3-001", "G1-RT-TB3-002"],
            started_utc=utc(), host=os.uname().nodename, account="KMS", base_commit=BASE_COMMIT,
            image=IMAGE, max_workers=self.resources.maximum, shard_counts=shards,
            sweep_manifest_sha256=sha(self.root / "sweep_inputs/SWEEP_MANIFEST.json"),
            source_sha256={p.name: sha(p) for p in (self.root / "code").glob("*.py")},
            original_input_sha256=self.original_hashes))
        jobs = {case: [(case, index, count) for index in range(count)]
                for case, count in shards.items()}
        self.run_shards(jobs.pop(PILOT), "pilot_trace", 3)
        self.compare_canary()
        self.finish_image("pilot_assembly", ["--case", PILOT])
        self.finish_image("pilot_g4", ["--pilot", PILOT])
        print("{} passed pilot trace, coverage, and G4 for both mounts".format(utc()), flush=True)
        all_jobs = [job for case in sorted(jobs) for job in jobs[case]]
        self.run_shards(all_jobs, "generation", self.resources.maximum)
        for case in sorted(jobs):
            self.finish_image("assemble_" + case.lower(), ["--case", case])
        self.finish_image("g4", ["--g4"])
        verified = {str(p): sha(p) for p in self.base_paths}
        if verified != self.original_hashes:
            raise RuntimeError("Prior production evidence changed during this run")
        self.resources.check("finished", 0, force=True)
        write(self.root / "VERIFY_RUN.json", dict(
            status="PASS", gate="G4", finished_utc=utc(), wall_seconds=time.monotonic()-started,
            original_inputs_unchanged=True, completion_sha256=sha(self.root / "results/COMPLETION.json"),
            resource_sha256=sha(self.root / "RESOURCES.jsonl")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--max-workers", type=int, required=True)
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    if (os.geteuid() != 1001 or os.uname().nodename != "acacia.postech.ac.kr"
            or root.parent != HOME or not root.name.startswith("G1_RT_TB3_FULL_SWEEP_")
            or not 1 <= args.max_workers <= 36):
        parser.error("Expected a dedicated sweep directory on Snowball/KMS with 1–36 workers")
    os.umask(0o077)
    Run(root, args.max_workers).execute()


if __name__ == "__main__":
    main()
