import json, glob, numpy as np, pandas as pd
def load(pattern, block):
    rows=[]
    for f in glob.glob(pattern):
        seed=int(f.split("seed")[-1].split("/")[0]); X=json.load(open(f))
        for r in X:
            for a,v in X[r].items():
                if a=="GM": continue
                s=np.array(v["sums"]); n=v["n"]
                rows.append(dict(block=block,route=r,arm=a,seed=seed,n=n,s0=s[0],s1=s[1],head=np.sqrt(s[0]/n),xy=np.sqrt(s[1]/n),pose95=s[3]/n,head95=s[5]/n,xy95=s[4]/n,nees3=s[2]/n,mirror=v["mirror"],
                                 xy_p95=v.get("xy_p95_cm",np.nan),head_p95=v.get("head_p95",np.nan)))
    return rows
D=pd.DataFrame(load("out_abl_raw/B0/seed*/RES.json","RAW")+load("out_abl/B0_dummy/*","x")+load("out_abl/B0/seed*/RES.json","SWB")+load("/home/claude/n1n6/out_abl/B0/seed*/RES.json","SWB"))
D.to_csv("ABL_RAW_VS_SWB_PERSEED.csv",index=False); ORD=["B","S","T","S+T","F2"]
SETS={"Paper1 (N1+N2+N4+N5)":["N1","N2","N4","N5"],"R5":["R5"],"N6":["N6"],"R2":["R2"],"R4":["R4"],"N3":["N3"],"all 9":["R2","R4","R5","N1","N2","N3","N4","N5","N6"]}
out=[]
for name,rs in SETS.items():
    for blk in ("RAW","SWB"):
        d=D[(D.block==blk)&D.route.isin(rs)]
        g=d.groupby(["arm","seed"]).agg(n=("n","sum"),s0=("s0","sum"),s1=("s1","sum"),p=("pose95",lambda x: np.nan),mir=("mirror","sum")).reset_index()
        # coverage pooled n-weighted
        cov=d.assign(w=d.pose95*d.n,h=d.head95*d.n,nz=d.nees3*d.n).groupby(["arm","seed"])[["w","h","nz","n"]].sum()
        g=g.set_index(["arm","seed"]); g["head"]=np.sqrt(g.s0/g.n); g["xy"]=np.sqrt(g.s1/g.n); g["pose95"]=cov.w/cov.n; g["head95"]=cov.h/cov.n; g["nees3"]=cov.nz/cov.n
        m=g.groupby("arm").agg(head=("head","median"),xy=("xy","median"),pose95=("pose95","median"),head95=("head95","median"),nees3=("nees3","median"),mirror_seeds=("mir",lambda x:int((x>0).sum())))
        for a in ORD:
            if a in m.index: out.append(dict(set=name,block=blk,arm=a,**m.loc[a].to_dict()))
O=pd.DataFrame(out); O.to_csv("ABL_RAW_VS_SWB_SUMMARY.csv",index=False); pd.set_option("display.width",220)
print(O.round(3).to_string(index=False))
R=D[D.block=="RAW"]; print("\nRAW per-route medians (heading/XY/Pose95/mirror)")
print(R.groupby(["route","arm"]).agg(head=("head","median"),xy=("xy","median"),pose95=("pose95","median"),xy_p95=("xy_p95","median"),mir=("mirror",lambda x:int((x>0).sum()))).unstack("arm").round(2).to_string())
