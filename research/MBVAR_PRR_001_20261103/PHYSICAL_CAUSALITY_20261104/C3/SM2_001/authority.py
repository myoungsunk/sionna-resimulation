"""Pure authorization. No numpy, RT, output creation or model imports."""
from pathlib import Path
import hashlib,json,math

HERE=Path(__file__).resolve().parent
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1048576),b''):h.update(block)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def bindings(plan):return {n:sha(HERE/n) for n in plan['bound_files']}
def check_go(go,plan,bound):
 if go.get('schema')!='C3_SM2_GO_V1' or go.get('decision')!='GO':raise ValueError('C3 independent GO required')
 if go.get('bindings_sha256')!=bound or go.get('authorized')!=plan['authorized']:raise ValueError('GO code/contract/scope binding')
 if go.get('max_total_solver_calls')!=1040 or go.get('repeat_bins')!=[0,128,256]:raise ValueError('GO call budget')
 spec_path=HERE/plan.get('spec_audit_file','audit/C3_SPEC_REAUDIT_RESULT.json')
 spec=read(spec_path)
 if spec.get('decision') not in ('SPEC_APPROVED','ACCEPT'):raise ValueError('independent SPEC acceptance')
 if go.get('spec_audit_sha256')!=sha(spec_path):raise ValueError('SPEC receipt binding')
def validate_row(row,plan):
 if row not in plan['authorized']:raise ValueError('unauthorized condition')
 if row['coordinate']!='R4_168' or row['xyz']!=[5.251464,.325895,.45] or row['yaw_deg'] not in [0.,180.,35.7,-35.7]:raise ValueError('canary only')
 x,y,z=row['xyz'];r=math.hypot(.6,.4)/2+.1
 if not (r<x<20-r and abs(y)<1.2-r and z==.45):raise ValueError('collision/bounds')
def verify_inputs(lock,windows=False):
 def path(p):
  if not windows and len(p)>2 and p[1]==':':return Path('/mnt/'+p[0].lower()+p[2:])
  return Path(p)
 def entry(v):
  p=path(v['path'])
  if p.stat().st_size!=v['size'] or sha(p)!=v['sha256']:raise ValueError('input drift '+str(p))
 entry(lock['source_hash_manifest'])
 root=path(lock['source_root'])
 for n,v in lock['source_sha256'].items():
  if sha(root/n)!=v:raise ValueError('source drift '+n)
 for v in lock['banks'].values():entry(v)
 for v in lock['legacy_dependencies'].values():entry(v)
 for c in lock['actual_yaw_read_only'].values():
  for v in c.values():entry(v)
 if lock['new_yaw_archive_comparison']!='NOT_APPLICABLE_NEW_YAW':raise ValueError('fake archive')
def check(go_path,output):
 plan=read(HERE/'PLAN.json');lock=read(HERE/'INPUT_LOCK.json');go=read(go_path)
 check_go(go,plan,bindings(plan))
 if Path(output).resolve()!=Path(plan['output_linux']).resolve() or Path(output).exists():raise ValueError('fresh frozen output required')
 if len(plan['authorized'])!=4 or plan['primary_calls']!=1028 or plan['repeat_calls']!=12 or plan['max_total_solver_calls']!=1040:raise ValueError('canary budget')
 for row in plan['authorized']:validate_row(row,plan)
 verify_inputs(lock)
 return plan,lock,go
