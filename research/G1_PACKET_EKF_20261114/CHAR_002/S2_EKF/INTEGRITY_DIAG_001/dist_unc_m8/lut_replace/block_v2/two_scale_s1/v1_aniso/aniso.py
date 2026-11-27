"""V1 anisotropy: uncentered correlation of 36-yaw error curves e(psi) vs separation along x (4 cm sweep + grid), y (grid rows), yaw (within station)."""
import sys, numpy as np, pandas as pd
sys.path[:0] = ["/home/claude/m8", "/home/claude/lut0", "/home/claude/bvb"]
from common import env; import h_ref as HR; from load import load
e0 = env(); ffd = HR.ffd_s_fn(e0["model"]); G = load(); BN = ["<3", "3-6", ">=6"]
def uc(a, b): a, b = np.ravel(a), np.ravel(b); return float(np.sum(a * b) / np.sqrt(np.sum(a * a) * np.sum(b * b)))
def comps(x, y, yaw, e):
    st = np.c_[np.full(36, x), np.full(36, y), np.radians(yaw), np.zeros(36)]; h, J = ffd(st, e0["spec"]); X = np.c_[np.ones(36), J[:, 2], h]
    return np.linalg.lstsq(X, e, rcond=None)[0]   # off, delta(rad), kappa
# grid curves
C = {}
for (c, r), g in G.groupby(["col", "row"]):
    g = g.sort_values("yaw"); C[(c, r)] = dict(x=g.x.iloc[0], y=g.y.iloc[0], rho=g.rho.iloc[0], b=int(g.b.iloc[0]), side=int(g.side.iloc[0]), e=g.e.values, yaw=g.yaw.values)
for k in C: C[k]["cmp"] = comps(C[k]["x"], C[k]["y"], C[k]["yaw"], C[k]["e"])
out = []
# fine x (4 cm sweep)
P = pd.read_csv("NEAR4CM_S.csv"); P["e"] = P.s_full - P.s_los
for xc, name in ((7.95, "P016 rho2.05"), (5.25, "P010 rho4.75"), (2.10, "P003 rho7.90")):
    cen = [v for v in C.values() if np.isclose(v["x"], xc) and np.isclose(v["y"], 0.)][0]
    xs = np.round(xc + np.arange(-0.16, 0.161, 0.04), 3); cur = {}
    for x in xs:
        if np.isclose(x, xc): cur[x] = (cen["e"], cen["cmp"])
        else:
            q = P[np.isclose(P.x, x)].sort_values("yaw_body_deg"); cur[x] = (q.e.values, comps(x, 0., q.yaw_body_deg.values, q.e.values))
    dsd = np.std([cur[x][1][1] for x in xs])
    for n in range(1, 9):
        pr = [(xs[i], xs[i + n]) for i in range(len(xs) - n)]
        out.append(dict(dir="x_fine", where=name, sep=0.04 * n, n=len(pr), curve_u=uc(np.concatenate([cur[a][0] for a, b in pr]), np.concatenate([cur[b][0] for a, b in pr])),
                        d_delta_deg=float(np.degrees(np.sqrt(np.mean([(cur[a][1][1] - cur[b][1][1]) ** 2 for a, b in pr])))), delta_sd_deg=float(np.degrees(dsd)),
                        delta_center_deg=float(np.degrees(cen["cmp"][1]))))
# grid x and y
cols = np.sort(G.col.unique()); rows = np.sort(G.row.unique())
for (c, r), v in C.items():
    i = np.searchsorted(cols, c)
    for n in range(1, 5):
        if i + n < len(cols):
            w = C[(cols[i + n], r)]
            if w["side"] == v["side"] and w["b"] == v["b"]: out.append(dict(dir="x_grid", where=BN[v["b"]], sep=round(abs(w["x"] - v["x"]), 2), pair=(v["e"], w["e"]), dd=np.degrees(v["cmp"][1] - w["cmp"][1])))
    for r2 in rows:
        if r2 > r:
            w = C[(c, r2)]
            if w["b"] == v["b"]: out.append(dict(dir="y_grid", where=BN[v["b"]], sep=round(abs(w["y"] - v["y"]), 2), pair=(v["e"], w["e"]), dd=np.degrees(v["cmp"][1] - w["cmp"][1])))
    for k in range(1, 10):
        out.append(dict(dir="yaw", where=BN[v["b"]], sep=10 * k, pair=(v["e"], np.roll(v["e"], -k)), dd=np.nan))
D = pd.DataFrame(out); F = D[D.dir == "x_fine"].drop(columns=["pair", "dd"], errors="ignore")
A = []
for (d, w, s), g in D[D.dir != "x_fine"].groupby(["dir", "where", "sep"]):
    A.append(dict(dir=d, where=w, sep=round(float(s), 3), n=len(g), curve_u=uc(np.concatenate([p[0] for p in g.pair]), np.concatenate([p[1] for p in g.pair])),
                  d_delta_deg=float(np.sqrt(np.nanmean(g.dd ** 2))) if d != "yaw" else np.nan))
A = pd.DataFrame(A)
def e_len(sep, u):
    for k in range(len(sep)):
        if u[k] < 1 / np.e: return float(sep[k] if k == 0 else sep[k - 1] + (u[k - 1] - 1 / np.e) / (u[k - 1] - u[k]) * (sep[k] - sep[k - 1]))
    return np.inf
pd.set_option("display.width", 220); print(F.round(3).to_string(index=False)); print(A.round(3).to_string(index=False))
L = []
for (d, w), g in pd.concat([F[["dir", "where", "sep", "curve_u"]], A[["dir", "where", "sep", "curve_u"]]]).groupby(["dir", "where"]):
    g = g.sort_values("sep"); s = np.r_[0, g.sep.values]; u = np.r_[1, g.curve_u.values]; L.append(dict(dir=d, where=w, L_e=e_len(s, u), min_sep=g.sep.min(), max_sep=g.sep.max()))
L = pd.DataFrame(L); print(L.round(3).to_string(index=False))
F.to_csv("V1_XFINE.csv", index=False); A.to_csv("V1_GRID_YAW.csv", index=False); L.to_csv("V1_LENGTHS.csv", index=False)
