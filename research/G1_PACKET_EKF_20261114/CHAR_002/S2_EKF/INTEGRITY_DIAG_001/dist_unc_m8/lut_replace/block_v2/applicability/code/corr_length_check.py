"""Correlation length of the s error, quantified from RT Corridor station sweeps, vs what the filter assumes and how routes sample it.
Fields at the same world yaw: e = s_full - s_LoS (raw), heading scatter (station delta minus distance-smoothed dbar), non-heading residual
(e after removing the station's own 2-psi heading shift and gain). Lags: x 0.45/0.9/1.35/1.8 m (columns), y 0.15/0.3/0.45/0.6/0.75/0.9 m (lines),
psi 10/20/30/60/90 deg (within station). Routes: along-track step, yaw step between packets (truth)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8")
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); SW["sL"] = SW.s_fp - ES0
xs = np.sort(SW.x_eval.round(3).unique()); ys = np.sort(SW.y_eval.round(2).unique()); ps = np.sort(SW.yaw_deg.unique())
ix = np.searchsorted(xs, SW.x_eval.round(3)); iy = np.searchsorted(ys, SW.y_eval.round(2)); ip = np.searchsorted(ps, SW.yaw_deg)
def cube(v): C = np.full((len(xs), len(ys), 36), np.nan); C[ix, iy, ip] = v; return C
F, L, A = cube(SW.s_fp.values), cube(SW.sL.values), cube(SW.a.values); RHO = np.full((len(xs), len(ys)), np.nan); RHO[ix, iy] = SW.rho.values
psi = np.radians(ps); side = np.sign(xs - 10.0); k2 = np.fft.rfftfreq(36, 1 / 36); w = lambda a: (a + np.pi / 2) % np.pi - np.pi / 2
def chiL(s): c = 2 * np.mean(s * np.cos(2 * psi)); d = 2 * np.mean(s * np.sin(2 * psi)); return 0.5 * np.arctan2(c, -d), np.hypot(c, d)
E = F - L; D = np.zeros(F.shape[:2]); RES = np.zeros_like(F)
for i in range(len(xs)):
    for j in range(len(ys)):
        cf, lf = chiL(F[i, j]); cl, ll = chiL(L[i, j]); D[i, j] = w(cf - cl)
        rot = np.fft.irfft(np.fft.rfft(L[i, j]) * np.exp(-1j * k2 * D[i, j]), n=36) * (lf / ll); RES[i, j] = F[i, j] - rot
# heading scatter: minus distance-smoothed mean (same side, 0.75 m Gaussian in rho, leave-self-out)
DS = np.zeros_like(D)
for i in range(len(xs)):
    for j in range(len(ys)):
        m = (side[:, None] == side[i]) & np.ones_like(D, bool); m[i, j] = False
        wt = np.exp(-0.5 * ((RHO - RHO[i, j]) / 0.75)**2) * m; DS[i, j] = D[i, j] - np.sum(wt * D) / np.sum(wt)
BIN = np.clip(np.searchsorted([0, 3, 6, 10], RHO, side="right") - 1, 0, 2); names = ["<3 m", "3-6 m", ">=6 m"]
def corr_pairs(pairs):
    a = np.array(pairs); return np.corrcoef(a.T)[0, 1] if len(a) > 10 else np.nan
out = []
for b in range(3):
    row = dict(bin=names[b])
    for lab, Z, perpsi in (("e", E, True), ("res", RES, True), ("dscat", DS, False)):
        for dx in (1, 2, 3, 4):
            pr = []
            for i in range(len(xs) - dx):
                for j in range(len(ys)):
                    if side[i] != side[i + dx] or BIN[i, j] != b: continue
                    if perpsi: pr += list(zip(Z[i, j], Z[i + dx, j]))
                    else: pr.append((Z[i, j], Z[i + dx, j]))
            row[f"{lab}_x{0.45 * dx:.2f}"] = corr_pairs(pr)
        for (j1, j2) in [(0, 1), (3, 4), (1, 2), (2, 3), (0, 2), (2, 4), (1, 3), (0, 3), (1, 4), (0, 4)]:
            dy = round(abs(ys[j2] - ys[j1]), 2); pr = []
            for i in range(len(xs)):
                if BIN[i, j1] != b: continue
                if perpsi: pr += list(zip(Z[i, j1], Z[i, j2]))
                else: pr.append((Z[i, j1], Z[i, j2]))
            row.setdefault(f"{lab}_y{dy:.2f}", []).append(pr)
    for k in list(row):
        if isinstance(row[k], list): row[k] = corr_pairs([p for q in row[k] for p in q])
    for lab, Z in (("e", E), ("res", RES)):
        for dp in (1, 2, 3, 6, 9):
            pr = []
            for i in range(len(xs)):
                for j in range(len(ys)):
                    if BIN[i, j] == b: pr += list(zip(Z[i, j], np.roll(Z[i, j], -dp)))
            row[f"{lab}_psi{10 * dp}"] = corr_pairs(pr)
    out.append(row)
T = pd.DataFrame(out).set_index("bin").T; pd.set_option("display.width", 200); print(T.round(2).to_string())
# routes: sampling step between packets (truth)
from common import TRUTH, packet
for r in ("R2", "R4", "R5"):
    T_ = TRUTH[r]["truth"]; p = packet("B0", 10, r); dsx = np.hypot(np.diff(T_[:, 0]), np.diff(T_[:, 1])); dpsi = np.degrees(np.abs(w(2 * np.diff(T_[:, 2])) / 2))
    print(r, "packets", len(T_), "dt median %.3f s" % np.median(np.diff(p["t"])), "step median %.3f m (p90 %.3f)" % (np.median(dsx), np.quantile(dsx, .9)),
          "yaw step median %.2f deg (p90 %.2f)" % (np.median(dpsi), np.quantile(dpsi, .9)), "length %.1f m, total turn %.0f deg" % (dsx.sum(), dpsi.sum()))
