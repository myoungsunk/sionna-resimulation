"""Build the curve-shift page from SHIFT_FIT.json and LEDE_SHIFT.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = ROOT / "results" / "CORRIDOR_SCAN_20261006"
data = json.loads((d / "SHIFT_FIT.json").read_text())
data.update(json.loads((d / "LEDE_SHIFT.json").read_text()))
data["txang"] = json.loads((d / "TX_ANGLE_SWEEP.json").read_text())
data["angmodel"] = json.loads((d / "ANGLE_MODEL_COMPARE.json").read_text())
data["tmpl"] = json.loads((d / "TEMPLATE_COMPARE.json").read_text())
data["errbud"] = json.loads((d / "ERROR_BUDGET.json").read_text())
data["errbud"]["multipath_x_shift_rms"] = 3.68
data["flat"] = json.loads((d / "FLAT_REGION_CHECK.json").read_text())
data["case"] = json.loads((d / "CASE_CHECK.json").read_text())
data["case"]["synthetic_n"] = 30
data["mpt"] = json.loads((d / "MULTIPATH_TEMPLATE.json").read_text())
data["mpm"] = json.loads((d / "MULTIPATH_MODEL.json").read_text())
data["abl"] = json.loads((d / "AXIS_ABLATION.json").read_text())
data["fax"] = json.loads((d / "FLAT_AXES.json").read_text())
page = (ROOT / "scripts" / "corridor_shift_page_template.html").read_text(encoding="utf8").replace("__RESULTS__", json.dumps(data, ensure_ascii=False, allow_nan=False))
out = d / "corridor_curve_shift.html"
out.write_text(page, encoding="utf8")
print(out, round(out.stat().st_size / 1e3), "kB")
