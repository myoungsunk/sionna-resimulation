"""Within-stratum paired seed bootstrap. Never combines routes or treatment arms."""
import numpy as np
import pandas as pd
strata=['stage','route','bias','channel','arm','accurate']
def aggregate(frame,out):
    reports=[];denoms=[];seed_tables=[]
    nums=[c for c in frame if c.startswith('delta_')]
    for key,all_rows in frame.groupby(strata):
        group=dict(zip(strata,key))
        for population,part in [('attempt',all_rows),('applied',all_rows[all_rows.applied])]:
            res=dict(**group,population=population,events=len(part),seeds=part.seed.nunique(),poses=part.pose_id.nunique())
            for label in ['benefit','harm','tie','mixed','censored']:
                res[label]=int((part.effect==label).sum())
            for col in ['on_only_recovered','off_only_recovered','both_recovered','neither_recovered','on_only_exited','off_only_exited','both_exited','neither_exited','on_only_reentered','off_only_reentered','both_reentered','neither_reentered']:
                res[col]=int(part[col].fillna(False).sum())
            denoms.append(res)
            per_seed=part.groupby('seed')[nums].median()
            if not per_seed.empty:
                seed_tables.append(per_seed.reset_index().assign(**group,population=population))
            for col in nums:
                x=per_seed[col].dropna().to_numpy()
                ci=[np.nan,np.nan]
                if len(x)>1:
                    rng=np.random.default_rng(20261103)
                    sample=x[rng.integers(len(x),size=(10000,len(x)))]
                    ci=np.percentile(np.median(sample,axis=1),[2.5,97.5])
                reports.append(dict(**group,population=population,metric=col,seeds=len(x),median=np.median(x) if len(x) else np.nan,lo=ci[0],hi=ci[1]))
    pd.concat(seed_tables,ignore_index=True).to_csv(out/'PAIRED_PER_SEED.csv',index=False)
    pd.DataFrame(reports).to_csv(out/'PAIRED_SUMMARY.csv',index=False)
    pd.DataFrame(denoms).to_csv(out/'DENOMINATORS.csv',index=False)

