from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


READINESS_SCHEMA_VERSION = "DS1_MEASUREMENT_READINESS.v1"


@dataclass(frozen=True)
class DS1MeasurementReadinessConfig:
    max_primary_candidates: int = 6
    max_control_candidates: int = 3
    min_measured_lo_db: float = 3.0
    min_measured_lo_ratio: float = 2.0
    min_tail_reduction_abs_gt_0p3m: float = 0.10
    min_p95_reduction_m: float = 0.05
    max_ready_theta_deg: float = 78.0
    min_co_separation_margin_db: float = 3.0
    max_arrival_axial_ratio_db: float = 6.0


@dataclass(frozen=True)
class DS1MeasurementReadinessBundle:
    readiness_rows: list[dict[str, str]]
    fixture_candidates: list[dict[str, str]]
    review_rows: list[dict[str, str]]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_csv_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = _field_order(rows)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_readiness_bundle(
    target_rows: list[dict[str, str]],
    phase1_rows: list[dict[str, str]] | None = None,
    config: DS1MeasurementReadinessConfig | None = None,
) -> DS1MeasurementReadinessBundle:
    cfg = config or DS1MeasurementReadinessConfig()
    readiness_rows = [assess_target_row(row, cfg) for row in target_rows]
    primary_candidates: list[dict[str, str]] = []
    for source, assessed in zip(target_rows, readiness_rows):
        if assessed["readiness_status"] != "READY_FOR_CAD_FIXTURE_PLANNING":
            continue
        if len(primary_candidates) >= int(cfg.max_primary_candidates):
            continue
        primary_candidates.append(_target_candidate_row(source, assessed, "primary_stress_target"))

    selected_geometry_ids = {row.get("geometry_id", "") for row in primary_candidates if row.get("geometry_id", "")}
    control_candidates = build_control_candidates(
        phase1_rows or [],
        start_rank=101,
        selected_geometry_ids=selected_geometry_ids,
        max_controls=int(cfg.max_control_candidates),
    )
    review_rows = [row for row in readiness_rows if row["readiness_status"] != "READY_FOR_CAD_FIXTURE_PLANNING"]
    return DS1MeasurementReadinessBundle(
        readiness_rows=readiness_rows,
        fixture_candidates=primary_candidates + control_candidates,
        review_rows=review_rows,
    )


