#!/usr/bin/env python3
"""RA5-I2: independent synthetic field/time/white known-generative controlled test.
Reuses pinned MBVAR-INFO info_core.k_pose,k_time,obs_covariance,psd_sqrt.
Not a measurement of physical RF temporal variation. No H/RT modification.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,importlib.util,json,math,os,pathlib
import numpy as np

def must(test,msg):
    if not test:raise RuntimeError(msg)
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read_ic(file,expected_git_blob=None):
    """Call the original mathematical implementation, not an independent redefinition."""
    require=pathlib.Path(file)
    must(require.is_file(),"ERR_SOURCE_INFO_CORE")
    s=importlib.util.spec_from_file_location("pinned_mbvar_info_core",require)
    m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    return m
def mk_route(kind):
    if kind=="REV60":
        k=np.r_[np.arange(0,31),np.arange(29,0,-1)]
    elif kind=="FWD60":
        k=np.arange(60)
    else:raise ValueError(kind)
    x=np.round(3.+.05*k,10);return np.c_[x,np.full(len(k),7.)],np.zeros(len(k)),.5*np.arange(len(k))
def make_sample(Kp_unique,Pt,loc,alpha,rng,ic,cross=.3):
    ap,at,aw=alpha
    n=len(loc)
    U=ic.sample_unit_field(Kp_unique,rng,channels=2,c=0.)[loc]
    T=ic.sample_unit_field(Pt,rng,channels=2,c=0.)
    V=rng.standard_normal((n,2))
    C=np.linalg.cholesky(np.array([[1.,cross],[cross,1.]]))
    spatial=math.sqrt(ap)*U@C.T
    timed=math.sqrt(at)*T@C.T
    white=math.sqrt(aw)*V@C.T
    return spatial+timed+white,spatial,timed,white

def fit_components(X,Kp,Kt):
    B=np.stack([Kp.ravel(),Kt.ravel(),np.eye(len(Kp)).ravel()],axis=1)
    solution=np.linalg.lstsq(B,X.ravel(),rcond=None)[0]
    return solution,float(np.linalg.cond(B)),int(np.linalg.matrix_rank(B, tol=1e-10))

def experiment(kind,ic,alpha,nfields,seed):
    positions,yaw,t=mk_route(kind)
    unique,loc=np.unique(positions,axis=0,return_inverse=True)
    Kp_u=ic.k_pose(unique,np.zeros(len(unique)),.5,math.radians(20))
    Kp=Kp_u[np.ix_(loc,loc)]
    Kt=ic.k_time(t,3.)
    Lp,mi,ma=ic.psd_sqrt(Kp_u)
    Lt,mt,mb=ic.psd_sqrt(Kt)
    r=np.random.default_rng(seed);samples=[];spatial_same=0.
    pairs=[]
    if kind=="REV60":
        indices={}
        for i,x in enumerate(loc):indices.setdefault(int(x),[]).append(i)
        pairs=[v[:2] for v in indices.values() if len(v)==2]
        must(len(pairs)==29,"ERR_REV_PAIRS "+str(len(pairs)))
    data_diffs=[]
    for f in range(nfields):
        Y,P,T,W=make_sample(Lp,Lt,loc,alpha,r,ic)
        samples.append(Y)
        if pairs:
            spatial_same=max(spatial_same,max(float(np.max(np.abs(P[i]-P[j]))) for i,j in pairs))
            data_diffs.append([float(Y[i,1]-Y[j,1]) for i,j in pairs])
    must(spatial_same==0.,"ERR_SPATIAL_REVISIT_NOT_SHARED")
    A=np.stack(samples)
    cov=np.cov(A[:,:,1],rowvar=False)
    ctrue=alpha[0]*Kp+alpha[1]*Kt+alpha[2]*np.eye(len(t))
    err=float(np.linalg.norm(cov-ctrue)/np.linalg.norm(ctrue))
    coeff,cond,rank=fit_components(cov,Kp,Kt)
    coeff_exact,_,rank_exact=fit_components(ctrue,Kp,Kt)
    must(max(abs(coeff_exact-np.asarray(alpha)))<1e-10,"ERR_KNOWN_COV_DECOMP")
    must(np.isfinite(err) and err<.35,"ERR_GENERATOR_COV_MISMATCH "+str(err))
    out=dict(route=kind,alpha_true=list(alpha),alpha_empirical=[float(x) for x in coeff],
       n_independent_fields=nfields,n_observations_per_field=len(t),
       n_exact_revisit_pairs=len(pairs),min_pose_kernel_eig=mi,min_time_kernel_eig=mt,
       covariance_relative_error=err,source_component_rank=rank,
       kernel_design_cond=cond,spatial_revisit_identity_max=spatial_same,
       recovery_max_abs=float(np.max(abs(coeff-np.asarray(alpha)))),
       field_statistical_units=nfields,
       scientific_scope="KNOWN_SYNTHETIC_GENERATOR_NO_PHYSICAL_TIME_RF")
    if pairs:
        dt=np.array([abs(t[i]-t[j]) for i,j in pairs])
        D=np.asarray(data_diffs)
        target_var=D.var(axis=0,ddof=1)/2
        # Identifiability from same-pose temporal changes: space cancels, time and white remain.
        AA=np.column_stack([1-np.exp(-dt/3.),np.ones(len(dt))])
        aa=np.linalg.lstsq(AA,target_var,rcond=None)[0]
        out.update(pair_time_alpha_est=float(aa[0]),pair_white_alpha_est=float(aa[1]),
            pair_time_alpha_true=float(alpha[1]),pair_white_alpha_true=float(alpha[2]),
            pair_design_rank=int(np.linalg.matrix_rank(AA)),
            pair_design_cond=float(np.linalg.cond(AA)),
            pair_differencing_formula="Var((eps_t2-eps_t1))/2 = alpha_t*(1-exp(-dt/tau)) + alpha_w")
        must(out["pair_design_rank"]==2,"ERR_TEMPORAL_REVISIT_RANK")
        must(abs(aa[0]-alpha[1])<.18 and abs(aa[1]-alpha[2])<.18,
             "ERR_TEMPORAL_FIT_SAMPLE "+str((aa,alpha)))
    else:
        out["pair_time_alpha_est"]=None
        out["pair_white_alpha_est"]=None
        out["pair_design_rank"]=0
        out["revisit_identification"]="NOT_IDENTIFIABLE_FROM_SAME_POSE_DIFFERENCING"
    return out

def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    ic=read_ic(args.info_core)
    # Verify that the library has exact intended covariance API and agrees with unit marginal.
    p,y,t=mk_route("REV60")
    k=ic.k_pose(p,y,.5,math.radians(20))
    tk=ic.k_time(t,3.)
    sig=np.ones((60,2))
    alpha=(.5,.3,.2)
    S=ic.obs_covariance(k,tk,alpha,sig,.3)
    must(S.shape==(120,120) and np.linalg.eigvalsh(S)[0]>-1e-9,"ERR_UPSTREAM_CORE_COV")
    res=[
      experiment("REV60",ic,(.5,.3,.2),args.fields,100),
      experiment("FWD60",ic,(.5,.3,.2),args.fields,101),
      experiment("REV60",ic,(.7,0.,.3),args.fields,102),
    ]
    with (out/"RA5_FIELD_TIME_PROBE.csv").open("w",newline="") as f:
        keys=sorted(set().union(*(r.keys() for r in res)))
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(res)
    qa=dict(status="PASS_SYNTHETIC_FIELD_TIME_GENERATOR_AND_REVISIT_IDENTIFIABILITY",
      source_info_core_sha256=sha(args.info_core),
      n_independent_field_draws_per_arm=args.fields,
      cases=[r["route"] for r in res],n_synthetic_scenarios=len(res),
      true_alpha_recovered_within_bound=all(r["recovery_max_abs"]<.18 for r in res),
      covariance_symmetry_max=float(np.max(abs(S-S.T))),
      true_cov_min_eigen=float(np.linalg.eigvalsh(S)[0]),
      physical_rf_time_process="NOT_VALIDATED",
      real_sensor_noise_correlation="NOT_CALIBRATED",
      real_scenario_generalization="NOT_TESTED",
      time_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      independent_auditor=False)
    must(qa["true_alpha_recovered_within_bound"],"ERR_SYNTHETIC_ALPHA_RECOVERY")
    (out/"RA5_FIELD_TIME_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    (out/"RA5_FIELD_TIME_DETAILS.json").write_text(json.dumps(res,indent=2)+"\n")
    print("RA5_FIELD_TIME_FINAL "+json.dumps(qa),flush=True)
    for r in res:
        print("RA5_FIELD_TIME_SCENARIO "+json.dumps({k:r[k] for k in ("route","alpha_true","alpha_empirical","n_exact_revisit_pairs","pair_time_alpha_est","pair_white_alpha_est","recovery_max_abs","kernel_design_cond")}),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--info-core",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--fields",type=int,default=600)
    a=ap.parse_args();must(a.fields>=200,"ERR_MIN_INDEPENDENT_FIELDS");main(a)
