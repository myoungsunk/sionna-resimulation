"""O3 build: Office LoS-only routes, seed inputs, and calibration arrays for all arms.
Routes: O01 (all LoS), O02 (all LoS), O03L = O03 RF rows 137-272 (t 99-194 s, the only LoS span >= 30 s).
NLoS spans are not used as trajectory (user decision 2026-11-18). LoS = RT LOS_EXISTS.
"""
import sys, json, math, itertools, hashlib, importlib.util, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8cal"); sys.path.insert(0, "/home/claude/m8")
from feats import EXIST, DS, FE, FZ
from scipy.optimize import nnls
from sklearn.ensemble import HistGradientBoostingRegressor
import gen_inputs_ext as G
s = importlib.util.spec_from_file_location("n4b", f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py")
n4b = importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
O = "/home/claude/office"; EDG = np.array([0., 3., 6., 10.]); A = np.array([5., 2.2])
def bins(rho): return np.clip(np.searchsorted(EDG, rho, side="right") - 1, 0, 2)
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
def hgb(): return HistGradientBoostingRegressor(max_iter=200, learning_rate=.05, max_leaf_nodes=15, l2_regularization=1., random_state=0)
def fitB(e, a):
    lo = np.abs(a) < .3; c0 = float(np.mean(e[lo]**2)); c1 = float(nnls((a**2)[:, None], e**2 - c0)[0][0]); return c1, c0
def yawbin(deg): return np.floor(((np.asarray(deg) + 185) % 360) / 10).astype(int)

RTall = pd.read_csv(f"{O}/OFFICE_ROUTE_FEATURES.csv.gz")
RTall["row"] = RTall.groupby("route").cumcount()
ROUTES = {}
for r in ("O01", "O02", "O03"):
    P = pd.read_csv(f"{O}/rel/{r}_M0/CASES/{r}_O0_M0_FULL/RADIO_POSE.csv")
    F = RTall[RTall.route == r].reset_index(drop=True); assert len(F) == len(P)
    sl = slice(137, 273) if r == "O03" else slice(0, len(P))
    name = "O03L" if r == "O03" else r
    Pk, Fk = P.iloc[sl].reset_index(drop=True), F.iloc[sl].reset_index(drop=True)
    assert Fk.los.all(), name
    t = Pk.t_s.to_numpy() - Pk.t_s.iloc[0]
    truth = np.c_[Pk.x_m, Pk.y_m, np.radians(Pk.yaw_antenna_deg)]
    ROUTES[name] = dict(t=t, truth=truth, F=Fk, pose_id=Pk.pose_id.to_numpy())
DONOR = RTall[RTall.los].reset_index(drop=True)          # LoS rows of all three routes (incl. O03 short LoS spans) as donor data

# ---------- seed inputs (same law as gen_inputs_ext / m7_inputs)
S, _ = G.load_sensor(); cfg, cfg2 = G.configs(S)
def inputs(name, seed):
    R = ROUTES[name]; t, truth = R["t"], R["truth"]
    ds, ang = S.motion_increments(t, truth, convention="legacy-euler")
    c0, _ = S.generate(t, ds, ang, cfg, seed); c2, _ = S.generate(t, ds, ang, cfg2, seed)
    x0, P0 = G.initial(S, truth, seed)
    base = dict(t=t, pose_id=R["pose_id"], z=R["F"][["range_m", "s_fp"]].to_numpy(), x0=x0, P0=P0, ds=c0["ds_odom"], dt=c0["dt_s"])
    return {"B0": dict(base, gy=c0["dtheta_gyro"]), "L2_GYRO_ARW": dict(base, gy=c2["dtheta_gyro"])}

# ---------- calibrations
CAL = {}; INFO = {}
OS = pd.read_csv(f"{O}/OFFICE_SWEEP_FEATURES.csv.gz"); OSL = OS[OS.los].reset_index(drop=True)
OSL["psi"] = np.radians(OSL.yaw_deg); OSL["b"] = bins(OSL.rho)
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz")
STc = json.load(open("/home/claude/m8/SWEEP_TABLE_5LINE.json"))
# office LoS-station polarization table (rule B, per bin)
tabO = dict(edges=[0., 3., 6., 10.], c1=[], c0=[])
for k in range(3):
    d = OSL[OSL.b == k]; c1, c0 = fitB(d.e_s.to_numpy(), d.a.to_numpy()); tabO["c1"].append(c1); tabO["c0"].append(c0)
tabC = dict(edges=STc["edges"], c1=STc["c1"], c0=STc["c0"])
# office kriging hyper-parameters: leave-one-station-out CV on LoS stations, per bin
def krig_pred(Xt, yt, Xq, prm, maxn=150):
    lx, ly, lp, nug = prm; mu0 = yt.mean(); out = np.empty(len(Xq))
    for i, q in enumerate(Xq):
        dd = np.abs(Xt[:, 0] - q[0]) / lx + np.abs(Xt[:, 1] - q[1]) / ly + np.abs(wrap(Xt[:, 2] - q[2])) / lp
        idx = np.argpartition(dd, maxn)[:maxn] if len(dd) > maxn else np.arange(len(dd)); Xi = Xt[idx]
        K = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
        w = np.linalg.solve((1 - nug) * K + nug * np.eye(len(idx)), (1 - nug) * np.exp(-dd[idx])); out[i] = mu0 + w @ (yt[idx] - mu0)
    return out
GRID = list(itertools.product([0.5, 1.5, 3.0], [0.5, 1.5, 3.0], np.radians([10, 25, 60]), [0.2, 0.5, 0.8]))
KP = {}; VRES = {}
for k in range(3):
    d = OSL[OSL.b == k].reset_index(drop=True); X = d[["x_eval", "y_eval", "psi"]].to_numpy(); y = d.e_s.to_numpy(); st = d.station.to_numpy()
    base = float(np.mean([np.mean((y[st == s_] - y[st != s_].mean())**2) for s_ in np.unique(st)]))
    best = None
    for prm in GRID:
        res = np.empty(len(d))
        for s_ in np.unique(st):
            m = st == s_; res[m] = y[m] - krig_pred(X[~m], y[~m], X[m], prm)
        mse = float(np.mean(res**2))
        if best is None or mse < best[0]: best = (mse, prm, res)
    KP[k] = dict(params=[float(v) for v in best[1]], cv_mse=best[0], baseline_mse=base, n_st=int(len(np.unique(st))))
    VRES[k] = best[2]
tabV = dict(edges=tabO["edges"], c1=list(tabO["c1"]), c0=list(tabO["c0"]))
for k in (0, 1):
    d = OSL[OSL.b == k]; c1, c0 = fitB(VRES[k], d.a.to_numpy()); tabV["c1"][k], tabV["c0"][k] = c1, c0
INFO.update(table_office=tabO, table_corridor=tabC, table_V=tabV, krige_office=KP)

def weighted(src, h):
    w = h[yawbin(src.yaw_deg)] * 36; return w / w.mean()
for name, R in ROUTES.items():
    T = R["F"]; h = np.bincount(yawbin(np.degrees(R["truth"][:, 2])), minlength=36).astype(float); h /= h.sum()
    out = {}
    # H2 (Office route LORO): donors = LoS rows of the other two routes
    src_route = "O03" if name == "O03L" else name
    D = DONOR[DONOR.route != src_route].reset_index(drop=True)
    g = hgb().fit(D[EXIST + DS], D.e_r); mu, cov, _ = n4b.fit_model(np, D, T, np.ones(len(D)), "POWER_BIN_JOINT", FE.GROUPS)
    out["H2"] = dict(mu_r=g.predict(T[EXIST + DS]), mu_s=mu[:, 1], Rrr=cov[:, 0, 0], Rss=cov[:, 1, 1])
    # F2L table: rule B on donor residual e_s - mu_s, mu_s from POWER fit on the *other* donor route (nested LORO)
    res, aa, rr = [], [], []
    for dr in D.route.unique():
        tr, te = D[D.route != dr].reset_index(drop=True), D[D.route == dr].reset_index(drop=True)
        m2, _, _ = n4b.fit_model(np, tr, te, np.ones(len(tr)), "POWER_BIN_JOINT", FE.GROUPS)
        res.append(te.e_s.to_numpy() - m2[:, 1]); aa.append(te.a.to_numpy()); rr.append(te.rho.to_numpy())
    res, aa, rr = map(np.concatenate, (res, aa, rr)); bb = bins(rr); tL = dict(edges=[0., 3., 6., 10.], c1=[], c0=[]); fb = fitB(res, aa)
    for k in range(3):
        m = bb == k
        c = fitB(res[m], aa[m]) if (m & (np.abs(aa) < .3)).sum() >= 10 and m.sum() >= 30 else fb
        tL["c1"].append(c[0]); tL["c0"].append(c[1])
    INFO[f"table_F2L_{name}"] = tL
    # T0: corridor sweep, (b) weights from this route's heading histogram
    w = weighted(SW, h); g = hgb().fit(SW[EXIST], SW.e_r, sample_weight=w); mu, cov, _ = n4b.fit_model(np, SW, T, w, "POWER_BIN_JOINT", FE.GROUPS)
    out["T0"] = dict(mu_r=g.predict(T[EXIST]), mu_s=mu[:, 1], Rrr=cov[:, 0, 0], Rss=cov[:, 1, 1])
    # T1: office LoS-station sweep, (b) weights
    w = weighted(OSL, h); g = hgb().fit(OSL[EXIST], OSL.e_r, sample_weight=w); mu, cov, _ = n4b.fit_model(np, OSL, T, w, "POWER_BIN_JOINT", FE.GROUPS)
    out["T1"] = dict(mu_r=g.predict(T[EXIST]), mu_s=mu[:, 1], Rrr=cov[:, 0, 0], Rss=cov[:, 1, 1])
    INFO[f"w_eff_{name}"] = dict(corridor=float(weighted(SW, h).sum()**2 / (weighted(SW, h)**2).sum()), office=float(w.sum()**2 / (w**2).sum()))
    CAL[name] = out
np.savez(f"{O}/O3_CAL.npz", **{f"{r}/{a}/{k}": v for r in CAL for a in CAL[r] for k, v in CAL[r][a].items()})
np.savez(f"{O}/O3_ROUTES.npz", **{f"{r}/{k}": v for r in ROUTES for k, v in ROUTES[r].items() if k != "F"},
         **{f"{r}/a": ROUTES[r]["F"].a.to_numpy() for r in ROUTES}, **{f"{r}/rho": ROUTES[r]["F"].rho.to_numpy() for r in ROUTES})
OSL[["x_eval", "y_eval", "psi", "e_s", "b"]].to_csv(f"{O}/O3_KRIGE_DATA.csv", index=False, float_format="%.17g")
json.dump(INFO, open(f"{O}/O3_INFO.json", "w"), indent=1)
import os
os.makedirs(f"{O}/inputs", exist_ok=True)
for name in ROUTES:
    for seed in range(10, 30):
        for cond, p in inputs(name, seed).items(): np.savez(f"{O}/inputs/{name}_{cond}_{seed}.npz", **p)
print(json.dumps({k: v for k, v in INFO.items() if not k.startswith("table_F2L")}, indent=0)[:3000])
for r in ROUTES: print(r, len(ROUTES[r]["t"]), ROUTES[r]["t"][-1], INFO[f"table_F2L_{r}"])
