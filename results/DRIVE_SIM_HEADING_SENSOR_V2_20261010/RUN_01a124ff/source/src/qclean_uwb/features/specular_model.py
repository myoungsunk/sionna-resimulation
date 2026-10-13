"""Analytic first-order specular reflections of the rectangular corridor (image method + ITU-R P.2040 slab coefficients).

Independent of the Sionna path solver: the reflected field of every surface is built from the geometry, the surface material and
the two antenna patterns, exactly like the LoS field (Cartesian contraction of the FFD vectors) but with the reflected path's
departure / arrival directions, its unfolded length and the slab reflection coefficients (TE / TM) of ITU-R P.2040-3 eq. (43a),
as used by Sionna RT 2.0 for a RadioMaterial with a thickness.
"""
from __future__ import annotations

import numpy as np

C0 = 299792458.0
EPS0 = 8.8541878128e-12
# ITU-R P.2040 constants (a, b, c, d): eps_r = a f_GHz^b, sigma = c f_GHz^d (same values as sionna.rt.radio_materials.itu).
ITU = {"concrete": (5.24, 0.0, 0.0462, 0.7822), "plasterboard": (2.73, 0.0, 0.0085, 0.9395)}
SURFACES = {  # name: (plane axis, coordinate or 'H'/'L'/'h', group, material, thickness_m)
    "floor": (2, "zero", "floor", "concrete", 0.2), "ceiling": (2, "H", "ceiling", "concrete", 0.2),
    "wall_y_neg": (1, "-h", "side_walls", "plasterboard", 0.0125), "wall_y_pos": (1, "h", "side_walls", "plasterboard", 0.0125),
    "end_x_min": (0, "zero", "end_walls", "concrete", 0.2), "end_x_max": (0, "L", "end_walls", "concrete", 0.2),
}


def eta_complex(material: str, f_hz, scale: float = 1.0):
    """Complex relative permittivity; ``scale`` multiplies eps_r and sigma (to test a wrong material assumption)."""
    a, b, c, d = ITU[material]
    a, c = a * scale, c * scale
    f_ghz = np.asarray(f_hz, float) / 1e9
    return a * f_ghz ** b - 1j * (c * f_ghz ** d) / (2 * np.pi * np.asarray(f_hz, float) * EPS0)


def slab_reflection(cos_theta, eta, d, wavelength):
    """ITU-R P.2040-3 eq. (43a): TE and TM reflection coefficients of a single-layer slab (vacuum on both sides)."""
    sin2 = 1.0 - cos_theta ** 2
    root = np.sqrt(eta - sin2 + 0j)
    r_te_p = (cos_theta - root) / (cos_theta + root)
    r_tm_p = (eta * cos_theta - root) / (eta * cos_theta + root)
    q = 2 * np.pi * d / wavelength * root
    e2q = np.exp(-2j * q)
    return r_te_p * (1 - e2q) / (1 - r_te_p ** 2 * e2q), r_tm_p * (1 - e2q) / (1 - r_tm_p ** 2 * e2q)


def plane(name, length, half_width, height):
    axis, key = SURFACES[name][0], SURFACES[name][1]
    coord = {"zero": 0.0, "H": height, "-h": -half_width, "h": half_width, "L": length}[key]
    n = np.zeros(3)
    n[axis] = 1.0
    return axis, coord, n


def mirror(point, axis, coord):
    q = np.array(point, float)
    q[axis] = 2.0 * coord - q[axis]
    return q


def reflected_field(banks, tx_pos, rx_pos, tx_rot, name, freq_hz, length, half_width, height, mat_scale: float = 1.0):
    """Return (E_arriving, k_arrival, L): the reflected TX field vectors at the receiver, shape (n_freq, 2 TX ports, 3), the propagation
    direction after reflection and the unfolded path length."""
    axis, coord, n = plane(name, length, half_width, height)
    _, _, _, material, thick = SURFACES[name]
    rx_img = mirror(rx_pos, axis, coord)
    vec = rx_img - np.asarray(tx_pos, float)
    L = float(np.linalg.norm(vec))
    k_i = vec / L
    cos_i = abs(float(k_i @ n))
    k_r = k_i - 2.0 * (k_i @ n) * n
    s = np.cross(k_i, n)
    if np.linalg.norm(s) < 1e-9:  # normal incidence: the plane of incidence is arbitrary and r_te = r_tm in the (s, p) convention
        s = np.cross(n, [1.0, 0.0, 0.0] if abs(n[0]) < 0.9 else [0.0, 1.0, 0.0])
    s = s / np.linalg.norm(s)
    p_i, p_r = np.cross(k_i, s), np.cross(k_r, s)
    r_te, r_tm = slab_reflection(cos_i, eta_complex(material, freq_hz, mat_scale), thick, C0 / np.asarray(freq_hz, float))
    e_tx = banks.vectors(tx_rot, k_i)  # (n_freq, 2, 3), field radiated toward the reflection point
    e_s = e_tx @ s
    e_p = e_tx @ p_i
    e_r = (r_te[:, None] * e_s)[..., None] * s + (r_tm[:, None] * e_p)[..., None] * p_r
    return e_r, k_r, L
