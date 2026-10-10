"""A16 part B: linearised batch observability and initial-heading ambiguity along the scripted routes with the actual LoS-only LUT.

  python scripts/drive_sim/observability_check.py --s1 S1 --lut-dir S4 --out DEV_RESULTS/OBSERVABILITY_A16.json [--s6-r1 S6dir --s6-routes S6_routes_dir]
Definitions are fixed in S0/PREREG_AMENDMENTS.md A16.  Truth-linearised local analysis, not a global observability proof.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import filters as F  # noqa: E402
from qclean_uwb.drivesim import sensors as S  # noqa: E402
from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.scenarios.corridor import CorridorSetup  # noqa: E402

DT = 0.2
COMMON_FROM = 150
SIG_R2 = 0.05 ** 2 + 0.149 ** 2 / 12.0 + 0.05 ** 2          # range variance the filter is told (A7 item 4)
SIG_S2 = 0.02 ** 2 + 0.16095229605409875 ** 2               # thermal (SNR 30 dB calibration) + route sigma_mismatch (A16)
NOISE = S.SensorNoise()
ARW_VAR = math.radians(NOISE.arw_deg_sqrt_s) ** 2 * DT
CFG = F.FilterConfig()
P0_STD = np.array(CFG.p0_std, float)
WB = CFG.wheel_base
STEP = np.array([1e-4, 1e-4, 1e-5, 1e-6, 1e-5, 1e-5])


def read_rows(path):
    rows = []
    for r in csv.DictReader(Path(path).open()):
        rows.append(dict(x=float(r["x"]), y=float(r["y"]), yaw=math.radians(float(r["yaw_body_deg"])), drive_g=int(r["drive_g"]), probe_id=int(r["probe_id"])))
    return rows


def increments(rows):
    x = np.array([r["x"] for r in rows])
    y = np.array([r["y"] for r in rows])
    yaw = np.unwrap(np.array([r["yaw"] for r in rows]))
    ds = np.r_[0.0, np.hypot(np.diff(x), np.diff(y))]
    dth = np.r_[0.0, np.diff(yaw)]
    return ds, dth


def propagate(p, ds, dth):
    """The filter's dead-reckoning recursion (predict) with noise-free increments; returns (N, 3) [x, y, psi]."""
    n = len(ds)
    out = np.empty((n, 3))
    x, y, psi = p[0], p[1], p[2]
    b, sf = p[3], p[4]
    out[0] = (x, y, psi)
    for k in range(1, n):
        x += ds[k] * math.cos(psi)
        y += ds[k] * math.sin(psi)
        psi += (dth[k] - b * DT) / (1.0 + sf)
        out[k] = (x, y, psi)
    return out


def jacobian_state(p, ds, dth):
    n = len(ds)
    J = np.empty((n, 3, 6))
    for i in range(6):
        d = np.zeros(6)
        d[i] = STEP[i]
        J[:, :, i] = (propagate(p + d, ds, dth) - propagate(p - d, ds, dth)) / (2.0 * STEP[i])
    return J


def information(rows, lut, anchor_xyz, robot_z, mount, use_range, use_s):
    ds, dth = increments(rows)
    p = np.array([rows[0]["x"], rows[0]["y"], rows[0]["yaw"], 0.0, 0.0, 0.0])
    traj = propagate(p, ds, dth)
    Jx = jacobian_state(p, ds, dth)
    n = len(ds)
    info = np.zeros((6, 6))
    # odom-heading pseudo-measurement: h = eps*ds/wb - SF*dth_g - b*dt   (filters.update_odom_heading)
    for k in range(1, n):
        H = np.zeros(6)
        H[3], H[4], H[5] = -DT, -dth[k], ds[k] / WB
        var = CFG.k_theta * abs(dth[k]) + CFG.k_stheta * abs(ds[k]) + ARW_VAR
        info += np.outer(H, H) / var
    if use_range:
        a = np.asarray(anchor_xyz, float)
        dz = a[2] - robot_z
        d = np.sqrt((traj[:, 0] - a[0]) ** 2 + (traj[:, 1] - a[1]) ** 2 + dz * dz)
        gr = np.stack(((traj[:, 0] - a[0]) / d, (traj[:, 1] - a[1]) / d), 1)
        Hr = np.einsum("kj,kji->ki", gr, Jx[:, :2, :])
        info += Hr.T @ Hr / SIG_R2
    if use_s:
        _, js = s_model(lut, anchor_xyz, robot_z, traj[:, 0], traj[:, 1], traj[:, 2], mount, with_jac=True)
        Hs = np.einsum("kj,kji->ki", js, Jx)
        info += Hs.T @ Hs / SIG_S2
    return info, Jx, traj


