import json, numpy as np
from common import *
import ekf3, fg3, surrogate as S
an = env()["spec"]["anchor"]; p = packet("B0", 10, "R5"); T = truth("R5")
ekf = ekf3.replay(p, ffd_h, "B0", nstate=3, anchor=an)
out = {}
# surrogate - FFD s error along the R5 truth, whitened by sqrt(R_ss)
for a, b in ((0, 100), (100, 160), (160, 260)):
    d = []
    for k in range(a, b):
        hs, _ = S.sur_h(T[k]); hf, _ = ffd_h(T[k]); d.append((hs[1] - hf[1]) / np.sqrt(ekf["Reff"][k][1, 1]))
    d = np.array(d); out[f"sur_minus_ffd_s_whitened_k{a}-{b}"] = dict(mean=round(float(d.mean()), 3), rms=round(float(np.sqrt(np.mean(d**2))), 3))
# causal lag=inf with the exact FFD model up to k=260
r = fg3.run_isam(p, ekf, ffd_h, ekf3.GYRO_N["B0"], nmax=261)
ef = np.linalg.norm(r["x"][:, :2] - T[:261, :2], axis=1); ee = np.linalg.norm(ekf["x"][:261, :2] - T[:261, :2], axis=1)
out["FFD_exact_causal_lag_inf_k0-260"] = dict(max_err_FG=round(float(ef.max()), 3), at_k=int(ef.argmax()), EKF_err_there=round(float(ee[ef.argmax()]), 3),
    rmse_FG=round(float(np.sqrt(np.mean(ef**2))), 3), rmse_EKF=round(float(np.sqrt(np.mean(ee**2))), 3), wall_s=round(r["wall"], 1))
print(json.dumps(out, indent=1)); json.dump(out, open(OUT + "/diag_r5_surrogate_vs_ffd.json", "w"), indent=1)
