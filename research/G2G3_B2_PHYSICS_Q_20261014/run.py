#!/usr/bin/env python3
"""B2 physically widened signed RF-error density, observable CIR Q, C1-C4, D algebra smoke.

No test-scene label, truth, or gyro-injection label enters the estimator.
Acquires verified external source only through original approved extraction.
No new RF calibration success claim if cross-scene PIT/coverage fails.
"""
from __future__ import annotations
import json,math,sys,traceback
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.special import expit
from scipy.stats import norm, t as student, kstest
from scipy.optimize import minimize,brentq
from scipy.integrate import quad,simpson

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
BASE=REPO/"research/G2G3_BC_CROSSSCENE_20261014"
PRE=REPO/"outputs/BC_CROSSSCENE"
OUT=REPO/"outputs/B2_PHYSICS_Q"
C=json.loads((ROOT/"CONTRACT.json").read_text())
OLD=json.loads((BASE/"CONTRACT.json").read_text())
qbin=float(C["detector_resolution_m"])

def serial(v):
    if isinstance(v,np.generic):return v.item()
    if isinstance(v,np.ndarray):return v.tolist()
    raise TypeError(str(type(v)))

def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name
    if p.exists():raise FileExistsError("Refusing overwrite "+str(p))
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=serial))

def audited(stage):
    r=json.loads((OUT/f"PRE_RUN_{stage}.json").read_text())
    if not r.get("audited_code_matches_execution_sha") or r.get("run_decision")!="GO_WITH_CLAIM_LIMITATION":
        raise RuntimeError("HARD_EXECUTION_BLOCK: missing approved source+input audit")

def features(df):
    # These are observable from the RF signal; no labels, true range, route or XY.
    gap=df["median_peak_gap_m"].to_numpy(float)
    energy=df["median_FP_energy_fraction"].to_numpy(float)
    ratio=df["median_fp_peak_ratio"].to_numpy(float)
    # Frozen dimensionless transforms; NO prior knowledge of heldout truth used.
    return np.stack([
        np.clip(gap/3.,0.,2.),
        np.clip(-np.log(np.maximum(energy,1e-8)) - 3.5,-2.,3.),
        np.clip((.4-ratio)*5.,-3.,3.),
    ],axis=1)

def fit(training):
    clean=training[training.los_clear]
    bad=training[~training.los_clear]
    if len(clean)<20 or len(bad)<8:raise RuntimeError("CASE_RESULT_INVALID: insufficient office groups")
    e=clean.signed_error_mean_m.to_numpy(float)
    eb=bad.signed_error_mean_m.to_numpy(float)
    mu=float(np.mean(e));sigma=float(np.std(e,ddof=1))
    loc=float(np.median(eb))
    scale=float(max(.06,1.4826*np.median(np.abs(eb-loc))))
    X=features(training)
    mean=X.mean(axis=0);sd=np.maximum(X.std(axis=0),.5)
    Xs=(X-mean)/sd
    XX=np.column_stack([np.ones(len(Xs)),Xs])
    y=(~training.los_clear).to_numpy(int).astype(float)
    penalty=C["logistic_regularization"]
    def obj(w):
        u=XX@w
        return np.sum(np.logaddexp(0,u)-y*u)+penalty*np.dot(w[1:],w[1:])*.5
    def jac(w):
        q=expit(XX@w)
        return XX.T@(q-y)+np.r_[0.,penalty*w[1:]]
    fit=minimize(obj,np.r_[np.log(y.mean()/(1-y.mean())),np.zeros(3)],jac=jac,method="BFGS",
                 options=dict(gtol=1e-9,maxiter=300))
    if not np.isfinite(fit.x).all() or np.linalg.norm(jac(fit.x))>1e-5:
        raise RuntimeError("CASE_RESULT_INVALID: logistic quality-score optimization failed")
    return dict(mu=mu,sigma=sigma,blocked_loc=loc,blocked_scale=scale,
                df=3,binwidth=qbin,
                quality_coef=fit.x.tolist(),
                quality_input_mean=mean.tolist(),quality_input_scale=sd.tolist(),
                global_blocked=float(y.mean()),shrinkage=C["Q_shrinkage"],n_training=len(training),
                original_fit_status="FITTED_ONLY_OFFICE_POSITIONS",regularized_fit_gradient_norm=float(np.linalg.norm(jac(fit.x))))

