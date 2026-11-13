"""Record v3.2 executed phases, source identity and sealed summary artifacts."""
from argparse import ArgumentParser
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy
import scipy

def sha(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()

def read(path):
    return json.loads(path.read_bytes())

def main():
    parser = ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    root = args.directory.resolve()
    out = root / "outputs"
    code = root / "code"
    receipt = read(code / "INPUTS_CHECK_1ce68f3.json")
    pref = read(out / "S1P_OBS_PREFLIGHT.json")
    r0 = read(out / "R0.json")
    def status(name):
        p = out / f"EXIT_{name}.txt"
        if not p.exists():
            return None
        return dict(exit_code=int(p.read_text()),
                    started_utc=(out / f"START_{name}_UTC.txt").read_text().strip(),
                    finished_utc=(out / f"FINISH_{name}_UTC.txt").read_text().strip())
    stages = {n:status(n) for n in ("PREFLIGHT", "GINT", "GINT_REFINED", "PRIMARY")}
    inputs = {k:v["sha256"] for k,v in receipt["inputs"].items()}
    files = {p.relative_to(root).as_posix():sha(p) for p in sorted(out.glob("*"))
             if p.is_file() and p.name != "MANIFEST.json"}
    artifacts = {p.name:sha(p) for p in sorted(code.iterdir()) if p.is_file()}
    raw_gates = {}
    for phase in ("initial","refined"):
        for p in sorted(out.glob(f"S1P_G_INT*{phase}*.json")):
            raw_gates[p.name] = files[p.relative_to(root).as_posix()]
    info = dict(question_id="G1-MODEL-001", role="IMPLEMENTER",
                repository="myoungsunk/sionna-resimulation",
                spec_commit="ebd55913519e852364a07fb33ec3188c9cbe7bca",
                spec_git_blob="3fa98586e743dd19398b41598992f2eac18a850d",
                local_code_provenance="Source hashes; execution additions are uncommitted.",
                research_governance_sha256=dict(
                    common="a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
                    implementer="2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da"),
                captured_utc=datetime.now(timezone.utc).isoformat(), stage3="HELD",
                input_sha256=inputs, code_sha256=artifacts, output_sha256=files,
                bank_sha256=dict(LP_plus45_bank="b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
                                 LP_minus45_bank="39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9"),
                stages=stages, checks=dict(r0=r0["passed"], eligible_cases=pref["primary"],
                                           sigma_axis=pref["sigma_axis"], gint_artifacts=raw_gates),
                environment=dict(python=sys.version, numpy=numpy.__version__, scipy=scipy.__version__,
                                 platform=platform.platform(),
                                 image="sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f"))
    (out / "MANIFEST.json").write_text(json.dumps(info, indent=2, allow_nan=False)+"\n", encoding="utf-8")

if __name__ == "__main__":
    main()
