#!/usr/bin/env python3
"""Independent polar radial/azimuth numerical reference for the frozen failed G3 cell."""
from __future__ import annotations
import argparse,csv,json,math,sys,time,traceback
from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from numpy.polynomial.legendre import leggauss

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import h3_cloud_stage1 as phase1
h=phase1.h
c=phase1.c
RADIAL_SIGMAS=8.0

def log_reference(case,lut,x,P,zs,zr,grid,na,nr):
    # Independent integral in anchor-centred (slant range, azimuth),
    # dx dy = r dr d(alpha). Never uses original GH nodes.
    a=np.asarray(case['anchor'][:2],float)
    dz=abs(float(case['anchor'][2]-case['robot_z_m']))
    eigen=np.linalg.eigvalsh(P[:2,:2])
    maxrho=np.linalg.norm(x[:2]-a)+10*np.sqrt(eigen[-1])+3.0
    upper=float(np.sqrt(maxrho**2+dz**2))
    if upper<zr+2:upper=zr+2
    sig=math.sqrt(c.RR)
    # Split at the likelihood's dominant radial interval; retain prior tails.
    bounds=sorted(set([dz, upper]+
        [float(v) for v in (zr-RADIAL_SIGMAS*sig,zr+RADIAL_SIGMAS*sig)
         if dz<v<upper]))
    ga,wa=leggauss(na)
    alpha=math.pi*ga
    logwa=np.log(wa*math.pi)
    gu,wu=leggauss(nr)
    rv=[];lw=[]
    for low,high in zip(bounds[:-1],bounds[1:]):
        radius=(high+low)/2+(high-low)*gu/2
        weight=wu*(high-low)/2
        radius=np.maximum(radius,dz+1e-12)
        rv.extend(radius)
        lw.extend(np.log(weight))
    rv=np.asarray(rv); lw=np.asarray(lw)
    radius_grid=np.repeat(rv,na)
    az=np.tile(alpha,len(rv))
    horizontal=np.sqrt(np.maximum(radius_grid**2-dz**2,0.0))
    xy=np.column_stack([a[0]+horizontal*np.cos(az),a[1]+horizontal*np.sin(az)])
    logquadrature=np.repeat(lw,na)+np.tile(logwa,len(rv))+np.log(radius_grid)
    logrange=-.5*(zr-radius_grid)**2/c.RR
    invbase=np.linalg.inv(P[:2,:2]-np.outer(P[:2,2],P[2,:2])/P[2,2])
    factor=np.linalg.slogdet(P[:2,:2]-np.outer(P[:2,2],P[2,:2])/P[2,2])
    if factor[0]<=0:raise RuntimeError("Conditional covariance not PD")
    lognormal=-math.log(2*math.pi)-.5*factor[1]
    cross=P[:2,2]/P[2,2]
    output=np.empty(grid.size)
    # Process each heading separately to bound memory and store complete profile.
    for i,psi in enumerate(grid):
        mean=x[:2]+float(h.wrap(psi-x[2]))*cross
        dif=xy-mean
        logpriorxy=lognormal-.5*np.einsum("ni,ij,nj->n",dif,invbase,dif,optimize=True)
        pts=np.empty((len(xy),3))
        pts[:,:2]=xy
        pts[:,2]=psi
        residual=zs-h.model(lut,pts,case)
        loglike=-.5*residual**2/c.RS+logrange
        output[i]=logsumexp(loglike+logpriorxy+logquadrature)+float(
            h.wrapped_logprior(np.asarray([psi]),x[2],P[2,2])[0])
        if i%360==0:print("REF",na,nr,"angle",i,flush=True)
    return output

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--out",type=Path,required=True)
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    report=dict(stage=2,status="RUNNING",scientific_PASS=False,recursive_fusion="NOT_RUN",
       hypothesis="Polar reference resolves GH instability to TV<=0.001",
       confirmed=[],contradicted=[],unresolved=[],next_action="STOP")
    records=[]
    try:
        snap,case,lut,x,P,zs,zr=phase1.frozen_snapshot()
        report["snapshot_id"]={k:snap[k] for k in ("case","condition","level","seed","sample","time_s")}
        grid=np.linspace(-math.pi,math.pi,1440,endpoint=False)
        base=None
        for na,nr in ((48,32),(96,64),(144,96)):
            start=time.time()
            lp=log_reference(case,lut,x,P,zs,zr,grid,na,nr)
            prob=phase1.probabilities(lp)
            path=args.out/f"polar_{na}_{nr}.npz"
            np.savez_compressed(path,angle_rad=grid,prob=prob,logp=lp)
            tv=phase1.total_variation(prob,base) if base is not None else None
            records.append(dict(nazimuth=na,nradial=nr,n_angles=len(grid),
                posterior_TV_previous=tv,MAP_grid_rad=float(grid[np.argmax(prob)]),
                log_evidence=float(logsumexp(lp)+math.log(2*math.pi/len(grid))),
                elapsed_s=time.time()-start))
            print(f"POLAR {na}x{nr} TV={tv}",flush=True)
            base=prob
        report["checks"]=records
        passed=all(record["posterior_TV_previous"] is not None and
                   record["posterior_TV_previous"]<=0.001 for record in records[-1:])
        if passed:
            report["confirmed"].append("Polar integration last-grid TV<=0.001")
            report["status"]="PASS_INTERNAL_POLAR_CONVERGENCE"
            report["next_action"]="Cross-check second independent integrator and MAP/HPD before Phase3"
            report["unresolved"].append("GH reference agreement and tail truncation not yet independently bounded")
            exitcode=0
        else:
            report["contradicted"].append("Three-resolution polar integral is not converged to TV<=0.001")
            report["status"]="NUMERICAL_HYPOTHESIS_CONTRADICTED_STOP"
            report["next_action"]="Review posterior modes/tail bound and adapt integration proposal; do not run Phase3"
            report["unresolved"].append("Polar tail truncation and likelihood support remain unverified")
            exitcode=3
    except Exception as exc:
        report["status"]="FAIL_CLOSED_BLOCKED"
        report["error"]=repr(exc);report["traceback"]=traceback.format_exc()
        report["unresolved"].append("Cloud reference computation incomplete")
        exitcode=2
    finally:
        with (args.out/"STAGE2_REFERENCE.csv").open("w",newline="") as f:
            if records:
                w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
        (args.out/"STAGE2_REPORT.json").write_text(json.dumps(report,indent=2,allow_nan=False))
        print("PHASE2_FINAL",json.dumps({k:report[k] for k in ("status","confirmed","contradicted","unresolved","next_action")}),flush=True)
    return exitcode

if __name__=="__main__":
    sys.exit(main())
