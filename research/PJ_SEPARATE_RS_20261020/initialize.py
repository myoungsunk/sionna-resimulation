#!/usr/bin/env python3
from pathlib import Path
import os,json,hashlib
root=Path(os.environ['PJ_SOURCE_ROOT']);out=Path(os.environ['PJ_OUT']);out.mkdir(parents=True,exist_ok=True)
bankdir=Path(os.environ['PJ_BANK_DOWNLOAD'])
expected={'LP_plus45_bank.npz':'b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b','LP_minus45_bank.npz':'39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9'}
receipts=[]
for name,want in expected.items():
    matches=list(bankdir.rglob(name));assert len(matches)==1,(name,matches)
    p=matches[0]
    with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
    assert h==want,(name,h,want)
    dest=root.parent/name
    if dest.is_symlink():dest.unlink()
    if not dest.exists():dest.symlink_to(p)
    receipts.append({'name':name,'bytes':p.stat().st_size,'sha256':h})
(root.parent/'BANK_MANIFEST.json').write_text(json.dumps({'npz_sha256':expected},indent=2))
m=json.loads((root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json').read_text());known={v['path']:v for v in m['assets']};checked=[]
for c in m['cases']:
    for key in ['full_path','los_path','samples_path']:
        p=root/c[key];assert p.exists(),p
        with p.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
        receipt={'path':c[key],'sha256':h,'bytes':p.stat().st_size,'registered_original_match':None}
        if c[key] in known:
            receipt['registered_original_match']=h==known[c[key]]['sha256']
            assert receipt['registered_original_match'],('CHANGED_ORIGINAL_RF',c[key])
        checked.append(receipt)
for r in m['routes']:assert (root/r['path']).exists(),r
(out/'STAGED_INPUT_QA.json').write_text(json.dumps({'source_banks':receipts,'original_RF_files':checked,'original_observer_model_unchanged':True},indent=2))
print('STAGED_SOURCE_PASS',len(checked),len(receipts),flush=True)
