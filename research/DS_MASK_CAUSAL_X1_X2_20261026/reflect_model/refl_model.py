"""Reflection-aware polarization/range observer for the single-anchor corridor.

Extends the LOS-only SourceFFD model with specular image-method paths off the six corridor planes, so that
the predicted first-path observables include the multipath that the Sionna RT generator put into the measured H.

Generator contract (scripts/drive_sim/rf_b_apply.py + qclean_uwb.drivesim.pattern_apply):
    H[f, rx, tx] = sum_paths  F_rx(f, arrival)^T  J_path(f)  F_tx(f, departure)  exp(-j 2 pi f tau)
with world-frame FFD field vectors F (SCALE included) and a 3x3 transverse Jones matrix J per path.
For the LOS path SourceFFD uses J = lambda / (4 pi L) * I, which reproduces the stored H_LoS observables to ~1e-5.
Here every specular path gets J = lambda / (4 pi L_total) * M_k ... M_1 with one Cartesian reflection operator
    M = r_TE(f) s s^T + r_TM(f) p_out p_in^T,   s = unit(k_in x n),  p_in = s x k_in,  p_out = s x k_out
per bounce (convention checked at normal incidence: r_TM = -r_TE there, so both polarizations reflect identically).

Scene (receipt results/CORRIDOR_SCAN2_20261007/*/receipt.json): box 20 x 2.4 x 2.7 m, floor/ceiling/end walls ITU
concrete 0.2 m, side walls ITU plasterboard 12.5 mm; Sionna RT 2.0.1, specular reflection up to depth 3, refraction on,
no diffraction / diffuse.  Refracted rays leave the box and never reach the receiver, so they are not modeled.

Nothing in this module reads truth.  It is a deterministic function of (x, y, yaw) and the scene description.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

import numpy as np

C0 = 299792458.0
EPS0 = 8.8541878128e-12
B_OLD = -0.5315983906250129          # range model constant of the original filter (p3_rf_adapter4.B_OLD)

# ITU-R P.2040 table 3 parameters as used by Sionna RT ITU materials: eps_r' = a f^b, sigma = c f^d  (f in GHz)
ITU = {
    "concrete": (5.24, 0.0, 0.0462, 0.7822),
    "plasterboard": (2.73, 0.0, 0.0085, 0.9395),
}


def complex_permittivity(material: str, freqs_hz: np.ndarray, eps_scale: float = 1.0, sigma_scale: float = 1.0) -> np.ndarray:
    a, b, c, d = ITU[material]
    fg = np.asarray(freqs_hz, float) / 1e9
    eps_r = eps_scale * a * fg ** b
    sigma = sigma_scale * c * fg ** d
    return eps_r - 1j * sigma / (2 * np.pi * np.asarray(freqs_hz, float) * EPS0)


def fresnel_interface(cos_i: np.ndarray, eta: np.ndarray):
    """Air -> half-space reflection (r_TE, r_TM); cos_i (n,), eta (nf,) -> each (n, nf)."""
    cos_i = np.asarray(cos_i, float)[:, None]
    sin2 = 1.0 - cos_i ** 2
    root = np.sqrt(eta[None, :] - sin2 + 0j)
    root = np.where(root.real < 0, -root, root)
    r_te = (cos_i - root) / (cos_i + root)
    r_tm = (eta[None, :] * cos_i - root) / (eta[None, :] * cos_i + root)
    return r_te, r_tm, root


def reflection_coefficients(cos_i, eta, thickness_m, freqs_hz, mode: str):
    """(r_TE, r_TM), each (n, nf).  mode 'halfspace' or 'slab' (single homogeneous layer in air, ITU-R P.2040 form)."""
    r_te, r_tm, root = fresnel_interface(cos_i, eta)
    if mode == "halfspace":
        return r_te, r_tm
    if mode != "slab":
        raise ValueError(mode)
    q = 2 * np.pi * np.asarray(freqs_hz, float)[None, :] * thickness_m / C0 * root
    e = np.exp(-2j * q)
    out = []
    for r in (r_te, r_tm):
        out.append(r * (1 - e) / (1 - r * r * e))
    return out[0], out[1]


@dataclass(frozen=True)
class Plane:
    name: str
    axis: int                # coordinate fixed on the plane (0=x, 1=y, 2=z)
    value: float
    normal: tuple            # inward unit normal
    bounds: tuple            # ((axis_a, lo, hi), (axis_b, lo, hi))
    material: str
    thickness_m: float


def corridor_planes(length=20.0, width=2.4, height=2.7, offsets=None, materials=None):
    """Six planes of the corridor box.  ``offsets`` {name: metres} shifts a plane along its normal (robustness runs)."""
    h = width / 2
    offsets = offsets or {}
    materials = materials or {}
    base = [
        ("floor", 2, 0.0, (0, 0, 1), ((0, 0, length), (1, -h, h)), "concrete", 0.2),
        ("ceiling", 2, height, (0, 0, -1), ((0, 0, length), (1, -h, h)), "concrete", 0.2),
        ("wall_y_neg", 1, -h, (0, 1, 0), ((0, 0, length), (2, 0, height)), "plasterboard", 0.0125),
        ("wall_y_pos", 1, h, (0, -1, 0), ((0, 0, length), (2, 0, height)), "plasterboard", 0.0125),
        ("end_x_min", 0, 0.0, (1, 0, 0), ((1, -h, h), (2, 0, height)), "concrete", 0.2),
        ("end_x_max", 0, length, (-1, 0, 0), ((1, -h, h), (2, 0, height)), "concrete", 0.2),
    ]
    out = []
    for name, ax, val, n, bnd, mat, th in base:
        shift = offsets.get(name, 0.0)          # positive = plane moves into the corridor
        out.append(Plane(name, ax, val + shift * n[ax], n, bnd, materials.get(name, mat), th))
    return out


def mirror(point: np.ndarray, plane: Plane) -> np.ndarray:
    p = np.array(point, float)
    p[..., plane.axis] = 2 * plane.value - p[..., plane.axis]
    return p


def enumerate_sequences(n_planes: int, max_depth: int):
    seqs = [()]
    for k in range(1, max_depth + 1):
        for s in itertools.product(range(n_planes), repeat=k):
            if all(s[i] != s[i + 1] for i in range(k - 1)):
                seqs.append(s)
    return seqs


def _unit(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-300)


def trace_sequence(anchor: np.ndarray, tags: np.ndarray, seq, planes, tol=1e-9):
    """Specular path for one plane sequence and many tag positions.

    Returns (valid (n,), vertices (n, k+2, 3), length (n,)).  Vertices = anchor, reflection points..., tag.
    """
    n = len(tags)
    k = len(seq)
    if k == 0:
        verts = np.stack([np.repeat(anchor[None], n, 0), tags], 1)
        return np.ones(n, bool), verts, np.linalg.norm(tags - anchor, axis=1)
    images = [np.asarray(anchor, float)]
    for j in seq:
        images.append(mirror(images[-1], planes[j]))
    valid = np.ones(n, bool)
    target = tags.copy()
    pts = [None] * k
    for idx in range(k - 1, -1, -1):
        pl = planes[seq[idx]]
        src = images[idx + 1]                       # image after this bounce
        den = target[:, pl.axis] - src[pl.axis]
        with np.errstate(divide="ignore", invalid="ignore"):
            t = (pl.value - src[pl.axis]) / den
        ok = np.isfinite(t) & (t > tol) & (t < 1 - tol)
        q = src[None, :] + t[:, None] * (target - src[None, :])
        for ax, lo, hi in pl.bounds:
            ok &= (q[:, ax] >= lo - 1e-9) & (q[:, ax] <= hi + 1e-9)
        valid &= ok
        pts[idx] = q
        target = q
    length = np.linalg.norm(tags - images[-1][None, :], axis=1)
    verts = np.stack([np.repeat(anchor[None], n, 0)] + pts + [tags], 1)
    return valid, verts, length


class ReflectiveFFD:
    """Observer h(state) = [range, s] with specular multipath.

    base:          a loaded SourceFFD (provides the FFD banks, polar-cap handling and the frequency grid)
    max_depth:     0 = LOS only (must reproduce SourceFFD), up to 3 (generator depth)
    material_mode: 'slab' or 'halfspace'
    range_mode:    'geometric' (original filter: 3D distance + B_OLD) or 'fp' (first-path range of the modeled CIR)
    """

    def __init__(self, base, max_depth: int = 3, material_mode: str = "slab", range_mode: str = "geometric",
                 planes=None, plane_subset=None, eps_scale=1.0, sigma_scale=1.0, fd_step_m=2e-3, fd_step_rad=math.radians(0.1)):
        from qclean_uwb.drivesim import observation as O
        from qclean_uwb.scenarios.corridor import ANCHOR_ROTATION
        self.O = O
        self.AR = np.asarray(ANCHOR_ROTATION, float)
        self.base = base
        self.freqs = np.asarray(base.freqs, float)
        self.nf = len(self.freqs)
        self.window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(self.nf) / (self.nf - 1))
        self.planes = planes if planes is not None else corridor_planes()
        if plane_subset is not None:
            self.planes = [p for p in self.planes if p.name in plane_subset]
        self.seqs = enumerate_sequences(len(self.planes), max_depth)
        self.material_mode = material_mode
        self.range_mode = range_mode
        self.fd_step_m, self.fd_step_rad = fd_step_m, fd_step_rad
        self.eta = {p.name: complex_permittivity(p.material, self.freqs, eps_scale, sigma_scale) for p in self.planes}
        self.max_depth = max_depth

    # ---------- channel ----------
    def _tx_field(self, k_dep):
        q = k_dep @ self.AR
        F, _, _, _ = self.base._cartesian_field(0, q, False)          # (m, nf, 3) local
        return F @ self.AR.T

    def _rx_fields(self, k_arr, yaw):
        """Both tag ports (+45, -45) for arrival propagation direction k_arr (m, 3) and antenna yaw (m,)."""
        co, si = np.cos(yaw), np.sin(yaw)
        v = -k_arr
        q = np.column_stack([co * v[:, 0] + si * v[:, 1], -si * v[:, 0] + co * v[:, 1], v[:, 2]])
        out = []
        for ib in range(2):
            F, _, _, _ = self.base._cartesian_field(ib, q, False)
            a = F.copy()
            a[:, :, 0] = co[:, None] * F[:, :, 0] - si[:, None] * F[:, :, 1]
            a[:, :, 1] = si[:, None] * F[:, :, 0] + co[:, None] * F[:, :, 1]
            out.append(a)
        return out

    def _bounce_operator(self, k_in, k_out, plane):
        """(m, nf, 3, 3) Cartesian reflection operator at one bounce."""
        n = np.asarray(plane.normal, float)
        s = np.cross(k_in, n)
        sn = np.linalg.norm(s, axis=1)
        deg = sn < 1e-9
        if deg.any():                                   # normal incidence: any in-plane unit vector
            alt = np.zeros(3)
            alt[(plane.axis + 1) % 3] = 1.0
            s[deg] = alt
            sn[deg] = 1.0
        s = s / sn[:, None]
        p_in = np.cross(s, k_in)
        p_out = np.cross(s, k_out)
        cos_i = np.abs(k_in @ n)
        r_te, r_tm = reflection_coefficients(cos_i, self.eta[plane.name], plane.thickness_m, self.freqs, self.material_mode)
        ss = np.einsum("mi,mj->mij", s, s)
        pp = np.einsum("mi,mj->mij", p_out, p_in)
        return r_te[:, :, None, None] * ss[:, None] + r_tm[:, :, None, None] * pp[:, None]

    def channel(self, states, case, return_paths=False):
        """Modeled H (n, nf, 2) for TX port 0 (+45 LP anchor), RX ports (+45, -45)."""
        x = np.atleast_2d(np.asarray(states, float))
        n = len(x)
        anchor = np.asarray(case["anchor"], float)
        tags = np.column_stack([x[:, 0], x[:, 1], np.full(n, float(case["robot_z_m"]))])
        yaw = x[:, 2] + np.radians(case["mount_deg"])
        H = np.zeros((n, self.nf, 2), complex)
        paths = []
        for seq in self.seqs:
            valid, verts, L = trace_sequence(anchor, tags, seq, self.planes)
            if not valid.any():
                continue
            iv = np.flatnonzero(valid)
            V = verts[iv]
            seg = _unit(np.diff(V, axis=1))                 # (m, k+1, 3) propagation directions
            k_dep, k_arr = seg[:, 0], seg[:, -1]
            T = self._tx_field(k_dep)                       # (m, nf, 3)
            E = T
            for j, pidx in enumerate(seq):
                M = self._bounce_operator(seg[:, j], seg[:, j + 1], self.planes[pidx])
                E = np.einsum("mfij,mfj->mfi", M, E)
            Rp = self._rx_fields(k_arr, yaw[iv])
            Lm = L[iv]
            amp = C0 / self.freqs[None, :] / (4 * np.pi * Lm[:, None]) * np.exp(-2j * np.pi * self.freqs[None, :] * Lm[:, None] / C0)
            for ip in range(2):
                H[iv, :, ip] += np.einsum("mfi,mfi->mf", Rp[ip], E) * amp
            if return_paths:
                paths.append(dict(seq=tuple(self.planes[i].name for i in seq), idx=iv, length=Lm))
        return (H, paths) if return_paths else H

    # ---------- observer ----------
    def _cir(self, H):
        return np.fft.ifft(H * self.window[None, :, None], n=4 * self.nf, axis=1) * self.nf

    def observe(self, H):
        cir = self._cir(H)
        return self.O.first_path_batch(cir, float(self.freqs[1] - self.freqs[0])), cir

    @staticmethod
    def _s_at(cir, idx):
        ii = np.arange(len(cir))
        p = np.abs(cir[ii, idx, :]) ** 2
        return (p[:, 0] - p[:, 1]) / np.maximum(p.sum(axis=1), 1e-300)

    def batch(self, states, case, gradient=True, return_diagnostics=False):
        """Same signature as SourceFFD.batch: pred (n, 2) = [range, s], J (n, 2, 4).

        s-Jacobian: central differences in x, y, yaw at the nominal first-path tap (tap held fixed, like SourceFFD).
        range: geometric (original contract) unless range_mode='fp'.
        """
        x = np.atleast_2d(np.asarray(states, float))
        n = len(x)
        steps = ((0, self.fd_step_m), (1, self.fd_step_m), (2, self.fd_step_rad))
        if gradient:
            # nominal + 6 perturbed states in ONE channel call (vectorised over states)
            stack = [x]
            for col, step in steps:
                xp = x.copy(); xm = x.copy()
                xp[:, col] += step; xm[:, col] -= step
                stack += [xp, xm]
            Hall = self.channel(np.concatenate(stack), case)
            H0 = Hall[:n]
        else:
            H0 = self.channel(x, case)
        obs, cir = self.observe(H0)
        idx = obs["index"]
        s0 = self._s_at(cir, idx)
        anchor = np.asarray(case["anchor"], float)
        d = np.column_stack([x[:, 0] - anchor[0], x[:, 1] - anchor[1], np.full(n, float(case["robot_z_m"]) - anchor[2])])
        dist = np.linalg.norm(d, axis=1)
        r = dist + B_OLD if self.range_mode == "geometric" else obs["range_m"]
        pred = np.column_stack([r, s0])
        J = None
        if gradient:
            J = np.zeros((n, 2, 4))
            J[:, 0, 0] = d[:, 0] / dist
            J[:, 0, 1] = d[:, 1] / dist
            for j, (col, step) in enumerate(steps):
                Hp = Hall[(1 + 2 * j) * n:(2 + 2 * j) * n]
                Hm = Hall[(2 + 2 * j) * n:(3 + 2 * j) * n]
                sp = self._s_at(self._cir(Hp), idx)
                sm = self._s_at(self._cir(Hm), idx)
                J[:, 1, col] = (sp - sm) / (2 * step)
            if not np.isfinite(J).all():
                raise RuntimeError("NONFINITE_REFLECTIVE_JACOBIAN")
        if return_diagnostics:
            return pred, J, dict(tap=idx, fp_range=obs["range_m"], s_detector=obs["s"])
        return pred, J

    def model(self, state, case):
        h, H = self.batch(np.asarray(state)[None, :], case, gradient=True)
        return h[0], H[0]
