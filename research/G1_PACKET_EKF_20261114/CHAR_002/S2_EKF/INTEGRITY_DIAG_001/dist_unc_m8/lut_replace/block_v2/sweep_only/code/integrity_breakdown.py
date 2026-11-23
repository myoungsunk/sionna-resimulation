"""SWB integrity breakdown (dev seeds 10-29, B0 / L2_GYRO_ARW) and comparison with H2, H2S, S0-id.
Outputs: SWB_INTEGRITY_BREAKDOWN.csv (per condition, seed, arm: I_seed, failing criteria, pooled Pose95 / Heading95 / XY95 / NEES),
         SWB_VS_REFS.csv (seed means of pooled XY RMSE, heading RMSE, Pose95, Heading95, NEES and N_I)."""
import json, numpy as np, pandas as pd
rows = []
for cond in ("B0", "L2_GYRO_ARW"):
    for s in range(10, 30):
        g = json.load(open(f"out_swb/{cond}/seed{s}/GROUP.json")); c = json.load(open(f"/home/claude/lut0/out_c0/C03/{cond}/seed{s}/GROUP.json"))
        for arm, src, k in (("H2", g, "H2"), ("H2S", g, "H2S"), ("SWB", g, "SWB"), ("S0-id", c, "F2SKRWV")):
            sa = src["seed_assessments"]["H2"][k]; grp = sa.get("groups", sa); fails = []
            for name in ("R2", "R4", "R5", "pooled"):
                if name in grp and not grp[name]["integrity_pass"]: fails += [f"{name}:{f}" for f in grp[name]["integrity_failures"]]
            p = src["point"]["pooled"][k]
            rows.append(dict(cond=cond, seed=s, arm=arm, I_seed=bool(sa["I_seed"]), failures=";".join(fails), xy_rmse_cm=p["xy_rmse_cm"], heading_rmse_deg=p["heading_rmse_deg"],
                             pose95=p["pose95_coverage"], heading95=p["heading95_coverage"], xy95=p["xy95_coverage"], mean_nees3=p["mean_nees3"]))
D = pd.DataFrame(rows); D.to_csv("SWB_INTEGRITY_BREAKDOWN.csv", index=False)
S = D.groupby(["cond", "arm"], sort=False).agg(N_I=("I_seed", "sum"), xy_rmse_cm=("xy_rmse_cm", "mean"), heading_rmse_deg=("heading_rmse_deg", "mean"), pose95=("pose95", "mean"),
    pose95_min=("pose95", "min"), heading95=("heading95", "mean"), mean_nees3=("mean_nees3", "mean")).reset_index()
S.to_csv("SWB_VS_REFS.csv", index=False); pd.set_option("display.width", 200); print(S.round(3).to_string(index=False))
