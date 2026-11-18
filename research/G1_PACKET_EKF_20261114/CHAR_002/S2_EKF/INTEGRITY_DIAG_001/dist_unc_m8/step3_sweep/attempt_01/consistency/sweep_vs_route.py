import numpy as np, pandas as pd
from scipy.optimize import nnls
Z=np.load("station_sweep_errors.npz")
S=pd.DataFrame({k:Z[k] for k in ["x","y","yaw","es","a","s_los","s_full","dtap"]}); S["rho"]=np.abs(S.x-10); S["src"]="sweep"
C="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_001/out"
Rt=[]
for r in ("R2","R4","R5"):
    E=pd.read_csv(f"{C}/ERRORS_{r}_aB_m0.csv.gz"); E["route"]=r; Rt.append(E)
Rt=pd.concat(Rt,ignore_index=True); Rt["a"]=Rt.g_psi*180/np.pi; Rt["rho"]=np.hypot(Rt.x-10,Rt.y)
def wrapd(d): return (d+180)%360-180
print("== 1. 같은 자세 일치성: 궤적 pose가 station에서 5 cm, yaw 5° 이내")
st_x=np.unique(S.x); pairs=[]
for i,p in Rt.iterrows():
    j=np.argmin(np.abs(st_x-p.x)); 
    if np.hypot(st_x[j]-p.x,p.y)>0.05: continue
    sw=S[np.isclose(S.x,st_x[j])]; dy=np.abs(wrapd(sw.yaw.values-p.yaw)); k=np.argmin(dy)
    if dy[k]>5: continue
    q=sw.iloc[k]; pairs.append(dict(route=p.route,rho=p.rho,dpos=np.hypot(st_x[j]-p.x,p.y),dyaw=dy[k],e_route=p.e_s,e_sweep=q.es,
        slos_route=p.s_los,slos_sweep=q.s_los,sfull_route=p.s_full,sfull_sweep=q.s_full,a_route=p.a,a_sweep=q.a))
P=pd.DataFrame(pairs); print("쌍 수",len(P), P.groupby("route").size().to_dict())
if len(P):
    for k,(u,v) in {"s_los":(P.slos_route,P.slos_sweep),"s_full":(P.sfull_route,P.sfull_sweep),"e":(P.e_route,P.e_sweep),"a":(P.a_route,P.a_sweep)}.items():
        print(f"  {k:6s} corr {np.corrcoef(u,v)[0,1]:.4f}  |diff| 중앙 {np.median(np.abs(u-v)):.2e}  p90 {np.quantile(np.abs(u-v),.9):.2e}  (RMS route {np.sqrt(np.mean(u**2)):.3f})")
    P.to_csv("sweep_route_pairs.csv",index=False)
EDG=[0,3,6,10]; AB=[0,.6,1.3,10]
for D in (S,Rt):
    D["rb"]=pd.cut(D.rho,EDG,right=False,labels=["<3","3-6",">=6"]).astype(str); D["ab"]=pd.cut(D.a.abs(),AB,right=False,labels=["low","mid","high"]).astype(str)
Rt["es"]=Rt.e_s
print("\n== 2. 같은 거리·같은 감도 셀의 E[e²] (sweep 대 궤적)")
g1=S.groupby(["rb","ab"]).agg(n_sw=("es","size"),E2_sw=("es",lambda v:np.mean(v**2)))
g2=Rt.groupby(["rb","ab"]).agg(n_rt=("es","size"),E2_rt=("es",lambda v:np.mean(v**2)))
G=g1.join(g2); G["ratio_rt_over_sw"]=G.E2_rt/G.E2_sw; print(G.round(4).to_string())
print("\n   heading 표본: |a| 구간 비율 (거리 bin별)")
print(pd.concat({"sweep":S.groupby("rb").ab.value_counts(normalize=True),"route":Rt.groupby("rb").ab.value_counts(normalize=True)},axis=1).round(2).to_string())
def ruleB(D):
    out=[]
    for b in ["<3","3-6",">=6"]:
        d=D[D.rb==b]; lo=d[d.a.abs()<0.3]; c0=np.mean(lo.es**2)
        c1=nnls(((d.a**2).values)[:,None],(d.es**2-c0).values)[0][0]
        out.append((b,np.degrees(np.sqrt(c1)),np.sqrt(c0),len(lo)))
    return out
print("\n== 3. 같은 규칙 B로 적합: σθ(°) / σres / c0 앵커 표본 수")
for name,D in [("sweep",S),("궤적 전체(e)",Rt)]+[(f"궤적 {r}",Rt[Rt.route==r]) for r in ("R2","R4","R5")]:
    try: print(f"  {name:12s}"+" | ".join(f"{b}: {t:.2f}° / {s:.4f} (n0={n})" for b,t,s,n in ruleB(D)))
    except Exception as ex: print(name,"fit fail",ex)
print("\n== 4. 궤적 횡방향: |y|<0.1 대 |y|≥0.1, 같은 셀 E[e²]/sweep")
Rt["yb"]=np.where(Rt.y.abs()<0.1,"|y|<0.1","|y|>=0.1")
g3=Rt.groupby(["rb","ab","yb"]).es.agg(["size",lambda v:np.mean(v**2)]).rename(columns={"<lambda_0>":"E2"})
g3=g3.join(g1,on=["rb","ab"]); g3["ratio"]=g3.E2/g3.E2_sw; print(g3[["size","ratio"]].unstack("yb").round(2).to_string())
