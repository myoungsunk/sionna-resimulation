"""Verify G3 transfer and reaggregate the recorded paired metrics."""
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path

run = Path(sys.argv[1])


def read(name):
    return json.loads((run / name).read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


verified = 0
raw_remote = 0
recovery = (run / "analysis/G3.json").is_file()
result_dir = "analysis" if recovery else "output"
receipts = ["INPUT_SHA256.txt", "OUTPUT_SHA256.txt"]
if recovery:
    receipts += ["EVALUATION_INPUT_SHA256.txt", "EVALUATION_OUTPUT_SHA256.txt"]
for receipt in receipts:
    for line in (run / receipt).read_text().splitlines():
        digest, relative = line.split(maxsplit=1)
        path = run / relative
        if receipt == "OUTPUT_SHA256.txt" and path.suffix == ".npz" and not path.is_file():
            raw_remote += 1
            continue
        require(sha(path) == digest, relative)
        verified += 1

contract = read("input/G3_CONTRACT.json")
result = read(f"{result_dir}/G3.json")
require(sha(run / "input/G3_CONTRACT.json") == result["contract_sha256"], "contract SHA")
require(set(result["cases"]) == set(contract["cases"]), "case identities")
all_rows = []
all_usable = True


def check(report, rows, expected):
    require(len(rows) == len({(r["case"], r["pose_id"]) for r in rows}), "duplicate pose")
    coverage = not (report["missing"] or report["unusable"])
    require(coverage == (len(rows) == expected), "coverage mismatch")
    require(report["checks"]["coverage_complete"] == coverage, "coverage verdict")
    if not rows:
        require(not report["passed"], "empty report cannot pass")
        return
    require(report["n_poses"] == len(rows), "pose count")
    values = dict(pose_rel_err_median=statistics.median(r["pose_rel_err"] for r in rows),
                  pose_rel_err_max=max(r["pose_rel_err"] for r in rows),
                  per_bin_rel_err_max=max(r["per_bin_max"] for r in rows),
                  abs_ds_max=max(r["abs_ds"] for r in rows),
                  fp_index_match_fraction=sum(r["fp_index_match"] for r in rows) / len(rows),
                  range_diff_max_m=max(r["range_diff_m"] for r in rows))
    require(all(math.isfinite(v) and v == report[k] for k, v in values.items()), "metric aggregation")
    threshold = report["thresholds"]
    require(threshold == dict(abs_ds_max=0.002, fp_index_match_min=0.995, range_diff_max_m=0.002),
            "preregistered thresholds")
    checks = dict(coverage_complete=coverage,
                  abs_ds_max=values["abs_ds_max"] <= threshold["abs_ds_max"],
                  fp_index_match=values["fp_index_match_fraction"] >= threshold["fp_index_match_min"],
                  range_diff_max_m=values["range_diff_max_m"] <= threshold["range_diff_max_m"])
    require(checks == report["checks"] and all(checks.values()) == report["passed"], "case verdict")


for case, expected in contract["cases"].items():
    tasks = read(f"input/cases/{case}.json")
    report = result["cases"][case]
    rows = read(f"{result_dir}/{case}/PARITY_ROWS.json")
    allowed = {(t["tag"], p["pose_id"], p["yaw_deg"]) for t in tasks for p in t["sampled_yaws"]}
    require(len(allowed) == expected["poses"] and len(tasks) == expected["trace_positions"], "sample size")
    require(all((r["tag"], r["pose_id"], r["yaw_deg"]) in allowed and r["case"] == case for r in rows),
            "pose identity")
    check(report, rows, expected["poses"])
    all_rows.extend(rows)
    all_usable &= report["passed"]
check(result["pooled"], all_rows, sum(v["poses"] for v in contract["cases"].values()))
status = "PASS" if all_usable and result["pooled"]["passed"] else "FAIL"
require(status == result["status"], "overall verdict")
exit_path = "EVALUATION_EXIT_CODE.txt" if recovery else "EXIT_CODE.txt"
require((run / exit_path).read_text().strip() == ("0" if status == "PASS" else "2"), "exit code")
verification = dict(status="PASS", g3_verdict=status, sha256_verified_files=verified,
                    raw_trace_files_retained_remote=raw_remote, cases=len(result["cases"]),
                    paired_poses=len(all_rows), result_sha256=sha(run / result_dir / "G3.json"))
with (run / "LOCAL_VERIFICATION.json").open("x", encoding="utf-8") as stream:
    json.dump(verification, stream, indent=2)
    stream.write("\n")
print(json.dumps(verification))
