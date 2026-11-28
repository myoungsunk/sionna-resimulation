"""Pre-diagnostic 1: S-W (model-matched white r and s from surrogate h(truth)) — EKF3 vs FG lag=inf, odom lateral 1e-4 in both. usage: pre_sw.py route seed [cond]"""
import sys, json, os, time
from sw_common import *
route, seed = sys.argv[1], int(sys.argv[2]); cond = sys.argv[3] if len(sys.argv) > 3 else "B0"; LAT = 1e-4
an = env()["spec"]["anchor"]; T = truth(route); p = make_white(packet(cond, seed, route), T, seed); N = ekf3.GYRO_N[cond]
ek = ekf3.replay(p, S.sur_h, cond, nstate=3, anchor=an, lateral=LAT)
t = time.time(); r = fg3.run_isam(p, ek, S.sur_h, N, lateral=LAT)
out = dict(route=route, seed=seed, cond=cond, lateral=LAT, accepted=float(ek["mask"].mean()), fg_wall_s=time.time() - t, ekf=metrics(ek["x"], ek["P"], T), fg=metrics(r["x"], r["P"], T))
os.makedirs(OUT + "/pre_sw", exist_ok=True); json.dump(out, open(f"{OUT}/pre_sw/{cond}_{route}_s{seed}.json", "w"), indent=1)
print(route, seed, round(out["ekf"]["anees"], 2), round(out["fg"]["anees"], 2), round(out["fg_wall_s"]))
