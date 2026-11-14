from collections import Counter
import json
from pathlib import Path

old=Path('/home/KMS/G1_RT_TB3_G6_20261114T124634Z_9ElGTD')
new=Path('/home/KMS/G1_RT_TB3_G6_REVALIDATION_20261114T144337Z_gPzl3x')
original=json.load((old/'G6.json').open())
prior={}
known_report=json.load((new/'G6_REVALIDATION.json').open())
for case,data in original['cases'].items():
    classic={}
    for path in (old/'traces').glob(case+'_*.jsonl'):
        for line in path.open():
            r=json.loads(line)
            tid=r['task_id']
            if tid in classic:
                raise ValueError('duplicate original task')
            classic[tid]=r['tau_s']
    for f in data['strict_unmatched_stations']:
        task=f['task_id']
        for path in f['paths']:
            indices=[i for i,t in enumerate(classic[task]) if t==path['delay_s']]
            assert len(indices)==1,(case,task,indices)
            key=(case,task,indices[0])
            assert key not in prior
            prior[key]=None
assert len(prior)==original['totals']['unmatched_strict']==612
for path in (new/'traces').glob('*.jsonl'):
    for line in path.open():
        r=json.loads(line)
        for i,p in enumerate(r['paths']):
            key=(r['case'],r['task_id'],i)
            if key in prior:
                assert prior[key] is None
                prior[key]=p
assert all(p is not None for p in prior.values())
counts=Counter(key[0] for key in prior)
still_bad=[key for key,p in prior.items() if p[-1] or abs(p[1]-p[2])>5e-14]
unmatched=[(case,f['task_id'],f['path_index']) for case,c in known_report['cases'].items() for f in c['failures']]
result=dict(original_exceeded=len(prior),original_case_counts=dict(counts),original_still_unmatched_or_exceeded=still_bad,
            original_max_residual_s=max(abs(p[1]-p[2]) for p in prior.values() if not p[-1]),
            new_count=len(unmatched),new_rows_that_previously_exceeded=[k for k in unmatched if k in prior])
print(json.dumps(result,indent=2))
