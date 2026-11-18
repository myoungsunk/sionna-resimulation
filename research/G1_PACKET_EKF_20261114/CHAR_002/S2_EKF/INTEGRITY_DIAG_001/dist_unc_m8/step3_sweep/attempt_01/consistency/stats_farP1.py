import numpy as np, pandas as pd, json
from scipy.optimize import nnls
pd.set_option("display.width",230); rng=np.random.default_rng(5)
def load(f,tag):
    Z=np.load(f); D=pd.DataFrame({k:Z[k] for k in ["x","y","yaw","es","esame","a","dtap","st","s_los"]}); D["st"]=tag+D.st; D["rho"]=np.hypot(D.x-10,D.y); return D
S0=load("station_sweep_errors_M7.npz","C"); S1=load("station_sweep_errors_farP1.npz","F")
C="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_001/out"
R=pd.concat([pd.read_csv(f"{C}/ERRORS_{r}_aB_m0.csv.gz").assign(route=r) for r in ("R2","R4","R5")],ignore_index=True)
R["rho"]=np.hypot(R.x-10,R.y); R["a"]=R.g_psi*180/np.pi; R["es"]=R.e_s; R["esame"]=R.e_s_same
for D in (S0,S1,R):
    D["rb"]=np.where(D.rho<3,"<3",np.where(D.rho<6,"3-6",">=6"))
    D["ab"]=pd.cut(D.a.abs(),[0,.6,1.3,10],right=False,labels=["low","mid","high"]).astype(str)
    D["yl"]=pd.cut(D.y.abs(),[0,.1,.2,.375,.6],right=False,labels=["y≈0","0.1-0.2","y≈0.30","y≈0.45"]).astype(str)
S=pd.concat([S0,S1],ignore_index=True); Sf=S[S.rb==">=6"]; Rf=R[R.rb==">=6"]
def summ(D):
    lo=D[D.a.abs()<0.3]
    return pd.Series(dict(n=len(D),E2=np.mean(D.es**2),c0_anchor=np.mean(lo.es**2) if len(lo) else np.nan,n0=len(lo),tap=np.mean(D.dtap!=0),same_share=np.mean(D.esame**2)/np.mean(D.es**2)))
print("== A. 원거리, 횡방향 줄별 (sweep) 대 같은 |y| 구간 (궤적)")
A=pd.concat({"sweep":Sf.groupby("yl").apply(summ,include_groups=False),"궤적":Rf.groupby("yl").apply(summ,include_groups=False)},axis=0)
print(A.round(4).to_string())
print("\n   sweep 원거리 station별 E[e²] 분포 (줄별): 중앙 / p90 / 최대")
print(Sf.groupby(["yl","st"]).es.apply(lambda v:np.mean(v**2)).groupby("yl").agg(["median",lambda v:v.quantile(.9),"max"]).round(4).to_string())
print("\n== B. 거울 대칭: e(x,+y,ψ) 대 e(x,−y,−ψ)")
F=S1.copy(); F["key"]=list(zip(F.x.round(3),F.y.round(3),F.yaw.round(1)))
m={k:v for k,v in zip(F.key,F.es)}; pairs=[(v,m.get((x,round(-y,3),round(((-yw+180)%360)-180,1)))) for (x,y,yw),v in zip(F.key,F.es) if y>0]
pairs=np.array([(a,b) for a,b in pairs if b is not None]); print("  쌍",len(pairs),"corr(e+, e−)",round(np.corrcoef(pairs[:,0],pairs[:,1])[0,1],4),"corr(e+, −e−)",round(np.corrcoef(pairs[:,0],-pairs[:,1])[0,1],4),"max|e+ + e−|",round(np.max(np.abs(pairs[:,0]+pairs[:,1])),4),"max|e+ − e−|",round(np.max(np.abs(pairs[:,0]-pairs[:,1])),4))
print("\n== C. 같은 자세 일치 (궤적 pose가 새 station에서 5 cm, yaw 5° 이내; a·Δψ 보정)")
rows=[]
XY=S1.groupby("st")[["x","y"]].first()
for p in Rf.itertuples():
    dd=np.hypot(XY.x-p.x,XY.y-p.y); j=dd.values.argmin()
    if dd.values[j]>0.05: continue
    sw=S1[S1.st==XY.index[j]]; d=(p.yaw-sw.yaw.values+180)%360-180; k=np.argmin(np.abs(d))
    if abs(d[k])>5: continue
    q=sw.iloc[k]; rows.append(dict(dlos=abs(p.s_los-(q.s_los+q.a*np.radians(d[k]))),er=p.es,es=q.es,dtr=p.dtap,dts=q.dtap,dpos=dd.values[j],dyaw=abs(d[k])))
