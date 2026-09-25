import json
from pathlib import Path
import numpy as np
import pytest
from rt_cp_uwb_py.g2_scoped_channel import observe,load_scoped_link,ARMS

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=ROOT/'results/SIONNA_G2_P1_SIMPLE_CONTRACT_20260924_01a0d1b0'

def settings():
    n=json.loads((CONTRACT/'POWER_NOISE_CONTRACT.json').read_text())['noise']
    d=json.loads((CONTRACT/'DETECTOR_CONTRACT.json').read_text())
    row=dict(scene_id='fixture',link_id='fixture_1',tx=[0,0,0],rx=[1,0,0])
    return n,d,row

def test_zero_signal_still_has_noise_and_paired_arms():
    n,d,row=settings();f=6250400000.+1950000.*np.arange(257)
    a,records=observe(np.zeros((257,6,6)),f,row,n,d)
    assert np.any(a['noise_H']!=0)
    for arm in ARMS:np.testing.assert_array_equal(a[arm+'_H_noisy'],a['noise_H'])
    assert len({r['seed'] for r in records})==1

def test_noise_is_absolute_and_detection_uses_observation():
    n,d,row=settings();f=6250400000.+1950000.*np.arange(257)
    h=np.zeros((257,6,6),complex);h[:,0,0]=1e-3*np.exp(-2j*np.pi*np.arange(257)*40/1028)
    a,r=observe(h,f,row,n,d);b,_=observe(h*2,f,row,n,d)
    np.testing.assert_array_equal(a['noise_H'],b['noise_H'])
    assert r[0]['state']=='DETECTED_CANDIDATE'
    assert 0<=r[0]['first_path_index']<40
    np.testing.assert_array_equal(a['CP_H'][:,0,0],h[:,0,0])

def test_actual_transform_matches_direct_sum():
    n,d,row=settings();f=6250400000.+1950000.*np.arange(257)
    a,_=observe(np.zeros((257,6,6)),f,row,n,d)
    taps=np.array([0,1,128,1027]);expected=257/1028*np.einsum('tk,kij->tij',np.exp(2j*np.pi*np.outer(taps,np.arange(257))/1028),np.hanning(257)[:,None,None]*a['noise_H'])
    np.testing.assert_allclose(a['CP_CIR'][taps],expected,atol=1e-18,rtol=1e-11)

def test_scoped_consumer_requires_explicit_acceptance(tmp_path):
    with pytest.raises(ValueError,match='EXPLICIT_SCOPED'):load_scoped_link(tmp_path,'x')
