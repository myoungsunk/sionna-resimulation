"""Regenerate frozen-law inputs into a NEW output; preserve both prior attempts."""
import hashlib, importlib.util, json, sys
from pathlib import Path
import numpy as np

out=Path(sys.argv[1]); out.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('gen','/home/claude/m8/gen_inputs_ext.py')
G=importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
G.OUT=out; sys.argv=['gen_inputs_ext.py','generate','30','49']; G.main()
root=Path('/home/claude/sionna-resimulation/research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/INTEGRITY_DIAG_001/dist_unc_m8')
index=json.loads((root/'step3_fair/freeze/INPUT_INDEX_EXT.json').read_text())['index']
rows=[]; differences={}
for cond,seeds in index.items():
    for seed,routes in seeds.items():
        for route,rec in routes.items():
            p=out/rec['path']; digest=hashlib.sha256(p.read_bytes()).hexdigest()
            old=Path('/home/claude/m8/inputs_ext')/rec['path']
            with np.load(p) as n,np.load(old) as o:
                gaps={k:float(np.max(np.abs(n[k]-o[k]))) for k in n.files}
            rows.append(dict(path=rec['path'],expected=rec['sha256'],actual=digest,match=digest==rec['sha256'],versus_numpy246=gaps))
result=dict(numpy=np.__version__,n=len(rows),hashes_matched=sum(r['match'] for r in rows),rows=rows)
(out.parent/'INPUT_REGEN_CHECKS.json').write_text(json.dumps(result,indent=2))
print('HASHES',result['hashes_matched'],'/',result['n'],flush=True)
