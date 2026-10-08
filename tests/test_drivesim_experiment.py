import numpy as np
import pandas as pd
import pytest

from qclean_uwb.drivesim import analysis as A
from qclean_uwb.drivesim import experiment as E
from qclean_uwb.drivesim import hs_lut as L
from qclean_uwb.drivesim import observation as O
from qclean_uwb.drivesim import sensors as S
from qclean_uwb.drivesim.trajectory import TrajectoryConfig, build_samples
from qclean_uwb.scenarios.corridor import CorridorSetup
from test_drivesim_hs_lut import ideal_banks

SETUP = CorridorSetup()


def ideal_world(period, mount, n=420):
    banks = ideal_banks()
    rows = build_samples(TrajectoryConfig(probe_period_s=period))[:n]
    h = np.empty((len(rows), 257, 2, 2), complex)
    for i, r in enumerate(rows):
        pos = SETUP.robot_position(r["x"], r["y"])
        d = (pos - SETUP.anchor_position)
        d = d / np.linalg.norm(d)
        h[i] = L.los_h(banks, d, r["yaw_body_deg"] + mount, dist_m=float(np.linalg.norm(pos - SETUP.anchor_position)))
    return E.World(rows, h, banks[0].freqs_hz, 0.0, mount, period), banks


def test_run_unit_on_los_only_channels_gives_sane_metrics():
    worlds, banks = {}, None
    for p in (None, 20.0):
        worlds[p], banks = ideal_world(p, 45.0)
    lut = L.HsLut(L.build_lut(banks, 6.0, 6.0))
    rows, series = E.run_unit(worlds, lut, sensor=S.SensorNoise(), mismatch_sigma=0.05, anchor_xyz=tuple(SETUP.anchor_position),
                              robot_z=SETUP.robot_antenna_z_m, range_offset=O.los_range_bias(banks[0].freqs_hz), snr_db=40.0, snr_idx=0,
                              drift_idx=2, seed=1, compare_filters=False)
    df = pd.DataFrame(rows)
    assert set(df.baseline) >= {"odom_imu", "gyro_only", "range", "range_s_P0", "range_s_P1_T20"} and (df.error == "").all()
    by = df.set_index("baseline")
    assert by.loc["range_s_P0", "heading_rmse_deg"] < by.loc["odom_imu", "heading_rmse_deg"]
    assert np.isfinite(df[["heading_rmse_deg", "pos_rmse_m", "nees_mean"]].to_numpy()).all()
    assert by.loc["range_s_P1_T20", "n_probes"] >= 1 and by.loc["range_s_P0", "n_probes"] == 0
    assert "range_s_P0" in series


def test_holm_and_paired_analysis_detects_a_clear_improvement():
    rng = np.random.default_rng(0)
    rows = []
    for lat in (0.0, 0.35):
        for seed in range(30):
            base = rng.uniform(5, 10)
            for name, val in (("odom_imu", base), ("range_s_P0", 0.3 * base + rng.normal(0, 0.1))):
                rows.append(dict(lateral=lat, mount_deg=0.0, drift=0, snr_db=30.0, seed=seed, baseline=name, filter="ekf", heading_rmse_deg=val))
    df = pd.DataFrame(rows)
    out = A.paired(df, "odom_imu", "range_s_P0", "heading_rmse_deg", ["lateral", "mount_deg", "drift", "snr_db"])
    assert out.improved.all() and (out.median_rel_improvement > 0.5).all() and (out.p_holm < 0.01).all()
    same = A.paired(df.assign(heading_rmse_deg=df.heading_rmse_deg), "odom_imu", "odom_imu", "heading_rmse_deg", ["lateral", "mount_deg", "drift", "snr_db"])
    assert not same.improved.any()


