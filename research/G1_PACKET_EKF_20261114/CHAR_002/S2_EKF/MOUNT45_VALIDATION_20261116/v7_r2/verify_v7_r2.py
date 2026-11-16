"""Verify the published V7 R2 execution record without loading the RF arrays."""

import hashlib
import json
import math
from pathlib import Path, PureWindowsPath


ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_bytes())


def check_hash(path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"SHA-256 mismatch: {path}")


def main():
    execution = ROOT / "execution"
    receipt = read(execution / "EXECUTION.json")
    if receipt["status"] != "PASS_EXECUTION" or receipt["exit_code"] != 0:
        raise ValueError("The frozen V7 execution did not pass")
    contract_path = ROOT / "RUN_CONTRACT.json"
    check_hash(contract_path, receipt["contract_sha256"])
    contract = read(contract_path)
    runner = ROOT.parent / "run_v7_mount45_r2.py"
    runner_sha, = [
        expected for name, expected in contract["inputs_sha256"].items()
        if PureWindowsPath(name).name == runner.name
    ]
    check_hash(runner, runner_sha)
    check_hash(execution / "V7_R2.json", receipt["outputs"]["V7_R2.json"])
    result = read(execution / "V7_R2.json")
    if result["status"] != "PARTIAL_R2_ONLY" or set(result["results"]) != {"B0_R2", "L2_R2"}:
        raise ValueError("Unexpected V7 route or bias scope")

    threshold = contract["V7_A_over_B"]
    for label, values in result["results"].items():
        for name, row in values["channels"].items():
            lower, upper = row["ci95"]["B"]
            ratio = row["ratio_A_over_B"]
            if values["complete_10s_blocks"] < 8 or lower <= 0 <= upper:
                if ratio is not None or row["status"] != "INCONCLUSIVE":
                    raise ValueError(f"Unresolved denominator was classified: {label}/{name}")
                continue
            signed = row["weighted_signed"]
            expected_ratio = abs(signed["A"] / signed["B"])
            status = "SUPPORTED" if expected_ratio >= threshold else "NOT_SUPPORTED"
            if ratio is None or not math.isclose(ratio, expected_ratio) or row["status"] != status:
                raise ValueError(f"Unexpected A/B decision: {label}/{name}")
    print("PASS V7 R2 B0/L2 execution, runner, contract, and A/B results")


if __name__ == "__main__":
    main()
