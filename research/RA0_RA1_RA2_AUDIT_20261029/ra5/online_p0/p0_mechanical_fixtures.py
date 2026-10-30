#!/usr/bin/env python3
"""RA5 P0 engineering negative controls and source-FFD fractional Jacobian QA."""
import argparse,datetime,json,inspect,math,pathlib,sys
import numpy as np
import online_observer as O
import run_prior_joint_canary as F

def must(x,msg):
    if not x:raise RuntimeError(msg)
def main(out):
    out=pathlib.Path(out);out.mkdir(parents=True,exist_ok=True)
    # Source/model pinned by runtime via existing common.base_model bank SHA checks.
    model=F.A.C.base_model()
    spec=F.A.C.CASES["R5_aA_m0"]
    state=np.array([[5.194742,.443085,math.radians(-2.990632),0.],
                    [2.259213,.031186,math.radians(-182.329178),0.],
                    [5.,1.,.3,0.]],float)
    obs=O.source_los(model,state,spec)
    valid=np.flatnonzero(obs["valid_sub"])
    must(len(valid)>=2,"ERR_SOURCE_FRACTIONAL_SOURCE_INVALID")
    rows=[]
    for i in valid:
        x=state[i]
        z,J,dg=O.source_jacobian(model,x,spec)
        must(np.max(abs(z-np.array([obs["r_sub"][i],obs["s0"][i],obs["ds1"][i]])))<1e-12,
             "ERR_SOURCE_OBS_DIFFERENCE")
        near=O.source_los(model,(x+np.array([1e-4,0.,0.,0.]))[None],spec)
        minus=O.source_los(model,(x-np.array([1e-4,0.,0.,0.]))[None],spec)
        if int(near["tap"][0])==int(obs["tap"][i])==int(minus["tap"][0]):
            fd=float((near["r_sub"][0]-minus["r_sub"][0])/(2e-4))
            must(abs(fd-J[0,0])<=1e-5,"ERR_REAL_SOURCE_R_JAC "+str([fd,J[0,0]]))
        rows.append(dict(pose=int(i),source_r_sub_m=float(z[0]),s0=float(z[1]),
            ds1=float(z[2]),tap=int(dg["tap"]),source_margin=float(dg["margin"]),
            source_branch_stable=bool(dg["smooth_active_branch"]),J_r_x=float(J[0,0])))
    X=np.array([O.bias_features("R5_aA_m0",x,spec) for x in state])
    fit=O.fit_bias(X,np.array([-.3,-.4,-.5]))
    val=O.predict_bias(fit,"R5_aA_m0",state[0],spec)
    val2=O.predict_bias(fit,"R5_aA_m0",state[0].copy(),spec)
    must(val==val2,"ERR_NONDETERMINISTIC_PRIOR_FEATURE")
    # No GT input to the implementation function.
    must("gt" not in inspect.signature(F.run_online).parameters,
        "ERR_FILTER_TRUTH_ARGUMENT")
    q=np.array(["AMBIG"]*300+["STABLE"]*300)
    E=np.random.default_rng(32).standard_normal((600,3))@np.array([[.13,.03,-.02],[0,.07,.025],[0,0,.04]])
    r=O.fit_covariance(E,q)
    must(all(np.linalg.eigvalsh(r[k]["R3"]).min()>0 for k in r),"ERR_PSD")
    cat=O.fit_categorical(np.arange(600)%7-3,q)
    must(all(abs(sum(cat[k]["p"].values())-1)<1e-12 for k in cat),"ERR_CLASS_NORM")
    s=np.random.default_rng(2).standard_normal((600,1))
    bad=np.repeat(s,3,axis=1)
    rejected=False
    try:O.fit_covariance(bad,q)
    except RuntimeError as e:
        if "ERR_R_NOT_PD" in str(e):rejected=True
    must(rejected,"ERR_SINGULAR_COVARIANCE_WAS_ACCEPTED")
    # Duplicate the second observation, which must have rank two, and Schur transform.
    R=r["STABLE"]["R3"]
    T=np.array([[1.,0.,0.],[0.,1.,0.],[0.,-1.,1.]])
    H=np.array([[1.,0.,0.,0.],[0,0,1,0],[.1,0,-.3,0.]])
    I=H.T@np.linalg.solve(R,H)
    Rq=T@R@T.T;Hq=T@H
    err=float(np.max(abs(I-Hq.T@np.linalg.solve(Rq,Hq))))
    must(err<1e-9,"ERR_EQUIV_FISHER")
    must(len(rows)>=2 and rejected,"ERR_NEGATIVE_TEST_COUNT")
    qa=dict(status="PASS_RA5_P0_TECHNICAL_SOURCE_AND_NEGATIVE_FIXTURES",
        n_source_poses=len(rows),numeric_Fisher_equivalence_error=err,
        singular_covariance_fixture_rejected=rejected,
        categorical_normalized=True,source_fractional_observer_valid=True,
        prior_model_independent_of_test_gt_parameter=True,
        independent_auditor=False,scientific_release=False,
        timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_P0_UNIT_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    (out/"RA5_P0_UNIT_ROWS.json").write_text(json.dumps(rows,indent=2)+"\n")
    print("RA5_P0_UNIT_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out",required=True);x=p.parse_args()
    main(x.out)