def assess_target_row(row: dict[str, str], config: DS1MeasurementReadinessConfig | None = None) -> dict[str, str]:
    cfg = config or DS1MeasurementReadinessConfig()
    rank = int(float(_get(row, "rank", default="0") or 0))
    material = _get(row, "m", "material", "material_key", default="")
    D_m = _num(row, "D", "D_m")
    u = _num(row, "u")
    theta_deg = _num(row, "theta_deg")
    e_lo = _num(row, "E_mit_measured_lo", default=math.nan)
    e_lo_db = _num(row, "E_mit_db_measured_lo", default=math.nan)
    tail_red = _num(row, "tail_reduction_abs_gt_0p3m_measured_lo", default=math.nan)
    p95_red = _num(row, "p95_reduction_m_measured_lo", default=math.nan)
    noise_floor = _num(row, "var_noise_floor_m2", default=math.nan)
    co_var = _num(row, "var_co_dw1000_m2", default=math.nan)
    generator = _get(row, "generator_type", default="")
    target_lock_gate = _get(row, "target_lock_gate_pass_measured_lo", "target_lock_gate_pass", default="")
    has_v3_lock = bool(target_lock_gate)
    target_lock_ok = (not has_v3_lock) or target_lock_gate.strip().lower() == "true"
    buildability_gate = _get(row, "buildability_pass_measured_lo", "buildability_pass", default="")
    has_buildability_gate = bool(buildability_gate)
    buildability_ok = (not has_buildability_gate) or buildability_gate.strip().lower() == "true"
    co_sep = _num(row, "co_separation_margin_db_measured_lo", "co_separation_margin_db", default=math.nan)
    arrival_ar = _num(row, "arrival_axial_ratio_db_measured_lo", "arrival_axial_ratio_db", default=math.nan)

    reasons: list[str] = []
    if not math.isfinite(e_lo) or not math.isfinite(e_lo_db):
        reasons.append("missing_measured_lo_E_mit")
    if math.isfinite(e_lo) and e_lo < cfg.min_measured_lo_ratio:
        reasons.append(f"E_mit_measured_lo<{cfg.min_measured_lo_ratio:g}")
    if math.isfinite(e_lo_db) and e_lo_db < cfg.min_measured_lo_db:
        reasons.append(f"E_mit_db_measured_lo<{cfg.min_measured_lo_db:g}")
    if not math.isfinite(noise_floor) or noise_floor <= 0.0:
        reasons.append("noise_floor_missing_or_zero")
    if math.isfinite(co_var) and math.isfinite(noise_floor) and co_var <= 0.0:
        reasons.append("co_variance_zero")
    if not generator:
        reasons.append("generator_type_missing")
    if has_v3_lock and not target_lock_ok:
        reasons.append("target_lock_gate_not_passed")
    if has_buildability_gate and not buildability_ok:
        reasons.append("buildability_gate_not_passed")
    if has_v3_lock and math.isfinite(co_sep) and co_sep < cfg.min_co_separation_margin_db:
        reasons.append(f"co_separation_margin_db<{cfg.min_co_separation_margin_db:g}")
    if has_v3_lock and math.isfinite(arrival_ar) and arrival_ar > cfg.max_arrival_axial_ratio_db:
        reasons.append(f"arrival_axial_ratio_db>{cfg.max_arrival_axial_ratio_db:g}")
    if theta_deg > cfg.max_ready_theta_deg and not has_v3_lock:
        reasons.append(f"theta_deg>{cfg.max_ready_theta_deg:g}")
    elif theta_deg > cfg.max_ready_theta_deg:
        reasons.append(f"high_oblique_fixture_review_theta_deg>{cfg.max_ready_theta_deg:g}")
    if math.isfinite(tail_red) and tail_red < cfg.min_tail_reduction_abs_gt_0p3m:
        reasons.append(f"tail_reduction_abs_gt_0p3m_measured_lo<{cfg.min_tail_reduction_abs_gt_0p3m:g}")
    if math.isfinite(p95_red) and p95_red < cfg.min_p95_reduction_m:
        reasons.append(f"p95_reduction_m_measured_lo<{cfg.min_p95_reduction_m:g}")

    hard_block = any(reason in {"missing_measured_lo_E_mit", "noise_floor_missing_or_zero", "co_variance_zero"} for reason in reasons)
    core_ok = (
        math.isfinite(e_lo)
        and math.isfinite(e_lo_db)
        and math.isfinite(noise_floor)
        and e_lo >= cfg.min_measured_lo_ratio
        and e_lo_db >= cfg.min_measured_lo_db
        and noise_floor > 0.0
        and bool(generator)
        and target_lock_ok
        and buildability_ok
    )
    measurement_effect_ok = (
        math.isfinite(tail_red)
        and math.isfinite(p95_red)
        and tail_red >= cfg.min_tail_reduction_abs_gt_0p3m
        and p95_red >= cfg.min_p95_reduction_m
    )
    geometry_ok = has_v3_lock or theta_deg <= cfg.max_ready_theta_deg
    if core_ok and measurement_effect_ok and geometry_ok and not hard_block:
        readiness_status = "READY_FOR_CAD_FIXTURE_PLANNING"
    elif hard_block:
        readiness_status = "BLOCKED_FOR_FIXTURE_PLANNING"
    else:
        readiness_status = "REVIEW_BEFORE_FIXTURE"

    return {
        "schema_version": READINESS_SCHEMA_VERSION,
        "rank": str(rank),
        "candidate_id": _candidate_id(rank, material, D_m, u, generator),
        "candidate_role": "primary_stress_target",
        "m": material,
        "D": _fmt(D_m),
        "u": _fmt(u),
        "actual_u": _get(row, "actual_u", default=""),
        "actual_delta_d_m": _get(row, "actual_delta_d_m", default=""),
        "u_preservation_error_m": _get(row, "u_preservation_error_m", default=""),
        "u_preservation_pass": _get(row, "u_preservation_pass", default=""),
        "theta_deg": _fmt(theta_deg),
        "wall_tilt_deg": _get(row, "wall_tilt_deg", default="0"),
        "at_asymmetry_frac": _get(row, "at_asymmetry_frac", default="0"),
        "specular_endpoint_margin_m": _get(row, "specular_endpoint_margin_m", default=""),
        "fixture_plate_span_m": _get(row, "fixture_plate_span_m", default=""),
        "hfss_auto_plate_width_m": _get(row, "hfss_auto_plate_width_m", default=""),
        "generator_type": generator,
        "fixture_class": fixture_class(theta_deg),
        "readiness_status": readiness_status,
        "claim_status": "MEASUREMENT_CLAIM_BLOCKED_UNTIL_MEASURED_ROWS_EXIST",
        "gate_reasons": ";".join(reasons) if reasons else "pass",
        "E_mit_measured_lo": _fmt(e_lo),
        "E_mit_db_measured_lo": _fmt(e_lo_db),
        "tail_reduction_abs_gt_0p3m_measured_lo": _fmt(tail_red),
        "p95_reduction_m_measured_lo": _fmt(p95_red),
        "var_noise_floor_m2": _fmt(noise_floor),
        "var_co_dw1000_m2": _fmt(co_var),
        "target_lock_gate_pass_measured_lo": target_lock_gate,
        "buildability_pass_measured_lo": buildability_gate,
        "buildability_status_measured_lo": _get(row, "buildability_status_measured_lo", "buildability_status", default=""),
        "buildability_reasons_measured_lo": _get(row, "buildability_reasons_measured_lo", "buildability_reasons", default=""),
        "co_separation_margin_db_measured_lo": _fmt(co_sep),
        "arrival_axial_ratio_db_measured_lo": _fmt(arrival_ar),
        "ranking_basis": _get(row, "ranking_basis", default=""),
        "required_action": (
            "Build CAD/fixture plan and collect measured LP CIR plus CP co/cross CIR; do not use this row as measurement evidence."
        ),
    }


