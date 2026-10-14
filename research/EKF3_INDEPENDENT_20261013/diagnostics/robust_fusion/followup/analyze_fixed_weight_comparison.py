"""Verify fixed-weight evidence and describe paired recursion/one-step effects.

Time points are correlated repeated observations. No independent-time-point
confidence intervals or hypothesis tests are produced. Fixed 1/3 is a training
control, not a match to held-out/test information or posterior covariance.
"""
import argparse
import csv
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import run_fixed_weight_comparison as run
from d6_d9_common import file_sha,atomic_json

MODELS=run.MODELS
ID=('case','channel','range_model','condition','level','seed','arm')
GROUP=('channel','range_model','condition','level','arm')


def write(path,rows):
    if not rows: raise RuntimeError('Empty analysis output '+path.name)
    fields=list(dict.fromkeys(k for r in rows for k in r))
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)


def scalar(a,name): return run.get(a,name)
def error_squared(a):
    e=scalar(a,'error')
    return e[:,2]**2,np.sum(e[:,:2]**2,axis=1)


def recursive_diagnostics(a):
    applied=scalar(a,'applied').astype(bool)
    weights=scalar(a,'weight')[applied]
    prior=scalar(a,'P_prior').reshape(-1,3,3)
    post=scalar(a,'P_post').reshape(-1,3,3)
    fields=dict(n=len(a),accepted_updates=int(applied.sum()),
        rejected_updates=int((~applied).sum()),gate_rejection_fraction=float((~applied).mean()),
        mean_weight=float(weights.mean()) if len(weights) else None,
        median_weight=float(np.median(weights)) if len(weights) else None,
        weight_p05=float(np.quantile(weights,.05)) if len(weights) else None,
        weight_p95=float(np.quantile(weights,.95)) if len(weights) else None,
        accepted_weight_below_third_fraction=float((weights<1/3).mean()) if len(weights) else None,
        median_pre_gate_NIS=float(np.median(scalar(a,'NIS'))),
        median_P_prior_xy_trace=float(np.median(prior[:,0,0]+prior[:,1,1])),
        median_P_post_xy_trace=float(np.median(post[:,0,0]+post[:,1,1])),
        median_P_prior_heading=float(np.median(prior[:,2,2])),
        median_P_post_heading=float(np.median(post[:,2,2])),
        median_P_xy_trace_ratio=float(np.median((post[:,0,0]+post[:,1,1])/(prior[:,0,0]+prior[:,1,1]))),
        median_P_heading_ratio=float(np.median(post[:,2,2]/prior[:,2,2])),
        median_gain_frobenius_applied=float(np.median(np.linalg.norm(scalar(a,'K')[applied],axis=1))) if applied.any() else None)
    hsq,xysq=error_squared(a)
    fields.update(heading_rmse_deg=float(np.sqrt(hsq.mean())*180/np.pi),
        xy_rmse_m=float(np.sqrt(xysq.mean())),mean_pose_NEES=float(scalar(a,'pose_NEES').mean()),
        mean_heading_NEES=float(scalar(a,'heading_NEES').mean()),
        pose95=float(scalar(a,'pose95').mean()),heading95=float(scalar(a,'heading95').mean()))
    return fields


def paired(a,b):
    ah,ax=error_squared(a);bh,bx=error_squared(b)
    return dict(n=len(a),heading_rmse_deg_candidate=float(np.sqrt(ah.mean())*180/np.pi),
        heading_rmse_deg_reference=float(np.sqrt(bh.mean())*180/np.pi),
        xy_rmse_m_candidate=float(np.sqrt(ax.mean())),xy_rmse_m_reference=float(np.sqrt(bx.mean())),
        mean_heading_squared_error_difference_rad2=float((ah-bh).mean()),
        mean_position_squared_error_difference_m2=float((ax-bx).mean()),
        heading_strict_improvement_fraction=float((ah<bh).mean()),
        position_strict_improvement_fraction=float((ax<bx).mean()),
        mean_pose_NEES_difference=float((scalar(a,'pose_NEES')-scalar(b,'pose_NEES')).mean()),
        pose95_difference=float((scalar(a,'pose95')-scalar(b,'pose95')).mean()),
        gate_rejection_fraction_candidate=float((scalar(a,'applied')==0).mean()),
        gate_rejection_fraction_reference=float((scalar(b,'applied')==0).mean()))


