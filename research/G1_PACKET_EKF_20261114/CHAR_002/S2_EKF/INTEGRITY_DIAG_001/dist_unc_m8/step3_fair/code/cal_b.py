"""M8 Step 3 fair plan: (b) planned-path heading reweighting + V table (kriging CV residual variance).

(b) source: plan files rf_poses_R*.json are not available in this workspace -> plan 2nd-priority proxy:
evaluator truth yaw histogram of the evaluated route (heading only; no position/order/error label).
Outputs: SWEEP_CAL_B.npz (per-route sweep calibration arrays), CAL_B_CHECKS.json (C3/C6/C7), SWEEP_TABLE_V.json
"""
import sys, json, hashlib, importlib.util, numpy as np, pandas as pd
from scipy.optimize import nnls
sys.path.insert(0, "/home/claude/m8cal"); sys.path.insert(0, "/home/claude/m8")
from feats import FE, FZ, EXIST
from common import packet, TRUTH
from sklearn.ensemble import HistGradientBoostingRegressor
import krige_online as KO

s = importlib.util.spec_from_file_location("n4b", f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py")
n4b = importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
SW = pd.read_csv("SWEEP_FEATURES.csv.gz")
F = pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def yawbin(deg): return np.floor(((np.asarray(deg) + 185) % 360) / 10).astype(int)   # 36 bins centred -180..170
EDG = np.array([0., 3., 6., 10.])
CHK = dict(b_source="2nd priority proxy: evaluator truth yaw of evaluated route (plan rf_poses_R*.json not available; "
                    "in this simulation the RF poses are the planned path)", routes={})
out = {}
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r)
    T = F[F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    # measured inputs only for evaluation-time features (z and CIR features); assert z identity
    assert np.max(np.abs(T[["range_m", "s_fp"]].to_numpy() - p["z"])) < 1e-9
    yaw = np.degrees(TRUTH[r]["truth"][:, 2])
    h = np.bincount(yawbin(yaw), minlength=36).astype(float); h /= h.sum()
    w = h[yawbin(SW.yaw_deg)] * 36; w = w / w.mean()
    mu, cov, info = n4b.fit_model(np, SW, T, w, "POWER_BIN_JOINT", FE.GROUPS)
    g = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, l2_regularization=1.0,
                                      random_state=0).fit(SW[EXIST], SW.e_r, sample_weight=w)
    out[r] = dict(mu_r=g.predict(T[EXIST]), mu_s=mu[:, 1], Rrr=cov[:, 0, 0], Rss=cov[:, 1, 1], w_hist=h)
    rho = np.hypot(TRUTH[r]["truth"][:, 0] - 10, TRUTH[r]["truth"][:, 1])
    CHK["routes"][r] = dict(hist_sha256=hashlib.sha256(h.tobytes()).hexdigest(), w_mean=float(w.mean()),
                            w_eff=float(w.sum()**2 / (w**2).sum()), w_zero_frac=float(np.mean(w == 0)),
                            occupied_bins=int((h > 0).sum()),
                            C7_Rss_H2S_median_by_bin={f"[{EDG[k]:.0f},{EDG[k+1]:.0f})": float(np.median(cov[(np.clip(np.searchsorted(EDG, rho, side='right') - 1, 0, 2) == k), 1, 1]))
                                                      for k in range(3)})
    print(r, "w_eff", round(CHK["routes"][r]["w_eff"]), "occupied", CHK["routes"][r]["occupied_bins"])

# ---- V: rule B refit of near/mid bins with station-level kriging CV residual (positions left out one at a time)
SW["psi"] = np.radians(SW.yaw_deg); SW["pos"] = SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str)
SW["b"] = np.clip(np.searchsorted(EDG, SW.rho, side="right") - 1, 0, 2)
P = json.load(open("KRIGE_PARAMS.json"))
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
def krige_cv(d, prm, maxn=150):
    lx, ly, lp, nug = prm; X = d[["x_eval", "y_eval", "psi"]].to_numpy(); y = d.e_s.to_numpy(); pos = d.pos.to_numpy()
    pred = np.empty(len(d))
    for ps in np.unique(pos):
        tr = pos != ps; Xt, yt = X[tr], y[tr]; mu0 = yt.mean()
        for i in np.flatnonzero(~tr):
            dd = np.abs(Xt[:, 0] - X[i, 0]) / lx + np.abs(Xt[:, 1] - X[i, 1]) / ly + np.abs(wrap(Xt[:, 2] - X[i, 2])) / lp
            idx = np.argpartition(dd, maxn)[:maxn]; Xi = Xt[idx]
            K = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly
                         + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
            wv = np.linalg.solve((1 - nug) * K + nug * np.eye(len(idx)), (1 - nug) * np.exp(-dd[idx]))
            pred[i] = mu0 + wv @ (yt[idx] - mu0)
    return y - pred
def fitB(e, a):
    lo = np.abs(a) < 0.3; c0 = float(np.mean(e[lo]**2)); c1 = float(nnls((a**2)[:, None], e**2 - c0)[0][0]); return c1, c0
ST = json.load(open("/home/claude/m8/SWEEP_TABLE_5LINE.json")); V = dict(edges=ST["edges"], c1=list(ST["c1"]), c0=list(ST["c0"]))
CHK["V"] = {}
for k in (0, 1):
    d = SW[SW.b == k].reset_index(drop=True)
    res = krige_cv(d, P[f"e_s|{k}"]["params"])
    c1, c0 = fitB(res, d.a.to_numpy()); V["c1"][k], V["c0"][k] = c1, c0
    CHK["V"][f"bin{k}"] = dict(n_pos=int(d.pos.nunique()), c1_unadj=ST["c1"][k], c0_unadj=ST["c0"][k], c1_V=c1, c0_V=c0,
                              E_e2_raw=float(np.mean(d.e_s**2)), E_res2_cv=float(np.mean(res**2)),
                              C6_smaller=bool(c1 <= ST["c1"][k] and c0 <= ST["c0"][k]))
    print("V bin", k, CHK["V"][f"bin{k}"])
V["sigma_theta_deg"] = [float(np.degrees(np.sqrt(c))) for c in V["c1"]]; V["sigma_res"] = [float(np.sqrt(c)) for c in V["c0"]]
V["source"] = "SWEEP_TABLE_5LINE with bins [0,3),[3,6) refit (rule B) on station-level kriging LOPO-CV residual; far bin unchanged"
json.dump(V, open("SWEEP_TABLE_V.json", "x"), indent=1)
np.savez("SWEEP_CAL_B.npz", **{f"{r}/{k}": v for r in out for k, v in out[r].items()})
CHK.update(SWEEP_FEATURES_sha256=sha("SWEEP_FEATURES.csv.gz"), KRIGE_PARAMS_sha256=sha("KRIGE_PARAMS.json"),
           SWEEP_TABLE_V_sha256=sha("SWEEP_TABLE_V.json"), SWEEP_CAL_B_sha256=sha("SWEEP_CAL_B.npz"))
json.dump(CHK, open("CAL_B_CHECKS.json", "w"), indent=1)
print(json.dumps({k: CHK[k] for k in CHK if k.endswith("sha256")}, indent=1))
