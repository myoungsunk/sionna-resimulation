"""S6 experiment machinery: worlds (timeline + clean channels), observations, baselines, per-run metrics."""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from qclean_uwb.drivesim import filters as F
from qclean_uwb.drivesim import observation as O
from qclean_uwb.drivesim import sensors as S
from qclean_uwb.drivesim.hs_lut import HsLut

POS_PROCESS_STD = 0.0
EXCLUDE_S = 30.0
WRONG_BRANCH_DEG = 20.0
CHI2_3_95 = 7.814727903251179        # chi2(3 dof) 95 % point (pose NEES coverage, A17)
GRID_S = 1.0
TRACE_HOOK = None                # A23 rev3: optional callable(world, out, err, nees, inputs, obs) for raw-trace saving; None = off
TRACE_PARTIAL = None             # A23 rev3: optional dict handed to run_filter; keeps the last valid state if a run fails
CHI2_3_LO, CHI2_3_HI = 0.215795283, 9.348403604          # chi2(3 dof) 2.5 % / 97.5 % points
COMMON_FROM_DRIVE_G = 150      # A16: 30 s of drive time at 5 Hz; common stations = non-probe samples from this drive index on


@dataclass
class World:
    rows: list[dict]
    h: np.ndarray                  # (n_sample, n_bin, 2, 2) clean channel of every sample
    freqs: np.ndarray
    lateral: float
    mount_deg: float
    period: float | None
    route: str = "R1"
    anchor: str = "A"

    @property
    def t(self):
        return np.array([r["t_s"] for r in self.rows])

    @property
    def truth(self):
        return np.column_stack([[r["x"] for r in self.rows], [r["y"] for r in self.rows], np.radians([r["yaw_body_deg"] for r in self.rows])])

    @property
    def turn_phase(self):
        return np.array([bool(r["turn_phase"]) for r in self.rows])

    @property
    def drive_g(self):
        return np.array([r["drive_g"] for r in self.rows])

    @property
    def probe_id(self):
        return np.array([r["probe_id"] for r in self.rows])

    @property
    def n_probes(self):
        return len({r["probe_id"] for r in self.rows if r["probe_id"] >= 0})


def read_timeline(path) -> tuple[list[dict], np.ndarray]:
    rows, ids = [], []
    for r in csv.DictReader(Path(path).open()):
        rows.append(dict(idx=int(r["idx"]), t_s=float(r["t_s"]), drive_g=int(r["drive_g"]), phase=r["phase"], x=float(r["x"]), y=float(r["y"]),
                         yaw_body_deg=float(r["yaw_body_deg"]), turn_phase=r["turn_phase"] == "True", probe_id=int(r["probe_id"]),
                         probe_offset_deg=float(r["probe_offset_deg"])))
        ids.append(int(r["pose_id"]))
    return rows, np.array(ids)


def make_world(timeline_csv, h_store: np.ndarray, freqs, lateral: float, mount_deg: float, period, max_samples: int | None = None, route: str = "R1", anchor: str = "A") -> World:
    rows, ids = read_timeline(timeline_csv)
    if max_samples:
        rows, ids = rows[:max_samples], ids[:max_samples]
    h = h_store[ids]
    if not np.isfinite(h).all():
        raise ValueError("H_STORE_HAS_MISSING_POSES")
    return World(rows, h, np.asarray(freqs, float), lateral, mount_deg, period, route, anchor)


def observe_world(world: World, snr_db: float | None, seed_key: tuple, sensor: S.SensorNoise, range_offset: float, measure: str = "fp"):
    """Noisy first-path observation of every sample plus the random UWB range component.  ``snr_db=None`` -> noise-free chain."""
    rng = np.random.default_rng(list(seed_key))
    nv = O.noise_var_from_snr(snr_db) if snr_db is not None else None
    obs = O.observe(world.h, world.freqs, nv, rng, return_h=(measure == "rx"))
    if measure == "rx":                                  # A11: same noisy channel, s from the total received power of each port
        s_rx, energy = O.rx_energy_s(obs.pop("h_noisy"), nv)
        obs["s"] = np.where(obs["detected"], s_rx, np.nan)
        obs["power"] = energy
    obs["s_kind"] = measure
    obs["n_bins"] = world.h.shape[1]
    rng2 = np.random.default_rng(list(seed_key) + [4242])
    obs["range_m"] = obs["range_m"] + sensor.range_sigma_m * rng2.standard_normal(len(world.rows))
    obs["noise_var"] = nv or 0.0
    obs["range_offset"] = range_offset
    return obs


