import numpy as np, pandas as pd, sys, json
sys.path.insert(0,"/home/claude/m8"); sys.path.insert(0,"/home/claude/m8cal"); from common import packet
exec(open("krige.py").read().split("GRID=")[0])
P=json.load(open("KRIGE_PARAMS.json"))
F=pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F=F[F.channel=="full"]
out={}; rows=[]
for r in ("R2","R4","R5"):
    p=packet("B0",10,r); T=F[F.case==f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    q=pd.DataFrame(dict(x=T.x_eval,y=T.y_eval,psi=T.yaw_eval_rad)); rho=np.hypot(q.x-10,q.y).values; qb=np.clip(np.searchsorted(EDG,rho,side="right")-1,0,2)
    pred={}
    for lab in ("e_r","e_s"):
        mu=np.empty(len(q)); var=np.empty(len(q))
        for b in range(3):
            m=qb==b
            if not m.any(): continue
            d=SW[SW.b==b].reset_index(drop=True); prm=P[f"{lab}|{b}"]["params"]
            mu[m],var[m]=predict(d,q[m],d[lab].to_numpy(),d[lab].mean(),d[lab].var(),*prm)
        pred[lab]=(mu,var)
    out[r]=dict(mu_r=pred["e_r"][0],var_r=pred["e_r"][1],mu_s=pred["e_s"][0],var_s=pred["e_s"][1])
    for lab,key,ch in (("e_r","mu_r",0),("e_s","mu_s",1)):
        e=T[lab].values
        for bl,m in (("<3",rho<3),("3-6",(rho>=3)&(rho<6)),(">=6",rho>=6),("전체",rho>=0)):
            for name,mu in (("보정없음",np.zeros(len(e))),("LORO",p["muMB"][:,ch]),("sweep kriging",out[r][key])):
                res=e[m]-mu[m]; rows.append(dict(route=r,ch=lab,rho=bl,mean=name,bias=res.mean(),rms=np.sqrt(np.mean(res**2)),R2=1-np.mean(res**2)/np.mean((e[m]-e[m].mean())**2)))
D=pd.DataFrame(rows); pd.set_option("display.width",220)
for lab,sc in (("e_r",100),("e_s",1)):
    d=D[D.ch==lab].copy(); d["bias"]*=sc; d["rms"]*=sc
    print(f"== {lab} 잔차 ({'cm' if sc==100 else 's'}) : bias / RMS / 설명률(분산)")
    print(d.pivot_table(index=["route","rho"],columns="mean",values=["bias","rms","R2"]).round(3).to_string())
np.savez("KRIGE_ROUTES.npz",**{f"{r}/{k}":v for r in out for k,v in out[r].items()})
