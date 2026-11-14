"""G1-DIAG-003 S0 checks against the frozen R2 report."""
import csv
import hashlib
import json
import sys
from pathlib import Path

import numpy as np


root = Path(sys.argv[1])
first = root / "r2_01"
second = root / "r2_02"
comparisons = []
failures = []


def check(name, actual, expected):
    passed = actual == expected
    comparisons.append({"check": name, "actual": actual, "expected": expected,
                        "match": passed})
    if not passed:
        failures.append(name)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric_files(run):
    traces = [p.relative_to(run) for p in (run / "replay").glob("*.npz")]
    return sorted(traces + [
        Path("score/R2_BIAS_METRICS.csv"),
        Path("score/R2_BIAS_CONTRASTS.csv"),
    ])


files = numeric_files(first)
check("R2 numerical file count", len(files), 34)
check("R2 numerical file set", list(map(str, numeric_files(second))),
      list(map(str, files)))
archive_bytes = {}
for f in files:
    left, right = first / f, second / f
    if not right.is_file():
        continue
    archive_bytes[str(f)] = [digest(left), digest(right)]
    check(f"byte equality {f}", left.read_bytes() == right.read_bytes(), True)
    if f.suffix == ".npz":
        with np.load(left, allow_pickle=False) as data:
            t_s = data["t_s"]
            check(f"all frames {f}", len(t_s), 979)
            check(f"evaluation frames {f}", int((t_s >= 30).sum()), 829)

with (first / "score/R2_BIAS_METRICS.csv").open(newline="") as handle:
    rows = list(csv.DictReader(handle))
check("R2 score row count", len(rows), 256)
for i, row in enumerate(rows):
    check(f"score seed row {i}", row["seed"], "0")
    check(f"evaluation count row {i}", row["eval_frames_expected"], "829")
recursive = {
    (r["case"], r["rf_channel"], r["level"], r["method"]): r
    for r in rows if r["evaluation_mode"] == "recursive"
}


def metric(case, channel, level, method, field, expected, digits,
           multiplier=1, signed=False):
    ref = recursive[(case, channel, level, method)]
    sign_flag = "+" if signed else ""
    actual = format(float(ref[field]) * multiplier, f"{sign_flag}.{digits}f")
    check(f"{case}/{channel}/{level}/{method}/{field}", actual, expected)


mount0 = "R2_aA_m0"
for level, dr, los, full in zip(
    ("L0", "L1", "L2"),
    ("1.69", "6.59", "24.97"),
    ("0.50", "0.40", "0.24"),
    ("7.50", "7.54", "7.52"),
):
    for method in ("DR3", "DR4"):
        metric(mount0, "full", level, method, "heading_rmse_deg", dr, 2)
    metric(mount0, "los", level, "J4", "heading_rmse_deg", los, 2)
    metric(mount0, "full", level, "J4", "heading_rmse_deg", full, 2)
metric(mount0, "full", "B0", "J4", "heading_rmse_deg", "7.49", 2)
metric(mount0, "full", "L2", "J4", "heading_rmse_deg", "7.521", 3)
metric(mount0, "full", "L2", "J4", "heading95_coverage", "16.3", 1, 100)
metric(mount0, "full", "L2", "J4", "heading_nees_mean", "86.37", 2)

for mount, channel, s_mean, s_sigma, j_mean, j_sigma in [
    ("m0", "los", "+0.1953", "0.0039", "+0.1996", "0.0022"),
    ("m45", "los", "+0.1989", "0.0033", "+0.2017", "0.0019"),
    ("m0", "full", "+0.1041", "0.0050", "+0.2087", "0.0026"),
    ("m45", "full", "+0.2065", "0.0036", "+0.1993", "0.0019"),
]:
    for method, mean, sigma in (("S4", s_mean, s_sigma), ("J4", j_mean, j_sigma)):
        metric(f"R2_aA_{mount}", channel, "L2", method,
               "bias_final_estimate_dps", mean, 4, signed=True)
        metric(f"R2_aA_{mount}", channel, "L2", method,
               "bias_final_sigma_dps", sigma, 4)

for run in (first, second):
    final = json.loads((run / "replay/FINAL.json").read_text(encoding="utf-8"))
    check(f"{run.name} replay scenario count", len(final["cases"]), 16)
    b0 = [r for r in final["cases"] if r["level"] == "B0"]
    check(f"{run.name} B0 scenario count", len(b0), 4)
    for case in b0:
        check(f"{run.name}/{case['case']}/{case['channel']} B0 max x/P error",
              case["B0_archived_DR_prior_parity"], [0.0, 0.0])

report = {
    "claim_scope": "DIAGNOSTIC_ONLY",
    "s2_prime": "STOP (FULL_6)",
    "step_3": "HOLD",
    "s0_r2": "FAIL" if failures else "REPORT_LEVEL_PASS",
    "s0_anchor_b": "NOT_RUN",
    "s0_overall": "FAIL" if failures else "PENDING_ANCHOR_B",
    "diagnostics_d1_d6": "NOT_RUN",
    "historical_r2_result_zip_frame_comparison": "UNVERIFIED_ARTIFACT_EXPIRED",
    "spec_commit": "ca80a52d8b66d5f96b3ab6de6549b751c835aa88",
    "source_commit": "81cdffbdedf43b318ebf8eddb4fcbac1fd30d878",
    "verified_input_zip_sha256": digest(Path(sys.argv[2])),
    "check_count": len(comparisons),
    "failures": failures,
    "per_file_sha256_first_second": archive_bytes,
    "checks": comparisons,
}
(root / "S0_REGRESSION.json").write_text(json.dumps(report, indent=2) + "\n",
                                         encoding="utf-8")
print(json.dumps({k: report[k] for k in
                  ("s0_r2", "s0_overall", "check_count", "failures")}, indent=2))
for record in comparisons:
    if not record["match"]:
        print(record)
sys.exit(1 if failures else 0)