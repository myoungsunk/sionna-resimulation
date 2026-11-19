"""Stage 1 cause split for the failed z_s gate (plan section 9: decompose before proceeding). Not a re-test of the gate.
Same LUT (K=8, J=6) and same z_s definition (A5), but hold-out = one station (LOSO) instead of a 1.75 m x-block,
which matches the operating density (routes run within 0.15 m of a sweep line). Also: where the near-range LUT error sits."""
import sys, json, importlib.util, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/lut1"); sys.path.insert(0, "/home/claude/m8cal")
from emp_lut import EmpLUT
from feats import FE, FZ
s = importlib.util.spec_from_file_location("n4b", f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py")
n4b = importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
SW = pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); SW["e_s_id"] = np.load("/home/claude/lut0/ES_FFDREF_CORRIDOR.npy")
SW["s_los"] = SW.s_fp - SW.e_s; SW["psi"] = np.radians(SW.yaw_deg); A = (10., 0., 2.65); K, J = 8, 6
EDG = np.array([0., 3., 6., 10.]); SW["b"] = np.clip(np.searchsorted(EDG, SW.rho, side="right") - 1, 0, 2)
SW["st"] = SW.x_eval.round(3).astype(str) + "_" + SW.y_eval.round(2).astype(str)
X, Y, P, S = SW.x_eval.to_numpy(), SW.y_eval.to_numpy(), SW.psi.to_numpy(), SW.s_fp.to_numpy()
pred = np.empty(len(SW)); a_cv = np.empty(len(SW)); mu = np.empty(len(SW))
P_ = json.load(open("/home/claude/m8cal/KRIGE_PARAMS.json")); V = json.load(open("/home/claude/lut0/S0ID_TABLES.json"))["tableV"]
def wrap(a): return (a + np.pi) % (2 * np.pi) - np.pi
for st in SW.st.unique():
    te = (SW.st == st).to_numpy(); tr = ~te
    L = EmpLUT(A, K, J, 1).fit(X[tr], Y[tr], P[tr], S[tr]); s_, _, _, ap = L.eval(X[te], Y[te], P[te]); pred[te] = s_; a_cv[te] = ap
    k = int(SW.b[te].iloc[0])
    if k == 2:
        m2, _, _ = n4b.fit_model(np, SW[tr].assign(e_s=SW.e_s_id[tr]).reset_index(drop=True), SW[te].reset_index(drop=True), np.ones(tr.sum()), "POWER_BIN_JOINT", FE.GROUPS)
        mu[te] = m2[:, 1]; continue
    trk = tr & (SW.b == k).to_numpy(); Xt = SW.loc[trk, ["x_eval", "y_eval", "psi"]].to_numpy(); yt = SW.e_s_id[trk].to_numpy(); mu0 = yt.mean()
    lx, ly, lp, nug = P_[f"e_s|{k}"]["params"]
    for i in np.flatnonzero(te):
        q = SW.loc[i, ["x_eval", "y_eval", "psi"]].to_numpy(float)
        d = np.abs(Xt[:, 0] - q[0]) / lx + np.abs(Xt[:, 1] - q[1]) / ly + np.abs(wrap(Xt[:, 2] - q[2])) / lp
        idx = np.argpartition(d, 150)[:150]; Xi = Xt[idx]
        Km = np.exp(-(np.abs(Xi[:, 0, None] - Xi[None, :, 0]) / lx + np.abs(Xi[:, 1, None] - Xi[None, :, 1]) / ly + np.abs(wrap(Xi[:, 2, None] - Xi[None, :, 2])) / lp))
        w = np.linalg.solve((1 - nug) * Km + nug * np.eye(150), (1 - nug) * np.exp(-d[idx])); mu[i] = mu0 + w @ (yt[idx] - mu0)
c1 = np.array(V["c1"])[SW.b]; c0 = np.array(V["c0"])[SW.b]
z_emp = (S - pred - mu) / np.sqrt(c1 * a_cv**2 + c0); z_ffd = (SW.e_s_id.to_numpy() - mu) / np.sqrt(c1 * SW.a.to_numpy()**2 + c0)
# kriging-on-EMP-labels variant (what Stage 3 would do): labels s_full - h_emp absorb LUT error -> mean from those labels
rows = []
for k in range(3):
    m = (SW.b == k).to_numpy()
    rows.append(dict(bin=["<3 m", "3-6 m", ">=6 m"][k], rmse_s_emp_loso=float(np.sqrt(np.mean((S - pred)[m]**2))), rmse_s_ffd=float(np.sqrt(np.mean(SW.e_s_id[m]**2))),
                     hemp_minus_slos_rms=float(np.sqrt(np.mean((pred - SW.s_los)[m]**2))), zcov_emp_loso=float(np.mean(np.abs(z_emp[m]) <= 1.96)),
                     zcov_ffd_loso=float(np.mean(np.abs(z_ffd[m]) <= 1.96)), sign_agree=float(np.mean(np.sign(a_cv[m & (np.abs(SW.a) >= .3).to_numpy()]) == np.sign(SW.a[m & (np.abs(SW.a) >= .3).to_numpy()])))))
R = pd.DataFrame(rows)
# where the near LUT error sits: by rho slice
SW["err_emp"] = pred - SW.s_los; SW["rslice"] = pd.cut(SW.rho, [0, .5, 1, 1.5, 2, 3, 4.5, 6, 10])
Q = SW.groupby("rslice", observed=True).agg(n=("rho", "size"), hemp_minus_slos_rms=("err_emp", lambda v: float(np.sqrt(np.mean(v**2)))),
                                            e_s_rms=("e_s", lambda v: float(np.sqrt(np.mean(v**2))))).reset_index()
R.to_csv("/home/claude/lut1/STAGE1_CAUSE_LOSO.csv", index=False); Q.astype({"rslice": str}).to_csv("/home/claude/lut1/STAGE1_CAUSE_RHO.csv", index=False)
pd.set_option("display.width", 250); print(R.round(4).to_string(index=False)); print(Q.round(4).to_string(index=False))