def fixture_class(theta_deg: float) -> str:
    if theta_deg <= 60.0:
        return "NEAR_NORMAL_CONTROL_COMPATIBLE"
    if theta_deg <= 75.0:
        return "OBLIQUE_FIXTURE_COMPATIBLE"
    if theta_deg <= 80.0:
        return "HIGH_OBLIQUE_REVIEW"
    return "GRAZING_REVIEW"


def build_control_candidates(
    phase1_rows: list[dict[str, str]],
    start_rank: int = 101,
    selected_geometry_ids: set[str] | None = None,
    max_controls: int = 3,
) -> list[dict[str, str]]:
    selected = selected_geometry_ids or set()
    specs = [
        ("control_best_glass", lambda row: _get(row, "material", default="") == "glass"),
        ("control_best_drywall", lambda row: _get(row, "material", default="") == "drywall"),
        (
            "control_near_normal_metal",
            lambda row: _get(row, "material", default="") == "metal" and _num(row, "theta_deg", default=999.0) <= 60.0,
        ),
    ]
    controls: list[dict[str, str]] = []
    for role, predicate in specs:
        if len(controls) >= int(max_controls):
            break
        pool = [
            row
            for row in phase1_rows
            if predicate(row) and _get(row, "geometry_id", default="") not in selected
        ]
        if not pool:
            continue
        best = max(pool, key=lambda row: _num(row, "E_mit_conservative_db", default=-999.0))
        controls.append(_phase1_control_candidate_row(best, start_rank + len(controls), role))
        selected.add(_get(best, "geometry_id", default=""))
    return controls


