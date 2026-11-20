"""Along-route correlation of the s error at packet scale (RT Corridor routes R2/R4/R5, case *_aB_m0, full channel e_s = s_full - s_LoS).
Two versions: raw e_s, and e_s after removing the smooth heading part -a*dbar(rho, side) (dbar from the station sweeps, distance-weighted).
Autocorrelation vs along-track lag; integrated autocorrelation tau = 1 + 2*sum rho_k (k up to first zero crossing) = factor by which a white-noise
assumption overstates information; compared with the filter's GM factor alpha = exp(-|ds|/1 m - turn/10 deg)."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/m8cal")
from feats import FZ
from common import env
e0 = env(); base, spec = e0["model"], e0["spec"]
O = pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz", usecols=["case", "channel", "pose_id", "x_eval", "y_eval", "yaw_eval_rad", "e_s"])
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy"); SW["sL"] = SW.s_fp - ES0
SW["pos"] = SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str); SW = SW.sort_values(["pos", "yaw_deg"]); psi = np.radians(np.arange(-180, 180, 10.))
w = lambda a: (a + np.pi / 2) % np.pi - np.pi / 2
def chi(s): c = 2 * np.mean(s * np.cos(2 * psi)); d = 2 * np.mean(s * np.sin(2 * psi)); return 0.5 * np.arctan2(c, -d)
st = SW.groupby("pos").apply(lambda g: pd.Series(dict(rho=g.rho.iloc[0], side=np.sign(g.x_eval.iloc[0] - 10), d=w(chi(g.s_fp.values) - chi(g.sL.values)))))
st = st[st.rho < 6]
def dbar(rho, side):
    q = st[st.side == side]; wt = np.exp(-0.5 * ((q.rho.values - rho) / 0.75)**2); return np.sum(wt * q.d.values) / np.sum(wt) if rho < 6 else 0.
def tau_int(r):
    k = np.argmax(r[1:] <= 0) + 1 if np.any(r[1:] <= 0) else len(r); return 1 + 2 * np.sum(r[1:k])
rows = []
for r in ("R2", "R4", "R5"):
    g = O[(O.case == f"{r}_aB_m0") & (O.channel == "full")].sort_values("pose_id").reset_index(drop=True)
    X = np.c_[g.x_eval, g.y_eval, g.yaw_eval_rad, np.zeros(len(g))]; J = base.batch(X, spec)[1][:, 1, 2]
    rho = np.hypot(g.x_eval - 10, g.y_eval).values; sd = np.sign(g.x_eval.values - 10)
    db = np.array([dbar(a, b) for a, b in zip(rho, sd)]); e_raw = g.e_s.values; e_rm = e_raw + J * db   # e = -a*delta  -> remove -a*dbar
    step = np.r_[0, np.hypot(np.diff(g.x_eval), np.diff(g.y_eval))]; turn = np.r_[0, np.abs(w(2 * np.diff(g.yaw_eval_rad)) / 2)]
    alpha = np.exp(-step / 1.0 - turn / np.radians(10.))
    for b, (lo, hi) in enumerate(((0, 3), (3, 6), (6, 10))):
        m = (rho >= lo) & (rho < hi)
        segs = np.split(np.arange(len(g)), np.flatnonzero(np.diff(m.astype(int)) != 0) + 1); segs = [s for s in segs if m[s[0]] and len(s) > 60]
        for lab, e in (("raw", e_raw), ("minus_dbar", e_rm)):
            acc = np.zeros(61); cnt = np.zeros(61)
            for s in segs:
                z = e[s] - e[s].mean()
                for k in range(61):
                    if k < len(z): acc[k] += np.sum(z[:len(z) - k] * z[k:]); cnt[k] += len(z) - k
            rk = (acc / cnt) / (acc[0] / cnt[0]); stp = np.median(step[np.concatenate(segs)]) if segs else np.nan
            ag = np.concatenate([np.cumprod(alpha[s][1:])[:0] for s in segs]) if segs else []
            a_med = np.median(alpha[np.concatenate(segs)]) if segs else np.nan
            rows.append(dict(route=r, bin=["<3 m", "3-6 m", ">=6 m"][b], series=lab, n=int(sum(len(s) for s in segs)), step_m=stp, rms=np.sqrt(acc[0] / cnt[0]),
                             r1=rk[1], r5=rk[5], r10=rk[10], r25=rk[25], r50=rk[50], tau_int=tau_int(rk),
                             lag_at_0p5_m=(np.argmax(rk < 0.5) * stp if np.any(rk < 0.5) else np.nan),
                             tau_filter_GM=(1 + a_med) / (1 - a_med)))
R = pd.DataFrame(rows); pd.set_option("display.width", 250); print(R.round(3).to_string(index=False)); R.to_csv("ROUTE_CORR_CHECK.csv", index=False)
