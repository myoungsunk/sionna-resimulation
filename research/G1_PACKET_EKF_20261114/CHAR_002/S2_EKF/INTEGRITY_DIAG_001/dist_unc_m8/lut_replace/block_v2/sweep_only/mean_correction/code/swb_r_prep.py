"""SWB-R preparation (DIAGNOSTIC): S0-style mean correction on SWB labels e = s_full - m (in-sample block at the 7200 station poses).
   rho < 6 m : kriging on e (S0 hyperparameters, as S0-id)
   rho >= 6 m: POWER_BIN_JOINT mu_s per route on e, with the original route weights (b) (as S0-id / SWB-c range calibration)
Outputs: ES_SWB.npy (labels), CAL_SWBR.npz (per-route mu_r, mu_s, Rrr, Rss; mu_r / Rrr copied from S0ID_CAL)."""
import sys, numpy as np, json
for p in ("/home/claude/m8", "/home/claude/m8cal", "/home/claude/lut2", "/home/claude/lut5"): sys.path.insert(0, p)
from common import packet, TRUTH
import stage2_static as S2, sw_block as SB
B = SB.SWB(); m, _, _, a = B.eval(S2.SW.x_eval.values, S2.SW.y_eval.values, S2.SW.psi.values); e = S2.S - m; np.save("ES_SWB.npy", e)
for k in range(3):
    q = S2.BIN == k; print("bin", k, "label rms %.4f mean %.4f" % (np.sqrt(np.mean(e[q]**2)), e[q].mean()))
C0 = np.load("/home/claude/lut0/S0ID_CAL.npz"); out = {}
for r in ("R2", "R4", "R5"):
    p = packet("B0", 10, r); T = S2.F[S2.F.case == f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    h = np.bincount(S2.yawbin(np.degrees(TRUTH[r]["truth"][:, 2])), minlength=36).astype(float); h /= h.sum(); w = h[S2.yawbin(S2.SW.yaw_deg)] * 36; w /= w.mean()
    mu, cov, _ = S2.n4b.fit_model(np, S2.SW.assign(e_s=e), T, w, "POWER_BIN_JOINT", S2.FE.GROUPS)
    out.update({f"{r}/mu_r": C0[f"{r}/mu_r"], f"{r}/Rrr": C0[f"{r}/Rrr"], f"{r}/mu_s": mu[:, 1], f"{r}/Rss": cov[:, 1, 1]})
    rho = np.hypot(T.x_eval - 10, T.y_eval).values; s_full = T.s_fp.values
    mm, _, _, _ = B.eval(T.x_eval.values, T.y_eval.values, T.yaw_eval_rad.values); far = rho >= 6
    print(r, "far packet residual RMS block %.4f  block+POWER %.4f" % (np.sqrt(np.mean((s_full - mm)[far]**2)), np.sqrt(np.mean((s_full - mm - mu[:, 1])[far]**2))))
np.savez("CAL_SWBR.npz", **out)
