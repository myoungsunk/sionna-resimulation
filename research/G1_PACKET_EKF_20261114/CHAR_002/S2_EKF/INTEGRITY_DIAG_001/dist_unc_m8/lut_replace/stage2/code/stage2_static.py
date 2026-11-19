"""Stage 2 static part (plan section 6, amendments 01 A5 and 02 B1/B4/B5).
For each P in P1, P1m, P2, P3:
  - h', a' at the 7200 station poses
  - 2b calibration rebuilt on labels e' = s_full - h' (same procedures as S0-id refit, s0id_refit.py):
      rule-B 5-line table (a'), POWER_BIN_JOINT (b) mu_s / R_ss per route, V table (kriging LOSO residual, S0 hyperparameters), kriging data
  - LOSO static gates: z_s coverage per distance bin for 2a (S0-id labels/tables, h', a') and 2b (own labels/tables);
    sign agreement sign(a') = sign(a_FFD) on |a_FFD| >= 0.3 (diagnostic: size of the injected error)
2b-cv (P1 only): kriging hyperparameters re-selected by the krige.py procedure (same grid, same rng(0) station draw)."""
import sys, json, itertools, importlib.util, numpy as np, pandas as pd
from scipy.optimize import nnls
sys.path.insert(0, "/home/claude/m8cal"); sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/lut2")
from feats import FE, FZ
from common import packet, TRUTH, env
import pert
s_ = importlib.util.spec_from_file_location("n4b", f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py")
n4b = importlib.util.module_from_spec(s_); s_.loader.exec_module(n4b)
OUT = "/home/claude/lut2"
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); ES0 = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
SW["psi"] = np.radians(SW.yaw_deg); EDG = np.array([0., 3., 6., 10.]); SW["b"] = np.clip(np.searchsorted(EDG, SW.rho, side="right") - 1, 0, 2)
SW["pos"] = SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str)
F = pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F = F[F.channel == "full"]
KP = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json")); V0 = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]
B0 = np.load("/home/claude/m8cal/SWEEP_CAL_B.npz")
X3 = SW[["x_eval", "y_eval", "psi"]].to_numpy(); POS = SW.pos.to_numpy(); BIN = SW.b.to_numpy(); S = SW.s_fp.to_numpy(); A0 = SW.a.to_numpy()
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
def yawbin(deg): return np.floor(((np.asarray(deg) + 185) % 360) / 10).astype(int)
def fitB(e, a):
    lo = np.abs(a) < .3; c0 = float(np.mean(e[lo]**2)); c1 = float(nnls((a**2)[:, None], e**2 - c0)[0][0]); return c1, c0


def kr_one(Xt, yt, mu0, q, prm, maxn=150):
    lx, ly, lp, nug = prm
    d = np.abs(Xt[:, 0] - q[0]) / lx + np.abs(Xt[:, 1] - q[1]) / ly + np.abs(wrap(Xt[:, 2] - q[2])) / lp
    idx = np.argpartition(d, maxn)[:maxn] if len(d) > maxn else np.arange(len(d)); Xi = Xt[idx]
    K = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
    w = np.linalg.solve((1 - nug) * K + nug * np.eye(len(idx)), (1 - nug) * np.exp(-d[idx])); return mu0 + w @ (yt[idx] - mu0)


def loso_mu(es, prms):
    """LOSO mean correction at every station row: kriging within bin for rho < 6 m (params prms[b]), POWER (uniform) for bin 2."""
    mu = np.empty(len(es))
    for st in np.unique(POS):
        te = POS == st; tr = ~te; k = int(BIN[te][0])
        if k == 2:
            m2, _, _ = n4b.fit_model(np, SW[tr].assign(e_s=es[tr]).reset_index(drop=True), SW[te].reset_index(drop=True), np.ones(tr.sum()), "POWER_BIN_JOINT", FE.GROUPS)
            mu[te] = m2[:, 1]; continue
        trk = tr & (BIN == k); Xt, yt = X3[trk], es[trk]; mu0 = yt.mean()
        for i in np.flatnonzero(te): mu[i] = kr_one(Xt, yt, mu0, X3[i], prms[k])
    return mu


def cv_select(es):
    """krige.py procedure for the e_s label: same GRID, same rng(0) stream (e_r draws replayed first), maxn = 120."""
    GRID = list(itertools.product([0.15, 0.45, 1.0], [0.15, 0.5, 1.5], [np.radians(10), np.radians(25), np.radians(60)], [0.2, 0.5, 0.8]))
    rng = np.random.default_rng(0); out = {}
    for lab in ("e_r", "e_s"):
        for b in range(3):
            m = BIN == b; poss = pd.unique(POS[m]); tp_ = rng.choice(poss, min(14, len(poss)), replace=False)
            if lab == "e_r" or b == 2: continue
            y = es[m]; Xb = X3[m]; Pb = POS[m]; mu0 = y.mean(); sc = []
            for prm in GRID:
                se = []
                for tp in tp_:
                    tr = Pb != tp; te = ~tr
                    pr = np.array([kr_one(Xb[tr], y[tr], mu0, q, prm, maxn=120) for q in Xb[te]]); se.append(np.mean((y[te] - pr)**2))
                sc.append((float(np.mean(se)), prm))
            sc.sort(key=lambda t: t[0]); out[b] = list(sc[0][1]); print("cv", b, out[b], sc[0][0], flush=True)
    return out