def summarize_info(info, Jx, rows):
    P0 = np.diag(P0_STD ** 2)
    sq = np.diag(P0_STD)
    ev = np.sort(np.linalg.eigvalsh(sq @ info @ sq))[::-1]
    P = np.linalg.inv(np.linalg.inv(P0) + info)
    jpsi = Jx[:, 2, :]
    std_psi = np.degrees(np.sqrt(np.einsum("ki,ij,kj->k", jpsi, P, jpsi)))
    com = np.array([(r["probe_id"] < 0) and (r["drive_g"] >= COMMON_FROM) for r in rows])
    return dict(whitened_info_eigenvalues=[float(v) for v in ev], heading_std_common_mean_deg=float(std_psi[com].mean()), heading_std_last_deg=float(std_psi[-1]),
                posterior_param_std=dict(zip(("x0", "y0", "psi0_deg", "b_dps", "SF", "eps"), [float(P[0, 0] ** .5), float(P[1, 1] ** .5), math.degrees(P[2, 2] ** .5),
                                                                                              math.degrees(P[3, 3] ** .5), float(P[4, 4] ** .5), float(P[5, 5] ** .5)])))


def ambiguity_profile(rows, lut, anchor_xyz, robot_z, mount):
    ds, dth = increments(rows)
    p0 = np.array([rows[0]["x"], rows[0]["y"], rows[0]["yaw"], 0.0, 0.0, 0.0])
    ref = propagate(p0, ds, dth)
    a = np.asarray(anchor_xyz, float)
    dz = a[2] - robot_z
    rng = lambda t: np.sqrt((t[:, 0] - a[0]) ** 2 + (t[:, 1] - a[1]) ** 2 + dz * dz)  # noqa: E731
    s_ref = s_model(lut, anchor_xyz, robot_z, ref[:, 0], ref[:, 1], ref[:, 2], mount)
    r_ref = rng(ref)
    deltas = np.arange(-180.0, 180.0, 1.0)
    chi = np.empty(len(deltas))
    for i, d in enumerate(deltas):
        p = p0.copy()
        p[2] += math.radians(d)
        t = propagate(p, ds, dth)
        # the path rotates about its start: the odom-heading pseudo-measurement is unaffected, range and s are
        s = s_model(lut, anchor_xyz, robot_z, t[:, 0], t[:, 1], t[:, 2], mount)
        chi[i] = float(np.sum((rng(t) - r_ref) ** 2) / SIG_R2 + np.sum((s - s_ref) ** 2) / SIG_S2)
    mins = [i for i in range(len(deltas)) if chi[i] < chi[i - 1] and chi[i] <= chi[(i + 1) % len(deltas)]]
    return dict(local_minima=[dict(delta_psi0_deg=float(deltas[i]), chi2=float(chi[i]), chi2_per_sample=float(chi[i] / len(ds))) for i in sorted(mins, key=lambda i: chi[i])[:6]],
                n_samples=len(ds), chi2_at_plus_minus_5deg=float(min(chi[np.argmin(abs(deltas - 5))], chi[np.argmin(abs(deltas + 5))])))


