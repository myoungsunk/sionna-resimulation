"""Build the interactive results page from corridor_analyze.py outputs."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sweep = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "CORRIDOR_SWEEP_20261006"
data = json.loads((sweep / "fp_ratio_series.json").read_text())
data["validation"] = json.loads((sweep / "VALIDATION.json").read_text())
data["angle"] = json.loads((sweep / "ANGLE_MATCH.json").read_text())
data["corr"] = json.loads((sweep / "ARTIFACT_CORRECTION.json").read_text())
data["validation_fp"] = json.loads((sweep / "FP_VALIDATION.json").read_text())
page = (ROOT / "scripts" / "corridor_results_page_template.html").read_text(encoding="utf8").replace(
    "__RESULTS__", json.dumps(data, ensure_ascii=False, allow_nan=False))
out = sweep / "corridor_yaw_sweep.html"
out.write_text(page, encoding="utf8")
print(out, round(out.stat().st_size / 1e3), "kB")
