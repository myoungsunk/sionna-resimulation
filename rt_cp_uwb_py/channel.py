from __future__ import annotations

import numpy as np

from .core import C0, Antenna, Material, PathRecord, fresnel_reflection, jones_reflection, normalize, transverse_basis


def circular_basis_matrix(convention: str = "IEEE-RHCP", circular_order: str = "RL") -> np.ndarray:
    if convention.upper() != "IEEE-RHCP":
        raise ValueError(f"unsupported circular convention: {convention}")
    left = np.array([1.0, 1j], dtype=np.complex128) / np.sqrt(2.0)
    right = np.array([1.0, -1j], dtype=np.complex128) / np.sqrt(2.0)
    if circular_order.upper() == "LR":
        return np.column_stack([left, right])
    if circular_order.upper() == "RL":
        return np.column_stack([right, left])
    raise ValueError(f"unsupported circular order: {circular_order}")


def convert_basis(H: np.ndarray, src: str, dst: str, convention: str = "IEEE-RHCP", circular_order: str = "RL") -> np.ndarray:
    src = src.lower()
    dst = dst.lower()
    arr = orient_tensor(H, H.shape[-1] if H.ndim == 3 else H.shape[0])
    if src == dst:
        return arr
    if {src, dst} != {"linear", "circular"}:
        raise ValueError(f"unsupported basis conversion: {src}->{dst}")
    U = circular_basis_matrix(convention, circular_order)
    # Internal tensor convention here is Nr x Nt x Nf.
    out = np.zeros_like(arr, dtype=np.complex128)
    for k in range(arr.shape[2]):
        if src == "linear":
            out[:, :, k] = U.conj().T @ arr[:, :, k] @ U
        else:
            out[:, :, k] = U @ arr[:, :, k] @ U.conj().T
    return out


def _basis_change(src_basis: np.ndarray, dst_basis: np.ndarray) -> np.ndarray:
    return np.asarray(dst_basis, dtype=np.complex128).conj().T @ np.asarray(src_basis, dtype=np.complex128)


def _rotation_angle_2d(matrix: np.ndarray) -> float:
    real = np.real(np.asarray(matrix, dtype=np.complex128))
    if not np.all(np.isfinite(real)):
        return float("nan")
    return float(np.arctan2(real[1, 0], real[0, 0]))


def _material_field_or_nan(material: Material, field_name: str) -> float:
    raw = getattr(material, field_name, None)
    if raw is None:
        return float("nan")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float("nan")


def _depol_path_label(material: Material, offdiag_max: float) -> str:
    has_material_xpol = np.isfinite(_material_field_or_nan(material, "xpol_coupling_db"))
    has_directional_xpol = np.isfinite(_material_field_or_nan(material, "xpol_coupling_hv_db")) or np.isfinite(
        _material_field_or_nan(material, "xpol_coupling_vh_db")
    )
    if offdiag_max > 1.0e-12 and (has_material_xpol or has_directional_xpol):
        return "material_xpol_coupling"
    if offdiag_max > 1.0e-12:
        return "offdiag_jones_unknown_source"
    return "specular_fresnel_only"


def _basis_orthogonality_error(
    s_in: np.ndarray,
    p_in: np.ndarray,
    k_in: np.ndarray,
    s_out: np.ndarray,
    p_out: np.ndarray,
    k_out: np.ndarray,
) -> float:
    bin_ = np.column_stack([s_in, p_in, -normalize(k_in)])
    bout = np.column_stack([s_out, p_out, normalize(k_out)])
    err = np.max(np.abs(bin_.T @ bin_ - np.eye(3)))
    return float(max(err, np.max(np.abs(bout.T @ bout - np.eye(3)))))


def _fallback_tangent_from_normal(normal: np.ndarray) -> np.ndarray:
    n = normalize(normal)
    alt = np.array([0.0, 0.0, 1.0]) if abs(float(n[2])) < 0.8 else np.array([0.0, 1.0, 0.0])
    t = np.cross(n, alt)
    if np.linalg.norm(t) < 1e-9:
        t = np.cross(n, np.array([1.0, 0.0, 0.0]))
    return normalize(t)


