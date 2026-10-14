#!/usr/bin/env python3
"""B-only RF signed-error calibration eligibility, and distance-win probability audit.

Uses immutable previously validated RF/DR artifact; no inference of online RF
quality from truth. Train folds are leave-one-route-out but SPATIALLY OVERLAP:
their scores are exploratory, NOT independent-scene calibration evidence.
The Gaussian signed-error likelihood uses channel/model only. z_obs bins are
DESCRIPTIVE ONLY and are never inserted naively as a generative likelihood.
"""
from __future__ import annotations
import argparse
import gzip
import hashlib
import io
import json
import math
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.integrate import quad
from scipy.special import ndtr, logsumexp

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
OUT=REPO/"outputs"/"B_RF_SIGNED"
INPUT=REPO/"inputs"/"B_RF_SIGNED"
C=json.loads((HERE/"CONTRACT.json").read_text())

def serialize(obj):
    if isinstance(obj,np.generic):return obj.item()
    if isinstance(obj,np.ndarray):return obj.tolist()
    raise TypeError(type(obj).__name__)

def save_json(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name
    if p.exists():raise FileExistsError(str(p))
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=serialize))

def verified_data():
    p=INPUT/"frozen_source.zip"
    if not p.exists():raise RuntimeError("HARD_EXECUTION_BLOCK: archive not acquired")
    if hashlib.sha256(p.read_bytes()).hexdigest()!=C["source"]["zip_sha256"]:
        raise RuntimeError("HARD_EXECUTION_BLOCK: archive SHA differs")
    import zipfile
    with zipfile.ZipFile(p) as z:
        names=("RAW_RF_UNIQUE.csv.gz","DR_RF_PAIRED_TRACE.csv.gz","AUDIT_RECEIPT.json")
        if any(n not in z.namelist() for n in names):
            raise RuntimeError("HARD_EXECUTION_BLOCK: archive lacks frozen records")
        src=json.loads(z.read("AUDIT_RECEIPT.json"))
        if src["status"]!="PASS_DESCRIPTIVE_AUDIT_NO_FILTER_INFERENCE" or src["input_parity"]!="PASS_D04_RF_AND_ARCHIVED_D0":
            raise RuntimeError("HARD_EXECUTION_BLOCK: frozen D0/D4 audit invalid")
        rf=pd.read_csv(io.BytesIO(gzip.decompress(z.read(names[0]))))
        dr=pd.read_csv(io.BytesIO(gzip.decompress(z.read(names[1]))))
    expected=int(C["source"]["unique_rf_n"]),int(C["source"]["dr_pairs_n"])
    if (len(rf),len(dr))!=expected:
        raise RuntimeError("HARD_EXECUTION_BLOCK: frozen record count mismatch")
    if rf.duplicated(["case","channel","correction","sample"]).any():
        raise RuntimeError("HARD_EXECUTION_BLOCK: duplicated unique RF record")
    if dr.duplicated(["case","channel","correction","condition","level","seed","sample"]).any():
        raise RuntimeError("HARD_EXECUTION_BLOCK: duplicated DR paired record")
    if rf["route"].nunique()!=3 or dr["route"].nunique()!=3:
        raise RuntimeError("HARD_EXECUTION_BLOCK: RF route domain changed")
    if not np.isfinite(rf["rf_signed_error_m"]).all():
        raise RuntimeError("HARD_EXECUTION_BLOCK: invalid RF residuals")
    # Matched truth-only scoring; these are NOT estimator features.
    if np.max(np.abs(rf["z_rf_m"]-rf["r_true_m"]-rf["rf_signed_error_m"]))>1e-9:
        raise RuntimeError("HARD_EXECUTION_BLOCK: RF residual identity fails")
    if np.max(np.abs(dr["r_DR_m"]-dr["z_rf_m"]-dr["delta_dr_minus_rf_m"]))>1e-9:
        raise RuntimeError("HARD_EXECUTION_BLOCK: DR-RF discrepancy identity fails")
    return rf,dr

