from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from . import analysis, antennas, sanity
from .channel import build_channel, convert_basis, ifft_to_cir, path_jones_debug, path_jones_response
from .config import default_config
from .core import Antenna, Material, PathRecord, Scene, Surface, fresnel_reflection, jones_reflection, make_ideal_cp_antenna, make_ideal_lp_antenna, transverse_basis
from .features import (
    CANONICAL_FEATURE_NAMES,
    CP16_FEATURE_NAMES,
    compute_a_fp_variants,
    compute_cir_baseline,
    compute_gamma_cp_variants,
    compute_rh_lh_cp16,
    extract_all_features,
    extract_first_path,
    select_circular_channels,
)
from .parity import run_parity_suite
from .materials import materials_library
from .scenes import compute_single_bounce_geometry, generate_room_tx_rx_grid, generate_symmetric_boresight_geometry, make_room_abc_scene, make_single_slab_scene
from .sweep import compose_case_seed, design_lhs_sweep, design_stage1_recovery_mini_cases, design_stage2_cases, design_stage2_recovery_mini_cases, inject_snr, run_one_case, run_sweep_batch, struct_array_to_table
from .trace import enumerate_paths


OPERATION_REGISTRY = {
    "analysis.computeConditionalAuc": analysis.compute_conditional_auc,
    "analysis.computeConditionalAucGrid": analysis.compute_conditional_auc,
    "analysis.computeDisagreementAnalysis": analysis.compute_disagreement_analysis,
    "analysis.cvLogisticAuc": analysis.cv_logistic_auc,
    "antennas.computeFfdMetrics": antennas.compute_ffd_metrics,
    "antennas.couplingFromAngle": antennas.coupling_from_angle,
    "antennas.interpolatePattern": antennas.interpolate_pattern,
    "antennas.loadFfdPattern": antennas.load_ffd_pattern,
    "antennas.loadPatchPattern": antennas.load_patch_pattern,
    "antennas.loadPatchPatternSynthetic": antennas.load_patch_pattern_synthetic,
    "antennas.makeIdealCpAntenna": make_ideal_cp_antenna,
    "antennas.makeIdealLpAntenna": make_ideal_lp_antenna,
    "antennas.makeRealisticPatchAntenna": antennas.make_realistic_patch_antenna,
    "antennas.makeRealisticLpAntennaFFD": antennas.make_realistic_lp_antenna_ffd,
    "antennas.makeRealisticPatchAntennaFFD": antennas.make_realistic_patch_antenna_ffd,
    "antennas.saveFfdPatternMat": antennas.save_ffd_pattern_mat,
    "channel.buildChannel": build_channel,
    "channel.convertBasis": convert_basis,
    "channel.ifftToCir": ifft_to_cir,
    "channel.pathJonesDebug": path_jones_debug,
    "config.defaultConfig": default_config,
    "core.Antenna": Antenna,
    "core.Material": Material,
    "core.PathRecord": PathRecord,
    "core.Scene": Scene,
    "core.Surface": Surface,
    "core.fresnelReflection": fresnel_reflection,
    "core.jonesReflection": jones_reflection,
    "core.localSpBases": transverse_basis,
    "core.transverseBasis": transverse_basis,
    "features.canonicalFeatureNames": lambda: CANONICAL_FEATURE_NAMES,
    "features.canonicalizeFeatureStruct": lambda **kwargs: kwargs,
    "features.computeAFpVariants": compute_a_fp_variants,
    "features.computeCirBaseline": compute_cir_baseline,
    "features.computeGammaCpVariants": compute_gamma_cp_variants,
    "features.computeRhLhCp16": compute_rh_lh_cp16,
    "features.extractAllFeatures": extract_all_features,
    "features.extractFirstPath": extract_first_path,
    "features.rhLhCp16FeatureNames": lambda: CP16_FEATURE_NAMES,
    "features.selectCircularChannels": select_circular_channels,
    "materials.materialsLibrary": materials_library,
    "sanity.checkA1_losPathLoss": sanity.check_los_path_loss,
    "sanity.checkA2_singleBouncePath": sanity.check_single_bounce_path,
    "sanity.checkA3_snellLaw": sanity.check_snell_law,
    "sanity.checkA4_pathEnumeration": sanity.check_path_enumeration,
    "sanity.checkB1_cpHandednessReversal": sanity.check_cp_handedness_reversal,
    "sanity.checkB2_evenBounceHandedness": sanity.check_cp_handedness_reversal,
    "sanity.checkB3_brewsterAngle": sanity.check_brewster_angle,
    "sanity.checkB4_normalIncidence": sanity.check_normal_incidence,
    "sanity.checkC1_losCirPeak": sanity.check_los_cir_peak,
    "sanity.checkC2_uwbPulseShape": sanity.check_uwb_pulse_shape,
    "sanity.checkD1_antennaCompare": sanity.check_coupling_unitarity,
    "sanity.checkD2_couplingUnitarity": sanity.check_coupling_unitarity,
    "sanity.checkD3_ffdBoresight": sanity.check_direct_cp_los_convention,
    "sanity.checkD4_directCpLosConvention": sanity.check_direct_cp_los_convention,
    "sanity.checkD5_singleBounceConcreteFresnel": sanity.check_single_bounce_concrete_fresnel,
    "sanity.runImplementedChecks": sanity.run_implemented_checks,
    "sanity.runAllChecks": sanity.run_implemented_checks,
    "sanity.runWeek1PipelineCheck": sanity.run_implemented_checks,
    "sanity.makeResult": lambda **kwargs: kwargs,
    "sanity.makeSurface": lambda **kwargs: Surface(**kwargs),
    "scenes.makeRoomABCScene": make_room_abc_scene,
    "scenes.makeSingleSlabScene": make_single_slab_scene,
    "scenes.computeSingleBounceGeometry": compute_single_bounce_geometry,
    "scenes.generateRoomTxRxGrid": generate_room_tx_rx_grid,
    "scenes.generateSymmetricBoresightGeometry": generate_symmetric_boresight_geometry,
    "sweep.composeCaseSeed": compose_case_seed,
    "sweep.designLhsSweep": design_lhs_sweep,
    "sweep.designStage1RecoveryMiniCases": design_stage1_recovery_mini_cases,
    "sweep.designStage2Cases": design_stage2_cases,
    "sweep.designStage2RecoveryMiniCases": design_stage2_recovery_mini_cases,
    "sweep.injectSnr": inject_snr,
    "sweep.runOneCase": run_one_case,
    "sweep.runSweepBatch": run_sweep_batch,
    "sweep.structArrayToTable": struct_array_to_table,
    "trace.enumeratePaths": enumerate_paths,
    "parity.runParitySuite": run_parity_suite,
}


def list_operations() -> list[str]:
    return sorted(OPERATION_REGISTRY)


def get_operation(name: str):
    if name in OPERATION_REGISTRY:
        return OPERATION_REGISTRY[name]
    short = [k for k in OPERATION_REGISTRY if k.lower().endswith("." + name.lower()) or k.lower() == name.lower()]
    if len(short) == 1:
        return OPERATION_REGISTRY[short[0]]
    if short:
        raise KeyError(f"ambiguous operation {name!r}: {short}")
    raise KeyError(f"unknown operation {name!r}")


def run_named_operation(name: str, kwargs: dict[str, Any] | None = None):
    op = get_operation(name)
    return op(**(kwargs or {}))


def write_result(result: Any, out: str | Path) -> None:
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(result, pd.DataFrame):
        result.to_csv(path, index=False)
    elif isinstance(result, (list, tuple)) and result and isinstance(result[0], dict):
        pd.DataFrame(result).to_csv(path, index=False)
    elif isinstance(result, dict):
        pd.DataFrame([result]).to_csv(path, index=False)
    else:
        path.write_text(str(result), encoding="utf-8")
