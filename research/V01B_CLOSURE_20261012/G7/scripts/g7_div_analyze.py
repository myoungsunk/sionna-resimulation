"""G7 309/4200 attribution (L1/L2/L3). Equivalence margins fixed BEFORE this analysis was run (but after aggregate means were seen to differ by <1e-4 SD):
  log heading RMSE and log position RMSE: paired mean difference within +-1 %; log mean-NEES per run: within +-2 %; pose95 'coverage' (pose_coverage) paired mean within +-1 percentage point;
  per-run |relative difference| p99 <= 5 % (outlier guard); max over runs reported, no pass/fail on the max.
Inputs (scratchpad): div_A (default BLAS), div_B (OPENBLAS_CORETYPE=HASWELL), div_C (default BLAS, +-1 ulp random noise on s and range_m), div_D (second default run), published 09_V2_main.csv."""
import sys,json,glob
from pathlib import Path
import numpy as np,pandas as pd
from scipy import stats
S=Path('/tmp/claude-0/-home-user-sionna-resimulation/1215cd75-99f4-55ac-b01a-7c56293627ba/scratchpad');OUT=Path(__file__).resolve().parents[1]/'out_div';OUT.mkdir(exist_ok=True)
K=['case','drift','seed','arm'];M=['heading_rmse_deg','pos_rmse_m','nees_mean']
pub=pd.read_csv('/home/user/sionna-resimulation/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/OUTPUT/09_V2_main.csv')
runs={'pub':pub}
for n in 'ABCD':
    p=S/f'div_{n}.csv'
    if p.exists():runs[n]=pd.read_csv(p)
runs={k:v.sort_values(K).reset_index(drop=True) for k,v in runs.items()}
def differing(a,b,tol=1e-9):
    d=np.zeros(len(a),bool)
    for c in M:d|=np.nan_to_num(np.abs(a[c].to_numpy(float)-b[c].to_numpy(float)))>tol
    return d
res={'pair_counts':{}}
for x,y in [('A','pub'),('B','pub'),('C','pub'),('A','B'),('A','C'),('A','D'),('B','C')]:
    if x in runs and y in runs:
        d=differing(runs[x],runs[y]);a=runs[x]
        res['pair_counts'][f'{x}_vs_{y}']=dict(total=int(d.sum()),by_arm={s:int(d[a.arm.to_numpy()==s].sum()) for s in 'ABCD'})
# L3 equivalence + tails
def tost(x,margin):    # paired mean diff of log metric within +-margin; TOST p = max of two one-sided
    n=len(x);m=x.mean();se=x.std(ddof=1)/np.sqrt(n);p1=1-stats.t.cdf((m+margin)/se,n-1);p2=stats.t.cdf((m-margin)/se,n-1);return float(m),float(max(p1,p2))
res['L3']={}
for x,y in [('A','pub'),('B','pub'),('C','pub'),('A','B'),('A','C')]:
    if x not in runs or y not in runs:continue
    a,b=runs[x],runs[y];r={}
    for arm in 'ABCD':
        m=(a.arm==arm).to_numpy();q={}
        for c,mg in (('heading_rmse_deg',0.01),('pos_rmse_m',0.01),('nees_mean',0.02)):
            lx=np.log(a.loc[m,c].to_numpy(float));ly=np.log(b.loc[m,c].to_numpy(float));ok=np.isfinite(lx)&np.isfinite(ly);dd=(lx-ly)[ok]
            mean,p=tost(dd,mg);rel=np.abs(np.expm1(dd))
            q[c]=dict(mean_log_diff=mean,tost_p=p,equivalent=bool(p<0.05),p99_abs_rel=float(np.percentile(rel,99)),max_abs_rel=float(rel.max()),p99_ok=bool(np.percentile(rel,99)<=0.05))
        cv=(a.loc[m,'pose_coverage'].to_numpy(float)-b.loc[m,'pose_coverage'].to_numpy(float));mean,p=tost(cv[np.isfinite(cv)],0.01);q['pose_coverage']=dict(mean_diff=mean,tost_p=p,equivalent=bool(p<0.05))
        q['nees_tail']={n:dict(p95=float(np.percentile(runs[n].loc[(runs[n].arm==arm).to_numpy(),'nees_mean'],95)),p99=float(np.percentile(runs[n].loc[(runs[n].arm==arm).to_numpy(),'nees_mean'],99)),max=float(runs[n].loc[(runs[n].arm==arm).to_numpy(),'nees_mean'].max())) for n in (x,y)}
        r[arm]=q
    res['L3'][f'{x}_vs_{y}']=r
json.dump(res,open(OUT/'g7_div_summary.json','w'),indent=1)
print(json.dumps(res['pair_counts'],indent=1))
# trace-level classification of A vs B differing runs
if 'A' in runs and 'B' in runs:
    d=differing(runs['A'],runs['B']);rows=runs['A'][d];cat={'status_flip_at_first_divergence':0,'numeric_drift_then_flip':0,'no_flip_continuous':0};det=[]
    for _,r in rows.iterrows():
        fn=f"{r.case}_d{int(r.drift)}_s{int(r.seed)}_{r.arm}.npz";a=np.load(S/'div_A'/fn);b=np.load(S/'div_B'/fn)
        ea,eb=a['est'],b['est'];ok=a['completed']&b['completed'];dif=np.nanmax(np.abs(ea-eb),axis=1);dif[~ok]=0
        idx=np.where(dif>1e-10)[0]
        if len(idx)==0:continue
        k0=int(idx[0]);flips=np.zeros(len(dif),bool)
        for key in ('odom_status','range_status','s_status'):flips|=(a[key]!=b[key])
        fl=np.where(flips)[0]
        if len(fl)==0:c='no_flip_continuous'
        elif fl[0]<=k0:c='status_flip_at_first_divergence'
        else:c='numeric_drift_then_flip'
        cat[c]+=1;det.append(dict(run=fn,first_divergence_step=k0,first_flip_step=int(fl[0]) if len(fl) else None,category=c,final_state_diff=float(dif[ok].max())))
    res['A_vs_B_classification']=cat;json.dump(dict(summary=res,detail=det),open(OUT/'g7_div_detail.json','w'),indent=1);print(cat)
    print('first divergence step quantiles',np.percentile([x['first_divergence_step'] for x in det],[0,25,50,75,100]).tolist() if det else None)
