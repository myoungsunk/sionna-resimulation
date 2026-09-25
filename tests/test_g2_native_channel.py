import json
import numpy as np
import pytest
from rt_cp_uwb_py.g2_native_channel import file_sha,load_native_link,sum_native_paths


def fixture(root,backend='Sionna RT 2.0.1'):
    row=dict(link_id='sample',tx=[0,0,1],rx=[1,0,1])
    for name,data in [('STATUS.json',dict(backend=backend,status='NATIVE_PIPELINE_COMPUTED')),
                      ('PRODUCTION_INPUTS.json',[row]),('sample_RESULT.json',row)]:
        (root/name).write_text(json.dumps(data))
    np.savez(root/'sample_CHANNEL.npz',tx_m=row['tx'],rx_m=row['rx'])
    (root/'MANIFEST.json').write_text(json.dumps({'outputs':{p.name:file_sha(p) for p in root.iterdir()}}))


def test_native_consumer_rejects_custom_backend(tmp_path):
    fixture(tmp_path,'custom volume')
    with pytest.raises(ValueError,match='NATIVE_BACKEND_NOT_COMPLETE'):load_native_link(tmp_path,'sample')


def test_native_consumer_checks_coordinates_and_output_hash(tmp_path):
    fixture(tmp_path)
    assert load_native_link(tmp_path,'sample')['input']['rx']==[1,0,1]
    (tmp_path/'sample_RESULT.json').write_text('{}')
    with pytest.raises(ValueError,match='NATIVE_OUTPUT_SHA_MISMATCH'):load_native_link(tmp_path,'sample')


def test_native_carrier_phase_uses_double_precision():
    import cmath
    rng=np.random.default_rng(42)
    a=(rng.normal(size=(2,2,13))+1j*rng.normal(size=(2,2,13))).astype(np.complex64)
    tau=rng.uniform(1e-9,90e-9,13).astype(np.float32);f=6.49999991e9
    expected=sum(a[:,:,i].astype(complex)*cmath.exp(-2j*np.pi*f*float(t)) for i,t in enumerate(tau))
    np.testing.assert_allclose(sum_native_paths(a,tau,f),expected,rtol=1e-14,atol=1e-14)