def mixweight(df,model):
    x=(features(df)-np.asarray(model["quality_input_mean"]))/np.asarray(model["quality_input_scale"])
    w=expit(np.column_stack([np.ones(len(x)),x])@np.asarray(model["quality_coef"]))
    w=C["Q_shrinkage"]*model["global_blocked"]+(1-C["Q_shrinkage"])*w
    return np.clip(w,1e-6,1-1e-6)

def clean_cdf(e,m):
    e=np.asarray(e,float);sigma=m["sigma"];w=m["binwidth"];mu=m["mu"]
    a=(e-mu+w/2)/sigma;b=(e-mu-w/2)/sigma
    def primitive(v):return v*norm.cdf(v)+norm.pdf(v)
    return np.clip((sigma/w)*(primitive(a)-primitive(b)),0,1)

def clean_pdf(e,m):
    e=np.asarray(e,float);sd=m["sigma"];bw=m["binwidth"];mu=m["mu"]
    return np.maximum((norm.cdf((e-mu+bw/2)/sd)-norm.cdf((e-mu-bw/2)/sd))/bw,1e-300)

def ecdf(e,m,weight):
    return (1-weight)*clean_cdf(e,m)+weight*student.cdf(e,df=3,loc=m["blocked_loc"],scale=m["blocked_scale"])

def epdf(e,m,weight):
    return (1-weight)*clean_pdf(e,m)+weight*student.pdf(e,df=3,loc=m["blocked_loc"],scale=m["blocked_scale"])

def cv_quantile(prob,m,weight):
    return float(brentq(lambda v:ecdf(v,m,weight)-prob,-20,20,xtol=1e-11))

def score_group(df,m):
    x=df.signed_error_mean_m.to_numpy(float)
    ww=mixweight(df,m)
    pit=ecdf(x,m,ww)
    cuts05=np.array([cv_quantile(.05,m,w) for w in ww])
    cuts01=np.array([cv_quantile(.01,m,w) for w in ww])
    return dict(n=len(df),
       RF_signed_mean_m=float(np.mean(x)),RF_signed_rmse_m=float(np.sqrt(np.mean(x*x))),
       mean_predictive_tail_weight=float(ww.mean()),
       p_negative_error=float(np.mean(x<0)),
       one_sided_95_empirical_coverage=float(np.mean(x>=cuts05)),
       one_sided_99_empirical_coverage=float(np.mean(x>=cuts01)),
       PIT_KS=float(kstest(pit,"uniform").statistic),
       mean_negative_log_density=float(-np.mean(np.log(np.maximum(epdf(x,m,ww),1e-300)))),
       min_signed_error_m=float(x.min()),median_predicted_95_bound_m=float(np.median(cuts05)),
       count_95_violations=int(np.sum(x<cuts05)))

