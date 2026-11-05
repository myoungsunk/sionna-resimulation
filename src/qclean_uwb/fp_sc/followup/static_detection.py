"""C-only static inputs: no fabricated time, controls, pose prior or truth state."""
from dataclasses import dataclass,asdict
import re
import numpy as np
from .contracts import ContractError,rooted,verify_files,STEP_M
from .numerics import cir_from_spectrum,raw_detection
from .detection import detect

@dataclass(frozen=True)
class StaticObservation:
    condition_id: str
    channel: str
    spectrum: np.ndarray

@dataclass(frozen=True)
class StaticReference:
    spectrum: np.ndarray

def load_static(root,spec,lock):
    if set(spec)!={'condition_id','channel','online_npz','evaluator_npz'}:
        raise ContractError('STATIC_SPEC_KEYS')
    if not re.fullmatch(r'[A-Za-z0-9_-]+',spec['condition_id']) or spec['channel'] not in ('Full','Native_LoS'):
        raise ContractError('STATIC_IDENTITY')
    arrays=[]
    for field,key in [('online_npz','Hrf'),('evaluator_npz','reference_H')]:
        rel=spec[field]
        if rel not in lock:raise ContractError('STATIC_INPUT_NOT_LOCKED')
        verify_files(root,{rel:lock[rel]})
        with np.load(rooted(root,rel),allow_pickle=False) as z:
            if set(z.files)!={key}:raise ContractError('STATIC_NO_TIME_PRIOR_OR_CONTROL_ALLOWED')
            a=z[key]
        if a.shape!=(257,2) or not np.iscomplexobj(a) or not np.isfinite(a).all():
            raise ContractError('STATIC_SPECTRUM_SCHEMA')
        arrays.append(a)
    return StaticObservation(spec['condition_id'],spec['channel'],arrays[0]),StaticReference(arrays[1])

def validate_static_specs(root,manifest):
    specs=manifest.get('static_cases',{})
    if not specs:return
    if manifest.get('execution_profile')!='VAB_DETECTION_ONLY_R1' or manifest.get('expected_static_cases')!=48 or len(specs)!=48:
        raise ContractError('STATIC_48_PROFILE_REQUIRED')
    keys=[(s['condition_id'],s['channel']) for s in specs.values()]
    conditions={k[0] for k in keys}
    if len(conditions)!=24 or set(keys)!={(c,ch) for c in conditions for ch in ('Full','Native_LoS')}:
        raise ContractError('STATIC_CONDITION_CHANNEL_GRID')
    if set(specs)&set(manifest['cases']):raise ContractError('STATIC_DYNAMIC_ID_COLLISION')
    for cid,s in specs.items():
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',cid):raise ContractError('STATIC_UNSAFE_CASE_ID')
        load_static(root,s,manifest['input_files'])

def evaluate_static(observed,reference,adapter,policy,mode='C'):
    """Future authorized E1-02 dispatch only; preparation never calls on real RF."""
    if mode!='C':raise ContractError('STATIC_C_ONLY')
    cir=cir_from_spectrum(observed.spectrum)
    e=adapter.evidence(cir,0.)
    d,prepared=detect(e,'C',policy)
    # Evaluator reference is accessed only after the online decision.
    ref,_,_=raw_detection(cir_from_spectrum(reference.spectrum))
    return dict(condition_id=observed.condition_id,channel=observed.channel,
        mode='C',scope='STATIC_C_ONLY_NO_TEMPORAL_PRIOR',decision=asdict(d),
        candidate_set_sha256=prepared.sha,reference_tap=ref,raw_tap=e.raw_tap,
        selected_tap=e.raw_tap,reference_valid=ref is not None,raw_valid=e.valid,
        flag=None if d.wrong_score is None else d.wrong_score>=policy.wrong_cut,
        raw_range_error=None if ref is None or not e.valid else (e.raw_tap-ref)*STEP_M,
        P_M_PM='NOT_APPLICABLE',history=None,prior_support=None,motion_support=None)
