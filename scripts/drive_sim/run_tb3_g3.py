
"""TB3 G3: pair the frozen per-bin and node traces on G0 positions.

Prepare inputs with: run_tb3_g3.py prepare G0_DIR G2_DIR INPUT_DIR TB3_COMMIT METHOD_B_CHECKOUT.
Stage this runner and run_tb3_g3_snowball.sh in INPUT_DIR before submitting the run.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/run-g3")
INPUT = Path("/input")
SOURCE = Path("/ref")
OUT = ROOT / "output"
CASES = tuple(f"{geom}_{anchor}" for geom in ("G-T1", "G-T2", "G-V") for anchor in "ABC")
SETS = ("P-A_TEACH", "P-A_REPEAT", "P-A_PRIME", "P-B", "C1", "C2", "C3", "C4")
PREREG = "results/DRIVE_SIM_20261007/S0/PREREG.json"
PARITY_RELATIVE_PATH = Path("scripts/drive_sim/parity_gate.py")
PARITY_SHA256 = "6d015180eb56ea076e12880d2fc2d60361b6ba8bb0b8dac7cde5edbb5e887d45"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, data):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    import hashlib
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Input SHA256 mismatch: {path}")


def prepare(g0, g2, dest, base_commit, reference_checkout):
    """Freeze the sample from G0 before seeing any parity result."""
    manifest = read(g0 / "RUN_MANIFEST.json")
    digests = manifest["output_sha256"]
    verify(g0 / "gates/G0.json", digests["gates/G0.json"])
    g2_result = read(g2 / "output/G2.json")
    g2_verification = read(g2 / "LOCAL_VERIFICATION.json")
    if (manifest["status"] != "PASS" or manifest["base_commit"] != base_commit
            or read(g0 / "gates/G0.json")["status"] != "PASS"
            or g2_result["status"] != "PASS" or g2_verification["status"] != "PASS"):
        raise ValueError("Missing G0 or G2 PASS for this research tree")
    verify(g2 / "output/G2.json", g2_verification["remote_result_sha256"])
    verify(g2 / "input/run_tb3_g1_pilot.py", "a8b086875196bbb778e68cd2821be08cd72fc34f83d0ef0fd116e3baa59dacf2")
    verify(g0 / "scene/SCENE_MANIFEST.json", digests["scene/SCENE_MANIFEST.json"])
    scene = read(g0 / "scene/SCENE_MANIFEST.json")
    import shutil
    parity = dest / "method_b" / PARITY_RELATIVE_PATH
    parity.parent.mkdir(parents=True, exist_ok=True)
    with parity.open("xb") as stream:
        stream.write((reference_checkout / PARITY_RELATIVE_PATH).read_bytes().replace(b"\r\n", b"\n"))
    verify(parity, PARITY_SHA256)
    for name in ("REFERENCE.json", "FFD_RESTORE_MANIFEST.json", "run_tb3_g1_pilot.py"):
        shutil.copyfile(g2 / "input" / name, dest / name)
    shutil.copyfile(g0 / "RUN_MANIFEST.json", dest / "G0_RUN_MANIFEST.json")
    shutil.copyfile(g2 / "output/G2.json", dest / "G2.json")
    tasks_dir = dest / "cases"
    tasks_dir.mkdir()
    mesh_dir = dest / "scene"
    mesh_dir.mkdir()
    shutil.copyfile(g0 / "scene/SCENE_MANIFEST.json", mesh_dir / "SCENE_MANIFEST.json")

    for geom in scene["geometries"].values():
        for item in geom["material_bindings"]:
            rel = Path("scene") / item["ply"]
            verify(g0 / rel, item["ply_sha256"])
            if item["ply_sha256"] != digests[rel.as_posix()]:
                raise ValueError(f"G0 mesh manifest mismatch: {rel}")
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(g0 / rel, dest / rel)

    totals = {}
    for case in CASES:
        files = {}
        for name in ("rf_poses", "rf_tasks", "SAMPLES"):
            rel = f"poses/{case}/{name}.json"
            verify(g0 / rel, digests[rel])
            files[name] = read(g0 / rel)
        poses = files["rf_poses"]
        tasks = files["rf_tasks"]
        tag_by_id = {i: t["tag"] for t in tasks for i in t["pose_ids"]}
        if set(tag_by_id) != set(range(len(poses))) or sum(len(t["pose_ids"]) for t in tasks) != len(poses):
            raise ValueError(f"Incomplete pose-to-task mapping: {case}")
        geom, anchor = case.split("_")
        ax, ay, _ = scene["geometries"][geom]["anchors_xyz_m"][anchor]
        selected = {}

        def add(tag, reason):
            selected.setdefault(tag, []).append(reason)

        for group in SETS:
            rows = [r for r in files["SAMPLES"] if r["set"] == group]
            if group in ("P-A_TEACH", "P-A_REPEAT"):
                for station in ("P001", "P009", "P018"):
                    r = next(r for r in rows if r["station_id"] == station and r["protocol"] == "base")
                    add(tag_by_id[r["pose_id"]], f"{group}:{station}")
            else:
                ordered = list(dict.fromkeys(tag_by_id[r["pose_id"]] for r in rows))
                if len(ordered) < 3:
                    raise ValueError(f"Not enough positions: {case}/{group}")
                for i in (0, (len(ordered) - 1) // 2, len(ordered) - 1):
                    add(ordered[i], f"{group}:position_index_{i}")
        for t in (min(tasks, key=lambda t: math.hypot(t["x"] - ax, t["y"] - ay)),
                  max(tasks, key=lambda t: math.hypot(t["x"] - ax, t["y"] - ay))):
            add(t["tag"], "anchor_horizontal_distance_extreme")
        if geom == "G-T2":
            for x in (6.35, 9.30, 13.15):
                t = min(tasks, key=lambda t: (abs(t["x"] - x), -t["y"], t["task_id"]))
                add(t["tag"], f"feature_midpoint_x_{x:.2f}")

        subset = []
        for task in tasks:
            tag = task["tag"]
            if tag not in selected:
                continue
            if math.hypot(task["x"] - ax, task["y"] - ay) < 0.01:
                raise ValueError(f"Unexpected anchor-axis degeneracy: {case}/{tag}")
            yaws = [{"pose_id": i, "yaw_deg": poses[i]["yaw_body_deg"]} for i in task["pose_ids"]]
            subset.append(dict(task, sampled_yaws=yaws, sample_reasons=selected[tag]))
        if len(subset) != len(selected):
            raise ValueError(f"Duplicate or missing trace tag: {case}")
        write(tasks_dir / f"{case}.json", subset)
        totals[case] = dict(trace_positions=len(subset), poses=sum(len(t["sampled_yaws"]) for t in subset))

    config = dict(question_id="G1-RT-TB3-001", role="IMPLEMENTER", gate="G3",
                  g0_base_commit=base_commit, method_b_commit=manifest["method_b_reference"],
                  governance=manifest["governance"], threshold_key="G2p_B_node_interpolation",
                  prereg_path=PREREG,
                  source_sha256={PREREG: "db28d1dd0dbb5a7c5695b0bb3ed630f5abaa10eb6c1eb48545c6b14c9a1a1d01",
                                 "src/qclean_uwb/features/fp_power.py":
                                     "6da23ff66372a106dfbea521cc176031169210fed226e38d7d2db55b21f7c86b"},
                  parity_sha256=PARITY_SHA256,
                  arms={"bin_by_bin": "all", "node_interpolation": "17"}, mount_deg=0,
                  anchor_axis_min_m=0.01,
                  selection="Per case: TEACH and REPEAT base at P001/P009/P018; first, middle, last distinct XY "
                            "in observation order for P-A_PRIME/P-B/C1/C2/C3/C4; nearest and farthest from anchor; "
                            "G-T2 also the nearest task in x to each feature midpoint, ties by greatest y then task ID. "
                            "Union by task tag; every G0 yaw at each selected XY; no RF-dependent selection.",
                  thresholds_applied="Existing G2p checks applied to each case and the pooled sample; "
                                     "257-bin Method B is the paired reference; H errors are reported as diagnostics.",
                  workers=36, shards_per_arm=4, cases=totals)
    write(dest / "G3_CONTRACT.json", config)
    print(totals, flush=True)


def run_shard(case, arm, nodes, shard):
    from run_tb3_g1_pilot import geometry_adapter, load_runtime
    trace, _, versions = load_runtime(SOURCE)
    geom, anchor = case.split("_")
    scene = read(INPUT / "scene/SCENE_MANIFEST.json")["geometries"][geom]
    ax = scene["anchors_xyz_m"][anchor][0]
    entry = dict(scene, anchors_xyz_m={"A": scene["anchors_xyz_m"][anchor]})
    trace.CorridorSetup, trace.C.build_scene = geometry_adapter(trace, entry, INPUT / "scene")
    sys.argv = [trace.__file__, "--tasks", str(INPUT / "cases" / f"{case}.json"),
                "--out", str(OUT / case / arm), "--nodes", nodes, "--threads", "1",
                "--anchor-x", str(ax), "--shard", shard]
    print(versions, sys.argv, flush=True)
    trace.main()


def evaluate(config, parity_path, report_root):
    sys.path[:0] = [str(SOURCE / "scripts"), str(SOURCE / "src")]
    import numpy as np
    import importlib.util

    verify(parity_path, config["parity_sha256"])
    spec = importlib.util.spec_from_file_location("parity_gate", parity_path)
    parity = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(parity)

    gates = read(SOURCE / PREREG)["config"]["gates"]
    thresholds = {k: v["value"] for k, v in gates[config["threshold_key"]].items()}
    banks = parity.load_banks()
    freqs = banks[0].freqs_hz
    if len(freqs) != 257:
        raise ValueError("Unexpected frequency axis")
    all_rows, all_missing, all_unusable = [], [], []
    reports = {}
    for case in CASES:
        rows, missing, unusable, audit = [], [], [], []
        for task in read(INPUT / "cases" / f"{case}.json"):
            tag = task["tag"]
            yaws = [p["yaw_deg"] for p in task["sampled_yaws"]]
            channels = {}
            for arm, nodes in config["arms"].items():
                base = OUT / case / arm / f"{tag}_trace"
                path = base.with_name(base.name + ".npz")
                receipt_path = base.with_name(base.name + "_receipt.json")
                if not path.is_file() or not receipt_path.is_file():
                    missing.append(dict(case=case, arm=arm, tag=tag))
                    continue
                trace = parity.load_trace(path)
                receipt = read(receipt_path)
                count = receipt["n_nodes"]
                indices = trace["node_bins"]
                valid_nodes = (np.array_equal(indices, np.arange(257)) if nodes == "all"
                               else np.isin(np.arange(0, 257, 16), indices).all())
                if (receipt["status"] != "OK" or trace["status"] != "OK"
                        or count != len(indices) or not valid_nodes
                        or float(trace["x"]) != task["x"] or float(trace["y"]) != task["y"]):
                    unusable.append(dict(case=case, arm=arm, tag=tag, status=receipt["status"],
                                         n_nodes=count, valid_nodes=bool(valid_nodes)))
                    continue
                h = parity.h_for_antenna_yaws(trace, banks, yaws)
                if h.shape != (len(yaws), 257, 2, 2) or not np.isfinite(h).all():
                    unusable.append(dict(case=case, arm=arm, tag=tag, status="INVALID_H"))
                    continue
                channels[arm] = h
                audit.append({k: receipt[k] for k in
                              ("tag", "n_nodes", "elapsed_s", "unmatched_paths", "screen_exceeded")} | {"arm": arm})
            if len(channels) != 2:
                continue
            for i, pose in enumerate(task["sampled_yaws"]):
                row = parity.compare(channels["node_interpolation"][i], channels["bin_by_bin"][i], freqs)
                if not all(math.isfinite(v) for v in row.values()):
                    raise ValueError(f"Nonfinite parity metric at {case}/{tag}/{pose['pose_id']}")
                rows.append(dict(case=case, tag=tag, xy=[task["x"], task["y"]], **pose, **row))
        expected = config["cases"][case]["poses"]
        if len(rows) != expected and not (missing or unusable):
            raise ValueError(f"Unexpected parity count at {case}")
        report = parity.summarize(rows, thresholds, "G3") if rows else {"passed": False}
        report = parity.coverage_checked(report, missing, unusable)
        report.update(expected_poses=expected, trace_audit=audit)
        reports[case] = report
        (report_root / case).mkdir(exist_ok=True)
        write(report_root / case / "PARITY_ROWS.json", rows)
        all_rows.extend(rows)
        all_missing.extend(missing)
        all_unusable.extend(unusable)

    pooled = parity.summarize(all_rows, thresholds, "G3") if all_rows else {"passed": False}
    pooled = parity.coverage_checked(pooled, all_missing, all_unusable)
    return dict(status="PASS" if pooled["passed"] and all(r["passed"] for r in reports.values()) else "FAIL",
                pooled=pooled, cases=reports)


def parity_file():
    return Path(__file__).parent / "method_b" / PARITY_RELATIVE_PATH


def evaluate_completed_traces():
    config = read(INPUT / "G3_CONTRACT.json")
    codes = read(OUT / "SHARD_EXIT.json")
    expected = {(case, arm, f"{i}/{config['shards_per_arm']}") for case in CASES
                for arm in config["arms"] for i in range(config["shards_per_arm"])}
    actual = {(c["case"], c["arm"], c["shard"]) for c in codes}
    if actual != expected or len(actual) != len(codes) or any(c["exit_code"] for c in codes):
        raise ValueError("Trace shards did not complete successfully")
    report_root = ROOT / "analysis"
    report_root.mkdir(exist_ok=False)
    t0 = time.monotonic()
    start = datetime.now(timezone.utc)
    result = evaluate(config, parity_file(), report_root)
    end = datetime.now(timezone.utc)
    trace_start = datetime.fromisoformat((ROOT / "STARTED_UTC.txt").read_text().strip())
    trace_end = datetime.fromisoformat((ROOT / "FINISHED_UTC.txt").read_text().strip())
    result.update(trace_started_utc=trace_start.isoformat(), trace_finished_utc=trace_end.isoformat(),
                  evaluation_started_utc=start.isoformat(), evaluation_finished_utc=end.isoformat(),
                  trace_stage_s=(trace_end - trace_start).total_seconds(), evaluation_s=time.monotonic()-t0,
                  contract_sha256=sha(INPUT / "G3_CONTRACT.json"), trace_receipt_sha256=sha(OUT / "SHARD_EXIT.json"),
                  evaluator_sha256=sha(Path(__file__)), parity_sha256=sha(parity_file()))
    write(report_root / "G3.json", result)
    print({key: value for key, value in result["pooled"].items() if key != "worst_by_abs_ds"}, flush=True)
    print("G3 " + result["status"], flush=True)
    return 0 if result["status"] == "PASS" else 2


def main():
    t0 = time.monotonic()
    started = datetime.now(timezone.utc).isoformat()
    config = read(INPUT / "G3_CONTRACT.json")
    ref = read(INPUT / "REFERENCE.json")
    for name, digest in (ref["method_b_sha256"] | config["source_sha256"]).items():
        verify(SOURCE / name, digest)
    for bank in read(INPUT / "FFD_RESTORE_MANIFEST.json")["banks"]:
        verify(SOURCE / bank["filename"], bank["sha256"])
    verify(parity_file(), config["parity_sha256"])
    if read(SOURCE / ref["solver_path"])["solver"] != ref["block_c_solver"]:
        raise ValueError("Solver settings differ from BLOCK_C")
    for binding in read(INPUT / "scene/SCENE_MANIFEST.json")["geometries"].values():
        for item in binding["material_bindings"]:
            verify(INPUT / "scene" / item["ply"], item["ply_sha256"])
    OUT.mkdir(exist_ok=False)
    jobs = []
    shards = config["shards_per_arm"]
    for case in CASES:
        (OUT / case).mkdir()
    for arm, nodes in config["arms"].items():
        for case in CASES:
            for i in range(shards):
                jobs.append((case, arm, nodes, f"{i}/{shards}"))

    def execute(job):
        case, arm, nodes, shard = job
        log = OUT / case / f"{arm}_{shard.split('/')[0]}.log"
        with log.open("x") as stream:
            cmd = ["nice", "-n", "10", sys.executable, "-u", __file__, "shard", *job]
            code = subprocess.run(cmd, stdout=stream, stderr=subprocess.STDOUT).returncode
        print(f"{case} {arm} shard {shard} exit {code}", flush=True)
        return dict(case=case, arm=arm, shard=shard, exit_code=code)

    print(f"{len(jobs)} shards on up to {config['workers']} workers; cases: {config['cases']}", flush=True)
    with ThreadPoolExecutor(max_workers=config["workers"]) as pool:
        codes = list(pool.map(execute, jobs))
    write(OUT / "SHARD_EXIT.json", codes)
    if any(c["exit_code"] for c in codes):
        raise RuntimeError("One or more G3 trace processes failed")
    trace_s = time.monotonic() - t0
    result = evaluate(config, parity_file(), OUT)
    result.update(started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
                  wall_s=time.monotonic() - t0, trace_s=trace_s, contract_sha256=sha(INPUT / "G3_CONTRACT.json"))
    write(OUT / "G3.json", result)
    print({key: value for key, value in result["pooled"].items() if key != "worst_by_abs_ds"}, flush=True)
    print("G3 " + result["status"], flush=True)
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    if sys.argv[1:2] == ["prepare"]:
        prepare(*map(Path, sys.argv[2:5]), sys.argv[5], Path(sys.argv[6]))
    elif sys.argv[1:2] == ["evaluate-only"]:
        sys.exit(evaluate_completed_traces())
    elif sys.argv[1:2] == ["shard"]:
        run_shard(*sys.argv[2:])
    else:
        sys.exit(main())
