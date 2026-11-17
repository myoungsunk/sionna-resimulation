# Step-1 preview: LORO fit of eps_s^2 = c1 a^2 + c0 per rho bin on filter measurement error eps = z - h(truth) - muMB (D3, seed10 B0)
import numpy as np, pandas as pd
from scipy.optimize import nnls
I="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001"
C="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_001/out"
EDG=[0,3,6,10]; R={}
for r in ["R2","R4","R5"]:
    d3=np.load(f"{I}/continuation_d2_d3/d3/B_B0_{r}.npz"); tr=np.load(f"{I}/m7_final_model_stage1/attempt_02/replay/cells/B0/own/seed10/{r}/H3/trace.npz")
    E=pd.read_csv(f"{C}/ERRORS_{r}_aB_m0.csv.gz").set_index("pose_id").loc[d3["pose_id"]]
    R[r]=pd.DataFrame(dict(eps=d3["eps"][:,1],a=E.g_psi.to_numpy()*180/np.pi,rho=np.hypot(E.x-10,E.y).to_numpy(),Rpk=tr["R_ref"][:,1,1]))
    R[r]["bin"]=np.clip(np.searchsorted(EDG,R[r].rho,side="right")-1,0,2)
def fit(donors):
    out=[]
    for b in range(3):
        X=[];y=[];w=[]
        for d in donors:
            s=R[d][R[d].bin==b]; X.append(np.c_[s.a**2,np.ones(len(s))]); y.append(s.eps**2); w.append(np.full(len(s),1/len(s)))
        X=np.vstack(X);y=np.concatenate(y);w=np.sqrt(np.concatenate(w))
        out.append(nnls(X*w[:,None],y*w)[0])
    return np.array(out)
rows=[]
print("fold 표 (holdout ← donor): bin [0,3) / [3,6) / [6,10) m:  σθ(°), σres")
for h in ["R2","R4","R5"]:
    c=fit([d for d in R if d!=h])
    print(f"{h}: "+" | ".join(f"σθ {np.degrees(np.sqrt(c[b,0])):.2f}°, σres {np.sqrt(c[b,1]):.4f}" for b in range(3)))
    s=R[h]; V=c[s.bin,0]*s.a**2+c[s.bin,1]; z=s.eps/np.sqrt(V); zp=s.eps/np.sqrt(s.Rpk)
    for b,lab in enumerate(["<3","3-6",">=6"]):
        m=s.bin==b
        for sl,ms in [("all",m),("|a|<0.6",m&(s.a.abs()<.6)),("|a|>=1.3",m&(s.a.abs()>=1.3))]:
            if ms.sum()<25: continue
            rows.append(dict(hold=h,rho=lab,sens=sl,n=int(ms.sum()),
              C_ratio=np.mean(s.eps[ms]**2)/np.mean(V[ms]),C_cov95=np.mean(np.abs(z[ms])<=1.96),
              Rpk_ratio=np.mean(s.eps[ms]**2)/np.mean(s.Rpk[ms]),Rpk_cov95=np.mean(np.abs(zp[ms])<=1.96)))
D=pd.DataFrame(rows); pd.set_option("display.width",200)
print("\nholdout: E[ε²]/예측 (1=맞음), packet 95% 포함률 — C(LORO) vs 현재 packet R_ss")
print(D.round(2).to_string(index=False))

print("\n=== 규칙 B: c0 = donor |a|<0.3 packet의 E[ε²] (경로 동일 가중), c1 = NNLS(ε²−c0 ~ a²)")
def fitB(donors):
    out=[]
    for b in range(3):
        c0s=[];X=[];y=[];w=[]
        for d in donors:
            s=R[d][R[d].bin==b]; lo=s[s.a.abs()<0.3]
            if len(lo)>=10: c0s.append(np.mean(lo.eps**2))
        c0=np.mean(c0s)
        for d in donors:
            s=R[d][R[d].bin==b]; X.append((s.a**2).to_numpy()[:,None]); y.append((s.eps**2-c0).to_numpy()); w.append(np.full(len(s),1/len(s)))
        X=np.vstack(X);y=np.concatenate(y);w=np.sqrt(np.concatenate(w))
        out.append([nnls(X*w[:,None],y*w)[0][0],c0,len(c0s)])
    return np.array(out)
rows=[]
for h in ["R2","R4","R5"]:
    c=fitB([d for d in R if d!=h])
    print(f"{h}: "+" | ".join(f"σθ {np.degrees(np.sqrt(c[b,0])):.2f}°, σres {np.sqrt(c[b,1]):.4f} (c0 donor {int(c[b,2])})" for b in range(3)))
    s=R[h]; V=c[s.bin,0]*s.a**2+c[s.bin,1]; z=s.eps/np.sqrt(V)
    for b,lab in enumerate(["<3","3-6",">=6"]):
        m=s.bin==b
        for sl,ms in [("all",m),("|a|<0.6",m&(s.a.abs()<.6)),("0.6-1.3",m&(s.a.abs()>=.6)&(s.a.abs()<1.3)),("|a|>=1.3",m&(s.a.abs()>=1.3))]:
            if ms.sum()<25: continue
            rows.append(dict(hold=h,rho=lab,sens=sl,n=int(ms.sum()),ratio=np.mean(s.eps[ms]**2)/np.mean(V[ms]),cov95=np.mean(np.abs(z[ms])<=1.96),mz2=np.mean(z[ms]**2)))
print(pd.DataFrame(rows).round(2).to_string(index=False))
