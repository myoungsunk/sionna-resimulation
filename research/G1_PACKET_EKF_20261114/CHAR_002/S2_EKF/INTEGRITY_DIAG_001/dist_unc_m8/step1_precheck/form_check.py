# Validity of e_s^2 ~ a^2 sigma_th(rho)^2 + sigma_res(rho)^2 on ROUTE data (CHAR-001 multipath error e_s = s_full - s_LoS)
import numpy as np, pandas as pd
B="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_001/out"
T=pd.read_csv("/home/claude/diag/dist_uncert_table.csv"); E6=np.r_[T.lo.values,9.01]
rows=[]
for r in ["R2","R4","R5"]:
    D=pd.read_csv(f"{B}/ERRORS_{r}_aB_m0.csv.gz")
    D["route"]=r; D["a"]=D.g_psi*180/np.pi; D["rho"]=np.hypot(D.x-10,D.y)
    D["blk"]=np.arange(len(D))//25  # ~ contiguous pose blocks for bootstrap
    rows.append(D[["route","pose_id","e_s","a","rho","blk"]])
D=pd.concat(rows,ignore_index=True); D["ga"]=D.a.abs()
D["rb"]=pd.cut(D.rho,[0,3,6,9.5],right=False,labels=["<3","3-6",">=6"])
D["sb"]=pd.cut(D.ga,[0,.6,1.3,10],right=False,labels=["low<0.6","mid0.6-1.3","high>=1.3"])
k=np.clip(np.searchsorted(E6,D.rho,side="right")-1,0,5)
D["predC"]=D.a**2*T.st.values[k]**2+T.sr.values[k]**2   # sweep-learned C
D["predA"]=T.sA.values[k]**2
print("== 1. 셀 표본 수 (궤적 × 거리 × 감도)")
print(pd.crosstab([D.route,D.rb],D.sb).to_string())
rng=np.random.default_rng(20261117)
def boot_ratio(d,col,nb=1000):
    g=d.groupby(["route","blk"]); keys=list(g.groups); e2=g.e_s.apply(lambda s:(s**2).sum()).values; p=g[col].sum().values
    if len(keys)<4: return np.nan,np.nan
    rs=[]; 
    for _ in range(nb):
        i=rng.integers(0,len(keys),len(keys)); rs.append(e2[i].sum()/p[i].sum())
    return np.quantile(rs,[.05,.95])
print("\n== 2. E[e²] / 예측 (1 = 맞음). sweep 학습 C, A. [90% block-bootstrap]")
out=[]
for (rb,sb),d in D.groupby(["rb","sb"],observed=True):
    if len(d)<40: continue
    rc=np.mean(d.e_s**2)/np.mean(d.predC); ra=np.mean(d.e_s**2)/np.mean(d.predA)
    lc,hc=boot_ratio(d,"predC"); la,ha=boot_ratio(d,"predA")
    out.append(dict(rho=rb,sens=sb,n=len(d),routes="/".join(f"{x}:{(d.route==x).sum()}" for x in ["R2","R4","R5"]),
        rms_e=np.sqrt(np.mean(d.e_s**2)),mean_e=d.e_s.mean(),C=f"{rc:.2f} [{lc:.2f},{hc:.2f}]",A=f"{ra:.2f} [{la:.2f},{ha:.2f}]"))
print(pd.DataFrame(out).to_string(index=False))
print("\n== 3. 경로 자료만으로 적합: 거리 bin 안에서 E[e²] = c1·a² + c0 (블록 bootstrap 90%)")
for rb,d in D.groupby("rb",observed=True):
    X=np.c_[d.a**2,np.ones(len(d))]; y=d.e_s.values**2
    c=np.linalg.lstsq(X,y,rcond=None)[0]
    keys=d.groupby(["route","blk"]).indices; kl=list(keys.values()); bs=[]
    for _ in range(1000):
        idx=np.concatenate([kl[j] for j in rng.integers(0,len(kl),len(kl))]); bs.append(np.linalg.lstsq(X[idx],y[idx],rcond=None)[0])
    bs=np.array(bs); q=np.quantile(bs,[.05,.95],axis=0)
    st=np.degrees(np.sqrt(max(c[0],0))); sr=np.sqrt(max(c[1],0))
    print(f"ρ {rb}: c1={c[0]:.2e} [{q[0,0]:.2e},{q[1,0]:.2e}] → σθ≈{st:.2f}° | c0={c[1]:.2e} [{q[0,1]:.2e},{q[1,1]:.2e}] → σres≈{sr:.3f}")
    # within-route check (removes route confound)
    for r,dr in d.groupby("route"):
        if dr.ga.max()-dr.ga.min()<0.5 or len(dr)<60: continue
        cc=np.linalg.lstsq(np.c_[dr.a**2,np.ones(len(dr))],dr.e_s.values**2,rcond=None)[0]
        print(f"     {r} 단독 (|a| {dr.ga.quantile(.1):.2f}–{dr.ga.quantile(.9):.2f}): c1={cc[0]:.2e}, c0={cc[1]:.2e}")
D.to_csv("/home/claude/diag/form_check_points.csv.gz",index=False)
