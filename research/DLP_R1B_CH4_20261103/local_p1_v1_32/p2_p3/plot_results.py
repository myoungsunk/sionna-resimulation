from pathlib import Path
import csv,json,hashlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
root=Path(__file__).resolve().parent
r=root/"results"
f=root/"figures";f.mkdir(exist_ok=True)
for item in json.loads((r/"REPLAY_OUTPUT_MANIFEST.json").read_bytes())["files"]:
    assert hashlib.sha256((r/item["path"]).read_bytes()).hexdigest()==item["sha256"]
def save(fig,name):
    for ext in ("png","svg"):fig.savefig(f/(name+"."+ext),dpi=150)
    plt.close(fig)
raw=list(csv.DictReader((r/"raw_observation_errors.csv").open()))
def col(name):return np.array([float(row[name]) for row in raw])
fig,ax=plt.subplots(2,2,figsize=(10,6),layout="constrained",sharex="col")
phases=("drive_out","turn","drive_back")
for i,(key,label,scale) in enumerate((("e0_r_m","Full range error (cm)",100),("e0_s","Full signed s error",1))):
    for phase in phases:
        mask=np.array([row["phase"]==phase for row in raw])
        for j,x in enumerate(("t_s","rho_gt_m")):
            ax[i,j].scatter(col(x)[mask],scale*col(key)[mask],s=5,label=phase)
            ax[i,j].axhline(0,color=".7",lw=.4)
        ax[i,0].set_ylabel(label)
ax[0,0].legend();ax[1,0].set_xlabel("Time (s)");ax[1,1].set_xlabel("Horizontal anchor distance (m)")
fig.suptitle("R1 / Anchor B   |   Pre-gate observation errors, 917 poses")
save(fig,"R1_RAW_ERROR_DISTANCE_PHASE")
fig,axs=plt.subplots(2,2,figsize=(10,6),sharex=True,layout="constrained")
scores=list(csv.DictReader((r/"ekf_scores_los_full.csv").open()))
for j,bias in enumerate(("B0","L2")):
    for arm,color in (("los","#186e9c"),("full","#b95421")):
        with np.load(r/f"ekf_trace_{arm}_{bias}.npz",allow_pickle=False) as z:
            yaw=np.rad2deg((z["xpost"][:,2]-z["psi_rad"]+np.pi)%(2*np.pi)-np.pi)
            xy=100*np.hypot(z["xpost"][:,0]-z["x_m"],z["xpost"][:,1]-z["y_m"])
            row=next(s for s in scores if (s["channel"],s["bias_level"],s["window"])==(arm,bias,"t_ge30"))
            for i,(arr,key,unit) in enumerate(((yaw,"heading_rmse_deg","°"),(xy,"xy_rmse_cm"," cm"))):
                axs[i,j].plot(z["t_s"],arr,color=color,lw=1,label=f'{arm.upper()}   {float(row[key]):.2f}{unit}')
    axs[0,j].set_title(bias)
    for ax in axs[:,j]:ax.axvline(30,ls="--",color=".5",lw=.8);ax.legend(fontsize=8)
    axs[1,j].set_xlabel("Time (s)")
axs[0,0].set_ylabel("Wrapped heading error (deg)");axs[1,0].set_ylabel("XY position error (cm)")
fig.suptitle("R1 / Anchor B   |   Legends show RMSE for t ≥ 30 s")
save(fig,"R1_HEADING_XY_TIME_AND_RMSE")
