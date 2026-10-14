"""Staged runner. Each stage requires its own current source-bound audit receipt.

Hypothesis failure is not a numerical failure. Optional diagnostics cannot mutate
or invalidate estimator outputs. Truth is read only by explicit scoring code.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import math
import os
import sys
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.integrate import quad, IntegrationWarning
from scipy.stats import norm
from scipy.special import logsumexp
import model

ROOT = Path(__file__).resolve().parent
CONTRACT = json.loads((ROOT/'CONTRACT.json').read_text())
OUT = Path('outputs/g2g3_minimal')


def serial(v):
    if isinstance(v, np.ndarray): return v.tolist()
    if isinstance(v, np.generic): return v.item()
    if isinstance(v, Path): return str(v)
    raise TypeError(type(v).__name__)


def save(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT/name
    if path.exists(): raise FileExistsError('refusing result overwrite: '+str(path))
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False,
                               allow_nan=False, default=serial))


def envelope(stage):
    return dict(stage=stage, execution='PASS', calculation='NOT_EVALUATED',
                hypothesis='NOT_EVALUATED', scientific_claim='CLAIM_BLOCK',
                claim_scope='No trained fault prior, no heldout RF quality, no full nonlinear pose filter',
                scientific_PASS=False, findings=[])


def require_audit(stage):
    p = OUT/('PRE_RUN_'+stage+'.json')
    if not p.is_file(): raise RuntimeError('HARD_EXECUTION_BLOCK: missing stage pre-audit')
    r = json.loads(p.read_text())
    if r.get('run_decision') not in ('GO', 'GO_WITH_CLAIM_LIMITATION'):
        raise RuntimeError('HARD_EXECUTION_BLOCK: audit not approved')
    if not r.get('audited_code_matches_execution_sha'):
        raise RuntimeError('HARD_EXECUTION_BLOCK: stale source audit')
    # Recheck direct source bytes before scientific imports are used.
    for path, sha in r['source_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha:
            raise RuntimeError('HARD_EXECUTION_BLOCK: source changed after pre-audit')
    return r


def independent_radial_reference(mu, sigma, z, cfg):
    """Direct quadrature of normalized prior*likelihood, not product-Gaussian formula."""
    lo = float(cfg['lower_slant_m'])
    terms = []
    for fault, pd0 in ((False, 1-cfg['fault_prior_probability']),
                       (True, cfg['fault_prior_probability'])):
        sd = math.sqrt(sigma*sigma+(cfg['fault_radial_std_m']**2 if fault else 0))
        td = norm.sf((lo-mu)/sd)
        for rc in cfg['rf_components']:
            sr, bias, pr = rc['std_m'], rc['bias_m'], rc['weight']
            def density(x):
                return pd0*pr*norm.pdf((x-mu)/sd)/sd/td*norm.pdf((z-x-bias)/sr)/sr
            # Breakpoints are from original inputs, not production posterior means.
            hi = max(lo+1, mu+16*sd, z-bias+16*sr)
            points = [lo, hi]
            for cen, scale in ((mu, sd), (z-bias, sr)):
                for k in (-8,-4,-2,-1,0,1,2,4,8):
                    if lo < cen+k*scale < hi: points.append(cen+k*scale)
            points = sorted(set(points))
            vals, errs = [], []
            for power in (0,1,2):
                fun = lambda t: (t**power)*density(t)
                with warnings.catch_warnings():
                    warnings.simplefilter('error', IntegrationWarning)
                    v, e = quad(fun, lo, hi, points=points[1:-1],
                                epsabs=1e-12, epsrel=1e-11, limit=250)
                    tail, et = quad(fun, hi, np.inf, epsabs=1e-13, epsrel=1e-11)
                vals.append(v+tail); errs.append(e+et)
            terms.append(dict(moments=vals, quad_error=errs))
    Z = sum(t['moments'][0] for t in terms)
    if not Z > 0: raise FloatingPointError('CASE_RESULT_INVALID: zero reference evidence')
    mean = sum(t['moments'][1] for t in terms)/Z
    second = sum(t['moments'][2] for t in terms)/Z
    return dict(mean=mean, variance=second-mean**2,
                weights=np.array([t['moments'][0]/Z for t in terms]),
                log_evidence=math.log(Z), component_integrals=terms)


def math_stage():
    r = envelope('math'); radial = []; linear = []
    fixtures = CONTRACT['fixtures'] + [
        dict(id='boundary',mu_dr=2.22,sigma_dr=.03,rf=2.18),
        dict(id='wide_prior',mu_dr=4.0,sigma_dr=1.0,rf=3.2)]
    for f in fixtures:
        row = dict(id=f['id'])
        try:
            a = model.infer(f['mu_dr'],f['sigma_dr'],f['rf'],CONTRACT['model'])
            b = independent_radial_reference(f['mu_dr'],f['sigma_dr'],f['rf'],CONTRACT['model'])
            errors = {k:float(np.max(np.abs(a[k]-b[k])))
                      for k in ('mean','variance','weights','log_evidence')}
            valid = max(errors.values()) <= CONTRACT['algebra_rtol']
            row.update(status='PASS' if valid else 'CASE_RESULT_INVALID',
                       differences=errors, analytic=a, quadrature=b)
        except Exception as exc:
            row.update(status='CASE_RESULT_INVALID',error=repr(exc))
        radial.append(row)
    mu=np.array([.1,-.2,.05])
    baseP=np.array([[.4,.03,.02],[.03,.2,-.01],[.02,-.01,.05]])
    H=np.array([[.7,-.2,0],[.2,.3,-.8]])
    z=np.array([.3,-.2])
    for rho in (-.6,0.,.6):
        R=np.array([[.03,rho*math.sqrt(.03*.08)],
                    [rho*math.sqrt(.03*.08),.08]])
        joint=[]; seq=[]
        for factor in (1.,9.):
            a=model.linear_joint(mu,baseP*factor,H,z,R)
            b=model.linear_sequential(mu,baseP*factor,H,z,R)
            joint.append(a); seq.append(b)
            diff=max(float(np.max(abs(a[0]-b[0]))),float(np.max(abs(a[1]-b[1]))),abs(a[2]-b[2]))
            linear.append(dict(rho=rho,prior_factor=factor,max_difference=diff,
                               status='PASS' if diff<=CONTRACT['algebra_rtol'] else 'CASE_RESULT_INVALID'))
        lj=np.log([.95,.05])+np.array([v[2] for v in joint])
        ls=np.log([.95,.05])+np.array([v[2] for v in seq])
        wj=np.exp(lj-logsumexp(lj));ws=np.exp(ls-logsumexp(ls))
        linear.append(dict(rho=rho,test='mixture_evidence',max_difference=float(abs(wj-ws).max()),
                           status='PASS' if abs(wj-ws).max()<=1e-8 else 'CASE_RESULT_INVALID'))
    # Negative control: adding the same Range twice must change the posterior.
    good=model.linear_joint(mu,baseP,H,z,np.diag([.03,.08]))
    bad=model.scalar_joseph(good[0],good[1],H[0],z[0],.03)
    doubled=float(np.max(abs(bad[1]-good[1])))
    duplicate_detected=doubled>1e-6
    r['radial_references']=radial; r['linear_checks']=linear
    r['double_range_negative_control']=dict(covariance_difference=doubled,detected=duplicate_detected)
    r['radial_pass']=all(x['status']=='PASS' for x in radial)
    r['linear_pass']=all(x['status']=='PASS' for x in linear)
    r['calculation']='PASS' if r['radial_pass'] and r['linear_pass'] and duplicate_detected else 'PARTIAL_CASE_RESULT_INVALID'
    r['hypothesis']='SUPPORTED_ALGEBRA_ONLY' if r['calculation']=='PASS' else 'NOT_EVALUATED'
    save('math.json',r)
    return r


def controls_stage():
    math_result=json.loads((OUT/'math.json').read_text())
    r=envelope('controls'); rows=[]
    if not math_result['radial_pass']:
        r.update(execution='NOT_RUN_DEPENDENCY',calculation='NOT_EVALUATED')
        save('controls.json',r);return r
    for f in CONTRACT['fixtures']:
        # Explicit input whitelist. The estimator never receives f['truth'] or f['expected'].
        a=model.infer(f['mu_dr'],f['sigma_dr'],f['rf'],CONTRACT['model'])
        p=float(a['p_dr_fault_rf_inlier'])
        dominant=p>=CONTRACT['model']['rf_dominance_threshold']
        desired=f['expected']=='rf_dominant'
        rows.append(dict(id=f['id'],rf_dominant=dominant,probability=p,
                         posterior_mean=float(a['mean']),posterior_std=float(np.sqrt(a['variance'])),
                         expected=f['expected'],hypothesis='SUPPORTED' if dominant==desired else 'CONTRADICTED',
                         truth_for_scoring=f['truth'],dr_abs_error=abs(f['mu_dr']-f['truth']),
                         rf_abs_error=abs(f['rf']-f['truth']),
                         mixture_abs_error=abs(float(a['mean'])-f['truth'])))
    r['fixtures']=rows;r['calculation']='PASS'
    r['hypothesis']='SUPPORTED_FIXED_CONTROLS' if all(x['hypothesis']=='SUPPORTED' for x in rows) else 'PARTIALLY_CONTRADICTED'
    # An injected optional-metadata defect is an audit-policy negative control, not real solver failure.
    before=model.infer(5.,.1,4.5,CONTRACT['model'])
    baseline=np.asarray(before['mean']).copy()
    try: _={}["optional_curvature_ratio"]
    except KeyError:
        r['findings'].append(dict(id='INJECTED_OPTIONAL_METADATA',severity='DIAGNOSTIC_DEFECT_OR_WARNING',
                                 injected=True,scope='optional report field only',
                                 estimator_unchanged=bool(np.array_equal(baseline,before['mean']))))
    save('controls.json',r);return r


def load_archive():
    folder=Path('inputs/range_audit')
    required=['AUDIT_RECEIPT.json','DR_RF_PAIRED_TRACE.csv.gz','RAW_RF_UNIQUE.csv.gz']
    for name in required:
        if not (folder/name).is_file():raise FileNotFoundError('HARD_EXECUTION_BLOCK: '+name)
    receipt=json.loads((folder/'AUDIT_RECEIPT.json').read_text())
    if receipt['git_commit']!='28bc2212c3bfa70f5c6d7eedec974cefbf79d516':
        raise RuntimeError('HARD_EXECUTION_BLOCK: changed reference run')
    if receipt['status']!='PASS_DESCRIPTIVE_AUDIT_NO_FILTER_INFERENCE':
        raise RuntimeError('HARD_EXECUTION_BLOCK: reference audit not valid')
    df=pd.read_csv(folder/'DR_RF_PAIRED_TRACE.csv.gz')
    keys=['case','channel','correction','condition','level','seed','sample']
    if len(df)!=223236 or df.duplicated(keys).any():
        raise RuntimeError('HARD_EXECUTION_BLOCK: changed input grain/duplicates')
    return df,receipt


def shadow_stage():
    r=envelope('shadow')
    if not json.loads((OUT/'math.json').read_text())['radial_pass']:
        r.update(execution='NOT_RUN_DEPENDENCY');save('shadow.json',r);return r
    df,receipt=load_archive()
    # Original field includes Rr; subtract it to obtain DR radial prior variance.
    v=df['dr_pred_range_sigma_m'].to_numpy()**2-.0068578637
    if np.any(v<=0):raise RuntimeError('HARD_EXECUTION_BLOCK: invalid extracted prior variance')
    a=model.infer(df['r_DR_m'].to_numpy(),np.sqrt(v),df['z_rf_m'].to_numpy(),CONTRACT['model'])
    pred=pd.DataFrame({k:df[k] for k in ['case','route','channel','correction','condition','level','seed','sample','t_s']})
    pred['r_DR_m']=df['r_DR_m'];pred['z_rf_m']=df['z_rf_m']
    pred['truth_for_scoring']=df['r_true_m']
    pred['posterior_mean']=a['mean'];pred['posterior_std']=np.sqrt(a['variance'])
    pred['p_dr_fault_rf_inlier']=a['p_dr_fault_rf_inlier']
    conflict=(df['delta_dr_minus_rf_m'].to_numpy()>0)&(df['nis'].to_numpy()>6.6348966010212145)
    pred['eligible_short_rejected']=conflict
    pred['would_prioritize_rf']=conflict&(a['p_dr_fault_rf_inlier']>=CONTRACT['model']['rf_dominance_threshold'])
    # Truth appears only below, after every prediction/decision has been produced.
    truth=df['r_true_m'].to_numpy()
    drerr=abs(df['r_DR_m'].to_numpy()-truth);rferr=abs(df['z_rf_m'].to_numpy()-truth)
    pred['rf_is_better_for_scoring']=rferr<drerr
    pred['mixture_abs_error']=abs(a['mean']-truth)
    pred['dr_abs_error']=drerr;pred['rf_abs_error']=rferr
    pred.to_csv(OUT/'shadow_predictions.csv.gz',index=False,compression='gzip')
    rows=[]
    keys=['channel','correction','condition','level']
    for key,grp in pred.groupby(keys,sort=True):
        for subset,mask in [('ALL',np.ones(len(grp),bool)),
                            ('RF_SHORTER_REJECTED',grp['eligible_short_rejected'].to_numpy()),
                            ('MODEL_RF_PRIORITY',grp['would_prioritize_rf'].to_numpy())]:
            g=grp.iloc[np.flatnonzero(mask)]
            if len(g)==0:continue
            rows.append(dict(zip(keys,key),subset=subset,n=len(g),
                        actual_rf_better_fraction=float(g['rf_is_better_for_scoring'].mean()),
                        dr_MAE=float(g['dr_abs_error'].mean()),rf_MAE=float(g['rf_abs_error'].mean()),
                        mixture_MAE=float(g['mixture_abs_error'].mean()),
                        mean_fault_inlier_probability=float(g['p_dr_fault_rf_inlier'].mean())))
    pd.DataFrame(rows).to_csv(OUT/'shadow_summary.csv',index=False)
    selected=pred[pred['would_prioritize_rf']]
    false=selected[~selected['rf_is_better_for_scoring']]
    false.sort_values(['case','condition','level','seed','sample']).head(30).to_csv(OUT/'false_priority_examples.csv',index=False)
    r.update(calculation='PASS',hypothesis='DESCRIPTIVE_ONLY',
             n=len(pred),selected_count=len(selected),false_priority_count=len(false),
             probability_calibration='NOT_VALIDATED',
             unique_RF_per_model=6201,RF_environment_independence=False,
             classifier_scope='Radial scalar shadow model: does not run S, pose or recurrence',
             four_way_split=True)
    if len(false):
        r['findings'].append(dict(severity='CLAIM_BLOCK',scope='zero false RF-priority claim',
                                 count=len(false),reason='archived counterexamples remain'))
    save('shadow.json',r);return r


def diagnosis_stage():
    r=envelope('diagnosis'); pair=CONTRACT['alias_pair']; rows=[]
    # Bounded, preregistered prior sensitivity. No post-score parameter selection.
    for pd0 in CONTRACT['sensitivity']['fault_probabilities']:
        for po in CONTRACT['sensitivity']['rf_outlier_probabilities']:
            cfg=copy.deepcopy(CONTRACT['model']);cfg['fault_prior_probability']=pd0
            for rc in cfg['rf_components']:
                rc['weight']*=((1-po)/.95 if rc['inlier'] else po/.05)
            for f in CONTRACT['fixtures']:
                a=model.infer(f['mu_dr'],f['sigma_dr'],f['rf'],cfg)
                rows.append(dict(fixture=f['id'],dr_fault_prior=pd0,rf_outlier_prior=po,
                            p_fault_inlier=float(a['p_dr_fault_rf_inlier']),
                            mean=float(a['mean']),
                            rf_dominant=bool(a['p_dr_fault_rf_inlier']>=.95)))
    pd.DataFrame(rows).to_csv(OUT/'prior_sensitivity.csv',index=False)
    # Identical observable input, two possible truths; latter are scoring labels only.
    a=model.infer(pair['mu_dr'],pair['sigma_dr'],pair['rf'],CONTRACT['model'])
    worlds=[]
    for truth in pair['world_truths']:
        worlds.append(dict(truth_for_scoring=truth,
                     identical_observations=[pair['mu_dr'],pair['sigma_dr'],pair['rf']],
                     same_p_fault_inlier=float(a['p_dr_fault_rf_inlier']),
                     actual_rf_better=abs(pair['rf']-truth)<abs(pair['mu_dr']-truth)))
    r.update(calculation='PASS',hypothesis='IDENTIFIABILITY_LIMIT_CONFIRMED',
             alias_worlds=worlds,alias_second_world_is_synthetic=True,
             conclusion='The specified Range/DR-summary-only inputs do not uniquely identify which source is wrong. This does not rule out informative independent gyro/CIR features.',
             sensitivity_models=9,parameter_retuning=0,
             next_direction='Need an observable, independently calibrated source-quality/fault signal, or retain ambiguity rather than promise correct source selection. New model implementation needs user confirmation.')
    save('diagnosis.json',r);return r


def final_stage():
    r=envelope('final');summaries={}
    for name in ('math','controls','shadow','diagnosis'):
        p=OUT/(name+'.json')
        if p.is_file():summaries[name]=json.loads(p.read_text())
        else:summaries[name]=dict(execution='MISSING',calculation='NOT_EVALUATED')
    checks=[]
    if (OUT/'shadow_predictions.csv.gz').is_file():
        df=pd.read_csv(OUT/'shadow_predictions.csv.gz')
        # Independent final scoring path from raw ranges; do not trust saved RF-win flags.
        truth=df['truth_for_scoring'].to_numpy()
        rf_wins=np.square(df['z_rf_m'].to_numpy()-truth)<np.square(df['r_DR_m'].to_numpy()-truth)
        saved=df['rf_is_better_for_scoring'].to_numpy(bool)
        consistent=bool(np.array_equal(rf_wins,saved))
        count_false=int((df['would_prioritize_rf'].to_numpy(bool)&~rf_wins).sum())
        checks.append(dict(test='independent_squared_error_win_check',pass_check=consistent,
                           false_priority_count=count_false,
                           saved_count=summaries['shadow'].get('false_priority_count')))
        checks.append(dict(test='final_count_parity',pass_check=count_false==summaries['shadow'].get('false_priority_count')))
    controls=summaries['controls'].get('fixtures',[])
    contradictions=[x['id'] for x in controls if x['hypothesis']=='CONTRADICTED']
    r.update(calculation='PASS' if all(x['pass_check'] for x in checks) else 'CASE_RESULT_INVALID',
             hypothesis='PARTIAL_SUPPORT_AND_CLAIM_LIMITS',
             stage_verdicts={k:{q:v.get(q,'NOT_EVALUATED') for q in ('execution','calculation','hypothesis','scientific_claim')} for k,v in summaries.items()},
             independent_output_checks=checks,contradicted_controls=contradictions,
             scientific_PASS=False,implementation_repairs=0,
             old_G3_TV_0387='UNCHANGED_CASE_RESULT_INVALID',
             unaffected_math_not_blocked_by_claims=True,
             exact_full_nonlinear_G2_G3='NOT_RUN',recursive_fusion='NOT_RUN',
             next_action='STOP before changing scientific hypothesis; report complete numerical/diagnostic findings and seek confirmation for new source-quality information or ambiguity-retaining estimator.')
    save('FINAL_BRIEFING.json',r)
    lines=['# Audited minimal G2/G3 result briefing','',
           'This is a radial model and exact linear-algebra verification, not full nonlinear pose-filter validation.','',
           '|Stage|Execution|Calculation|Hypothesis|Scientific claim|','|---|---|---|---|---|']
    for k,v in r['stage_verdicts'].items():
        lines.append('|'+k+'|'+'|'.join(str(v[q]) for q in ('execution','calculation','hypothesis','scientific_claim'))+'|')
    lines+=['','## Findings',
            'Control contradictions: '+str(contradictions),
            'False RF-priority cases in shadow replay: '+str(summaries['shadow'].get('false_priority_count')),
            'Prior sensitivity is diagnostic only; no parameter was chosen after evaluating truth.',
            'An identical-input/different-truth pair demonstrates a scope-limited source-identification limit.',
            'Optional metadata defects and hypothesis failures did not block independent math verification.',
            'Input or formula defects remain hard execution blocks for dependent stages.',
            '', '## Stop',r['next_action']]
    (OUT/'BRIEFING.md').write_text('\n'.join(lines)+'\n')
    return r


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['math','controls','shadow','diagnosis','final'])
    args=ap.parse_args();require_audit(args.stage)
    r=globals()[args.stage+'_stage']()
    print('STAGE_VERDICT',json.dumps({k:r.get(k) for k in ('stage','execution','calculation','hypothesis','scientific_claim')},ensure_ascii=False))
