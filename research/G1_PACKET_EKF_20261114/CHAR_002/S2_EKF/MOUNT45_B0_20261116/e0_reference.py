"""Independent E0 arithmetic and shadow-gate replay for frozen packets.

`reference(model, case, packet)` takes the original observer model, its SPEC
mapping, and an online packet mapping.  It does not call the native online
filter implementation.  Model observations/Jacobians still come from the
original `model.batch` implementation by design.
"""

from __future__ import annotations

import math
from typing import Mapping

import numpy as np


GATE = 9.210340371976184


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def _sinc_half(angle: float) -> tuple[float, float]:
    """Return sin(angle/2)/(angle/2) and its derivative w.r.t. angle."""
    if abs(angle) < 1e-4:
        a2 = angle * angle
        return (1.0 - a2 / 24.0 + a2 * a2 / 1920.0 - a2**3 / 322560.0,
                -angle / 12.0 + angle**3 / 480.0 - angle**5 / 53760.0)
    half = angle / 2.0
    return math.sin(half) / half, (half * math.cos(half) - math.sin(half)) / (2.0 * half * half)


def _predict(x: np.ndarray, P: np.ndarray, ds: float, gyro_angle: float,
             dt: float) -> tuple[np.ndarray, np.ndarray]:
    """Native four-state motion and process-noise model, independently coded."""
    bias = float(x[3])
    angle = gyro_angle - bias * dt
    sinc, dsinc = _sinc_half(angle)
    middle = float(x[2]) + angle / 2.0
    direction = np.array([math.cos(middle), math.sin(middle)])
    direction_perp = np.array([-direction[1], direction[0]])
    displacement = ds * sinc * direction
    derivative = ds * (dsinc * direction + sinc * direction_perp / 2.0)

    out = x.copy()
    out[:2] += displacement
    out[2] = _wrap(float(x[2]) + angle)

    F = np.eye(4)
    F[:2, 2] = (-displacement[1], displacement[0])
    F[:2, 3] = -dt * derivative
    F[2, 3] = -dt
    G = np.zeros((4, 3))
    G[:2, 0] = sinc * direction
    G[:2, 1] = derivative
    G[2, 1] = 1.0
    G[3, 2] = 1.0
    Q = np.diag([2e-5 * abs(ds), math.radians(0.015) ** 2 * dt, 0.0])
    covariance = F @ P @ F.T + G @ Q @ G.T
    return out, (covariance + covariance.T) * 0.5