def calibrate(es, a, prms):
    tab = dict(edges=[0., 3., 6., 10.], c1=[], c0=[])
    for k in range(3):
        m = BIN == k; c1, c0 = fitB(es[m], a[m]); tab["c1"].append(c1); tab["c0"].append(c0)
    mu = loso_mu(es, prms); V = dict(edges=tab["edges"], c1=list(tab["c1"]), c0=list(tab["c0"]))
    for k in (0, 1):
        m = BIN == k; V["c1"][k], V["c0"][k] = fitB((es - mu)[m], a[m])
    cal = {}
    for r in ("R2", "R4", "R5"):
        p = packet("B0", 10, r); T = F[F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
        h = np.bincount(yawbin(np.degrees(TRUTH[r]["truth"][:, 2])), minlength=36).astype(float); h /= h.sum()
        w = h[yawbin(SW.yaw_deg)] * 36; w = w / w.mean()
        mu_r, cov, _ = n4b.fit_model(np, SW.assign(e_s=es), T, w, "POWER_BIN_JOINT", FE.GROUPS)
        cal.update({f"{r}/mu_r": B0[f"{r}/mu_r"], f"{r}/mu_s": mu_r[:, 1], f"{r}/Rrr": cov[:, 0, 0], f"{r}/Rss": cov[:, 1, 1]})
    return tab, V, mu, cal


def gate(resid, a, V):
    z = resid / np.sqrt(np.array(V["c1"])[BIN] * a**2 + np.array(V["c0"])[BIN])
    return [float(np.mean(np.abs(z[BIN == k]) <= 1.96)) for k in range(3)], z


if __name__ == "__main__":
    e0 = env(); spec, base = e0["spec"], e0["model"]; prm0 = {k: KP[f"e_s|{k}"]["params"] for k in range(3)}
    import os
    if os.path.exists(f"{OUT}/MU_LOSO_S0ID.npy"): mu0 = np.load(f"{OUT}/MU_LOSO_S0ID.npy")
    else: mu0 = loso_mu(ES0, prm0); np.save(f"{OUT}/MU_LOSO_S0ID.npy", mu0)
    cov_s0id, _ = gate(ES0 - mu0, A0, V0); res = dict(S0id=dict(zcov=cov_s0id)); print("S0-id", cov_s0id, flush=True)
    for P in ("P1", "P1m", "P2", "P3"):
        hP, aP = pert.at_stations(pert.make(base, P), SW.x_eval.to_numpy(), SW.y_eval.to_numpy(), SW.psi.to_numpy(), spec)
        eP = S - hP; np.save(f"{OUT}/ES_{P}.npy", eP); np.save(f"{OUT}/A_{P}.npy", aP)
        cov2a, _ = gate(S - hP - mu0, aP, V0)
        tab, V, mu, cal = calibrate(eP, aP, prm0); cov2b, _ = gate(eP - mu, aP, V)
        np.savez(f"{OUT}/CAL_{P}.npz", **cal); np.save(f"{OUT}/MU_LOSO_{P}.npy", mu)
        sel = np.abs(A0) >= .3
        sign = [float(np.mean(np.sign(aP[sel & (BIN == k)]) == np.sign(A0[sel & (BIN == k)]))) for k in range(3)]
        dh = [float(np.sqrt(np.mean((hP - (S - ES0))[BIN == k]**2))) for k in range(3)]
        res[P] = dict(zcov_2a=cov2a, zcov_2b=cov2b, sign_agree_diag=sign, h_err_rms=dh, table5=tab, tableV=V,
                      dmu_s_route_max={r: float(np.abs(cal[f"{r}/mu_s"] - np.load("/home/claude/lut0/S0ID_CAL.npz")[f"{r}/mu_s"]).max()) for r in ("R2", "R4", "R5")})
        print(P, json.dumps({k: res[P][k] for k in ("zcov_2a", "zcov_2b", "sign_agree_diag", "h_err_rms")}), flush=True)
        if P == "P1":
            prm = cv_select(eP); prm[2] = prm0[2]
            tab, V, mu, cal = calibrate(eP, aP, prm); cov2c, _ = gate(eP - mu, aP, V)
            np.savez(f"{OUT}/CAL_P1cv.npz", **cal); np.save(f"{OUT}/MU_LOSO_P1cv.npy", mu)
            res["P1cv"] = dict(krige_params={str(k): v for k, v in prm.items()}, zcov_2b=cov2c, table5=tab, tableV=V); print("P1cv", cov2c, prm, flush=True)
        json.dump(res, open(f"{OUT}/STAGE2_STATIC.json", "w"), indent=1)