def error_fitted(sample):
    v=np.asarray(sample,float)
    mu=float(v.mean())
    sd=float(v.std(ddof=0))
    if len(v)<30 or sd<1e-6:
        raise RuntimeError("CASE_RESULT_INVALID: too few or degenerate training residuals")
    return mu,sd

def emetrics(err):
    x=np.asarray(err,float)
    return dict(n=len(x),mean_m=float(x.mean()),median_m=float(np.median(x)),
        std_m=float(x.std()),rmse_m=float(np.sqrt(np.mean(x*x))),
        p_under=float(np.mean(x<0)),p_under_05m=float(np.mean(x<-.05)),
        p_under_10m=float(np.mean(x<-.10)),p_over_20m=float(np.mean(x>.20)),
        signed_q01_m=float(np.quantile(x,.01)),
        signed_q05_m=float(np.quantile(x,.05)),
        signed_q95_m=float(np.quantile(x,.95)),
        signed_q99_m=float(np.quantile(x,.99)))

def one_sided(train,heldout):
    x=np.asarray(train,float); y=np.asarray(heldout,float)
    tau95=max(0.,-float(np.quantile(x,.05)))
    tau99=max(0.,-float(np.quantile(x,.01)))
    return dict(train_n=len(x),heldout_n=len(y),tau95_m=tau95,tau99_m=tau99,
        heldout_95_coverage=float(np.mean(y>=-tau95)),
        heldout_99_coverage=float(np.mean(y>=-tau99)))

def dr_mixture_win(delta,sdr,muR,sR,pfault,faultstd):
    """Exact independent normal error convolution for E_D - E_RF = delta.

    E_R ~ N(muR,sR²) and E_D follows nominal normal or predeclared broad
    fault component. No truth labels, no same-Range double measurement.
    Source calibration assumptions, not a full nonlinear range likelihood.
    """
    d=np.asarray(delta,float); sd=np.asarray(sdr,float)
    if np.any(sd<=0) or sR<=0:
        raise ValueError("HARD_EXECUTION_BLOCK: bad DR or RF error std")
    a=sd*sd
    weights=[]
    posterior=[]
    for pf,extra in ((1-pfault,0.),(pf,faultstd)):
        vD=a+extra*extra
        vr=sR*sR
        V=vD+vr
        # delta=E_D-E_R; prior mean(E_D)=0, mean(E_R)=muR.
        logev=-.5*(np.log(2*math.pi*V)+(d+muR)**2/V)+np.log(pf)
        postvar=vD*vr/V
        postmean=(muR*vD-d*vr)/V
        cut=-d/2
        t=(postmean-cut)/np.sqrt(postvar)
        prob=np.where(d>0,ndtr(t),np.where(d<0,ndtr(-t),0.))
        weights.append(logev)
        posterior.append(prob)
    lw=np.stack(weights,axis=-1)
    w=np.exp(lw-logsumexp(lw,axis=-1,keepdims=True))
    return np.clip(np.sum(w*np.stack(posterior,axis=-1),axis=-1),0,1)

def direct_scalar_probability(delta,drstd,muR,sR,pfault,faultstd):
    from scipy.stats import norm
    def integrand(er):
        pr=norm.pdf(er,loc=muR,scale=sR)
        drerr=delta+er
        return pr*((1-pfault)*norm.pdf(drerr,0,drstd)+
                    pfault*norm.pdf(drerr,0,math.hypot(drstd,faultstd)))
    pivot=-delta/2
    den=quad(integrand,-np.inf,np.inf,epsabs=1e-13,epsrel=1e-11)[0]
    if den<=0:raise RuntimeError("CASE_RESULT_INVALID: independent evidence zero")
    if delta>0:
        num=quad(integrand,pivot,np.inf,epsabs=1e-13,epsrel=1e-11)[0]
    elif delta<0:
        num=quad(integrand,-np.inf,pivot,epsabs=1e-13,epsrel=1e-11)[0]
    else:
        num=0.
    return num/den

