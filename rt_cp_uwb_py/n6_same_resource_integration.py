"""Reusable N6 same-resource simulation gates.

This module keeps three questions separate:

* A: detector-free, path-level physical conditioning;
* B: frozen, leakage-free session-quality sensing under matched feature budgets;
* C: retention policy utility against an independent frozen range residual.

``q_clean`` is always a clean-session/session-quality score.  It is never
interpreted here as a calibrated range-error probability or a guarantee of a
small range error.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


EPS = 1.0e-15
DEFAULT_SEED = 20260713
PRIMARY_RETENTION = 0.90
SENSITIVITY_RETENTION = 0.80

CP_H00_POWER = "cp_rr_power_mid_linear"
CP_H10_POWER = "cp_lr_power_mid_linear"
LP_H00_POWER = "lp_hh_power_mid_linear"
LP_H10_POWER = "lp_vh_power_mid_linear"


@dataclass(frozen=True)
class MarginContract:
    """Pre-registered margins needed for confirmatory B1 and C90 gates."""

    delta_b: float | None
    delta_y: float | None

    @property
    def frozen(self) -> bool:
        return (
            self.delta_b is not None
            and self.delta_y is not None
            and math.isfinite(self.delta_b)
            and math.isfinite(self.delta_y)
            and self.delta_b >= 0.0
            and self.delta_y >= 0.0
        )


def stable_hash(seed: int, *values: object) -> str:
    payload = "|".join([str(seed), *(str(value) for value in values)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def percentile_ci(values: Iterable[float]) -> tuple[float, float]:
    array = np.asarray(list(values), dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        return math.nan, math.nan
    return float(np.quantile(array, 0.025)), float(np.quantile(array, 0.975))


def safe_auc(y: Sequence[float], score: Sequence[float]) -> float:
    y_array = np.asarray(y, dtype=float)
    score_array = np.asarray(score, dtype=float)
    mask = np.isfinite(y_array) & np.isfinite(score_array)
    if int(mask.sum()) < 2 or np.unique(y_array[mask]).size != 2:
        return math.nan
    return float(roc_auc_score(y_array[mask], score_array[mask]))


def safe_spearman(y: Sequence[float], score: Sequence[float]) -> float:
    y_array = np.asarray(y, dtype=float)
    score_array = np.asarray(score, dtype=float)
    mask = np.isfinite(y_array) & np.isfinite(score_array)
    if int(mask.sum()) < 3 or np.unique(y_array[mask]).size < 2 or np.unique(score_array[mask]).size < 2:
        return math.nan
    return float(spearmanr(y_array[mask], score_array[mask]).statistic)


def ece_binary(y: Sequence[float], probability: Sequence[float], bins: int = 10) -> float:
    y_array = np.asarray(y, dtype=float)
    p_array = np.asarray(probability, dtype=float)
    mask = np.isfinite(y_array) & np.isfinite(p_array)
    y_array = y_array[mask]
    p_array = np.clip(p_array[mask], 0.0, 1.0)
    if not len(y_array):
        return math.nan
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = len(y_array)
    value = 0.0
    for index in range(bins):
        member = (p_array >= edges[index]) & (
            p_array < edges[index + 1] if index < bins - 1 else p_array <= edges[index + 1]
        )
        if member.any():
            value += float(member.sum()) / total * abs(float(p_array[member].mean()) - float(y_array[member].mean()))
    return float(value)


def validate_state_contract(config: Mapping[str, Any], feature_columns: Iterable[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Audit the raw-index state contract without interpreting CP hand names."""

    materialization = dict(config.get("materialization", {}))
    tensor_order = list(materialization.get("tensor_order", []))
    states = dict(materialization.get("states", {}))
    primary_state = dict(materialization.get("primary_state", {}))
    secondary_state = dict(materialization.get("secondary_state", {}))
    forbidden_state = dict(materialization.get("forbidden_primary_comparator_state", {}))
    primary = list(states.get("primary", [primary_state.get("rx_index"), primary_state.get("tx_index")]))
    secondary = list(states.get("secondary", [secondary_state.get("rx_index"), secondary_state.get("tx_index")]))
    forbidden = list(states.get("forbidden", [forbidden_state.get("rx_index"), forbidden_state.get("tx_index")]))
    state_rows = [
        {
            "logical_state": "H00",
            "rx_index": 0,
            "tx_index": 0,
            "role": "primary",
            "cp_channel": "RR raw index",
            "lp_channel": "XX/HH raw index",
        },
        {
            "logical_state": "H10",
            "rx_index": 1,
            "tx_index": 0,
            "role": "secondary",
            "cp_channel": "LR raw index",
            "lp_channel": "YX/VH raw index",
        },
        {
            "logical_state": "H11",
            "rx_index": 1,
            "tx_index": 1,
            "role": "forbidden_primary_comparator",
            "cp_channel": "LL raw index",
            "lp_channel": "YY/VV raw index",
        },
    ]
    columns = set(feature_columns)
    checks = [
        {
            "criterion": "tensor_order_rx_tx_freq",
            "observed": repr(tensor_order),
            "expected": "['rx', 'tx', 'freq']",
            "pass": tensor_order == ["rx", "tx", "freq"],
        },
        {
            "criterion": "primary_is_H00",
            "observed": repr(primary),
            "expected": "[0, 0]",
            "pass": primary == [0, 0],
        },
        {
            "criterion": "secondary_is_H10_fixed_tx",
            "observed": repr(secondary),
            "expected": "[1, 0]",
            "pass": secondary == [1, 0],
        },
        {
            "criterion": "H11_explicitly_forbidden",
            "observed": repr(forbidden),
            "expected": "[1, 1]",
            "pass": forbidden == [1, 1],
        },
        {
            "criterion": "no_H11_materialized_feature",
            "observed": sorted(column for column in columns if "h11" in column.lower()),
            "expected": "[]",
            "pass": not any("h11" in column.lower() for column in columns),
        },
        {
            "criterion": "both_arms_have_H00_H10_features",
            "observed": {
                prefix: any(column.startswith(prefix) for column in columns)
                for prefix in ["cp_h00_", "cp_h10_", "lp_h00_", "lp_h10_"]
            },
            "expected": "all true",
            "pass": all(any(column.startswith(prefix) for column in columns) for prefix in ["cp_h00_", "cp_h10_", "lp_h00_", "lp_h10_"]),
        },
    ]
    return pd.DataFrame(state_rows), pd.DataFrame(checks)