def stage_B2():
    audited("B2")
    df=pd.read_csv(PRE/"INDEPENDENT_SCENE_RF_POSITIONS.csv")
    if len(df)!=64 or set(df.scene)!={"office","A2","A2B"}:
        raise RuntimeError("HARD_EXECUTION_BLOCK: source table not the frozen 64 positions")
    office=df[df.scene=="office"]
    if (len(office)!=35 or office.los_clear.sum()!=25 or
        len(df[df.scene=="A2"])!=15 or len(df[df.scene=="A2B"])!=14):
        raise RuntimeError("HARD_EXECUTION_BLOCK: source scene or status mismatch")
    m=fit(office)
    rows=[]
    for group,subset in [('office_fit',office),('A2_holdout',df[df.scene=="A2"]),
         ('A2B_related_holdout',df[df.scene=="A2B"]),('corridor_combined_holdout',df[df.scene!="office"])]:
        rows.append(dict(group=group,**score_group(subset,m)))
    pd.DataFrame(rows).to_csv(OUT/"B2_TRANSFER.csv",index=False)
    # Controlled base model from original B1 for same exact observations;
    # compare without retuning either model on heldout labels.
    from scipy.stats import t
    clean=office[office.los_clear].signed_error_mean_m.to_numpy(float)
    bad=office[~office.los_clear].signed_error_mean_m.to_numpy(float)
    base=dict(mu=float(np.mean(clean)),sigma=float(np.std(clean,ddof=1)),
              badloc=float(np.median(bad)),badscale=float(max(.06,1.4826*np.median(np.abs(bad-np.median(bad))))),
              w=10/35)
    baseline=[]
    for group,g in [('A2_holdout',df[df.scene=="A2"]),('A2B_related_holdout',df[df.scene=="A2B"])]:
        err=g.signed_error_mean_m.to_numpy(float)
        oldpdf=(1-base["w"])*norm.pdf(err,base["mu"],base["sigma"])+base["w"]*t.pdf(err,df=3,loc=base["badloc"],scale=base["badscale"])
        baseline.append(dict(group=group,original_B1_mean_NLL=float(-np.mean(np.log(np.maximum(oldpdf,1e-300)))),
                   B2_mean_NLL=float(score_group(g,m)["mean_negative_log_density"])))
    pd.DataFrame(baseline).to_csv(OUT/"B2_VS_B1_EXTERNAL_NLL.csv",index=False)
    # Positional LOOCV within OFFICE with source groups present; diagnostic, not
    # statistically independent scene count.
    loocv=[]
    for j in range(len(office)):
        rest=office.drop(index=office.index[j])
        md=fit(rest)
        sample=office.iloc[[j]]
        e=float(sample.signed_error_mean_m.iloc[0])
        w=float(mixweight(sample,md)[0])
        loocv.append(dict(scene="office",idx=int(j),error=e,pit=float(ecdf(e,md,w)),
                          in_95=bool(e>=cv_quantile(.05,md,w)),
                          in_99=bool(e>=cv_quantile(.01,md,w))))
    pd.DataFrame(loocv).to_csv(OUT/"B2_OFFICE_LOOCV.csv",index=False)
    cl=next(x for x in rows if x["group"]=="corridor_combined_holdout")
    report=dict(stage="B2",execution="PASS",calculation="PASS_CONDITIONAL_NORMALIZED_DENSITY",
      hypothesis="RF_CIR_AND_QUANTIZATION_CONDITIONAL_SIGNED_MODEL_EXTERNAL_TRANSFER",
      hypothesis_result="SUPPORTED_DESCRIPTIVE_EXTERNAL_95_COVERAGE" if cl["one_sided_95_empirical_coverage"]>=.95 else "CONTRADICTED_EXTERNAL_95_TAIL",
      full_scientific_calibration="CLAIM_BLOCK_INSUFFICIENT_DISTINCT_SCENES_AND_UNCALIBRATED_DR_FAULT",
      source_handling="OFFICE_ONLY_FIT_A2_A2B_NO_LABEL_TUNING",
      quality_inputs=["observed_corrected_range","first_to_peak_gap","first_energy_fraction","first_to_peak_ratio"],
      labels_used_for_training=["office geometric blocked label","office signed error ground truth"],
      test_truth_used_in_prediction=False,
      clean_convolution_assumption="Gaussian residual plus independent uniform +/- half FFT tap-spacing; conservative physics-inspired assumption, NOT proven exact detector noise",
      fit=m,rows=rows,baseline=baseline,
      office_LOOCV_95_coverage=float(np.mean([x["in_95"] for x in loocv])),
      office_LOOCV_99_coverage=float(np.mean([x["in_99"] for x in loocv])),
      prior_model_provenance="unmodified DR fault pF 0.05, extra2m still synthetic; no independent dynamic calibration",
      scientific_PASS=False)
    save("B2_REPORT.json",report)
    print("B2_FINAL",json.dumps({k:report[k] for k in ("calculation","hypothesis_result","office_LOOCV_95_coverage","office_LOOCV_99_coverage")}),flush=True)

