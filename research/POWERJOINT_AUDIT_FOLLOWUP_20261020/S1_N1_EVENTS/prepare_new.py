"""Join preserved T2 inputs to actual release LoS observations. No recursive run."""
from pathlib import Path
import argparse,importlib.util,json,sys
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;SOURCE=HERE.parents[2]
AUDIT=SOURCE/'research/POWERJOINT_AUDIT_RERUN_20261020'
sys.path.insert(0,str(AUDIT/'T4_F1_EVENT'))
from run_events import load_npz,normalize,sha
sys.path.insert(0,str(AUDIT/'T2_NEW_ROUTE_BASELINE'))
from prepare_inputs import receipt_index

def main():
    p=argparse.ArgumentParser();p.add_argument('--route',required=True);p.add_argument('--t2-root',type=Path,required=True)
    p.add_argument('--release-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    request_path=SOURCE/'research/POWERJOINT_M45_COMPACT_20261019/01_ROUTE_REQUEST.json'
    request=json.loads(request_path.read_text());route=next(r for r in request['routes'] if r['id']==a.route)
    frequency=request['radio']['frequency_Hz'];freq=frequency['start']+frequency['step']*np.arange(frequency['count'])
    feature_path=SOURCE/'research/PHYSICS_RS_STAGED_20261015/code/features.py'
    spec=importlib.util.spec_from_file_location('s1_source_observer',feature_path)
    feature=importlib.util.module_from_spec(spec);spec.loader.exec_module(feature)
    expected,receipts=receipt_index(a.release_root);inputs={str(request_path):sha(request_path),str(feature_path):sha(feature_path)}
    items=[];pairings=[]
    for anchor in route['anchors']:
        cid=f'{a.route}_{anchor}_M45_FULL'
        fulls=[x for x in expected if x.name=='H_FULL.npy' and x.parent.name==cid]
        if len(fulls)!=1:raise ValueError('NONUNIQUE_RELEASE_CASE:'+cid)
        full=fulls[0];los=full.parent/'H_DIRECT_LOS.npy';flags=full.parent/'LOS_EXISTS.npy';radio=full.parent/'RADIO_POSE.csv'
        for path in [full,los,flags,radio]:
            if path not in expected or sha(path)!=expected[path]:raise ValueError('SOURCE_MEMBER_SHA:'+str(path))
            inputs[str(path)]=expected[path]
        rows=pd.read_csv(radio);ids=rows.pose_id.to_numpy(int)
        if not rows.pose_id.is_unique:raise ValueError('NONUNIQUE_POSE_ID')
        h=np.load(full,allow_pickle=False);l=np.load(los,allow_pickle=False);exists=np.load(flags,allow_pickle=False)
        if h.shape!=l.shape or h.shape!=(len(rows),257,2,2):raise ValueError('PAIR_ARRAY_SHAPE')
        if exists.shape!=(len(rows),) or not np.isin(exists,[0,1]).all():raise ValueError('ACTUAL_VISIBILITY_FLAGS')
        exists=exists.astype(bool)
        obs=pd.DataFrame(feature.extract(h[:,:,:,0],freq))
        # Extract the exact Native LoS observation only at explicitly visible rows.
        zlos=np.full((len(rows),2),np.nan)
        if exists.any():
            lf=pd.DataFrame(feature.extract(l[exists,:,:,0],freq))
            zlos[exists]=lf[['range_m','s_fp']].to_numpy()
        for bias,bias_dps in [('B0',0.),('L2',.2)]:
            paths=list(a.t2_root.rglob(f'{cid}_{bias}.npz'))
            if len(paths)!=1:raise ValueError('NONUNIQUE_T2_TRACE:'+cid+bias)
            path=paths[0];data=normalize(load_npz(path));ri=np.flatnonzero(data['radio_mask'])
            if not np.array_equal(data['radio_pose_ids'],ids):raise ValueError('EXACT_POSE_ID_PAIRING')
            if len(ri)!=len(rows) or not np.array_equal(data['t'][ri],rows.t_s.to_numpy(float)):raise ValueError('EXACT_RADIO_CLOCK')
            err=np.max(abs(data['truth'][ri,:2]-rows[['x_m','y_m']].to_numpy()))
            yaw=np.max(abs((data['truth'][ri,2]-np.radians(rows.yaw_body_deg)+np.pi)%(2*np.pi)-np.pi))
            if err>1e-12 or yaw>1e-12:raise ValueError('PAIR_COORDINATES')
            gap=float(np.max(abs(data['z'][ri]-obs[['range_m','s_fp']].to_numpy())))
            if gap>1e-10:raise ValueError('FULL_OBSERVER_PARITY')
            if not np.array_equal(exists,data['los_exists_at_radio']):raise ValueError('VISIBILITY_TRACE_PAIRING')
            merged=dict(data);merged['actual_los_z_at_radio']=zlos;merged['actual_los_exists_at_radio']=exists
            dest=a.out/(cid+'_'+bias+'.npz');np.savez_compressed(dest,**merged)
            case=dict(id=cid,anchor=request['scenes'][route['environment']]['anchors'][anchor],
                      mount_deg=request['motion']['mount_deg'],robot_z_m=request['motion']['z_m'])
            items.append(dict(case=case,bias=bias,bias_dps=bias_dps,npz=dest.name,historical_power1_trace=str(path.resolve()),
                              los_status='CERTIFIED_EXPLICIT_SOURCE_FLAGS',training_scope='all legacy routes; new held out'))
            pairings.append(dict(case=cid,bias=bias,n_radio=len(ri),coordinate_max_abs_difference_m=float(err),
                                 yaw_max_abs_difference_rad=float(yaw),full_observation_max_abs_difference=gap,
                                 blocked_los_rows=int((~exists).sum()),t2_sha256=sha(path),input_npz_sha256=sha(dest)))
            inputs[str(path)]=sha(path)
    (a.out/'BUNDLE.json').write_text(json.dumps(dict(cases=items),indent=2))
    (a.out/'PAIRING_RECEIPT.json').write_text(json.dumps(dict(inputs=inputs,source_receipts=receipts,pairings=pairings),indent=2))
    print('PREPARED_NEW_ACTUAL_LOS',a.route,len(items),flush=True)
if __name__=='__main__':main()
