"""Build and seal the six primary M1-R(J_joint) XY grids for G1-MODEL-001."""
import datetime
import hashlib
import json
import shutil
import time
from pathlib import Path
from argparse import ArgumentParser

from run_step1 import verify
from v33_observation import build_grid

CASES = ("R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0")
RUN3_R5 = {
    "S1P_R5_aA_m0_M1R_JOINT_J.npy": "ce2dfcd37c28468b34df9d9f81e1696430f0ea30f3ecbd1cc4638692a594ff93",
    "S1P_R5_aA_m0_M1R_JOINT_MIN_CHI2.npy": "2236e85fc0b17c5103f7bac22b0f92fe6c6be18008006748e99cd29298f64846",
    "S1P_R5_aA_m0_M1R_JOINT_INDEX.json": "ae224c819add53dc6f377481d3ded9f2785d18a36e6387bdef09ce7b38762606",
}
EXPECTED_STATIONS = {"R2_aA_m0": 21, "R2_aB_m0": 21,
                     "R4_aA_m0": 10, "R4_aB_m0": 10,
                     "R5_aA_m0": 30, "R5_aB_m0": 30}
SPEC_COMMIT = "06de4adf336ef4436626c2ad6103c2dcf197d041"
RUN3_COMMIT = "b6de9ffaffc7b1a40b9caebbef197d879e447e19"


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    parser = ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--banks", type=Path, required=True)
    parser.add_argument("--grid", type=Path, required=True)
    parser.add_argument("--prior-grid", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--input-check", type=Path, required=True)
    parser.add_argument("--workers", type=int, required=True)
    args = parser.parse_args()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    if args.receipt.exists():
        raise FileExistsError(args.receipt)
    args.grid.mkdir(parents=True, exist_ok=True)
    verify(args.root, args.input_check)
    inherited = {}
    r5_records = []
    prior_stem = "S1P_R5_aA_m0_M1R_JOINT"
    for name, expected in RUN3_R5.items():
        source = args.prior_grid / name
        if digest(source) != expected:
            raise ValueError("RUN3 R5 grid hash mismatch: " + name)
        target = args.grid / name
        if target.exists():
            raise FileExistsError(target)
        shutil.copyfile(str(source), str(target))
        actual = digest(target)
        if actual != expected:
            raise ValueError("Copied R5 grid hash mismatch: " + name)
        r5_records.append({"file": name, "sha256": actual, "bytes": target.stat().st_size})
    prior_index = json.loads((args.grid / (prior_stem + "_INDEX.json")).read_text())
    if prior_index.get("case") != "R5_aA_m0" or prior_index.get("model") != "M1-R(J_joint)":
        raise ValueError("R5 inherited grid identity mismatch")
    inherited["R5_aA_m0"] = r5_records
    case_records = {}
    for case in CASES:
        if case == "R5_aA_m0":
            case_records[case] = {
                "status": "REUSED_HASH_VERIFIED_RUN3",
                "stations": len(prior_index["groups"]),
                "started_utc": None,
                "finished_utc": utc(),
                "grid": r5_records,
            }
            continue
        started = utc()
        t0 = time.monotonic()
        index = build_grid(args.root, args.banks, args.grid, case, workers=args.workers)
        if index.get("case") != case or index.get("model") != "M1-R(J_joint)":
            raise ValueError("Unexpected grid identity: " + case)
        if len(index.get("groups", [])) != EXPECTED_STATIONS[case]:
            raise ValueError("Unexpected station count: " + case)
        files = {}
        stem = "S1P_" + case + "_M1R_JOINT"
        for suffix in ("J.npy", "MIN_CHI2.npy", "INDEX.json"):
            path = args.grid / (stem + "_" + suffix)
            files[path.name] = {"sha256": digest(path), "bytes": path.stat().st_size}
        case_records[case] = {
            "status": "BUILT",
            "stations": len(index["groups"]),
            "started_utc": started,
            "finished_utc": utc(),
            "elapsed_seconds": time.monotonic() - t0,
            "grid": files,
        }
        print(json.dumps({"case": case, "status": "BUILT",
                          "stations": len(index["groups"]),
                          "elapsed_seconds": case_records[case]["elapsed_seconds"]}),
              flush=True)
    report = {
        "stage": "S2-prime M1-R(J_joint) XY grid",
        "question_id": "G1-MODEL-001",
        "spec_commit": SPEC_COMMIT,
        "run3_commit": RUN3_COMMIT,
        "cases": case_records,
        "workers": args.workers,
        "total_stations": sum(row["stations"] for row in case_records.values()),
        "created_utc": utc(),
    }
    with args.receipt.open("x") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"receipt": str(args.receipt),
                      "total_stations": report["total_stations"],
                      "status": "PASS_GRID_BUILD"}), flush=True)


if __name__ == "__main__":
    main()
