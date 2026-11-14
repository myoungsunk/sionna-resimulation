"""Attribute the original G8 coefficient mismatch from saved paths; no ray calls."""
import sys
from pathlib import Path

import numpy as np

from run_tb3_g1_pilot import load_runtime, read, sha, write


def cartesian_fields(P, banks, theta, phi, rotation):
    et, ep = np.stack([bank.sample(theta, phi) for bank in banks], axis=2)
    th, ph = P.sph_basis(theta, phi)
    return P.SCALE * ((et[..., None] * th + ep[..., None] * ph) @ rotation.T)


def project(tx, rx, jones):
    return np.einsum("bri,bij,btj->brt", rx, jones, tx)


def main(destination):
    core, _, versions = load_runtime(Path("/ref"))
    import drjit as dr
    from sionna.rt.utils import rotation_matrix, theta_phi_from_unit_vec
    from qclean_uwb.drivesim.rf_store import load_banks
    from qclean_uwb.scenarios.corridor import rot_z

    P, C, mi = core.P, core.C, core.mi
    root = Path("/g1")
    old = Path("/g8")
    manifest = read(root / "G1.json")
    scene = read(Path("/input/scene/SCENE_MANIFEST.json"))["geometries"]["G-T1"]
    banks = load_banks()
    path = root / "PATHS_LoS.npz"
    assert sha(path) == manifest["outputs"][path.name]["sha256"]
    a = np.load(path, allow_pickle=False)
    near = np.load(old / "paths/G-T1_A/PATHS_NEAR.npz", allow_pickle=False)
    previous = near["coefficients"][near["is_los"]]
    pose_ids = near["pose_id"][near["is_los"]]
    previous = previous[np.argsort(pose_ids)]
    assert np.array_equal(np.sort(pose_ids), np.arange(len(pose_ids)))
    native = a["a"]
    freqs = banks[0].freqs_hz
    assert np.array_equal(freqs, a["freqs_hz"]) and np.array_equal(freqs, near["frequencies_hz"])
    poses = read(old / "rf_poses.json")
    tasks = read(old / "rf_tasks.json")
    terms = {name: np.empty_like(native) for name in (
        "method_b_reconstructed", "remove_jones_spline", "remove_spline_use_native_local_angles",
    )}
    checksums = {path.name: sha(path)}
    max_world_angle_delta = 0.0
    src = np.array(scene["anchors_xyz_m"]["A"])
    for task in tasks:
        trace_name = f"trace/{task['tag']}_trace.npz"
        trace_file = root / trace_name
        checksums[trace_name] = sha(trace_file)
        assert checksums[trace_name] == manifest["outputs"][trace_name]["sha256"]
        trace = np.load(trace_file, allow_pickle=False)
        ids = task["pose_ids"]
        direct = np.argmin(abs(trace["tau"] - a["tau"][ids[0], 0]))
        assert trace["tau"][direct] == a["tau"][ids[0], 0]
        angles = trace["ang"][:, direct:direct + 1]
        for index, field in enumerate(("theta_t", "phi_t", "theta_r", "phi_r")):
            delta = (a[field][ids] - angles[index] + np.pi) % (2 * np.pi) - np.pi
            max_world_angle_delta = max(max_world_angle_delta, float(np.abs(delta).max()))
        stored_jones = P.interp_jones(trace["jones"], trace["node_freq_hz"], freqs,
                                      present=trace["present"])[:, direct]
        # Keep the original transmit direction. Replace the node spline by the
        # exact free-space frequency law and transverse projector for LoS.
        departure = P.direction(*angles[:2])[0]
        projection = np.eye(3) - np.outer(departure, departure)
        distance = trace["tau"][direct] * C.C0
        free_space = C.C0 / (4 * np.pi * distance * freqs[:, None, None]) * projection
        tx = np.stack([P.field_world(b, C.ANCHOR_ROTATION, *angles[:2])[:, 0]
                       for b in banks], axis=1)

        tgt = np.array([task["x"], task["y"], scene["rx_z_m"]])
        raw_direction = mi.Point3f(*map(float, tgt)) - mi.Point3f(*map(float, src))
        native_direction = mi.Vector3f(raw_direction * dr.rcp(dr.norm(raw_direction)))
        matrix_t = rotation_matrix(mi.Point3f(*C.euler(C.ANCHOR_ROTATION)))
        theta_t, phi_t = [float(np.asarray(v)[0])
                          for v in theta_phi_from_unit_vec(matrix_t.T @ native_direction)]
        tx_local = cartesian_fields(P, banks, theta_t, phi_t, C.ANCHOR_ROTATION)
        for pose_id in ids:
            rotation = rot_z(poses[pose_id]["yaw_body_deg"])
            rx = np.stack([P.field_world(b, rotation, *angles[2:])[:, 0] for b in banks], axis=1)
            terms["method_b_reconstructed"][pose_id] = project(tx, rx, stored_jones)
            terms["remove_jones_spline"][pose_id] = project(tx, rx, free_space)
            matrix_r = rotation_matrix(mi.Point3f(*C.euler(rotation)))
            theta_r, phi_r = [float(np.asarray(v)[0])
                              for v in theta_phi_from_unit_vec(matrix_r.T @ -native_direction)]
            rx_local = cartesian_fields(P, banks, theta_r, phi_r, rotation)
            terms["remove_spline_use_native_local_angles"][pose_id] = project(
                tx_local, rx_local, free_space)
    assert np.allclose(terms["method_b_reconstructed"], previous, rtol=1e-12, atol=1e-15)
    nodes = core.node_bins(len(freqs), "17")
    between = np.setdiff1d(np.arange(len(freqs)), nodes)
    comparisons = {}
    for name, candidate in terms.items():
        relative = abs(candidate - native) / abs(native)
        comparisons[name] = {
            "max_relative": float(relative.max()),
            "node_max_relative": float(relative[:, nodes].max()),
            "between_nodes_max_relative": float(relative[:, between].max()),
            "max_absolute": float(np.abs(candidate - native).max()),
            "entries_over_1e-6": int(np.count_nonzero(relative >= 1e-6)),
        }
    write(destination, {
        "runtime_versions": versions,
        "pose_count": len(poses),
        "nodes": nodes,
        "input_sha256": checksums,
        "old_F1_coefficients_reproduced_max_absolute": float(
            abs(terms["method_b_reconstructed"] - previous).max()),
        "native_vs_method_b_stored_world_angle_delta_max_rad": max_world_angle_delta,
        "comparisons_to_native_g1_port_coefficients": comparisons,
    })


if __name__ == "__main__":
    main(Path(sys.argv[1]))
