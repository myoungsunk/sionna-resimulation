from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class RtConfig:
    project_root: Path
    c0: float = 299_792_458.0
    f_center: float = 6.5e9
    bw: float = 500e6
    n_freq: int = 257
    window_type: str = "hann"
    circular_order: str = "RL"
    convention: str = "IEEE-RHCP"
    seed_base: int = 0
    seed_stage_id: str = ""
    seed_replicate_id: int = 0
    rt_max_bounce: int = 2
    tx_handedness: str = "R"
    tx_port_order: tuple[str, str] = ("R", "L")
    rx_port_order: tuple[str, str] = ("R", "L")
    # After the P-7 port-basis correction, "auto" always resolves to the
    # direct-compatible same-TX branch. Frozen historical replays must request
    # the old opposite-TX convention explicitly.
    cp_branch_convention: str = "auto"
    replay_fp_hints: bool = False
    fresnel_incidence_mode: str = "actual"
    fresnel_fixed_theta_deg: float = 45.0
    polarization_mode: str = "CP"
    # The measured antenna's two linear feeds are DIAGONAL, not x/y. Measured
    # basis angle psi = 42.58 deg relative to the plate's TE/TM axes
    # (Y1f complex-coherence estimator, |rho| = 0.988; C1b after branch
    # calibration). Corroborated by the pattern lineage: RHCP_new/LHCP_new are
    # algebraically -j(E_+45 +- j E_-45), residual 4e-11 (Y2a).
    # These defaults describe the PHYSICAL feeds. LP_x/LP_y remain available and
    # are a genuinely different pattern set (10-16 % apart), not a rotation.
    measured_pol_basis_deg: float = 42.58
    measured_pol_basis_source: str = "Y1f/C1b measured; nominal design 45 deg"
    anchor_linear_pol_axis_deg: float = 45.0
    tag_ant1_linear_pol_axis_deg: float = 45.0
    tag_ant2_linear_pol_axis_deg: float = -45.0
    tag_pol_tilt_deg: float = 0.0
    anchor_pol_tilt_deg: float = 0.0
    lp_copol_gain_pattern_file: str = "LP_+45_new_6G7G_11pts.ffd"
    lp_crosspol_gain_pattern_file: str = "LP_-45_new_6G7G_11pts.ffd"
    use_te_tm_reflection: bool = True
    material_fresnel_model: str = "te_tm_fresnel"
    path_polarization_tracking: bool = True
    results_dir: Path = field(init=False)
    sanity_dir: Path = field(init=False)
    sweep_dir: Path = field(init=False)

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root)
        self.results_dir = self.project_root / "results"
        self.sanity_dir = self.results_dir / "sanity"
        self.sweep_dir = self.results_dir / "sweep"

    @property
    def freqs(self) -> np.ndarray:
        return np.linspace(
            self.f_center - self.bw / 2.0,
            self.f_center + self.bw / 2.0,
            self.n_freq,
            dtype=float,
        )


def default_config(project_root: str | Path | None = None) -> RtConfig:
    if project_root is None:
        project_root = Path(__file__).resolve().parents[1]
    return RtConfig(project_root=Path(project_root))
