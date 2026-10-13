"""R2-4c: score the frozen chosen model (E1_on_B) on the P4 LoS-only channel (R1 scored only B there). Uses the saved R1 P4_HELDOUT_LOS_PAIRED.csv; same site-cluster bootstrap (4000, seed 20261012) as p4_blind_range_eval.py.
Interpretation: E1 is trained on Full-RF residuals (multipath-induced bias); on a LoS-only channel it is NOT expected to help -- reported so Full-RF and LoS-detector results are not conflated.
usage: p4_score_los_chosen.py R1_P4_DIR OUT_JSON"""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
R=Path(sys.argv[1]);res={}
for ch,fn in (('los','P4_HELDOUT_LOS_PAIRED.csv'),('full','P4_HELDOUT_FULLRF_PAIRED.csv')):
    d=pd.read_csv(R/fn)
    for exp,q in d.groupby('experiment'):
        qd=q[q.detected];g=qd.groupby('site_id');sB=(qd.e_B**2).groupby(qd.site_id).mean().to_numpy();sC=(qd.e_chosen**2).groupby(qd.site_id).mean().to_numpy()
        rng=np.random.default_rng(20261012);rel=[]
        for _ in range(4000):
            p=rng.integers(0,len(sB),len(sB));rel.append(np.sqrt(sC[p].mean())/np.sqrt(sB[p].mean())-1)
        res[f'{exp}/{ch}']=dict(n=int(len(qd)),detection_rate=float(q.detected.mean()),rmse_B=float(np.sqrt(sB.mean())),rmse_chosen=float(np.sqrt(sC.mean())),mean_e_B=float(qd.e_B.mean()),mean_e_chosen=float(qd.e_chosen.mean()),
            rel_change_site_rmse=float(np.sqrt(sC.mean())/np.sqrt(sB.mean())-1),ci95=[float(np.percentile(rel,2.5)),float(np.percentile(rel,97.5))],n_site_clusters=int(len(sB)))
Path(sys.argv[2]).write_text(json.dumps(res,indent=1));print(json.dumps(res,indent=1))
