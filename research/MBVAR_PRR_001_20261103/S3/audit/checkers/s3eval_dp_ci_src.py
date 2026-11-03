from pathlib import Path
import pandas as pd,numpy as np,json
p=Path('/mnt/d/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103')
c=pd.read_csv(p/'S3/runs/EVAL_001/CROSS_STAGE_PAIRED.csv');rows=[]
for key,t in c[(c.window=='primary')&(c.channel=='Full')].groupby(['route','bias','metric']):
 d=t.sort_values('seed').D_CP_minus_D_P.to_numpy();i=np.random.default_rng(20261103).integers(20,size=(10000,20));q=np.quantile(np.median(d[i],axis=1),[.025,.975]);rows.append(dict(route=key[0],bias=key[1],metric=key[2],median=float(np.median(d)),CI=q.tolist(),decreased_fraction=float(np.mean(d<0))))
print(json.dumps(rows))