def matched_feature_pools(columns: Iterable[str]) -> dict[str, list[str]]:
    """Return isomorphic CP/DLP pools, dropping descriptors absent from either arm."""

    columns = sorted(set(columns))
    cp_map: dict[str, str] = {}
    lp_map: dict[str, str] = {}
    for column in columns:
        if column.startswith("cp_h00_"):
            cp_map[f"h00:{column[len('cp_h00_'):]}"] = column
        elif column.startswith("cp_h10_"):
            cp_map[f"h10:{column[len('cp_h10_'):]}"] = column
        elif column.startswith("cp_pair_"):
            cp_map[f"pair:{column[len('cp_pair_'):]}"] = column
        elif column.startswith("lp_h00_"):
            lp_map[f"h00:{column[len('lp_h00_'):]}"] = column
        elif column.startswith("lp_h10_"):
            lp_map[f"h10:{column[len('lp_h10_'):]}"] = column
        elif column.startswith("lp_pair_"):
            lp_map[f"pair:{column[len('lp_pair_'):]}"] = column
    common = sorted(set(cp_map) & set(lp_map))
    h00 = sorted(key for key in common if key.startswith("h00:"))
    return {
        "cp_fixed": [cp_map[key] for key in common],
        "dlp_fixed": [lp_map[key] for key in common],
        "lp1": [lp_map[key] for key in h00],
        "descriptor_keys": common,
    }


def coerce_dirty_label(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.notna().all() and set(numeric.astype(int).unique()).issubset({0, 1}):
        return numeric.astype(int)
    normalized = values.astype("string").str.strip().str.lower().str.replace("-", "_", regex=False)
    mapping = {
        "0": 0,
        "false": 0,
        "clean": 0,
        "1": 1,
        "true": 1,
        "dirty": 1,
        "not_clean": 1,
        "nolos": 1,
        "no_los": 1,
        "rd_los": 1,
    }
    mapped = normalized.map(mapping)
    if mapped.isna().any():
        unknown = sorted(normalized.loc[mapped.isna()].dropna().unique().tolist())
        raise ValueError(f"Unsupported dirty-label values: {unknown[:10]}")
    return mapped.astype(int)


def rank_features(x: pd.DataFrame, y: np.ndarray, candidates: Sequence[str], budget: int) -> list[str]:
    scores: dict[str, float] = {}
    for column in candidates:
        score = safe_spearman(y, pd.to_numeric(x[column], errors="coerce").to_numpy(float))
        scores[column] = abs(score) if math.isfinite(score) else -1.0
    selected = sorted(candidates, key=lambda column: (-scores[column], column))[:budget]
    if len(selected) != budget:
        raise ValueError(f"Feature pool has {len(selected)} usable descriptors; exact budget {budget} is required")
    return selected


def _model(c_value: float) -> Any:
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(C=float(c_value), solver="liblinear", penalty="l2", max_iter=2000, random_state=DEFAULT_SEED),
    )


def cluster_block_permutation(frame: pd.DataFrame, target: str, cluster: str, seed: int) -> np.ndarray:
    """Permute complete target vectors only among equal-size clusters."""

    rng = np.random.default_rng(seed)
    output = pd.to_numeric(frame[target], errors="raise").to_numpy(int).copy()
    groups: dict[int, list[np.ndarray]] = {}
    for _, group in frame.groupby(cluster, sort=True):
        groups.setdefault(len(group), []).append(group.index.to_numpy(int))
    original = output.copy()
    for blocks in groups.values():
        if len(blocks) < 2:
            continue
        order = rng.permutation(len(blocks))
        for destination, source in enumerate(order):
            output[blocks[destination]] = original[blocks[source]]
    return output


