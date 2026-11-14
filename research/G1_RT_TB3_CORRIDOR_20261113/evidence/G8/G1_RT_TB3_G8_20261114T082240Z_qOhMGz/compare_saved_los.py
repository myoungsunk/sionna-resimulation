"""Compare saved G8 and G1 LoS coefficients, delays and phase arithmetic; no RT calls."""

import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def sha256(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def phase(times, frequencies):
    return np.exp(-2j * np.pi * frequencies * times)


def metrics(value, reference):
    absolute = np.abs(value - reference)
    relative = np.divide(
        absolute, np.abs(reference), out=np.full_like(absolute, np.inf),
        where=reference != 0,
    )
    relative[(value == 0) & (reference == 0)] = 0
    norms = np.linalg.norm(reference.reshape(len(reference), -1), axis=1)
    delta_norms = np.linalg.norm((value - reference).reshape(len(reference), -1), axis=1)
    return {
        "max_absolute": float(absolute.max()),
        "max_relative": float(relative.max()),
        "entries_at_or_over_1e-6": int((relative >= 1e-6).sum()),
        "poses_at_or_over_1e-6": int((relative >= 1e-6).any(axis=(1, 2, 3)).sum()),
        "max_pose_relative_frobenius": float((delta_norms / norms).max()),
    }


def main(g8, g1):
    legacy_path = g1 / "PATHS_LoS.npz"
    legacy_record = json.loads((g1 / "G1.json").read_text())
    legacy_hash = sha256(legacy_path)
    assert legacy_hash == legacy_record["outputs"]["PATHS_LoS.npz"]["sha256"]
    g8_record = json.loads((g8 / "G8.json").read_text())
    poses = json.loads((g8 / "rf_poses.json").read_text())
    pose_ids = [p["pose_id"] for p in poses]
    legacy = np.load(legacy_path, allow_pickle=False)
    near = np.load(g8 / "paths/G-T1_A/PATHS_NEAR.npz", allow_pickle=False)
    saved_legacy = np.load(g8 / "H_LoS.npy", allow_pickle=False)
    saved_g8 = np.load(g8 / "H_LoS_from_full_trace.npy", allow_pickle=False)
    frequencies = near["frequencies_hz"]
    assert np.array_equal(frequencies, legacy["freqs_hz"])
    los_rows = np.flatnonzero(near["is_los"])
    row_by_pose = {int(near["pose_id"][row]): row for row in los_rows}
    assert len(row_by_pose) == len(los_rows) == len(pose_ids)
    indices = [row_by_pose[pose] for pose in pose_ids]
    coeff = near["coefficients"][indices]
    tau = near["tau_s"][indices, None]
    native_coeff = legacy["a"]
    native_tau = legacy["tau"]
    native_phase = phase(native_tau, frequencies)
    g8_phase = phase(tau, frequencies)
    reconstructed_g8 = coeff * g8_phase[..., None, None]
    reconstructed_g1 = np.empty_like(saved_legacy)
    # Reproduce the original multiplication order and dtypes in G1 run_los.
    for bin_index, freq in enumerate(frequencies):
        a = native_coeff[:, bin_index].astype(np.complex64)[..., None]
        delay = native_tau[:, bin_index, None].astype(np.float32)
        reconstructed_g1[:, bin_index] = (
            a * np.exp(-2j * np.pi * freq * delay)[:, None, None, :]
        ).sum(-1)
    assert np.array_equal(reconstructed_g1, saved_legacy)
    within_trace = metrics(reconstructed_g8, saved_g8)
    cross = metrics(reconstructed_g8, saved_legacy)
    for observed, key in [
        (within_trace, "same_trace_h_los_check"), (cross, "legacy_h_los_check")
    ]:
        assert np.isclose(observed["max_relative"], g8_record[key]["max_relative_error"],
                          atol=1e-14, rtol=1e-8), (key, observed)
    offsets = near["tau_s"] - np.array([near["tau_s"][row_by_pose[p]] for p in near["pose_id"]])
    schema = json.loads((g8 / "paths/G-T1_A/PATHS_NEAR_SCHEMA.json").read_text())
    assert (offsets >= 0).all() and (offsets <= 2 * schema["tap_seconds"]).all()
    weakest = g8_record["legacy_h_los_check"]["worst_index"]
    worst_pose = pose_ids.index(weakest["pose_id"])
    worst_bin = weakest["bin"]
    worst_rx = weakest["rx_port_index"]
    worst_tx = weakest["tx_port_index"]
    print(json.dumps({
        "mode": "read-only saved-output comparison",
        "source_native_paths_sha256": legacy_hash,
        "legacy_phase_reproduced_bitwise": True,
        "within_trace": within_trace,
        "cross": cross,
        "phase_arithmetic_only": metrics(native_coeff * native_phase[..., None, None],
                                         saved_legacy),
        "delay_only_using_float64_phase": metrics(native_coeff * g8_phase[..., None, None],
                                                 native_coeff * native_phase[..., None, None]),
        "coefficient_only": metrics(coeff, native_coeff),
        "cross_with_float64_phase_on_both": metrics(reconstructed_g8,
                                                    native_coeff * native_phase[..., None, None]),
        "max_absolute_delay_difference_s": float(np.max(np.abs(tau - native_tau))),
        "near_max_offset_m": float(offsets.max() * schema["propagation_speed_m_s"]),
        "worst_cross_entry_legacy_amplitude": float(abs(saved_legacy[worst_pose, worst_bin,
                                                                       worst_rx, worst_tx])),
        "worst_cross_entry_delay_difference_s": float(tau[worst_pose, 0]
                                                     - native_tau[worst_pose, worst_bin]),
    }, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
