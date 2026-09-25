from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

import numpy as np


VALID_CHANNEL_IDS = {"LP-LP", "RHCP-RHCP", "RHCP-LHCP", "LHCP-LHCP", "LHCP-RHCP"}
VALID_SOURCE_KINDS = {"LOCAL_MOCK", "SOMI_PY_RT", "SOMI_ANSYS", "LOCAL_DIAGNOSTIC"}
VALID_SPLIT_AUDIT_STATUS = {"PASS", "BLOCKED_FOR_PRIMARY", "DIAGNOSTIC_NOT_PRIMARY"}
VALID_CONVERGENCE_STATUS = {"PASS", "CONVERGED", "FAIL", "UNKNOWN"}
VALID_PROVENANCE_PROMOTION_STATUS = {
    "PROMOTED_TO_MAIN",
    "PROMOTED_TO_MAIN_BRIDGE",
    "MAIN_BRIDGE_CANDIDATE_WARNING_QUALIFIED",
    "DIAGNOSTIC_ONLY",
    "BLOCKED_MISSING_COMPLEX",
    "BLOCKED_AMBIGUOUS_CHANNEL",
    "BLOCKED_UNCONVERGED",
    "BLOCKED_MISSING_EXPORT_PROVENANCE",
    "BLOCKED_MISSING_CASE_MAP",
    "BLOCKED_BY_TXRX_MISMATCH",
    "BLOCKED_BY_FFD_GATE",
    "BLOCKED_BY_TARGET_CS_GATE",
    "BLOCKED_BY_SBR_GEOMETRY_WARNING",
    "BLOCKED_BY_MATERIAL_SURROGATE",
}


class BridgeValidationError(ValueError):
    """Raised when DS1v5 bridge data cannot be used as main evidence."""


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(np.isnan(value))
    except TypeError:
        return False
    except ValueError:
        return False


def _int_or_zero(value: Any) -> int:
    if _is_missing(value) or value == "":
        return 0
    return int(float(value))


def normalize_channel_id(channel_id: str) -> str:
    value = str(channel_id).strip().upper()
    aliases = {
        "LP": "LP-LP",
        "LP_LP": "LP-LP",
        "RHCP_RHCP": "RHCP-RHCP",
        "RHCP_LHCP": "RHCP-LHCP",
        "LHCP_LHCP": "LHCP-LHCP",
        "LHCP_RHCP": "LHCP-RHCP",
    }
    value = aliases.get(value, value)
    if value not in VALID_CHANNEL_IDS:
        raise BridgeValidationError(
            f"Ambiguous or unsupported channel_id={channel_id!r}; expected one of {sorted(VALID_CHANNEL_IDS)}"
        )
    return value


def ensure_complex_array(values: Any, *, name: str = "H_f") -> np.ndarray:
    arr = np.asarray(values)
    if not np.iscomplexobj(arr):
        raise BridgeValidationError(f"{name} must be complex dtype; magnitude-only arrays are blocked")
    if arr.ndim != 1:
        raise BridgeValidationError(f"{name} must be a one-dimensional frequency response")
    if arr.size < 2:
        raise BridgeValidationError(f"{name} must contain at least two frequency samples")
    if not np.all(np.isfinite(arr.real)) or not np.all(np.isfinite(arr.imag)):
        raise BridgeValidationError(f"{name} contains non-finite complex values")
    return arr.astype(np.complex128, copy=False)


def ensure_frequency_grid(freq_hz: Any) -> np.ndarray:
    arr = np.asarray(freq_hz, dtype=float)
    if arr.ndim != 1 or arr.size < 2:
        raise BridgeValidationError("freq_hz must be a one-dimensional grid with at least two samples")
    if not np.all(np.isfinite(arr)):
        raise BridgeValidationError("freq_hz contains non-finite values")
    if not np.all(np.diff(arr) > 0):
        raise BridgeValidationError("freq_hz must be strictly monotone increasing")
    return arr


@dataclass(frozen=True)
class ChannelFeatureConfig:
    band_min_hz: float | None = None
    band_max_hz: float | None = None
    cir_window: str = "hann"
    eps: float = 1e-15


@dataclass(frozen=True)
class ComplexChannelRecord:
    case_id: str
    channel_id: str
    freq_hz: np.ndarray
    H_f: np.ndarray
    source_kind: str
    source_id: str
    solve_id: str = ""
    phase_mode: str = "physical_delay"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel_id", normalize_channel_id(self.channel_id))
        freq = ensure_frequency_grid(self.freq_hz)
        H = ensure_complex_array(self.H_f)
        if len(freq) != len(H):
            raise BridgeValidationError("freq_hz and H_f lengths do not match")
        source_kind = str(self.source_kind)
        if source_kind not in VALID_SOURCE_KINDS:
            raise BridgeValidationError(f"Unsupported source_kind={source_kind!r}")
        object.__setattr__(self, "freq_hz", freq)
        object.__setattr__(self, "H_f", H)

    def to_feature_identity(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "channel_id": self.channel_id,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "solve_id": self.solve_id,
            "phase_mode": self.phase_mode,
        }


