from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    paper_axis: str
    description: str
    script: str
    required_inputs: tuple[str, ...]
    expected_outputs: tuple[str, ...]
    claim_boundary: str

    def status(self, root: Path) -> dict[str, object]:
        payload = asdict(self)
        payload["script_status"] = "PRESENT" if (root / self.script).exists() else "MISSING"
        payload["required_input_status"] = {
            rel: "PRESENT" if (root / rel).exists() else "MISSING" for rel in self.required_inputs
        }
        return payload


PRIMARY_PACKAGE = "results/DATA_PACKAGE_5SPACE_CONDITION_FACTORIAL_FULLRUN_20260603"
SUPPORT_PACKAGE = "results/DATA_PACKAGE_5SPACE_CONDITION_GEOMETRY_20260602"
ROLE_PACKAGE = "results/PAPER2_ROLE_MATCHED_QCLEAN_VALIDATION_PACKAGE_20260604"

P1_EXPERIMENTS = {
    "P1_SIM_PATH2H_CLASSIFICATION": ExperimentSpec(
        "P1_SIM_PATH2H_CLASSIFICATION",
        "paper1_sim",
        "PATH-2H CP feature classification against CIR baselines.",
        "scripts/run_p1_canonical_fast_gate_20260601.py",
        (
            f"{SUPPORT_PACKAGE}/00_canonical_rt_master/feature_table.csv",
            f"{SUPPORT_PACKAGE}/00_canonical_rt_master/label_table.csv",
            f"{SUPPORT_PACKAGE}/01_p1_fast_gate_oof/fold_audit.csv",
        ),
        (f"{SUPPORT_PACKAGE}/01_p1_fast_gate_oof/P1_SIM_PATH2H_CLASSIFICATION.md",),
        "CP identifies RD-LoS reflection-dominant session-quality states; no direct range-error reduction claim.",
    ),
    "P1_SIM_PATH3H_REFINEMENT": ExperimentSpec(
        "P1_SIM_PATH3H_REFINEMENT",
        "paper1_sim",
        "PATH-3H HB-near-delay / HB-prior mechanism refinement.",
        "scripts/run_p1_canonical_fast_gate_20260601.py",
        (
            f"{SUPPORT_PACKAGE}/00_canonical_rt_master/feature_table.csv",
            f"{SUPPORT_PACKAGE}/00_canonical_rt_master/label_table.csv",
            f"{SUPPORT_PACKAGE}/01_p1_fast_gate_oof/fold_audit.csv",
        ),
        (f"{SUPPORT_PACKAGE}/01_p1_fast_gate_oof/P1_SIM_PATH3H_REFINEMENT.md",),
        "3H is a mechanism refinement, not the main breakthrough.",
    ),
    "P1_SIM_CONTROLS": ExperimentSpec(
        "P1_SIM_CONTROLS",
        "paper1_sim",
        "Paper 1 control comparisons including shuffled/residualized CP where available.",
        "scripts/run_p1_canonical_full_gate_20260601.py",
        (f"{SUPPORT_PACKAGE}/00_canonical_rt_master/feature_table.csv",),
        (f"{SUPPORT_PACKAGE}/03_p1_controls/P1_SIM_CONTROLS.md",),
        "Controls support feature-state identification only.",
    ),
    "P1_SIM_ROBUSTNESS": ExperimentSpec(
        "P1_SIM_ROBUSTNESS",
        "paper1_sim",
        "Paper 1 robustness split summaries.",
        "scripts/run_p1_canonical_full_gate_20260601.py",
        (f"{SUPPORT_PACKAGE}/00_canonical_rt_master/feature_table.csv",),
        (f"{SUPPORT_PACKAGE}/04_p1_robustness/P1_SIM_ROBUSTNESS.md",),
        "Robustness does not promote CP to range-error reduction.",
    ),
}

P2_EXPERIMENTS = {
    "P2_SIM_QCLEAN_DECILE": ExperimentSpec(
        "P2_SIM_QCLEAN_DECILE",
        "paper2_sim",
        "q-clean decile diagnostics from frozen OOF scores.",
        "scripts/run_p2_canonical_qclean_gate_20260601.py",
        (f"{SUPPORT_PACKAGE}/01_p1_fast_gate_oof/oof_scores_path2h.csv",),
        (f"{SUPPORT_PACKAGE}/05_p2_qclean_gate/P2_SIM_QCLEAN_DECILE.md",),
        "q_clean is clean-session/session-quality confidence, not range-error confidence.",
    ),
    "P2_SIM_GATING_POLICY": ExperimentSpec(
        "P2_SIM_GATING_POLICY",
        "paper2_sim",
        "q-clean gating policy tables.",
        "scripts/run_p2_canonical_qclean_gate_20260601.py",
        (f"{SUPPORT_PACKAGE}/01_p1_fast_gate_oof/classification_oof_scores_all.csv",),
        (f"{SUPPORT_PACKAGE}/05_p2_qclean_gate/P2_SIM_GATING_POLICY.md",),
        "Frozen OOF q-clean scores only; no train-score policy.",
    ),
    "P2_SIM_WEIGHTING_BACKEND": ExperimentSpec(
        "P2_SIM_WEIGHTING_BACKEND",
        "paper2_sim",
        "Paper 2 calibrated backend weighting replay.",
        "scripts/run_p2_canonical_calibrated_backend_20260601.py",
        (f"{PRIMARY_PACKAGE}/06_p2_calibrated_backend/q_clean_calibrated_scores.csv",),
        (f"{PRIMARY_PACKAGE}/06_p2_calibrated_backend/P2_SIM_CALIBRATED_WEIGHTING_BACKEND.md",),
        "Current backend evidence remains simulation/proxy-bound.",
    ),
    "P2_SIM_RELOCATION": ExperimentSpec(
        "P2_SIM_RELOCATION",
        "paper2_sim",
        "Local scan or session-selection simulation using neighbor relation.",
        "scripts/run_p2_canonical_local_scan_20260601.py",
        (f"{PRIMARY_PACKAGE}/07_p2_local_scan/local_scan_candidate_edges.csv",),
        (f"{SUPPORT_PACKAGE}/07_p2_local_scan/P2_SIM_RELOCATION.md",),
        "If neighbor relation is insufficient, call this session selection, not relocation.",
    ),
    "P2_OPERATIONAL_RELIABILITY_ROLE_MATCHED": ExperimentSpec(
        "P2_OPERATIONAL_RELIABILITY_ROLE_MATCHED",
        "paper2_sim",
        "Role-matched starvation-constrained operational replay.",
        "scripts/run_p2_starvation_constrained_replay_20260604.py",
        (f"{PRIMARY_PACKAGE}/package_manifest.json", f"{ROLE_PACKAGE}/CLAIM_SUMMARY.md"),
        (f"{ROLE_PACKAGE}/CLAIM_SUMMARY.md",),
        "Do not promote beyond STARVATION_CONSTRAINED_LEVEL2_PARTIAL.",
    ),
}


def select_experiments(registry: dict[str, ExperimentSpec], selected: str) -> list[ExperimentSpec]:
    if selected == "all":
        return list(registry.values())
    if selected not in registry:
        valid = ", ".join(["all", *registry])
        raise KeyError(f"unknown experiment {selected!r}; valid: {valid}")
    return [registry[selected]]
