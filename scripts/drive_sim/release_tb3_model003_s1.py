"""Combine the frozen prior gates, regeneration verification, and S0 for S1."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


PRIOR = "8d56c1b41532ebe6bb18df7a359d7da52ca02b0e"
S0 = "924222dd797e47b7885f8a006b18a4dc7419b31c"
RT = "research/G1_RT_TB3_CORRIDOR_20261113/evidence"
S0_DIR = "research/G1_PACKET_EKF_20261114/MODEL_003/S0"
REGEN_CASES = {"G-T2_B", "G-T2_C"}
PUBLISHED = {
    "G0": "G0/gates/G0.json",
    "G1": "G1/output/G1.json",
    "G2": "G2/output/G2.json",
    "G3a": "G3a/G1_RT_TB3_G3A_20261114T065509Z_qJRtuw/G3A.json",
    "G3b": "G3b/G1_RT_TB3_G3B_20261114T072931Z_tUu1JZ/G3B.json",
    "G3c": "G3c/G1_RT_TB3_G3C_20261114T073923Z_hfLYcu/G3C.json",
    "G4": "G4/G1_RT_TB3_PRODUCTION_20261114T101708Z_6ZEqNa/G4.json",
    "G5": "G5/G1_RT_TB3_G5_20261114T122910Z_94D6ow/G5.json",
    "G7": "G7/G1_RT_TB3_G7_20261114T091332Z/G7.json",
    "G8": "G8/G1_RT_TB3_G8_REVALIDATE_20261114_QG7Pn5/output/G8.json",
}


def record(blob, **provenance):
    data = json.loads(blob)
    if data.get("status") != "PASS":
        raise ValueError(f"Gate status is {data.get('status')}: {provenance}")
    return data, dict(status="PASS", sha256=hashlib.sha256(blob).hexdigest(), **provenance)


def commit_evidence(commit, path):
    raw = subprocess.check_output(["git", "show", f"{commit}:{path}"])
    return record(raw, commit=commit, path=path)[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("regeneration", "g9", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    gates = {g: commit_evidence(PRIOR, f"{RT}/{f}") for g, f in PUBLISHED.items()}
    regeneration, regen_record = record(args.regeneration.read_bytes())
    g9, entered_g9 = record(args.g9.read_bytes())
    if (set(regeneration["regenerated_cases"]) != REGEN_CASES
            or regeneration["inputs_sha256"]["g9"] != entered_g9["sha256"]
            or g9["seal_status"] != "SEALED" or g9["violations"] != 0):
        raise ValueError("Release has inconsistent regeneration or seal provenance")
    gates["G6"] = regen_record
    gates["G9"] = entered_g9
    check = commit_evidence(S0, f"{S0_DIR}/TIMELINE_READBACK.json")
    result = dict(question_id="G1-MODEL-003", status="PASS", s1_eligible=True,
                  s0=check, gates=gates, release_regeneration=regen_record,
                  g3a_b_c_and_g4_g8_regenerated_cases=sorted(REGEN_CASES),
                  s1_rt_scope=["G-T1_A", "G-T1_B", "G-T1_C"])
    with args.out.open("x", encoding="utf-8") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
