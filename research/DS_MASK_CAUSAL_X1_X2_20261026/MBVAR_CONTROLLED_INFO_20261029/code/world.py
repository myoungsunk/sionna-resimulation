"""MBVAR-INFO-001 world: pose ledger, canonical pose keys, collision/LOS checks, FFD LOS model, motion Jacobians.

Repository dependencies are imported from the pinned sources fetched by reflect_model/fetch_inputs.sh (REFLECT_ROOT):
SourceFFD (FFD_P0P3_20261016), core.predict (EKF4_RANGE_S_STAGED_20261014), exp_pb (pol_bias_model, read-only).
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
EXP = HERE.parent                                    # MBVAR_CONTROLLED_INFO_20261029
DSM = EXP.parent                                     # DS_MASK_CAUSAL_X1_X2_20261026
sys.path.insert(0, str(DSM / "pol_bias_model"))
import exp_pb as PB  # noqa: E402

C = PB.C
from core import predict, wrap  # noqa: E402

PARAMS = json.loads((EXP / "config" / "PLAN_PARAMETERS.json").read_text())
W = PARAMS["world"]
ROBOT_Z = float(W["robot_antenna_height_m"])
ANCHORS = {"A": tuple(W["anchors"]["A"]), "C": tuple(W["anchors"]["C"]), "B": tuple(W["anchors"]["B_RESERVE"])}
PRIMARY_ANCHORS = ("A", "C")
ROOM = (float(W["width_m"]), float(W["length_m"]))
ROBOT_BODY = (0.6, 0.4)                               # PLAN_P0_P6 §F
CLEARANCE_M = 0.10                                    # P0 proposal, recorded in P0_PREMISE
SPACING = float(W["trajectory_pose_spacing_m"])
RF = PARAMS["rf_canary"]
PLATE_C = np.array(RF["base_plate_center_xyz_m"][:2]); PLATE_L = float(RF["base_plate_length_m"]); PLATE_H = float(RF["base_plate_height_m"])


def spec(anchor_id: str) -> dict:
    return dict(anchor=ANCHORS[anchor_id], robot_z_m=ROBOT_Z, mount_deg=float(W["mount_deg"]))


_MODEL = None


def model():
    global _MODEL
    if _MODEL is None:
        _MODEL = C.base_model()
    return _MODEL


def h_H(states: np.ndarray, anchor_id: str):
    """FFD LOS observation h (n,2) and Jacobian H (n,2,4) at states (n,4) or (n,3)."""
    s = np.atleast_2d(states)
    if s.shape[1] == 3:
        s = np.c_[s, np.zeros(len(s))]
    h, H = model().batch(s, spec(anchor_id))
    return np.asarray(h), np.asarray(H)


# ----------------------------------------------------------------------------- trajectories
def t1_horizontal():
    x = np.round(np.arange(2.0, 10.0 + 1e-9, SPACING), 10)
    return np.c_[x, np.full(len(x), 6.0), np.zeros(len(x))]


def t4_s_curve():
    xs = np.linspace(2.0, 10.0, 200001)
    ys = 5.5 + 0.8 * np.sin(2 * np.pi * (xs - 2.0) / 8.0)
    seg = np.hypot(np.diff(xs), np.diff(ys)); s = np.r_[0.0, np.cumsum(seg)]
    L = s[-1]; targets = np.r_[np.arange(0.0, L, SPACING), L]
    x = np.interp(targets, s, xs); y = 5.5 + 0.8 * np.sin(2 * np.pi * (x - 2.0) / 8.0)
    dy = 0.8 * (2 * np.pi / 8.0) * np.cos(2 * np.pi * (x - 2.0) / 8.0)
    return np.c_[x, y, np.arctan2(dy, 1.0)]


def t5_spin():
    yaw = np.radians(np.arange(0.0, 360.0 + 1e-9, 5.0))
    return np.c_[np.full(len(yaw), 6.0), np.full(len(yaw), 6.0), yaw]


def t2_tangent_a_y7():                                  # AMENDMENT-001
    x = np.round(np.arange(2.0, 10.0 + 1e-9, SPACING), 10)
    return np.c_[x, np.full(len(x), 7.0), np.zeros(len(x))]


def _arc_a(rh, t0=10.0, t1=80.0):                      # AMENDMENT-001: CCW arc about anchor A, yaw = tangent
    cx, cy = ANCHORS["A"][:2]
    L = rh * math.radians(t1 - t0); s = np.r_[np.arange(0.0, L, SPACING), L]; th = math.radians(t0) + s / rh
    return np.c_[cx + rh * np.cos(th), cy + rh * np.sin(th), np.angle(np.exp(1j * (th + math.pi / 2)))]


TRAJ = {"T1_HORIZONTAL": t1_horizontal, "T4_S_CURVE": t4_s_curve, "T5_SPIN": t5_spin}
# AMENDMENT-001 candidates (anchor A only); radii from the 3-D range medians of the already-valid windows
AMEND1 = {"T2_TANGENT_A_Y7": t2_tangent_a_y7,
          "T3_ARC_A_R4266": lambda: _arc_a(math.sqrt(4.80 ** 2 - 2.2 ** 2)),
          "T3_ARC_A_R5345": lambda: _arc_a(math.sqrt(5.78 ** 2 - 2.2 ** 2))}
AMEND1_ANCHORS = ("A",)


def canonical_yaw_deg(yaw_rad: float) -> float:
    d = math.degrees(yaw_rad) % 360.0
    d = round(d, 9)
    return 0.0 if d == 360.0 else d


def pose_key(scene: str, anchor_id: str, x: float, y: float, yaw: float) -> str:
    obj = dict(scene=scene, anchor=list(ANCHORS[anchor_id]), x=round(float(x), 9), y=round(float(y), 9), z=ROBOT_Z,
               yaw_deg=canonical_yaw_deg(yaw), mount_deg=float(W["mount_deg"]))
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


# ----------------------------------------------------------------------------- geometry checks
def footprint(x, y, yaw):
    l, w = ROBOT_BODY; c, s = math.cos(yaw), math.sin(yaw)
    pts = [(+l / 2, +w / 2), (+l / 2, -w / 2), (-l / 2, -w / 2), (-l / 2, +w / 2)]
    return np.array([[x + c * a - s * b, y + s * a + c * b] for a, b in pts])


def plate_segment(rot_deg: float):
    t = math.radians(rot_deg); u = np.array([math.cos(t), math.sin(t)])
    return PLATE_C - u * PLATE_L / 2, PLATE_C + u * PLATE_L / 2


def _seg_dist(p, a, b):
    ab = b - a; t = np.clip(np.dot(p - a, ab) / np.dot(ab, ab), 0, 1)
    return float(np.linalg.norm(p - (a + t * ab)))


def _seg_intersect(p1, p2, q1, q2):
    def cr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    d1, d2, d3, d4 = cr(q1, q2, p1), cr(q1, q2, p2), cr(p1, p2, q1), cr(p1, p2, q2)
    if (d1 * d2 < 0) and (d3 * d4 < 0):
        den = (p2[0] - p1[0]) * (q2[1] - q1[1]) - (p2[1] - p1[1]) * (q2[0] - q1[0])
        u = ((q1[0] - p1[0]) * (q2[1] - q1[1]) - (q1[1] - p1[1]) * (q2[0] - q1[0])) / den
        return True, float(u)
    return False, None


def pose_checks(x, y, yaw, anchor_id):
    fp = footprint(x, y, yaw)
    room_margin = float(min(fp[:, 0].min(), fp[:, 1].min(), ROOM[0] - fp[:, 0].max(), ROOM[1] - fp[:, 1].max()))
    out = dict(room_margin_m=room_margin, room_ok=room_margin >= CLEARANCE_M)
    a3 = np.array(ANCHORS[anchor_id]); r3 = np.array([x, y, ROBOT_Z])
    for name, rot in (("C10", 0.0), ("C11", 45.0)):
        p, q = plate_segment(rot)
        dmin = min(_seg_dist(c, p, q) for c in fp)
        # footprint polygon vs plate segment intersection
        hit = any(_seg_intersect(fp[i], fp[(i + 1) % 4], p, q)[0] for i in range(4))
        ok_clear = (dmin >= CLEARANCE_M) and not hit
        cut, u = _seg_intersect(a3[:2], r3[:2], p, q)
        blocked = False
        if cut:
            zc = a3[2] + u * (r3[2] - a3[2])
            blocked = 0.0 <= zc <= PLATE_H
        out[f"{name}_clear_m"] = dmin; out[f"{name}_clear_ok"] = ok_clear; out[f"{name}_los_blocked"] = blocked
    return out


# ----------------------------------------------------------------------------- motion along a pose window
def motion_window(poses: np.ndarray, dt: float):
    """Noise-free controls and linearised F_k, Q_k along consecutive truth poses (b_g = 0)."""
    n = len(poses)
    X = np.c_[poses, np.zeros(n)]
    F = [np.eye(4)]; Q = [np.zeros((4, 4))]; ds_l = [0.0]; dth_l = [0.0]
    for k in range(1, n):
        dp = poses[k, :2] - poses[k - 1, :2]
        dth = float(wrap(poses[k, 2] - poses[k - 1, 2]))
        phi = poses[k - 1, 2] + dth / 2
        c = math.sin(dth / 2) / (dth / 2) if abs(dth) > 1e-12 else 1.0
        ds = float(dp @ np.array([math.cos(phi), math.sin(phi)])) / c
        q = np.diag([2e-5 * abs(ds), math.radians(0.015) ** 2 * dt, 0.0])
        _, _, Fk, Gk = predict(X[k - 1], np.zeros((4, 4)), ds, dth, dt, q)
        F.append(np.asarray(Fk)); Q.append(np.asarray(Gk) @ q @ np.asarray(Gk).T); ds_l.append(ds); dth_l.append(dth)
    return X, F, Q, np.array(ds_l), np.array(dth_l)


# ============================================================================ AMENDMENT-003
def taps_of(states, anchor_id):
    """First-path tap index the detector reports at `states` (observable of the receiver)."""
    s = np.atleast_2d(states)
    if s.shape[1] == 3:
        s = np.c_[s, np.zeros(len(s))]
    _, _, dg = model().batch(s, spec(anchor_id), return_diagnostics=True)
    return np.asarray(dg["tap"], int)


def h_H_tap(states, anchor_id, taps):
    """FFD LOS observation and Jacobian with the first-path tap index fixed to `taps` (tap-conditioned model).
    Same chain as SourceFFD.batch (Hann window, 4x zero padding, two-port power ratio at the tap) without the
    detector's argmax, so h is continuous in the state; equals SourceFFD.batch when taps are its own taps."""
    s = np.atleast_2d(np.asarray(states, float))
    if s.shape[1] == 3:
        s = np.c_[s, np.zeros(len(s))]
    m = model(); h, dh, dist, dr, cells, rho = m.spectrum(s, spec(anchor_id), True)
    nf = m.nf; n = len(s); ii = np.arange(n); idx = np.asarray(taps, int)
    cir = np.fft.ifft(h * m.window[None, :, None], n=4 * nf, axis=1) * nf
    dcir = np.fft.ifft(dh * m.window[None, :, None, None], n=4 * nf, axis=1) * nf
    cf = cir[ii, idx]; dcp = dcir[ii, idx]
    power = np.abs(cf) ** 2; dpower = 2 * np.real(cf.conj()[..., None] * dcp); den = power.sum(axis=1)
    sv = (power[:, 0] - power[:, 1]) / den
    jac = (dpower[:, 0] - dpower[:, 1] - sv[:, None] * dpower.sum(axis=1)) / den[:, None]
    J = np.zeros((n, 2, 4)); J[:, 0, :3] = dr; J[:, 1, :3] = jac
    B = sys.modules[type(m).__module__].B_OLD
    return np.column_stack([dist + B, sv]), J