def write_readiness_outputs(
    output_root: Path,
    source_run_root: Path,
    target_rows: list[dict[str, str]],
    phase1_rows: list[dict[str, str]],
    command_line: str,
    config: DS1MeasurementReadinessConfig | None = None,
) -> dict[str, object]:
    cfg = config or DS1MeasurementReadinessConfig()
    output_root.mkdir(parents=True, exist_ok=True)
    bundle = build_readiness_bundle(target_rows, phase1_rows, cfg)

    readiness_csv = output_root / "DS1_measurement_readiness_table.csv"
    fixture_csv = output_root / "DS1_measurement_fixture_candidates.csv"
    review_csv = output_root / "DS1_measurement_blocked_or_review_candidates.csv"
    note_md = output_root / "DS1_measurement_protocol_note.md"
    manifest_json = output_root / "DS1_measurement_readiness_manifest.json"

    write_csv_rows(readiness_csv, bundle.readiness_rows)
    write_csv_rows(fixture_csv, bundle.fixture_candidates)
    write_csv_rows(review_csv, bundle.review_rows)
    note_md.write_text(_protocol_note(source_run_root, bundle, cfg), encoding="utf-8")

    outputs = [readiness_csv, fixture_csv, review_csv, note_md]
    manifest = {
        "schema_version": READINESS_SCHEMA_VERSION,
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "command_line": command_line,
        "source_run_root": str(source_run_root),
        "config": asdict(cfg),
        "input_files": _input_records(
            [
                source_run_root / "DS1_measurement_targets.csv",
                source_run_root / "phase1" / "phase1_geometry_metrics.csv",
                source_run_root / "DS1_manifest.json",
            ]
        ),
        "output_files": _input_records(outputs),
        "primary_ready_count": sum(
            1 for row in bundle.readiness_rows if row["readiness_status"] == "READY_FOR_CAD_FIXTURE_PLANNING"
        ),
        "fixture_candidate_count": len(bundle.fixture_candidates),
        "claim_boundary": [
            "measurement planning only",
            "not measured LP/CP evidence",
            "not full-wave channel evidence",
            "Paper 1 must not claim CP directly reduces range error",
        ],
    }
    manifest_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "output_root": str(output_root),
        "source_run_root": str(source_run_root),
        "readiness_table": str(readiness_csv),
        "fixture_candidates": str(fixture_csv),
        "review_table": str(review_csv),
        "protocol_note": str(note_md),
        "manifest": str(manifest_json),
        "primary_ready_count": manifest["primary_ready_count"],
        "fixture_candidate_count": len(bundle.fixture_candidates),
    }


def _target_candidate_row(source: dict[str, str], assessed: dict[str, str], role: str) -> dict[str, str]:
    row = dict(source)
    row["candidate_id"] = assessed["candidate_id"]
    row["candidate_role"] = role
    row["readiness_status"] = assessed["readiness_status"]
    row["claim_status"] = assessed["claim_status"]
    row["fixture_class"] = assessed["fixture_class"]
    row["gate_reasons"] = assessed["gate_reasons"]
    return row


def _phase1_control_candidate_row(row: dict[str, str], rank: int, role: str) -> dict[str, str]:
    material = _get(row, "material", default="")
    D_m = _num(row, "D_m")
    u = _num(row, "u")
    generator = _get(row, "generator_type", default="baseline_image_method") or "baseline_image_method"
    theta = _num(row, "theta_deg")
    return {
        "rank": str(rank),
        "candidate_id": _candidate_id(rank, material, D_m, u, role),
        "candidate_role": role,
        "geometry_id": _get(row, "geometry_id", default=""),
        "m": material,
        "s": _get(row, "s_m", default=""),
        "D": _fmt(D_m),
        "theta_deg": _fmt(theta),
        "u": _fmt(u),
        "actual_u": _get(row, "actual_u", default=""),
        "actual_delta_d_m": _get(row, "actual_delta_d_m", default=""),
        "u_preservation_error_m": _get(row, "u_preservation_error_m", default=""),
        "u_preservation_pass": _get(row, "u_preservation_pass", default=""),
        "rho": _get(row, "rho", default=""),
        "wall_tilt_deg": _get(row, "wall_tilt_deg", default="0"),
        "at_asymmetry_frac": _get(row, "at_asymmetry_frac", default="0"),
        "at_normal_offset_m": _get(row, "at_normal_offset_m", default="0"),
        "specular_endpoint_margin_m": _get(row, "specular_endpoint_margin_m", default=""),
        "fixture_plate_span_m": _get(row, "fixture_plate_span_m", default=""),
        "hfss_auto_plate_width_m": _get(row, "hfss_auto_plate_width_m", default=""),
        "generator_type": generator,
        "phi_worst": _get(row, "phi_worst", default=""),
        "E_mit_ideal": _get(row, "E_mit_conservative", default=""),
        "E_mit_db_ideal": _get(row, "E_mit_conservative_db", default=""),
        "E_mit_measured_lo": "",
        "E_mit_db_measured_lo": "",
        "rank_score": _get(row, "rank_score", default=""),
        "ranking_basis": "phase1_control_not_phase4_nonideality_band",
        "readiness_status": "CONTROL_FOR_CONTRAST_NOT_PRIMARY_TARGET",
        "claim_status": "MEASUREMENT_CLAIM_BLOCKED_UNTIL_MEASURED_ROWS_EXIST",
        "fixture_class": fixture_class(theta),
        "gate_reasons": "control_candidate_not_primary_ranked_target",
    }


