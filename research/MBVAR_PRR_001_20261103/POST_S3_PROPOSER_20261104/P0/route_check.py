"""Separately inspect each route without pooling seeds as independent RF samples."""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import rankdata
d=Path(__file__).resolve().parent
f=pd.read_csv(d/'BEFORE_FEATURES.csv');l=pd.read_csv(d/'LABELS.csv')
rows=[]
for gkey,g in l.merge(f,on='event').groupby(['stage','phase','route','bias','channel','arm']):
 for col in f.columns[2:]:
  # Each seed contributes at most one median per outcome class.
  q=g.groupby(['seed','accurate'])[col].median().dropna().reset_index()
  x=q.loc[~q.accurate,col].to_numpy(); y=q.loc[q.accurate,col].to_numpy()
  concord=np.nan if not len(x)*len(y) else ((x[:,None]>y).mean()+.5*(x[:,None]==y).mean())
  rows.append(dict(zip(['stage','phase','route','bias','channel','arm'],gkey),feature=col,incorrect_seeds=len(x),accurate_seeds=len(y),incorrect_median=np.median(x) if len(x) else np.nan,accurate_median=np.median(y) if len(y) else np.nan,auc_higher_means_inaccurate=concord))
a=pd.DataFrame(rows);a.to_csv(d/'WITHIN_ROUTE_SEED_CONCORDANCE.csv',index=False)
print(a.query("phase=='EVAL' and channel=='Full' and incorrect_seeds>0 and accurate_seeds>0").groupby('feature').auc_higher_means_inaccurate.agg(['min','max']).round(3))