@dataclass(frozen=True)
class FrequencyGridManifest:
    frequency_grid_id: str
    n_frequency: int
    freq_min_hz: float
    freq_max_hz: float
    spacing_hz: float

    @classmethod
    def from_grid(cls, frequency_grid_id: str, freq_hz: Any) -> "FrequencyGridManifest":
        freq = ensure_frequency_grid(freq_hz)
        spacing = float(np.median(np.diff(freq)))
        return cls(
            frequency_grid_id=str(frequency_grid_id),
            n_frequency=int(freq.size),
            freq_min_hz=float(freq[0]),
            freq_max_hz=float(freq[-1]),
            spacing_hz=spacing,
        )


@dataclass(frozen=True)
class ChannelConventionManifest:
    channel_convention_id: str
    tx_polarization: str
    rx_polarization: str
    channel_id: str
    convention_status: str = "PASS"

    def __post_init__(self) -> None:
        object.__setattr__(self, "channel_id", normalize_channel_id(self.channel_id))


@dataclass(frozen=True)
class CaseAlignmentRow:
    case_id: str
    pose_group_id: str
    cad_variant_family: str
    source_geometry_family: str


@dataclass(frozen=True)
class AnsysSolveProvenance:
    solve_id: str
    aedt_project_path: str
    design_name: str
    setup_name: str
    solver_version: str
    adaptive_pass_count: int
    convergence_metric_name: str
    convergence_metric_value: float
    convergence_status: str
    export_command: str
    source_file: str
    source_file_sha256: str
    channel_convention_id: str
    frequency_grid_id: str
    case_map_id: str
    execution_host: str = ""
    remote_workdir: str = ""
    export_timestamp: str = ""
    tx_role: str = ""
    rx_role: str = ""
    tx_pose_xyz: str = ""
    rx_pose_xyz: str = ""
    s_parameter_direction: str = ""
    txrx_role_status: str = "MISSING_GATE"
    ffd_handedness_gate_status: str = "MISSING_GATE"
    target_cs_gate_status: str = "MISSING_GATE"
    sbr_model_variant: str = "PHYSICAL_MATERIALS"
    sbr_material_status: str = "PASS"
    sbr_room_material_override: str = ""
    sbr_condition_material_override: str = ""
    sbr_no_room: str = ""
    sbr_geometry_quality_status: str = "UNKNOWN"
    file_format_error_count: int = 0
    volume_interface_inconsistency_count: int = 0
    volume_interface_inconsistency_ray_count: int = 0
    face_contact_warning_count: int = 0
    source_background_region_warning_count: int = 0
    normal_completion_status: str = "UNKNOWN"
    touchstone_import_status: str = "UNKNOWN"
    complex_s21_status: str = "UNKNOWN"

    def __post_init__(self) -> None:
        status = str(self.convergence_status).upper()
        if status not in VALID_CONVERGENCE_STATUS:
            raise BridgeValidationError(f"Invalid convergence_status={self.convergence_status!r}")
        object.__setattr__(self, "convergence_status", status)

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any]) -> "AnsysSolveProvenance":
        data = {}
        for key, field_def in cls.__dataclass_fields__.items():
            value = row.get(key, field_def.default)
            if _is_missing(value):
                value = field_def.default
            data[key] = value
        data["adaptive_pass_count"] = _int_or_zero(data.get("adaptive_pass_count"))
        data["convergence_metric_value"] = float(data.get("convergence_metric_value") or float("nan"))
        for key in [
            "file_format_error_count",
            "volume_interface_inconsistency_count",
            "volume_interface_inconsistency_ray_count",
            "face_contact_warning_count",
            "source_background_region_warning_count",
        ]:
            data[key] = _int_or_zero(data.get(key))
        return cls(**data)

    def has_export_provenance(self) -> bool:
        return bool(self.export_command and self.source_file and self.source_file_sha256)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SplitLeakageAuditRow:
    eval_arm: str
    fold_id: str
    split_kind: str
    group_key: str
    n_train_unique: int
    n_test_unique: int
    n_overlap: int
    overlap_examples: str
    status: str

    def __post_init__(self) -> None:
        if self.status not in VALID_SPLIT_AUDIT_STATUS:
            raise BridgeValidationError(f"Invalid split leakage status={self.status!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AnsysProvenanceAuditRow:
    solve_id: str
    case_id: str
    channel_id: str
    source_file: str
    source_file_sha256: str
    has_complex_s21: bool
    channel_convention_status: str
    convergence_status: str
    export_provenance_status: str
    case_map_status: str
    txrx_role_status: str
    ffd_handedness_gate_status: str
    target_cs_gate_status: str
    sbr_model_variant: str
    sbr_material_status: str
    sbr_geometry_quality_status: str
    geometry_warning_count: int
    file_format_error_count: int
    volume_interface_inconsistency_count: int
    volume_interface_inconsistency_ray_count: int
    face_contact_warning_count: int
    source_background_region_warning_count: int
    normal_completion_status: str
    touchstone_import_status: str
    complex_s21_status: str
    promotion_status: str
    blocker_reason: str

    def __post_init__(self) -> None:
        if self.promotion_status not in VALID_PROVENANCE_PROMOTION_STATUS:
            raise BridgeValidationError(f"Invalid promotion_status={self.promotion_status!r}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def decide_ansys_promotion(
    *,
    has_complex_s21: bool,
    channel_convention_status: str,
    convergence_status: str,
    export_provenance_status: str,
    case_map_status: str,
    execution_host: str,
    txrx_role_status: str = "PASS",
    ffd_handedness_gate_status: str = "PASS",
    target_cs_gate_status: str = "PASS",
    sbr_model_variant: str = "PHYSICAL_MATERIALS",
    sbr_material_status: str = "PASS",
    sbr_geometry_quality_status: str = "PASS",
    file_format_error_count: int = 0,
    volume_interface_inconsistency_count: int = 0,
    volume_interface_inconsistency_ray_count: int = 0,
    face_contact_warning_count: int = 0,
    source_background_region_warning_count: int = 0,
    normal_completion_status: str = "PASS",
    s_parameter_direction: str = "S21_tag_to_anchor",
    require_somi: bool = True,
    allow_local_exception: bool = False,
    allow_warning_qualified: bool = False,
    warning_qualified_volume_ray_cap: int = 100,
) -> tuple[str, str]:
    if not has_complex_s21:
        return "BLOCKED_MISSING_COMPLEX", "complex S21 columns are missing"
    if str(channel_convention_status).upper() != "PASS":
        return "BLOCKED_AMBIGUOUS_CHANNEL", "channel convention is not PASS"
    if str(convergence_status).upper() not in {"PASS", "CONVERGED"}:
        return "BLOCKED_UNCONVERGED", "solve convergence is not PASS/CONVERGED"
    if str(export_provenance_status).upper() != "PASS":
        return "BLOCKED_MISSING_EXPORT_PROVENANCE", "export command/source hash provenance missing"
    if str(case_map_status).upper() != "PASS":
        return "BLOCKED_MISSING_CASE_MAP", "case map is missing or incomplete"
    if require_somi and str(execution_host).upper() != "SOMI" and not allow_local_exception:
        return "BLOCKED_MISSING_EXPORT_PROVENANCE", "real Ansys evidence requires execution_host=SOMI"
    if str(txrx_role_status).upper() != "PASS" or str(s_parameter_direction) != "S21_tag_to_anchor":
        return "BLOCKED_BY_TXRX_MISMATCH", "AEDT source/receiver role gate is not PASS for S21_tag_to_anchor"
    if str(ffd_handedness_gate_status).upper() != "PASS":
        return "BLOCKED_BY_FFD_GATE", "independent FFD handedness gate is missing or not PASS"
    if str(target_cs_gate_status).upper() != "PASS":
        return "BLOCKED_BY_TARGET_CS_GATE", "target coordinate-system gate is missing or not PASS"
    if str(sbr_material_status).upper() != "PASS" or str(sbr_model_variant).upper() != "PHYSICAL_MATERIALS":
        return "DIAGNOSTIC_ONLY", (
            "SBR model uses non-physical-material diagnostic variant; "
            f"sbr_model_variant={sbr_model_variant}, sbr_material_status={sbr_material_status}"
        )
    if str(normal_completion_status).upper() not in {"PASS", "TRUE", "OK"}:
        return "BLOCKED_BY_SBR_GEOMETRY_WARNING", "AEDT run did not report normal completion"
    warning_count = (
        int(file_format_error_count)
        + int(volume_interface_inconsistency_count)
        + int(face_contact_warning_count)
        + int(source_background_region_warning_count)
    )
    if str(sbr_geometry_quality_status).upper() == "FAIL":
        return "BLOCKED_BY_SBR_GEOMETRY_WARNING", "SBR geometry quality gate failed"
    if warning_count > 0 or str(sbr_geometry_quality_status).upper() == "WARN":
        if (
            allow_warning_qualified
            and int(face_contact_warning_count) == 0
            and int(source_background_region_warning_count) == 0
            and int(volume_interface_inconsistency_ray_count) <= int(warning_qualified_volume_ray_cap)
        ):
            return "MAIN_BRIDGE_CANDIDATE_WARNING_QUALIFIED", (
                "SBR solver warnings present but retained as warning-qualified bridge candidate; "
                f"warning_count={warning_count}, volume_ray_count={volume_interface_inconsistency_ray_count}, "
                f"volume_ray_cap={warning_qualified_volume_ray_cap}"
            )
        return "DIAGNOSTIC_ONLY", f"SBR solver warnings present; warning_count={warning_count}"
    if str(sbr_geometry_quality_status).upper() != "PASS":
        return "BLOCKED_BY_SBR_GEOMETRY_WARNING", "SBR geometry quality gate is missing or not PASS"
    return "PROMOTED_TO_MAIN_BRIDGE", ""
