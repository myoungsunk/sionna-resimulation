"""Evaluate the native LP response on direct paths already found by F1."""
from __future__ import annotations

import numpy as np


def native_direct_coefficients(core, tx_xyz, rx_xyz, poses, mount_deg, banks, ports):
    """Apply pinned Sionna field operations to known LoS segments without PathSolver."""
    import drjit as dr
    from qclean_uwb.scenarios.corridor import rot_z
    from sionna.rt.antenna_pattern import antenna_pattern_to_world_implicit
    from sionna.rt.utils import jones_vec_dot, rotation_matrix

    C, mi = core.C, core.mi
    tx = mi.Point3f(*map(float, tx_xyz))
    rx = mi.Point3f(*map(float, rx_xyz))
    path = mi.Vector3f(rx - tx)
    distance = dr.norm(path)
    direction = path * dr.rcp(distance)
    tx_rotation = rotation_matrix(mi.Point3f(*C.euler(C.ANCHOR_ROTATION)))
    rotations = np.array([C.euler(rot_z(p["yaw_body_deg"] + mount_deg))
                          for p in poses])
    rx_rotation = rotation_matrix(mi.Point3f(*(mi.Float(axis) for axis in rotations.T)))
    tx_ports, rx_ports = ports
    frequencies = banks[0]["freqs_hz"]
    coefficients = np.empty((len(poses), len(frequencies), 2, 2), dtype=np.complex128)
    for bin_index, frequency in enumerate(frequencies):
        for bank, tx_port, rx_port in zip(banks, tx_ports, rx_ports, strict=True):
            values = bank["e_theta"][bin_index], bank["e_phi"][bin_index]
            tx_port.update(*values)
            rx_port.update(*values)
        tx_fields = [antenna_pattern_to_world_implicit(port.evaluate, tx_rotation, direction, "out")
                     for port in tx_ports]
        rx_fields = [antenna_pattern_to_world_implicit(port.evaluate, rx_rotation, -direction, "in")
                     for port in rx_ports]
        wavelength = C.C0 / mi.Float(float(frequency))
        scale = dr.rcp(distance) * (wavelength * dr.rcp(4. * dr.pi))
        for r, rx_field in enumerate(rx_fields):
            for t, tx_field in enumerate(tx_fields):
                coefficient = jones_vec_dot(rx_field, tx_field) * scale
                coefficients[:, bin_index, r, t] = (
                    np.asarray(coefficient.real) + 1j * np.asarray(coefficient.imag)
                )
    delay = distance * dr.rcp(C.C0)
    return coefficients, float(np.asarray(delay)[0])
