"""Light feasibility check (RT Corridor station sweeps, LoS truth available): spatial averaging of s_full at fixed world yaw
as a multipath-excluded block. Window = +-k x-columns (0.45 m step, same anchor side) x {same y line | all 5 lines}, with or without the centre column.
Per centre station, over 36 yaws:  sbar(psi) - s_LoS(psi) = c - a_LoS*delta - kappa*s_LoS + r   (heading-equivalent shift delta, gain kappa).
Also: LoS blur alone (window mean of s_LoS vs centre s_LoS), and prediction of the held-out s_full by sbar vs by s_LoS.
LoS-free diagnostic: per-station deviation delta_dev of s_full from the centre-excluded window mean (derivative of sbar via Fourier),
and its lag-1 autocorrelation along x (fast phase rotation -> low autocorrelation)."""
import numpy as np, pandas as pd
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
SW["sL"] = SW.s_fp - ES0
xs = np.sort(SW.x_eval.round(3).unique()); ys = np.sort(SW.y_eval.round(2).unique()); ps = np.sort(SW.yaw_deg.unique())
ix = np.searchsorted(xs, SW.x_eval.round(3)); iy = np.searchsorted(ys, SW.y_eval.round(2)); ip = np.searchsorted(ps, SW.yaw_deg)
def cube(v): C = np.full((len(xs), len(ys), len(ps)), np.nan); C[ix, iy, ip] = v; return C
F, L, A, RHO = cube(SW.s_fp.values), cube(SW.sL.values), cube(SW.a.values), cube(SW.rho.values)[:, :, 0]
side = np.sign(xs - 10.0); BIN = np.clip(np.searchsorted([0, 3, 6, 10], RHO, side="right") - 1, 0, 2)
psi = np.radians(ps); kfreq = np.fft.rfftfreq(36, d=1 / 36)
def dpsi(s): return np.fft.irfft(1j * kfreq * np.fft.rfft(s), n=36)  # d s / d psi (psi period 2 pi, 36 samples)
def fit(d, a, s):
    X = np.c_[np.ones(36), -a, -s]; b, *_ = np.linalg.lstsq(X, d, rcond=None); return np.degrees(b[1]), b[2], d - X @ b
def window(C, i, j, k, lines, centre):
    cols = [q for q in range(i - k, i + k + 1) if 0 <= q < len(xs) and side[q] == side[i] and (centre or q != i)]
    rows = range(len(ys)) if lines == "all" else [j]
    return np.nanmean(np.stack([C[q, r] for q in cols for r in rows]), axis=0) if cols else None
rows = []
for k in (0, 1, 2, 3):
    for lines in ("same", "all"):
        for centre in (True, False):
            if k == 0 and (not centre or lines == "same"): 
                if not (k == 0 and lines == "same" and centre): continue
            for i in range(len(xs)):
                for j in range(len(ys)):
                    sb = window(F, i, j, k, lines, centre); lb = window(L, i, j, k, lines, centre)
                    if sb is None: continue
                    dl, kp, rr = fit(sb - L[i, j], A[i, j], L[i, j]); db, kb, _ = fit(lb - L[i, j], A[i, j], L[i, j])
                    rows.append(dict(k=k, lines=lines, centre=centre, bin=int(BIN[i, j]), delta=dl, kappa=kp, resid_rms=np.sqrt(np.mean(rr**2)),
                                     blur_delta=db, blur_kappa=kb, raw_rms=np.sqrt(np.mean((sb - L[i, j])**2)),
                                     pred_full_by_sbar=np.sqrt(np.mean((F[i, j] - sb)**2)), pred_full_by_LoS=np.sqrt(np.mean((F[i, j] - L[i, j])**2))))
D = pd.DataFrame(rows); D["bin"] = D.bin.map({0: "<3 m", 1: "3-6 m", 2: ">=6 m"})
g = D.groupby(["bin", "k", "lines", "centre"])
T = pd.DataFrame(dict(n=g.size(), delta_mean=g.delta.mean(), delta_sd=g.delta.std(), blur_delta_sd=g.blur_delta.std(), kappa_mean=g.kappa.mean(),
                      resid_rms=g.resid_rms.mean(), sbar_vs_LoS_rms=g.raw_rms.apply(lambda v: np.sqrt(np.mean(v**2))),
                      fullpred_sbar=g.pred_full_by_sbar.apply(lambda v: np.sqrt(np.mean(v**2))), fullpred_LoS=g.pred_full_by_LoS.apply(lambda v: np.sqrt(np.mean(v**2))))).reset_index()
pd.set_option("display.width", 250); print(T.round(3).to_string(index=False)); T.to_csv("SPATIAL_AVG_CHECK.csv", index=False)
# LoS-free diagnostic vs truth: per-station delta relative to centre-excluded window mean (k=1, all lines), and relative to LoS (truth)
out = []
for i in range(len(xs)):
    for j in range(len(ys)):
        sb = window(F, i, j, 1, "all", False)
        if sb is None: continue
        dd, _, _ = fit(F[i, j] - sb, dpsi(sb), sb); dt, _, _ = fit(F[i, j] - L[i, j], A[i, j], L[i, j])
        out.append(dict(i=i, j=j, bin=int(BIN[i, j]), d_dev=dd, d_true=dt))
O = pd.DataFrame(out)
def lag1(col):
    v = []
    for b in range(3):
        x1, x2 = [], []
        for j in range(len(ys)):
            S = O[(O.j == j)].set_index("i")[col]
            for i in S.index:
                if i + 1 in S.index and BIN[i, j] == b and side[i] == side[i + 1]: x1.append(S[i]); x2.append(S[i + 1])
        v.append(np.corrcoef(x1, x2)[0, 1])
    return v
print("lag-1 autocorr along x (bins <3, 3-6, >=6): LoS-free d_dev", np.round(lag1("d_dev"), 2), " truth d_true", np.round(lag1("d_true"), 2))
print(O.groupby("bin")[["d_dev", "d_true"]].agg(["mean", "std"]).round(2)); print("corr(d_dev, d_true) by bin", O.groupby("bin").apply(lambda q: np.corrcoef(q.d_dev, q.d_true)[0, 1]).round(2).to_dict())
