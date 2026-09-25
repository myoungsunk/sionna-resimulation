from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from .ds1v5_bridge_schema import (
    AnsysProvenanceAuditRow,
    AnsysSolveProvenance,
    BridgeValidationError,
    ComplexChannelRecord,
    decide_ansys_promotion,
    normalize_channel_id,
)


REQUIRED_CHANNEL_COLUMNS = {
    "case_id",
    "solve_id",
    "tx_polarization",
    "rx_polarization",
    "channel_id",
    "freq_hz",
}


def _has_complex_columns(df: pd.DataFrame) -> bool:
    return {"s21_re", "s21_im"}.issubset(df.columns)


def _read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() in {".tsv", ".tab"}:
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def read_ansys_provenance(path: str | Path | None) -> dict[str, AnsysSolveProvenance]:
    if path is None:
        return {}
    df = _read_table(path)
    out: dict[str, AnsysSolveProvenance] = {}
    for row in df.to_dict(orient="records"):
        prov = AnsysSolveProvenance.from_mapping(row)
        out[prov.solve_id] = prov
    return out


def _case_map_status(case_id: str, case_map: pd.DataFrame | None) -> str:
    if case_map is None:
        return "FAIL"
    if "case_id" not in case_map.columns:
        return "FAIL"
    return "PASS" if str(case_id) in set(case_map["case_id"].astype(str)) else "FAIL"


def _audit_row(
    *,
    case_id: str,
    channel_id: str,
    solve_id: str,
    provenance: dict[str, AnsysSolveProvenance],
    has_complex_s21: bool,
    channel_convention_status: str,
    case_map_status: str,
    require_somi: bool,
    allow_local_exception: bool,
    allow_warning_qualified: bool,
) -> AnsysProvenanceAuditRow:
    prov = provenance.get(str(solve_id))
    if prov is None:
        convergence_status = "UNKNOWN"
        export_status = "FAIL"
        source_file = ""
        source_hash = ""
        execution_host = ""
        txrx_role_status = "MISSING_GATE"
        ffd_handedness_gate_status = "MISSING_GATE"
        target_cs_gate_status = "MISSING_GATE"
        sbr_model_variant = "UNKNOWN"
        sbr_material_status = "MISSING_GATE"
        sbr_geometry_quality_status = "UNKNOWN"
        file_format_error_count = 0
        volume_interface_inconsistency_count = 0
        volume_interface_inconsistency_ray_count = 0
        face_contact_warning_count = 0
        source_background_region_warning_count = 0
        normal_completion_status = "UNKNOWN"
        touchstone_import_status = "UNKNOWN"
        complex_s21_status = "PASS" if has_complex_s21 else "FAIL"
        s_parameter_direction = ""
    else:
        convergence_status = prov.convergence_status
        export_status = "PASS" if prov.has_export_provenance() else "FAIL"
        source_file = prov.source_file
        source_hash = prov.source_file_sha256
        execution_host = prov.execution_host
        txrx_role_status = prov.txrx_role_status
        ffd_handedness_gate_status = prov.ffd_handedness_gate_status
        target_cs_gate_status = prov.target_cs_gate_status
        sbr_model_variant = prov.sbr_model_variant
        sbr_material_status = prov.sbr_material_status
        sbr_geometry_quality_status = prov.sbr_geometry_quality_status
        file_format_error_count = prov.file_format_error_count
        volume_interface_inconsistency_count = prov.volume_interface_inconsistency_count
        volume_interface_inconsistency_ray_count = prov.volume_interface_inconsistency_ray_count
        face_contact_warning_count = prov.face_contact_warning_count
        source_background_region_warning_count = prov.source_background_region_warning_count
        normal_completion_status = prov.normal_completion_status
        touchstone_import_status = prov.touchstone_import_status
        complex_s21_status = prov.complex_s21_status
        s_parameter_direction = prov.s_parameter_direction

    promotion, reason = decide_ansys_promotion(
        has_complex_s21=has_complex_s21,
        channel_convention_status=channel_convention_status,
        convergence_status=convergence_status,
        export_provenance_status=export_status,
        case_map_status=case_map_status,
        execution_host=execution_host,
        txrx_role_status=txrx_role_status,
        ffd_handedness_gate_status=ffd_handedness_gate_status,
        target_cs_gate_status=target_cs_gate_status,
        sbr_model_variant=sbr_model_variant,
        sbr_material_status=sbr_material_status,
        sbr_geometry_quality_status=sbr_geometry_quality_status,
        file_format_error_count=file_format_error_count,
        volume_interface_inconsistency_count=volume_interface_inconsistency_count,
        volume_interface_inconsistency_ray_count=volume_interface_inconsistency_ray_count,
        face_contact_warning_count=face_contact_warning_count,
        source_background_region_warning_count=source_background_region_warning_count,
        normal_completion_status=normal_completion_status,
        s_parameter_direction=s_parameter_direction,
        require_somi=require_somi,
        allow_local_exception=allow_local_exception,
        allow_warning_qualified=allow_warning_qualified,
    )
    geometry_warning_count = (
        int(file_format_error_count)
        + int(volume_interface_inconsistency_count)
        + int(face_contact_warning_count)
        + int(source_background_region_warning_count)
    )
    return AnsysProvenanceAuditRow(
        solve_id=str(solve_id),
        case_id=str(case_id),
        channel_id=channel_id,
        source_file=source_file,
        source_file_sha256=source_hash,
        has_complex_s21=bool(has_complex_s21),
        channel_convention_status=channel_convention_status,
        convergence_status=convergence_status,
        export_provenance_status=export_status,
        case_map_status=case_map_status,
        txrx_role_status=txrx_role_status,
        ffd_handedness_gate_status=ffd_handedness_gate_status,
        target_cs_gate_status=target_cs_gate_status,
        sbr_model_variant=sbr_model_variant,
        sbr_material_status=sbr_material_status,
        sbr_geometry_quality_status=sbr_geometry_quality_status,
        geometry_warning_count=geometry_warning_count,
        file_format_error_count=int(file_format_error_count),
        volume_interface_inconsistency_count=int(volume_interface_inconsistency_count),
        volume_interface_inconsistency_ray_count=int(volume_interface_inconsistency_ray_count),
        face_contact_warning_count=int(face_contact_warning_count),
        source_background_region_warning_count=int(source_background_region_warning_count),
        normal_completion_status=normal_completion_status,
        touchstone_import_status=touchstone_import_status,
        complex_s21_status=complex_s21_status,
        promotion_status=promotion,
        blocker_reason=reason,
    )


