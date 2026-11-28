"""Summarize pre-diagnostic 1 (S-W EKF vs FG): paired FG-EKF differences per route with seed bootstrap 95% CI; equivalence margin ln 1.15."""
import json, glob, numpy as np
from common import OUT
D = np.log(1.15); rng = np.random.default_rng(0); res = {}
rows = [json.load(open(f)) for f in sorted(glob.glob(OUT + "/pre_sw/B0_*.json"))]
def boot(d):
    b = [rng.choice(d, len(d)).mean() for _ in range(5000)]; return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]
for route in ("R2", "R4", "R5", "ALL"):
    R = [r for r in rows if route == "ALL" or r["route"] == route]
    out = dict(n=len(R))
    for m in ("log_anees", "cover95", "pos_rmse", "yaw_rmse_deg"):
        e = np.array([r["ekf"][m] for r in R]); f = np.array([r["fg"][m] for r in R]); d = f - e
        out[m] = dict(ekf_mean=float(e.mean()), fg_mean=float(f.mean()), diff_mean=float(d.mean()), diff_ci95=boot(d))
    ci = out["log_anees"]["diff_ci95"]; out["equivalent_log_anees_within_ln1.15"] = bool(-D < ci[0] and ci[1] < D)
    out["anees_median_ekf_fg"] = [float(np.median([r["ekf"]["anees"] for r in R])), float(np.median([r["fg"]["anees"] for r in R]))]
    res[route] = out
bad = [dict(route=r["route"], seed=r["seed"], ekf=r["ekf"], fg=r["fg"]) for r in rows if r["ekf"]["anees"] > 50 or r["fg"]["anees"] > 50]
res["outliers_anees_gt_50"] = bad
R = [r for r in rows if not (r["route"] == "R5" and r["seed"] == 14)]
d = np.array([r["fg"]["log_anees"] - r["ekf"]["log_anees"] for r in R]); res["ALL_excluding_R5_s14"] = dict(n=len(R), log_anees_diff_mean=float(d.mean()), ci95=boot(d), equivalent=bool(-D < boot(d)[0] and boot(d)[1] < D))
json.dump(res, open(OUT + "/PRE1_SW_EKF_VS_FG.json", "w"), indent=1)
for k in ("R2", "R4", "R5", "ALL"):
    o = res[k]; print(k, "n", o["n"], "| log ANEES EKF %.3f FG %.3f diff %.3f CI [%.3f, %.3f] equiv %s" % (o["log_anees"]["ekf_mean"], o["log_anees"]["fg_mean"], o["log_anees"]["diff_mean"], *o["log_anees"]["diff_ci95"], o["equivalent_log_anees_within_ln1.15"]),
          "| cover95 EKF %.3f FG %.3f | pos RMSE EKF %.3f FG %.3f | yaw EKF %.2f FG %.2f | median ANEES %.2f/%.2f" % (o["cover95"]["ekf_mean"], o["cover95"]["fg_mean"], o["pos_rmse"]["ekf_mean"], o["pos_rmse"]["fg_mean"], o["yaw_rmse_deg"]["ekf_mean"], o["yaw_rmse_deg"]["fg_mean"], *o["anees_median_ekf_fg"]))
print("excl R5 s14:", res["ALL_excluding_R5_s14"]); print("outliers:", [(b["route"], b["seed"], round(b["ekf"]["anees"], 1), round(b["ekf"]["pos_max"], 2), round(b["fg"]["anees"], 1), round(b["fg"]["pos_max"], 2)) for b in bad])
