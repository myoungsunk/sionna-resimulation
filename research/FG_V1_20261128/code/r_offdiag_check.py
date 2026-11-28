"""R off-diagonal over all M7 packets (B0, L2_GYRO_ARW x seeds 10-29 x R2/R4/R5) and joint vs split [r, s] FG on B0/seed10/R2."""
import json, numpy as np
from common import *
import ekf3, fg3, surrogate as S
rows = []
for c in ("B0", "L2_GYRO_ARW"):
    for s in range(10, 30):
        for r in ("R2", "R4", "R5"):
            p = packet(c, s, r); rows.append(dict(cell=f"{c}/seed{s}/{r}", n=len(p["R"]), max_abs_offdiag=float(np.abs(p["R"][:, 0, 1]).max())))
an = env()["spec"]["anchor"]; p = packet("B0", 10, "R2"); ek = ekf3.replay(p, S.sur_h, "B0", nstate=3, anchor=an)
a = fg3.run_isam(p, ek, S.sur_h, ekf3.GYRO_N["B0"]); b = fg3.run_isam(p, ek, S.sur_h, ekf3.GYRO_N["B0"], split=True)
out = dict(packets_total=sum(r["n"] for r in rows), cells=len(rows), max_abs_offdiag_packet_R=max(r["max_abs_offdiag"] for r in rows),
           Reff_note="EKF adds sigma_b^2 to R[1,1] only, so Reff off-diagonal is also 0",
           joint_vs_split_FG_B0_seed10_R2=dict(max_abs_dx=float(np.abs(a["x"] - b["x"]).max()), max_abs_dP=float(np.abs(a["P"] - b["P"]).max()), wall_joint_s=a["wall"], wall_split_s=b["wall"]),
           gating_note="EKF gate is the joint 2D NIS (9.21) on [r, s]; split factors reuse that joint mask. A split design needs its own gating rule.",
           per_cell=rows)
json.dump(out, open(OUT + "/R_OFFDIAG_AND_SPLIT_CHECK.json", "w"), indent=1); print({k: v for k, v in out.items() if k != "per_cell"})