BASELINES = (
    # name, timeline period, filter options
    dict(name="odom_imu", period=None, use_range=False, use_s=False, use_odom_heading=True),
    dict(name="gyro_only", period=None, use_range=False, use_s=False, use_odom_heading=False),
    dict(name="range", period=None, use_range=True, use_s=False, use_odom_heading=True),
    dict(name="range_s_P0", period=None, use_range=True, use_s=True, use_odom_heading=True),
    dict(name="range_s_P0_noturn", period=None, use_range=True, use_s=True, use_odom_heading=True, skip_s_in_turn=True),
    dict(name="range_s_P1_T10", period=10.0, use_range=True, use_s=True, use_odom_heading=True),
    dict(name="range_s_P1_T20", period=20.0, use_range=True, use_s=True, use_odom_heading=True),
    dict(name="range_s_P1_T60", period=60.0, use_range=True, use_s=True, use_odom_heading=True),
    dict(name="inverse_heading_P0", period=None, use_range=True, use_s=True, use_odom_heading=True, s_mode="inverse"),
)
FILTER_KINDS_COMPARED = ("iekf", "ukf", "gsf")                 # on range_s_P0 and range_s_P1_T20, next to the EKF


def filter_config(base: dict, world: World, obs: dict, sensor: S.SensorNoise, mismatch_sigma: float, anchor_xyz, robot_z, kind="ekf") -> F.FilterConfig:
    cfg = F.FilterConfig(kind=kind, mount_deg=world.mount_deg, anchor_xyz=tuple(anchor_xyz), robot_z=robot_z, s_mismatch_sigma=mismatch_sigma,
                         range_offset=obs["range_offset"], range_sigma=sensor.range_sigma_m, k_s=sensor.k_s_m, k_theta=sensor.k_theta_rad,
                         k_stheta=sensor.k_stheta_rad2_per_m, arw_var=math.radians(sensor.arw_deg_sqrt_s) ** 2 * 0.2,
                         noise_var_cir_tap=6.0 * obs["noise_var"], pos_process_std=POS_PROCESS_STD, s_kind=obs.get("s_kind", "fp"),
                         noise_var_bin=obs["noise_var"], n_bins=obs.get("n_bins", 257))
    for k in ("use_range", "use_s", "use_odom_heading", "skip_s_in_turn", "s_mode"):
        if k in base:
            setattr(cfg, k, base[k])
    return cfg


