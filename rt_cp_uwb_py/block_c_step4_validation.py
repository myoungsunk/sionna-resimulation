"""STEP 4 validation summaries for Paper 2 Block C."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

import numpy as np
import pandas as pd

from rt_cp_uwb_py.block_c_hw_imperfection import MISSING_GROUNDED_HW_RANGE


GATE_B1 = "GATE_B1_RD_BLIND_BASELINE_INTERACTION"
GATE_C = "GATE_C_CP_SPECIFICITY"
OVERALL = "OVERALL_RD_BLIND_REFLECTION"
EVIDENCE_CI = "CP_MAIN_MINUS_CIR_ML_RD_BLIND_RISK_STATE_NLL"


@dataclass(frozen=True)
class Step4Verdict:
    gate_id: str
    status: str
    detail: str


def build_profile_validation(
    worst: pd.DataFrame,
    profile_map: pd.DataFrame,
    step3_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Join STEP 2 profile metadata to STEP 3 backend gates."""

    require_columns(worst, ["knob", "level_id", "severity_order"], "STEP 2 worst-phase summary")
    require_columns(profile_map, ["profile_id", "level_id", "retention", "cp_margin_drop_from_ideal_db"], "STEP 3 profile map")
    require_columns(step3_summary, ["profile_id", "gate_id", "status"], "STEP 3 backend gate summary")

    meta = profile_map.merge(
        worst[
            [
                "knob",
                "level_id",
                "severity_order",
                "phase_rad",
                "cp_margin_proxy_db",
                "state_nll_proxy",
                "ab_match_status",
            ]
        ],
        on=["knob", "level_id", "phase_rad", "cp_margin_proxy_db", "state_nll_proxy"],
        how="left",
    )
    gate = pivot_step3_gates(step3_summary)
    out = meta.merge(gate, on="profile_id", how="left")
    ideal = out[out["level_id"].astype(str).eq("ideal")]
    ideal_gate_c = float(pd.to_numeric(ideal["gate_c_observed"], errors="coerce").iloc[0]) if not ideal.empty else np.nan
    out["gate_c_delta_from_ideal_nll"] = pd.to_numeric(out["gate_c_observed"], errors="coerce") - ideal_gate_c
    out["step3_backend_all_gates_pass"] = (
        out["gate_b1_status"].astype(str).str.startswith("PASS")
        & out["gate_c_status"].astype(str).str.startswith("PASS")
        & out["overall_status"].astype(str).eq("CP_SPECIFIC_RD_BLIND_SUPPORTED_SIM_DIAGNOSTIC")
    )
    out["grounded_hw_range_status"] = MISSING_GROUNDED_HW_RANGE
    out["failure_threshold_interpretation"] = "FORBIDDEN_WITHOUT_GROUNDED_HW_RANGE"
    return out.sort_values(["knob", "severity_order", "level_id"], na_position="last").reset_index(drop=True)


