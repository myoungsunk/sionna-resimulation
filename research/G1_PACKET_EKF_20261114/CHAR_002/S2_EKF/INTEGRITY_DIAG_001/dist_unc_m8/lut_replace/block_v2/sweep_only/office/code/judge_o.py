"""Office judgement (dev seeds 10-29): per arm N_I (I_seed vs H2), gross (mirror-like) count, seed means of pooled XY / heading RMSE and coverages,
seed-paired ratio SWB-O / F2T1V median and bootstrap 97.5% upper (10,000 resamples, rng 20261119), per-route seed-summed RMSE, heading bias."""
import json, numpy as np, pandas as pd
rows = []; per = []
for cond in ("B0", "L2_GYRO_ARW"):
    for s in range(10, 30):
        g = json.load(open(f"out_o/{cond}/seed{s}/GROUP.json"))
        for a in ("H2", "F2T1V", "SWB-O"):
            p = g["point"]["pooled"][a]
            per.append(dict(cond=cond, seed=s, arm=a, I=bool(g["seed_assessments"][a]["I_seed"]), gross=sum(g["gross"][r][a] for r in ("O01", "O02", "O03L")),
                            xy=p["xy_rmse_cm"], hd=p["heading_rmse_deg"], pose95=p["pose95_coverage"], heading95=p["heading95_coverage"], nees=p["mean_nees3"],
                            **{f"{r}_xy": g["point"][r][a]["xy_rmse_cm"] for r in ("O01", "O02", "O03L")}, **{f"{r}_hd": g["point"][r][a]["heading_rmse_deg"] for r in ("O01", "O02", "O03L")},
                            **{f"{r}_I": bool(g["seed_assessments"][a]["groups"][r]["integrity_pass"]) for r in ("O01", "O02", "O03L")},
                            **{f"{r}_bias": g["heading_bias_deg"][r][a] for r in ("O01", "O02", "O03L")}))
P = pd.DataFrame(per); P.to_csv("OFFICE_PERSEED.csv", index=False)
for cond in ("B0", "L2_GYRO_ARW"):
    q = P[P.cond == cond]
    for a in ("H2", "F2T1V", "SWB-O"):
        z = q[q.arm == a]; row = dict(cond=cond, arm=a, N_I=int(z.I.sum()), gross=int(z.gross.sum()), xy=z.xy.mean(), hd=z.hd.mean(), pose95=z.pose95.mean(), heading95=z.heading95.mean(), nees=z.nees.mean())
        for r in ("O01", "O02", "O03L"): row[f"{r}_xy"] = z[f"{r}_xy"].mean(); row[f"{r}_hd"] = z[f"{r}_hd"].mean(); row[f"{r}_I"] = int(z[f"{r}_I"].sum()); row[f"{r}_bias"] = z[f"{r}_bias"].mean()
        if a == "SWB-O":
            ref = q[q.arm == "F2T1V"].set_index("seed"); cur = z.set_index("seed"); rng = np.random.default_rng(20261119)
            for m in ("xy", "hd"):
                rat = (cur[m] / ref[m]).to_numpy(); bs = np.median(rat[rng.integers(0, len(rat), (10000, len(rat)))], axis=1); row[f"{m}_ratio_med"] = np.median(rat); row[f"{m}_ratio_u975"] = np.quantile(bs, .975)
        rows.append(row)
D = pd.DataFrame(rows); D.to_csv("OFFICE_JUDGE.csv", index=False); pd.set_option("display.width", 300)
print(D[["cond", "arm", "N_I", "gross", "xy", "hd", "pose95", "heading95", "nees", "xy_ratio_med", "xy_ratio_u975", "hd_ratio_med", "hd_ratio_u975"]].round(3).to_string(index=False))
print(D[["cond", "arm", "O01_xy", "O02_xy", "O03L_xy", "O01_hd", "O02_hd", "O03L_hd", "O01_I", "O02_I", "O03L_I", "O01_bias", "O02_bias", "O03L_bias"]].round(2).to_string(index=False))
