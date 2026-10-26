import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from evidence_contract import (validate_source_qa,training_provenance,validate_training,
    verify_input_manifest,check_baseline,validate_alignment,fresh_output,METRICS)
from evidence_helpers import source_receipt,input_manifest
from office_transfer_core import sha256,load_lock

LOCK=Path(__file__).resolve().parents[1]/'lock.json'


@pytest.mark.parametrize('change',['status','lock','commit','nan','threshold','routes','count','archive','table'])
def test_prepare_evidence_fails_closed(tmp_path,change):
    table=tmp_path/'table';table.write_text('synthetic')
    path=tmp_path/'qa.json';qa=source_receipt(path,LOCK,table)
    assert validate_source_qa(path,LOCK,table)==qa
    if change=='status':qa['technical']='BLOCKED'
    elif change=='lock':qa['lock_sha256']='0'*64
    elif change=='commit':qa['source_commit']='0'*40
    elif change=='nan':qa['routes'][0]['model_vs_direct_los_max_abs']=float('nan')
    elif change=='threshold':qa['routes'][0]['model_vs_direct_los_max_abs']=.051
    elif change=='routes':qa['routes'][1]=qa['routes'][0].copy()
    elif change=='count':qa['routes'][0]['n_rf']+=1
    elif change=='archive':qa['routes'][0]['release_sha256']='0'*64
    else:table.write_text('modified')
    path.write_text(json.dumps(qa))
    with pytest.raises(ValueError):validate_source_qa(path,LOCK,table)


def test_model_train_prepare_chain(tmp_path):
    source=tmp_path/'source.json';source_receipt(source,LOCK)
    model=tmp_path/'model';model.write_bytes(b'not_deserialized')
    prov=training_provenance(source,LOCK)
    train=tmp_path/'train.json';qa={'status':'SOURCE_TRAINING_COMPLETE','model_sha256':sha256(model),'provenance':prov}
    train.write_text(json.dumps(qa))
    assert validate_training(model,train,source,LOCK)==prov
    model.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='TRAIN_QA'):validate_training(model,train,source,LOCK)
    qa['model_sha256']=sha256(model);qa['provenance']['source_qa_sha256']='f'*64
    train.write_text(json.dumps(qa))
    with pytest.raises(ValueError,match='TRAIN_QA'):validate_training(model,train,source,LOCK)


def test_frozen_target_inventory(tmp_path):
    data=tmp_path/'trace';data.write_bytes(b'synthetic')
    manifest=tmp_path/'manifest.json';inputs={'trace':data}
    digest=input_manifest(manifest,LOCK,inputs,'R2_aA_m0','full','B0')
    commit=load_lock(LOCK)['corridor_p2_commit']
    def verify(files=inputs,ch='full',h=digest):
        return verify_input_manifest(manifest,h,files,'R2_aA_m0',ch,'B0',commit)
    assert verify()['trace']['sha256']==sha256(data)
    with pytest.raises(ValueError,match='MANIFEST_SHA'):verify(h='0'*64)
    with pytest.raises(ValueError,match='IDENTITY'):verify(ch='los')
    with pytest.raises(ValueError,match='FILE_SET'):verify(files={})
    data.write_bytes(b'changed')
    with pytest.raises(ValueError,match='INPUT_SHA'):verify()


@pytest.mark.parametrize('change',['value','nan','duplicate','missing'])
def test_baseline_gate(change):
    score={key:1. for key in METRICS}
    row=dict(score,case='R2_aA_m0',channel='full',bias='B0',arm='BASE')
    reference=pd.DataFrame([row])
    assert check_baseline(score,reference,'R2_aA_m0','full','B0')['status']=='PASS'
    if change=='value':score['heading_rmse_deg']+=1e-6
    elif change=='nan':score['heading_rmse_deg']=float('nan')
    elif change=='duplicate':reference=pd.concat([reference,reference])
    else:reference=reference.iloc[:0]
    with pytest.raises(ValueError):check_baseline(score,reference,'R2_aA_m0','full','B0')


@pytest.mark.parametrize('change',['time','ids','fractional','truth','observation','packet'])
def test_alignment(change):
    t=np.array([0.,1.]);ids=np.array([0.,1.]);truth=np.zeros((2,3))
    obs=pd.DataFrame({'pose_id':[0,1]});pk=obs.copy()
    validate_alignment(t,ids,truth,obs,pk)
    if change=='time':t[1]=0
    elif change=='ids':ids[1]=0
    elif change=='fractional':ids[1]=.5
    elif change=='truth':truth[0,0]=np.nan
    elif change=='observation':obs.pose_id=[0,0]
    else:pk.pose_id=[0,2]
    with pytest.raises(ValueError):validate_alignment(t,ids,truth,obs,pk)


def test_fresh_output_preserves_existing_files(tmp_path):
    out=fresh_output(tmp_path/'out');file=out/'result';file.write_text('keep')
    with pytest.raises(ValueError,match='NO_OVERWRITE'):fresh_output(out)
    assert file.read_text()=='keep'


def test_fit_uses_checked_prepare_chain(tmp_path,monkeypatch):
    import office_transfer_cli as cli
    from test_core import build_frame,DummySource
    frame=build_frame(n=45)
    frame['pose_id']=frame.groupby('route').cumcount()
    frame['valid_for_training']=True;frame['los_exists']=True
    table=tmp_path/'source.csv';frame.to_csv(table,index=False)
    lock=load_lock(LOCK)
    for meta in lock['paths'].values():meta['rf_n']=45
    lock_path=tmp_path/'lock.json';lock_path.write_text(json.dumps(lock))
    source_qa=tmp_path/'source_qa.json';source_receipt(source_qa,lock_path,table)
    monkeypatch.setattr(cli,'verify_checkout',lambda *a:None)
    monkeypatch.setattr(cli,'load_source_ffd',lambda *a:DummySource())
    args=SimpleNamespace(audit_checkout=tmp_path,lock=lock_path,source_qa=source_qa,
                         source_table=table,out=tmp_path/'fit')
    cli.fit_office(args)
    assert validate_training(args.out/'OFFICE_TRAINED_MODELS.joblib',args.out/'OFFICE_TRAIN_QA.json',
                             source_qa,lock_path)['training_file_sha256']==sha256(table)
    table.write_text('tampered')
    args.out=tmp_path/'should_not_start'
    with pytest.raises(ValueError,match='TABLE_SHA'):cli.fit_office(args)
    assert not args.out.exists()
