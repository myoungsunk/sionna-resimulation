"""Station-level decomposition of the FFD residual e = s_full - h_FFD (corridor, anchor B, mount 0).
per station fit (36 yaw):  e(psi) = off + a(psi)*dlt + kap*h(psi) + shape(psi)
  off: additive offset, dlt: heading-type shift (rad, s-bias = a*dlt), kap: polarization-ratio (amplitude) term, shape: rest"""
import numpy as np, pandas as pd, json
from load import load, EDG
D=load(); rows=[]
for (c,r),g in D.groupby(["col","row"]):
    X=np.c_[np.ones(len(g)),g.a,g.h]; beta,*_=np.linalg.lstsq(X,g.e.values,rcond=None); fit=X@beta
    rows.append(dict(col=c,row=r,x=g.x.iloc[0],y=g.y.iloc[0],rho=g.rho.iloc[0],side=g.side.iloc[0],b=g.b.iloc[0],off=beta[0],dlt=beta[1],kap=beta[2],
                     ms_e=np.mean(g.e**2),ms_off=np.mean((X[:,0]*beta[0])**2),ms_dlt=np.mean((g.a*beta[1])**2),ms_kap=np.mean((g.h*beta[2])**2),ms_shape=np.mean((g.e-fit)**2)))
S=pd.DataFrame(rows); S.to_csv("STATION_COMPONENTS.csv",index=False)
B=["<3","3-6",">=6"]
print("== station component size per bin: mean ± SD over stations (dlt in deg)")
for b in range(3):
    q=S[S.b==b]
    print(f"{B[b]:>4} n={len(q):3d}  off {q.off.mean():+.4f}±{q.off.std():.4f}  dlt {np.degrees(q.dlt.mean()):+.2f}±{np.degrees(q.dlt.std()):.2f}°  kap {q.kap.mean():+.3f}±{q.kap.std():.3f}")
print("== share of station mean-square e (pooled per bin): off / dlt / kap / shape  (sum of parts ≠ 1 due to cross terms)")
for b in range(3):
    q=S[S.b==b]; t=q.ms_e.sum(); print(f"{B[b]:>4}  e_rms {np.sqrt(q.ms_e.mean()):.4f}  off {q.ms_off.sum()/t:.2f}  dlt {q.ms_dlt.sum()/t:.2f}  kap {q.ms_kap.sum()/t:.2f}  shape {q.ms_shape.sum()/t:.2f}")
print("== spatial structure of components: lag-1 column correlation (same row, 0.45 m), and correlation with same-side rho-smooth (LOCO, 0.75 m)")
def loco_smooth(S,v,bw=0.75):
    out=np.empty(len(S))
    for i,(c,sd,rho) in enumerate(zip(S.col,S.side,S.rho)):
        q=(S.side==sd)&(S.col!=c); w=np.exp(-0.5*((S.rho[q]-rho)/bw)**2); out[i]=np.sum(w*S[v][q])/np.sum(w)
    return out
for v in ("off","dlt","kap"):
    S[v+"_sm"]=loco_smooth(S,v)
P=S.pivot_table(index="row",columns="col",values=["off","dlt","kap"])
for v in ("off","dlt","kap"):
    line=[]
    for b in range(3):
        q=S[S.b==b]; sm=q[v+"_sm"]; ex=1-np.mean((q[v]-sm)**2)/np.mean((q[v]-q[v].mean())**2+1e-30)
        line.append(f"{B[b]} R²(LOCO smooth, about bin mean)={ex:+.2f}  |mean|/SD={abs(q[v].mean())/q[v].std():.2f}")
    A=P[v].to_numpy(); lag=np.corrcoef(A[:,:-1].ravel(),A[:,1:].ravel())[0,1]
    print(f"{v:>3}: lag1 col corr {lag:+.2f} | "+" | ".join(line))
S.to_csv("STATION_COMPONENTS.csv",index=False)
