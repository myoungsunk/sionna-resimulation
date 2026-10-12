"""03_DISTANCE_BIAS_VAR for 12 cases using the join/summary code of frozen features.py lines 25-29, then regress the 7 published cases."""
import json,numpy as np,pandas as pd
from pathlib import Path
G=Path(__file__).resolve().parent/'g7';out=G/'out'
features=pd.read_csv(out/'01_FEATURES_12.csv');labels=pd.read_csv(out/'02_LABELS_EVAL_ONLY_12.csv')
joined=features.merge(labels,on=['case','route','pose_id'],validate='one_to_one');joined['distance_bin']=pd.cut(joined.true_distance_m,[0,5,10,np.inf],right=False).astype(str);summary=[]
for key,g in joined.groupby(['case','distance_bin'],observed=True):
    r={'case':key[0],'distance_bin':key[1],'n':len(g),'descriptive_only':len(g)<20}
    for col in ['e_s','e_MP','e_range']:
        v=g[col].to_numpy();r.update({col+'_mean':float(np.mean(v)),col+'_variance_ddof0':float(np.var(v)),col+'_rms':float(np.sqrt(np.mean(v*v)))})
    summary.append(r)
new=pd.DataFrame(summary);new.to_csv(out/'03_DISTANCE_BIAS_VAR_12.csv',index=False)
pub=pd.read_csv(G/'pub/03_DISTANCE_BIAS_VAR.csv') if (G/'pub/03_DISTANCE_BIAS_VAR.csv').exists() else pd.read_csv('/home/user/sionna-resimulation/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/OUTPUT/03_DISTANCE_BIAS_VAR.csv')
n7=new[new.case.isin(set(pub.case))].sort_values(['case','distance_bin']).reset_index(drop=True);pub=pub.sort_values(['case','distance_bin']).reset_index(drop=True)
assert list(n7.columns)==list(pub.columns) and (n7[['case','distance_bin','n']].values==pub[['case','distance_bin','n']].values).all()
w=0.
for c in pub.columns:
    if pub[c].dtype.kind=='f':w=max(w,float(np.max(np.abs(n7[c]-pub[c]))/max(np.max(np.abs(pub[c])),1.)))
res=dict(rows=len(pub),worst_rel_to_scale=w,pass_1e12=bool(w<=1e-12));json.dump(res,open(out/'REGRESSION_03.json','w'),indent=1);print(res,'new rows',len(new))
print(new[~new.case.isin(set(pub.case))].groupby('case')[['n','e_s_rms','e_MP_rms','e_range_rms']].agg({'n':'sum','e_s_rms':'mean','e_MP_rms':'mean','e_range_rms':'mean'}).round(4).to_string())
print(pub.groupby('case')[['e_s_rms','e_MP_rms','e_range_rms']].mean().round(4).to_string())
