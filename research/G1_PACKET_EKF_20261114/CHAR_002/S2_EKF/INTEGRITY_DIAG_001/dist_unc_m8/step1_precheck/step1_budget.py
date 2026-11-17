import numpy as np, pandas as pd
exec(open("step1_fold_preview.py").read().split('rows=[]\nprint("fold')[0])  # load R, fit defs
exec("\n".join(open("step1_fold_preview.py").read().split("\n")).split('=== 규칙 B')[1].split("rows=[]")[0].split("\n",1)[1])
P="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1/attempt_02/replay/cells/B0/own/seed10"
def causal(t,arc,yaw,mask,V):
    out=np.zeros(len(t)); h=[]
    for i in range(len(t)):
        h=[j for j in h if t[i]-t[j]<=10.][-100:]
        out[i]=sum(2*np.sqrt(V[i]*V[j])*np.exp(-(arc[i]-arc[j])-(yaw[i]-yaw[j])/np.radians(10)) for j in h)
        if mask[i]: h.append(i)
    return out
rows=[]
for r in ["R2","R4","R5"]:
    c=fitB([d for d in R if d!=r]); Z=np.load(f"{P}/{r}/H3/trace.npz")
    t,a,rho,arc,yaw,m=Z["t"],Z["a"],Z["distance"],Z["arc"],Z["yaw"],Z["mask"]; Rpk=Z["R_ref"][:,1,1]
    b=np.clip(np.searchsorted([0,3,6,10],rho,side="right")-1,0,2); c1,c0=c[b,0],c[b,1]
    V=c1*a**2+c0; st=float(Z["sigma_theta_rad"][0])
    arms={"H2 (packet R)":Rpk,"H3 (M7)":Z["Reff"][:,1,1]+a**2*st**2,"F0 white C":V,
          "F1 M-cov":V+causal(t,arc,yaw,m,V),"F2 M-state":c0+causal(t,arc,yaw,m,c0)+c1*a**2}
    eps=R[r].eps.to_numpy()
    for lab,s in [("<3",rho<3),("3-6",(rho>=3)&(rho<6)),(">=6",rho>=6)]:
        row=dict(route=r,rho=lab,abs_a=np.median(np.abs(a[s])),E_eps2=np.mean(eps[s]**2))
        for k,v in arms.items(): row[k]=np.median(v[s])/row["E_eps2"]
        rows.append(row)
D=pd.DataFrame(rows); pd.set_option("display.width",220)
print("중앙값 R_ss,eff / E[ε²] (1 = 실제 오차 2차 모멘트와 같음; F2·H3은 GM 몫 a²σθ² 백색 등가 포함)")
print(D.round(2).to_string(index=False))
