"""Independently check serialized G8 outputs against the original pilot and G1."""

from pathlib import Path
import sys

import numpy as np

from run_tb3_g1_pilot import read, sha, write


def main(current, previous, g1, destination):
    g1_manifest = read(g1 / "G1.json")
    native_path = g1 / "PATHS_LoS.npz"
    assert sha(native_path) == g1_manifest["outputs"][native_path.name]["sha256"]
    assert sha(current / "rf_poses.json") == sha(previous / "rf_poses.json")
    assert sha(current / "H_LoS_original_g1.npy") == sha(previous / "H_LoS.npy")
    pack_path = "paths/G-T1_A/PATHS_NEAR.npz"
    result = read(current / "G8.json")
    with (np.load(current / pack_path, allow_pickle=False) as pack,
          np.load(previous / pack_path, allow_pickle=False) as old_pack,
          np.load(native_path, allow_pickle=False) as native):
        assert set(pack.files) == set(old_pack.files)
        for field in set(pack.files) - {"coefficients"}:
            assert np.array_equal(pack[field], old_pack[field]), field
        is_los = pack["is_los"]
        assert np.array_equal(pack["coefficients"][~is_los], old_pack["coefficients"][~is_los])
        order = np.argsort(pack["pose_id"][is_los])
        assert np.array_equal(pack["pose_id"][is_los][order],
                              [p["pose_id"] for p in read(current / "rf_poses.json")])
        delays = pack["tau_s"][is_los][order, None]
        direct = pack["coefficients"][is_los][order]
        assert np.array_equal(pack["frequencies_hz"], native["freqs_hz"])
        reference = np.load(current / "H_LoS.npy", allow_pickle=False)
        rebuilt = direct * np.exp(
            -2j * np.pi * pack["frequencies_hz"][None, :] * delays
        )[..., None, None]
        assert np.array_equal(np.broadcast_to(delays, native["tau"].shape), native["tau"])
        peak_coefficients = float(np.max(np.abs(direct - native["a"])))
        absolute = np.abs(rebuilt - reference)
        relative = np.divide(absolute, np.abs(reference), out=np.zeros_like(absolute),
                             where=reference != 0)
        assert np.all(absolute[reference == 0] == 0)
        assert float(relative.max()) == result["independent_g1_h_los_check"]["max_relative_error"]

    new_h = np.load(current / "H_full.npy", allow_pickle=False)
    old_h = np.load(previous / "H_full.npy", allow_pickle=False)
    old_direct = np.load(previous / "H_LoS_from_full_trace.npy", allow_pickle=False)
    reconstructed_change = (new_h - old_h) - (rebuilt - old_direct)
    assert np.max(np.abs(reconstructed_change)) < 1e-15
    write(destination, {
        "same_pose_table": True,
        "original_g1_channel_sha256_preserved": True,
        "near_path_geometry_and_metadata_identical": True,
        "reflected_near_coefficients_bitwise_identical": True,
        "native_g1_tau_bitwise_identical": True,
        "native_g1_port_coefficient_max_absolute_delta": peak_coefficients,
        "native_g1_port_coefficients_bitwise_identical": peak_coefficients == 0,
        "recomputed_g8_max_relative": float(relative.max()),
        "full_H_max_absolute_change": float(np.max(np.abs(new_h - old_h))),
        "full_H_max_absolute_change_beyond_direct_term": float(
            np.max(np.abs(reconstructed_change))),
        "near_paths": len(is_los),
    })


if __name__ == "__main__":
    main(*map(Path, sys.argv[1:]))
