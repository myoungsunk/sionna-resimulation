import model as m
import numpy as np,json
rows=json.loads((m.BASE/'RESUMED_PROGRESS.json').read_text());checks=[]
for r in rows:
 ch,lv,arm=r['channel'],r['level'],r['method'];v=np.load(m.BASE/f'outputs/{ch}_{lv}_{arm}.npz');d=m.e.data(ch);sel=d['t_s']>=40
 metric=m.e.metrics(v['estimate'][sel],v['covariance'][sel],d['truth_for_offline_scoring_only'][sel],np.full(sel.sum(),40.))
 assert all(abs(metric[k]-r[k])<1e-10 for k in metric)
 if arm=='S4':
  s=np.load(m.e.OLD/f'results/replay/R2_aB_m0_{ch}_{lv}_seed0_recursive.npz');j=s['names'].tolist().index('S4');assert np.array_equal(v['estimate'],s['estimate'][:,j]) and np.array_equal(v['covariance'],s['covariance'][:,j]) and np.array_equal(v['mask'],s['status'][:,j]=='APPLIED')
 elif arm=='v3':
  s=np.load(m.BASE.parent/f'POL_HEADING_VAR_20261106_v3/outputs/{ch}_{lv}_v3.npz');assert np.array_equal(v['estimate'],s['estimate']) and np.array_equal(v['covariance'],s['covariance'])
 else:
  bs=json.loads((m.BASE/f'outputs/{ch}_{lv}_{arm}_branches.json').read_text());counts=[len(b) for b in bs];masserr=max(abs(sum(b['weight'] for b in bb)-1) for bb in bs)
  resultant=[abs(sum(b['weight']*np.exp(1j*b['heading_rad']-.5*b['heading_sigma_rad']**2) for b in bb)) for bb in bs]
  checks.append(dict(channel=ch,level=lv,method=arm,max_branches=max(counts),multibranch_frames=sum(n>1 for n in counts),max_mass_error=masserr,min_resultant=min(resultant)))
assert len(rows)==32
m.dump('OUTPUT_VALIDATION.json',dict(status='PASS',baseline_states_covariances_masks_exact=True,metrics_recomputed=True,branch_diagnostics=checks))
print(json.dumps(checks))
