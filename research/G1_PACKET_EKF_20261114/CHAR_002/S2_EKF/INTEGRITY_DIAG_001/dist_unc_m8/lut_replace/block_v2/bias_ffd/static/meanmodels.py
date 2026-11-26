"""Curve-level mean models for the FFD residual, evaluated leave-one-column-out on the station grid.
  M0  : none (= BV0 mean)
  MBs : scalar offset, bin x side mean of e
  MB  : bin x side mean of the components [off, dlt, kap]  -> mean = off + a*dlt + kap*h
  MS  : rho-smooth (0.75 m, same side) components         (BV-like + offset)
  MN  : <3 m local curve: mean of e(psi) at col-1 / col+1 (same row, same yaw, same side);  >=3 m: MB
After each mean, variance table as in bv_block.table: c0 = mean r^2 (|a|<0.3), c1 = nnls(a^2, r^2 - c0), per bin."""
import numpy as np, pandas as pd, json
from scipy.optimize import nnls
from load import load
D=load(); S=pd.read_csv("STATION_COMPONENTS.csv").set_index(["col","row"]); B=["<3","3-6",">=6"]
cols=np.sort(D.col.unique())
key=list(zip(D.col,D.row)); comp=lambda v: S.loc[key,v].values
def bin_side_loco(vals_station, v):
    """per station: mean of v over other columns in same bin & side"""
    St=S.reset_index(); out={}
    for (c,r),g in St.groupby(["col","row"]):
        b,sd=g.b.iloc[0],g.side.iloc[0]; q=St[(St.b==b)&(St.side==sd)&(St.col!=c)]; out[(c,r)]=q[v].mean()
    return np.array([out[k] for k in key])
mean={}
mean["M0"]=np.zeros(len(D))
# scalar offset: bin x side mean of e excluding own column
g=D.groupby(["b","side"]); s=D.groupby(["b","side","col"]).e.agg(["sum","size"]).reset_index()
tot=s.groupby(["b","side"])[["sum","size"]].transform("sum"); s["loco"]=(tot["sum"]-s["sum"])/(tot["size"]-s["size"])
mean["MBs"]=D.merge(s[["b","side","col","loco"]],on=["b","side","col"],how="left").loco.values
mean["MB"]=bin_side_loco(None,"off")+D.a.values*bin_side_loco(None,"dlt")+D.h.values*bin_side_loco(None,"kap")
mean["MS"]=comp("off_sm")+D.a.values*comp("dlt_sm")+D.h.values*comp("kap_sm")
# local curve neighbour for near field
E=D.pivot_table(index=["row","yaw"],columns="col",values="e"); ci={c:i for i,c in enumerate(cols)}; nbm=np.full(len(D),np.nan)
for i,(c,r,y) in enumerate(zip(D.col,D.row,D.yaw)):
    j=ci[c]; v=[E.loc[(r,y),cols[k]] for k in (j-1,j+1) if 0<=k<len(cols) and (cols[k]>=1000)==(c>=1000)]
    nbm[i]=np.mean(v) if v else np.nan
mean["MN"]=np.where(D.b.values==0,nbm,mean["MB"])
res=[]; tabs={}
for m,mu in mean.items():
    r=D.e.values-mu; a=D.a.values; tabs[m]=dict(edges=[0,3,6,10],c1=[],c0=[])
    for b in range(3):
        q=(D.b.values==b)&np.isfinite(r); lo=q&(np.abs(a)<.3); c0=float(np.mean(r[lo]**2)); c1=float(nnls((a[q]**2)[:,None],r[q]**2-c0)[0][0])
        tabs[m]["c1"].append(c1); tabs[m]["c0"].append(c0)
        z=r[q]/np.sqrt(c1*a[q]**2+c0); hb=np.degrees(np.sum(a[q]*r[q])/np.sum(a[q]**2))
        # heading-equivalent bias per station side, then RMS over side (bias that does not average out within a side)
        hs=[np.degrees(np.sum(a[q&(D.side.values==sd)]*r[q&(D.side.values==sd)])/np.sum(a[q&(D.side.values==sd)]**2)) for sd in (-1,1)]
        res.append(dict(model=m,bin=B[b],mean=r[q].mean(),head_eq_deg=hb,head_eq_by_side=f"{hs[0]:+.2f}/{hs[1]:+.2f}",rms=np.sqrt(np.mean(r[q]**2)),
                        sd_centered=r[q].std(),bias2_share=r[q].mean()**2/np.mean(r[q]**2),sig_theta_deg=np.degrees(np.sqrt(c1)),sig_res=np.sqrt(c0),cov95=np.mean(np.abs(z)<=1.96)))
R=pd.DataFrame(res); pd.set_option("display.width",250); print(R.round(4).to_string(index=False))
R.to_csv("MEAN_MODELS_LOCO.csv",index=False); json.dump(tabs,open("TABLES_MEAN_MODELS.json","w"),indent=1)