def step_pair(a,b,mask):
    if not mask.any(): return dict(n=0)
    aa,bb=a[mask],b[mask]
    result=paired(aa,bb)
    for label,field in (('heading','heading_sq_change'),('position','xy_sq_change')):
        ca,cb=scalar(aa,field),scalar(bb,field)
        result['mean_'+label+'_update_squared_error_change_candidate']=float(ca.mean())
        result['mean_'+label+'_update_squared_error_change_reference']=float(cb.mean())
        result[label+'_candidate_update_strict_improvement_fraction']=float((ca<0).mean())
        result[label+'_reference_update_strict_improvement_fraction']=float((cb<0).mean())
    accepted=scalar(aa,'applied').astype(bool)
    result.update(mean_weight_candidate=float(scalar(aa,'weight')[accepted].mean()) if accepted.any() else None,
        mean_weight_reference=float(scalar(bb,'weight')[accepted].mean()) if accepted.any() else None)
    return result


def verify_metric(actual,reference):
    maximum=0.
    for field,value in actual.items():
        if field in ID or field in ('model','donor'): continue
        original=reference[field]
        if value is None:
            if original not in ('','None'): raise RuntimeError('Metric None mismatch '+field)
        elif field in ('n','accepted_updates','rejected_updates'):
            if int(value)!=int(original): raise RuntimeError('Metric count mismatch '+field)
        else:
            difference=abs(float(value)-float(original));maximum=max(maximum,difference)
            if not math.isfinite(difference) or difference>1e-10:
                raise RuntimeError('Trace/metric difference '+field+' '+str(difference))
    return maximum


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    recursive_cells=[];rec_pairs=[];step_cells=[];rec_groups={};step_groups={}
    inputs={};max_difference=0.;trace_rows=0;one_metrics_checked=0
    for stage in ('NOISE','L1','L2'):
        path=args.root/stage;manifest=json.loads((path/'MANIFEST.json').read_text())
        if manifest.get('status')!='COMPLETED' or manifest.get('exit_code')!=0:
            raise RuntimeError('Stage incomplete '+stage)
        for name,sha in manifest['sha256'].items():
            if file_sha(path/name)!=sha: raise RuntimeError('Output hash drift '+stage+'/'+name)
        inputs[stage]=dict(manifest_sha256=file_sha(path/'MANIFEST.json'),sha256=manifest['sha256'])
        parity=json.loads((path/'PARITY.json').read_text())
        if parity['baseline']['status']!='PASS' or parity['same_prior_gate']!='PASS':
            raise RuntimeError('Stage gate failed '+stage)
        schema=json.loads((path/'TRACE_SCHEMA.json').read_text())
        if schema['fields']!=[list(item) for item in run.FIELDS]: raise RuntimeError('Trace schema drift')
        own=list(csv.DictReader((path/'RECURSIVE_METRICS.csv').open()))
        one=list(csv.DictReader((path/'ONE_STEP_METRICS.csv').open()))
        lookup={tuple(row[k] for k in ID)+(row['model'],):row for row in own}
        one_lookup={tuple(row[k] for k in ID)+(row['donor'],row['model']):row for row in one}
        files=sorted(path.glob('*.npz'))
        if {p.name for p in files}!={n for n in manifest['sha256'] if n.endswith('.npz')}:
            raise RuntimeError('Unmanifested trace input '+stage)
        if len(files)!=63 or len(own)!=252 or len(one)!=504: raise RuntimeError('Incomplete full grid '+stage)
        for filename in files:
            case,channel,rm,seedstr=filename.stem.split('__')
            identity=dict(case=case,channel=channel,range_model=rm,
                condition='noise_pair' if stage=='NOISE' else 'gyro_bias',
                level=1 if stage in ('NOISE','L1') else 2,seed=int(seedstr[4:]),arm='C')
            group=tuple(identity[k] for k in GROUP)
            with np.load(filename,allow_pickle=False) as cache:
                recursive={n:cache['recursive__'+n] for n in MODELS}
                for name,a in recursive.items():
                    trace_rows+=len(a)
                    row=run.metrics(a,dict(identity,model=name))
                    key=tuple(str(identity[k]) for k in ID)+(name,)
                    max_difference=max(max_difference,verify_metric(row,lookup[key]))
                    recursive_cells.append(dict(identity,model=name,**recursive_diagnostics(a)))
                    rec_groups.setdefault(group+(name,),[]).append(a)
                for reference in ('RF_FIXED_THIRD','M0','RF_HUBER_ONLY'):
                    rec_pairs.append(dict(identity,candidate='RF_CAUCHY',reference=reference,
                        **paired(recursive['RF_CAUCHY'],recursive[reference])))
                for donor in run.DONORS:
                    candidate=cache['one__'+donor+'__RF_CAUCHY']
                    for name in MODELS:
                        a=cache['one__'+donor+'__'+name]
                        key=tuple(str(identity[k]) for k in ID)+(donor,name)
                        max_difference=max(max_difference,verify_metric(run.metrics(a,dict(identity,model=name,donor=donor)),one_lookup[key]))
                        one_metrics_checked+=1
                        for field in ('t','truth','prior','P_prior','applied'):
                            if not np.array_equal(scalar(a,field),scalar(candidate,field)):
                                raise RuntimeError('Common-prior pairing mismatch '+field)
                        if np.max(np.abs(scalar(a,'NIS')-scalar(candidate,'NIS')))>1e-8:
                            raise RuntimeError('Common-prior NIS mismatch')
                    for reference in ('RF_FIXED_THIRD','M0','RF_HUBER_ONLY'):
                        other=cache['one__'+donor+'__'+reference]
                        accepted=scalar(candidate,'applied').astype(bool)
                        masks={'all':np.ones(len(candidate),dtype=bool),'accepted':accepted,
                            'accepted_cauchy_weight_below_third':accepted&(scalar(candidate,'weight')<1/3),
                            'accepted_cauchy_weight_at_or_above_third':accepted&(scalar(candidate,'weight')>=1/3)}
                        for subset,mask in masks.items():
                            step_cells.append(dict(identity,donor=donor,candidate='RF_CAUCHY',reference=reference,
                                subset=subset,**step_pair(candidate,other,mask)))
                        step_groups.setdefault(group+(donor,reference),[]).append((candidate,other))
        print(stage,'verified',len(files),'input cells',flush=True)
    pooled=[]
    for key,arrays in rec_groups.items():
        a=np.concatenate(arrays)
        pooled.append(dict(zip(GROUP+('model',),key),trajectory_seed_cells=len(arrays),**recursive_diagnostics(a)))
    step_pooled=[]
    for key,pairs in step_groups.items():
        a=np.concatenate([p[0] for p in pairs]);b=np.concatenate([p[1] for p in pairs])
        accepted=scalar(a,'applied').astype(bool)
        masks={'all':np.ones(len(a),dtype=bool),'accepted':accepted,
            'accepted_cauchy_weight_below_third':accepted&(scalar(a,'weight')<1/3),
            'accepted_cauchy_weight_at_or_above_third':accepted&(scalar(a,'weight')>=1/3)}
        for subset,mask in masks.items():
            step_pooled.append(dict(zip(GROUP+('donor','reference'),key),candidate='RF_CAUCHY',
                subset=subset,trajectory_seed_cells=len(pairs),**step_pair(a,b,mask)))
    outputs={'RECURSIVE_CELL_DIAGNOSTICS.csv':recursive_cells,'POOLED_RECURSIVE_DIAGNOSTICS.csv':pooled,
        'PAIRED_RECURSIVE_TRAJECTORY_SEED.csv':rec_pairs,'PAIRED_ONE_STEP_TRAJECTORY_SEED.csv':step_cells,
        'POOLED_ONE_STEP_PAIRED.csv':step_pooled}
    for name,rows in outputs.items(): write(args.out/name,rows)
    atomic_json(args.out/'ANALYSIS_RECEIPT.json',dict(status='PASS',scientific_PASS=False,
        command=sys.argv,completed_utc=datetime.now(timezone.utc).isoformat(),input_evidence=inputs,
        recursive_metric_cells_verified=len(recursive_cells),one_step_metric_cells_verified=one_metrics_checked,
        recursive_trace_rows=trace_rows,max_trace_metric_difference=max_difference,metric_tolerance=1e-10,
        pairing_gate_tolerance=1e-8,source_sha256=file_sha(Path(__file__)),
        output_sha256={name:file_sha(args.out/name) for name in outputs},
        interpretation='DESCRIPTIVE_PAIRED_TRAJECTORY_SEED_COMPARISONS_NO_INDEPENDENT_TIMEPOINT_INFERENCE',
        weight_control='FIXED_TRAINING_CONTROL_ONE_THIRD_NOT_HELD_OUT_INFORMATION_MATCH',
        proportions='STRICT_SAMPLEWISE_ERROR_COMPARISONS_DESCRIPTIVE_NOT_SIGNIFICANCE',
        selectivity_strata='FIXED_BEFORE_ANALYSIS_CAUCHY_WEIGHT_LESS_THAN_ONE_THIRD_OR_AT_LEAST_ONE_THIRD'))


if __name__=='__main__': main()
