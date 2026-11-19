"""Verify the added-arm G3 execution against its pretrace sample manifest."""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import sys

BINS = 257
STAGES = ("G3A", "G3B", "G3C")


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open("rb") as stream:
        block_hash = hashlib.sha256()
        for block in iter(lambda: stream.read(1 << 20), b""):
            block_hash.update(block)
    return block_hash.hexdigest()


def collect_stage(run, stage, manifest, tasks):
    finished = read(run / f"{stage}_RUN.json")
    if finished["sample_manifest_sha256"] != sha(run / "SAMPLE_MANIFEST.json"):
        raise ValueError(f"{stage}: inconsistent sample manifest")
    exits = {(r["case"], r["task_id"]): r["exit_code"] for r in finished["task_exits"]}
    if len(exits) != len(tasks) or set(exits) != {(case, task["task_id"]) for case, task in tasks}:
        raise ValueError(f"{stage}: unexpected task exit coverage")
    scopes = defaultdict(list)
    source_hashes = {}
    for case, task in tasks:
        task_id = task["task_id"]
        out = run / "cases" / case / "tasks" / str(task_id)
        receipt = out / f"{stage}.json"
        worker = read(receipt)
        if ((worker["stage"].upper(), worker["case"], worker["task_id"], worker["positions"])
                != (stage, case, task_id, 1)):
            raise ValueError(f"Invalid worker receipt: {receipt}")
        if (worker["input_sha256"]["sample_plan"] != manifest["case_plans"][case]
                or worker["solver_100k"]["refraction"] is not False
                or worker["solver_100k"]["samples_per_src"] != 100_000):
            raise ValueError(f"Invalid nominal trace provenance: {receipt}")
        if stage != "G3A" and worker["input_sha256"]["g3a_receipt"] != sha(out / "G3A.json"):
            raise ValueError(f"Invalid nominal trace receipt reuse: {receipt}")
        if stage == "G3C" and worker["solver_400k"] != dict(worker["solver_100k"], samples_per_src=400_000):
            raise ValueError(f"Invalid 400k configuration: {receipt}")
        if exits[case, task_id] != (0 if worker["status"] == "PASS" else 2):
            raise ValueError(f"Inconsistent worker exit: {receipt}")
        for filename, digest in worker["output_sha256"].items():
            if sha(out / filename) != digest:
                raise ValueError(f"Worker output changed: {out / filename}")
        if stage != "G3A":
            detail = read(out / f"{stage}_PARITY_ROWS.json")
            expected = {(arm, task["tag"], pose["pose_id"], pose["yaw_deg"])
                        for arm, item in task["arms"].items() for pose in item["sampled_yaws"]}
            keys = {(row["arm"], row["tag"], row["pose_id"], row["yaw_deg"]) for row in detail}
            if len(detail) != len(expected) or keys != expected:
                raise ValueError(f"Unexpected yaw-comparison coverage: {receipt}")
        if stage == "G3C":
            energy = read(out / "G3C_ENERGY_ROWS.json")
            if len(energy) != 1 or energy[0]["tag"] != task["tag"]:
                raise ValueError(f"Unexpected energy trace key: {receipt}")
            bins = [row["bin"] for name in ("energy", "invalid") for row in energy[0][name]]
            if sorted(bins) != list(range(BINS)):
                raise ValueError(f"Unexpected frequency comparison coverage: {receipt}")
        calls = worker["timings"]["solver_calls"]
        if calls != (17 if stage == "G3B" else BINS):
            raise ValueError(f"Unexpected solver-call coverage ({calls}): {receipt}")
        source_hashes[receipt.relative_to(run).as_posix()] = sha(receipt)
        for arm in task["arms"]:
            report = worker["arms"][arm]
            row = dict(report, solver_calls=calls)
            scopes["pooled"].append(row)
            scopes[f"arm:{arm}"].append(row)
            scopes[f"case:{case}"].append(row)
            scopes[f"case_arm:{case}:{arm}"].append(row)

    def aggregate(rows):
        out = {"positions": len(rows), "solver_calls": sum(r["solver_calls"] for r in rows)}
        if stage == "G3A":
            keys = ("expected_bins", "compared_bins", "invalid_bins", "mismatched_bins")
            counts = {k: sum(r[k] for r in rows) for k in keys}
            passed = (counts["expected_bins"] == counts["compared_bins"] == len(rows) * BINS
                      and counts["invalid_bins"] == counts["mismatched_bins"] == 0)
        elif stage == "G3B":
            count = sum(r["completed_comparisons"] for r in rows)
            expected = sum(r["expected_comparisons"] for r in rows)
            usable = [r for r in rows if r["completed_comparisons"]]
            n_match = sum(round(r["fp_index_match_fraction"] * r["completed_comparisons"]) for r in usable)
            thresholds = {"abs_ds_max": 0.002, "fp_index_match_min": 0.995, "range_diff_max_m": 0.002}
            ds = max((r["abs_ds_max"] for r in usable), default=None)
            dist = max((r["range_diff_max_m"] for r in usable), default=None)
            fraction = n_match / count if count else None
            counts = dict(expected_comparisons=expected, completed_comparisons=count,
                          fp_index_matches=n_match, fp_index_match_fraction=fraction,
                          abs_ds_max=ds, range_diff_max_m=dist, thresholds=thresholds)
            passed = (bool(usable) and count == expected and ds <= 0.002
                      and fraction >= 0.995 and dist <= 0.002)
        else:
            keys = ("expected_bins", "compared_bins", "invalid_bins", "expected_comparisons",
                    "completed_comparisons", "added_paths", "removed_paths")
            counts = {k: sum(r[k] for r in rows) for k in keys}
            for k in ("abs_ds_max", "max_added_energy_fraction", "max_removed_energy_fraction"):
                counts[k] = max((r[k] for r in rows if r[k] is not None), default=None)
            passed = (counts["expected_bins"] == counts["compared_bins"] == len(rows) * BINS
                      and counts["invalid_bins"] == 0
                      and counts["completed_comparisons"] == counts["expected_comparisons"]
                      and counts["max_added_energy_fraction"] is not None
                      and counts["max_added_energy_fraction"] < 0.01 and counts["abs_ds_max"] <= 0.002)
        return dict(out, **counts, status="PASS" if passed else "FAIL")

    results = {name: aggregate(rows) for name, rows in sorted(scopes.items())}
    return dict(stage=stage, status="PASS" if all(v["status"] == "PASS" for v in results.values()) else "FAIL",
                started_utc=finished["started_utc"], finished_utc=finished["finished_utc"],
                wall_s=finished["wall_s"], summary=results, receipt_sha256=source_hashes)


