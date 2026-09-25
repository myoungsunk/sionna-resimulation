import numpy as np
import pytest
from rt_cp_uwb_py.g2_native_summary import summarize_paths


def test_direct_reflection_and_transmission_are_distinct_with_padding_ignored():
    a=np.ones((2,2,4),complex)
    a[:,:,3]=1000
    tau=np.array([1.,2.,3.,0.])*1e-9
    events=np.array([[0,1,4,0],[0,1,0,0],[0,0,0,0]])
    r=summarize_paths(a,tau,events,[1,1,1,0])
    assert r['valid_paths']==3 and r['native_los_present']
    assert r['reflected_paths']==r['transmitted_paths']==r['multiple_reflection_paths']==1
    assert r['reflection_path_power_fraction']==pytest.approx(1/3)
    assert r['power_weighted_delay_s']==pytest.approx(2e-9)
    assert r['rms_path_delay_spread_s']==pytest.approx(np.sqrt(2/3)*1e-9)


def test_empty_paths_have_no_fabricated_delay():
    r=summarize_paths(np.empty((2,2,0)),np.empty(0),np.empty((3,0)),np.empty(0))
    assert r['valid_paths']==0 and not r['native_los_present']
    assert r['earliest_path_delay_s'] is None and r['reflection_path_power_fraction'] is None


def test_invalid_delays_rejected():
    with pytest.raises(ValueError):
        summarize_paths(np.ones((2,2,1)),[-1],[[0]],[1])


def test_refresh_binding_rejects_geometry_drift(tmp_path,monkeypatch):
    import json
    import rt_cp_uwb_py.g2_native_summary as mod
    geometry=tmp_path/'geometry.json';geometry.write_text('{}')
    labels=tmp_path/'labels.json';labels.write_text(json.dumps([{'link_id':'sample','NoLoS':False}]))
    binding=tmp_path/'binding.json'
    binding.write_text(json.dumps(dict(status='NATIVE_REFRESH_COMPLETE',link_ids=['sample'],
        production_root=str(tmp_path),geometry_root=str(tmp_path),labels_file=str(labels),
        bound_files=[dict(path=str(p),sha256=mod.file_sha(p)) for p in [geometry,labels]])))
    monkeypatch.setattr(mod,'load_native_link',lambda *args:{'input':{'link_id':'sample'}})
    assert mod.load_native_refresh(binding,'sample')['labels']['NoLoS'] is False
    geometry.write_text('{"changed":true}')
    with pytest.raises(ValueError,match='REFRESH_BINDING_SHA_MISMATCH'):
        mod.load_native_refresh(binding,'sample')


def test_refresh_rejects_uncomputed_binding(tmp_path):
    import json
    from rt_cp_uwb_py.g2_native_summary import load_native_refresh
    p=tmp_path/'binding.json';p.write_text(json.dumps({'status':'PENDING'}))
    with pytest.raises(ValueError,match='REFRESH_INCOMPLETE'):
        load_native_refresh(p,'sample')
