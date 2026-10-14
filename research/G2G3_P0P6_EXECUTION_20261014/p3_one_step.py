#!/usr/bin/env python3
"""P3 physical one-step G2-Approx and G3-Exact R0 pose/covariance verification.

All measurement data are from frozen H3, DR prior propagated WITHOUT RF.
Truth appears only in score_snapshot() AFTER posterior computation.
No positional oracle/Gyro-level labels are used by the integrator.

G2-Approx: frozen Range EKF with original gate followed by conditional S-only
likelihood integrated over EKF Gaussian XY|psi.
G3-Exact (numerical): frozen prior and joint S+Range likelihood, with
likelihood-tilted Gaussian XY proposal and GH integration. Also exposes exact
sequential Bayes algebra using the SAME target weights.
"""
from __future__ import annotations
import argparse,csv,json,math,sys,time,traceback
from pathlib import Path
import numpy as np
from numpy.polynomial.hermite import hermgauss
from scipy.special import logsumexp
from scipy.stats import chi2

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
H3=REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics/h3_offline/results/H3_OFFLINE_20261014_01a1380d"
sys.path.insert(0,str(REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics"))
sys.path.insert(0,str(H3))
import h3_offline as h
import d6_d9_common as c
h.REPO=REPO

ANGLE_GRID=1440
GH_LEVELS=(25,41)
S_GH_LEVELS=(9,17)
RAD=180/math.pi
TV_LIMIT=.001
R0_R=np.diag([c.RS,c.RR])


def wrap(a):return (np.asarray(a)+np.pi)%(2*np.pi)-np.pi
def jsafe(a):
    if isinstance(a,np.generic):return a.item()
    if isinstance(a,np.ndarray):return a.tolist()
    raise TypeError(type(a).__name__)


def tilted(mean,cov,zr,case):
    """Existing H3 D method: iterated Gaussian proposal for Range ONLY.
    Proposal does not modify the joint measurement likelihood.
    """
    anchor=np.asarray(case["anchor"][:2],float)
    dz2=float(case["anchor"][2]-case["robot_z_m"])**2
    guess=mean.copy()
    for _ in range(15):
        dx=guess-anchor
        predicted=math.sqrt(float(dx@dx)+dz2)
        grad=dx/predicted
        v=cov@grad
        innovation=zr-predicted+float(grad@(guess-mean))
        nxt=mean+v*innovation/(float(grad@v)+c.RR)
        if not np.isfinite(nxt).all():raise ValueError("CASE_RESULT_INVALID: tilted proposal nonfinite")
        if np.linalg.norm(nxt-guess)<1e-9:
            guess=nxt;break
        guess=.5*guess+.5*nxt
    dx=guess-anchor
    r=math.sqrt(float(dx@dx)+dz2)
    H=dx/r;v=cov@H
    Q=cov-np.outer(v,v)/(float(H@v)+c.RR)
    if np.linalg.eigvalsh(Q).min()<=0:raise ValueError("CASE_RESULT_INVALID: tilted proposal non-PD")
    return guess,Q


def posterior_at_order(lut,x,P,zs,zr,case,kind,order,prior_source="DR"):
    """Stream each angular bin's quadrature nodes to bound RAM.

    Return full joint (x,y,psi) moments. Angular grid is equal-area.
    The original wrapped psi prior enters ONCE. Range likelihood enters ONCE.
    """
    if np.linalg.eigvalsh(P).min()<=0:raise ValueError("invalid Gaussian prior covariance")
    gh,gw=hermgauss(order)
    gx,gy=np.meshgrid(gh,gh,indexing="ij")
    standard=np.stack([gx.ravel(),gy.ravel()],axis=1)*math.sqrt(2)
    logw=np.log(np.outer(gw,gw).ravel()/math.pi)
    nr=len(logw)
    phis=np.linspace(-math.pi,math.pi,ANGLE_GRID,endpoint=False)
    heading_log=h.wrapped_logprior(phis,x[2],P[2,2])
    cond=P[:2,:2]-np.outer(P[:2,2],P[2,:2])/P[2,2]
    if np.linalg.eigvalsh(cond).min()<=0:raise ValueError("invalid conditional xy covariance")
    cross=P[:2,2]/P[2,2]
    det=np.linalg.slogdet(cond)
    lprior=-math.log(2*math.pi)-.5*det[1]
    invprior=np.linalg.inv(cond)
    Lp=np.linalg.cholesky(cond)
    log_marg=np.empty(ANGLE_GRID)
    cond_xy_mean=np.empty((ANGLE_GRID,2))
    cond_xy_E2=np.empty((ANGLE_GRID,2,2))
    anchors=np.asarray(case["anchor"][:2],float)
    dz2=float(case["anchor"][2]-case["robot_z_m"])**2
    for i,phi in enumerate(phis):
        m=x[:2]+float(wrap(phi-x[2]))*cross
        if kind=="G3_JOINT":
            q,Q=tilted(m,cond,zr,case)
            L=np.linalg.cholesky(Q)
            xy=q+standard@L.T
            detq=np.linalg.slogdet(Q)
            lq=-math.log(2*math.pi)-.5*detq[1]
            d=xy-m;eq=xy-q
            ip=np.einsum("ni,ij,nj->n",d,invprior,d,optimize=True)
            iq=np.einsum("ni,ij,nj->n",eq,np.linalg.inv(Q),eq,optimize=True)
            ratio=(lprior-.5*ip)-(lq-.5*iq)
        elif kind=="G2_EKF_S":
            xy=m+standard@Lp.T
            ratio=np.zeros(nr)
        else:raise ValueError("unknown method "+str(kind))
        pts=np.empty((nr,3))
        pts[:,:2]=xy;pts[:,2]=phi
        predS=h.model(lut,pts,case)
        loglikeS=-.5*(zs-predS)**2/c.RS
        if kind=="G3_JOINT":
            slant=np.sqrt(np.sum((xy-anchors)**2,axis=1)+dz2)
            loglikeR=-.5*(zr-slant)**2/c.RR
        else:loglikeR=0.
        terms=logw+ratio+loglikeS+loglikeR
        weight=np.exp(terms-logsumexp(terms))
        log_marg[i]=float(heading_log[i]+logsumexp(terms))
        cond_xy_mean[i]=weight@xy
        cond_xy_E2[i]=np.einsum("n,ni,nj->ij",weight,xy,xy)
    ppsi=np.exp(log_marg-logsumexp(log_marg))
    sx=float(ppsi@np.sin(phis));cx=float(ppsi@np.cos(phis))
    concentration=float(math.hypot(sx,cx))
    if concentration<1e-8:raise ValueError("CASE_RESULT_INVALID: joint yaw moment undefined")
    avgpsi=float(math.atan2(sx,cx))
    means_xy=ppsi@cond_xy_mean
    second=np.einsum("p,pij->ij",ppsi,cond_xy_E2)
    difpsi=wrap(phis-avgpsi)
    cross_xypsi=np.einsum("p,pi,p->i",ppsi,cond_xy_mean-means_xy,difpsi)
    pxy=second-np.outer(means_xy,means_xy)
    ppsi_var=float(ppsi@(difpsi*difpsi))
    cov=np.empty((3,3))
    cov[:2,:2]=pxy;cov[:2,2]=cross_xypsi;cov[2,:2]=cross_xypsi;cov[2,2]=ppsi_var
    cov=(cov+cov.T)*.5
    eig=np.linalg.eigvalsh(cov)
    if not np.isfinite(cov).all() or eig.min()<=0:
        raise ValueError(f"CASE_RESULT_INVALID: joint posterior covariance non-PD {eig}")
    idx=int(np.argmax(ppsi))
    idx_sorted=np.argsort(ppsi)[::-1]
    width=int(np.searchsorted(np.cumsum(ppsi[idx_sorted]),.95))+1
    return dict(
        mean=np.r_[means_xy,avgpsi],P=cov,
        map_heading_rad=float(phis[idx]),hpdi95_width_deg=width*(360/ANGLE_GRID),
        ppsi=ppsi,phigrid=phis,circular_resultant=concentration,
        covariance_min_eigenvalue=float(eig.min()),numeric_evidence=float(logsumexp(log_marg)+math.log(2*math.pi/ANGLE_GRID)),
        kind=kind,order=order,
        range_factor_applied=(kind=="G3_JOINT"),
        xpsi_cross_covariance=[float(cov[0,2]),float(cov[1,2])],
    )


def calc_pair(lut,x,P,zs,zr,case,method,levels):
    if method=="G2_EKF_S":
        xp,PP,gate=h.range_update(x,P,zr,case,0.,c.RR,True)
        zs_case=(xp,PP)
    else:
        xp,PP=x,P;gate="likelihood_included_once"
        zs_case=(x,P)
    records=[]
    t0=time.time()
    for gh_order in levels:
        po=posterior_at_order(lut,*zs_case,zs,zr,case,kind=method,order=gh_order)
        rec={**po, "order":gh_order}
        records.append(rec)
        print("P3_ORDER",method,gh_order,"gate",gate,"evidence",rec["numeric_evidence"],"sec",round(time.time()-t0,3),flush=True)
    pa,pb=records[-2:]
    tv=float(.5*np.abs(pa["ppsi"]-pb["ppsi"]).sum())
    map_delta=float(abs(wrap(pa["map_heading_rad"]-pb["map_heading_rad"]))*RAD)
    hpd_delta=float(abs(pa["hpdi95_width_deg"]-pb["hpdi95_width_deg"]))
    rel_ev=float(abs(math.expm1(pb["numeric_evidence"]-pa["numeric_evidence"])))
    ok=(tv<=TV_LIMIT and map_delta<=.1 and hpd_delta<=1. and rel_ev<=.005)
    output=dict(pb)
    for k in ("ppsi","phigrid"):output.pop(k)
    return dict(status="NUMERICAL_PASS" if ok else "CASE_RESULT_INVALID",gate=gate,
        posterior=output,num=dict(orders=levels,TV=tv,map_delta_deg=map_delta,
                                HPD_delta_deg=hpd_delta,evidence_relative_diff=rel_ev),
        raw_probs=pb["ppsi"],raw_angles=pb["phigrid"],ref_pose=x,ref_cov=P,
        seconds=time.time()-t0)


def score(po,truth,prior):
    mu=po["posterior"]["mean"]
    cov=po["posterior"]["P"]
    error=mu-truth.copy()
    error[2]=wrap(error[2])
    nees=float(error@np.linalg.solve(cov,error))
    expected=prior-truth.copy();expected[2]=wrap(expected[2])
    return dict(pos_err_m=float(np.linalg.norm(error[:2])),
        heading_error_deg=float(abs(error[2])*RAD),joint_pos_NEES=nees,
        pose95=bool(nees<=chi2.ppf(.95,3)),
        DR_pos_error_m=float(np.linalg.norm(expected[:2])),
        DR_heading_error_deg=float(abs(expected[2])*RAD),
        map_heading_error_deg=float(abs(wrap(po["posterior"]["map_heading_rad"]-truth[2]))*RAD))


def build_snap(p0,case,condition,level,seed,index):
    t,tr,poseids,motion,_=c.case_motion(p0,case,seed,level,condition)
    if index>=len(t):raise RuntimeError("CASE_RESULT_INVALID: invalid sample index")
    f=c.DiagnosticFilter(c.initial_state(tr[0],seed))
    for k in range(index+1):
        if k:f.predict(float(motion["ds_odom"][k]),float(motion["dtheta_gyro"][k]),float(motion["dt_s"][k]))
    return dict(t=t,truth=tr,poseids=poseids,prior=f.pose.copy(),cov=f.Ppose.copy())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--mode",choices=("P3","P4_SPARSE"),default="P3")
    args=parser.parse_args()
    if args.out.exists():raise FileExistsError(args.out)
    args.out.mkdir(parents=True)
    report=dict(stage=args.mode,status="RUNNING",scientific_PASS=False,scope="FROZEN_R0_FULL_3STATE_ONE_STEP",
                numeric_pass=0,numeric_invalid=0,case_failures=[],results=[],
                excluded_status="A numeric invalid cell excludes only its own estimator; no performance cherry-picking")
    try:
        p0=c.check_inputs(full_p0=False)
        lut=c.original_lut(p0)
        freq=c.spectrum(p0)
        cases={v["id"]:v for v in p0["cases"]}
        if args.mode=="P3":
            jobs=[
                ("R2_aA_m0","gyro_bias",2,0,978,"los","B_OLD"),
                ("R2_aA_m0","gyro_bias",0,0,978,"los","B_OLD"),
                ("R4_aA_m0","gyro_bias",0,0,550,"full","E1_FULL_LORO"),
            ]
        else:
            jobs=[]
            for ci in p0["cases"]:
                for cond,level in (("noise_pair",1),("gyro_bias",0),("gyro_bias",1),("gyro_bias",2)):
                    for channel,rmodel in (("los","B_OLD"),("full","B_OLD"),("full","E1_FULL_LORO")):
                        jobs.append((ci["id"],cond,level,0,-1,channel,rmodel))
        grouped={}
        cache={}
        corrected_cache={}
        folds=json.loads(c.P3_MODEL.read_text())["loro_fold_params"]
        for caseid,cond,lev,seed,idx,channel,rmodel in jobs:
            case=cases[caseid]
            key=(caseid,cond,lev,seed)
            snap=grouped.get(key)
            if snap is None:
                # For P4 sparse always sample at last requested route frame.
                k=(case["rf_count"] if idx<0 else idx)
                # Actual Tnone route may be shorter than archived H record;
                # use the separate route timeline's frozen contract length.
                length=next(x["samples"] for x in p0["routes"] if x["id"]==case["route"])
                k=(length-1 if idx<0 else idx)
                snap=build_snap(p0,case,cond,lev,seed,k)
                grouped[key]=snap
            k=(len(snap["t"])-1 if idx<0 else idx)
            if (caseid,channel) not in cache:
                cache[caseid,channel]=c.rf_case(p0,case,channel,freq,snap["poseids"])
            obs=cache[caseid,channel]
            if (caseid,channel) not in corrected_cache:
                corrected_cache[caseid,channel]=c.corrected_ranges(
                    obs,folds[case["route"]],allow_e1_on_los=False,channel=channel
                )
            correction=corrected_cache[caseid,channel]
            if rmodel not in correction:
                raise RuntimeError("HARD_EXECUTION_BLOCK: requested RF correction unavailable")
            zs,zr=float(obs["s"][k]),float(correction[rmodel][k])
            for method,gh in (("G2_EKF_S",S_GH_LEVELS),("G3_JOINT",GH_LEVELS)):
                base=dict(case=caseid,channel=channel,range_model=rmodel,condition=cond,level=lev,
                          seed=seed,sample=k,time_s=float(snap["t"][k]),method=method)
                try:
                    start=time.time()
                    result=calc_pair(lut,snap["prior"],snap["cov"],zs,zr,case,method,gh)
                    if result["status"]=="NUMERICAL_PASS":
                        report["numeric_pass"]+=1
                        scorecard=score(result,snap["truth"][k],snap["prior"])
                    else:
                        report["numeric_invalid"]+=1
                        scorecard={}
                    po=result["posterior"]
                    # Save actual state and covariance (not just the angle).
                    row=dict(base,**result["num"],**scorecard,
                       status=result["status"],gate=result["gate"],
                       mean_x=float(po["mean"][0]),mean_y=float(po["mean"][1]),
                       mean_psi_rad=float(po["mean"][2]),
                       map_heading_rad=float(po["map_heading_rad"]),
                       Pxx=float(po["P"][0,0]),Pxy=float(po["P"][0,1]),
                       Pyy=float(po["P"][1,1]),Pxpsi=float(po["P"][0,2]),
                       Pypsi=float(po["P"][1,2]),Ppsipsi=float(po["P"][2,2]),
                       posterior_min_eigenvalue=po["covariance_min_eigenvalue"],
                       circular_resultant=po["circular_resultant"],
                       sample_elapsed_s=time.time()-start)
                    report["results"].append(row)
                    print("P3_ROW",json.dumps({k:row[k] for k in ("case","method","status","TV","pos_err_m","heading_error_deg") if k in row}),flush=True)
                    if args.mode=="P3":
                        np.savez_compressed(args.out/f"{caseid}_{cond}_{lev}_{seed}_{k}_{channel}_{method}.npz",
                           heading_rad=result["raw_angles"],posterior_heading=result["raw_probs"],
                           pose_mean=po["mean"],pose_covariance=po["P"],DR_prior=snap["prior"],DR_covariance=snap["cov"])
                except Exception as exc:
                    report["numeric_invalid"]+=1
                    report["case_failures"].append(dict(base,error=str(exc),exception_type=type(exc).__name__,
                                                        trace=traceback.format_exc()[-1400:]))
                    print("P3_CELL_INVALID",base,str(exc),flush=True)
        report["status"]="EXECUTED_WITH_SCOPED_RESULTS"
        report["total_attempts"]=len(report["results"])+len(report["case_failures"])
        valid=[r for r in report["results"] if r["status"]=="NUMERICAL_PASS"]
        report["n_valid"]=len(valid)
        report["n_invalid"]=report["total_attempts"]-len(valid)
        if not valid:report["status"]="CASE_RESULT_INVALID_ALL"
    except Exception as exc:
        report["status"]="HARD_EXECUTION_BLOCK";report["error"]=str(exc);report["traceback"]=traceback.format_exc()[-5000:]
    finally:
        (args.out/"P3_P4_REPORT.json").write_text(json.dumps(report,indent=2,allow_nan=False,default=jsafe))
        if report["results"]:
            fields=list(dict.fromkeys(k for r in report["results"] for k in r))
            with (args.out/"P3_P4_PAIRED.csv").open("w",newline="") as f:
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(report["results"])
        print("P3_FINAL",json.dumps({k:report[k] for k in ("stage","status","numeric_pass","numeric_invalid","n_valid","n_invalid") if k in report}),flush=True)
    return 0 if report["status"]=="EXECUTED_WITH_SCOPED_RESULTS" else 2


if __name__=="__main__":
    raise SystemExit(main())