def seal_check(production):
    root = production / "results"
    manifest_path = root / "seal" / "SEAL_MANIFEST.json"
    log_path = root / "seal" / "ACCESS_LOG.jsonl"
    if (sha(manifest_path) != "4d755c9a016275f2ba51fee02e9908fe8cb2a27f32c187192f00bc957c45ee4a"
            or sha(log_path) != "92a670d7946869d0061b8fafb29d10b19b2343f9566b4eb3acdce5be92fb8b91"):
        raise ValueError("Production seal records changed")
    manifest = read(manifest_path)
    expected = {f"{geom}_{anchor}" for geom in ("G-T2", "G-V") for anchor in "ABC"}
    if (manifest["status"] != "SEALED" or set(manifest["cases"]) != expected or list(root.rglob("UNSEAL.json"))):
        raise ValueError("Production seal status changed")
    count = 0
    for case, rec in manifest["cases"].items():
        for rel, si in rec["files"].items():
            path = root / rel
            if path.is_symlink() or path.stat().st_mode & 0o222 or path.stat().st_size != si["bytes"]:
                raise ValueError(f"Production sealed file mode/size changed: {path}")
            if sha(path) != si["sha256"]:
                raise ValueError(f"Production sealed file digest changed: {path}")
            count += 1
    if count != 18:
        raise ValueError("Production seal file coverage is incomplete")
    return dict(status="SEALED", checked_files=count, cases=sorted(expected),
                seal_manifest_sha256=sha(manifest_path), seal_access_log_sha256=sha(log_path))


def main():
    run, production = (Path(arg).resolve() for arg in sys.argv[1:])
    manifest = read(run / "SAMPLE_MANIFEST.json")
    tasks = []
    for case, ids in manifest["cases"].items():
        path = run / "cases" / case / "SAMPLE_PLAN.json"
        rows = read(path)["tasks"]
        if sha(path) != manifest["case_plans"][case] or [t["task_id"] for t in rows] != ids:
            raise ValueError("Frozen case plan changed")
        tasks.extend((case, t) for t in rows)
    if len(tasks) != 195 or sum(len(v["sampled_yaws"]) for _, task in tasks for v in task["arms"].values()) != 2739:
        raise ValueError("Unexpected frozen XY or yaw scope")
    stages = {name: collect_stage(run, name, manifest, tasks) for name in STAGES}
    result = dict(question_id="G1-RT-TB3-002", role="IMPLEMENTER",
                  status="PASS" if all(rec["status"] == "PASS" for rec in stages.values()) else "FAIL",
                  sample_counts=manifest["sample_counts"], sample_manifest_sha256=sha(run / "SAMPLE_MANIFEST.json"),
                  checked_utc=datetime.now(timezone.utc).isoformat(), stages=stages, seal=seal_check(production),
                  summarizer_sha256=sha(Path(__file__)))
    with (run / "DIAG_G3_RESULT.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    for name, stage in stages.items():
        print(name, stage["status"], stage["wall_s"], stage["summary"]["pooled"])
    print(result["seal"])
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
