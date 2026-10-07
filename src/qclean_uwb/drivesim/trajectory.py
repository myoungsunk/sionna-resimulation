"""Scripted (open-loop) truth trajectory for the corridor drive: out leg, 180 deg turn, back leg, optional probes.

The truth never depends on the estimator or on Monte Carlo seeds, so the RF channel is computed once per
(lateral y0, mount offset) pose set.  Probe periods are counted in *drive time*, which makes the pose sets for
T = 10, 20, 60 s nested (T = 10 s is the superset).

Conventions: world x along the corridor, yaw counter-clockwise from +x, degrees.  Body yaw is the robot heading;
antenna yaw = body yaw + mount offset (lever arm 0, so the antenna sits at the body position).
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

import numpy as np

PHASES = ("drive_out", "turn", "drive_back", "probe")


@dataclass(frozen=True)
class TrajectoryConfig:
    x0_m: float = 1.2
    y0_m: float = 0.0
    n_steps: int = 440                 # per leg
    speed_m_s: float = 0.2
    rate_hz: float = 5.0
    wobble_amp_deg: float = 4.0
    wobble_period_s: float = 12.0
    wobble_seed: int = 20261007
    turn_rate_deg_s: float = 25.0
    probe_rate_deg_s: float = 25.0
    probe_span_deg: float = 45.0
    probe_step_deg: float = 5.0
    probe_period_s: float | None = None   # None = no probe (P0)

    @property
    def dt(self) -> float:
        return 1.0 / self.rate_hz

    @property
    def step_m(self) -> float:
        return self.speed_m_s / self.rate_hz

    def snapshot(self) -> dict:
        return asdict(self)


def wobble_phase(seed: int) -> float:
    return float(np.random.default_rng(seed).uniform(0.0, 2.0 * math.pi))


def probe_offsets_deg(span: float = 45.0, step: float = 5.0) -> list[float]:
    """Relative yaw of the 36 samples of one probe: to -span, sweep to +span, back to 0."""
    n = int(round(span / step))
    down = [-step * i for i in range(1, n + 1)]
    sweep = [-span + step * i for i in range(1, 2 * n + 1)]
    back = [span - step * i for i in range(1, n + 1)]
    return down + sweep + back


def _rate_check(cfg: TrajectoryConfig) -> None:
    per_sample_turn = cfg.turn_rate_deg_s / cfg.rate_hz
    per_sample_probe = cfg.probe_rate_deg_s / cfg.rate_hz
    if not (math.isclose(per_sample_probe, cfg.probe_step_deg) and math.isclose(180.0 % per_sample_turn, 0.0, abs_tol=1e-9)):
        raise ValueError("ROTATION_RATE_MUST_GIVE_GRID_ALIGNED_SAMPLES")


def build_samples(cfg: TrajectoryConfig) -> list[dict]:
    """Sample table (one row per 5 Hz UWB event).  Rows are dicts with the keys documented in ``COLUMNS``."""
    _rate_check(cfg)
    phi = wobble_phase(cfg.wobble_seed)
    w = lambda g: cfg.wobble_amp_deg * math.sin(2.0 * math.pi * (g * cfg.dt) / cfg.wobble_period_s + phi)  # noqa: E731
    n = cfg.n_steps
    period = None if cfg.probe_period_s is None else int(round(cfg.probe_period_s * cfg.rate_hz))
    offsets = probe_offsets_deg(cfg.probe_span_deg, cfg.probe_step_deg)
    rows: list[dict] = []
    x, y = cfg.x0_m, cfg.y0_m
    probe_id = 0

    def add(phase, g, yaw, **extra):
        rows.append(dict(idx=len(rows), t_s=len(rows) * cfg.dt, drive_g=g, phase=phase, x=x, y=y, yaw_body_deg=yaw,
                         turn_phase=phase == "turn", probe_id=extra.get("probe_id", -1), probe_offset_deg=extra.get("off", 0.0)))

    def maybe_probe(g, base):
        nonlocal probe_id
        if period and g > 0 and g % period == 0:
            for off in offsets:
                add("probe", g, base + off, probe_id=probe_id, off=off)
            probe_id += 1

    for g in range(0, n + 1):                      # out leg, heading 0 + wobble
        psi = w(g)
        add("drive_out", g, psi)
        maybe_probe(g, psi)
        if g < n:
            x += cfg.step_m * math.cos(math.radians(psi))
            y += cfg.step_m * math.sin(math.radians(psi))
    hold = w(n)
    for j in range(1, int(round(180.0 / cfg.probe_step_deg)) + 1):   # in-place 180 deg turn, wobble held
        add("turn", n, hold + cfg.probe_step_deg * j)
    for g in range(n, 2 * n):                      # back leg, heading 180 + wobble; sample g=n is the last turn sample
        psi = 180.0 + w(g)
        x += cfg.step_m * math.cos(math.radians(psi))
        y += cfg.step_m * math.sin(math.radians(psi))
        add("drive_back", g + 1, 180.0 + w(g + 1))
        maybe_probe(g + 1, 180.0 + w(g + 1))
    return rows


def check_region(rows: list[dict], x_range=(1.0, 19.0), y_limit: float = 0.74) -> None:
    xs = np.array([r["x"] for r in rows])
    ys = np.array([r["y"] for r in rows])
    if xs.min() < x_range[0] or xs.max() > x_range[1] or np.abs(ys).max() > y_limit:
        raise ValueError(f"TRAJECTORY_OUTSIDE_ALLOWED_REGION x[{xs.min():.3f},{xs.max():.3f}] |y|max {np.abs(ys).max():.3f}")


def pose_key(x: float, y: float, yaw_deg: float) -> tuple:
    return (round(x, 6), round(y, 6), round(yaw_deg, 6))


def unique_poses(rows_by_variant: list[list[dict]]) -> tuple[list[dict], list[list[int]]]:
    """Union of body poses over several timelines; returns (pose list, per-timeline pose_id per sample)."""
    table: dict[tuple, int] = {}
    poses: list[dict] = []
    ids: list[list[int]] = []
    for rows in rows_by_variant:
        cur = []
        for r in rows:
            k = pose_key(r["x"], r["y"], r["yaw_body_deg"])
            if k not in table:
                table[k] = len(poses)
                poses.append(dict(pose_id=len(poses), x=k[0], y=k[1], yaw_body_deg=k[2]))
            cur.append(table[k])
        ids.append(cur)
    return poses, ids


def rf_tasks(poses: list[dict], mount_deg: float) -> list[dict]:
    """Group poses by position: one A-method task per (x, y) with the list of antenna yaws to compute."""
    by_pos: dict[tuple, list[dict]] = {}
    for p in poses:
        by_pos.setdefault((p["x"], p["y"]), []).append(p)
    tasks = []
    for i, ((x, y), ps) in enumerate(sorted(by_pos.items())):
        yaws = sorted({round(p["yaw_body_deg"] + mount_deg, 6) for p in ps})
        tasks.append(dict(task_id=i, tag=f"x{x:.4f}_y{y:.4f}", x=x, y=y, antenna_yaw_deg=yaws, pose_ids=[p["pose_id"] for p in ps]))
    return tasks


def motion_increments(rows: list[dict]) -> dict:
    """True per-sample path length and heading change (for odometry/gyro generation)."""
    x = np.array([r["x"] for r in rows]); y = np.array([r["y"] for r in rows]); yaw = np.array([r["yaw_body_deg"] for r in rows])
    ds = np.r_[0.0, np.hypot(np.diff(x), np.diff(y))]
    dyaw = np.r_[0.0, np.diff(yaw)]
    return dict(ds_m=ds, dyaw_deg=dyaw)


def samples_sha256(rows: list[dict]) -> str:
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=float)
    return hashlib.sha256(blob.encode()).hexdigest()
