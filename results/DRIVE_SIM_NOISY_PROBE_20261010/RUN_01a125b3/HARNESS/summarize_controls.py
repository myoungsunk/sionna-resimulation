from pathlib import Path
import json,time
import numpy as np,pandas as pd
J=Path('/job');files=list(J.glob('10_PAIRED_FILTER_RESULTS_*.csv'));files=[x for x in files if 'PARTIAL' not in x.name];df=pd.concat([pd.read_csv(x) for x in files],ignore_index=True)
keys=['case','station','drift','seed','snr','arm'];assert not df.duplicated(keys).any();df.to_csv(J/'10_PAIRED_FILTER_RESULTS.csv',index=False)
ok=df[df.status=='COMPLETED'].copy();seedrows=[]
for key,g in ok.groupby(['case','drift','snr','arm','seed']):
 row=dict(zip(['case','drift','snr','arm','seed'],key));row.update(stations=len(g),heading_endpoint_rmse_deg=float(np.sqrt(np.mean(g.heading_abs_deg**2))),position_endpoint_rmse_m=float(np.sqrt(np.mean(g.pos_error_m**2))),nees_pose_df3=float(g.nees_pose_df3.mean()),pose_coverage95=float(g.pose_coverage95.mean()),heading_coverage95=float(g.heading_coverage95.mean()),s_reject_rate=float(g.s_reject_rate.mean()),s_nis_pre_gate=float(g.s_nis_pre_gate.mean()),s_nis_accepted=float(g.s_nis_accepted.mean()));seedrows.append(row)
sd=pd.DataFrame(seedrows);sd.to_csv(J/'11_SEED_UNIT_METRICS.csv',index=False);group=[]
for key,g in sd.groupby(['case','drift','snr','arm']):
 row=dict(zip(['case','drift','snr','arm'],key));row['seeds']=len(g);row['stations_each_seed_min']=int(g.stations.min())
 for col in ['heading_endpoint_rmse_deg','position_endpoint_rmse_m','nees_pose_df3','pose_coverage95','heading_coverage95','s_reject_rate','s_nis_pre_gate','s_nis_accepted']:
  row[col+'_seed_mean']=float(g[col].mean());row[col+'_seed_min']=float(g[col].min());row[col+'_seed_max']=float(g[col].max())
 group.append(row)
pd.DataFrame(group).to_csv(J/'12_CASE_DRIFT_SNR_ARM.csv',index=False)
pair=[];index=['case','station','drift','seed','snr']
for arm in ['A','B','C','G1','G2']:
 p=ok[ok.arm=='D'].merge(ok[ok.arm==arm],on=index,suffixes=('_D','_control'),validate='one_to_one')
 for col in ['heading_abs_deg','pos_error_m','nees_pose_df3']:p[col+'_D_minus_control']=p[col+'_D']-p[col+'_control']
 pair.extend(p[index+[c+'_D_minus_control' for c in ['heading_abs_deg','pos_error_m','nees_pose_df3']]].assign(control=arm).to_dict('records'))
pd.DataFrame(pair).to_csv(J/'13_PAIRED_DIFFERENCES.csv',index=False)
overall=[]
for key,g in sd.groupby(['snr','arm']):
 overall.append({'snr':int(key[0]),'arm':key[1],'case_drift_seed_units':len(g),'heading_endpoint_rmse_deg_seed_unit_mean':float(g.heading_endpoint_rmse_deg.mean()),'position_endpoint_rmse_m_seed_unit_mean':float(g.position_endpoint_rmse_m.mean()),'nees_pose_df3_seed_unit_mean':float(g.nees_pose_df3.mean()),'pose_coverage95_seed_unit_mean':float(g.pose_coverage95.mean()),'heading_coverage95_seed_unit_mean':float(g.heading_coverage95.mean())})
report={'execution_rows':len(df),'completed_runs':len(ok),'failed_runs':int((df.status=='FAILED').sum()),'missing_prior_tasks':int((df.status=='NO_EVALUATION_PRIOR').sum()),'cases':sorted(ok.case.unique()),'seed_ids':sorted(int(x) for x in ok.seed.unique()),'overall_descriptive_only':overall,'interpretation':'Endpoint after same three-waypoint physical clock and return, not full-route RMSE. Seed is repeated unit; station/time rows are not independent repetitions. Five seeds do not establish calibration consistency or hardware performance. Aggregate is descriptive and mixes available cases only; primary tables retain case/drift/SNR. Missing/failed denominators preserved. G3 exactly aliases D. No fitted uncertainty, F/H joint mixture or truth-fed initialization.'}
(J/'CONTROL_SUMMARY.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
