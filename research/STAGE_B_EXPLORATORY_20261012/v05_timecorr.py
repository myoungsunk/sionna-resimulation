"""V05 step 1 (exploratory): range-error temporal correlation from REAL timeline timestamps, drive phase only, within contiguous drive segments (no pairs across corners or probes).
Series: e_full = range_full - d_true, e_mp = range_full - range_los (multipath part). Each is analysed (a) with the global mean removed and (b) with the distance-conditional mean mu(d) removed
(centered variance). Lags are in samples (dt = 0.2 s, step 0.04 m at 0.2 m/s -> lag*0.04 m). IAT = 1 + 2*sum rho(L) up to the first lag with rho < 0.05 (cap 60).
Uncertainty: cluster bootstrap over whole drive-segment series of a route (2.5/97.5 %; few clusters -> wide, partly dependent across cases). Turn-phase samples (in-place rotation, fixed XY) are reported separately and never mixed in."""
import json
from pathlib import Path
import numpy as np,pandas as pd
R=Path('/home/user/sionna-resimulation/results/DRIVE_SIM_20261007/S1/routes');G7=Path(__file__).resolve().parents[1]/'V01B_CLOSURE_20261012/G7/out';OUT=Path(__file__).resolve().parent/'out'
f=pd.read_csv(G7/'01_FEATURES_12.csv');l=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv');d=f.merge(l,on=['case','route','pose_id'])
d['e_full']=d.e_range;d['e_mp']=d.range_m-d.range_los
DT=0.2;MAXLAG=60
def segments(df):
    """contiguous runs of phase=='drive' in timeline order; returns list of index arrays"""
    ph=(df.phase.to_numpy()=='drive');seg=[];start=None
    for i,p in enumerate(ph):
        if p and start is None:start=i
        if (not p) and start is not None:seg.append(np.arange(start,i));start=None
    if start is not None:seg.append(np.arange(start,len(ph)))
    return [s for s in seg if len(s)>=20]
def acf_pooled(series_list):
    num=np.zeros(MAXLAG+1);den=np.zeros(MAXLAG+1);var=0.;n0=0
    for x in series_list:
        n=len(x);var+=np.dot(x,x);n0+=n
        for L in range(1,min(MAXLAG,n-2)+1):
            num[L]+=np.dot(x[:-L],x[L:]);den[L]+=n-L
    v=var/n0;rho=np.array([1.]+[(num[L]/den[L]/v if den[L]>0 else np.nan) for L in range(1,MAXLAG+1)]);return rho
def iat_from(rho):
    cut=next((L for L in range(1,MAXLAG+1) if (not np.isfinite(rho[L])) or rho[L]<0.05),MAXLAG);return float(1+2*rho[1:cut].sum()),int(cut)
def block_boot(series_list,B=400,seed=0):
    """cluster bootstrap over whole drive-segment series (valid when blocks >> correlation length). A moving-block bootstrap with 10 s blocks was tried first and
    REJECTED: blocks shorter than the correlation length bias the IAT low (its CI excluded the point estimate)."""
    rng=np.random.default_rng(seed);vals=[]
    for _ in range(B):
        pick=rng.integers(0,len(series_list),size=len(series_list));vals.append(iat_from(acf_pooled([series_list[j] for j in pick]))[0])
    return [float(np.percentile(vals,2.5)),float(np.percentile(vals,97.5))]
out={'method':__doc__,'cases':{},'routes':{}}
mu_tab=None
for case,g in d.groupby('case'):
    route=case[:2];tl=pd.read_csv(R/f'timeline_{route}_Tnone.csv').merge(g[['pose_id','e_full','e_mp','true_distance_m']],on='pose_id',how='left')
    segs=segments(tl);res={'n_drive_segments':len(segs),'n_drive_samples':int(sum(len(s) for s in segs)),'n_turn_samples':int((tl.phase=='turn').sum()),'drive_missing_error_samples':int(tl.e_full.iloc[np.concatenate(segs)].isna().sum())}
    # distance-conditional mean from this case's drive samples (descriptive; the LORO tables for filters are built elsewhere)
    dd=tl.true_distance_m.to_numpy();edges=np.quantile(dd[np.concatenate(segs)],np.linspace(0,1,9));edges[0]-=1e-9;edges[-1]+=1e-9
    for name in ('e_full','e_mp'):
        e=tl[name].to_numpy(float);mu=np.zeros_like(e);b=np.digitize(dd,edges)-1
        for k in range(8):
            m=(b==k)&np.isfinite(e);mu[m]=e[m].mean() if m.any() else 0
        for cond in ('global','conditional'):
            ser=[(e[s]-(e[s].mean() if False else 0)) for s in segs]
            if cond=='global':gm=np.nanmean(np.concatenate([e[s] for s in segs]));ser=[e[s]-gm for s in segs]
            else:ser=[e[s]-mu[s] for s in segs]
            rho=acf_pooled([x[np.isfinite(x)] if False else x for x in ser]);iat,cut=iat_from(rho)
            res[f'{name}_{cond}']=dict(rho1=float(rho[1]),rho5=float(rho[5]),rho25=float(rho[25]),iat_samples=iat,iat_s=iat*DT,cutoff_lag=cut,ar1_tau_s=float(-DT/np.log(max(rho[1],1e-6))),centered_sd_m=float(np.sqrt(np.mean(np.concatenate(ser)**2))))
    out['cases'][case]=res
# route-level pooled (both anchors/mounts share the route timeline but have different errors -> pool the case-level series per route) with block bootstrap
for route in ('R2','R4','R5'):
    series={'e_full':[],'e_mp':[]}
    for case,g in d[d.route==route].groupby('case'):
        tl=pd.read_csv(R/f'timeline_{route}_Tnone.csv').merge(g[['pose_id','e_full','e_mp']],on='pose_id',how='left')
        for s in segments(tl):
            for k in series:
                x=tl[k].to_numpy(float)[s];series[k].append(x-np.nanmean(x))     # per-segment mean removal (conservative: removes slow trends)
    rr={}
    for k,v in series.items():
        rho=acf_pooled(v);iat,cut=iat_from(rho);rr[k]=dict(iat_samples=iat,iat_s=iat*DT,rho1=float(rho[1]),cutoff_lag=cut,iat_95ci_samples=block_boot(v),n_series=len(v),n_samples=int(sum(len(x) for x in v)))
    out['routes'][route]=rr
OUT.mkdir(exist_ok=True);json.dump(out,open(OUT/'v05_timecorr.json','w'),indent=1)
for route,rr in out['routes'].items():print(route,{k:(round(v['iat_samples'],1),[round(x,1) for x in v['iat_95ci_samples']],round(v['rho1'],2)) for k,v in rr.items()})
print({c:(r['n_drive_segments'],round(r['e_mp_conditional']['iat_samples'],1),round(r['e_mp_global']['iat_samples'],1)) for c,r in out['cases'].items()})
