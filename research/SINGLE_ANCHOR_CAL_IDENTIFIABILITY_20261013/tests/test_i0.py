import sys
from pathlib import Path
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from replay import validate, load_public, replay

def valid():
    return dict(t_s=np.array([0.,.2,.4]),dt_s=np.array([0.,.2,.2]),ds_odom=np.zeros(3),dtheta_gyro=np.zeros(3),dtheta_odom=np.zeros(3),x0=np.zeros(6))

def test_valid():
    validate(valid())

@pytest.mark.parametrize('mode',['truth','missing_gyro','nan','duplicate_time','wrong_dt','wrong_shape','bad_prior'])
def test_reject_bad_contract(mode):
    d=valid()
    if mode=='truth': d['true_position']=np.zeros((3,2))
    if mode=='missing_gyro': del d['dtheta_gyro']
    if mode=='nan': d['ds_odom'][1]=np.nan
    if mode=='duplicate_time': d['t_s'][1]=0
    if mode=='wrong_dt': d['dt_s'][1]=.3
    if mode=='wrong_shape': d['dtheta_odom']=np.zeros(2)
    if mode=='bad_prior': d['x0'][3]=np.nan
    with pytest.raises(ValueError): validate(d)

def test_npz_rejects_truth(tmp_path):
    d=valid();d['truth']=np.zeros(3)
    np.savez(tmp_path/'p.npz',**d)
    with pytest.raises(ValueError): load_public(tmp_path/'p.npz')

@pytest.mark.parametrize('field,value',[('use_range',True),('use_s',True),('known_wheelbase_error',.01)])
def test_no_implicit_rf_or_oracle(tmp_path,field,value):
    import json
    from dataclasses import asdict
    from replay import FilterConfig
    cfg=asdict(FilterConfig());cfg[field]=value
    np.savez(tmp_path/'p.npz',**valid())
    (tmp_path/'c.json').write_text(json.dumps(cfg))
    with pytest.raises(ValueError): replay(tmp_path/'p.npz',tmp_path/'c.json')
