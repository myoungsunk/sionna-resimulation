import numpy as np, pandas as pd, json
from scipy.optimize import nnls
pd.set_option("display.width",240); rng=np.random.default_rng(3)
def load(f,tag):
    Z=np.load(f); D=pd.DataFrame({k:Z[k] for k in ["x","y","yaw","es","esame","a","dtap","s_los"]}); D["src"]=tag; return D
S=pd.concat([load("station_sweep_errors_M7.npz","center"),load("station_sweep_errors_farP1.npz","far4"),load("station_sweep_errors_midP.npz","mid4")],ignore_index=True)
S["rho"]=np.hypot(S.x-10,S.y); S["pos"]=S.x.round(3).astype(str)+"_"+S.y.round(2).astype(str)
C="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_001/out"
R=pd.concat([pd.read_csv(f"{C}/ERRORS_{r}_aB_m0.csv.gz").assign(route=r) for r in ("R2","R4","R5")],ignore_index=True)
R["rho"]=np.hypot(R.x-10,R.y); R["a"]=R.g_psi*180/np.pi; R["es"]=R.e_s; R["esame"]=R.e_s_same
for D in (S,R):
    D["rb"]=np.where(D.rho<3,"<3",np.where(D.rho<6,"3-6",">=6"))
    D["ab"]=pd.cut(D.a.abs(),[0,.6,1.3,10],right=False,labels=["low","mid","high"]).astype(str)
    D["yl"]=pd.cut(D.y.abs(),[0,.1,.2,.375,.6],right=False,labels=["y≈0","0.1-0.2","y≈0.30","y≈0.45"]).astype(str)
print("위치 수:",S.pos.nunique(),"pose:",len(S),"| 거리별 위치 수:",S.groupby("rb").pos.nunique().to_dict())
print("\n== A. 거리 × 횡방향 줄: sweep 대 궤적 (같은 |y| 구간)")
def summ(D):
    lo=D[D.a.abs()<0.3]; return pd.Series(dict(n=len(D),E2=np.mean(D.es**2),c0=np.mean(lo.es**2) if len(lo)>=10 else np.nan,tap=np.mean(D.dtap!=0)))
a=S.groupby(["rb","yl"]).apply(summ,include_groups=False); b=R.groupby(["rb","yl"]).apply(summ,include_groups=False)
A=a.join(b,lsuffix="_sw",rsuffix="_rt"); A["E2비(궤적/sw)"]=A.E2_rt/A.E2_sw
print(A[["n_sw","E2_sw","E2_rt","E2비(궤적/sw)","c0_sw","c0_rt","tap_sw","tap_rt"]].round(4).to_string())
print("\n   같은 거리·감도 셀 E[e²] 궤적/sweep: 줄 묶음별")
for name,sub in {"y=0만":S[S.y==0],"4줄만":S[S.y!=0],"5줄 전체":S}.items():
    g=R.groupby(["rb","ab"]).es.agg(lambda v:np.mean(v**2))/sub.groupby(["rb","ab"]).es.agg(lambda v:np.mean(v**2))
    print(f"  {name:6s}", " ".join(f"{i[0]}/{i[1]}:{v:.2f}" for i,v in g.items()))
def fitB(d):
    lo=d[d.a.abs()<0.3]; c0=np.mean(lo.es**2); c1=nnls(((d.a**2).values)[:,None],(d.es**2-c0).values)[0][0]; return c1,c0
def boot(d,unit,nb=1000):
    g={k:v for k,v in d.groupby(unit)}; ks=list(g); c1,c0=fitB(d)
    bs=np.array([fitB(pd.concat([g[k] for k in rng.choice(ks,len(ks))])) for _ in range(nb)])
    return dict(n=len(ks),th=np.degrees(np.sqrt(c1)),th_ci=np.degrees(np.sqrt(np.quantile(bs[:,0],[.05,.95]))),P0=np.mean(bs[:,0]==0),
                res=np.sqrt(c0),res_ci=np.sqrt(np.quantile(bs[:,1],[.05,.95])),share=c1*np.mean(d.a**2)/np.mean(d.es**2))
