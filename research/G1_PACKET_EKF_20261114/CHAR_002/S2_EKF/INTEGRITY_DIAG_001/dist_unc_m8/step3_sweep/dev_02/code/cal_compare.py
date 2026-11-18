import sys, numpy as np, pandas as pd, importlib.util, json
sys.path.insert(0,"/home/claude/m8cal"); sys.path.insert(0,"/home/claude/m8")
from feats import FE, FZ, EXIST
from common import packet
from sklearn.ensemble import HistGradientBoostingRegressor
s=importlib.util.spec_from_file_location("n4b",f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py"); n4b=importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
pd.set_option("display.width",240)
SW=pd.read_csv("SWEEP_FEATURES.csv.gz")
F=pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F=F[F.channel=="full"]
w_sw=n4b.site_weights(np,pd,SW)
hgb=HistGradientBoostingRegressor(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=0).fit(SW[EXIST],SW.e_r)
out={}; rows=[]
for r in ("R2","R4","R5"):
    p=packet("B0",10,r); T=F[F.case==f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    assert np.max(np.abs(T[["range_m","s_fp"]].to_numpy()-p["z"]))<1e-9
    mu_sp,cov_sp,info=n4b.fit_model(np,SW,T,w_sw,"POWER_BIN_JOINT",FE.GROUPS); cov_sp[:,0,1]=cov_sp[:,1,0]=0
    mu_hgb=hgb.predict(T[EXIST])
    rho=np.hypot(T.x_eval-10,T.y_eval); er,es=T.e_r.to_numpy(),T.e_s.to_numpy()
    out[r]=dict(mu_r_sweepPOWER=mu_sp[:,0],mu_r_sweepHGB=mu_hgb,mu_s_sweepPOWER=mu_sp[:,1],Rrr_sweep=cov_sp[:,0,0],Rss_sweepPOWER=cov_sp[:,1,1],bins=info["bins"],cuts=info["cutpoints_train"])
    MU={"LORO μ_MB(HGB EXDS)":p["muMB"][:,0],"LORO μ_BASE(POWER)":p["muBASE"][:,0],"sweep POWER":mu_sp[:,0],"sweep HGB(EX)":mu_hgb,"sweep 상수":np.full(len(er),np.average(SW.e_r,weights=w_sw)),"0":np.zeros(len(er))}
    RR={"LORO R_rr":p["R"][:,0,0],"sweep R_rr":cov_sp[:,0,0]}
    MS={"LORO μ_s":p["muMB"][:,1],"sweep POWER μ_s":mu_sp[:,1],"0":np.zeros(len(er))}
    for lab,m in [("<3",rho<3),("3-6",(rho>=3)&(rho<6)),(">=6",rho>=6),("전체",rho>=0)]:
        for k,mu in MU.items():
            res=er[m]-mu[m]; row=dict(route=r,rho=lab,ch="range",mean=k,bias_cm=100*res.mean(),rms_cm=100*np.sqrt(np.mean(res**2)))
            for kk,R in RR.items():
                z=res/np.sqrt(R[m]); row[f"cov95[{kk}]"]=np.mean(np.abs(z)<=1.96); row[f"z2[{kk}]"]=np.mean(z**2)
            rows.append(row)
        for k,mu in MS.items():
            res=es[m]-mu[m]; rows.append(dict(route=r,rho=lab,ch="s",mean=k,bias_cm=res.mean(),rms_cm=np.sqrt(np.mean(res**2))))
D=pd.DataFrame(rows); D.to_csv("CAL_COMPARE.csv",index=False)
print("sweep POWER 모델: log_fp_power 삼분위 cut",out["R2"]["cuts"]); print(pd.DataFrame(out["R2"]["bins"]).round(5).to_string(index=False))
print("\n== 거리 채널: 평균 보정별 잔차 (cm) 와 분산 calibration")
d=D[D.ch=="range"]
print(d[d.rho=="전체"].pivot_table(index="mean",columns="route",values=["bias_cm","rms_cm"]).round(2).to_string())
print("\n   포함률·z² (평균=LORO μ_MB 또는 sweep 평균, 분산=LORO 또는 sweep R_rr)")
sel=d[d["mean"].isin(["LORO μ_MB(HGB EXDS)","sweep POWER","sweep HGB(EX)"])]
print(sel.pivot_table(index=["route","rho"],columns="mean",values=["cov95[LORO R_rr]","cov95[sweep R_rr]","z2[LORO R_rr]","z2[sweep R_rr]"]).round(2).to_string())
print("\n== 거리 채널 R_rr 크기 비교 (중앙값, m²)")
for r in ("R2","R4","R5"):
    p=packet("B0",10,r); print(r,"LORO",np.round(np.median(p["R"][:,0,0]),5),"sweep",np.round(np.median(out[r]["Rrr_sweep"]),5))
print("\n== 편파 채널 평균: 잔차 bias / RMS")
d=D[D.ch=="s"]; print(d.pivot_table(index=["route","rho"],columns="mean",values=["bias_cm","rms_cm"]).round(4).to_string())
np.savez("SWEEP_CAL_ROUTES.npz",**{f"{r}/{k}":v for r in out for k,v in out[r].items() if isinstance(v,np.ndarray)})