def _arc_resample(xs, ys):
    seg = np.hypot(np.diff(xs), np.diff(ys)); s = np.r_[0.0, np.cumsum(seg)]
    L = s[-1]; tg = np.r_[np.arange(0.0, L, SPACING), L]
    x = np.interp(tg, s, xs); y = np.interp(tg, s, ys)
    return x, y


def _sinus(c, A, lam):
    def fn():
        xs = np.linspace(2.0, 10.0, 200001); ys = c + A * np.sin(2 * np.pi * (xs - 2.0) / lam)
        x, _ = _arc_resample(xs, ys); y = c + A * np.sin(2 * np.pi * (x - 2.0) / lam)
        dy = A * (2 * np.pi / lam) * np.cos(2 * np.pi * (x - 2.0) / lam)
        return np.c_[x, y, np.arctan2(dy, 1.0)]
    return fn


def _line_y(c):
    def fn():
        x = np.round(np.arange(2.0, 10.0 + 1e-9, SPACING), 10)
        return np.c_[x, np.full(len(x), float(c)), np.zeros(len(x))]
    return fn


def _diag(d):
    def fn():
        x0 = max(2.0, d - 11.5); x1 = min(10.0, d - 0.5)
        L = (x1 - x0) * math.sqrt(2); t = np.r_[np.arange(0.0, L, SPACING), L] / math.sqrt(2)
        x = x0 + t
        return np.c_[x, d - x, np.full(len(x), -math.pi / 4)]
    return fn


