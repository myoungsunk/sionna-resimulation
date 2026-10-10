"""Read-only checks of statements in research/HEADING_RELIABILITY_20261010/00-02 against the stored supplement data (descriptive, no model).

Needs: BLOCK_C (FULL_RF/H_<case>.npy, INPUTS/rf_poses_R*.json, INPUTS/timeline_R2_Tnone.csv), BLOCK_D/FIRST_SECOND_PATH_R2A_m0_CENTER_BIN.csv,
the A23 LUT / meta / frequency axis.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np
import pandas as pd

from qclean_uwb.drivesim import hs_lut as HL
from qclean_uwb.drivesim import observation as O
from qclean_uwb.scenarios.corridor import CorridorSetup


def stations(route_json: Path):
    P = json.loads(route_json.read_text())
    P = P if isinstance(P, list) else P["poses"]
    g = collections.OrderedDict()
    for p in P:
        g.setdefault((round(p["x"], 4), round(p["y"], 4)), []).append(p)
    return [v for v in g.values() if len(v) >= 3], len(g), len(P)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--block-c", type=Path, required=True)
    ap.add_argument("--first-second-csv", type=Path, required=True)
    ap.add_argument("--lut", type=Path, required=True)
    ap.add_argument("--lut-meta", type=Path, required=True)
    ap.add_argument("--freqs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    out = {}
    # 1. stations, offsets, symmetric availability (document 02 and the frozen index schedule)
    sched = {}
    for r in ("R2", "R4", "R5"):
        st, n_xy, n_pose = stations(a.block_c / "INPUTS" / f"rf_poses_{r}.json")
        o2, o4, sym = [], [], 0
        for v in st:
            yaw = np.array([p["yaw_body_deg"] for p in v])
            d = ((yaw - yaw[0] + 180) % 360 - 180)
            o2.append(float(d[2]))
            o4.append(float(d[4]))
            step = float(np.min(np.abs(d[d != 0])))
            k = int(round(10 / step))
            sym += bool(np.any(np.isclose(d, k * step, atol=0.05)) and np.any(np.isclose(d, -k * step, atol=0.05)))
        sched[r] = dict(poses=n_pose, unique_xy_rounded_1e4=n_xy, stations=len(st), sizes=sorted({len(v) for v in st}), index2_offset_abs_range=[float(np.min(np.abs(o2))), float(np.max(np.abs(o2)))],
                        index4_offset_abs_range=[float(np.min(np.abs(o4))), float(np.max(np.abs(o4)))], index2_negative=int(np.sum(np.array(o2) < 0)), index2_positive=int(np.sum(np.array(o2) > 0)), stations_with_symmetric_pm10=sym)
    out["schedule"] = sched
    # 2. first/second path gap (R2-A m0, centre bin)
    d = pd.read_csv(a.first_second_csv)
    tl = pd.read_csv(a.block_c / "INPUTS" / "timeline_R2_Tnone.csv")
    d3 = dict(zip(tl.pose_id.values, np.sqrt((tl.x.values - 4.0) ** 2 + tl.y.values ** 2 + 2.2 ** 2)))
    d["d3"] = d.pose_id.map(d3)
    g = d.delay_gap_s * 1e9
    out["first_second_path_R2A_m0"] = dict(n=int(len(d)), gap_ns_quantiles_0_10_50_90_100=[float(x) for x in np.percentile(g, [0, 10, 50, 90, 100])], share_below_2ns=float((g < 2).mean()), share_below_0p25ns=float((g < 0.25).mean()),
                                           by_distance={f"{lo}-{hi}": dict(n=int(((d.d3 >= lo) & (d.d3 < hi)).sum()), gap_median_ns=float(g[(d.d3 >= lo) & (d.d3 < hi)].median()), amp_ratio_rx0_median=float(d.tx0_rx0_second_over_first_amplitude[(d.d3 >= lo) & (d.d3 < hi)].median()),
                                                                 amp_ratio_rx1_median=float(d.tx0_rx1_second_over_first_amplitude[(d.d3 >= lo) & (d.d3 < hi)].median())) for lo, hi in ((0, 5), (5, 10), (10, 99))})
    # 3. residual e_s = s_chain(H_full) - LUT(truth) within stations
    meta = json.loads(a.lut_meta.read_text())
    lut = HL.HsLut(dict(theta_deg=np.array(meta["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["meta"]["phi_deg"][2]), s=np.load(a.lut)))
    freqs = np.load(a.freqs)
    st, _, _ = stations(a.block_c / "INPUTS" / "rf_poses_R2.json")
    res = {}
    for case, ax, mt in (("R2_aA_m0", 4.0, 0), ("R2_aA_m45", 4.0, 45), ("R2_aB_m0", 10.0, 0)):
        H = np.load(a.block_c / "FULL_RF" / f"H_{case}.npy", mmap_mode="r")
        cs = CorridorSetup(anchor_x_m=ax)
        A, rz = cs.anchor_position, cs.robot_antenna_z_m
        within, change02, lev, p2p024 = [], [], [], []
        for v in st:
            ids = [p["pose_id"] for p in v]
            x, y = np.array([p["x"] for p in v]), np.array([p["y"] for p in v])
            yaw = np.radians([p["yaw_body_deg"] for p in v])
            e = O.observe(np.asarray(H[ids]), freqs, None, None)["s"] - HL.s_model(lut, A, rz, x, y, yaw, mt)
            ok = np.isfinite(e)
            within.append(float(np.std(e[ok])))
            if np.isfinite(e[[0, 2, 4]]).all():
                change02.append(abs(float(e[2] - e[0])))
                lev.append(abs(float(e[0])))
                p2p024.append(float(np.ptp(e[[0, 2, 4]])))
        res[case] = dict(stations=len(st), within_station_sd_median=float(np.median(within)), abs_e_s_at_index0_median=float(np.median(lev)), change_idx0_to_idx2_median=float(np.median(change02)),
                         ptp_over_idx_0_2_4_median=float(np.median(p2p024)), ratio_change_to_level=float(np.median(change02) / np.median(lev)))
    out["residual_within_station"] = res
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1)[:3000])


if __name__ == "__main__":
    main()
