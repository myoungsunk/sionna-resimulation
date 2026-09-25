from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np
import pandas as pd


SCOPE_PRIORITY: tuple[str, ...] = ("room_material_los", "room_material", "room", "pooled")
SCOPE_COLUMNS: dict[str, tuple[str, ...]] = {
    "room_material_los": ("room_type", "material", "los_label"),
    "room_material": ("room_type", "material"),
    "room": ("room_type",),
    "pooled": (),
}


@dataclass(frozen=True)
class LutSelectionConfig:
    N_min: int = 5
    N_ref: int = 20
    allow_ground_truth_los: bool = False
    fallback_to_pooled: bool = True
    theta_min_deg: float = 10.0
    theta_max_deg: float = 70.0
    theta_bin_deg: float = 5.0
    beta_bin_deg: float = 15.0
    nlos_score_threshold: float = 0.5
    residual_proxy_threshold_db: float | None = None


@dataclass(frozen=True)
class LutScopeSelection:
    chosen_scope: str
    train_n: int
    lut_support_weight: float
    reason: str
    meets_n_min: bool
    los_label_source: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "chosen_scope": self.chosen_scope,
            "train_n": self.train_n,
            "lut_support_weight": self.lut_support_weight,
            "reason": self.reason,
            "meets_n_min": self.meets_n_min,
            "los_label_source": self.los_label_source,
        }


def select_lut_scope(sample: Mapping[str, Any] | pd.Series, lut_stats: Any, cfg: LutSelectionConfig | Mapping[str, Any] | None = None) -> LutScopeSelection:
    """Select the most specific supported RSSD LUT scope.

    Production mode does not consume simulation ground-truth ``los_label``.
    Use ``estimated_los_label`` when present, or a proxy such as ``nlos_score``.
    Set ``allow_ground_truth_los=True`` only for simulation/analysis audits.
    """

    config = _coerce_cfg(cfg)
    row = _sample_dict(sample)
    stats = _stats_frame(lut_stats)
    if stats.empty:
        return _selection("pooled" if config.fallback_to_pooled else "none", 0, config, "no_lut_stats_available", False, "none")

    scoped_rows = _prepare_stats(stats)
    theta_center = _sample_theta_bin(row, config)
    beta_center = _sample_beta_bin(row, config)
    los_label, los_source = _sample_los_label(row, config)
    if not np.isfinite(theta_center) or not np.isfinite(beta_center):
        return _selection("pooled" if config.fallback_to_pooled else "none", 0, config, "invalid_theta_or_beta_bin", False, los_source)

    unavailable: list[str] = []
    low_support: list[str] = []
    pooled_train_n = _lookup_train_n(scoped_rows, row, "pooled", theta_center, beta_center, los_label)

    for scope in SCOPE_PRIORITY:
        if scope == "room_material_los" and los_label is None:
            unavailable.append("room_material_los:no_observable_los_label")
            continue
        train_n = _lookup_train_n(scoped_rows, row, scope, theta_center, beta_center, los_label)
        if train_n >= int(config.N_min):
            reason = f"selected_{scope}:train_n={train_n}"
            if unavailable:
                reason += ";skipped=" + ",".join(unavailable)
            return _selection(scope, train_n, config, reason, True, los_source)
        low_support.append(f"{scope}:{train_n}")

    if config.fallback_to_pooled:
        reason = "fallback_to_pooled_no_scope_meets_N_min"
        if low_support:
            reason += ";support=" + ",".join(low_support)
        return _selection("pooled", pooled_train_n, config, reason, pooled_train_n >= int(config.N_min), los_source)

    reason = "no_supported_lut_scope"
    if low_support:
        reason += ";support=" + ",".join(low_support)
    return _selection("none", 0, config, reason, False, los_source)


def _coerce_cfg(cfg: LutSelectionConfig | Mapping[str, Any] | None) -> LutSelectionConfig:
    if cfg is None:
        return LutSelectionConfig()
    if isinstance(cfg, LutSelectionConfig):
        return cfg
    kwargs = {field: cfg[field] for field in LutSelectionConfig.__dataclass_fields__ if field in cfg}
    return LutSelectionConfig(**kwargs)


def _sample_dict(sample: Mapping[str, Any] | pd.Series) -> dict[str, Any]:
    if isinstance(sample, pd.Series):
        return sample.to_dict()
    return dict(sample)


def _stats_frame(lut_stats: Any) -> pd.DataFrame:
    if isinstance(lut_stats, pd.DataFrame):
        return lut_stats.copy()
    if isinstance(lut_stats, Mapping):
        if "counts" in lut_stats:
            return _stats_frame(lut_stats["counts"])
        rows: list[dict[str, Any]] = []
        for scope, value in lut_stats.items():
            if isinstance(value, pd.DataFrame):
                frame = value.copy()
                frame["scope"] = scope
                rows.extend(frame.to_dict(orient="records"))
            elif isinstance(value, list):
                for item in value:
                    row = dict(item)
                    row.setdefault("scope", scope)
                    rows.append(row)
            elif isinstance(value, Mapping):
                row = dict(value)
                row.setdefault("scope", scope)
                rows.append(row)
        return pd.DataFrame(rows)
    raise TypeError("lut_stats must be a pandas DataFrame or a mapping")