def fit_matched_oof(
    frame: pd.DataFrame,
    feature_pools: Mapping[str, Sequence[str]],
    *,
    target_col: str,
    fold_col: str,
    cluster_col: str,
    case_col: str = "case_id",
    feature_budget: int = 15,
    c_value: float = 1.0,
    seed: int = DEFAULT_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit frozen outer-fold OOF q_clean scores with fold-local selection."""

    required_arms = ["cp_fixed", "dlp_fixed"]
    missing = [arm for arm in required_arms if arm not in feature_pools]
    if missing:
        raise ValueError(f"Missing feature pools: {missing}")
    y = coerce_dirty_label(frame[target_col]).to_numpy(int)
    predictions = {arm: np.full(len(frame), np.nan) for arm in required_arms}
    predictions["shuffle_null"] = np.full(len(frame), np.nan)
    trace: list[dict[str, Any]] = []
    folds = sorted(pd.to_numeric(frame[fold_col], errors="raise").astype(int).unique().tolist())

    work = frame.reset_index(drop=True).copy()
    for fold in folds:
        test = pd.to_numeric(work[fold_col], errors="raise").astype(int).eq(fold).to_numpy()
        train = ~test
        train_idx = np.flatnonzero(train)
        test_idx = np.flatnonzero(test)
        train_clusters = set(work.iloc[train_idx][cluster_col].astype(str))
        test_clusters = set(work.iloc[test_idx][cluster_col].astype(str))
        overlap = len(train_clusters & test_clusters)
        if overlap:
            raise ValueError(f"Outer fold {fold} leaks {overlap} clusters")
        if np.unique(y[train_idx]).size != 2:
            raise ValueError(f"Outer fold {fold} training target has fewer than two classes")

        for arm in required_arms:
            candidates = list(feature_pools[arm])
            selected = rank_features(work.iloc[train_idx], y[train_idx], candidates, feature_budget)
            model = _model(c_value)
            model.fit(work.iloc[train_idx][selected], y[train_idx])
            p_dirty = model.predict_proba(work.iloc[test_idx][selected])[:, list(model[-1].classes_).index(1)]
            predictions[arm][test_idx] = 1.0 - p_dirty
            trace.append(
                {
                    "fold_id": int(fold),
                    "arm": arm,
                    "candidate_n_features": len(candidates),
                    "selected_n_features": len(selected),
                    "selected_features": ";".join(selected),
                    "feature_budget": feature_budget,
                    "train_rows": len(train_idx),
                    "test_rows": len(test_idx),
                    "train_clusters": len(train_clusters),
                    "test_clusters": len(test_clusters),
                    "train_test_cluster_overlap": overlap,
                    "model": f"imputer+scaler+logistic_l2_C={c_value}",
                }
            )

        shuffle_train = work.iloc[train_idx].copy().reset_index(drop=True)
        shuffle_train[target_col] = y[train_idx]
        y_shuffle = cluster_block_permutation(
            shuffle_train,
            target=target_col,
            cluster=cluster_col,
            seed=seed + int(fold),
        )
        candidates = list(feature_pools["cp_fixed"])
        selected = rank_features(shuffle_train, y_shuffle, candidates, feature_budget)
        null_model = _model(c_value)
        null_model.fit(shuffle_train[selected], y_shuffle)
        p_dirty = null_model.predict_proba(work.iloc[test_idx][selected])[:, list(null_model[-1].classes_).index(1)]
        predictions["shuffle_null"][test_idx] = 1.0 - p_dirty
        trace.append(
            {
                "fold_id": int(fold),
                "arm": "shuffle_null",
                "candidate_n_features": len(candidates),
                "selected_n_features": len(selected),
                "selected_features": ";".join(selected),
                "feature_budget": feature_budget,
                "train_rows": len(train_idx),
                "test_rows": len(test_idx),
                "train_clusters": len(train_clusters),
                "test_clusters": len(test_clusters),
                "train_test_cluster_overlap": overlap,
                "model": f"cluster-block-shuffled-target;imputer+scaler+logistic_l2_C={c_value}",
            }
        )

    if any(not np.isfinite(prediction).all() for prediction in predictions.values()):
        raise RuntimeError("OOF scoring did not cover every row")
    out = work[[case_col, cluster_col, fold_col]].copy()
    out["y_dirty"] = y
    out["q_clean_cp"] = predictions["cp_fixed"]
    out["q_clean_dlp"] = predictions["dlp_fixed"]
    out["q_clean_shuffle"] = predictions["shuffle_null"]
    return out, pd.DataFrame(trace)


def _metric_row(y_dirty: np.ndarray, q_clean: np.ndarray) -> dict[str, float]:
    p_dirty = 1.0 - np.asarray(q_clean, dtype=float)
    return {
        "auc": safe_auc(y_dirty, p_dirty),
        "brier": float(brier_score_loss(y_dirty, np.clip(p_dirty, 0.0, 1.0))),
        "ece": ece_binary(y_dirty, p_dirty),
    }


def sensing_cluster_bootstrap(
    oof: pd.DataFrame,
    *,
    cluster_col: str,
    n_boot: int,
    seed: int = DEFAULT_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    observed: list[dict[str, Any]] = []
    for arm, column in [("CP-fixed", "q_clean_cp"), ("DLP-fixed", "q_clean_dlp"), ("shuffle/null", "q_clean_shuffle")]:
        observed.append({"arm": arm, **_metric_row(oof["y_dirty"].to_numpy(int), oof[column].to_numpy(float))})
    groups = [group.index.to_numpy(int) for _, group in oof.groupby(cluster_col, sort=True)]
    rng = np.random.default_rng(seed)
    bootstrap_rows: list[dict[str, float | int]] = []
    for replicate in range(n_boot):
        chosen = rng.integers(0, len(groups), size=len(groups))
        index = np.concatenate([groups[position] for position in chosen])
        sample = oof.iloc[index]
        y = sample["y_dirty"].to_numpy(int)
        cp = _metric_row(y, sample["q_clean_cp"].to_numpy(float))
        dlp = _metric_row(y, sample["q_clean_dlp"].to_numpy(float))
        null = _metric_row(y, sample["q_clean_shuffle"].to_numpy(float))
        bootstrap_rows.append(
            {
                "replicate": replicate,
                "auc_cp": cp["auc"],
                "auc_dlp": dlp["auc"],
                "auc_shuffle": null["auc"],
                "delta_auc_cp_minus_dlp": cp["auc"] - dlp["auc"],
                "delta_auc_cp_minus_shuffle": cp["auc"] - null["auc"],
            }
        )
    return pd.DataFrame(observed), pd.DataFrame(bootstrap_rows)


def sensing_gate_table(
    metrics: pd.DataFrame,
    bootstrap: pd.DataFrame,
    *,
    margin: MarginContract,
    mode: str,
) -> pd.DataFrame:
    cp_auc = float(metrics.loc[metrics["arm"].eq("CP-fixed"), "auc"].iloc[0])
    dlp_auc = float(metrics.loc[metrics["arm"].eq("DLP-fixed"), "auc"].iloc[0])
    null_auc = float(metrics.loc[metrics["arm"].eq("shuffle/null"), "auc"].iloc[0])
    b0_low, b0_high = percentile_ci(bootstrap["delta_auc_cp_minus_shuffle"])
    b1_low, b1_high = percentile_ci(bootstrap["delta_auc_cp_minus_dlp"])
    confirmatory = mode == "full"
    b0_pass = confirmatory and math.isfinite(b0_low) and b0_low > 0.0
    if not confirmatory:
        b1_verdict = "NOT_RUN_CONFIRMATORY"
    elif margin.delta_b is None or not math.isfinite(margin.delta_b):
        b1_verdict = "BLOCKED_MARGIN_NOT_FROZEN"
    else:
        b1_verdict = "PASS" if b1_low > -margin.delta_b else "NOT_ESTABLISHED"
    return pd.DataFrame(
        [
            {
                "gate": "B0",
                "criterion": "L95(AUC_CP - AUC_cluster_block_shuffle) > 0",
                "value": cp_auc - null_auc,
                "ci_low": b0_low,
                "ci_high": b0_high,
                "margin": 0.0,
                "verdict": "PASS" if b0_pass else ("NOT_RUN_CONFIRMATORY" if not confirmatory else "NOT_ESTABLISHED"),
            },
            {
                "gate": "B1",
                "criterion": "L95(AUC_CP - AUC_DLP) > -delta_B",
                "value": cp_auc - dlp_auc,
                "ci_low": b1_low,
                "ci_high": b1_high,
                "margin": margin.delta_b,
                "verdict": b1_verdict,
            },
            {
                "gate": "B2",
                "criterion": "L95(AUC_CP - AUC_DLP) > 0; optional CP-specific sensing gate",
                "value": cp_auc - dlp_auc,
                "ci_low": b1_low,
                "ci_high": b1_high,
                "margin": 0.0,
                "verdict": "PASS" if confirmatory and b1_low > 0.0 else ("NOT_RUN_CONFIRMATORY" if not confirmatory else "NOT_ESTABLISHED"),
            },
        ]
    )


def physical_case_metrics(
    paths: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    bandwidth_hz: float,
    unresolved_window_b: float,
) -> pd.DataFrame:
    required = {
        "case_id",
        "path_index",
        "is_los",
        "path_delay_s",
        CP_H00_POWER,
        CP_H10_POWER,
        LP_H00_POWER,
        LP_H10_POWER,
    }
    missing = sorted(required - set(paths.columns))
    if missing:
        raise ValueError(f"Missing physical path columns: {missing}")
    frame = paths.copy()
    frame["case_id"] = frame["case_id"].astype(str)
    frame["_is_los"] = frame["is_los"].astype(str).str.lower().isin(["true", "1", "yes"])
    frame["_delay"] = pd.to_numeric(frame["path_delay_s"], errors="coerce")
    direct = (
        frame.loc[frame["_is_los"] & frame["_delay"].notna()]
        .sort_values(["case_id", "_delay", "path_index"])
        .drop_duplicates("case_id")
        .copy()
    )
    direct_delay = direct.set_index("case_id")["_delay"]
    frame["_direct_delay"] = frame["case_id"].map(direct_delay)
    frame["_dtau_b"] = (frame["_delay"] - frame["_direct_delay"]) * float(bandwidth_hz)
    late = frame.loc[
        frame["_direct_delay"].notna()
        & ~frame["_is_los"]
        & frame["_dtau_b"].between(-1e-9, float(unresolved_window_b), inclusive="both")
    ].copy()
    if late.empty:
        raise ValueError("No reflected paths in the configured physical window")
    meta = metadata.copy()
    meta["case_id"] = meta["case_id"].astype(str)
    rows: list[pd.DataFrame] = []
    arms = {
        "CP": (CP_H00_POWER, CP_H10_POWER),
        "DLP": (LP_H00_POWER, LP_H10_POWER),
    }
    for arm, (h00, h10) in arms.items():
        for scope, columns in [("A_primary_H00", [h00]), ("A_sensitivity_H00_H10", [h00, h10])]:
            direct_power = direct[columns].apply(pd.to_numeric, errors="coerce").clip(lower=0.0).sum(axis=1, min_count=len(columns))
            late_power = late[columns].apply(pd.to_numeric, errors="coerce").clip(lower=0.0).sum(axis=1, min_count=len(columns))
            d = pd.DataFrame({"case_id": direct["case_id"].to_numpy(), "direct_power": direct_power.to_numpy(float)})
            l = pd.DataFrame({"case_id": late["case_id"].to_numpy(), "late_power": late_power.to_numpy(float)}).groupby("case_id", as_index=False)["late_power"].sum(min_count=1)
            case = meta.merge(d, on="case_id", validate="one_to_one").merge(l, on="case_id", validate="one_to_one")
            case = case.loc[case["direct_power"].gt(0.0) & case["late_power"].ge(0.0)].copy()
            case["arm"] = arm
            case["scope"] = scope
            case["r_phys"] = (case["late_power"] + EPS) / (case["direct_power"] + EPS)
            case["sir_db"] = 10.0 * np.log10((case["direct_power"] + EPS) / (case["late_power"] + EPS))
            rows.append(case)
    return pd.concat(rows, ignore_index=True)


def physical_cluster_bootstrap(
    physical: pd.DataFrame,
    *,
    cluster_col: str,
    n_boot: int,
    seed: int = DEFAULT_SEED,
    mode: str = "full",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    pair_rows: list[pd.DataFrame] = []
    for scope, group in physical.groupby("scope", sort=True):
        cp = group.loc[group["arm"].eq("CP"), ["case_id", cluster_col, "r_phys", "sir_db"]].rename(
            columns={"r_phys": "r_phys_cp", "sir_db": "sir_db_cp"}
        )
        dlp = group.loc[group["arm"].eq("DLP"), ["case_id", "r_phys", "sir_db"]].rename(
            columns={"r_phys": "r_phys_dlp", "sir_db": "sir_db_dlp"}
        )
        pair = cp.merge(dlp, on="case_id", validate="one_to_one")
        pair["scope"] = scope
        pair["delta_log_r_phys"] = np.log(pair["r_phys_cp"] + EPS) - np.log(pair["r_phys_dlp"] + EPS)
        pair["delta_sir_db"] = pair["sir_db_cp"] - pair["sir_db_dlp"]
        pair_rows.append(pair)
    paired = pd.concat(pair_rows, ignore_index=True)
    rng = np.random.default_rng(seed)
    summary: list[dict[str, Any]] = []
    for scope, group in paired.groupby("scope", sort=True):
        clusters = group.groupby(cluster_col, sort=True)[["delta_log_r_phys", "delta_sir_db"]].median().reset_index()
        draws = rng.integers(0, len(clusters), size=(n_boot, len(clusters)))
        boot_r = np.median(clusters["delta_log_r_phys"].to_numpy(float)[draws], axis=1)
        boot_sir = np.median(clusters["delta_sir_db"].to_numpy(float)[draws], axis=1)
        r_low, r_high = percentile_ci(boot_r)
        sir_low, sir_high = percentile_ci(boot_sir)
        confirmatory = mode == "full" and scope == "A_primary_H00"
        summary.extend(
            [
                {
                    "scope": scope,
                    "metric": "delta_log_r_phys_cp_minus_dlp",
                    "value": float(np.median(clusters["delta_log_r_phys"])),
                    "ci_low": r_low,
                    "ci_high": r_high,
                    "n_clusters": len(clusters),
                    "verdict": "PASS" if confirmatory and r_high < 0.0 else ("NOT_RUN_CONFIRMATORY" if mode != "full" else "NOT_ESTABLISHED"),
                },
                {
                    "scope": scope,
                    "metric": "delta_sir_db_cp_minus_dlp",
                    "value": float(np.median(clusters["delta_sir_db"])),
                    "ci_low": sir_low,
                    "ci_high": sir_high,
                    "n_clusters": len(clusters),
                    "verdict": "SUPPORTING_DIRECTION" if sir_low > 0.0 else "NOT_ESTABLISHED_SUPPORTING_DIRECTION",
                },
            ]
        )
    return paired, pd.DataFrame(summary)


def aggregate_policy_clusters(
    frame: pd.DataFrame,
    *,
    cluster_col: str,
    q_cp_col: str,
    q_dlp_col: str,
    residual_col: str,
    dirty_threshold: float,
    clean_threshold: float,
) -> pd.DataFrame:
    work = frame[[cluster_col, q_cp_col, q_dlp_col, residual_col]].copy()
    work[residual_col] = pd.to_numeric(work[residual_col], errors="coerce")
    work = work.dropna(subset=[cluster_col, q_cp_col, q_dlp_col, residual_col])
    work["dirty"] = work[residual_col].abs().ge(float(dirty_threshold))
    work["strict_clean"] = work[residual_col].abs().lt(float(clean_threshold))
    return (
        work.groupby(cluster_col, sort=True)
        .agg(
            q_cp=(q_cp_col, "median"),
            q_dlp=(q_dlp_col, "median"),
            dirty_count=("dirty", "sum"),
            clean_count=("strict_clean", "sum"),
            n_rows=(residual_col, "size"),
        )
        .reset_index()
    )


def _select_top_clusters(sample: pd.DataFrame, score_col: str, fraction: float, seed: int, arm: str) -> set[str]:
    if not 0.0 < fraction < 1.0:
        raise ValueError("Retention fraction must be between zero and one")
    n_keep = max(1, int(math.ceil(len(sample) * fraction)))
    ranked = sample.copy()
    ranked["_tie"] = [stable_hash(seed, arm, cluster) for cluster in ranked["_sample_cluster_id"]]
    ranked = ranked.sort_values([score_col, "_tie"], ascending=[False, True])
    return set(ranked.head(n_keep)["_sample_cluster_id"].astype(str))


def _deterministic_top_indices(
    scores: Sequence[float],
    sample_ids: Sequence[str],
    fraction: float,
    seed: int,
    arm: str,
) -> np.ndarray:
    """Vectorized top-r selection with the exact registered hash tie-break.

    Only the score group crossing the retention boundary needs hashing.  This
    preserves :func:`_select_top_clusters` semantics for distinct clusters
    with identical scores while avoiding a full stable sort per bootstrap.
    """

    if not 0.0 < fraction < 1.0:
        raise ValueError("Retention fraction must be between zero and one")
    score_array = np.asarray(scores)
    id_array = np.asarray(sample_ids, dtype=str)
    if score_array.ndim != 1 or len(score_array) != len(id_array):
        raise ValueError("scores and sample_ids must be aligned one-dimensional arrays")
    if not len(score_array):
        return np.asarray([], dtype=int)
    if not np.isfinite(score_array.astype(float)).all():
        raise ValueError("Policy scores must be finite")
    n_keep = max(1, int(math.ceil(len(score_array) * fraction)))
    cutoff = np.partition(score_array, len(score_array) - n_keep)[len(score_array) - n_keep]
    above = np.flatnonzero(score_array > cutoff)
    tied = np.flatnonzero(score_array == cutoff)
    remaining = n_keep - len(above)
    if remaining < 0 or remaining > len(tied):
        raise RuntimeError("Invalid retention boundary partition")
    tie_order = sorted(
        tied.tolist(),
        key=lambda index: stable_hash(seed, arm, id_array[index]),
    )
    return np.asarray([*above.tolist(), *tie_order[:remaining]], dtype=int)


def _policy_metrics_arrays(
    *,
    sample_ids: Sequence[str],
    q_cp: Sequence[float],
    q_dlp: Sequence[float],
    dirty: Sequence[float],
    clean: Sequence[float],
    n_rows: Sequence[float],
    fraction: float,
    seed: int,
    random_scores: Sequence[int] | None = None,
) -> dict[str, Any]:
    """Numpy equivalent of :func:`policy_metrics`, including selections."""

    ids = np.asarray(sample_ids, dtype=str)
    cp_score = np.asarray(q_cp, dtype=float)
    dlp_score = np.asarray(q_dlp, dtype=float)
    dirty_array = np.asarray(dirty, dtype=float)
    clean_array = np.asarray(clean, dtype=float)
    rows_array = np.asarray(n_rows, dtype=float)
    if random_scores is None:
        random_score = np.asarray(
            [int(stable_hash(seed, "random", value)[:16], 16) for value in ids],
            dtype=np.uint64,
        )
    else:
        random_score = np.asarray(random_scores, dtype=np.uint64)
    cp_index = _deterministic_top_indices(cp_score, ids, fraction, seed, "CP")
    dlp_index = _deterministic_top_indices(dlp_score, ids, fraction, seed, "DLP")
    random_index = _deterministic_top_indices(random_score, ids, fraction, seed, "random")
    total_rows = float(rows_array.sum())

    def values(index: np.ndarray) -> tuple[float, float]:
        accepted_rows = float(rows_array[index].sum())
        risk = float(dirty_array[index].sum() / accepted_rows) if accepted_rows else math.nan
        clean_yield = float(clean_array[index].sum() / total_rows) if total_rows else math.nan
        return risk, clean_yield

    risk_cp, yield_cp = values(cp_index)
    risk_dlp, yield_dlp = values(dlp_index)
    risk_random, yield_random = values(random_index)
    cp_ids = set(ids[cp_index].tolist())
    dlp_ids = set(ids[dlp_index].tolist())
    random_ids = set(ids[random_index].tolist())
    union = cp_ids | dlp_ids
    return {
        "retained_fraction": fraction,
        "risk_cp": risk_cp,
        "risk_dlp": risk_dlp,
        "risk_random": risk_random,
        "yield_cp": yield_cp,
        "yield_dlp": yield_dlp,
        "yield_random": yield_random,
        "delta_risk_cp_minus_dlp": risk_cp - risk_dlp,
        "delta_yield_cp_minus_dlp": yield_cp - yield_dlp,
        "delta_risk_cp_minus_random": risk_cp - risk_random,
        "jaccard_cp_dlp": float(len(cp_ids & dlp_ids) / len(union)) if union else math.nan,
        "cp_retained_cluster_ids": ";".join(sorted(cp_ids)),
        "dlp_retained_cluster_ids": ";".join(sorted(dlp_ids)),
        "random_retained_cluster_ids": ";".join(sorted(random_ids)),
    }


def policy_metrics(sample: pd.DataFrame, fraction: float, seed: int) -> dict[str, Any]:
    cp_keep = _select_top_clusters(sample, "q_cp", fraction, seed, "CP")
    dlp_keep = _select_top_clusters(sample, "q_dlp", fraction, seed, "DLP")
    random_frame = sample.copy()
    random_frame["q_random"] = [int(stable_hash(seed, "random", value)[:16], 16) for value in random_frame["_sample_cluster_id"]]
    random_keep = _select_top_clusters(random_frame, "q_random", fraction, seed, "random")

    def arm_values(keep: set[str]) -> tuple[float, float]:
        accepted = sample.loc[sample["_sample_cluster_id"].astype(str).isin(keep)]
        accepted_rows = float(accepted["n_rows"].sum())
        total_rows = float(sample["n_rows"].sum())
        risk = float(accepted["dirty_count"].sum() / accepted_rows) if accepted_rows else math.nan
        clean_yield = float(accepted["clean_count"].sum() / total_rows) if total_rows else math.nan
        return risk, clean_yield

    risk_cp, yield_cp = arm_values(cp_keep)
    risk_dlp, yield_dlp = arm_values(dlp_keep)
    risk_random, yield_random = arm_values(random_keep)
    union = cp_keep | dlp_keep
    jaccard = float(len(cp_keep & dlp_keep) / len(union)) if union else math.nan
    return {
        "retained_fraction": fraction,
        "risk_cp": risk_cp,
        "risk_dlp": risk_dlp,
        "risk_random": risk_random,
        "yield_cp": yield_cp,
        "yield_dlp": yield_dlp,
        "yield_random": yield_random,
        "delta_risk_cp_minus_dlp": risk_cp - risk_dlp,
        "delta_yield_cp_minus_dlp": yield_cp - yield_dlp,
        "delta_risk_cp_minus_random": risk_cp - risk_random,
        "jaccard_cp_dlp": jaccard,
        "cp_retained_cluster_ids": ";".join(sorted(cp_keep)),
        "dlp_retained_cluster_ids": ";".join(sorted(dlp_keep)),
        "random_retained_cluster_ids": ";".join(sorted(random_keep)),
    }


def retention_cluster_bootstrap(
    clusters: pd.DataFrame,
    *,
    cluster_col: str,
    fractions: Sequence[float],
    n_boot: int,
    seed: int = DEFAULT_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = clusters.reset_index(drop=True).copy()
    base["_sample_cluster_id"] = base[cluster_col].astype(str)
    observed = pd.DataFrame([policy_metrics(base, float(fraction), seed) for fraction in fractions])
    rng = np.random.default_rng(seed)
    q_cp = pd.to_numeric(base["q_cp"], errors="raise").to_numpy(float)
    q_dlp = pd.to_numeric(base["q_dlp"], errors="raise").to_numpy(float)
    dirty = pd.to_numeric(base["dirty_count"], errors="raise").to_numpy(float)
    clean = pd.to_numeric(base["clean_count"], errors="raise").to_numpy(float)
    n_rows = pd.to_numeric(base["n_rows"], errors="raise").to_numpy(float)
    original_ids = base[cluster_col].astype(str).to_numpy()
    rows: list[dict[str, Any]] = []
    for replicate in range(n_boot):
        positions = rng.integers(0, len(base), size=len(base))
        drawn_ids = original_ids[positions]
        sample_ids = np.asarray(
            [f"{value}__draw{draw}" for draw, value in enumerate(drawn_ids)],
            dtype=str,
        )
        sample_q_cp = q_cp[positions]
        sample_q_dlp = q_dlp[positions]
        sample_dirty = dirty[positions]
        sample_clean = clean[positions]
        sample_n_rows = n_rows[positions]
        policy_seed = seed + replicate + 1
        random_score = np.asarray(
            [int(stable_hash(policy_seed, "random", value)[:16], 16) for value in sample_ids],
            dtype=np.uint64,
        )
        for fraction in fractions:
            values = _policy_metrics_arrays(
                sample_ids=sample_ids,
                q_cp=sample_q_cp,
                q_dlp=sample_q_dlp,
                dirty=sample_dirty,
                clean=sample_clean,
                n_rows=sample_n_rows,
                fraction=float(fraction),
                seed=policy_seed,
                random_scores=random_score,
            )
            rows.append({"replicate": replicate, **{key: value for key, value in values.items() if not key.endswith("cluster_ids")}})
    return observed, pd.DataFrame(rows)


def retention_power_gate(n_clusters: int, retention: float, minimum_excluded: int = 30, minimum_clusters: int = 300) -> pd.DataFrame:
    rejected_fraction = 1.0 - retention
    excluded = int(math.floor(n_clusters * rejected_fraction + 1.0e-9))
    required = max(int(minimum_clusters), int(math.ceil(minimum_excluded / rejected_fraction - 1.0e-9)))
    passed = n_clusters >= required and excluded >= minimum_excluded
    return pd.DataFrame(
        [
            {
                "gate": "POWER-C90",
                "n_clusters": n_clusters,
                "retention": retention,
                "expected_excluded_clusters": excluded,
                "minimum_excluded_clusters": minimum_excluded,
                "minimum_required_clusters": required,
                "verdict": "PASS" if passed else "BLOCKED_BY_POWER",
            }
        ]
    )


def retention_gate_table(
    observed: pd.DataFrame,
    bootstrap: pd.DataFrame,
    *,
    margin: MarginContract,
    power_pass: bool,
    mode: str,
    primary_retention: float = PRIMARY_RETENTION,
) -> pd.DataFrame:
    primary = observed.loc[np.isclose(observed["retained_fraction"], primary_retention)].iloc[0]
    boot = bootstrap.loc[np.isclose(bootstrap["retained_fraction"], primary_retention)]
    risk_low, risk_high = percentile_ci(boot["delta_risk_cp_minus_dlp"])
    yield_low, yield_high = percentile_ci(boot["delta_yield_cp_minus_dlp"])
    random_low, random_high = percentile_ci(boot["delta_risk_cp_minus_random"])
    confirmatory = mode == "full" and power_pass
    if not confirmatory:
        base_verdict = "BLOCKED_BY_POWER" if mode == "full" and not power_pass else "NOT_RUN_CONFIRMATORY"
    else:
        base_verdict = "NOT_ESTABLISHED"
    risk_verdict = "PASS" if confirmatory and risk_high < 0.0 else base_verdict
    random_verdict = "PASS" if confirmatory and random_high < 0.0 else base_verdict
    if not confirmatory:
        yield_verdict = base_verdict
    elif margin.delta_y is None or not math.isfinite(margin.delta_y):
        yield_verdict = "BLOCKED_MARGIN_NOT_FROZEN"
    else:
        yield_verdict = "PASS" if yield_low > -margin.delta_y else "NOT_ESTABLISHED"
    return pd.DataFrame(
        [
            {
                "gate": "C90-risk",
                "criterion": "U95(R_dirty_CP90 - R_dirty_DLP90) < 0",
                "value": primary["delta_risk_cp_minus_dlp"],
                "ci_low": risk_low,
                "ci_high": risk_high,
                "margin": 0.0,
                "verdict": risk_verdict,
            },
            {
                "gate": "C90-yield",
                "criterion": "L95(Y_clean_CP90 - Y_clean_DLP90) > -delta_Y",
                "value": primary["delta_yield_cp_minus_dlp"],
                "ci_low": yield_low,
                "ci_high": yield_high,
                "margin": margin.delta_y,
                "verdict": yield_verdict,
            },
            {
                "gate": "C90-random",
                "criterion": "U95(R_dirty_CP90 - R_dirty_random90) < 0",
                "value": primary["delta_risk_cp_minus_random"],
                "ci_low": random_low,
                "ci_high": random_high,
                "margin": 0.0,
                "verdict": random_verdict,
            },
        ]
    )


def claim_truth_table(p0: str, power: str, a: str, b0: str, b1: str, c_risk: str, c_yield: str, b2: str) -> pd.DataFrame:
    integrated = all(value == "PASS" for value in [p0, power, a, b0, b1, c_risk, c_yield])
    if p0 != "PASS":
        result = "BLOCKED_RESOURCE_OR_EXTRACTION_FAIRNESS"
    elif a == "PASS" and (b0 != "PASS" or b1 != "PASS"):
        result = "SUPPORTED_PHYSICAL_SELECTIVITY_ONLY"
    elif integrated:
        result = "SUPPORTED_RETENTION_BASED_SAME_RESOURCE_INTEGRATED_ADVANTAGE"
    else:
        result = "SAME_RESOURCE_INTEGRATED_OPERATIONAL_ADVANTAGE_NOT_ESTABLISHED"
    sensing_scope = "CP_SPECIFIC" if b2 == "PASS" else "DUAL_POL_GENERAL_OR_NOT_ESTABLISHED"
    return pd.DataFrame(
        [
            {
                "P0": p0,
                "Power": power,
                "A_primary": a,
                "B0": b0,
                "B1": b1,
                "B2_optional": b2,
                "C90_risk": c_risk,
                "C90_yield": c_yield,
                "retention_integrated_claim": result,
                "sensing_scope": sensing_scope,
                "q_clean_boundary": "clean-session/session-quality confidence; not calibrated range-error probability",
            }
        ]
    )
