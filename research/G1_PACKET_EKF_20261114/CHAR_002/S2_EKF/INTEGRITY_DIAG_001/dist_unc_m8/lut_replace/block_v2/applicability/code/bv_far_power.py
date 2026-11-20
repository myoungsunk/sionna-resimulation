"""Far range (rho >= 6 m) at packet poses: residual of s_full against (a) h_FFD, (b) S0-id h_FFD + POWER mu_s (runtime channel features),
(c) BV block, (d) BV block + POWER refit on BV labels (s_full - m at stations). Near/mid for reference with kriging omitted."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "/home/claude/m8"); sys.path.insert(0, "/home/claude/m8cal"); sys.path.insert(0, "/home/claude/lut2"); sys.path.insert(0, "/home/claude/lut3"); sys.path.insert(0, "/home/claude/lut0")
from common import env, packet, TRUTH
import h_ref as HR, bv_block as BVM, stage2_static as S2
e0 = env(); base, spec = e0["model"], e0["spec"]; ffd = HR.ffd_s_fn(base); SW = S2.SW; bv = BVM.BV(ffd, spec, SW)
Xs = np.c_[SW.x_eval, SW.y_eval, SW.psi, np.zeros(len(SW))]; mS, _ = bv.s_fn()(Xs, spec); e_bv = SW.s_fp.values - mS
B0 = np.load("/home/claude/lut0/S0ID_CAL.npz"); rows = []
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r); T = S2.F[S2.F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    h = np.bincount(S2.yawbin(np.degrees(TRUTH[r]["truth"][:, 2])), minlength=36).astype(float); h /= h.sum(); wgt = h[S2.yawbin(SW.yaw_deg)] * 36; wgt /= wgt.mean()
    mu_bv, _, _ = S2.n4b.fit_model(np, SW.assign(e_s=e_bv), T, wgt, "POWER_BIN_JOINT", S2.FE.GROUPS)
    X = np.c_[T.x_eval, T.y_eval, T.yaw_eval_rad, np.zeros(len(T))]; s = T.s_fp.values; hF, JF = ffd(X, spec); m, J = bv.s_fn()(X, spec)
    rho = np.hypot(T.x_eval - 10, T.y_eval).values; b = np.clip(np.searchsorted(BVM.EDG, rho, side="right") - 1, 0, 2)
    preds = {"LoS": (hF, JF[:, 2]), "S0-id POWER": (hF + B0[f"{r}/mu_s"], JF[:, 2]), "BV": (m, J[:, 2]), "BV + POWER": (m + mu_bv[:, 1], J[:, 2])}
    for nm, (pr, a) in preds.items():
        e = s - pr
        for i in range(3):
            q = b == i
            rows.append(dict(route=r, bin=["<3 m", "3-6 m", ">=6 m"][i], arm=nm, n=int(q.sum()), mean=e[q].mean(), head_eq=np.degrees(-np.mean(e[q] * a[q]) / np.mean(a[q]**2)), rms=np.sqrt(np.mean(e[q]**2))))
D = pd.DataFrame(rows)
A = D.groupby(["bin", "arm"]).apply(lambda q: pd.Series(dict(n=q.n.sum(), mean=np.average(q["mean"], weights=q.n), head_eq=np.average(q.head_eq, weights=q.n), rms=np.sqrt(np.average(q.rms**2, weights=q.n)))))
pd.set_option("display.width", 200); print(A.round(4).to_string()); D.to_csv("BV_FAR_POWER.csv", index=False)
