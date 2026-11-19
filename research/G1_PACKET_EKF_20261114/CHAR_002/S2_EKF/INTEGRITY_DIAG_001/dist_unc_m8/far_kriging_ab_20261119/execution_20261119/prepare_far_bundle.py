import hashlib, io, json, subprocess, tarfile
from pathlib import Path

ROOT = Path(subprocess.check_output(['git','rev-parse','--show-toplevel'],text=True).strip())
S2 = 'research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF/'
I = S2 + 'INTEGRITY_DIAG_001/'
D = I + 'dist_unc_m8/'
REF = '205dbd1c57e0e09fb605c40fe550c89ed08bd2b5'
files = subprocess.check_output(['git','ls-tree','-r','--name-only',REF],cwd=ROOT,text=True).splitlines()
selected = []
for f in files:
    if f.startswith(S2) and f.endswith('.py'):
        # Source only; no held-out confirmation assets are read.
        selected.append(f)
    elif f.startswith(D+'step3_fair/') and f.endswith(('.json','.csv')):
        selected.append(f)
    elif f.startswith(D+'far_kriging_ab_20261119/'):
        selected.append(f)
    elif f in [D+'step1/attempt_01/FIT_TABLES.json',D+'step3_sweep/dev_02/code/SWEEP_FEATURES.csv.gz',D+'step3_sweep/dev_02/code/KRIGE_PARAMS.json']:
        selected.append(f)
    elif f.startswith(I+'m7_final_model_stage1/attempt_02/') and f.endswith('RUN_CONTRACT.json'):
        selected.append(f)
    elif f.startswith(I+'gm_theta_m6/inputs/') and (f.endswith(('_evaluator.npz','COMMON_CONTRACT.md','ROLE_IMPLEMENTER.md'))):
        selected.append(f)
    elif f.startswith(S2+'MOUNT45_VALIDATION_20261116/frozen_inputs/G1_CHAR002_S2_INPUTS_20261115/') and f.endswith('_online.npz'):
        selected.append(f)
manifest=[]
with tarfile.open(ROOT/'far_bundle.tar.gz','w:gz') as tar:
    for f in selected:
        b=subprocess.check_output(['git','show',REF+':'+f],cwd=ROOT)
        if b.startswith(b'version https://git-lfs.github.com/spec/v1'):
            pin=b.decode().split('oid sha256:')[1].splitlines()[0]
            b=(ROOT/f).read_bytes()
            assert hashlib.sha256(b).hexdigest()==pin, f
        manifest.append(dict(path=f,sha256=hashlib.sha256(b).hexdigest(),size=len(b)))
        info=tarfile.TarInfo('sionna-resimulation/'+f); info.size=len(b)
        tar.addfile(info,io.BytesIO(b))
    b=json.dumps(dict(source_commit=REF,files=manifest),indent=2).encode()
    info=tarfile.TarInfo('BUNDLE_MANIFEST.json'); info.size=len(b); tar.addfile(info,io.BytesIO(b))
print('files',len(manifest),'bytes',sum(v['size'] for v in manifest),'archive',(ROOT/'far_bundle.tar.gz').stat().st_size)