def fixture():
    tests=[(.3,.2,-.025,.05,0.,2.),(-.4,.15,.025,.11,.05,2.),
           (.15,.4,0.,.08,.05,2.),(-.3,.1,-.02,.14,.20,1.),
           (.06,.25,0.,.07,0.,2.),(.5,.08,-.03,.10,.1,2.)]
    rows=[]
    for delta,sd,mu,sr,pf,fstd in tests:
        exact=float(dr_mixture_win(np.array([delta]),np.array([sd]),mu,sr,pf,fstd)[0])
        independent=direct_scalar_probability(delta,sd,mu,sr,pf,fstd)
        diff=abs(exact-independent)
        rows.append(dict(delta=delta,dr_sigma=sd,rf_mean=mu,rf_sigma=sr,
            pfault=pf,fault_std=fstd,analytic=exact,
            independent=independent,absolute_difference=diff))
    passed=max(x["absolute_difference"] for x in rows)<=C["math_atol"]
    save_json("B_MATH_AUDIT.json",dict(status="PASS" if passed else "CASE_RESULT_INVALID",
        claims="Exact 1D Gaussian-error distance superiority only; NOT calibration",
        rows=rows,maximum_difference=max(x["absolute_difference"] for x in rows)))
    if not passed:raise RuntimeError("CASE_RESULT_INVALID: probability algebra discrepancy")
    print("B_MATH_AUDIT PASS",flush=True)

