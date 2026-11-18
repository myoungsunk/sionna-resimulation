"""O2 static transfer (no filter). Office sweep 35 st x 36 yaw and Office routes O01-O03 (mount 0).
Labels: e_r = range_m - (d3D + B_OLD); e_s = s_fp - s_LoS(frozen FFD synthetic, parity-checked in O1); a = ds_LoS/dpsi (per rad).
T0 = corridor-sweep calibration (SWEEP_FEATURES, uniform weights); T1 = Office-sweep calibration (leave-one-station-out on sweep)."""
import sys, json, numpy as np, pandas as pd, importlib.util
SRC = "/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_model003_src"
sys.path.insert(0, SRC); sys.path.insert(0, "/home/claude/m8cal")
from qclean_uwb.drivesim import hs_lut as model, observation as obs, pattern_apply as pat
from feats import features, B_OLD, EXIST, FE, FZ
from scipy.optimize import nnls
from sklearn.ensemble import HistGradientBoostingRegressor
banks = [pat.Bank(dict(np.load(f"/home/claude/rel/{n}", allow_pickle=False))) for n in ("LP_plus45_bank.npz", "LP_minus45_bank.npz")]
s = importlib.util.spec_from_file_location("n4b", f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py")
n4b = importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
A = np.array([5., 2.2, 2.65]); ZR = .45; EDG = np.array([0., 3., 6., 10.])
def o30(c):
    m = np.abs(c); b = m.max(axis=1).argmax(axis=1); s_ = np.take_along_axis(m, b[:, None, None], axis=2)[:, :, 0]; pk = s_.max(axis=1)
    return (s_ >= .3 * pk[:, None]).argmax(axis=1)
def s_at(c, i):
    p = np.abs(c[np.arange(len(c)), i, :])**2; return (p[:, 0] - p[:, 1]) / p.sum(axis=1)

def label(x, y, yaw, H):
    delta = np.c_[x, y, np.full(len(x), ZR)] - A; d = np.linalg.norm(delta, axis=1); dirn = delta / d[:, None]
    F = features(H)
    sl = np.empty(len(x)); a = np.empty(len(x))
    for k in range(0, len(x), 256):
        ii = range(k, min(k + 256, len(x)))
        hs = [np.stack([model.los_h(banks, dirn[i], float(yaw[i] + dy), float(d[i])) for i in ii]) for dy in (-.5, 0., .5)]
        cs = [obs.cir_batch(h[..., 0]) for h in hs]; il = o30(cs[1]); sm, sc, sp = (s_at(c, il) for c in cs)
        sl[k:k + len(ii)] = sc; a[k:k + len(ii)] = (sp - sm) / 1.0 * 180 / np.pi
    F["e_r"] = F.range_m - (d + B_OLD); F["e_s"] = F.s_fp - sl; F["a"] = a
    F["rho"] = np.hypot(x - A[0], y - A[1]); F["x_eval"] = x; F["y_eval"] = y; F["yaw_deg"] = yaw
    F["b"] = np.clip(np.searchsorted(EDG, F.rho, side="right") - 1, 0, 2)
    return F

# ---- Office sweep
rp = json.load(open("/home/claude/office/rf_poses.json")); rp = sorted(rp, key=lambda r: r["h_row"])
H = np.load("/home/claude/office/H_full.npy", mmap_mode="r")
lab = pd.read_csv("/home/claude/office/rel/../../office/st_labels.csv") if False else None
X = np.array([[r["x"], r["y"], r["yaw_deg"]] for r in rp])
OS = label(X[:, 0], X[:, 1], X[:, 2], H); OS["station"] = [r["station_id"] for r in rp]
L = pd.read_csv("/tmp/off/SWEEP_STATION_LABELS.csv", encoding="utf-8-sig").set_index("map_label")
OS["los"] = OS.station.map(L.geometric_los_clear).astype(bool)
OS.to_csv("/home/claude/office/OFFICE_SWEEP_FEATURES.csv.gz", index=False)
# ---- Office routes
RT = []
for o in ("O01", "O02", "O03"):
    d = f"/home/claude/office/rel/{o}_M0/CASES/{o}_O0_M0_FULL"; P = pd.read_csv(f"{d}/RADIO_POSE.csv")
    F = label(P.x_m.to_numpy(), P.y_m.to_numpy(), P.yaw_antenna_deg.to_numpy(float), np.load(f"{d}/H_FULL.npy"))
    F["route"] = o; F["los"] = np.load(f"{d}/LOS_EXISTS.npy").astype(bool); RT.append(F)
RT = pd.concat(RT, ignore_index=True); RT.to_csv("/home/claude/office/OFFICE_ROUTE_FEATURES.csv.gz", index=False)
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["b"] = np.clip(np.searchsorted(EDG, SW.rho, side="right") - 1, 0, 2)
ST = json.load(open("/home/claude/m8/SWEEP_TABLE_5LINE.json"))

def fitB(e, a):
    lo = np.abs(a) < .3; c0 = float(np.mean(e[lo]**2)); c1 = float(nnls((a**2)[:, None], e**2 - c0)[0][0]); return c1, c0
R = {}
# 1) form: rule B on office sweep, per bin, all / LoS stations; binned E[e_s^2] vs a^2 (quintiles)
R["form"] = {}
for k in range(3):
    for sub, m in (("all", OS.b == k), ("LoS", (OS.b == k) & OS.los), ("NLoS", (OS.b == k) & ~OS.los)):
        d = OS[m]
        if len(d) < 40: continue
        c1, c0 = fitB(d.e_s.to_numpy(), d.a.to_numpy())
        q = pd.qcut(d.a**2, 5, duplicates="drop"); g = d.groupby(q, observed=True).agg(a2=("a", lambda v: np.mean(v**2)), e2=("e_s", lambda v: np.mean(v**2)))
        pred = c1 * g.a2 + c0
        R["form"][f"bin{k}/{sub}"] = dict(n=len(d), n_st=int(d.station.nunique()), c1=c1, c0=c0, sig_theta_deg=float(np.degrees(np.sqrt(c1))), sig_res=float(np.sqrt(c0)),
                                         corridor_c1=ST["c1"][k], corridor_c0=ST["c0"][k],
                                         quintile_a2=g.a2.round(4).tolist(), quintile_e2=g.e2.round(5).tolist(), quintile_fit=pred.round(5).tolist(),
                                         corr_e2_a2=float(np.corrcoef(g.a2, g.e2)[0, 1]) if len(g) > 2 else None)

# 2) corridor-sweep (T0) mu_r HGB + POWER R and table; office-sweep (T1, leave-one-station-out)
def hgb(): return HistGradientBoostingRegressor(max_iter=200, learning_rate=.05, max_leaf_nodes=15, l2_regularization=1., random_state=0)
g0 = hgb().fit(SW[EXIST], SW.e_r)
mu0, cov0, _ = n4b.fit_model(np, SW, OS, np.ones(len(SW)), "POWER_BIN_JOINT", FE.GROUPS)
muR0, covR0, _ = n4b.fit_model(np, SW, RT, np.ones(len(SW)), "POWER_BIN_JOINT", FE.GROUPS)
OS["mu_r_T0"] = g0.predict(OS[EXIST]); OS["Rrr_T0"] = cov0[:, 0, 0]; OS["mu_s_T0"] = mu0[:, 1]
RT["mu_r_T0"] = g0.predict(RT[EXIST]); RT["Rrr_T0"] = covR0[:, 0, 0]; RT["mu_s_T0"] = muR0[:, 1]
# T1 on sweep: leave-one-station-out
for c in ("mu_r_T1", "Rrr_T1", "mu_s_T1"): OS[c] = np.nan
for st in OS.station.unique():
    tr, te = OS.station != st, OS.station == st
    OS.loc[te, "mu_r_T1"] = hgb().fit(OS.loc[tr, EXIST], OS.loc[tr, "e_r"]).predict(OS.loc[te, EXIST])
    mu, cov, _ = n4b.fit_model(np, OS[tr].reset_index(drop=True), OS[te].reset_index(drop=True), np.ones(tr.sum()), "POWER_BIN_JOINT", FE.GROUPS)
    OS.loc[te, "Rrr_T1"] = cov[:, 0, 0]; OS.loc[te, "mu_s_T1"] = mu[:, 1]
# T1 on routes: full office sweep
g1 = hgb().fit(OS[EXIST], OS.e_r); muR1, covR1, _ = n4b.fit_model(np, OS, RT, np.ones(len(OS)), "POWER_BIN_JOINT", FE.GROUPS)
RT["mu_r_T1"] = g1.predict(RT[EXIST]); RT["Rrr_T1"] = covR1[:, 0, 0]; RT["mu_s_T1"] = muR1[:, 1]
# polarization variance tables: corridor 5-line (T0) and office sweep rule B (T1, all stations)
tab1 = dict(c1=[fitB(OS[OS.b == k].e_s.to_numpy(), OS[OS.b == k].a.to_numpy())[0] for k in range(3)],
            c0=[fitB(OS[OS.b == k].e_s.to_numpy(), OS[OS.b == k].a.to_numpy())[1] for k in range(3)])
R["table_T1"] = tab1
def summarize(D, tag):
    out = {}
    for sub, m in (("LoS", D.los), ("NLoS", ~D.los)):
        for k in range(3):
            d = D[m & (D.b == k)]
            if len(d) < 20: continue
            row = dict(n=len(d), e_r_mean_cm=100 * d.e_r.mean(), e_r_sd_cm=100 * d.e_r.std(), e_s_rms=float(np.sqrt(np.mean(d.e_s**2))))
            for T in ("T0", "T1"):
                rr = d.e_r - d[f"mu_r_{T}"]; z = rr / np.sqrt(d[f"Rrr_{T}"])
                tab = ST if T == "T0" else tab1
                vs = tab["c1"][k] * d.a**2 + tab["c0"][k]; zs = (d.e_s - d[f"mu_s_{T}"]) / np.sqrt(vs)
                row.update({f"{T}_resid_r_mean_cm": 100 * rr.mean(), f"{T}_resid_r_rms_cm": 100 * np.sqrt(np.mean(rr**2)),
                            f"{T}_z_r_cov95": float(np.mean(np.abs(z) <= 1.96)), f"{T}_z_s_cov95": float(np.mean(np.abs(zs) <= 1.96)),
                            f"{T}_resid_s_rms": float(np.sqrt(np.mean((d.e_s - d[f"mu_s_{T}"])**2)))})
            out[f"{sub}/bin{k}"] = row
    return out
R["office_sweep"] = summarize(OS, "sweep")
R["office_routes"] = {o: summarize(RT[RT.route == o], o) for o in ("O01", "O02", "O03")}
json.dump(R, open("/home/claude/office/O2_STATIC.json", "w"), indent=1, default=float)
pd.set_option("display.width", 250)
print(pd.DataFrame({k: {kk: v[kk] for kk in ("n", "n_st", "c1", "c0", "sig_theta_deg", "sig_res", "corridor_c1", "corridor_c0", "corr_e2_a2")} for k, v in R["form"].items()}).T.round(5).to_string())
for name, blk in [("SWEEP", R["office_sweep"])] + [(o, R["office_routes"][o]) for o in R["office_routes"]]:
    print("==", name); print(pd.DataFrame(blk).T.round(3).to_string())
