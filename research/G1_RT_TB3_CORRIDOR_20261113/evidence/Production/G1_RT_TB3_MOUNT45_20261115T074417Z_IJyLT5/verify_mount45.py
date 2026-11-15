"""Verify coverage, frame, artifact identity and independent completion receipts."""
import hashlib
import json
from pathlib import Path

root = Path(".")
baseline = Path((root / "MOUNT0_RUN.txt").read_text().strip())
def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

result = root / "results"
runtime = read(result / "RUN_MANIFEST.json")
mount0 = read(root / "PRODUCTION_F1_MOUNT0.json")
assert runtime["f1"] == dict(mount0, mount_deg=45)
generation = read(result / "GENERATION_RESULT.json")
g4 = read(result / "gates/G4.json")
seal = read(result / "gates/SEAL_STORAGE_CHECK.json")
cases = read(result / "CASES.json")
old_cases = read(baseline / "results/CASES.json")
assert set(cases) == set(old_cases) and len(cases) == generation["cases"] == 11
assert generation["status"] == "PASS" and not generation["failures"]
totals = generation["totals"]
assert (totals["poses"], totals["main_poses"], totals["diagnostic_new_poses"],
        totals["near_poses"], totals["trace_positions"], totals["extra_export_solver_calls"]) == (
        61992, 52218, 9774, 27810, 26460, 0)
assert generation["cases_sha256"] == sha(result / "CASES.json")
assert set(g4["cases"]) == set(cases) and g4["mount_deg"] == 45
assert seal["status"] == "PASS" and seal["files"] == 18
assert not (result / "seal/UNSEAL.json").exists()
receipt_keys = ("task_id", "pose_ids", "node_bins", "n_full_paths", "n_near_paths")
for case, info in cases.items():
    before = old_cases[case]
    assert info["mount_deg"] == 45
    for key in ("poses", "main_poses", "diagnostic_new_poses", "trace_positions",
                "near_poses", "anchor_xyz", "robot_z", "shape", "samples_sha256",
                "solver_batch_calls", "extra_export_solver_calls"):
        assert info[key] == before[key], (case, key)
    for key in ("los_H_sha256", "full_H_sha256"):
        assert info[key] != before[key], (case, key)
    rel = Path("paths") / case / "TRACE_RECEIPTS.json"
    for left, right in zip(read(result / rel), read(baseline / "results" / rel)):
        assert all(left[k] == right[k] for k in receipt_keys), (case, left["task_id"])
p90_max = max(arm["p90_abs_delta_s"] for case in g4["cases"].values()
              for arm in case["gate_by_arm"].values())
summary = dict(
    mount_deg=45, generation_status="PASS", g4_status=g4["status"], g4_p90_max_abs_delta_s=p90_max,
    g6_status="BASELINE_FAIL_OPEN", status="GENERATED_AND_CHECKED" if g4["status"] == "PASS" else "G4_FAIL",
    case_count=len(cases), totals=totals,
    generation_wall_s=generation["wall_s"], mount0_path_receipt_match=True,
    seals_verified=seal["files"], seal_storage_check_sha256=sha(result / "gates/SEAL_STORAGE_CHECK.json"),
    mount0_seal_receipt_sha256=sha(root / "MOUNT0_SEAL_BEFORE.sha256"),
    g8_canary_sha256=sha(root / "canary01/CANARY.json"), g4_sha256=sha(result / "gates/G4.json"),
    cases_sha256=sha(result / "CASES.json"))
with (root / "MOUNT45_RESULT.json").open("x") as out:
    json.dump(summary, out, indent=2, allow_nan=False)
    out.write("\n")
print(json.dumps(summary), flush=True)
