"""Verify guarded generation metadata before the frozen G4 calculation."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


BASE_CASES = {f"{geometry}_{anchor}" for geometry in ("G-T1", "G-T2", "G-V") for anchor in "ABC"}
CASES = BASE_CASES | {"G-T1_A_P-F", "G-T1_B_P-F"}
BINS = list(range(0, 257, 16))
G6_TARGETS = {("G-T2_B", 1708), ("G-T2_C", 1025), ("G-T2_C", 1840), ("G-T2_C", 2477)}
EXPECTED = dict(poses=61992, main_poses=52218, diagnostic_new_poses=9774,
                near_poses=27810, trace_positions=26460, solver_batch_calls=449820,
                extra_export_solver_calls=0)
UNCHANGED = ("poses", "main_poses", "diagnostic_new_poses", "trace_positions", "near_poses",
             "anchor_xyz", "robot_z", "mount_deg", "shape", "samples_sha256",
             "solver_batch_calls", "extra_export_solver_calls")


def read(path):
    return json.loads(path.read_bytes())


def checked_read(path, digest):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"Digest mismatch for {path}")
    return json.loads(data)


def generation(root):
    result = read(root / "GENERATION_RESULT.json")
    if (result["status"] != "PASS" or result["cases"] != len(CASES)
            or any(result["totals"][name] != value for name, value in EXPECTED.items())):
        raise ValueError(f"Incomplete frozen generation coverage in {root}")
    cases = checked_read(root / "CASES.json", result["cases_sha256"])
    if set(cases) != CASES:
        raise ValueError(f"Unexpected generation case set in {root}")
    return result, cases


def checked_case_receipts(root, case, entry):
    manifest = checked_read(root / "H" / case / "MANIFEST.json", entry["manifest_sha256"])
    filename = f"paths/{case}/TRACE_RECEIPTS.json"
    records = checked_read(root / filename, manifest["output_sha256"][filename])
    if (manifest["status"] != "PASS" or len(records) != manifest["trace_positions"]
            or [row["task_id"] for row in records] != list(range(len(records)))):
        raise ValueError(f"Incomplete receipt coverage in {root}/{case}")
    return manifest, records


def compare_case(current, baseline, case):
    if any(current[0][name] != baseline[0][name] for name in UNCHANGED):
        raise ValueError(f"Frozen case coverage differs at {case}")
    counts = Counter()
    affected = []
    for new, old in zip(current[1], baseline[1], strict=True):
        key = case, new["task_id"]
        if (any(new[name] != old[name] for name in ("task_id", "pose_ids", "tag", "node_bins", "solver_calls"))
                or new["node_bins"] != BINS or new["solver_calls"] != len(BINS)):
            raise ValueError(f"Frozen task scope differs at {key}")
        entries = new["pre_field_rejections_by_node"]
        observed = {entry["bin"]: entry["count"] for entry in entries}
        removed = old["n_full_paths"] - new["n_full_paths"]
        if (len(observed) != len(entries) or set(observed).difference(BINS)
                or any(type(count) is not int or count < 1 for count in observed.values())
                or sum(observed.values()) != new["pre_field_rejections"] or removed < 0
                or any(observed.get(bin_index, 0) < removed for bin_index in BINS)):
            raise ValueError(f"Guarded task accounting differs at {key}")
        if key in G6_TARGETS and removed != 1:
            raise ValueError(f"The known G6 path was not removed at {key}")
        if removed or observed:
            affected.append(dict(task_id=key[1], removed_paths=removed,
                                 pre_field_rejections_by_node=entries))
        counts.update(positions=1, removed_paths=removed, pre_field_rejections=sum(observed.values()))
    return dict(
        **counts, affected=affected, poses=current[0]["poses"],
        near_poses=current[0]["near_poses"],
        h_full_sha256_changed=current[0]["full_H_sha256"] != baseline[0]["full_H_sha256"],
        h_los_sha256_changed=current[0]["los_H_sha256"] != baseline[0]["los_H_sha256"],
    )


def verify(run, previous, code_commit):
    root, old = run / "results", previous / "results"
    result, cases = generation(root)
    _, baseline = generation(old)
    guard = result["g6_result_sha256"]
    if result["finite_face_guard"] is not True:
        raise ValueError("The generation receipt does not declare finite-face filtering")
    seal = read(root / "seal/SEAL_MANIFEST.json")
    sealed_cases = {case for case in BASE_CASES if case.startswith(("G-T2_", "G-V_"))}
    if (seal["status"] != "SEALED" or set(seal["cases"]) != sealed_cases
            or (root / "seal/UNSEAL.json").exists()):
        raise ValueError("Confirmation cases are not sealed")
    summaries = {}
    for case in sorted(CASES):
        current = checked_case_receipts(root, case, cases[case])
        original = checked_case_receipts(old, case, baseline[case])
        for shard in current[0]["shards"]:
            stage = shard["engine"]["finite_face_guard"]
            if (stage["stage"] != "PRE_FIELD" or stage["g6_result_sha256"] != guard
                    or shard["code_commit"] != code_commit):
                raise ValueError(f"Guarded shard provenance differs at {case}")
        summaries[case] = compare_case(current, original, case)
    affected = {(case, row["task_id"]) for case, entry in summaries.items()
                for row in entry["affected"] if row["removed_paths"]}
    if not G6_TARGETS <= affected:
        raise ValueError("Known G6 targets are absent from the production comparison")
    return dict(status="PASS", scope="generation metadata and same-trace coverage",
                code_commit=code_commit, g6_result_sha256=guard,
                totals=result["totals"], cases=summaries,
                removed_paths=sum(row["removed_paths"] for row in summaries.values()),
                pre_field_rejections=sum(row["pre_field_rejections"] for row in summaries.values()),
                changed_positions=len(affected))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run", "previous", "out"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()
    summary = verify(args.run, args.previous, args.code_commit)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
