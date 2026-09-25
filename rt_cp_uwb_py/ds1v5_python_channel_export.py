from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np

from .ds1v5_bridge_schema import BridgeValidationError, ComplexChannelRecord


C_M_PER_S = 299_792_458.0


@dataclass(frozen=True)
class PathComponent:
    component_id: str
    coefficient: complex
    delay_s: float
    hit_count_a: int = 0
    hit_count_b: int = 0


def physical_delay_replay(freq_hz: np.ndarray, components: Iterable[PathComponent]) -> np.ndarray:
    freq = np.asarray(freq_hz, dtype=float)
    if freq.ndim != 1 or freq.size < 2 or not np.all(np.diff(freq) > 0):
        raise BridgeValidationError("freq_hz must be a monotone one-dimensional grid")
    H = np.zeros_like(freq, dtype=np.complex128)
    for comp in components:
        coeff = complex(comp.coefficient)
        H += coeff * np.exp(-1j * 2.0 * np.pi * freq * float(comp.delay_s))
    return H


def path_length_to_delay_s(length_m: float, phase_center_offset_m: float = 0.0) -> float:
    return float(length_m + phase_center_offset_m) / C_M_PER_S


def record_from_physical_paths(
    *,
    case_id: str,
    channel_id: str,
    freq_hz: np.ndarray,
    components: Iterable[PathComponent],
    source_kind: str,
    source_id: str,
    solve_id: str = "",
    execution_host: str = "",
    remote_workdir: str = "",
) -> ComplexChannelRecord:
    H = physical_delay_replay(freq_hz, components)
    return ComplexChannelRecord(
        case_id=case_id,
        channel_id=channel_id,
        freq_hz=np.asarray(freq_hz, dtype=float),
        H_f=H,
        source_kind=source_kind,
        source_id=source_id,
        solve_id=solve_id,
        phase_mode="physical_delay",
        metadata={"execution_host": execution_host, "remote_workdir": remote_workdir},
    )


def component_from_mapping(row: Mapping[str, object]) -> PathComponent:
    if "coefficient" in row:
        coeff = complex(row["coefficient"])  # type: ignore[arg-type]
    else:
        coeff = float(row.get("coeff_re", 0.0)) + 1j * float(row.get("coeff_im", 0.0))
    if "delay_s" in row:
        delay_s = float(row["delay_s"])  # type: ignore[arg-type]
    elif "path_length_m" in row:
        delay_s = path_length_to_delay_s(float(row["path_length_m"]), float(row.get("phase_center_offset_m", 0.0)))
    else:
        raise BridgeValidationError("Path component requires delay_s or path_length_m")
    return PathComponent(
        component_id=str(row.get("component_id", "")),
        coefficient=coeff,
        delay_s=delay_s,
        hit_count_a=int(row.get("hit_count_a", 0)),
        hit_count_b=int(row.get("hit_count_b", 0)),
    )


def synthetic_two_path_record(
    *,
    case_id: str = "synthetic",
    channel_id: str = "LP-LP",
    freq_hz: np.ndarray | None = None,
    direct_coeff: complex = 1.0 + 0.0j,
    reflected_coeff: complex = 0.25 + 0.15j,
    direct_delay_s: float = 10e-9,
    reflected_delay_s: float = 12e-9,
    source_kind: str = "LOCAL_MOCK",
) -> ComplexChannelRecord:
    freq = np.asarray(freq_hz if freq_hz is not None else np.linspace(6.0e9, 7.0e9, 33), dtype=float)
    components = [
        PathComponent("direct", direct_coeff, direct_delay_s),
        PathComponent("plate_scattered_component_A", reflected_coeff, reflected_delay_s, hit_count_a=1),
    ]
    return record_from_physical_paths(
        case_id=case_id,
        channel_id=channel_id,
        freq_hz=freq,
        components=components,
        source_kind=source_kind,
        source_id="synthetic_two_path",
    )


def require_somi_manifest(manifest: Mapping[str, object]) -> None:
    host = str(manifest.get("execution_host", "")).upper()
    if host != "SOMI":
        raise BridgeValidationError("Real Python RT outputs require execution_host=SOMI for main evidence")
    for key in ["remote_workdir", "command_line", "output_files", "output_hashes"]:
        if not manifest.get(key):
            raise BridgeValidationError(f"Somi real-run manifest missing {key}")
