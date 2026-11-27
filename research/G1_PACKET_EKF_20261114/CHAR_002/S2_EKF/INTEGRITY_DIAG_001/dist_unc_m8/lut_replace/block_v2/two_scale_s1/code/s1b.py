"""S1b: N1-N6 route pairs, label A (FFD) and B (fullco block). Uncentered correlation vs darc (straight pairs), |a| tercile classes."""
import sys, numpy as np, pandas as pd
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0", "/home/claude/v1"]
from common import env; import h_ref as HR, sw_block_fullco as SB
Q = pd.read_csv("/home/claude/tc/N1N6_RESID.csv.gz"); e0 = env(); ffd = HR.ffd_s_fn(e0["model"]); blk = SB.SWB().s_fn()
st = np.c_[Q.x_eval, Q.y_eval, Q.yaw_eval_rad, np.zeros(len(Q))]
hF, JF = ffd(st, e0["spec"]); hB, JB = blk(st, None)
Q["eA"], Q["aA"], Q["eB"], Q["aB"] = Q.s_fp.values - hF, JF[:, 2], Q.s_fp.values - hB, JB[:, 2]
EDG = [0, 3, 6, 99]; BN = ["<3", "3-6", ">=6"]; LAG = np.r_[0.0, 0.04, 0.08, 0.12, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
def ucorr(x, y): return float(np.sum(x * y) / np.sqrt(np.sum(x * x) * np.sum(y * y)))
rows = []
for lab in ("A", "B"):
    acc = {}
    for r, q in Q.groupby("route"):
        q = q.sort_values("t").reset_index(drop=True); t = q.t.values; i, j = np.triu_indices(len(q), 1); k = (t[j] - t[i]) <= 30.; i, j = i[k], j[k]
        b = np.clip(np.searchsorted(EDG, q.rho.values[i], side="right") - 1, 0, 2); da = np.abs(q.arc.values[j] - q.arc.values[i]); dy = np.degrees(np.abs(q.yawc.values[j] - q.yawc.values[i]))
        e = q[f"e{lab}"].values; a = q[f"a{lab}"].values; aa = np.abs(a)
        for bi in range(3):
            m0 = (b == bi) & (dy < 2)
            if not m0.any(): continue
            qa = aa[np.clip(np.searchsorted(EDG, q.rho.values, side="right") - 1, 0, 2) == bi]; lo, hi = np.quantile(qa, [1 / 3, 2 / 3])
            for cls, sel, x in (("hi|a|: u=e/a", (aa[i] >= hi) & (aa[j] >= hi), e / np.where(aa > 1e-6, a, np.nan)), ("lo|a|: e", (aa[i] <= lo) & (aa[j] <= lo), e), ("all: e", np.ones(len(i), bool), e)):
                for L0, L1 in zip(LAG[:-1], LAG[1:]):
                    mm = m0 & sel & (da > L0) & (da <= L1)
                    acc.setdefault((BN[bi], cls, L1), ([], [])); acc[(BN[bi], cls, L1)][0].append(x[i[mm]]); acc[(BN[bi], cls, L1)][1].append(x[j[mm]])
    for (bn, cls, L1), (xs, ys) in acc.items():
        x, y = np.concatenate(xs), np.concatenate(ys); ok = np.isfinite(x) & np.isfinite(y); x, y = x[ok], y[ok]
        if len(x) < 50: continue
        rows.append(dict(label=lab, bin=bn, cls=cls, lag_hi=L1, n=len(x), u=ucorr(x, y), c=float(np.corrcoef(x, y)[0, 1]), mean_over_rms=float(np.mean(np.r_[x, y]) / np.sqrt(np.mean(np.r_[x, y] ** 2)))))
R = pd.DataFrame(rows); R.to_csv("S1B_ROUTE_CORR.csv", index=False)
def e_len(g):
    g = g.sort_values("lag_hi"); lag, u = g.lag_hi.values, g.u.values
    for k in range(1, len(lag)):
        if u[k] < 1 / np.e <= u[k - 1]: return lag[k - 1] + (u[k - 1] - 1 / np.e) / (u[k - 1] - u[k]) * (lag[k] - lag[k - 1])
    return np.nan if u[0] < 1 / np.e else np.inf
S = R.groupby(["label", "bin", "cls"]).apply(lambda g: pd.Series(dict(L_e=e_len(g), plateau_1to3m=g[(g.lag_hi > 1.0) & (g.lag_hi <= 3.0)].u.mean(), u_at_0p2=g[g.lag_hi == 0.2].u.mean(), u_at_0p5=g[g.lag_hi == 0.5].u.mean(), u_at_1=g[g.lag_hi == 1.0].u.mean(), mean_over_rms=g.mean_over_rms.mean()))).reset_index()
S.to_csv("S1B_SUMMARY.csv", index=False); pd.set_option("display.width", 220); print(S.round(3).to_string(index=False))
