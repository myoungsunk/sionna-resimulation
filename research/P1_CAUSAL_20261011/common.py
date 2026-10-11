"""Frozen P0 artifacts and common data definitions; no production source edits."""
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ROOT/'research/P0_RESTORE_20261011'))
from qclean_uwb.drivesim import hs_lut as HL
from pole_safe_model import CartesianPoleField
from pole_safe_model_v2 import PoleSafeModelV2
RUN=ROOT/'results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff'
B=ROOT/'results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C'
T=ROOT/'results/DRIVE_SIM_20261007/S1/routes'
COEFF_SHA='87a38e9cc221244cb8b6ca08ba59afd2090bb64594d486b020c694d06dc76a5e'
LUT_SHA='711e12ee48a30cb666db4ada749b983de49bd565ea351b906269ec8da375a079'
CASES=('R2_aA_m0','R2_aB_m0','R2_aA_m45','R4_aA_m0','R4_aB_m0','R5_aA_m0','R5_aB_m0')

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(4194304),b''):h.update(b)
    return h.hexdigest()

def __getattr__(name):
    if name=='PoseIndex':
        from rf_pose_index import PoseIndex
        return PoseIndex
    raise AttributeError(name)

def models(coeff):
    coeff=Path(coeff)
    assert sha256(coeff)==COEFF_SHA,'P0_COEFFICIENT_HASH_MISMATCH'
    p=RUN/'LUT/hs_lut_2deg.npy';assert sha256(p)==LUT_SHA,'LUT_HASH_MISMATCH'
    meta=json.loads((RUN/'LUT/hs_lut_meta.json').read_text());m=meta['meta']
    lut=HL.HsLut(dict(theta_deg=m['theta_deg'],phi_deg=np.arange(m['phi_deg'][0],m['phi_deg'][1]+.01,m['phi_deg'][2]),s=np.load(p)))
    a=np.load(coeff,allow_pickle=False)
    field=CartesianPoleField.__new__(CartesianPoleField)
    field.freq=a['freq'];field.scale=float(a['scale']);field.terms=[tuple(map(int,v)) for v in a['terms']]
    field.coeff=a['coeff'];field.origin=a['origin'];field.fit_receipts=[]
    safe=PoleSafeModelV2.__new__(PoleSafeModelV2)
    safe.original_lut=lut;safe.field=field;safe.model_version='CARTESIAN_FIELD_DEG4_CORE2_BLEND2_3_FP_V2'
    return lut,safe,meta

def receipt(out,extra=None):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    paths=list(Path(__file__).parent.glob('*.py'))+list((ROOT/'src/qclean_uwb/drivesim').glob('*.py'))+list((ROOT/'research/P0_RESTORE_20261011').glob('*.py'))
    d={str(p.relative_to(ROOT)):sha256(p) for p in paths}
    data=dict(parent_commit='9604e4c20b694cf29542b4b545f64ebd5414d285',native_base='5a50fa9f0813a3dd0f9ca53e26da3cd3fbcfada9',LUT_SHA=LUT_SHA,coefficient_SHA=COEFF_SHA,source_files_sha256=d)
    if extra:data.update(extra)
    (out/'SOURCE_RECEIPT.json').write_text(json.dumps(data,indent=2))
    src=out/'executed_source';src.mkdir(exist_ok=True)
    for p in Path(__file__).parent.glob('*.py'):(src/p.name).write_bytes(p.read_bytes())
    return data
