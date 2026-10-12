"""P1: existing fixed offset (B) vs training-LoS constant (C) / affine (C2), leave-one-route-out, FULL-RF held-out measurements.
Adds site-weighted metrics, per route/mount/anchor breakdown and a paired site-cluster bootstrap CI (cluster = physical site route|x|y, shared by the 12 conditions).
Only train-fold data ever enters a fit. usage: p1_loro_comparison.py OUT_DIR"""
import json,sys
from pathlib import Path
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];G7=ROOT/'research/V01B_CLOSURE_20261012/G7/out';B_OLD=-0.5315983906250129
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
f=pd.read_csv(G7/'01_FEATURES_12.csv',usecols=['case','route','pose_id','range_m']);l=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv',usecols=['case','route','pose_id','range_los','true_distance_m','true_x','true_y'])
d=f.merge(l,on=['case','route','pose_id'],validate='one_to_one');d['mount']=d.case.str.extract(r'_m(\d+)')[0].astype(int);d['anchor']=d.case.str.extract(r'_(a[AB])_')[0]
d['site']=[f'{r}|{x:.4f}|{y:.4f}' for r,x,y in zip(d.route,d.true_x,d.true_y)]
preds={'A_raw':d.range_m.copy(),'B_old':d.range_m-B_OLD}
c_arr=pd.Series(np.nan,index=d.index);const=pd.Series(np.nan,index=d.index);aff=pd.Series(np.nan,index=d.index)
fits={}
for r in ('R2','R4','R5'):
    tr=d[d.route!=r];te=d.route==r
    c=float((tr.range_los-tr.true_distance_m).mean());b,a=np.polyfit(tr.true_distance_m,tr.range_los,1);fits[r]=dict(const=c,intercept=float(a),slope=float(b))
    const[te]=d.range_m[te]-c;aff[te]=(d.range_m[te]-a)/b
preds['C_const']=const;preds['C2_affine']=aff
err={k:(v-d.true_distance_m) for k,v in preds.items()}
def summ(e,sub):
    g=(e[sub.index]**2).groupby([sub.case,sub.site]).mean();return dict(n=len(sub),rmse_pose=float(np.sqrt((e[sub.index]**2).mean())),rmse_site=float(np.sqrt(g.mean())),mean=float(e[sub.index].mean()),sd=float(e[sub.index].std()),abs_p95=float(np.percentile(np.abs(e[sub.index]),95)))
rows=[]
for scope,keys in [('all',[None])]+[(k,sorted(d[k].unique())) for k in ('route','mount','anchor')]:
    for kv in keys:
        sub=d if kv is None else d[d[scope]==kv]
        for arm,e in err.items():rows.append(dict(scope=scope if kv is None else f'{scope}={kv}',arm=arm,**summ(e,sub)))
pd.DataFrame(rows).to_csv(out/'P1_LORO_COMPARISON.csv',index=False)
# paired site-cluster bootstrap: difference of site-weighted MSE (arm - B) -> relative RMSE change
rng=np.random.default_rng(20261012);sites=d.site.unique();idx={s:g.index.to_numpy() for s,g in d.groupby('site')}
se={k:(e**2) for k,e in err.items()};cs={k:np.array([se[k][idx[s]].sum() for s in sites]) for k in se};cn=np.array([len(idx[s]) for s in sites])
# case-site weighting is approximated by pose counts inside a site cluster (each site has the same conditions); the pooled-MSE ratio is bootstrapped over site clusters
boot={k:[] for k in ('C_const','C2_affine')}
for _ in range(2000):
    pick=rng.integers(0,len(sites),len(sites));den=cn[pick].sum();base=cs['B_old'][pick].sum()/den
    for k in boot:boot[k].append(np.sqrt(cs[k][pick].sum()/den)/np.sqrt(base)-1)
summary={'fits':fits,'plan_reference_pose_pooled':{'B_old':0.143847,'C_const':0.145249,'C2_affine':0.144594},
 'recomputed_pose_pooled':{k:float(np.sqrt((e**2).mean())) for k,e in err.items()},
 'relative_change_vs_B_site_cluster_bootstrap':{k:dict(point=float(np.sqrt((err[k]**2).mean())/np.sqrt((err['B_old']**2).mean())-1),ci95=[float(np.percentile(v,2.5)),float(np.percentile(v,97.5))]) for k,v in boot.items()},
 'n_site_clusters':int(len(sites)),'limitations':['3 routes, 1 scene: route hold-out is exploratory, not independent geometry','pose counts weight clusters','1 XY (route start) shared by R2 and R4 is still in the exploratory LORO']}
decision='KEEP_B_OLD_AND_GO_TO_P2' if all(v['ci95'][0]>0 or v['point']>=0 for v in summary['relative_change_vs_B_site_cluster_bootstrap'].values()) else 'NEW_CALIBRATION_HAS_GAIN_CHECK'
summary['decision']=decision;(out/'P1_LORO_SUMMARY.json').write_text(json.dumps(summary,indent=1))
(out/'P1_DECISION.md').write_text(f"# P1 decision\n\nresult: **{decision}**\n\n```json\n{json.dumps(summary,indent=1)}\n```\n")
print(json.dumps(summary,indent=1));print(pd.DataFrame(rows)[lambda x:x.scope=='all'].round(5).to_string())
