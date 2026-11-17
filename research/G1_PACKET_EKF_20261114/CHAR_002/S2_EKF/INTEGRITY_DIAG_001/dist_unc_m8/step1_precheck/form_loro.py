import numpy as np, pandas as pd
D=pd.read_csv("form_check_points.csv.gz")
D["rb"]=pd.cut(D.rho,[0,3,6,9.5],right=False,labels=["<3","3-6",">=6"]).astype(str)
D["sb"]=pd.cut(D.ga,[0,.6,1.3,10],right=False,labels=["low","mid","high"]).astype(str)
rng=np.random.default_rng(1)
rows=[]
for hold in ["R2","R4","R5"]:
    tr=D[D.route!=hold]; te=D[D.route==hold].copy()
    pred=np.zeros(len(te)); prA=np.zeros(len(te))
    for rb in ["<3","3-6",">=6"]:
        t=tr[tr.rb==rb]; c=np.maximum(np.linalg.lstsq(np.c_[t.a**2,np.ones(len(t))],t.e_s**2,rcond=None)[0],1e-8)
        m=(te.rb==rb).values; pred[m]=c[0]*te.a[m]**2+c[1]; prA[m]=np.mean(t.e_s**2)
    te["pC"]=pred; te["pA"]=prA
    for (rb,sb),d in te.groupby(["rb","sb"]):
        if len(d)<25: continue
        g=d.groupby("blk"); e2=g.e_s.apply(lambda s:(s**2).sum()).values; pc=g.pC.sum().values
        bs=[e2[i].sum()/pc[i].sum() for i in (rng.integers(0,len(e2),len(e2)) for _ in range(1000))]
        z=d.e_s/np.sqrt(d.pC)
        rows.append(dict(hold=hold,rho=rb,sens=sb,n=len(d),ratio_C=f"{np.mean(d.e_s**2)/np.mean(d.pC):.2f} [{np.quantile(bs,.05):.2f},{np.quantile(bs,.95):.2f}]",
                         cov95_C=round(np.mean(np.abs(z)<=1.96),2),ratio_A=round(np.mean(d.e_s**2)/np.mean(d.pA),2)))
print("LORO: 두 경로로 c1·a²+c0 적합 → 남은 경로. E[e²]/예측 [90% block bootstrap], packet 95% 포함률")
print(pd.DataFrame(rows).to_string(index=False))
