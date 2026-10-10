"""Piecewise-straight routes (R2 loop, R4 zigzag, R5 serpentine) with in-place corner turns, wobble and probes (A9).

Same conventions as ``trajectory.build_samples`` (kept untouched for R1): speed 0.2 m/s at 5 Hz, kinematic truth (a step moves along the
*previous sample's* yaw, which includes the heading wobble), probe stops by drive time, wobble held during any in-place rotation.
Phases are ``drive`` / ``turn`` / ``probe``; ``turn_phase`` marks every corner turn.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from qclean_uwb.drivesim.trajectory import TrajectoryConfig, probe_offsets_deg, wobble_phase

LANE_M = 0.45
X_START, X_END = 1.2, 18.8
ZIGZAG_DEG = 35.7
TURN_STEP_DEG = 5.0
ANCHORS = {"A": (4.0, 0.0), "B": (10.0, 0.0)}      # ceiling anchors, horizontal position; B is the added centre anchor


@dataclass(frozen=True)
class Leg:
    heading_deg: float
    length_m: float


@dataclass(frozen=True)
class RouteSpec:
    name: str
    start: tuple
    legs: tuple


def r2_spec() -> RouteSpec:
    L = X_END - X_START
    return RouteSpec("R2", (X_START, -LANE_M), (Leg(90.0, 2 * LANE_M), Leg(0.0, L), Leg(-90.0, 2 * LANE_M), Leg(180.0, L)))


def r4_spec() -> RouteSpec:
    leg = 2 * LANE_M / math.sin(math.radians(ZIGZAG_DEG))
    return RouteSpec("R4", (X_START, -LANE_M), tuple(Leg(ZIGZAG_DEG if k % 2 == 0 else -ZIGZAG_DEG, leg) for k in range(14)))


def r5_spec() -> RouteSpec:
    L = X_END - X_START
    return RouteSpec("R5", (X_START, LANE_M), (Leg(0.0, L), Leg(-90.0, LANE_M), Leg(180.0, L), Leg(-90.0, LANE_M), Leg(0.0, L)))


SPECS = {"R2": r2_spec, "R4": r4_spec, "R5": r5_spec}


def _wrap180(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def build_route_samples(spec: RouteSpec, cfg: TrajectoryConfig) -> list[dict]:
    phi = wobble_phase(cfg.wobble_seed)
    w = lambda g: cfg.wobble_amp_deg * math.sin(2.0 * math.pi * (g * cfg.dt) / cfg.wobble_period_s + phi)  # noqa: E731
    period = None if cfg.probe_period_s is None else int(round(cfg.probe_period_s * cfg.rate_hz))
    offsets = probe_offsets_deg(cfg.probe_span_deg, cfg.probe_step_deg)
    rows: list[dict] = []
    x, y = spec.start
    g, probe_id = 0, 0
    cur = spec.legs[0].heading_deg                       # unwrapped nominal heading

    def add(phase, yaw, **extra):
        rows.append(dict(idx=len(rows), t_s=len(rows) * cfg.dt, drive_g=g, phase=phase, x=x, y=y, yaw_body_deg=yaw, turn_phase=phase == "turn",
                         probe_id=extra.get("probe_id", -1), probe_offset_deg=extra.get("off", 0.0)))

    def maybe_probe(base):
        nonlocal probe_id
        if period and g > 0 and g % period == 0:
            for off in offsets:
                add("probe", base + off, probe_id=probe_id, off=off)
            probe_id += 1

    add("drive", cur + w(0))
    for k, leg in enumerate(spec.legs):
        if k > 0:
            d = _wrap180(leg.heading_deg - cur)
            n_t = max(1, math.ceil(abs(d) / TURN_STEP_DEG - 1e-9))
            for j in range(1, n_t + 1):
                add("turn", cur + w(g) + d * j / n_t)
            cur += d
        for _ in range(max(1, round(leg.length_m / cfg.step_m))):
            psi = math.radians(rows[-1]["yaw_body_deg"])
            x += cfg.step_m * math.cos(psi)
            y += cfg.step_m * math.sin(psi)
            g += 1
            add("drive", cur + w(g))
            maybe_probe(cur + w(g))
    return rows


def anchor_clearance(rows: list[dict], anchors=ANCHORS) -> dict:
    return {k: min(math.hypot(r["x"] - ax, r["y"] - ay) for r in rows) for k, (ax, ay) in anchors.items()}


def choose_wobble_seed(spec: RouteSpec, base_cfg: TrajectoryConfig, periods=(None, 10.0, 20.0, 60.0), min_clearance=0.02, x_range=(1.0, 19.0),
                       y_limit=0.74, max_tries=50) -> tuple[int, dict]:
    """First seed (base, base+1, ...) whose route keeps the region limits and the anchor-axis clearance for every probe-period variant."""
    for k in range(max_tries):
        seed = base_cfg.wobble_seed + k
        ok, worst = True, {}
        for T in periods:
            rows = build_route_samples(spec, TrajectoryConfig(**{**base_cfg.snapshot(), "wobble_seed": seed, "probe_period_s": T}))
            xs = [r["x"] for r in rows]
            ys = [abs(r["y"]) for r in rows]
            c = anchor_clearance(rows)
            worst = {a: min(worst.get(a, 9.0), v) for a, v in c.items()}
            if min(xs) < x_range[0] or max(xs) > x_range[1] or max(ys) > y_limit or min(c.values()) < min_clearance:
                ok = False
                break
        if ok:
            return seed, worst
    raise ValueError(f"NO_WOBBLE_SEED_SATISFIES_GUARDS {spec.name}")
