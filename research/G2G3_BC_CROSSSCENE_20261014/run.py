#!/usr/bin/env python3
"""B external office/anchor signed RF calibration + C four controls.

Only source-locked reference data; no online use of ground truth or injected
condition labels. 19 yaw observations at one physical tag are never called
19 independent RF scenes. Frozen B_OLD offset is used everywhere.
Office report's within-office fitted offset is NOT used in predictions.
"""
from __future__ import annotations
import argparse, csv, json, math, hashlib, subprocess, sys, traceback
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from scipy.stats import norm, t as student, spearmanr
from scipy.integrate import quad, simpson
from scipy.optimize import brentq

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OFF=REPO/"externalOffice"
OUT=REPO/"outputs"/"BC_CROSSSCENE"
C=json.loads((ROOT/"CONTRACT.json").read_text())
C0=299792458.0
N=257
DF=1950000.
DELAY_TO_M=C0/(4*N*DF)
WIN=np.hanning(N)
CORR=-float(C["prior_BOLD_offset_m"])

def safe(obj):
    if isinstance(obj,np.generic): return obj.item()
    if isinstance(obj,np.ndarray):return obj.tolist()
    raise TypeError(type(obj).__name__)

def save(name,value):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name
    if p.exists():raise RuntimeError("HARD_EXECUTION_BLOCK: refusing result overwrite "+name)
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False,default=safe))

def audit_runtime(stage):
    p=OUT/f"PRE_RUN_{stage}.json"
    if not p.exists():raise RuntimeError("HARD_EXECUTION_BLOCK: no pre-run receipt")
    rec=json.loads(p.read_text())
    if not rec.get("code_match") or rec.get("run_decision") not in ("GO","GO_WITH_CLAIM_LIMITATION"):
        raise RuntimeError("HARD_EXECUTION_BLOCK: source not audited")
    if stage in ("B","C") and not (OUT/"H_EXTRACTION.json").exists():
        raise RuntimeError("HARD_EXECUTION_BLOCK: no external scene result")

def detector(H,tx0=False):
    h=np.asarray(H)
    if h.shape!=(19,N,2,2) or not np.iscomplexobj(h) or not np.isfinite(h).all():
        raise RuntimeError("CASE_RESULT_INVALID: office H shape/finite contract violated")
    cir=np.fft.ifft(h*WIN[None,:,None,None],n=4*N,axis=1)*N
    amp=np.abs(cir)
    peaks=amp.max(axis=1)
    if tx0:
        rx=peaks[:,:,0].argmax(axis=1)
        tx=np.zeros(19,dtype=int)
    else:
        k=peaks.reshape(19,4).argmax(axis=1)
        rx=k//2;tx=k%2
    a=amp[np.arange(19),:,rx,tx]
    pk=peaks[np.arange(19),rx,tx]
    if (pk<=0).any():raise RuntimeError("CASE_RESULT_INVALID: invalid CIR peak")
    fp=(a>=.3*pk[:,None]).argmax(axis=1)
    zraw=fp*DELAY_TO_M
    peakidx=a.argmax(axis=1)
    first_to_peak=(peakidx-fp)*DELAY_TO_M
    fp_ratio=a[np.arange(19),fp]/pk
    power=np.sum(a*a,axis=1)
    fp_energy=(a[np.arange(19),fp]**2)/np.maximum(power,1e-300)
    return dict(range_raw_m=zraw,peak_gap_m=first_to_peak,
                first_over_peak=fp_ratio,first_energy_over_total=fp_energy,
                rx_choice=rx,tx_choice=tx,first_bin=fp)

def h_path_office(p):
    tag=f"office_x{p['x']}_y{p['y']}"
    return OFF/"results"/"OFFICE_SNOWBALL_20261008_819fa93"/"full35_stride1"/tag/(tag+"_H.npy")