def _predict_packet(x: np.ndarray, P: np.ndarray, k: int,
                    packet: Mapping[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    if k == 0:
        return x.copy(), P.copy()
    return _predict(x, P, float(packet["ds"][k]), float(packet["gy"][k]),
                    float(packet["dt"][k]))


def _observe(model, x: np.ndarray, case: Mapping) -> tuple[np.ndarray, np.ndarray]:
    h, H = model.batch(x[None, :], case)
    h = np.asarray(h, dtype=float)[0]
    H = np.asarray(H, dtype=float)[0]
    if h.shape != (2,) or H.shape != (2, 4):
        raise ValueError(f"observer returned shapes h={h.shape}, H={H.shape}; expected (2,), (2,4)")
    if not np.isfinite(h).all() or not np.isfinite(H).all():
        raise ValueError("nonfinite observer output")
    return h, H


def _joseph(x: np.ndarray, P: np.ndarray, H: np.ndarray, innovation: np.ndarray,
            R: np.ndarray, permitted: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    S = H @ P @ H.T + R
    S = (S + S.T) * 0.5
    K = np.zeros((4, 2))
    if not permitted:
        return x.copy(), P.copy(), K, S
    K = np.linalg.solve(S, H @ P).T
    updated = x + K @ innovation
    updated[2] = _wrap(float(updated[2]))
    A = np.eye(4) - K @ H
    covariance = A @ P @ A.T + K @ R @ K.T
    return updated, (covariance + covariance.T) * 0.5, K, S


def _hand_sigma(rho: float) -> float:
    # Frozen W0 hand polarization-bias table, indexed by anchor-relative XY range.
    return float(np.interp(rho, [0.0, 1.5, 3.0, 6.0, 10.0],
                           [0.011, 0.020, 0.050, 0.120, 0.240]))


def reference(model, case: Mapping, packet: Mapping[str, np.ndarray]) -> dict[str, np.ndarray]:
    """Replay E0 independently; case is the original SPEC mapping.

    Returned keys use the native trace names (`x`, `P`, `prior`, `Pprior`,
    `h`, `H`, `K`, `Reff`, `mask`) plus update/gate diagnostics.
    """
    required = ("z", "x0", "P0", "ds", "gy", "dt", "muBASE", "muMB", "R")
    missing = [key for key in required if key not in packet]
    if missing:
        raise KeyError(f"packet missing fields: {missing}")
    anchor = np.asarray(case["anchor"], dtype=float)
    if anchor.shape != (3,):
        raise ValueError("case['anchor'] must have shape (3,)")

    z = np.asarray(packet["z"], dtype=float)
    n = len(z)
    if z.shape != (n, 2) or n == 0:
        raise ValueError("packet z must have shape (N,2), N>0")
    x0 = np.asarray(packet["x0"], dtype=float)
    if x0.shape not in ((3,), (4,)):
        raise ValueError(f"packet x0 shape mismatch: expected (3,) or (4,), got {x0.shape}")
    for key, shape in (("P0", (4, 4)), ("muBASE", (n, 2)),
                       ("muMB", (n, 2)), ("R", (n, 2, 2)), ("ds", (n,)),
                       ("gy", (n,)), ("dt", (n,))):
        if np.asarray(packet[key]).shape != shape:
            raise ValueError(f"packet {key} shape mismatch: expected {shape}, got {np.asarray(packet[key]).shape}")

    x = np.r_[x0[:3], 0.0]
    P = np.asarray(packet["P0"], dtype=float).copy()
    if not np.isfinite(x).all() or not np.isfinite(P).all() or not np.isfinite(z).all():
        raise ValueError("nonfinite initial state/covariance/observation")

    # Shadow gate: recursively use baseline mean and packet R only, before the
    # fixed mask is applied to the main E0 W0 filter.
    shadow_x = x.copy()
    shadow_P = P.copy()
    mask = np.empty(n, dtype=bool)
    for k in range(n):
        shadow_x, shadow_P = _predict_packet(shadow_x, shadow_P, k, packet)
        gate_h, gate_H = _observe(model, shadow_x, case)
        gate_innovation = z[k] - gate_h - np.asarray(packet["muBASE"])[k]
        gate_R = np.asarray(packet["R"])[k]
        gate_S = gate_H @ shadow_P @ gate_H.T + gate_R
        gate_S = (gate_S + gate_S.T) * 0.5
        nis = float(gate_innovation @ np.linalg.solve(gate_S, gate_innovation))
        mask[k] = nis <= GATE
        if mask[k]:
            shadow_x, shadow_P, _, _ = _joseph(shadow_x, shadow_P, gate_H,
                                               gate_innovation, gate_R, True)

    fields = {
        "x": np.empty((n, 4)), "P": np.empty((n, 4, 4)),
        "prior": np.empty((n, 4)), "Pprior": np.empty((n, 4, 4)),
        "h": np.empty((n, 2)), "H": np.empty((n, 2, 4)),
        "K": np.empty((n, 4, 2)), "Reff": np.empty((n, 2, 2)),
        "Rvar": np.empty((n, 2, 2)), "nu": np.empty((n, 2)),
        "sigma_b": np.empty(n), "rho_before": np.empty(n),
        "S": np.empty((n, 2, 2)),
    }
    for k in range(n):
        rho = math.hypot(float(x[0] - anchor[0]), float(x[1] - anchor[1]))
        sigma = _hand_sigma(rho)
        prior, Pprior = _predict_packet(x, P, k, packet)
        h, H = _observe(model, prior, case)
        innovation = z[k] - h - np.asarray(packet["muMB"])[k]
        Rvar = np.asarray(packet["R"][k], dtype=float).copy()
        Rvar[1, 1] += sigma**2
        x, P, K, S = _joseph(prior, Pprior, H, innovation, Rvar, bool(mask[k]))
        for key, value in (("x", x), ("P", P), ("prior", prior), ("Pprior", Pprior),
                           ("h", h), ("H", H), ("K", K), ("Reff", Rvar),
                           ("Rvar", Rvar), ("nu", innovation), ("sigma_b", sigma),
                           ("rho_before", rho), ("S", S)):
            fields[key][k] = value

    fields["mask"] = mask
    if not all(np.isfinite(value).all() for value in fields.values()):
        raise ValueError("reference replay produced nonfinite trace")
    return fields
