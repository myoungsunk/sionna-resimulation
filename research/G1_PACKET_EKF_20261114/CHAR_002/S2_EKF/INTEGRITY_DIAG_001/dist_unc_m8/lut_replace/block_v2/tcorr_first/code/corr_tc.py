"""Pair correlations on N1-N6 residuals. Polarisation: arc length L (rotation < 2 deg) and yaw length Y (move < 2 cm) per rho bin.
Range: correlated fraction f and length l along |dd| (true range change); axis comparison dd vs darc vs dt by leave-one-route-out pair score."""
import numpy as np, pandas as pd, json
Q = pd.read_csv("N1N6_RESID.csv.gz"); EDG = [0, 3, 6, 99]; BN = ["<3", "3-6", ">=6"]
def pairs(q, tmax=10.):
    t = q.t.values; i, j = np.triu_indices(len(q), 1); k = (t[j] - t[i]) <= tmax; return i[k], j[k]
def e_len(lag, c, f=1.0, minn=None):
    """lag where corr first drops below f/e (linear interpolation)"""
    thr = f / np.e
    for k in range(1, len(lag)):
        if c[k] < thr <= c[k - 1]: return float(lag[k - 1] + (c[k - 1] - thr) / (c[k - 1] - c[k]) * (lag[k] - lag[k - 1]))
    return np.nan
res = []; PR = {}
for r, q in Q.groupby("route"):
    q = q.reset_index(drop=True); i, j = pairs(q); b = np.clip(np.searchsorted(EDG, q.rho.values[i], side="right") - 1, 0, 2)
    darc = np.abs(q.arc.values[j] - q.arc.values[i]); dyaw = np.degrees(np.abs(q.yawc.values[j] - q.yawc.values[i])); dd = np.abs(q.d.values[j] - q.d.values[i]); dt = q.t.values[j] - q.t.values[i]
    PR[r] = (q, i, j, b, darc, dyaw, dd, dt)
    for bi in range(3):
        sel = b == bi
        if sel.sum() < 50: continue
        zs = q.r_s.values; zr = q.r_r.values
        def corr_curve(x, m, v, edges):
            lag, c = [], []
            for lo, hi in zip(edges[:-1], edges[1:]):
                k = m & (x > lo) & (x <= hi)
                if k.sum() >= 30: lag.append(.5 * (lo + hi)); c.append(np.corrcoef(v[i[k]], v[j[k]])[0, 1])
            return np.array(lag), np.array(c)
        la, ca = corr_curve(darc, sel & (dyaw < 2), zs, np.arange(0, 2.04, .04))
        ly, cy = corr_curve(dyaw, sel & (darc < .02), zs, np.arange(0, 95, 5.))
        lr, cr = corr_curve(dd, sel, zr, np.r_[0, np.arange(.005, .505, .01)])
        f = cr[0] if len(cr) else np.nan
        res.append(dict(route=r, bin=BN[bi], L_arc_m=e_len(la, ca) if len(la) > 1 else np.nan, n_arc=int((sel & (dyaw < 2)).sum()),
                        Y_deg=e_len(ly, cy) if len(ly) > 1 else np.nan, n_yaw=int((sel & (darc < .02)).sum()), yaw_c1=float(cy[0]) if len(cy) else np.nan,
                        f_r=float(f), l_r_m=e_len(lr, cr, f=f) if len(lr) > 1 else np.nan, rr_c_at_0p1=float(np.interp(.1, lr, cr)) if len(lr) > 1 else np.nan))
R = pd.DataFrame(res); pd.set_option("display.width", 220); print(R.round(3).to_string(index=False))
M = R.groupby("bin")[["L_arc_m", "Y_deg", "f_r", "l_r_m"]].agg(["median", "min", "max", "count"]); print(M.round(3).to_string())
# axis comparison for range: LORO pair score
def score(axis_name, x_of):
    out = []
    for hold in PR:
        tr = [k for k in PR if k != hold]; X, P = [], []
        for k in tr:
            q, i, j, b, darc, dyaw, dd, dt = PR[k]; z = (q.r_r.values - q.r_r.mean()) / q.r_r.std(); X.append(x_of(darc, dyaw, dd, dt)); P.append(z[i] * z[j])
        X, P = np.concatenate(X), np.concatenate(P)
        best = None
        for l in np.geomspace(.005, 20, 60):
            for f in np.linspace(.05, 1, 20):
                s = np.mean((P - f * np.exp(-X / l))**2)
                if best is None or s < best[0]: best = (s, f, l)
        q, i, j, b, darc, dyaw, dd, dt = PR[hold]; z = (q.r_r.values - q.r_r.mean()) / q.r_r.std(); x = x_of(darc, dyaw, dd, dt)
        out.append(dict(axis=axis_name, hold=hold, f=best[1], l=best[2], test=np.mean((z[i] * z[j] - best[1] * np.exp(-x / best[2]))**2), null=np.mean((z[i] * z[j])**2)))
    return pd.DataFrame(out)
S = pd.concat([score("dd_m", lambda a, y, d, t: d), score("darc_m", lambda a, y, d, t: a), score("dt_s", lambda a, y, d, t: t),
               score("arc+yaw/10deg", lambda a, y, d, t: a + y / 10.)])
print(S.groupby("axis")[["f", "l", "test", "null"]].median().round(4).to_string()); print(S.pivot(index="hold", columns="axis", values="test").round(4).to_string())
R.to_csv("CORR_ROUTES.csv", index=False); S.to_csv("RANGE_AXIS_LORO.csv", index=False)