def extract():
    audit_runtime("EXTRACT")
    ext_hash=subprocess.check_output(["git","rev-parse","HEAD"],cwd=OFF,text=True).strip()
    if ext_hash!=C["source_commit"]:
        raise RuntimeError("HARD_EXECUTION_BLOCK: external scene commit mismatch")
    raw=(OFF/"results/OFFICE_RANGING_20261008/OFFICE_RANGING.json")
    office=json.loads(raw.read_text())
    positions=office["positions"]
    assert len(positions)==C["office_positions_expected"]
    checks=[];rows=[]
    for p in positions:
        H=np.load(h_path_office(p),allow_pickle=False)
        legacy=detector(H,False)
        tx0=detector(H,True)
        calc=float(np.mean(legacy["range_raw_m"]-float(p["range_m"])))
        archived=float(p["mean"])
        parity=abs(calc-archived)
        checks.append(dict(x=float(p["x"]),y=float(p["y"]),parity_abs_m=parity,
                           same_selected_tx_fraction=float(np.mean(legacy["tx_choice"]==0))))
        if parity>C["math"]["office_parity_mean_tol_m"]:
            raise RuntimeError(f"HARD_EXECUTION_BLOCK: office receiver parity at {p['x'],p['y']} {parity}")
        rows.append(aggregate("office",p["los_clear"],p["x"],p["y"],p["range_m"],tx0))
    assert sum(p["los_clear"] for p in positions)==25
    for group,source_path in [
        ("A2","results/CORRIDOR_ANCHOR2_20261007/SHIFT_FIT_ANCHOR2.json"),
        ("A2B","results/CORRIDOR_ANCHOR2B_20261007/SHIFT_FIT_ANCHOR2B.json")
    ]:
        entries=json.loads((OFF/source_path).read_text())["positions"]
        if len(entries)!=C["alternate_anchor_positions_expected"][group]:
            raise RuntimeError("HARD_EXECUTION_BLOCK: anchor dataset missing positions")
        for p in entries:
            h=OFF/p["file"].replace("_sweep.npz","_H.npy")
            det=detector(np.load(h,allow_pickle=False),True)
            # In this corridor geometry, direct LoS is present; do NOT treat its
            # repeated yaw samples as independent calibrating observations.
            rows.append(aggregate(group,True,p["x"],p["y"],p["range_m"],det))
    import pandas as pd
    dataframe=pd.DataFrame(rows)
    dataframe.to_csv(OUT/"INDEPENDENT_SCENE_RF_POSITIONS.csv",index=False)
    report=dict(execution="PASS",receiver_parity="PASS",office_positions=35,
      office_los=25,office_blocked=10,
      a2_positions=15,a2b_positions=14,
      exact_office_source_commit=ext_hash,
      maximum_legacy_det_mean_parity_m=max(q["parity_abs_m"] for q in checks),
      mean_matching_TX0_choice=float(np.mean([q["same_selected_tx_fraction"] for q in checks])),
      original_office_fitted_offset_m=office["los_clear_median_offset_m"],
      applied_FIXED_B_OLD_OFFSET_m=C["prior_BOLD_offset_m"],
      note="Office report self-fitted offset has NOT been used. A2 and A2B share corridor geometry; not 29 independent RF scenes.",
      source_json_sha256=hashlib.sha256(raw.read_bytes()).hexdigest(),
      scientific_PASS=False)
    save("H_EXTRACTION.json",report)
    print("BC_EXTRACTED",json.dumps({k:report[k] for k in ("office_positions","a2_positions","a2b_positions","maximum_legacy_det_mean_parity_m")}),flush=True)

def aggregate(group,los,x,y,truth,det):
    e=det["range_raw_m"]+CORR-float(truth)
    return dict(scene=group,los_clear=bool(los),x=float(x),y=float(y),
        true_range_m=float(truth),
        raw_error_mean_m=float(np.mean(det["range_raw_m"]-truth)),
        signed_error_mean_m=float(np.mean(e)),signed_error_median_m=float(np.median(e)),
        signed_error_min_m=float(np.min(e)),signed_error_max_m=float(np.max(e)),
        signed_error_rms_m=float(np.sqrt(np.mean(e*e))),
        yaw_sample_count=int(len(e)),
        median_fp_peak_ratio=float(np.median(det["first_over_peak"])),
        median_peak_gap_m=float(np.median(det["peak_gap_m"])),
        median_FP_energy_fraction=float(np.median(det["first_energy_over_total"])),
        peak_gap95_m=float(np.quantile(det["peak_gap_m"],.95)))

def fit_density(office):
    los=office[office.los_clear].signed_error_mean_m.to_numpy(float)
    blocked=office[~office.los_clear].signed_error_mean_m.to_numpy(float)
    if len(los)!=25 or len(blocked)!=10:raise RuntimeError("HARD_EXECUTION_BLOCK: office group mismatch")
    center0=float(np.mean(los));sd0=max(.015,float(np.std(los,ddof=1)))
    med=float(np.median(blocked))
    mad=float(np.median(np.abs(blocked-med)))
    # Predeclared Student-t df=3, with scale not fitted against external validation.
    outscale=max(.06,1.4826*mad)
    return dict(w_clean=25/35,mu_clean=center0,sd_clean=sd0,
                w_blocked=10/35,loc_blocked=med,scale_blocked=outscale,
                degrees_freedom=3)

