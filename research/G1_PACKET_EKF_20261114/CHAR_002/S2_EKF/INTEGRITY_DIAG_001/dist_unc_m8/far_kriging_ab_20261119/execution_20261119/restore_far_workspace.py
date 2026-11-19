"""Restore only exploratory assets from a SHA-bound Git bundle; no fitting."""
import hashlib, json, shutil
from pathlib import Path
import numpy as np
import pandas as pd

H=Path('/home/claude'); ROOT=H/'sionna-resimulation'
S2=ROOT/'research/G1_PACKET_EKF_20261114/CHAR_002/S2_EKF'
I=S2/'INTEGRITY_DIAG_001'; D=I/'dist_unc_m8'
M8=H/'m8'; CAL=H/'m8cal'; REL=H/'rel'
for p in (M8,CAL,REL): p.mkdir(exist_ok=False)
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((H/'BUNDLE_MANIFEST.json').read_text())
for r in manifest['files']:
    assert sha(ROOT/r['path'])==r['sha256'],r['path']
def cp(a,b):
    b.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(a,b)

# Preserve original code bytes; absolute paths resolve only inside this container.
for f in (D/'step3_fair/code').glob('*.py'): cp(f,M8/f.name)
for name in ('SWEEP_FEATURES.csv.gz','KRIGE_PARAMS.json'):
    cp(D/'step3_sweep/dev_02/code'/name,CAL/name)
cp(D/'step3_fair/freeze/SWEEP_TABLE_V.json',CAL/'SWEEP_TABLE_V.json')
cp(D/'step1/attempt_01/FIT_TABLES.json',M8/'FIT_TABLES.json')
cp(I/'exposure_m1_m4/exposure_score.py',I/'final_model_stage0/inputs/exposure_score.py')

# CSV exported with 17 significant digits; round-trip parser avoids decimal truncation.
arr={}
for r in ('R2','R4','R5'):
    df=pd.read_csv(D/f'step3_fair/freeze/SWEEP_CAL_B_{r}.csv',float_precision='round_trip')
    for k in ('mu_r','mu_s','Rrr','Rss'): arr[f'{r}/{k}']=df[k].to_numpy()
    df=pd.read_csv(D/f'step3_fair/freeze/HEADING_HIST_B_{r}.csv',float_precision='round_trip')
    arr[f'{r}/w_hist']=df.h.to_numpy()
np.savez(CAL/'SWEEP_CAL_B.npz',**arr)
checks=json.loads((D/'step3_fair/freeze/CAL_B_CHECKS.json').read_text())
calcheck={name:dict(expected=checks[key+'_sha256'],actual=sha(CAL/name)) for name,key in
          (('SWEEP_FEATURES.csv.gz','SWEEP_FEATURES'),('KRIGE_PARAMS.json','KRIGE_PARAMS'),
           ('SWEEP_TABLE_V.json','SWEEP_TABLE_V'),('SWEEP_CAL_B.npz','SWEEP_CAL_B'))}
for name,rec in calcheck.items():
    assert rec['actual']==rec['expected'],(name,rec)

IG=I/'m7_final_model_stage1/attempt_02/input_generation'
con=json.loads((IG/'RUN_CONTRACT.json').read_text())
for cell in con['cells']:
    r=cell['route']; online=cell['online']
    [p]=list((S2/'MOUNT45_VALIDATION_20261116/frozen_inputs/G1_CHAR002_S2_INPUTS_20261115').glob(f'*_{r}_B0_Full_10__online.npz'))
    assert sha(p)==online['sha256']
    cp(p,REL/f'{r}_B0_Full_10__online.npz')
    p=I/f'gm_theta_m6/inputs/{r}_evaluator.npz'
    assert sha(p)==con['evaluator_inputs'][r]['sha256']
    cp(p,REL/f'{r}_B0_Full_10__evaluator.npz')

native=H/'native'
shutil.copytree(I/'continuation_ks/replay_inputs/R45_sources',native)
for name in ('LP_plus45_bank.npz','LP_minus45_bank.npz'):
    (native/name).symlink_to(Path('/banks')/name)
(M8/'base.json').write_text(json.dumps(dict(native=str(native))))
(H/'RESTORE_CHECKS.json').write_text(json.dumps(dict(status='PASS',source_commit=manifest['source_commit'],calibration=calcheck),indent=2))
print('RESTORE_PASS',calcheck,flush=True)
