import json,glob,numpy as np,pandas as pd
ARMS=("H0","H1","H2","H3","F1","F2","F1S","F2S")
rows=[]
for cond in ("B0","L2_GYRO_ARW"):
    for f in sorted(glob.glob(f"/home/claude/m8/out_sweep/{cond}/own/seed*/GROUP.json")):
        g=json.load(open(f))
        for grp in ("R2","R4","R5","pooled"):
            for a in ARMS:
                p=g["point"][grp][a]
                rows.append(dict(cond=cond,seed=g["seed"],group=grp,arm=a,head=p["heading_rmse_deg"],xy=p["xy_rmse_cm"],pose95=p["pose95_coverage"],h95=p["heading95_coverage"],nees=p["mean_nees3"],
                                 J=g["seed_assessments"][a]["J_seed"]))
D=pd.DataFrame(rows); D.to_csv("/home/claude/m8/POINT_BY_SEED_SWEEP.csv",index=False)
pd.set_option("display.width",250)
print("== 궤적별 중앙값 (20 seed): heading RMSE ° / XY RMSE cm / Pose95 / Heading95")
for cond in ("B0","L2_GYRO_ARW"):
    s=D[D["cond"]==cond]; m=s.groupby(["group","arm"])[["head","xy","pose95","h95","nees"]].median().round(3)
    print(f"-- {cond}"); print(m.unstack("group").reorder_levels([1,0],axis=1).sort_index(axis=1).to_string())
print("\n== H2 대비 RMSE 비용 중앙값 (%), seed별 짝 / DR(H0)·거리단독(H1) 대비 개선 중앙값 (%)")
for cond in ("B0","L2_GYRO_ARW"):
    s=D[D["cond"]==cond].set_index(["seed","group","arm"])
    out=[]
    for a in ("H3","F1","F2","F1S","F2S"):
        for grp in ("R2","R4","R5","pooled"):
            x=s.xs((grp,a),level=("group","arm")); h2=s.xs((grp,"H2"),level=("group","arm")); h0=s.xs((grp,"H0"),level=("group","arm")); h1=s.xs((grp,"H1"),level=("group","arm"))
            out.append(dict(arm=a,group=grp,head_cost=np.median(100*(x["head"]/h2["head"]-1)),xy_cost=np.median(100*(x["xy"]/h2["xy"]-1)),
                            xy_cost_p90=np.quantile(100*(x["xy"]/h2["xy"]-1),.9),
                            head_vs_DR=np.median(100*(1-x["head"]/h0["head"])),xy_vs_DR=np.median(100*(1-x["xy"]/h0["xy"])),head_vs_H1=np.median(100*(1-x["head"]/h1["head"]))))
    print(f"-- {cond}"); print(pd.DataFrame(out).round(1).pivot(index="arm",columns="group").to_string())
print("\n== 짝 비교: seed별 J (행: 앞 arm, 열: 뒤 arm)")
for cond in ("B0","L2_GYRO_ARW"):
    s=D[(D["cond"]==cond)&(D.group=="pooled")].pivot(index="seed",columns="arm",values="J")
    for a,b in (("F2S","F2"),("F2S","H3"),("F1S","F1"),("F2S","F1S"),("F2","H3")):
        t=pd.crosstab(s[a],s[b]); 
        def c(i,j): return int(t.loc[i,j]) if i in t.index and j in t.columns else 0
        print(f"{cond} {a} vs {b}: 둘다통과 {c(True,True)}, {a}만 {c(True,False)}, {b}만 {c(False,True)}, 둘다실패 {c(False,False)}")
