#!/usr/bin/env python3
"""Frozen G3 sample 978: Range-aware adaptive importance integration VALIDITY AUDIT ONLY.

This does not implement a new G2/G3 estimator, nor change any baseline data.
The conditional Gaussian p(XY|psi), frozen S LUT and corrected B_OLD Range are
the exact offline H3 model; truth does not enter any likelihood/proposal.

Importance proposal: p(r|z_r) truncated to physical slant range, and an
adaptive, full-support mixture q(alpha|psi) fitted from frozen S likelihood
and Gaussian XY prior on pilot radial nodes. Two independent scrambled Sobol
sequences are evaluated using exact importance weights. A separate
deterministic polar-azimuth/truncated radial integration is the reference.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from scipy.integrate import quad
from scipy.special import logsumexp
from scipy.stats import norm, qmc
from numpy.polynomial.legendre import leggauss

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import h3_cloud_stage1 as phase1

h=phase1.h
c=phase1.c
N_PHI=1440
PILOT_BINS=512
PILOT_RADIAL_QUANTILES=(0.04,0.15,0.32,0.5,0.68,0.85,0.96)
UNIFORM_FLOOR=0.10
SCRAMBLE_SEEDS=(1069,2099)
QMC_EXPONENTS=(12,14,16)
REF_LEVELS=((1024,12),(2048,20),(4096,28))
TV_THRESHOLD=0.001
EVIDENCE_REL_THRESHOLD=0.005
SYNTHETIC_REL_THRESHOLD=0.003
MAX_QMC_EXP=16


def build_context(case,lut,x,P,zs,zr):
    Cxy=P[:2,:2]-np.outer(P[:2,2],P[2,:2])/P[2,2]
    sign,logdet=np.linalg.slogdet(Cxy)
    if sign<=0 or np.linalg.eigvalsh(Cxy).min()<=0:
        raise RuntimeError("Non-PD conditional XY covariance")
    dz=abs(float(case["anchor"][2])-float(case["robot_z_m"]))
    sigma=math.sqrt(float(c.RR))
    zmin=(dz-zr)/sigma
    tail=float(norm.sf(zmin))
    if tail<=0 or not math.isfinite(tail):
        raise RuntimeError("Truncated radial importance proposal has zero support")
    return dict(
        case=case,lut=lut,x=x,P=P,zs=zs,zr=zr,dz=dz,sigma=sigma,tail=tail,
        cov=Cxy,inv=np.linalg.inv(Cxy),lognorm=-math.log(2*math.pi)-.5*logdet,
        cross=P[:2,2]/P[2,2],anchor=np.asarray(case["anchor"][:2],float),
        logC=math.log(sigma*math.sqrt(2*math.pi)*tail),
    )


def slant_quantile(ctx,u):
    # Exactly sample q_r(r) proportional to exp(-(r-z_r)^2/(2*R_r)), r>=dz.
    # Survival-function inversion stays stable near the physical lower bound.
    u=np.clip(np.asarray(u,float),1e-13,1-1e-13)
    z=norm.isf(ctx["tail"]*(1-u))
    return ctx["zr"]+ctx["sigma"]*z


def coords(ctx,rad,alpha):
    rho=np.sqrt(np.maximum(rad*rad-ctx["dz"]**2,0))
    return np.column_stack([
        ctx["anchor"][0]+rho*np.cos(alpha),
        ctx["anchor"][1]+rho*np.sin(alpha),
    ])


def log_gaussian_xy(ctx,xy,psi):
    center=ctx["x"][:2]+float(h.wrap(psi-ctx["x"][2]))*ctx["cross"]
    d=xy-center
    V=ctx["inv"]
    q=V[0,0]*d[:,0]**2+(V[0,1]+V[1,0])*d[:,0]*d[:,1]+V[1,1]*d[:,1]**2
    return ctx["lognorm"]-.5*q


def log_s_like(ctx,xy,psi):
    pts=np.empty((len(xy),3),float)
    pts[:,:2]=xy
    pts[:,2]=psi
    predicted=h.model(ctx["lut"],pts,ctx["case"])
    return -.5*(ctx["zs"]-predicted)**2/c.RS


def pilot_proposals(ctx,grid):
    dphi=2*math.pi/PILOT_BINS
    mids=-math.pi+(np.arange(PILOT_BINS)+.5)*dphi
    ur=np.asarray(PILOT_RADIAL_QUANTILES)
    rad=slant_quantile(ctx,ur)
    rstack=np.repeat(rad,PILOT_BINS)
    astack=np.tile(mids,len(rad))
    xy=coords(ctx,rstack,astack)
    prior_psi=h.wrapped_logprior(grid,ctx["x"][2],ctx["P"][2,2])
    masses=np.empty((len(grid),PILOT_BINS),float)
    pilot_lograd=np.repeat(np.log(rad),PILOT_BINS)
    for i,psi in enumerate(grid):
        # Pilot estimates E_qr[r * pXY * pS], not the final integral.
        candidate=(pilot_lograd+log_gaussian_xy(ctx,xy,psi)
                   +log_s_like(ctx,xy,psi)).reshape(len(rad),PILOT_BINS)
        logmass=logsumexp(candidate,axis=0)-math.log(len(rad))
        scaled=np.exp(logmass-logsumexp(logmass))
        masses[i]=(1-UNIFORM_FLOOR)*scaled+UNIFORM_FLOOR/PILOT_BINS
        if i%360==0:
            print("PILOT",i,"/1440",flush=True)
    if not np.allclose(masses.sum(axis=1),1,atol=1e-12):
        raise RuntimeError("Invalid adaptive angular mass normalization")
    if masses.min()<UNIFORM_FLOOR/PILOT_BINS-1e-14:
        raise RuntimeError("Importance proposal lost its full-support floor")
    return masses,prior_psi


def inverted_azimuth(masses,u):
    # Rosenblatt transform: sample a categorical azimuth cell then uniform
    # inside the cell; q_alpha is piecewise constant and exactly evaluated.
    cdf=np.cumsum(masses)
    cdf[-1]=1.
    indices=np.searchsorted(cdf,u,side="right")
    indices=np.minimum(indices,PILOT_BINS-1)
    low=np.where(indices==0,0.,cdf[np.maximum(indices-1,0)])
    frac=np.clip((u-low)/masses[indices],0.,1.)
    binwidth=2*math.pi/PILOT_BINS
    alpha=-math.pi+(indices+frac)*binwidth
    logq=np.log(masses[indices])-math.log(binwidth)
    return alpha,logq


def log_estimate(logweights,n):
    lw=logweights[:n]
    return float(logsumexp(lw)-math.log(n))


def relative_ess(logweights,n):
    v=logweights[:n]
    top=logsumexp(v)
    return float(math.exp(2*top-logsumexp(2*v))/n)


def importance_run(ctx,grid,masses,prior_psi,seed,maxexp,prefixes,out):
    U=qmc.Sobol(2,scramble=True,seed=seed).random_base2(maxexp)
    radii=slant_quantile(ctx,U[:,1])
    prefix_lengths=[1<<j for j in prefixes]
    loglike=np.empty((len(prefix_lengths),len(grid)))
    weighted_ess=np.empty((len(prefix_lengths),len(grid)))
    for i,psi in enumerate(grid):
        alpha,logq=inverted_azimuth(masses[i],U[:,0])
        xy=coords(ctx,radii,alpha)
        logw=(ctx["logC"]+np.log(radii)+log_gaussian_xy(ctx,xy,psi)
              +log_s_like(ctx,xy,psi)-logq)
        for j,n in enumerate(prefix_lengths):
            loglike[j,i]=log_estimate(logw,n)+prior_psi[i]
            weighted_ess[j,i]=relative_ess(logw,n)
        if i%360==0:
            print("QMC",seed,1<<maxexp,"angle",i,flush=True)
    result=[]
    for j,n in enumerate(prefix_lengths):
        post=phase1.probabilities(loglike[j])
        record=dict(
            algorithm="RANGE_AWARE_ADAPTIVE_IMPORTANCE_RQMC",
            seed=seed,n=n,
            log_evidence=float(logsumexp(loglike[j])+math.log(2*math.pi/len(grid))),
            ess_posterior_weighted_fraction=float(post@weighted_ess[j]),
            ess_posterior_core_min_fraction=float(
                np.min(weighted_ess[j,post>=post.max()*0.01])),
            map_rad=float(grid[np.argmax(post)]),
            logp=loglike[j],
            post=post,
        )
        result.append(record)
        np.savez_compressed(out/f"qmc_{seed}_n{n}.npz",
                            angles_rad=grid,prob=post,logp=loglike[j],
                            ess_fraction=weighted_ess[j])
    return result


def reference_run(ctx,grid,prior_psi,na,nrad,out):
    # A separate deterministic trapezoid azimuth × Gauss-Legendre radial
    # quadrature in the EXACT truncated range-likelihood measure.
    # No importance-pilot angular mass or Sobol samples are used.
    ga,wa=leggauss(nrad)
    ru=(ga+1)/2
    r=slant_quantile(ctx,ru)
    rw=wa/2
    phi=-math.pi+(np.arange(na)+0.5)*(2*math.pi/na)
    rr=np.repeat(r,na)
    aa=np.tile(phi,nrad)
    xy=coords(ctx,rr,aa)
    logmeasure=ctx["logC"]+np.repeat(np.log(rw),na)+math.log(2*math.pi/na)+np.log(rr)
    logp=np.empty(len(grid))
    for i,psi in enumerate(grid):
        log_integrand=logmeasure+log_gaussian_xy(ctx,xy,psi)+log_s_like(ctx,xy,psi)
        logp[i]=logsumexp(log_integrand)+prior_psi[i]
        if i%360==0:
            print("REFERENCE",na,nrad,"angle",i,flush=True)
    posterior=phase1.probabilities(logp)
    np.savez_compressed(out/f"reference_phi{na}_r{nrad}.npz",
                        angles_rad=grid,prob=posterior,logp=logp)
    return dict(algorithm="DETERMINISTIC_TRUNCATED_RADIAL_POLAR",
                nphi=na,nrad=nrad,
                log_evidence=float(logsumexp(logp)+math.log(2*math.pi/len(grid))),
                map_rad=float(grid[np.argmax(posterior)]),
                logp=logp,post=posterior)


def synthetic_identity_test():
    """Exact isotropic Gaussian×Range integral, tests q_r and q_alpha weights."""
    dz=2.2
    zr=4.5
    sig=math.sqrt(c.RR)
    stdxy=2.
    Z=float(norm.sf((dz-zr)/sig))
    C=sig*math.sqrt(2*math.pi)*Z
    exact=quad(
        lambda rad: rad/stdxy**2 *
           math.exp(-(rad**2-dz**2)/(2*stdxy**2)) *
           math.exp(-.5*((rad-zr)/sig)**2),
        dz,np.inf,epsabs=1e-13,epsrel=1e-11,
    )[0]
    if not exact>0:
        raise RuntimeError("Synthetic exact integral invalid")
    B=PILOT_BINS
    phi=-math.pi+(np.arange(B)+.5)*2*math.pi/B
    trial=2*np.cos(phi-.7)+.8*np.cos(4*phi)
    masses=(1-UNIFORM_FLOOR)*np.exp(trial-logsumexp(trial))+UNIFORM_FLOOR/B
    rows=[]
    for seed in SCRAMBLE_SEEDS:
        u=qmc.Sobol(2,scramble=True,seed=seed).random_base2(14)
        alpha,logq=inverted_azimuth(masses,u[:,0])
        rad=zr+sig*norm.isf(np.maximum(Z*(1-u[:,1]),1e-300))
        # Add a known multimodal angular factor with mean 1 on the full circle.
        angular=1.+.6*np.cos(4*alpha)
        w=C*rad/stdxy**2*np.exp(-(rad*rad-dz*dz)/(2*stdxy**2))
        w=w*angular/(2*math.pi*np.exp(logq))
        estimate=float(np.mean(w))
        relerr=abs(estimate-exact)/exact
        rows.append(dict(seed=seed,analytic=exact,rqmc=estimate,relative_error=relerr))
        if not relerr<=SYNTHETIC_REL_THRESHOLD:
            raise RuntimeError(f"Synthetic importance identity failed: {rows}")
    return rows


def compare_a_b(a,b):
    return dict(
        TV=phase1.total_variation(a["post"],b["post"]),
        rel_evidence=abs(math.expm1(a["log_evidence"]-b["log_evidence"])),
        MAP_delta_deg=float(abs(h.wrap(a["map_rad"]-b["map_rad"]))*h.RAD),
    )


def summary_rows(qmc_results,refs):
    rows=[]
    for e,pairs in qmc_results.items():
        for rec in pairs:
            rows.append({k:v for k,v in rec.items() if k not in ("post","logp")})
    for r in refs:
        rows.append({k:v for k,v in r.items() if k not in ("post","logp")})
    return rows


def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--out",type=Path,required=True)
    args=cli.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    report=dict(
        scope="VALIDITY_OF_RANGE_AWARE_ADAPTIVE_IMPORTANCE_AT_ONE_FROZEN_CELL_ONLY",
        status="RUNNING",scientific_PASS=False,recursive_fusion="NOT_RUN",
        stage3_G2_G3="NOT_RUN",stage4_performance="NOT_RUN",
        original_G3_TV=phase1.EXPECTED_TV,
        thresholds=dict(posterior_TV=TV_THRESHOLD,relative_evidence=EVIDENCE_REL_THRESHOLD,
                        synthetic_relative_error=SYNTHETIC_REL_THRESHOLD),
        preregistered=dict(
            qmc_scramble_seeds=SCRAMBLE_SEEDS,qmc_n=[1<<e for e in QMC_EXPONENTS],
            polar_reference=REF_LEVELS,angular_grid=N_PHI,pilot_bins=PILOT_BINS,
            angular_uniform_floor=UNIFORM_FLOOR,radial_support="[abs(dz), infinity)",
        ),
        confirmed=[],contradicted=[],unresolved=[],next_action="STOP_ONCE_VALIDITY_DECIDED",
    )
    measurements=[]
    exitcode=2
    t0=time.time()
    try:
        report["synthetic_identity"]=synthetic_identity_test()
        report["confirmed"].append("Analytic Gaussian × Range importance identity")
        snap,case,lut,x,P,zs,zr=phase1.frozen_snapshot()
        report["frozen_snapshot"]={k:v for k,v in snap.items() if k!="frozen_input_sha256"}
        report["input_sha256"]=snap["frozen_input_sha256"]
        ctx=build_context(case,lut,x,P,zs,zr)
        report["radial_proposal"]=dict(
            min_slant_m=ctx["dz"],mean_observed_range_m=ctx["zr"],
            sigma_m=ctx["sigma"],truncation_survival=ctx["tail"],
            conditional_position_eigenvalues=np.linalg.eigvalsh(ctx["cov"]).tolist(),
        )
        grid=np.linspace(-math.pi,math.pi,N_PHI,endpoint=False)
        masses,prior_psi=pilot_proposals(ctx,grid)
        report["pilot"]=dict(nbins=PILOT_BINS,floor=UNIFORM_FLOOR,
                             minimum_bin_mass=float(masses.min()),
                             maximum_bin_mass=float(masses.max()))
        refs=[]
        for level,(nphi,nrad) in enumerate(REF_LEVELS):
            start=time.time()
            ref=reference_run(ctx,grid,prior_psi,nphi,nrad,args.out)
            measurements.append({k:v for k,v in ref.items() if k not in ("post","logp")})
            ref["elapsed_seconds"]=time.time()-start
            refs.append(ref)
            if len(refs)>=2:
                comparison=compare_a_b(refs[-1],refs[-2])
                print("REFERENCE_COMPARISON",level,comparison,flush=True)
                if comparison["TV"]<=TV_THRESHOLD and comparison["rel_evidence"]<=EVIDENCE_REL_THRESHOLD:
                    break
        report["reference_levels"]=[
            dict(nphi=z["nphi"],nrad=z["nrad"],log_evidence=z["log_evidence"])
            for z in refs]
        report["reference_last_pair"]=compare_a_b(refs[-1],refs[-2])
        ref_converged=report["reference_last_pair"]["TV"]<=TV_THRESHOLD and (
            report["reference_last_pair"]["rel_evidence"]<=EVIDENCE_REL_THRESHOLD)
        report["reference_converged"]=bool(ref_converged)
        if ref_converged:
            report["confirmed"].append("Independent deterministic range-centred reference converged")
        else:
            report["contradicted"].append("Deterministic reference not converged at predefined cap")

        qmc_results={}
        # Pre-registered modest and maximum budgets; only escalate if needed.
        for maxexp in (14,16):
            for seed in SCRAMBLE_SEEDS:
                outputs=importance_run(
                    ctx,grid,masses,prior_psi,seed,maxexp,
                    QMC_EXPONENTS[:2] if maxexp==14 else (16,),
                    args.out)
                if seed not in qmc_results:
                    qmc_results[seed]={}
                for rec in outputs:
                    qmc_results[seed][rec["n"]]=rec
                    measurements.append({k:v for k,v in rec.items() if k not in ("post","logp")})
            length=1<<maxexp
            independent=compare_a_b(
                qmc_results[SCRAMBLE_SEEDS[0]][length],
                qmc_results[SCRAMBLE_SEEDS[1]][length])
            reference_pair=[
                compare_a_b(qmc_results[seed][length],refs[-1])
                for seed in SCRAMBLE_SEEDS
            ]
            ess=[qmc_results[seed][length]["ess_posterior_weighted_fraction"]
                 for seed in SCRAMBLE_SEEDS]
            valid=(ref_converged and
                   independent["TV"]<=TV_THRESHOLD and
                   independent["rel_evidence"]<=EVIDENCE_REL_THRESHOLD and
                   all(q["TV"]<=TV_THRESHOLD and
                       q["rel_evidence"]<=EVIDENCE_REL_THRESHOLD for q in reference_pair) and
                   min(ess)>=0.05)
            record=dict(n=length,independent_scrambles=independent,
                        deterministic_reference_comparisons=reference_pair,
                        posterior_weighted_ESS_fractions=ess,all_gates_passed=bool(valid))
            report.setdefault("qmc_evaluations",[]).append(record)
            print("QMC_COMPARISON",record,flush=True)
            if valid:
                break
        report["elapsed_seconds"]=time.time()-t0
        accepted=bool(report["qmc_evaluations"][-1]["all_gates_passed"])
        if accepted:
            report["status"]="VALIDATED_SINGLE_CELL_NUMERICAL_FEASIBILITY_ONLY"
            report["confirmed"].append("Two independent adaptive RQMC scrambles agree with deterministic reference")
            report["next_action"]="STOP. Do not execute subsequent G2/G3 performance or recursive stages."
            report["unresolved"].append(
                "Generalization to other times/channels, posterior covariance, and overall G2/G3 performance"
            )
            exitcode=0
        else:
            report["status"]="NOT_VALIDATED_AT_PREREGISTERED_BUDGET"
            report["contradicted"].append(
                "Adaptive importance approach did not meet all independent precision gates")
            report["next_action"]="STOP. Audit ESS / azimuth multimodality / reference tails before any new hypothesis."
            report["unresolved"].append(
                "Numerical viability at higher budgets, different proposals, or other data conditions"
            )
            exitcode=3
    except Exception as exc:
        report["status"]="FAIL_CLOSED_IMPLEMENTATION_OR_NUMERICAL_ERROR"
        report["error"]=str(exc)
        report["error_type"]=type(exc).__name__
        report["traceback"]=traceback.format_exc()
        report["unresolved"].append("Implementation or input parity error prevented validity conclusion.")
        exitcode=2
    finally:
        report["elapsed_seconds"]=time.time()-t0
        if measurements:
            columns=list(dict.fromkeys(k for row in measurements for k in row))
            with (args.out/"IMPORTANCE_AND_REFERENCE_METRICS.csv").open("w",newline="") as f:
                w=csv.DictWriter(f,fieldnames=columns)
                w.writeheader()
                w.writerows(measurements)
        (args.out/"VALIDITY_AUDIT.json").write_text(
            json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),
            encoding="utf-8")
        print("FINAL_VALIDITY_AUDIT",json.dumps(
            {k:report[k] for k in ("status","confirmed","contradicted","unresolved","next_action")},
            ensure_ascii=False),flush=True)
    return exitcode


if __name__=="__main__":
    sys.exit(main())
