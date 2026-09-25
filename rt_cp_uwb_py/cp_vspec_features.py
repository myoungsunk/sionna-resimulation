"""Frozen balanced arm features for the C_V1 V-SPEC experiment."""

from __future__ import annotations

import numpy as np

from rt_cp_uwb_py.channel import ifft_to_cir
from rt_cp_uwb_py.cp_polarization_transforms import linear_to_circular
from rt_cp_uwb_py.features import extract_first_path


ARM_IDS = ("B_DLP_HV", "C_DLP_SYNTH_CP", "D_NATIVE_DUAL_CP", "E_NATIVE_CP_CO_ONLY", "F_CP_SHUFFLED_CROSS")


def _first_path_features(response: np.ndarray, freqs_hz: np.ndarray) -> tuple[float, float]:
    h_t, t_axis = ifft_to_cir(np.asarray(response, dtype=np.complex128), freqs_hz, window_type="hann")
    _, t_fp, _ = extract_first_path(h_t, t_axis, method="leading_edge")
    return float(t_fp), float(np.sum(np.abs(h_t) ** 2))


def build_vspec_arm_features(cp: np.ndarray, lp: np.ndarray, freqs_hz: np.ndarray, *, seed: int) -> dict[str, np.ndarray]:
    """Materialize all C comparison arms from the same complex case bank."""

    if cp.shape != lp.shape or cp.ndim != 4 or cp.shape[1:3] != (2, 2):
        raise ValueError(f"expected matched [case,2,2,freq] tensors, got cp={cp.shape}, lp={lp.shape}")
    shuffled = np.random.default_rng(seed).permutation(cp.shape[0])
    rows = {arm: [] for arm in ARM_IDS}
    for index in range(cp.shape[0]):
        lp_h00 = _first_path_features(lp[index, 0, 0, :], freqs_hz)
        lp_h10 = _first_path_features(lp[index, 1, 0, :], freqs_hz)
        cp_h00 = _first_path_features(cp[index, 0, 0, :], freqs_hz)
        cp_h10 = _first_path_features(cp[index, 1, 0, :], freqs_hz)
        cp_shuffle = _first_path_features(cp[shuffled[index], 1, 0, :], freqs_hz)
        synth = linear_to_circular(lp[index])
        synth_h00 = _first_path_features(synth[0, 0, :], freqs_hz)
        synth_h10 = _first_path_features(synth[1, 0, :], freqs_hz)
        rows["B_DLP_HV"].append([*lp_h00, *lp_h10])
        rows["C_DLP_SYNTH_CP"].append([*synth_h00, *synth_h10])
        rows["D_NATIVE_DUAL_CP"].append([*cp_h00, *cp_h10])
        rows["E_NATIVE_CP_CO_ONLY"].append([*cp_h00])
        rows["F_CP_SHUFFLED_CROSS"].append([*cp_h00, *cp_shuffle])
    return {arm: np.asarray(values, dtype=float) for arm, values in rows.items()}
