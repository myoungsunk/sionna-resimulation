from __future__ import annotations

import numpy as np
import pandas as pd


QCLEAN_CLAIM_BOUNDARY = "q_clean is clean-session/session-quality confidence, not range-error confidence."


def q_clean_2h(p_nolos: np.ndarray | float, p_rd: np.ndarray | float) -> np.ndarray:
    return np.clip((1.0 - np.asarray(p_nolos, dtype=float)) * (1.0 - np.asarray(p_rd, dtype=float)), 0.0, 1.0)


def q_clean_3h(p_nolos: np.ndarray | float, p_hb_near: np.ndarray | float, p_hb_prior: np.ndarray | float) -> np.ndarray:
    return np.clip(
        (1.0 - np.asarray(p_nolos, dtype=float))
        * (1.0 - np.asarray(p_hb_near, dtype=float))
        * (1.0 - np.asarray(p_hb_prior, dtype=float)),
        0.0,
        1.0,
    )


def prediction_table_to_qclean(predictions: pd.DataFrame) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()
    piv = predictions.pivot_table(
        index=["source", "arm", "model", "case_id", "source_id"],
        columns="target",
        values="score",
        aggfunc="mean",
    ).reset_index()
    for col in ["label_nolos", "label_rd_los", "label_hb_near", "label_hb_prior"]:
        if col not in piv.columns:
            piv[col] = 0.0
    piv["q_clean_2h"] = q_clean_2h(piv["label_nolos"], piv["label_rd_los"])
    piv["q_clean_3h"] = q_clean_3h(piv["label_nolos"], piv["label_hb_near"], piv["label_hb_prior"])
    piv["claim_boundary"] = QCLEAN_CLAIM_BOUNDARY
    return piv


def decile_rates(qclean: pd.DataFrame, labels: pd.DataFrame, *, q_col: str = "q_clean_2h") -> pd.DataFrame:
    if qclean.empty:
        return pd.DataFrame()
    merged = qclean.merge(labels, on=["case_id", "source_id"], how="left")
    rows: list[dict[str, object]] = []
    for (source, arm, model), part in merged.groupby(["source", "arm", "model"]):
        values = pd.to_numeric(part[q_col], errors="coerce")
        if values.notna().sum() < 2:
            continue
        ranked = part.assign(_decile=pd.qcut(values.rank(method="first"), 10, labels=False, duplicates="drop"))
        for decile, sub in ranked.groupby("_decile"):
            rows.append(
                {
                    "source": source,
                    "arm": arm,
                    "model": model,
                    "q_clean_column": q_col,
                    "decile": int(decile),
                    "n": int(len(sub)),
                    "q_clean_min": float(sub[q_col].min()),
                    "q_clean_max": float(sub[q_col].max()),
                    "NoLoS_rate": _label_rate(sub, "label_nolos"),
                    "RD_LoS_rate": _label_rate(sub, "label_rd_los"),
                    "HB_prior_rate": _label_rate(sub, "label_hb_prior"),
                    "claim_boundary": QCLEAN_CLAIM_BOUNDARY,
                }
            )
    return pd.DataFrame(rows)


def same_acceptance_selected_risk(qclean: pd.DataFrame, labels: pd.DataFrame, *, q_col: str = "q_clean_2h", acceptance: float = 0.5) -> pd.DataFrame:
    merged = qclean.merge(labels, on=["case_id", "source_id"], how="left")
    rows: list[dict[str, object]] = []
    for (source, arm, model), part in merged.groupby(["source", "arm", "model"]):
        n_select = max(1, int(round(len(part) * acceptance)))
        selected = part.sort_values(q_col, ascending=False).head(n_select)
        rows.append(
            {
                "source": source,
                "arm": arm,
                "model": model,
                "q_clean_column": q_col,
                "acceptance": float(acceptance),
                "selected_n": int(len(selected)),
                "selected_RD_LoS_rate": _label_rate(selected, "label_rd_los"),
                "selected_HB_prior_rate": _label_rate(selected, "label_hb_prior"),
                "claim_boundary": QCLEAN_CLAIM_BOUNDARY,
            }
        )
    return pd.DataFrame(rows)


def _label_rate(df: pd.DataFrame, label_col: str) -> float:
    for candidate in [label_col, f"{label_col}_y", f"{label_col}_label"]:
        if candidate in df.columns:
            return float(pd.to_numeric(df[candidate], errors="coerce").mean())
    return float("nan")
