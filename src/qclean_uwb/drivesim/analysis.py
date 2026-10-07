"""S6 statistics for the pre-registered hypotheses H1-H4 (see results/DRIVE_SIM_20261007/S0/PREREG.json, "test")."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

ALPHA = 0.01
MIN_REL_IMPROVEMENT = 0.10
BOOT = 10_000
KEYS = ["lateral", "mount_deg", "drift", "snr_db", "seed"]


def holm(pvalues) -> np.ndarray:
    """Holm step-down adjusted p-values."""
    p = np.asarray(pvalues, float)
    order = np.argsort(p)
    adj = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * p[i])
        adj[i] = min(running, 1.0)
    return adj


def bootstrap_ci(x, stat=np.median, n=BOOT, level=0.95, seed=0):
    x = np.asarray(x, float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(x), size=(n, len(x)))
    vals = stat(x[idx], axis=1)
    lo, hi = np.percentile(vals, [(1 - level) / 2 * 100, (1 + level) / 2 * 100])
    return float(lo), float(hi)


def paired(df: pd.DataFrame, a: str, b: str, metric: str, by: list[str], merge_on: list[str] | None = None) -> pd.DataFrame:
    """Per condition: paired comparison of baseline/filter ``a`` (reference) against ``b`` (candidate) on ``metric`` (lower is better).

    ``rel_improvement`` = (metric_a - metric_b) / metric_a per seed pair; improvement rule: Holm-significant AND median >= 10 %.
    """
    key = merge_on or KEYS
    da = df[df.baseline == a].set_index(key)[metric]
    db = df[df.baseline == b].set_index(key)[metric]
    both = pd.concat([da.rename("a"), db.rename("b")], axis=1, join="inner").dropna().reset_index()
    rows = []
    for cond, g in both.groupby(by):
        cond = cond if isinstance(cond, tuple) else (cond,)
        d = g.a.to_numpy() - g.b.to_numpy()
        rel = d / np.maximum(g.a.to_numpy(), 1e-12)
        try:
            p = wilcoxon(d, alternative="two-sided").pvalue if np.any(d != 0) else 1.0
        except ValueError:
            p = 1.0
        lo, hi = bootstrap_ci(d)
        rows.append(dict(zip(by, cond), n=len(g), median_a=float(np.median(g.a)), median_b=float(np.median(g.b)), median_diff=float(np.median(d)),
                         ci_lo=lo, ci_hi=hi, median_rel_improvement=float(np.median(rel)), p=float(p)))
    cols = by + ["n", "median_a", "median_b", "median_diff", "ci_lo", "ci_hi", "median_rel_improvement", "p"]
    out = pd.DataFrame(rows, columns=cols)
    out["p_holm"] = holm(out.p.to_numpy()) if len(out) else np.array([], float)
    out["significant"] = out.p_holm < ALPHA
    out["improved"] = out.significant & (out.median_rel_improvement >= MIN_REL_IMPROVEMENT)
    out["worse"] = out.significant & (out.median_rel_improvement <= -MIN_REL_IMPROVEMENT)
    return out


def h1(df, metric="heading_rmse_deg"):
    cond = ["lateral", "mount_deg", "drift", "snr_db"]
    return dict(vs_odom_imu=paired(df, "odom_imu", "range_s_P0", metric, cond), vs_gyro_only=paired(df, "gyro_only", "range_s_P0", metric, cond))


def h2(df, metric="heading_rmse_deg"):
    return paired(df, "inverse_heading_P0", "range_s_P0", metric, ["lateral", "mount_deg", "drift", "snr_db"])


def h3(df, metric="heading_rmse_deg", baseline="range_s_P0"):
    """Mount 45 deg vs mount 0 deg (candidate = 45).  ``median_rel_improvement`` > 0 means 45 deg is better (H3), < 0 means 0 deg is better (H3_alt)."""
    sub = df[df.baseline == baseline]
    a = sub[sub.mount_deg == 0.0].set_index(["lateral", "drift", "snr_db", "seed"])[metric]
    b = sub[sub.mount_deg == 45.0].set_index(["lateral", "drift", "snr_db", "seed"])[metric]
    both = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna().reset_index()
    tmp = pd.concat([both.assign(baseline="m0", value=both.a)[["lateral", "drift", "snr_db", "seed", "baseline", "value"]],
                     both.assign(baseline="m45", value=both.b)[["lateral", "drift", "snr_db", "seed", "baseline", "value"]]])
    tmp = tmp.rename(columns={"value": metric}).assign(mount_deg=0.0)
    return paired(tmp, "m0", "m45", metric, ["lateral", "drift", "snr_db"], merge_on=["lateral", "mount_deg", "drift", "snr_db", "seed"])


def h4(df, x_percent=10.0, column="wrong_branch_frac"):
    """Largest probe period whose seed-mean wrong-branch fraction has a bootstrap 95 % upper bound <= X % (per condition)."""
    names = {"range_s_P0": None, "range_s_P1_T10": 10, "range_s_P1_T20": 20, "range_s_P1_T60": 60}
    rows = []
    for cond, g in df[df.baseline.isin(names)].groupby(["lateral", "mount_deg", "drift", "snr_db"]):
        per_T = {}
        for b, T in names.items():
            v = g[g.baseline == b][column].to_numpy() * 100.0
            if len(v):
                per_T[T] = bootstrap_ci(v, stat=np.mean, level=0.9)[1]          # one-sided 95 % upper bound = upper end of the 90 % interval
        ok = [T for T in (10, 20, 60) if T in per_T and per_T[T] <= x_percent]
        rows.append(dict(zip(["lateral", "mount_deg", "drift", "snr_db"], cond), **{f"ub_T{k}": v for k, v in per_T.items() if k},
                         ub_P0=per_T.get(None), largest_T_ok=max(ok) if ok else None))
    return pd.DataFrame(rows)
