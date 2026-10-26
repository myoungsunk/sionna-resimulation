import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from office_transfer_core import ResidualTransfer,sha256,load_lock
from corridor_control import outer_split,fit_control,load_control
from test_core import build_frame,DummySource


def test_outer_embargo_and_held_route_rejection():
    d=build_frame(routes=('R4','R5'),n=90);d['scene']='CORRIDOR'
    xy=d.iloc[[0]][['x_eval','y_eval']].to_numpy()
    kept,qa=outer_split(d,xy,'R2')
    assert qa['removed']==1 and len(kept)==179
    d.loc[0,'route']='R2'
    with pytest.raises(ValueError,match='HELD_ROUTE'):outer_split(d,xy,'R2')


def test_corridor_shared_learner_inner_oof_and_geometry():
    d=build_frame(routes=('R4','R5'),n=90);d['scene']='CORRIDOR'
    cases={c:{'id':c,'mount_deg':i*45,'anchor':[i,0,2.65],'robot_z_m':.45}
           for i,c in enumerate(d.case.unique())}
    seen=[]
    class Source(DummySource):
        def batch(self,states,case,gradient=False):
            seen.append(case['mount_deg']);return super().batch(states,case,gradient)
    model=ResidualTransfer.fit(d,Source(),scene='CORRIDOR',cases=cases)
    assert model.training_routes==('R4','R5') and set(seen)=={0,45}
    assert all(f['validation_route'] not in f['teacher_routes'] for f in model.fold_audit)
    assert model.pwide.get_params()['max_iter']==160
    assert model.pwide.get_params()['learning_rate']==.055
    assert model.predict(d.iloc[:3],np.zeros(3),'PWIDE').shape==(3,)
    # Near-identical teacher sites must be embargoed in BOTH inner folds.
    d.loc[d.route=='R5',['x_eval','y_eval']]=d.loc[d.route=='R4',['x_eval','y_eval']].to_numpy()
    with pytest.raises(ValueError,match='INNER_SOURCE_NOT_ENOUGH'):
        ResidualTransfer.fit(d,Source(),scene='CORRIDOR',cases=cases)


def test_fit_corridor_command_and_wrong_held_rejected(tmp_path,monkeypatch):
    import corridor_control as cc
    import office_transfer_cli as cli
    root=tmp_path/'source';art=tmp_path/'art';art.mkdir();root.mkdir()
    cases=[];inputs={};frames=[];observations=[]
    all_data=build_frame(routes=('R2','R4','R5'),n=90)
    for route,frame in all_data.groupby('route',sort=True):
        frame=frame.copy();name=route+'_case';frame['case']=name;frame['pose_id']=np.arange(len(frame))
        pose=pd.DataFrame({'pose_id':frame.pose_id,'x':frame.x_eval,'y':frame.y_eval,'yaw_body_deg':frame.yaw_body_deg})
        sample=root/(name+'.json');sample.write_text(pose.to_json(orient='records'))
        cases.append({'id':name,'route':route,'samples_path':sample.name,'anchor':[0,0,2.65],
                      'mount_deg':0 if route=='R4' else 45,'robot_z_m':.45})
        inputs[name+'/samples']=sample
        frame['range_m']=2.1;frame['channel']='full'
        frames.append(frame);observations.append(frame[['case','pose_id','channel','range_m','s_fp']])
    packets=root/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz';packets.parent.mkdir(parents=True)
    pd.concat(frames).to_csv(packets,index=False)
    obs=art/'OBSERVATION_FEATURES_LABELS.csv.gz';pd.concat(observations).to_csv(obs,index=False)
    manifest=root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json';manifest.parent.mkdir()
    manifest.write_text(json.dumps({'cases':cases}))
    inputs.update(observations=obs,packets=packets,cases=manifest)
    lock=Path(__file__).resolve().parents[1]/'lock.json'
    inventory=tmp_path/'input.json';inventory.write_text(json.dumps({'schema':'CORRIDOR_CONTROL_INPUTS_V1',
        'held':'R2','target_commit':load_lock(lock)['corridor_p2_commit'],
        'files':{k:sha256(v) for k,v in inputs.items()}}))
    out=tmp_path/'models'
    V=SimpleNamespace(ROOT=root,ART=art,OUT=out,MANIFEST={'cases':cases},one=lambda name:obs,SourceFFD=DummySource)
    def features(pk,ids):return pk.set_index('pose_id').loc[ids].reset_index(),None
    monkeypatch.setattr(cc,'verify_checkout',lambda *a:None)
    monkeypatch.setattr(cli,'load_p2_environment',lambda *a:SimpleNamespace(V=V,full_features=features))
    for key in ('PJ_SOURCE_ROOT','PJ_ART','PJ_OUT'):monkeypatch.delenv(key,raising=False)
    args=SimpleNamespace(lock=lock,target_checkout=root,target_artifacts=art,out=out,held='R2',
        input_manifest=inventory,input_manifest_sha256=sha256(inventory))
    fit_control(args)
    model=load_control(out/'R2_C_PWIDE.joblib',out/'R2_C_PWIDE_QA.json','R2',lock)
    assert model.training_routes==('R4','R5')
    with pytest.raises(ValueError,match='QA_MISMATCH'):
        load_control(out/'R2_C_PWIDE.joblib',out/'R2_C_PWIDE_QA.json','R4',lock)
    # Held labels do not affect training: poisoned held measurements are skipped.
    observed=pd.read_csv(obs);observed.loc[observed.case=='R2_case','s_fp']=np.nan
    observed.to_csv(obs,index=False)
    train,_,_=cc.build_training(cases,'R2',inputs,DummySource(),SimpleNamespace(full_features=features))
    assert set(train.route)=={'R4','R5'} and np.isfinite(train.e_s).all()
