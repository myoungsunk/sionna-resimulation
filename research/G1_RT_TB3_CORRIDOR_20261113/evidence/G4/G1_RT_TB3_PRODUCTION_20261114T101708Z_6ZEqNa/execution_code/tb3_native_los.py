"""Evaluate the native LP response on direct paths already found by F1."""
from __future__ import annotations

import numpy as np


def native_direct_coefficients(core, tx_xyz, rx_xyz, poses, mount_deg, banks, ports):
    """Apply pinned Sionna field operations to known LoS segments without PathSolver."""
    coefficients, delays = native_direct_fields(core, tx_xyz, rx_xyz, poses, mount_deg, banks, ports)
    if not np.all(delays == delays[0]):
        raise ValueError("Native direct path delay disagrees across yaws at one position")
    return coefficients, float(delays[0])


def native_direct_fields(core, tx_xyz, rx_xyz, poses, mount_deg, banks, ports):
    """Compute the same native field for a single XY or one RX position per pose."""
    import drjit as dr
    from qclean_uwb.scenarios.corridor import rot_z
    from sionna.rt.path_solvers.field_calculator import FieldCalculator
    from sionna.rt.path_solvers.paths_buffer import PathsBuffer

    C, mi = core.C, core.mi
    tx = mi.Point3f(*map(float, tx_xyz))
    count = len(poses)
    rx_xyz = np.asarray(rx_xyz)
    if rx_xyz.shape == (3,):
        rx = mi.Point3f(*(dr.full(mi.Float, float(coordinate), count) for coordinate in rx_xyz))
    elif rx_xyz.shape == (count, 3):
        rx = mi.Point3f(*(mi.Float(axis) for axis in rx_xyz.T))
    else:
        raise ValueError("Expected one RX position or exactly one per pose")
    tx_orientation = mi.Point3f(*C.euler(C.ANCHOR_ROTATION))
    rotations = np.array([C.euler(rot_z(p["yaw_body_deg"] + mount_deg))
                          for p in poses])
    rx_orientation = mi.Point3f(*(mi.Float(axis) for axis in rotations.T))
    dr.make_opaque(tx, rx, tx_orientation, rx_orientation)
    # One zero-interaction row per yaw on the already validated F1 segment.
    # The native field calculator runs without a candidate generator.
    paths = PathsBuffer(count, max_depth=0, diffraction=False)
    paths.valid = dr.full(mi.Bool, True, count)
    indices = dr.arange(mi.UInt, count)
    dr.scatter(paths.target_indices, indices, indices)
    calculator = FieldCalculator()
    tx_ports, rx_ports = ports
    tx_patterns = [port.evaluate for port in tx_ports]
    rx_patterns = [port.evaluate for port in rx_ports]
    frequencies = banks[0]["freqs_hz"]
    coefficients = np.empty((len(poses), len(frequencies), 2, 2), dtype=np.complex128)
    for bin_index, frequency in enumerate(frequencies):
        for bank, tx_port, rx_port in zip(banks, tx_ports, rx_ports, strict=True):
            values = bank["e_theta"][bin_index], bank["e_phi"][bin_index]
            tx_port.update(*values)
            rx_port.update(*values)
        # PathSolver uses an opaque batch of direct path geometry and keeps
        # these operations in the same FieldCalculator kernel.
        paths.valid = dr.full(mi.Bool, True, count)
        paths.schedule()
        dr.eval()
        wavelength = C.C0 / mi.Float(float(frequency))
        calculator(wavelength, paths, samples_per_src=1, diffraction=False,
                   src_positions=tx, tgt_positions=rx,
                   src_orientations=tx_orientation, tgt_orientations=rx_orientation,
                   src_antenna_patterns=tx_patterns, tgt_antenna_patterns=rx_patterns)
        for r, row in enumerate(paths.a):
            for t, coefficient in enumerate(row):
                coefficients[:, bin_index, r, t] = (
                    np.asarray(coefficient.real) + 1j * np.asarray(coefficient.imag)
                )
    delays = np.asarray(paths.tau)
    if delays.shape != (count,) or not np.isfinite(delays).all():
        raise ValueError("Native direct field produced invalid delays")
    return coefficients, delays
