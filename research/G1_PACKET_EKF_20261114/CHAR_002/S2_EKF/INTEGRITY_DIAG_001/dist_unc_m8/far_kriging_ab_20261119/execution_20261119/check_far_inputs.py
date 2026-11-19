import hashlib,json
from pathlib import Path
H=Path('/home/claude')
D=H/'sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8'
expected=json.loads((D/'step3_fair/freeze/INPUT_INDEX_EXT.json').read_text())
rows=[]
for cond,seeds in expected['index'].items():
    for seed,routes in seeds.items():
        for route,rec in routes.items():
            p=H/'m8/inputs_ext'/rec['path']
            actual=hashlib.sha256(p.read_bytes()).hexdigest()
            rows.append(dict(condition=cond,seed=seed,route=route,path=rec['path'],expected=rec['sha256'],actual=actual,match=actual==rec['sha256']))
out=dict(status='PASS' if all(r['match'] for r in rows) else 'FAIL',n=len(rows),rows=rows)
(H/'INPUT_HASH_CHECKS.json').write_text(json.dumps(out,indent=2))
print(out['status'],len(rows),'matched',sum(r['match'] for r in rows))
assert out['status']=='PASS'
