"""C0-3 refit: S0 (F2SKRW-V) calibration rebuilt from the reference-model residual label e_s = s_full - h_FFD
(ES_FFDREF_CORRIDOR.npy, C0-2). Same procedures as S0: rule-B 5-line table, POWER_BIN_JOINT (b) mu_s/R_ss per route,
V table (kriging LOPO-CV residual refit, KRIGE_PARAMS fixed), kriging data. Range channel untouched."""
import sys, json, hashlib, importlib.util, numpy as np, pandas as pd
from scipy.optimize import nnls
sys.path.insert(0, "/home/claude/m8cal"); sys.path.insert(0, "/home/claude/m8")
from feats import FE, FZ
from common import packet, TRUTH
s = importlib.util.spec_from_file_location("n4b", f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py")
n4b = importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["e_s"] = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
F = pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
EDG = np.array([0., 3., 6., 10.]); SW["b"] = np.clip(np.searchsorted(EDG, SW.rho, side="right") - 1, 0, 2)
def yawbin(deg): return np.floor(((np.asarray(deg) + 185) % 360) / 10).astype(int)
def fitB(e, a):
    lo = np.abs(a) < .3; c0 = float(np.mean(e[lo]**2)); c1 = float(nnls((a**2)[:, None], e**2 - c0)[0][0]); return c1, c0
tab = dict(edges=[0., 3., 6., 10.], c1=[], c0=[])
for k in range(3):
    d = SW[SW.b == k]; c1, c0 = fitB(d.e_s.to_numpy(), d.a.to_numpy()); tab["c1"].append(c1); tab["c0"].append(c0)
B0 = np.load("/home/claude/m8cal/SWEEP_CAL_B.npz"); out = {}
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r); T = F[F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    h = np.bincount(yawbin(np.degrees(TRUTH[r]["truth"][:, 2])), minlength=36).astype(float); h /= h.sum()
    w = h[yawbin(SW.yaw_deg)] * 36; w = w / w.mean()
    mu, cov, _ = n4b.fit_model(np, SW, T, w, "POWER_BIN_JOINT", FE.GROUPS)
    out[r] = dict(mu_r=B0[f"{r}/mu_r"], mu_s=mu[:, 1], Rrr=cov[:, 0, 0], Rss=cov[:, 1, 1])
    print(r, "max|d mu_s|", float(np.abs(mu[:, 1] - B0[f"{r}/mu_s"]).max()), "max|d Rrr|", float(np.abs(cov[:, 0, 0] - B0[f"{r}/Rrr"]).max()))
# V table
SW["psi"] = np.radians(SW.yaw_deg); SW["pos"] = SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str)
P = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json"))
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
def krige_cv(d, prm, maxn=150):
    lx, ly, lp, nug = prm; X = d[["x_eval", "y_eval", "psi"]].to_numpy(); y = d.e_s.to_numpy(); pos = d.pos.to_numpy(); pred = np.empty(len(d))
    for ps in np.unique(pos):
        tr = pos != ps; Xt, yt = X[tr], y[tr]; mu0 = yt.mean()
        for i in np.flatnonzero(~tr):
            dd = np.abs(Xt[:, 0] - X[i, 0]) / lx + np.abs(Xt[:, 1] - X[i, 1]) / ly + np.abs(wrap(Xt[:, 2] - X[i, 2])) / lp
            idx = np.argpartition(dd, maxn)[:maxn]; Xi = Xt[idx]
            K = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
            wv = np.linalg.solve((1 - nug) * K + nug * np.eye(len(idx)), (1 - nug) * np.exp(-dd[idx])); pred[i] = mu0 + wv @ (yt[idx] - mu0)
    return y - pred
V = dict(edges=tab["edges"], c1=list(tab["c1"]), c0=list(tab["c0"]))
for k in (0, 1):
    d = SW[SW.b == k].reset_index(drop=True); res = krige_cv(d, P[f"e_s|{k}"]["params"]); V["c1"][k], V["c0"][k] = fitB(res, d.a.to_numpy())
ST = json.load(open("/home/claude/m8/SWEEP_TABLE_5LINE.json")); VT = json.load(open("/home/claude/m8cal/SWEEP_TABLE_V.json"))
cmp = dict(table5_rel_diff=[float(abs(a / b - 1)) for a, b in zip(tab["c1"] + tab["c0"], ST["c1"] + ST["c0"])],
           tableV_rel_diff=[float(abs(a / b - 1)) for a, b in zip(V["c1"] + V["c0"], VT["c1"] + VT["c0"])])
print(cmp)
np.savez("/home/claude/lut0/S0ID_CAL.npz", **{f"{r}/{k}": v for r in out for k, v in out[r].items()})
json.dump(dict(table5=tab, tableV=V, compare_to_S0=cmp), open("/home/claude/lut0/S0ID_TABLES.json", "w"), indent=1)
