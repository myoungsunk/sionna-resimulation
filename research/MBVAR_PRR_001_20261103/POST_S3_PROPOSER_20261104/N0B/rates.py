"""Compact descriptive tables preserving original event denominators and paired censoring."""
import numpy as np
import pandas as pd

def tabulate(frame,output):
    rows=[]
    keys=['stage','route','bias','channel','arm','accurate']
    for key,cell in frame.groupby(keys):
        for population,part in [('attempt',cell),('applied',cell[cell.applied])]:
            complete=part[part.on_full_20 & part.off_full_20]
            row=dict(zip(keys,key),population=population,registered=len(cell),events=len(part),complete20=len(complete),censored20=len(part)-len(complete),seeds=part.seed.nunique())
            for arm in ['on','off']:
                exited=complete[arm+'_exit_s'].notna()
                recovered=complete[arm+'_recovery_s'].notna()
                reentered=complete[arm+'_reentry_s'].notna()
                row[arm+'_exit_n']=int(exited.sum()) if key[-1] else None
                row[arm+'_exit_rate']=exited.mean() if key[-1] else np.nan
                row[arm+'_reentry_n']=int(reentered.sum()) if key[-1] else None
                row[arm+'_reentry_among_exits']=reentered.sum()/exited.sum() if key[-1] and exited.any() else np.nan
                row[arm+'_rec_n']=int(recovered.sum()) if not key[-1] else None
                row[arm+'_rec_rate']=recovered.mean() if not key[-1] else np.nan
            rows.append(row)
    pd.DataFrame(rows).to_csv(output/'EVENT_RATES.csv',index=False)
