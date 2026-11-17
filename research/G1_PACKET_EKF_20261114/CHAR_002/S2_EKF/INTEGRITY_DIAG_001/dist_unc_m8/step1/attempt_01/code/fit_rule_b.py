# Step-1 rule B LORO fit with SourceFFD analytic a_truth (P1 checks included)
import sys,json,numpy as np,pandas as pd
from scipy.optimize import nnls
sys.path.insert(0,"/home/claude/m8"); from common import *
e=env(); model,spec=e["model"],e["spec"]
EDG=np.array([0.,3.,6.,10.]); D={}; P1={}
for r in ("R2","R4","R5"):
    p=packet("B0",10,r); tr=TRUTH[r]["truth"]; assert np.array_equal(p["pose_id"],TRUTH[r]["pose_id"])
    st=np.c_[tr,np.zeros(len(tr))]
    h,H=model.batch(st,spec)[:2]
    eps=p["z"][:,1]-h[:,1]-p["muMB"][:,1]; a=H[:,1,2]
    d3=np.load(f"/home/claude/m8/tmp/d3_{r}.npz"); P1[r]=dict(eps_vs_d3=float(np.max(np.abs(eps-d3["eps"][:,1]))))
    C=pd.read_csv(f"/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_001/out/ERRORS_{r}_aB_m0.csv.gz").set_index("pose_id").loc[p["pose_id"]]
    afd=C.g_psi.to_numpy()*180/np.pi; big=np.abs(afd)>=0.2
    P1[r].update(sign_mismatch=int(np.sum(np.sign(afd[big])!=np.sign(a[big]))),med_rel=float(np.median(np.abs(a[big]-afd[big])/np.abs(afd[big]))))
    rho=np.hypot(tr[:,0]-spec["anchor"][0],tr[:,1]-spec["anchor"][1])
    D[r]=pd.DataFrame(dict(eps=eps,a=a,rho=rho,bin=np.clip(np.searchsorted(EDG,rho,side="right")-1,0,2)))
print("P1",json.dumps(P1,indent=0))
def fitB(donors):
    tab=[]
    for b in range(3):
        anchors={d:float(np.mean(D[d][(D[d].bin==b)&(D[d].a.abs()<0.3)].eps**2)) for d in donors if ((D[d].bin==b)&(D[d].a.abs()<0.3)).sum()>=10}
        if not anchors: raise SystemExit(f"STOP_NO_ANCHOR bin {b}")
        c0=float(np.mean(list(anchors.values())))
        X=[];y=[];w=[]
        for d in donors:
            s=D[d][D[d].bin==b]; X.append((s.a**2).to_numpy()); y.append((s.eps**2-c0).to_numpy()); w.append(np.full(len(s),1/len(s)))
        X=np.concatenate(X);y=np.concatenate(y);sw=np.sqrt(np.concatenate(w))
        c1=float(nnls((X*sw)[:,None],y*sw)[0][0])
        tab.append(dict(lo=float(EDG[b]),hi=float(EDG[b+1]),c1=c1,c0=c0,sigma_theta_rad=np.sqrt(c1),sigma_theta_deg=float(np.degrees(np.sqrt(c1))),sigma_res=np.sqrt(c0),
                        anchor_donors=sorted(anchors),n_by_donor={d:int((D[d].bin==b).sum()) for d in donors}))
    return tab
PRE={"R2":[(1.38,.0112),(3.64,.0351),(5.56,.1221)],"R4":[(1.04,.0104),(4.21,.0347),(7.54,.1058)],"R5":[(1.37,.0094),(3.67,.0343),(6.26,.0865)]}
TABLES={}; worst=0
for h in ("R2","R4","R5"):
    t=fitB([d for d in D if d!=h]); TABLES[h]=t
    for b,row in enumerate(t):
        dth=abs(row["sigma_theta_deg"]/PRE[h][b][0]-1); dr=abs(row["sigma_res"]/PRE[h][b][1]-1); worst=max(worst,dth,dr)
        print(h,f"[{row['lo']:.0f},{row['hi']:.0f})",f"σθ {row['sigma_theta_deg']:.3f}° (pre {PRE[h][b][0]}) σres {row['sigma_res']:.4f} (pre {PRE[h][b][1]}) anchors {row['anchor_donors']}")
print("max relative deviation from preview",round(worst,4),"PASS" if worst<=0.10 else "STOP")
json.dump(dict(rule="B",bins=EDG.tolist(),tables=TABLES,P1=P1,max_dev_vs_preview=worst),open("/home/claude/m8/FIT_TABLES.json","w"),indent=1,default=float)
