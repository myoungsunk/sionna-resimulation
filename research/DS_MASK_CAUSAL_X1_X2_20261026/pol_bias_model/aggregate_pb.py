"""Merge PB shards and apply the pre-registered decisions (PROTOCOL_PB.md)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "reflect_model"))
import common as C  # noqa: E402

METHODS = ["VAR", "GM03", "GM1Y20", "WIN05Y10", "WIN1Y5"]
N_MIN = 21          # of 28 conditions (75 %)


def main():
    files = sorted(C.OUT.glob("PB_SCORES_*_*.csv"))
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df.to_csv(C.OUT / "PB_SCORES.csv", index=False)
    key = ["case", "bias"]
    H = df.pivot_table(index=key, columns="arm", values="head_rmse"); X = df.pivot_table(index=key, columns="arm", values="xy_rmse_cm")
    Z = df.pivot_table(index=key, columns="arm", values="head_z_rms"); CV = df.pivot_table(index=key, columns="arm", values="xy_cov95")
    n = len(H); out = dict(conditions=int(n), shards=len(files), n_min=N_MIN, methods={})
    lines = [f"# PB results ({n} conditions)\n", "| method | bg | head < BB_ORIG | XY < BB_ORIG | head < own ORIG | worst head ratio vs BB_ORIG | median head ratio vs BB_ORIG | median gap closed to ORPOL | median head z | median XY cov95 | P1 | P2 | P3 |", "|" + "---|" * 13]
    for bg in ("MB", "BB"):
        for m in ["ORIG"] + METHODS:
            a = f"{bg}_{m}"
            if a not in H:
                continue
            hb = int((H[a] < H["BB_ORIG"]).sum()); xb = int((X[a] < X["BB_ORIG"]).sum()); ho = int((H[a] < H[f"{bg}_ORIG"]).sum())
            ratio = H[a] / H["BB_ORIG"]; gap = (H[f"{bg}_ORIG"] - H[a]) / (H[f"{bg}_ORIG"] - H[f"{bg}_ORPOL"])
            p1 = hb >= N_MIN and xb >= N_MIN; p2 = float(ratio.max()) <= 1.10; p3 = float(Z[a].median()) <= 1.5 and float(CV[a].median()) >= 0.80
            out["methods"][a] = dict(head_better_than_BB_ORIG=hb, xy_better_than_BB_ORIG=xb, head_better_than_own_ORIG=ho, worst_ratio=float(ratio.max()),
                                     median_ratio=float(ratio.median()), median_gap_closed=float(gap.median()), median_head_z=float(Z[a].median()),
                                     median_xy_cov95=float(CV[a].median()), P1=p1, P2=p2, P3=p3)
            lines.append(f"| {m} | {bg} | {hb}/{n} | {xb}/{n} | {ho}/{n} | {ratio.max():.2f} | {ratio.median():.2f} | {gap.median():.2f} | {Z[a].median():.2f} | {CV[a].median():.2f} | {p1} | {p2} | {p3} |")
    # by bias level and by mount, MB methods
    lines.append("\n## median heading ratio vs BB_ORIG by gyro-bias level (MB background)\n")
    tab = (H[[f"MB_{m}" for m in ["ORIG"] + METHODS + ["ORPOL"]]].div(H["BB_ORIG"], axis=0)).groupby(level="bias").median().round(3)
    lines.append(tab.to_string())
    mount = df.groupby(key).mount.first()
    tab2 = (H[[f"MB_{m}" for m in ["ORIG"] + METHODS + ["ORPOL"]]].div(H["BB_ORIG"], axis=0)).groupby(mount.values).median().round(3)
    lines.append("\n## same, by mount\n"); lines.append(tab2.to_string())
    lines.append("\n## heading RMSE [deg] per condition\n"); lines.append(H.round(3).to_string())
    (C.OUT / "PB_SUMMARY.md").write_text("\n".join(lines) + "\n")
    (C.OUT / "PB_DECISIONS.json").write_text(json.dumps(out, indent=1))
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    main()