def pwin(d,z,sd,model,q):
    delta=d-z;pF=OLD["dr_fault_prior"]["p_fault"];sf=OLD["dr_fault_prior"]["fault_extra_sigma_m"]
    def dens(e):
        fp=float(epdf(e,model,q))
        return fp*((1-pF)*norm.pdf(e+delta,0,sd)+pF*norm.pdf(e+delta,0,math.hypot(sd,sf)))
    cut=-delta/2
    splits=sorted(set([-20.,20.,cut,z-d,model["mu"],model["blocked_loc"]]))
    splits=[s for s in splits if -20<=s<=20]
    def integ(low,high,power=0):
        if high<=low:return 0.
        knots=[low]+[v for v in splits if low<v<high]+[high]
        ans=0.
        for a,b in zip(knots[:-1],knots[1:]):
            val,_=quad(lambda e:e**power*dens(e),a,b,epsabs=1e-12,epsrel=1e-9,limit=160)
            ans+=val
        return ans
    norm_const=integ(-20,20)
    if norm_const<=1e-250:raise RuntimeError("CASE_RESULT_INVALID: pwin evidence zero")
    numerator=(integ(cut,20) if delta>0 else integ(-20,cut) if delta<0 else 0.)
    mean_e=integ(-20,20,1)/norm_const
    return dict(pwin=float(np.clip(numerator/norm_const,0,1)),
                unguarded_mean_range=float(z-mean_e),logevidence=float(np.log(norm_const)))

def independent_pwin(d,z,sd,m,q):
    delta=d-z
    if delta==0:return 0.
    fault=OLD["dr_fault_prior"];pf=fault["p_fault"];sF=fault["fault_extra_sigma_m"]
    def mass(v):
        return epdf(v,m,q)*((1-pf)*norm.pdf(v+delta,0,sd)+
                            pf*norm.pdf(v+delta,0,math.hypot(sd,sF)))
    cut=-delta/2
    grid=np.linspace(-15,15,12001)
    den=simpson(mass(grid),x=grid)
    ngrid=np.linspace(cut,15,12001) if delta>0 else np.linspace(-15,cut,12001)
    return float(simpson(mass(ngrid),x=ngrid)/den)

def action(d,z,sd,m,q):
    post=pwin(d,z,sd,m,q)
    delt=d-z
    nis=float(delt*delt/(sd*sd+m["sigma"]**2+m["binwidth"]**2/12))
    selected=bool(delt>0 and nis>OLD["rule"]["nis_threshold"] and
             post["pwin"]>=OLD["rule"]["p_win_threshold"])
    return dict(action=float(z-m["mu"] if selected else d),selected=selected,nis=nis,**post)

def stage_C2():
    audited("C2")
    B=json.loads((OUT/"B2_REPORT.json").read_text())
    m=B["fit"]
    # Use one real Office RF Q point chosen BEFORE evaluating external test
    office=pd.read_csv(PRE/"INDEPENDENT_SCENE_RF_POSITIONS.csv")
    q_train=mixweight(office[office.scene=="office"].iloc[[0]],m)[0]
    fixtures=[]
    for f in OLD["controls"]:
        d=float(f["dr_m"]);z=float(f["rf_m"]);r=float(f["truth_m"]);sd=float(f["sigma_dr_m"])
        v=action(d,z,sd,m,q_train)
        truth_error=abs(v["action"]-r)
        numerical_independent=independent_pwin(d,z,sd,m,q_train)
        if abs(v["pwin"]-numerical_independent)>OLD["math"]["absolute_tolerance"]*150:
            raise RuntimeError("CASE_RESULT_INVALID: C2 posterior event integral disagreement")
        fixtures.append(dict(id=f["id"],truth=r,DR=d,RF=z,
            DR_abs_error=abs(d-r),RF_abs_error=abs(z-r),
            unguarded_abs_error=abs(v["unguarded_mean_range"]-r),
            guarded_abs_error=truth_error,guarded_action=v["action"],
            selected=v["selected"],pwin=v["pwin"],independent_prob=numerical_independent,nis=v["nis"]))
    c2=next(x for x in fixtures if x["id"]=="C2_DR_drift")
    rescue=bool(c2["guarded_abs_error"]<c2["DR_abs_error"]-.5)
    guards=all(x["guarded_abs_error"]<=x["DR_abs_error"]+1e-9 for x in fixtures if x["id"]!="C2_DR_drift")
    result=dict(stage="C2",execution="PASS",numerical="PASS_INDEPENDENT_EVENT_INTEGRALS",
      hypothesis="SUPPORTED_GUARDED_ACTION_IN_PREDECLARED_FIXTURES" if rescue and guards else "CONTRADICTED_GUARD_ACTION",
      transfer_probabilities_calibrated=False,DR_fault_calibrated=False,
      C2_rescued=rescue,C1_C3_C4_guarded=guards,fixtures=fixtures,scientific_PASS=False,
      next="D mathematical identity / isolated numerical smoke only, NO adoption of uncalibrated source probabilities")
    save("C2_REPORT.json",result)
    print("C2_FINAL",json.dumps({k:result[k] for k in ("numerical","hypothesis","C2_rescued","C1_C3_C4_guarded")}),flush=True)

