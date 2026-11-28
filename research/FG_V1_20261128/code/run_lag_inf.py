"""lag=inf FG (3-state, surrogate) vs EKF3 (surrogate) on one cell; saves trace npz + summary json."""
import sys, json, numpy as np, time
from common import *
import ekf3, fg3, surrogate as S
cond, seed, route = sys.argv[1], int(sys.argv[2]), sys.argv[3]; budget = float(sys.argv[4]) if len(sys.argv) > 4 else 540
an = env()["spec"]["anchor"]; p = packet(cond, seed, route); T = truth(route); N = ekf3.GYRO_N[cond]
ek = ekf3.replay(p, S.sur_h, cond, nstate=3, anchor=an)
r = fg3.run_isam(p, ek, S.sur_h, N, budget_s=budget); n = len(r["x"])
def stats(x, P, T):
    e = x - T; e[:, 2] = fg3.wrap(e[:, 2])
    nees = np.array([e[i] @ np.linalg.solve(P[i], e[i]) for i in range(len(e))])
    return dict(pos_rmse=float(np.sqrt(np.mean(np.sum(e[:, :2]**2, 1)))), yaw_rmse_deg=float(np.degrees(np.sqrt(np.mean(e[:, 2]**2)))),
                pos_p95=float(np.percentile(np.linalg.norm(e[:, :2], axis=1), 95)), anees3=float(nees.mean()), nees95_frac=float(np.mean(nees <= 7.815)))
out = dict(cell=f"{cond}/seed{seed}/{route}", n_total=len(p["t"]), n_done=n, complete=n == len(p["t"]), wall_s=r["wall"],
           step_ms_mean=float(1e3 * r["t_update"].mean()), step_ms_last100=float(1e3 * r["t_update"][-100:].mean()),
           relin_mean=float(r["relin"].mean()), reelim_mean=float(r["reelim"].mean()), reelim_last=int(r["reelim"][-1]),
           ekf3=stats(ek["x"][:n], ek["P"][:n], T[:n]), fg_lag_inf=stats(r["x"], r["P"], T[:n]),
           surrogate_fallback=S.STATS["fallback"])
np.savez(f"{TRACE}/laginf_{cond}_s{seed}_{route}.npz", fg_x=r["x"], fg_P=r["P"], ekf_x=ek["x"], ekf_P=ek["P"], mask=ek["mask"], Reff=ek["Reff"], truth=T, t_update=r["t_update"], relin=r["relin"], reelim=r["reelim"])
json.dump(out, open(f"{OUT}/laginf_{cond}_s{seed}_{route}.json", "w"), indent=1); print(json.dumps(out))
