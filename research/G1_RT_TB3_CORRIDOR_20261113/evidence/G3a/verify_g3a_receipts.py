"""Recount G3a coverage and mismatch results from the transferred receipts."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def verification(run, inputs):
    def validate_set(manifest):
        verified = {}
        for line in manifest.read_text(encoding="utf-8").splitlines():
            digest, rel = line.split("  ", 1)
            rel = rel.removeprefix("./")
            path = run / rel
            require(path.resolve().is_relative_to(run.resolve()) and rel not in verified,
                    f"Invalid checksum path: {rel}")
            require(sha(path) == digest, f"SHA-256 mismatch: {rel}")
            verified[rel] = digest
        return verified

    received = validate_set(run / "SHA256.txt")
    require((run / "EXIT_CODE.txt").read_text().strip() == "0", "Snowball process failed")
    g3a = read(run / "G3A.json")
    rows = read(run / "POSITION_CHECKS.json")
    manifest = read(run / "MANIFEST.json")
    expected = {}
    for case, totals in read(inputs / "G3_CONTRACT.json")["cases"].items():
        tasks = read(inputs / "cases" / f"{case}.json")
        require(len(tasks) == totals["trace_positions"], f"Wrong G3 position count: {case}")
        for task in tasks:
            key = (case, task["tag"])
            require(key not in expected, f"Duplicate expected position: {key}")
            expected[key] = (task["x"], task["y"])
    require(len(expected) == 195 and len(rows) == 195, "Wrong number of positions")
    require({(r["case"], r["tag"]) for r in rows} == set(expected), "Coverage mismatch")

    raw_hashes = {}
    raw_receipt_paths = set()
    for line in (run / "RAW_SHA256.txt").read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        if rel.endswith(".npz"):
            require(rel not in raw_hashes, f"Duplicate trace {rel}")
            raw_hashes[rel] = digest
        elif rel.endswith(".json"):
            require(rel not in raw_receipt_paths, f"Duplicate receipt {rel}")
            raw_receipt_paths.add(rel)
        else:
            raise ValueError(f"Unexpected raw artifact: {rel}")
    expected_raw_paths = set()
    expected_receipt_paths = set()
    trace_calls = compared = invalid_bins = mismatched_bins = missing = extra = 0
    affected = 0
    case_counts = {}
    for r in rows:
        case, tag = r["case"], r["tag"]
        counts = case_counts.setdefault(case, Counter())
        counts["positions"] += 1
        raw_rel = f"raw/{case}/{tag}.npz"
        receipt_rel = f"raw/{case}/{tag}.json"
        if not r["trace_calls"]:
            require(r["compared_bins"] == 0 and not r["invalid_bins"] and not r["mismatched_bins"],
                    f"Invalid missing-trace record {case}/{tag}")
            continue
        expected_raw_paths.add(raw_rel)
        expected_receipt_paths.add(receipt_rel)
        require(raw_hashes.get(raw_rel) == r["trace_sha256"] and tuple(r["xy"]) == expected[(case, tag)],
                f"Raw trace identity mismatch: {case}/{tag}")
        bad = {b["bin"] for b in r["invalid_bins"]}
        mismatch = {b["bin"] for b in r["mismatched_bins"]}
        require(not (bad & mismatch) and (bad | mismatch) <= set(range(257))
                and len(bad) == len(r["invalid_bins"]) and len(mismatch) == len(r["mismatched_bins"])
                and r["trace_calls"] == 257 and r["compared_bins"] + len(bad) == 257,
                f"Invalid coverage accounting: {case}/{tag}")
        for b in r["mismatched_bins"]:
            require(b["baseline_only"] >= 0 and b["bin_only"] >= 0
                    and b["baseline_only"] + b["bin_only"] > 0, f"Empty mismatch: {case}/{tag}")
            missing += b["baseline_only"]
            extra += b["bin_only"]
        trace_calls += r["trace_calls"]
        compared += r["compared_bins"]
        invalid_bins += len(bad)
        mismatched_bins += len(mismatch)
        affected += bool(mismatch)
        counts.update(compared_bins=r["compared_bins"], invalid_bins=len(bad), mismatched_bins=len(mismatch))
    require(set(raw_hashes) == expected_raw_paths and raw_receipt_paths == expected_receipt_paths,
            "Missing or extra raw output keys")
    for name, count in dict(trace_calls=trace_calls, compared_bins=compared, invalid_bins=invalid_bins,
                            mismatched_bins=mismatched_bins, affected_positions=affected,
                            baseline_only_paths=missing, bin_only_paths=extra,
                            completed_positions=len(raw_hashes)).items():
        require(count == g3a[name], f"Recomputed count differs: {name}")
    for case, count in case_counts.items():
        require(all(count[k] == value for k, value in g3a["cases"][case].items()), f"Case counts differ: {case}")
    status = "INCOMPLETE" if compared != 50115 else "FAIL" if mismatched_bins else "PASS"
    require(g3a["status"] == status and g3a["position_checks_sha256"] == received["POSITION_CHECKS.json"]
            and g3a["manifest_sha256"] == received["MANIFEST.json"], "Status or receipt hash differs")
    print(json.dumps(dict(verification="PASS", verdict=status, pass_coverage=f"{compared}/50115",
                          downloaded_checksums=len(received), checked_remote_trace_hash_entries=len(raw_hashes),
                          mismatched_bins=mismatched_bins, invalid_bins=invalid_bins,
                          frozen_spec_commit=manifest["frozen_spec_commit"], result_sha256=received["G3A.json"]),
                     indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path)
    ap.add_argument("inputs", type=Path)
    args = ap.parse_args()
    verification(args.run, args.inputs)
