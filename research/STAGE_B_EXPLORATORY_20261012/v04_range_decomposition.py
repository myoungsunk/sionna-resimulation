"""V04 (exploratory, noise-free observer): decompose the first-arrival range error of the 12 legacy cases.
 e_range (full multipath) = [range_los - d_true]  (detector/LoS-only part)  +  [range_full - range_los]  (multipath first-arrival shift).
Uses 01_FEATURES_12.csv / 02_LABELS_EVAL_ONLY_12.csv (G7 outputs). Evaluation-only labels are used for analysis, not for any online estimator."""
import json
from pathlib import Path
import numpy as np,pandas as pd
G7=Path(__file__).resolve().parents[1]/'V01B_CLOSURE_20261012/G7/out';OUT=Path(__file__).resolve().parent/'out';OUT.mkdir(exist_ok=True)
f=pd.read_csv(G7/'01_FEATURES_12.csv');l=pd.read_csv(G7/'02_LABELS_EVAL_ONLY_12.csv')
d=f.merge(l,on=['case','route','pose_id'],validate='one_to_one')
d['mount']=d.case.str.extract(r'_m(\d+)')[0].astype(int);d['anchor']=d.case.str.extract(r'_(a[AB])_')[0]
d['e_los_part']=d.range_los-d.true_distance_m;d['e_mp_part']=d.range_m-d.range_los;d['tap_switch']=(d.tap!=d.tap_los)
d['dbin']=pd.cut(d.true_distance_m,[0,5,10,np.inf],right=False).astype(str)
def iat(x,maxlag=80):
    x=np.asarray(x,float);x=x[np.isfinite(x)];x=x-x.mean();v=np.dot(x,x)/len(x);ac=[np.dot(x[:-k],x[k:])/(len(x)-k)/v for k in range(1,maxlag)];ac=np.array(ac);cut=np.argmax(ac<0.05) if (ac<0.05).any() else len(ac)
    return float(1+2*ac[:cut].sum()),float(ac[0])
rows=[]
for (case,db),g in d.groupby(['case','dbin']):
    rows.append(dict(case=case,dbin=db,n=len(g),mean_e_range=g.e_range.mean(),sd_e_range=g.e_range.std(),mean_los_part=g.e_los_part.mean(),sd_los_part=g.e_los_part.std(),mean_mp_part=g.e_mp_part.mean(),sd_mp_part=g.e_mp_part.std(),
        p95_abs_mp=np.percentile(np.abs(g.e_mp_part),95),frac_tap_switch=g.tap_switch.mean()))
pd.DataFrame(rows).to_csv(OUT/'v04_by_case_distance.csv',index=False)
tot=dict(n=len(d),mean_e_range=d.e_range.mean(),sd_e_range=d.e_range.std(),mean_los_part=d.e_los_part.mean(),sd_los_part=d.e_los_part.std(),mean_mp_part=d.e_mp_part.mean(),sd_mp_part=d.e_mp_part.std(),frac_tap_switch=float(d.tap_switch.mean()),
         var_share_los_part=float(d.e_los_part.var()/d.e_range.var()),var_share_mp_part=float(d.e_mp_part.var()/d.e_range.var()),corr_los_mp=float(np.corrcoef(d.e_los_part,d.e_mp_part)[0,1]))
tot['by_mount']={str(m):dict(mean_e_range=float(g.e_range.mean()),sd=float(g.e_range.std()),mean_los=float(g.e_los_part.mean()),sd_mp=float(g.e_mp_part.std())) for m,g in d.groupby('mount')}
tot['by_anchor']={str(m):dict(mean_e_range=float(g.e_range.mean()),sd=float(g.e_range.std()),mean_los=float(g.e_los_part.mean()),sd_mp=float(g.e_mp_part.std())) for m,g in d.groupby('anchor')}
tot['by_distance_bin']={str(m):dict(n=int(len(g)),mean_e_range=float(g.e_range.mean()),sd=float(g.e_range.std()),mean_los=float(g.e_los_part.mean()),sd_los=float(g.e_los_part.std()),mean_mp=float(g.e_mp_part.mean()),sd_mp=float(g.e_mp_part.std())) for m,g in d.groupby('dbin')}
# temporal structure of the multipath part along each route order (pose_id order within case)
tot['iat_mp_part']={};tot['iat_los_part']={}
for case,g in d.sort_values(['case','pose_id']).groupby('case'):
    tot['iat_mp_part'][case]=iat(g.e_mp_part);tot['iat_los_part'][case]=iat(g.e_los_part)
# range vs s multipath coupling (full-vs-LoS differences)
tot['corr_range_mp_vs_s_mp']=float(np.corrcoef(d.e_mp_part,d.e_MP)[0,1])
meta=json.load(open('/home/user/sionna-resimulation/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json'))['range_bias']
tot['filter_fixed_range_offset_m']=meta
json.dump(tot,open(OUT/'v04_summary.json','w'),indent=1,default=float)
print(json.dumps({k:v for k,v in tot.items() if k not in('iat_mp_part','iat_los_part','by_distance_bin')},indent=1,default=float)[:3000]);print(json.dumps(tot['by_distance_bin'],indent=1,default=float))
print('IAT mp part (median over cases):',np.median([v[0] for v in tot['iat_mp_part'].values()]),'lag1',np.median([v[1] for v in tot['iat_mp_part'].values()]))