def _prepare_stats(stats: pd.DataFrame) -> pd.DataFrame:
    out = stats.copy()
    if "scope" not in out.columns:
        out["scope"] = _infer_scope(out)
    theta_col = _first_existing(out, ["theta_bin_center_deg", "theta_A_bin_center_deg", "theta_A_deg"])
    beta_col = _first_existing(out, ["beta_bin_center_deg", "beta_deg"])
    train_col = _first_existing(out, ["train_n", "n_train", "train_samples", "n_samples", "n_source"])
    if theta_col is None or beta_col is None or train_col is None:
        missing = []
        if theta_col is None:
            missing.append("theta bin column")
        if beta_col is None:
            missing.append("beta bin column")
        if train_col is None:
            missing.append("train count column")
        raise KeyError(f"lut_stats missing {', '.join(missing)}")
    out["_theta_center"] = pd.to_numeric(out[theta_col], errors="coerce")
    out["_beta_center"] = pd.to_numeric(out[beta_col], errors="coerce").map(_wrap180_scalar)
    out["_train_n"] = pd.to_numeric(out[train_col], errors="coerce").fillna(0).astype(int)
    for col in ["room_type", "material", "los_label"]:
        if col in out.columns:
            out[col] = out[col].map(_norm_label)
    out["scope"] = out["scope"].map(_norm_label)
    return out


def _infer_scope(stats: pd.DataFrame) -> str:
    cols = set(stats.columns)
    if {"room_type", "material", "los_label"}.issubset(cols):
        return "room_material_los"
    if {"room_type", "material"}.issubset(cols):
        return "room_material"
    if "room_type" in cols:
        return "room"
    return "pooled"


def _first_existing(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in df.columns), None)


def _selection(scope: str, train_n: int, cfg: LutSelectionConfig, reason: str, meets_n_min: bool, los_source: str) -> LutScopeSelection:
    train = max(0, int(train_n))
    denom = float(cfg.N_ref) if cfg.N_ref else 1.0
    return LutScopeSelection(
        chosen_scope=scope,
        train_n=train,
        lut_support_weight=float(min(1.0, train / denom)),
        reason=reason,
        meets_n_min=bool(meets_n_min),
        los_label_source=los_source,
    )


def _sample_theta_bin(sample: Mapping[str, Any], cfg: LutSelectionConfig) -> float:
    if "theta_bin_center_deg" in sample:
        return _as_float(sample.get("theta_bin_center_deg"))
    theta = _as_float(sample.get("theta_A_deg"))
    if not np.isfinite(theta) or theta < cfg.theta_min_deg or theta >= cfg.theta_max_deg or cfg.theta_bin_deg <= 0:
        return np.nan
    idx = np.floor((theta - cfg.theta_min_deg) / cfg.theta_bin_deg)
    return float(cfg.theta_min_deg + idx * cfg.theta_bin_deg + cfg.theta_bin_deg / 2.0)


def _sample_beta_bin(sample: Mapping[str, Any], cfg: LutSelectionConfig) -> float:
    if "beta_bin_center_deg" in sample:
        return _wrap180_scalar(_as_float(sample.get("beta_bin_center_deg")))
    beta = _wrap180_scalar(_as_float(sample.get("beta_deg")))
    if not np.isfinite(beta) or cfg.beta_bin_deg <= 0:
        return np.nan
    idx = np.floor((beta + 180.0) / cfg.beta_bin_deg)
    center = -180.0 + idx * cfg.beta_bin_deg + cfg.beta_bin_deg / 2.0
    return _wrap180_scalar(center)


def _sample_los_label(sample: Mapping[str, Any], cfg: LutSelectionConfig) -> tuple[str | None, str]:
    estimated = _nonempty(sample.get("estimated_los_label"))
    if estimated is not None:
        return _norm_los(estimated), "estimated_los_label"
    nlos_score = _as_float(sample.get("nlos_score"))
    if np.isfinite(nlos_score):
        return ("no_los" if nlos_score >= cfg.nlos_score_threshold else "los"), "nlos_score"
    if cfg.residual_proxy_threshold_db is not None:
        residual = abs(_as_float(sample.get("rssd_residual_db")))
        if np.isfinite(residual):
            return ("no_los" if residual >= cfg.residual_proxy_threshold_db else "los"), "rssd_residual_db"
    if cfg.allow_ground_truth_los:
        gt = _nonempty(sample.get("los_label"))
        if gt is not None:
            return _norm_los(gt), "ground_truth_los_label"
    return None, "none"


def _lookup_train_n(stats: pd.DataFrame, sample: Mapping[str, Any], scope: str, theta_center: float, beta_center: float, los_label: str | None) -> int:
    rows = stats[stats["scope"].eq(scope)].copy()
    if rows.empty:
        return 0
    rows = rows[np.isclose(rows["_theta_center"], theta_center, atol=1e-9, equal_nan=False)]
    rows = rows[np.isclose(rows["_beta_center"], beta_center, atol=1e-9, equal_nan=False)]
    if rows.empty:
        return 0
    for col in SCOPE_COLUMNS[scope]:
        if col == "los_label":
            if los_label is None:
                return 0
            value = los_label
        else:
            value = _norm_label(sample.get(col))
        if col not in rows.columns:
            return 0
        rows = rows[rows[col].eq(value)]
        if rows.empty:
            return 0
    return int(pd.to_numeric(rows["_train_n"], errors="coerce").fillna(0).max())


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _wrap180_scalar(value: float) -> float:
    if not np.isfinite(value):
        return np.nan
    return float(((value + 180.0) % 360.0) - 180.0)


def _nonempty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "unknown", "unknown_los"}:
        return None
    return text


def _norm_label(value: Any) -> str:
    text = "" if value is None else str(value).strip().lower()
    return text


def _norm_los(value: Any) -> str:
    text = _norm_label(value).replace("-", "_")
    if text in {"nlos", "no_los", "non_los", "blocked"}:
        return "no_los"
    if text in {"los", "line_of_sight"}:
        return "los"
    return text
