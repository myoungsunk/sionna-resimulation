"""G1-FLOOR-001 Step 1 reference implementation (S1-0 inventory, S1-1 parity, S1-2 sweep inversion).

Reference only: the spec (SPEC_KO.md) governs. This script is a starting point to be modified, not a frozen executor.
Inputs are files extracted from git (see SPEC_KO.md section 1). Truth pose is used ONLY to build labels and, in the
primary arm, the station XY passed to the LoS model; the heading search never sees the true heading except through
the prior centre ``psi_true + e_prior`` drawn from N(0, sigma_prior).

Usage (one case):
  python -I step1_reference.py --case R2_aA_m0 --block-c DIR --freqs freqs_hz.npy --lut hs_lut_2deg.npy \
      --src DIR_WITH_qclean_uwb --out OUT_DIR [--snr-db 30 --seeds 0 1 2]
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def wrap180(a):
    return (np.asarray(a, float) + 180.0) % 360.0 - 180.0


def station_groups(samples, min_n=3, ndigits=4):
    """Same-XY pose groups (yaw sweeps). Returns list of index arrays in pose order."""
    g = collections.OrderedDict()
    for i, p in enumerate(samples):
        g.setdefault((round(p["x"], ndigits), round(p["y"], ndigits)), []).append(i)
    return [np.array(v) for v in g.values() if len(v) >= min_n]


def invert_sweep(L, lut, anchor, robot_z, mount, x0, y0, rel_deg, s_obs, prior_deg, window_deg, step_deg=0.25):
    """Least-squares absolute heading of the first pose of a sweep.

    rel_deg: relative yaw of each sweep pose w.r.t. the first pose (as the robot believes it, i.e. possibly IMU-perturbed).
    Returns (psi_hat, J_min, margin, n_valid). margin = (J_2nd - J_min)/J_min over minima separated by > 20 deg.
    """
    ok = np.isfinite(s_obs)
    if ok.sum() < 3:
        return np.nan, np.nan, np.nan, int(ok.sum())
    if window_deg >= 180:
        grid = np.arange(-180.0, 180.0, step_deg)
    else:
        grid = prior_deg + np.arange(-window_deg, window_deg + 1e-9, step_deg)
    G = grid[:, None] + rel_deg[None, ok]
    pred = L.s_model(lut, anchor, robot_z, np.full(G.shape, x0), np.full(G.shape, y0), np.radians(G), mount)
    J = np.nansum((pred - s_obs[None, ok]) ** 2, axis=1)
    k = int(np.argmin(J))
    far = np.abs(wrap180(grid - grid[k])) > 20.0
    margin = float((J[far].min() - J[k]) / max(J[k], 1e-12)) if far.any() else np.nan
    return float(wrap180(grid[k])), float(J[k]), margin, int(ok.sum())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--block-c", required=True, type=Path)
    ap.add_argument("--freqs", required=True, type=Path)
    ap.add_argument("--lut", required=True, type=Path)
    ap.add_argument("--src", required=True, type=Path, help="directory that contains the qclean_uwb package")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--snr-db", type=float, default=None, help="omit for noise-free")
    ap.add_argument("--seeds", type=int, nargs="*", default=[0])
    ap.add_argument("--prior-sigma", type=float, nargs="*", default=[2.0, 5.0])
    ap.add_argument("--windows", type=float, nargs="*", default=[180.0, 30.0, 10.0])
    ap.add_argument("--imu-k", type=float, nargs="*", default=[0.0, 0.0085],
                    help="relative-yaw error per degree of |rotation| (TB3 trackA ~0.0076-0.0095)")
    ap.add_argument("--spans", type=float, nargs="*", default=[90.0, 40.0], help="sub-span (deg, centred) of each sweep")
    a = ap.parse_args(argv)

    sys.path.insert(0, str(a.src))
    from qclean_uwb.drivesim import hs_lut as L
    from qclean_uwb.drivesim import observation as O

    cases = {c["case"]: c for c in json.loads((a.block_c / "CASES.json").read_text())}
    c = cases[a.case]
    route = a.case.split("_")[0]
    p_full = a.block_c / "FULL_RF" / f"H_{a.case}.npy"
    p_los = a.block_c / f"H_LoS_{a.case}.npy"
    p_smp = a.block_c / a.case / "SAMPLES.json"
    inputs = {str(p): sha256(p) for p in (p_full, p_los, p_smp, a.freqs, a.lut)}
    # S1-0 hash gate: CASES.json H_sha256 = LoS H, input_H_sha256 = full H
    assert inputs[str(p_los)] == c["H_sha256"], "LoS H sha mismatch"
    assert inputs[str(p_full)] == c["input_H_sha256"], "full H sha mismatch"

    f = np.load(a.freqs)
    H, HL = np.load(p_full), np.load(p_los)
    S = json.loads(p_smp.read_text())
    assert H.shape == HL.shape == (len(S), 257, 2, 2)
    meta_th, meta_ph = np.arange(0.0, 90.0 + 1e-9, 2.0), np.arange(-180.0, 180.0, 2.0)
    lut = L.HsLut(dict(theta_deg=meta_th, phi_deg=meta_ph, s=np.load(a.lut)))
    anchor, z, mount = tuple(c["anchor_xyz"]), float(c["robot_z"]), float(c["mount_deg"])
    x = np.array([p["x"] for p in S]); y = np.array([p["y"] for p in S]); yaw = np.array([p["yaw_body_deg"] for p in S])

    groups = station_groups(S)
    a.out.mkdir(parents=True, exist_ok=True)

    # S1-1 parity (noise-free LoS H vs LUT)
    sL0 = O.observe(HL, f, None, None, tx=0)["s"]
    sM = L.s_model(lut, anchor, z, x, y, np.radians(yaw), mount)
    d = np.abs(sL0 - sM)
    parity = dict(median_abs=float(np.nanmedian(d)), p90_abs=float(np.nanpercentile(d, 90)), n=int(np.isfinite(d).sum()))
    parity["pass"] = parity["median_abs"] <= 0.005 and parity["p90_abs"] <= 0.02

    rows = []
    noise_arms = [None] if a.snr_db is None else [a.snr_db]
    for snr in noise_arms:
        nv = O.noise_var_from_snr(snr) if snr is not None else None
        for seed in (a.seeds if snr is not None else [0]):
            rng = np.random.default_rng(seed)
            sF = O.observe(H, f, nv, rng, tx=0)["s"]
            sL = O.observe(HL, f, nv, rng, tx=0)["s"]
            for gi, v in enumerate(groups):
                rel_true = wrap180(yaw[v] - yaw[v[0]])
                centre = rel_true.mean()
                for span in a.spans:
                    m = np.abs(rel_true - centre) <= span / 2 + 1e-6
                    vv, rt = v[m], rel_true[m]
                    for k_imu in a.imu_k:
                        # IMU-believed relative yaw: error grows with |rotation| from the first pose (sign fixed, TB3-like)
                        rel_bel = rt + k_imu * np.abs(rt)
                        for sp in a.prior_sigma:
                            e_prior = float(rng.normal(0.0, sp))
                            prior = yaw[v[0]] + e_prior
                            for w in a.windows:
                                for chan, s_obs in (("full", sF[vv]), ("los", sL[vv])):
                                    psi, J, marg, n = invert_sweep(L, lut, anchor, z, mount, x[v[0]], y[v[0]],
                                                                   rel_bel, s_obs, prior, w)
                                    rows.append(dict(case=a.case, route=route, group=gi, x=x[v[0]], y=y[v[0]],
                                                     dist_xy=math.hypot(x[v[0]] - anchor[0], y[v[0]] - anchor[1]),
                                                     snr_db=snr, seed=seed, span_deg=span, n_pose=len(vv), imu_k=k_imu,
                                                     prior_sigma=sp, e_prior=e_prior, window=w, channel=chan,
                                                     err_deg=float(wrap180(psi - yaw[v[0]])) if np.isfinite(psi) else np.nan,
                                                     J=J, margin=marg, n_valid=n))
    out_csv = a.out / f"S1_SWEEP_ERRORS_{a.case}.csv"
    with open(out_csv, "w", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wtr.writeheader(); wtr.writerows(rows)
    inv = dict(case=a.case, n_pose=len(S), n_groups=len(groups),
               group_sizes=[int(len(v)) for v in groups],
               group_span_deg=[float(np.ptp(wrap180(yaw[v] - yaw[v[0]]))) for v in groups])
    manifest = dict(spec="G1-FLOOR-001", step="S1-0..S1-2 reference", case=a.case, parity=parity, inventory=inv,
                    inputs=inputs, src_files={str(p): sha256(p) for p in
                                              [a.src / "qclean_uwb/drivesim/observation.py", a.src / "qclean_uwb/drivesim/hs_lut.py"]},
                    outputs={str(out_csv): sha256(out_csv)}, args=vars(a) | {"block_c": str(a.block_c), "freqs": str(a.freqs),
                                                                              "lut": str(a.lut), "src": str(a.src), "out": str(a.out)},
                    command=sys.argv, timestamp_utc=dt.datetime.now(dt.timezone.utc).isoformat())
    (a.out / f"S1_MANIFEST_{a.case}.json").write_text(json.dumps(manifest, indent=1, default=str))
    print(json.dumps(dict(parity=parity, n_rows=len(rows), n_groups=len(groups)), indent=1))


if __name__ == "__main__":
    main()
