import json, glob, numpy as np, pandas as pd
rows=[]
def add(route,arm,seed,v):
    s=np.array(v["sums"]); n=v["n"]; rows.append(dict(route=route,arm=arm,seed=seed,head=np.sqrt(s[0]/n),xy=np.sqrt(s[1]/n),pose95=s[3]/n,head95=s[5]/n,nees3=s[2]/n,mirror=v["mirror"]))
for f in glob.glob("out_var/B0/seed*/RES.json"):
    seed=int(f.split("seed")[-1].split("/")[0]); X=json.load(open(f))
    for r in X:
        for a,v in X[r].items(): add(r,a,seed,v)
for f in glob.glob("/home/claude/n1n6/v1_replay/B0/seed*/RES.json"):
    seed=int(f.split("seed")[-1].split("/")[0])
    if seed>=30: continue
    X=json.load(open(f))
    for r in X:
        for a in ("H0","H1S","H2S-SWB"): add(r,a,seed,X[r][a])
for f in glob.glob("out/B0/seed*/RES.json")+glob.glob("out_r4/B0/seed*/RES.json"):
    seed=int(f.split("seed")[-1].split("/")[0]); X=json.load(open(f))
    for r in X:
        for a in ("H0","H1S","H2S-SWB"): add(r,a,seed,X[r][a])
D=pd.DataFrame(rows); D.to_csv("VARIANT_PERSEED.csv",index=False); ORD=["H0","H1S","H2S-SWB","SWB-AVG","SWB-RAW"]
M=D.groupby(["route","arm"]).agg(head=("head","median"),xy=("xy","median"),pose95=("pose95","median"),head95=("head95","median"),mirror=("mirror",lambda m:int((m>0).sum())),n=("seed","nunique"))
for r in ["N1","N2","N4","N5","N3","N6","R2","R4","R5"]:
    print("--",r); print(M.loc[r].reindex(ORD).round(3).to_string())
rng=np.random.default_rng(1)
print("\nseed-paired ratio variant / H2S-SWB (median, UB97.5)")
for r in ["N1","N2","N4","N5","N3","N6","R2","R4","R5"]:
    P=D[D.route==r].pivot(index="seed",columns="arm"); o=[]
    for a in ("SWB-AVG","SWB-RAW"):
        for m in ("xy","head"):
            x=(P[m][a]/P[m]["H2S-SWB"]).values; b=np.median(x[rng.integers(0,len(x),(10000,len(x)))],1); o.append(f"{a} {m} {np.median(x):.2f}({np.quantile(b,.975):.2f})")
    print(r," | ".join(o))
