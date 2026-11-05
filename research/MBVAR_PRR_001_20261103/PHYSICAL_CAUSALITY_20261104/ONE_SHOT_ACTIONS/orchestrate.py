"""One-shot data orchestration. No PathSolver calls in prepare, verify or test."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

HERE = Path(__file__).resolve().parent
LEDGER_SHA = "89c78f74f50e7486b8a831413ad9df478ff6386013ae85131455950d0ad4c5ef"

def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def dump(path, data):
    Path(path).write_text(json.dumps(data, indent=2, allow_nan=False)+"\n")

def ledger():
    assert sha(HERE/"LEDGER.csv") == LEDGER_SHA
    with (HERE/"LEDGER.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len({r["task_id"] for r in rows}) == 400
    return rows

def safe_extract(archive, target):
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as reader:
        for member in reader:
            destination = (target/member.name).resolve()
            assert destination.is_relative_to(target.resolve())
            assert member.isfile() or member.isdir()
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("wb") as out:
                    out.write(reader.extractfile(member).read())

def unpack(work):
    manifest = json.loads((HERE/"ASSETS.json").read_text())
    release = json.loads((HERE/"INPUT_RELEASE.json").read_text())
    for name in manifest:
        local = HERE/"assets"/name
        if not local.exists():
            local.parent.mkdir(exist_ok=True)
            urllib.request.urlretrieve(release["base_url"]+"/"+name, local)
    for label in sorted({v["group"] for v in manifest.values()}):
        target = work/(label+".tar.gz")
        with target.open("wb") as out:
            for name, value in sorted(manifest.items()):
                if value["group"] != label:
                    continue
                part = HERE/"assets"/name
                assert part.stat().st_size == value["size"] and sha(part) == value["sha256"]
                out.write(part.read_bytes())
        safe_extract(target, work if label=="inputs" else work/"reuse"/label)
    for name, expected in json.loads((HERE/"SOURCE_FILES.json").read_text()).items():
        assert sha(work/name) == expected, name

def original_qa(folder):
    import numpy as np
    results = json.loads((folder/"out/QA.json").read_text())
    for line in (folder/"SHA256SUMS.txt").read_text().splitlines():
        expected, name = line.split(None, 1)
        assert sha(folder/name) == expected, name
    for q in results:
        assert q["status"] == "PASS_TECHNICAL" and q["calls"] == 257
        route = q.get("route", "R4")
        rawdir = folder/"out"/f"{route}B_{q['pose']}_{q['mode']}"
        assert {p.name for p in (rawdir/"bins").glob("*.npz")} == {f"{i:03d}.npz" for i in range(257)}
        hs = []
        for i in range(257):
            with np.load(rawdir/"bins"/f"{i:03d}.npz") as z:
                a, tau = z["a"], z["tau"]
                assert a.shape == (2,2,len(tau)) and len(tau)>0
                for name in ("objects","interactions","valid","vertices","primitives","source_index"):
                    assert name in z.files
                assert np.isfinite(a).all() and np.isfinite(tau).all()
                h = (a*np.exp(np.complex64(-2j*np.pi*float(z["freq"]))*tau)[None,None,:]).sum(-1)
                assert np.linalg.norm(h-z["H"])/np.linalg.norm(z["H"]) <= 1e-8
                hs.append(z["H"])
        with np.load(rawdir/"RAW_H.npz") as z:
            assert z["H"].shape == (257,2,2)
            assert np.array_equal(z["H"], np.asarray(hs, dtype=complex))
            data=folder.parents[1]/"source/results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C"
            case=route+"_aB_m0"
            reference=data/(f"FULL_RF/H_{case}.npy" if q["mode"]=="Full" else f"H_LoS_{case}.npy")
            assert np.array_equal(z["reference"],np.load(reference,mmap_mode="r")[q["pose"]])
            error = np.linalg.norm(z["H"][:,:,0]-z["reference"][:,:,0])/np.linalg.norm(z["reference"][:,:,0])
            assert error <= (1e-3 if q["mode"]=="Full" else 1e-5)
        yield (route+"_B",str(q["pose"]),"FULL" if q["mode"]=="Full" else "NATIVE_LOS"),rawdir

def prepare(work):
    unpack(work)
    import numpy as np
    assert np.__version__ == "1.26.4", "FROZEN_NUMPY_REQUIRED"
    registered = ledger()
    reuse = {}
    for group in ("B0","B1","SM1a"):
        for key, rawdir in original_qa(work/"reuse"/group):
            task, = [r for r in registered if (r["route"],r["pose_id"],r["rf_mode"])==key]
            assert task["task_id"] not in reuse
            reuse[task["task_id"]] = str(rawdir.relative_to(work))
    # G2 is a prerequisite only. G3 supplies the 20 registered counterfactual keys.
    for group, expected_count in (("G2",4),("G3",20)):
        folders = sorted(p for p in (work/"reuse/G3"/group).iterdir() if p.is_dir() and p.name.startswith("SM2_"))
        assert len(folders) == expected_count
        for folder in folders:
            hashes = json.loads((folder/"ARTIFACT_HASHES.json").read_text())
            for name, expected in hashes.items():
                assert sha(folder/name) == expected, str(folder/name)
            assert len(list((folder/"bins").glob("*.npz"))) == 257
            assert len(list((folder/"repeat").glob("*.npz"))) == 3
            binding=json.loads((HERE/"PR35_BINDINGS.json").read_text())[folder.name]
            assert sha(folder/"MANIFEST.json")==binding["manifest_sha256"]
            assert sha(folder/"RAW.npz")==binding["raw_sha256"]
            m=json.loads((folder/"MANIFEST.json").read_text())
            assert m["code_revision"]==binding["code_revision"] and m["go_sha256"]==binding["go_sha256"]
            assert m["condition"]==binding["condition"] and m["raw_sha256"]==binding["raw_sha256"]
            assert m["status"]=="C3_RAW_NUMERICAL_PASS" and m["primary_solver_calls"]==257 and m["repeat_solver_calls"]==3
            assert {f.name for f in (folder/"repeat").glob("*.npz")}=={"000.npz","128.npz","256.npz"}
            if group == "G3":
                assert folder.name in {r["task_id"] for r in registered}
                reuse[folder.name] = str(folder.relative_to(work))
    pending = sorted([r for r in registered if r["task_id"] not in reuse],key=lambda r:(r["rf_mode"],r["task_id"]))
    assert len(reuse)==92 and len(pending)==308
    assert all(r["source_track"]=="ORIGINAL_6_WALL_CORRIDOR" for r in pending)
    assert sum(int(r["expected_solver_calls"]) for r in pending)==79156
    canary = [r for r in registered if r["route"]=="R4_B" and r["pose_id"] in ("194","234") and r["source_track"]=="ORIGINAL_6_WALL_CORRIDOR"]
    assert len(canary)==4
    dump(work/"shard_canary.json",canary)
    shards = [pending[i::4] for i in range(4)]
    for i, tasks in enumerate(shards):
        dump(work/f"shard_{i}.json",tasks)
    dump(work/"inventory.json",dict(reused=reuse,pending=[r["task_id"] for r in pending],
                                  calls=80184,canary="1028 fresh solver calls required before 4 production shards"))
    dump(work/"PRECHECK.json",dict(status="PASS_OFFLINE",registered=400,reused=92,
                                  new_tasks=308,new_calls=79156,shard_tasks=list(map(len,shards))))
    return shards

def run_shard(work, shard):
    # Manual dispatch creates an immutable run-specific draft release before this step.
    assert os.environ.get("RT_EXECUTION_APPROVED") == "80184"
    available=sorted(os.sched_getaffinity(0))
    assert len(available)>=4, "FOUR_CPU_RUNNER_REQUIRED"
    os.sched_setaffinity(0,set(available[:4]))
    tasks = json.loads((work/f"shard_{shard}.json").read_text())
    expected_count = 4 if shard=="canary" else 77
    assert len(tasks)==expected_count
    output = work/f"output_{shard}"
    output.mkdir(exist_ok=False)
    started = time.monotonic()
    tag = os.environ["RT_RELEASE_TAG"]
    repo = os.environ["GITHUB_REPOSITORY"]
    finished = threading.Event()
    remote_errors = []
    def monitor():
        while not finished.is_set():
            try:
                response = subprocess.check_output(["gh","release","view",tag,"--repo",repo,"--json","assets"],timeout=20)
                assets = json.loads(response)["assets"]
                jobs=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}/jobs?per_page=100"],timeout=20))["jobs"]
                if any(j["status"]=="completed" and j["conclusion"] in ("failure","cancelled","timed_out") for j in jobs):
                    (output/"STOP").touch()
                if any(a["name"].startswith("GLOBAL_STOP_") for a in assets):
                    (output/"STOP").touch()
            except Exception as error:
                remote_errors.append(str(error))
                # A failed control-plane read cannot authorize further generation.
                (output/"STOP").touch()
            finished.wait(10)
    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    def execute(row):
        if (output/"STOP").exists() or time.monotonic()-started>7200:
            return
        taskfile = output/(row["task_id"]+".json")
        dump(taskfile,row)
        env = dict(os.environ,RT_WORK=str(work),RT_OUT=str(output/row["task_id"]))
        with (output/(row["task_id"]+".log")).open("wb") as log:
            try:
                result = subprocess.run(["python","-u",str(HERE/"task.py"),str(taskfile)],
                                        env=env,cwd=work/"source",stdout=log,stderr=subprocess.STDOUT,timeout=900)
                failed = result.returncode != 0
            except subprocess.TimeoutExpired:
                failed = True
        if failed:
            (output/"STOP").touch()
            notice = work/f"GLOBAL_STOP_{shard}.json"
            dump(notice,dict(task_id=row["task_id"],reason="KEY_FAILURE",shard=shard))
            subprocess.run(["gh","release","upload",tag,str(notice),"--clobber","--repo",repo],timeout=30,check=False)
        return row["task_id"]
    # Submit at most four keys so failure cannot leave a queued solver call.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for start in range(0,len(tasks),4):
            list(pool.map(execute,tasks[start:start+4]))
            if (output/"STOP").exists():
                break
    finished.set()
    watcher.join(timeout=25)
    statuses=[]
    for row in tasks:
        result=output/row["task_id"]/"result.json"
        receipt=json.loads(result.read_text()) if result.exists() else {}
        statuses.append(dict(task_id=row["task_id"],status=receipt.get("status","NOT_RUN_OR_INTERRUPTED"),
                             calls=receipt.get("calls",None if (output/row["task_id"]).exists() else 0),
                             saved_bins=len(list((output/row["task_id"]).glob("*/bins/*.npz")))))
    dump(output/"STATUS.json",statuses)
    dump(output/"CONTROL_PLANE_ERRORS.json",remote_errors)
    package(output,work/f"shard_{shard}.tar.gz")
    assert len(statuses)==expected_count and all(r["status"]=="PASS_TECHNICAL" for r in statuses)

def package(folder, destination):
    hashes={str(p.relative_to(folder)).replace(chr(92),"/"):sha(p) for p in folder.rglob("*") if p.is_file() and p.name!="OUTPUT_SHA256.json"}
    dump(folder/"OUTPUT_SHA256.json",hashes)
    with tarfile.open(destination,"w:gz") as archive:
        archive.add(folder,arcname=folder.name)
    dump(Path(str(destination)+".sha256.json"),dict(sha256=sha(destination),bytes=destination.stat().st_size))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=["prepare","run"])
    parser.add_argument("--work",type=Path,required=True)
    parser.add_argument("--shard",choices=["canary","0","1","2","3"])
    args=parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=True)
    if args.mode=="prepare":
        prepare(args.work)
    else:
        run_shard(args.work,args.shard)

if __name__=="__main__":
    main()