def pdf(v,p):
    return p["w_clean"]*norm.pdf(v,p["mu_clean"],p["sd_clean"])+p["w_blocked"]*student.pdf(v,df=3,loc=p["loc_blocked"],scale=p["scale_blocked"])

def cdf(v,p):
    return p["w_clean"]*norm.cdf(v,p["mu_clean"],p["sd_clean"])+p["w_blocked"]*student.cdf(v,df=3,loc=p["loc_blocked"],scale=p["scale_blocked"])

def invcdf(v,p):
    return float(brentq(lambda x:cdf(x,p)-v,-20.,20.,xtol=1e-10))

def summary_scores(scene,params):
    y=scene.signed_error_mean_m.to_numpy(float)
    pit=np.asarray(cdf(y,params))
    q01=invcdf(.01,params);q05=invcdf(.05,params)
    lower=-q05
    from scipy.stats import kstest
    return dict(n_unique_positions=len(y),mean_m=float(y.mean()),rmse_m=float(np.sqrt(np.mean(y*y))),
       under_truth_fraction=float(np.mean(y<0)),
       median_fp_peak_ratio=float(scene.median_fp_peak_ratio.median()),
       signed_q05_m=float(np.quantile(y,.05)),signed_q95_m=float(np.quantile(y,.95)),
       coverage_95_upper=float(np.mean(y>=q05)),
       coverage_99_upper=float(np.mean(y>=q01)),
       gaussian_likelihood_95_interval_coverage=float(np.mean((pit>=.025)&(pit<=.975))),
       PIT_uniform_KS=float(kstest(pit,"uniform").statistic),
       mean_neglog_likelihood=float(-np.mean(np.log(np.maximum(pdf(y,params),1e-300)))),
       predicted_95_upper_margin_m=lower)

def calibrate():
    audit_runtime("B")
    import pandas as pd
    df=pd.read_csv(OUT/"INDEPENDENT_SCENE_RF_POSITIONS.csv")
    office=df[df.scene=="office"];other=df[df.scene!="office"]
    params=fit_density(office)
    diag=[]
    for name,g in [("office_fit_all",office),("office_clear_fit",office[office.los_clear]),
                  ("office_blocked_fit",office[~office.los_clear]),
                  ("anchor_A2_external",other[other.scene=="A2"]),
                  ("anchor_A2B_external",other[other.scene=="A2B"]),
                  ("both_anchor_configs_correlated",other)]:
        diag.append(dict(group=name,**summary_scores(g,params)))
    pd.DataFrame(diag).to_csv(OUT/"B_INDEPENDENT_SCENE_TRANSFER.csv",index=False)
    # No source quality model parameters fit from observed truth/labels.
    features=[]
    for name,g in df.groupby("scene",sort=True):
        if len(g)>4:
            for attr in ("median_fp_peak_ratio","median_peak_gap_m","median_FP_energy_fraction"):
                rho,p=spearmanr(g[attr],np.abs(g.signed_error_mean_m))
                features.append(dict(scene=name,feature=attr,spearman_abs_error=float(rho) if np.isfinite(rho) else None,
                                     p_nominal=float(p) if np.isfinite(p) else None,n=len(g)))
    pd.DataFrame(features).to_csv(OUT/"B_Q_DESCRIPTIVE_SPEARMAN.csv",index=False)
    report=dict(stage="B",status="EXECUTED_WITH_CLAIM_LIMITATION",
      numerical="PASS_INPUT_AND_NORMALIZED_DENSITY",
      calibrated_model=params,
      two_source_domains=dict(train="office 35 positions (including 25 clear/10 blocked)",
                              holdout="corridor alternate anchor A2 15 + A2B 14 (same corridor family)"),
      external_transfer=diag,
      expected_full_BOLD_current_world_comparable=False,
      calibration_independent_scene="Office vs corridor scene is distinct geometry; yes external scene transfer test",
      calibrated_probability_guarantee="NOT_ESTABLISHED: only one office training scene; 15+14 geometrically correlated positions; no DR motion in independent scene",
      E1_signed_likelihood="NOT_ELIGIBLE: office antennas/observer features differ from original E1 training schema",
      DR_fault_prior="UNVALIDATED: no independent gyro/odom trajectories in office or alternate-anchor static sweeps",
      CIR_quality="extracted descriptive features; no independent validated predictive RF quality calibration",
      scientific_PASS=False)
    save("B_REPORT.json",report)
    print("B_TRANSFER_COMPLETE",json.dumps({x["group"]:{k:x[k] for k in ("n_unique_positions","rmse_m","coverage_95_upper","coverage_99_upper")} for x in diag}),flush=True)

