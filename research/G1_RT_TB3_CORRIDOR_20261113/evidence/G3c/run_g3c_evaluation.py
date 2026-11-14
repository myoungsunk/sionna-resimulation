"""Evaluate G3c ray-count convergence against frozen G3a raw traces."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import run_g3a as g3a
from run_g3c_trace import BASELINE, BASELINE_DIGESTS, RUN, verify
from run_tb3_g1_pilot import load_runtime, read, write


N_BINS = 257
N_POSITIONS = 195
N_POSES = 5067
ADDED_LIMIT = 0.01
DS_LIMIT = 0.002
BINS = list(range(N_BINS))


def match_matrix(tau_100, dirs_100, chain_100, tau_400, dirs_400, chain_400):
    delay = np.abs(tau_100[:, None] - tau_400[None, :])
    direction = np.linalg.norm(dirs_100[:, None, :] - dirs_400[None, :, :], axis=-1)
    chain = (chain_100[:, None, :] == chain_400[None, :, :]).all(axis=-1)
    return (delay <= g3a.TAU_TOL_S) & (direction <= g3a.DIRECTION_TOL) & chain


def energy_metrics(pairs, energy_100, energy_400):
    if np.any(pairs.sum(axis=0) > 1) or np.any(pairs.sum(axis=1) > 1):
        raise ValueError("AMBIGUOUS_PATH_MATCH")
    total_100 = energy_100.sum()
    total_400 = energy_400.sum()
    if not all(np.isfinite(e) and e > 0 for e in (total_100, total_400)):
        raise ValueError("INVALID_TOTAL_ENERGY")
    removed = ~pairs.any(axis=1)
    added = ~pairs.any(axis=0)
    return (int(added.sum()), int(removed.sum()),
            float(energy_400[added].sum() / total_400),
            float(energy_100[removed].sum() / total_100))


def self_check():
    tau_100 = np.array([1e-8, 2e-8, 3e-8])
    tau_400 = np.array([2e-8, 1e-8 + 1e-14, 4e-8])
    dirs_100 = np.eye(3, 6)
    dirs_400 = dirs_100[[1, 0, 2]]
    seq_100 = np.array([[1, 3], [1, 5], [1, 7]])
    seq_400 = np.array([[1, 5], [1, 3], [1, 9]])
    args = (tau_100, dirs_100, seq_100, tau_400, dirs_400, seq_400)
    pairs = match_matrix(*args)
    assert g3a.match(*args) == (1, 1, False)
    assert energy_metrics(pairs, np.array([4., 5., 1.]), np.array([5., 4., 1.])) == (1, 1, 0.1, 0.1)
    assert energy_metrics(np.eye(3, dtype=bool), np.ones(3), np.ones(3)) == (0, 0, 0., 0.)
    for matrix, energies, expected in (
        (np.ones((3, 3), bool), np.ones(3), "AMBIGUOUS_PATH_MATCH"),
        (np.eye(3, dtype=bool), np.zeros(3), "INVALID_TOTAL_ENERGY"),
    ):
        try:
            energy_metrics(matrix, energies, np.ones(3))
        except ValueError as exc:
            assert str(exc) == expected
        else:
            raise AssertionError(f"Invalid pair was accepted: {expected}")


def frozen_parity(manifest):
    contract = read(g3a.INPUT / "G3_CONTRACT.json")
    verify(g3a.INPUT / "G3_CONTRACT.json", manifest["contract_sha256"])
    parity_path = g3a.INPUT / "parity_gate.py"
    verify(parity_path, contract["parity_sha256"])
    module = importlib.util.spec_from_file_location("frozen_parity_gate", parity_path)
    parity = importlib.util.module_from_spec(module)
    module.loader.exec_module(parity)
    return parity


def checksum_table(path):
    table = {}
    for line in path.read_text().splitlines():
        digest, rel = line.split(maxsplit=1)
        if rel in table:
            raise ValueError(f"Duplicate checksum in {path}: {rel}")
        table[rel] = digest
    return table


def preflight():
    self_check()
    manifest = read(RUN / "MANIFEST.json")
    trace_exit = RUN / "TRACE_EXIT_CODE.txt"
    deadline = time.monotonic() + 3600
    while not (trace_exit.is_file() and trace_exit.stat().st_size):
        if time.monotonic() >= deadline:
            raise TimeoutError("400k trace completion receipt still unavailable")
        time.sleep(5)
    if trace_exit.read_text().strip() != "0":
        raise ValueError("400k trace did not complete")
    if manifest["solver_100k"] | {"samples_per_src": 400_000} != manifest["solver_400k"]:
        raise ValueError("The 400k arm changes more than samples_per_src")
    if (manifest["max_added_energy_fraction_exclusive"], manifest["max_abs_delta_s_inclusive"]) != (ADDED_LIMIT, DS_LIMIT):
        raise ValueError("G3c thresholds changed")
    for name, digest in manifest["run_input_sha256"].items():
        verify(RUN / name, digest)
    baseline_table = BASELINE / "RAW_SHA256.txt"
    verify(baseline_table, BASELINE_DIGESTS["RAW_SHA256.txt"])
    checks_100 = checksum_table(baseline_table)
    checks_400 = checksum_table(RUN / "RAW_SHA256.txt")
    if checks_100.keys() != checks_400.keys() or len(checks_400) != N_POSITIONS*2:
        raise ValueError("Raw input coverage mismatch")
    for root, checks in ((BASELINE, checks_100), (RUN, checks_400)):
        for rel, digest in checks.items():
            verify(root / rel, digest)
    tasks = g3a.task_table()
    (RUN / "analysis").mkdir(exist_ok=False)
    write(RUN / "EVALUATION_MANIFEST.json", dict(
        evaluator_sha256=g3a.sha(Path(__file__)), launch_evaluation_sha256=g3a.sha(RUN / "launch_evaluation.sh"),
        trace_manifest_sha256=g3a.sha(RUN / "MANIFEST.json"),
        raw_100k_digest_table_sha256=g3a.sha(BASELINE / "RAW_SHA256.txt"),
        raw_400k_digest_table_sha256=g3a.sha(RUN / "RAW_SHA256.txt"),
        parity_sha256=read(g3a.INPUT / "G3_CONTRACT.json")["parity_sha256"],
        energy="Per bin, sum of squared ISO Jones Frobenius norms for arm-only paths divided by all-path sum in the same arm",
        match=dict(tau_tol_s=g3a.TAU_TOL_S, direction_tol=g3a.DIRECTION_TOL,
                   chain="ordered interactions and object IDs", ambiguity="invalid"),
        channel="Both arms use frozen all-bin Method B assembly and signed_s_single_tx with TX +45",
    ))
    for case in tasks:
        print(case)


def load_raw(trace, root, case, task, solver, freq):
    tag = task["tag"]
    out = root / "raw" / case
    raw_path, receipt = out / f"{tag}.npz", read(out / f"{tag}.json")
    xy = [task["x"], task["y"]]
    if (receipt["case"], receipt["tag"], receipt["task_id"], receipt["xy"], receipt["sampled_yaws"],
        receipt["solver"], receipt["bin_count"]) != (
            case, tag, task["task_id"], xy, task["sampled_yaws"], solver, N_BINS):
        raise ValueError(f"Trace receipt mismatch: {raw_path}")
    verify(raw_path, receipt["raw_sha256"])
    with np.load(raw_path, allow_pickle=False) as z:
        offsets, iso = z["bin_offsets"], z["jones_iso"]
        tau, angles = z["tau"].astype(float), z["ang"].astype(float)
        events, objects = z["interactions"], z["objects"]
        if (not np.array_equal(z["node_bins"], BINS) or not np.array_equal(z["node_freq_hz"], freq)
                or (float(z["x"]), float(z["y"]), int(z["task_id"])) != (*xy, task["task_id"])
                or offsets.shape != (N_BINS+1,) or offsets[0] != 0 or offsets[-1] != len(tau)
                or not np.all(np.diff(offsets) > 0) or iso.shape != (2, 2, len(tau))
                or angles.shape != (4, len(tau)) or events.shape != (len(tau), solver["max_depth"])
                or events.shape != objects.shape or (tau < 0).any()
                or (events == trace.rt.constants.InteractionType.REFRACTION).any()
                or not all(np.isfinite(arr).all() for arr in (iso, tau, angles))):
            raise ValueError(f"Invalid raw trace: {raw_path}")
    none = trace.rt.constants.InteractionType.NONE
    chain = np.concatenate((events, np.where(events == none, 0, objects)), axis=1)
    directions = trace.P.path_directions(*angles)
    energy = np.sum(iso.real.astype(np.float64)**2 + iso.imag.astype(np.float64)**2, axis=(0, 1))
    sections = [slice(lo, hi) for lo, hi in zip(offsets[:-1], offsets[1:])]
    return dict(receipt=receipt, tau=tau, iso=iso, angles=angles,
                directions=directions, chain=chain, energy=energy, sections=sections)


def channel_for_yaws(trace, parity, raw, banks, yaws):
    by_bin = {i: (raw["iso"][:, :, section], raw["tau"][section], raw["angles"][:, section])
              for i, section in enumerate(raw["sections"])}
    tau, angles, _, jones, _, present = trace._assemble(by_bin, BINS)
    counts = np.array([s.stop - s.start for s in raw["sections"]])
    if not np.array_equal(present.sum(axis=1), counts):
        raise ValueError("Frozen all-bin assembly did not retain every observed path")
    result = parity.h_for_antenna_yaws(dict(status="OK", jones=jones, tau=tau, ang=np.array(angles),
                                          node_freq_hz=banks[0].freqs_hz, present=present), banks, yaws)
    if result.shape != (len(yaws), N_BINS, 2, 2) or not np.isfinite(result).all():
        raise ValueError("Invalid reconstructed channel")
    return result


def evaluate_case(case):
    manifest = read(RUN / "MANIFEST.json")
    trace, _, _ = load_runtime(g3a.SOURCE)
    parity = frozen_parity(manifest)
    banks = parity.load_banks()
    freq = banks[0].freqs_hz
    out = RUN / "analysis" / case
    out.mkdir()
    tasks = g3a.task_table()[case]
    expected_anchors = read(g3a.INPUT / "scene/SCENE_MANIFEST.json")["geometries"]
    geom, anchor = case.split("_")

    ratios = np.full((len(tasks), N_BINS, 2), np.nan)
    counts = np.full((len(tasks), N_BINS, 2), -1, dtype=np.int32)
    invalid = []
    rows = []
    for i, task in enumerate(tasks):
        pair = [load_raw(trace, root, case, task, solver, freq)
                for root, solver in ((BASELINE, manifest["solver_100k"]), (RUN, manifest["solver_400k"]))]
        rec_100, rec_400 = [p["receipt"] for p in pair]
        if (rec_100["anchor_xyz"] != rec_400["anchor_xyz"]
                or rec_400["anchor_xyz"] != expected_anchors[geom]["anchors_xyz_m"][anchor]
                or rec_100["shape_ids"] != rec_400["shape_ids"]):
            raise ValueError(f"Scene identity mismatch: {case}/{task['tag']}")
        for bin_id in BINS:
            a, b = [tuple(raw[key][raw["sections"][bin_id]] for key in ("tau", "directions", "chain", "energy"))
                    for raw in pair]
            pairs = match_matrix(*a[:3], *b[:3])
            try:
                n_added, n_removed, e_added, e_removed = energy_metrics(pairs, a[3], b[3])
            except ValueError as exc:
                invalid.append(dict(tag=task["tag"], bin=bin_id, reason=str(exc)))
                continue
            counts[i, bin_id] = [n_added, n_removed]
            ratios[i, bin_id] = [e_added, e_removed]
        yaws = [p["yaw_deg"] for p in task["sampled_yaws"]]
        h_100, h_400 = [channel_for_yaws(trace, parity, raw, banks, yaws) for raw in pair]
        for pose, candidate, reference in zip(task["sampled_yaws"], h_400, h_100, strict=True):
            metrics = parity.compare(candidate, reference, freq)
            if not all(math.isfinite(v) for v in metrics.values()):
                raise ValueError(f"Nonfinite comparison: {case}/{task['tag']}/{pose['pose_id']}")
            rows.append(dict(case=case, tag=task["tag"], **pose, **metrics))
    np.savez_compressed(out / "ENERGY_ROWS.npz", tags=[t["tag"] for t in tasks], bins=BINS,
                        added_energy_fraction=ratios[:, :, 0], removed_energy_fraction=ratios[:, :, 1],
                        added_path_count=counts[:, :, 0], removed_path_count=counts[:, :, 1])
    write(out / "INVALID_BIN_ROWS.json", invalid)
    write(out / "PARITY_ROWS.json", rows)


def summarize():
    results = {}
    invalid_bins = 0
    for case, tasks in g3a.task_table().items():
        root = RUN / "analysis" / case
        invalid = read(root / "INVALID_BIN_ROWS.json")
        invalid_bins += len(invalid)
        tags = [t["tag"] for t in tasks]
        expected_pose_keys = {(t["tag"], p["pose_id"], p["yaw_deg"]) for t in tasks for p in t["sampled_yaws"]}
        rows = read(root / "PARITY_ROWS.json")
        if (len(rows) != len(expected_pose_keys) or any(r["case"] != case for r in rows)
                or {(r["tag"], r["pose_id"], r["yaw_deg"]) for r in rows} != expected_pose_keys):
            raise ValueError(f"Unexpected pose coverage: {case}")
        with np.load(root / "ENERGY_ROWS.npz", allow_pickle=False) as data:
            add = data["added_energy_fraction"]
            removed = data["removed_energy_fraction"]
            add_n, removed_n = data["added_path_count"], data["removed_path_count"]
            valid = np.isfinite(add)
            if (add.shape != (len(tags), N_BINS) or data["tags"].tolist() != tags
                    or not np.array_equal(data["bins"], BINS)
                    or not np.array_equal(valid, np.isfinite(removed))
                    or not np.array_equal(valid, add_n >= 0) or not np.array_equal(valid, removed_n >= 0)
                    or int((~valid).sum()) != len(invalid)):
                raise ValueError(f"Unexpected bin coverage: {case}")
            peak = None
            if valid.any():
                i, j = np.unravel_index(np.nanargmax(add), add.shape)
                peak = dict(case=case, tag=tags[i], bin=int(j), fraction=float(add[i, j]),
                            added_path_count=int(add_n[i, j]))
            peak_removed = float(np.nanmax(removed)) if valid.any() else None
        worst_pose = max(rows, key=lambda row: row["abs_ds"])
        results[case] = dict(positions=len(tags), compared_bins=int(valid.sum()),
                             invalid_bins=len(invalid), compared_poses=len(rows),
                             added_path_occurrences=int(add_n[valid].sum()),
                             removed_path_occurrences=int(removed_n[valid].sum()),
                             bins_with_added_paths=int((add_n > 0).sum()),
                             bins_with_removed_paths=int((removed_n > 0).sum()),
                             bins_above_or_equal_energy_limit=int((add >= ADDED_LIMIT).sum()),
                             peak_added_energy=peak, max_removed_energy_fraction=peak_removed, worst_pose=worst_pose)
    compared_bins = sum(x["compared_bins"] for x in results.values())
    compared_poses = sum(x["compared_poses"] for x in results.values())
    peaks = [x["peak_added_energy"] for x in results.values() if x["peak_added_energy"] is not None]
    peak = max(peaks, key=lambda x: x["fraction"], default=None)
    worst = max((x["worst_pose"] for x in results.values()), key=lambda x: x["abs_ds"])
    checks = dict(complete_bin_coverage=compared_bins == N_POSITIONS*N_BINS and invalid_bins == 0,
                  complete_pose_coverage=compared_poses == N_POSES,
                  added_energy_below_limit=peak is not None and peak["fraction"] < ADDED_LIMIT,
                  abs_delta_s_within_limit=worst["abs_ds"] <= DS_LIMIT)
    status = "PASS" if all(checks.values()) else "FAIL"
    now = datetime.now(timezone.utc)
    started = datetime.fromisoformat((RUN / "STARTED_UTC.txt").read_text().strip())
    result = dict(question_id="G1-RT-TB3-001", stage="G3c", status=status, checks=checks,
                  compared_bins=compared_bins, expected_bin_pairs=N_POSITIONS*N_BINS,
                  compared_poses=compared_poses, expected_pose_pairs=N_POSES, invalid_bins=invalid_bins,
                  max_added_energy_fraction=peak["fraction"] if peak else None, peak_added_energy=peak,
                  max_abs_delta_s=worst["abs_ds"], worst_pose=worst,
                  trace_wall_s=float((RUN / "TRACE_WALL_S.txt").read_text()),
                  gate_finished_utc=now.isoformat(), wall_s=(now-started).total_seconds(),
                  trace_manifest_sha256=g3a.sha(RUN / "MANIFEST.json"),
                  evaluation_manifest_sha256=g3a.sha(RUN / "EVALUATION_MANIFEST.json"),
                  cases=results)
    write(RUN / "G3C.json", result)
    print(json.dumps({k: v for k, v in result.items() if k != "cases"}), flush=True)
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    action, *args = sys.argv[1:]
    if action == "preflight":
        preflight()
    elif action == "case":
        evaluate_case(*args)
    elif action == "summarize":
        sys.exit(summarize())
    else:
        raise ValueError(f"Unexpected mode: {action}")
