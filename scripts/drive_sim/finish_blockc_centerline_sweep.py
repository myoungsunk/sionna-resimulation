"""Verify and merge the four BLOCK_C centerline shards, then run G4 and G8."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import time

import numpy as np

from merge_tb3_production import LOS_ANGLES, fill_los, load_near
from run_tb3_g1_pilot import read, sha, write
from run_tb3_production import F1_SHA, utc_now, verify
from validate_tb3_g4 import MODEL_SOURCE_SHA256, evaluate_case, load_model


CASE = "BLOCKC_B"


def bound_path(root, name):
    path = (root / name).resolve()
    if root.resolve() not in path.parents:
        raise ValueError(f"Artifact escapes its root: {name}")
    return path


def verified_shards(root, code_commit):
    inputs = root / "inputs"
    contract = read(inputs / "RUN_CONTRACT.json")
    for name, digest in contract["input_sha256"].items():
        verify(bound_path(inputs, name), digest)
    verify(inputs / "PRODUCTION_F1.json", F1_SHA)
    tasks = read(inputs / "rf_tasks.json")
    poses = read(inputs / "rf_poses.json")
    if ([t["task_id"] for t in tasks] != list(range(40))
            or [p["pose_id"] for p in poses] != list(range(1440))
            or sorted(i for t in tasks for i in t["pose_ids"]) != list(range(1440))):
        raise ValueError("Expected exactly 40 tasks partitioning 1440 global pose IDs")
    invariant_keys = ("source_sha256", "method_b_sha256", "runtime_versions", "engine",
                      "finite_face_guard", "governance", "image")
    baseline = None
    shards = []
    for index in range(4):
        directory = root / "attempts" / "production" / f"shard{index}"
        manifest = read(directory / "MANIFEST.json")
        selected = tasks[index::4]
        ids = np.array(sorted(i for task in selected for i in task["pose_ids"]), dtype=np.int64)
        if (manifest["status"] != "PASS" or manifest["scope"] != "CENTERLINE_SWEEP_SHARD"
                or manifest["code_commit"] != code_commit
                or (manifest["shard_index"], manifest["shard_count"]) != (index, 4)
                or manifest["selected_task_ids"] != [t["task_id"] for t in selected]
                or manifest["poses"] != len(ids) or manifest["trace_positions"] != 10
                or manifest["solver_calls"] != 170 or manifest["extra_export_solver_calls"] != 0
                or manifest["mounts_deg"] != [0] or manifest["shared_trace"] is not True
                or manifest["run_contract_sha256"] != sha(inputs / "RUN_CONTRACT.json")
                or manifest["input_sha256"] != contract["input_sha256"]
                or manifest["ffd_sha256"] != contract["ffd_sha256"]
                or manifest["method_b_sha256"] != contract.get("method_b_sha256", {})
                or manifest["engine"] != read(inputs / "PRODUCTION_F1.json")
                or manifest["serialization_g8"]["status"] != "PASS"):
            raise ValueError(f"Invalid shard provenance, coverage or solver count: {directory}")
        invariant = {key: manifest[key] for key in invariant_keys}
        if baseline is None:
            baseline = invariant
        elif invariant != baseline:
            raise ValueError("Source or runtime settings differ between shards")
        for name, digest in manifest["source_sha256"].items():
            verify(bound_path(Path(__file__).parent, name), digest)
        artifacts = {p.relative_to(directory).as_posix() for p in directory.rglob("*")
                     if p.is_file() and p != directory / "MANIFEST.json"}
        if artifacts != set(manifest["output_sha256"]) or artifacts != set(manifest["output_bytes"]):
            raise ValueError(f"Unexpected or missing shard artifacts: {directory}")
        for name, digest in manifest["output_sha256"].items():
            path = bound_path(directory, name)
            verify(path, digest)
            if path.stat().st_size != manifest["output_bytes"][name]:
                raise ValueError(f"Shard byte count differs: {path}")
        mount = directory / "mount0"
        stored_ids = np.load(mount / "POSE_IDS.npy", allow_pickle=False)
        if stored_ids.dtype != np.int64 or not np.array_equal(stored_ids, ids):
            raise ValueError(f"Shard global pose IDs differ: {directory}")
        receipts = read(directory / "TRACE_RECEIPTS.json")
        for task, receipt in zip(selected, receipts, strict=True):
            if (any(receipt[key] != task[key] for key in ("task_id", "pose_ids"))
                    or receipt["node_bins"] != list(range(0, 257, 16))
                    or receipt["solver_calls"] != 17 or receipt["n_full_paths"] < 1
                    or receipt["mounts_deg"] != [0]):
                raise ValueError(f"Invalid same-trace receipt: {directory}")
        if read(directory / "SERIALIZATION_G8.json")["status"] != "PASS":
            raise ValueError(f"Shard serialization gate failed: {directory}")
        shards.append((mount, ids, receipts, manifest, sha(directory / "MANIFEST.json")))
    return contract, shards


def run(args):
    started, started_utc = time.monotonic(), utc_now()
    contract, shards = verified_shards(args.root, args.code_commit)
    results = args.root / "results"
    results.mkdir(mode=0o700, exist_ok=False)
    h_dir, p_dir, pose_dir = (results / folder / CASE for folder in ("H", "paths", "poses"))
    for folder in (h_dir, p_dir, pose_dir):
        folder.mkdir(parents=True, mode=0o700)
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
        poses=1440, trace_positions=40, solver_calls=680, extra_export_solver_calls=0,
        shared_trace=True, heading_error_computed=False,
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
