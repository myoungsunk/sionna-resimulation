import json, numpy as np, pandas as pd, collections
ARMS=("H0","H2","F2L","F2T0","F2T1nK","F2T1","F2T1V"); ROUTES=("O01","O02","O03L")
pd.set_option("display.width",250)
dec=[]; per=[]; fails=collections.defaultdict(collections.Counter)
for c in ("B0","L2_GYRO_ARW"):
    G=[json.load(open(f"out_o3/{c}/seed{s}/GROUP.json")) for s in range(10,30)]
    for a in ARMS:
        sa=[g["seed_assessments"][a] for g in G]
        dec.append(dict(cond=c,arm=a,N_I=sum(x["I_seed"] for x in sa),N_A=sum(x["A_seed"] for x in sa),N_J=sum(x["J_seed"] for x in sa),
                        gross=sum(g["gross"][r][a] for g in G for r in ROUTES)))
        for x in sa:
            for gname,gg in x["groups"].items():
                for it in gg["integrity_failures"]:
                    if not it.endswith("ci10_lower"): fails[(c,a)][f"{gname}:{it}"]+=1
        for r in (*ROUTES,"pooled"):
            P=[g["point"][r][a] for g in G]; n=np.array([p["n"] for p in P]); f=lambda k: np.array([p[k] for p in P])
            per.append(dict(cond=c,arm=a,route=r,xy=np.sqrt(np.sum(n*f("xy_rmse_cm")**2)/n.sum()),hd=np.sqrt(np.sum(n*f("heading_rmse_deg")**2)/n.sum()),
                            pose95=np.sum(n*f("pose95_coverage"))/n.sum(),xy95=np.sum(n*f("xy95_coverage"))/n.sum(),hd95=np.sum(n*f("heading95_coverage"))/n.sum(),nees=np.sum(n*f("mean_nees3"))/n.sum()))
D=pd.DataFrame(dec); P=pd.DataFrame(per)
D.to_csv("O3_DECISION.csv",index=False); P.to_csv("O3_ROUTE_POOLED.csv",index=False)
print(D.pivot_table(index="arm",columns="cond",values=["N_I","N_A","N_J","gross"]).reindex(ARMS).to_string())
for c in ("B0",):
    p=P[P.cond==c]; h=p[p.arm=="H2"].set_index("route")
    for r in (*ROUTES,"pooled"):
        print("==",c,r); q=p[p.route==r].set_index("arm").reindex(ARMS)
        q["dxy%"]=100*(q.xy/h.loc[r,"xy"]-1); q["dhd%"]=100*(q.hd/h.loc[r,"hd"]-1)
        print(q[["xy","dxy%","hd","dhd%","pose95","xy95","hd95","nees"]].round(3).to_string())
for k in [("B0","F2T1"),("B0","F2L"),("B0","H2")]: print(k, dict(fails[k].most_common(8)))
