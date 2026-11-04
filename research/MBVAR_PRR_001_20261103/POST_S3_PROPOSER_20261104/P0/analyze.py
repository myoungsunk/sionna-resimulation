from pathlib import Path
import json,hashlib,itertools
import numpy as np
import pandas as pd
from scipy.stats import rankdata
out=Path(__file__).resolve().parent
pkg=Path('D:/codex/MBVAR_PRR_001_20261103/research/MBVAR_PRR_001_20261103')
cache=out.parent/'S1_INPUTS'
features=[];labels=[];benefits=[]; hashes={}
def digest(p):
 h=hashlib.sha256(p.read_bytes()).hexdigest();hashes[str(p)]=h;return h
def angle(a):return np.angle(np.exp(1j*a))
def readtrace(r,idx,name):
 p=r/name
 assert digest(p)==idx[name]['sha256']
 return np.load(p)
def auc(x,y):
 y=np.asarray(y,bool); n=y.sum();m=len(y)-n
 if not n or not m:return np.nan
 return (rankdata(x)[y].sum()-n*(n+1)/2)/(n*m)
keys=['route','bias','channel','seed']
for st,phase in itertools.product(['S2','S3'],['DEV','EVAL']):
 r=pkg/st/'runs'/(phase+'_001'); repaired=st=='S2' and phase=='DEV'
 rr=pkg/st/'runs/DEV_REPAIR_001' if repaired else r
 ep=rr/('EVENT_ENDPOINTS_CORRECTED.csv' if repaired else 'EVENT_ENDPOINTS.csv')
 digest(ep);idxfile=r/'TRACE_INDEX.json';digest(idxfile)
 idx={v['file']:v for v in json.loads(idxfile.read_text())}
 events=pd.read_csv(ep).query("kind=='P'")
 for (route,bias,ch,seed),df in events.groupby(keys):
  key=f'{route}_aB_m0_{bias}_{ch}';suffix='_main' if st=='S3' else ''
  with readtrace(r,idx,f'{key}_{seed}_A{suffix}.npz') as a,readtrace(r,idx,f'{key}_{seed}_B{suffix}.npz') as b:
   ax=a['x'];bx=b['x']
  f=cache/'algorithm_input'/(key+'.npz');digest(f)
  with np.load(f) as pk: D=pk['D'];ids=pk['pose_id']
  for arm,g in df.groupby('arm'):
   with readtrace(r,idx,f'{key}_{seed}_{arm}{suffix}.npz') as tr:
    h=tr['H'];P=tr['P'];d0=tr['d0'];t=tr['t'];lamb=tr['marginal_lambda'];w=tr['episode_first'];info=tr['nis']
    assert np.array_equal(ids,tr['pose_id'])
    for row in g.itertuples():
     k=row.event_index;j=k-1;assert j>=0
     win=(t<t[k])&(t>=t[k]-5.-1e-9)
     # A committed state at j is causal even following a prior intervention.
     keyid=f'{st}.{phase}.{route}.{bias}.{ch}.{seed}.{arm}.{k}'
     disp=getattr(row,'disposition','APPLIED');applied=disp in ('ACCEPT','APPLIED')
     assert row.already_accurate==((row.start_heading_deg<=1) and (row.start_xy_m<=.1))
     labels.append(dict(event=keyid,stage=st,phase=phase,route=route,bias=bias,channel=ch,seed=seed,arm=arm,index=k,disposition=disp,applied=applied,accurate=row.already_accurate,head_deg=row.start_heading_deg,xy_m=row.start_xy_m,benefit=np.nan))
     features.append(dict(event=keyid,last_feature_index=j,d0_mean=d0[win].mean(),d0_abs_mean=np.abs(d0[win]).mean(),d0_positive_share=(d0[win]>0).mean(),ds_abs_mean=D[win].mean(),episode_age_s=t[k]-w[j] if np.isfinite(w[j]) else np.nan,heading_H_abs=abs(h[j,1,2]),info_lambda=lamb[j],priorproxy_heading_var=P[j,2,2],xy_heading_cov_norm=np.linalg.norm(P[j,:2,2]),nis_mean=info[win].mean(),ab_xy=np.linalg.norm(ax[j,:2]-bx[j,:2]),ab_head_deg=abs(np.degrees(angle(ax[j,2]-bx[j,2])))))
 if phase=='DEV':
  sp=rr/('SNAPSHOT_ENDPOINTS_CORRECTED.csv' if repaired else 'SNAPSHOT_ENDPOINTS.csv');digest(sp)
  m=pd.read_csv(sp)
  for group,sub in m.groupby(keys+['start_index']):
   route,bias,ch,seed,k=group
   assert len(sub)==4 and sub.already_accurate.nunique()==1
   truth_path=cache/'evaluator_truth'/f'{route}_aB_m0_{bias}.npz';digest(truth_path)
   with np.load(truth_path) as f:gt=f['truth']
   for on,off in [('C_P' if st=='S2' else 'C_CP','A'),('D_P' if st=='S2' else 'D_CP','B')]:
    x=sub.set_index('arm');rec=dict(stage=st,route=route,bias=bias,channel=ch,seed=seed,start_index=k,on=on,off=off,accurate=x.loc[off,'already_accurate'])
    for h in [10,20]:
     for field in ['heading_integral','xy_integral']:
      col=f'{field}_{h}s';rec['delta_'+col]=x.loc[on,col]-x.loc[off,col] if not x.loc[[on,off],f'window_{h}s_censored'].any() else np.nan
    rec['delta_recovery_s']=x.loc[on,'recovery_time_s']-x.loc[off,'recovery_time_s'] if not x.loc[[on,off],'censored'].any() else np.nan
    for arm in [on,off]:
     v=x.loc[arm];key=f'{route}_aB_m0_{bias}_{ch}'
     name=f'{key}_snapshot{int(v.snapshot)}_{arm}.npz' if st=='S2' else f'{key}_{seed}_{arm}_{v.variant}.npz'
     path=rr/name if (rr/name).exists() else r/name
     digest(path)
     with np.load(path) as f:
      y=f['x'];true=gt[k:k+len(y)]
      he=np.abs(np.degrees(angle(y[:,2]-true[:,2])));xy=np.linalg.norm(y[:,:2]-true[:,:2],axis=1)
      for field,val in [('heading_p95',np.quantile(he,.95)),('xy_p95',np.quantile(xy,.95))]:rec['delta_'+field]=rec.get('delta_'+field,0)+(1 if arm==on else -1)*val
    benefits.append(rec)
