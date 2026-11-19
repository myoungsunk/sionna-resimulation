"""Assess full G6 coverage and corrected finite-face delay residuals."""
from __future__ import annotations

import argparse
from collections import Counter
from itertools import pairwise
import json
from math import isfinite
from pathlib import Path
from time import monotonic

from diagnose_tb3_g6_image import G6_SHA256, IMPLEMENTER_POLICY_SHA256, STRICT_TOL_S
from run_tb3_g1_pilot import read, sha, write
from run_tb3_production import utc_now, verify
from validate_tb3_g6 import CASES, ROUTES


NODES = list(range(0, 257, 16))
METRICS = ("positions", "solver_calls", "examined_paths", "image_geometry_unmatched",
           "delay_exceeded", "primitive_seam_crossings")


def continuity(route, signatures):
    """Retain adjacent multiset comparison using corrected ordered face identities."""
    compared = 0
    changes = []
    for a, b in pairwise(route):
        if a not in signatures or b not in signatures:
            continue
        compared += 1
        added = signatures[b] - signatures[a]
        removed = signatures[a] - signatures[b]
        if added or removed:
            changes.append(dict(from_task=a, to_task=b, appeared=dict(sorted(added.items())),
                                disappeared=dict(sorted(removed.items()))))
    return dict(compared_adjacent_pairs=compared, set_changes=len(changes), changes=changes)


