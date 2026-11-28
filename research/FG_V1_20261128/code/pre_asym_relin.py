"""Pre-diagnostic 3a: R5/B0/seed10 real data, FG lag=inf with relinearization off and a threshold sweep vs EKF3. usage: pre_asym_relin.py thr"""
import sys, json, os
from sw_common import *
thr = float(sys.argv[1]); an = env()["spec"]["anchor"]; T = truth("R5"); p = packet("B0", 10, "R5")
ek = ekf3.replay(p, S.sur_h, "B0", nstate=3, anchor=an); r = fg3.run_isam(p, ek, S.sur_h, ekf3.GYRO_N["B0"], thr=thr)
d = r["x"] - ek["x"]; d[:, 2] = fg3.wrap(d[:, 2]); pe = np.linalg.norm(r["x"][:, :2] - T[:, :2], axis=1)
out = dict(threshold=thr, max_dpos_vs_ekf_m=float(np.abs(d[:, :2]).max()), max_dyaw_vs_ekf_deg=float(np.degrees(np.abs(d[:, 2]).max())),
           fg_max_err_k100_200=float(pe[100:200].max()), fg=metrics(r["x"], r["P"], T), ekf=metrics(ek["x"], ek["P"], T), relin_mean=float(r["relin"].mean()), wall_s=r["wall"])
os.makedirs(OUT + "/pre_asym", exist_ok=True); json.dump(out, open(f"{OUT}/pre_asym/relin_thr_{thr:g}.json", "w"), indent=1)
print(thr, {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items() if k not in ("fg", "ekf")}, "FG pos RMSE %.3f ANEES %.2f" % (out["fg"]["pos_rmse"], out["fg"]["anees"]))
