#!/usr/bin/env python3
"""P0-P3 actual H3 RF, full 3x3 pose moments and numerical G2/G3 validation.

Original H3 RF observer/LUT, R0 Rs/Rr, gyro/wheel observations frozen and used
without fitting. Numerical proposal may change; likelihood does not.
No external B2 Office likelihood is silently injected into the incompatible
H3 sensor contract. Source/data/truth-leak gate runs before every stage.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,subprocess,sys,time,traceback
from pathlib import Path
import numpy as np
from numpy.polynomial.hermite import hermgauss
from scipy.special import logsumexp,ndtri
from scipy.stats import qmc

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
OUT=REPO/"outputs/G2G3_FULL_P0_P3"
H3=REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics"
ARCH=H3/"h3_offline/results/H3_OFFLINE_20261014_01a1380d"
sys.path.insert(0,str(H3))
sys.path.insert(0,str(ARCH))
import h3_cloud_stage1 as prev
h=prev.h
c=prev.c
h.REPO=REPO
C=json.loads((ROOT/"CONTRACT.json").read_text())

def wrap(x):return (np.asarray(x)+np.pi)%(2*np.pi)-np.pi

def save(name,data):
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/name
    if p.exists():raise FileExistsError("AUDIT: immutable output already exists "+name)
    def encode(z):
        if isinstance(z,np.generic):return z.item()
        if isinstance(z,np.ndarray):return z.tolist()
        raise TypeError(type(z).__name__)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False,default=encode))

def audit(stage):
    p=OUT/("PRE_RUN_"+stage+".json")
    if not p.is_file():raise RuntimeError("HARD_EXECUTION_BLOCK: missing stage audit")
    r=json.loads(p.read_text())
    if not r["code_match"] or r["run_decision"]!="GO_WITH_CLAIM_LIMITATION":
        raise RuntimeError("HARD_EXECUTION_BLOCK: source review not valid")
    for name,sha in r["source_sha256"].items():
        if hashlib.sha256((REPO/name).read_bytes()).hexdigest()!=sha:
            raise RuntimeError("HARD_EXECUTION_BLOCK: changed audited source "+name)

def model_inputs():
    p0=c.check_inputs(full_p0=False)
    lut=c.original_lut(p0)
    freq=c.spectrum(p0)
    p3=json.loads(c.P3_MODEL.read_text())
    fold=p3["loro_fold_params"]
    return p0,lut,freq,fold

def sample(p0,freq,fold,case_name,condition,level,seed,index,channel,range_model):
    case=next(q for q in p0["cases"] if q["id"]==case_name)
    times,truth,pids,motion,_=c.case_motion(p0,case,seed,level,condition)
    if index>=len(times) or times[index]<C["evaluation_start_s"]:
        raise RuntimeError("HARD_EXECUTION_BLOCK: selected sample outside evaluated time")
    filt=c.DiagnosticFilter(c.initial_state(truth[0],seed))
    for i in range(index+1):
        if i:filt.predict(float(motion["ds_odom"][i]),
                          float(motion["dtheta_gyro"][i]),
                          float(motion["dt_s"][i]))
    obs=c.rf_case(p0,case,channel,freq,pids)
    corr=c.corrected_ranges(obs,fold[case["route"]],
         allow_e1_on_los=False,channel=channel)
    if range_model not in corr:
        raise RuntimeError("HARD_EXECUTION_BLOCK: frozen corrected RF unavailable")
    zs=float(obs["s"][index]);zr=float(corr[range_model][index])
    x=filt.pose.copy();P=filt.Ppose.copy()
    if not (np.isfinite(x).all() and np.isfinite(P).all() and
       np.linalg.eigvalsh(P).min()>0 and np.isfinite([zs,zr]).all()):
        raise RuntimeError("HARD_EXECUTION_BLOCK: nonfinite original input or invalid DR covariance")
    return dict(case=case,case_id=case_name,condition=condition,level=level,seed=seed,
      sample=index,t_s=float(times[index]),channel=channel,range_model=range_model,
      x=x,P=P,truth=truth[index].copy(),z_s=zs,z_r=zr)

def stripped(row):
    return {k:v for k,v in row.items() if k not in ("case","x","P","truth")}

def get_nodes(kind,n,seed=None):
    if kind=="gh":
        x,w=hermgauss(n)
        a,b=np.meshgrid(x,x,indexing="ij")
        pts=np.stack([a.ravel(),b.ravel()],axis=1)*math.sqrt(2)
        lw=np.log(np.outer(w,w).ravel()/math.pi)
        return pts,lw
    u=qmc.Sobol(d=2,scramble=True,seed=seed).random_base2(int(math.log2(n)))
    pts=ndtri(np.clip(u,1e-12,1-1e-12))
    return pts,np.full(n,-math.log(n))

def likelihood_tilt(mean,cov,zr,case):
    """Frozen Range-only tilted proposal; exact importance weights restore original target."""
    anchor=np.asarray(case["anchor"][:2],float)
    dz2=(float(case["anchor"][2])-float(case["robot_z_m"]))**2
    old=mean.copy();RR=float(c.RR)
    for _ in range(15):
        dr=old-anchor
        rd=math.sqrt(float(dr@dr)+dz2)
        H=dr/rd
        gain=(cov@H)/(float(H@cov@H)+RR)
        x=mean+gain*(zr-rd+float(H@(old-mean)))
        if not np.isfinite(x).all():raise RuntimeError("CASE_RESULT_INVALID: proposal nonfinite")
        if np.linalg.norm(x-old)<1e-9:
            old=x;break
        old=.5*old+.5*x
    diff=old-anchor
    radial=math.sqrt(float(diff@diff)+dz2)
    H=diff/radial
    v=cov@H
    qcov=cov-np.outer(v,v)/(float(H@v)+RR)
    if np.linalg.eigvalsh(qcov).min()<=0:
        raise RuntimeError("CASE_RESULT_INVALID: tilted covariance not positive definite")
    return old,qcov

def sample_quadrature(obs,lut,mode,kind,n,seed=None,bins=1440,write_posterior=None):
    """Posterior moments from p(x,y|psi)*p(psi)*L_s*[L_r], unbiased for the GH/QMC target.

    G2X mode uses Gaussian EKF Range update if admitted, S likelihood exactly once.
    G3 mode uses exact nonlinear Range + S once with a proposal tilted towards Range.
    """
    x=obs["x"].copy();P=obs["P"].copy()
    case=obs["case"];zs=obs["z_s"];zr=obs["z_r"]
    range_gate="likelihood_no_gate"
    if mode=="G2X":
        x,P,range_gate=h.range_update(x,P,zr,case,0.,c.RR,True)
        if range_gate not in ("applied","rejected_NIS"):
            raise RuntimeError("CASE_RESULT_INVALID: unexpected original gate")
    elif mode!="G3":
        raise ValueError(mode)
    vpsi=float(P[2,2]);cov=P[:2,:2]-np.outer(P[:2,2],P[2,:2])/vpsi
    if np.linalg.eigvalsh(cov).min()<=0:raise RuntimeError("CASE_RESULT_INVALID: non-PD conditional prior")
    inv=np.linalg.inv(cov)
    lp_prior=-math.log(2*math.pi)-.5*float(np.linalg.slogdet(cov)[1])
    shift=P[:2,2]/vpsi
    anchor=np.asarray(case["anchor"][:2],float)
    dh2=(float(case["anchor"][2])-float(case["robot_z_m"]))**2
    standard,logweights=get_nodes(kind,n,seed)
    grid=np.linspace(-math.pi,math.pi,bins,endpoint=False)
    logp=np.empty(bins,float)
    mxy=np.empty((bins,2),float)
    covxy=np.empty((bins,2,2),float)
    priorlog=h.wrapped_logprior(grid,x[2],vpsi)
    for i,psi in enumerate(grid):
        mc=x[:2]+float(wrap(psi-x[2]))*shift
        if mode=="G3":
            qm,qp=likelihood_tilt(mc,cov,zr,case)
        else:
            qm,qp=mc,cov
        T=np.linalg.cholesky(qp)
        xy=qm+standard@T.T
        pts=np.empty((len(xy),3),float)
        pts[:,:2]=xy;pts[:,2]=psi
        error_s=(zs-h.model(lut,pts,case))
        logl=-.5*error_s**2/float(c.RS)
        if mode=="G3":
            pr=np.sqrt(((xy-anchor)**2).sum(axis=1)+dh2)
            error_r=zr-pr
            logl+=-.5*error_r**2/float(c.RR)
        dprior=xy-mc
        dq=xy-qm
        invq=np.linalg.inv(qp)
        logpriorx=lp_prior-.5*np.einsum("ni,ij,nj->n",dprior,inv,dprior,optimize=True)
        logqx=-math.log(2*math.pi)-.5*float(np.linalg.slogdet(qp)[1])-.5*np.einsum("ni,ij,nj->n",dq,invq,dq,optimize=True)
        lj=logweights+logpriorx-logqx+logl
        z=logsumexp(lj)
        if not np.isfinite(z):raise RuntimeError("CASE_RESULT_INVALID: zero/nonfinite quadrature evidence")
        ww=np.exp(lj-z)
        mean=ww@xy
        centered=xy-mean
        cv=centered.T@(centered*ww[:,None])
        mxy[i]=mean;covxy[i]=cv;logp[i]=z+priorlog[i]
        if i%360==0:print("FULL_POSE",mode,kind,n,seed,i,"/",bins,flush=True)
    post=np.exp(logp-logsumexp(logp))
    meanxy=post@mxy
    gauge=float(np.arctan2(post@np.sin(grid),post@np.cos(grid)))
    angular_resultant=float(math.hypot(post@np.sin(grid),post@np.cos(grid)))
    if angular_resultant<.05:
        gauge=float(grid[np.argmax(post)])
    angles=wrap(grid-gauge)
    cov_pose=np.zeros((3,3))
    dif=mxy-meanxy
    cov_pose[:2,:2]=np.einsum("n,nij->ij",post,covxy)+np.einsum("n,ni,nj->ij",post,dif,dif)
    cov_pose[:2,2]=cov_pose[2,:2]=(post[:,None]*dif*angles[:,None]).sum(axis=0)
    cov_pose[2,2]=post@(angles**2)
    cov_pose=(cov_pose+cov_pose.T)/2.
    minimum_eigen=float(np.linalg.eigvalsh(cov_pose).min())
    if minimum_eigen<=-1e-9 or not np.isfinite(cov_pose).all():
        raise RuntimeError("CASE_RESULT_INVALID: posterior 3state covariance not PSD")
    mean_pose=np.r_[meanxy,gauge]
    truth=obs["truth"]
    error=mean_pose-truth;error[2]=wrap(error[2])
    hmap=float(grid[np.argmax(post)])
    sortedp=np.sort(post)[::-1]
    min95=int(np.searchsorted(np.cumsum(sortedp),.95))+1
    truthidx=int(np.argmin(np.abs(wrap(grid-truth[2]))))
    cutoff=sortedp[min95-1]
    hpd_in=bool(post[truthidx]>=cutoff)
    try:nees=float(error@np.linalg.solve(cov_pose,error))
    except np.linalg.LinAlgError:nees=None
    result=dict(mode=mode,kind=kind,n=n,seed=seed,heading_bins=bins,
       evidence_log=float(logsumexp(logp)+math.log(2*math.pi/bins)),
       range_gate=range_gate,
       mean_pose=mean_pose.tolist(),P3=cov_pose.tolist(),
       cov3_min_eigen=minimum_eigen,
       heading_resultant=angular_resultant,
       MAP_rad=hmap,
       x_y_error_m=float(np.linalg.norm(error[:2])),
       heading_MAP_abs_error_deg=float(abs(wrap(hmap-truth[2]))*180/math.pi),
       heading_mean_abs_error_deg=float(abs(error[2])*180/math.pi),
       heading_hpd95_contains_truth=hpd_in,heading_hpd95_total_width_deg=min95*360/bins,
       posterior_pose_NEES=nees,
       dr_xy_error_m=float(np.linalg.norm(obs["x"][:2]-truth[:2])),
       dr_heading_abs_error_deg=float(abs(wrap(obs["x"][2]-truth[2]))*180/math.pi),
       true_pose=truth.tolist(),prior_pose=obs["x"].tolist(),
       observed_s=zs,observed_r=zr,
       posterior=np.asarray(post))
    if write_posterior is not None:
        np.savez_compressed(write_posterior,angles=grid,prob=post,logp=logp,
            meanxy_by_heading=mxy,covxy_by_heading=covxy,mean_pose=mean_pose,P=cov_pose)
    return result

def without_arrays(row):
    return {k:v for k,v in row.items() if k!="posterior"}

def compare(a,b):
    pa=a["posterior"];pb=b["posterior"]
    if pa.shape!=pb.shape:raise RuntimeError("CASE_RESULT_INVALID: posterior angle grids differ")
    return dict(tv=float(.5*np.abs(pa-pb).sum()),
        map_delta_deg=float(abs(wrap(a["MAP_rad"]-b["MAP_rad"]))*180/math.pi),
        evidence_rel=float(abs(math.expm1(a["evidence_log"]-b["evidence_log"]))),
        max_xy_mean_delta_m=float(np.max(np.abs(np.asarray(a["mean_pose"][:2])-np.asarray(b["mean_pose"][:2])))),
        max_cov_entry_delta=float(np.max(np.abs(np.asarray(a["P3"])-np.asarray(b["P3"])))))

def numeric_valid(pair):
    fixed=C["fixed"]
    return (pair["tv"]<=fixed["tv"] and pair["map_delta_deg"]<=fixed["map_angle_deg"] and
            pair["evidence_rel"]<=fixed["evidence_relative"] and
            pair["max_xy_mean_delta_m"]<=fixed["mean_3state_accuracy_m"] and
            pair["max_cov_entry_delta"]<=fixed["cov_3state_accuracy_max"])

def stage_p0():
    audit("P0")
    started=time.time()
    snap,p0,lut,x,P,zs,zr=prev.frozen_snapshot()
    if abs(snap["time_s"]-195.6)>1e-9:raise RuntimeError("HARD_EXECUTION_BLOCK: frozen time mismatch")
    meta=dict(stage="P0",status="PASS_SOURCE_AND_D0_G0_PARITY",case=snap["case"],
      snapshot=snap,input_valid=True,scientific_PASS=False,
      source_revision=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(),
      frozen_original_blob=c.check_frozen_baseline_files(),actual_RS=float(c.RS),actual_RR=float(c.RR),
      seed_independence="Same original RF scene for all DR seeds",elapsed_s=time.time()-started,
      claim="Code/input parity only. Original numerical failures remain documented.")
    save("P0_RESULT.json",meta)
    print("P0_FINAL",meta["status"],meta["actual_RS"],meta["actual_RR"],flush=True)

def stage_p1():
    audit("P1")
    p0,lut,freq,fold=model_inputs()
    f=C["fixed"]
    obs=sample(p0,freq,fold,f["case"],f["condition"],f["level"],f["seed"],f["sample"],f["channel"],f["range_model"])
    x,P,zr=obs["x"],obs["P"],obs["z_r"]
    xp,pp,gate=h.range_update(x,P,zr,obs["case"],0.,c.RR,True)
    s_los=h.posterior(h.fixed_logfun(lut,x,P,obs["z_s"],obs["case"]))
    with (ARCH/"STAGE4_SMOKE_01/SMOKE_PARTIAL.csv").open(newline="",encoding="utf-8-sig") as stream:
        source=[row for row in csv.DictReader(stream) if
              row["case"]==obs["case_id"] and
              row["condition"]==obs["condition"] and int(row["level"])==obs["level"] and
              int(row["seed"])==obs["seed"] and row["channel"]==obs["channel"] and
              row["range_model"]==obs["range_model"] and int(row["sample"])==obs["sample"]]
    oldg0=next((r for r in source if r["method"]=="G0"),None)
    oldg2=next((r for r in source if r["method"]=="G2X"),None)
    if oldg0 is None or oldg2 is None:
        raise RuntimeError("HARD_EXECUTION_BLOCK: archived G0/G2X missing")
    g0parity=abs(float(wrap(s_los["MAP"]-float(oldg0["MAP_rad"]))))
    if g0parity>1e-7 or gate!=oldg2["range_gate"]:
        raise RuntimeError("HARD_EXECUTION_BLOCK: original G0/G2X/source gate mismatch")
    # Analytic normalized Gaussian dependence factorization for nonzero Rsr
    residual=np.array([.12,-.05]);sig=np.array([[.045,.009],[.009,.018]])
    inv=np.linalg.inv(sig)
    logjoint=-.5*float(residual@inv@residual)-.5*math.log(float((2*math.pi)**2*np.linalg.det(sig)))
    mu_s=sig[0,1]/sig[1,1]*residual[1]
    cond=sig[0,0]-sig[0,1]**2/sig[1,1]
    logseq=(-.5*residual[1]**2/sig[1,1]-.5*math.log(2*math.pi*sig[1,1])-
            .5*(residual[0]-mu_s)**2/cond-.5*math.log(2*math.pi*cond))
    delta=abs(logjoint-logseq)
    if delta>1e-12:raise RuntimeError("HARD_EXECUTION_BLOCK: Gaussian conditional double-counting formula mismatch")
    save("P1_RESULT.json",dict(stage="P1",status="PASS_R0_SOURCE_MODEL_AND_FACTOR",
       G0_MAP_parity_rad=g0parity,archived_G2X_range_gate=gate,
       rejected_prior_to_RF_range_delta_m=float(zr-h.c.range_h(x,obs["case"]["anchor"],obs["case"]["robot_z_m"])[0]),
       S_R_nonzero_correlation_factorization_abs_log_difference=delta,
       R0_s_r_correlation=0,measurements_counted_once=True,
       R0_Frozen_source="PASS",external_B2_to_H3_source_equivalence="NOT_ESTABLISHED",
       B2_candidate_status="CLAIM_BLOCK_ONLY_B2_NOT_R0",
       scientific_PASS=False))
    print("P1_FINAL PASS G0parity",g0parity,"range_gate",gate,"conditional_error",delta,flush=True)

def stage_p2():
    audit("P2")
    if json.loads((OUT/"P1_RESULT.json").read_text())["status"].startswith("PASS") is False:
        raise RuntimeError("HARD_EXECUTION_BLOCK: P1 not passed")
    p0,lut,freq,fold=model_inputs();z=C["fixed"]
    obs=sample(p0,freq,fold,z["case"],z["condition"],z["level"],z["seed"],z["sample"],z["channel"],z["range_model"])
    all_rows=[];status="RUNNING";pairs=[]
    for n in z["gh_orders"]:
        now=time.perf_counter()
        try:
            a=sample_quadrature(obs,lut,"G3","gh",n,bins=z["posterior_heading_bins"],
                 write_posterior=OUT/f"P2_G3_GH_{n}.npz")
            all_rows.append(dict(without_arrays(a),seconds=time.perf_counter()-now))
            pairs.append(a)
        except Exception as e:
            all_rows.append(dict(mode="G3",kind="gh",n=n,exception=str(e),exception_type=type(e).__name__))
    for seed in z["rqmc_seeds"]:
        now=time.perf_counter()
        try:
            a=sample_quadrature(obs,lut,"G3","rqmc",z["rqmc_n"],seed=seed,bins=z["posterior_heading_bins"],
                write_posterior=OUT/f"P2_G3_RQMC_{seed}.npz")
            all_rows.append(dict(without_arrays(a),seconds=time.perf_counter()-now))
            pairs.append(a)
        except Exception as e:
            all_rows.append(dict(mode="G3",kind="rqmc",n=z["rqmc_n"],seed=seed,exception=str(e),exception_type=type(e).__name__))
    checks=[]
    if len(pairs)==4:
        for i in range(1,len(pairs)):
            checks.append(dict(compared=f"{pairs[0]['kind']}{pairs[0]['n']} vs {pairs[i]['kind']}{pairs[i]['n']} seed{pairs[i]['seed']}",
                      **compare(pairs[0],pairs[i])))
        checks.append(dict(compared="QMC seed vs seed",**compare(pairs[2],pairs[3])))
        status="PASS_INDEPENDENT_HEADING_AND_3STATE_MOMENTS" if all(numeric_valid(v) for v in checks) else "CASE_RESULT_INVALID_NUMERIC_PRECISION"
    else:status="CASE_RESULT_INVALID_NUMERICAL_EXCEPTION"
    result=dict(stage="P2",status=status,case=obs["case_id"],condition=obs["condition"],
      level=obs["level"],seed=obs["seed"],sample=obs["sample"],time_s=obs["t_s"],
      numerical_comparisons=checks,methods=all_rows,scientific_PASS=False,
      old_reference="Original GH41/65 TV 0.387065 invalid; BF tilted GH pilot numerically validated heading only",
      semantic_scope="Actual original H3 RF/LUT full 3state posterior moments under R0, no independent calibrated B2 replacement.")
    save("P2_RESULT.json",result)
    print("P2_FINAL",status,"checks",checks,flush=True)

def stage_p3():
    audit("P3")
    prior=json.loads((OUT/"P2_RESULT.json").read_text())
    if "HARD_EXECUTION_BLOCK" in prior.get("status",""):
        raise RuntimeError("HARD_EXECUTION_BLOCK: invalid source dependency")
    p0,lut,freq,fold=model_inputs()
    rows=[]
    for sel in C["p3_preselected"]:
        b=dict(sel)
        try:
            obs=sample(p0,freq,fold,sel["case"],sel["condition"],sel["level"],sel["seed"],
                       sel["sample"],sel["channel"],sel["range_model"])
        except Exception as e:
            rows.append(dict(b,status="HARD_EXECUTION_BLOCK",error=str(e)))
            continue
        b["time_s"]=obs["t_s"]
        for mode in ("G2X","G3"):
            previous=None;valid=False
            for n in C["p3_gh_orders"]:
                try:
                    output=sample_quadrature(obs,lut,mode,"gh",n,bins=C["p3_heading_bins"])
                    difference=compare(output,previous) if previous is not None else None
                    valid=bool(difference and numeric_valid(difference))
                    row=dict(b,method=mode,gh_order=n,
                        calculation="PASS_INTERNAL_CONVERGENCE" if valid else "NEEDS_MORE_NUMERICAL_RESOLUTION",
                        **without_arrays(output),
                        **({("comparison_"+k):v for k,v in difference.items()} if difference else {}))
                    rows.append(row)
                    if valid:break
                    previous=output
                except Exception as e:
                    rows.append(dict(b,method=mode,gh_order=n,
                        calculation="CASE_RESULT_INVALID_NUMERIC_EXCEPTION",error_type=type(e).__name__,error=str(e)))
                    break
    # All rows even invalid are preserved; no removing bad performance outcomes.
    path=OUT/"P3_ONE_STEP_TRACE.csv"
    cols=list(dict.fromkeys(k for r in rows for k in r))
    with path.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=cols);writer.writeheader()
        for line in rows:
            writer.writerow({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in line.items()})
    nvalid=sum(r.get("calculation")=="PASS_INTERNAL_CONVERGENCE" for r in rows)
    errors=[r for r in rows if r.get("calculation","").startswith("CASE_RESULT_INVALID")]
    results=dict(stage="P3",status="COMPLETED_WITH_NUMERICAL_SCOPE",n_requested=len(C["p3_preselected"])*2,
        n_valid=nvalid,n_unresolved=len(C["p3_preselected"])*2-nvalid,
        n_numeric_exceptions=len(errors),all_records=len(rows),
        requirements="Do not select favorable cells; include all numerical failures and heading/position deterioration",
        scientific_claim="NO_GENERALIZATION_SINGLE_SEED_AND_R0",scientific_PASS=False,
        next="P4 must evaluate paired multiple routes and reference accuracy separately from numeric invalid failures")
    save("P3_RESULT.json",results)
    print("P3_FINAL",results,flush=True)

if __name__=="__main__":
    par=argparse.ArgumentParser()
    par.add_argument("stage",choices=["P0","P1","P2","P3"])
    args=par.parse_args()
    try:
        globals()["stage_"+args.stage.lower()]()
    except Exception as err:
        OUT.mkdir(parents=True,exist_ok=True)
        p=OUT/(args.stage+"_ERROR.json")
        p.write_text(json.dumps(dict(stage=args.stage,error_type=type(err).__name__,
             error=str(err),traceback=traceback.format_exc(),scientific_PASS=False),ensure_ascii=False,indent=2))
        print("STAGE_FATAL",args.stage,type(err).__name__,str(err),flush=True)
        raise