def inspect_case(case, original, selection, trace_dir, source_hashes, prior_case=None, targets=None):
    from tb3_g6_guard_replay import INPUT_HASHES, verify_rejections

    guarded = prior_case is not None
    metrics = METRICS + (("removed_paths", "removed_path_nodes", "pre_field_rejections") if guarded else ())
    signatures, seen = {}, set()
    failures = []
    inputs, shard_ids = {}, set()
    counts = Counter({k: 0 for k in metrics})
    max_residual, max_hit, worst = 0.0, 0.0, None
    wanted = {t for route in selection["routes"].values() for t in route}
    expected = original["cases"][case]
    if set(selection["routes"]) != set(ROUTES) or len(wanted) != selection["positions"] or len(wanted) != expected["positions"]:
        raise ValueError(f"Original route selection differs in {case}")
    shards = sorted(trace_dir.glob(f"{case}_*.jsonl"))
    for path in shards:
        manifest_path = path.with_suffix(".manifest.json")
        manifest = read(manifest_path)
        index, n_shards = map(int, manifest["shard"].split("/"))
        if (manifest["case"] != case or manifest["smoke"] or manifest["node_bins"] != NODES
                or manifest.get("finite_face_guard", False) != guarded
                or manifest["strict_tolerance_s"] != STRICT_TOL_S or index in shard_ids
                or n_shards != len(shards) or not 0 <= index < n_shards):
            raise ValueError(f"Invalid trace shard provenance: {path}")
        verify(path, manifest["output_sha256"])
        inputs[path.name], inputs[manifest_path.name] = manifest["output_sha256"], sha(manifest_path)
        for name, digest in manifest["code_sha256"].items():
            if source_hashes.setdefault(name, digest) != digest:
                raise ValueError(f"Inconsistent tracing or runtime code for {name}")
        archived_inputs = {p: digest for p, digest in manifest["input_sha256"].items()
                           if p.startswith("/original/traces/")}
        originals = {p: digest for p, digest in original["input_sha256"].items()
                     if p.startswith(f"/run/traces/{case}_")}
        if ({"/run/traces/" + Path(p).name: digest for p, digest in archived_inputs.items()} != originals
                or manifest["input_sha256"]["/original/G6.json"] != G6_SHA256
                or manifest["input_sha256"][f"/original/selected/{case}.json"] != selection["selector_sha256"]):
            raise ValueError(f"Trace does not bind the complete old archive: {path}")

        if guarded:
            prior_files = {p: digest for p, digest in manifest["input_sha256"].items() if p.startswith("/prior/")}
            if prior_files != ({"/prior/" + name: digest for name, digest in INPUT_HASHES.items()} |
                               {"/prior/traces/" + path.name: prior_case["trace_sha256"][path.name]}):
                raise ValueError(f"Trace does not bind the previous corrected archive: {path}")

        shard_ids.add(index)
        local = Counter({k: 0 for k in metrics})
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)
                task = record["task_id"]
                if (record["case"] != case or task in seen or task not in wanted
                        or record["node_bins"] != NODES or not record["paths"]):
                    raise ValueError(f"Wrong or duplicate trace row: {case}/{task}")
                seen.add(task)
                signatures[task] = Counter()
                local.update(positions=1, solver_calls=len(NODES), examined_paths=len(record["paths"]))
                if guarded:
                    target = targets.get(task)
                    removed = [] if target is None else [target["path_index"]]
                    guard = record.get("guard", {})
                    if guard.get("removed_baseline_indices", []) != removed:
                        raise ValueError(f"Unexpected removed path identity: {case}/{task}")
                    pre_field, matched = verify_rejections(guard.get("rejections", []), NODES, target)
                    local.update(removed_paths=len(removed), removed_path_nodes=matched, pre_field_rejections=pre_field)
                for i, (face, measured, image, seams, hit_offset, issue) in enumerate(record["paths"]):
                    if (not face or not isfinite(measured) or measured <= 0 or not isfinite(hit_offset)
                            or hit_offset < 0 or type(seams) is not int or not 0 <= seams <= 3
                            or (image is None) != (issue is not None)
                            or (image is not None and (not isfinite(image) or image <= 0))):
                        raise ValueError(f"Invalid corrected delay data: {case}/{task}/{i}")
                    signatures[task][face] += 1
                    max_hit = max(max_hit, hit_offset)
                    local["primitive_seam_crossings"] += seams
                    residual = abs(measured - image) if image is not None else None
                    local["image_geometry_unmatched"] += int(issue is not None)
                    local["delay_exceeded"] += int(residual is not None and residual > STRICT_TOL_S)
                    item = dict(task_id=task, path_index=i, xy=record["xy"], face_sequence=face,
                                recorded_geometry_delay_s=measured, image_delay_s=image, residual_s=residual,
                                max_recorded_plane_offset_m=hit_offset, issue=issue)
                    if issue is not None or residual > STRICT_TOL_S:
                        failures.append(item)
                    if residual is not None and residual > max_residual:
                        max_residual, worst = residual, item
        if dict(local) != manifest["totals"]:
            raise ValueError(f"Trace and worker counts differ: {path}")
        counts.update(local)
    complete = (seen == wanted and all(counts[k] == expected[k] for k in METRICS[:2])
                and counts["examined_paths"] + counts["removed_paths"] == expected["examined_paths"])
    routes = {name: continuity(route, signatures) for name, route in selection["routes"].items()}
    if guarded:
        complete &= (targets.keys() <= wanted and counts["removed_paths"] == len(targets)
                     and counts["removed_path_nodes"] == len(targets) * len(NODES)
                     and all(routes[name]["compared_adjacent_pairs"] == prev["compared_adjacent_pairs"]
                             for name, prev in prior_case["routes"].items()))
    return dict(complete=complete, counts=dict(counts), missing_tasks=sorted(wanted - seen),
                max_residual_s=max_residual, max_recorded_hit_plane_offset_m=max_hit,
                worst_path=worst, failures=failures, routes=routes,
                original_unmatched_strict=expected["unmatched_strict"], trace_sha256=inputs)


