from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

C0 = 299_792_458.0
EPS0 = 8.8541878128e-12


def normalize(vec: np.ndarray) -> np.ndarray:
    arr = np.asarray(vec, dtype=float).reshape(3)
    n = float(np.linalg.norm(arr))
    if n <= 0.0:
        raise ValueError("zero-length vector")
    return arr / n


def transverse_basis(direction: np.ndarray, up_hint: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    k = normalize(direction)
    up = normalize(np.array([0.0, 0.0, 1.0]) if up_hint is None else up_hint)
    u = up - float(np.dot(up, k)) * k
    if np.linalg.norm(u) < 1e-9:
        alt = np.array([1.0, 0.0, 0.0])
        u = alt - float(np.dot(alt, k)) * k
    u = normalize(u)
    v = normalize(np.cross(k, u))
    return u, v


@dataclass(frozen=True)
class Material:
    name: str = "material"
    kind: str = "dielectric"
    eps_r: float = 4.0
    tan_delta: float = 0.0
    conductivity_s_m: float = 0.0
    pec_tm_sign: float = -1.0
    xpol_coupling_db: float = 35.0
    xpol_coupling_phase_deg: float = 0.0
    xpol_coupling_hv_db: float | None = None
    xpol_coupling_hv_phase_deg: float | None = None
    xpol_coupling_vh_db: float | None = None
    xpol_coupling_vh_phase_deg: float | None = None

    def __post_init__(self) -> None:
        if self.kind.lower() == "pec" and float(self.pec_tm_sign) != -1.0:
            raise ValueError("PEC TM sign must be -1.0 (IEEE convention)")

    def eps_r_at(self, freqs_hz: np.ndarray) -> np.ndarray:
        return np.full(np.asarray(freqs_hz, dtype=float).shape, float(self.eps_r), dtype=float)

    def sigma_at(self, freqs_hz: np.ndarray) -> np.ndarray:
        freqs = np.asarray(freqs_hz, dtype=float)
        if self.conductivity_s_m:
            return np.full(freqs.shape, float(self.conductivity_s_m), dtype=float)
        return 2.0 * np.pi * np.maximum(freqs, 1.0) * EPS0 * float(self.eps_r) * float(self.tan_delta)


@dataclass(frozen=True)
class Surface:
    surface_id: int
    name: str
    point: np.ndarray
    normal: np.ndarray
    u_axis: np.ndarray
    v_axis: np.ndarray
    half_u: float
    half_v: float
    material: Material = field(default_factory=Material)

    def __post_init__(self) -> None:
        n = normalize(self.normal)
        u = np.asarray(self.u_axis, dtype=float).reshape(3)
        u = normalize(u - float(np.dot(u, n)) * n)
        v = np.asarray(self.v_axis, dtype=float).reshape(3)
        v = normalize(v - float(np.dot(v, n)) * n - float(np.dot(v, u)) * u)
        object.__setattr__(self, "point", np.asarray(self.point, dtype=float).reshape(3))
        object.__setattr__(self, "normal", n)
        object.__setattr__(self, "u_axis", u)
        object.__setattr__(self, "v_axis", v)

    def contains_point(self, point: np.ndarray, eps: float = 1e-7) -> bool:
        d = np.asarray(point, dtype=float).reshape(3) - self.point
        u = float(np.dot(d, self.u_axis))
        v = float(np.dot(d, self.v_axis))
        return abs(u) <= self.half_u + eps and abs(v) <= self.half_v + eps


@dataclass(frozen=True)
class Scene:
    surfaces: tuple[Surface, ...] = ()


@dataclass(frozen=True)
class PathRecord:
    points: tuple[np.ndarray, ...]
    surface_ids: tuple[int, ...]
    surface_names: tuple[str, ...]
    materials: tuple[Material, ...]
    bounce_count: int
    path_length_m: float
    delay_s: float
    launch_dir: np.ndarray
    arrival_dir: np.ndarray
    incidence_angles_rad: tuple[float, ...]
    normals: tuple[np.ndarray, ...]
    blocked: bool = False
    valid: bool = True
    jones_f: np.ndarray | None = None
    scalar_factor_f: np.ndarray | None = None


@dataclass
class Antenna:
    position: np.ndarray
    boresight: np.ndarray
    h_axis: np.ndarray
    v_axis: np.ndarray
    basis: str = "circular"
    convention: str = "IEEE-RHCP"
    circular_order: str = "RL"
    tx_peak_gain_dbi: float = 0.0
    rx_peak_gain_dbi: float = 0.0
    pattern_data: dict[str, Any] = field(default_factory=dict)
    use_ffd: bool = False
    ffd_port_r: dict[str, Any] | None = None
    ffd_port_l: dict[str, Any] | None = None
    ffd_local_to_world: np.ndarray | None = None
    global_up: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 1.0]))

    def __post_init__(self) -> None:
        b = normalize(self.boresight)
        h = np.asarray(self.h_axis, dtype=float).reshape(3)
        h = normalize(h - float(np.dot(h, b)) * b)
        v = np.asarray(self.v_axis, dtype=float).reshape(3)
        v = normalize(v - float(np.dot(v, b)) * b - float(np.dot(v, h)) * h)
        self.position = np.asarray(self.position, dtype=float).reshape(3)
        self.boresight = b
        self.h_axis = h
        self.v_axis = v
        if self.ffd_local_to_world is None:
            self.ffd_local_to_world = np.column_stack([h, v, b])
        else:
            self.ffd_local_to_world = np.asarray(self.ffd_local_to_world, dtype=float).reshape(3, 3)
        self.global_up = normalize(self.global_up)

    @property
    def port_count(self) -> int:
        return 2

    def wave_basis(self, direction: np.ndarray) -> np.ndarray:
        u, v = transverse_basis(direction, self.global_up)
        return np.column_stack([u, v]).astype(np.complex128)

    def port_basis_vectors(self, direction: np.ndarray) -> np.ndarray:
        k = normalize(direction)
        h = self.h_axis - float(np.dot(self.h_axis, k)) * k
        if np.linalg.norm(h) < 1e-9:
            h = self.v_axis - float(np.dot(self.v_axis, k)) * k
        h = normalize(h)
        v = self.v_axis - float(np.dot(self.v_axis, k)) * k - float(np.dot(self.v_axis, h)) * h
        if np.linalg.norm(v) < 1e-9:
            v = np.cross(k, h)
        v = normalize(v)
        if self.basis.lower() == "linear":
            return np.column_stack([h, v]).astype(np.complex128)
        right = (h - 1j * v) / np.sqrt(2.0)
        left = (h + 1j * v) / np.sqrt(2.0)
        if self.circular_order.upper() == "LR":
            return np.column_stack([left, right]).astype(np.complex128)
        return np.column_stack([right, left]).astype(np.complex128)

    def tx_port_to_wave(self, direction: np.ndarray, freqs_hz: np.ndarray) -> np.ndarray:
        W = self.wave_basis(direction)
        if self.use_ffd:
            fields = self.ffd_port_vectors_world(direction, freqs_hz)
            out = np.zeros((2, self.port_count, len(freqs_hz)), dtype=np.complex128)
            for k in range(len(freqs_hz)):
                out[:, :, k] = W.conj().T @ fields[:, :, k]
            return out
        P = self.port_basis_vectors(direction)
        base = W.conj().T @ P
        return np.repeat(base[:, :, None], len(freqs_hz), axis=2)

    def rx_wave_to_port(self, arrival_dir: np.ndarray, freqs_hz: np.ndarray) -> np.ndarray:
        look_dir = -normalize(arrival_dir)
        W = self.wave_basis(arrival_dir)
        if self.use_ffd:
            fields = self.ffd_port_vectors_world(look_dir, freqs_hz)
            out = np.zeros((self.port_count, 2, len(freqs_hz)), dtype=np.complex128)
            for k in range(len(freqs_hz)):
                out[:, :, k] = fields[:, :, k].T @ W
            return out
        P = self.port_basis_vectors(look_dir)
        # P-7 (2026-08-07): 켤레를 쓰지 않는다. 상호성에 따른 수신 응답은 유효길이와의
        # **비켤레** 내적(V_oc ∝ h_eff·E)이며, 켤레는 편파 *효율*(전력량) 계산에만 든다.
        # 바로 위 FFD 분기가 이미 `fields.T @ W` 로 켤레 없이 계산한다 — 같은 함수의
        # 두 분기가 달랐던 것이 원인이다. 실수 기저(LP)에서는 무해하나 원편파에서는
        # (h−jv) → (h+jv) 로 **손잡이가 뒤집힌다**.
        # 근거: 비대칭 앵커 R–R/R–L/L–L 이 수정 후에만 co/cross 와 일치(사전등록 §2 V3),
        #       홀수 반사 손잡이 반전이 수정 후에만 관측(V4), LP3/L2B 는 불변(V5).
        base = P.T @ W
        return np.repeat(base[:, :, None], len(freqs_hz), axis=2)

    def directional_gain_linear_f(self, direction: np.ndarray, freqs_hz: np.ndarray, tx: bool = True) -> np.ndarray:
        if self.use_ffd:
            return np.ones(len(freqs_hz), dtype=float)
        dbi = self.tx_peak_gain_dbi if tx else self.rx_peak_gain_dbi
        return np.full(len(freqs_hz), 10.0 ** (dbi / 10.0), dtype=float)

    def ffd_port_vectors_world(self, direction: np.ndarray, freqs_hz: np.ndarray) -> np.ndarray:
        from .antennas import interpolate_ffd_field

        if self.ffd_port_r is None or self.ffd_port_l is None:
            raise ValueError("FFD antenna requires both RHCP and LHCP port patterns")
        dirs = np.asarray(direction, dtype=float).reshape(3)
        local_dir = self.ffd_local_to_world.T @ normalize(dirs)
        x, y, z = local_dir
        theta = float(np.arccos(np.clip(z, -1.0, 1.0)))
        phi = float(np.mod(np.arctan2(y, x), 2.0 * np.pi))
        r_field_local = interpolate_ffd_field(self.ffd_port_r, theta, phi, freqs_hz)
        l_field_local = interpolate_ffd_field(self.ffd_port_l, theta, phi, freqs_hz)
        fields = np.stack([r_field_local, l_field_local], axis=1)
        return np.einsum("ij,jpk->ipk", self.ffd_local_to_world, fields)


