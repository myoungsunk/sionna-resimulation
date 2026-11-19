"""Non-inferiority vs S0-id (plan section 9, amendment 01 A1). Per condition (B0, L2_GYRO_ARW):
  N_I >= N_I(S0-id) - 1 ; seed-paired ratio (cand / S0-id) of pooled XY RMSE and heading RMSE: median, bootstrap 97.5% upper <= 1.10
  (10,000 resamples of seeds, numpy default_rng(20261119)); mirror routes total <= S0-id.
Also reported: N_J (H2S ref), seed-summed route RMSE, mean heading bias.
usage: judge.py <tag> <cand_dir> <arm,arm,...> <s0_dir> <s0_arm> <seed_lo> <seed_hi> <out_csv>"""
import sys, json, numpy as np, pandas as pd
tag, cdir, arms, sdir, sarm, lo, hi, out = sys.argv[1:9]; arms = arms.split(","); seeds = range(int(lo), int(hi) + 1)
def load(dr, c, s): return json.load(open(f"{dr}/{c}/seed{s}/GROUP.json"))
def summ(dr, arm, c):
    R = dict(I=[], J=[], mir=[], xy=[], hd=[], bias=[]); rt = {r: [0., 0., 0.] for r in ("R2", "R4", "R5")}
    for s in seeds:
        g = load(dr, c, s); R["I"].append(g["seed_assessments"]["H2"][arm]["I_seed"]); R["J"].append(g["seed_assessments"]["H2S"][arm]["J_seed"])
        R["mir"].append(g["seed_assessments"]["H2"][arm]["mirror_routes"]); p = g["point"]["pooled"][arm]; R["xy"].append(p["xy_rmse_cm"]); R["hd"].append(p["heading_rmse_deg"])
        R["bias"].append(np.mean([g["heading_bias_deg"][r][arm] for r in rt]) if "heading_bias_deg" in g else np.nan)
        for r in rt:
            q = g["point"][r][arm]; rt[r][0] += q["n"]; rt[r][1] += q["n"] * q["xy_rmse_cm"]**2; rt[r][2] += q["n"] * q["heading_rmse_deg"]**2
    R = {k: np.array(v, float) for k, v in R.items()}; R["route"] = {r: (np.sqrt(v[1] / v[0]), np.sqrt(v[2] / v[0])) for r, v in rt.items()}; return R
rows = []
for c in ("B0", "L2_GYRO_ARW"):
    S = summ(sdir, sarm, c)
    for arm in [sarm + "@ref"] + arms:
        A = S if arm.endswith("@ref") else summ(cdir, arm, c); rng = np.random.default_rng(20261119); res = dict(tag=tag, cond=c, arm=arm.replace("@ref", " (S0-id)"))
        for m in ("xy", "hd"):
            rat = A[m] / S[m]; bs = np.median(rat[rng.integers(0, len(rat), (10000, len(rat)))], axis=1)
            res[f"{m}_ratio_med"] = float(np.median(rat)); res[f"{m}_ratio_u975"] = float(np.quantile(bs, .975))
        res.update(N_I=int(A["I"].sum()), N_J=int(A["J"].sum()), mirror_routes=int(A["mir"].sum()), xy_mean_cm=float(A["xy"].mean()), hd_mean_deg=float(A["hd"].mean()),
                   heading_bias_deg=float(np.nanmean(A["bias"])) if not np.all(np.isnan(A["bias"])) else np.nan,
                   **{f"{r}_xy_cm": v[0] for r, v in A["route"].items()}, **{f"{r}_hd_deg": v[1] for r, v in A["route"].items()})
        res["NI_pass"] = bool(res["N_I"] >= S["I"].sum() - 1 and res["xy_ratio_u975"] <= 1.10 and res["hd_ratio_u975"] <= 1.10 and res["mirror_routes"] <= S["mir"].sum())
        rows.append(res)
D = pd.DataFrame(rows); D.to_csv(out, index=False); pd.set_option("display.width", 300)
print(D[["cond", "arm", "N_I", "N_J", "mirror_routes", "xy_ratio_med", "xy_ratio_u975", "hd_ratio_med", "hd_ratio_u975", "heading_bias_deg", "NI_pass"]].round(3).to_string(index=False))