def test_h3_direction_convention_and_h4_bound():
    rng = np.random.default_rng(1)
    rows = []
    for mount, level in ((0.0, 10.0), (45.0, 2.0)):
        for seed in range(30):
            rows.append(dict(lateral=0.0, mount_deg=mount, drift=0, snr_db=30.0, seed=seed, baseline="range_s_P0", filter="ekf",
                             heading_rmse_deg=level + rng.normal(0, 0.2), wrong_branch_frac=0.0))
    out = A.h3(pd.DataFrame(rows))
    assert out.median_rel_improvement.iloc[0] > 0.5 and out.improved.iloc[0]          # 45 deg better -> H3
    wb = []
    for b, frac in (("range_s_P0", 0.5), ("range_s_P1_T10", 0.01), ("range_s_P1_T20", 0.02), ("range_s_P1_T60", 0.30)):
        for seed in range(30):
            wb.append(dict(lateral=0.0, mount_deg=0.0, drift=0, snr_db=30.0, seed=seed, baseline=b, wrong_branch_frac=frac))
    r = A.h4(pd.DataFrame(wb))
    assert r.largest_T_ok.iloc[0] == 20


def test_route_analysis_helpers_h6_h7_and_generic_conditions():
    rng = np.random.default_rng(3)
    rows = []
    for route in ("R2", "R4"):
        for anchor in ("A", "B"):
            for seed in range(30):
                base = rng.uniform(1.0, 2.0)
                for name, val in (("odom_imu", base), ("range_s_P0", 0.4 * base * (1.0 if anchor == "A" else 0.8))):
                    rows.append(dict(route=route, anchor=anchor, lateral=0.0, mount_deg=0.0, drift=0, snr_db=30.0, seed=seed, baseline=name, filter="ekf",
                                     heading_rmse_deg=val, disp_err_m=val, wrong_branch_frac=0.0))
    df = pd.DataFrame(rows)
    assert A.cond(df) == ["route", "anchor", "lateral", "mount_deg", "drift", "snr_db"] and A.cond(df, drop=("anchor",))[1] == "lateral"
    h6 = A.h6_closure(df)
    assert len(h6) == 4 and h6.improved.all()
    h7 = A.h7_anchor(df)
    assert len(h7) == 2 and (h7.median_rel_improvement > 0.1).all()          # B is 20 % lower by construction -> positive = B better


def test_common_station_metrics_use_the_same_drive_positions_in_every_probe_schedule():
    """A16: heading_rmse_common_deg is scored on non-probe samples with drive_g >= 150, identical truth for P0 and P1."""
    worlds, banks = {}, None
    for p in (None, 20.0):
        banks = ideal_banks()
        rows = [r for r in build_samples(TrajectoryConfig(probe_period_s=p)) if r["drive_g"] <= 260][:700]
        h = np.empty((len(rows), 257, 2, 2), complex)
        for i, r in enumerate(rows):
            pos = SETUP.robot_position(r["x"], r["y"])
            d = pos - SETUP.anchor_position
            h[i] = L.los_h(banks, d / np.linalg.norm(d), r["yaw_body_deg"] + 45.0, dist_m=float(np.linalg.norm(d)))
        worlds[p] = E.World(rows, h, banks[0].freqs_hz, 0.0, 45.0, p)
    com = {p: (w.probe_id < 0) & (w.drive_g >= E.COMMON_FROM_DRIVE_G) for p, w in worlds.items()}
    assert com[None].sum() == com[20.0].sum() > 0
    assert np.allclose(worlds[None].truth[com[None]], worlds[20.0].truth[com[20.0]])
    lut = L.HsLut(L.build_lut(banks, 6.0, 6.0))
    rows, _ = E.run_unit(worlds, lut, sensor=S.SensorNoise(), mismatch_sigma=0.05, anchor_xyz=tuple(SETUP.anchor_position), robot_z=SETUP.robot_antenna_z_m,
                         range_offset=O.los_range_bias(banks[0].freqs_hz), snr_db=40.0, snr_idx=0, drift_idx=1, seed=2, compare_filters=False)
    by = pd.DataFrame(rows).set_index("baseline")
    assert by.loc["range_s_P0", "n_common_samples"] == by.loc["range_s_P1_T20", "n_common_samples"] == com[None].sum()
    assert np.isnan(by.loc["range_s_P0", "heading_rmse_probe_deg"]) and np.isfinite(by.loc["range_s_P1_T20", "heading_rmse_probe_deg"])
    assert np.isfinite(by[["heading_rmse_common_deg", "pos_rmse_common_m"]].to_numpy()).all()