def pivot_step3_gates(summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for profile_id, part in summary.groupby("profile_id", dropna=False):
        row: dict[str, Any] = {"profile_id": str(profile_id)}
        for gate_id, prefix in [(GATE_B1, "gate_b1"), (GATE_C, "gate_c"), (OVERALL, "overall"), (EVIDENCE_CI, "evidence_ci")]:
            match = part[part["gate_id"].astype(str).eq(gate_id)]
            if match.empty:
                row[f"{prefix}_status"] = "MISSING"
                row[f"{prefix}_observed"] = np.nan
                row[f"{prefix}_ci_low"] = np.nan
                row[f"{prefix}_ci_high"] = np.nan
                continue
            first = match.iloc[0]
            row[f"{prefix}_status"] = str(first.get("status", ""))
            row[f"{prefix}_observed"] = as_float(first.get("observed", np.nan))
            row[f"{prefix}_ci_low"] = as_float(first.get("ci_low", np.nan))
            row[f"{prefix}_ci_high"] = as_float(first.get("ci_high", np.nan))
        rows.append(row)
    return pd.DataFrame(rows)


def build_knob_sensitivity(profile_validation: pd.DataFrame, diagnostics: pd.DataFrame) -> pd.DataFrame:
    """Summarize V2/V4 backend sensitivity by imperfection knob."""

    diag_by_knob = {str(row.get("knob", "")): row for row in diagnostics.to_dict("records")}
    rows: list[dict[str, Any]] = []
    frame = profile_validation[~profile_validation["level_id"].astype(str).eq("ideal")].copy()
    for knob, part in frame.groupby("knob", dropna=False):
        ordered = part.sort_values(["severity_order", "level_id"], na_position="last").copy()
        delta = pd.to_numeric(ordered["gate_c_delta_from_ideal_nll"], errors="coerce")
        max_idx = delta.idxmax()
        min_ret_idx = pd.to_numeric(ordered["retention"], errors="coerce").idxmin()
        diag = diag_by_knob.get(str(knob), {})
        backend_metric_monotone = monotone_non_decreasing(delta.to_numpy(dtype=float)) if len(delta) > 1 else True
        all_backend_pass = bool(ordered["step3_backend_all_gates_pass"].all())
        rows.append(
            {
                "knob": str(knob),
                "n_profiles": int(len(ordered)),
                "all_backend_gates_pass": all_backend_pass,
                "backend_gate_cliff_status": "PASS_NO_CLIFF_GATE_STATUS_STABLE" if all_backend_pass else "FAIL_BACKEND_GATE_CLIFF",
                "backend_metric_monotone_non_decreasing_worse_nll": backend_metric_monotone,
                "backend_metric_monotonicity_status": "PASS_MONOTONE" if backend_metric_monotone else "PARTIAL_NON_MONOTONE_BUT_GATES_STABLE",
                "worst_backend_profile_id": str(ordered.loc[max_idx, "profile_id"]),
                "max_gate_c_delta_from_ideal_nll": float(delta.loc[max_idx]),
                "min_retention_profile_id": str(ordered.loc[min_ret_idx, "profile_id"]),
                "min_retention": float(pd.to_numeric(ordered.loc[[min_ret_idx], "retention"], errors="coerce").iloc[0]),
                "most_negative_cp_margin_drop_db": float(pd.to_numeric(ordered["cp_margin_drop_from_ideal_db"], errors="coerce").min()),
                "channel_margin_monotone_nonincreasing": bool_from_any(diag.get("monotone_nonincreasing_margin_worst_phase", "")),
                "channel_ab_match_all_pass": bool_from_any(diag.get("ab_match_all_pass", "")),
                "grounded_hw_range_status": MISSING_GROUNDED_HW_RANGE,
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("max_gate_c_delta_from_ideal_nll", ascending=False).reset_index(drop=True)


def build_phase_robustness(sweep: pd.DataFrame) -> pd.DataFrame:
    """Summarize V3 phase spread at every STEP 2 level."""

    require_columns(sweep, ["knob", "level_id", "phase_rad", "cp_margin_proxy_db", "cp_margin_drop_from_ideal_db"], "STEP 2 sweep")
    rows: list[dict[str, Any]] = []
    for (knob, level_id), part in sweep.groupby(["knob", "level_id"], dropna=False):
        margin = pd.to_numeric(part["cp_margin_proxy_db"], errors="coerce")
        nll = pd.to_numeric(part.get("state_nll_proxy", pd.Series(index=part.index, dtype=float)), errors="coerce")
        drop = pd.to_numeric(part["cp_margin_drop_from_ideal_db"], errors="coerce")
        worst_drop = float(drop.min())
        spread = float(margin.max() - margin.min())
        nll_spread = float(nll.max() - nll.min()) if len(nll) else np.nan
        status = "PASS_PHASE_INVARIANT_IDEAL" if str(level_id) == "ideal" else "PASS_PHASE_SPREAD_WITHIN_WORST_DROP"
        if str(level_id) != "ideal" and spread > abs(worst_drop) + 1.0e-12:
            status = "WARN_PHASE_SPREAD_EXCEEDS_WORST_DROP"
        rows.append(
            {
                "knob": str(knob),
                "level_id": str(level_id),
                "n_phases": int(part["phase_rad"].nunique()),
                "cp_margin_phase_spread_db": spread,
                "state_nll_phase_spread": nll_spread,
                "worst_cp_margin_drop_db": worst_drop,
                "phase_robustness_status": status,
            }
        )
    return pd.DataFrame(rows).sort_values(["knob", "level_id"]).reset_index(drop=True)


def build_step4_gate_ledger(
    profile_validation: pd.DataFrame,
    knob_sensitivity: pd.DataFrame,
    phase_robustness: pd.DataFrame,
    sweep: pd.DataFrame,
) -> pd.DataFrame:
    """Create a compact STEP 4 validation gate ledger."""

    all_backend_pass = bool(profile_validation["step3_backend_all_gates_pass"].all()) if not profile_validation.empty else False
    all_ab_pass = bool(sweep["ab_match_status"].astype(str).eq("PASS_AB_MATCH").all()) if "ab_match_status" in sweep.columns else False
    phase_warnings = int(phase_robustness["phase_robustness_status"].astype(str).str.startswith("WARN").sum()) if not phase_robustness.empty else 0
    nonmonotone_knobs = int((~knob_sensitivity["backend_metric_monotone_non_decreasing_worse_nll"].astype(bool)).sum()) if not knob_sensitivity.empty else 0
    top_knob = ""
    if not knob_sensitivity.empty:
        top = knob_sensitivity.iloc[0]
        top_knob = f"{top['knob']}::{top['worst_backend_profile_id']} delta={float(top['max_gate_c_delta_from_ideal_nll']):.6g}"

    rows = [
        Step4Verdict(
            "V_HV2_A_B_MATCH",
            "PASS_A_B_MATCH_ALL_PROFILES" if all_ab_pass else "FAIL_A_B_MISMATCH",
            "C-A CP-basis and C-B H/V-equivalent STEP 2 outputs match within tolerance.",
        ),
        Step4Verdict(
            "V2_BACKEND_NO_CLIFF",
            "PASS_NO_CLIFF_ALL_STEP3_GATES_STABLE" if all_backend_pass else "FAIL_BACKEND_GATE_CLIFF",
            f"profiles={int(profile_validation['profile_id'].nunique()) if not profile_validation.empty else 0}",
        ),
        Step4Verdict(
            "V2_BACKEND_METRIC_MONOTONICITY",
            "PASS_BACKEND_METRIC_MONOTONE_ALL_KNOBS" if nonmonotone_knobs == 0 else "PARTIAL_NON_MONOTONE_METRIC_BUT_GATES_STABLE",
            f"nonmonotone_knobs={nonmonotone_knobs}",
        ),
        Step4Verdict(
            "V3_PHASE_ROBUSTNESS",
            "PASS_PHASE_SPREAD_WITHIN_DROP_ALL_LEVELS" if phase_warnings == 0 else "WARN_PHASE_SPREAD_EXCEEDS_WORST_DROP",
            f"phase_warning_levels={phase_warnings}",
        ),
        Step4Verdict(
            "V4_KNOB_SENSITIVITY",
            "PASS_SMOKE_KNOB_PRIORITY_TABLE_BUILT" if top_knob else "FAIL_KNOB_PRIORITY_MISSING",
            top_knob,
        ),
        Step4Verdict(
            "FAILURE_THRESHOLD",
            "NOT_OBSERVED_IN_SMOKE_PROFILES_BUT_REALITY_FORBIDDEN_WITHOUT_GROUNDED_HW_RANGE"
            if all_backend_pass
            else "OBSERVED_IN_SMOKE_PROFILES_REALITY_STILL_FORBIDDEN_WITHOUT_GROUNDED_HW_RANGE",
            MISSING_GROUNDED_HW_RANGE,
        ),
    ]
    overall_status = "PASS_STEP4_VALIDATION_COMPLETE_SMOKE_ONLY" if all_backend_pass and all_ab_pass else "STEP4_VALIDATION_HAS_FAILURES"
    rows.append(
        Step4Verdict(
            "OVERALL_STEP4",
            overall_status,
            "No grounded HW range; do not make reality/irreality threshold claim.",
        )
    )
    return pd.DataFrame([row.__dict__ for row in rows])


def require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{label} is missing columns: {missing}")


def monotone_non_decreasing(values: np.ndarray, atol: float = 1.0e-12) -> bool:
    finite = values[np.isfinite(values)]
    if len(finite) <= 1:
        return True
    return bool(np.all(np.diff(finite) >= -float(atol)))


def bool_from_any(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "pass"}


def as_float(value: Any) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return np.nan
    if not isfinite(out):
        return np.nan
    return out
