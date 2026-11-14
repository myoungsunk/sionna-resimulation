"""Isolate FFD grid arithmetic with native LoS geometry, basis and channel contraction."""
from pathlib import Path
import sys

import numpy as np

from run_tb3_g1_pilot import load_runtime, read, write


def direct_port(bank, bin_index, receive, mi, scale):
    # Use the same native query angles, interpolating before casting back to
    # the native complex type. The rest of the Sionna evaluation is untouched.
    def evaluate(theta, phi):
        fields = bank.sample(np.asarray(theta, dtype=np.float64),
                             np.asarray(phi, dtype=np.float64), [bin_index])
        return tuple(
            mi.Complex2f(mi.Float(field[0].real * scale),
                         mi.Float(field[0].imag * (-scale if receive else scale)))
            for field in fields
        )

    return evaluate


def main(destination):
    core, _, _ = load_runtime(Path("/ref"))
    import drjit as dr
    from qclean_uwb.scenarios.corridor import rot_z
    from sionna.rt.antenna_pattern import antenna_pattern_to_world_implicit as world
    from sionna.rt.utils import jones_vec_dot, rotation_matrix

    C, mi, P = core.C, core.mi, core.P
    poses = read(Path("/g8/rf_poses.json"))
    tasks = read(Path("/g8/rf_tasks.json"))
    scene = read(Path("/input/scene/SCENE_MANIFEST.json"))["geometries"]["G-T1"]
    legacy = np.load("/g1/PATHS_LoS.npz", allow_pickle=False)
    native = legacy["a"]
    raw_banks = C.load_banks()
    banks = [P.Bank(b) for b in raw_banks]
    tx_ports, rx_ports = C.make_ports(raw_banks)
    # Cover both band endpoints, a mid-band node, and an interior bin.
    bins = (0, 128, 171, 256)
    exact_count = 0
    delta_relative = 0.0
    native_delta_relative = 0.0
    substitution_delta_relative = 0.0
    tx = mi.Point3f(*scene["anchors_xyz_m"]["A"])
    rt = rotation_matrix(mi.Point3f(*C.euler(C.ANCHOR_ROTATION)))
    for task in tasks:
        ids = task["pose_ids"]
        rx = mi.Point3f(task["x"], task["y"], scene["rx_z_m"])
        vector = mi.Vector3f(rx - tx)
        distance = dr.norm(vector)
        direction = vector * dr.rcp(distance)
        rr = np.array([C.euler(rot_z(poses[i]["yaw_body_deg"])) for i in ids])
        rr = rotation_matrix(mi.Point3f(*(mi.Float(axis) for axis in rr.T)))
        for k in bins:
            for b, t, r in zip(raw_banks, tx_ports, rx_ports, strict=True):
                t.update(b["e_theta"][k], b["e_phi"][k])
                r.update(b["e_theta"][k], b["e_phi"][k])
            conventional = ([p.evaluate for p in tx_ports], [p.evaluate for p in rx_ports])
            controlled = ([direct_port(b, k, False, mi, P.SCALE) for b in banks],
                          [direct_port(b, k, True, mi, P.SCALE) for b in banks])
            wavelength = C.C0 / mi.Float(float(legacy["freqs_hz"][k]))
            scale = dr.rcp(distance) * (wavelength * dr.rcp(4. * dr.pi))
            for method, (patterns_t, patterns_r) in enumerate((conventional, controlled)):
                fs_t = [world(p, rt, direction, "out") for p in patterns_t]
                fs_r = [world(p, rr, -direction, "in") for p in patterns_r]
                output = np.empty((len(ids), 2, 2), dtype=np.complex128)
                for r, rf in enumerate(fs_r):
                    for t, tf in enumerate(fs_t):
                        a = jones_vec_dot(rf, tf) * scale
                        output[:, r, t] = np.asarray(a.real) + 1j * np.asarray(a.imag)
                reference = native[ids, k]
                if method == 0:
                    conventional_output = output
                    exact_count += int(np.count_nonzero(output == reference))
                    native_delta_relative = max(native_delta_relative, float(
                        np.max(np.abs(output - reference) / np.abs(reference))))
                else:
                    delta_relative = max(delta_relative, float(
                        np.max(np.abs(output - reference) / np.abs(reference))))
                    substitution_delta_relative = max(substitution_delta_relative, float(
                        np.max(np.abs(output - conventional_output) / np.abs(conventional_output))))
    write(destination, {
        "pose_count": len(poses), "tested_bins": bins,
        "native_reference_coefficient_entries_reproduced_bitwise": exact_count,
        "native_evaluation_max_relative_to_frozen_reference": native_delta_relative,
        "method_b_interpolation_max_relative_to_frozen_reference": delta_relative,
        "max_relative_coefficient_delta_replacing_only_ffd_grid_arithmetic": substitution_delta_relative,
    })


if __name__ == "__main__":
    main(Path(sys.argv[1]))