def empirical(args):
    out = {}
    if args.s6_r1:
        for f in sorted(Path(args.s6_r1).glob("results_y*_m*.csv")):
            d = pd.read_csv(f)
            d = d[d["filter"] == "ekf"]
            lat, mount = float(d.lateral.iloc[0]), float(d.mount_deg.iloc[0])
            for b, g in d.groupby("baseline"):
                out[("R1", "A", lat, mount, b)] = float(g.heading_rmse_deg.median())
    if args.s6_routes:
        for f in sorted(Path(args.s6_routes).glob("results_R*_a*_m*.csv")):
            d = pd.read_csv(f)
            d = d[d["filter"] == "ekf"]
            for b, g in d.groupby("baseline"):
                out[(d.route.iloc[0], d.anchor.iloc[0], float(d.lateral.iloc[0]), float(d.mount_deg.iloc[0]), b)] = float(g.heading_rmse_deg.median())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1", type=Path, required=True)
    ap.add_argument("--lut-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--s6-r1", type=Path)
    ap.add_argument("--s6-routes", type=Path)
    ap.add_argument("--quick", action="store_true", help="coarser ambiguity profile (development)")
    args = ap.parse_args()
    meta = json.loads((args.lut_dir / "hs_lut_meta.json").read_text())
    lut = HsLut(dict(theta_deg=np.array(meta["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["meta"]["phi_deg"][2]), s=np.load(args.lut_dir / "hs_lut_2deg.npy")))
    emp = empirical(args)
    sched = (("P0", "none"), ("T60", "60"), ("T20", "20"), ("T10", "10"))
    cases = [("R1", "A", lat, f"timeline_y{lat:g}_T{{}}.csv", args.s1) for lat in (0.0, 0.35)]
    cases += [(r, an, 0.0, f"timeline_{r}_T{{}}.csv", args.s1 / "routes") for r in ("R2", "R4", "R5") for an in ("A", "B")]
    base_name = {"odom_imu": "odom_imu", "range": "range", "range_s": None}
    results = []
    for route, an, lat, pat, root in cases:
        setup = CorridorSetup(anchor_x_m=4.0 if an == "A" else 10.0)
        for mount in (0.0, 45.0):
            for sname, stag in sched:
                rows = read_rows(root / pat.format(stag if stag != "none" else "none"))
                rec = dict(route=route, anchor=an, lateral=lat, mount_deg=mount, schedule=sname, n_samples=len(rows))
                for cfgname, (ur, us) in (("odom_imu", (False, False)), ("range", (True, False)), ("range_s", (True, True))):
                    info, Jx, _ = information(rows, lut, setup.anchor_position, setup.robot_antenna_z_m, mount, ur, us)
                    rec[cfgname] = summarize_info(info, Jx, rows)
                    key_b = {"odom_imu": "odom_imu", "range": "range", "range_s": "range_s_P0" if sname == "P0" else f"range_s_P1_{sname}"}[cfgname]
                    e = emp.get((route, an, lat if route == "R1" else 0.0, mount, key_b))
                    if route != "R1" and e is None:
                        e = emp.get((route, an, lat, mount, key_b))
                    if e is not None:
                        rec[cfgname]["empirical_median_heading_rmse_deg"] = e
                rec["ambiguity"] = ambiguity_profile(rows, lut, setup.anchor_position, setup.robot_antenna_z_m, mount) if sname == "P0" else None
                results.append(rec)
                print(route, an, lat, mount, sname, "psi_std(range_s)=%.2f deg" % rec["range_s"]["heading_std_common_mean_deg"], flush=True)
    args.out.write_text(json.dumps(dict(definition="A16 part B", sig_r2=SIG_R2, sig_s2=SIG_S2, p0_std=P0_STD.tolist(), results=results), indent=1))


if __name__ == "__main__":
    main()
