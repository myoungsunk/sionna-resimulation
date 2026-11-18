"""Build the reflection-fit page from REFLECTION_FIT.json (lede and caveats come from LEDE.json if present)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "results" / "CORRIDOR_SCAN_20261006" / "REFLECTION_FIT.json"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.parent / "corridor_reflection_fit.html"
data = json.loads(src.read_text())
data["yaw_deg"] = [float(a) for a in range(0, 181, 10)]
text = json.loads((src.parent / "LEDE.json").read_text()) if (src.parent / "LEDE.json").exists() else dict(lede="(draft)", caveats=[])
data.update(text)
page = (ROOT / "scripts" / "corridor_reflection_page_template.html").read_text(encoding="utf8").replace(
    "__RESULTS__", json.dumps(data, ensure_ascii=False, allow_nan=False))
out.write_text(page, encoding="utf8")
print(out, round(out.stat().st_size / 1e3), "kB")
