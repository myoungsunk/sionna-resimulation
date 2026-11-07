"""Contract/packaging regression tests; synthetic inputs only, not scientific results."""
import hashlib, io, json, zipfile
import numpy as np
import pytest
import anchor_b_inputs as inputs
import r2_bias_replay as replay
from r2_bias_audit import verify_sources
from pack_anchor_b import validate_trace, pack

def trace():
    n=979
    return dict(t_s=np.arange(n)*.2,pose_id=np.arange(n),truth_for_offline_scoring_only=np.zeros((n,3)),
                z_r_m=np.ones(n),z_s=np.zeros(n),xminus=np.zeros((n,3)),Pminus=np.tile(np.eye(3),(n,1,1)))

@pytest.mark.parametrize('field,value', [('z_s',np.zeros(978)),('xminus',np.full((979,3),np.nan)),('Pminus',np.zeros((979,3,3))),('pose_id',np.zeros(979)),('t_s',np.arange(979)*.3)])
def test_invalid_trace_stops(field,value):
    d=trace();d[field]=value
    with pytest.raises(ValueError):validate_trace(d)

def test_case_and_row_denominators():
    assert replay.CASES==('R2_aB_m0',)
    scenarios=len(replay.CASES)*len(replay.CHANNELS)*len(replay.BIAS_LEVELS)
    assert scenarios==8 and scenarios*len(replay.MODES)==16
    assert scenarios*len(replay.MODES)*len(replay.METHODS)==128

def test_source_tampering_stops(tmp_path):
    p=tmp_path/'core.py';p.write_text('frozen')
    lock={'core.py':inputs.sha_file(p)}
    verify_sources(lock,tmp_path)
    p.write_text('changed')
    with pytest.raises(RuntimeError,match='SOURCE_CHANGED'):verify_sources(lock,tmp_path)

def test_archive_hash_stops(tmp_path,monkeypatch):
    p=tmp_path/'a.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('a','b')
    monkeypatch.setattr(inputs,'read_lock',lambda:{'archive_sha256':'0'*64})
    with pytest.raises(RuntimeError,match='ARCHIVE_HASH'):inputs.open_verified_archive(p)

def test_archive_passes_exact_hash(tmp_path,monkeypatch):
    p=tmp_path/'a.zip'
    with zipfile.ZipFile(p,'w') as z:z.writestr('a','b')
    monkeypatch.setattr(inputs,'read_lock',lambda:{'archive_sha256':inputs.sha_file(p)})
    with inputs.open_verified_archive(p) as z:assert z.read('a')==b'b'

def test_b0_reference_mismatch_detected():
    d=trace();n=len(d['t_s']);x=np.zeros((n,8,4));P=np.zeros((n,8,4,4))
    P[:,0,:3,:3]=d['Pminus'];x[42,0,0]=.001
    dx,dp=replay.saved_one_step_DR_reference(d,{'one_step':{'estimate':x,'covariance':P}})
    assert dx==.001 and dp==0 and max(dx,dp)>1e-7

def test_pack_roundtrip_raw_full_and_shared_prior(tmp_path):
    d=trace();n=979
    prior=tmp_path/'dr3.npz';control=tmp_path/'R2_aB_m0_B0_CONTROL.npz';los=tmp_path/'los.npz';out=tmp_path/'packed.zip'
    np.savez(prior,**{k:v for k,v in d.items() if k not in ('z_s','z_r_m')})
    mu=np.full((n,1,2),.25);h=np.ones((n,1,2));nu=np.full((n,1,2),.5)
    gt=np.column_stack([d['truth_for_offline_scoring_only'],np.zeros(n)])
    np.savez(control,t_s=d['t_s'],pose_id=d['pose_id'],truth_scoring_only=gt,names=['OFF_BB'],h=h,mu=mu,nu=nu,
             specs_json=json.dumps({'anchor':[10,0,2.65],'mount_deg':0}))
    np.savez(los,t=d['t_s'],gt=gt,z_los=np.column_stack([d['z_r_m'],d['z_s']]))
    pack(control,los,prior,inputs.sha_file(prior),out)
    with zipfile.ZipFile(out) as z:
        summary=json.loads(z.read('P2_OUT/P2_ONE_STEP_SUMMARY.json'))
        assert len(summary['per_case'])==2
        for desc in summary['per_case']:
            raw=z.read('P2_OUT/'+desc['trace_file'])
            assert hashlib.sha256(raw).hexdigest()==desc['trace_sha256']
            with np.load(io.BytesIO(raw)) as a:
                np.testing.assert_array_equal(a['xminus'],d['xminus'])
                if desc['channel']=='full':
                    np.testing.assert_array_equal(a['z_r_m'],np.full(n,1.75))
                    np.testing.assert_array_equal(a['z_s'],np.full(n,1.75))
    with pytest.raises(FileExistsError):pack(control,los,prior,inputs.sha_file(prior),out)

def test_control_cannot_substitute_for_independent_prior(tmp_path):
    p=tmp_path/'wrong.npz';np.savez(p,prior=np.zeros((979,4)))
    with pytest.raises(ValueError,match='INDEPENDENT_DR3_PRIOR'):
        pack(p,p,p,inputs.sha_file(p),tmp_path/'no.zip')
