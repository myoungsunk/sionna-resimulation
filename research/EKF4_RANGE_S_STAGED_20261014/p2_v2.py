"""P2-v2 audited replay: original frozen synthetic generation and four models.

No changed P2 scientific data, seeds, Q, R, or gradient threshold.
Separate estimator-level numerical failures from test diagnostics and claims.
All estimation execution is GitHub-hosted Actions ONLY, after pre-run audit.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback
import numpy as np
from synthetic import generate, run_model
from validate import sha, write

HERE=Path(__file__).resolve().parent
EXPECTED_SPEC_SHA='548258a444c02a3a1d0c2d210b470489560b1bd56ad911cc9ee93d7631b36ce7'
EXPECTED_GENERATOR_SHA='c3fc54d9726beab176971aa8652c0b6f613e4c8150351c4d9643'


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _check_gate(audit_path, p0p1_path, r2_path, phase):
    if os.getenv('GITHUB_ACTIONS')!='true':
        raise RuntimeError('P2 inference must run in GitHub Actions')
    audit=_read(audit_path)
    p0=_read(Path(p0p1_path)/'FINAL.json')
    r2=_read(Path(r2_path)/'FINAL.json')
    commit=os.getenv('GITHUB_SHA')
    if not (audit['decision']=='GO' and audit['stage']==phase
            and audit['git_sha']==commit and p0['git_sha']==commit
            and p0['stages']['P0']=='PASS' and p0['stages']['P1']=='PASS'
            and p0['exit_code']==0
            and r2['git_sha']==commit and r2['status']=='PASS'):
        raise RuntimeError('required pre-run audit/related numerical gates not met')
    if sha(HERE/'P2_SPEC.json')!=EXPECTED_SPEC_SHA or sha(HERE/'synthetic.py')!=EXPECTED_GENERATOR_SHA:
        raise RuntimeError('frozen P2 input contract mismatch')
    for name,saved in audit['source_sha256'].items():
        if sha(HERE/name)!=saved:
            raise RuntimeError('source changed after audit: '+name)
    return audit,p0,r2


def _save_csv(file,rows):
    if not rows:return
    keys=list(dict.fromkeys(key for row in rows for key in row))
    with Path(file).open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def _groups(rows,failures,spec,full):
    """Route/condition summaries; no incomplete-pair CI promoted to proof."""
    groups=[]
    contrasts=[]
    bootstrap=np.random.default_rng(spec['bootstrap_seed'])
    for path in spec['paths']:
        for bias in spec['true_bias_dps']:
            group=[r for r in rows if r['path']==path and r['true_bias_dps']==bias]
            bad=[r for r in failures if r['path']==path and r['true_bias_dps']==bias]
            by_model={name:{r['trial']:r for r in group if r['model']==name}
                      for name in spec['models']}
            successes={m:len(v) for m,v in by_model.items()}
            failures_by_model={m:sum(r['model']==m for r in bad) for m in spec['models']}
            pairs=set.intersection(*(set(v) for v in by_model.values()))
            g={'path':path,'true_bias_dps':bias,'complete_four_model_pairs':len(pairs),
               'expected_pairs':spec['trials_per_path_bias'] if full else 1,
               'success_by_model':successes,'invalid_by_model':failures_by_model,
               'all_models_complete':len(pairs)==(spec['trials_per_path_bias'] if full else 1)}
            for model,values in by_model.items():
                d=list(values.values())
                if d:
                    g[model+'_heading_RMSE_deg_on_successful_cases']=math.sqrt(
                        sum(x['heading_MSE_deg2'] for x in d)/len(d))
                    g[model+'_position_RMSE_m_on_successful_cases']=math.sqrt(
                        sum(x['position_MSE_m2'] for x in d)/len(d))
                    g[model+'_heading95_on_successful_cases']=sum(x['heading95'] for x in d)/len(d)
                    g[model+'_pose95_on_successful_cases']=sum(x['pose95'] for x in d)/len(d)
                else:
                    g[model+'_heading_RMSE_deg_on_successful_cases']=None
                    g[model+'_position_RMSE_m_on_successful_cases']=None
            groups.append(g)
            if full:
                for first,second in (('MAP3','MAP4'),('EKF3','EKF4'),('EKF4','MAP4')):
                    ids=sorted(set(by_model[first]) & set(by_model[second]))
                    delta=np.array([by_model[second][i]['heading_MSE_deg2']-
                                    by_model[first][i]['heading_MSE_deg2'] for i in ids])
                    record={'path':path,'true_bias_dps':bias,'contrast':second+'-minus-'+first,
                            'valid_pairs':len(ids),'required_pairs':spec['trials_per_path_bias'],
                            'conditioning':'paired successful subset only; missing data may bias estimate',
                            'primary':first=='MAP3' and second=='MAP4' and bias==.05}
                    if len(delta)>=2:
                        indices=bootstrap.integers(0,len(delta),
                            size=(spec['bootstrap_draws'],len(delta)))
                        low,high=np.quantile(delta[indices].mean(axis=1),[.025,.975])
                        record.update({'mean_heading_MSE_delta_deg2':float(delta.mean()),
                                       'CI95_low':float(low),'CI95_high':float(high),
                                       'full_data':len(ids)==spec['trials_per_path_bias']})
                        if record['full_data']:
                            record['route_claim']=('SUPPORT' if high<0 else
                              ('CONTRADICTED' if low>0 else 'INCONCLUSIVE'))
                        else:
                            record['route_claim']='NOT_ADJUDICATED_MISSING_PAIRS'
                    else:
                        record['route_claim']='NOT_ADJUDICATED_INSUFFICIENT_PAIRS'
                    contrasts.append(record)
    return groups,contrasts


def run_phase(out,phase,audit_path,gates_path,r2_path):
    audit,p0,r2=_check_gate(audit_path,gates_path,r2_path,phase)
    cfg=_read(HERE/'P2_SPEC.json')
    out=Path(out).resolve()
    out.mkdir(parents=True,exist_ok=False)
    start={
        'schema':'P2_V2_AUDITED_PAIRED_V1',
        'phase':phase,
        'commit':os.environ['GITHUB_SHA'],
        'run_id':os.environ['GITHUB_RUN_ID'],
        'run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),
        'start_utc':datetime.now(timezone.utc).isoformat(),
        'source_hashes':{x:sha(HERE/x) for x in
          ('p2_v2.py','synthetic.py','core.py','stable_descent.py','P2_SPEC.json')},
        'preaudit_sha256':sha(audit_path),
        'p0_p1_receipt_sha256':sha(Path(gates_path)/'FINAL.json'),
        'r2_receipt_sha256':sha(Path(r2_path)/'FINAL.json'),
        'contract':cfg,
        'scientific_PASS':False,
        'scope':'matched synthetic estimator comparison; NOT real RF or independent scene',
        'P3_P6':'NOT_RUN'}
    write(out/'START.json',start)
    rows,failures=[],[]
    status='STARTED'
    rc=1
    try:
        for path_idx,path in enumerate(cfg['paths']):
            for bias in cfg['true_bias_dps']:
                limit=1 if phase=='preflight' else cfg['trials_per_path_bias']
                for trial in range(limit):
                    cell={'path':path,'true_bias_dps':bias,'trial':trial}
                    td=out/'trials'/path/str(bias)/f'{trial:03d}'
                    td.mkdir(parents=True,exist_ok=False)
                    data=generate(cfg,path_idx,trial,bias)
                    np.savez_compressed(td/'INPUTS.npz',**data)
                    for model in cfg['models']:
                        md=td/model
                        md.mkdir(parents=True,exist_ok=False)
                        try:
                            result=run_model(data,model,cfg,cell,md)
                        except RuntimeError as exc:
                            # An explicit solver nonconvergence invalidates that
                            # estimator/cell ONLY. Programming errors remain HARD.
                            if str(exc)!='MAP nonconvergence; evidence preserved, no silent fallback':
                                raise
                            failure={'classification':'CASE_RESULT_INVALID_NUMERICAL',
                                     **cell,'model':model,'exception':str(exc)}
                            original=md/'FAILURE.json'
                            if original.exists():
                                failure['original_failure']=_read(original)
                            failures.append(failure)
                            write(md/'MODEL_RESULT.json',{'status':'INVALID',**failure})
                            continue
                        rows.append({**cell,'model':model,**result})
                        write(md/'MODEL_RESULT.json',{'status':'VALID',**cell,'model':model,'metrics':result})
                    if (trial+1)%10==0 or (phase=='preflight'):
                        print('P2_PROGRESS '+json.dumps({**cell,'model_success_count':len(rows),
                            'case_failure_count':len(failures)},ensure_ascii=False),flush=True)
                    _save_csv(out/'TRIAL_METRICS.csv',rows)
                    write(out/'CASE_INVALID.json',failures)
        groups,contrasts=_groups(rows,failures,cfg,phase=='full')
        write(out/'GROUP_METRICS.json',groups)
        write(out/'PAIRED_CI.json',contrasts)
        _save_csv(out/'PAIRED_CI.csv',contrasts)
        if phase=='preflight':
            # Preflight is a resource-allocation decision: known numerical
            # failures must be diagnosed before expensive full repeats.
            status='PREFLIGHT_READY_FOR_FULL' if not failures else 'PREFLIGHT_NUMERICAL_CASES_TO_DIAGNOSE'
            rc=0 if not failures else 3
        else:
            required=cfg['trials_per_path_bias']
            enough=all(g['complete_four_model_pairs']==required for g in groups)
            primary=[a for a in contrasts if a['primary']]
            claim=('ALL_THREE_ROUTES_SUPPORT' if enough and len(primary)==3
                   and all(a.get('route_claim')=='SUPPORT' for a in primary)
                   else 'ALL_THREE_ROUTES_SUPPORT_NOT_ESTABLISHED')
            status='FULL_P2_COMPLETED' if enough else 'FULL_P2_COMPLETED_WITH_INVALID_CASES'
            # Science mismatch only blocks further model-direction decisions,
            # not data eligibility checks or technical execution receipts.
            write(out/'SCIENTIFIC_DECISION.json',{
                'scope':'matched synthetic, not FFD real RF',
                'all_route_claim':claim,
                'per_route_primary':[a for a in primary],
                'unresolved_failures':len(failures),
                'requires_user_direction_confirmation':claim!='ALL_THREE_ROUTES_SUPPORT',
                'note':'Full case availability required for the original 100-trial claim.',
                'scientific_PASS':False})
            rc=0
    except Exception as exc:
        status='HARD_EXECUTION_BLOCK'
        rc=1
        (out/'TRACEBACK.log').write_text(traceback.format_exc(),encoding='utf-8')
        print('P2_HARD_FAILURE '+str(exc),flush=True)
    finally:
        write(out/'CASE_INVALID.json',failures)
        _save_csv(out/'TRIAL_METRICS.csv',rows)
        # Preserve outputs and the original exception history for review.
        final={**start,'status':status,'exit_code':rc,
               'completed_model_trials':len(rows),'invalid_model_cases':len(failures),
               'complete_four_model_pairs':len([1 for path in cfg['paths']
                 for bias in cfg['true_bias_dps'] for trial in range(
                   1 if phase=='preflight' else cfg['trials_per_path_bias'])
                 if all(any(row['path']==path and row['true_bias_dps']==bias and
                       row['trial']==trial and row['model']==name for row in rows)
                       for name in cfg['models'])]),
               'end_utc':datetime.now(timezone.utc).isoformat(),
               'sha256_outputs':{str(f.relative_to(out)):sha(f) for f in sorted(out.rglob('*')) if f.is_file()}}
        write(out/'FINAL.json',final)
        print('P2_PHASE_FINAL '+json.dumps({k:v for k,v in final.items()
             if k not in ('sha256_outputs','contract','source_hashes')},ensure_ascii=False,allow_nan=False),flush=True)
    return rc


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=['preflight','full'],required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--gates',type=Path,required=True)
    parser.add_argument('--r2',type=Path,required=True)
    args=parser.parse_args()
    return run_phase(args.out,args.phase,args.audit,args.gates,args.r2)


if __name__=='__main__':
    raise SystemExit(main())
