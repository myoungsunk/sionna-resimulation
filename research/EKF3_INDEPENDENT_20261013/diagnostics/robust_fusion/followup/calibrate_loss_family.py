"""Training-only route-heldout Cauchy/Student-t shape calibration, fixed R0/zero mean."""
import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from scipy.optimize import brentq
from scipy.spatial import cKDTree
from scipy.special import gammaln

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
from rf_components import check_inputs,original_lut,archived_direct_s_model,file_sha,atomic_json
from d6_d9_common import RS,RR

DFS=(3.,4.,6.,10.,20.,50.,100.)
CONTRACT=dict(schema='LOSS_SHAPE_TRAIN_ONLY_V1',df_candidates=DFS,spatial_buffer_m=.25,
    minimum_train_unique=100,mean='ZERO_NO_FIT',covariance='FROZEN_R0',eval_start_s=30,
    cauchy_fit='ZERO_LOCATION_D_DIMENSIONAL_CAUCHY_PROXY_SCALE_MLE_IN_R0_UNITS',
    cauchy_use='CONVENTIONAL_CAUCHY_M_ESTIMATOR_NOT_FINITE_VARIANCE_LIKELIHOOD',
    student_fit='MINIMUM_TRAINING_NLL_WITH_COVARIANCE_R0_TIES_FIRST_CANDIDATE',
    training_seeds='NONE_RF_GEOMETRY_ONCE_PER_CASE_POSE',
    evaluation_labels_used=False,scientific_PASS=False)

def fit_shapes(residual):
    z=np.asarray(residual,float)
    if z.ndim!=2 or not np.isfinite(z).all() or len(z)<100:raise ValueError('Invalid calibration rows')
    n,d=z.shape;q=np.sum(z*z,axis=1)
    if np.count_nonzero(q)<=n*d/(d+1):raise ValueError('Degenerate Cauchy scale training data')
    def equation(logc):return d-(d+1)*np.mean(q/(np.exp(2*logc)+q))
    lo,hi=-30.,30.
    if not equation(lo)<0<equation(hi):raise RuntimeError('Scale MLE bracket failed')
    c=float(np.exp(brentq(equation,lo,hi,xtol=1e-12)))
    candidates=[]
    for df in DFS:
        a=(df-2)/df
        const=gammaln(df/2)-gammaln((df+d)/2)+d/2*math.log(df*math.pi)+d/2*math.log(a)
        nll=float(np.mean(const+(df+d)/2*np.log1p(q/(df*a))))
        candidates.append(dict(df=df,mean_nll_standardized=nll))
    chosen=min(candidates,key=lambda x:x['mean_nll_standardized'])
    return dict(cauchy_scale=c,cauchy_score_equation=float(equation(math.log(c))),student_df=chosen['df'],student_candidates=candidates)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--inputs',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    args.out.mkdir(exist_ok=False)
    atomic_json(args.out/'TRAINING_CONTRACT.json',CONTRACT)
    im=json.loads((args.inputs/'MANIFEST.json').read_text())
    for n,h in im['sha256'].items():
        if file_sha(args.inputs/n)!=h:raise RuntimeError('Input drift '+n)
    p0=check_inputs();lut=original_lut(p0);blocks=[]
    for case in p0['cases']:
        model=archived_direct_s_model(lut,anchor_xyz_m=tuple(case['anchor']),tag_height_m=case['robot_z_m'],mount_deg=case['mount_deg'])
        for channel in ('los','full'):
            with np.load(args.inputs/(case['id']+'_'+channel+'.npz')) as f:
                ids=np.flatnonzero(f['t']>=30);_,first=np.unique(f['pose_ids'][ids],return_index=True);ids=ids[np.sort(first)]
                truth=f['truth'][ids];hs=np.array([model(x)[0] for x in truth]);anchor=np.asarray(case['anchor'])
                hr=np.sqrt(np.sum((truth[:,:2]-anchor[:2])**2,axis=1)+(case['robot_z_m']-anchor[2])**2)
                blocks.append(dict(case=case['id'],route=case['route'],channel=channel,xy=truth[:,:2],pose_ids=f['pose_ids'][ids],
                    error_s=f['s'][ids]-hs,error_B_OLD=f['B_OLD'][ids]-hr,
                    **({('error_E1_outer_'+r):f['E1_outer_'+r][ids]-hr for r in ('R2','R4','R5')} if channel=='full' else {})))
        print('RF residuals',case['id'],flush=True)
    params=[];folds=[]
    for holdout in ('R2','R4','R5'):
        for channel in ('los','full'):
            test=[b for b in blocks if b['route']==holdout and b['channel']==channel]
            train=[b for b in blocks if b['route']!=holdout and b['channel']==channel]
            tree=cKDTree(np.concatenate([b['xy'] for b in test]))
            for rm in (('B_OLD',) if channel=='los' else ('B_OLD','E1_FULL_LORO')):
                rows=[];membership=[];removed=0
                for b in train:
                    keep=tree.query(b['xy'])[0]>.25;removed+=int((~keep).sum())
                    er=b['error_B_OLD'] if rm=='B_OLD' else b['error_E1_outer_'+holdout]
                    rows.append(np.column_stack([b['error_s'][keep],er[keep]]))
                    membership.extend([dict(case=b['case'],pose_id=int(pid)) for pid in b['pose_ids'][keep]])
                values=np.concatenate(rows)/np.sqrt([RS,RR])
                if len(values)<100:raise RuntimeError('Insufficient buffered train rows')
                base=dict(heldout_route=holdout,channel=channel,range_model=rm,train_unique=len(values),overlap_removed=removed)
                folds.append(base|dict(training_membership=membership,test_labels_consumed=False,
                    E1='FROZEN_OUTER_'+holdout if rm=='E1_FULL_LORO' else 'NOT_APPLICABLE'))
                for arm,columns in (('A',[0]),('B',[1]),('C',[0,1])):
                    params.append(base|dict(arm=arm,**fit_shapes(values[:,columns])))
    atomic_json(args.out/'FROZEN_LOSS_PARAMETERS.json',params)
    atomic_json(args.out/'TRAINING_FOLDS.json',folds)
    atomic_json(args.out/'TRAINING_RECEIPT.json',dict(status='PASS',created_utc=datetime.now(timezone.utc).isoformat(),
        parameter_cells=len(params),input_manifest_sha256=file_sha(args.inputs/'MANIFEST.json'),input_sha256=im['sha256'],
        source_sha256=file_sha(Path(__file__)),contract=CONTRACT,scientific_PASS=False,
        limitations='Single previously studied RF scene; frozen E1 model selection and spatial overlap history remain exploratory',
        output_sha256={p.name:file_sha(p) for p in args.out.iterdir() if p.is_file()}))
    print('Frozen parameter cells',len(params),flush=True)

if __name__=='__main__':main()
