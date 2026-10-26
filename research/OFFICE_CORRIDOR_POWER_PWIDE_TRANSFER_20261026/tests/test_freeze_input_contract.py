"""Synthetic frozen-manifest contract tests; does not execute RF fitting/replay."""
from pathlib import Path
import json
import numpy as np
import pytest

from freeze_input_contract import CASES, control_files, target_files, freeze, validate_control_origin
from office_transfer_core import sha256

LOCK=Path(__file__).resolve().parents[1]/'lock.json'


@pytest.fixture
def frozen_inputs(tmp_path,monkeypatch):
    root=tmp_path/'source';root.mkdir()
    art=tmp_path/'art';art.mkdir()
    case_rows=[]
    for name in CASES:
        route=name.split('_',1)[0]
        sample=root/f'samples/{name}.json';sample.parent.mkdir(exist_ok=True)
        sample.write_text('[{"pose_id":0}]',encoding='utf-8')
        los=root/f'los/{name}.npy';los.parent.mkdir(exist_ok=True)
        np.save(los,np.zeros((1,)))
        case_rows.append({'id':name,'route':route,
                          'samples_path':sample.relative_to(root).as_posix(),
                          'los_path':los.relative_to(root).as_posix()})
    origin=root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'
    origin.parent.mkdir(parents=True)
    origin.write_text(json.dumps({'cases':case_rows}),encoding='utf-8')
    for rel in ('research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz',
                'research/PJ_DS_GATED_20261021/results_strict/SB_SCORES.csv'):
        p=root/rel;p.parent.mkdir(parents=True);p.write_bytes(b'synthetic-fixture')
    for name in ('R2_aA_m45_full_B0_TRACE.npz','OBSERVATION_FEATURES_LABELS.csv.gz',
                 'OOF_PARAMETERS.csv.gz'):
        (art/name).write_bytes(b'example')
    monkeypatch.setattr('freeze_input_contract.verify_checkout',lambda *args,**kwargs: True)
    return root,art,tmp_path


def test_explicit_freeze_rechecks_training_provenance(frozen_inputs):
    root,art,base=frozen_inputs
    q=freeze(root,art,base/'frozen','R2','R2_aA_m45','full','B0',LOCK)
    assert q['training']=='NOT_RUN' and q['replay']=='NOT_RUN'
    assert len(control_files(root,art))==10
    assert len(target_files(root,art,'R2_aA_m45','full','B0'))==5
    held=q['control_manifest']
    qa=base/'corridor_qa.json'
    qa.write_text(json.dumps({'status':'CORRIDOR_CONTROL_TRAINED',
      'identity':{'held':'R2','input_manifest_sha256':sha256(held),
                  'lock_sha256':sha256(LOCK)}}),encoding='utf-8')
    assert validate_control_origin(root,art,held,qa,'R2',LOCK)['status']=='PASS'
    (art/'OBSERVATION_FEATURES_LABELS.csv.gz').write_bytes(b'changed')
    with pytest.raises(ValueError,match='CONTROL_TRAINING_INPUTS_CHANGED'):
        validate_control_origin(root,art,held,qa,'R2',LOCK)


def test_freeze_blocks_wrong_route_and_duplicate_artifacts(frozen_inputs):
    root,art,base=frozen_inputs
    with pytest.raises(ValueError,match='FROZEN_HELD_CASE_MISMATCH'):
        freeze(root,art,base/'bad','R5','R2_aA_m45','full','B0',LOCK)
    (art/'nested').mkdir()
    (art/'nested'/'OOF_PARAMETERS.csv.gz').write_bytes(b'duplicate')
    with pytest.raises(ValueError,match='FROZEN_ARTIFACT_NOT_UNIQUE'):
        freeze(root,art,base/'blocked','R2','R2_aA_m45','full','B0',LOCK)
    assert not (base/'blocked').exists()


def test_control_qa_wrong_held_blocks(frozen_inputs):
    root,art,base=frozen_inputs
    frozen=freeze(root,art,base/'frozen','R2','R2_aA_m45','full','B0',LOCK)
    qa=base/'corridor_qa.json'
    qa.write_text(json.dumps({'status':'CORRIDOR_CONTROL_TRAINED',
      'identity':{'held':'R4','input_manifest_sha256':frozen['control_manifest_sha256'],
                  'lock_sha256':sha256(LOCK)}}))
    with pytest.raises(ValueError,match='CONTROL_TRAINING_ORIGIN_SHA_MISMATCH'):
        validate_control_origin(root,art,frozen['control_manifest'],qa,'R2',LOCK)