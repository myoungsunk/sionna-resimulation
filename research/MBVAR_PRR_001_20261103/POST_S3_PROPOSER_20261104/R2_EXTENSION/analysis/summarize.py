"""Summarize complete R2 runs with original P0 pre-event features and published R4/R5 bins."""
from pathlib import Path
import json
import sys
import numpy as np
import pandas as pd

here=Path(__file__).resolve().parent
ext=here.parent
parent=ext.parent
def read_json(p): return json.loads(p.read_bytes())
rows=[]
counts=[]
policies=[]
for arg in sys.argv[1:]:
    run=ext/arg
    m=read_json(run/'MANIFEST.json')
    assert m['status']=='COMPLETE'
    counts.append(pd.read_csv(run/'POLICY_COUNTS.csv'))
    policies.append(pd.read_csv(run/'NATURAL_SUMMARY.csv'))
    if not m['pairs']:
        continue
    events=pd.read_csv(run/'EVENT_RESULTS.csv')
    assert len(events)==m['pairs'] and events.event.is_unique
    for (stage,bias,ch,seed,arm),g in events.groupby(['stage','bias','channel','seed','arm']):
        name=f'R2_{bias}_{ch}_{seed}'
        pkpath=(ext/('inputs' if ch=='Full' else 'native_inputs'))/f'R2_aB_m0_{bias}_{ch}.npz'
        with np.load(pkpath) as pk,np.load(run/'natural'/f'{name}_A.npz') as base,np.load(run/'natural'/f'{name}_B.npz') as discount,np.load(run/'natural'/f'{stage}_{name}_{arm}.npz') as trace:
            d0,t,P,H,episode,nis,info=(trace[n] for n in ['d0','t','P','H','episode_first','nis','marginal_lambda'])
            A,B,D=base['x'],discount['x'],pk['D']
            for item in g.to_dict('records'):
                k=item['index'];j=k-1;win=(t<t[k])&(t>=t[k]-5.-1e-9)
                assert j>=0 and np.array_equal(trace['pose_id'],pk['pose_id']) and trace['pose_id'][k]==item['pose_id']
                item.update(last_feature_index=j,d0_mean=d0[win].mean(),d0_abs_mean=abs(d0[win]).mean(),d0_positive_share=(d0[win]>0).mean(),ds_abs_mean=D[win].mean(),episode_age_s=t[k]-episode[j],heading_H_abs=abs(H[j,1,2]),info_lambda=info[j],priorproxy_heading_var=P[j,2,2],xy_heading_cov_norm=np.linalg.norm(P[j,:2,2]),nis_mean=nis[win].mean(),ab_xy=np.linalg.norm(A[j,:2]-B[j,:2]),ab_head_deg=abs(np.degrees(np.angle(np.exp(1j*(A[j,2]-B[j,2]))))))
                rows.append(item)
policy=pd.concat(policies,ignore_index=True)
keys=['stage','channel','bias','seed','window']
metrics=['heading_rmse_deg','xy_rmse_m']
baseline=policy.query("arm=='A'")[keys+metrics]
r=policy.merge(baseline,on=keys,validate='many_to_one',suffixes=('','_A'))
for col in metrics:r[col+'_ratio']=r[col]/r[col+'_A']
gkeys=['stage','channel','bias','arm','window']
table=r.groupby(gkeys)[[v+'_ratio' for v in metrics]].quantile([.5,.9]).rename_axis(index=gkeys+['quantile']).reset_index()
table.to_csv(here/'POLICY_RATIOS.csv',index=False)
pd.concat(counts).groupby(['stage','channel','bias'])[['attempts','applied']].sum().to_csv(here/'COUNTS.csv')
df=pd.DataFrame(rows)
if not df.empty:
    assert df.event.is_unique
    df.to_csv(here/'FEATURE_EFFECTS.csv',index=False)
    df.groupby(['stage','channel','accurate','applied','effect']).size().rename('n').to_csv(here/'EFFECT_COUNTS.csv')
    source=pd.read_csv(parent/'N0B/feature_analysis/CONDITIONAL.csv')
    descriptors=['stage','bias','arm','context','d0_cut','context_cut']
    cuts=source[descriptors].drop_duplicates()
    joined=df[df.channel.eq('Full') & df.applied].merge(cuts,on=['stage','bias','arm'])
    if len(joined):
        joined['high_d0']=joined.d0_abs_mean>joined.d0_cut
        joined['high_context']=[r[c]>r['context_cut'] for (_,r),c in zip(joined.iterrows(),joined.context)]
        joined.groupby(descriptors+['high_d0','high_context','effect']).agg(n=('event','size'),seeds=('seed','nunique')).to_csv(here/'R2_IN_PUBLISHED_BINS.csv')

# Repeat the published seed-median rank calculation within each R2 stratum.
def correlation(v):
    return v.iloc[:,0].rank().corr(v.iloc[:,1].rank()) if len(v)>=3 and v.nunique().min()>1 else np.nan
if not df.empty:
    variables=df.columns[df.columns.get_loc('last_feature_index')+1:]
    associations=[]
    keys=['stage','channel','bias','arm']
    for group,part in df[df.applied].groupby(keys):
        for variable in variables:
            for endpoint in ['delta_head_int_20','delta_xy_int_20']:
                vals=part.groupby('seed')[[variable,endpoint]].median().dropna()
                deletions=pd.Series([correlation(vals.drop(s)) for s in vals.index],dtype=float)
                associations.append(dict(zip(keys,group),feature=variable,endpoint=endpoint,seeds=len(vals),rho=correlation(vals),leave_one_min=deletions.min(),leave_one_max=deletions.max()))
    pd.DataFrame(associations).to_csv(here/'SEED_ASSOCIATIONS.csv',index=False)
