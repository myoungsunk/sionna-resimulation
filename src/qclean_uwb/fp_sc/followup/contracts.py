"""Fail-closed I/O, experiment authorization and schema primitives.

Authorization is deliberately NOT inherited from E0/E1-01. Numerical results,
scientific gates, and external independent acceptance are distinct fields.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
import hashlib
import json
import math
import platform
import sys
from typing import Any
import numpy as np

BASE_SHA = "2be558a6fa62bb5472e4e275e684df907ac16e84"
STEP_M = 299792458.0 / (1028 * 1950000.0)
STAGES = ("E1-02", "E1-03", "E2-01", "E2-02", "E2-03", "E2-04",
          "E3-01", "E3-02", "E3-03", "E3-04", "E4-01", "E4-02",
          "E4-03", "E5-01", "E5-02", "E5-03")
DEPENDENCIES = {
    "E1-02": ["E1-01"], "E1-03": ["E1-02"], "E2-01": ["E1-03"],
    "E2-02": ["E2-01"], "E2-03": ["E2-02"], "E2-04": ["E2-03"],
    "E3-01": ["E2-04"], "E3-02": ["E3-01"], "E3-03": ["E3-02"],
    "E3-04": ["E3-03"], "E4-01": ["E3-04"], "E4-02": ["E4-01"],
    "E4-03": ["E4-01"], "E5-01": ["E4-02"], "E5-02": ["E5-01"],
    "E5-03": ["E5-02"],
}
OPTIONAL = {"E4-03", "E5-03"}


class ContractError(ValueError):
    """Invalid or unapproved input. Never convert this to a scientific PASS."""


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def sha256(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return jsonable(asdict(value))
    if isinstance(value, np.ndarray):
        return jsonable(value.tolist())
    if isinstance(value, np.generic):
        return jsonable(value.item())
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError("NONFINITE_JSON: use explicit null and a reason")
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(jsonable(value), ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def finite(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    a = np.asarray(value, dtype=float)
    if a.shape != shape or not np.isfinite(a).all():
        raise ContractError(f"INVALID_{name}: expected finite {shape}, got {a.shape}")
    return a


def covariance(value: Any, n: int, *, positive: bool = False) -> np.ndarray:
    a = finite(value, (n, n), "COVARIANCE")
    scale = max(1., float(np.linalg.norm(a, 2)))
    if np.max(np.abs(a - a.T)) > 1e-12 * scale:
        raise ContractError("ASYMMETRIC_COVARIANCE")
    a = (a + a.T) * .5
    ev = np.linalg.eigvalsh(a)
    if ev[0] < -1e-12 * scale or (positive and ev[0] <= 0):
        raise ContractError("NON_PSD_OR_NON_PD_COVARIANCE")
    return a


@dataclass(frozen=True)
class Support:
    """Detector-domain interval, not a Gaussian confidence interval.

    Width/slack must come from a separately reviewed native mapping recipe.
    No automatic half-tap support, geometry-only mapping, or 4cm sigma.
    """
    low: float
    high: float
    scale: float
    provenance: str

    def __post_init__(self) -> None:
        if not np.isfinite([self.low, self.high, self.scale]).all():
            raise ContractError("NONFINITE_SUPPORT")
        if self.low > self.high or self.scale <= 0 or not self.provenance:
            raise ContractError("INVALID_SUPPORT")

    def residual(self, r: float) -> float:
        if not math.isfinite(r):
            raise ContractError("NONFINITE_DISTANCE")
        return max(self.low - r, r - self.high, 0.) / self.scale


@dataclass(frozen=True)
class Policy:
    """Concrete development proposal. Values are not scientifically accepted."""
    wrong_cut: float = 2.
    replace_gain: float = .8
    margin: float = .5
    prior_weight: float = 1.
    rf_weight: float = .7
    min_support: float = .15
    max_prior_width_m: float = 1.5
    history_max_age_s: float = 2.
    vmax_mps: float = .2
    motion_slack_m: float = .02
    mapping_slack_m: float = .15
    native_sigma_scale: float = 2.
    bootstrap_packets: int = 2
    risk_R_multiplier: float = 4.

    def __post_init__(self) -> None:
        vals = asdict(self)
        if not all(math.isfinite(v) and v >= 0 for v in vals.values()):
            raise ContractError("INVALID_POLICY_NUMBER")
        if not 0 < self.min_support <= 1 or self.history_max_age_s <= 0:
            raise ContractError("INVALID_SUPPORT_OR_HISTORY")
        if self.mapping_slack_m <= 0 or self.native_sigma_scale <= 0:
            raise ContractError("MAPPING_UNCERTAINTY_REQUIRED")
        if self.max_prior_width_m <= 0 or self.vmax_mps <= 0:
            raise ContractError("INVALID_PRIOR_OR_MOTION_BOUND")
        if self.bootstrap_packets < 1 or type(self.bootstrap_packets) is not int:
            raise ContractError("INVALID_BOOTSTRAP_COUNT")
        if self.risk_R_multiplier < 1:
            raise ContractError("RISK_ARM_MAY_NOT_SHRINK_R")

    @property
    def sha(self) -> str:
        return digest(asdict(self))


def rooted(root: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise ContractError("ABSOLUTE_PATH_NOT_ALLOWED")
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ContractError("PATH_TRAVERSAL")
    return path


def verify_files(root: Path, files: dict[str, str]) -> None:
    if not files:
        raise ContractError("EMPTY_FILE_LOCK")
    for rel, expected in files.items():
        path = rooted(root, rel)
        if not path.is_file():
            raise ContractError(f"MISSING_PAYLOAD:{rel}")
        with path.open("rb") as f:
            if f.read(64).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ContractError(f"LFS_POINTER_NOT_PAYLOAD:{rel}")
        if len(expected) != 64 or sha256(path) != expected:
            raise ContractError(f"SHA_MISMATCH:{rel}")


def authorize(root: Path, manifest_path: Path, approval_path: Path,
              stages: list[str], code_files: list[str]) -> tuple[dict, dict]:
    """Check governance BEFORE loading any waveform, label, or FFD bank."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval.get("execute_science") is not True:
        raise ContractError("SCIENCE_EXECUTION_NOT_AUTHORIZED")
    if manifest.get("schema") != "FP_SC_FOLLOWUP_STUDY_V1":
        raise ContractError("WRONG_STUDY_SCHEMA")
    if approval.get("manifest_sha256") != sha256(manifest_path):
        raise ContractError("MANIFEST_NOT_APPROVED")
    if not stages or len(set(stages)) != len(stages):
        raise ContractError("EMPTY_OR_DUPLICATE_STAGES")
    if not set(stages) <= set(STAGES) & set(approval.get("stages", [])):
        raise ContractError("STAGE_NOT_APPROVED")
    if set(stages) & OPTIONAL - set(approval.get("optional_stages", [])):
        raise ContractError("OPTIONAL_SCOPE_REQUIRES_SEPARATE_GO")
    if not approval.get("actor") or not approval.get("issued_utc"):
        raise ContractError("MISSING_APPROVAL_PROVENANCE")
    locked_code = manifest.get("code_files", {})
    if set(locked_code) != set(code_files):
        raise ContractError("CODE_LOCK_INCOMPLETE")
    if digest(locked_code) != approval.get("code_lock_sha256"):
        raise ContractError("CODE_LOCK_NOT_APPROVED")
    verify_files(root, locked_code)
    verify_files(root, manifest.get("input_files", {}))
    actual_env = {"python": platform.python_version(), "numpy": np.__version__}
    if manifest.get("environment") != actual_env:
        raise ContractError(f"ENVIRONMENT_MISMATCH:{actual_env}")
    if manifest.get("policy_sha256") != Policy(**manifest["policy"]).sha:
        raise ContractError("POLICY_SHA_MISMATCH")
    if manifest.get("mapping_reviewed") is not True:
        raise ContractError("HOLD_MAPPING_UNRESOLVED")
    if manifest.get('execution_profile') == 'VAB_DETECTION_ONLY_R1':
        if stages != ['E1-02'] or approval.get('stages') != ['E1-02']:
            raise ContractError('VAB_DETECTION_SINGLE_STAGE_ONLY')
        from .detection import HISTORY_RECIPE
        from .bridge import RECIPE_SHA
        from .selection import SELECTOR_SET_RECIPE
        from .integrity import INTEGRITY_RECIPE
        path = manifest.get('mapping_receipt')
        if path not in manifest.get('input_files', {}):
            raise ContractError('MAPPING_EVIDENCE_NOT_LOCKED')
        mapping = json.loads(rooted(root, path).read_text(encoding='utf-8'))
        expected = dict(status='PASS_DYNAMIC_MAPPING_REVIEW', policy_sha256=manifest['policy_sha256'],
                        candidate_mode=manifest.get('candidate_mode'), arm='VAB',
                        bridge_recipe_sha256=RECIPE_SHA, selector_recipe=SELECTOR_SET_RECIPE,
                        history_recipe=HISTORY_RECIPE, code_lock_sha256=digest(locked_code),
                        integrity_recipe=INTEGRITY_RECIPE,
                        baseline_source_lock_sha256=digest(manifest.get('baseline_sources', {})),
                        case_payload_lock_sha256=digest({spec[key]: manifest['input_files'].get(spec[key])
                            for spec in [*manifest['cases'].values(), *manifest.get('static_cases', {}).values()]
                            for key in ('online_npz','evaluator_npz')}))
        if any(mapping.get(k) != v for k, v in expected.items()):
            raise ContractError('MAPPING_RECIPE_OR_REVIEW_MISMATCH')
        if not mapping.get('evidence_files') or not mapping.get('reviewer'):
            raise ContractError('MAPPING_EVIDENCE_OR_REVIEWER_MISSING')
        for rel, sha in mapping['evidence_files'].items():
            if manifest['input_files'].get(rel) != sha:
                raise ContractError('MAPPING_EVIDENCE_NOT_LOCKED')
        # No reviewed provider can attest VALID prior integrity in this version.
        # A forged readiness boolean or receipt must not activate P/M execution.
        raise ContractError('HOLD_PRIOR_INTEGRITY_PROVIDER_MISSING')
    if any(s in stages for s in ("E4-02", "E4-03")):
        if manifest.get("seed_exposure_reviewed") is not True:
            raise ContractError("SEALED_SEED_EXPOSURE_UNRESOLVED")
    return manifest, approval


def prerequisite(stage: str, receipts: dict[str, dict], approval: dict) -> bool:
    """Return exploratory-continuation flag; no retrospective PASS conversion."""
    exploratory = False
    for parent in DEPENDENCIES[stage]:
        r = receipts.get(parent, {})
        if r.get("execution_status") != "COMPLETE" or not r.get("numerical_qa_pass"):
            raise ContractError(f"PREREQUISITE_TECHNICAL_INCOMPLETE:{parent}")
        if r.get("scientific_gate") != "PASS":
            if parent not in approval.get("exploratory_after_nonpass", []):
                raise ContractError(f"PREREQUISITE_SCIENTIFIC_HOLD:{parent}")
            exploratory = True
    return exploratory


def environment() -> dict:
    return {"python": platform.python_version(), "numpy": np.__version__,
            "platform": platform.platform(), "executable": sys.executable}
