import json, glob, numpy as np, pandas as pd
ROUTES=("R2","R4","R5"); ARMS=("H2S","C0","C1","C2","C3","C4"); rows=[]
for f in sorted(glob.glob("/home/claude/tc/out_c/B0/seed*/GROUP.json")):
    g=json.load(open(f)); s=int(f.split("seed")[-1].split("/")[0]); P=g["point"]
    for a in ARMS:
        n=np.array([P[r][a]["n"] for r in ROUTES],float); w=n/n.sum()
        rows.append(dict(seed=s,arm=a,xy=float(np.sqrt(w@[P[r][a]["xy_rmse_cm"]**2 for r in ROUTES])),hd=float(np.sqrt(w@[P[r][a]["heading_rmse_deg"]**2 for r in ROUTES])),
            pose95=P["pooled"][a]["pose95_coverage"],h95=P["pooled"][a]["heading95_coverage"],xy95=P["pooled"][a]["xy95_coverage"],nees3=P["pooled"][a]["mean_nees3"],
            I=g["I"][a]["I_seed"],mir=sum(g["mirror"][r][a] for r in ROUTES)>0, **{f"xy95_{r}":P[r][a]["xy95_coverage"] for r in ROUTES}, **{f"mir_{r}":g["mirror"][r][a]>0 for r in ROUTES}))
D=pd.DataFrame(rows); D.to_csv("C_PERSEED.csv",index=False); rng=np.random.default_rng(0)
def boot(x,B=10000):
    x=np.asarray(x); i=rng.integers(0,len(x),(B,len(x))); return float(np.median(x)),float(np.quantile(np.median(x[i],1),.975))
out=[]; ref=D[D.arm=="C0"].set_index("seed")
for a in ARMS:
    s=D[D.arm==a].set_index("seed").loc[ref.index]; r=dict(arm=a,N_I=int(s.I.sum()),mirror=int(s.mir.sum()),xy=s.xy.median(),hd=s.hd.median(),pose95=s.pose95.median(),h95=s.h95.median(),xy95=s.xy95.median(),nees3=s.nees3.median(),
        **{f"xy95_{q}":s[f"xy95_{q}"].median() for q in ROUTES},**{f"mir_{q}":int(s[f"mir_{q}"].sum()) for q in ROUTES})
    if a not in ("C0","H2S"): r["xy_ratio"],r["xy_u975"]=boot(s.xy/ref.xy); r["hd_ratio"],r["hd_u975"]=boot(s.hd/ref.hd); r["noninf"]=bool(r["N_I"]>=out[1]["N_I"]-1 and r["xy_u975"]<=1.1 and r["hd_u975"]<=1.1 and r["mirror"]<=out[1]["mirror"])
    out.append(r)
S=pd.DataFrame(out); S.to_csv("C_SUMMARY.csv",index=False); pd.set_option("display.width",250); print(S.round(3).to_string(index=False))