def stage_D0():
    audited("D0")
    # Mathematically exact sequential Bayes vs joint for signed non-Gaussian RF,
    # tested independently on a 1-D radial continuous state + latent fault modes.
    m=json.loads((OUT/"B2_REPORT.json").read_text())["fit"]
    Q=m["global_blocked"]
    r=np.linspace(2.2,12.2,24001)
    # Predeclared test prior mixtures; not the frozen full (x,y,psi) prior.
    mu_dr=6.414651253;z=3.672195826;sd=.245318414
    from scipy.special import logsumexp
    prior=(.95*norm.pdf(r,mu_dr,sd)+.05*norm.pdf(r,mu_dr,math.hypot(sd,2.)))
    prior=prior/simpson(prior,x=r)
    rf=epdf(z-r,m,Q)
    s_obs=.19
    # Simple nonlinear s(r,psi) likelihood is a diagnostic separable toy,
    # not original LUT, no inference about full pose from its results.
    angles=np.linspace(-math.pi,math.pi,181)
    angular_prior=np.exp(-.5*((angles+.4)/.8)**2)
    joint=np.empty((len(angles),len(r)))
    sequential=np.empty_like(joint)
    for i,psi in enumerate(angles):
        s_pred=np.sin(psi)*np.exp(-r/10.)
        Ls=norm.pdf(s_obs,s_pred,.08)
        pr=prior*angular_prior[i]
        # Direct single-step joint likelihood
        joint[i]=pr*rf*Ls
        # Independent sequential conditionally normalized Range, then S
        range_post=pr*rf
        range_evidence=simpson(range_post,x=r)
        if range_evidence<=0:raise RuntimeError("CASE_RESULT_INVALID: zero range evidence")
        sequential[i]=(range_post/range_evidence)*Ls*range_evidence
    jp=joint/(simpson(simpson(joint,x=r,axis=1),x=angles))
    sp=sequential/(simpson(simpson(sequential,x=r,axis=1),x=angles))
    max_diff=float(np.max(np.abs(jp-sp)))
    tv_heading=float(simpson(np.abs(simpson(jp-sp,x=r,axis=1)),x=angles)/2)
    status="PASS_ALGEBRAIC_NON_GAUSSIAN_RADIAL" if max_diff<1e-12 and tv_heading<1e-12 else "CASE_RESULT_INVALID"
    result=dict(stage="D0",execution="PASS",calculation=status,max_density_abs_difference=max_diff,
      heading_total_variation=tv_heading,
      hypothesis="Exact Bayes G2 sequential and G3 joint agree for identical normalized signed RF likelihood",
      limitation="Only 1D radial and 1 angular nonlinear toy, NOT actual x-y-heading/S LUT/multimodal reference. Previous tilted original G3 one-cell result separately verified.",
      actual_full_G2_G3="NOT_RUN",actual_pose_covariance="NOT_RUN",scientific_PASS=False)
    save("D0_REPORT.json",result)
    print("D0_FINAL",json.dumps({k:result[k] for k in ("calculation","max_density_abs_difference","heading_total_variation")}),flush=True)

if __name__=="__main__":
    stage=sys.argv[1]
    {"B2":stage_B2,"C2":stage_C2,"D0":stage_D0}[stage]()
