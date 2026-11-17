import numpy as np, pandas as pd
B="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114"
T=pd.read_csv("/home/claude/diag/dist_uncert_table.csv"); edges=np.r_[T.lo.values,9.01]
ELL={0:.5,1:.5,2:1.3,3:1.3,4:.3,5:.3}; ELLPSI={0:np.radians(30),1:np.radians(30),2:np.radians(30),3:np.radians(30),4:np.radians(12),5:np.radians(12)}
def binof(r): return np.clip(np.digitize(r,edges)-1,0,len(T)-1)
models={
 "A 거리 분산": lambda k,a: T.sA.values[k]**2,
 "C 두 항 (LS)": lambda k,a: a**2*T.st.values[k]**2+T.sr.values[k]**2,
 "C 두 항 (강건)": lambda k,a: a**2*T.str_.values[k]**2+T.srr.values[k]**2,
}
rows=[]; wrows=[]
for r in ["R2","R4","R5"]:
    d3=np.load(f"{B}/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/continuation_d2_d3/d3/B_B0_{r}.npz")
    E=pd.read_csv(f"{B}/CHAR_001/out/ERRORS_{r}_aB_m0.csv.gz").set_index("pose_id").loc[d3["pose_id"]]
    e=E.e_s.to_numpy(); a=E.g_psi.to_numpy()*180/np.pi; rho=np.hypot(E.x.to_numpy()-10,E.y.to_numpy()); k=binof(rho)
    t=d3["t"]; arc=d3["arc_m"]; yw=d3["yaw_arc_rad"]
    for name,f in models.items():
        s2=f(k,a); z=e/np.sqrt(s2)
        for lab,m in [("<3 m",rho<3),("3–6 m",(rho>=3)&(rho<6)),("≥6 m",rho>=6),("전체",rho>=0)]:
            rows.append(dict(route=r,model=name,bin=lab,n=int(m.sum()),cov95=np.mean(np.abs(z[m])<=1.96),mz2=np.mean(z[m]**2)))
        # 5 s windows
        w0=np.floor(t/5).astype(int)
        for w in np.unique(w0):
            m=w0==w; n=m.sum()
            if n<10: continue
            span=(arc[m].max()-arc[m].min())/ELL[int(np.median(k[m]))]+(yw[m].max()-yw[m].min())/ELLPSI[int(np.median(k[m]))]
            nind=min(n,1+span)
            mu=e[m].mean(); vbar=np.mean(s2[m])
            wrows.append(dict(route=r,model=name,rho=np.median(rho[m]),white=abs(mu)<=1.96*np.sqrt(vbar/n),neff=abs(mu)<=1.96*np.sqrt(vbar/nind),nind=nind,n=n))
R=pd.DataFrame(rows); W=pd.DataFrame(wrows)
pd.set_option("display.width",220)
print("== packet 단위 95% 포함률 (목표 0.95) / 평균 z² (목표 1)")
p=R.pivot_table(index=["model","bin"],columns="route",values=["cov95","mz2"]).round(2); print(p.to_string())
print("\n== 5 s 창 평균의 95% 포함률: 백색 가정 vs N_eff 보정 (거리 구분)")
W["bin"]=np.where(W.rho<3,"<3 m",np.where(W.rho<6,"3–6 m","≥6 m"))
q=W.groupby(["model","bin"]).agg(n_win=("white","size"),white=("white","mean"),neff=("neff","mean"),nind_med=("nind","median"),n_med=("n","median")).round(2); print(q.to_string())
