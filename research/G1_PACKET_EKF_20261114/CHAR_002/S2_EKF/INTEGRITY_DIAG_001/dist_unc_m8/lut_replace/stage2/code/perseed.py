"""flatten GROUP.json -> per-seed CSV (pooled + route point metrics, I/A/J, mirror, heading bias)"""
import sys, json, glob, os, pandas as pd
src, out = sys.argv[1], sys.argv[2]; rows = []
for f in sorted(glob.glob(f"{src}/*/seed*/GROUP.json")):
    c = f.split("/")[-3]; s = int(f.split("/")[-2][4:]); g = json.load(open(f))
    for a in g["point"]["pooled"]:
        for grp in ("R2", "R4", "R5", "pooled"):
            p = g["point"][grp][a]; sa = g["seed_assessments"]
            rows.append(dict(cond=c, seed=s, arm=a, group=grp, **{k: p[k] for k in ("n", "xy_rmse_cm", "heading_rmse_deg", "mean_nees3", "pose95_coverage", "xy95_coverage", "heading95_coverage")},
                             I_seed=sa["H2"][a]["I_seed"], J_seed_H2S=sa["H2S"][a]["J_seed"], mirror_routes=sa["H2"][a]["mirror_routes"],
                             heading_bias_deg=(g["heading_bias_deg"][grp][a] if "heading_bias_deg" in g and grp != "pooled" else None)))
pd.DataFrame(rows).to_csv(out, index=False); print(len(rows))
