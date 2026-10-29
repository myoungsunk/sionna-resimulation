"""H-OC test: is the state over-confidence caused by fusing temporally correlated RF residuals as white?

Fixed BASE mask (as published).  For MB_ORIG and MB_VAR, B0, mount 0:
  DEC_m  : use every m-th accepted packet (phases averaged)  -> fewer, less correlated updates
  RSC_m  : use all packets, R x m                              -> same nominal information as DEC_m, no decorrelation
Prediction under H-OC: as m -> N/neff, heading z-RMS and dh^2/HPH -> ~1 for DEC_m; RSC_m differs from DEC_m only if
averaging of correlated noise matters.  Evidence, not a tuned filter.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diag_mbvar as DG  # noqa: E402

MS = (1, 2, 4, 8, 16)


def one(D, arm, model):
    bg, mode = arm.split("_")[0], arm.split("_")[1].lower()
    X, PX, L = DG.run(D, bg, mode, "fixed", model=model)
    s = DG.scores(D, X, PX)
    u = L["used"] & (D["t"] >= 30 - 1e-9)
    dh = D["hg"] - L["hx"]
    s["dh2_HPH_s"] = float(np.mean(dh[u, 1] ** 2) / np.mean(L["HPH"][u, 1, 1]))
    s["dh2_HPH_r"] = float(np.mean(dh[u, 0] ** 2) / np.mean(L["HPH"][u, 0, 0]))
    s["n_used"] = int(L["used"].sum())
    return s


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    out = Path(a.out); model = DG.C.base_model(); rows = []
    for c in DG.CASES:
        D0 = DG.load(c, "B0", model)
        idx = np.flatnonzero(D0["acc"])
        for arm in ("MB_ORIG", "MB_VAR"):
            for m in MS:
                phases = [0] if m == 1 else [0, m // 2]
                for ph in phases:
                    D = dict(D0); keep = np.zeros_like(D0["acc"]); keep[idx[ph::m]] = True; D["acc"] = keep
                    rows.append(dict(case=c, arm=arm, kind="DEC", m=m, phase=ph, **one(D, arm, model)))
                if m > 1:
                    D = dict(D0); D["R"] = D0["R"] * m
                    rows.append(dict(case=c, arm=arm, kind="RSC", m=m, phase=0, **one(D, arm, model)))
            print(c, arm, flush=True)
    pd.DataFrame(rows).to_csv(out / "D3b_OVERCOUNT_TEST.csv", index=False, float_format="%.6g")


if __name__ == "__main__":
    main()
