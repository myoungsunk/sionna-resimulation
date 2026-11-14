"""Seal and hash S2′ evidence without changing any prior execution."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

base = Path(sys.argv[1])
assert base.name == "RUN4_20261113T105130Z"
out = base / "s2_out"
entry = base.parent / "RUN4_20261113T094312Z" / "MANIFEST.json"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read(name):
    return (out / name).read_text().strip()


def json_file(name):
    return json.loads(read(name))


entry_sha = sha(entry)
assert entry_sha == "18d1a312da1e870746b4569658da8a98ffa46601af4dc9040be5d084eac7e299"
gate = json.loads(entry.read_text())
results = {}
for name in ("calibrate", "calibrate_retry", "primary", "primary_retry", "b0", "sensitivity"):
    exit_file = out / ("EXIT_" + name + ".txt")
    if not exit_file.is_file():
        continue
    results[name] = {
        "started_utc": read("START_" + name + "_UTC.txt"),
        "finished_utc": read("FINISH_" + name + "_UTC.txt"),
        "exit_code": int(exit_file.read_text()),
        "command": read("COMMAND_" + name + ".txt"),
        "code_hash_list": "s2_out/CODE_" + name + "_SHA256.txt",
    }
verdict = json_file("S2P_VERDICT.json")
assert verdict["spec_commit"] == gate["spec_commit"]
assert any(results.get(k, {}).get("exit_code") == 0 for k in ("primary", "primary_retry"))
assert sum(verdict["physical_stations"].values()) == 122
assert results["b0"]["exit_code"] == results["sensitivity"]["exit_code"] == 0
assert json_file("INDEPENDENT_CHECK.json")["status"] == "PASS"
reused, grid_counts = {}, {}
for path in sorted((base / "grid").glob("*_INDEX.json")):
    index = json.loads(path.read_text())
    grid_counts[index["model"]] = grid_counts.get(index["model"], 0) + len(index["groups"]) * 20
    for name, value in index["files"].items():
        file = base / "grid" / name
        assert sha(file) == value, name
        reused[name] = {"bytes":file.stat().st_size, "sha256":value}
    reused[path.name] = {"bytes":path.stat().st_size, "sha256":sha(path)}
assert grid_counts == {"M0": 2020, "M1-R(J_joint)": 2440}
manifest = {
    "question_id": "G1-MODEL-001", "role": "IMPLEMENTER", "run_id": base.name,
    "repository": gate["repository"], "branch": gate["branch"],
    "spec_commit": gate["spec_commit"], "spec_git_blob": gate["spec_git_blob"],
    "research_governance_sha256": gate["research_governance_sha256"],
    "entry_run": gate["run_id"], "entry_manifest_sha256": entry_sha,
    "prior_evidence": gate["prior_evidence"],
    "gate_status": gate["status"]["G_E2E_PRIME"],
    "sealed_utc": datetime.now(timezone.utc).isoformat(),
    "stages": results, "input_sha256": gate["input_sha256"],
    "bank_sha256": gate["bank_sha256"], "grid_files": reused, "grid_rf_realizations": grid_counts,
    "grid_payload_bytes": sum(v["bytes"] for n,v in reused.items() if n.endswith(".npy")),
    "code_sha256": {str(p.relative_to(base)):sha(p) for p in sorted((base / "s2_code").glob("*"))
                    if p.is_file()},
    "output_sha256": {str(p.relative_to(base)):sha(p) for p in sorted(out.glob("*"))
                      if p.is_file()},
    "root_sha256": {p.name:sha(p) for p in sorted(base.glob("*")) if p.is_file()},
    "verdict": verdict["verdict"],
    "coverage": verdict["coverage"],
    "correlation": verdict["correlation"],
    "bootstrap": {"reps":verdict["bootstrap_replicates"], "paths":verdict["paths_per_replica"],
                  "seeds":verdict["seeds"]},
    "scope": {
        "primary_A2": "COMPLETE",
        "B0": "COMPLETE" if results.get("b0", {}).get("exit_code") == 0 else "NOT_COMPLETED",
        "sigma_beta": "COMPLETE" if results.get("sensitivity", {}).get("exit_code") == 0 else "NOT_COMPLETED",
        "E2_E3_E4_and_M1_RI": "NOT_RUN_PENDING_SPECIFICATION",
        "step3": "HELD",
    }
}
with (base / "MANIFEST.json").open("x", encoding="utf-8") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2, allow_nan=False)
    f.write("\n")
print(json.dumps({"verdict":manifest["verdict"], "outputs":len(manifest["output_sha256"]),
                  "grid_files":len(reused), "scope":manifest["scope"]}))

