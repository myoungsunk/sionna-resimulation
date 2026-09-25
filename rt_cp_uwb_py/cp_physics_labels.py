"""Outcome-blind physics-label generators for CP-PH4."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def build_direct_purity_labels(path_rows: pd.DataFrame, *, early_window_s: float) -> pd.DataFrame:
    """Compute direct-path power share within a pre-frozen early window.

    A row is label-valid only when at least one direct path is present and the
    direct delay/power and early-window total power are finite and positive.
    The function uses path metadata only and must never be used as a runtime
    feature generator.
    """

    required = {"case_id", "is_los", "path_delay_s", "power"}
    missing = sorted(required - set(path_rows.columns))
    if missing:
        raise ValueError(f"direct-purity input missing columns: {missing}")
    if early_window_s < 0.0:
        raise ValueError("early_window_s must be non-negative")
    records: list[dict[str, Any]] = []
    for case_id, group in path_rows.groupby("case_id", sort=True):
        work = group.copy()
        work["path_delay_s"] = pd.to_numeric(work["path_delay_s"], errors="coerce")
        work["power"] = pd.to_numeric(work["power"], errors="coerce")
        direct_mask = work["is_los"].map(lambda value: str(value).strip().lower() in {"true", "1", "yes"})
        direct = work.loc[direct_mask & np.isfinite(work["path_delay_s"]) & np.isfinite(work["power"])]
        if direct.empty:
            records.append({"case_id": int(case_id), "D_label": np.nan, "d_label_mask": False, "direct_delay_s": np.nan, "direct_power": np.nan, "early_window_power": np.nan, "reason": "NO_DIRECT_PATH"})
            continue
        direct_row = direct.sort_values(["path_delay_s", "power"], ascending=[True, False]).iloc[0]
        direct_delay = float(direct_row["path_delay_s"])
        direct_power = float(direct_row["power"])
        early = work.loc[
            np.isfinite(work["path_delay_s"])
            & np.isfinite(work["power"])
            & (work["path_delay_s"] >= direct_delay)
            & (work["path_delay_s"] <= direct_delay + early_window_s),
            "power",
        ]
        early_power = float(early.sum())
        valid = bool(direct_power >= 0.0 and early_power > 0.0)
        records.append(
            {
                "case_id": int(case_id),
                "D_label": float(np.clip(direct_power / early_power, 0.0, 1.0)) if valid else np.nan,
                "d_label_mask": valid,
                "direct_delay_s": direct_delay,
                "direct_power": direct_power,
                "early_window_power": early_power,
                "reason": "VALID" if valid else "NONPOSITIVE_EARLY_POWER",
            }
        )
    return pd.DataFrame.from_records(records).sort_values("case_id").reset_index(drop=True)
