"""EKF3 surrogate vs FFD, and G0 gate (FG lag=1, one GN step) vs EKF3, on B0/seed10/R2."""
import json, numpy as np
from common import *
import ekf3, fg3, surrogate as S
an = env()["spec"]["anchor"]; p = packet("B0", 10, "R2")
e_ffd = ekf3.replay(p, ffd_h, "B0", nstate=3, anchor=an); e_sur = ekf3.replay(p, S.sur_h, "B0", nstate=3, anchor=an)
d = e_sur["x"] - e_ffd["x"]; d[:, 2] = fg3.wrap(d[:, 2])
xg, Pg = fg3.g0(p, e_sur, S.sur_h, ekf3.GYRO_N["B0"]); g = xg - e_sur["x"]; g[:, 2] = fg3.wrap(g[:, 2])
out = dict(ekf3_sur_vs_ffd=dict(max_dpos_m=float(np.abs(d[:, :2]).max()), max_dyaw_deg=float(np.degrees(np.abs(d[:, 2]).max())), mask_diff=int((e_sur["mask"] != e_ffd["mask"]).sum())),
           g0_vs_ekf3_sur=dict(max_dpos_m=float(np.abs(g[:, :2]).max()), max_dyaw_rad=float(np.abs(g[:, 2]).max()), max_dP=float(np.abs(Pg - e_sur["P"]).max())))
print(out); json.dump(out, open(OUT + "/EQUIVALENCE_CHECK.json", "w"), indent=1)
