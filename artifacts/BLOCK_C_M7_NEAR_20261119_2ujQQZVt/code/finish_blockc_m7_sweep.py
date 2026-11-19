"""Verify and merge the four original-M7 BLOCK_C centerline shards, then run G4 and G8."""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import shutil
import sys
import time

import numpy as np

from merge_tb3_production import LOS_ANGLES, fill_los, load_near
from run_tb3_g1_pilot import read, sha, write
from run_tb3_production import utc_now, verify
from validate_tb3_g4 import MODEL_SOURCE_SHA256, evaluate_case, load_model


CASE = "BLOCKC_B"


def bound_path(root, name):
    path = (root / name).resolve()
    if root.resolve() not in path.parents:
        raise ValueError(f"Artifact escapes its root: {name}")
    return path


def verify_artifacts(directory, manifest):
    files = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
             if p.is_file() and p != directory / "MANIFEST.json"}
    if files != set(manifest["output_sha256"]) or files != set(manifest["output_bytes"]):
        raise ValueError(f"Unrecorded or missing artifacts: {directory}")
    for name, digest in manifest["output_sha256"].items():
        path = bound_path(directory, name)
        verify(path, digest)
        if path.stat().st_size != manifest["output_bytes"][name]:
            raise ValueError(f"Artifact byte count differs: {path}")


