import sys, pickle, json, numpy as np, pandas as pd
from multiprocessing import Pool
sys.path.insert(0,"/home/claude/v1"); from v1_common import *
_G={}
def init():
    from common import env, scorers; import h_ref as HR, sw_block_fullco as SB
    g,Rrr,Rss=pickle.load(open("/home/claude/v1/CAL_V1.pkl","rb")); F=pd.read_csv(f"{FZ}/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F=F[F.channel=="full"]
    e=env(); blk=SB.SWB().s_fn(); _G.update(g=g,Rrr=np.array(Rrr),Rss=np.array(Rss),F=F,e=e,eS=HR.swap_env(e,blk),blk=blk,sc=scorers())
def job(seed):
    from common import packet, TRUTH, m7_kwargs, R7; from run_m8s3 import sweep_packet, ZERO_SB; import m8_replay as M
    ft,swb,bm=_G["sc"]; r="R5"; p=packet("B0",seed,r); T=_G["F"][_G["F"].case=="R5_aB_m0"].set_index("pose_id").loc[p["pose_id"]].reset_index()
    bh=bin3(rho_hat(p["z"][:,0])); mu=_G["g"].predict(T[EXIST]); z0=np.zeros(len(mu)); tab=dict(edges=E3.tolist(),c1=[0.]*3,c0=_G["Rss"].tolist())
    tr={"SWB-U3":M.replay_m8(sweep_packet(p,mu,z0,_G["Rrr"][bh],_G["Rss"][bh]),_G["eS"],"F0",table=tab,sigma_b=ZERO_SB,condition="B0",**M.ARM_MODES["F0"]),
        "SWB-U0":M.replay_m8(sweep_packet(p,z0,z0,_G["Rrr"][bh],_G["Rss"][bh]),_G["eS"],"F0",table=tab,sigma_b=ZERO_SB,condition="B0",**M.ARM_MODES["F0"]),
        "H2":M.replay_m8(p,_G["e"],"F0",table=dict(edges=E3.tolist(),c1=[0.]*3,c0=[1e-9]*3),sigma_b=ZERO_SB,condition="B0",white="packet",corr=None,gm=None) if False else R7.replay(p,_G["e"],"H2",**m7_kwargs("H2",r,"B0"))}
    X=TRUTH[r]["truth"]; t=p["t"]; w=lambda a:(a+np.pi)%(2*np.pi)-np.pi
    out=dict(seed=seed,dpsi0=float(np.degrees(w(p["x0"][2]-X[0,2]))))
    for a,d in tr.items():
        b=bm(d,X,t); out[f"{a}|mirror"]=int(b["mirror_fail_count"]>0 and b["passages"][0]["MIRROR_FAIL"])
        i34=int(np.argmin(abs(t-34))); s=slice(0,i34+1); m=d["mask"][s].astype(bool)
        K=d["K"][s]; nu=d["nu"][s]
        for c,nm in ((0,"r"),(1,"s")):
            out[f"{a}|dpsi_{nm}"]=float(np.degrees(np.sum((K[:,2,c]*nu[:,c])[m]))); out[f"{a}|dy_{nm}"]=float(100*np.sum((K[:,1,c]*nu[:,c])[m]))
        out[f"{a}|epsi34"]=float(np.degrees(w(d["x"][i34,2]-X[i34,2]))); out[f"{a}|ey34"]=float(100*(d["x"][i34,1]-X[i34,1]))
        out[f"{a}|dpsi_pred"]=float(np.degrees(w(d["x"][i34,2]-d["x"][0,2]))-out[f"{a}|dpsi_r"]-out[f"{a}|dpsi_s"])
    # static polarization residual at true pose in approach window (SWB vs FFD)
    st=np.c_[X[:i34+1,:3],np.zeros(i34+1)]; zs=p["z"][:i34+1,1]
    mS,JS=_G["blk"](st,None); hF,HF=_G["e"]["model"].batch(st,_G["e"]["spec"])
    out["res_s_SWB"]=float(np.mean(zs-mS)); out["res_s_FFD"]=float(np.mean(zs-hF[:,1])); out["res_s_H2"]=float(np.mean(zs-hF[:,1]-p["muMB"][:i34+1,1]))
    out["a_SWB"]=float(np.median(np.abs(JS[:,2]))); out["a_FFD"]=float(np.median(np.abs(HF[:,1,2]))); out["ay_SWB"]=float(np.median(np.abs(JS[:,1]))); out["ay_FFD"]=float(np.median(np.abs(HF[:,1,1])))
    out["res_r"]=float(100*np.mean(p["z"][:i34+1,0]-hF[:,0])); out["res_r_U3"]=float(100*np.mean(p["z"][:i34+1,0]-hF[:,0]-mu[:i34+1])); out["rho_end"]=float(np.hypot(X[i34,0]-10,X[i34,1]))
    return out
if __name__=="__main__":
    with Pool(2,initializer=init) as pool: R=pool.map(job,range(10,30))
    D=pd.DataFrame(R); D.to_csv("MIRROR_DECOMP_R5.csv",index=False)
    print(D[["res_s_SWB","res_s_FFD","res_s_H2","a_SWB","a_FFD","ay_SWB","ay_FFD","res_r","res_r_U3","rho_end"]].iloc[0].round(4).to_dict())
    for a in ("H2","SWB-U0","SWB-U3"):
        cols=[f"{a}|{k}" for k in ("mirror","epsi34","ey34","dpsi_pred","dpsi_r","dpsi_s","dy_r","dy_s")]
        print("\n==",a,"mirror seeds",D.seed[D[f"{a}|mirror"]>0].tolist())
        print(D.groupby(D[f"{a}|mirror"]>0)[cols[1:]].median().round(2).to_string())
