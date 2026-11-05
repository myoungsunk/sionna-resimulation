"""G4 pre-import authorization and frozen dependency verification (stdlib only)."""
from pathlib import Path
import hashlib,json,sys,platform,importlib.metadata,os
HERE=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bindings(plan):return {n:sha(HERE/n) for n in plan['bound_files']}
def entry(v):
 p=Path(v['path'])
 if p.stat().st_size!=v['size'] or sha(p)!=v['sha256']:raise ValueError('input drift '+str(p))
def verify_inputs(lock):
 for category in ('contracts','source_model_dependencies','banks','governance'):
  for v in lock[category].values():entry(v)
 entry(lock['c1b_input_lock']);entry(lock['diagnostics'])
 c1b=read(lock['c1b_input_lock']['path'])
 for n,v in lock['source_model_dependencies'].items():
  if v['sha256']!=c1b['sources'][n]['sha256'] or v['size']!=c1b['sources'][n]['size']:raise ValueError('C1B transitive identity')
 for row in lock['conditions']:
  for v in row['files'].values():entry(v)
  m=read(row['files']['MANIFEST.json']['path']);original=m['condition']
  if any(row[k]!=original[k] for k in ('id','coordinate','xyz','yaw_deg')):raise ValueError('capture condition')
  if m['status']!='C3_RAW_NUMERICAL_PASS':raise ValueError('capture incomplete')
 for control in lock['actual_yaw_read_only'].values():
  for v in control.values():entry(v)
 c3=HERE.parent
 for n in ('SM2_001/audit/C3_DATA_RESULT_AUDIT_RESULT.json','G3_001/audit/C3_G3_RETAINED_DATA_RESULT_AUDIT_RESULT.json','G3_001/audit/C3_G3_PUBLICATION_AUDIT_RESULT.json'):
  if read(c3/n)['decision']!='ACCEPT':raise ValueError('predecessor DATA gate')
 if read(c3/'G3_001/audit/C3_G3_RETAINED_DATA_RESULT_AUDIT_RESULT.json')['original_clean_execution_acceptance'] is not False:raise ValueError('G3 forced status')
def verify_scope(plan,lock):
 expected=[(f"SM2_{c['id']}_Y{yi}",c['id'],c['xyz'],y,yi) for c in plan['coordinates'] for yi,y in enumerate([0.,180.,35.7,-35.7])]
 actual=[tuple(r[k] for k in ('id','coordinate','xyz','yaw_deg','yaw_index')) for r in lock['conditions']]
 if len(expected)!=24 or actual!=expected or len(set(r[0] for r in actual))!=24:raise ValueError('exact24 scope/order')
 if plan['fd_steps_rad']!=[1e-5,5e-6] or plan['anchor']!=[10.,0.,2.7-.05] or plan['mount_deg']!=0 or plan['robot_z_m']!=.45:raise ValueError('model geometry/FD drift')
 if (plan['fd_abs_tol'],plan['fd_rel_tol'],plan['decomposition_abs_tol'])!=(1e-6,1e-4,1e-12):raise ValueError('threshold drift')
 if plan['pairwise_contrasts']!=[dict(first=i,second=j,delta='second-minus-first') for i in range(4) for j in range(i+1,4)]:raise ValueError('pair scope')
def runtime(plan,lock):
 env=read(Path(lock['source_model_cache'])/'provenance/ENV_LOCK.json')
 packages={n:importlib.metadata.version(n) for n in env['packages']}
 if sys.version!=env['python'] or platform.platform()!=env['os'] or packages!=env['packages'] or sha(sys.executable)!=plan['python_executable_sha256']:raise ValueError('original model runtime')
 if any(os.environ.get(n)!='1' for n in env['threads']):raise ValueError('thread environment before imports')
 return dict(python=sys.version,os=platform.platform(),packages=packages,executable_sha256=sha(sys.executable),threads={n:os.environ[n] for n in env['threads']})
def check_go(plan,go):
 if go.get('schema')!='C3_G4_GO_V1' or go.get('decision')!='GO' or go.get('bindings_sha256')!=bindings(plan):raise ValueError('independent G4 SHA GO required')
 for key in ('spec_audit','code_audit'):
  path=HERE/plan[key]
  if read(path)['decision'] not in ('ACCEPT','SPEC_APPROVED') or go.get(key+'_sha256')!=sha(path):raise ValueError('independent gate '+key)
 if go.get('output')!=plan['output'] or go.get('conditions')!=24 or go.get('pairs')!=36 or go.get('new_RT_calls')!=0:raise ValueError('G4 GO scope')