def pwin_quad(d,z,sd_dr,p):
    delta=d-z
    if sd_dr<=0:raise RuntimeError("HARD_EXECUTION_BLOCK: invalid DR std")
    probF=float(C["dr_fault_prior"]["p_fault"])
    sdF=float(C["dr_fault_prior"]["fault_extra_sigma_m"])
    def joint(er):
        return float(pdf(er,p))*((1-probF)*norm.pdf(er+delta,0,sd_dr) +
                                probF*norm.pdf(er+delta,0,math.hypot(sd_dr,sdF)))
    span=[p["mu_clean"],p["loc_blocked"],-delta]
    pts=sorted(set([-24.,24.]+
         [float(x) for x in span]+
         [float(x+offset) for x in span for offset in (-.4,-.1,.1,.4)]))
    pts=[x for x in pts if -24<=x<=24]
    def integral(start,end,power=0):
        if end<=start:return 0.
        spl=[start]+[x for x in pts if start<x<end]+[end]
        tot=0.
        for lo,hi in zip(spl[:-1],spl[1:]):
            integ,_=quad(lambda x:x**power*joint(x),lo,hi,epsabs=1e-11,epsrel=1e-9,limit=100)
            tot+=integ
        return tot
    Z=integral(-24,24)
    if Z<=1e-240:raise RuntimeError("CASE_RESULT_INVALID: zero evidence")
    threshold=-delta/2
    wins=integral(threshold,24) if delta>0 else (integral(-24,threshold) if delta<0 else 0)
    postmean_e=integral(-24,24,1)/Z
    return dict(pwin=float(np.clip(wins/Z,0,1)),posterior_mean_r=float(z-postmean_e),
                logevidence=float(math.log(Z)))

def independent_grid(d,z,sd_dr,p):
    de=d-z
    e=np.linspace(-12,12,24001)
    if de==0:return 0.
    def direct_density(x):
        fr=(p["w_clean"]*norm.pdf(x,p["mu_clean"],p["sd_clean"])+
            p["w_blocked"]*student.pdf(x,df=3,loc=p["loc_blocked"],scale=p["scale_blocked"]))
        fd=((1-C["dr_fault_prior"]["p_fault"])*norm.pdf(x+de,0,sd_dr)+
            C["dr_fault_prior"]["p_fault"]*norm.pdf(x+de,0,math.hypot(sd_dr,C["dr_fault_prior"]["fault_extra_sigma_m"])))
        return fr*fd
    den=float(simpson(direct_density(e),x=e))
    if den<=1e-230:raise RuntimeError("CASE_RESULT_INVALID: independent grid evidence underflow")
    cutoff=-de/2
    if de>0:
        numerator_grid=np.linspace(cutoff,12,24001)
    else:
        numerator_grid=np.linspace(-12,cutoff,24001)
    prob=float(simpson(direct_density(numerator_grid),x=numerator_grid)/den)
    return prob

def action(dr,z,pwin,sd_dr,p):
    delta=dr-z
    Rrf=p["sd_clean"]**2
    nis=delta*delta/(sd_dr*sd_dr+Rrf)
    selected=bool(delta>0 and nis>C["rule"]["nis_threshold"] and pwin>=C["rule"]["p_win_threshold"])
    return (float(z-p["mu_clean"]) if selected else float(dr),selected,float(nis))

