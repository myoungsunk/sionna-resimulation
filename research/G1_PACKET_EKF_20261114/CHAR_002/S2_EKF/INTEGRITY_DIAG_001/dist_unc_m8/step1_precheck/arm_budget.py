# Offline s-channel noise budget per arm along M7 B0 seed10 H3 trajectory (prior a, prior rho, own accepted mask).
import numpy as np, pandas as pd
P="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/m7_final_model_stage1/attempt_02/replay/cells/B0/own/seed10"
T=pd.read_csv("/home/claude/diag/dist_uncert_table.csv"); E=np.r_[T.lo.values,9.01]
ELL=np.array([.5,.5,1.3,1.3,.3,.3]); ELP=np.radians([30,30,30,30,12,12])
def b(r): return np.clip(np.searchsorted(E,r,side="right")-1,0,5)
def causal(t,arc,yaw,mask,V,ell,elp):
    out=np.zeros(len(t)); hist=[]
    for i in range(len(t)):
        hist=[h for h in hist if t[i]-t[h]<=10.][-100:]
        out[i]=sum(2*np.sqrt(V[i]*V[j])*np.exp(-(arc[i]-arc[j])/ell[i]-(yaw[i]-yaw[j])/elp[i]) for j in hist)
        if mask[i]: hist.append(i)
    return out
rows=[]
for r in ["R2","R4","R5"]:
    Z=np.load(f"{P}/{r}/H3/trace.npz")
    t,a,rho,arc,yaw,m=Z["t"],Z["a"],Z["distance"],Z["arc"],Z["yaw"],Z["mask"]
    R0=Z["R_ref"][:,1,1]; k=b(rho); ell,elp=ELL[k],ELP[k]
    st=float(Z["sigma_theta_rad"][0])
    arms={}
    arms["H3 (M7)"]=Z["Reff"][:,1,1]+a**2*st**2           # KI R_eff + GM marginal a²σθ²
    V6=a**2*T.st.values[k]**2+T.sr.values[k]**2
    arms["H6W"]=R0+V6
    arms["H6 M-cov"]=R0+V6+causal(t,arc,yaw,m,V6,ell,elp)
    Vr=T.sr.values[k]**2
    arms["H7 M-state"]=R0+Vr+causal(t,arc,yaw,m,Vr,ell,elp)+a**2*T.st.values[k]**2
    V8=T.sA.values[k]**2
    arms["H8"]=R0+V8+causal(t,arc,yaw,m,V8,ell,elp)
    for lab,sel in [("<3 m",rho<3),("3–6 m",(rho>=3)&(rho<6)),("≥6 m",rho>=6)]:
        row=dict(route=r,bin=lab,n=int(sel.sum()),abs_a=np.median(np.abs(a[sel])),R_ref=np.median(R0[sel]))
        for nm,v in arms.items(): row[nm]=np.median(v[sel]/R0[sel])
        rows.append(row)
D=pd.DataFrame(rows); pd.set_option("display.width",250)
print("중앙값: R_ss,eff / R_ref,ss  (H3·H7은 GM 몫 a²σθ²를 등가 백색으로 더한 값)")
print(D.round(2).to_string(index=False))
D.to_csv("/home/claude/diag/arm_budget.csv",index=False)
