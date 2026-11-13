"""Build the five parity-eligible v3.3 M0 grid cases."""
import datetime
import hashlib
import json
import time
from argparse import ArgumentParser
from pathlib import Path

from run_step1 import verify
from v33_baseline import M0_EXCLUDED, build_grid

CASES = ("R2_aA_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0")
EXPECTED_STATIONS = {"R2_aA_m0": 21, "R4_aA_m0": 10, "R4_aB_m0": 10,
                     "R5_aA_m0": 30, "R5_aB_m0": 30}
SPEC_COMMIT = "06de4adf336ef4436626c2ad6103c2dcf197d041"


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    parser = ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--banks", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--input-check", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    args = parser.parse_args()
    if args.workers < 1 or args.receipt.exists():
        raise ValueError("Invalid worker count or existing receipt")
    if "R2_aB_m0" not in M0_EXCLUDED:
        raise ValueError("M0 parity exclusion changed")
    verify(args.root, args.input_check)
    records = {}
    for case in CASES:
        started = utc()
        t0 = time.monotonic()
        index = build_grid(args.root, args.banks, args.grid, case, workers=args.workers)
        if index.get("case") != case or index.get("model") != "M0":
            raise ValueError("Unexpected M0 grid identity: " + case)
        if len(index.get("groups", [])) != EXPECTED_STATIONS[case]:
            raise ValueError("Unexpected M0 station count: " + case)
        stem = "S1P_" + case + "_M0"
        files = {}
        for suffix in ("J.npy", "INDEX.json"):
            path = args.grid / (stem + "_" + suffix)
            files[path.name] = {"sha256": digest(path), "bytes": path.stat().st_size}
        records[case] = {
            "status": "BUILT", "stations": len(index["groups"]),
            "started_utc": started, "finished_utc": utc(),
            "elapsed_seconds": time.monotonic() - t0, "grid": files,
        }
        print(json.dumps({"case": case, "status": "BUILT",
                          "stations": len(index["groups"]),
                          "elapsed_seconds": records[case]["elapsed_seconds"]}),
              flush=True)
    report = {
        "stage": "S2-prime B0 M0 XY grid",
        "question_id": "G1-MODEL-001", "spec_commit": SPEC_COMMIT,
        "excluded_by_frozen_M0_parity": sorted(M0_EXCLUDED),
        "cases": records, "workers": args.workers,
        "total_stations": sum(row["stations"] for row in records.values()),
        "created_utc": utc(),
    }
    with args.receipt.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"receipt": str(args.receipt),
                      "total_stations": report["total_stations"],
                      "status": "PASS_M0_GRID_BUILD"}), flush=True)


if __name__ == "__main__":
    main()
