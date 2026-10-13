"""Offline original-FP residual structure audit; never enables T1 from ACF alone."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

DIAG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DIAG))
from d6_d9_common import P3_MODEL, P3_SHA256, atomic_json, file_sha, write_csv
from d8_polarization_quality import load_paired, outer_e1_labels, split_exclude_overlap

# Frozen before evaluation. These are descriptive checks, not scientific admission.
CRITERIA = dict(xy_buffer_m=.25, revisit_yaw_rad=math.radians(5),
                revisit_min_dt_s=5., min_train_unique=100, lags=[1,2,4,8,16,32],
                min_holdout_prediction_improvement=.05,
                min_supported_routes=2, temporal_intervention_required=True)


def corr(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or min(np.std(a), np.std(b)) < 1e-12:
        return None
    return float(np.corrcoef(a, b)[0, 1])


def groups(rows):
    result = defaultdict(list)
    for r in rows:
        result[r['case']].append(r)
    return [sorted(v, key=lambda r: int(r['sample_index'])) for v in result.values()]


def pairs(rows, column, mean, lag=1):
    blocks = []
    for seq in groups(rows):
        for a, b in zip(seq[:-lag], seq[lag:]):
            # Filtering shared sites must not turn a gap into an adjacent pair.
            if int(b['sample_index'])-int(a['sample_index']) != lag:
                continue
            dt = float(b['t_s'])-float(a['t_s'])
            dx = float(b['true_x_m'])-float(a['true_x_m'])
            dy = float(b['true_y_m'])-float(a['true_y_m'])
            yaw = abs(math.atan2(math.sin(float(b['true_heading_rad'])-float(a['true_heading_rad'])),
                                 math.cos(float(b['true_heading_rad'])-float(a['true_heading_rad']))))
            blocks.append((float(a[column])-mean, float(b[column])-mean,
                           dt, math.hypot(dx, dy), yaw))
    return np.asarray(blocks, float).reshape(-1, 5)


def unique_rows(rows):
    """Do not count repeated visits or sensor seeds as independent RF draws."""
    seen, kept = set(), []
    for r in rows:
        key = (r['case'], r['channel'], r['pose_id'])
        if key not in seen:
            kept.append(r); seen.add(key)
    return kept


def fit_ar1(rows, column, mean):
    p = pairs(rows, column, mean)
    if len(p) < 3 or p[:, 0]@p[:, 0] <= 1e-20:
        return dict(rho=None, tau_s=None, n_pairs=len(p))
    rho = float(p[:, 0]@p[:, 1]/(p[:, 0]@p[:, 0]))
    dt = float(np.median(p[:, 2]))
    tau = -dt/math.log(rho) if 0 < rho < 1 else None
    return dict(rho=rho, tau_s=tau, n_pairs=len(p), median_dt_s=dt)


def transfer(rows, column, mean, ar):
    p = pairs(rows, column, mean)
    if len(p) < 3 or ar['tau_s'] is None:
        return dict(n_pairs=len(p), improvement=None)
    residual = p[:, 1]-np.exp(-p[:, 2]/ar['tau_s'])*p[:, 0]
    base = float(np.mean(p[:, 1]**2))
    return dict(n_pairs=len(p), improvement=1-float(np.mean(residual**2))/base if base>0 else None,
                centered_pair_acf=corr(p[:,0],p[:,1]), innovation_acf=corr(residual[:-1],residual[1:]),
                conditional_innovation_variance=float(np.var(residual)),
                stationary_decomposition_identified=False)


def revisits(rows, column, mean):
    differences, gaps, exact = [], [], 0
    for seq in groups(rows):
        xy = np.asarray([[float(r['true_x_m']),float(r['true_y_m'])] for r in seq])
        yaw = np.asarray([float(r['true_heading_rad']) for r in seq])
        t = np.asarray([float(r['t_s']) for r in seq])
        e = np.asarray([float(r[column])-mean for r in seq])
        for i in range(len(seq)):
            distance = np.linalg.norm(xy[i+1:]-xy[i],axis=1)
            dyaw = np.abs(np.arctan2(np.sin(yaw[i+1:]-yaw[i]),np.cos(yaw[i+1:]-yaw[i])))
            ids = np.flatnonzero((distance<=CRITERIA['xy_buffer_m']) &
                                (dyaw<=CRITERIA['revisit_yaw_rad']) &
                                (t[i+1:]-t[i]>=CRITERIA['revisit_min_dt_s']))+i+1
            if len(ids):
                # One nearest revisit per source, not all dense neighbouring pairs.
                j = ids[np.argmin(np.linalg.norm(xy[ids]-xy[i],axis=1))]
                differences.append(e[j]-e[i]); gaps.append(t[j]-t[i])
                exact += int(seq[j]['pose_id']==seq[i]['pose_id'])
    return dict(n_revisit_pairs=len(differences), exact_pose_pairs=exact,
                revisit_residual_difference_rms=float(np.sqrt(np.mean(np.square(differences)))) if differences else None,
                median_revisit_dt_s=float(np.median(gaps)) if gaps else None)


def run(source, out):
    out.mkdir(parents=True, exist_ok=False)
    atomic_json(out/'PREREGISTERED_CRITERIA.json', CRITERIA)
    records, hashes = load_paired(source)
    records = [r for r in records if float(r['t_s'])>=30]
    if file_sha(P3_MODEL) != P3_SHA256:
        raise RuntimeError('Frozen E1 hash mismatch')
    frozen = json.loads(P3_MODEL.read_text(encoding='utf-8'))
    routes = sorted({r['route'] for r in records})
    if len(routes)!=3:
        raise RuntimeError('Three routes required')
    summaries, lags, parameters = [], [], []
    for holdout in routes:
        for channel in ('los','full'):
            test0=[r for r in records if r['route']==holdout and r['channel']==channel]
            candidates=[r for r in records if r['route']!=holdout and r['channel']==channel]
            train0, removed=split_exclude_overlap(candidates,test0,CRITERIA['xy_buffer_m'])
            for model in (('B_OLD',) if channel=='los' else ('B_OLD','E1_FULL_LORO')):
                train,test=train0,test0
                test_removed=0
                if model=='E1_FULL_LORO':
                    # Frozen coefficients already saw candidates, including shared XY.
                    test,test_removed=split_exclude_overlap(test,candidates,CRITERIA['xy_buffer_m'])
                    train=outer_e1_labels(train,holdout,frozen)
                    test=outer_e1_labels(test,holdout,frozen)
                unique=unique_rows(train)
                base=dict(heldout_route=holdout,channel=channel,range_model=model,
                          train_unique_geometry=len(unique),train_sequence_rows=len(train),test_rows=len(test),
                          train_overlap_removed=removed,e1_test_overlap_removed=test_removed,
                          e1_outer_fold=holdout if model=='E1_FULL_LORO' else '')
                columns=('error_s','error_range_'+model+'_m')
                if len(unique)<CRITERIA['min_train_unique'] or not test:
                    summaries.append(base|dict(target='joint',status='INSUFFICIENT_SPLIT')); continue
                values=np.asarray([[float(r[c]) for c in columns] for r in unique])
                means=np.mean(values,axis=0)
                cov=np.cov(values.T,ddof=1)
                parameters.append(base|dict(mean=means.tolist(),total_empirical_covariance=cov.tolist(),
                                            columns=list(columns),independent_sample_count_not_claimed=True))
                for i,column in enumerate(columns):
                    ar=fit_ar1(train,column,float(means[i]))
                    result=transfer(test,column,float(means[i]),ar)
                    summary=base|dict(target=('s','r')[i],mean=float(means[i]),total_variance=float(cov[i,i]),
                                      **ar,**{('heldout_'+k):v for k,v in result.items()},**revisits(test,column,float(means[i])))
                    summaries.append(summary)
                    for lag in CRITERIA['lags']:
                        p=pairs(test,column,float(means[i]),lag)
                        lags.append(base|dict(target=('s','r')[i],lag=lag,n_pairs=len(p),
                            acf=corr(p[:,0],p[:,1]),
                            median_dt_s=float(np.median(p[:,2])) if len(p) else None,
                            median_displacement_m=float(np.median(p[:,3])) if len(p) else None,
                            median_yaw_change_rad=float(np.median(p[:,4])) if len(p) else None,
                            time_distance_correlation=corr(p[:,2],p[:,3]),
                            time_yaw_correlation=corr(p[:,2],p[:,4])))
    write_csv(out/'RF_RESIDUAL_STRUCTURE.csv',summaries)
    write_csv(out/'RF_LAG_GEOMETRY.csv',lags)
    atomic_json(out/'RF_TRAINING_MOMENTS.json',parameters)
    gate=dict(status='INCONCLUSIVE',m2_t1_allowed=False,scientific_PASS=False,
              temporal_ar1_validity='NOT_ESTABLISHED',criteria=CRITERIA,
              reason='Single deterministic scene with one traversal time parametrization per route; no controlled temporal variation at fixed geometry. ACF and one-step transfer cannot identify temporal mechanism or uniquely decompose correlated and instantaneous variance.',
              n_summary_rows=len(summaries),input_sha256=hashes,
              frozen_e1_sha256=P3_SHA256,script_sha256=file_sha(Path(__file__)),
              sequence_samples_not_independent_replicates=True,
              output_sha256={p.name:file_sha(p) for p in out.iterdir() if p.is_file()})
    atomic_json(out/'RF_RESIDUAL_STRUCTURE_GATE.json',gate)
    print(json.dumps(dict(status=gate['status'],m2_t1_allowed=False,n_summary_rows=len(summaries))))


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--d7',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    a=ap.parse_args();run(a.d7,a.out)
