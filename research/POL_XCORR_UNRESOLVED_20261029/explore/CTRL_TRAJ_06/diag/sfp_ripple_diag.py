#!/usr/bin/env python3
"""Diagnose why the LoS-model LUT mismatches s_fp with the real banks: range ripple of s_fp from FP-tap quantisation.
Along y=0.3 at body yaw 0 (and 180), dense x step 5 mm: s_fp, window power ratio sW, Stokes S, tap index n0.
Also derivatives d/dx (ripple slope) vs d/dpsi (heading sensitivity)."""
import argparse, importlib.util, json, math, sys
from pathlib import Path
import numpy as np, pandas as pd
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('c6', HERE.parent / 'ctrl_traj_06.py'); C6 = importlib.util.module_from_spec(spec); spec.loader.exec_module(C6)
C2 = C6.C2
ap = argparse.ArgumentParser(); ap.add_argument('--bank-dir', required=True); ap.add_argument('--out', required=True); a = ap.parse_args()
out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
ant = C2.Antennas(C6.REPO, a.bank_dir); rows = []; summ = {}
xs = np.round(np.arange(4.2, 19.8001, 0.005), 4); n = len(xs)
for mount in (0, 45):
    for yb in (0, 180):
        for dpsi in (0.0, 1.0):
            xyz = np.column_stack([xs, np.full(n, 0.3), np.full(n, C6.ZR)])
            H = []
            for i in range(0, n, 1500):
                H.append(C2.channel(ant, C6.ANCHOR, xyz[i:i + 1500], np.full(min(1500, n - i), yb + mount + dpsi), []))
            H = np.concatenate(H, 1); S, n0, q, sfp = C2.observe(H)
            W = C6.taps(H); j11 = np.sum(abs(W[..., 0]) ** 2, 1); j22 = np.sum(abs(W[..., 1]) ** 2, 1); sW = (j11 - j22) / (j11 + j22)
            rows.append(pd.DataFrame({'mount': mount, 'yaw_body': yb, 'dpsi': dpsi, 'x': xs, 'n0': n0, 'sfp': sfp, 'sW': sW, 'S1': S[:, 0], 'S2': S[:, 1], 'S3': S[:, 2], 'q': q}))
D = pd.concat(rows); D.to_csv(out / 'SFP_RIPPLE.csv.gz', index=False)
for (mo, yb), g in D.groupby(['mount', 'yaw_body']):
    g0 = g[g.dpsi == 0].reset_index(drop=True); g1 = g[g.dpsi == 1].reset_index(drop=True); far = np.hypot(g0.x - 4, 0.3) > 6
    res = {}
    for c in ('sfp', 'sW', 'S1', 'S2', 'S3'):
        v = g0[c].to_numpy(); sm = pd.Series(v).rolling(61, center=True).mean().to_numpy()      # 30 cm smooth
        rip = v - sm; dx = np.gradient(v, 0.005); dpsi_ = (g1[c] - g0[c]).to_numpy()
        res[c] = {'ripple_rms_far': float(np.nanstd(rip[far])), 'ripple_pp_far': float(np.nanmax(rip[far]) - np.nanmin(rip[far])),
                  'abs_d_dx_med_far_per_m': float(np.median(abs(dx[far]))), 'abs_d_dpsi_med_far_per_deg': float(np.median(abs(dpsi_[far]))),
                  'equiv_heading_deg_per_cm_range': float(np.median(abs(dx[far])) * 0.01 / max(np.median(abs(dpsi_[far])), 1e-12))}
    res['n0_switches_far'] = int(np.sum(np.diff(g0.n0.to_numpy()[far]) != 0))
    summ[f'm{mo}_yb{yb}'] = res
(out / 'SUMMARY.json').write_text(json.dumps(summ, indent=1)); print(json.dumps(summ, indent=1))
