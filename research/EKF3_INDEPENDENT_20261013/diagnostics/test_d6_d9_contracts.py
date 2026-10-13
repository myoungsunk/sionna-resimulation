"""Independent contract tests; no full frozen RF runs and no output overwrite."""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np
import pytest

from d6_d9_common import (FROZEN_BLOB_SHA1, atomic_json,
                          check_frozen_baseline_files, finish,
                          json_safe, make_out, write_csv)
from d8_polarization_quality import (RANGE_LABELS, fit_ridge,
                                      phase_evidence, predict_mean,
                                      predict_variance)
from d9_quality_aware_fusion import (METHODS, covariance_for,
                                     enforce_d5_baseline)


def test_all_entrypoints_import_cleanly_without_radio_execution():
    import d6_nonlinearity_mc  # noqa: F401
    import d6_d5_trace_audit  # noqa: F401
    import d6_bias_observability  # noqa: F401
    import d7_cir_multipath_audit  # noqa: F401
    import d8_polarization_quality  # noqa: F401
    import d9_quality_aware_fusion  # noqa: F401


def test_frozen_original_code_blob_hashes_match_published_base():
    evidence=check_frozen_baseline_files()
    assert evidence==FROZEN_BLOB_SHA1
    assert len(evidence)==5


def test_strict_json_safe_and_numpy_path_serialization():
    value={'local':Path('Windows/path'), 'nested': {'np':np.float64(1.2),
           'n':np.int64(3), 'vector':np.array([1,2,3]), 'bool':np.bool_(True)}}
    enc=json_safe(value)
    assert enc['local']==str(Path('Windows/path'))
    assert enc['nested']['vector']==[1,2,3]
    assert enc['nested']['bool'] is True
    json.dumps(enc,allow_nan=False)
    with pytest.raises(TypeError):json_safe({'unsupported':object()})
    with pytest.raises(ValueError):json_safe({'nan':float('nan')})


def test_atomic_manifest_and_no_partial_success(tmp_path):
    out=make_out(tmp_path/'D8_SMOKE')
    f=out/'dummy.csv'
    write_csv(f,[{'a':1,'b':2}])
    finish(out,'D8',{'path':Path('C:/test/data'),
                     'numeric':np.float64(.125)},[f],caveats=['TEST_ONLY'])
    man=out/'D8_MANIFEST.json'
    raw=json.loads(man.read_text(encoding='utf-8'))
    assert raw['config']['path']==str(Path('C:/test/data'))
    assert raw['sha256']['dummy.csv']
    assert raw['code_sha256']['d6_d9_common.py']
    assert 'execution_commit' in raw
    assert raw['status']=='EXECUTED_EXPLORATORY_ONLY'
    assert raw['scientific_PASS'] is False
    with pytest.raises(FileExistsError):finish(out,'D8',{},[f])
    assert json.loads(man.read_text(encoding='utf-8'))==raw
    out2=make_out(tmp_path/'FAILED')
    file=out2/'dummy.csv'
    write_csv(file,[{'a':1}])
    with pytest.raises(TypeError):finish(out2,'D9',{'bad':object()},[file])
    assert not (out2/'D9_MANIFEST.json').exists()
    assert not list(out2.glob('*.part'))
    with pytest.raises(FileExistsError):make_out(out)


def test_range_correction_mismatch_blocks_covariance_application():
    train=[{'s_fp':float(k)/100,
            'error_s':.03+.01*(k%5),
            'error_range_B_OLD_m':.10+.03*(k%7),
            'error_range_E1_FULL_LORO_m':-.02+.005*(k%7)}
            for k in range(100)]
    qs={target:fit_ridge(train,target,'Q1_S_ONLY',10.,'B_OLD')
        for target in ('s','r')}
    # Covariance selector expects strict Q3. The schema must still reject
    # a train-on-B_OLD model claiming to match E1.
    fold={'range_model':'E1_FULL_LORO',
          'range_target':RANGE_LABELS['E1_FULL_LORO'],
          'models':{'Q3_CIR_POL':qs}}
    with pytest.raises(RuntimeError, match='mismatch|different residual'):
        covariance_for({'s_fp':.1},fold,'F3_CIR_R')
    e1={target:fit_ridge(train,target,'Q1_S_ONLY',10.,'E1_FULL_LORO')
        for target in ('s','r')}
    fold['models']['Q3_CIR_POL']=e1
    rs,rr,rsr,mean_s,mean_r=covariance_for({'s_fp':.1},fold,'F3_CIR_R')
    assert rs>0 and rr>0 and rsr==0.
    assert math.isfinite(mean_s) and math.isfinite(mean_r)
    assert rr==predict_variance({'s_fp':.1},e1['r'])
    assert mean_r==predict_mean({'s_fp':.1},e1['r'])
    with pytest.raises(RuntimeError,match='R_sr'):
        covariance_for({'s_fp':.1},fold,'F3_CIR_R',True)
    assert covariance_for({},fold,'F0_ORIGINAL')[-2:]==(0.,0.)


def test_phase_requires_external_independent_receiver_evidence(tmp_path):
    assert phase_evidence(None) is None
    missing=tmp_path/'phase.json'
    missing.write_text(json.dumps({'independent_rx_phase_calibration':True}),encoding='utf-8')
    with pytest.raises(RuntimeError,match='calibration'):
        phase_evidence(missing)


def baseline_record(case='R2_aA_m0'):
    return {'case':case,'channel':'full','condition':'noise_pair','level':0,
            'seed':0,'range_model':'B_OLD','arm':'C','n':10,
            'heading_rmse_deg':1.,'xy_rmse_m':.2,'mean_pose_NEES':2.,
            'mean_heading_NEES':1.,'pose95':.8,
            'accepted_updates':9,'rejected_updates':1}


def test_d5_parity_requires_every_requested_cell_and_rejects_duplicates(tmp_path):
    a=baseline_record()
    ref=tmp_path/'frozen_D5.csv'
    with ref.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(a));w.writeheader();w.writerow(a)
    result=[{**a,'method':'F0_ORIGINAL'}]
    x=enforce_d5_baseline(result,ref,range_model='B_OLD')
    assert x['status']=='ALL_REQUESTED_F0_CELLS_MATCHED'
    assert x['compared']==x['expected']==1
    with pytest.raises(RuntimeError,match='MISSING'):
        enforce_d5_baseline(result+[{**result[0],'case':'R2_aB_m0'}],ref,
                            range_model='B_OLD')
    with pytest.raises(RuntimeError,match='Duplicate new'):
        enforce_d5_baseline(result+result,ref,range_model='B_OLD')
    with pytest.raises(RuntimeError,match='parity'):
        enforce_d5_baseline([{**result[0],'heading_rmse_deg':5.}],ref,
                            range_model='B_OLD')


def test_methods_explicitly_preserve_f0_and_only_q3_quality_arms():
    assert METHODS['F0_ORIGINAL']==(False,False,False)
    assert all(METHODS[m][2] for m in ('F3_CIR_R','F4_UT_CIR_R',
                                       'F5_BIAS4_CIR_R','F6_UT_BIAS4_CIR_R'))
