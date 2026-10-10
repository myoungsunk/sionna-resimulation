"""Post-A23 descriptive check: split the R2-A real `s`/range residual into multipath (full H - LoS-only chain at the true pose)
and LoS-chain/LUT error (LoS-only chain - LUT at the true pose).  Inputs are the published A23 inputs (H, LUT, timeline, FFD banks).

Exploratory and descriptive: no thresholds, no adoption decision.  The LoS-only channel is synthesised from the FFD banks at the actual
link length (hs_lut.los_h); the L2 audit shows this matches Sionna max_depth=0 to <1e-6 on 8 poses, but it is not a Sionna LoS-only run on
this timeline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from qclean_uwb.drivesim import hs_lut as HL
from qclean_uwb.drivesim import observation as O
from qclean_uwb.drivesim import pattern_apply as P
from qclean_uwb.scenarios.corridor import CorridorSetup


def lag1(a):
    a = a - a.mean()
    return float((a[1:] * a[:-1]).sum() / (a * a).sum())


def stats(a):
    return dict(mean=float(a.mean()), rms=float(np.sqrt((a ** 2).mean())), sd=float(a.std()), lag1=lag1(a), max_abs=float(np.abs(a).max()), n=int(len(a)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", type=Path, required=True, help="A23 INPUTS dir (H, LUT, meta, freqs, timeline)")
    ap.add_argument("--banks", type=Path, required=True, help="dir with restored LP_plus45_bank.npz / LP_minus45_bank.npz")
    ap.add_argument("--h", default="H_R2_aA_m0.npy")
    ap.add_argument("--timeline", default="timeline_R2_Tnone.csv")
    ap.add_argument("--anchor-x", type=float, default=4.0)
    ap.add_argument("--mount", type=float, default=0.0)
    ap.add_argument("--exclude-s", type=float, default=30.0)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    freqs = np.load(a.inputs / "freqs_hz.npy")
    H = np.load(a.inputs / a.h, mmap_mode="r")
    meta = json.loads((a.inputs / "hs_lut_meta.json").read_text())
    lut = HL.HsLut(dict(theta_deg=np.array(meta["meta"]["theta_deg"]), phi_deg=np.arange(-180.0, 180.0, meta["meta"]["phi_deg"][2]), s=np.load(a.inputs / "hs_lut_2deg.npy")))
    off = meta["range_bias"]["mean_m"]
    banks = []
    for n in ("LP_plus45", "LP_minus45"):
        with np.load(a.banks / f"{n}_bank.npz") as z:
            banks.append(P.Bank({k: z[k] for k in z.files}))
    if not np.array_equal(banks[0].freqs_hz, freqs):
        raise SystemExit("BANK_FREQS_DIFFER")
    tl = pd.read_csv(a.inputs / a.timeline)
    cs = CorridorSetup(anchor_x_m=a.anchor_x)
    A, rz = cs.anchor_position, cs.robot_antenna_z_m
    x, y, yaw = tl.x.values, tl.y.values, tl.yaw_body_deg.values + a.mount * 0.0
    Hs = np.asarray(H[tl.pose_id.values])
    full = O.observe(Hs, freqs, None, None)
    d3 = np.empty(len(tl))
    Hl = np.empty_like(Hs)
    for i in range(len(tl)):
        d = np.array([x[i], y[i], rz]) - A
        d3[i] = np.linalg.norm(d)
        Hl[i] = HL.los_h(banks, d / d3[i], yaw[i] + a.mount, d3[i])
    los = O.observe(Hl, freqs, None, None)
    lut_s = HL.s_model(lut, A, rz, x, y, np.radians(yaw), a.mount)
    keep = (tl.t_s.values >= a.exclude_s) & np.isfinite(full["s"]) & np.isfinite(los["s"])
    tot, mp, lp = (full["s"] - lut_s)[keep], (full["s"] - los["s"])[keep], (los["s"] - lut_s)[keep]
    rt, rm, rl = (full["range_m"] - (d3 + off))[keep], (full["range_m"] - los["range_m"])[keep], (los["range_m"] - (d3 + off))[keep]
    dk = d3[keep]
    out = dict(
        scope="descriptive; exploratory; one case", h=a.h, n=int(keep.sum()),
        s=dict(total=stats(tot), multipath=stats(mp), los_chain_vs_lut=stats(lp),
               var_share=dict(multipath=float(mp.var() / tot.var()), los_chain_vs_lut=float(lp.var() / tot.var()), cross=float(2 * np.cov(mp, lp)[0, 1] / tot.var()))),
        range=dict(total=stats(rt), multipath=stats(rm), los_chain_vs_offset=stats(rl)),
        corr=dict(s_multipath_vs_range_multipath=float(np.corrcoef(mp, rm)[0, 1]), s_total_vs_range_total=float(np.corrcoef(tot, rt)[0, 1])),
        first_path_tap_differs_full_vs_los=float((full["index"][keep] != los["index"][keep]).mean()),
        by_distance={f"{lo}-{hi}": dict(n=int(((dk >= lo) & (dk < hi)).sum()), total_rms=float(np.sqrt((tot[(dk >= lo) & (dk < hi)] ** 2).mean())),
                                        multipath_rms=float(np.sqrt((mp[(dk >= lo) & (dk < hi)] ** 2).mean())), multipath_mean=float(mp[(dk >= lo) & (dk < hi)].mean()),
                                        los_chain_rms=float(np.sqrt((lp[(dk >= lo) & (dk < hi)] ** 2).mean()))) for lo, hi in ((0, 5), (5, 10), (10, 99))})
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(out, indent=1))
    print(json.dumps(out["s"], indent=1))


if __name__ == "__main__":
    main()
