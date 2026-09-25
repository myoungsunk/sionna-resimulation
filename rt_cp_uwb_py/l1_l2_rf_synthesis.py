"""Opt-in saved-path, passive Cartesian RF synthesis for L1/L2.

Port order is RHCP, LHCP, LP X, LP Y, LP +45, LP -45. This module
implements numerical synthesis; it does not grant physical input admission.
"""
from pathlib import Path

import numpy as np
from scipy.interpolate import CubicSpline, RegularGridInterpolator

from .core import Material, make_ideal_cp_antenna, normalize
from .channel import _local_sp_bases
from .passive_reflection import passive_jones_reflection

C0 = 299792458.0
DEFAULT_FREQUENCIES = 6250400000.0 + 1950000.0 * np.arange(257)


def historical_mount_frames(row):
    """Return TX/RX local-to-world frames using room sweep mount semantics."""
    bore = normalize([float(row.get('tx_boresight_' + a, v))
                      for a, v in zip('xyz', (0., 0., -1.))])
    h = np.array([1., 0., 0.])
    if abs(np.dot(h, bore)) > .95:
        h = np.array([0., 1., 0.])
    h = normalize(h - np.dot(h, bore) * bore)
    yaw = np.deg2rad(float(row.get('rx_azimuth_deg', 0.)))
    rx_h = np.array([np.cos(yaw), np.sin(yaw), 0.])
    tilt = np.deg2rad(float(row.get('rx_tilt_deg', 0.)))
    up = np.array([0., 0., 1.])
    rx_bore = normalize(up * np.cos(tilt) + np.cross(rx_h, up) * np.sin(tilt))
    return (make_ideal_cp_antenna(np.zeros(3), bore, h).ffd_local_to_world,
            make_ideal_cp_antenna(np.zeros(3), rx_bore, rx_h).ffd_local_to_world)


class SixPortGrids:
    """Reusable bilinear angular interpolators for six physical FFD ports."""

    def __init__(self, grids):
        if len(grids) != 6:
            raise ValueError('Exactly six ordered FFD grids required')
        self.ports = []
        for item in grids:
            if isinstance(item, (str, Path)):
                with np.load(item) as archive:
                    p = {key: archive[key].copy() for key in archive.files}
            else:
                p = item
            theta, phi, freq = [np.asarray(p[k], float) for k in ('theta', 'phi', 'frequencies')]
            fields = np.asarray(p['fields'], complex)
            if fields.shape != (len(freq), len(theta), len(phi), 2):
                raise ValueError('FFD shape mismatch')
            if any(np.any(np.diff(a) <= 0) for a in (theta, phi, freq)):
                raise ValueError('FFD axes must increase strictly')
            if not all(np.isfinite(a).all() for a in (theta, phi, freq, fields)):
                raise ValueError('Nonfinite FFD input')
            interp = RegularGridInterpolator((theta, phi), fields.transpose(1, 2, 0, 3))
            self.ports.append((phi[0], freq, interp))

    def world_fields(self, directions, frame, frequencies):
        """Return complex fields with shape (6, paths, frequency, Cartesian)."""
        directions = np.asarray(directions, float)
        directions = directions / np.linalg.norm(directions, axis=-1, keepdims=True)
        frame = np.asarray(frame, float)
        if frame.shape != (3, 3) or not np.allclose(frame.T @ frame, np.eye(3), atol=1e-12):
            raise ValueError('Mount frame must be orthonormal')
        local = directions @ frame
        th = np.arccos(np.clip(local[:, 2], -1., 1.))
        ph = np.arctan2(local[:, 1], local[:, 0])
        et = np.column_stack((np.cos(th)*np.cos(ph), np.cos(th)*np.sin(ph), -np.sin(th))) @ frame.T
        ep = np.column_stack((-np.sin(ph), np.cos(ph), np.zeros(len(ph)))) @ frame.T
        output = []
        for p0, source_f, interp in self.ports:
            if min(frequencies) < source_f[0] or max(frequencies) > source_f[-1]:
                raise ValueError('Frequency extrapolation is not admitted')
            sampled = interp(np.column_stack((th, (ph-p0) % (2*np.pi) + p0)))
            world = sampled[..., 0, None]*et[:, None, :] + sampled[..., 1, None]*ep[:, None, :]
            output.append(CubicSpline((source_f-6.5e9)/1e9, world, axis=1)((frequencies-6.5e9)/1e9))
        return np.asarray(output)


