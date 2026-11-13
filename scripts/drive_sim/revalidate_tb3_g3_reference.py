"""G3 revalidation with a 400k-ray reference and the frozen production arm."""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path[:0] = ["/g3/recovery", "/g3/input"]
import run_tb3_g3 as g3
from run_tb3_g1_pilot import geometry_adapter, load_runtime


BASE = Path("/g3")
RUN = Path("/revalidation")
OUTPUT = RUN / "output"
REFERENCE_CONFIG = RUN / "REFERENCE_SOLVER.json"
RAYS = 400_000
SHARDS = 6
WORKERS = 48
G3_RESULT_SHA = "cdca5bc1d53a1ab65328bc9ddce0bd02ff810fd330785177fb87ffd1c0056c1b"


def start():
    return datetime.now(timezone.utc).isoformat()


def run_shard(case, shard):
    trace, _, _ = load_runtime(g3.SOURCE)
    geom, anchor = case.split("_")
    scene = g3.read(g3.INPUT / "scene/SCENE_MANIFEST.json")["geometries"][geom]
    ax = scene["anchors_xyz_m"][anchor][0]
    entry = dict(scene, anchors_xyz_m={"A": scene["anchors_xyz_m"][anchor]})
    trace.CorridorSetup, trace.C.build_scene = geometry_adapter(trace, entry, g3.INPUT / "scene")
    trace.C.SOLVER_SOURCE = SEED_CONFIG
    sys.argv = [trace.__file__, "--tasks", str(g3.INPUT / f"cases/{case}.json"),
                "--out", str(OUTPUT / case / "bin_by_bin"), "--nodes", "all", "--threads", "1",
                "--anchor-x", str(ax), "--shard", shard]
    trace.main()


def validate_inputs():
    g3.verify(BASE / "analysis/G3.json", G3_RESULT_SHA)
    g3.verify(Path(g3.__file__), g3.read(BASE / "analysis/G3.json")["evaluator_sha256"])
    for line in (BASE / "INPUT_SHA256.txt").read_text().splitlines():
        digest, relative = line.split(maxsplit=1)
        g3.verify(BASE / relative, digest)
    contract = g3.read(g3.INPUT / "G3_CONTRACT.json")
    ref = g3.read(g3.INPUT / "REFERENCE.json")
    for name, digest in (ref["method_b_sha256"] | contract["source_sha256"]).items():
        g3.verify(g3.SOURCE / name, digest)
    for bank in g3.read(g3.INPUT / "FFD_RESTORE_MANIFEST.json")["banks"]:
        g3.verify(g3.SOURCE / bank["filename"], bank["sha256"])
    g3.verify(g3.INPUT / "parity_gate.py", contract["parity_sha256"])
    if g3.read(g3.SOURCE / ref["solver_path"])["solver"] != ref["block_c_solver"]:
        raise ValueError("Original solver settings disagree with BLOCK_C")
    return contract, ref


def main():
    t0 = time.monotonic()
    contract, ref = validate_inputs()
    started = start()
    solver = ref["block_c_solver"] | {"samples_per_src": RAYS}
    OUTPUT.mkdir(exist_ok=False)
    g3.write(SEED_CONFIG, dict(solver=solver))
    for case in g3.CASES:
        (OUTPUT / case / "bin_by_bin").mkdir(parents=True)
        (OUTPUT / case / "node_interpolation").mkdir()
    stage_digests = {}
    for line in (BASE / "OUTPUT_SHA256.txt").read_text().splitlines():
        digest, relative = line.split(maxsplit=1)
        path = Path(relative)
        if path.parts[2:3] == ("node_interpolation",) and path.suffix in (".json", ".npz"):
            g3.verify(BASE / path, digest)
            target = RUN / path
            shutil.copyfile(BASE / path, target)
            g3.verify(target, digest)
            stage_digests[relative] = digest
    count = sum(n["trace_positions"] for n in contract["cases"].values())
    if len(stage_digests) != 2 * count:
        raise ValueError("Missing original node arm trace or receipt")
    g3.write(RUN / "REVALIDATION_CONTRACT.json",
             dict(kind="G3_REFERENCE_REVALIDATION", question_id=contract["question_id"],
                  started_utc=started, frozen_scope_sha256=g3.sha(g3.INPUT / "G3_CONTRACT.json"),
                  frozen_gate_sha256=G3_RESULT_SHA, evaluator_sha256=g3.sha(Path(g3.__file__)),
                  parity_sha256=contract["parity_sha256"], method_b_commit=ref["method_b_commit"],
                  container=ref["image"], governance=contract["governance"], workers=WORKERS,
                  runner_sha256=g3.sha(Path(__file__)), reference_arm_solver=solver,
                  production_arm_solver=ref["block_c_solver"], production_arm_sha256=stage_digests))
    print(f"Revalidating {count} reference traces, {WORKERS} workers, {RAYS} rays per bin", flush=True)

    def execute(job):
        case, i = job
        shard = f"{i}/{SHARDS}"
        with (OUTPUT / case / f"bin_by_bin_{i}.log").open("x") as log:
            call = ["nice", "-n", "10", sys.executable, "-u", __file__, "shard", case, shard]
            code = subprocess.run(call, stdout=log, stderr=subprocess.STDOUT).returncode
        print(f"{case} shard {shard} exit {code}", flush=True)
        return dict(case=case, shard=shard, exit_code=code)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        codes = list(pool.map(execute, ((case, i) for case in g3.CASES for i in range(SHARDS))))
    g3.write(RUN / "SHARD_EXIT.json", codes)
    if any(c["exit_code"] for c in codes):
        raise RuntimeError("Reference trace shard failed")
    trace_s = time.monotonic() - t0

    for case in g3.CASES:
        tasks = g3.read(g3.INPUT / f"cases/{case}.json")
        for task in tasks:
            receipt = OUTPUT / case / "bin_by_bin" / f"{task['tag']}_trace_receipt.json"
            if g3.read(receipt)["solver"] != solver:
                raise ValueError("Reference trace solver mismatch")
    report_root = RUN / "analysis"
    report_root.mkdir()
    result = g3.evaluate(contract, g3.parity_file(), report_root)
    result.update(kind="G3_REFERENCE_REVALIDATION", started_utc=started, finished_utc=start(),
                  contract_sha256=g3.sha(g3.INPUT / "G3_CONTRACT.json"),
                  revalidation_contract_sha256=g3.sha(RUN / "REVALIDATION_CONTRACT.json"),
                  reference_rays=RAYS, trace_stage_s=trace_s, wall_s=time.monotonic() - t0,
                  original_g3_status="FAIL", original_g3_sha256=G3_RESULT_SHA)
    g3.write(report_root / "G3.json", result)
    print("G3 reference revalidation " + result["status"], flush=True)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    g3.INPUT = BASE / "input"
    g3.OUT = OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "shard"))
    parser.add_argument("case", nargs="?")
    parser.add_argument("shard", nargs="?")
    args = parser.parse_args()
    if args.mode == "shard":
        run_shard(args.case, args.shard)
    else:
        sys.exit(main())
