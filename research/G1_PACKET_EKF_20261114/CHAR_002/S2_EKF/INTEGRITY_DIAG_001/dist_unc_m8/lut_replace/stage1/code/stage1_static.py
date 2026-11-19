"""Stage 1 static part (plan amendment 01: A2 selection, A3 sign gate, A5 z_s gate). Corridor 5-line sweep, Full only for the LUT.
Spatial blocks: 10 contiguous x blocks over station positions (all 5 lines removed together)."""
import sys, json, itertools, importlib.util, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/lut1"); sys.path.insert(0, "/home/claude/m8cal")
from emp_lut import EmpLUT
from feats import FE, FZ
s = importlib.util.spec_from_file_location("n4b", f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py")
n4b = importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["e_s_id"] = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
SW["s_los"] = SW.s_fp - SW.e_s; SW["psi"] = np.radians(SW.yaw_deg); A = (10., 0., 2.65)
EDG = np.array([0., 3., 6., 10.]); SW["b"] = np.clip(np.searchsorted(EDG, SW.rho, side="right") - 1, 0, 2)
xs = np.sort(SW.x_eval.unique()); blk_of_x = {x: int(i * 10 // len(xs)) for i, x in enumerate(xs)}; SW["blk"] = SW.x_eval.map(blk_of_x)
X, Y, P, S = SW.x_eval.to_numpy(), SW.y_eval.to_numpy(), SW.psi.to_numpy(), SW.s_fp.to_numpy()
def cv_pred(K, J):
    pred = np.empty(len(SW)); a = np.empty(len(SW))
    for b in range(10):
        tr, te = SW.blk != b, SW.blk == b
        L = EmpLUT(A, K, J, 1).fit(X[tr], Y[tr], P[tr], S[tr]); s_, _, _, ap = L.eval(X[te], Y[te], P[te]); pred[te] = s_; a[te] = ap
    return pred, a
sel = []
for K, J in itertools.product((2, 4, 6, 8), (4, 6, 8)):
    pred, _ = cv_pred(K, J); sel.append(dict(K=K, J=J, n_param=(2 * K + 1) * J * 3, cv_rmse=float(np.sqrt(np.mean((S - pred)**2))),
                                             **{f"cv_rmse_bin{k}": float(np.sqrt(np.mean((S - pred)[SW.b == k]**2))) for k in range(3)}))
    print(sel[-1], flush=True)
SEL = pd.DataFrame(sel); best = SEL.loc[SEL.cv_rmse.idxmin()]; K, J = int(best.K), int(best.J)
pred, a_cv = cv_pred(K, J)
# A5: leave-block-out mu_s (S0-id labels): kriging for rho < 6 (S0 hyper-parameters), POWER (uniform w) elsewhere
P_ = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json")); V = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
mu = np.empty(len(SW))
for b in range(10):
    tr, te = (SW.blk != b).to_numpy(), (SW.blk == b).to_numpy()
    m2, _, _ = n4b.fit_model(np, SW[tr].assign(e_s=SW.e_s_id[tr]).reset_index(drop=True), SW[te].reset_index(drop=True), np.ones(tr.sum()), "POWER_BIN_JOINT", FE.GROUPS)
    mu[te] = m2[:, 1]
    for k in (0, 1):
        trk = tr & (SW.b == k).to_numpy(); Xt = SW.loc[trk, ["x_eval", "y_eval", "psi"]].to_numpy(); yt = SW.e_s_id[trk].to_numpy(); mu0 = yt.mean()
        lx, ly, lp, nug = P_[f"e_s|{k}"]["params"]
        for i in np.flatnonzero(te & (SW.b == k).to_numpy()):
            q = SW.loc[i, ["x_eval", "y_eval", "psi"]].to_numpy(float)
            d = np.abs(Xt[:, 0] - q[0]) / lx + np.abs(Xt[:, 1] - q[1]) / ly + np.abs(wrap(Xt[:, 2] - q[2])) / lp
            idx = np.argpartition(d, 150)[:150]; Xi = Xt[idx]
            Km = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
            w = np.linalg.solve((1 - nug) * Km + nug * np.eye(150), (1 - nug) * np.exp(-d[idx])); mu[i] = mu0 + w @ (yt[idx] - mu0)
c1 = np.array(V["c1"])[SW.b]; c0 = np.array(V["c0"])[SW.b]
z_emp = (S - pred - mu) / np.sqrt(c1 * a_cv**2 + c0); z_ffd = (S - (S - SW.e_s_id.to_numpy()) - mu) / np.sqrt(c1 * SW.a.to_numpy()**2 + c0)
rows = []
for k in range(3):
    m = (SW.b == k).to_numpy(); hi = m & (np.abs(SW.a) >= .3).to_numpy()
    rows.append(dict(bin=["<3 m", "3-6 m", ">=6 m"][k], n=int(m.sum()),
                     rmse_s_emp_cv=float(np.sqrt(np.mean((S - pred)[m]**2))), rmse_s_ffd=float(np.sqrt(np.mean(SW.e_s_id[m]**2))),
                     hemp_minus_slos_rms=float(np.sqrt(np.mean((pred - SW.s_los)[m]**2))),
                     sign_agree_absa_ge_0p3=float(np.mean(np.sign(a_cv[hi]) == np.sign(SW.a[hi]))), n_sign=int(hi.sum()),
                     corr_a=float(np.corrcoef(a_cv[m], SW.a[m])[0, 1]), a_rms_ratio=float(np.sqrt(np.mean(a_cv[m]**2)) / np.sqrt(np.mean(SW.a[m]**2))),
                     zcov_emp=float(np.mean(np.abs(z_emp[m]) <= 1.96)), zcov_ffd=float(np.mean(np.abs(z_ffd[m]) <= 1.96))))
G = pd.DataFrame(rows); G["gate_sign"] = G.sign_agree_absa_ge_0p3 >= .95; G["gate_z"] = G.zcov_emp >= .90
L = EmpLUT(A, K, J, 1).fit(X, Y, P, S)
json.dump(dict(selection=SEL.to_dict(orient="records"), chosen=dict(K=K, J=J), gates=G.to_dict(orient="records"),
               gates_pass=bool(G.gate_sign.all() and G.gate_z.all()), lut=L.to_dict()), open("/home/claude/lut1/STAGE1_STATIC.json", "w"), indent=1)
pd.set_option("display.width", 250); print(SEL.round(4).to_string(index=False)); print("chosen", K, J); print(G.round(4).to_string(index=False))
