"""Hardware-sensitivity yardstick for the sensor-v2 replay.
A = published 09_V2_main.csv (other HW, py3.11)  vs  this machine default BLAS (7 published cases)
B = this machine default BLAS  vs  this machine OPENBLAS_CORETYPE=HASWELL (same code, same inputs, only the BLAS kernel changes)
Metrics are paired by (case,drift,seed,arm)."""
import json,numpy as np,pandas as pd
from pathlib import Path
G=Path(__file__).resolve().parent/'g7';k=['case','drift','seed','arm']
pub=pd.read_csv('/home/user/sionna-resimulation/results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/OUTPUT/09_V2_main.csv')
me=pd.read_csv(G/'out/09_V2_main_12.csv');me=me[me.case.isin(set(pub.case))]
hw=pd.read_csv(G/'job_hw/OUTPUT/09_V2_main.csv')
def prep(d):return d.sort_values(k).reset_index(drop=True)
pub,me,hw=prep(pub),prep(me),prep(hw)
for x in (me,hw):assert (x[k].values==pub[k].values).all()
M=['heading_rmse_deg','pos_rmse_m','nees_mean']
def cmp(a,b):
    out={}
    for arm in 'ABCD':
        ma=a.arm==arm;r={}
        d=np.zeros(ma.sum(),bool)
        for c in M:
            x,y=a.loc[ma,c].to_numpy(float),b.loc[ma,c].to_numpy(float);dd=np.abs(x-y);d|=dd>1e-9
            sd=float(np.std(y));r[c]=dict(mean_a=float(np.mean(x)),mean_b=float(np.mean(y)),mean_diff_over_sd=float((np.mean(x)-np.mean(y))/sd) if sd>0 else 0.,median_abs_rel=float(np.median(dd/np.maximum(np.abs(y),1e-12))),p95_abs_rel=float(np.percentile(dd/np.maximum(np.abs(y),1e-12),95)),max_abs=float(dd.max()))
        r['runs_differing_gt_1e-9']=int(d.sum());r['runs']=int(ma.sum());out[arm]=r
    return out
res=dict(A_published_vs_this_machine=cmp(me,pub),B_this_machine_default_vs_HASWELL=cmp(me,hw),C_published_vs_HASWELL=cmp(hw,pub))
json.dump(res,open(G/'out/SIM_HW_SENSITIVITY.json','w'),indent=1)
for name,r in res.items():
    print(name)
    for arm in 'ABCD':print(' ',arm,'differ',r[arm]['runs_differing_gt_1e-9'],'/',r[arm]['runs'],'| pos_rmse mean diff/sd %.3f'%r[arm]['pos_rmse_m']['mean_diff_over_sd'],'| heading median rel %.1e p95 %.1e'%(r[arm]['heading_rmse_deg']['median_abs_rel'],r[arm]['heading_rmse_deg']['p95_abs_rel']),'| nees mean diff/sd %.3f'%r[arm]['nees_mean']['mean_diff_over_sd'])
