"""NEW-ONLY synthetic unit tests. Does not require or run frozen RF scenes."""
from __future__ import annotations
import math,json
from pathlib import Path
import numpy as np
import pytest
from d10_d14_core import (EarlyWindowConfig, METHODS, extract_cir_methods,
    hann_pulse_template,normalized_ukf_update,correlation,rankdata,
    signed_power_ratio,stage_finish,validate_stage,save_json,write_rows)


def make_pulses(*,extra=False):
    co=np.zeros(42,complex);cross=np.zeros(42,complex)
    co[10:17]=[2,3,4,3,2,1,.4]
    cross[10:17]=.1*co[10:17]
    if extra:
        cross[13]=3.;cross[14]=6.;cross[15]=3.
    return np.column_stack((co,cross))


def test_same_pulse_shape_has_no_cross_excess_false_trigger():
    h=make_pulses();d,e=extract_cir_methods(h,fp_index=10,
        config=EarlyWindowConfig(max_taps=5,max_search_taps=9))
    assert e['cross_rise_onset'] is None
    assert e['window_width_taps']==5
    assert all(-1<=v<=1 for v in d.values())
    assert d['W0_FP']==pytest.approx(d['W2_ADAPTIVE_CROSS'])


def test_stopping_before_cross_excess_not_after_it():
    h=make_pulses(extra=True)
    cfg=EarlyWindowConfig(max_taps=6,max_search_taps=9,
                          rise_factor=1.01,consecutive=2,
                          growth_ratio=1.6,excess_over_co_fp=.02)
    d,e=extract_cir_methods(h,fp_index=10,config=cfg)
    assert e['selected_reference_rx']==0
    assert e['cross_rise_onset']==13
    assert e['window_end_exclusive']==13
    assert e['window_width_taps']==3
    assert e['stop_reason']=='CROSS_EXCESS_RISE'
    assert d['W2_ADAPTIVE_CROSS']>d['W4_TOTAL_ENERGY']


def test_single_tap_fallback_and_cannot_infer_early_unresolved():
    h=make_pulses(extra=True)
    d,e=extract_cir_methods(h,fp_index=10,
        config=EarlyWindowConfig(max_taps=2,max_search_taps=9,
                   consecutive=1,growth_ratio=1.3))
    assert e['unresolved_at_fp_unidentifiable']
    assert 1<=e['window_width_taps']<=2
    assert d['W0_FP']==pytest.approx(.9801980198019802)


def test_co_fixed_port_not_automatically_physical_co():
    h=make_pulses()
    d,e=extract_cir_methods(h,fp_index=10,config=EarlyWindowConfig(co_port='rx2'))
    assert e['selected_reference_rx']==1
    assert e['reference_is_physical_co'] is False
    assert 1<=e['window_width_taps']<=4


def test_signed_ratio_redundancy_and_bounds():
    for a,b in [(2.,4.),(4.,1.),(.1,3.)]:
        s=signed_power_ratio([a,b])
        assert (1+s)/(1-s)==pytest.approx(a/b)
    with pytest.raises(ValueError):signed_power_ratio([0,0])


def test_receiver_invalid_contract_rejected():
    with pytest.raises(ValueError):EarlyWindowConfig(max_taps=0).validate()
    with pytest.raises(ValueError):EarlyWindowConfig(co_port='oracle_co').validate()
    with pytest.raises(ValueError):extract_cir_methods(np.zeros((20,2),complex),fp_index=40)


def test_hann_reference_nbins_4n_shape():
    v=hann_pulse_template(257,1028)
    assert v.shape==(1028,)
    assert np.isfinite(v).all()
    with pytest.raises(ValueError):hann_pulse_template(257,1024)


def test_linear_ukf_measurement_update_matches_linear_kalman():
    x=np.array([1.,2.,.1]);P=np.diag([.05,.06,.015]);z=np.array([1.24]);R=np.array([[.02]])
    def h(v):return np.asarray([v[0]+.25*v[2]])
    H=np.array([[1.,0.,.25]])
    S=H@P@H.T+R
    K=P@H.T@np.linalg.inv(S)
    xp=x+(K@(z-h(x)))
    Pp=P-K@S@K.T
    xx,pp,status,nis=normalized_ukf_update(x,P,z,h,R,gate_threshold=1e9)
    assert status=='applied'
    assert np.allclose(xx,xp,atol=1e-11)
    assert np.allclose(pp,Pp,atol=1e-11)
    xx,pp,status,nis=normalized_ukf_update(x,P,np.array([9.]),h,R,gate_threshold=1.)
    assert status=='rejected_NIS'
    assert np.array_equal(xx,x) and np.array_equal(pp,P)


def test_rank_spearman_and_negative_corr():
    a=np.array([0,1,2,3,4],float);b=4-a
    assert correlation(a,b,method='spearman')==pytest.approx(-1.)
    assert correlation(a,b)==pytest.approx(-1.)
    assert rankdata(np.array([4,4,7])).tolist()==[1.5,1.5,3.]
    assert correlation(np.ones(5),b) is None


def test_manifest_json_paths_are_safe_and_hash_checked(tmp_path):
    output=tmp_path/'test';output.mkdir()
    src=output/'record.csv'
    write_rows(src,[{'a':1,'b':'x'},{'a':2,'b':'y'}])
    stage_finish(output,'D11',[src],config={'input':tmp_path,'t':np.float64(.15)},
                 warnings=['synthetic test only'])
    validate_stage(output,'D11',['record.csv'])
    man=json.loads((output/'D11_MANIFEST.json').read_text())
    assert man['config']['t']==.15
    assert man['scientific_PASS'] is False
    src.write_text('tamper')
    with pytest.raises(RuntimeError):validate_stage(output,'D11',['record.csv'])


def test_methods_are_unique_and_w0_single_tap():
    assert len(set(METHODS))==6
    h=make_pulses()
    d,_=extract_cir_methods(h,fp_index=10)
    assert d['W0_FP']==pytest.approx(signed_power_ratio(np.abs(h[10])**2))
