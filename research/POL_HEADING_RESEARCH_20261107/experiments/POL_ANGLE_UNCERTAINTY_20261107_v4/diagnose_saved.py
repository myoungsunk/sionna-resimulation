"""Offline diagnostic at saved aggregate predicted states, not per-component runtime telemetry."""
import run_angle as m
import numpy as np
raw=m.e.data('full');ctrl,x0=m.e.build_positive_bias_controls(raw['t_s'],raw['truth_for_offline_scoring_only'],'B0');records={}
for arm in ['v4','refined','shifted','fine']:
 d=np.load(m.BASE/f'outputs/full_B0_{arm}.npz');counts=[];slope=[]
 for k,z in enumerate(raw['z_s']):
  if k:q,P=m.e.predict_one(d['estimate'][k-1],d['covariance'][k-1],ctrl['ds_odom'][k],ctrl['dtheta_gyro'][k],ctrl['dt_s'][k])
  else:q,P=m.e.initial(x0,4)
  roots=m.inverse_roots(q,z);counts.append(len(roots));slope.append(max([float(np.linalg.norm(H[:2])) for a,H in roots],default=0))
 records[arm]=dict(counts=counts,maximum_abs_inverse_xy_gradient=float(max(slope)),accepted_no_inverse=int(np.sum((np.array(counts)==0)&d['mask'])))
coarse=records['v4']['counts'];summary={a:dict(accepted_no_inverse=r['accepted_no_inverse'],maximum_abs_inverse_xy_gradient=r['maximum_abs_inverse_xy_gradient'],root_count_disagreement_with_coarse=int(np.sum(np.array(r['counts'])!=coarse))) for a,r in records.items()}
m.dump('SAVED_STATE_DIAGNOSTIC.json',dict(scope='offline aggregate predicted states only, not actual component-level accepted/rejected counts',case='Full B0',summary=summary,counts=records,claim='state-dependent inverse roots can change between trajectories; this diagnostic does not isolate causality or establish optimizer failure; no optimizer is used'))
print(summary)
