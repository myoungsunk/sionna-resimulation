import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
import evidence_contract as E
import office_mount_inputs as M
import office_transfer_cli as CLI
from office_transfer_core import augment_d0, sha256, load_lock

LOCK=Path(__file__).resolve().parents[1]/'lock.json'

def source(tmp_path, monkeypatch):
    folder=tmp_path/'prepared';folder.mkdir()
    rows=[];routes=[]
    for mount in (0,45):
        for route in ('O01','O02','O03'):
            case=f'{route}_O0_M{mount}_FULL'
            rows.append(dict(case=case,route=route,mount_deg=mount,pose_id=0,scene='OFFICE_E',
                valid_for_training=True,los_exists=True,log_fp_power=-2.,e_r=.1,e_s=.2,d0_gt_source=.2))
            routes.append(dict(case=case,route=route,mount_deg=mount,n_rf=1,n_train_valid=1))
    table=folder/'OFFICE_SOURCE_LABELS.csv.gz';pd.DataFrame(rows).to_csv(table,index=False)
    manifest=tmp_path/'INPUT_MANIFEST.json'
    manifest.write_text(json.dumps({'original_45_lock_sha256':sha256(LOCK)}))
    qa=folder/'OFFICE_SOURCE_QA.json'
    qa.write_text(json.dumps(dict(technical='SOURCE_DATASET_PREPARED_MOUNT_0_45',
        source_commit=load_lock(LOCK)['source_audit_commit'],input_manifest_sha256=sha256(manifest),
        outputs_sha256={table.name:sha256(table)},routes=routes,valid_training_rows=6)))
    def check(output, path, expected):
        assert output==folder and path==manifest
        if sha256(path)!=expected:raise ValueError('MANIFEST_HASH_CHANGED')
    monkeypatch.setattr(M,'validate_outputs',check)
    return table,qa,manifest

def test_joint_qa_binds_manifest_and_actual_table(tmp_path,monkeypatch):
    table,qa,manifest=source(tmp_path,monkeypatch)
    result=E.validate_source_qa(qa,LOCK,table)
    assert result['label_file_sha256']==sha256(table)
    table.write_bytes(b'changed')
    with pytest.raises(ValueError,match='SOURCE_TABLE_SHA'):E.validate_source_qa(qa,LOCK,table)

def test_joint_qa_rechecks_frozen_manifest(tmp_path,monkeypatch):
    table,qa,manifest=source(tmp_path,monkeypatch)
    doc=json.loads(manifest.read_text());doc['extra']='changed';manifest.write_text(json.dumps(doc))
    with pytest.raises(ValueError,match='MANIFEST_HASH_CHANGED'):E.validate_source_qa(qa,LOCK,table)

def test_mount0_and45_prior_augmentation_use_actual_cases():
    frame=pd.DataFrame(dict(case=['zero','fortyfive'],route=['O01','O01'],x_eval=[1.,1.],
        y_eval=[2.,2.],yaw_body_deg=[0.,0.],s_fp=[.3,.4]))
    class Model:
        def __init__(self):self.mounts=[]
        def batch(self,states,case,gradient=False):
            self.mounts.append(case['mount_deg'])
            return np.zeros((len(states),2)),None
    model=Model();cases={'zero':{'mount_deg':0},'fortyfive':{'mount_deg':45}}
    rows,d0=augment_d0(frame,model,np.random.default_rng(1),3,cases)
    assert sorted(model.mounts)==[0,45]
    assert np.array_equal(d0,frame.s_fp.to_numpy()[rows])

def test_fit_accepts_shared_route_pose_ids_but_passes_mount_mapping(tmp_path,monkeypatch):
    table,qa,manifest=source(tmp_path,monkeypatch)
    monkeypatch.setattr(CLI,'verify_checkout',lambda *a:None)
    monkeypatch.setattr(CLI,'load_source_ffd',lambda *a:object())
    monkeypatch.setattr(CLI.PowerTransfer,'fit',lambda *a:SimpleNamespace())
    captured={}
    def residual(frame,model,cases=None):
        captured.update(cases)
        return SimpleNamespace(gate_tau_d0=.2,medians=pd.Series([0.],index=['log_fp_power']))
    monkeypatch.setattr(CLI.ResidualTransfer,'fit',residual)
    out=tmp_path/'models'
    CLI.fit_office(SimpleNamespace(audit_checkout=tmp_path,source_table=table,source_qa=qa,lock=LOCK,out=out))
    result=json.loads((out/'OFFICE_TRAIN_QA.json').read_text())
    assert result['training_rows']==6 and result['source_mounts']==[0,45]
    assert len(captured)==6
    assert captured['O01_O0_M0_FULL']['mount_deg']==0
    assert captured['O01_O0_M45_FULL']['mount_deg']==45
