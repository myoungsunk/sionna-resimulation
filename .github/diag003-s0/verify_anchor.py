"""Compare Anchor B replay report and JOINT4 frames to archived original."""
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np


out = Path(sys.argv[1])
case = sys.argv[2]
evidence = Path(sys.argv[3])
expected = {"R4_aB_m0": ["1.323", "40.0"], "R5_aB_m0": ["2.541", "22.1"]}[case]
stem = case + "_full_B0"
member = stem + "_TRACE.npz"
comparison = {}
with zipfile.ZipFile(evidence) as reference:
    original_b = reference.read(member)
    replay_b = (out / member).read_bytes()
    with np.load(io.BytesIO(original_b), allow_pickle=False) as old:
        with np.load(io.BytesIO(replay_b), allow_pickle=False) as new:
            j = old["arms"].tolist().index("JOINT4")
            assert j == new["arms"].tolist().index("JOINT4")
            for key in ("t_s", "pose_id", "truth_scoring_only", "state", "cov", "accepted", "nis", "mu", "R"):
                a, b = old[key], new[key]
                if key not in ("t_s", "pose_id", "truth_scoring_only"):
                    a, b = a[:, j], b[:, j]
                if a.shape != b.shape or a.dtype != b.dtype:
                    raise ValueError(f"Cannot compare {case} {key}: shape or dtype differs")
                delta = np.abs(a.astype(float) - b.astype(float))
                changed = a != b
                comparison[key] = {
                    "shape": list(a.shape),
                    "byte_equal": a.tobytes() == b.tobytes(),
                    "different_values": int(np.count_nonzero(changed)),
                    "different_frames": int(np.count_nonzero(changed.reshape(len(a), -1).any(axis=1))),
                    "max_abs": float(np.max(delta)),
                }
with (out / (stem+"_SCORES.csv")).open(newline="") as f:
    row, = [r for r in csv.DictReader(f) if r["model"] == "JOINT4" and r["mode"] == "NATURAL_RECURSIVE"]
got = [f"{float(row['heading_rmse_deg']):.3f}", f"{100 * float(row['heading95']):.1f}"]
ok = got == expected
record = {"classification":"DIAGNOSTIC_ONLY", "case":case, "status":"REPORT_LEVEL_PASS" if ok else "FAIL",
          "verdict_basis":"published decimal digits", "original_frame_comparison":"RECORDED",
          "reported_rmse_deg_coverage_pct":got,"expected":expected,"reference_frames_sha256":hashlib.sha256(original_b).hexdigest(),
          "replay_frames_sha256":hashlib.sha256(replay_b).hexdigest(),"frame_comparison":comparison}
(out / (case + "_ANCHOR_S0.json")).write_text(json.dumps(record,indent=2)+"\n", encoding="utf-8")
print(json.dumps(record,indent=2))
sys.exit(not ok)
