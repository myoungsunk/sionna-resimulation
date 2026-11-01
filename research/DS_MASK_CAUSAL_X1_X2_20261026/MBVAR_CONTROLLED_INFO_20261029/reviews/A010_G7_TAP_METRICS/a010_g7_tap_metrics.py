"""A010 G7 correction (audit ef0b707c): separate four tap metrics that the RFRES 'fp_switch' (= idxF != idxL) conflated in wording.

  FULL_LOS_TAP_DISAGREE        fraction of packets where the Full-RT and LoS-only-RT first-path index differ at the SAME pose
  TEMPORAL_TAP_CHANGE_FULL     fraction of consecutive packet pairs whose Full-RT first-path index changes
  TEMPORAL_TAP_CHANGE_LOS      same for the LoS-only RT channel
  TIME_CHANGE_OF_DISAGREEMENT  fraction of consecutive pairs where the disagreement indicator changes
Reads results/P2_RFRES_run_40992695655/RFRES_ROWS.csv only (time-ordered drive-trace packets per case). Append-only output.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

src = Path("results/P2_RFRES_run_40992695655/RFRES_ROWS.csv"); out = Path("reviews/A010_G7_TAP_METRICS")
R = pd.read_csv(src); rows = []
for case, d in R.groupby("case", sort=False):
    d = d.sort_values("t"); F, L = d.idxF.to_numpy(), d.idxL.to_numpy(); dis = F != L
    rows.append(dict(case=case, packets=len(d), FULL_LOS_TAP_DISAGREE=float(dis.mean()),
                     TEMPORAL_TAP_CHANGE_FULL=float(np.mean(F[1:] != F[:-1])), TEMPORAL_TAP_CHANGE_LOS=float(np.mean(L[1:] != L[:-1])),
                     TIME_CHANGE_OF_DISAGREEMENT=float(np.mean(dis[1:] != dis[:-1])),
                     median_abs_index_gap_when_disagree=float(np.median(np.abs(F[dis] - L[dis]))) if dis.any() else 0.0,
                     frac_full_earlier_than_los_when_disagree=float(np.mean(F[dis] < L[dis])) if dis.any() else None,
                     median_packet_dt_s=float(np.median(np.diff(d.t)))))
T = pd.DataFrame(rows); T.to_csv(out / "A010_G7_TAP_METRICS.csv", index=False, float_format="%.6g")
(out / "A010_G7_TAP_METRICS.json").write_text(json.dumps(dict(source=str(src), source_sha256=__import__("hashlib").sha256(src.read_bytes()).hexdigest(),
     note="RFRES FP_SWITCH flag (threshold 0.05) was computed on FULL_LOS_TAP_DISAGREE; it is NOT a temporal switching rate. Prior RFRES outputs unchanged.",
     cases=rows), indent=1))
print(T.round(3).to_string(index=False))
