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
 if go.get('max_total_solver_calls')!=5200 or go.get('repeat_bins')!=[0,128,256]:raise ValueError('GO call budget')
 spec_path=HERE/plan.get('spec_audit_file','audit/C3_SPEC_REAUDIT_RESULT.json')
 spec=read(spec_path)
 if spec.get('decision') not in ('SPEC_APPROVED','ACCEPT'):raise ValueError('independent SPEC acceptance')
 if go.get('spec_audit_sha256')!=sha(spec_path):raise ValueError('SPEC receipt binding')
def expected_rows(plan):
 coords=[('R5_982',[1.521387,-.338994,.45]),('P10Yp',[10,.35,.45]),('P10Yn',[10,-.35,.45]),('P139Yp',[13.9,.35,.45]),('P139Yn',[13.9,-.35,.45])]
 return [dict(id=f'SM2_{c}_Y{i}',coordinate=c,xyz=xyz,yaw_deg=y,order=ci*4+i) for ci,(c,xyz) in enumerate(coords) for i,y in enumerate([0.,180.,35.7,-35.7])]

def validate_row(row,plan):
 if row not in plan['authorized']:raise ValueError('unauthorized condition')
 expected=expected_rows(plan)
 if row not in expected:raise ValueError('G3 remaining20 only')
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
 if plan['authorized']!=expected_rows(plan) or plan['primary_calls']!=5140 or plan['repeat_calls']!=60 or plan['max_total_solver_calls']!=5200:raise ValueError('G3 budget/scope')
 for n,digest in read(HERE/'G2_PREREQUISITE.json').items():
  if sha(HERE.parent/'SM2_001'/n)!=digest:raise ValueError('G2 prerequisite drift '+n)
 if read(HERE.parent/'SM2_001/audit/C3_DATA_RESULT_AUDIT_RESULT.json')['decision']!='ACCEPT':raise ValueError('G2 DATA prerequisite')
 for row in plan['authorized']:validate_row(row,plan)
 verify_inputs(lock)
 return plan,lock,go
