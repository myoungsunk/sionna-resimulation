import json, glob, numpy as np
from common import OUT
rng = np.random.default_rng(0); res = {}
def boot(d):
    b = [rng.choice(d, len(d)).mean() for _ in range(5000)]; return [float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]
for v in ("real", "s_white", "r_white", "both_white"):
    R = [json.load(open(f)) for f in sorted(glob.glob(f"{OUT}/pre_r4/{v}_s*.json"))]; o = dict(n=len(R))
    for est in ("ekf", "fg"):
        la = np.array([r[est]["log_anees"] for r in R])
        o[est] = dict(anees_geo_mean=float(np.exp(la.mean())), log_anees_ci95=boot(la), anees_median=float(np.median([r[est]["anees"] for r in R])),
                      cover95=float(np.mean([r[est]["cover95"] for r in R])), pos_rmse=float(np.mean([r[est]["pos_rmse"] for r in R])), yaw_rmse_deg=float(np.mean([r[est]["yaw_rmse_deg"] for r in R])))
        o[est]["at_or_below_3.9"] = bool(o[est]["anees_geo_mean"] <= 3 * 1.3)
    res[v] = o
json.dump(res, open(OUT + "/PRE2_R4_DECOMPOSITION.json", "w"), indent=1)
for v, o in res.items():
    print(f"{v:10s} n={o['n']} | EKF ANEES(geo) {o['ekf']['anees_geo_mean']:.2f} med {o['ekf']['anees_median']:.2f} cover {o['ekf']['cover95']:.3f} pos {o['ekf']['pos_rmse']:.3f} yaw {o['ekf']['yaw_rmse_deg']:.2f} | FG ANEES(geo) {o['fg']['anees_geo_mean']:.2f} med {o['fg']['anees_median']:.2f} cover {o['fg']['cover95']:.3f} pos {o['fg']['pos_rmse']:.3f} yaw {o['fg']['yaw_rmse_deg']:.2f}")
