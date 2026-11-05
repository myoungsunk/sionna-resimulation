#!/usr/bin/env python3
"""Evidence-linked temporal diagnostics, NOT controlled recursive C2 causality.
All 3136 original RF C0A pose ids, historical POWER1 full EKF B0 traces.
Report pre-registered windows, lag association, covariance+actual error.
"""
from pathlib import Path
import math,json,numpy as np,pandas as pd
D=Path('/mnt/data');O=D/'fp_ekf_verification'
rf=pd.read_csv(D/'c0a/c0a_outputs/C0A_AGGREGATE_TAP_DECOMPOSITION.csv')
windows={
'R4':[(0.,15.,'R4_initial'),(33.,35.2,'R4_33'),(59.,61.,'R4_near'),(99.,105.4,'R4_99')],
'R5':[(79.,81.,'R5_79'),(92.,94.,'R5_92'),(132.,135.,'R5_near'),(195.,198.,'R5_195')],
}
def wrap(x):return (x+np.pi)%(2*np.pi)-np.pi
rows=[];every=[]
for route in ['R4','R5']:
 d=rf[rf.route==route].set_index('pose_id',verify_integrity=True)
 tr=np.load(D/f'replay_{route.lower()}/{route}_aB_m0_full_B0_TRACE.npz')
 j=list(tr['arms']).index('POWER1');j4=list(tr['arms']).index('JOINT4')
 pose=tr['pose_id'].astype(int);t=tr['t_s']
 assert np.all(pose==d.loc[pose,'pose_id'].to_numpy()) if 'pose_id' in d.columns else np.allclose(d.loc[pose,'t_s'].to_numpy(),t)
 e=wrap(tr['state'][:,j,2]-tr['truth_scoring_only'][:,2]);sg=np.sqrt(tr['cov'][:,j,2,2]);nees=(e/sg)**2
 e4=wrap(tr['state'][:,j4,2]-tr['truth_scoring_only'][:,2]);sg4=np.sqrt(tr['cov'][:,j4,2,2]);nees4=(e4/sg4)**2
 ed=d.loc[pose]
 data=pd.DataFrame({'route':route,'pose_id':pose,'t_s':t,'s_error':ed.physical_e_mp.to_numpy(),'abs_s_error':ed.physical_e_mp.abs().to_numpy(),'fp_shift':(ed.delta_tap!=0).to_numpy(),'delta_tap':ed.delta_tap.to_numpy(),'err_deg':np.degrees(e),'sigma_deg':np.degrees(sg),'NEES':nees,'NEES_joint4':nees4,'NIS':tr['nis'][:,j],'accept':tr['accepted'][:,j],'heading95':nees<=3.841458820694124})
 every.append(data)
 for start,end,tag in windows[route]:
  w=data[(data.t_s>=start-1e-10)&(data.t_s<=end+1e-10)].copy(); assert len(w)>2
  one=data.iloc[int(round(start/.2))];endrow=data.iloc[min(len(data)-1,int(round(end/.2)))]
  next20=data[(data.t_s>=end)&(data.t_s<=end+20)]
  rows.append({'window':tag,'route':route,'start_s':start,'end_s':end,'n':len(w),'abs_s_mean':float(w.abs_s_error.mean()),'abs_s_max':float(w.abs_s_error.max()),'FP_shift_count':int(w.fp_shift.sum()),'FP_shift_frac':float(w.fp_shift.mean()),'NIS_mean':float(w.NIS.mean()),'NIS_gt_gate_count':int((w.NIS>9.210340371976184).sum()),'Heading_RMSE_deg':float(np.sqrt(np.mean(w.err_deg**2))),'Heading_sigma_mean_deg':float(w.sigma_deg.mean()),'NEES_mean':float(w.NEES.mean()),'heading95':float(w.heading95.mean()),'err_start_deg':float(one.err_deg),'err_end_deg':float(endrow.err_deg),'next20_Nees_mean':float(next20.NEES.mean()),'next20_rmse_deg':float(np.sqrt(np.mean(next20.err_deg**2)))})
 pd.DataFrame(rows).to_csv(O/'C2_TEMPORAL_WINDOW_ASSOCIATIONS.csv',index=False)
 pd.concat(every,ignore_index=True).to_csv(O/'C2_ORIGINAL_TRAJECTORY_RF_EKF.csv',index=False)
 print(pd.DataFrame(rows).to_string(index=False))
# historical temporal followup test: match original r4 and r5 baseline first/last accepted high RF events
qa={'record_counts':{r:int(len(d)) for r,d in pd.concat(every,ignore_index=True).groupby('route')},'windows':len(rows),'status':'TEMPORAL_OBSERVATIONAL_ONLY_NOT_C2_NATURAL_RECURSIVE_INTERVENTION','disclaimer':'Prior x/P and Kalman gain not rerun; association and temporal coincidence cannot establish causality; no on-line oracle sensor used'}
(O/'C2_TEMPORAL_QA.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2))