def test_C():
    audit_runtime("C")
    b=json.loads((OUT/"B_REPORT.json").read_text())
    if b["numerical"]!="PASS_INPUT_AND_NORMALIZED_DENSITY":raise RuntimeError("HARD_EXECUTION_BLOCK: B input/calibration invalid")
    p=b["calibrated_model"]
    rr=[]
    for f in C["controls"]:
        d=float(f["dr_m"]);z=float(f["rf_m"]);r=float(f["truth_m"]);sd=float(f["sigma_dr_m"])
        out=pwin_quad(d,z,sd,p)
        indep=independent_grid(d,z,sd,p)
        if abs(out["pwin"]-indep)>C["math"]["absolute_tolerance"]*150:
            raise RuntimeError("CASE_RESULT_INVALID: independent probability integrals disagree "+f["id"]+" "+str([out["pwin"],indep]))
        corrected,selected,nis=action(d,z,out["pwin"],sd,p)
        rr.append(dict(fixture=f["id"],truth_m=r,dr_m=d,rf_m=z,
            dr_error_m=abs(d-r),rf_error_m=abs(z-r),
            unguarded_posterior_mean_error_m=abs(out["posterior_mean_r"]-r),
            guarded_error_m=abs(corrected-r),
            guarded_range_m=corrected,rf_selected=selected,
            model_RF_win_probability=out["pwin"],independent_RF_win_probability=indep,
            NIS_trial=nis))
    # Model and threshold never updated in response to fixture truths.
    c1c3c4=all(row["guarded_error_m"]<=row["dr_error_m"]+1e-9 for row in rr if row["fixture"]!="C2_DR_drift")
    c2=next(r for r in rr if r["fixture"]=="C2_DR_drift")
    recovered=bool(c2["dr_error_m"]-c2["guarded_error_m"]>0.5)
    if any(abs(r["model_RF_win_probability"]-r["independent_RF_win_probability"])>1.5e-5 for r in rr):
        raise RuntimeError("CASE_RESULT_INVALID: C quadrature precision failed")
    # Heldout external RF noise and a declared synthetic DR offset: diagnostic
    # noise-observation replay, not independent odometry or recursive G2/G3.
    import pandas as pd
    positions=pd.read_csv(OUT/"INDEPENDENT_SCENE_RF_POSITIONS.csv")
    external=positions[positions.scene.isin(["A2","A2B"])].copy()
    stress=[]
    for label,offset,sd in (("DR_near_truth",.03,.10),("DR_positive_drift",2.8,.245318414)):
        for _,row in external.iterrows():
            rt=float(row.true_range_m)
            z=rt+float(row.signed_error_mean_m)
            d=rt+offset
            calc=pwin_quad(d,z,sd,p)
            cand,sel,nis=action(d,z,calc["pwin"],sd,p)
            stress.append(dict(scene=row.scene,x=row.x,y=row.y,
                scenario=label,true_range_m=rt,
                RF_error_m=z-rt,DR_error_m=offset,
                RF_selected=sel,pwin=calc["pwin"],
                baseline_DR_abs_error_m=abs(d-rt),
                post_action_abs_error_m=abs(cand-rt),
                improved=abs(cand-rt)<abs(d-rt)))
    st=pd.DataFrame(stress)
    st.to_csv(OUT/"C_EXTERNAL_STATIC_RF_SYNTHETIC_DR.csv",index=False)
    report=dict(stage="C",run_scope="PREDECLARED_4_FIXTURES_PLUS_ALTERNATE_ANCHOR_STATIC_RF_WITH_SYNTHETIC_DR",
                numerical="PASS_INDEPENDENT_1D_QUAD_AND_GRID",
                status="PASS_CONTROL_GUARDS" if recovered and c1c3c4 else "HYPOTHESIS_CONTRADICTED",
                expected_vs_actual=dict(C2_expected="Recover with >0.5m radial gain",C2_actual=bool(recovered),
                      C1_C3_C4_expected="Guarded action never harms accurate DR",
                      C1_C3_C4_actual=bool(c1c3c4)),
                trials=rr,
                external_anchor_summary=[
                    dict(scene=str(scene),scenario=str(scenario),n=len(g),
                         RF_selection_count=int(g.RF_selected.sum()),
                         harmful_selection_count=int(((g.RF_selected)&
                          (g.post_action_abs_error_m>g.baseline_DR_abs_error_m+1e-9)).sum()),
                         mean_DR_mae_m=float(g.baseline_DR_abs_error_m.mean()),
                         mean_action_mae_m=float(g.post_action_abs_error_m.mean()))
                     for (scene,scenario),g in st.groupby(["scene","scenario"])],
                limitations=["Independent static scenes have no measured DR gyro/odometry; synthetic DR stress only",
                             "Uncalibrated p_fault=0.05/width2m, and learned RF params from 35 office positions",
                             "C valid doesn't imply B independent posterior calibration or G2/G3 pose safety"],
                scientific_PASS=False)
    save("C_REPORT.json",report)
    print("C_FINAL",json.dumps({k:report[k] for k in ("status","expected_vs_actual","external_anchor_summary")}),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("stage",choices=["extract","B","C"])
    args=ap.parse_args()
    try:
        if args.stage=="extract":extract()
        elif args.stage=="B":calibrate()
        else:test_C()
    except Exception as err:
        print("BC_ERROR",type(err).__name__,str(err),flush=True)
        raise