def _local_sp_bases(k_in: np.ndarray, k_out: np.ndarray, normal: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, float]:
    kin = normalize(k_in)
    kout = normalize(k_out)
    n = normalize(normal)
    dot_in = float(np.dot(kin, n))
    dot_out = float(np.dot(kout, n))
    if dot_in > 0.0 or (abs(dot_in) <= 1e-12 and dot_out > 0.0):
        n = -n
    cos_i = float(np.clip(-np.dot(kin, n), 0.0, 1.0))
    theta_i = float(np.arccos(cos_i))
    s_in_raw = np.cross(kin, n)
    s_out_raw = np.cross(kout, n)
    n_in = float(np.linalg.norm(s_in_raw))
    n_out = float(np.linalg.norm(s_out_raw))
    if n_in < 1e-9 and n_out < 1e-9:
        s_in = _fallback_tangent_from_normal(n)
        s_out = s_in
    elif n_in < 1e-9:
        s_out = normalize(s_out_raw)
        s_in = s_out
    elif n_out < 1e-9:
        s_in = normalize(s_in_raw)
        s_out = s_in
    else:
        s_in = normalize(s_in_raw)
        s_out = normalize(s_out_raw)
        if float(np.dot(s_in, s_out)) < 0.0:
            s_out = -s_out
    p_in = normalize(np.cross(kin, s_in))
    p_out = normalize(np.cross(kout, s_out))
    return s_in, p_in, s_out, p_out, theta_i


def _transport_wave_basis(k_out: np.ndarray, prev_basis: np.ndarray, up_hint: np.ndarray) -> np.ndarray:
    k = normalize(k_out)
    u_prev = np.real(prev_basis[:, 0])
    v_prev = np.real(prev_basis[:, 1])
    u = u_prev - float(np.dot(u_prev, k)) * k
    if np.linalg.norm(u) < 1e-9:
        u = v_prev - float(np.dot(v_prev, k)) * k
    if np.linalg.norm(u) < 1e-9:
        u_alt, v_alt = transverse_basis(k, up_hint)
        return np.column_stack([u_alt, v_alt]).astype(np.complex128)
    u = normalize(u)
    v = normalize(np.cross(k, u))
    return np.column_stack([u, v]).astype(np.complex128)


def path_jones_debug(path: PathRecord, freqs_hz: np.ndarray, up_hint: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, dict]:
    freqs = np.asarray(freqs_hz, dtype=float)
    up = np.array([0.0, 0.0, 1.0]) if up_hint is None else np.asarray(up_hint, dtype=float).reshape(3)
    R = np.zeros((2, 2, len(freqs)), dtype=np.complex128)
    R[0, 0, :] = 1.0
    R[1, 1, :] = 1.0
    points = [np.asarray(p, dtype=float).reshape(3) for p in path.points]
    wave_basis = None
    debug: dict = {
        "bounce_count": int(path.bounce_count),
        "path_length_m": float(path.path_length_m),
        "delay_s": float(path.delay_s),
        "n_freq": int(len(freqs)),
        "bounces": [],
    }
    if path.bounce_count > 0:
        u0, v0 = transverse_basis(points[1] - points[0], up)
        wave_basis = np.column_stack([u0, v0]).astype(np.complex128)
        debug["initial_wave_basis"] = wave_basis
    else:
        debug["initial_wave_basis"] = np.eye(3, 2, dtype=np.complex128)
    for idx in range(path.bounce_count):
        k_in = points[idx + 1] - points[idx]
        k_out = points[idx + 2] - points[idx + 1]
        w_in = wave_basis
        s_in, p_in, s_out, p_out, theta_i = _local_sp_bases(k_in, k_out, path.normals[idx])
        local_in = np.column_stack([s_in, p_in]).astype(np.complex128)
        local_out = np.column_stack([s_out, p_out]).astype(np.complex128)
        in_rot = _basis_change(w_in, local_in)
        wave_basis = _transport_wave_basis(k_out, wave_basis, up)
        out_rot = _basis_change(local_out, wave_basis)
        refl = jones_reflection(path.materials[idx], theta_i, freqs)
        gamma_s, gamma_p = fresnel_reflection(path.materials[idx], theta_i, freqs)
        offdiag_max = float(max(np.max(np.abs(refl[0, 1, :])), np.max(np.abs(refl[1, 0, :]))))
        bounce_debug = {
            "bounce_idx": idx + 1,
            "incident_k": normalize(k_in),
            "reflected_k": normalize(k_out),
            "surface_normal": normalize(path.normals[idx]),
            "s_hat": s_in,
            "p_hat_inc": p_in,
            "p_hat_ref": p_out,
            "wave_basis_in": w_in,
            "wave_basis_out": wave_basis,
            "local_basis_in": local_in,
            "local_basis_out": local_out,
            "in_rotation": in_rot,
            "out_rotation": out_rot,
            "psi_in_rad": _rotation_angle_2d(in_rot),
            "psi_out_rad": _rotation_angle_2d(out_rot),
            "theta_i_rad": float(theta_i),
            "theta_fresnel_eff_rad": float(theta_i),
            "Gamma_s": gamma_s,
            "Gamma_p": gamma_p,
            "J_local_sp": refl,
            "J_local_sp_offdiag_max_abs": offdiag_max,
            "xpol_coupling_db": _material_field_or_nan(path.materials[idx], "xpol_coupling_db"),
            "xpol_coupling_phase_deg": _material_field_or_nan(path.materials[idx], "xpol_coupling_phase_deg"),
            "xpol_coupling_hv_db": _material_field_or_nan(path.materials[idx], "xpol_coupling_hv_db"),
            "xpol_coupling_vh_db": _material_field_or_nan(path.materials[idx], "xpol_coupling_vh_db"),
            "depol_path": _depol_path_label(path.materials[idx], offdiag_max),
            "basis_determinant": float(np.linalg.det(np.column_stack([s_in, p_in, -normalize(k_in)]))),
            "basis_orthogonality_error": _basis_orthogonality_error(s_in, p_in, k_in, s_out, p_out, k_out),
            "J_world": np.zeros((2, 2, len(freqs)), dtype=np.complex128),
            "J_chain_after_bounce": np.zeros((2, 2, len(freqs)), dtype=np.complex128),
        }
        bounce_debug["psi_in_deg"] = float(np.rad2deg(bounce_debug["psi_in_rad"]))
        bounce_debug["psi_out_deg"] = float(np.rad2deg(bounce_debug["psi_out_rad"]))
        bounce_debug["theta_i_deg"] = float(np.rad2deg(theta_i))
        bounce_debug["theta_fresnel_eff_deg"] = float(np.rad2deg(theta_i))
        for k in range(len(freqs)):
            event = out_rot @ refl[:, :, k] @ in_rot
            R[:, :, k] = event @ R[:, :, k]
            bounce_debug["J_world"][:, :, k] = event
            bounce_debug["J_chain_after_bounce"][:, :, k] = R[:, :, k]
        debug["bounces"].append(bounce_debug)
    if path.bounce_count > 0:
        u_final, v_final = transverse_basis(points[-1] - points[-2], up)
        final_basis = np.column_stack([u_final, v_final]).astype(np.complex128)
        final_rot = _basis_change(wave_basis, final_basis)
        for k in range(len(freqs)):
            R[:, :, k] = final_rot @ R[:, :, k]
        debug["final_wave_basis_before_canonical"] = wave_basis
        debug["final_canonical_basis"] = final_basis
        debug["final_basis_transport_to_canonical"] = final_rot
    else:
        debug["final_wave_basis_before_canonical"] = debug["initial_wave_basis"]
        debug["final_canonical_basis"] = debug["initial_wave_basis"]
        debug["final_basis_transport_to_canonical"] = np.eye(2, dtype=np.complex128)
    scalar = (C0 / np.maximum(freqs, 1.0)) / (4.0 * np.pi * max(path.path_length_m, 1e-12))
    scalar = scalar.astype(np.complex128)
    debug["final_jones_f"] = R
    debug["scalar_factor_f"] = scalar
    return R, scalar, debug


