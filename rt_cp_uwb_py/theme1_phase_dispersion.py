from __future__ import annotations

import csv
import hashlib
import json
import math
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from rt_cp_uwb_py.features import select_circular_channels, CP_BRANCH_SAME


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_ROOT = ROOT / "results" / "THEME1_CP_CHANNEL_STATE_CLASSIFICATION_FULLRT_20260628"
DEFAULT_RT_ROOT = DEFAULT_SOURCE_ROOT / "02_rt_fullrun"
DEFAULT_SPLIT_TABLE = DEFAULT_SOURCE_ROOT / "03_source_freeze" / "theme1_split_manifest.csv"
DEFAULT_CONFIG = DEFAULT_SOURCE_ROOT / "04_feature_discovery" / "configs" / "feature_discovery_theme1_20260628.yaml"
DEFAULT_OUTPUT_ROOT = ROOT / "results" / "THEME1_RD_LOS_PHASE_DISPERSION_20260629"
DEFAULT_PLAN = ROOT / ".omx" / "plans" / "theme1_rd_los_phase_dispersion_plan_20260629.md"
REPORT_CLAIM_BOUNDARY = (
    "Simulation-only RD-LoS channel-state mechanism evidence. RD-LoS is a reflection-dominant "
    "channel state, not a range-error label. q_clean remains clean-session/session-quality "
    "confidence only; no direct CP range-error reduction, measurement transfer, backend utility, "
    "AMR, or localization-accuracy claim is established."
)
CODE_HASH_FILES = [
    "scripts/run_p2_condition_factorial_rt_chunked_fullrun_20260602.py",
    "scripts/freeze_theme1_source_split_20260628.py",
    "rt_cp_uwb_py/features.py",
    "rt_cp_uwb_py/channel.py",
    "rt_cp_uwb_py/antennas.py",
    "rt_cp_uwb_py/feature_discovery.py",
]
LABEL_COLUMNS = ["Clean-LoS", "NoLoS", "RD-LoS", "HB-near-delay", "HB-prior", "not-clean_2H", "not-clean_3H"]
PRIMARY_METRICS = [
    "vphi_1p_cp_same",
    "vphi_1p_cp_cross",
    "vphi_1p_lp_dominant",
    "vdphi_cp_linear_residual",
    "vdphi_cp_clean_oof",
    "cp_phase_residual_circvar",
    "gamma_cp_6_phase_circvar",
    "s3_fp",
    "s3_late",
    "s3_all",
    "xpr_fp_db",
    "xpr_late_db",
    "xpr_all_db",
    "strongest_reflection_angle_separation_deg",
    "dphi_path_all",
    "dphi_path_early",
    "dphi_path_direct",
    "dphi_path_late_reflection",
]
MATCH_RATIOS = [0.20, 0.30, 0.50, 0.70, 0.90]


@dataclass(frozen=True)
class InputPaths:
    rt_root: Path
    split_table: Path
    config_path: Path


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def as_path(path: str | Path | None, default: Path) -> Path:
    if path is None:
        return default.resolve()
    p = Path(path)
    return p.resolve() if p.is_absolute() else (ROOT / p).resolve()