P=pd.DataFrame(rows)
if len(P):
    print(f"  n={len(P)}  LoS차 중앙 {P.dlos.median():.4f} | e corr {np.corrcoef(P.er,P.es)[0,1]:.3f} | RMS 궤적 {np.sqrt(np.mean(P.er**2)):.3f} sweep {np.sqrt(np.mean(P.es**2)):.3f} | dtap 같음 {np.mean(P.dtr==P.dts):.2f}")
    for t in (2,1): 
        q=P[(P.dpos<=0.02)&(P.dyaw<=t*2)]; 
        if len(q)>3: print(f"   (≤2 cm, ≤{2*t}°) n={len(q)} e corr {np.corrcoef(q.er,q.es)[0,1]:.3f}")
def fitB(d):
    lo=d[d.a.abs()<0.3]; c0=np.mean(lo.es**2); c1=nnls(((d.a**2).values)[:,None],(d.es**2-c0).values)[0][0]; return c1,c0
def boot(d,unit="st",nb=1500):
    g={k:v for k,v in d.groupby(unit)}; ks=list(g); c1,c0=fitB(d)
    bs=np.array([fitB(pd.concat([g[k] for k in rng.choice(ks,len(ks))])) for _ in range(nb)])
    th=np.degrees(np.sqrt(bs[:,0]))
    return dict(units=len(ks),σθ=round(np.degrees(np.sqrt(c1)),2),σθ_90=np.round(np.quantile(th,[.05,.95]),2).tolist(),P0=round(np.mean(bs[:,0]==0),2),
                σres=round(np.sqrt(c0),4),σres_90=np.round(np.quantile(np.sqrt(bs[:,1]),[.05,.95]),4).tolist(),a2share=round(c1*np.mean(d.a**2)/np.mean(d.es**2),2))
# mirror-aware unit: x position (± lines of same x and |y| are mirror pairs)
S["unit"]=S.x.round(3).astype(str)+"_"+S.y.abs().round(2).astype(str)
print("\n== D. 원거리 규칙 B 적합, station 단위 bootstrap")
print("  y=0만        ",boot(S[(S.rb==">=6")&(S.y==0)]))
print("  새 4줄만      ",boot(S[(S.rb==">=6")&(S.y!=0)],unit="unit"))
print("  y=0 + 4줄     ",boot(S[S.rb==">=6"],unit="unit"))
print("  y=0 + 4줄 (x=1.2 제외)",boot(S[(S.rb==">=6")&~np.isclose(S.x,1.2)],unit="unit"))
print("  궤적 원거리 (참고, 블록=궤적×0.45 m x-bin)",boot(Rf.assign(blk=Rf.route+(Rf.x/0.45).round().astype(str)),unit="blk"))
print("\n== E. 궤적 예측 일관성 (근·중거리=y=0 sweep 규칙 B, 원거리=y=0+4줄 규칙 B)")
fit={b:fitB(S0[S0.rb==b]) for b in ["<3","3-6"]}; fit[">=6"]=fitB(S[S.rb==">=6"])
fit_y0={b:fitB(S0[S0.rb==b]) for b in ["<3","3-6",">=6"]}
FT=json.load(open("/home/claude/m8/FIT_TABLES.json"))["tables"]
rows=[]
for r in ("R2","R4","R5"):
    d=R[R.route==r]
    for name,f in {"sweep y=0":fit_y0,"sweep y=0+4줄":fit,"경로 LORO":{b:(t["c1"],t["c0"]) for b,t in zip(["<3","3-6",">=6"],FT[r])}}.items():
        V=np.array([f[b][0] for b in d.rb])*d.a**2+np.array([f[b][1] for b in d.rb]); z=d.es/np.sqrt(V)
        for (b,s),idx in d.groupby(["rb","ab"]).groups.items():
            if len(idx)<25: continue
            rows.append(dict(route=r,rho=b,sens=s,table=name,ratio=np.mean(d.es[idx]**2)/np.mean(V[idx]),cov=np.mean(np.abs(z[idx])<=1.96)))
T=pd.DataFrame(rows)
print(T.groupby("table").agg(cov_min=("cov","min"),cov_med=("cov","median"),ratio_min=("ratio","min"),ratio_med=("ratio","median"),ratio_max=("ratio","max"),cells_0p5_2=("ratio",lambda v:np.mean((v>=.5)&(v<=2)))).round(2).to_string())
print("\n  원거리 셀 E[e²]/V")
print(T[T.rho==">=6"].pivot_table(index=["route","sens"],columns="table",values="ratio").round(2).to_string())
print("\n  적합값 σθ / σres:", {k:{b:(round(np.degrees(np.sqrt(c1)),2),round(np.sqrt(c0),4)) for b,(c1,c0) in f.items()} for k,f in [("y=0",fit_y0),("y=0+4줄",fit)]})
T.to_csv("stats_farP1_prediction.csv",index=False)
