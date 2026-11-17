import sys,glob,json,numpy as np,pandas as pd
sys.path.insert(0,"/home/claude/m8"); from common import TRUTH,packet
EDG=[0,3,6,10]; ARMS=("H2","H3","F0","F1","F2")
eps={}
for r in ("R2","R4","R5"):
    p=packet("B0",10,r); import m8_replay  # noqa
EPS={r:np.load(f"/home/claude/m8/tmp/d3_{r}.npz")["eps"][:,1] for r in ("R2","R4","R5")}
def comp(cond,mode="own"):
    for f in sorted(glob.glob(f"/home/claude/m8/out/{cond}/{mode}/seed*/compact.npz")):
        yield int(f.split("seed")[1].split("/")[0]),np.load(f)
cal=[];bud=[];far=[];bg=[];f2=[]
for cond in ("B0","L2_GYRO_ARW"):
  for seed,Z in comp(cond):
    for r in ("R2","R4","R5"):
        tr=TRUTH[r]["truth"]
        for arm in ARMS:
            k=f"{r}/{arm}/"
            nu=Z[k+"nu"][:,1].astype(float); S=Z[k+"S"][:,1,1].astype(float); a=Z[k+"a"].astype(float); rho=Z[k+"distance"].astype(float)
            Rss=Z[k+"Reff"][:,1,1].astype(float); z=nu/np.sqrt(S)
            rb=np.clip(np.searchsorted(EDG,rho,side="right")-1,0,2); ab=np.digitize(np.abs(a),[0.6,1.3])
            for b in range(3):
                for s in range(3):
                    m=(rb==b)&(ab==s)
                    if m.sum()>=10: cal.append(dict(cond=cond,seed=seed,route=r,arm=arm,rho=b,sens=s,n=int(m.sum()),cov=float(np.mean(np.abs(z[m])<=1.96)),z2=float(np.mean(z[m]**2))))
                m=rb==b
                if cond=="B0" and m.sum():
                    gm={"H3":None,"F2":None}
                    extra=0.
                    if arm=="F2": extra=np.median((a[m]*Z[k+"gm_load"][m])**2)
                    bud.append(dict(seed=seed,route=r,arm=arm,rho=b,Rss_over_E=float((np.median(Rss[m])+extra)/np.mean(EPS[r][m if len(EPS[r])==len(m) else slice(None)]**2))))
            x=Z[k+"x"].astype(float); P=Z[k+"P33"].astype(float); K=Z[k+"K"].astype(float)
            if r=="R5":
                for b in (1,2):
                    m=rb==b
                    far.append(dict(cond=cond,seed=seed,arm=arm,rho=["3-6","6-10"][b-1],sig_psi_deg=float(np.degrees(np.median(np.sqrt(P[m,2,2])))),
                        Kpsi_s=float(np.median(np.abs(K[m,2,1]))),Rss=float(np.median(Rss[m])),y_rms_cm=float(100*np.sqrt(np.mean((x[m,1]-tr[m,1])**2))),
                        head_rms_deg=float(np.degrees(np.sqrt(np.mean(((x[m,2]-tr[m,2]+np.pi)%(2*np.pi)-np.pi)**2))))))
            if r=="R4":
                b_g=Z[k+"b_g"].astype(float); hi=np.abs(a)>=1.3
                bg.append(dict(cond=cond,seed=seed,arm=arm,tv_hi_deg_s=float(np.degrees(np.sum(np.abs(np.diff(b_g))[hi[1:]]))),
                               rmse_deg_s=float(np.degrees(np.sqrt(np.mean(b_g**2)))),end_deg_s=float(np.degrees(b_g[-1]))))
            if arm=="F2":
                f2.append(dict(cond=cond,seed=seed,route=r,P_eta_med=float(np.median(Z[k+"P_eta"])),btheta_deg_p95=float(np.degrees(np.quantile(np.abs(Z[k+"b_theta"]),.95))),
                               corr_with_H3=float(np.corrcoef(Z[k+"b_theta"],Z[f"{r}/H3/b_theta"])[0,1]) if np.std(Z[f"{r}/H3/b_theta"])>0 else np.nan))
pd.set_option("display.width",250)
C=pd.DataFrame(cal)
C["rho"]=C.rho.map({0:"<3",1:"3-6",2:">=6"}); C["sens"]=C.sens.map({0:"|a|<0.6",1:"0.6-1.3",2:">=1.3"})
w=C.assign(cn=C["cov"]*C["n"],zn=C["z2"]*C["n"]).groupby(["cond","arm","rho","sens"])[["n","cn","zn"]].sum()
w["cov95"]=w["cn"]/w["n"]; w["mean_z2"]=w["zn"]/w["n"]
print("== 1. 편파 채널 calibration (ν_s/√S_ss, 수용·거절 모두, 20 seed × 3궤적 합)")
print(w[["n","cov95","mean_z2"]].unstack("arm").xs("B0").round(2).to_string())
print("\n== 2. R5 원거리 기전 (seed 중앙값)")
print(pd.DataFrame(far).groupby(["cond","rho","arm"]).median(numeric_only=True).drop(columns="seed").round(3).to_string())
print("\n== 3. R4 b_g (°/s; 참값 0) seed 중앙값")
print(pd.DataFrame(bg).groupby(["cond","arm"]).median(numeric_only=True).drop(columns="seed").round(3).to_string())
print("\n== 4. F2 상태")
print(pd.DataFrame(f2).groupby(["cond","route"]).median(numeric_only=True).drop(columns="seed").round(3).to_string())
B=pd.DataFrame(bud); B["rho"]=B.rho.map({0:"<3",1:"3-6",2:">=6"})
print("\n== 5. 예산 R_ss,eff/E[ε²] (B0, 자기 trace, seed 중앙값; F2는 GM 등가 a²c1 포함, H3는 GM 미포함)")
print(B.groupby(["route","rho","arm"]).Rss_over_E.median().unstack("arm").round(2).to_string())
for n,df in [("CAL",C),("FAR",pd.DataFrame(far)),("BG",pd.DataFrame(bg)),("F2",pd.DataFrame(f2)),("BUDGET",B)]: df.to_csv(f"/home/claude/m8/DIAG_{n}.csv",index=False)
