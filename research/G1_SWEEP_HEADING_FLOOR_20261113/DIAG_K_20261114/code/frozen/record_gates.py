"""Record the frozen observations and v3.4 entry gate for the S2′ run."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

run = Path(sys.argv[1])
entry = run.parent / "RUN4_20261113T094312Z"
previous = run.parent / "RUN3_20261113T085001Z"
manifest_path = entry / "MANIFEST.json"
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert digest(manifest_path) == "18d1a312da1e870746b4569658da8a98ffa46601af4dc9040be5d084eac7e299"
manifest = json.loads(manifest_path.read_text())


def verified(root, name, evidence):
    source = root / "outputs" / name
    value = digest(source)
    relpath = "outputs/" + name
    assert value == evidence[relpath], name
    return {"path": str(source), "sha256": value}, json.loads(source.read_text())


def status(value):
    return "PASS" if value else "FAIL"


preflight, obs = verified(entry, "S1P_OBS_PREFLIGHT.json", manifest["output_sha256"])
regression, r0 = verified(entry, "R0.json", manifest["output_sha256"])
e2e_path, e2e = verified(entry, "S1P_G_E2E.json", manifest["output_sha256"])
assert e2e["status"] == "PASS"
snap = run / "s2_out" / "S2P_G_SNAP.json"
assert snap.is_file()
assert r0["passed"] and len(obs["primary"]) == 6
out = {
    "question_id": "G1-MODEL-001",
    "spec_commit": manifest["spec_commit"],
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "R0": dict(regression, status=status(r0["passed"]), j_bit_identical=r0["j_bit_identical"]),
    "G-OBS-0": status(r0["passed"]),
    "G-OBS-1/2": dict(preflight, cases={c:obs["by_case"][c]["gates"] for c in obs["primary"]}),
    "G-E2E-prime": dict(e2e_path, status=e2e["status"], paths_per_model=e2e["paths_per_model"]),
    "G-SNAP": {"path": str(snap), "sha256": digest(snap), "assessment": "distribution reported"},
}
with (run / "s2_out" / "S1P_GATES.json").open("x", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False, allow_nan=False)
    f.write("\n")

