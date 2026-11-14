"""Check transferred F1 pilot receipts and summarize the fixed diagnostic sample."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(sys.argv[1])
CASES = (
    ("G-T2_A", "x6.0000_y-0.3100"),
    ("G-T2_A", "x6.0000_y-0.3300"),
    ("G-T2_A", "x6.0000_y0.4700"),
    ("G-T2_A", "x6.0003_y0.4698"),
    ("G-T2_A", "x6.3521_y0.4684"),
    ("G-T2_A", "x7.0252_y0.0549"),
    ("G-T2_B", "x13.6482_y0.4903"),
    ("G-T2_B", "x13.6500_y0.4902"),
    ("G-T2_C", "x17.0000_y0.4700"),
)
CONTROL_BINS = (0, 52, 121, 128, 138, 139, 140, 141, 142, 143, 144, 162, 173, 174, 205, 256)
DIAGNOSTIC_DELAYS_NS = (12.7115136194789, 20.7318056055783, 20.7357739867575, 67.68729576833721)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(valid, message):
    if not valid:
        raise ValueError(message)


checksums = {}
for line in (HERE / "SHA256.txt").read_text().splitlines():
    expected, filename = line.split("  ./", 1)
    require(Path(filename).name == filename, f"Unexpected recorded path {filename}")
    require(filename not in checksums, f"Duplicate checksum {filename}")
    checksums[filename] = expected
    require(sha(HERE / filename) == expected, f"Changed file {filename}")
require((HERE / "EXIT_CODE.txt").read_text().strip() == "0", "Pilot command failed")

summaries = []
for i, (case, tag) in enumerate(CASES):
    path = HERE / f"{i}_{case}_{tag}.json"
    require(path.name in checksums, "Pilot location missing from checksum manifest")
    d = json.loads(path.read_text())
    rows, controls = d["rows"], d["control_rows"]
    require((d["case"], d["tag"]) == (case, tag), "Location identity mismatch")
    require([r["bin"] for r in rows] == list(range(257)), "Missing or duplicated frequency bin")
    require([r["bin"] for r in controls] == list(CONTROL_BINS), "Control coverage mismatch")
    require(d["input_sha256"]["script"] == checksums["run_f1_pilot.py"], "Pilot script hash mismatch")
    require(d["input_sha256"]["prior_g3"] == "cdca5bc1d53a1ab65328bc9ddce0bd02ff810fd330785177fb87ffd1c0056c1b"
            and d["input_sha256"]["revalidation"] == "93314d133bdab1f449cf8c34bb08c96797aba9b5b8b1b7b66cda4714e4529702",
            "Unexpected reference gate evidence")
    require(d["solver"] == (d["control_solver"] | {"refraction": False})
            and d["control_solver"]["refraction"], "Unexpected F1 delta")
    mismatch = [r["bin"] for r in rows if r["baseline_only"] or r["bin_only"]]
    require(mismatch == d["failed_bins"] and d["status"] == ("FAIL" if mismatch else "PASS"),
            "F1 status mismatch")
    target_present = sum(r["target_paths"] == 1 for r in rows)
    summary = dict(case=case, tag=tag, status=d["status"], paths_at_bin0=rows[0]["paths"],
                   bins_with_signature_mismatch=mismatch,
                   restored_original_target_bins=target_present if i < 5 else None,
                   max_matched_f1_delay_delta_s=max(r["matched_max_delay_delta_s"] for r in rows),
                   max_matched_f1_direction_delta=max(r["matched_max_direction_delta"] for r in rows),
                   controls_with_refraction=sum(r["refraction_paths_on"] > 0 for r in controls),
                   max_control_refraction_energy_share=max(r["refraction_iso_energy_share"] for r in controls),
                   max_common_path_jones_abs_delta=max(r["max_matched_jones_abs_delta"] for r in controls),
                   wall_s=d["wall_s"])
    if i >= 5:
        delay = DIAGNOSTIC_DELAYS_NS[i-5]
        closest = min((1e9 * tau for tau in d["baseline_paths"]["tau_s"]), key=lambda t: abs(t-delay))
        summary["prior_diagnostic_delay_ns"] = delay
        summary["f1_closest_delay_ns_at_bin0"] = closest
        summary["within_delay_tolerance_at_bin0"] = abs(closest-delay) <= 2e-4
    summaries.append(summary)
require(len(list(HERE.glob("[0-8]_G-T2_*.json"))) == 9, "Unexpected pilot output count")

result = dict(question_id="G1-RT-TB3-001", status="PASS" if all(r["status"] == "PASS" for r in summaries) else "FAIL",
              positions=len(CASES), f1_traces=257*len(CASES), control_traces=len(CONTROL_BINS)*len(CASES),
              checksummed_files=len(checksums), source_checksum_manifest=sha(HERE / "SHA256.txt"),
              started_utc=(HERE / "STARTED_UTC.txt").read_text().strip(),
              finished_utc=(HERE / "FINISHED_UTC.txt").read_text().strip(),
              cases=summaries)
print(json.dumps(result, indent=2, allow_nan=False))
