"""V0-1 (sweep stage): range mean-correction candidates, x-column-out CV on RT Corridor sweep (200 st x 36 yaw).
U0 none | U1 3-bin rho mean [0,3,6,10) | U1f 1 m rho-bin mean (diagnostic) | U3 CAL_U: HGB(EXIST CIR features), uniform station weights.
Residual after correction -> per-bin mean, RMS, sd; R_rr as rho-bin variance of CV residual (bins [0,3,6,10))."""
import json, numpy as np, pandas as pd, sys
from sklearn.ensemble import HistGradientBoostingRegressor
EXIST=['log_fp_power','abs_s_fp','early4','early8','early16','delay_rms_ns','peak_diff_ns','eta_fp_win80','s_diff4','s_diff8','s_diff16','tap_pol_var80','jones_diversity','freq_s_var','detector_s_span','detector_delay_span_ns']
S=pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz"); col=S.x_eval.round(3); cols=np.sort(col.unique())
E3=np.array([0,3,6,10.]); b3=np.clip(np.searchsorted(E3,S.rho,side="right")-1,0,2); b1=np.clip(np.floor(S.rho).astype(int),0,9)
pred={k:np.zeros(len(S)) for k in ("U0","U1","U1f","U3")}
for c in cols:
    te=(col==c).values; tr=~te
    for k,bb in (("U1",b3),("U1f",b1)):
        m=pd.Series(S.e_r[tr].values).groupby(bb[tr]).mean(); pred[k][te]=m.reindex(bb[te]).fillna(S.e_r[tr].mean()).values
    g=HistGradientBoostingRegressor(max_iter=200,learning_rate=0.05,max_leaf_nodes=15,l2_regularization=1.0,random_state=0).fit(S.loc[tr,EXIST],S.e_r[tr])
    pred["U3"][te]=g.predict(S.loc[te,EXIST])
R={}
for k,p in pred.items():
    r=S.e_r.values-p; rows=[]
    for q in range(3):
        m=b3==q; rows.append(dict(bin=[E3[q],E3[q+1]],mean_cm=100*r[m].mean(),rms_cm=100*np.sqrt(np.mean(r[m]**2)),sd_cm=100*r[m].std(),
                                  p95_abs_cm=100*np.quantile(np.abs(r[m]),.95)))
    # station-level mean (what a static bias looks like to the filter): per-station mean residual spread
    st=pd.Series(r).groupby([S.x_eval.round(3),S.y_eval.round(2)]).mean()
    R[k]=dict(bins=rows,station_mean_sd_cm=100*float(st.std()),far_ge6_mean_cm=100*float(r[S.rho>=6].mean()))
raw=S.e_r.values; R["raw_e_r_by_1m"]= {int(i):round(100*float(raw[b1==i].mean()),2) for i in range(10) if (b1==i).any()}
json.dump(R,open("V0_RANGE_CV.json","w"),indent=1,default=float)
for k in ("U0","U1","U1f","U3"):
    print(k, " | ".join(f"{int(r['bin'][0])}-{int(r['bin'][1])}m mean {r['mean_cm']:+.2f} rms {r['rms_cm']:.2f} p95 {r['p95_abs_cm']:.2f}" for r in R[k]["bins"]), f"| station-mean sd {R[k]['station_mean_sd_cm']:.2f}")
print("raw e_r mean by 1 m bin (cm):",R["raw_e_r_by_1m"])