def _protocol_note(
    source_run_root: Path,
    bundle: DS1MeasurementReadinessBundle,
    config: DS1MeasurementReadinessConfig,
) -> str:
    ready = [row for row in bundle.readiness_rows if row["readiness_status"] == "READY_FOR_CAD_FIXTURE_PLANNING"]
    top_lines = ["| rank | role | material | D_m | u | theta_deg | status |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in bundle.fixture_candidates[: max(1, int(config.max_primary_candidates) + int(config.max_control_candidates))]:
        top_lines.append(
            "| "
            + " | ".join(
                [
                    row.get("rank", ""),
                    row.get("candidate_role", ""),
                    row.get("m", ""),
                    row.get("D", ""),
                    row.get("u", ""),
                    row.get("theta_deg", ""),
                    row.get("readiness_status", ""),
                ]
            )
            + " |"
        )
    return "\n".join(
        [
            "# DS1 Measurement Readiness Gate",
            "",
            f"Source run root: `{source_run_root}`",
            "",
            "## Decision",
            "",
            "- Status: fixture/CAD planning only.",
            f"- Primary targets ready for CAD planning: {len(ready)} of {len(bundle.readiness_rows)}.",
            f"- Fixture candidate rows emitted: {len(bundle.fixture_candidates)}.",
            "- Controlled measurement claims remain blocked until measured LP CIR and CP co/cross CIR rows are collected.",
            "- The fixed DS1 ranking is noise-aware, but it remains image-method/geometrical-optics simulation, not full-wave channel evidence.",
            "",
            "## Fixture Candidates",
            "",
            *top_lines,
            "",
            "## Required Measurement Inputs",
            "",
            "- LP CIR and first-path estimate from the same detector stack used for the control row.",
            "- CP co-channel CIR and CP cross-channel CIR for the same pose, material, and scan phase.",
            "- Fixture geometry record: material, D, u, wall tilt, A/T asymmetry, TX/RX polarization sense, and antenna orientation.",
            "- Per-session noise-floor estimate or empty-scene/direct-only reference.",
            "",
            "## Claim Boundary",
            "",
            "- Do not claim that CP directly reduces range error.",
            "- Do not describe selected rows as hardware evidence before measured rows exist.",
            "- Do not describe CAD/HFSS scaffolds as solved full-wave evidence unless AEDT solve, mesh, convergence, ports, antenna model, and S-parameter export are verified.",
            "",
        ]
    )


def _input_records(paths: Iterable[Path]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for path in paths:
        records.append(
            {
                "path": str(path),
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "sha256": _sha256(path) if path.exists() and path.is_file() else None,
            }
        )
    return records


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _field_order(rows: list[dict[str, str]]) -> list[str]:
    preferred = [
        "schema_version",
        "rank",
        "candidate_id",
        "candidate_role",
        "geometry_id",
        "m",
        "D",
        "u",
        "theta_deg",
        "wall_tilt_deg",
        "at_asymmetry_frac",
        "at_normal_offset_m",
        "generator_type",
        "fixture_class",
        "readiness_status",
        "claim_status",
        "gate_reasons",
    ]
    fields: list[str] = []
    for field in preferred:
        if any(field in row for row in rows):
            fields.append(field)
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    return fields


def _candidate_id(rank: int, material: str, D_m: float, u: float, variant: str) -> str:
    return f"DS1_M{rank:03d}_{_safe(material)}_D{_token(D_m)}_u{_token(u)}_{_safe(variant)[:36]}"


def _get(row: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return str(value)
    return default


def _num(row: dict[str, str], *names: str, default: float | None = None) -> float:
    value = _get(row, *names, default="")
    if value == "":
        if default is None:
            raise KeyError("missing numeric field: " + " or ".join(names))
        return float(default)
    return float(value)


def _fmt(value: float) -> str:
    if not math.isfinite(float(value)):
        return ""
    return f"{float(value):.12g}"


def _token(value: float) -> str:
    text = f"{float(value):.3f}".rstrip("0").rstrip(".")
    return text.replace("-", "m").replace(".", "p")


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in str(text))