GEO2 = {}
for _c in (5, 6, 7, 8, 9):
    GEO2[f"L_y{_c}"] = _line_y(_c)
for _c in (5.5, 6.5, 7.5):
    for _A in (0.4, 0.8, 1.2):
        for _W in (4, 8):
            GEO2[f"S_c{_c}_A{_A}_W{_W}"] = _sinus(_c, _A, _W)
for _d in (12, 14):
    GEO2[f"D_{_d}"] = _diag(_d)
GEO2_ANCHORS = ("A", "C")


def _rev(c, x0, kind):
    def fn():
        k = np.r_[np.arange(0, 31), np.arange(29, 0, -1)] if kind == "REV60" else np.arange(0, 60)
        x = np.round(x0 + SPACING * k, 10)
        return np.c_[x, np.full(len(x), float(c)), np.zeros(len(x))]
    return fn


REVISIT_CANDIDATES = [(c, x0) for c in (7, 6, 8) for x0 in (3.0, 4.0, 5.0, 3.5, 4.5)]
REVISIT = {}
for _c, _x0 in REVISIT_CANDIDATES:
    for _k in ("REV60", "FWD60"):
        REVISIT[f"{_k}_y{_c}_x{_x0}"] = _rev(_c, _x0, _k)


def traj_fn(name):
    for d in (TRAJ, AMEND1, GEO2, REVISIT):
        if name in d:
            return d[name]
    raise KeyError(name)
