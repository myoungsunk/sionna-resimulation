"""Pre-diagnostic 2: R4 overconfidence decomposition (current T0 config: no lateral noise in EKF, 1e-10 regularization in FG).
usage: pre_r4.py variant seed   variant in real | s_white | r_white | both_white"""
import sys, json, os
from sw_common import *
var, seed = sys.argv[1], int(sys.argv[2]); cond = "B0"; route = "R4"
an = env()["spec"]["anchor"]; T = truth(route); p0 = packet(cond, seed, route)
rows = {"real": None, "s_white": (1,), "r_white": (0,), "both_white": (0, 1)}[var]
p = p0 if rows is None else make_white(p0, T, seed, rows)
ek = ekf3.replay(p, S.sur_h, cond, nstate=3, anchor=an); r = fg3.run_isam(p, ek, S.sur_h, ekf3.GYRO_N[cond])
out = dict(route=route, seed=seed, variant=var, accepted=float(ek["mask"].mean()), ekf=metrics(ek["x"], ek["P"], T), fg=metrics(r["x"], r["P"], T))
os.makedirs(OUT + "/pre_r4", exist_ok=True); json.dump(out, open(f"{OUT}/pre_r4/{var}_s{seed}.json", "w"), indent=1)
print(var, seed, round(out["ekf"]["anees"], 2), round(out["fg"]["anees"], 2))
