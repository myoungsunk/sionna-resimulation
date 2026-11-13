"""Check the copied G3 revalidation receipts against the frozen G3 sample."""
import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "G3"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    import hashlib

    with path.open("rb") as data:
        return hashlib.file_digest(data, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(run):
    expected_hashes = {}
    for manifest, parent in (("SHA256.txt", run), ("EVALUATION_SHA256.txt", run / "EVALUATION")):
        for line in (parent / manifest).read_text().splitlines():
            digest, path = line.split(maxsplit=1)
            if path == "-":
                require(digest == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                        "expected empty-input checksum")
                continue
            path = Path(path).as_posix()
            require(path not in expected_hashes, f"duplicate hash: {path}")
            require(sha(parent / path) == digest, f"bad hash: {path}")
            expected_hashes[path] = digest
    for name in ("analysis/G3.json", "REFERENCE_SOLVER.json", "REVALIDATION_CONTRACT.json",
                 "SHARD_EXIT.json", "EXIT_CODE.txt", "COMMAND.txt", "EVALUATION_EXIT_CODE.txt"):
        require(name in expected_hashes, f"missing digest: {name}")

    result = read(run / "EVALUATION/analysis/G3.json")
    original = read(BASE / "analysis/G3.json")
    frozen = read(BASE / "input/G3_CONTRACT.json")
    revalidation = read(run / "REVALIDATION_CONTRACT.json")
    require(original["status"] == result["original_g3_status"] == "FAIL", "original verdict")
    require(sha(BASE / "analysis/G3.json") == result["original_g3_sha256"] ==
            revalidation["frozen_gate_sha256"], "original gate SHA")
    require(sha(BASE / "input/G3_CONTRACT.json") == result["contract_sha256"] ==
            revalidation["frozen_scope_sha256"], "scope SHA")
    require(sha(run / "REVALIDATION_CONTRACT.json") == result["revalidation_contract_sha256"], "new scope SHA")
    require(sha(run / "revalidate_tb3_g3_reference.py") == revalidation["runner_sha256"], "runner SHA")
    require(revalidation["parity_sha256"] == result["parity_sha256"] == frozen["parity_sha256"], "parity identity")
    require(result["evaluator_sha256"] == original["evaluator_sha256"], "evaluator identity")
    require(sha(run / "TRACE_SHA256.txt") == result["trace_manifest_sha256"], "trace manifest SHA")
    require((run / "EXIT_CODE.txt").read_text().strip() == "1", "first attempt execution receipt")
    frozen_solver = read(BASE / "input/REFERENCE.json")["block_c_solver"]
    require(frozen_solver == revalidation["production_arm_solver"], "production solver")
    require(read(run / "REFERENCE_SOLVER.json")["solver"] == revalidation["reference_arm_solver"] ==
            (frozen_solver | {"samples_per_src": 400_000}), "reference solver")
    require(result["reference_rays"] == 400_000, "sample count")
    require(set(result["cases"]) == set(frozen["cases"]), "case scope")
    expected_shards = {(case, f"{i}/6") for case in frozen["cases"] for i in range(6)}
    shards = read(run / "SHARD_EXIT.json")
    require(len(shards) == len(expected_shards) and
            {(row["case"], row["shard"]) for row in shards} == expected_shards and
            all(row["exit_code"] == 0 for row in shards), "trace shard receipts")

    expected_nodes = {}
    for line in (BASE / "OUTPUT_SHA256.txt").read_text().splitlines():
        digest, relative = line.split(maxsplit=1)
        path = Path(relative)
        if path.parts[2:3] == ("node_interpolation",) and path.suffix in (".json", ".npz"):
            expected_nodes[relative] = digest
    require(len(expected_nodes) == 390 and expected_nodes == revalidation["production_arm_sha256"],
            "production trace identities")

    def check(report, rows, expected):
        require(len(rows) == report["n_poses"] and rows, "row count")
        metrics = dict(pose_rel_err_median=statistics.median(r["pose_rel_err"] for r in rows),
                       pose_rel_err_max=max(r["pose_rel_err"] for r in rows),
                       per_bin_rel_err_max=max(r["per_bin_max"] for r in rows),
                       abs_ds_max=max(r["abs_ds"] for r in rows),
                       range_diff_max_m=max(r["range_diff_m"] for r in rows),
                       fp_index_match_fraction=sum(r["fp_index_match"] for r in rows) / len(rows))
        require(all(math.isfinite(value) and report[k] == value for k, value in metrics.items()), "metric aggregation")
        thresholds = report["thresholds"]
        require(thresholds == original["pooled"]["thresholds"], "frozen thresholds")
        checks = dict(coverage_complete=(len(rows) == expected and not report["missing"] and not report["unusable"]),
                      abs_ds_max=metrics["abs_ds_max"] <= thresholds["abs_ds_max"],
                      range_diff_max_m=metrics["range_diff_max_m"] <= thresholds["range_diff_max_m"],
                      fp_index_match=metrics["fp_index_match_fraction"] >= thresholds["fp_index_match_min"])
        require(checks == report["checks"] and all(checks.values()) == report["passed"], "verdict")

    pooled_rows = []
    for case, config in frozen["cases"].items():
        path = f"analysis/{case}/PARITY_ROWS.json"
        require(path in expected_hashes, f"missing hash: {path}")
        rows = read(run / "EVALUATION" / path)
        report = result["cases"][case]
        tasks = read(BASE / "input" / "cases" / f"{case}.json")
        eligible = {(task["tag"], pose["pose_id"], pose["yaw_deg"])
                    for task in tasks for pose in task["sampled_yaws"]}
        actual = {(row["tag"], row["pose_id"], row["yaw_deg"]) for row in rows}
        require(len(tasks) == config["trace_positions"] and len(eligible) == config["poses"], "scope count")
        require(len(actual) == len(rows) and actual <= eligible and all(row["case"] == case for row in rows),
                "pose identities")
        check(report, rows, config["poses"])
        pooled_rows.extend(rows)
    pooled = result["pooled"]
    check(pooled, pooled_rows, sum(c["poses"] for c in frozen["cases"].values()))
    verdict = "PASS" if pooled["passed"] and all(case["passed"] for case in result["cases"].values()) else "FAIL"
    require(result["status"] == verdict, "overall verdict")
    require((run / "EVALUATION/EVALUATION_EXIT_CODE.txt").read_text().strip() == ("0" if verdict == "PASS" else "2"), "evaluation exit code")
    print(json.dumps(dict(verification="PASS", verdict=verdict, paired=len(pooled_rows),
                          unusable=len(pooled["unusable"]), hashes_verified=len(expected_hashes),
                          channels_retained_remotely=len(expected_nodes) // 2, result_sha256=sha(run / "EVALUATION/analysis/G3.json")),
                     indent=2))


if __name__ == "__main__":
    verify(Path(sys.argv[1]))
