"""Page: first-path ranging error at the 10 LoS-blocked office positions (from OFFICE_RANGING.json, after scripts/office_ranging_error.py).
    python scripts/office_render_ranging.py
"""
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RANG = ROOT / "results" / "OFFICE_RANGING_20261008"
ANA = ROOT / "results" / "OFFICE_ANALYSIS_20261008"


def main():
    r = json.loads((RANG / "OFFICE_RANGING.json").read_text())
    loss = {(p["x"], p["y"]): p for p in json.loads((ANA / "OFFICE_BLOCKED.json").read_text())["positions"]}
    yaw = json.loads((ANA / "OFFICE_ANALYSIS.json").read_text())["yaw_deg"]
    clear = [p for p in r["positions"] if p["los_clear"]]
    blk = [p for p in r["positions"] if not p["los_clear"]]
    for p in blk:
        p["loss_db"] = loss[(p["x"], p["y"])]["loss_db"]
    env = dict(lo=np.min([p["err_cal_m"] for p in clear], 0).round(3).tolist(), hi=np.max([p["err_cal_m"] for p in clear], 0).round(3).tolist())
    keep = ("x", "y", "theta_deg", "range_m", "blockers", "loss_db", "err_m", "err_cal_m", "mean", "mean_cal", "std", "err_single")
    data = dict(yaw_deg=yaw, offset_m=r["los_clear_median_offset_m"], tap_m=r["tap_spacing_m"], summary=r["summary"], clear_env=env, positions=[{k: p[k] for k in keep} for p in blk])
    page = (ROOT / "scripts" / "office_ranging_template.html").read_text(encoding="utf8").replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    (RANG / "office_ranging.html").write_text(page, encoding="utf8")
    for p in blk:
        print((p["x"], p["y"]), p["loss_db"], round(p["mean_cal"], 2), round(p["std"], 2), p["blockers"])
    print(np.corrcoef([p["loss_db"] for p in blk], [p["mean_cal"] for p in blk])[0, 1])


if __name__ == "__main__":
    main()
