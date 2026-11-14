"""Measure the effect of image-class grouping on the saved G6 failures."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import platform
import sys
import time

import numpy as np

import validate_tb3_g6 as g6
from run_tb3_g1_pilot import read, sha, write
from run_tb3_production import case_inputs, verify


G6_SHA256 = "b0da8458aacdcffc9800f413d65ed6da25a0a911190d818d862280c81e12fdef"
STRICT_TOL_S = 5e-14
IMPLEMENTER_POLICY_SHA256 = {
    "COMMON_CONTRACT.md": "a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
    "ROLE_IMPLEMENTER.md": "2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da",
}


def image_name(sequence):
    return ">".join(sequence) if sequence else "LOS"


def candidate_delays(tx, rx, entry, transforms, legacy):
    if transforms is None:
        from qclean_uwb.features.reflection_attribution import image_delays

        length, width, height = entry["dimensions_m"]
        return image_delays(tx, rx, length, width / 2, height)
    sequences, sign, translation = transforms
    delays = np.linalg.norm(sign * rx + translation - tx, axis=1) / legacy.C0
    return dict(zip(sequences, delays, strict=True))


def class_owners(delays, anchors, tie_s):
    ordered = np.argsort(delays, kind="stable")
    owners = np.empty(len(delays), dtype=int)
    class_index = 0
    for i in ordered:
        if delays[i] - anchors[class_index] > tie_s:
            class_index += 1
        if not 0 <= delays[i] - anchors[class_index] <= tie_s:
            raise ValueError("Reconstruction disagrees with frozen class grouping")
        owners[i] = class_index
    if class_index != len(anchors) - 1:
        raise ValueError("Class reconstruction did not visit every anchor")
    return owners


def diagnose_station(case, task, trace, recorded, entry, transforms, legacy):
    anchor = entry["anchors_xyz_m"][case.split("_")[1]]
    xy = [task["x"], task["y"]]
    if (trace["tag"] != task["tag"] or [trace["x"], trace["y"]] != xy
            or xy != recorded["xy"] or trace["status"] != "OK"):
        raise ValueError(f"Saved trace does not match the frozen task: {case}/{task['task_id']}")
    tx = np.asarray(anchor)
    rx = np.asarray([*xy, entry["rx_z_m"]])
    tau = np.asarray(trace["tau_s"])
    table = candidate_delays(tx, rx, entry, transforms, legacy)
    delays = np.asarray(list(table.values()))
    sequences = list(table)
    classes, names = legacy.classes(table)
    owners = class_owners(delays, classes, legacy.tie_s)

    class_distance = np.abs(tau[:, None] - classes)
    picked_class = class_distance.argmin(axis=1)
    class_residual = class_distance[np.arange(len(tau)), picked_class]
    failed = np.flatnonzero(class_residual > legacy.tol)
    if len(failed) != recorded["unmatched_strict"]:
        raise ValueError(f"Saved strict count differs at {case}/{task['task_id']}")

    for idx, expected in zip(failed, recorded["paths"], strict=True):
        solved = float(tau[idx])
        original_index = picked_class[idx]
        original_class = names[original_index]
        old_residual = float(class_residual[idx])
        if (solved != expected["delay_s"] or old_residual != expected["residual_s"]
                or original_class != expected["nearest_image"]):
            raise ValueError(f"Saved failing path differs: {case}/{task['task_id']}/{idx}")
        unmerged = np.abs(delays - solved)
        candidate = int(unmerged.argmin())
        candidate_class = owners[candidate]
        candidate_delay = float(delays[candidate])
        candidate_residual = float(unmerged[candidate])
        yield dict(
            case=case, task_id=task["task_id"], path_index=int(idx), xy=xy,
            solved_delay_s=solved,
            original_class=original_class, original_residual_s=old_residual,
            original_class_delay_s=float(classes[original_index]),
            nearest_image=image_name(sequences[candidate]),
            nearest_image_delay_s=candidate_delay,
            nearest_image_residual_s=candidate_residual,
            nearest_image_class=names[candidate_class],
            nearest_image_class_delay_s=float(classes[candidate_class]),
            class_displacement_s=candidate_delay - float(classes[candidate_class]),
            same_class_as_original=bool(original_index == candidate_class),
            in_threshold_candidate_count=int((unmerged <= legacy.tol).sum()),
            recovered_at_strict=bool(candidate_residual <= legacy.tol),
        )


def summary(rows):
    if not rows:
        raise ValueError("Empty failing-path summary")
    recovered = [r for r in rows if r["recovered_at_strict"]]
    return dict(
        failed_in_original=len(rows),
        recovered_without_grouping=len(recovered),
        still_above_threshold=len(rows) - len(recovered),
        recovered_in_original_class=sum(r["same_class_as_original"] for r in recovered),
        recovered_in_different_class=sum(not r["same_class_as_original"] for r in recovered),
        recovered_by_candidate=dict(Counter(r["nearest_image"] for r in recovered)),
        remaining_by_candidate=dict(Counter(r["nearest_image"] for r in rows if not r["recovered_at_strict"])),
        original_residual_max_s=max(r["original_residual_s"] for r in rows),
        nearest_image_residual_max_s=max(r["nearest_image_residual_s"] for r in rows),
        class_displacement_max_s=max(r["class_displacement_s"] for r in rows),
    )


def diagnose(args):
    started, tick = datetime.now(timezone.utc), time.monotonic()
    verify(args.g6 / "G6.json", G6_SHA256)
    original = read(args.g6 / "G6.json")
    verify(Path(g6.__file__), original["matcher_sha256"])
    verify(args.g6 / "selected/SELECTION.json", original["input_sha256"]["/run/selected/SELECTION.json"])
    selection = read(args.g6 / "selected/SELECTION.json")
    legacy = g6.legacy_kernel(args.source)
    if legacy.tol != STRICT_TOL_S or original["strict_tolerance_s"] != STRICT_TOL_S:
        raise ValueError("Unexpected G6 strict threshold")
    g6.check_kernel(legacy)
    traces = args.g6 / "traces"
    g0, g7 = args.production / "g0", args.production / "g7"
    by_case, by_geometry, rows = {}, defaultdict(list), []
    checks = {}
    for case, group in original["cases"].items():
        entry, _, _, tasks, *_ = case_inputs(g0, g7, case)
        stored, _, missing, unexpected = g6.traces_for_case(case, selection[case], traces, checks)
        if missing or unexpected:
            raise ValueError(f"Incomplete archived G6 trace: {case}")
        geometry = case.split("_")[0]
        transforms = None
        if geometry == "G-T2":
            transforms = g6.mirror_transforms(g6.mesh_planes(entry, g0 / "scene"), 3)
        case_rows = []
        for station in group["strict_unmatched_stations"]:
            index = station["task_id"]
            case_rows.extend(diagnose_station(case, tasks[index], stored[index], station, entry,
                                             transforms, legacy))
        if len(case_rows) != group["unmatched_strict"]:
            raise ValueError(f"Incomplete failing-path coverage: {case}")
        by_case[case] = summary(case_rows)
        by_geometry[geometry].extend(case_rows)
        rows.extend(case_rows)
    if len(rows) != original["totals"]["unmatched_strict"]:
        raise ValueError("Original G6 failing-path total differs")
    for path, digest in checks.items():
        archived = f"/run/traces/{Path(path).name}"
        if original["input_sha256"][archived] != digest:
            raise ValueError(f"Digest differs from original G6 run: {archived}")
    result = dict(
        purpose="Post-run attribution of saved G6 failing paths; original gate verdict retained",
        question_id=original["question_id"], official_gate_status=original["status"], role="IMPLEMENTER",
        threshold_s=legacy.tol, image_class_tie_s=legacy.tie_s,
        image_candidate_limitations="Plane images; nearest delay does not verify a finite-face reflection or identify its traced branch",
        sha256=dict(g6=G6_SHA256, selection=sha(args.g6 / "selected/SELECTION.json"),
                    g0_manifest=sha(g0 / "RUN_MANIFEST.json"), g7_manifest=sha(g7 / "RUN_MANIFEST.json"),
                    legacy=original["legacy_sha256"], matcher=original["matcher_sha256"],
                    diagnostic=sha(Path(__file__)), checked_archived_trace_files=len(checks)),
        governance=IMPLEMENTER_POLICY_SHA256,
        code_base_commit=args.code_commit, runtime=dict(python=platform.python_version(), numpy=np.__version__),
        command=[sys.executable, *sys.argv], started_utc=started.isoformat(),
        finished_utc=datetime.now(timezone.utc).isoformat(), wall_s=time.monotonic() - tick,
        total=summary(rows), by_case=by_case, by_geometry={g: summary(items) for g, items in by_geometry.items()},
        rows=rows,
    )
    write(args.out, result)
    print({k: {m: s[m] for m in ("failed_in_original", "recovered_without_grouping", "still_above_threshold")}
           for k, s in ({"ALL": result["total"]} | result["by_geometry"]).items()}, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("g6", "production", "source", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    diagnose(parser.parse_args())


if __name__ == "__main__":
    main()
