import numpy as np
Z=np.load("/home/claude/diag/station_sweep_errors.npz"); x,yaw,st,d,es,a=Z["x"],Z["yaw"],Z["st"],Z["d"],Z["es"],Z["a"]
dtap=Z["dtap"]; esame=Z["esame"]
rho=np.abs(x-10); D=np.degrees
rows=[]
for s in np.unique(st):
    m=st==s; o=np.argsort(yaw[m]); e=es[m][o]; aa=a[m][o]; ps=yaw[m][o]
    X=np.c_[np.ones(36),aa]; coef,*_=np.linalg.lstsq(X,e,rcond=None); fit=X@coef; r=e-fit
    vt=np.var(e); vh=np.var(coef[1]*aa); vr=np.var(r)
    # local +/-30 deg windows (circular), fit c_w + delta_w a, record heading part at center
    hl=np.empty(36); cl=np.empty(36); rl=np.empty(36)
    for k in range(36):
        w=[(k+j)%36 for j in range(-3,4)]; Xw=np.c_[np.ones(7),aa[w]]; cw,*_=np.linalg.lstsq(Xw,e[w],rcond=None)
        hl[k]=cw[1]*aa[k]; cl[k]=cw[0]; rl[k]=e[k]-cw[0]-cw[1]*aa[k]
    rows.append(dict(x=x[m][0],rho=rho[m][0],ms=np.mean(e**2),vt=vt,mean=np.mean(e),R2g=vh/vt,delta_g=D(coef[1]),
                     H_loc=np.mean(hl**2),C_loc=np.mean(cl**2),Rres_loc=np.mean(rl**2),
                     a_rms=np.sqrt(np.mean(aa**2)),tapshift=np.mean(dtap[m]!=0),same_share=np.var(esame[m])/vt))
import pandas as pd
R=pd.DataFrame(rows).sort_values("x")
pd.set_option("display.width",200)
print(R.round(4).to_string(index=False))
R.to_csv("/home/claude/diag/station_decomp.csv",index=False)
for lab,mm in [("근거리 ρ<3 m",R.rho<3),("원거리 ρ≥3 m",R.rho>=3),("  3–6 m",(R.rho>=3)&(R.rho<6)),("  6–9 m",R.rho>=6)]:
    q=R[mm]; tot=q.H_loc+q.C_loc+q.Rres_loc
    print(f"{lab}: n={len(q)}  e_s RMS {np.sqrt(q.ms.mean()):.4f} | 전역 δ: a로 설명되는 분산 비율 {q.R2g.median():.2f} | 국소(±30°): heading 몫 {(q.H_loc/tot).median():.2f}, s 오프셋 몫 {(q.C_loc/tot).median():.2f}, 잔여 {(q.Rres_loc/tot).median():.2f} | a RMS {q.a_rms.median():.2f}")
