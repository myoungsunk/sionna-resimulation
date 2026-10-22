#!/usr/bin/env python3
"""Route-heldout diagnostic; only stored Full-CIR features and LoS training labels."""
from pathlib import Path
import json, numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import roc_auc_score

ROOT=Path(__file__).resolve().parent
D=pd.read_csv(ROOT/"results_hpath/HP_PACKETS.csv.gz").sort_values(["case","pose_id"]).reset_index(drop=True)
OUT=ROOT/"results_los_bias";OUT.mkdir(exist_ok=True)
OFFS=[-8,-4,-2,-1,1,2,4,8]
F=["sF_+0","log_fp_power","fp_full"]+[f"sF_{o:+d}" for o in OFFS]
for o in OFFS:
    key=f"ds_{o:+d}"
    D[key]=D[f"sF_{o:+d}"]-D["sF_+0"]
    F.append(key)
assert D.route.nunique()==3 and all(x in D for x in F+["sL_+0","sMGTp1_+0","sMGTm1_+0"])
D["e_true"]=D["sF_+0"]-D["sL_+0"]
rows=[];cases=[];qa=[]
def rmse(x):
    x=np.asarray(x,float);return float(np.sqrt(np.mean(x*x)))
def mkm():
    return HistGradientBoostingRegressor(max_iter=160,learning_rate=.055,max_leaf_nodes=17,max_depth=5,min_samples_leaf=20,l2_regularization=1.,random_state=20261022)
for held in ["R2","R4","R5"]:
    tr=D[D.route!=held].copy();te=D[D.route==held].copy()
    med=tr[F].replace([np.inf,-np.inf],np.nan).median().fillna(0)
    A=tr[F].replace([np.inf,-np.inf],np.nan).fillna(med).reset_index(drop=True)
    B=te[F].replace([np.inf,-np.inf],np.nan).fillna(med).reset_index(drop=True)
    y=tr.e_true.to_numpy()
    cir=mkm().fit(A,y)
    cir_pred=cir.predict(B)
    # d0 is formed from exactly available +/-1 degree LoS LUT lookup, no ground-truth e fed to model.
    # The same train packets are duplicated as 2 prior-perturbation conditions.
    tr_prior=np.r_[tr["sMGTp1_+0"].to_numpy(),tr["sMGTm1_+0"].to_numpy()]
    tr_full=np.r_[tr["sF_+0"].to_numpy(),tr["sF_+0"].to_numpy()]
    Atr=pd.concat([A,A],ignore_index=True)
    Atr["d0"]=tr_full-tr_prior
    yy=np.r_[y,y]
    d0model=mkm().fit(Atr,yy)
    threshold=float(np.quantile(np.abs(y),.95))
    q={"held_route":held,"train_n":len(tr),"test_n":len(te),"prior_deg":[-1,1],"bias_threshold_train":threshold}
    qa.append(q)
    for delta,lutcol in [(1,"sMGTp1_+0"),(-1,"sMGTm1_+0")]:
        d0=te["sF_+0"].to_numpy()-te[lutcol].to_numpy()
        Xt=B.copy();Xt["d0"]=d0
        d0_pred=d0model.predict(Xt)
        e_true=te.e_true.to_numpy();sL=te["sL_+0"].to_numpy();sF=te["sF_+0"].to_numpy()
        # for signed heading error eprior = prior - truth = delta
        g=(te["sMGTp1_+0"].to_numpy()-te["sMGTm1_+0"].to_numpy())/2
        k=9*g/(9*g*g+.01)
        m={"RAW":np.zeros(len(te)),"CIR_ONLY":cir_pred,"CIR_PLUS_D0":d0_pred,
           "D0_DIRECT":d0,"MIX_25":.25*cir_pred+.75*d0,
           "MIX_50":.5*cir_pred+.5*d0,"MIX_75":.75*cir_pred+.25*d0,
           "ORACLE_LOS":e_true}
        gtrue=sL-te[lutcol].to_numpy()
        for name,ehat in m.items():
            pred=sF-ehat;nu=pred-te[lutcol].to_numpy()
            nu_prior=te["sF_+0"].to_numpy()-te[lutcol].to_numpy()
            # fixed-gain diagnostic, no recursive claims
            post=delta+k*nu
            rec={"route":held,"delta":delta,"arm":name,"n":len(te),
                 "los_rmse":rmse(pred-sL),"los_mae":float(np.mean(np.abs(pred-sL))),
                 "hdiag_rmse_deg":rmse(post),"hdiag_mae_deg":float(np.mean(np.abs(post))),
                 "residual_mean":float(np.mean(pred-sL)),
                 "d0_auc_trainlabel":float(roc_auc_score(np.abs(e_true)>=threshold,np.abs(d0))) if len(np.unique(np.abs(e_true)>=threshold))==2 else np.nan}
            rows.append(rec)
            tmp=te[["case","route","pose_id"]].copy()
            tmp["delta"]=delta;tmp["arm"]=name;tmp["los_error"]=pred-sL;tmp["nu"]=nu;tmp["oracle_nu"]=gtrue;tmp["hdiag_post_deg"]=post
            cases.append(tmp)
    # heading sensitivity across prior perturbation for each matching pose
    recs=pd.DataFrame(rows)
    for name in m:
        ru=[r for r in rows if r["route"]==held and r["arm"]==name]
        assert len(ru)==2
ALL=pd.DataFrame(rows);S=pd.concat(cases,ignore_index=True)
gain=[]
for (route,arm),d in S.groupby(["route","arm"]):
    w=d.pivot_table(index=["case","pose_id"],columns="delta",values=["nu","oracle_nu"])
    w=w.dropna()
    a=(w[("nu",1)]-w[("nu",-1)]).to_numpy()
    b=(w[("oracle_nu",1)]-w[("oracle_nu",-1)]).to_numpy()
    # oracle_nu differences are exactly -2*g
    gain.append({"route":route,"arm":arm,"gain":float(a@b/(b@b)),"diff_rmse":rmse(a-b),"pairs":len(w)})
G=pd.DataFrame(gain)
assert np.max(np.abs(G[G.arm=="D0_DIRECT"].gain.to_numpy()))<1e-10
assert np.max(np.abs(G[G.arm=="CIR_ONLY"].gain.to_numpy()-1))<1e-10
ALL.to_csv(OUT/"LOSC_MEASUREMENT.csv",index=False)
G.to_csv(OUT/"LOSC_GAIN.csv",index=False)
S.to_csv(OUT/"LOSC_PACKET_DIAGNOSTIC.csv.gz",index=False,compression="gzip")
(OUT/"LOSC_QA.json").write_text(json.dumps({"samples":len(D),"routes":sorted(D.route.unique().tolist()),"train_eval_separated":True,"source_file":"results_hpath/HP_PACKETS.csv.gz","feature_columns":F,"model":"HGB 160 iterations fixed","qa":qa},indent=2))
print("RESULTS")
print(ALL.groupby(["route","arm"])[["los_rmse","hdiag_rmse_deg"]].mean().round(5).to_string())
print("HEADING GAIN")
print(G.round(5).to_string(index=False))
