"""Remaining G2-G6 execution for the N3 CP physics-conditioned bridge.

This module consumes frozen full-FFD path truth and frozen OOF q_clean scores.
Physical risk is an evaluation endpoint and is never used as a training label.
"""

from __future__ import annotations

import hashlib
import json
import math
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-30
SEED = 20260712


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def resolve_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError("Config root must be a mapping")
    return config


def ensure_output(root: Path) -> dict[str, Path]:
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"Output directory already exists and is non-empty: {root}")
    dirs = {
        "root": root,
        "tables": root / "tables",
        "figures": root / "figures",
        "configs": root / "configs",
        "logs": root / "logs",
        "reports": root / "reports",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    return dirs


def combine_power(frame: pd.DataFrame, arm: dict[str, Any]) -> pd.Series:
    columns = list(arm["power_columns"])
    values = frame[columns].apply(pd.to_numeric, errors="coerce").clip(lower=0.0)
    operation = arm["combining_operation"]
    if operation == "canonical":
        return values.iloc[:, 0]
    if operation == "sum":
        return values.sum(axis=1, min_count=len(columns))
    if operation == "max":
        return values.max(axis=1, skipna=False)
    raise ValueError(f"Unsupported combining operation: {operation}")


def incidence_angle_deg(frame: pd.DataFrame) -> pd.Series:
    launch = frame[["launch_dir_x", "launch_dir_y", "launch_dir_z"]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    normal = frame[["first_normal_x", "first_normal_y", "first_normal_z"]].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    numerator = np.abs(np.sum(launch * normal, axis=1))
    denominator = np.linalg.norm(launch, axis=1) * np.linalg.norm(normal, axis=1)
    cosine = np.divide(numerator, denominator, out=np.full(len(frame), np.nan), where=denominator > 0)
    return pd.Series(np.degrees(np.arccos(np.clip(cosine, 0.0, 1.0))), index=frame.index)


def angle_bin(values: pd.Series) -> pd.Series:
    return pd.cut(
        pd.to_numeric(values, errors="coerce"),
        bins=[0.0, 45.0, 60.0, 70.0, 75.0, 90.000001],
        labels=["normal_to_mid", "high_mid", "brewster_like", "near_grazing", "grazing"],
        include_lowest=True,
        right=False,
    ).astype("string")


def read_physical_inputs(config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[Path]]:
    inputs = config["inputs"]
    fullffd_root = resolve_path(inputs["fullffd_root"])
    path_sources = sorted(fullffd_root.glob(inputs["path_glob"]))
    if not path_sources:
        raise FileNotFoundError("No configured full-FFD path chunks found")
    base_columns = [
        "case_id", "path_id", "path_index", "is_los", "bounce_count", "path_delay_s",
        "launch_dir_x", "launch_dir_y", "launch_dir_z",
        "first_normal_x", "first_normal_y", "first_normal_z",
    ]
    power_columns = sorted({column for arm in config["receiver_arms"].values() for column in arm["power_columns"]})
    usecols = [*base_columns, *power_columns]
    path_frame = pd.concat(
        [pd.read_csv(path, usecols=usecols, dtype={"case_id": "string"}) for path in path_sources],
        ignore_index=True,
    )
    path_frame["case_id"] = path_frame["case_id"].astype(str)
    feature = pd.read_csv(
        resolve_path(inputs["feature_table"]),
        usecols=["case_id", "space_id", "condition_id"],
        dtype={"case_id": "string"},
    ).drop_duplicates("case_id")
    split = pd.read_csv(
        resolve_path(inputs["split_table"]),
        usecols=["case_id", "epoch_id", "physical_cluster_id", "fold_id"],
        dtype={"case_id": "string"},
    ).drop_duplicates("case_id")
    return path_frame, feature, split, path_sources


def materialize_physical_metrics(
    path_frame: pd.DataFrame, feature: pd.DataFrame, split: pd.DataFrame, config: dict[str, Any]
) -> pd.DataFrame:
    frame = path_frame.copy()
    frame["is_los_bool"] = frame["is_los"].astype(str).str.lower().isin(["true", "1", "yes"])
    frame["path_delay_s_num"] = pd.to_numeric(frame["path_delay_s"], errors="coerce")
    direct = (
        frame.loc[frame["is_los_bool"] & frame["path_delay_s_num"].notna()]
        .sort_values(["case_id", "path_delay_s_num", "path_index"])
        .drop_duplicates("case_id")
        .copy()
    )
    direct_delay = direct.set_index("case_id")["path_delay_s_num"]
    frame["direct_delay_s"] = frame["case_id"].map(direct_delay)
    contract = config["source_contract"]
    frame["path_dtau_B"] = (
        frame["path_delay_s_num"] - frame["direct_delay_s"]
    ) * float(contract["bandwidth_hz"])
    window = frame.loc[
        frame["direct_delay_s"].notna()
        & ~frame["is_los_bool"]
        & frame["path_dtau_B"].between(-1e-9, float(contract["unresolved_window_B"]), inclusive="both")
    ].copy()
    if window.empty:
        raise ValueError("No first-path-window reflected paths")

    dominant_score = combine_power(window, config["receiver_arms"]["CP2"]).fillna(0.0) + combine_power(
        window, config["receiver_arms"]["DLP2-NC"]
    ).fillna(0.0)
    dominant = window.assign(_dominant_score=dominant_score).sort_values(
        ["case_id", "_dominant_score"], ascending=[True, False]
    ).drop_duplicates("case_id")
    dominant = dominant[["case_id", "bounce_count", "launch_dir_x", "launch_dir_y", "launch_dir_z", "first_normal_x", "first_normal_y", "first_normal_z"]].copy()
    dominant["theta_inc_deg"] = incidence_angle_deg(dominant)
    dominant["angle_bin"] = angle_bin(dominant["theta_inc_deg"])
    bounce = pd.to_numeric(dominant["bounce_count"], errors="coerce")
    dominant["dominant_parity"] = np.where(bounce.mod(2).eq(0), "even", "odd")
    dominant.loc[bounce.isna(), "dominant_parity"] = "unknown"
    dominant = dominant[["case_id", "theta_inc_deg", "angle_bin", "dominant_parity"]]

    metadata = feature.merge(split, on="case_id", how="inner", validate="one_to_one").merge(
        dominant, on="case_id", how="inner", validate="one_to_one"
    )
    rows: list[pd.DataFrame] = []
    for arm_name, arm in config["receiver_arms"].items():
        direct_arm = direct[["case_id"]].copy()
        direct_arm["direct_power"] = combine_power(direct, arm).to_numpy(float)
        window_arm = window[["case_id"]].copy()
        window_arm["window_power"] = combine_power(window, arm).to_numpy(float)
        window_sum = window_arm.groupby("case_id", as_index=False)["window_power"].sum(min_count=1)
        case = metadata.merge(direct_arm, on="case_id", how="inner").merge(window_sum, on="case_id", how="inner")
        case = case.loc[case["direct_power"].gt(0.0) & case["window_power"].ge(0.0)].copy()
        case["arm"] = arm_name
        case["r_phys"] = (case["window_power"] + EPS) / (case["direct_power"] + EPS)
        case["sir"] = (case["direct_power"] + EPS) / (case["window_power"] + EPS)
        case["log_r_phys"] = np.log(case["r_phys"])
        case["log_sir"] = np.log(case["sir"])
        case["diagnostic_only"] = arm_name == "DLP2-ORACLE"
        rows.append(case)
    return pd.concat(rows, ignore_index=True)


def cluster_median_ci(frame: pd.DataFrame, value_col: str, n_boot: int, seed: int) -> tuple[float, float, float]:
    cluster_values = (
        frame[["physical_cluster_id", value_col]].dropna().groupby("physical_cluster_id")[value_col].median().to_numpy(float)
    )
    if not len(cluster_values):
        return math.nan, math.nan, math.nan
    estimate = float(np.median(cluster_values))
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(cluster_values), size=(n_boot, len(cluster_values)))
    samples = np.median(cluster_values[indices], axis=1)
    return estimate, float(np.quantile(samples, 0.025)), float(np.quantile(samples, 0.975))


def build_g2(physical: pd.DataFrame, n_boot: int) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    fields = ["case_id", "physical_cluster_id", "space_id", "condition_id", "angle_bin", "dominant_parity", "r_phys", "sir"]
    cp = physical.loc[physical["arm"].eq("CP2"), fields].rename(columns={"r_phys": "r_cp", "sir": "sir_cp"})
    dlp = physical.loc[physical["arm"].eq("DLP2-NC"), ["case_id", "r_phys", "sir"]].rename(columns={"r_phys": "r_dlp", "sir": "sir_dlp"})
    paired = cp.merge(dlp, on="case_id", how="inner", validate="one_to_one")
    paired["r_phys_ratio_cp_over_dlp"] = (paired["r_cp"] + EPS) / (paired["r_dlp"] + EPS)
    paired["sir_ratio_cp_over_dlp"] = (paired["sir_cp"] + EPS) / (paired["sir_dlp"] + EPS)

    summary_rows = []
    for idx, metric in enumerate(["r_phys_ratio_cp_over_dlp", "sir_ratio_cp_over_dlp"]):
        estimate, low, high = cluster_median_ci(paired, metric, n_boot, SEED + idx)
        summary_rows.append({"scope": "pooled", "stratum": "ALL", "metric": metric, "median": estimate, "ci_low": low, "ci_high": high, "n_cases": len(paired), "n_clusters": paired["physical_cluster_id"].nunique(), "bootstrap": n_boot})
    stratum_rows = []
    for group_col in ["space_id", "condition_id", "angle_bin", "dominant_parity"]:
        for level, group in paired.groupby(group_col, dropna=False):
            for idx, metric in enumerate(["r_phys_ratio_cp_over_dlp", "sir_ratio_cp_over_dlp"]):
                estimate, low, high = cluster_median_ci(group, metric, n_boot, SEED + 100 + idx)
                stratum_rows.append({"scope": group_col, "stratum": str(level), "metric": metric, "median": estimate, "ci_low": low, "ci_high": high, "n_cases": len(group), "n_clusters": group["physical_cluster_id"].nunique(), "bootstrap": n_boot})
    summary = pd.DataFrame(summary_rows)
    strata = pd.DataFrame(stratum_rows)
    r_row = summary.loc[summary["metric"].eq("r_phys_ratio_cp_over_dlp")].iloc[0]
    sir_row = summary.loc[summary["metric"].eq("sir_ratio_cp_over_dlp")].iloc[0]
    primary_pass = float(r_row["ci_high"]) < 1.0 and float(sir_row["ci_low"]) > 1.0
    reverse = float(r_row["ci_low"]) > 1.0 and float(sir_row["ci_high"]) < 1.0
    space = strata.loc[strata["scope"].eq("space_id")]
    space_r = space.loc[space["metric"].eq("r_phys_ratio_cp_over_dlp"), "median"].lt(1.0).all()
    space_sir = space.loc[space["metric"].eq("sir_ratio_cp_over_dlp"), "median"].gt(1.0).all()
    if primary_pass and space_r and space_sir:
        verdict = "SUPPORTED_SCOPED_SIMULATION"
    elif primary_pass:
        verdict = "MIXED_INTERACTION_SCOPED"
    elif reverse:
        verdict = "REFUTED_FOR_PRIMARY_CONTRACT"
    else:
        verdict = "NOT_ESTABLISHED"
    gate = {"gate": "G2", "pass": bool(primary_pass), "verdict": verdict, "r_ci_high": float(r_row["ci_high"]), "sir_ci_low": float(sir_row["ci_low"]), "all_space_direction": bool(space_r and space_sir)}
    return paired, pd.concat([summary, strata], ignore_index=True), gate


def ece10(y: np.ndarray, q: np.ndarray) -> float:
    bins = np.linspace(0.0, 1.0, 11)
    total = len(y)
    if not total:
        return math.nan
    value = 0.0
    for index in range(10):
        mask = (q >= bins[index]) & (q < bins[index + 1] if index < 9 else q <= bins[index + 1])
        if mask.any():
            value += mask.mean() * abs(float(q[mask].mean()) - float(y[mask].mean()))
    return float(value)


def accepted_mask(q: pd.Series, fraction: float) -> pd.Series:
    n_accept = int(math.ceil(len(q) * fraction))
    accepted = pd.Series(False, index=q.index)
    accepted.loc[q.sort_values(ascending=False, kind="mergesort").index[:n_accept]] = True
    return accepted


def load_oof_by_arm(config: dict[str, Any]) -> dict[str, pd.DataFrame]:
    inputs = config["inputs"]
    columns = ["case_id", "epoch_id", "physical_cluster_id", "fold_id", "arm", "n_features", "label_variant", "q_clean", "y_clean", "true_label"]
    cp_all = pd.read_csv(resolve_path(inputs["cp_oof_table"]), usecols=columns, dtype={"case_id": "string"})
    dual_all = pd.read_csv(resolve_path(inputs["dual_lp_oof_table"]), usecols=columns, dtype={"case_id": "string"})
    template = pd.read_csv(resolve_path(inputs["template_oof_table"]), usecols=columns, dtype={"case_id": "string"})
    mapping = {
        "CP2": (cp_all, config["receiver_arms"]["CP2"]["feature_arm"]),
        "LP1": (cp_all, config["receiver_arms"]["LP1"]["feature_arm"]),
        "DLP2-NC": (dual_all, config["receiver_arms"]["DLP2-NC"]["feature_arm"]),
        "DLP2-XPOL": (template, config["receiver_arms"]["DLP2-XPOL"]["feature_arm"]),
    }
    return {name: frame.loc[frame["arm"].astype(str).eq(arm)].copy() for name, (frame, arm) in mapping.items()}


def paired_operating_bootstrap(frame: pd.DataFrame, n_boot: int, seed: int) -> dict[str, float]:
    cluster = frame.groupby("physical_cluster_id", as_index=False).agg(
        cp_accept=("cp_accept", "sum"), dlp_accept=("dlp_accept", "sum"),
        cp_dirty_accept=("cp_dirty_accept", "sum"), dlp_dirty_accept=("dlp_dirty_accept", "sum"),
        cp_clean_yield=("cp_clean_yield", "sum"), dlp_clean_yield=("dlp_clean_yield", "sum"),
        n=("case_id", "size"),
    )
    def stat(sample: pd.DataFrame) -> tuple[float, float]:
        cp_dirty = sample["cp_dirty_accept"].sum() / max(sample["cp_accept"].sum(), 1)
        dlp_dirty = sample["dlp_dirty_accept"].sum() / max(sample["dlp_accept"].sum(), 1)
        n = sample["n"].sum()
        yield_diff = (sample["cp_clean_yield"].sum() - sample["dlp_clean_yield"].sum()) / max(n, 1)
        return float(cp_dirty - dlp_dirty), float(yield_diff)
    dirty_obs, yield_obs = stat(cluster)
    rng = np.random.default_rng(seed)
    dirty_samples = np.empty(n_boot)
    yield_samples = np.empty(n_boot)
    for i in range(n_boot):
        sample = cluster.iloc[rng.integers(0, len(cluster), len(cluster))]
        dirty_samples[i], yield_samples[i] = stat(sample)
    return {
        "dirty_diff": dirty_obs,
        "dirty_ci_low": float(np.quantile(dirty_samples, 0.025)),
        "dirty_ci_high": float(np.quantile(dirty_samples, 0.975)),
        "yield_diff": yield_obs,
        "yield_ci_low": float(np.quantile(yield_samples, 0.025)),
        "yield_ci_high": float(np.quantile(yield_samples, 0.975)),
    }


def build_g3(
    physical: pd.DataFrame, oof: dict[str, pd.DataFrame], config: dict[str, Any], n_boot: int
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, pd.DataFrame]]:
    fractions = [float(value) for value in config["future_gates"]["retained_fractions"]]
    thresholds = [float(value) for value in config["future_gates"]["sensitivity_dirty_thresholds"]]
    arm_frames: dict[str, pd.DataFrame] = {}
    curve_rows: list[dict[str, Any]] = []
    cap_rows: list[dict[str, Any]] = []
    for arm_name in ["LP1", "DLP2-NC", "DLP2-XPOL", "CP2"]:
        arm_phys = physical.loc[physical["arm"].eq(arm_name)].copy()
        merged = arm_phys.merge(oof[arm_name], on=["case_id", "physical_cluster_id", "epoch_id", "fold_id"], how="inner", validate="one_to_one")
        arm_frames[arm_name] = merged
        for threshold in thresholds:
            dirty = merged["r_phys"].ge(threshold)
            ordered = merged.assign(_dirty=dirty).sort_values("q_clean", ascending=False, kind="mergesort")
            cumulative_dirty = ordered["_dirty"].cumsum() / np.arange(1, len(ordered) + 1)
            for fraction in fractions:
                accept = accepted_mask(merged["q_clean"], fraction)
                retained = merged.loc[accept]
                retained_dirty = retained["r_phys"].ge(threshold)
                all_dirty = dirty
                curve_rows.append(
                    {
                        "arm": arm_name, "dirty_threshold": threshold, "retained_fraction": fraction,
                        "n_total": len(merged), "n_retained": int(accept.sum()),
                        "retained_mean_r_phys": float(retained["r_phys"].mean()),
                        "retained_median_r_phys": float(retained["r_phys"].median()),
                        "retained_dirty_rate": float(retained_dirty.mean()),
                        "clean_retained_yield": float((accept & ~dirty).mean()),
                        "dirty_tail_capture_rejected": float((~accept & all_dirty).sum() / max(all_dirty.sum(), 1)),
                        "ece10_retained": ece10(retained["y_clean"].to_numpy(int), retained["q_clean"].to_numpy(float)),
                        "brier_retained": float(np.mean((retained["q_clean"].to_numpy(float) - retained["y_clean"].to_numpy(float)) ** 2)),
                    }
                )
            for cap in [float(value) for value in config["future_gates"]["fixed_dirty_risk_caps"]]:
                valid = np.flatnonzero(cumulative_dirty.to_numpy(float) <= cap)
                max_k = int(valid.max() + 1) if len(valid) else 0
                cap_rows.append({"arm": arm_name, "dirty_threshold": threshold, "risk_cap": cap, "max_retained_cases": max_k, "max_retained_fraction": max_k / len(ordered), "achieved_dirty_rate": float(cumulative_dirty.iloc[max_k - 1]) if max_k else math.nan})

    curve = pd.DataFrame(curve_rows)
    caps = pd.DataFrame(cap_rows)
    primary_threshold = float(config["future_gates"]["primary_dirty_threshold"])
    cp = arm_frames["CP2"].copy()
    dlp = arm_frames["DLP2-NC"].copy()
    common = cp[["case_id", "physical_cluster_id", "q_clean", "r_phys"]].rename(columns={"q_clean": "q_cp", "r_phys": "r_cp"}).merge(
        dlp[["case_id", "q_clean", "r_phys"]].rename(columns={"q_clean": "q_dlp", "r_phys": "r_dlp"}), on="case_id", validate="one_to_one"
    )
    diff_rows = []
    for index, fraction in enumerate(fractions):
        common["cp_accept"] = accepted_mask(common["q_cp"], fraction)
        common["dlp_accept"] = accepted_mask(common["q_dlp"], fraction)
        common["cp_dirty_accept"] = common["cp_accept"] & common["r_cp"].ge(primary_threshold)
        common["dlp_dirty_accept"] = common["dlp_accept"] & common["r_dlp"].ge(primary_threshold)
        common["cp_clean_yield"] = common["cp_accept"] & common["r_cp"].lt(primary_threshold)
        common["dlp_clean_yield"] = common["dlp_accept"] & common["r_dlp"].lt(primary_threshold)
        result = paired_operating_bootstrap(common, n_boot, SEED + 300 + index)
        cp_curve = curve.loc[curve["arm"].eq("CP2") & curve["dirty_threshold"].eq(primary_threshold) & curve["retained_fraction"].eq(fraction)].iloc[0]
        dlp_curve = curve.loc[curve["arm"].eq("DLP2-NC") & curve["dirty_threshold"].eq(primary_threshold) & curve["retained_fraction"].eq(fraction)].iloc[0]
        diff_rows.append({"retained_fraction": fraction, **result, "ece_delta_cp_minus_dlp": float(cp_curve["ece10_retained"] - dlp_curve["ece10_retained"]), "bootstrap": n_boot})
    differences = pd.DataFrame(diff_rows)
    primary_rows = differences.loc[differences["retained_fraction"].isin([0.8, 0.9])]
    dirty_pass = primary_rows["dirty_ci_high"].lt(0.0).all() and len(primary_rows) == 2
    yield_pass = primary_rows["yield_ci_low"].gt(0.0).any()
    primary_fraction = float(config["future_gates"]["primary_operating_fraction"])
    ece_row = differences.loc[differences["retained_fraction"].eq(primary_fraction)].iloc[0]
    ece_pass = float(ece_row["ece_delta_cp_minus_dlp"]) <= 0.01
    passed = bool(dirty_pass and yield_pass and ece_pass)
    any_support = bool(primary_rows["dirty_ci_high"].lt(0.0).any() or primary_rows["yield_ci_low"].gt(0.0).any())
    verdict = "SUPPORTED_PRIMARY_OPERATING_POINTS" if passed else ("MIXED_OPERATING_POINT_SCOPED" if any_support else "NOT_ESTABLISHED")
    gate = {"gate": "G3", "pass": passed, "verdict": verdict, "dirty_pass_0p8_0p9": bool(dirty_pass), "yield_pass_either": bool(yield_pass), "ece_delta_at_primary": float(ece_row["ece_delta_cp_minus_dlp"]), "ece_pass": bool(ece_pass)}
    return curve, differences, caps, gate, arm_frames


