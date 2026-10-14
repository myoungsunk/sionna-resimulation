"""Bounded diagnostic repair: same posterior, different probability questions.

No change to model.py, CONTRACT parameters, RF data, or threshold. A direct
CDF readout is a diagnostic, not deployment of a new G2/G3 estimator.
"""
from __future__ import annotations
import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/'outputs/readout_review'


def audit_first():
    OUT.mkdir(parents=True,exist_ok=False)
    approval=json.loads((ROOT/'READOUT_APPROVAL.json').read_text())
    r=dict(audit_id=approval['audit_id'],source_commit=subprocess.check_output(
           ['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
           source_sha256={},run_decision='HOLD',audited_code_matches_execution_sha=False,
           independent_reviewer=False,audit_method='source and algebra review; independent integral readout check',
           scope='same frozen posterior; bounded probability-readout and claim-scope diagnostic')
    try:
        if approval['review_decision']!='GO_WITH_CLAIM_LIMITATION':raise RuntimeError('readout not approved')
        for name,expected in approval['source_git_blobs'].items():
            p=REPO/name
            actual=subprocess.check_output(['git','hash-object',str(p)],text=True).strip()
            if actual!=expected:raise RuntimeError('HARD_EXECUTION_BLOCK: unreviewed readout source '+name)
            r['source_sha256'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
        acq=json.loads((REPO/'inputs/range_audit/ACQUISITION.json').read_text())
        if acq['zip_sha256']!=approval['reference_zip_sha256']:
            raise RuntimeError('HARD_EXECUTION_BLOCK: input reference ZIP drift')
        for name,expected in acq['file_sha256'].items():
            if hashlib.sha256((REPO/'inputs/range_audit'/name).read_bytes()).hexdigest()!=expected:
                raise RuntimeError('HARD_EXECUTION_BLOCK: extracted reference drift')
        r.update(run_decision='GO_WITH_CLAIM_LIMITATION',audited_code_matches_execution_sha=True,
                 input_sha256=acq['file_sha256'])
    finally:
        (OUT/'PRE_RUN_READOUT_AUDIT.json').write_text(json.dumps(r,indent=2))
    print('READOUT_PRE_AUDIT',r['run_decision'])


def main():
    audit_first()  # Before importing/executing scientific computation.
    import numpy as np
    import pandas as pd
    from scipy.special import log_ndtr
    from scipy.stats import norm
    from scipy.integrate import quad
    import model
    C=json.loads((ROOT/'CONTRACT.json').read_text())
    cfg=C['model']

    def readout(mu,sigma,z):
        mu,sigma,z=np.broadcast_arrays(np.asarray(mu,float),np.asarray(sigma,float),np.asarray(z,float))
        result=model.infer(mu,sigma,z,cfg)
        midpoint=(mu+z)*.5
        lo=cfg['lower_slant_m']
        component_cdf=[]
        for fault in (False,True):
            vd=sigma*sigma+(cfg['fault_radial_std_m']**2 if fault else 0)
            for rc in cfg['rf_components']:
                vr=rc['std_m']**2
                # Same posterior component parameters as audited product identity.
                v=vd*vr/(vd+vr);m=(vr*mu+vd*(z-rc['bias_m']))/(vd+vr)
                s=np.sqrt(v)
                logratio=log_ndtr((m-midpoint)/s)-log_ndtr((m-lo)/s)
                fj=np.where(midpoint>lo,-np.expm1(np.minimum(logratio,0.0)),0.0)
                component_cdf.append(np.clip(fj,0,1))
        F=np.sum(result['weights']*np.stack(component_cdf,axis=-1),axis=-1)
        pbetter=np.where(mu>z,F,np.where(mu<z,1-F,0.0))
        return result,np.clip(pbetter,0,1)

    def independent_probability(mu,sigma,z):
        # Integrate raw prior*likelihood directly. Does not use readout's CDF,
        # posterior component means, or production weights.
        lo=cfg['lower_slant_m'];mid=(mu+z)/2
        def target(r):
            pd=0.0
            for fault,w in ((False,1-cfg['fault_prior_probability']),(True,cfg['fault_prior_probability'])):
                sd=math.sqrt(sigma*sigma+(cfg['fault_radial_std_m']**2 if fault else 0))
                pd+=w*norm.pdf((r-mu)/sd)/sd/norm.sf((lo-mu)/sd)
            likelihood=sum(v['weight']*norm.pdf((z-r-v['bias_m'])/v['std_m'])/v['std_m']
                           for v in cfg['rf_components'])
            return pd*likelihood
        hi=max(lo+2,mu+16*math.sqrt(sigma*sigma+cfg['fault_radial_std_m']**2),
               max(z-v['bias_m']+16*v['std_m'] for v in cfg['rf_components']))
        points=[lo,hi]
        for center,sd in [(mu,sigma),(mu,math.sqrt(sigma*sigma+cfg['fault_radial_std_m']**2))]+[
                         (z-v['bias_m'],v['std_m']) for v in cfg['rf_components']]:
            points.extend(center+k*sd for k in (-8,-4,-2,-1,0,1,2,4,8) if lo<center+k*sd<hi)
        def integral(upper):
            if upper<=lo:return 0.0
            p=sorted(set(t for t in points if lo<t<upper))
            return quad(target,lo,upper,points=p,epsabs=1e-12,epsrel=1e-11,limit=250)[0]
        den=integral(hi)+quad(target,hi,np.inf,epsabs=1e-13)[0]
        if not den>0:raise RuntimeError('CASE_RESULT_INVALID: direct integral zero')
        below=integral(mid)/den
        return below if mu>z else (1-below if mu<z else 0.0)

    fixtures=[]
    for f in C['fixtures']:
        a,p=readout(f['mu_dr'],f['sigma_dr'],f['rf'])
        q=independent_probability(f['mu_dr'],f['sigma_dr'],f['rf'])
        error=abs(float(p)-q)
        fixtures.append(dict(id=f['id'],p_fault_inlier=float(a['p_dr_fault_rf_inlier']),
                       p_RF_distance_better=float(p),independent_integral_probability=q,
                       absolute_readout_error=error,
                       old_probability_threshold_met=bool(a['p_dr_fault_rf_inlier']>=.95),
                       direct_probability_threshold_met=bool(p>=.95),
                       truth_for_scoring=f['truth'],dr_abs_error=abs(f['mu_dr']-f['truth']),
                       rf_abs_error=abs(f['rf']-f['truth']),
                       mixture_abs_error=abs(float(a['mean'])-f['truth'])))
    numeric_ok=all(r['absolute_readout_error']<=1e-8 for r in fixtures)
    report=dict(execution='PASS',calculation='PASS' if numeric_ok else 'CASE_RESULT_INVALID',
                hypothesis='FAULT_EVENT_IS_NOT_DISTANCE_ADVANTAGE_EVENT',
                scientific_claim='CLAIM_BLOCK_UNCALIBRATED_POSTERIOR_AND_FULL_POSE',
                scientific_PASS=False,fixtures=fixtures,parameter_changes=0,threshold_changes=0,
                new_estimator_adopted=False,scope='probability-readout diagnostic only',
                formula='delta>0: P(RF closer|data)=P(r_true<(mu_DR+z_RF)/2|data); delta<0: complementary event',
                constant_model_blob='1b13e7fa1909168f3f7cb2d35d2d86d4c00cb5b9')
    if not numeric_ok:
        (OUT/'READOUT_RESULT.json').write_text(json.dumps(report,indent=2))
        raise RuntimeError('CASE_RESULT_INVALID: CDF/integral mismatch; do not replay')
    df=pd.read_csv(REPO/'inputs/range_audit/DR_RF_PAIRED_TRACE.csv.gz')
    var=df['dr_pred_range_sigma_m'].to_numpy()**2-.0068578637
    if len(df)!=223236 or np.any(var<=0):raise RuntimeError('HARD_EXECUTION_BLOCK: input dimensions/variance')
    a,p=readout(df['r_DR_m'].to_numpy(),np.sqrt(var),df['z_rf_m'].to_numpy())
    eligible=(df['delta_dr_minus_rf_m'].to_numpy()>0)&(df['nis'].to_numpy()>6.6348966010212145)
    old=eligible&(a['p_dr_fault_rf_inlier']>=.95)
    new=eligible&(p>=.95)
    # Predictions and selections were completed BEFORE using truth for scoring.
    truth=df['r_true_m'].to_numpy()
    wins=(df['z_rf_m'].to_numpy()-truth)**2<(df['r_DR_m'].to_numpy()-truth)**2
    def aggregate(mask):
        n=int(mask.sum());bad=int((mask&~wins).sum())
        return dict(n_selected=n,n_less_accurate_RF=bad,
                    observed_precision=float(wins[mask].mean()) if n else None,
                    mean_model_probability=float(p[mask].mean()) if n else None)
    report.update(n_rows=len(df),eligible_n=int(eligible.sum()),
                  old_fault_event_selection=aggregate(old),direct_distance_selection=aggregate(new),
                  zero_activation_not_evidence_of_safety=bool(old.sum()==0))
    rows=[]
    for key,ix in df.groupby(['channel','correction','condition','level']).indices.items():
        mask=np.zeros(len(df),bool);mask[ix]=new[ix]
        if not mask.any():continue
        # Export-only repair: retain numerical values but convert NumPy scalar labels.
        key=tuple(v.item() if isinstance(v,np.generic) else v for v in key)
        rows.append(dict(zip(['channel','correction','condition','level'],key),**aggregate(mask)))
    pd.DataFrame(rows).to_csv(OUT/'DIRECT_READOUT_BY_CONDITION.csv',index=False)
    report['by_condition']=rows
    report['claim_scope_repairs']=[
       'C2 failing the old 95% fault-event threshold does not imply RF failed to improve the estimate.',
       'No RF-priority activation gives no empirical false-priority precision; report null rather than perfect safety.',
       'C4 non-dominant flag is not protection of the continuous mixture mean; record its point-estimate harm.',
       'Direct distance probability is conditional on the same uncalibrated synthetic model, not an externally calibrated 95% guarantee.']
    report['next_action']='STOP before adopting a new online decision or changing the prior/model; provide diagnostic repair and request direction confirmation.'
    report['export_repair']=dict(previous_run=38527288934,scope='NumPy scalar group labels to JSON native scalars',numerical_code_changed=False)
    (OUT/'READOUT_RESULT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False))
    print('READOUT_FINAL',json.dumps(report,ensure_ascii=False,allow_nan=False))


if __name__=='__main__':main()
