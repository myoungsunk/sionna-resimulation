"""Regression checks for outer-route E1 exclusion and H3's s-only control."""
import numpy as np
import pytest

from d7_cir_multipath_audit import E1_DETECTOR_FEATURES
from d8_polarization_quality import outer_e1_labels, calibration_gate, split_exclude_overlap
from d6_d9_verdict import summary


def params(intercept):
    return {'E1':{'w':[intercept]+[0.]*7, 'mu':[0.]*7,'sd':[1.]*7}}


def row(route, own_label):
    return {'route':route,'error_range_B_OLD_m':2.,
            'error_range_E1_FULL_LORO_m':own_label,
            **dict(zip(E1_DETECTOR_FEATURES,[1.]+[0.]*7))}


def test_outer_e1_never_reuses_training_rows_own_leaky_fold():
    frozen={'chosen':'E1_on_B','loro_fold_params':{
        'R2':params(.25),'R4':params(900.),'R5':params(-900.)}}
    original=[row('R4',100.), row('R5',-100.),row('R2',1.75)]
    result=outer_e1_labels(original,'R2',frozen)
    assert [r['error_range_E1_FULL_LORO_m'] for r in result]==[1.75]*3
    assert all(r['e1_label_outer_excluded_route']=='R2' for r in result)
    # Altering the two folds that contain R2 truth has no effect.
    frozen['loro_fold_params']['R4']=params(1e9)
    frozen['loro_fold_params']['R5']=params(-1e9)
    assert outer_e1_labels(original,'R2',frozen)==result
    assert original[0]['error_range_E1_FULL_LORO_m']==100.
    with pytest.raises(RuntimeError,match='outer-route'):
        outer_e1_labels(original,'R9',frozen)


def test_frozen_e1_shared_training_site_not_counted_as_unseen_test():
    test=[{'true_x_m':1.,'true_y_m':2.},
          {'true_x_m':3.,'true_y_m':4.}]
    training=[{'true_x_m':1.+1e-5,'true_y_m':2.}]
    kept,dropped=split_exclude_overlap(test,training,1e-4)
    assert kept==test[1:]
    assert dropped==1


def score(nll, ratio=1.):
    return {'zero_mean_gaussian_nll_proxy':nll,
            'calibration_empirical_over_predict_var':ratio}


def test_q3_gate_requires_incremental_value_over_s_only_q1():
    assert calibration_gate(score(3.),score(1.),q1=score(2.))['status'].endswith('PASS')
    bad=calibration_gate(score(3.),score(1.),q1=score(.5))
    assert bad['status'].endswith('FAIL')
    assert bad['nll_improvement_vs_Q1']==-.5
    assert calibration_gate(score(3.),score(1.))['status'].endswith('FAIL')


def evidence(q1_nll=2., include_q1=True):
    rows=[]
    for route in ('R2','R4','R5'):
        for variant,nll in [('Q0_FIXED',3.),('Q1_S_ONLY',q1_nll),('Q3_CIR_POL',1.)]:
            if variant=='Q1_S_ONLY' and not include_q1:
                continue
            rows.append({'heldout_route':route,'channel':'full',
                'range_model':'B_OLD','target':'s','variant':variant,
                'n_test':100, **score(nll)})
    return rows


def h3(rows):
    result=summary(None,None,None,None,rows,None)
    return next(r for r in result['hypotheses'] if r['hypothesis']=='H3_CIR_QUALITY_PREDICTION')


def test_h3_cannot_be_supported_by_q0_improvement_alone():
    assert h3(evidence(.5))['status']=='NOT_SUPPORTED'
    missing=h3(evidence(include_q1=False))
    assert missing['status']=='INCONCLUSIVE'
    assert missing['evidence']['required_Q1_cells_missing']==3
    assert h3(evidence())['status']=='PARTIALLY_SUPPORTED'


def test_h3_does_not_pool_away_a_failed_channel_scope():
    rows=evidence()+[{**r,'channel':'los'} for r in evidence(.5)]
    assert h3(rows)['status']=='NOT_SUPPORTED'
    with pytest.raises(RuntimeError,match='Duplicate D8'):
        h3(evidence()+evidence()[:1])
