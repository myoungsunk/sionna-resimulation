"""S1a: spatial correlation of station components (label A: e = s_full - h_FFD), corridor sweep 40 cols x 5 rows x 36 yaw."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/bvb"); from load import load
D = load(); rows = []; shape = {}
for (c, r), g in D.groupby(["col", "row"]):
    g = g.sort_values("yaw"); X = np.c_[np.ones(len(g)), g.a, g.h]; beta, *_ = np.linalg.lstsq(X, g.e.values, rcond=None)
    rows.append(dict(col=c, row=r, x=g.x.iloc[0], y=g.y.iloc[0], rho=g.rho.iloc[0], side=g.side.iloc[0], b=g.b.iloc[0], off=beta[0], dlt=np.degrees(beta[1]), kap=beta[2]))
    shape[(c, r)] = g.e.values - X @ beta
S = pd.DataFrame(rows); cols = np.sort(S.col.unique()); rws = np.sort(S.row.unique()); BN = ["<3", "3-6", ">=6"]
def corr(x, y, centered):
    x, y = np.asarray(x, float), np.asarray(y, float)
    if centered: x, y = x - x.mean(), y - y.mean()
    return float(np.sum(x * y) / np.sqrt(np.sum(x * x) * np.sum(y * y)))
P = S.set_index(["col", "row"]); out = []
for kind, lags in (("x", [1, 2, 3, 4]), ("y", [1, 2])):
    for L in lags:
        pairs = []
        for (c, r), s in P.iterrows():
            if kind == "x":
                i = np.searchsorted(cols, c) + L
                if i >= len(cols): continue
                k = (cols[i], r)
            else:
                i = np.searchsorted(rws, r) + L
                if i >= len(rws): continue
                k = (c, rws[i])
            t = P.loc[k]
            if t.side != s.side or t.b != s.b: continue
            pairs.append(((c, r), k, int(s.b), abs(t.x - s.x) + abs(t.y - s.y)))
        for bi in range(3):
            pp = [p for p in pairs if p[2] == bi]
            if len(pp) < 8: continue
            sep = np.mean([p[3] for p in pp]); rec = dict(axis=kind, lag=L, sep_m=round(sep, 3), bin=BN[bi], n=len(pp))
            for v in ("dlt", "kap", "off"):
                a = [P.loc[p[0], v] for p in pp]; b = [P.loc[p[1], v] for p in pp]
                rec[f"{v}_u"] = corr(a, b, False); rec[f"{v}_c"] = corr(a, b, True)
            a = np.concatenate([shape[p[0]] for p in pp]); b = np.concatenate([shape[p[1]] for p in pp])
            rec["shape_u"] = corr(a, b, False); rec["shape_c"] = corr(a, b, True); out.append(rec)
R = pd.DataFrame(out); R.to_csv("S1A_STATION_CORR.csv", index=False); pd.set_option("display.width", 250)
print(R.round(2).to_string(index=False))
print(S.groupby("b")[["dlt", "kap", "off"]].agg(["mean", "std"]).round(3).to_string())
