import numpy as np, pandas as pd, sys, itertools, json
sys.path.insert(0,"/home/claude/m8"); from common import packet
FZ="/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/MOUNT45_VALIDATION_20261116/frozen_inputs"
SW=pd.read_csv("SWEEP_FEATURES.csv.gz"); SW["psi"]=np.radians(SW.yaw_deg)
EDG=np.array([0,3,6,10]); SW["b"]=np.clip(np.searchsorted(EDG,SW.rho,side="right")-1,0,2)
SW["pos"]=SW.x_eval.round(3).astype(str)+"_"+SW.y_eval.round(2).astype(str)
def wrap(a): return (a+np.pi)%(2*np.pi)-np.pi
def predict(train, q, y, mu0, var0, lx, ly, lp, nug, maxn=150):
    """simple kriging of residual y (train) at query rows q; exponential separable kernel."""
    X=train[["x_eval","y_eval","psi"]].to_numpy(); Q=q[["x","y","psi"]].to_numpy(); out=np.empty(len(Q)); ov=np.empty(len(Q))
    for i,(qx,qy,qp) in enumerate(Q):
        d=np.abs(X[:,0]-qx)/lx+np.abs(X[:,1]-qy)/ly+np.abs(wrap(X[:,2]-qp))/lp
        idx=np.argpartition(d,maxn)[:maxn] if len(d)>maxn else np.arange(len(d))
        Xi=X[idx]; Kij=np.exp(-(np.abs(Xi[:,0,None]-Xi[None,:,0])/lx+np.abs(Xi[:,1,None]-Xi[None,:,1])/ly+np.abs(wrap(Xi[:,2,None]-Xi[None,:,2]))/lp))
        k=np.exp(-d[idx]); A=(1-nug)*Kij+nug*np.eye(len(idx)); w=np.linalg.solve(A,(1-nug)*k)
        out[i]=mu0+w@(y[idx]-mu0); ov[i]=var0*(1-(1-nug)*w@k)
    return out,ov
GRID=list(itertools.product([0.15,0.45,1.0],[0.15,0.5,1.5],[np.radians(10),np.radians(25),np.radians(60)],[0.2,0.5,0.8]))
best={}
rng=np.random.default_rng(0)
for lab in ("e_r","e_s"):
    for b in range(3):
        d=SW[SW.b==b].reset_index(drop=True); mu0=d[lab].mean(); var0=d[lab].var()
        poss=d.pos.unique(); test_pos=rng.choice(poss,min(14,len(poss)),replace=False)
        scores=[]
        for (lx,ly,lp,nug) in GRID:
            se=[]
            for tp in test_pos:
                tr=d[d.pos!=tp]; te=d[d.pos==tp]
                pr,_=predict(tr,te.rename(columns={"x_eval":"x","y_eval":"y"}),tr[lab].to_numpy(),mu0,var0,lx,ly,lp,nug,maxn=120)
                se.append(np.mean((te[lab].to_numpy()-pr)**2))
            scores.append((np.mean(se),(lx,ly,lp,nug)))
        scores.sort(); base=np.mean([np.mean((d[d.pos==tp][lab]-mu0)**2) for tp in test_pos])
        best[(lab,b)]=dict(params=scores[0][1],cv_mse=scores[0][0],baseline_mse=base)
        print(lab,b,"최적",tuple(round(v,3) for v in scores[0][1]),f"CV MSE {scores[0][0]:.5f} / 평균만 {base:.5f} → 설명 {1-scores[0][0]/base:.2f}")
json.dump({f"{k[0]}|{k[1]}":dict(params=list(v["params"]),cv_mse=v["cv_mse"],baseline=v["baseline_mse"]) for k,v in best.items()},open("KRIGE_PARAMS.json","w"),indent=1)