def run_one(world: World, obs: dict, inputs: dict, cfg: F.FilterConfig, lut: HsLut | None, x0) -> dict:
    flags = dict(turn_phase=world.turn_phase)
    out = F.run_filter(cfg, lut, inputs, obs, flags, x0, partial=TRACE_PARTIAL)
    truth = world.truth
    err = out["est"][:, :3] - truth
    err[:, 2] = F.wrap(err[:, 2])
    t = world.t
    keep = t >= EXCLUDE_S
    head = np.degrees(err[:, 2])
    pos = np.hypot(err[:, 0], err[:, 1])
    nees = np.array([float(e @ np.linalg.solve(P + 1e-18 * np.eye(3), e)) for e, P in zip(err[keep], out["cov3"][keep])])
    st = out["stats"]
    s_total = st["s_updates"] + st["s_rejected"]
    turn = world.turn_phase
    ret = keep & (np.arange(len(t)) > (np.flatnonzero(turn).max() if turn.any() else -1))
    disp_true = truth[-1, :2] - truth[0, :2]
    disp_est = out["est"][-1, :2] - out["est"][0, :2]
    res = dict(closure_err_m=float(np.hypot(*disp_est)), disp_err_m=float(np.hypot(*(disp_est - disp_true))), final_pos_err_m=float(pos[-1]),
               heading_rmse_deg=float(np.sqrt(np.mean(head[keep] ** 2))), pos_rmse_m=float(np.sqrt(np.mean(pos[keep] ** 2))),
               heading_final_abs_deg=float(abs(head[-1])), heading_rmse_return_deg=float(np.sqrt(np.mean(head[ret] ** 2))),
               wrong_branch_frac=float(np.mean(np.abs(head[keep]) > WRONG_BRANCH_DEG)),
               wrong_branch_frac_10=float(np.mean(np.abs(head[keep]) > 10.0)), wrong_branch_frac_30=float(np.mean(np.abs(head[keep]) > 30.0)),
               nees_mean=float(np.mean(nees)), nis_s_mean=float(np.mean(st["nis_s"])) if len(st["nis_s"]) else float("nan"),
               s_reject_frac=float(st["s_rejected"] / s_total) if s_total else float("nan"),
               r_reject_frac=float(st["r_rejected"] / max(st["r_updates"] + st["r_rejected"], 1)),
               n_probes=world.n_probes, duration_s=float(t[-1]), n_samples=len(t))
    # A23 rev2 (additive columns): s / range NIS and rejection on the evaluation mask (t >= EXCLUDE_S), pre-gate and accepted-only
    for name, key in (("s", "s_log"), ("r", "r_log")):
        lg = st.get(key) or []
        if lg:
            kk = np.array([e[0] for e in lg], int)
            nn = np.array([e[1] for e in lg], float)
            aa = np.array([e[2] for e in lg], bool)
            m = keep[kk]
            res[f"nis_{name}_eval_pre"] = float(nn[m].mean()) if m.any() else float("nan")
            res[f"nis_{name}_eval_acc"] = float(nn[m & aa].mean()) if (m & aa).any() else float("nan")
            res[f"{name}_reject_frac_eval"] = float(1.0 - aa[m].mean()) if m.any() else float("nan")
            res[f"n_{name}_eval"] = int(m.sum())
        else:
            res.update({f"nis_{name}_eval_pre": float("nan"), f"nis_{name}_eval_acc": float("nan"), f"{name}_reject_frac_eval": float("nan"), f"n_{name}_eval": 0})
    # A17 (additive columns): coverage of the filter's own covariance
    sig_psi = np.sqrt(np.maximum(out["cov3"][:, 2, 2], 1e-18))
    res.update(nees_tail_lo=float(np.mean(nees < CHI2_3_LO)), nees_tail_hi=float(np.mean(nees > CHI2_3_HI)))
    res.update(nees_cov95=float(np.mean(nees <= CHI2_3_95)), heading_cov95=float(np.mean(np.abs(F.wrap(err[keep][:, 2])) <= 1.96 * sig_psi[keep])))
    # A16 (additive columns): the same drive positions in every probe schedule, and the probe samples on their own
    common = (world.probe_id < 0) & (world.drive_g >= COMMON_FROM_DRIVE_G)
    probe = (world.probe_id >= 0) & (world.drive_g >= COMMON_FROM_DRIVE_G)
    res.update(heading_rmse_common_deg=float(np.sqrt(np.mean(head[common] ** 2))) if common.any() else float("nan"),
               pos_rmse_common_m=float(np.sqrt(np.mean(pos[common] ** 2))) if common.any() else float("nan"),
               heading_rmse_probe_deg=float(np.sqrt(np.mean(head[probe] ** 2))) if probe.any() else float("nan"), n_common_samples=int(common.sum()))
    if TRACE_HOOK is not None:
        TRACE_HOOK(world, out, err, nees, inputs, obs)
    grid = np.arange(0.0, t[-1] + 1e-9, GRID_S)
    idx = np.clip(np.searchsorted(t, grid, side="right") - 1, 0, len(t) - 1)
    return dict(metrics=res, heading_err_deg=head[idx].astype(np.float32), pos_err_m=pos[idx].astype(np.float32))


