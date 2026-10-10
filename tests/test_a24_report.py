import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_spec = importlib.util.spec_from_file_location("a24_report_under_test", Path(__file__).resolve().parents[1] / "scripts" / "drive_sim" / "a24_report.py")
M = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(M)


def frame(offset, drifts, seeds=6):
    rows = []
    for arm in ("A0_real_real", "M0_Rmatched_Rmatched"):
        for d in drifts:
            for s in range(seeds):
                rows.append(dict(arm=arm, seed=s, drift=d, error="", baseline="range_s_P0", filter="ekf", nees_mean=3.0 + s * 0.1 + d + offset, nees_cov95=0.9, heading_cov95=0.9, nees_tail_lo=0.02, nees_tail_hi=0.03,
                                 heading_rmse_common_deg=1.0, pos_rmse_common_m=0.2, s_reject_frac_eval=0.0, r_reject_frac_eval=0.0, nis_s_eval_acc=1.0, nis_r_eval_acc=1.0))
    return pd.DataFrame(rows)


def test_contrast_pairs_on_common_drifts_and_seeds():
    f0, f2 = frame(0.0, (0, 1, 2)), frame(2.0, (0,))
    out = M.build(M.load_rows([_write(f0, "f0")], "F0"), {"F2": M.load_rows([_write(f2, "f2")], "F2")}, [0])
    c = out["contrasts"]["F2-F0"]["A0_real_real"]["nees_mean"]
    assert abs(c["mean"] - 2.0) < 1e-12 and c["n"] == 6                  # F0 averaged over drift 0 only, not over 0-2
    assert "within_band" in out["arms"]["F2"]["A0_real_real"]


def _write(df, name, _d=[]):
    import tempfile
    d = Path(tempfile.mkdtemp())
    p = d / f"{name}.csv"
    df.to_csv(p, index=False)
    return p


def test_verdicts_follow_the_approved_limits():
    f0, f2 = frame(0.0, (0,)), frame(0.0, (0,))
    f2["nees_mean"] = f2["nees_mean"] - 0.0
    out = M.build(M.load_rows([_write(f0, "g0")], "F0"), {"F2": M.load_rows([_write(f2, "g2")], "F2")}, [0])
    v = M.verdicts(out, "F2")
    assert v["P4_no_harm"]["M0_Rmatched_Rmatched"] is True and v["P3_not_worse_than_F0"]["A0_real_real"] is True
    f2b = f2.copy()
    f2b["nees_mean"] += 2.0
    f2b["heading_rmse_common_deg"] += 0.5
    out2 = M.build(M.load_rows([_write(f0, "h0")], "F0"), {"F2": M.load_rows([_write(f2b, "h2")], "F2")}, [0])
    v2 = M.verdicts(out2, "F2")
    assert v2["P4_no_harm"]["M0_Rmatched_Rmatched"] is False and v2["P3_not_worse_than_F0"]["A0_real_real"] is False