def path_jones_response(path: PathRecord, freqs_hz: np.ndarray, up_hint: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    R, scalar, _ = path_jones_debug(path, freqs_hz, up_hint)
    return R, scalar


def build_channel(
    paths: list[PathRecord],
    tx_ant: Antenna,
    rx_ant: Antenna,
    freqs_hz: np.ndarray,
    eval_basis: str = "",
    convention: str = "IEEE-RHCP",
    circular_order: str = "RL",
) -> np.ndarray:
    freqs = np.asarray(freqs_hz, dtype=float).reshape(-1)
    H = np.zeros((rx_ant.port_count, tx_ant.port_count, len(freqs)), dtype=np.complex128)
    for path in paths:
        if path.jones_f is not None and path.scalar_factor_f is not None:
            R, scalar = path.jones_f, path.scalar_factor_f
        else:
            R, scalar = path_jones_response(path, freqs)
        g_tx = tx_ant.tx_port_to_wave(path.launch_dir, freqs)
        g_rx = rx_ant.rx_wave_to_port(path.arrival_dir, freqs)
        gain = np.sqrt(tx_ant.directional_gain_linear_f(path.launch_dir, freqs, tx=True) * rx_ant.directional_gain_linear_f(path.arrival_dir, freqs, tx=False))
        for k, f_hz in enumerate(freqs):
            core = g_rx[:, :, k] @ R[:, :, k] @ (scalar[k] * gain[k] * g_tx[:, :, k])
            H[:, :, k] += core * np.exp(-1j * 2.0 * np.pi * f_hz * path.delay_s)
    if eval_basis:
        current = "circular" if tx_ant.basis.lower() == rx_ant.basis.lower() == "circular" else "linear"
        if current != eval_basis.lower():
            H = convert_basis(H, current, eval_basis, convention, circular_order)
    return H


def build_channel_with_debug(
    paths: list[PathRecord],
    tx_ant: Antenna,
    rx_ant: Antenna,
    freqs_hz: np.ndarray,
    eval_basis: str = "",
    convention: str = "IEEE-RHCP",
    circular_order: str = "RL",
) -> tuple[np.ndarray, dict]:
    freqs = np.asarray(freqs_hz, dtype=float).reshape(-1)
    H = np.zeros((rx_ant.port_count, tx_ant.port_count, len(freqs)), dtype=np.complex128)
    path_debugs = []
    for path_idx, path in enumerate(paths, start=1):
        R, scalar, pdebug = path_jones_debug(path, freqs)
        g_tx = tx_ant.tx_port_to_wave(path.launch_dir, freqs)
        g_rx = rx_ant.rx_wave_to_port(path.arrival_dir, freqs)
        gain = np.sqrt(tx_ant.directional_gain_linear_f(path.launch_dir, freqs, tx=True) * rx_ant.directional_gain_linear_f(path.arrival_dir, freqs, tx=False))
        H_path = np.zeros_like(H)
        for k, f_hz in enumerate(freqs):
            core = g_rx[:, :, k] @ R[:, :, k] @ (scalar[k] * gain[k] * g_tx[:, :, k])
            H_path[:, :, k] = core * np.exp(-1j * 2.0 * np.pi * f_hz * path.delay_s)
            H[:, :, k] += H_path[:, :, k]
        pdebug.update(
            {
                "path_idx": path_idx,
                "surface_ids": tuple(path.surface_ids),
                "surface_names": tuple(path.surface_names),
                "launch_dir": path.launch_dir,
                "arrival_dir": path.arrival_dir,
                "g_tx": g_tx,
                "g_rx": g_rx,
                "scalar_gain": scalar * gain,
                "H_path": H_path,
            }
        )
        path_debugs.append(pdebug)
    if eval_basis:
        current = "circular" if tx_ant.basis.lower() == rx_ant.basis.lower() == "circular" else "linear"
        if current != eval_basis.lower():
            H = convert_basis(H, current, eval_basis, convention, circular_order)
    return H, {"paths": path_debugs, "n_freq": int(len(freqs)), "freqs_hz": freqs}


def _window_vector(name: str, n: int) -> np.ndarray:
    mode = str(name).lower()
    if mode in {"hann", "hanning"}:
        if n == 1:
            return np.ones(1)
        idx = np.arange(n, dtype=float)
        return 0.5 - 0.5 * np.cos(2.0 * np.pi * idx / (n - 1))
    if mode in {"rect", "rectangular", "none"}:
        return np.ones(n)
    if mode == "blackman":
        if n == 1:
            return np.ones(1)
        idx = np.arange(n, dtype=float)
        return 0.42 - 0.5 * np.cos(2.0 * np.pi * idx / (n - 1)) + 0.08 * np.cos(4.0 * np.pi * idx / (n - 1))
    raise ValueError(f"unsupported window_type: {name}")


def ifft_to_cir(H_f: np.ndarray, freqs_hz: np.ndarray, window_type: str = "hann") -> tuple[np.ndarray, np.ndarray]:
    freqs = np.asarray(freqs_hz, dtype=float).reshape(-1)
    if len(freqs) < 2:
        raise ValueError("ifft_to_cir requires at least two frequency points")
    df = float(freqs[1] - freqs[0])
    if not np.all(np.abs(np.diff(freqs) - df) < 1e-3):
        raise ValueError("frequencies must be uniform")
    H = np.asarray(H_f, dtype=np.complex128)
    freq_dim = detect_frequency_dim(H, len(freqs))
    H_perm = np.moveaxis(H, freq_dim, -1)
    shape = H_perm.shape
    n_pad = 4 * len(freqs)
    flat = H_perm.reshape(-1, len(freqs))
    win = _window_vector(window_type, len(freqs))
    padded = np.zeros((flat.shape[0], n_pad), dtype=np.complex128)
    padded[:, : len(freqs)] = flat * win[None, :]
    h_flat = np.fft.ifft(padded, axis=1) * len(freqs)
    h_perm = h_flat.reshape(*shape[:-1], n_pad)
    h_t = np.moveaxis(h_perm, -1, freq_dim)
    t_axis = np.arange(n_pad, dtype=float) / (n_pad * df)
    return h_t, t_axis


def detect_frequency_dim(arr: np.ndarray, n_freq: int) -> int:
    matches = [i for i, size in enumerate(arr.shape) if size == n_freq]
    if not matches:
        raise ValueError("no array dimension matches numel(freqs)")
    if arr.ndim == 1:
        return 0
    return matches[-1]


def orient_tensor(H_f: np.ndarray, n_freq: int) -> np.ndarray:
    H = np.asarray(H_f, dtype=np.complex128)
    if H.ndim == 1:
        return H.reshape(1, 1, -1)
    freq_dim = detect_frequency_dim(H, n_freq)
    H = np.moveaxis(H, freq_dim, -1)
    if H.ndim == 2:
        H = H.reshape(H.shape[0], 1, H.shape[1])
    return H
