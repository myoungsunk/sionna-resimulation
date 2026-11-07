import model as m
import numpy as np,json,time
from concurrent.futures import ProcessPoolExecutor,as_completed

def task(ch,lv,done):
 p=json.loads((m.BASE/'CALIBRATION.json').read_text())['parameters'];out=m.BASE/'outputs';z=m.e.data(ch);ctrl,x0=m.e.build_positive_bias_controls(z['t_s'],z['truth_for_offline_scoring_only'],lv)
 saved=np.load(m.e.OLD/f'results/replay/R2_aB_m0_{ch}_{lv}_seed0_recursive.npz');j=saved['names'].tolist().index('S4');mask=saved['status'][:,j]=='APPLIED';rows=[]
 for arm in ['S4','v3','v6','refined']:
  if (ch,lv,arm) in done:continue
  start=time.perf_counter();extra={};dest=out/f'{ch}_{lv}_{arm}.npz';assert not dest.exists()
  if arm=='S4':X,P=saved['estimate'][:,j],saved['covariance'][:,j]
  elif arm=='v3':
   v=np.load(m.BASE.parent/f'POL_HEADING_VAR_20261106_v3/outputs/{ch}_{lv}_v3.npz');X,P=v['estimate'],v['covariance']
  else:
   X,P,extra,branches=m.run(ctrl,z['z_s'],x0,mask,p,max_step_deg=.125 if arm=='refined' else .25,subdiv=2 if arm=='refined' else 1)
   assert all(abs(sum(b['weight'] for b in bs)-1)<1e-10 for bs in branches)
   m.dump(f'outputs/{ch}_{lv}_{arm}_branches.json',branches)
  assert np.isfinite(X).all() and np.isfinite(P).all() and np.linalg.eigvalsh(P).min()>0
  for key in ['heading_density','observation_angle_likelihood']:
   if key in extra:assert np.isfinite(extra[key]).all() and np.max(abs(extra[key].sum(axis=1)-1))<1e-5
  np.savez_compressed(dest,estimate=X,covariance=P,t_s=z['t_s'],mask=mask,**extra)
  sel=z['t_s']>=40;metrics=m.e.metrics(X[sel],P[sel],z['truth_for_offline_scoring_only'][sel],np.full(sel.sum(),40.))
  row=dict(channel=ch,level=lv,method=arm,seconds=time.perf_counter()-start,**metrics);rows.append(row);m.dump(f'RESUME_{ch}_{lv}.json',rows);print(json.dumps(row),flush=True)
 return rows

if __name__=='__main__':
 hashes=json.loads((m.BASE/'INPUT_HASHES.json').read_text());assert all(m.sha(f)==h for f,h in hashes.items())
 rows=json.loads((m.BASE/'PROGRESS.json').read_text());m.dump('PARTIAL_EXECUTION.json',dict(reason='Cooperative stop to resume unfinished conditions in parallel; no scientific code change',run='b9ce9338-9d96-47de-a27b-0a35edb7e947',resource='3f0c070d-e038-4648-bf84-63e968c0e5fb',exit_code=1,completed_rows=rows,resume_hash=m.sha(__file__)))
 done={(r['channel'],r['level'],r['method']) for r in rows}
 with ProcessPoolExecutor(max_workers=4) as pool:
  futures=[pool.submit(task,ch,lv,done) for lv in ['B0','L0','L1','L2'] for ch in ['los','full'] if (ch,lv,'refined') not in done]
  for f in as_completed(futures):rows+=f.result();m.dump('RESUMED_PROGRESS.json',rows)
 assert len(rows)==32 and len({(r['channel'],r['level'],r['method']) for r in rows})==32
 checks=[]
 for ch in ['los','full']:
  for lv in ['B0','L0','L1','L2']:
   a=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'v6'));b=next(r for r in rows if (r['channel'],r['level'],r['method'])==(ch,lv,'refined'))
   dh=abs(a['heading_rmse_deg']-b['heading_rmse_deg']);dx=abs(a['xy_rmse_m']-b['xy_rmse_m']);ds=max(abs(a[k]/b[k]-1) for k in ['heading_sigma_rms_deg','xy_sigma_rms_m']);checks.append(dict(channel=ch,level=lv,heading_delta=dh,xy_delta=dx,sigma_relative=ds,passed=dh<.02 and dx<.005 and ds<.02))
 assert all(m.sha(f)==h for f,h in hashes.items())
 m.dump('RESULT.json',dict(status='EXECUTION_COMPLETED',inputs_unchanged=True,convergence=checks,converged=all(c['passed'] for c in checks),output_hashes={f.name:m.sha(f) for f in (m.BASE/'outputs').iterdir()}))
