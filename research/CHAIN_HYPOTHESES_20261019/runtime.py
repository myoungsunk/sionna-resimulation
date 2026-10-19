"""Runtime binding to an isolated, already-extracted frozen input directory."""
from pathlib import Path
import sys,json,hashlib
import numpy as np
BANK_SHA={'LP_plus45_bank.npz':'b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b','LP_minus45_bank.npz':'39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9'}

def write_json(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+'\n')

def load(work):
    work=Path(work).resolve();root=work/'source'
    for rel in ['research/FFD_P0P3_20261016','research/R5_N4B_20261015','research/R5_N4C_20261015','research/EKF4_RANGE_S_STAGED_20261014','research/PHYSICS_RS_STAGED_20261015/code','results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src']:
        sys.path.insert(0,str(root/rel))
    (work/'ffd_p0p3/out').mkdir(parents=True,exist_ok=True)
    receipts=[]
    for name,expected in BANK_SHA.items():
        p=work/name
        with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        receipts.append({'file':name,'bytes':p.stat().st_size,'sha256':actual,'original_match':actual==expected})
    if not all(r['original_match'] for r in receipts):
        raise ValueError('Actual bank values require numerical equivalence evaluation before mixing; no packaging-only mismatch assumed.')
    write_json(work/'BANK_MANIFEST.json',{'npz_sha256':BANK_SHA})
    import p0_initial
    banks=p0_initial.load_banks()
    for b in banks:
        b.e_theta.flags.writeable=False;b.e_phi.flags.writeable=False
    from source_model import SourceFFD
    from core import transition,gaussian_update
    from r2_bias_replay import build_positive_bias_controls
    from features import extract,FEATURES,GROUPS
    import n4b_rf_errors
    write_json(work/'BANK_READONLY_RECEIPT.json',receipts)
    return dict(model=SourceFFD(banks),transition=transition,gaussian_update=gaussian_update,controls=build_positive_bias_controls,extract=extract,features=FEATURES,groups=GROUPS,n4=n4b_rf_errors,root=root)
