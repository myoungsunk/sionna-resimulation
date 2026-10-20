"""Compare every Q common metric with same-seed/bias/motion T2; no filter rerun."""
from pathlib import Path
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;AUDIT=HERE.parents[2]/'research/POWERJOINT_AUDIT_RERUN_20261020'
METRICS=['heading_rmse_deg','signed_heading_deg','heading_sigma_rms_deg','heading95','heading_nees','pose_nees','conditional_xy_nees','xy_rmse_m','bias_rmse_dps','bias_mean_dps','bias_final_dps']
def main():
 a=pd.read_csv(HERE/'RESULTS.csv',float_precision='round_trip');a=a[(a.population=='new')&(a.arm=='Q_POWER1')]
 b=pd.read_csv(AUDIT/'T2_NEW_ROUTE_BASELINE/ALL_METRICS.csv',float_precision='round_trip');b=b[(b.arm=='POWER1')&(b.scope=='motion')]
 merged=a.merge(b,on=['case','bias','seed'],suffixes=('_s2','_t2'),validate='one_to_one');assert len(merged)==180
 rows=[]
 for r in merged.to_dict('records'):
  diff={k:float(r[k+'_s2']-r[k+'_t2']) for k in METRICS};maximum=max(abs(v) for v in diff.values())
  assert np.isfinite(list(diff.values())).all() and maximum<=1e-9,('T2_COMMON11_PARITY',r['case'],r['bias'],r['seed'],diff)
  rows.append(dict(case=r['case'],bias=r['bias'],seed=r['seed'],scope='motion_t_ge30',check='T2_SAME_SEED_ALL11_METRICS',status='PASS',max_abs_difference=maximum,historical_gate_available=r['seed']==0,**{k+'_difference':v for k,v in diff.items()}))
 pd.DataFrame(rows).to_csv(HERE/'T2_METRIC_PARITY.csv',index=False);print('S2_T2_180_CELLS_COMMON11_PARITY_PASS',max(r['max_abs_difference'] for r in rows),flush=True)
if __name__=='__main__':main()
