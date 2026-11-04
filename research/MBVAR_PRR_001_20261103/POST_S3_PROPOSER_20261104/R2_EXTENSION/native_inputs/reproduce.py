"""R2-only reproduction of the archived MU_R_EXDS fit, parity-gated Native inference."""
from pathlib import Path
import sys
import hashlib
import json
import pandas as pd
folder = Path(__file__).resolve().parent
pkg = folder.parents[2]
sys.path.insert(0, str(pkg / 'A0_R3_REFIT'))
import refit as original
source_path = pkg / 'A0_R3_REFIT/refit.py'
source = source_path.read_text()
assert source.count("for route in ['R4','R5']:") == 2
source = source.replace("for route in ['R4','R5']:", "for route in ['R2']:")
source = source.replace("details[0 if case.startswith('R4') else 2]", "details[0]")
source = source.replace("cache/'refit_reference'/(case+'_MR_SERIES.csv.gz')", "out/(case+'_MR_SERIES.csv.gz')")
source = source.replace("next(cache.rglob(case+'_'+bias+'.npz'))", "cache/'research/DS_MASK_CAUSAL_X1_X2_20261026/why_ds_worse/CONTROL'/(case+'_'+bias+'.npz')")
source = source[:source.index("if __name__=='__main__'")]
ns = {'__file__':str(source_path)}
exec(compile(source, str(source_path),'exec'), ns)
ns['out']=folder
if sys.argv[1]=='lock':
    archive=ns['old']/'p2/research/PJ_DS_GATED_20261021/results_murec/MR_SERIES.csv.gz'
    group=pd.read_csv(archive)
    group=group[group.case.eq('R2_aB_m0')]
    assert len(group)==1958 and set(group.channel)=={'full'}
    target=folder/'R2_aB_m0_MR_SERIES.csv.gz'
    group.to_csv(target,index=False,compression={'method':'gzip','mtime':0})
    ns['save']('REFERENCE.json',{target.name:{'sha256':ns['sha'](target.read_bytes())},'source_sha256':ns['sha'](archive.read_bytes()),'producer_code_sha256':ns['sha'](source_path.read_bytes())})
elif (folder/'FULL_GATE.json').exists() or (folder/'FIT_STARTED').exists():
    raise RuntimeError('Single fit already attempted')
else:
    (folder/'FIT_STARTED').write_text('R2 held-route, one authorized fit\n')
sys.exit(ns['main'](sys.argv[1]))
