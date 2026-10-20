"""Assemble verified T2 traces and Full-only features; never generate RF or GT features.

Reads existing release H_FULL and RADIO_POSE pose IDs only. Frequency and fixed
case geometry come from the pinned route request, not inferred from poses.
"""
from pathlib import Path
import argparse,importlib.util,json,os,shutil,sys,traceback
for key in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS'):os.environ[key]='1'
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'T2_NEW_ROUTE_BASELINE'))
from prepare_inputs import receipt_index,sha,BIAS_LEVELS
sys.path.insert(0,str(HERE.parent/'T4_F1_EVENT'))
from run_events import load_npz,normalize
from utility_policy import MEASURED,NEW_CASES


def one_identical(paths,label):
    paths=sorted(paths)
    if not paths:raise ValueError('BLOCKED_INPUT:MISSING_'+label)
    if len({sha(p) for p in paths})!=1:raise ValueError('NONIDENTICAL_DUPLICATE:'+label)
    return paths[0]


def preserve_copy(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists():
        if sha(dest)!=sha(source):raise ValueError('REFUSE_OVERWRITE_DIFFERENT_TRACE:'+str(dest))
    elif source.resolve()!=dest.resolve():shutil.copy2(source,dest)
    if sha(dest)!=sha(source):raise ValueError('TRACE_COPY_SHA')


def main():
    p=argparse.ArgumentParser();p.add_argument('--t2-root',type=Path,required=True)
    p.add_argument('--release-root',type=Path,required=True);p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--request',type=Path);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    request_path=args.request or args.source_root/'research/POWERJOINT_M45_COMPACT_20261019/01_ROUTE_REQUEST.json'
    inputs={str(Path(__file__)):sha(Path(__file__))};items=[];records=[];errors=[]
    try:
        inputs[str(request_path)]=sha(request_path)
        request=json.loads(request_path.read_text(encoding='utf-8'))
        f=request['radio']['frequency_Hz'];freq=f['start']+f['step']*np.arange(f['count'])
        if f['count']!=257:raise ValueError('PINNED_FREQUENCY_COUNT_CHANGED')
        measured_path=args.source_root/'research/PHYSICS_RS_STAGED_20261015/code/features.py'
        spec=importlib.util.spec_from_file_location('assembly_original_measured_features',measured_path)
        measured=importlib.util.module_from_spec(spec);spec.loader.exec_module(measured)
        if list(measured.FEATURES)!=MEASURED:raise ValueError('PINNED_FEATURE_SCHEMA_CHANGED')
        inputs[str(measured_path)]=sha(measured_path)
        expected,receipts=receipt_index(args.release_root)
        inputs.update({r['path']:r['sha256'] for r in receipts})
        routes={r['id']:r for r in request['routes']}
        for cid in sorted(NEW_CASES):
            route,anchor_name=cid.split('_')[:2]
            full_path=one_identical([p for p in expected if p.name=='H_FULL.npy' and p.parent.name==cid],cid+'_H_FULL')
            radio_path=one_identical([p for p in expected if p.name.endswith('RADIO_POSE.csv') and p.parent==full_path.parent],cid+'_RADIO_POSE')
            for path in (full_path,radio_path):
                if sha(path)!=expected[path]:raise ValueError('RELEASE_MEMBER_SHA:'+str(path))
                inputs[str(path)]=expected[path]
            # Read only immutable RF row identifiers; no pose/error columns used as features.
            radio=pd.read_csv(radio_path,usecols=['pose_id']);ids=radio.pose_id.to_numpy(int)
            if not radio.pose_id.is_unique:raise ValueError('DUPLICATE_RELEASE_RF_ID')
            h=np.load(full_path,mmap_mode='r',allow_pickle=False)
            if h.shape!=(len(ids),257,2,2):raise ValueError('RELEASE_FULL_H_SHAPE')
            # Exactly the original CHAIN/T2 extractor and TX LP+ column.
            feature=pd.concat([pd.DataFrame(measured.extract(h[i:i+64,:,:,0],freq)) for i in range(0,len(h),64)],ignore_index=True)
            feature['case']=cid;feature['pose_id']=ids
            feature_path=args.out/'features'/(cid+'_FULL_FEATURES.csv');feature_path.parent.mkdir(exist_ok=True)
            feature.to_csv(feature_path,index=False)
            environment=routes[route]['environment']
            if anchor_name not in routes[route]['anchors']:raise ValueError('REQUEST_ANCHOR_MISMATCH')
            case=dict(id=cid,anchor=request['scenes'][environment]['anchors'][anchor_name],
                      mount_deg=request['motion']['mount_deg'],robot_z_m=request['motion']['z_m'])
            for label,bias in BIAS_LEVELS.items():
                trace_path=one_identical(list(args.t2_root.rglob(f'{cid}_{label}.npz')),cid+'_'+label)
                receipt_path=trace_path.parent.parent/'MANIFEST.json'
                receipt=json.loads(receipt_path.read_text(encoding='utf-8'))
                if receipt.get('technical')!='TECHNICAL_PASS' or receipt.get('route')!=route:
                    raise ValueError('T2_NOT_CERTIFIED_ROUTE:'+str(receipt_path))
                inputs[str(receipt_path)]=sha(receipt_path);inputs[str(trace_path)]=sha(trace_path)
                data=normalize(load_npz(trace_path))
                if not np.array_equal(data['radio_pose_ids'],ids):raise ValueError('T2_RELEASE_RF_ID_MISMATCH')
                if int(data['radio_mask'].sum())!=len(ids):raise ValueError('T2_RF_MASK_COUNT')
                delta=float(np.max(abs(data['z'][data['radio_mask']]-feature[['range_m','s_fp']].to_numpy())))
                if delta>1e-10:raise ValueError('T2_RELEASE_OBSERVATION_PARITY:'+str(delta))
                target=args.out/'traces'/trace_path.name;preserve_copy(trace_path,target)
                items.append(dict(case=case,bias=label,bias_dps=bias,npz=str(target.relative_to(args.out)).replace('\\','/'),
                                  features=str(feature_path.relative_to(args.out)).replace('\\','/')))
                records.append(dict(case=cid,bias=label,trace_sha256=sha(target),feature_sha256=sha(feature_path),
                                    H_full_sha256=expected[full_path],radio_ids_sha256=expected[radio_path],
                                    observation_max_abs_difference=delta,t2_actions_run_id=receipt.get('actions_run_id'),
                                    n_radio=len(ids),n_motion=len(data['t'])))
            print('ASSEMBLED_EXISTING_NEW_INPUT',cid,flush=True)
        if len(items)!=36:raise ValueError('EXPECTED_9_CASES_X_4_BIASES')
        for file in (args.out/'features').glob('*.csv'):
            if file.stat().st_size>20_000_000:raise ValueError('FEATURE_CSV_EXCEEDS_20MB:'+file.name)
        (args.out/'NEW_CASES.json').write_text(json.dumps(dict(range_model='B_OLD',sensor_seed=0,cases=items),indent=2),encoding='utf-8')
    except Exception as exc:errors.append(dict(error=str(exc),traceback=traceback.format_exc(),retry=False))
    pd.DataFrame(records).to_csv(args.out/'ASSEMBLY_RECEIPT.csv',index=False)
    (args.out/'ERRORS.json').write_text(json.dumps(errors,indent=2),encoding='utf-8')
    manifest=dict(task='T7B_NEW_INPUT_ASSEMBLY',technical='TECHNICAL_PASS' if not errors else 'ERROR_OR_BLOCKED_INPUT',
                  inputs=inputs,actions_run_id=os.getenv('GITHUB_RUN_ID'),artifact_id=None,
                  outputs={str(p.relative_to(args.out)).replace('\\','/'):sha(p) for p in args.out.rglob('*') if p.is_file() and p.name!='MANIFEST.json'},
                  note='Existing H_FULL extraction and byte-preserving T2 copies only; no RF generation, sensor rerun, GT features or NativeLoS H read')
    (args.out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
