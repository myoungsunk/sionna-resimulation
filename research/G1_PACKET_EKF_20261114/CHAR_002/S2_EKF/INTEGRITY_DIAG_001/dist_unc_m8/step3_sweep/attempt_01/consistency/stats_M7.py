import numpy as np, pandas as pd
from scipy.optimize import nnls
pd.set_option("display.width",250)
C="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_001/out"
R=pd.concat([pd.read_csv(f"{C}/ERRORS_{r}_aB_m0.csv.gz").assign(route=r) for r in ("R2","R4","R5")],ignore_index=True)
R["rho"]=np.hypot(R.x-10,R.y); R["a"]=R.g_psi*180/np.pi; R["e"]=R.e_s
def load(f):
    Z=np.load(f); S=pd.DataFrame({k:Z[k] for k in ["x","yaw","es","a","s_los","s_full","dtap"]}); S["rho"]=np.abs(S.x-10); S["e"]=S.es; return S
SW={"F1(이전)":load("station_sweep_errors.npz"),"M7(새)":load("station_sweep_errors_M7.npz")}
def lab(D):
    D["rb"]=pd.cut(D.rho,[0,3,6,10],right=False,labels=["<3","3-6",">=6"]).astype(str)
    D["ab"]=pd.cut(D.a.abs(),[0,.6,1.3,10],right=False,labels=["low","mid","high"]).astype(str)
    f=np.abs((D.yaw+180)%360-180); D["phi"]=np.minimum(f,180-f)
    D["pb"]=pd.cut(D.phi,[0,15,30,60,90.01],right=False,labels=["0-15축","15-30","30-60","60-90벽"]).astype(str)
for D in [R,*SW.values()]: lab(D)
# ---------- 1. matched poses
print("== 1. 같은 자세 (5 cm, yaw 5° 이내; yaw 차이는 a·Δψ로 보정)")
xs=np.unique(SW["M7(새)"].x)
for name,S in SW.items():
    rows=[]
    for p in R.itertuples():
        j=np.argmin(np.abs(xs-p.x)); dp=np.hypot(xs[j]-p.x,p.y)
        if dp>0.05: continue
        sw=S[np.isclose(S.x,xs[j])]; d=(p.yaw-sw.yaw.values+180)%360-180; k=np.argmin(np.abs(d))
        if abs(d[k])>5: continue
        q=sw.iloc[k]; dpsi=np.radians(d[k])
        rows.append(dict(rb=p.rb,dlos=abs(p.s_los-(q.s_los+q.a*dpsi)),er=p.e,es=q.e,dtr=p.dtap,dts=q.dtap,dyaw=abs(d[k])))
    P=pd.DataFrame(rows)
    out=P.groupby("rb").apply(lambda g: pd.Series(dict(n=len(g),LoS차_중앙=np.median(g.dlos),e_corr=np.corrcoef(g.er,g.es)[0,1],e차_중앙=np.median(np.abs(g.er-g.es)),
        e_RMS_궤적=np.sqrt(np.mean(g.er**2)),e_RMS_sweep=np.sqrt(np.mean(g.es**2)),tap이동_궤적=np.mean(g.dtr!=0),tap이동_sweep=np.mean(g.dts!=0),dtap같음=np.mean(g.dtr==g.dts))),include_groups=False)
    print(f"-- {name}"); print(out.round(3).to_string())
    t=P[P.dyaw<=1]; print(f"   |Δyaw|≤1°: n={len(t)}, e corr {np.corrcoef(t.er,t.es)[0,1]:.3f}, dtap 같음 {np.mean(t.dtr==t.dts):.2f}")
# ---------- 2. cell E[e2]
print("\n== 2. 같은 거리·감도 셀 E[e²]: 궤적/sweep 비율")
G=R.groupby(["rb","ab"]).e.agg(n_rt="size",E2_rt=lambda v:np.mean(v**2))
for name,S in SW.items():
    g=S.groupby(["rb","ab"]).e.agg(lambda v:np.mean(v**2)); G[f"궤적/{name}"]=G.E2_rt/g
print(G.round(3).to_string())
print("\n== 3. 같은 거리·heading 구간(복도축 기준 φ) E[e²]: 궤적/sweep 비율")
H=R.groupby(["rb","pb"]).e.agg(n_rt="size",E2_rt=lambda v:np.mean(v**2))
for name,S in SW.items(): H[f"궤적/{name}"]=H.E2_rt/S.groupby(["rb","pb"]).e.agg(lambda v:np.mean(v**2))
print(H.round(3).to_string())
print("\n== 4. tap 이동 비율 (1.5 m bin)")
def tb(D): D=D.copy(); D["b"]=pd.cut(D.rho,[0,1.5,3,4.5,6,7.5,9.01],right=False).astype(str); return D.groupby("b").dtap.apply(lambda v:np.mean(v!=0))
print(pd.concat({"궤적":tb(R),**{k:tb(v) for k,v in SW.items()}},axis=1).round(3).to_string())
# ---------- 5. rule B fit
def ruleB(D):
    out={}
    for b in ["<3","3-6",">=6"]:
        d=D[D.rb==b]; c0=np.mean(d[d.a.abs()<0.3].e**2); c1=nnls(((d.a**2).values)[:,None],(d.e**2-c0).values)[0][0]
        out[b]=(c1,c0,int((d.a.abs()<0.3).sum()))
    return out
print("\n== 5. 규칙 B 적합 σθ(°) / σres  [c0 앵커 n]")
FITS={"궤적 전체":ruleB(R),**{k:ruleB(v) for k,v in SW.items()}}
for k,f in FITS.items(): print(f"  {k:9s}"+" | ".join(f"{b}: {np.degrees(np.sqrt(c1)):.2f}° / {np.sqrt(c0):.4f} [n0={n}]" for b,(c1,c0,n) in f.items()))
# ---------- 6. prediction consistency on routes
print("\n== 6. sweep 규칙 B 표로 궤적 오차 예측: E[e²]/V (1=맞음), packet 95% 포함률  (비교: 경로 LORO 규칙 B, Step 1 F2 표)")
import json
FT=json.load(open("/home/claude/m8/FIT_TABLES.json"))["tables"]
rows=[]
for r in ("R2","R4","R5"):
    d=R[R.route==r]
    tabs={**{k:FITS[k] for k in SW},"경로 LORO":{row_b:(t["c1"],t["c0"],0) for row_b,t in zip(["<3","3-6",">=6"],FT[r])}}
    for name,f in tabs.items():
        V=np.array([f[b][0] for b in d.rb])*d.a**2+np.array([f[b][1] for b in d.rb]); z=d.e/np.sqrt(V)
        for (b,s),m in d.groupby(["rb","ab"]).groups.items():
            if len(m)<25: continue
            rows.append(dict(route=r,rho=b,sens=s,table=name,n=len(m),ratio=np.mean(d.e[m]**2)/np.mean(V[m]),cov=np.mean(np.abs(z[m])<=1.96)))
T=pd.DataFrame(rows)
print(T.pivot_table(index=["route","rho","sens","n"],columns="table",values=["ratio","cov"]).round(2).to_string())
s=T.groupby("table").agg(cov_min=("cov","min"),cov_med=("cov","median"),ratio_med=("ratio","median"),ratio_max=("ratio","max"),ratio_min=("ratio","min"))
print("\n요약 (셀 단위)"); print(s.round(2).to_string())
T.to_csv("stats_M7_prediction.csv",index=False)
