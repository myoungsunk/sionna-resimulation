"""First-pass static characterisation on N1-N6 (truth poses, full channel, anchor B, mount 0).
r_s = s_fp - m_fullco(x, y, yaw);  r_r = range - (d3D + B_OLD) - mu_r(U3 HGB, V1)."""
import sys, json, pickle, numpy as np, pandas as pd
sys.path[:0] = ["/home/claude/v1", "/home/claude/lut0", "/home/claude/m8"]
from v1_common import EXIST, B_OLD
import sw_block_fullco as SB
F = pd.read_csv("/home/claude/n1n6/cir_features/OBSERVATION_FEATURES.csv.gz"); F = F[(F.channel == "full")].copy()
g, Rrr, Rss = pickle.load(open("/home/claude/v1/CAL_V1.pkl", "rb")); B = SB.SWB(); fn = B.s_fn()
A = np.array([10., 0., 2.65]); out = []
for r in [f"N{i}" for i in range(1, 7)]:
    q = F[F.case == f"{r}_aB_m0"].sort_values("t").copy()
    st = np.c_[q.x_eval, q.y_eval, q.yaw_eval_rad, np.zeros(len(q))]; m, J = fn(st, None)
    d3 = np.sqrt((q.x_eval - A[0])**2 + (q.y_eval - A[1])**2 + (q.z_eval - A[2])**2)
    q["r_s"] = q.s_fp - m; q["a"] = J[:, 2]; q["r_r"] = q.range_m - (d3 + B_OLD) - g.predict(q[EXIST]); q["d"] = d3
    q["rho"] = np.hypot(q.x_eval - A[0], q.y_eval - A[1]); q["route"] = r
    dxy = np.r_[0, np.hypot(np.diff(q.x_eval), np.diff(q.y_eval))]; dps = np.r_[0, np.abs(np.angle(np.exp(1j * np.diff(q.yaw_eval_rad))))]
    q["arc"] = np.cumsum(dxy); q["yawc"] = np.cumsum(dps); out.append(q)
Q = pd.concat(out); Q.to_csv("N1N6_RESID.csv.gz", index=False)
print(Q.groupby("route").agg(n=("t", "size"), rs_rms=("r_s", lambda v: np.sqrt(np.mean(v**2))), rr_rms_cm=("r_r", lambda v: 100 * np.sqrt(np.mean(v**2))),
      rep=("range_m", lambda v: np.mean(np.r_[False, np.diff(v.values) == 0]))).round(4).to_string())
