from pathlib import Path
import json
import numpy as np,pandas as pd
from scipy.stats import chi2
J=Path('/job');rows=[];matched=set();durations=set();angles=set()
for folder in (J/'BODY_CONTROLS').glob('*/*'):
 if not (folder/'ORACLE_EVAL_ONLY.npz').exists():continue
 oracle=np.load(folder/'ORACLE_EVAL_ONLY.npz');truth=oracle['true_xypsi'];xy=tuple(truth[0,:2]);matched.add(xy);tokens=folder.name.split('_');base={'case':folder.parent.name,'station':int(tokens[0][1:]),'drift':int(tokens[1][1:]),'seed':int(tokens[2][1:]),'snr':int(tokens[3][3:]),'x_truth_eval_only':xy[0],'y_truth_eval_only':xy[1]}
 for fp in folder.glob('STATE_TRACE_*.npz'):
  z=np.load(fp);arm=fp.stem.removeprefix('STATE_TRACE_');last=int(z['last_valid_sample']);n=len(z['t_s']);durations.add(round(float(z['t_s'][-1]),9));pi=z['packet_indices'];angles.add(tuple(np.round(np.degrees((truth[pi,2]-truth[0,2]+np.pi)%(2*np.pi)-np.pi),6)))
  for label,j in [('third_RF',int(pi[-1])),('after_return',n-1)]:
   row={**base,'arm':arm,'evaluation_stage':label,'completed':bool(last>=j),'eval_time_s':float(z['t_s'][j])}
   if last>=j:
    e=truth[j]-z['x_after_RF'][j,:3];e[2]=(e[2]+np.pi)%(2*np.pi)-np.pi;cov=z['P_after_RF'][j,:3,:3];eig=np.linalg.eigvalsh(cov);valid=eig.min()>0;nees=float(e@np.linalg.solve(cov,e)) if valid else None
    row.update(heading_signed_error_deg=float(np.degrees(e[2])),position_error_m=float(np.linalg.norm(e[:2])),nees_pose_df3=nees,pose_cov_min_eigenvalue=float(eig.min()),pose_cov_trace=float(np.trace(cov)),heading_variance_rad2=float(cov[2,2]),nees_lower025=bool(nees<chi2.ppf(.025,3)) if valid else None,nees_upper975=bool(nees>chi2.ppf(.975,3)) if valid else None)
   rows.append(row)
  for j in pi:
   if last<j:continue
   before=truth[j,2]-z['x_before_RF'][j,2];after=truth[j,2]-z['x_after_RF'][j,2];before=(before+np.pi)%(2*np.pi)-np.pi;after=(after+np.pi)%(2*np.pi)-np.pi
   rows.append({**base,'arm':arm,'evaluation_stage':'RF_update','completed':True,'eval_time_s':float(z['t_s'][j]),'s_status':str(z['s_status'][j]),'heading_error_before_deg':float(np.degrees(before)),'heading_error_after_deg':float(np.degrees(after)),'harmful_heading_update_eval_only':bool(abs(after)>abs(before)+1e-12),'heading_Jacobian_per_rad_online':float(z['H_s'][j,2])})
pd.DataFrame(rows).to_csv(J/'14_EVALUATION_STAGES_AND_UPDATES.csv',index=False)
(J/'STATION_AND_SCHEDULE_CHECK.json').write_text(json.dumps({'independent_physical_xy_sites':len(matched),'physical_xy_eval_only':sorted(matched),'scheduled_relative_angles_deg':sorted(angles),'durations_s':sorted(durations),'nominal_dt_s':.2,'settle_s':.4,'fixed_true_xy':True,'actual_physical_slip_motion':'NOT_MODELLED','stages':'third RF vs after return; online H_s in s/rad, truth labels offline only','NEES_two_sided_reference':{'df':3,'lower025':float(chi2.ppf(.025,3)),'upper975':float(chi2.ppf(.975,3)),'status':'descriptive Gaussian reference, not adopted PASS threshold'}} ,indent=2));print('probe stage rows',len(rows),'physical sites',len(matched))