def verified_shards(root, code_commit):
    inputs = root / "inputs"
    contract = read(inputs / "RUN_CONTRACT.json")
    for name, digest in contract["input_sha256"].items():
        verify(bound_path(inputs, name), digest)
    config_path = inputs / "M7_RT_CONFIG.json"
    if "M7_RT_CONFIG.json" not in contract["input_sha256"]:
        raise ValueError("Original M7 configuration must be bound in the contract")
    config = read(config_path)
    solver = config["solver"]
    if (solver["refraction"] is not True or solver["samples_per_src"] != 100000
            or solver["max_depth"] != 3 or solver["seed"] != 20260924):
        raise ValueError("Original M7 solver envelope differs")
    code_hashes = contract["current_code_sha256"]
    for name, digest in code_hashes.items():
        verify(bound_path(Path(__file__).parent, name), digest)
    runner_sha = sha(Path(__file__).with_name("run_blockc_m7_sweep.py"))
    if "run_blockc_m7_sweep.py" not in code_hashes:
        raise ValueError("The original-M7 runner must be frozen in the contract")
    invariants = ("method_b_sha256", "ffd_sha256", "runtime_versions", "engine",
                  "source_commit", "material_bindings", "runner_sha256")
    expected_runtime = None

    def common(directory):
        nonlocal expected_runtime
        manifest = read(directory / "MANIFEST.json")
        if (manifest["status"] != "PASS" or manifest["scope"] != "M7_CENTERLINE_SWEEP_SHARD"
                or manifest["code_commit"] != code_commit
                or manifest["source_commit"] != contract["source_commit"]
                or manifest["run_contract_sha256"] != sha(inputs / "RUN_CONTRACT.json")
                or manifest["config_sha256"] != sha(config_path) or manifest["engine"] != config
                or manifest["input_sha256"] != contract["input_sha256"]
                or manifest["method_b_sha256"] != contract["method_b_sha256"]
                or manifest["ffd_sha256"] != contract["ffd_sha256"]
                or manifest["runner_sha256"] != runner_sha or manifest["mounts_deg"] != [0]
                or any(manifest["runtime_versions"][name] != version for name, version in
                       (("sionna-rt", "2.0.1"), ("mitsuba", "3.8.0"), ("drjit", "1.3.1")))
                or manifest["shared_trace"] is not True or manifest["original_h_array_equal"] is not True
                or any(manifest[key] is not False for key in
                       ("finite_face_guard", "native_los_override", "post_filter"))
                or manifest["extra_export_solver_calls"] != 0
                or manifest["serialization_g8"]["status"] != "PASS"):
            raise ValueError(f"Invalid original-M7 provenance: {directory}")
        runtime = {key: manifest[key] for key in invariants}
        if expected_runtime is None:
            expected_runtime = runtime
        elif runtime != expected_runtime:
            raise ValueError("Original-M7 source, geometry or runtime differs between runs")
        verify_artifacts(directory, manifest)
        if read(directory / "SERIALIZATION_G8.json")["status"] != "PASS":
            raise ValueError(f"Serialization gate failed: {directory}")
        return manifest

    baseline_gate = read(root / "BASELINE_PASS.json")
    if (baseline_gate["status"] != "PASS" or baseline_gate["routes"] != ["R2", "R4", "R5"]
            or set(baseline_gate["manifest_sha256"]) != {"R2", "R4", "R5"}):
        raise ValueError("All three original M7 baseline checks must pass before completion")
    baseline_contracts = {row["route"]: row for row in contract["baselines"]}
    if set(baseline_contracts) != {"R2", "R4", "R5"}:
        raise ValueError("Contract must bind R2/R4/R5 original baseline H and rows")
    baselines = {}
    for route in baseline_gate["routes"]:
        directory = root / "baseline" / route
        verify(directory / "MANIFEST.json", baseline_gate["manifest_sha256"][route])
        manifest = common(directory)
        comparison = read(directory / "BASELINE_COMPARISON.json")
        expected = baseline_contracts[route]
        if (comparison != manifest["baseline_comparison"] or comparison["array_equal"] is not True
                or comparison["max_abs_delta_h"] != 0
                or comparison["H_sha256"] != expected["original_H_sha256"]
                or comparison["pose_ids"] != expected["original_pose_ids"]
                or len(comparison["pose_ids"]) != 3 or manifest["poses"] != 3):
            raise ValueError(f"Original M7 baseline H parity failed: {route}")
        baselines[route] = directory

    tasks, poses = (read(inputs / name) for name in ("rf_tasks.json", "rf_poses.json"))
    if ([task["task_id"] for task in tasks] != list(range(40))
            or [pose["pose_id"] for pose in poses] != list(range(1440))
            or sorted(i for task in tasks for i in task["pose_ids"]) != list(range(1440))
            or any(len(task["pose_ids"]) != 36 for task in tasks)):
        raise ValueError("Expected 40 tasks partitioning all 1440 global pose IDs")
    shards = []
    for index in range(4):
        directory = root / "attempts" / "production" / f"shard{index}"
        manifest = common(directory)
        selected = tasks[index::4]
        ids = np.array(sorted(i for task in selected for i in task["pose_ids"]), dtype=np.int64)
        if ((manifest["shard_index"], manifest["shard_count"]) != (index, 4)
                or manifest["selected_task_ids"] != [task["task_id"] for task in selected]
                or manifest["poses"] != len(ids) or manifest["trace_positions"] != len(selected)
                or manifest["pose_table_sha256"] != sha(inputs / "rf_poses.json")
                or manifest["task_table_sha256"] != sha(inputs / "rf_tasks.json")
                or manifest["baseline_comparison"] is not None):
            raise ValueError(f"Incomplete production shard coverage: {directory}")
        mount = directory / "mount0"
        received = np.load(mount / "POSE_IDS.npy", allow_pickle=False)
        if received.dtype != np.int64 or not np.array_equal(received, ids):
            raise ValueError(f"Global pose IDs differ: {directory}")
        receipts = read(directory / "TRACE_RECEIPTS.json")
        with np.load(mount / "PATHS_LoS.npz", allow_pickle=False) as archive:
            frequency_axis = archive["freqs_hz"]
        raw_files = set()
        for task, receipt in zip(selected, receipts, strict=True):
            nodes = receipt["node_bins"]
            if (any(receipt[key] != task[key] for key in ("task_id", "tag", "pose_ids"))
                    or nodes != sorted(set(nodes)) or not set(range(0, 257, 16)).issubset(nodes)
                    or any(not isinstance(node, int) or not 0 <= node <= 256 for node in nodes)
                    or receipt["solver_calls"] != len(nodes) or receipt["n_full_paths"] < 1
                    or receipt["original_h_array_equal"] is not True or receipt["mounts_deg"] != [0]):
                raise ValueError(f"Invalid adaptive same-trace receipt: {directory}")
            raw = bound_path(directory, receipt["raw_trace"])
            verify(raw, receipt["raw_trace_sha256"])
            raw_files.add(raw)
            with np.load(raw, allow_pickle=False) as data:
                count = receipt["n_full_paths"]
                if (str(data["status"]) != "OK" or not np.array_equal(data["node_bins"], nodes)
                        or data["jones"].shape != (len(nodes), count, 3, 3)
                        or data["tau"].shape != (count,) or data["ang"].shape != (4, count)
                        or data["present"].shape != (len(nodes), count)
                        or not np.array_equal(data["node_freq_hz"], frequency_axis[nodes])
                        or data["interactions"].shape != (count, solver["max_depth"])
                        or data["objects"].shape != data["interactions"].shape
                        or not np.array_equal(data["path_counts"], data["present"].sum(axis=1))
                        or float(data["x"]) != task["x"] or float(data["y"]) != task["y"]
                        or any(not np.isfinite(data[key]).all()
                               for key in ("jones", "tau", "ang", "node_freq_hz"))):
                    raise ValueError(f"Incomplete original raw trace: {raw}")
        if (len(raw_files) != len(selected)
                or raw_files != {path.resolve() for path in (directory / "trace").glob("*_trace.npz")}
                or manifest["solver_calls"] != sum(row["solver_calls"] for row in receipts)):
            raise ValueError("Adaptive solver counts or unique raw trace coverage differ")
        shards.append((mount, ids, receipts, manifest, sha(directory / "MANIFEST.json")))
    return contract, shards, baselines

