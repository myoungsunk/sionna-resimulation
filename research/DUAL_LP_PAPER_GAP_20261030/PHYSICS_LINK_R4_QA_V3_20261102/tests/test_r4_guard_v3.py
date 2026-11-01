"""Regression tests for the 2026-11-02 QA validator defects.

Uses actual saved packet arrays and immutable original CONTROL timestamps.
No synthetic success data or change to EKF/trace paths.
"""
import os, sys
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
ROOT=Path(os.environ.get('DLP_RERUN_ROOT','/mnt/data/work_r4qa/source/DualLP_Physics_Link_Validation_RERUN_20261101'))
REPAIR=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'code'),str(REPAIR/'code')]
import bootstrap as B
import repair_v3 as M
CASE=B.CASES[0];BIAS='B0';ARM='MB_VAR';GATE='self'
NORM={'key_count':'exact','time_order':'exact','timeline_reference':'exact','timeline_dt':'control','score_mask':'exact',
      'initial_state':'state','initial_P':'P','rho_lookup':'state','R':'R','innovation':'innovation',
      'S':'S','NIS':'NIS','mask':'exact','post_state':'state','post_P':'P',
      'observer_finite':'exact','P_symmetry':'P','motion_prior':'state','motion_Pprior':'P','score_count':'exact'}

@pytest.fixture(scope='module')
def source():
    D=B.read_data(CASE,BIAS);T=B.read_trace(CASE,BIAS,ARM,GATE)
    reference_t=B.C.load_control(CASE,'B0')['t_s'].copy()
    return D,T,reference_t

def copy_data(D):
    return {k:(v.copy() if isinstance(v,np.ndarray) else v) for k,v in D.items()}

def corrupt(D, name):
    copied=copy_data(D)
    if name=='pose_id':copied['pose_id'][1]=copied['pose_id'][0]
    elif name=='time_reverse':copied['t'][1]=copied['t'][0]-1.0
    elif name=='time_equal':copied['t'][1]=copied['t'][0]
    elif name=='shift_one_second':copied['t']+=1.0
    else:raise ValueError(name)
    return copied

def detect(D,T,ref):
    return M.r4_mutation_probe(B,CASE,BIAS,ARM,GATE,D,T,NORM,ref)

def test_clean_has_no_false_alarm(source):
    D,T,ref=source
    p=detect(D,T,ref)
    assert p['detected'] is False, p['offending_metrics']
    assert set(p['current_metrics'])==set(NORM)
    assert max(abs(p['current_metrics'][k]) for k in ['time_order','timeline_reference','timeline_dt','score_count','score_mask'])==0

@pytest.mark.parametrize('kind,expected_metric',[
  ('pose_id','key_count'),('time_reverse','time_order'),('time_equal','time_order'),('shift_one_second','score_count')])
def test_corruption_caught_on_current_call(source,kind,expected_metric):
    D,T,ref=source
    r=detect(corrupt(D,kind),T,ref)
    assert r['detected'] and expected_metric in r['offending_metrics']
    if kind=='shift_one_second':
       assert int(np.count_nonzero(D['t']>=30-1e-9))==829
       assert int(np.count_nonzero(D['t']+1>=30-1e-9))==834
       assert r['current_metrics']['score_count']==5
       assert r['current_metrics']['score_mask']==5

def test_detector_disabled_makes_negative_test_fail(source):
    D,T,ref=source
    for name in ['pose_id','time_reverse','time_equal','shift_one_second']:
        corrupted=corrupt(D,name)
        all_zero={k:0. for k in NORM}
        # Directly patch the actual current-call result, not a previous loop value.
        with patch.object(M,'trace_metrics',return_value=all_zero) as patched:
            result=detect(corrupted,T,ref)
            patched.assert_called_once()
            assert result['detected'] is False
            mutation_test_status='PASS' if result['detected'] else 'FAIL'
            assert mutation_test_status=='FAIL'

def test_single_run_and_order_permutation_are_identical(source):
    D,T,ref=source
    kinds=['pose_id','time_reverse','time_equal','shift_one_second']
    first={k:detect(corrupt(D,k),T,ref) for k in kinds}
    second={k:detect(corrupt(D,k),T,ref) for k in reversed(kinds)}
    third=detect(corrupt(D,'time_equal'),T,ref)
    for name in kinds:
        assert first[name]['detected']==second[name]['detected']
        assert first[name]['offending_metrics']==second[name]['offending_metrics']
    assert third['offending_metrics']==first['time_equal']['offending_metrics']

def test_fail_closed_on_unknown_missing_nan_metrics():
    assert M.required_violations({},NORM)==['MISSING_OR_EXTRA_METRIC']
    assert M.required_violations({'junk':0},NORM)==['MISSING_OR_EXTRA_METRIC']
    sample={k:0. for k in NORM};sample['score_mask']=float('nan')
    assert 'score_mask' in M.required_violations(sample,NORM)
