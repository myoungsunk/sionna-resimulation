"""Frozen archives and exclusion checks for the guarded G6 replay."""
from __future__ import annotations

import json

from run_tb3_g1_pilot import read
from run_tb3_production import verify


PRIOR_SHA = "e17723bbd0b5cb835a396b89fa72def3c590359f86e6f427d08180e64affb767"
BOUNDARY_SHA = "f678574ea2818f0ba10d0467f737b1af272027928ce1bc28aef134d83c2f4a2c"
INPUT_HASHES = {"G6_REVALIDATION.json": PRIOR_SHA, "BOUNDARY_STAGES.json": BOUNDARY_SHA}


def load_prior(root, strict_tolerance):
    for name, digest in INPUT_HASHES.items():
        verify(root / name, digest)
    prior = read(root / "G6_REVALIDATION.json")
    boundary = read(root / "BOUNDARY_STAGES.json")
    if (prior["status"] != "FAIL" or boundary["gate_status"] != "FAIL"
            or prior["strict_tolerance_s"] != strict_tolerance
            or boundary["strict_tolerance_s"] != strict_tolerance
            or prior["strict_failures"] != 4):
        raise ValueError("Frozen G6 revalidation or boundary diagnosis differs")
    by_case = {case: {} for case in prior["cases"]}
    for row in boundary["cases"]:
        target = row["prior"]
        case, task, path = row["case"], row["task_id"], row["path_index"]
        if (task in by_case[case] or (case, task, path) !=
                (target["case"], target["task_id"], target["path_index"])):
            raise ValueError("Invalid frozen boundary case identity")
        by_case[case][task] = target
    for case, result in prior["cases"].items():
        failures = {f["task_id"]: f for f in result["failures"]}
        if len(failures) != len(result["failures"]) or failures.keys() != by_case[case].keys():
            raise ValueError("Boundary targets do not cover the prior G6 failures")
        for task, target in by_case[case].items():
            failure = failures[task]
            if (target["path_index"] != failure["path_index"] or
                    target["gate_error"] != failure["issue"] or failure["image_delay_s"] is not None):
                raise ValueError("Frozen boundary target is not a finite-face geometry failure")
    return prior, by_case


def archived_rows(root, prior_case, case, index, count, chosen, smoke):
    names = {name: digest for name, digest in prior_case["trace_sha256"].items()
             if name.endswith(".jsonl")}
    if not smoke:
        if len(names) != count:
            raise ValueError(f"Guarded shard count differs from the previous run: {case}")
        name = f"{case}_{index:02d}.jsonl"
        names = {name: names[name]}
    expected = {task["task_id"] for task in chosen}
    rows = {}
    inputs = {}
    for name, digest in names.items():
        p = root / "traces" / name
        verify(p, digest)
        inputs[str(p)] = digest
        with p.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                task = row["task_id"]
                if task in expected:
                    if row["case"] != case or task in rows:
                        raise ValueError(f"Unexpected prior corrected trace row: {case}/{task}")
                    rows[task] = row
    if rows.keys() != expected:
        raise ValueError(f"Missing prior corrected trace rows for {case}")
    return rows, inputs


def verify_rejections(entries, nodes, target):
    """Account separately for observed candidates and the archived output removal."""
    seen_bins = set()
    accounted = 0
    total = 0
    for entry in entries:
        node, rejected = entry["bin"], entry["paths"]
        if node not in nodes or node in seen_bins or not rejected:
            raise ValueError("Unexpected pre-field rejection node coverage")
        seen_bins.add(node)
        total += len(rejected)
        if target is not None:
            hits = target["vertices"]
            target_rejections = [r for r in rejected
                                 if r["reason"] == target["gate_error"]
                                 and r["vertices_m"] == [v["native_point_m"] for v in hits]
                                 and [p for _, p in r["chain"]] == [v["primitive"] for v in hits]
                                 and r["face_sequence"] == ">".join(v["face"] for v in hits)]
            if len(target_rejections) != 1:
                raise ValueError(f"Expected one frozen boundary rejection at node {node}")
            accounted += 1
    if target is not None and seen_bins != set(nodes):
        raise ValueError("Boundary rejection missing at one or more frozen F1 nodes")
    return total, accounted
