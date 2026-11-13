"""Replay the frozen G1-FLOOR baseline and compare the preregistered R0 outputs."""
from pathlib import Path
import argparse
import json
import shutil

import run_step1 as s1
import run_step2 as s2

def main():
    p = argparse.ArgumentParser()
    p.add_argument("inputs", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.mkdir()
    base = Path(__file__).resolve().parent
    prior = base / "RUN_20261113T052908Z"
    s1.run(a.inputs, a.output, base / "INPUTS_CHECK_1ce68f3.json", analyze=False)
    expected = json.loads((prior / "S2_VERDICT.json").read_bytes())
    comparisons = {}
    for case in expected["n90_by_case"]:
        path = f"S1_J_{case}.npy"
        comparisons[case] = {
            "replay_sha256": s1.sha(a.output / path),
            "reference_sha256": s1.sha(prior / path),
        }
    bits = all(c["replay_sha256"] == c["reference_sha256"] for c in comparisons.values())
    summary = dict(passed=False, j_bit_identical=bits, comparisons=comparisons)
    receipt = a.output / "R0.json"
    s1.dump(receipt, summary)
    if not bits:
        raise SystemExit("R0 J curves differ")
    for name in ("S1_RHO.json", "S2_PARAMS.json"):
        shutil.copyfile(prior / name, a.output / name)
    # R0 requires the same posterior calculation and 1000 frozen replicates;
    # the legacy STOP-only floor scan is outside the replay comparison.
    s2.floor_scan = lambda *_: None
    replay = s2.run(a.output)
    keys = ("ratio_1_to_17", "nees_1_to_17", "coverage_1_to_17")
    diff = {m: {k: replay["stats"][m][k] - expected["stats"][m][k] for k in keys}
            for m in s2.MODELS}
    passed = all(abs(x) < 1e-9 for m in diff.values() for x in m.values())
    summary.update(passed=passed, statistic_differences=diff)
    s1.dump(receipt, summary)
    if not passed:
        raise SystemExit("R0 Step 2 does not reproduce")

if __name__ == "__main__":
    main()
