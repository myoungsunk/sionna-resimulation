"""Python replacement surface for the rt_cp_uwb MATLAB package.

The package intentionally mirrors the MATLAB package boundaries:
core/trace/channel/features/sweep/sanity plus CLI entrypoints.
"""

from .config import RtConfig, default_config
from .h10b_e6_splits import (
    channel_dropout_augment,
    channel_dropout_split,
    e6_splits_manifest,
    heading_bin_labels,
    leave_heading_bin_out_splits,
    leave_material_out_splits,
    material_scene_variants,
)
from .h10b_ffd_predictor import H10BFFDPredictor
from .h10b_proximity_doa import (
    HEADING_POLICIES,
    PROXIMITY_DOA_SCHEMA_VERSION,
    CombinedDOAResult,
    HeadingProxyResult,
    ProximityDOAConfig,
    RSSDDOAResult,
    branch_select_by_heading_prior,
    build_tilt_contrast_rhcp_lut,
    clear_lut_cache,
    combined_doa_log_score_batch,
    combined_doa_residuals_optimizer,
    extract_tilt_contrast_rhcp_db,
    heading_proxy_candidate_pos,
    heading_proxy_estimate,
    heading_proxy_log_score_batch,
    heading_proxy_residual,
    proximity_doa_manifest,
    rssd_doa_estimate,
    rssd_doa_log_score_batch,
    sigma_heading_doa,
    tilt_contrast_fisher_at_beta,
    tilt_contrast_fisher_curve,
)
from .h10b_range_factor import (
    H10BPhaseCenterConfig,
    extract_h10b_amplitude_observations,
    extract_h10b_range_observations,
    h10b_ffd_amplitude_log_score_batch,
    h10b_ffd_amplitude_residuals_optimizer,
    h10b_range_factor_manifest,
)
from .lut_selection import LutScopeSelection, LutSelectionConfig, select_lut_scope
from .operations import get_operation, list_operations, run_named_operation
from .reliability_gate import ReliabilityGateConfig, ReliabilityWeightResult, classify_fix_status, compute_reliability_weight
from .sweep import run_one_case, run_sweep_batch

__all__ = [
    # Core / config
    "H10BFFDPredictor",
    "H10BPhaseCenterConfig",
    "RtConfig",
    "default_config",
    # Proximity DOA v2 — Path A (heading-proxy)
    "HEADING_POLICIES",
    "PROXIMITY_DOA_SCHEMA_VERSION",
    "HeadingProxyResult",
    "ProximityDOAConfig",
    "branch_select_by_heading_prior",
    "heading_proxy_candidate_pos",
    "heading_proxy_estimate",
    "heading_proxy_log_score_batch",
    "heading_proxy_residual",
    "sigma_heading_doa",
    # Proximity DOA v2 — Path B (RSSD / tilt_contrast_rhcp)
    "RSSDDOAResult",
    "build_tilt_contrast_rhcp_lut",
    "clear_lut_cache",
    "rssd_doa_estimate",
    "rssd_doa_log_score_batch",
    "tilt_contrast_fisher_at_beta",
    "tilt_contrast_fisher_curve",
    # Proximity DOA v2 — Combined
    "CombinedDOAResult",
    "combined_doa_log_score_batch",
    "combined_doa_residuals_optimizer",
    # Shared utilities
    "extract_tilt_contrast_rhcp_db",
    "proximity_doa_manifest",
    # Range factor
    "extract_h10b_amplitude_observations",
    "extract_h10b_range_observations",
    "h10b_ffd_amplitude_log_score_batch",
    "h10b_ffd_amplitude_residuals_optimizer",
    "h10b_range_factor_manifest",
    # E6 splits
    "channel_dropout_augment",
    "channel_dropout_split",
    "e6_splits_manifest",
    "heading_bin_labels",
    "leave_heading_bin_out_splits",
    "leave_material_out_splits",
    "material_scene_variants",
    # LUT / reliability / ops
    "LutScopeSelection",
    "LutSelectionConfig",
    "ReliabilityGateConfig",
    "ReliabilityWeightResult",
    "classify_fix_status",
    "compute_reliability_weight",
    "get_operation",
    "list_operations",
    "run_named_operation",
    "run_one_case",
    "run_sweep_batch",
    "select_lut_scope",
]
