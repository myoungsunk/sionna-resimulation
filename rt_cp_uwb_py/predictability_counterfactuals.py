"""Safe construction checks for Part 4 v3 same-realization counterfactuals."""
from __future__ import annotations

import numpy as np


def redistribute_energy(total_energy: float, fractions: np.ndarray) -> np.ndarray:
    fractions = np.asarray(fractions, dtype=float)
    if total_energy < 0 or fractions.ndim != 1 or len(fractions) == 0 or np.any(fractions < 0):
        raise ValueError("invalid counterfactual energy request")
    norm = float(fractions.sum())
    if norm <= 0:
        raise ValueError("counterfactual fractions must have positive sum")
    result = float(total_energy) * fractions / norm
    if not np.isclose(result.sum(), total_energy, rtol=0.0, atol=1e-10):
        raise AssertionError("total interferer energy was not preserved")
    return result


def phase_randomize(amplitude: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    values = np.asarray(amplitude, dtype=np.complex128)
    return np.abs(values) * np.exp(1j * rng.uniform(-np.pi, np.pi, size=values.shape))


def intervention_manifest_row(case_id: int, intervention_id: str, *, evidence_only: bool, channel_level: bool, status: str, limitation: str = "") -> dict[str, object]:
    if evidence_only == channel_level:
        raise ValueError("an intervention must be exactly evidence-only or channel-level")
    return {"case_id": int(case_id), "intervention_id": intervention_id, "evidence_only": evidence_only, "channel_level": channel_level, "status": status, "limitation": limitation}
