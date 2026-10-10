from pathlib import Path
import json,pickle,time,hashlib,concurrent.futures
import numpy as np
J=Path('/job')
def pair(task):
 c,d,s=task;paths=[J/'TRACES/main'/f'{c}_d{d}_s{s}_{arm}_stochastic_unknown.npz' for arm in 'ABCD']+[J/'TRACES/E'/f'{c}_d{d}_s{s}_E_stochastic_unknown.npz'];a=np.load(paths[0]);shared=[k for k in a.files if k.startswith('sensor_')]+['t','truth','pose_id','keep','initial_state','initial_prior'];fail=[]
 for p in paths[1:]:
  b=np.load(p)
  for k in shared:
   if not np.array_equal(a[k],b[k],equal_nan=True):fail.append(p.name+':'+k)
  if p.parent.name=='E':
   used=np.isfinite(b['s_R']);expect=.09**2*b['R_multiplier'][used]
   if not np.allclose(b['s_R'][used],expect,rtol=1e-12,atol=1e-15):fail.append('E R mismatch')
   if np.any(used&((b['q_good_5deg']<.5)|~b['rf_available'])):fail.append('E accepted query while reliability abstains')
 return fail
if __name__=='__main__':
 start=time.time();plan=json.loads((J/'PLAN.json').read_text());tasks=[(c,d,s) for c in plan['cases'] for d in range(3) for s in range(50)]
 with concurrent.futures.ProcessPoolExecutor(max_workers=24) as ex:fail=[v for r in ex.map(pair,tasks,chunksize=8) for v in r]
 models=[]
 for p in sorted((J/'RELIABILITY').glob('*.pkl')):
  a=pickle.loads(p.read_bytes());assert not any('truth' in c or 'error' in c or 'correct' in c for c in a['columns']);assert all(not g.startswith(a['held_out_route']) for g in a.get('training_groups',[])+a.get('calibration_groups',[]));assert not set(a.get('training_groups',[])).intersection(a.get('calibration_groups',[]));models.append(p.name)
 pilot=json.loads((J/'OUTPUT/PILOT_STATUS.json').read_text());assert pilot['failed']==0 and len(pilot['parity'])==80
 record={'state':'PASS' if not fail else 'FAIL','pairs':len(tasks),'same_sensor_initial_prior_mask':not fail,'failures':fail,'held_out_model_inference_columns_and_group_separation':True,'models':models,'pilot_original_filter_parity_runs':80,'seconds':time.time()-start,'scope':'implementation/record preservation checks, not scientific acceptance'};(J/'VERIFICATION.json').write_text(json.dumps(record,indent=2));print(json.dumps(record),flush=True)
 if fail:raise SystemExit(2)