def run(args):
    tick, started = monotonic(), utc_now()
    original_path = args.original / "G6.json"
    verify(original_path, G6_SHA256)
    original = read(original_path)
    selection_path = args.original / "selected/SELECTION.json"
    selection_sha = original["input_sha256"]["/run/selected/SELECTION.json"]
    verify(selection_path, selection_sha)
    selection = read(selection_path)
    if (original["status"] != "FAIL" or original["strict_tolerance_s"] != STRICT_TOL_S
            or set(selection) != set(CASES) or set(original["cases"]) != set(CASES)):
        raise ValueError("Unexpected original G6 contract or coverage")
    source_hashes = {}
    prior = None
    prior_inputs = {}
    if args.finite_face_prior:
        from tb3_g6_guard_replay import INPUT_HASHES, load_prior

        prior, targets = load_prior(args.finite_face_prior, STRICT_TOL_S)
        prior_inputs = INPUT_HASHES
    cases = {case: inspect_case(case, original, selection[case], args.traces, source_hashes,
                                None if prior is None else prior["cases"][case],
                                None if prior is None else targets[case]) for case in CASES}
    used = {name for case in cases.values() for name in case["trace_sha256"]}
    if used != {p.name for p in args.traces.iterdir() if p.is_file()}:
        raise ValueError("Unexpected files or case coverage in trace directory")
    totals = {key: sum(case["counts"][key] for case in cases.values()) for key in cases[CASES[0]]["counts"]}
    coverage = all(case["complete"] for case in cases.values())
    strict_failures = totals["image_geometry_unmatched"] + totals["delay_exceeded"]
    status = "INCOMPLETE" if not coverage else "PASS" if strict_failures == 0 else "FAIL"
    peak_case = max(cases, key=lambda c: cases[c]["max_residual_s"])
    write(args.out, dict(
        status=status, stage="G6_REVALIDATION" if prior is None else "G6_FINITE_FACE_REVALIDATION",
        question_id=original["question_id"], role="IMPLEMENTER",
        code_commit=args.code_commit, original_status=original["status"], original_unmatched_strict=original["totals"]["unmatched_strict"],
        strict_tolerance_s=STRICT_TOL_S, strict_failures=strict_failures, threshold_rule="unmatched or residual > 5e-14 s",
        delays="float64 recorded solver endpoints and hit vertices; exact image using frozen input endpoints",
        matching="ordered connected finite planar faces selected from recorded object/primitive hits",
        continuity="adjacent multiset comparison with ordered finite-face labels",
        case_count=len(cases), route_count=len(cases)*len(ROUTES), node_bins=NODES,
        totals=totals, max_residual_s=cases[peak_case]["max_residual_s"],
        worst_path={"case": peak_case} | (cases[peak_case]["worst_path"] or {}),
        adjacent_pairs=sum(r["compared_adjacent_pairs"] for c in cases.values() for r in c["routes"].values()),
        adjacent_set_changes=sum(r["set_changes"] for c in cases.values() for r in c["routes"].values()),
        original_adjacent_set_changes=original["adjacent_set_changes"], cases=cases,
        governance=IMPLEMENTER_POLICY_SHA256,
        input_sha256={"G6.json": G6_SHA256, "SELECTION.json": selection_sha} | prior_inputs,
        finite_face_guard=None if prior is None else dict(
            scope="pre-field masking; complete original G6 selection with 17 nodes",
            prior_status=prior["status"], prior_strict_failures=prior["strict_failures"],
            prior_adjacent_set_changes=prior["adjacent_set_changes"],
            prior_examined_paths=prior["totals"]["examined_paths"],
            retained_path_replay="identical archived delays and detailed node-zero geometry after explicit exclusions"),
        source_sha256=source_hashes | {Path(__file__).name: sha(Path(__file__))},
        started_utc=started, finished_utc=utc_now(), assess_wall_s=monotonic()-tick))
    print(f"G6_REVALIDATION {status}: {totals} max_residual_s={cases[peak_case]['max_residual_s']:.12g}", flush=True)
    return {"PASS": 0, "FAIL": 2, "INCOMPLETE": 3}[status]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("original", "traces", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--finite-face-prior", type=Path, help="Frozen prior replay records for the guard")
    parser.add_argument("--code-commit", required=True)
    raise SystemExit(run(parser.parse_args()))


if __name__ == "__main__":
    main()