def run(args):
    started, started_utc = time.monotonic(), utc_now()
    contract, shards, baselines = verified_shards(args.root, args.code_commit)
    results = args.root / "results"
    results.mkdir(mode=0o700, exist_ok=False)
    h_dir, p_dir, pose_dir = (results / folder / CASE for folder in ("H", "paths", "poses"))
    for folder in (h_dir, p_dir, pose_dir):
        folder.mkdir(parents=True, mode=0o700)
    traces_dir = results / "traces" / CASE
    traces_dir.mkdir(parents=True, mode=0o700)
    baseline_dir = results / "baselines"
    baseline_dir.mkdir()
    shutil.copyfile(args.root / "BASELINE_PASS.json", baseline_dir / "BASELINE_PASS.json")
    for route, directory in baselines.items():
        destination = baseline_dir / route
        destination.mkdir()
        for name in ("MANIFEST.json", "BASELINE_COMPARISON.json"):
            shutil.copyfile(directory / name, destination / name)
    shape = (1440, 257, 2, 2)
    channels = {name: np.lib.format.open_memmap(h_dir / name, mode="w+", dtype=np.complex128,
                                               shape=shape)
                for name in ("H_full.npy", "H_LoS.npy")}
    los = dict(a=np.empty(shape, np.complex128), tau=np.empty(shape[:2], np.float64),
               counts=np.empty(shape[:2], np.int64), interactions=np.empty(shape[:2], np.int64),
               **{name: np.empty(shape[:2], np.float64) for name in LOS_ANGLES})
    frequencies, schema, all_near, receipts = None, None, [], []
    for mount, ids, shard_receipts, _, _ in shards:
        with np.load(mount / "PATHS_LoS.npz", allow_pickle=False) as source:
            current_frequencies = source["freqs_hz"]
        if frequencies is None:
            frequencies = current_frequencies
            if (frequencies.dtype != np.float64 or frequencies.shape != (257,)
                    or not np.isfinite(frequencies).all() or np.any(np.diff(frequencies) <= 0)):
                raise ValueError("Invalid frequency grid")
        elif not np.array_equal(frequencies, current_frequencies):
            raise ValueError("Shard frequency axes differ")
        for name, target in channels.items():
            data = np.load(mount / name, mmap_mode="r", allow_pickle=False)
            if (data.shape != (len(ids), *shape[1:]) or data.dtype != np.complex128
                    or not np.isfinite(data).all()):
                raise ValueError(f"Invalid channel shard: {mount / name}")
            target[ids] = data
        fill_los(los, mount, ids, frequencies, channels["H_LoS.npy"][ids])
        all_near.append(load_near(mount, set(ids.tolist()), channels["H_LoS.npy"], frequencies))
        candidate = read(mount / "PATHS_NEAR_SCHEMA.json")
        if schema is None:
            schema = candidate
        elif schema != candidate:
            raise ValueError("PATHS_NEAR schemas differ")
        for receipt in shard_receipts:
            raw = bound_path(mount.parent, receipt["raw_trace"])
            shutil.copyfile(raw, traces_dir / f"task_{receipt['task_id']:04d}_trace.npz")
        receipts.extend(shard_receipts)
    for channel in channels.values():
        channel.flush()
    ids = np.arange(1440, dtype=np.int64)
    np.savez_compressed(p_dir / "PATHS_LoS.npz", pose_id=ids, freqs_hz=frequencies, **los)
    merged = {key: np.concatenate([pack[key] for pack in all_near]) for key in all_near[0]}
    order = np.lexsort((merged["path_index"], merged["pose_id"]))
    np.savez_compressed(p_dir / "PATHS_NEAR.npz", frequencies_hz=frequencies,
                        **{key: value[order] for key, value in merged.items()})
    write(p_dir / "PATHS_NEAR_SCHEMA.json", schema)
    receipts.sort(key=lambda row: row["task_id"])
    write(p_dir / "TRACE_RECEIPTS.json", receipts)
    for path in sorted((args.root / "inputs").iterdir()):
        if path.is_file() and path.suffix.lower() in (".json", ".csv"):
            shutil.copyfile(path, pose_dir / path.name)
    model, observation, banks, model_frequencies, model_sha, bank_sha = load_model(args)
    model_root = args.model_source.resolve()
    model_src = model_root / "src" if (model_root / "src").is_dir() else model_root
    loaded_modules = {}
    for relative, expected_sha in MODEL_SOURCE_SHA256.items():
        module_name = relative[:-3].replace("/", ".")
        module = __import__(module_name, fromlist=["__file__"])
        actual = Path(module.__file__).resolve()
        if actual != (model_src / relative).resolve() or sha(actual) != expected_sha:
            raise ValueError(f"Independent G4 loaded an unexpected module: {actual}")
        loaded_modules[module_name] = dict(path=str(actual), sha256=sha(actual))
    # This helper imports qclean_uwb too. Load it only after the independent
    # model and every pinned transitive module have been verified in memory.
    from tb3_paths_near import check_g8

    if not np.array_equal(model_frequencies, frequencies) or bank_sha != contract["ffd_sha256"]:
        raise ValueError("Independent G4 bank frequencies or provenance differ")
    g4_started = time.monotonic()
    g4 = evaluate_case(results, CASE, model, observation, banks, frequencies)
    g4.pop("_delta_by_pose")
    g4.update(gate="G4", wall_s=time.monotonic()-g4_started,
              model_source_sha256=model_sha, loaded_modules=loaded_modules, ffd_bank_sha256=bank_sha)
    write(results / "G4.json", g4)
    g8_started = time.monotonic()
    g8 = check_g8(p_dir / "PATHS_NEAR.npz", channels["H_LoS.npy"], ids)
    g8.update(gate="G8_SERIALIZATION", wall_s=time.monotonic()-g8_started)
    write(results / "G8.json", g8)
    passed = read(results / "G4.json")["status"] == read(results / "G8.json")["status"] == "PASS"
    artifacts = [p for p in sorted(results.rglob("*")) if p.is_file()]
    write(results / "completion.json", dict(
        status="PASS" if passed else "FAIL", case=CASE, code_commit=args.code_commit,
        question_id=contract.get("question_id"), role="IMPLEMENTER", mount_deg=0,
        poses=1440, trace_positions=40, solver_calls=sum(r["solver_calls"] for r in receipts),
        base_nodes=17, adaptive_nodes=True,
        node_count_distribution=dict(Counter(r["solver_calls"] for r in receipts)),
        original_h_array_equal=True, finite_face_guard=False, native_los_override=False,
        post_filter=False, raw_traces=40, extra_export_solver_calls=0,
        shared_trace=True, heading_error_computed=False,
        source_commit=shards[0][3]["source_commit"],
        baseline_pass_sha256=sha(args.root / "BASELINE_PASS.json"),
        run_contract_sha256=sha(args.root / "inputs" / "RUN_CONTRACT.json"),
        shards=[dict(manifest_sha256=digest, manifest=manifest) for _, _, _, manifest, digest in shards],
        started_utc=started_utc, finished_utc=utc_now(), wall_s=time.monotonic()-started,
        command=[sys.executable, *sys.argv], finish_source_sha256=sha(Path(__file__)),
        output_sha256={p.relative_to(results).as_posix(): sha(p) for p in artifacts},
        output_bytes={p.relative_to(results).as_posix(): p.stat().st_size for p in artifacts},
        g4=g4, g8=g8,
    ))
    if not passed:
        raise RuntimeError("Merged G4 or G8 failed; outputs and FAIL completion preserved")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "model-source", "banks-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