def fixed_effect_coefficient(frame: pd.DataFrame, x_col: str, y_col: str) -> float:
    work = frame[[x_col, y_col, "space_id", "condition_id"]].dropna()
    if len(work) < 10:
        return math.nan
    dummies = pd.get_dummies(work[["space_id", "condition_id"]].astype(str), drop_first=True, dtype=float)
    matrix = np.column_stack([np.ones(len(work)), work[x_col].to_numpy(float), dummies.to_numpy(float)])
    coefficient = np.linalg.lstsq(matrix, work[y_col].to_numpy(float), rcond=None)[0]
    return float(coefficient[1])


def association_bootstrap(frame: pd.DataFrame, n_boot: int, seed: int) -> dict[str, float]:
    cluster = frame.groupby("physical_cluster_id", as_index=False).agg(
        delta_log_sir=("delta_log_sir", "mean"), target=("target", "mean"),
        space_id=("space_id", "first"), condition_id=("condition_id", "first"),
    )
    rho = float(cluster["delta_log_sir"].corr(cluster["target"], method="spearman"))
    beta = fixed_effect_coefficient(cluster, "delta_log_sir", "target")
    rng = np.random.default_rng(seed)
    rhos = np.empty(n_boot)
    betas = np.empty(n_boot)
    for i in range(n_boot):
        sample = cluster.iloc[rng.integers(0, len(cluster), len(cluster))]
        rhos[i] = sample["delta_log_sir"].corr(sample["target"], method="spearman")
        betas[i] = fixed_effect_coefficient(sample, "delta_log_sir", "target")
    return {"spearman": rho, "spearman_ci_low": float(np.nanquantile(rhos, 0.025)), "spearman_ci_high": float(np.nanquantile(rhos, 0.975)), "fixed_effect_beta": beta, "beta_ci_low": float(np.nanquantile(betas, 0.025)), "beta_ci_high": float(np.nanquantile(betas, 0.975)), "n_clusters": len(cluster)}


