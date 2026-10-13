from pathlib import Path
import sys,json,hashlib,subprocess,concurrent.futures,os,csv,math,datetime
root=Path(__file__).parent
out=root/'audit_evidence/remote_f1d6d9fc'
old=root/'audit_evidence/remote_03e06b55'
prefix='research/DR_EKF_DIAGNOSIS_20261013/'
commit='f1d6d9fc984feb2c9a3b5fba36ca9aaa31fbe933'
def read(p): return json.loads(p.read_text())
def save(n,v): (out/n).write_text(json.dumps(v,indent=2,allow_nan=False),encoding='utf-8')
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
assert read(out/'V0_FINAL_CACHE_AUDIT.json')['counts']=={'VALID':63}
sys.path.insert(0,str(root/prefix/'followup_v2'))
import common as C
import diagnose_dr_trace as D
import confirm_dr_independent as E
import dr_io as IO
from ablate_dr_calibration import load_rows,arm_summary
spec=read(out/'D6_SPEC.json');seeds=C.parse_seed_range(spec['seeds'])
assert C.git_frozen_spec()
# Input provenance must match before importing results into scientific interpretation.
checks=[]
for manifest_name in ['MANIFEST_D6_CONFIRMATION_s8100-8399.json','MANIFEST_D5_PF_VALIDATION.json']:
 m=read(out/'out'/manifest_name)
 for kind in ['inputs','outputs']:
  for rel,expected in m[kind].items():
   p=out/rel[len(prefix):] if rel.startswith(prefix) and (out/rel[len(prefix):]).exists() else root/rel
   actual=sha(p) if p.is_file() else None
   checks.append(dict(manifest=manifest_name,kind=kind,path=rel,expected=expected,actual=actual,match=actual==expected))
save('PROVENANCE_CHECKS.json',checks)
assert all(c['match'] for c in checks),[c for c in checks if not c['match']]
# Route only reads to the verified snapshot; frozen source files are not edited.
D.CACHE=out/'cache'
rows=load_rows(spec['arms'],seeds)
print('ALL 63 CELL SUMMARIES RECOMPUTED',flush=True)
criteria=E.evaluate(spec,rows,seeds);verdict=E.verdict(criteria)
official=read(out/'out/D6_CONFIRMATION_s8100-8399.json')
def compare(a,b,loc):
 if isinstance(a,dict) and isinstance(b,dict):return [x for k in set(a)|set(b) for x in compare(a.get(k),b.get(k),loc+'.'+str(k))]
 if isinstance(a,list) and isinstance(b,list):
  if len(a)!=len(b):return [loc+'.length']
  return [x for i,(aa,bb) in enumerate(zip(a,b)) for x in compare(aa,bb,loc+'.'+str(i))]
 if isinstance(a,(float,int)) and isinstance(b,(float,int)):
  return [] if math.isclose(a,b,rel_tol=1e-8,abs_tol=1e-8) else [loc]
 return [] if a==b else [loc]
arms=IO.json_safe({a:dict(summary=arm_summary(rr),cells=rr) for a,rr in rows.items()})
diff=compare(official['criteria'],criteria,'criteria')+compare(official['arms'],arms,'arms')+compare(official['verdict'],verdict,'verdict')+compare(official['spec'],spec,'spec')
assert official['spec_sha256']==sha(out/'D6_SPEC.json')
assert official['n']==300 and official['seeds']==[8100,8399]
csv_rows=list(csv.DictReader((out/'out/D6_CONFIRMATION_s8100-8399_CELLS.csv').open()))
flat=[r for a in spec['arms'] for r in rows[a]]
assert len(csv_rows)==len(flat)==63
csv_diffs=[]
for i,(a,b) in enumerate(zip(csv_rows,flat)):
 for k,v in a.items():
  expected=b.get(k)
  if isinstance(expected,bool):same=v==str(expected)
  elif isinstance(expected,(float,int)):same=(math.isnan(float(v)) and math.isnan(expected)) or math.isclose(float(v),expected,rel_tol=1e-8,abs_tol=1e-8)
  else:same=v==str(expected)
  if not same:csv_diffs.append(f'{i}.{k}')
save('V1_FINAL_RECONCILIATION.json',dict(status='RECONCILED' if not diff and not csv_diffs else 'MISMATCH',value_differences=diff,csv_differences=csv_diffs,verdict=verdict,criteria=criteria,arms=arms,commit=commit,cache_routing='diagnose_dr_trace.CACHE overridden in audit process only; no generators invoked',timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()))
print('V1', 'RECONCILED' if not diff and not csv_diffs else 'MISMATCH',verdict,flush=True)

