import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'): os.environ[key]='1'
import csv,json,hashlib,datetime,subprocess,collections
from pathlib import Path
import numpy as np
root=Path(__file__).resolve().parents[5]
out=Path(__file__).resolve().parent
src=out.parent/'DYNAMIC_MAPPING_R1_20261105'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
receipt=json.loads((src/'RUN_001/RUN_RECEIPT.json').read_text())
for name,h in receipt['files'].items(): assert sha(src/'RUN_001'/name)==h
nom=list(csv.DictReader((src/'RUN_001/NOMINAL.csv').open()))
stress=list(csv.DictReader((src/'RUN_001/STRESS.csv').open()))
key=lambda r:(r['case_id'],int(r['k']))
lookup={key(r):r for r in nom};assert len(lookup)==6272 and len(stress)==43904
step=299792458/(1028*1950000)
def summary(a):
    a=np.asarray(a,dtype=float)
    return dict(min=float(a.min()),median=float(np.median(a)),max=float(a.max())) if len(a) else None
groups=collections.defaultdict(list);strata=collections.Counter();routes=collections.Counter();unique=set();records=[]
for s in stress:
    n=lookup[key(s)];ref=int(n['ref_tap'])*step;lo,hi=float(s['low']),float(s['high'])
    gap=max(lo-ref,ref-hi,0);fail=gap>1e-10
    assert fail==bool(int(s['narrow_reference_exclusion'])) and int(s['hold_width'])==0
    r=dict(case_id=s['case_id'],k=int(s['k']),route=s['route'],channel=s['channel'],stress=s['stress'],stratum=n['stratum'],ref_tap=int(n['ref_tap']),raw_tap=int(n['raw_tap']),excluded=fail,gap_m=gap,prior_penalty=(gap/.15)**2,width_m=hi-lo,center_shift_m=(lo+hi-float(n['low'])-float(n['high']))/2,ref_side='below' if ref<lo-1e-10 else 'above' if ref>hi+1e-10 else 'inside')
    records.append(r);groups[s['stress']].append(r)
    if fail:
        strata[(n['channel'],n['stratum'])]+=1;routes[(s['route'],s['stress'])]+=1;unique.add(key(s))
assert sum(r['excluded'] for r in records)==11095
with (out/'DIAGNOSTIC_ROWS.csv').open('x',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
result=dict(question_id='FP-SC-PRIOR-FAILURE-ANALYSIS-R1',role='PROPOSER_POSTHOC_SELF_CHECK',base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),new_model_calls=0,E1_02_started=False,E2_started=False,step_m=step,rows=len(records),excluded=11095,affected_packet_rows=len(unique),input_hashes={n:sha(src/'RUN_001'/n) for n in ('NOMINAL.csv','STRESS.csv')},stress={})
for name,rs in groups.items():
    fails=[r for r in rs if r['excluded']]
    result['stress'][name]=dict(total=len(rs),excluded=len(fails),width=summary([r['width_m'] for r in rs]),gap_failed=summary([r['gap_m'] for r in fails]),penalty_failed=summary([r['prior_penalty'] for r in fails]),center_shift=summary([r['center_shift_m'] for r in rs]),sides=dict(collections.Counter(r['ref_side'] for r in fails)))
result['excluded_by_channel_stratum']={'/'.join(k):v for k,v in sorted(strata.items())}
result['excluded_by_route_stress']={'/'.join(k):v for k,v in sorted(routes.items())}
result['examples']=sorted((r for r in records if r['excluded']),key=lambda r:r['gap_m'],reverse=True)[:5]
manifest=json.loads((src/'FINAL_PREPARATION_MANIFEST.json').read_text());geo={}
for cid,spec in manifest['cases'].items():
    path=root/spec['online_npz'];assert sha(path)==manifest['input_files'][spec['online_npz']]
    with np.load(path,allow_pickle=False) as z:
        x=z['prior'][:,:2];p=z['Pprior'][:,:2,:2]
        d=np.sqrt((x[:,0]-10)**2+x[:,1]**2+2.2**2)
        geo[cid]=dict(abs_dr_dx=summary(abs((x[:,0]-10)/d)),abs_dr_dy=summary(abs(x[:,1]/d)),sigma_x=summary(np.sqrt(p[:,0,0])),sigma_y=summary(np.sqrt(p[:,1,1])))
result['prior_geometry']=geo
result['governance_hashes']={name:sha(Path('C:/Users/Myoungsun Kim/.codex/research-governance')/name) for name in ('COMMON_CONTRACT.md','ROLE_PROPOSER.md')}
(out/'SUMMARY.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('input_hashes','governance_hashes','examples')},indent=2))