L=pd.DataFrame(labels);F=pd.DataFrame(features);B=pd.DataFrame(benefits)
assert L.event.is_unique and F.event.is_unique
L.to_csv(out/'LABELS.csv',index=False);F.to_csv(out/'BEFORE_FEATURES.csv',index=False);B.to_csv(out/'BENEFIT.csv',index=False)
grid=[]
for st,ph,rt,bi,ch in itertools.product(['S2','S3'],['DEV','EVAL'],['R4','R5'],['B0','L2'],['Full','Native_LoS']):
 for se,arm in itertools.product(range(10) if ph=='DEV' else range(10,30),(['C_P','D_P'] if st=='S2' else ['C_CP','D_CP'])):
  grid.append((st,ph,rt,bi,ch,se,arm))
cols=['stage','phase']+keys+['arm']
tab=pd.DataFrame(grid,columns=cols).merge(L.assign(applied_accurate=L.applied&L.accurate).groupby(cols).agg(events=('event','size'),applied=('applied','sum'),accurate=('accurate','sum'),applied_accurate=('applied_accurate','sum')).reset_index(),how='left').fillna(0)
tab.to_csv(out/'CROSSTAB.csv',index=False)
# Descriptive concordance only. Do not optimize signs or cutoffs, or pool route identities.
rows=[]
for c,g in L.merge(F,on='event').groupby(['stage','phase','route','bias','channel','arm','seed']):
 for field in F.columns[2:]:
  sub=g[[field,'accurate']].dropna()
  rows.append(dict(zip(['stage','phase','route','bias','channel','arm','seed'],c),feature=field,n=len(sub),inaccurate=(~sub.accurate).sum(),auc_higher_means_inaccurate=auc(sub[field],~sub.accurate)))
a=pd.DataFrame(rows);a.to_csv(out/'SEED_STRATA.csv',index=False)
a.groupby(['stage','phase','route','feature']).auc_higher_means_inaccurate.agg(['count','median','min','max']).to_csv(out/'ROUTE_SEED_SUMMARY.csv')
print(L[L.phase=='EVAL'].groupby(['stage','route','channel']).agg(n=('event','size'),accurate=('accurate','sum'),applied=('applied','sum')))
print(B.groupby('stage').agg(n=('on','size'),both_better=('delta_heading_integral_20s',lambda s:s.lt(-1e-9).sum())))
print(B[(B.delta_heading_integral_20s.abs()>1e-8)][['stage','route','bias','start_index','on','delta_heading_integral_20s','delta_xy_integral_20s']].to_string(index=False))
(out/'SOURCE_DIGESTS.json').write_text(json.dumps(hashes,indent=2))
