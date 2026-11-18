import sys, numpy as np, pandas as pd, importlib.util, json
sys.path.insert(0,"/home/claude/m8cal"); sys.path.insert(0,"/home/claude/m8")
from feats import FE, FZ, EXIST
from common import packet
from sklearn.ensemble import HistGradientBoostingRegressor
s=importlib.util.spec_from_file_location("n4b",f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/89df74db9945_n4b_rf_errors.py"); n4b=importlib.util.module_from_spec(s); s.loader.exec_module(n4b)
SW=pd.read_csv("SWEEP_FEATURES.csv.gz")
F=pd.read_csv(f"{FZ}/OFFICE_CORRIDOR_TRANSFER_FIX_20261026/6a69a36ad0f5_OBSERVATION_FEATURES_LABELS.csv.gz"); F=F[F.channel=="full"]
# route heading distribution (body yaw, 10° bins), pooled over the two donor routes only (LORO-consistent), no error labels used
def yawbin(deg): return np.floor(((np.asarray(deg)+185)%360)/10).astype(int)   # bins centred on -180..170
out={}
for hold in ("R2","R4","R5"):
    don=F[(F.route!=hold)&(F.case.str.endswith("_aB_m0"))]
    h=np.bincount(yawbin(np.degrees(don.yaw_eval_rad)),minlength=36).astype(float); h/=h.sum()
    w=h[yawbin(SW.yaw_deg)]*36; w=w/w.mean()
    mu,cov,_=n4b.fit_model(np,SW,F[F.case==f"{hold}_aB_m0"].set_index("pose_id").loc[packet("B0",10,hold)["pose_id"]].reset_index(),w,"POWER_BIN_JOINT",FE.GROUPS)
    g=HistGradientBoostingRegressor(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=0).fit(SW[EXIST],SW.e_r,sample_weight=w)
    T=F[F.case==f"{hold}_aB_m0"].set_index("pose_id").loc[packet("B0",10,hold)["pose_id"]].reset_index()
    out[hold]=dict(mu_s=mu[:,1],mu_r=g.predict(T[EXIST]),Rrr=cov[:,0,0],w_eff=float(w.sum()**2/(w**2).sum()))
    p=packet("B0",10,hold); er,es=T.e_r.values,T.e_s.values
    print(f"{hold}: 유효 표본 {out[hold]['w_eff']:.0f}/7200 | s 잔차 편향: 보정없음 {es.mean():+.4f}, LORO {np.mean(es-p['muMB'][:,1]):+.4f}, sweep 재가중 {np.mean(es-mu[:,1]):+.4f}"
          f" | r 잔차 RMS: LORO {100*np.sqrt(np.mean((er-p['muMB'][:,0])**2)):.2f}, sweep 재가중 {100*np.sqrt(np.mean((er-out[hold]['mu_r'])**2)):.2f} cm")
np.savez("SWEEP_CAL_ROUTES_RW.npz",**{f"{r}/{k}":v for r in out for k,v in out[r].items() if isinstance(v,np.ndarray)})
