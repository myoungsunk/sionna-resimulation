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
entries=read(out/'cache/CACHE_D6_MANIFEST.json')['files']
previous=read(old/'cache/CACHE_D6_MANIFEST.json')['files']
tree={line.split('\t')[1]:line.split()[2] for line in (out/'git_tree.txt').read_text().splitlines()}
assert len(entries)==63 and all(entries[k]==v for k,v in previous.items())
new=sorted(set(entries)-set(previous)); assert len(new)==2
print('MANIFEST unchanged 61; new',new,flush=True)
def fetch(rel):
 v=entries[rel]; assert v['stored_as']=='whole'
 p=out/'cache'/rel; p.parent.mkdir(parents=True,exist_ok=True)
 if not p.exists():
  tmp=p.with_name(p.name+'.download')
  url=f'https://raw.githubusercontent.com/myoungsunk/sionna-resimulation/{commit}/{prefix}cache/{rel}'
  for attempt in range(4):
   r=subprocess.run(['curl.exe','--fail','--silent','--show-error','--connect-timeout','15','--max-time','180','--continue-at','-','--output',str(tmp),url])
   if r.returncode==0: break
  assert r.returncode==0
  assert tmp.stat().st_size==v['bytes'] and sha(tmp)==v['sha256']
  tmp.rename(p)
 assert sha(p)==v['sha256']
 h=hashlib.sha1(f'blob {v["bytes"]}'.encode()+b'\0');h.update(p.read_bytes())
 assert h.hexdigest()==tree[prefix+'cache/'+rel]
 print('DOWNLOADED VERIFIED',rel,flush=True)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(fetch,new))
for rel,v in previous.items():
 p=old/'cache'/rel
 assert p.stat().st_size==v['bytes'] and sha(p)==v['sha256']
 dest=out/'cache'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
 if not dest.exists():os.link(p,dest)
print('ALL 63 SHA256 VERIFIED',flush=True)
sys.path.insert(0,str(root/prefix/'followup_v2'))
import common as C
import diagnose_dr_trace as D
import confirm_dr_independent as E
import dr_io as IO
from ablate_dr_calibration import load_rows,arm_summary
spec=read(out/'D6_SPEC.json');seeds=C.parse_seed_range(spec['seeds'])
assert C.git_frozen_spec()
records=[r for r in read(old/'V0_UPLOADED_CACHE_AUDIT.json')['records'] if r['status']=='VALID']
for rel in new:
 route,lv=Path(rel).stem.split('_d')
 summary,_=C.validated_cache(out/'cache'/rel,seeds,route,min_age_s=0,sha=True,full_psd=True)
 summary.update(arm='PF_A2_3',route=route,drift=int(lv));records.append(summary)
assert len(records)==63 and all(r['status']=='VALID' for r in records)
save('V0_FINAL_CACHE_AUDIT.json',dict(status='READY_FOR_D6',counts={'VALID':63},records=records,reused_full_content_audit=str(old/'V0_UPLOADED_CACHE_AUDIT.json'),all_63_sha256_reverified=True))
print('V0 READY_FOR_D6 63',flush=True)
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
