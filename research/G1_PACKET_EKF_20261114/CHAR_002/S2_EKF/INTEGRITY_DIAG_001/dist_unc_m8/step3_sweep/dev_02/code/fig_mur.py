import numpy as np, pandas as pd, sys, json, glob
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0,"/home/claude/m8"); from common import TRUTH, packet
plt.rcParams.update({"font.family":"Noto Sans CJK KR","font.size":9,"axes.spines.top":False,"axes.spines.right":False,"axes.grid":True,"grid.alpha":.25})
FZ="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_inputs"
F=pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F=F[F.channel=="full"]
CU=np.load("/home/claude/m8cal/SWEEP_CAL_ROUTES.npz"); CW=np.load("/home/claude/m8cal/SWEEP_CAL_ROUTES_RW.npz")
COL={"LORO μ_r (F2SK)":"#0072B2","sweep μ_r (F2SKR)":"#D55E00","sweep μ_r, heading 재가중 (F2SKRW)":"#009E73","보정 없음":"#999999"}
fig,ax=plt.subplots(3,3,figsize=(13,9.5))
seed=int(sys.argv[1]) if len(sys.argv)>1 else 10
Z=np.load(f"/home/claude/m8/out_sweepKR/B0/own/seed{seed}/compact.npz")
for j,r in enumerate(("R2","R4","R5")):
    p=packet("B0",10,r); T=F[F.case==f"{r}_aB_m0"].set_index("pose_id").loc[p["pose_id"]]; tr=TRUTH[r]["truth"]; t=p["t"]
    rho=np.hypot(T.x_eval-10,T.y_eval).values; er=T.e_r.values
    mus={"보정 없음":np.zeros(len(er)),"LORO μ_r (F2SK)":p["muMB"][:,0],"sweep μ_r (F2SKR)":CU[f"{r}/mu_r_sweepHGB"],"sweep μ_r, heading 재가중 (F2SKRW)":CW[f"{r}/mu_r"]}
    edges=np.arange(0,9.6,0.75); c=(edges[:-1]+edges[1:])/2
    for name,mu in mus.items():
        res=100*(er-mu); b=np.digitize(rho,edges)-1
        m=[np.mean(res[b==k]) if np.sum(b==k)>10 else np.nan for k in range(len(c))]
        ax[0,j].plot(c,m,"-o",ms=3,lw=2,color=COL[name],label=name)
    ax[0,j].axhline(0,color="k",lw=.8); ax[0,j].set_title(f"{r}: 거리 잔차 e_r − μ_r 의 평균 (0.75 m bin)"); ax[0,j].set_xlabel("수평거리 ρ (m)"); ax[0,j].set_ylabel("cm")
    for name,arm in (("LORO μ_r (F2SK)","F2SK"),("sweep μ_r (F2SKR)","F2SKR"),("sweep μ_r, heading 재가중 (F2SKRW)","F2SKRW")):
        x=Z[f"{r}/{arm}/x"].astype(float); xy=100*np.hypot(x[:,0]-tr[:,0],x[:,1]-tr[:,1])
        ax[1,j].plot(t,xy,lw=1.6,color=COL[name],label=name)
        he=np.degrees((x[:,2]-tr[:,2]+np.pi)%(2*np.pi)-np.pi); ax[2,j].plot(t,he,lw=1.4,color=COL[name],label=name)
    ax[1,j].set_title(f"{r}: XY 오차 (seed {seed}, B0)"); ax[1,j].set_ylabel("cm"); ax[1,j].set_xlabel("t (s)")
    ax[2,j].set_title(f"{r}: heading 오차"); ax[2,j].set_ylabel("deg"); ax[2,j].set_xlabel("t (s)"); ax[2,j].axhline(0,color="k",lw=.8)
h,l=ax[0,0].get_legend_handles_labels(); fig.legend(h,l,loc="upper center",ncol=4,frameon=False,bbox_to_anchor=(.5,1.0))
fig.tight_layout(rect=(0,0,1,.96)); fig.savefig(f"/home/claude/m8/fig_mur_seed{seed}.png",dpi=130)
print("saved")