def calibration_report():
    rf,dr=verified_data()
    rf["observed_range_bin"]=pd.cut(rf["z_rf_m"],
                       [-np.inf,5.,10.,np.inf],
                       labels=["lt5","5to10","ge10"])
    records=[]
    diagnostics=[]
    train_models={}
    for (channel,correction),df in rf.groupby(["channel","correction"],sort=True):
        for route in ("R2","R4","R5"):
            tr=df[df.route!=route]
            te=df[df.route==route]
            mean,sd=error_fitted(tr.rf_signed_error_m)
            train_models[(channel,correction,route)]=(mean,sd)
            score=one_sided(tr.rf_signed_error_m,te.rf_signed_error_m)
            test_error=te.rf_signed_error_m.to_numpy(float)
            normal_ll=-.5*((test_error-mean)/sd)**2-np.log(sd*math.sqrt(2*math.pi))
            from scipy.stats import kstest
            pit=ndtr((test_error-mean)/sd)
            ks=float(kstest(pit,"uniform").statistic)
            records.append(dict(channel=channel,correction=correction,holdout_route=route,
                train_n=len(tr),test_n=len(te),train_mu_m=mean,train_sigma_m=sd,
                test_mean_m=float(test_error.mean()),test_rmse_m=float(np.sqrt(np.mean(test_error**2))),
                test_normal_95_interval_coverage=float(np.mean(np.abs(test_error-mean)<=1.96*sd)),
                test_signed_gaussian_nll=float(-np.mean(normal_ll)),
                test_PIT_uniform_KS=ks,**score))
            # Q_proxy = observed r-bin, NOT a correct generative p(z|r,Q)
            for observed_bin,b in te.groupby("observed_range_bin",observed=True):
                t=tr[tr["observed_range_bin"]==observed_bin]
                if len(t)<30:continue
                err=t.rf_signed_error_m.to_numpy(float)
                e=b.rf_signed_error_m.to_numpy(float)
                tau=max(0.,-np.quantile(err,.05))
                p_global=(np.count_nonzero(tr.rf_signed_error_m.to_numpy() < -.10)+1)/(len(tr)+2)
                p_bin=(np.count_nonzero(err < -.10)+1)/(len(err)+2)
                target=(e<-.10).astype(float)
                diagnostics.append(dict(channel=channel,correction=correction,
                    holdout_route=route,observed_bin=str(observed_bin),n=len(e),train_n=len(t),
                    rf_mean_m=float(e.mean()),rf_sd_m=float(e.std()),
                    p_under_10cm=float(target.mean()),test_signed_tau95_coverage=float(np.mean(e>=-tau)),
                    train_tau95_m=float(tau),prediction_p_under_10_global=float(p_global),
                    prediction_p_under_10_bin=float(p_bin),
                    brier_global=float(np.mean((target-p_global)**2)),
                    brier_bin=float(np.mean((target-p_bin)**2))))
    pd.DataFrame(records).to_csv(OUT/"RF_HELDOUT_BY_ROUTE.csv",index=False)
    pd.DataFrame(diagnostics).to_csv(OUT/"RF_QPROXY_BY_OBS_DISTANCE.csv",index=False)
    unique_summary=[]
    for (ch,model),g in rf.groupby(["channel","correction"],sort=True):
        unique_summary.append(dict(channel=ch,correction=model,**emetrics(g.rf_signed_error_m)))
    pd.DataFrame(unique_summary).to_csv(OUT/"RF_SIGNED_ERROR_METRICS.csv",index=False)
    print("B_RF route-split residual score complete",len(records),flush=True)

    groups=[]
    predictions=[]
    for (ch,model,route),g in dr.groupby(["channel","correction","route"],sort=True):
        mu,sd=train_models[(ch,model,route)]
        delta=g.delta_dr_minus_rf_m.to_numpy(float)
        innovation=g.dr_pred_range_sigma_m.to_numpy(float)
        drvar=innovation**2-C["original_r_r"]
        if (drvar<=0).any():raise RuntimeError("HARD_EXECUTION_BLOCK: RF variance counted twice or invalid")
        drstd=np.sqrt(drvar)
        nom=dr_mixture_win(delta,drstd,mu,sd,0.,C["trial_fault_sigma_m"])
        alt=dr_mixture_win(delta,drstd,mu,sd,
                           C["trial_fault_probability"],C["trial_fault_sigma_m"])
        y=g.rf_wins.to_numpy(bool).astype(float)
        for name,p in (("nominal_dr",nom),("trial_fault_prior",alt)):
            predictions.append(pd.DataFrame(dict(channel=ch,correction=model,route=route,
                case=g.case.to_numpy(),condition=g.condition.to_numpy(),
                level=g.level.to_numpy(),seed=g.seed.to_numpy(),
                sample=g["sample"].to_numpy(),n_is_rejected=g.nis.to_numpy()>C["nis99"],
                rf_is_shorter=(delta>0),pwin=p,y=y,p_model=name)))
    pred=pd.concat(predictions,ignore_index=True)
    pred.to_csv(OUT/"RF_WIN_PROB_TRACE.csv.gz",index=False,compression="gzip")

    def score(g,label):
        p=np.clip(g.pwin.to_numpy(float),1e-12,1-1e-12)
        y=g.y.to_numpy(float)
        selected=p>=C["diagnostic_probability_threshold"]
        return dict(group=label,n=len(g),positive_rate=float(y.mean()),
            brier=float(np.mean((p-y)**2)),log_loss=float(np.mean(-y*np.log(p)-(1-y)*np.log1p(-p))),
            ece_10bin=float(sum(len(g0)/len(g)*abs(g0.pwin.mean()-g0.y.mean())
                for _,g0 in g.groupby(pd.cut(g.pwin,np.linspace(0,1,11),
                              include_lowest=True),observed=True))),
            pwin_ge95_n=int(selected.sum()),
            pwin_ge95_false_n=int(np.count_nonzero(selected & (y==0))),
            pwin_ge95_precision=float(y[selected].mean()) if selected.any() else None)
    scores=[]
    for (method,ch,model,condition,level),g in pred.groupby(
        ["p_model","channel","correction","condition","level"],sort=True):
        scores.append(dict(method=method,channel=ch,correction=model,
             condition=condition,level=int(level),**score(g,"ALL")))
        conf=g[(g.rf_is_shorter)&(g.n_is_rejected)]
        if len(conf):
            scores.append(dict(method=method,channel=ch,correction=model,
                condition=condition,level=int(level),**score(conf,"SHORTER_AND_NIS_REJECT")))
    pd.DataFrame(scores).to_csv(OUT/"RF_WIN_CALIBRATION_SCORES.csv",index=False)
    # DR fault-proxy diagnostic: truth for scoring only, sensor seed not independent.
    dr_base=dr[(dr.channel=="los")&(dr.correction=="B_OLD")].copy()
    drbase=[]
    for (cond,level,route),g in dr_base.groupby(["condition","level","route"]):
        sd=np.sqrt(np.maximum(g.dr_pred_range_sigma_m.to_numpy(float)**2-C["original_r_r"],0))
        error=g.dr_signed_error_m.to_numpy(float)
        zscores=error/sd
        drbase.append(dict(condition=cond,level=int(level),route=route,n=len(g),
            predicted_sigma_mean_m=float(sd.mean()),
            actual_DR_abs_error_mean_m=float(np.mean(np.abs(error))),
            actual_DR_rmse_m=float(np.sqrt(np.mean(error**2))),
            out_of_95_gaussian_fraction=float(np.mean(np.abs(zscores)>1.95996398454)),
            radial_error_gt_0_5m=float(np.mean(np.abs(error)>.5)),
            absolute_normalized_DR_error_p95=float(np.quantile(np.abs(zscores),.95))))
    pd.DataFrame(drbase).to_csv(OUT/"DR_FAULT_PRIOR_DIAGNOSTIC.csv",index=False)

    summary=dict(
        stage="B",status="EXECUTED_CALIBRATION_DIAGNOSTIC",
        numerical_result="PASS_FOR_AUDITED_SCORES_AND_FORMULA_ONLY",
        hypotheses=dict(
            RF_signed_error_may_be_described="SUPPORTED_IN_FROZEN_DATA",
            observed_range_bin_predicts_tail="EVALUATED_DESCRIPTIVELY_NOT_GENERATIVE",
            RF_error_metrics_directly_equal_RF_DR_win_probability="FALSE_REQUIRES_DR_ERROR_AND_DELTA",
            independent_R2_R5_spatial_calibration="NOT_ELIGIBLE_ORIGINAL_0_5M_HOLDOUT",
            actual_online_CIR_quality_calibrated="NOT_TESTED",
            actual_online_DR_fault_prior_calibrated="NOT_TESTED"),
        scientific_claim="CLAIM_BLOCK_INDEPENDENT_CALIBRATION_AND_TRUE_PROBABILITY",
        scientific_PASS=False,
        source_artifact=C["source"],routes=["R2","R4","R5"],
        rows_unique_RF=int(len(rf)),rows_paired=int(len(dr)),
        audit_conditions="RF fitting excludes the heldout route; time/spatial reuse still violates independent-scene certification.",
        fitted_gaussian_train_route_only=True,
        no_truth_used_for_prediction=True,
        truth_used_only_as_RF_training_labels_and_eval_scoring=True,
        source_signed=unique_summary,
        heldout_route_coverage=records,
        dr_fault_prior_trials=["nominal_DR", "fixed_0.05_fault_2m_trial"],
        not_a_valid_likelihood_warning="Conditioning on observed z-bin cannot be naively used as normalized generative p(z|r,Q).",
        next_action="Assess independent CIR/gyro data eligibility, not claim a calibrated RF superiority posterior.")
    save_json("B_REPORT.json",summary)
    print("B_FINAL",json.dumps({k:summary[k] for k in ("status","scientific_claim","rows_unique_RF","rows_paired")}),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("stage",choices=("fixture","evaluate"))
    arg=parser.parse_args()
    if arg.stage=="fixture":
        fixture()
    else:
        math_report=OUT/"B_MATH_AUDIT.json"
        if not math_report.exists() or json.loads(math_report.read_text())["status"]!="PASS":
            raise RuntimeError("HARD_EXECUTION_BLOCK: numerical formula fixture not PASS")
        calibration_report()
