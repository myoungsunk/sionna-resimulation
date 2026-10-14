"""G3 numerical feasibility at the 195.6s frozen failure case.

Try a *proposed* likelihood-tilted Gaussian quadrature. Report unknown or
invalid if two independent numerical estimators do not agree. No default
bypass or retuning of original R0 likelihood, data, or TV tolerance.
"""
from __future__ import annotations
import hashlib
import json
import math
import sys
import time
import traceback
from pathlib import Path

import numpy as np
from numpy.polynomial.hermite import hermgauss
from scipy.special import logsumexp, ndtri
from scipy.stats import qmc

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/"outputs/g2g3_bf"
C=json.loads((ROOT/"CONTRACT.json").read_text())
sys.path.insert(0,str(REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics"))
import h3_cloud_stage1 as prev


def independent_importance_log_density(pts,mean,invprior,logprior,qmean,invq,logq):
    diff=pts-mean
    pre=-.5*np.einsum("ni,ij,nj->n",diff,invprior,diff,optimize=True)+logprior
    df=pts-qmean
    prop=-.5*np.einsum("ni,ij,nj->n",df,invq,df,optimize=True)+logq
    return pre-prop


def tv(a,b):
    return float(np.abs(a-b).sum()/2.)


def normalize(logp):
    if not np.isfinite(logp).all():raise RuntimeError("Nonfinite log density")
    return np.exp(logp-logsumexp(logp))


def tilted_q(mean,cov,zr,case,RR):
    """Damped iterated linear least-squares for ONLY the Range likelihood.

    It is a proposal, not a new target probability model. No S or truth
    used to tune proposal; exact importance ratio corrects approximation.
    """
    anchor=np.asarray(case["anchor"][:2],float)
    dz2=float(case["robot_z_m"]-case["anchor"][2])**2
    guess=mean.copy()
    for _ in range(15):
        dr=guess-anchor
        h=math.sqrt(float(dr@dr)+dz2)
        H=dr/h
        pH=cov@H
        innovation=zr-h+float(H@(guess-mean))
        nxt=mean + pH/(float(H@pH)+RR)*innovation
        if not np.isfinite(nxt).all():
            raise RuntimeError("Proposal non-finite")
        if np.linalg.norm(nxt-guess)<1e-9:
            guess=nxt
            break
        # Range model smooth at nonzero dz, but guard fixed-point oscillation.
        guess=.5*guess+.5*nxt
    dr=guess-anchor
    r=math.sqrt(float(dr@dr)+dz2)
    H=dr/r
    v=cov@H
    qcov=cov-np.outer(v,v)/(float(H@v)+RR)
    if np.linalg.eigvalsh(qcov).min()<=0:
        raise RuntimeError("Proposed Gaussian covariance not PD")
    return guess,qcov


def one_integral(kind,grid,order,case,lut,x,P,zs,zr,seed=None):
    h=prev.h
    Rr=float(prev.c.RR)
    Rs=float(prev.c.RS)
    varpsi=P[2,2]
    cross=P[:2,2]/varpsi
    cov=P[:2,:2]-np.outer(P[:2,2],P[2,:2])/varpsi
    invprior=np.linalg.inv(cov)
    slog=np.linalg.slogdet(cov)
    if slog[0]<=0:raise RuntimeError("Conditional prior covariance invalid")
    logprior=-math.log(2*math.pi)-.5*slog[1]
    anchor=np.asarray(case["anchor"][:2],float)
    dz2=float(case["robot_z_m"]-case["anchor"][2])**2

    if kind=="gh":
        g,w=hermgauss(order)
        gx,gy=np.meshgrid(g, g,indexing="ij")
        standard=np.stack((gx.ravel(),gy.ravel()),axis=1)*math.sqrt(2)
        lgweights=np.log(np.outer(w,w).ravel()/math.pi)
    elif kind=="rqmc":
        u=qmc.Sobol(d=2,scramble=True,seed=seed).random_base2(int(math.log2(order)))
        standard=ndtri(np.clip(u,1e-12,1-1e-12))
        lgweights=np.full(len(standard),-math.log(len(standard)))
    else:
        raise ValueError(kind)
    result=np.empty(len(grid),float)
    logpriorpsi=h.wrapped_logprior(grid,x[2],varpsi)
    s=math.sqrt(Rs)
    for i,psi in enumerate(grid):
        m=x[:2]+float(h.wrap(psi-x[2]))*cross
        qmean,qcov=tilted_q(m,cov,zr,case,Rr)
        L=np.linalg.cholesky(qcov)
        xy=qmean+standard@L.T
        pts=np.empty((len(xy),3),float)
        pts[:,:2]=xy
        pts[:,2]=psi
        residual_s=zs-h.model(lut,pts,case)
        slant=np.sqrt(np.sum((xy-anchor)**2,axis=1)+dz2)
        residual_r=zr-slant
        loglike=-.5*((residual_s/s)**2+residual_r**2/Rr)
        sign,logdet=np.linalg.slogdet(qcov)
        if sign<=0:raise RuntimeError("Proposal Gaussian non-PD")
        logq=-math.log(2*math.pi)-.5*logdet
        ratio=independent_importance_log_density(
            xy,m,invprior,logprior,qmean,np.linalg.inv(qcov),logq)
        result[i]=logsumexp(lgweights+ratio+loglike)+logpriorpsi[i]
        if i%360==0:print("G3_TILTED",kind,order,seed,"angle",i,flush=True)
    return result


def main():
    from stages import audit,save
    audit("D")
    output=dict(stage="D",execution="RUNNING",calculation="NOT_EVALUATED",
        hypothesis="TILTED_QUADRATURE_REPAIRS_ORIGINAL_H3_G3_NUMERICAL_INTEGRAL",
        scientific_claim="CLAIM_BLOCK_G3_PERFORMANCE_UNTIL_INDEPENDENT_NUMERICAL",
        original_frozen_position_TV=0.38706501555739936,
        original_status="CASE_RESULT_INVALID_FROZEN_195p6s",
        actual_G3_reference="NOT_VALIDATED",scientific_PASS=False,
        numerical_orders=C["D"]["tilted_GH_orders"],independent_n=C["D"]["independent_rqmc_n"],
        independent_seeds=C["D"]["independent_seed"],next="NOT_EVALUATED")
    try:
        snap,case,lut,x,P,zs,zr=prev.frozen_snapshot()
        output["snapshot"]={k:v for k,v in snap.items()
                  if k not in ("frozen_input_sha256",)}
        output["source_inputs_sha256"]=snap["frozen_input_sha256"]
        grid=np.linspace(-math.pi,math.pi,1440,endpoint=False)
        gh=[]
        for order in C["D"]["tilted_GH_orders"]:
            started=time.time()
            lp=one_integral("gh",grid,order,case,lut,x,P,zs,zr)
            p=normalize(lp)
            row=dict(order=order,
                TV_prev=tv(p,gh[-1]["p"]) if gh else None,
                MAP_deg=float(math.degrees(grid[np.argmax(p)])),
                log_evidence=float(logsumexp(lp)+math.log(2*math.pi/len(grid))),
                seconds=float(time.time()-started),p=p,logp=lp)
            gh.append(row)
            np.savez_compressed(OUT/f"D_TILTED_GH_{order}.npz",angles=grid,post=p,logp=lp)
            print("TILTED_GH",order,"TVprev",row["TV_prev"],flush=True)
        output["tilted_results"]=[{k:v for k,v in row.items() if k not in ("p","logp")} for row in gh]
        ng=int(C["D"]["independent_rqmc_n"])
        seeds=list(C["D"]["independent_seed"])
        independent=[]
        for seed in seeds:
            started=time.time()
            lp=one_integral("rqmc",grid,ng,case,lut,x,P,zs,zr,seed)
            p=normalize(lp)
            independent.append(dict(seed=seed,p=p,lp=lp,
                                    time_s=time.time()-started,
                                    TV_vs_GH=tv(p,gh[-1]["p"]),
                                    MAP_deg=float(math.degrees(grid[np.argmax(p)])),
                                    log_evidence=float(logsumexp(lp)+math.log(2*math.pi/len(grid)))))
            np.savez_compressed(OUT/f"D_TILTED_RQMC_{seed}.npz",angles=grid,post=p,logp=lp)
        seed_tv=tv(independent[0]["p"],independent[1]["p"])
        max_tv=max(gh[-1]["TV_prev"],seed_tv,*[j["TV_vs_GH"] for j in independent])
        max_map=max(abs(float(gh[-1]["MAP_deg"]-j["MAP_deg"])) for j in independent)
        evidence=np.array([gh[-1]["log_evidence"]]+[j["log_evidence"] for j in independent])
        relative_evidence=float(np.max(np.abs(np.expm1(evidence-evidence[0]))))
        output.update(
            rqmc=[{k:v for k,v in j.items() if k not in ("p","lp")} for j in independent],
            seed_TV=seed_tv,max_TV=max_tv,max_MAP_delta_deg=max_map,
            max_relative_evidence=relative_evidence,
        )
        passed=(max_tv<=C["thresholds"]["posterior_tv"] and
                max_map<=C["thresholds"]["map_deg"] and
                relative_evidence<=.005)
        output["actual_G3_reference"]="PASS_INDEPENDENT_NUMERICAL" if passed else "CASE_RESULT_INVALID_NUMERICAL_NONCONVERGENCE"
        output["calculation"]="PASS_INDEPENDENT_NUMERICAL" if passed else "CASE_RESULT_INVALID_FROZEN_CELL"
        output["hypothesis"]="SUPPORTED" if passed else "CONTRADICTED_OR_UNRESOLVED"
        output["next"]="If numerical failure, no full one-step G3 accuracy claims or recursive G3. Record GH/QMC disagreement and seek revised numerical integration hypothesis."
    except Exception as ex:
        output["execution"]="FAIL_SCOPED"
        output["calculation"]="CASE_RESULT_INVALID"
        output["error_type"]=type(ex).__name__
        output["error"]=str(ex)
        output["traceback"]=traceback.format_exc()
        output["next"]="Diagnose source/numeric defect; do not run G3-dependent E/F"
    else:
        output["execution"]="PASS_COMPLETED_PROBE"
    finally:
        save("D_RESULT.json",output)
        print("STAGE_D_FINAL",json.dumps({k:output.get(k) for k in ("execution","calculation","hypothesis","actual_G3_reference","max_TV","next")}),flush=True)


if __name__=="__main__":
    main()
