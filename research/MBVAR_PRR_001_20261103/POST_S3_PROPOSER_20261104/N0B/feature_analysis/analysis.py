"""Exploratory, post hoc association on registered events. Run with Python/pandas."""
from pathlib import Path
import pandas as pd
import numpy as np

out = Path(__file__).resolve().parent
f = pd.read_csv(out.parents[1] / 'P0/BEFORE_FEATURES.csv')
e = pd.read_csv(out.parent / 'runs/RUN_001/EVENT_RESULTS.csv')
features = list(f.columns[2:])
ends = ['delta_head_int_20', 'delta_xy_int_20']
keys = ['stage','route','channel','bias','arm']
ids = keys + ['event','seed','index','accurate','applied','effect'] + ends
x = e[ids].merge(f, on='event', how='left', validate='one_to_one', indicator=True)
assert len(x)==520 and x._merge.eq('both').all() and (x.last_feature_index==x['index']-1).all()
x.drop(columns='_merge').to_csv(out/'EVENT_JOIN.csv',index=False)
a = x[x.applied]
assert len(a)==491
# Each seed contributes one median per variable and stratum, regardless of event count.
rows=[]
for key,g in a.groupby(keys):
    for feat in features:
        for end in ends:
            m=g.groupby('seed')[[feat,end]].median().dropna()
            def rho(v):
                return v[feat].rank().corr(v[end].rank()) if len(v)>=3 and v.nunique().min()>1 else np.nan
            leave=pd.Series([rho(m.drop(s)) for s in m.index],dtype=float)
            rows.append([*key,feat,end,len(m),rho(m),leave.min(),leave.max(),leave.count()])
r=pd.DataFrame(rows,columns=keys+['feature','endpoint','seeds','rho','leave_one_min','leave_one_max','valid_deletions'])
r.to_csv(out/'SEED_ASSOCIATIONS.csv',index=False)
# Coverage of the observed R4 Full benefit interval among R5 Full harm events.
rows=[]
for (stage,bias,arm),g in a[a.channel.eq('Full')].groupby(['stage','bias','arm']):
    for feat in features:
        pos=g[(g.route=='R4') & (g.effect=='benefit')][feat].dropna()
        neg=g[(g.route=='R5') & (g.effect=='harm')].dropna(subset=[feat])
        hit=neg[neg[feat].between(pos.min(),pos.max())]
        rows.append([stage,bias,arm,feat,pos.size,pos.min(),pos.max(),len(neg),len(hit),hit.event.iloc[0] if len(hit) else None])
pd.DataFrame(rows,columns=['stage','bias','arm','feature','benefit_n','min','max','harm_n','inside','example']).to_csv(out/'OVERLAP.csv',index=False)

# Shared descriptive bins for Full, pooled over routes within each treatment specification.
rows=[]
for (stage,bias,arm),g in a[a.channel.eq('Full')].groupby(['stage','bias','arm']):
    for ctx in ['heading_H_abs','priorproxy_heading_var','xy_heading_cov_norm']:
        cut=g[['d0_abs_mean',ctx]].median()
        for key,b in g.groupby([g.d0_abs_mean.gt(cut.iloc[0]),g[ctx].gt(cut.iloc[1]),'route']):
            counts=b.effect.value_counts()
            m=b.groupby('seed')[ends].median().median()
            rows.append([stage,bias,arm,ctx,*cut,*key,len(b),b.seed.nunique(),*(counts.get(s,0) for s in ['benefit','harm','mixed']),*m])
pd.DataFrame(rows,columns=['stage','bias','arm','context','d0_cut','context_cut','high_d0','high_context','route','events','seeds','benefit','harm','mixed',*ends]).to_csv(out/'CONDITIONAL.csv',index=False)
