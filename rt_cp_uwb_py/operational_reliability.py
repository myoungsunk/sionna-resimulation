"""Operational reliability metrics for Paper 2 q-clean gate analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from rt_cp_uwb_py.localization_policies import snr_quality_score


DEFAULT_ACCEPTANCE_RATES = (0.30, 0.50, 0.70, 0.90)
DEFAULT_SCAN_COST_WEIGHT = 0.05


@dataclass(frozen=True)
class GateMetric:
    gate: str
    value: object
    reference: object
    status: str
    detail: str = ""


SCORE_COLUMNS = {
    "cp_qclean": (
        "q_clean_3H_CP_selected_calibrated",
        "q_clean_2H_CP_selected_calibrated",
        "q_clean_3H_CP",
        "q_clean_2H_CP",
    ),
    "cir_qclean": (
        "q_clean_3H_CIR_only_selected_calibrated",
        "q_clean_2H_CIR_only_selected_calibrated",
        "q_clean_3H_CIR_only",
        "q_clean_2H_CIR_only",
    ),
    "p_nolos_cp": ("p_NoLoS_3H_CP", "p_NoLoS_2H_CP"),
    "p_nolos_cir": ("p_NoLoS_3H_CIR_only", "p_NoLoS_2H_CIR_only"),
    "p_rd_cp": ("p_RD_2H_CP",),
    "p_hbprior_cp": ("p_HBprior_3H_CP",),
}


SAME_ACCEPTANCE_POLICIES = (
    "cp_qclean",
    "cir_qclean",
    "snr_quality",
    "nolos_range_safe",
    "reflection_safe",
    "oracle_clean",
)


SCAN_POLICIES = (
    "cp_qclean",
    "cir_qclean",
    "snr_quality",
    "nolos_range_safe",
    "reflection_safe",
    "oracle_clean",
)


def boolish(value: object) -> bool:
    if isinstance(value, bool):
        return bool(value)
    if value is None:
        return False
    if isinstance(value, (int, float)) and np.isfinite(value):
        return bool(value)
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y"}


def boolish_series(series: pd.Series) -> pd.Series:
    return series.map(boolish).astype(bool)


def first_numeric(df: pd.DataFrame, candidates: Iterable[str], default: float = np.nan) -> pd.Series:
    if isinstance(default, pd.Series):
        result = pd.to_numeric(default.reindex(df.index), errors="coerce").astype(float).copy()
    else:
        result = pd.Series(default, index=df.index, dtype=float)
    missing = pd.Series(True, index=df.index)
    for col in candidates:
        if col not in df.columns:
            continue
        values = pd.to_numeric(df[col], errors="coerce")
        take = missing & values.notna()
        result.loc[take] = values.loc[take]
        missing = missing & ~take
    return result


def first_bool(df: pd.DataFrame, candidates: Iterable[str], default: bool = False) -> pd.Series:
    result = pd.Series(default, index=df.index, dtype=bool)
    missing = pd.Series(True, index=df.index)
    for col in candidates:
        if col not in df.columns:
            continue
        values = boolish_series(df[col])
        raw_present = df[col].notna()
        take = missing & raw_present
        result.loc[take] = values.loc[take]
        missing = missing & ~take
    return result


def add_operational_columns(rows: pd.DataFrame) -> pd.DataFrame:
    """Add scalar scores and binary risk labels used by operational gates."""

    out = rows.copy()
    out["score_cp_qclean"] = first_numeric(out, SCORE_COLUMNS["cp_qclean"], 0.5).clip(0.0, 1.0)
    out["score_cir_qclean"] = first_numeric(out, SCORE_COLUMNS["cir_qclean"], 0.5).clip(0.0, 1.0)
    out["score_p_nolos_cp"] = first_numeric(out, SCORE_COLUMNS["p_nolos_cp"], 0.5).clip(0.0, 1.0)
    out["score_p_nolos_cir"] = first_numeric(out, SCORE_COLUMNS["p_nolos_cir"], out["score_p_nolos_cp"]).clip(0.0, 1.0)
    p_rd = first_numeric(out, SCORE_COLUMNS["p_rd_cp"], 0.0).clip(0.0, 1.0)
    p_hbprior = first_numeric(out, SCORE_COLUMNS["p_hbprior_cp"], 0.0).clip(0.0, 1.0)
    out["score_reflection_risk_cp"] = pd.concat([p_rd, p_hbprior], axis=1).max(axis=1).clip(0.0, 1.0)
    out["score_nolos_range_safe"] = (1.0 - out["score_p_nolos_cp"]).clip(0.0, 1.0)
    out["score_reflection_safe"] = (1.0 - out["score_reflection_risk_cp"]).clip(0.0, 1.0)
    out["score_snr_quality"] = pd.to_numeric(out.get("snr_db", pd.Series(np.nan, index=out.index)), errors="coerce").map(snr_quality_score)
    out["score_oracle_clean"] = first_bool(out, ("oracle_clean_3H", "oracle_clean_2H", "Clean-LoS"), False).astype(float)

    out["label_nolos"] = first_bool(out, ("NoLoS", "NoLoS_x", "NoLoS_y"), False)
    out["label_rd"] = first_bool(out, ("RD-LoS", "RD-LoS_x", "RD-LoS_y"), False)
    out["label_hbnear"] = first_bool(out, ("HB-near-delay", "HB-near-delay_x", "HB-near-delay_y"), False)
    out["label_hbprior"] = first_bool(out, ("HB-prior", "HB-prior_x", "HB-prior_y"), False)
    out["label_clean"] = first_bool(out, ("Clean-LoS", "Clean-LoS_x", "Clean-LoS_y"), False)
    if "not-clean_3H" in out.columns:
        out["label_not_clean"] = boolish_series(out["not-clean_3H"])
    elif "not-clean_2H" in out.columns:
        out["label_not_clean"] = boolish_series(out["not-clean_2H"])
    else:
        out["label_not_clean"] = out["label_nolos"] | out["label_rd"] | out["label_hbnear"] | out["label_hbprior"] | ~out["label_clean"]
    out["label_reflection"] = out["label_rd"] | out["label_hbprior"]
    out["label_unsafe_update"] = out["label_not_clean"]
    return out


def score_column_for_policy(policy_name: str) -> str:
    mapping = {
        "cp_qclean": "score_cp_qclean",
        "cir_qclean": "score_cir_qclean",
        "snr_quality": "score_snr_quality",
        "nolos_range_safe": "score_nolos_range_safe",
        "reflection_safe": "score_reflection_safe",
        "oracle_clean": "score_oracle_clean",
    }
    if policy_name not in mapping:
        raise KeyError(policy_name)
    return mapping[policy_name]


def top_acceptance_mask(rows: pd.DataFrame, score_col: str, acceptance_rate: float) -> pd.Series:
    if not 0.0 < acceptance_rate <= 1.0:
        raise ValueError(f"acceptance_rate must be in (0, 1], got {acceptance_rate}")
    n_select = max(1, int(np.ceil(len(rows) * acceptance_rate)))
    tie_cols = [col for col in ("case_id", "pose_group_id", "anchor_id") if col in rows.columns]
    ranked = rows.assign(_score=pd.to_numeric(rows[score_col], errors="coerce").fillna(-np.inf))
    ranked = ranked.sort_values(["_score", *tie_cols], ascending=[False, *([True] * len(tie_cols))])
    selected_index = ranked.head(n_select).index
    return rows.index.isin(selected_index)


def summarize_selection(selected: pd.DataFrame, rejected: pd.DataFrame) -> dict[str, float]:
    unsafe_total = int(selected["label_unsafe_update"].sum() + rejected["label_unsafe_update"].sum())
    rejected_unsafe = int(rejected["label_unsafe_update"].sum())
    clean_total = int(selected["label_clean"].sum() + rejected["label_clean"].sum())
    rejected_clean = int(rejected["label_clean"].sum())
    return {
        "selected_count": int(len(selected)),
        "rejected_count": int(len(rejected)),
        "selected_not_clean_rate": float(selected["label_not_clean"].mean()) if len(selected) else np.nan,
        "selected_nolos_rate": float(selected["label_nolos"].mean()) if len(selected) else np.nan,
        "selected_rd_rate": float(selected["label_rd"].mean()) if len(selected) else np.nan,
        "selected_hbprior_rate": float(selected["label_hbprior"].mean()) if len(selected) else np.nan,
        "selected_reflection_rate": float(selected["label_reflection"].mean()) if len(selected) else np.nan,
        "unsafe_update_rate": float(selected["label_unsafe_update"].mean()) if len(selected) else np.nan,
        "fallback_precision": float(rejected_unsafe / len(rejected)) if len(rejected) else np.nan,
        "fallback_recall": float(rejected_unsafe / unsafe_total) if unsafe_total else np.nan,
        "false_reject_rate": float(rejected_clean / clean_total) if clean_total else np.nan,
    }


def same_acceptance_summary(
    rows: pd.DataFrame,
    acceptance_rates: Iterable[float] = DEFAULT_ACCEPTANCE_RATES,
    policies: Iterable[str] = SAME_ACCEPTANCE_POLICIES,
) -> pd.DataFrame:
    scored = add_operational_columns(rows)
    split_values = ["all"]
    if "calibration_split" in scored.columns:
        split_values.extend(sorted(scored["calibration_split"].dropna().astype(str).unique()))

    summary_rows: list[dict[str, object]] = []
    for split in split_values:
        subset = scored if split == "all" else scored[scored["calibration_split"].astype(str).eq(split)]
        if subset.empty:
            continue
        for policy in policies:
            score_col = score_column_for_policy(policy)
            for rate in acceptance_rates:
                selected_mask = top_acceptance_mask(subset, score_col, float(rate))
                selected = subset.loc[selected_mask]
                rejected = subset.loc[~selected_mask]
                metrics = summarize_selection(selected, rejected)
                summary_rows.append(
                    {
                        "calibration_split": split,
                        "policy_name": policy,
                        "acceptance_target": float(rate),
                        "accepted_update_ratio": float(len(selected) / len(subset)),
                        "score_mean_selected": float(pd.to_numeric(selected[score_col], errors="coerce").mean()) if len(selected) else np.nan,
                        **metrics,
                    }
                )
    return pd.DataFrame(summary_rows)


def same_acceptance_delta(summary: pd.DataFrame, policy: str = "cp_qclean") -> pd.DataFrame:
    baselines = [name for name in SAME_ACCEPTANCE_POLICIES if name != policy and name != "oracle_clean"]
    rows: list[dict[str, object]] = []
    keys = ["calibration_split", "acceptance_target"]
    for key_values, group in summary.groupby(keys, dropna=False):
        if not isinstance(key_values, tuple):
            key_values = (key_values,)
        policy_row = group[group["policy_name"].eq(policy)]
        if policy_row.empty:
            continue
        policy_row = policy_row.iloc[0]
        for baseline in baselines:
            baseline_row = group[group["policy_name"].eq(baseline)]
            if baseline_row.empty:
                continue
            baseline_row = baseline_row.iloc[0]
            rows.append(
                {
                    "calibration_split": key_values[0],
                    "acceptance_target": key_values[1],
                    "policy_name": policy,
                    "baseline_policy": baseline,
                    "delta_selected_not_clean_rate": float(policy_row["selected_not_clean_rate"] - baseline_row["selected_not_clean_rate"]),
                    "delta_selected_nolos_rate": float(policy_row["selected_nolos_rate"] - baseline_row["selected_nolos_rate"]),
                    "delta_selected_reflection_rate": float(policy_row["selected_reflection_rate"] - baseline_row["selected_reflection_rate"]),
                    "delta_unsafe_update_rate": float(policy_row["unsafe_update_rate"] - baseline_row["unsafe_update_rate"]),
                    "delta_fallback_precision": float(policy_row["fallback_precision"] - baseline_row["fallback_precision"]),
                    "delta_false_reject_rate": float(policy_row["false_reject_rate"] - baseline_row["false_reject_rate"]),
                }
            )
    return pd.DataFrame(rows)


def scan_action_decisions(
    candidates: pd.DataFrame,
    score_rows: pd.DataFrame,
    policies: Iterable[str] = SCAN_POLICIES,
    cost_weight: float = DEFAULT_SCAN_COST_WEIGHT,
) -> pd.DataFrame:
    scored = add_operational_columns(score_rows)
    candidate_cols = [
        "case_id",
        "calibration_split",
        "score_cp_qclean",
        "score_cir_qclean",
        "score_snr_quality",
        "score_nolos_range_safe",
        "score_reflection_safe",
        "score_oracle_clean",
        "label_not_clean",
        "label_nolos",
        "label_reflection",
        "label_unsafe_update",
    ]
    lookup = scored[[col for col in candidate_cols if col in scored.columns]].copy()
    source_lookup = lookup.add_prefix("source_").rename(columns={"source_case_id": "source_case_id"})
    candidate_lookup = lookup.add_prefix("candidate_").rename(columns={"candidate_case_id": "candidate_case_id"})
    merged = candidates.merge(source_lookup, on="source_case_id", how="left", validate="many_to_one")
    merged = merged.merge(candidate_lookup, on="candidate_case_id", how="left", validate="many_to_one")
    merged["movement_cost_m"] = pd.to_numeric(merged["movement_cost_m"], errors="coerce").fillna(0.0)

    rows: list[dict[str, object]] = []
    group_cols = ["trajectory_id", "step_idx", "source_case_id"]
    for key, group in merged.groupby(group_cols, dropna=False):
        key_dict = dict(zip(group_cols, key if isinstance(key, tuple) else (key,)))
        source = group.iloc[0]
        for policy in policies:
            score_col = f"candidate_{score_column_for_policy(policy)}"
            ranked = group.copy()
            ranked["_action_score"] = pd.to_numeric(ranked[score_col], errors="coerce").fillna(-np.inf) - cost_weight * ranked["movement_cost_m"]
            ranked = ranked.sort_values(["_action_score", "movement_cost_m", "candidate_case_id"], ascending=[False, True, True])
            selected = ranked.iloc[0]
            rows.append(
                {
                    **key_dict,
                    "policy_name": policy,
                    "source_calibration_split": source.get("source_calibration_split"),
                    "source_case_id": source.get("source_case_id"),
                    "selected_case_id": selected.get("candidate_case_id"),
                    "selected_action": selected.get("action"),
                    "selected_current": bool(selected.get("candidate_case_id") == source.get("source_case_id")),
                    "candidate_count": int(len(group)),
                    "movement_cost_m": float(selected["movement_cost_m"]),
                    "source_q_cp": float(source.get("source_score_cp_qclean", np.nan)),
                    "selected_q_cp": float(selected.get("candidate_score_cp_qclean", np.nan)),
                    "source_not_clean": bool(source.get("source_label_not_clean", False)),
                    "selected_not_clean": bool(selected.get("candidate_label_not_clean", False)),
                    "source_nolos": bool(source.get("source_label_nolos", False)),
                    "selected_nolos": bool(selected.get("candidate_label_nolos", False)),
                    "source_reflection": bool(source.get("source_label_reflection", False)),
                    "selected_reflection": bool(selected.get("candidate_label_reflection", False)),
                    "source_unsafe_update": bool(source.get("source_label_unsafe_update", False)),
                    "selected_unsafe_update": bool(selected.get("candidate_label_unsafe_update", False)),
                    "q_cp_gain": float(selected.get("candidate_score_cp_qclean", np.nan) - source.get("source_score_cp_qclean", np.nan)),
                    "not_clean_reduced": bool(source.get("source_label_not_clean", False) and not selected.get("candidate_label_not_clean", False)),
                    "nolos_reduced": bool(source.get("source_label_nolos", False) and not selected.get("candidate_label_nolos", False)),
                    "reflection_reduced": bool(source.get("source_label_reflection", False) and not selected.get("candidate_label_reflection", False)),
                    "unsafe_reduced": bool(source.get("source_label_unsafe_update", False) and not selected.get("candidate_label_unsafe_update", False)),
                }
            )
    return pd.DataFrame(rows)


def scan_action_summary(decisions: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    split_values = ["all"]
    if "source_calibration_split" in decisions.columns:
        split_values.extend(sorted(decisions["source_calibration_split"].dropna().astype(str).unique()))
    for split in split_values:
        subset = decisions if split == "all" else decisions[decisions["source_calibration_split"].astype(str).eq(split)]
        if subset.empty:
            continue
        for policy, group in subset.groupby("policy_name", dropna=False):
            rows.append(
                {
                    "calibration_split": split,
                    "policy_name": policy,
                    "decision_count": int(len(group)),
                    "selected_non_current_rate": float((~group["selected_current"].astype(bool)).mean()),
                    "mean_candidate_count": float(pd.to_numeric(group["candidate_count"], errors="coerce").mean()),
                    "mean_movement_cost_m": float(pd.to_numeric(group["movement_cost_m"], errors="coerce").mean()),
                    "mean_q_cp_gain": float(pd.to_numeric(group["q_cp_gain"], errors="coerce").mean()),
                    "selected_not_clean_rate": float(group["selected_not_clean"].astype(bool).mean()),
                    "selected_nolos_rate": float(group["selected_nolos"].astype(bool).mean()),
                    "selected_reflection_rate": float(group["selected_reflection"].astype(bool).mean()),
                    "selected_unsafe_update_rate": float(group["selected_unsafe_update"].astype(bool).mean()),
                    "unsafe_reduction_rate": float(group["unsafe_reduced"].astype(bool).mean()),
                    "reflection_reduction_rate": float(group["reflection_reduced"].astype(bool).mean()),
                    "nolos_reduction_rate": float(group["nolos_reduced"].astype(bool).mean()),
                    "cost_normalized_q_gain": float(
                        pd.to_numeric(group["q_cp_gain"], errors="coerce").sum()
                        / max(pd.to_numeric(group["movement_cost_m"], errors="coerce").sum(), 1e-9)
                    ),
                }
            )
    return pd.DataFrame(rows)


def operational_gates(same_summary: pd.DataFrame, delta: pd.DataFrame, scan_summary: pd.DataFrame) -> pd.DataFrame:
    gates: list[GateMetric] = []
    expected_rows = len(SAME_ACCEPTANCE_POLICIES) * len(DEFAULT_ACCEPTANCE_RATES)
    test_same = same_summary[same_summary["calibration_split"].eq("test")]
    gates.append(
        GateMetric(
            "same_acceptance_test_rows_present",
            int(len(test_same)),
            f">={expected_rows}",
            "PASS" if len(test_same) >= expected_rows else "FAIL",
        )
    )
    cp_vs_snr = delta[delta["calibration_split"].eq("test") & delta["baseline_policy"].eq("snr_quality")]
    cp_vs_cir = delta[delta["calibration_split"].eq("test") & delta["baseline_policy"].eq("cir_qclean")]
    for name, rows in (("snr", cp_vs_snr), ("cir", cp_vs_cir)):
        if rows.empty:
            gates.append(GateMetric(f"cp_qclean_vs_{name}_same_acceptance_present", 0, ">0", "FAIL"))
            continue
        reflection_wins = int((pd.to_numeric(rows["delta_selected_reflection_rate"], errors="coerce") < 0).sum())
        unsafe_wins = int((pd.to_numeric(rows["delta_unsafe_update_rate"], errors="coerce") < 0).sum())
        gates.append(
            GateMetric(
                f"cp_qclean_vs_{name}_reflection_risk_wins",
                reflection_wins,
                f">={max(1, len(rows) // 2)}",
                "PASS" if reflection_wins >= max(1, len(rows) // 2) else "CLAIM_BOUNDARY_FAIL",
                "Same-acceptance CP q-clean should reduce selected reflection exposure for the operational gate claim.",
            )
        )
        gates.append(
            GateMetric(
                f"cp_qclean_vs_{name}_unsafe_update_wins",
                unsafe_wins,
                f">={max(1, len(rows) // 2)}",
                "PASS" if unsafe_wins >= max(1, len(rows) // 2) else "CLAIM_BOUNDARY_FAIL",
                "Same-acceptance CP q-clean should reduce unsafe updates for a broad gate claim.",
            )
        )

    test_scan = scan_summary[scan_summary["calibration_split"].eq("test")]
    cp_scan = test_scan[test_scan["policy_name"].eq("cp_qclean")]
    if cp_scan.empty:
        gates.append(GateMetric("cp_qclean_scan_test_summary_present", 0, 1, "FAIL"))
    else:
        row = cp_scan.iloc[0]
        gates.append(
            GateMetric(
                "cp_qclean_scan_has_non_current_actions",
                round(float(row["selected_non_current_rate"]), 6),
                ">0",
                "PASS" if float(row["selected_non_current_rate"]) > 0 else "CLAIM_BOUNDARY_FAIL",
            )
        )
        gates.append(
            GateMetric(
                "cp_qclean_scan_mean_q_gain_positive",
                round(float(row["mean_q_cp_gain"]), 6),
                ">0",
                "PASS" if float(row["mean_q_cp_gain"]) > 0 else "CLAIM_BOUNDARY_FAIL",
            )
        )
    return pd.DataFrame([metric.__dict__ for metric in gates])
