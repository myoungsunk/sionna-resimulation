"""Write or check the sensor-v2 freeze manifest (sha256 of raw bytes and of the line-ending-normalised content)."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
V2_VERBATIM = [
    "src/qclean_uwb/drivesim/filter_v2.py", "src/qclean_uwb/drivesim/sensor_v2.py", "src/qclean_uwb/drivesim/evaluation_v2.py",
    "configs/sensor_v2/neutral.json", "configs/sensor_v2/assumed_common_scale.json", "configs/sensor_v2/assumed_bias_rw.json", "configs/sensor_v2/filter_fixed_bias.json",
    "scripts/drive_sim/run_sensor_v2.py", "scripts/drive_sim/evaluate_sensor_v2_rf.py", "scripts/drive_sim/ablate_sensor_v2_correlation.py",
    "scripts/drive_sim/validate_sensor_v2_stage2.py", "scripts/drive_sim/analyze_sensor_v2_stage2.py",
    "tests/test_sensor_v2.py", "tests/test_sensor_v2_covariance_guard_stage2.py", "tests/test_sensor_v2_input_contract.py",
    "results/SENSOR_V2_20261008/PREREG_V2.md", "results/SENSOR_V2_20261008/MODEL_CONTRACT.md", "results/SENSOR_V2_20261008/CHANGE_MANIFEST.json",
    "results/SENSOR_V2_20261008/PREREG_SNAPSHOTS.json", "results/SENSOR_V2_20261008/SENSOR_V2_REAUDIT_KO.md",
]
V2_MERGED = ["src/qclean_uwb/drivesim/filters.py", "src/qclean_uwb/drivesim/experiment.py", "scripts/drive_sim/run_experiments.py", "scripts/drive_sim/run_route_experiments.py"]
MANIFEST = ROOT / "results/DRIVE_SIM_20261007/V2_FREEZE/V2_FREEZE.json"


def digests(path: Path) -> dict:
    b = path.read_bytes()
    return dict(sha256=hashlib.sha256(b).hexdigest(), sha256_lf=hashlib.sha256(b.replace(b"\r\n", b"\n")).hexdigest(), bytes=len(b))


def current() -> dict:
    return dict(verbatim={f: digests(ROOT / f) for f in V2_VERBATIM}, merged_hooks={f: digests(ROOT / f) for f in V2_MERGED})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["write", "check"])
    a = ap.parse_args()
    cur = current()
    if a.cmd == "write":
        if MANIFEST.exists():
            raise SystemExit("refusing to overwrite an existing freeze manifest")
        MANIFEST.write_text(json.dumps(dict(cur, note="verbatim = byte-identical copies of the integrated-branch snapshot; merged_hooks = current repo files that carry the v2 hooks (legacy path bit-identical to base 2337c33, tests/test_sensor_v2_legacy_unchanged_current.py)"), indent=1))
        print("written", MANIFEST)
        return 0
    ref = json.loads(MANIFEST.read_text())
    bad = []
    for part in ("verbatim", "merged_hooks"):
        for f, d in ref[part].items():
            now = cur[part].get(f)
            if now is None or now["sha256_lf"] != d["sha256_lf"]:
                bad.append((part, f))
    print("freeze check:", "OK" if not bad else f"MISMATCH {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
