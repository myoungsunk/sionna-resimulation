"""Reproducibility of the non-zero-mean part across stations (leave-one-column-out, LOCO). Station grid = 40 cols (0.45 m) x 5 rows."""
import numpy as np, pandas as pd
from load import load
D=load(); S=pd.read_csv("STATION_COMPONENTS.csv"); B=["<3","3-6",">=6"]
cols=np.sort(S.col.unique()); ci={c:i for i,c in enumerate(cols)}
# local neighbour prediction of components: average of col-1 and col+1, same row, only if both on same anchor side and same bin
def nb(v):
    P=S.set_index(["row","col"])[v]; out=[]
    for r,c,sd in zip(S.row,S.col,S.side):
        i=ci[c]; vals=[P.get((r,cols[j])) for j in (i-1,i+1) if 0<=j<len(cols) and (cols[j]>=1000)==(c>=1000)]
        out.append(np.mean(vals) if vals else np.nan)
    return np.array(out)
def rowpred(v):  # same column, other rows (y diversity)
    g=S.groupby("col")[v]; s=g.transform("sum"); n=g.transform("size"); return ((s-S[v])/(n-1)).values
print("== component reproducibility, R² about bin mean (1 = fully predictable from other stations, <=0 = not)")
print("comp  bin   rho-smooth   col-neighbour(0.45 m)   same-col other rows(y)")
for v in ("off","dlt","kap"):
    S[v+"_nb"]=nb(v); S[v+"_row"]=rowpred(v)
    for b in range(3):
        q=S[S.b==b]; den=np.mean((q[v]-q[v].mean())**2)
        f=lambda p: 1-np.nanmean((q[v]-p)**2)/den
        print(f"{v:>4} {B[b]:>4}   {f(q[v+'_sm']):+.2f}         {f(q[v+'_nb']):+.2f}                  {f(q[v+'_row']):+.2f}")
S.to_csv("STATION_COMPONENTS.csv",index=False)
