"""Synthetic injection test of the pair-product regression (plan PLAN_SYNTH_KO.md)."""
import sys, json, numpy as np, pandas as pd
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0"]
from common import env; import h_ref as HR
Q = pd.read_csv("/home/claude/tc/N1N6_RESID.csv.gz"); e0 = env(); ffd = HR.ffd_s_fn(e0["model"])
st = np.c_[Q.x_eval, Q.y_eval, Q.yaw_eval_rad, np.zeros(len(Q))]; _, J = ffd(st, e0["spec"]); Q["a"] = J[:, 2]
EDG = [0, 3, 6, 99]; STH = np.radians([0.92, 3.25, 3.36]); SRES = np.array([0.011, 0.048, 0.161])
LB = np.array([0, .04, .08, .12, .2, .3, .5, .75, 1., 1.5, 2., 3., 4.]); BN = ["<3", "3-6", ">=6"]
R = []
for r, q in Q.groupby("route"):
    q = q.sort_values("t").reset_index(drop=True); t = q.t.values; i, j = np.triu_indices(len(q), 1); k = (t[j] - t[i]) <= 30.; i, j = i[k], j[k]
    b = np.clip(np.searchsorted(EDG, q.rho.values, side="right") - 1, 0, 2); da = np.abs(q.arc.values[j] - q.arc.values[i]); dy = np.degrees(np.abs(q.yawc.values[j] - q.yawc.values[i]))
    m = dy < 2; R.append(dict(q=q, b=b, i=i[m], j=j[m], da=da[m], bi=b[i[m]]))
_all = pd.concat([d['q'].assign(bb=d['b']) for d in R]); HI = [float(np.quantile(np.abs(_all.a[_all.bb == k]), 2 / 3)) for k in range(3)]  # |a| top-tercile threshold per bin over all routes
def ou(arc, L, rng):
    x = np.empty(len(arc)); x[0] = rng.standard_normal(); d = np.abs(np.diff(arc)); phi = np.exp(-d / L)
    w = rng.standard_normal(len(arc) - 1)
    for k in range(1, len(arc)): x[k] = phi[k - 1] * x[k - 1] + np.sqrt(1 - phi[k - 1] ** 2) * w[k - 1]
    return x
def synth(case, rng):
    Lt, Lr = {"T1": (1., .1), "T2": (.1, 1.), "T3": (.3, .3), "T4": (1., .1), "T5": (1., .1)}[case]; E = []
    for d in R:
        q, b = d["q"], d["b"]; a = q.a.values; arc = q.arc.values
        dl = STH[b] * ou(arc, Lt, rng); n = SRES[b] * ou(arc, Lr, rng)
        if case == "T4":
            for bi in range(3):
                mm = b == bi; n[mm & (np.abs(a) >= HI[bi])] *= np.sqrt(3.)
        if case == "T5": dl = dl + np.where(b == 1, np.radians(-2.5), 0.)
        E.append(a * dl + n)
    return E
def estimate(E):
    out = {}
    for bi in range(3):
        y0, x0 = [], []
        for d, e in zip(R, E):
            mm = d["b"] == bi; y0.append(e[mm] ** 2); x0.append(d["q"].a.values[mm] ** 2)
        y0, x0 = np.concatenate(y0), np.concatenate(x0); X = np.c_[x0, np.ones(len(x0))]; c0 = np.linalg.lstsq(X, y0, rcond=None)[0]
        rows = [(0., c0[0], c0[1], 1.)]
        for L0, L1 in zip(LB[:-1], LB[1:]):
            yy, xx = [], []
            for d, e in zip(R, E):
                mm = (d["bi"] == bi) & (d["da"] > L0) & (d["da"] <= L1); a = d["q"].a.values
                yy.append(e[d["i"][mm]] * e[d["j"][mm]]); xx.append(a[d["i"][mm]] * a[d["j"][mm]])
            yy, xx = np.concatenate(yy), np.concatenate(xx)
            if len(yy) < 50: continue
            X = np.c_[xx, np.ones(len(xx))]; cond = np.linalg.cond(X.T @ X / len(xx)); c = np.linalg.lstsq(X, yy, rcond=None)[0]
            rows.append((.5 * (L0 + L1), c[0], c[1], cond))
        out[bi] = np.array(rows)
    return out
def e_len(lag, rho):
    for k in range(1, len(lag)):
        if rho[k] < 1 / np.e <= rho[k - 1]: return lag[k - 1] + (rho[k - 1] - 1 / np.e) / (rho[k - 1] - rho[k]) * (lag[k] - lag[k - 1])
    return np.nan
res = []
for case in ("T1", "T2", "T3", "T4", "T5"):
    Lt, Lr = {"T1": (1., .1), "T2": (.1, 1.), "T3": (.3, .3), "T4": (1., .1), "T5": (1., .1)}[case]
    for rep in range(20):
        est = estimate(synth(case, np.random.default_rng(rep)))
        for bi in range(3):
            A = est[bi]; ok = A[:, 3] <= 10; lag, ct, cr = A[ok, 0], A[ok, 1], A[ok, 2]
            res.append(dict(case=case, rep=rep, bin=BN[bi], Lt_true=Lt, Lr_true=Lr, Lt_hat=e_len(lag, ct / ct[0]), Lr_hat=e_len(lag, cr / cr[0]),
                            s2t_ratio=ct[0] / STH[bi] ** 2, s2r_ratio=cr[0] / SRES[bi] ** 2 if case != "T4" else np.nan,
                            ct_plateau=float(np.mean(ct[(lag > 1) & (lag <= 4)]) / ct[0]) if np.any((lag > 1) & (lag <= 4)) else np.nan, max_lag_used=float(lag.max())))
D = pd.DataFrame(res); D.to_csv("SYNTH_REPS.csv", index=False)
S = D.groupby(["case", "bin"]).agg(Lt_true=("Lt_true", "first"), Lt_med=("Lt_hat", "median"), Lt_p10=("Lt_hat", lambda v: v.quantile(.1)), Lt_p90=("Lt_hat", lambda v: v.quantile(.9)),
                                   Lr_true=("Lr_true", "first"), Lr_med=("Lr_hat", "median"), Lr_p10=("Lr_hat", lambda v: v.quantile(.1)), Lr_p90=("Lr_hat", lambda v: v.quantile(.9)),
                                   s2t=("s2t_ratio", "median"), s2r=("s2r_ratio", "median"), plateau_t=("ct_plateau", "median"), maxlag=("max_lag_used", "median"), nan_Lt=("Lt_hat", lambda v: int(v.isna().sum()))).reset_index()
S["pass_L"] = (abs(S.Lt_med / S.Lt_true - 1) <= .3) & (abs(S.Lr_med / S.Lr_true - 1) <= .3)
S["pass_var"] = (abs(S.s2t - 1) <= .2) & ((abs(S.s2r - 1) <= .2) | S.s2r.isna())
S.to_csv("SYNTH_SUMMARY.csv", index=False); pd.set_option("display.width", 250); print(S.round(3).to_string(index=False))