def path_operator(path, frequencies):
    """Frequency-independent passive Cartesian reflection transport."""
    points = np.asarray(path['points'], float)
    segments = np.diff(points, axis=0)
    norms = np.linalg.norm(segments, axis=1)
    if len(norms) == 0 or np.any(norms <= 1e-9) or not np.isfinite(points).all():
        raise ValueError('Invalid saved path geometry')
    directions = segments / norms[:, None]
    normals, materials = path['normals'], path['materials']
    if len(normals) != len(materials) or len(normals) != len(points)-2:
        raise ValueError('Saved reflection metadata mismatch')
    op = np.eye(3, dtype=complex)
    for i, (normal, definition) in enumerate(zip(normals, materials)):
        material = Material(**definition)
        if material.conductivity_s_m != 0:
            raise ValueError('Frequency-dependent conductivity not admitted')
        si, pi, so, po, angle = _local_sp_bases(directions[i], directions[i+1], normal)
        j = passive_jones_reflection(material, angle, np.asarray([frequencies[0], frequencies[-1]]))
        if not np.allclose(j[:, :, 0], j[:, :, 1], atol=1e-14, rtol=1e-13):
            raise ValueError('Dispersive reflection operator not admitted')
        op = np.column_stack((so, po)) @ j[:, :, 0] @ np.column_stack((si, pi)).T @ op
    length = float(path['path_length_m'])
    if not np.isfinite(length) or length <= 0 or not np.isclose(length, norms.sum(), atol=1e-9, rtol=1e-12):
        raise ValueError('Saved path length disagrees with vertices')
    return op, directions[0], directions[-1], length


def synthesize(paths, grids, row=None, frequencies=None, *, frames=None, return_per_path=False):
    """Return H (3,2,2,F), optionally paired with per-path H (3,2,2,P,F).

    RX effective-length contraction is reciprocal transpose, without conjugation.
    Explicit frames override historical row mounts for numerical fixtures.
    """
    freq = np.asarray(DEFAULT_FREQUENCIES if frequencies is None else frequencies, float)
    if freq.ndim != 1 or not len(freq) or np.any(freq <= 0) or not np.isfinite(freq).all() or np.any(np.diff(freq) <= 0):
        raise ValueError('Positive increasing frequencies required')
    ports = grids if isinstance(grids, SixPortGrids) else SixPortGrids(grids)
    tx_frame, rx_frame = historical_mount_frames(row or {}) if frames is None else frames
    if not paths:
        empty = np.zeros((3, 2, 2, 0, len(freq)), complex)
        return (empty.sum(axis=3), empty) if return_per_path else empty.sum(axis=3)
    records = [path_operator(p, freq) for p in paths]
    operators = np.array([r[0] for r in records])
    tx = ports.world_fields(np.array([r[1] for r in records]), tx_frame, freq).reshape(3, 2, len(paths), len(freq), 3)
    rx = ports.world_fields(-np.array([r[2] for r in records]), rx_frame, freq).reshape(3, 2, len(paths), len(freq), 3)
    lengths = np.array([r[3] for r in records])
    factor = C0 / freq[None, :] / (4*np.pi*lengths[:, None]) * np.exp(-2j*np.pi*freq[None, :]*lengths[:, None]/C0)
    per_path = np.einsum('arpfc,pcd,atpfd->artpf', rx, operators, tx, optimize=True) * factor[None, None, None, :, :]
    result = per_path.sum(axis=3)
    if not np.isfinite(result).all():
        raise ValueError('Nonfinite synthesized channel')
    return (result, per_path) if return_per_path else result