def build_g4(
    arm_frames: dict[str, pd.DataFrame], config: dict[str, Any], n_boot: int
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    primary_fraction = float(config["future_gates"]["primary_operating_fraction"])
    rows = []
    scatter_primary = pd.DataFrame()
    cp = arm_frames["CP2"].copy()
    cp["accepted"] = accepted_mask(cp["q_clean"], primary_fraction)
    cp["brier_loss"] = (cp["q_clean"] - cp["y_clean"]) ** 2
    cp["combined_loss"] = cp["brier_loss"] + cp["accepted"].astype(float) * np.log1p(cp["r_phys"])
    for index, comparator in enumerate(["DLP2-NC", "DLP2-XPOL"]):
        other = arm_frames[comparator].copy()
        other["accepted"] = accepted_mask(other["q_clean"], primary_fraction)
        other["brier_loss"] = (other["q_clean"] - other["y_clean"]) ** 2
        other["combined_loss"] = other["brier_loss"] + other["accepted"].astype(float) * np.log1p(other["r_phys"])
        fields = ["case_id", "physical_cluster_id", "space_id", "condition_id", "sir", "brier_loss", "combined_loss"]
        pair = cp[fields].rename(columns={"sir": "sir_cp", "brier_loss": "brier_loss_cp", "combined_loss": "combined_loss_cp"}).merge(
            other[["case_id", "sir", "brier_loss", "combined_loss"]].rename(columns={"sir": "sir_other", "brier_loss": "brier_loss_other", "combined_loss": "combined_loss_other"}), on="case_id", validate="one_to_one"
        )
        pair["delta_log_sir"] = np.log(pair["sir_cp"] + EPS) - np.log(pair["sir_other"] + EPS)
        for loss_index, loss_kind in enumerate(["combined", "brier_only"]):
            pair["delta_loss"] = pair[f"{loss_kind.replace('_only', '')}_loss_cp"] - pair[f"{loss_kind.replace('_only', '')}_loss_other"]
            pair["target"] = -pair["delta_loss"]
            result = association_bootstrap(pair, n_boot, SEED + 500 + index * 10 + loss_index)
            result.update({"comparator": comparator, "loss_kind": loss_kind, "n_cases": len(pair), "bootstrap": n_boot})
            result["pass"] = bool(result["spearman_ci_low"] > 0.0 and result["beta_ci_low"] > 0.0)
            rows.append(result)
        if comparator == "DLP2-NC":
            pair["delta_loss"] = pair["combined_loss_cp"] - pair["combined_loss_other"]
            pair["target"] = -pair["delta_loss"]
            scatter_primary = pair.copy()
    association = pd.DataFrame(rows)
    passed = bool(association["pass"].all())
    gate = {"gate": "G4", "pass": passed, "verdict": "PHYSICAL_TO_SENSING_ASSOCIATION_SUPPORTED" if passed else "NOT_ESTABLISHED_NONCIRCULAR_BRIDGE", "association_cells_passed": int(association["pass"].sum()), "association_cells_required": 4}
    return association, gate, scatter_primary


def gate_g5(config: dict[str, Any], g2: dict[str, Any], g3: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not (g2["pass"] and g3["pass"]):
        table = pd.DataFrame([{"required_arm": "DLP2-NC", "available": False, "reason": "G2_AND_G3_PREREQUISITES_NOT_BOTH_PASS"}])
        return table, {"gate": "G5", "pass": False, "verdict": "SKIPPED_PREREQUISITE"}
    robustness = pd.read_csv(resolve_path(config["inputs"]["robustness_oof_table"]), usecols=["arm", "snr_db", "quant_contract"])
    arms = set(robustness["arm"].astype(str))
    required = config["receiver_arms"]["DLP2-NC"]["feature_arm"]
    available = required in arms
    table = pd.DataFrame([{"required_arm": required, "available": available, "available_arms": "|".join(sorted(arms)), "snr_cells": robustness["snr_db"].nunique(), "quant_cells": robustness["quant_contract"].nunique()}])
    return table, {"gate": "G5", "pass": False, "verdict": "NOT_RUN_MISSING_MATCHED_DLP2_ROBUSTNESS" if not available else "READY_NOT_IMPLEMENTED"}


def gate_g6(config: dict[str, Any]) -> tuple[pd.DataFrame, dict[str, Any]]:
    blocker = pd.read_csv(resolve_path(config["inputs"]["m1_blocker_table"]))
    required = pd.read_csv(resolve_path(config["inputs"]["m1_required_contract"]))
    passed = blocker["verdict"].astype(str).eq("PASS").all() and required["status"].astype(str).eq("PRESENT").all()
    table = pd.DataFrame([{"m1_gate_rows": len(blocker), "required_fields": len(required), "present_fields": int(required["status"].astype(str).eq("PRESENT").sum()), "m1_pass": passed, "source_blocker_verdicts": "|".join(sorted(blocker["verdict"].astype(str).unique()))}])
    return table, {"gate": "G6", "pass": bool(passed), "verdict": "MEASUREMENT_PROMOTION_SUPPORTED" if passed else "BLOCKED_M1_MEASUREMENT"}


def physical_summary(physical: pd.DataFrame, n_boot: int) -> pd.DataFrame:
    rows = []
    for index, (arm, group) in enumerate(physical.groupby("arm")):
        for metric in ["direct_power", "r_phys", "sir"]:
            estimate, low, high = cluster_median_ci(group, metric, n_boot, SEED + 700 + index)
            rows.append({"arm": arm, "metric": metric, "median": estimate, "ci_low": low, "ci_high": high, "n_cases": len(group), "n_clusters": group["physical_cluster_id"].nunique(), "bootstrap": n_boot})
    return pd.DataFrame(rows)


def make_figures(physical: pd.DataFrame, curve: pd.DataFrame, scatter: pd.DataFrame, figures: Path) -> list[Path]:
    outputs = []
    fig, ax = plt.subplots(figsize=(7, 5))
    for arm, color in [("CP2", "#d95f02"), ("DLP2-NC", "#1b9e77"), ("DLP2-XPOL", "#7570b3")]:
        values = np.sort(np.log10(physical.loc[physical["arm"].eq(arm), "r_phys"].clip(lower=EPS).to_numpy(float)))
        ax.plot(values, np.linspace(0, 1, len(values), endpoint=True), label=arm, color=color)
    ax.axvline(0.0, color="black", linestyle="--", linewidth=1)
    ax.set(xlabel="log10(r_phys)", ylabel="ECDF", title="Physical contamination ratio")
    ax.legend(); ax.grid(alpha=0.25); fig.tight_layout()
    path = figures / "physical_ratio_ecdf.png"; fig.savefig(path, dpi=180); plt.close(fig); outputs.append(path)

    view = curve.loc[curve["dirty_threshold"].eq(1.0)]
    fig, ax = plt.subplots(figsize=(7, 5))
    for arm, group in view.groupby("arm"):
        ax.plot(group["retained_fraction"], group["retained_dirty_rate"], marker="o", label=arm)
    ax.set(xlabel="Retained fraction", ylabel="Retained dirty rate", title="Frozen q_clean risk coverage")
    ax.legend(); ax.grid(alpha=0.25); fig.tight_layout()
    path = figures / "risk_coverage_cp_vs_duallp.png"; fig.savefig(path, dpi=180); plt.close(fig); outputs.append(path)

    fig, ax = plt.subplots(figsize=(7, 5))
    sample = scatter.sample(min(3000, len(scatter)), random_state=SEED) if len(scatter) else scatter
    ax.scatter(sample.get("delta_log_sir", []), sample.get("target", []), s=8, alpha=0.25)
    ax.axhline(0.0, color="black", linewidth=0.8); ax.axvline(0.0, color="black", linewidth=0.8)
    ax.set(xlabel="delta log SIR (CP2 - DLP2-NC)", ylabel="-delta loss", title="Physical-to-sensing association diagnostic")
    ax.grid(alpha=0.25); fig.tight_layout()
    path = figures / "bridge_delta_scatter.png"; fig.savefig(path, dpi=180); plt.close(fig); outputs.append(path)
    return outputs


def final_interpretation(gates: dict[str, dict[str, Any]]) -> str:
    g2, g3, g4 = gates["G2"], gates["G3"], gates["G4"]
    if g2["pass"] and g3["pass"] and g4["pass"]:
        return "CP_PHYSICS_CONDITIONED_SENSING_SUPPORTED_SCOPED_SIMULATION"
    if g2["pass"] and g3["pass"]:
        return "SYSTEM_BENEFIT_OBSERVED_PHYSICAL_BRIDGE_NOT_ESTABLISHED"
    if g2["pass"]:
        return "PHYSICAL_BENEFIT_ONLY_NO_SENSING_SUPERIORITY"
    if g3["pass"]:
        return "OPERATIONAL_DIFFERENCE_WITHOUT_CP_PHYSICS_CLAIM"
    return "CP_SPECIFIC_END_TO_END_SENSING_SUPERIORITY_NOT_ESTABLISHED"


def markdown_report(
    output_root: Path, physical_summary_table: pd.DataFrame, g2_table: pd.DataFrame,
    differences: pd.DataFrame, association: pd.DataFrame, gates: dict[str, dict[str, Any]],
    interpretation: str, n_boot: int,
) -> str:
    pooled = g2_table.loc[g2_table["scope"].eq("pooled")]
    r = pooled.loc[pooled["metric"].eq("r_phys_ratio_cp_over_dlp")].iloc[0]
    sir = pooled.loc[pooled["metric"].eq("sir_ratio_cp_over_dlp")].iloc[0]
    primary = differences.loc[differences["retained_fraction"].isin([0.8, 0.9])]
    lines = [
        "# N3 CP Physics-Conditioned Sensing Bridge",
        "", "## Final verdict", "",
        f"- Integrated interpretation: `{interpretation}`",
        *[f"- {gate}: `{item['verdict']}`" for gate, item in gates.items()],
        "", "This is simulation-only, backend-independent session-quality sensing evidence. It is not measurement, hardware, range-error reduction, or position-integrity evidence.",
        "", "## G2 physical conditioning", "",
        f"- CP2/DLP2-NC median r_phys ratio: `{r['median']:.6g}`; cluster-bootstrap CI `[{r['ci_low']:.6g}, {r['ci_high']:.6g}]`.",
        f"- CP2/DLP2-NC median SIR ratio: `{sir['median']:.6g}`; cluster-bootstrap CI `[{sir['ci_low']:.6g}, {sir['ci_high']:.6g}]`.",
        f"- Bootstrap: `{n_boot}` physical-cluster resamples.",
        "", "## G3 frozen q_clean operational consumption", "",
    ]
    for _, row in primary.iterrows():
        lines.append(f"- retention `{row['retained_fraction']:.2f}`: dirty-rate delta CP-DLP `{row['dirty_diff']:.6g}` CI `[{row['dirty_ci_low']:.6g}, {row['dirty_ci_high']:.6g}]`; clean-yield delta `{row['yield_diff']:.6g}` CI `[{row['yield_ci_low']:.6g}, {row['yield_ci_high']:.6g}]`.")
    lines.extend(["", "## G4 association diagnostic", ""])
    for _, row in association.iterrows():
        lines.append(f"- `{row['comparator']}` / `{row['loss_kind']}`: Spearman `{row['spearman']:.6g}` CI `[{row['spearman_ci_low']:.6g}, {row['spearman_ci_high']:.6g}]`; fixed-effect beta `{row['fixed_effect_beta']:.6g}` CI `[{row['beta_ci_low']:.6g}, {row['beta_ci_high']:.6g}]`.")
    lines.extend([
        "", "The G4 diagnostic is associational, not causal. PASS requires both the preregistered combined loss and a non-circular Brier-only sensitivity check, because combined loss contains r_phys and is mechanically coupled to SIR.",
        "", "## G5/G6 limitations", "",
        f"- G5: `{gates['G5']['verdict']}`. The available SNR×quant replay lacks the matched DLP2-NC arm when this gate is blocked.",
        f"- G6: `{gates['G6']['verdict']}`. Existing M1 tables are preregistration/blocker artifacts, not completed same-aperture measurement evidence.",
        "", "## Claim boundary", "",
        "- `q_clean` remains a clean-session/session-quality confidence score.",
        "- Physical-risk outcomes were downstream evaluation endpoints and were not used as training labels.",
        "- Do not claim that CP directly reduces range error or that simulation proves same-aperture hardware superiority.",
        f"- Result package: `{rel(output_root)}`.",
    ])
    return "\n".join(lines) + "\n"


def append_csv_row(path: Path, row: dict[str, Any], key: str) -> None:
    current = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=list(row))
    if key in current.columns:
        current = current.loc[~current[key].astype(str).eq(str(row[key]))]
    pd.concat([current, pd.DataFrame([row])], ignore_index=True).to_csv(path, index=False)


def run_remaining_stages(
    config_path: Path, output_root: Path | None, smoke: bool, bootstrap_override: int | None
) -> int:
    config = load_config(config_path)
    stage = "smoke" if smoke else "full"
    default_bootstrap = int(config["future_gates"]["smoke_bootstrap" if smoke else "final_bootstrap"])
    n_boot = int(bootstrap_override or default_bootstrap)
    if not smoke and n_boot < 2000:
        raise ValueError("Final run requires at least 2000 bootstrap resamples")
    root = output_root or ROOT / "results" / f"n3_cp_physics_conditioned_sensing_bridge_{stage}_{timestamp_tag()}"
    dirs = ensure_output(root)
    shutil.copy2(config_path, dirs["configs"] / config_path.name)

    path_frame, feature, split, path_sources = read_physical_inputs(config)
    physical = materialize_physical_metrics(path_frame, feature, split, config)
    summary = physical_summary(physical, n_boot)
    paired_g2, g2_table, g2_gate = build_g2(physical, n_boot)
    oof = load_oof_by_arm(config)
    curve, differences, caps, g3_gate, arm_frames = build_g3(physical, oof, config, n_boot)
    association, g4_gate, scatter = build_g4(arm_frames, config, n_boot)
    robustness, g5_gate = gate_g5(config, g2_gate, g3_gate)
    measurement, g6_gate = gate_g6(config)
    gates = {item["gate"]: item for item in [g2_gate, g3_gate, g4_gate, g5_gate, g6_gate]}
    interpretation = final_interpretation(gates)
    figures = make_figures(physical, curve, scatter, dirs["figures"])

    gate_table = pd.DataFrame([{**item, "integrated_interpretation": interpretation} for item in gates.values()])
    claim_table = pd.DataFrame([{
        "claim": "CP physics-conditioned end-to-end sensing superiority over matched DLP2-NC",
        "verdict": interpretation,
        "allowed_scope": "simulation-only backend-independent q_clean session-quality sensing",
        "forbidden": "range-error guarantee|position integrity|hardware superiority|causal mediation",
        "measurement_status": g6_gate["verdict"],
    }])
    tables = {
        "physical_metric_by_case.csv.gz": physical,
        "physical_metric_summary.csv": summary,
        "physical_metric_by_stratum.csv": g2_table,
        "g2_paired_physical_ratio.csv.gz": paired_g2,
        "qclean_operating_curve.csv": curve,
        "qclean_pairwise_difference.csv": differences,
        "fixed_risk_cap.csv": caps,
        "bridge_association.csv": association,
        "robustness_availability.csv": robustness,
        "measurement_availability.csv": measurement,
        "gate_summary.csv": gate_table,
        "claim_boundary.csv": claim_table,
    }
    for name, frame in tables.items():
        frame.to_csv(dirs["tables"] / name, index=False, compression="gzip" if name.endswith(".gz") else None)

    report_text = markdown_report(root, summary, g2_table, differences, association, gates, interpretation, n_boot)
    package_report = dirs["reports"] / "N3_CP_PHYSICS_CONDITIONED_SENSING_BRIDGE.md"
    package_report.write_text(report_text, encoding="utf-8")
    external_report = ROOT / "reports" / "common" / f"N3_CP_PHYSICS_CONDITIONED_SENSING_BRIDGE_{root.name.rsplit('_', 2)[-2]}_{root.name.rsplit('_', 1)[-1]}.md"
    if not smoke:
        external_report.write_text(report_text, encoding="utf-8")

    run_card = "\n".join([
        "# N3 Bridge Run Card", "", f"- stage: `{stage}`", f"- bootstrap: `{n_boot}`",
        f"- interpretation: `{interpretation}`", *[f"- {name}: `{gate['verdict']}`" for name, gate in gates.items()],
        "", "Scientific boundaries: simulation-only; q_clean is session-quality confidence; G6 requires M1 measurement.",
    ]) + "\n"
    (dirs["root"] / "RUN_CARD.md").write_text(run_card, encoding="utf-8")
    (dirs["logs"] / "run.log").write_text(f"created_at_utc={utc_now()}\nstage={stage}\nbootstrap={n_boot}\ninterpretation={interpretation}\n", encoding="utf-8")

    input_paths = [*path_sources]
    for name, value in config["inputs"].items():
        if name not in {"path_glob", "fullffd_root"}:
            input_paths.append(resolve_path(value))
    source_lineage = pd.DataFrame([{"input": rel(path), "bytes": path.stat().st_size, "sha256": sha256_file(path), "read_only": True} for path in input_paths])
    source_lineage.to_csv(dirs["tables"] / "source_lineage.csv", index=False)

    manifest = {
        "schema_version": "n3_cp_physics_conditioned_sensing_bridge_full.v1",
        "created_at_utc": utc_now(), "stage": stage, "command": " ".join(sys.argv),
        "python": platform.python_version(), "platform": platform.platform(),
        "config": rel(config_path), "config_sha256": sha256_file(config_path), "seed": int(config["seed"]),
        "bootstrap": n_boot, "inputs": [rel(path) for path in input_paths],
        "gates": gates, "integrated_interpretation": interpretation,
        "claim_boundary": config["claim_boundary"],
        "outputs": [], "external_outputs": [rel(external_report)] if not smoke else [],
    }
    manifest_path = dirs["configs"] / "RUN_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    output_files = sorted(path for path in dirs["root"].rglob("*") if path.is_file())
    manifest["outputs"] = [rel(path) for path in output_files]
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    checksum_files = sorted(path for path in dirs["root"].rglob("*") if path.is_file() and path.name != "CHECKSUMS_SHA256.csv")
    pd.DataFrame([{"file": rel(path), "sha256": sha256_file(path), "bytes": path.stat().st_size} for path in checksum_files]).to_csv(dirs["root"] / "CHECKSUMS_SHA256.csv", index=False)

    if not smoke:
        tag = root.name
        figure_records = [
            ("physical_ecdf", figures[0], "N3 CP2 versus matched DLP2 physical ratio ECDF", dirs["tables"] / "physical_metric_by_case.csv.gz"),
            ("risk_coverage", figures[1], "N3 q_clean dirty-risk versus retention comparison", dirs["tables"] / "qclean_operating_curve.csv"),
            ("bridge_scatter", figures[2], "N3 physical-to-sensing bridge delta association", dirs["tables"] / "bridge_association.csv"),
        ]
        for suffix, figure_path, role, provenance in figure_records:
            append_csv_row(
                ROOT / "data" / "manifests" / "figure_manifest.csv",
                {"figure_id": f"{tag}_{suffix}", "path": rel(figure_path), "status": "PRESENT", "source_package": rel(root), "figure_role": role, "table_provenance": rel(provenance), "required_action": ""},
                "figure_id",
            )
        append_csv_row(
            ROOT / "data" / "manifests" / "report_manifest.csv",
            {"report_id": tag, "path": rel(external_report), "status": "PRESENT", "report_role": "N3 matched CP-dual-LP physics-conditioned sensing bridge", "source_package": rel(root), "table_refs": rel(dirs["tables"] / "gate_summary.csv"), "figure_refs": ";".join(rel(path) for path in figures), "required_action": "M1 measurement required for hardware promotion"},
            "report_id",
        )
        index_path = ROOT / "reports" / "common" / "RESULTS_INDEX.md"
        index_line = f"| N3 CP physics-conditioned bridge | {rel(dirs['tables'] / 'gate_summary.csv')} | {rel(external_report)} | {interpretation} |"
        index_text = index_path.read_text(encoding="utf-8")
        if index_line not in index_text:
            index_path.write_text(index_text.rstrip() + "\n" + index_line + "\n", encoding="utf-8")

    print(json.dumps({"output": rel(root), "report": rel(external_report) if not smoke else rel(package_report), "gates": {name: gate["verdict"] for name, gate in gates.items()}, "integrated_interpretation": interpretation}, ensure_ascii=False))
    return 0
