import json, numpy as np, pandas as pd
rows=[]
for c in ("B0","L2_GYRO_ARW"):
    for s in range(10,30):
        n=json.load(open(f"out_c0/C03/{c}/seed{s}/GROUP.json")); o=json.load(open(f"s0ref/out_s3/{c}/own/seed{s}/GROUP.json"))
        for arm in ("H2","H2S","F2SKRWV"):
            mx=max(abs(v-o["point"][g][arm][k]) for g in ("R2","R4","R5","pooled") for k,v in n["point"][g][arm].items())
            mci=max(abs(lo-o["ci10"][g]["absolute_ci95"][arm][m][0]) for g in ("R2","R4","R5","pooled") for m,(lo,hi) in n["ci10"][g]["absolute_ci95"][arm].items())
            for ref in ("H2","H2S"):
                a=n["seed_assessments"][ref][arm]; b=o["seed_assessments"][ref][arm]
                rows.append(dict(cond=c,seed=s,arm=arm,ref=ref,max_point_diff=mx,max_cilow_diff=mci,
                                 same_I=a["I_seed"]==b["I_seed"],same_A=a["A_seed"]==b["A_seed"],same_J=a["J_seed"]==b["J_seed"],same_mirror=a["mirror_routes"]==b["mirror_routes"]))
D=pd.DataFrame(rows); D.to_csv("C0_3_COMPARE.csv",index=False)
S=D.groupby(["arm","ref"]).agg(max_point_diff=("max_point_diff","max"),max_cilow_diff=("max_cilow_diff","max"),I=("same_I","all"),A=("same_A","all"),J=("same_J","all"),mirror=("same_mirror","all"))
print(S.to_string()); ok=bool((D[["same_I","same_A","same_J","same_mirror"]].all().all()) and D.max_point_diff.max()<=1e-3)
json.dump(dict(status="PASS" if ok else "FAIL",max_point_diff=float(D.max_point_diff.max()),max_cilow_diff=float(D.max_cilow_diff.max()),
  all_decisions_identical=bool(D[["same_I","same_A","same_J","same_mirror"]].all().all()),runs=40),open("C0_3_RESULT.json","w"),indent=1)
print(json.load(open("C0_3_RESULT.json")))
