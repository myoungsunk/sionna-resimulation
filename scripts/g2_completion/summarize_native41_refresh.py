"""Export native RF observables, retained paths, comparisons, and a checked consumer binding."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from rt_cp_uwb_py.g2_native_channel import file_sha,load_native_link
from rt_cp_uwb_py.g2_native_summary import summarize_paths,load_native_refresh
from rt_cp_uwb_py.g2_scoped_channel import ARMS


def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,allow_nan=False),encoding='utf8')
def csv_write(p,rows):
    with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);a=ap.parse_args()
    root=a.root.resolve();production=root/'production'
    c=read(root/'CONFIG.json');geometry=Path(c['geometry_root'])
    previous=Path(c['source_native_revision'])/'production_v2'
    assert read(root/'CONSUMER_RECEIPT.json')['status']=='NATIVE_PIPELINE_PASS'
    assert c['solver']['los'] is True
    features,labels,frequency_stats,comparison,path_records=[],[],[],[],[]
    for row in c['rows']:
        key=row['link_id'];got=load_native_link(production,key)
        detail,data=got['result'],got['channel']
        old=load_native_link(previous,key)['channel']
        direct_values=set()
        with np.load(root/'native_raw'/(key+'_NATIVE.npz')) as z:
            mid={}
            for fi,f in enumerate(z['frequencies_hz']):
                for arm in ARMS:
                    coef=z[f'{arm}_a_{fi:03d}'];tau=z[f'{arm}_tau_{fi:03d}']
                    events=z[f'{arm}_interactions_{fi:03d}'];valid=z[f'{arm}_valid_{fi:03d}']
                    summary=summarize_paths(coef,tau,events,valid)
                    direct_values.add(summary['native_los_present'])
                    frequency_stats.append(dict(link_id=key,arm=arm,bin=fi,frequency_hz=float(f),**summary))
                    if fi!=128:continue
                    mid[arm]=summary
                    n=len(tau);ev=events.reshape(3,n);mask=valid.reshape(-1)
                    xyz=z[f'{arm}_vertices_128'].reshape(3,n,3)
                    objects=z[f'{arm}_objects_128'].reshape(3,n)
                    primitives=z[f'{arm}_primitives_128'].reshape(3,n)
                    for pi in np.flatnonzero(mask):
                        steps=[]
                        for depth in range(3):
                            event=int(ev[depth,pi])
                            if event==0:continue
                            oid=int(objects[depth,pi])
                            steps.append(dict(event_code=event,object_id=oid,
                                object_name=detail['object_indices'].get(str(oid)),
                                primitive_id=int(primitives[depth,pi]),point_m=xyz[depth,pi].tolist()))
                        path_records.append(dict(link_id=key,arm=arm,frequency_bin=128,
                            path_index=int(pi),frequency_hz=float(f),tx_m=row['tx'],rx_m=row['rx'],
                            delay_s=float(tau[pi]),coefficient_real=coef[:,:,pi].real.tolist(),
                            coefficient_imag=coef[:,:,pi].imag.tolist(),steps=steps))
        consistent=len(direct_values)==1
        label=dict(link_id=key,scene_id=row['scene_id'],NoLoS=not next(iter(direct_values)) if consistent else None,
            NoLoS_status='NATIVE_GEOMETRIC_LOS_CONSISTENT_ALL_BINS_AND_ARMS' if consistent else 'INCONSISTENT_NATIVE_LOS_MEMBERSHIP',
            RD_LoS=None,HB_near_delay=None,HB_prior=None,taxonomy_status='RD_HB_DEFERRED_BY_USER',
            definition='NoLoS is absence of a valid zero-interaction native LoS path; not inferred from detector timing or range error',
            native_paths_sha256=detail['native_paths_sha256'])
        labels.append(label)
        for detection in detail['detections']:
            arm=detection['arm']
            features.append(dict(link_id=key,scene_id=row['scene_id'],NoLoS=label['NoLoS'],
                **detection,**{('midband_'+k):v for k,v in mid[arm].items()}))
            before=old[arm+'_H'];after=data[arm+'_H']
            difference=np.linalg.norm(after-before);denom=np.linalg.norm(before)
            comparison.append(dict(link_id=key,arm=arm,
                H_relative_l2_change=float(difference/denom) if denom else None,
                H_max_absolute_change=float(np.max(abs(after-before))),
                clean_CIR_max_absolute_change=float(np.max(abs(data[arm+'_CIR_clean']-old[arm+'_CIR_clean']))),
                identical_noise=bool(np.array_equal(old['noise_H'],data['noise_H']))))
    assert len(features)==123 and len(frequency_stats)==31611 and len(labels)==41
    assert all(r['identical_noise'] for r in comparison),'PAIRED_NOISE_CHANGED'
    csv_write(root/'FEATURES.csv',features)
    csv_write(root/'FREQUENCY_PATH_METRICS.csv',frequency_stats)
    csv_write(root/'CHANNEL_COMPARISON.csv',comparison)
    write(root/'LABELS.json',labels)
    with (root/'MIDBAND_PATHS.jsonl').open('w',encoding='utf8') as f:
        for row in path_records:f.write(json.dumps(row,allow_nan=False)+'\n')
    binding=dict(status='NATIVE_REFRESH_COMPLETE',scope='41 relocated rows only',
        production_root=str(production),geometry_root=str(geometry),labels_file=str(root/'LABELS.json'),
        geometry_model='native air-slab-air reference sheets; hollow-column synthetic geometry',
        link_ids=[r['link_id'] for r in c['rows']],consumer='rt_cp_uwb_py.g2_native_summary.load_native_refresh',
        bound_files=[dict(path=str(p),sha256=file_sha(p)) for p in
            [production/'MANIFEST.json',root/'CONFIG.json',geometry/'SCENE_MESH_MANIFEST.json',
             geometry/'MODEL_CONTRACT.json',root/'LABELS.json',root/'FEATURES.csv']])
    write(root/'PRODUCTION_BINDING.json',binding)
    consumed=[]
    for row in c['rows']:
        got=load_native_refresh(root/'PRODUCTION_BINDING.json',row['link_id'])
        assert got['geometry_root']==str(geometry)
        assert got['input']['tx']==row['tx'] and got['input']['rx']==row['rx']
        assert got['labels']['link_id']==row['link_id']
        assert all(np.isfinite(v).all() for k,v in got['channel'].items() if np.issubdtype(v.dtype,np.number))
        consumed.append(dict(link_id=row['link_id'],status='PASS',geometry_root=got['geometry_root']))
    write(root/'REFRESH_CONSUMER_RECEIPT.json',dict(status='PASS',rows=consumed))
    result=dict(status='NATIVE41_REFRESH_COMPLETE',rows=41,frequency_bins=257,arms=3,port_pairs=12,cir_taps=1028,
        production_pathsolver_calls=31611,smoke_pathsolver_calls=18,custom_propagation_calls=0,
        detector_states=dict(Counter(r['state'] for r in features)),
        NoLoS=dict(Counter(str(r['NoLoS']) for r in labels)),
        path_metric_rows=len(frequency_stats),midband_paths=len(path_records),
        changed_channel_arm_rows=sum(r['H_max_absolute_change']>0 for r in comparison),
        max_H_relative_l2_change=max((r['H_relative_l2_change'] or 0) for r in comparison),
        empty_frequency_arm_pathsets=sum(r['valid_paths']==0 for r in frequency_stats),
        native_los_consistency=all(r['NoLoS_status']=='NATIVE_GEOMETRIC_LOS_CONSISTENT_ALL_BINS_AND_ARMS' for r in labels),
        production_binding='PASS',RD_HB='DEFERRED_BY_USER',final_audit_executed=False,sealed=False,G3_run=False,
        full_101_scene_RF_recalculation=False)
    write(root/'REFRESH_STATUS.json',result)
    # The historical failed bitwise test was not re-run in this revision.
    precision=read(root/'PHASE_PRECISION_RECEIPT.json')
    precision['original_bitwise_cross_platform_check']='NOT_RUN_THIS_REVISION; historical failure retained in prior native revision'
    write(root/'PHASE_PRECISION_RECEIPT.json',precision)
    write(root/'SUMMARY_MANIFEST.json',dict(inputs={str(p):file_sha(p) for p in
        [root/'CONFIG.json',production/'MANIFEST.json',geometry/'SCENE_MESH_MANIFEST.json',previous/'MANIFEST.json']},
        code={str(p):file_sha(p) for p in [Path(__file__).resolve(),ROOT/'rt_cp_uwb_py/g2_native_summary.py']},
        outputs={p.name:file_sha(p) for p in [root/name for name in
            ['FEATURES.csv','FREQUENCY_PATH_METRICS.csv','CHANNEL_COMPARISON.csv','LABELS.json','MIDBAND_PATHS.jsonl',
             'PRODUCTION_BINDING.json','REFRESH_CONSUMER_RECEIPT.json','REFRESH_STATUS.json']]}))
    print(json.dumps(result))


if __name__=='__main__':main()