PERIOD_CODE = {None: 0, 10.0: 1, 20.0: 2, 60.0: 3, "S10e0": 1, "S10e5": 1, "S10em5": 1}     # A20 steered T10 worlds share the stored T10 noise streams (paired by seed)
ROUTE_CODE = {"R1": 0, "R2": 1, "R4": 2, "R5": 3}      # R1 = 0 keeps the v1 noise streams unchanged


def run_unit(worlds: dict, lut: HsLut, *, sensor: S.SensorNoise, mismatch_sigma: float, anchor_xyz, robot_z: float, range_offset: float,
             snr_db: float | None, snr_idx: int, drift_idx: int, seed: int, compare_filters: bool = True, measure: str = "fp",
             obs_transform=None, drift_transform=None, cfg_transform=None, baselines=None) -> tuple[list[dict], dict]:
    """All baselines (and the filter-type comparison) for one (lateral, mount, drift, SNR, seed).  ``worlds`` maps period -> World."""
    any_world = next(iter(worlds.values()))
    level = S.DRIFT_LEVELS[drift_idx]
    drift = S.draw_drift(level, np.random.default_rng([seed, drift_idx, 1]))
    if drift_transform is not None:                       # A17 diagnostics only; None reproduces the stored behaviour
        drift = drift_transform(drift)
    init = np.random.default_rng([seed, 3]).standard_normal(6)
    p0 = np.array(F.FilterConfig().p0_std)
    truth0 = any_world.truth[0]
    x0 = np.array([truth0[0], truth0[1], truth0[2], 0.0, 0.0, 0.0]) + init * p0 * np.array([1, 1, 1, 0, 0, 0])
    ident = dict(route=any_world.route, anchor=any_world.anchor, lateral=any_world.lateral, mount_deg=any_world.mount_deg, drift=drift_idx, drift_name=level.name, snr_db=snr_db if snr_db is not None else float("nan"),
                 seed=seed)
    prepared = {}
    for period, w in worlds.items():
        code = PERIOD_CODE[period]
        ds, dth = S.true_increments(w.rows)
        inputs = S.generate_inputs(ds, dth, drift, sensor, 0.2, np.random.default_rng([seed, drift_idx, 2, code]))
        obs = observe_world(w, snr_db, (seed, snr_idx, code, int(round(w.lateral * 100)), int(w.mount_deg)) + ((ROUTE_CODE[w.route],) if w.route != "R1" else ()), sensor, range_offset, measure)
        if obs_transform is not None:                       # A17 diagnostics only
            obs = obs_transform(obs, w, np.random.default_rng([seed, snr_idx, code, 9090]))
        prepared[period] = (inputs, obs)
    rows, series = [], {}
    base_list = BASELINES if baselines is None else baselines
    jobs = [(b, "ekf") for b in base_list]
    if compare_filters:
        jobs += [(b, k) for b in base_list if b["name"] in ("range_s_P0", "range_s_P1_T20") for k in FILTER_KINDS_COMPARED]
    for base, kind in jobs:
        if base["period"] not in worlds:
            continue
        w = worlds[base["period"]]
        inputs, obs = prepared[base["period"]]
        cfg = filter_config(base, w, obs, sensor, mismatch_sigma, anchor_xyz, robot_z, kind=kind)
        if cfg_transform is not None:                       # A17 diagnostics only
            cfg = cfg_transform(cfg, base)
        row = dict(ident, baseline=base["name"], filter=kind, period_s=base["period"] if base["period"] else float("nan"))
        try:
            res = run_one(w, obs, inputs, cfg, lut, x0)
            row.update(res["metrics"], error="")
            if kind == "ekf":
                series[base["name"]] = (res["heading_err_deg"], res["pos_err_m"])
        except Exception as exc:  # noqa: BLE001  (a numerical failure of one run must not stop the campaign; it is counted and reported)
            row.update(error=f"{type(exc).__name__}: {exc}")
        rows.append(row)
    return rows, series