def rel(path: str | Path, root: Path = ROOT) -> str:
    p = Path(path).resolve()
    try:
        return str(p.relative_to(root.resolve())).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return "MISSING"
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def csv_row_count(path: Path) -> str:
    if not path.exists() or path.suffix.lower() != ".csv":
        return ""
    with path.open("rb") as f:
        return str(max(0, sum(1 for _ in f) - 1))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    if not fields:
        fields = ["status"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def prepare_stage_dir(out_root: Path, stage_name: str, overwrite_stage: bool = False) -> Path:
    stage = out_root / stage_name
    if stage.exists() and any(stage.iterdir()) and not overwrite_stage:
        raise FileExistsError(f"Stage output exists; pass --overwrite-stage to replace: {stage}")
    if overwrite_stage and stage.exists():
        for path in sorted(stage.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
    stage.mkdir(parents=True, exist_ok=True)
    return stage


def output_root(path: str | Path | None = None) -> Path:
    return as_path(path, DEFAULT_OUTPUT_ROOT)


def input_paths(
    rt_root_arg: str | Path | None = None,
    split_table_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
) -> InputPaths:
    rt_root = as_path(rt_root_arg, DEFAULT_RT_ROOT)
    split_table = as_path(split_table_arg, DEFAULT_SPLIT_TABLE)
    config_path = as_path(config_arg, DEFAULT_CONFIG)
    return InputPaths(rt_root=rt_root, split_table=split_table, config_path=config_path)


def _read_table_or_chunks(rt_root: Path, name: str, stage: Path | None = None) -> tuple[pd.DataFrame, str]:
    top = rt_root / name
    if top.exists():
        return pd.read_csv(top), "top_level"
    chunk_paths = sorted(rt_root.glob(f"chunks/chunk_*/{name}"))
    frames = [pd.read_csv(path) for path in chunk_paths if path.exists() and path.stat().st_size > 0]
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    if stage is not None and not df.empty:
        staged = stage / "staged_source_tables" / name
        staged.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(staged, index=False)
    return df, "chunk_concatenated" if frames else "missing"


def _bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series(False, index=df.index)
    s = df[col]
    if s.dtype == bool:
        return s.fillna(False)
    return s.map(lambda x: str(x).strip().lower() in {"1", "true", "yes", "y"}).fillna(False)


def load_joined_inputs(paths: InputPaths, stage: Path | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
    features, f_src = _read_table_or_chunks(paths.rt_root, "feature_table.csv", stage)
    labels, l_src = _read_table_or_chunks(paths.rt_root, "label_table.csv", stage)
    split = pd.read_csv(paths.split_table) if paths.split_table.exists() else pd.DataFrame()
    if features.empty or labels.empty:
        raise FileNotFoundError(f"Missing feature/label source under {paths.rt_root}")
    merged = features.merge(labels, on="case_id", how="left", suffixes=("", "_label"), validate="one_to_one")
    if not split.empty:
        keep = [c for c in ["case_id", "pose_group_id", "split_fold", "calibration_split"] if c in split.columns]
        merged = merged.merge(split[keep], on="case_id", how="left", suffixes=("", "_split"), validate="one_to_one")
    return merged, features, labels, {"feature_table_source": f_src, "label_table_source": l_src}


def build_source_audit(
    *,
    out_root_arg: str | Path | None = None,
    rt_root_arg: str | Path | None = None,
    split_table_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
    force_new_rt: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    paths = input_paths(rt_root_arg, split_table_arg, config_arg)
    stage = prepare_stage_dir(out, "00_source_audit", overwrite_stage)
    source_rows: list[dict[str, Any]] = []
    for role, path in [
        ("rt_root", paths.rt_root),
        ("feature_table", paths.rt_root / "feature_table.csv"),
        ("label_table", paths.rt_root / "label_table.csv"),
        ("rt_path_long", paths.rt_root / "rt_path_long.csv"),
        ("cir_bank_manifest", paths.rt_root / "cir_bank_manifest.csv"),
        ("fullrun_manifest", paths.rt_root / "fullrun_manifest.json"),
        ("split_table", paths.split_table),
        ("config_path", paths.config_path),
    ]:
        source_rows.append(
            {
                "role": role,
                "path": rel(path),
                "exists": bool(path.exists()),
                "row_count": csv_row_count(path),
                "sha256": sha256_file(path) if path.is_file() else "",
            }
        )
    write_csv(stage / "source_resolution_audit.csv", source_rows)

    chunk_rows: list[dict[str, Any]] = []
    for chunk_dir in sorted((paths.rt_root / "chunks").glob("chunk_*")):
        if not chunk_dir.is_dir():
            continue
        cir_bank = chunk_dir / "cir" / "multianchor_lp_cp_cir_bank.npz"
        chunk_rows.append(
            {
                "chunk": chunk_dir.name,
                "chunk_manifest": rel(chunk_dir / "chunk_manifest.json"),
                "feature_rows": csv_row_count(chunk_dir / "feature_table.csv"),
                "label_rows": csv_row_count(chunk_dir / "label_table.csv"),
                "path_rows": csv_row_count(chunk_dir / "rt_path_long.csv"),
                "cir_bank_exists": cir_bank.exists(),
                "cir_bank_sha256": sha256_file(cir_bank),
            }
        )
    write_csv(stage / "chunk_inventory.csv", chunk_rows)

    code_rows = []
    for rel_path in CODE_HASH_FILES:
        p = ROOT / rel_path
        code_rows.append({"path": rel_path, "exists": p.exists(), "sha256": sha256_file(p)})
    write_csv(stage / "current_code_hashes.csv", code_rows)

    cir_rows = []
    for idx, chunk in enumerate(sorted((paths.rt_root / "chunks").glob("chunk_*"))):
        p = chunk / "cir" / "multianchor_lp_cp_cir_bank.npz"
        row = {"chunk": chunk.name, "path": rel(p), "status": "MISSING"}
        if p.exists():
            try:
                data = np.load(p, allow_pickle=False)
                row.update(
                    {
                        "status": "PASS",
                        "keys": ";".join(data.files),
                        "case_id_shape": str(data["case_id"].shape) if "case_id" in data else "",
                        "freqs_hz_shape": str(data["freqs_hz"].shape) if "freqs_hz" in data else "",
                        "cp_h_shape": str(data["cp_h"].shape) if "cp_h" in data else "",
                        "lp_h_shape": str(data["lp_h"].shape) if "lp_h" in data else "",
                    }
                )
            except Exception as exc:
                row.update({"status": "READ_FAIL", "error": str(exc)})
        cir_rows.append(row)
        if idx >= 4:
            break
    write_csv(stage / "cir_bank_schema_audit.csv", cir_rows)

    manifest_path = paths.rt_root / "fullrun_manifest.json"
    status = "BLOCKED_MISSING_FULLRUN_MANIFEST"
    fullrun_status = "MISSING"
    row_counts: dict[str, Any] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        fullrun_status = str(manifest.get("status", "UNKNOWN"))
        row_counts = dict(manifest.get("row_counts", {}))
        status = "SOURCE_REUSE_GATE_PASS" if fullrun_status == "FULLRUN_COMPLETE" else "SOURCE_REUSE_GATE_PARTIAL"
    if force_new_rt:
        status = "NEW_RT_REQUIRED_FORCE_SOMI"
    elif fullrun_status != "FULLRUN_COMPLETE":
        status = "NEW_RT_REQUIRED_SOMI"

    payload = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": status,
        "rt_root": rel(paths.rt_root),
        "split_table": rel(paths.split_table),
        "config_path": rel(paths.config_path),
        "fullrun_status": fullrun_status,
        "row_counts": row_counts,
        "new_rt_policy": "If required, run additive full RT only on Somi.",
        "recommended_new_rt_root": "results/THEME1_CP_CHANNEL_STATE_CLASSIFICATION_FULLRT_CURRENTCODE_20260629",
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "source_manifest.json", payload)
    return payload


def _rx_order(value: Any) -> tuple[str, str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ("R", "L")
    text = str(value).replace(";", ",").replace("|", ",")
    parts = [p.strip().upper()[0] for p in text.split(",") if p.strip()]
    if len(parts) >= 2:
        return ("L" if parts[0].startswith("L") else "R", "L" if parts[1].startswith("L") else "R")
    return ("R", "L")


def _finite_delay(value: Any) -> float:
    try:
        out = float(value)
    except Exception:
        return float("nan")
    return out if math.isfinite(out) else float("nan")


def _reference_delay(row: pd.Series) -> tuple[float, str]:
    for col, source in [
        ("los_path_delay_s", "los_path_delay_s"),
        ("t_fp_s", "t_fp_s"),
        ("lp_t_fp_s", "lp_t_fp_s"),
    ]:
        tau = _finite_delay(row.get(col, np.nan))
        if math.isfinite(tau):
            return tau, source
    return float("nan"), "MISSING"


def _weighted_circular_variance(unit: np.ndarray, weights: np.ndarray) -> float:
    valid = np.isfinite(weights) & (weights > 0) & np.isfinite(unit.real) & np.isfinite(unit.imag)
    if int(valid.sum()) < 3:
        return float("nan")
    denom = float(np.sum(weights[valid]))
    if denom <= 0:
        return float("nan")
    resultant = np.sum(weights[valid] * unit[valid]) / denom
    return float(1.0 - abs(resultant))


def single_path_circvar(H: np.ndarray, freqs: np.ndarray, tau_ref_s: float) -> float:
    H = np.asarray(H).reshape(-1)
    freqs = np.asarray(freqs, dtype=float).reshape(-1)
    if not math.isfinite(tau_ref_s) or H.size != freqs.size:
        return float("nan")
    comp = H * np.exp(1j * 2.0 * np.pi * freqs * float(tau_ref_s))
    unit = np.exp(1j * np.angle(comp))
    weights = np.abs(H) ** 2
    return _weighted_circular_variance(unit, weights)


def linear_ratio_residual_circvar(H_same: np.ndarray, H_cross: np.ndarray, freqs: np.ndarray, eps: float = 1e-12) -> float:
    same = np.asarray(H_same).reshape(-1)
    cross = np.asarray(H_cross).reshape(-1)
    f = np.asarray(freqs, dtype=float).reshape(-1)
    valid = np.isfinite(same.real) & np.isfinite(same.imag) & np.isfinite(cross.real) & np.isfinite(cross.imag) & (np.abs(same) > eps) & (np.abs(cross) > eps)
    if int(valid.sum()) < 3:
        return float("nan")
    ratio = cross[valid] / (same[valid] + eps)
    phase = np.unwrap(np.angle(ratio))
    fv = f[valid]
    coeff = np.linalg.lstsq(np.column_stack([fv, np.ones_like(fv)]), phase, rcond=None)[0]
    residual = phase - (coeff[0] * fv + coeff[1])
    return float(1.0 - abs(np.mean(np.exp(1j * residual))))


def _dominant_lp_channel(lp_tensor: np.ndarray) -> np.ndarray:
    H = np.asarray(lp_tensor)
    if H.ndim != 3:
        H = H.reshape(2, 2, -1)
    power = np.sum(np.abs(H) ** 2, axis=2)
    idx = np.unravel_index(int(np.nanargmax(power)), power.shape)
    return H[idx[0], idx[1], :].reshape(-1)


def _case_groups(df: pd.DataFrame, bandwidth_hz: float) -> pd.DataFrame:
    out = pd.DataFrame({"case_id": df["case_id"].astype(int)})
    clean = _bool_series(df, "Clean-LoS")
    rd = _bool_series(df, "RD-LoS")
    nolos = _bool_series(df, "NoLoS")
    dt = pd.to_numeric(df.get("delta_tau_reflection_los_s", df.get("delta_tau_s", np.nan)), errors="coerce")
    t_fp = pd.to_numeric(df.get("t_fp_s", np.nan), errors="coerce")
    los_delay = pd.to_numeric(df.get("los_path_delay_s", np.nan), errors="coerce")
    has_los = _bool_series(df, "has_los_path") | _bool_series(df, "has_los")
    tol = max(0.5 / float(bandwidth_hz), 2.0e-10) if bandwidth_hz > 0 else 2.0e-10
    delta_tau_b = dt * float(bandwidth_hz)
    direct_first = has_los & t_fp.notna() & los_delay.notna() & ((t_fp - los_delay).abs() <= tol)
    out["group_clean_los"] = clean
    out["group_rd_los_all"] = rd
    out["group_rd_delta_tau_b_lt_1"] = rd & delta_tau_b.lt(1.0)
    out["group_rd_delta_tau_b_ge_1_direct_first"] = rd & delta_tau_b.ge(1.0) & direct_first
    out["group_nolos"] = nolos
    out["delta_tau_b"] = delta_tau_b
    out["direct_first_tolerance_s"] = tol
    return out


def build_phase_metrics(
    *,
    out_root_arg: str | Path | None = None,
    rt_root_arg: str | Path | None = None,
    split_table_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    paths = input_paths(rt_root_arg, split_table_arg, config_arg)
    stage = prepare_stage_dir(out, "01_phase_metrics", overwrite_stage)
    df, _, _, source_info = load_joined_inputs(paths, stage)
    df_by_case = df.drop_duplicates("case_id").set_index("case_id", drop=False)
    split_by_case = df_by_case.get("split_fold", pd.Series(np.nan, index=df_by_case.index))
    clean_by_case = _bool_series(df_by_case, "Clean-LoS")
    rows: list[dict[str, Any]] = []
    unit_parts: list[np.ndarray] = []
    weight_parts: list[np.ndarray] = []
    case_parts: list[np.ndarray] = []
    fold_parts: list[np.ndarray] = []
    clean_parts: list[np.ndarray] = []
    bandwidth_hz = float("nan")

    cir_paths = sorted((paths.rt_root / "chunks").glob("chunk_*/cir/multianchor_lp_cp_cir_bank.npz"))
    if not cir_paths and (paths.rt_root / "cir" / "multianchor_lp_cp_cir_bank.npz").exists():
        cir_paths = [paths.rt_root / "cir" / "multianchor_lp_cp_cir_bank.npz"]
    for cir_path in cir_paths:
        data = np.load(cir_path, allow_pickle=False)
        case_ids = np.asarray(data["case_id"]).astype(int)
        freqs = np.asarray(data["freqs_hz"], dtype=float)
        cp_h = np.asarray(data["cp_h"])
        lp_h = np.asarray(data["lp_h"]) if "lp_h" in data else None
        if not math.isfinite(bandwidth_hz):
            bandwidth_hz = float(np.nanmax(freqs) - np.nanmin(freqs))
        units = np.ones((len(case_ids), len(freqs)), dtype=np.complex128)
        weights = np.zeros((len(case_ids), len(freqs)), dtype=float)
        folds = np.full(len(case_ids), np.nan, dtype=float)
        cleans = np.zeros(len(case_ids), dtype=bool)
        for i, cid in enumerate(case_ids):
            if cid not in df_by_case.index:
                rows.append({"case_id": cid, "cir_source": rel(cir_path), "phase_status": "MISSING_CASE_METADATA"})
                continue
            row = df_by_case.loc[cid]
            tau, tau_source = _reference_delay(row)
            tx = str(row.get("cp16_tx_hand", row.get("tx_handedness", "R")))
            order = _rx_order(row.get("cp16_rx_port_order", row.get("rx_port_order", None)))
            same, cross, meta = select_circular_channels(cp_h[i], freqs, tx, order, branch_convention=CP_BRANCH_SAME)
            status = "PASS" if same is not None and cross is not None and math.isfinite(tau) else "PARTIAL"
            if same is not None and cross is not None:
                ratio = cross.reshape(-1) / (same.reshape(-1) + 1.0e-12)
                valid = np.isfinite(ratio.real) & np.isfinite(ratio.imag) & (np.abs(same.reshape(-1)) > 1.0e-12) & (np.abs(cross.reshape(-1)) > 1.0e-12)
                units[i, valid] = np.exp(1j * np.angle(ratio[valid]))
                weights[i, valid] = np.abs(same.reshape(-1)[valid]) ** 2 + np.abs(cross.reshape(-1)[valid]) ** 2
            lp_dom = _dominant_lp_channel(lp_h[i]) if lp_h is not None else np.full(len(freqs), np.nan + 1j * np.nan)
            rows.append(
                {
                    "case_id": cid,
                    "cir_source": rel(cir_path),
                    "phase_status": status,
                    "tau_ref_s": tau,
                    "tau_ref_source": tau_source,
                    "vphi_1p_cp_same": single_path_circvar(same, freqs, tau) if same is not None else float("nan"),
                    "vphi_1p_cp_cross": single_path_circvar(cross, freqs, tau) if cross is not None else float("nan"),
                    "vphi_1p_lp_dominant": single_path_circvar(lp_dom, freqs, tau),
                    "vdphi_cp_linear_residual": linear_ratio_residual_circvar(same, cross, freqs) if same is not None and cross is not None else float("nan"),
                    "cp_same_rx_port": meta.get("same_rx_port", ""),
                    "cp_cross_rx_port": meta.get("reversed_rx_port", ""),
                    "cp_tx_port": meta.get("tx_port", ""),
                }
            )
            folds[i] = float(split_by_case.loc[cid]) if cid in split_by_case.index and pd.notna(split_by_case.loc[cid]) else np.nan
            cleans[i] = bool(clean_by_case.loc[cid]) if cid in clean_by_case.index else False
        unit_parts.append(units)
        weight_parts.append(weights)
        case_parts.append(case_ids)
        fold_parts.append(folds)
        clean_parts.append(cleans)

    metrics = pd.DataFrame(rows)
    if unit_parts:
        units_all = np.vstack(unit_parts)
        weights_all = np.vstack(weight_parts)
        cases_all = np.concatenate(case_parts)
        folds_all = np.concatenate(fold_parts)
        cleans_all = np.concatenate(clean_parts)
        oof_vals = np.full(len(cases_all), np.nan, dtype=float)
        unique_folds = sorted({int(x) for x in folds_all[np.isfinite(folds_all)]})
        if unique_folds:
            for fold in unique_folds:
                ref_mask = cleans_all & np.isfinite(folds_all) & (folds_all.astype(int) != fold)
                test_mask = np.isfinite(folds_all) & (folds_all.astype(int) == fold)
                ref = _reference_unit(units_all, weights_all, ref_mask)
                for idx in np.flatnonzero(test_mask):
                    oof_vals[idx] = _weighted_circular_variance(units_all[idx] * np.conj(ref), weights_all[idx])
        else:
            ref = _reference_unit(units_all, weights_all, cleans_all)
            for idx in range(len(cases_all)):
                oof_vals[idx] = _weighted_circular_variance(units_all[idx] * np.conj(ref), weights_all[idx])
        oof = pd.DataFrame({"case_id": cases_all.astype(int), "vdphi_cp_clean_oof": oof_vals})
        metrics = metrics.merge(oof, on="case_id", how="left", validate="one_to_one")
    else:
        metrics["vdphi_cp_clean_oof"] = np.nan

    keep_cols = [
        "case_id",
        "space_id",
        "space_type",
        "room_type",
        "anchor_id",
        "pose_group_id",
        "split_fold",
        "snr_db",
        "fp_peak_val",
        "fp_to_total_ratio",
        "t_fp_s",
        "los_path_delay_s",
        "strongest_reflection_delay_s",
        "delta_tau_reflection_los_s",
        "range_error_m",
        "cp_phase_residual_circvar",
        "cp_phase_slope_delay_s",
        "gamma_cp_6_phase_circvar",
        "xpr_fp_db",
        "xpr_late_db",
        "xpr_all_db",
        "s3_fp",
        "s3_late",
        "s3_all",
        "strongest_reflection_angle_separation_deg",
        *LABEL_COLUMNS,
    ]
    meta_cols = [c for c in keep_cols if c in df_by_case.columns]
    table = df_by_case[meta_cols].reset_index(drop=True).merge(metrics, on="case_id", how="left", validate="one_to_one")
    if not math.isfinite(bandwidth_hz):
        bandwidth_hz = float("nan")
    groups = _case_groups(table, bandwidth_hz if math.isfinite(bandwidth_hz) and bandwidth_hz > 0 else 1.0)
    table = table.merge(groups, on="case_id", how="left", validate="one_to_one")
    table.to_csv(stage / "phase_metric_table.csv", index=False)

    missing_rows = []
    for col in [c for c in PRIMARY_METRICS if c in table.columns]:
        vals = pd.to_numeric(table[col], errors="coerce")
        missing_rows.append(
            {
                "metric": col,
                "n_total": int(len(table)),
                "n_missing_or_nan": int(vals.isna().sum()),
                "missing_rate": float(vals.isna().mean()) if len(vals) else float("nan"),
                "reason": "metric unavailable for sample, missing source column, or insufficient complex support",
            }
        )
    write_csv(stage / "phase_missingness_audit.csv", missing_rows)
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE" if len(table) else "BLOCKED_NO_ROWS",
        "metric_rows": int(len(table)),
        "cir_banks": int(len(cir_paths)),
        "bandwidth_hz": bandwidth_hz,
        "source_info": source_info,
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "phase_metric_manifest.json", manifest)
    return manifest


def _reference_unit(units: np.ndarray, weights: np.ndarray, mask: np.ndarray) -> np.ndarray:
    if int(mask.sum()) < 3:
        return np.ones(units.shape[1], dtype=np.complex128)
    num = np.sum(weights[mask] * units[mask], axis=0)
    den = np.sum(weights[mask], axis=0)
    ref = np.ones(units.shape[1], dtype=np.complex128)
    valid = den > 0
    mean = np.zeros_like(ref)
    mean[valid] = num[valid] / den[valid]
    ref[valid] = np.exp(1j * np.angle(mean[valid]))
    return ref


def _path_incoherence(part: pd.DataFrame, power_col: str = "power", phase_col: str = "phase") -> tuple[float, int, float]:
    if part.empty or power_col not in part or phase_col not in part:
        return float("nan"), 0, float("nan")
    power = pd.to_numeric(part[power_col], errors="coerce").to_numpy(dtype=float)
    phase = pd.to_numeric(part[phase_col], errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(power) & np.isfinite(phase) & (power > 0)
    if int(valid.sum()) == 0:
        return float("nan"), 0, float("nan")
    amp = np.sqrt(power[valid])
    z = amp * np.exp(1j * phase[valid])
    denom = float(np.sum(amp))
    if denom <= 0:
        return float("nan"), int(valid.sum()), float(np.sum(power[valid]))
    return float(1.0 - abs(np.sum(z)) / denom), int(valid.sum()), float(np.sum(power[valid]))


def build_path_mechanism(
    *,
    out_root_arg: str | Path | None = None,
    rt_root_arg: str | Path | None = None,
    split_table_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    paths = input_paths(rt_root_arg, split_table_arg, config_arg)
    stage = prepare_stage_dir(out, "05_path_mechanism", overwrite_stage)
    metric_path = out / "01_phase_metrics" / "phase_metric_table.csv"
    if not metric_path.exists():
        raise FileNotFoundError(metric_path)
    metrics = pd.read_csv(metric_path)
    path_df, source = _read_table_or_chunks(paths.rt_root, "rt_path_long.csv", stage)
    if path_df.empty:
        raise FileNotFoundError(f"No rt_path_long source under {paths.rt_root}")
    bandwidth = _bandwidth_from_first_cir(paths.rt_root)
    width = 1.0 / bandwidth if bandwidth and bandwidth > 0 else 2.0e-9
    meta = metrics.set_index("case_id", drop=False)
    rows: list[dict[str, Any]] = []
    for cid, part in path_df.groupby("case_id", sort=True):
        if cid not in meta.index:
            continue
        row = meta.loc[cid]
        delay = pd.to_numeric(part.get("path_delay_s", part.get("delay", np.nan)), errors="coerce")
        windows = {
            "all": part,
            "early": part[delay.sub(float(row.get("t_fp_s", np.nan))).abs().le(0.5 * width)] if pd.notna(row.get("t_fp_s", np.nan)) else part.iloc[0:0],
            "direct": part[delay.sub(float(row.get("los_path_delay_s", np.nan))).abs().le(0.5 * width)] if pd.notna(row.get("los_path_delay_s", np.nan)) else part.iloc[0:0],
            "late_reflection": part[delay.sub(float(row.get("strongest_reflection_delay_s", np.nan))).abs().le(0.5 * width)] if pd.notna(row.get("strongest_reflection_delay_s", np.nan)) else part.iloc[0:0],
        }
        for window, wpart in windows.items():
            dphi, n_paths, sum_power = _path_incoherence(wpart)
            rows.append(
                {
                    "case_id": int(cid),
                    "window": window,
                    "dphi_path": dphi,
                    "n_paths": n_paths,
                    "sum_power": sum_power,
                    "window_width_s": width,
                    "status": "PASS" if n_paths > 0 and math.isfinite(dphi) else "NO_PATH_SUPPORT",
                    "claim_role": "RT_MECHANISM_AUDIT_ONLY",
                }
            )
    path_metrics = pd.DataFrame(rows)
    path_metrics.to_csv(stage / "path_phase_incoherence_table.csv", index=False)
    if not path_metrics.empty:
        support = path_metrics.groupby("window", dropna=False).agg(n_cases=("case_id", "nunique"), n_supported=("status", lambda s: int((s == "PASS").sum())), dphi_median=("dphi_path", "median")).reset_index()
    else:
        support = pd.DataFrame(columns=["window", "n_cases", "n_supported", "dphi_median"])
    support.to_csv(stage / "path_window_support.csv", index=False)
    wide = path_metrics.pivot_table(index="case_id", columns="window", values="dphi_path", aggfunc="first").reset_index()
    wide.columns = ["case_id"] + [f"dphi_path_{c}" for c in wide.columns[1:]]
    enriched = metrics.drop(columns=[c for c in metrics.columns if c.startswith("dphi_path_")], errors="ignore").merge(wide, on="case_id", how="left", validate="one_to_one")
    enriched.to_csv(out / "01_phase_metrics" / "phase_metric_table_with_path.csv", index=False)
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE" if len(path_metrics) else "BLOCKED_NO_PATH_METRICS",
        "path_rows": int(len(path_df)),
        "path_source": source,
        "metric_rows": int(len(path_metrics)),
        "bandwidth_hz": bandwidth,
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "path_mechanism_manifest.json", manifest)
    return manifest


def _bandwidth_from_first_cir(rt_root: Path) -> float:
    paths = sorted((rt_root / "chunks").glob("chunk_*/cir/multianchor_lp_cp_cir_bank.npz"))
    if not paths and (rt_root / "cir" / "multianchor_lp_cp_cir_bank.npz").exists():
        paths = [rt_root / "cir" / "multianchor_lp_cp_cir_bank.npz"]
    if not paths:
        return float("nan")
    data = np.load(paths[0], allow_pickle=False)
    freqs = np.asarray(data["freqs_hz"], dtype=float)
    return float(np.nanmax(freqs) - np.nanmin(freqs))


def _analysis_table(out: Path) -> pd.DataFrame:
    enriched = out / "01_phase_metrics" / "phase_metric_table_with_path.csv"
    base = out / "01_phase_metrics" / "phase_metric_table.csv"
    path = enriched if enriched.exists() else base
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def safe_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    valid = np.isfinite(scores)
    if int(valid.sum()) < 3:
        return float("nan")
    y = y_true[valid].astype(int)
    s = scores[valid].astype(float)
    if len(np.unique(y)) < 2:
        return float("nan")
    try:
        from sklearn.metrics import roc_auc_score

        return float(roc_auc_score(y, s))
    except Exception:
        order = np.argsort(s)
        ranks = np.empty_like(order, dtype=float)
        ranks[order] = np.arange(len(s), dtype=float) + 1.0
        n_pos = float(y.sum())
        n_neg = float(len(y) - y.sum())
        if n_pos == 0 or n_neg == 0:
            return float("nan")
        return float((ranks[y == 1].sum() - n_pos * (n_pos + 1.0) / 2.0) / (n_pos * n_neg))


def _metric_summary(df: pd.DataFrame, metric_cols: Sequence[str], group_cols: Sequence[str]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    groups = {
        "Clean-LoS": df["group_clean_los"].fillna(False).astype(bool),
        "RD-LoS_all": df["group_rd_los_all"].fillna(False).astype(bool),
        "RD-LoS_delta_tau_B_lt_1": df["group_rd_delta_tau_b_lt_1"].fillna(False).astype(bool),
        "RD-LoS_delta_tau_B_ge_1_direct_first": df["group_rd_delta_tau_b_ge_1_direct_first"].fillna(False).astype(bool),
        "NoLoS": df["group_nolos"].fillna(False).astype(bool),
    }
    for group_name, mask in groups.items():
        part = df[mask]
        for metric in metric_cols:
            if metric not in part:
                continue
            vals = pd.to_numeric(part[metric], errors="coerce")
            rows.append(
                {
                    "group": group_name,
                    "metric": metric,
                    "n": int(len(part)),
                    "n_valid": int(vals.notna().sum()),
                    "median": float(vals.median(skipna=True)),
                    "mean": float(vals.mean(skipna=True)),
                    "q25": float(vals.quantile(0.25)),
                    "q75": float(vals.quantile(0.75)),
                }
            )
    return pd.DataFrame(rows)


def _pairwise_auc_delta(df: pd.DataFrame, metric_cols: Sequence[str], suffix: str = "") -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    clean = df["group_clean_los"].fillna(False).astype(bool)
    comparisons = {
        "RD-LoS_all": df["group_rd_los_all"].fillna(False).astype(bool),
        "RD-LoS_delta_tau_B_lt_1": df["group_rd_delta_tau_b_lt_1"].fillna(False).astype(bool),
        "RD-LoS_delta_tau_B_ge_1_direct_first": df["group_rd_delta_tau_b_ge_1_direct_first"].fillna(False).astype(bool),
        "NoLoS": df["group_nolos"].fillna(False).astype(bool),
    }
    for comp, mask in comparisons.items():
        part = df[clean | mask].copy()
        y = mask[clean | mask].astype(int).to_numpy()
        for metric in metric_cols:
            if metric not in part:
                continue
            scores = pd.to_numeric(part[metric], errors="coerce").to_numpy(dtype=float)
            clean_vals = pd.to_numeric(df.loc[clean, metric], errors="coerce")
            comp_vals = pd.to_numeric(df.loc[mask, metric], errors="coerce")
            raw_auc = safe_auc(y, scores)
            rows.append(
                {
                    "comparison": f"Clean-LoS_vs_{comp}",
                    "metric": metric,
                    "context": suffix or "all",
                    "auc_raw_metric_high_implies_comparison": raw_auc,
                    "auc_separation": float(max(raw_auc, 1.0 - raw_auc)) if math.isfinite(raw_auc) else float("nan"),
                    "median_clean": float(clean_vals.median(skipna=True)),
                    "median_comparison": float(comp_vals.median(skipna=True)),
                    "median_delta_comparison_minus_clean": float(comp_vals.median(skipna=True) - clean_vals.median(skipna=True)),
                    "n_clean_valid": int(clean_vals.notna().sum()),
                    "n_comparison_valid": int(comp_vals.notna().sum()),
                    "status": "PASS" if clean_vals.notna().sum() >= 10 and comp_vals.notna().sum() >= 10 else "LOW_SUPPORT",
                }
            )
    return pd.DataFrame(rows)


def _bootstrap_ci(df: pd.DataFrame, metric_cols: Sequence[str], seed: int = 20260629, n_boot: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    clean_mask = df["group_clean_los"].fillna(False).astype(bool)
    comps = {
        "RD-LoS_all": df["group_rd_los_all"].fillna(False).astype(bool),
        "RD-LoS_delta_tau_B_lt_1": df["group_rd_delta_tau_b_lt_1"].fillna(False).astype(bool),
        "RD-LoS_delta_tau_B_ge_1_direct_first": df["group_rd_delta_tau_b_ge_1_direct_first"].fillna(False).astype(bool),
        "NoLoS": df["group_nolos"].fillna(False).astype(bool),
    }
    for comp, mask in comps.items():
        for metric in metric_cols:
            if metric not in df:
                continue
            c = pd.to_numeric(df.loc[clean_mask, metric], errors="coerce").dropna().to_numpy(dtype=float)
            r = pd.to_numeric(df.loc[mask, metric], errors="coerce").dropna().to_numpy(dtype=float)
            if len(c) < 10 or len(r) < 10:
                rows.append({"comparison": f"Clean-LoS_vs_{comp}", "metric": metric, "status": "LOW_SUPPORT", "n_clean": len(c), "n_comparison": len(r)})
                continue
            vals = []
            for _ in range(n_boot):
                cs = rng.choice(c, size=len(c), replace=True)
                rs = rng.choice(r, size=len(r), replace=True)
                vals.append(float(np.median(rs) - np.median(cs)))
            arr = np.asarray(vals, dtype=float)
            rows.append(
                {
                    "comparison": f"Clean-LoS_vs_{comp}",
                    "metric": metric,
                    "status": "PASS",
                    "n_clean": len(c),
                    "n_comparison": len(r),
                    "median_delta_bootstrap_mean": float(np.mean(arr)),
                    "ci95_low": float(np.quantile(arr, 0.025)),
                    "ci95_high": float(np.quantile(arr, 0.975)),
                    "bootstrap_seed": seed,
                    "n_boot": n_boot,
                }
            )
    return pd.DataFrame(rows)


def build_phase_sanity(
    *,
    out_root_arg: str | Path | None = None,
    overwrite_stage: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    stage = prepare_stage_dir(out, "02_phase_sanity", overwrite_stage)
    df = _analysis_table(out)
    metric_cols = [c for c in PRIMARY_METRICS if c in df.columns]
    summary = _metric_summary(df, metric_cols, [])
    auc_delta = _pairwise_auc_delta(df, metric_cols)
    ci = _bootstrap_ci(df, metric_cols)
    summary.to_csv(stage / "phase_group_summary.csv", index=False)
    auc_delta.to_csv(stage / "phase_auc_median_delta.csv", index=False)
    ci.to_csv(stage / "phase_bootstrap_ci.csv", index=False)
    figure_rows = _build_phase_figures(stage, df, metric_cols)
    write_csv(stage / "phase_metric_figure_manifest.csv", figure_rows)
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE" if not auc_delta.empty else "BLOCKED_NO_COMPARISONS",
        "metric_count": len(metric_cols),
        "comparison_rows": int(len(auc_delta)),
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "phase_sanity_manifest.json", manifest)
    return manifest


def _build_phase_figures(stage: Path, df: pd.DataFrame, metric_cols: Sequence[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        return [{"figure": "ALL", "status": "MISSING_MATPLOTLIB", "detail": str(exc)}]
    candidates = [m for m in ["vphi_1p_cp_same", "vdphi_cp_clean_oof", "cp_phase_residual_circvar", "dphi_path_all"] if m in metric_cols]
    groups = [
        ("Clean-LoS", "group_clean_los"),
        ("RD-LoS", "group_rd_los_all"),
        ("RD unresolved", "group_rd_delta_tau_b_lt_1"),
        ("RD sep/direct", "group_rd_delta_tau_b_ge_1_direct_first"),
        ("NoLoS", "group_nolos"),
    ]
    for metric in candidates:
        data = []
        labels = []
        for label, col in groups:
            vals = pd.to_numeric(df.loc[df[col].fillna(False).astype(bool), metric], errors="coerce").dropna().to_numpy(dtype=float)
            if len(vals):
                data.append(vals)
                labels.append(label)
        if not data:
            rows.append({"figure": f"{metric}_boxplot.png", "status": "NO_VALID_DATA"})
            continue
        fig, ax = plt.subplots(figsize=(7.0, 4.0))
        try:
            ax.boxplot(data, tick_labels=labels, showfliers=False)
        except TypeError:
            ax.boxplot(data, labels=labels, showfliers=False)
        ax.set_ylabel(metric)
        ax.tick_params(axis="x", labelrotation=25)
        ax.set_title(f"{metric}: channel-state comparison")
        fig.tight_layout()
        name = f"{metric}_boxplot.png"
        fig.savefig(stage / name, dpi=180)
        plt.close(fig)
        rows.append({"figure": name, "status": "PRESENT", "sha256": sha256_file(stage / name)})
    return rows


def _quantile_match(df: pd.DataFrame, cols: Sequence[str], bins: int, seed: int) -> pd.DataFrame:
    clean = df[df["group_clean_los"].fillna(False).astype(bool)].copy()
    rd = df[df["group_rd_los_all"].fillna(False).astype(bool)].copy()
    for frame in [clean, rd]:
        key_parts = []
        for col in cols:
            vals = pd.to_numeric(frame[col], errors="coerce")
            try:
                q = pd.qcut(vals.rank(method="first"), q=bins, labels=False, duplicates="drop")
            except Exception:
                q = pd.Series(np.nan, index=frame.index)
            key_parts.append(q.astype("Int64").astype(str))
        frame["_match_key"] = key_parts[0]
        for part in key_parts[1:]:
            frame["_match_key"] = frame["_match_key"].astype(str) + "|" + part.astype(str)
    rng = np.random.default_rng(seed)
    pieces = []
    for key in sorted(set(clean["_match_key"]).intersection(set(rd["_match_key"]))):
        c = clean[clean["_match_key"].eq(key)]
        r = rd[rd["_match_key"].eq(key)]
        n = min(len(c), len(r))
        if n <= 0:
            continue
        pieces.append(c.iloc[rng.choice(len(c), size=n, replace=False)].copy())
        pieces.append(r.iloc[rng.choice(len(r), size=n, replace=False)].copy())
    return pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()


def build_range_matched(
    *,
    out_root_arg: str | Path | None = None,
    overwrite_stage: bool = False,
    range_gate_m: float = 0.1,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    stage = prepare_stage_dir(out, "03_range_matched", overwrite_stage)
    df = _analysis_table(out)
    metric_cols = [c for c in PRIMARY_METRICS if c in df.columns]
    df["abs_range_error_m"] = pd.to_numeric(df.get("range_error_m", np.nan), errors="coerce").abs()
    hard = df[df["abs_range_error_m"].le(float(range_gate_m))].copy()
    quantile = _quantile_match(df[df["abs_range_error_m"].notna()].copy(), ["abs_range_error_m"], 10, 20260629)
    parts = []
    for name, part in [("abs_range_error_lt_gate", hard), ("range_error_quantile_matched", quantile)]:
        if part.empty:
            continue
        tmp = _pairwise_auc_delta(part, metric_cols, suffix=name)
        tmp["match_method"] = name
        parts.append(tmp)
    result = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    result.to_csv(stage / "range_matched_auc_delta_ci.csv", index=False)
    support = _support_rows({"abs_range_error_lt_gate": hard, "range_error_quantile_matched": quantile})
    write_csv(stage / "range_match_support.csv", support)
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE" if not result.empty else "LOW_SUPPORT_OR_BLOCKED",
        "range_gate_m": range_gate_m,
        "result_rows": int(len(result)),
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "range_matched_manifest.json", manifest)
    return manifest


def build_power_matched(
    *,
    out_root_arg: str | Path | None = None,
    overwrite_stage: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    stage = prepare_stage_dir(out, "04_power_matched", overwrite_stage)
    df = _analysis_table(out)
    metric_cols = [c for c in PRIMARY_METRICS if c in df.columns]
    match_cols = [c for c in ["snr_db", "fp_peak_val", "fp_to_total_ratio"] if c in df.columns]
    matched = _quantile_match(df.dropna(subset=match_cols).copy(), match_cols, 4, 20260630) if match_cols else pd.DataFrame()
    result = _pairwise_auc_delta(matched, metric_cols, suffix="snr_fp_power_quantile_matched") if not matched.empty else pd.DataFrame()
    result["match_method"] = "snr_fp_power_quantile_matched" if not result.empty else ""
    result.to_csv(stage / "power_matched_auc_delta_ci.csv", index=False)
    write_csv(stage / "power_match_support.csv", _support_rows({"snr_fp_power_quantile_matched": matched}))
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE" if not result.empty else "LOW_SUPPORT_OR_BLOCKED",
        "match_columns": match_cols,
        "result_rows": int(len(result)),
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "power_matched_manifest.json", manifest)
    return manifest


def _support_rows(parts: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    rows = []
    for name, part in parts.items():
        if part.empty:
            rows.append({"match_method": name, "n_total": 0, "n_clean": 0, "n_rd_los": 0, "status": "LOW_SUPPORT"})
            continue
        n_clean = int(part["group_clean_los"].fillna(False).astype(bool).sum())
        n_rd = int(part["group_rd_los_all"].fillna(False).astype(bool).sum())
        rows.append(
            {
                "match_method": name,
                "n_total": int(len(part)),
                "n_clean": n_clean,
                "n_rd_los": n_rd,
                "status": "PASS" if n_clean >= 10 and n_rd >= 10 else "LOW_SUPPORT",
            }
        )
    return rows


def build_optional_ablation_skipped(*, out_root_arg: str | Path | None = None, overwrite_stage: bool = False) -> dict[str, Any]:
    out = output_root(out_root_arg)
    stage = prepare_stage_dir(out, "05b_phase_ablation", overwrite_stage)
    manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "SKIPPED_OPTIONAL_NOT_RUN",
        "reason": "Plan frames phase metrics as mechanism validation; main classifier/q_clean evidence remains in existing Theme 1 rich feature-set package.",
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(stage / "phase_ablation_manifest.json", manifest)
    return manifest


def artifact_manifest(root: Path, package_dir: Path) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() == ".zip":
            continue
        rows.append(
            {
                "relative_path": rel(path, root),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "artifact_role": "theme1_rd_los_phase_dispersion",
            }
        )
    df = pd.DataFrame(rows)
    df.to_csv(package_dir / "theme1_phase_artifact_manifest.csv", index=False)
    return df


def write_report(package_dir: Path, out: Path) -> Path:
    auc_path = out / "02_phase_sanity" / "phase_auc_median_delta.csv"
    range_path = out / "03_range_matched" / "range_matched_auc_delta_ci.csv"
    power_path = out / "04_power_matched" / "power_matched_auc_delta_ci.csv"
    source_manifest = out / "00_source_audit" / "source_manifest.json"
    status_lines = []
    for name, path in [
        ("source_audit", source_manifest),
        ("phase_sanity", out / "02_phase_sanity" / "phase_sanity_manifest.json"),
        ("range_matched", out / "03_range_matched" / "range_matched_manifest.json"),
        ("power_matched", out / "04_power_matched" / "power_matched_manifest.json"),
        ("path_mechanism", out / "05_path_mechanism" / "path_mechanism_manifest.json"),
    ]:
        status = "MISSING"
        if path.exists():
            try:
                status = str(json.loads(path.read_text(encoding="utf-8")).get("status", "UNKNOWN"))
            except Exception:
                status = "READ_FAIL"
        status_lines.append(f"| {name} | {status} | `{rel(path, out)}` |")
    top_rows = []
    if auc_path.exists():
        auc = pd.read_csv(auc_path)
        key = auc[auc["comparison"].eq("Clean-LoS_vs_RD-LoS_all")].copy()
        key = key.sort_values("auc_separation", ascending=False).head(8)
        for row in key.itertuples(index=False):
            top_rows.append(
                f"| {row.metric} | {row.auc_raw_metric_high_implies_comparison:.3f} | {row.auc_separation:.3f} | {row.median_delta_comparison_minus_clean:.4g} | {row.status} |"
            )
    if not top_rows:
        top_rows = ["| NA | NA | NA | NA | MISSING |"]
    text = "\n".join(
        [
            "# Theme 1 RD-LoS Phase Dispersion Report",
            "",
            f"Generated: {now_utc()}",
            "",
            "## Scope",
            "",
            "This package tests whether RD-LoS differs from Clean-LoS as a phase/polarization/angle channel state. It does not claim CP directly reduces range error.",
            "",
            "## Gate Status",
            "",
            "| Gate | Status | Evidence |",
            "| --- | --- | --- |",
            *status_lines,
            "",
            "## Clean-LoS vs RD-LoS Phase Metrics",
            "",
            "| Metric | Raw AUC | Separation AUC | Median delta RD-Clean | Status |",
            "| --- | ---: | ---: | ---: | --- |",
            *top_rows,
            "",
            "## Matched Comparisons",
            "",
            f"- Range-error matched table: `{rel(range_path, out)}`",
            f"- SNR/first-path-power matched table: `{rel(power_path, out)}`",
            "",
            "## Claim Boundary",
            "",
            REPORT_CLAIM_BOUNDARY,
            "",
            "## Report-Safe Wording",
            "",
            "RD-LoS is evaluated as a reflection-dominant channel state. Energy-weighted circular phase-dispersion metrics and CP co/cross differential phase metrics test whether RD-LoS departs from a single direct-path phase model even under range-error and signal-strength controls.",
            "",
        ]
    )
    path = package_dir / "THEME1_RD_LOS_PHASE_DISPERSION_REPORT.md"
    path.write_text(text, encoding="utf-8")
    return path


def build_package(*, out_root_arg: str | Path | None = None, overwrite_stage: bool = False) -> dict[str, Any]:
    out = output_root(out_root_arg)
    package_dir = prepare_stage_dir(out, "06_report_package", overwrite_stage)
    report_path = write_report(package_dir, out)
    manifest_df = artifact_manifest(out, package_dir)
    report_manifest = pd.DataFrame(
        [
            {"path": report_path.name, "bytes": report_path.stat().st_size, "sha256": sha256_file(report_path)},
            {"path": "theme1_phase_artifact_manifest.csv", "bytes": (package_dir / "theme1_phase_artifact_manifest.csv").stat().st_size, "sha256": sha256_file(package_dir / "theme1_phase_artifact_manifest.csv")},
        ]
    )
    report_manifest.to_csv(package_dir / "theme1_phase_report_manifest.csv", index=False)
    deliverables = ROOT / "deliverables"
    deliverables.mkdir(parents=True, exist_ok=True)
    zip_path = deliverables / "THEME1_RD_LOS_PHASE_DISPERSION_PACKAGE_20260629.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out.rglob("*")):
            if not path.is_file() or path == zip_path or path.name.endswith(".sha256"):
                continue
            zf.write(path, f"release/results/{rel(path, out)}")
        for path in [
            ROOT / "rt_cp_uwb_py" / "theme1_phase_dispersion.py",
            DEFAULT_PLAN,
        ]:
            if path.exists():
                zf.write(path, f"release/code/{path.name}")
        for path in sorted((ROOT / "scripts").glob("build_theme1_phase_*20260629.py")):
            zf.write(path, f"release/scripts/{path.name}")
    checksum = sha256_file(zip_path)
    (zip_path.with_suffix(zip_path.suffix + ".sha256")).write_text(f"{checksum}  {zip_path.name}\n", encoding="utf-8")
    package_manifest = {
        "created_at_utc": now_utc(),
        "script": Path(sys.argv[0]).name,
        "command_line": subprocess.list2cmdline(sys.argv),
        "status": "COMPLETE",
        "package_path": rel(zip_path),
        "sha256": checksum,
        "artifact_count": int(len(manifest_df)),
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
    write_json(package_dir / "theme1_phase_package_manifest.json", package_manifest)
    return package_manifest


def build_all(
    *,
    out_root_arg: str | Path | None = None,
    rt_root_arg: str | Path | None = None,
    split_table_arg: str | Path | None = None,
    config_arg: str | Path | None = None,
    overwrite_stage: bool = False,
    force_new_rt: bool = False,
) -> dict[str, Any]:
    out = output_root(out_root_arg)
    source = build_source_audit(out_root_arg=out, rt_root_arg=rt_root_arg, split_table_arg=split_table_arg, config_arg=config_arg, overwrite_stage=overwrite_stage, force_new_rt=force_new_rt)
    if str(source.get("status", "")).startswith("NEW_RT_REQUIRED"):
        write_json(
            out / "BLOCKED_NEW_RT_REQUIRED_SOMI.json",
            {
                "status": source.get("status"),
                "required_action": "Run additive Theme 1 full RT on Somi, then rerun phase package against the new RT root.",
                "suggested_command": "/root/.micromamba/envs/ds1/bin/python3.11 scripts/run_p2_condition_factorial_rt_chunked_fullrun_20260602.py --manifest-root results/p2_condition_factorial_prert_manifest_20260602 --out results/THEME1_CP_CHANNEL_STATE_CLASSIFICATION_FULLRT_CURRENTCODE_20260629/02_rt_fullrun --chunk-size 300 --workers 16 --max-chunks 0 --force-patch-ffd --force-lp-ffd",
            },
        )
        return source
    phase = build_phase_metrics(out_root_arg=out, rt_root_arg=rt_root_arg, split_table_arg=split_table_arg, config_arg=config_arg, overwrite_stage=overwrite_stage)
    path = build_path_mechanism(out_root_arg=out, rt_root_arg=rt_root_arg, split_table_arg=split_table_arg, config_arg=config_arg, overwrite_stage=overwrite_stage)
    sanity = build_phase_sanity(out_root_arg=out, overwrite_stage=overwrite_stage)
    range_match = build_range_matched(out_root_arg=out, overwrite_stage=overwrite_stage)
    power_match = build_power_matched(out_root_arg=out, overwrite_stage=overwrite_stage)
    ablation = build_optional_ablation_skipped(out_root_arg=out, overwrite_stage=overwrite_stage)
    package = build_package(out_root_arg=out, overwrite_stage=overwrite_stage)
    return {
        "created_at_utc": now_utc(),
        "status": "COMPLETE",
        "source": source,
        "phase": phase,
        "path": path,
        "sanity": sanity,
        "range_matched": range_match,
        "power_matched": power_match,
        "phase_ablation": ablation,
        "package": package,
        "claim_boundary": REPORT_CLAIM_BOUNDARY,
    }
