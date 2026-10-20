"""Input-only enumeration of S2 folds and primary evaluation cells; no fit/replay."""
from pathlib import Path
import argparse,hashlib,json,sys
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'research/R5_N4B_20261015'))
from n4b_rf_errors import feature_splits,site_weights
from model import ARMS

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def hash_keys(frame):return hashlib.sha256(json.dumps([[str(c),int(i)] for c,i in frame[['case','pose_id']].itertuples(index=False,name=None)],separators=(',',':')).encode()).hexdigest()
def splits(full):
    records={}
    for held,tr,te in feature_splits(np,full):
        train=full.loc[tr];before=full[full.route!=held];test=full.loc[te]
        dist=cKDTree(test[['x_eval','y_eval']]).query(train[['x_eval','y_eval']])[0]
        assert (dist>1e-4).all() and held not in set(train.route)
        records[held]=dict(held_route=held,rows_before_site_exclusion=len(before),rows_after_site_exclusion=len(train),test_rows=len(test),
          sites_before=len(before[['x_eval','y_eval']].round(5).drop_duplicates()),sites_after=len(train[['x_eval','y_eval']].round(5).drop_duplicates()),
          heldout_min_distance_m=float(dist.min()),heldout_site_overlap=0,training_key_sha256=hash_keys(train),weights_sha256=hashlib.sha256(site_weights(np,pd,train).tobytes()).hexdigest(),
          training_keys=[[str(c),int(i)] for c,i in train[['case','pose_id']].itertuples(index=False,name=None)],training_mount_values=sorted(train.mount_feature.unique().tolist()))
    records['ALL_OLD']=dict(held_route=None,rows_before_site_exclusion=len(full),rows_after_site_exclusion=len(full),sites_after=len(full[['x_eval','y_eval']].round(5).drop_duplicates()),
       training_key_sha256=hash_keys(full),weights_sha256=hashlib.sha256(site_weights(np,pd,full).tobytes()).hexdigest(),training_keys=[[str(c),int(i)] for c,i in full[['case','pose_id']].itertuples(index=False,name=None)],training_mount_values=sorted(full.mount_feature.unique().tolist()),new_C_O_rows=0,includes_R2_A_M45=bool((full.case=='R2_aA_m45').any()))
    return records

def main():
    p=argparse.ArgumentParser();p.add_argument('--labels',type=Path,required=True);p.add_argument('--cases',type=Path,required=True);a=p.parse_args()
    assert sha(a.labels)=='02038c4c967750905a80dde31b0bcd0b667bd5d11df1cb02e05023e06893ee4d'
    assert sha(a.cases)=='462c0bc89e1b55653d289d8a529c1c7022c17a8d954c5ea5740a99092d367455'
    frame=pd.read_csv(a.labels);full=frame[frame.channel=='full'].copy().reset_index(drop=True)
    cases=json.loads(a.cases.read_text())['cases'];rows=[];refs=[]
    for c in cases:
        for bias in ['B0','L2']:
            for channel in ['full']+(['los'] if c['id'] in ['R2_aA_m0','R2_aA_m45'] else []):
                for arm in ARMS:rows.append(dict(case=c['id'],route=c['id'].split('_')[0],population='legacy',channel=channel,bias=bias,seed=0,arm=arm,fold=c['id'].split('_')[0],primary_scope='motion_t_ge30',mount_status='OUT_OF_TRAINING_RANGE_MOUNT' if c['id']=='R2_aA_m45' else 'IN_TRAINING_RANGE_MOUNT'))
                if channel=='los':refs.append(dict(case=c['id'],route='R2',population='legacy',channel=channel,bias=bias,seed=0,arm='JOINT4_R0',fold='R2'))
    new=[]
    for route in ['C01','C02','C03','O01','O02','O03']:
        for anchor in ['A','B'] if route.startswith('C') else ['O0']:new.append(dict(id=f'{route}_{anchor}_M45_FULL',anchor={'A':[4.,0.,2.65],'B':[10.,0.,2.65],'O0':[5.,2.2,2.65]}[anchor],mount_deg=45.,robot_z_m=.45))
    for c in new:
        for bias in ['B0','L0','L1','L2']:
            for seed in range(5):
                for arm in ARMS:rows.append(dict(case=c['id'],route=c['id'].split('_')[0],population='new',channel='full',bias=bias,seed=seed,arm=arm,fold='ALL_OLD',primary_scope='motion_t_ge30',mount_status='IN_TRAINING_RANGE_MOUNT'))
    assert len(rows)==792 and len(refs)==4
    pd.DataFrame(rows).to_csv(HERE/'CASE_MATRIX.csv',index=False);pd.DataFrame(refs).to_csv(HERE/'LOS_REFERENCE_MATRIX.csv',index=False)
    data=dict(labels_sha256=sha(a.labels),cases_sha256=sha(a.cases),site_exclusion='exact pinned feature_splits; held-route nearest xy distance>1e-4m',site_weights='pinned site_weights: inverse multiplicity of rounded5 xy, normalize mean1',folds=splits(full))
    (HERE/'TRAIN_SPLITS.json').write_text(json.dumps(data,indent=2)+'\n')
    (HERE/'CASE_METADATA.json').write_text(json.dumps({'legacy':cases,'new':new},indent=2)+'\n')
    print('S2_CONTRACT_PREPARED',len(rows),{k:v['rows_after_site_exclusion'] for k,v in data['folds'].items()})
if __name__=='__main__':main()
