"""Route-held-out Corridor residual control using the Office learner definition."""
import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from office_transfer_core import load_lock,sha256,ResidualTransfer,P_FEATURES
from evidence_contract import fresh_output,execution_record,read_json
from runtime_contract import verify_checkout,configure_replay,verify_replay_bindings

DEFINITION='POWER_INNER_OOF_MODEL_GT_RESIDUAL_HGB160_U20X3_V1'


def inventory(args,root,cases,V):
    inputs={'observations':Path(V.one('OBSERVATION_FEATURES_LABELS.csv.gz')),
            'packets':root/'research/PJ_DS_GATED_20261021/results_hpath/HP_PACKETS.csv.gz',
            'cases':root/'research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json'}
    if not inputs['observations'].resolve().is_relative_to(Path(args.target_artifacts).resolve()):
        raise ValueError('OBSERVATIONS_OUTSIDE_ARTIFACT_ROOT')
    for case in cases:
        path=(root/case['samples_path']).resolve()
        if not path.is_relative_to(root):raise ValueError('SAMPLE_PATH_ESCAPE')
        inputs[case['id']+'/samples']=path
    doc=read_json(args.input_manifest)
    if (sha256(args.input_manifest)!=args.input_manifest_sha256 or
            doc.get('schema')!='CORRIDOR_CONTROL_INPUTS_V1' or doc.get('held')!=args.held or
            doc.get('target_commit')!=load_lock(args.lock)['corridor_p2_commit'] or
            set(doc.get('files',{}))!=set(inputs)):
        raise ValueError('CORRIDOR_INPUT_MANIFEST_MISMATCH')
    for name,path in inputs.items():
        if doc['files'][name]!=sha256(path):raise ValueError('CORRIDOR_INPUT_SHA_MISMATCH:'+name)
    return inputs


def outer_split(frame,held_xy,held):
    if held not in ('R2','R4','R5'):raise ValueError('UNKNOWN_HELD_ROUTE')
    if set(frame.route)!={'R2','R4','R5'}-{held}:
        raise ValueError('HELD_ROUTE_OR_MISSING_TRAIN_ROUTE')
    distance=cKDTree(held_xy).query(frame[['x_eval','y_eval']].to_numpy(float))[0]
    kept=frame.loc[distance>1e-4].copy().reset_index(drop=True)
    if set(kept.route)!=set(frame.route):raise ValueError('OUTER_EMBARGO_EMPTY_ROUTE')
    return kept,{'before':len(frame),'after':len(kept),'removed':int((distance<=1e-4).sum()),
                 'threshold_m':1e-4,'held':held}


def build_training(cases,held,inputs,model,R2):
    obs=pd.read_csv(inputs['observations']);pk=pd.read_csv(inputs['packets'])
    frames=[];held_xy=[];mapping={}
    for case in cases:
        pose=pd.DataFrame(read_json(inputs[case['id']+'/samples']))
        if not pose.pose_id.is_unique or not np.isfinite(pose[['x','y','yaw_body_deg']]).all().all():
            raise ValueError('CORRIDOR_POSE_INVALID')
        if case['route']==held:
            held_xy.append(pose[['x','y']].to_numpy(float));continue
        ids=pose.pose_id.to_numpy()
        packets=pk[pk.case==case['id']]
        observations=obs[(obs.case==case['id'])&(obs.channel=='full')]
        if not packets.pose_id.is_unique or not observations.pose_id.is_unique:
            raise ValueError('CORRIDOR_DUPLICATE_INPUT')
        features,_=R2.full_features(packets,ids)
        f=observations.set_index('pose_id').loc[ids]
        z=f[['range_m','s_fp']].to_numpy(float)
        if not np.isfinite(z).all() or not np.allclose(features['sF_+0'],z[:,1],atol=1e-9,rtol=0):
            raise ValueError('CORRIDOR_OBSERVER_PARITY')
        state=np.c_[pose.x,pose.y,np.radians(pose.yaw_body_deg),np.zeros(len(pose))]
        pred=np.concatenate([model.batch(state[k:k+64],case,gradient=False)[0] for k in range(0,len(state),64)])
        d=features.reset_index(drop=True).copy()
        d['case']=case['id'];d['route']=case['route'];d['scene']='CORRIDOR';d['pose_id']=ids
        d['x_eval']=pose.x.to_numpy();d['y_eval']=pose.y.to_numpy();d['yaw_body_deg']=pose.yaw_body_deg.to_numpy()
        d['s_fp']=z[:,1];d['e_r']=z[:,0]-pred[:,0];d['e_s']=z[:,1]-pred[:,1];d['d0_gt_source']=d.e_s
        if not np.isfinite(d[['e_r','e_s','log_fp_power']]).all().all():raise ValueError('CORRIDOR_TRAIN_NONFINITE')
        frames.append(d);mapping[case['id']]=case
    train,audit=outer_split(pd.concat(frames,ignore_index=True),np.concatenate(held_xy),held)
    return train,mapping,audit


def fit_control(args):
    from office_transfer_cli import load_p2_environment,save_json
    root=Path(args.target_checkout).resolve();lock=load_lock(args.lock)
    verify_checkout(root,lock['corridor_p2_commit'],'TARGET_P2')
    out=fresh_output(args.out)
    runtime=configure_replay(root,args.target_artifacts,out)
    R2=load_p2_environment(root);verify_replay_bindings(R2.V,runtime)
    cases=[c for c in R2.V.MANIFEST['cases'] if c['route'] in ('R2','R4','R5')]
    inputs=inventory(args,root,cases,R2.V)
    train,cases_by_id,embargo=build_training(cases,args.held,inputs,R2.V.SourceFFD(),R2)
    residual=ResidualTransfer.fit(train,R2.V.SourceFFD(),scene='CORRIDOR',cases=cases_by_id)
    identity={'definition':DEFINITION,'held':args.held,'train_routes':sorted(train.route.unique()),
              'input_manifest_sha256':args.input_manifest_sha256,'lock_sha256':sha256(args.lock)}
    inventory(args,root,cases,R2.V)
    path=out/f'{args.held}_C_PWIDE.joblib'
    joblib.dump({'RESIDUAL':residual,'identity':identity},path,compress=3)
    save_json(out/f'{args.held}_C_PWIDE_QA.json',{'status':'CORRIDOR_CONTROL_TRAINED','identity':identity,
        'model_sha256':sha256(path),'outer_embargo':embargo,'inner_folds':residual.fold_audit,
        'training_rows':len(train),'features':P_FEATURES+['d0'],'execution':execution_record(args.lock),
        'target_labels_used':False,'held_geometry_use':'spatial embargo only','runtime_paths':runtime})


def load_control(model_path,qa_path,held,lock_path):
    qa=read_json(qa_path);identity=qa.get('identity',{})
    if (qa.get('status')!='CORRIDOR_CONTROL_TRAINED' or qa.get('model_sha256')!=sha256(model_path) or
            identity.get('definition')!=DEFINITION or identity.get('held')!=held or
            set(identity.get('train_routes',[]))!={'R2','R4','R5'}-{held} or
            identity.get('lock_sha256')!=sha256(lock_path)):
        raise ValueError('CORRIDOR_CONTROL_QA_MISMATCH')
    package=joblib.load(model_path);model=package['RESIDUAL']
    if (package.get('identity')!=identity or model.training_scene!='CORRIDOR' or
            set(model.training_routes)!=set(identity['train_routes'])):
        raise ValueError('CORRIDOR_CONTROL_MODEL_MISMATCH')
    return model
