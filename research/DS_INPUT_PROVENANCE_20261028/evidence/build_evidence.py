from pathlib import Path
import json, hashlib, shutil, importlib.util, subprocess
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

repo=Path(r'D:\SLAM_bot\DS_X1_X2_RESULTS_COMMIT_20261026')
out=repo/'research/DS_INPUT_PROVENANCE_20261028'
base=Path(r'D:\SLAM_bot\OFFICE_CORRIDOR_TRANSFER_FIX_20261026\execution_33e9849')
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source_map=json.loads((out/'INPUT_SOURCE_MAP.json').read_text())
(out/'evidence').mkdir(exist_ok=True)
for source,name in [(base/'p2_artifacts/prepared/experiment.py','power_oof_experiment.py'),
                    (base/'p2_artifacts/prepared/TRAIN_FOLD_RECEIPTS.json','TRAIN_FOLD_RECEIPTS.json'),
                    (base/'p2/research/PJ_DS_GATED_20261021/mu_recursive.py','mu_recursive.py'),
                    (base/'p2/research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json','P0_INPUT_MANIFEST.json')]:
    target=out/'evidence'/name
    shutil.copy2(source,target)
    if not any(x['name']==name for x in source_map['files']):
        source_map['files'].append(dict(name=name,source_path=str(source),repo_path=target.relative_to(repo).as_posix(),sha256=sha(source),bytes=source.stat().st_size,new_in_this_package=True))
(out/'INPUT_SOURCE_MAP.json').write_text(json.dumps(source_map,indent=2)+'\n')
feature=pd.read_csv(out/'prepared/OBSERVATION_FEATURES_LABELS.csv.gz')
full=feature[feature.channel=='full']
folds=[]
receipts=json.loads((out/'evidence/TRAIN_FOLD_RECEIPTS.json').read_text())
for held in ('R2','R4','R5'):
    test=feature[feature.route==held]
    dist=cKDTree(test[['x_eval','y_eval']].to_numpy()).query(full[['x_eval','y_eval']].to_numpy())[0]
    power=full[(full.route!=held)&(dist>1e-4)]
    receipt=next(x for x in receipts if x['held_route']==held)
    trhash=hashlib.sha256(power[['case','pose_id','e_r','e_s']].to_csv(index=False).encode()).hexdigest()
    assert len(power)==receipt['train_n']
    mr=full[full.route!=held]
    folds.append(dict(held_route=held,power_train_rows=len(power),power_case_counts=power.groupby('case').size().to_dict(),power_m45_rows=int(power.case.str.endswith('_m45').sum()),power_training_receipt_count_match=True,power_training_receipt_hash_match=trhash==receipt['train_data_sha256'],original_in_memory_train_hash=receipt['train_data_sha256'],csv_reloaded_train_hash=trhash,hash_limitation='Original in-memory training serialization hash not reproduced from CSV; no claim of independent numerical fit reproduction. Original compressed input bytes separately verified.',mr_full_feature_case_counts=mr.groupby('case').size().to_dict(),mr_m45_rows=int(mr.case.str.endswith('_m45').sum()),mr_note='Training selector from mu_recursive.py; case pose_id coverage checked against source manifest below; no fitting performed'))
manifest=json.loads((out/'evidence/P0_INPUT_MANIFEST.json').read_text())
channels=[]
for c in manifest['cases']:
    path=base/'p2'/c['full_path']
    H=np.load(path,mmap_mode='r',allow_pickle=False)
    ids=pd.DataFrame(json.loads((base/'p2'/c['samples_path']).read_text())).pose_id.to_numpy(int)
    f=full[full.case==c['id']]
    assert len(ids)==len(H) and set(ids)==set(f.pose_id)
    channels.append(dict(case=c['id'],path=str(path),shape=list(H.shape),dtype=str(H.dtype),bytes=path.stat().st_size,sha256=sha(path)))
folder=(base/'p2'/manifest['cases'][0]['full_path']).parent
requested=[k+'_m45' for k in ('R2_aB','R4_aA','R4_aB','R5_aA','R5_aB')]
audit=dict(scope='Frozen staged source and prepared artifacts; not an exhaustive search of external archives or servers',full_rf_directory=str(folder),full_rf_directory_files=sorted(p.name for p in folder.glob('H_*.npy')),existing_channels=channels,requested_mount45=[dict(case=c,full_H_exists=(folder/('H_'+c+'.npy')).exists(),prepared_feature_rows=int((feature.case==c).sum())) for c in requested],folds=folds,regeneration='Requested five Full H absent in staged snapshot. Recover matching validated archive if available; otherwise generate Full RF from original Sionna scenario/mount convention and regenerate features/predictions.',fitting='No fit or simulation run. POWER and MR train on other routes; R2-held has no mount45 training, R4/R5-held includes R2_aA_m45. Refit original frozen training folds for new-case inference if fitted estimators unavailable. Adding new mount45 training data is a separately versioned experiment; never train on held target route.')
(out/'MOUNT45_AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
spec=importlib.util.spec_from_file_location('verify_inputs',out/'verify_inputs.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
validation=mod.verify()
(out/'VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n')
print(json.dumps({'validation':validation['status'],'folds':folds,'requested_mount45':audit['requested_mount45']},indent=2))