print("\n== B. 규칙 B 적합 (위치 단위 bootstrap 90%): σθ° [구간] P(0) | σres [구간] | a² 몫")
Rb=R.assign(blk=R.route+"_"+(R.x/0.45).round().astype(str))
FITS={}
for name,sub,unit in [("y=0만",S[S.y==0],"pos"),("4줄만",S[S.y!=0],"pos"),("5줄 전체",S,"pos"),("궤적 전체",Rb,"blk")]:
    FITS[name]={}
    for bn in ["<3","3-6",">=6"]:
        r=boot(sub[sub.rb==bn],unit); FITS[name][bn]=fitB(sub[sub.rb==bn])
        print(f"  {name:8s} {bn:4s} n={r['n']:3d}  σθ {r['th']:.2f}° [{r['th_ci'][0]:.2f},{r['th_ci'][1]:.2f}] P0 {r['P0']:.2f} | σres {r['res']:.4f} [{r['res_ci'][0]:.4f},{r['res_ci'][1]:.4f}] | a² {r['share']:.2f}")
print("\n== C. 궤적 예측 일관성 (ρ × |a| 셀, n≥25)")
FT=json.load(open("/home/claude/m8/FIT_TABLES.json"))["tables"]
mixed={"<3":FITS["y=0만"]["<3"],"3-6":FITS["y=0만"]["3-6"],">=6":fitB(S[(S.rb==">=6")])}
mixed[">=6"]=fitB(pd.concat([S[(S.rb==">=6")&(S.src!="mid4")]]))
rows=[]
for r in ("R2","R4","R5"):
    d=R[R.route==r]
    tabs={"y=0만":FITS["y=0만"],"혼합(근중 y=0, 원 5줄)":mixed,"5줄 전체":FITS["5줄 전체"],"4줄만":FITS["4줄만"],"경로 LORO":{b:(t["c1"],t["c0"]) for b,t in zip(["<3","3-6",">=6"],FT[r])}}
    for name,f in tabs.items():
        V=np.array([f[b][0] for b in d.rb])*d.a**2+np.array([f[b][1] for b in d.rb]); z=d.es/np.sqrt(V)
        for (bn,s),idx in d.groupby(["rb","ab"]).groups.items():
            if len(idx)<25: continue
            rows.append(dict(route=r,rho=bn,sens=s,table=name,ratio=np.mean(d.es[idx]**2)/np.mean(V[idx]),cov=np.mean(np.abs(z[idx])<=1.96)))
T=pd.DataFrame(rows)
print(T.groupby("table",sort=False).agg(cov_min=("cov","min"),cov_med=("cov","median"),ratio_min=("ratio","min"),ratio_med=("ratio","median"),ratio_max=("ratio","max"),
      in_0p5_2=("ratio",lambda v:np.mean((v>=.5)&(v<=2))),in_0p67_1p5=("ratio",lambda v:np.mean((v>=2/3)&(v<=1.5)))).round(2).to_string())
print("\n   셀별 E[e²]/V (5줄 전체 vs 경로 LORO vs 혼합)")
P=T.pivot_table(index=["route","rho","sens"],columns="table",values="ratio")[["5줄 전체","혼합(근중 y=0, 원 5줄)","y=0만","경로 LORO"]]
C2=T.pivot_table(index=["route","rho","sens"],columns="table",values="cov")[["5줄 전체","경로 LORO"]].add_suffix(" cov")
print(P.join(C2).round(2).to_string())
T.to_csv("stats_all5_prediction.csv",index=False)
json.dump({k:{b:dict(sigma_theta_deg=float(np.degrees(np.sqrt(c1))),sigma_res=float(np.sqrt(c0)),c1=float(c1),c0=float(c0)) for b,(c1,c0) in v.items()} for k,v in FITS.items()},open("SWEEP_FITS_all5.json","w"),indent=1,ensure_ascii=False)