def make_ideal_cp_antenna(position, boresight, h_axis=None, handedness: str = "R") -> Antenna:
    b = normalize(boresight)
    h = np.array([1.0, 0.0, 0.0]) if h_axis is None else np.asarray(h_axis, dtype=float)
    if abs(float(np.dot(normalize(h), b))) > 0.95:
        h = np.array([0.0, 1.0, 0.0])
    v = np.cross(b, h)
    order = "RL" if handedness.upper().startswith("R") else "LR"
    return Antenna(position=np.asarray(position), boresight=b, h_axis=h, v_axis=v, basis="circular", circular_order=order)


def make_ideal_lp_antenna(position, boresight, h_axis=None) -> Antenna:
    b = normalize(boresight)
    h = np.array([1.0, 0.0, 0.0]) if h_axis is None else np.asarray(h_axis, dtype=float)
    if abs(float(np.dot(normalize(h), b))) > 0.95:
        h = np.array([0.0, 1.0, 0.0])
    v = np.cross(b, h)
    return Antenna(position=np.asarray(position), boresight=b, h_axis=h, v_axis=v, basis="linear")


def fresnel_reflection(material: Material, theta_i: float, freqs_hz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    freqs = np.asarray(freqs_hz, dtype=float)
    if material.kind.lower() == "pec":
        # KNOWN DEFECT (recorded 2026-07-30, not fixed here -- see below).
        #
        # With the shipped materials_library()["metal_pec"], pec_tm_sign = -1.0,
        # so this returns diag(-1, -1). In this pipeline that operator PRESERVES
        # circular handedness, which is wrong for a perfect conductor: verified
        # end-to-end in scripts/r1c_pec_handedness_anchored.py, where an
        # isolated PEC bounce gives XPR_refl = +10.03 / +14.94 dB (same-handed
        # port dominant) instead of the required negative value.
        #
        # jones_reflection() does NOT use this path for PEC -- it has its own
        # branch that sets diag(-1, +1), which is the handedness-flipping
        # operator here. So the CP channel is correct today, and this defect is
        # latent: it only bites a caller that consumes fresnel_reflection()
        # directly for a PEC material.
        #
        # Not fixed in place because pec_tm_sign is a declared material property
        # that other code paths (LP/dielectric flows, designed_stress scenes)
        # may already be calibrated against; flipping it here would silently
        # change those. Fixing it properly means auditing every pec_tm_sign
        # consumer, which is out of scope for the CP gap analysis.
        gamma_s = -np.ones(freqs.shape, dtype=np.complex128)
        gamma_p = (1.0 if float(material.pec_tm_sign) >= 0.0 else -1.0) * np.ones(freqs.shape, dtype=np.complex128)
        return gamma_s, gamma_p
    omega = 2.0 * np.pi * np.maximum(freqs, 1.0)
    eps_c = material.eps_r_at(freqs) - 1j * material.sigma_at(freqs) / (omega * EPS0)
    sin2 = float(np.sin(theta_i) ** 2)
    cos_theta = float(np.cos(theta_i))
    root = np.sqrt(eps_c - sin2)
    root = np.where(np.real(root) < 0.0, -root, root)
    gamma_te = (cos_theta - root) / (cos_theta + root)
    gamma_tm = (eps_c * cos_theta - root) / (eps_c * cos_theta + root)
    return gamma_te.astype(np.complex128), gamma_tm.astype(np.complex128)


def jones_reflection(material: Material, theta_i: float, freqs_hz: np.ndarray) -> np.ndarray:
    gamma_te, gamma_tm = fresnel_reflection(material, theta_i, freqs_hz)
    out = np.zeros((2, 2, len(freqs_hz)), dtype=np.complex128)

    if material.kind.lower() == "pec":
        # PEC in the TE/TM basis: diag(-1, +1). A perfect conductor reverses
        # circular handedness, and this is the operator that does so HERE.
        #
        # Do NOT "simplify" this to the fresnel_reflection() return value.
        # fresnel_reflection() has its own PEC branch (core.py:243-246) that
        # returns diag(-1, -1) because Material.pec_tm_sign = -1.0. That is a
        # handedness-PRESERVING operator in this pipeline, i.e. wrong for a PEC.
        #
        # Settled by an anchored end-to-end test,
        # scripts/r1c_pec_handedness_anchored.py, which uses the pipeline's own
        # FFD antennas and resolved branch convention and validates the
        # convention on the direct path first (two identical CP antennas facing
        # each other must be co-polarised -> XPR_direct > 0):
        #
        #   candidate        XPR_direct   XPR_refl(c61)  XPR_refl(c7)   verdict
        #   fresnel_asis        +15.45        +10.03        +14.94      preserves
        #   diag(-1,+1)         +15.45        -10.11        -14.93      FLIPS  <-
        #   orig scale=0.5      +15.45         -4.24         -0.84      partial
        #
        # An earlier test (r1b) reached the opposite conclusion because it used
        # ideal antennas with the FFD branch convention; the two conventions
        # swap which RX port is labelled "same" (features.py:232-233), which
        # inverts the reported XPR sign. r1b is superseded by r1c.
        out[0, 0, :] = -1.0
        out[1, 1, :] = +1.0
        # Off-diagonals remain 0: an ideal flat PEC has no TE/TM cross-coupling.
    else:
        out[0, 0, :] = gamma_te
        out[1, 1, :] = gamma_tm
        xdb_hv = material.xpol_coupling_hv_db
        xdb_vh = material.xpol_coupling_vh_db
        xph = float(material.xpol_coupling_phase_deg)
        xph_hv = xph if material.xpol_coupling_hv_phase_deg is None else float(material.xpol_coupling_hv_phase_deg)
        xph_vh = -xph if material.xpol_coupling_vh_phase_deg is None else float(material.xpol_coupling_vh_phase_deg)
        if xdb_hv is None and xdb_vh is None and np.isfinite(float(material.xpol_coupling_db)):
            xdb_hv = float(material.xpol_coupling_db)
            xdb_vh = float(material.xpol_coupling_db)
        elif xdb_hv is None and xdb_vh is not None:
            xdb_hv = xdb_vh
            xph_hv = -xph_vh
        elif xdb_vh is None and xdb_hv is not None:
            xdb_vh = xdb_hv
            xph_vh = -xph_hv
        if xdb_hv is not None and xdb_vh is not None and np.isfinite(float(xdb_hv)) and np.isfinite(float(xdb_vh)):
            diag_scale = np.sqrt(np.maximum(np.abs(gamma_te * gamma_tm), 0.0))
            out[0, 1, :] = (10.0 ** (-float(xdb_hv) / 20.0)) * diag_scale * np.exp(1j * np.deg2rad(xph_hv))
            out[1, 0, :] = (10.0 ** (-float(xdb_vh) / 20.0)) * diag_scale * np.exp(1j * np.deg2rad(xph_vh))
    return out