def load_ansys_complex_channels(
    channel_csv: str | Path,
    *,
    provenance_csv: str | Path | None = None,
    case_map_csv: str | Path | None = None,
    require_somi: bool = True,
    allow_local_exception: bool = False,
    allow_warning_qualified: bool = False,
) -> tuple[list[ComplexChannelRecord], pd.DataFrame, pd.DataFrame]:
    channels = _read_table(channel_csv)
    missing_cols = sorted(REQUIRED_CHANNEL_COLUMNS - set(channels.columns))
    if missing_cols:
        raise BridgeValidationError(f"Ansys channel table missing required columns: {missing_cols}")

    has_complex = _has_complex_columns(channels)
    provenance = read_ansys_provenance(provenance_csv)
    case_map = _read_table(case_map_csv) if case_map_csv is not None else None

    audit_rows: list[dict[str, object]] = []
    missing_case_rows: list[dict[str, object]] = []
    records: list[ComplexChannelRecord] = []

    grouped = channels.groupby(["case_id", "solve_id", "channel_id"], dropna=False, sort=True)
    for (case_id, solve_id, raw_channel_id), sub in grouped:
        case_id_s = str(case_id)
        solve_id_s = str(solve_id)
        try:
            channel_id = normalize_channel_id(str(raw_channel_id))
            channel_status = "PASS"
        except BridgeValidationError:
            channel_id = str(raw_channel_id)
            channel_status = "FAIL"
        map_status = _case_map_status(case_id_s, case_map)
        if map_status != "PASS":
            missing_case_rows.append({"case_id": case_id_s, "solve_id": solve_id_s, "channel_id": channel_id})

        audit = _audit_row(
            case_id=case_id_s,
            channel_id=channel_id,
            solve_id=solve_id_s,
            provenance=provenance,
            has_complex_s21=has_complex,
            channel_convention_status=channel_status,
            case_map_status=map_status,
            require_somi=require_somi,
            allow_local_exception=allow_local_exception,
            allow_warning_qualified=allow_warning_qualified,
        )
        audit_rows.append(audit.to_dict())
        accepted_statuses = {"PROMOTED_TO_MAIN_BRIDGE"}
        if allow_warning_qualified:
            accepted_statuses.add("MAIN_BRIDGE_CANDIDATE_WARNING_QUALIFIED")
        if audit.promotion_status not in accepted_statuses:
            continue

        sub = sub.sort_values("freq_hz")
        freq = sub["freq_hz"].to_numpy(float)
        H = sub["s21_re"].to_numpy(float) + 1j * sub["s21_im"].to_numpy(float)
        prov = provenance[solve_id_s]
        source_id = f"SOMI_AEDT_CASE{case_id_s}"
        for source_col in ("source_id", "channel_bundle_id"):
            if source_col in sub.columns:
                values = [str(v) for v in sub[source_col].dropna().unique() if str(v).strip()]
                if values:
                    source_id = values[0]
                    break
        records.append(
            ComplexChannelRecord(
                case_id=case_id_s,
                channel_id=channel_id,
                freq_hz=freq,
                H_f=H,
                source_kind="SOMI_ANSYS" if str(prov.execution_host).upper() == "SOMI" else "LOCAL_DIAGNOSTIC",
                source_id=source_id,
                solve_id=solve_id_s,
                phase_mode="physical_delay",
                metadata={
                    "execution_host": prov.execution_host,
                    "remote_workdir": prov.remote_workdir,
                    "channel_source_file": prov.source_file,
                    "channel_source_file_sha256": prov.source_file_sha256,
                },
            )
        )

    audit_df = pd.DataFrame(audit_rows)
    missing_df = pd.DataFrame(missing_case_rows, columns=["case_id", "solve_id", "channel_id"])
    return records, audit_df, missing_df


def write_import_audits(
    output_root: str | Path,
    audit_df: pd.DataFrame,
    missing_case_df: pd.DataFrame,
) -> None:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    audit_df.to_csv(root / "ansys_provenance_audit.csv", index=False)
    missing_case_df.to_csv(root / "missing_case_report.csv", index=False)
