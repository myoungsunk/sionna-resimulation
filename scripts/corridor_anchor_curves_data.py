"""Collect the anchor-1 / anchor-2 yaw curves for the curve page.   python scripts/corridor_anchor_curves_data.py"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
import corridor_shift_fit as sf  # noqa: E402
import corridor_template_compare as tc  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

OUT = ROOT / "results/CORRIDOR_ANCHOR2_20261007"


def main():
    plan = json.loads((ROOT / "results/CORRIDOR_ANCHOR_PLAN_20261007/SCAN_PLAN.json").read_text())
    cmp_ = {(r["x"], r["tx"]): r for r in json.loads((OUT / "ANCHOR_COMPARE.json").read_text())["rows"]}
    s1 = {}
    for f in ("results/CORRIDOR_SCAN_20261006/SHIFT_FIT.json", "results/CORRIDOR_SCAN2_20261007/SHIFT_FIT_SCAN2.json"):
        for p in json.loads((ROOT / f).read_text())["positions"]:
            if p["y"] == 0.0:
                s1[p["x"]] = p
    s2 = {p["x"]: p for p in json.loads((OUT / "SHIFT_FIT_ANCHOR2.json").read_text())["positions"]}
    setup2, banks = CorridorSetup(anchor_y_m=-0.4), sf.Banks()
    meta = {r["x"]: r for r in plan["positions"] if r["anchor"] == "A2"}
    r4 = lambda a: [round(float(v), 4) for v in a]
    recs = []
    for x in sorted(s2):
        rec = dict(x=x, theta=meta[x]["theta_deg"], phi=meta[x]["phi_deg"], range_m=meta[x]["range_m"], tx={})
        for tn in sf.TX:
            dense, _ = tc.model_curve(banks, setup2, x, -0.4, tn)
            c = cmp_[(x, tn)]
            rec["tx"][tn] = dict(a1=r4(np.abs(s1[x]["tx"][tn]["s_full"])), a2=r4(np.abs(s2[x]["tx"][tn]["s_full"])),
                                 ideal=r4(np.abs(np.cos(2 * np.radians(sf.YAWS)))), model=r4(np.abs(dense)[::10]),
                                 rms_diff=round(c["rms_diff_abs"], 4), yaw_rmse={k: round(v, 2) for k, v in c["yaw_rmse"].items()})
        recs.append(rec)
    recs.sort(key=lambda r: (r["theta"], r["x"]))
    (OUT / "ANCHOR_CURVES.json").write_text(json.dumps(dict(yaw_deg=sf.YAWS.tolist(), model_yaw_deg=np.arange(0, 181, 1.0).tolist(), records=recs), separators=(",", ":")))
    print(len(recs), "positions", (OUT / "ANCHOR_CURVES.json").stat().st_size // 1000, "kB")


if __name__ == "__main__":
    main()
