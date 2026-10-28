"""Merge PB shards and apply the pre-registered decisions (PROTOCOL_PB.md)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "reflect_model"))
import common as C  # noqa: E402

METHODS = ["VAR", "GM03", "GM1Y20", "WIN05Y10", "WIN1Y5", "VARM", "VARM_LORO", "VAR2D", "VAR2D_LORO"]


def main():
    files = sorted(C.OUT.glob("PB_SCORES_*_*.csv"))
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df.to_csv(C.OUT / "PB_SCORES.csv", index=False)
    key = ["case", "bias"]
    ORIG7 = {"R2_aA_m0", "R2_aB_m0", "R2_aA_m45", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"}
    H = df.pivot_table(index=key, columns="arm", values="head_rmse"); X = df.pivot_table(index=key, columns="arm", values="xy_rmse_cm")
    Z = df.pivot_table(index=key, columns="arm", values="head_z_rms"); CV = df.pivot_table(index=key, columns="arm", values="xy_cov95")
    cases = H.index.get_level_values("case")
    subsets = {"PREREG_original7": cases.isin(ORIG7), "mount0": cases.str.endswith("_m0"), "mount45": cases.str.endswith("_m45"), "all": np.ones(len(H), bool)}
    out = dict(shards=len(files), subsets={}); lines = []
    for sname, sel in subsets.items():
        h, x, z, cv = H[sel], X[sel], Z[sel], CV[sel]; n = len(h)
        if n == 0:
            continue
        nmin = int(np.ceil(0.75 * n)); out["subsets"][sname] = dict(conditions=int(n), n_min=nmin, methods={})
        lines += [f"\n# {sname}: {n} conditions (P1 needs {nmin})\n", "| method | bg | head < BB_ORIG | XY < BB_ORIG | head < own ORIG | worst head ratio vs BB_ORIG | median head ratio vs BB_ORIG | median gap closed to ORPOL | median head z | median XY cov95 | P1 | P2 | P3 |", "|" + "---|" * 13]
        for bg in ("MB", "BB"):
            for m in ["ORIG"] + METHODS:
                a = f"{bg}_{m}"
                if a not in h:
                    continue
                hb = int((h[a] < h["BB_ORIG"]).sum()); xb = int((x[a] < x["BB_ORIG"]).sum()); ho = int((h[a] < h[f"{bg}_ORIG"]).sum())
                ratio = h[a] / h["BB_ORIG"]; gap = (h[f"{bg}_ORIG"] - h[a]) / (h[f"{bg}_ORIG"] - h[f"{bg}_ORPOL"])
                p1 = hb >= nmin and xb >= nmin; p2 = float(ratio.max()) <= 1.10; p3 = float(z[a].median()) <= 1.5 and float(cv[a].median()) >= 0.80
                out["subsets"][sname]["methods"][a] = dict(head_better_than_BB_ORIG=hb, xy_better_than_BB_ORIG=xb, head_better_than_own_ORIG=ho, worst_ratio=float(ratio.max()),
                                                          median_ratio=float(ratio.median()), median_gap_closed=float(gap.median()), median_head_z=float(z[a].median()),
                                                          median_xy_cov95=float(cv[a].median()), P1=p1, P2=p2, P3=p3)
                lines.append(f"| {m} | {bg} | {hb}/{n} | {xb}/{n} | {ho}/{n} | {ratio.max():.2f} | {ratio.median():.2f} | {gap.median():.2f} | {z[a].median():.2f} | {cv[a].median():.2f} | {p1} | {p2} | {p3} |")
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
    print("\n".join(lines))


if __name__ == "__main__":
    main()
