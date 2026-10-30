#!/usr/bin/env python3
"""RA5-ONLINE-P0 engineering: original BB full-state/P parity -> train-only
prior-mean / categorical tap discrepancy / FULL 3x3 model-error covariance
-> new 2/3-observation EKF at fixed vs self gate. NO RT, no independent release.

Only one held-out route per job; all source GT used strictly to train on other
routes, and for scoring after inference. The inference function accepts no GT.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,os,pathlib,sys,time
import numpy as np
HERE=pathlib.Path(__file__).resolve()
RA4=HERE.parents[1]/"ra4"
INTEG=HERE.parents[1]/"ra5"/"integration"
# Actual path: .../ra5/online_p0/file.py -> parents[0]=online_p0; parents[1]=ra5
RA4=HERE.parents[2]/"ra4"
INTEG=HERE.parents[1]/"integration"
sys.path.insert(0,str(RA4))
sys.path.insert(0,str(INTEG))
import ra4_effect_isolation as A
import online_observer as O

CASES=A.CASES
N_BY_ROUTE={"R2":979,"R4":742,"R5":1415}
SCHEMA="RA5_ONLINE_P0_20261030"
ORIGINAL_SHA="9bcd5da2fbadde626c9ff8cdc9ea940e6c980b13"

def must(b,msg):
    if not b:raise RuntimeError(msg)
def native_json(obj):
    if isinstance(obj,np.generic):return obj.item()
    if isinstance(obj,np.ndarray):return obj.tolist()
    raise TypeError('UNSUPPORTED_JSON_TYPE '+type(obj).__name__)
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def write_csv(p,rows):
    must(bool(rows),"ERR_EMPTY_TABLE "+str(p))
    keys=sorted(set().union(*(r.keys() for r in rows)))
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def matrix_json(D):
    return [[float(x) for x in row] for row in np.asarray(D)]
def load_source(case,root,assets,freq,model):
    """Source original Full-H and SAMPLES truth for teacher training, not inference."""
    n=N_BY_ROUTE[case[:2]];p=root/("H_"+case+".npy")
    sp=root/("SAMPLES_"+case+".json")
    name=next(k for k in assets if k.endswith("/FULL_RF/H_"+case+".npy"))
    nameS=next(k for k in assets if k.endswith("/"+case+"/SAMPLES.json"))
    must(sha(p)==assets[name]["sha256"] and sha(sp)==assets[nameS]["sha256"],
         "ERR_SOURCE_SHA "+case)
    h=np.load(p,mmap_mode="r",allow_pickle=False)
    samples=json.loads(sp.read_text())
    must(len(samples)==len(h) and n<=len(samples),"ERR_SAMPLE_COUNT "+case)
    spec=A.C.CASES[case]
    gt=np.array([[s["x"],s["y"],math.radians(s["yaw_body_deg"]),0.]
                 for s in samples[:n]],float)
    frames={k:[] for k in ("r_int","r_sub","s0","ds1","tap","port","margin","valid_sub")}
    src={k:[] for k in ("r_sub","s0","ds1","tap","port")}
    for start in range(0,n,64):
        stop=min(n,start+64)
        fr=O.observer(np.asarray(h[start:stop,:,:,0]),float(freq[1]-freq[0]))
        sr=O.source_los(model,gt[start:stop],spec)
        for k in frames:frames[k].extend(fr[k])
        for k in src:src[k].extend(sr[k])
    frames={k:np.asarray(v) for k,v in frames.items()}
    src={k:np.asarray(v) for k,v in src.items()}
    valid=frames["valid_sub"]&np.isfinite(src["r_sub"])&np.isfinite(src["s0"])&np.isfinite(src["ds1"])
    features=np.stack([O.bias_features(case,x,spec) for x in gt])
    must(np.isfinite(features).all() and valid.sum()>=.95*n,
         "ERR_SOURCE_OBSERVATION_COVERAGE "+case+" "+str(valid.sum()))
    return dict(case=case,route=case[:2],n=n,full=frames,los=src,valid=valid,
       features=features,gt=gt,anchor=spec,full_H_sha=assets[name]["sha256"],
       samples_sha=assets[nameS]["sha256"])
def fit_train(data):
    """All fits on SOURCE ROUTES ONLY. Covariance is deterministic Full-LoS effective model error."""
    F=np.concatenate([c["features"][c["valid"]] for c in data])
    Y=np.concatenate([(c["full"]["r_sub"]-c["los"]["r_sub"])[c["valid"]] for c in data])
    fit=O.fit_bias(F,Y,alpha=1.)
    rf=O.predict_bias # test uses prior only
    w=np.c_[np.ones(len(F)),(F[:,1:]-fit["center"])/fit["scale"]]
    E_r=Y-w@fit["coeff"]
    Es=np.concatenate([(c["full"]["s0"]-c["los"]["s0"])[c["valid"]] for c in data])
    Ed=np.concatenate([(c["full"]["ds1"]-c["los"]["ds1"])[c["valid"]] for c in data])
    means=np.array([0.,float(Es.mean()),float(Ed.mean())])
    E=np.column_stack([E_r,Es-means[1],Ed-means[2]])
    margin=np.concatenate([c["full"]["margin"][c["valid"]] for c in data])
    q=np.array([O.quality_bin(v) for v in margin])
    cov=O.fit_covariance(E,q,shrink=.15)
    delta=np.concatenate([(c["full"]["tap"]-c["los"]["tap"])[c["valid"]] for c in data]).astype(int)
    categorical=O.fit_categorical(delta,q)
    must(len(F)>2000 and np.isfinite(E).all(),"ERR_NOT_ENOUGH_SOURCE_TRAIN")
    return dict(bias=fit,means=means,cov=cov,categorical=categorical,
       n_train=len(F),source_cases=[c["case"] for c in data],
       source_routes=sorted(set(c["route"] for c in data)),
       residual_rms=np.sqrt(np.mean(E**2,axis=0)))
def train_details(model):
    return dict(n_train=model["n_train"],source_cases=model["source_cases"],
       source_routes=model["source_routes"],mean_s0=float(model["means"][1]),
       mean_ds1=float(model["means"][2]),
       bias_coefficient=np.asarray(model["bias"]["coeff"]).tolist(),
       bias_center=np.asarray(model["bias"]["center"]).tolist(),
       bias_scale=np.asarray(model["bias"]["scale"]).tolist(),
       residual_rms=np.asarray(model["residual_rms"]).tolist(),
       covariance={k:dict(n=int(v["n"]),R3=matrix_json(v["R3"]),R2=matrix_json(v["R2"]),
                          min_eig=v["eigen_min"],condition=v["condition"])
                   for k,v in model["cov"].items()},
       conditional_tap_class_probs=model["categorical"],
       statistic="FULL_MINUS_LOS_DETERMINISTIC_RF_RESIDUAL_NOT_HARDWARE_NOISE")
def local_update(x,P,v,H,R):
    """Independent Joseph update linear algebra, no use of scoring truth."""
    S=.5*(H@P@H.T+R+(H@P@H.T+R).T)
    eig=np.linalg.eigvalsh(S)
    must(eig[0]>0 and np.isfinite(eig).all(),"ERR_INNOV_NOT_PD "+str(eig))
    nu=float(v@np.linalg.solve(S,v))
    K=np.linalg.solve(S,H@P).T
    return nu,K
def run_online(*,t,z,quality,source_model,spec,case,cal,ds,gy,dt,x0,P0,base_mask,dim,gate):
    """No GT argument, source labels, original mu, or oracle data available."""
    must(dim in (2,3) and gate in ("BASE_FIXED","SELF_NIS"),"ERR_ARM")
    n=len(t);x=np.asarray(x0,float).copy();P=np.asarray(P0,float).copy()
    X=np.empty((n,4));PC=np.empty((n,4,4));mask=np.zeros(n,bool);logs=[]
    thresholds=O.CHI2
    for k in range(n):
        if k:
            q=np.diag([2e-5*abs(ds[k]),math.radians(.015)**2*dt[k],0.])
            x,P,_,_=A.predict(x,P,float(ds[k]),float(gy[k]),float(dt[k]),q)
        xpre=x.copy();Ppre=P.copy()
        zrow=z[k,:dim]
        qbin=O.quality_bin(quality["margin"][k])
        R=cal["cov"][qbin]["R2" if dim==2 else "R3"]
        reason="OK";accepted=False;value=float("nan");k_norm=float("nan")
        h=np.full(dim,np.nan);v=np.full(dim,np.nan)
        Kgain=np.full((4,dim),np.nan);expected_tap=None;expected_port=None
        is_source_valid=False
        doobs=(bool(base_mask[k]) if gate=="BASE_FIXED" else True)
        valid=bool(quality["valid_sub"][k]) and np.isfinite(zrow).all()
        if doobs and valid:
            try:
                hs,J,dg=O.source_jacobian(source_model,x,spec)
                expected_tap=int(dg["tap"]);expected_port=int(dg["port"])
                b,jb=O.predict_bias_jac(cal["bias"],case,x,spec)
                h=hs[:dim].copy();H=J[:dim].copy()
                h[0]+=b;H[0]+=jb
                h[1:]+=cal["means"][1:dim]
                is_source_valid=True
                v=zrow-h
                if not dg["smooth_active_branch"]:
                    reason="SOURCE_TAP_SWITCH_NEAR_PRIOR"
                elif int(quality["tap"][k])!=int(dg["tap"]):
                    # The LoS prediction and Full-H observation selected different
                    # discrete arrivals. The Gaussian model was calibrated only
                    # within a matching active tap; record as a mismatch stratum.
                    # Mixture likelihood is NOT calibrated in this P0 canary.
                    reason="OBSERVED_SOURCE_TAP_MISMATCH_BLOCKED"
                else:
                    value,K=local_update(x,P,v,H,R)
                    Kgain=K.copy()
                    if gate=="BASE_FIXED" or value<=thresholds[dim]:
                        y=x+K@v;y[2]=O.wrap(y[2])
                        AA=np.eye(4)-K@H
                        Pn=AA@P@AA.T+K@R@K.T
                        Pn=.5*(Pn+Pn.T)
                        ev=np.linalg.eigvalsh(Pn)
                        must(ev[0]>-1e-9,"ERR_P_NOT_PSD")
                        x=y;P=Pn;accepted=True;k_norm=float(np.linalg.norm(K))
                    else:reason="REJECT_SELF_NIS"
            except RuntimeError as e:
                if str(e).startswith(("ERR_LOS_FRACTIONAL_INVALID","ERR_FD_CROSSING_DISCONTINUITY")):
                    reason=str(e).split(" ",1)[0]
                else:raise
        elif not doobs:reason="REJECT_FIXED_MASK"
        elif not valid:reason="INVALID_NATIVE_FRACTIONAL"
        X[k]=x;PC[k]=P;mask[k]=accepted
        logs.append(dict(packet=k,t_s=float(t[k]),gate=gate,dim=dim,
            base_accept=bool(base_mask[k]),accepted=bool(accepted),reason=reason,
            r_observed_m=float(zrow[0]),s0_observed=float(zrow[1]),
            ds1_observed=float(zrow[2]) if dim==3 else None,
            r_pred_m=float(h[0]),s0_pred=float(h[1]),
            ds1_pred=float(h[2]) if dim==3 else None,
            innovation_r_m=float(v[0]),innovation_s=float(v[1]),
            innovation_ds1=float(v[2]) if dim==3 else None,
            qbin=qbin,tap_observed=int(quality["tap"][k]),
            port_observed=int(quality["port"][k]),tap_margin=float(quality["margin"][k]),
            NIS=value,threshold=thresholds[dim],K_fro=k_norm,
            K_matrix=Kgain.tolist(),R_matrix=np.asarray(R).tolist(),
            rho_prior_m=float(math.hypot(xpre[0]-spec["anchor"][0],xpre[1]-spec["anchor"][1])),
            sigma_b_used=None,source_predicted_tap=expected_tap,
            source_predicted_strong_port=expected_port,
            observed_vs_source_predicted_tap_delta=(int(quality["tap"][k])-expected_tap if expected_tap is not None else None),
            R_rr=float(R[0,0]),R_rs=float(R[0,1]),
            R_rds=float(R[0,2]) if dim==3 else None,
            R_sds=float(R[1,2]) if dim==3 else None,
            prior_x=xpre.tolist(),prior_P=Ppre.tolist(),
            post_x=x.tolist(),post_P=P.tolist(),
            eligible_source_model=is_source_valid))
    return dict(X=X,P=PC,mask=mask,logs=logs)
def first_difference(D,fixed,self_,dim):
    ix=np.flatnonzero(fixed["mask"]!=self_["mask"])
    if not len(ix):return dict(status="NO_MASK_DIFFERENCE",dim=dim)
    k=int(ix[0])
    f=fixed["logs"][k];s=self_["logs"][k]
    parity=max(float(np.max(abs(np.array(f["prior_x"])-np.array(s["prior_x"])))),
        float(np.max(abs(np.array(f["prior_P"])-np.array(s["prior_P"])))))
    must(parity<1e-10,"ERR_FIRST_MASK_PRIOR_NOT_MATCHED "+str((k,parity)))
    return dict(status="FIRST_MASK_DIFFERENCE",packet=k,time_s=float(D["t"][k]),
       dim=dim,prior_parity_max=parity,
       fixed_accept=f["accepted"],self_accept=s["accepted"],
       fixed_NIS=f["NIS"],self_NIS=s["NIS"],
       post_x_max_gap=float(np.max(abs(fixed["X"][k]-self_["X"][k]))),
       post_P_max_gap=float(np.max(abs(fixed["P"][k]-self_["P"][k]))),
       cause="POLICY_DECISION_DIVERGENCE_WITH_SAME_PRE_UPDATE_PRIOR")
def scores(D,z,dim,gate,mode,level):
    a=A.E.scores(D,z["X"],z["P"])
    return dict(case=mode,gyro_level=level,dim=dim,gate=gate,
       head_rmse_deg=a["head_rmse"],xy_rmse_cm=a["xy_rmse_cm"],
       head_z_rms=a["head_z_rms"],xy_nees=a["nees_xy"],
       head_cov95=a["head_cov95"],xy_cov95=a["xy_cov95"],
       n_accepted=int(z["mask"].sum()),n_packets=len(z["mask"]),
       n_source_invalid=sum("SOURCE" in l["reason"] for l in z["logs"]),
       n_native_invalid=sum(l["reason"]=="INVALID_NATIVE_FRACTIONAL" for l in z["logs"]),
       n_tap_mismatch_blocked=sum(l["reason"]=="OBSERVED_SOURCE_TAP_MISMATCH_BLOCKED" for l in z["logs"]),
       n_source_switch_blocked=sum(l["reason"]=="SOURCE_TAP_SWITCH_NEAR_PRIOR" for l in z["logs"]),
       n_nis_finite=sum(np.isfinite(l["NIS"]) for l in z["logs"]))
def validate_negative_controls(cal,source_model,case,spec):
    # Off-diagonal R cannot be represented as a product of independent scalars.
    R=cal["cov"]["STABLE"]["R3"];H=np.array([[.7,.4,0,0],[0,0,1.4,.03],[0,0,-.5,0.]])
    T=np.array([[1.,0.,0.],[0.,1.,0.],[0.,1.,1.]])
    R2=T@R@T.T;H2=T@H
    info=H.T@np.linalg.solve(R,H)
    info2=H2.T@np.linalg.solve(R2,H2)
    must(np.max(abs(info-info2))<1e-8,"ERR_INFORMATION_BASIS_PARITY")
    # Deliberate duplicated scalar observation: covariance is rank deficient.
    Z=np.array([[1.,0.],[0.,1.],[0.,1.]])
    Rd=Z@R[:2,:2]@Z.T
    must(np.linalg.matrix_rank(Rd)==2,"ERR_DUPLICATE_SHOULD_BE_SINGULAR")
    # Bias prediction must be independent of any GT array or packet-keyed old mu.
    x=np.array([4.,1.,.3,0.])
    before=O.predict_bias(cal["bias"],case,x,spec)
    after=O.predict_bias(cal["bias"],case,x.copy(),spec)
    must(before==after,"ERR_NONDETERMINISTIC_BIAS")
    return dict(info_basis_max_abs=float(np.max(abs(info-info2))),
       duplicate_cov_rank=int(np.linalg.matrix_rank(Rd)),
       train_only_bias_function=True,passed=True)
def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    root=pathlib.Path(args.rf_root);source_sha=pathlib.Path(args.input_manifest)
    lock=json.loads(source_sha.read_text())
    assets={x["path"]:x for x in lock["assets"] if x.get("sha256")}
    f=root/"freqs_hz.npy"
    match=next(a for a in assets if a.endswith("/freqs_hz.npy"))
    must(sha(f)==assets[match]["sha256"],"ERR_FREQ_SHA")
    freq=np.load(f,allow_pickle=False)
    must(len(freq)==257 and abs(float(freq[1]-freq[0])-1.95e6)<1.,"ERR_FREQ_GRID")
    model=A.C.base_model()
    source=[load_source(c,root,assets,freq,model) for c in CASES]
    test=next(c for c in source if c["case"]==args.case)
    train=[c for c in source if c["route"]!=test["route"]]
    must(len(train)>=4 and all(c["route"]!=test["route"] for c in train),"ERR_TRAIN_LEAK")
    fitted=fit_train(train)
    negative=validate_negative_controls(fitted,model,args.case,A.C.CASES[args.case])
    spec=A.C.CASES[args.case]
    D,mus=A.make_D(args.case,args.level,model)
    must(len(D["z"])==test["n"],"ERR_CTRL_H_POSE_ALIGN")
    f0=test["full"]
    dr=float(np.max(abs(f0["r_int"]-D["z"][:,0])))
    ds0=float(np.max(abs(f0["s0"]-D["z"][:,1])))
    must(dr<=1e-9 and ds0<=1e-12,"ERR_OLD_PACKET_REPLAY "+str((dr,ds0)))
    # independent baseline from exp_pb/E.run, full state and covariance, not scores only
    official=A.E.run(D,mus["BB"],{"mode":"orig"},model)
    replay=A.run_arm(D,mus["BB"],model,"NONE","BASE_FIXED")
    xdiff=float(np.max(abs(replay[0]-official[0])))
    pdiff=float(np.max(abs(replay[1]-official[1])))
    must(max(xdiff,pdiff)<=1e-10 and np.array_equal(replay[2],D["acc"]),
         "ERR_BASE_BB_ORIG_FULL_PARITY "+str((xdiff,pdiff)))
    ref_score=A.E.scores(D,replay[0],replay[1])
    z=np.column_stack([f0["r_sub"],f0["s0"],f0["ds1"]])
    q=f0
    runs={};result=[];first=[]
    for dim in (2,3):
        for gate in ("BASE_FIXED","SELF_NIS"):
            zrun=run_online(t=D["t"],z=z,quality=q,source_model=model,spec=spec,
                case=args.case,cal=fitted,ds=D["ds"],gy=D["gy"],dt=D["dt"],
                x0=D["x0"],P0=D["P0"],base_mask=D["acc"],dim=dim,gate=gate)
            runs[(dim,gate)]=zrun
            result.append(scores(D,zrun,dim,gate,args.case,args.level))
            print("RA5_NEW_ARM "+json.dumps(result[-1],default=native_json),flush=True)
        first.append(first_difference(D,runs[(dim,"BASE_FIXED")],runs[(dim,"SELF_NIS")],dim))
    refrow=dict(case=args.case,gyro_level=args.level,dim=2,gate="BASE_FIXED",arm="BB_ORIG_NATIVE",head_rmse_deg=ref_score["head_rmse"],
       xy_rmse_cm=ref_score["xy_rmse_cm"],head_z_rms=ref_score["head_z_rms"],xy_nees=ref_score["nees_xy"],
       head_cov95=ref_score["head_cov95"],xy_cov95=ref_score["xy_cov95"],
       n_accepted=int(D["acc"].sum()),n_packets=len(D["t"]))
    result.append(refrow)
    labels=[]
    for k in range(len(D["t"])):
        edge=O.quality_bin(q["margin"][k])
        # Test label uses Full-H true-Los matched pose; category is NOT passed to inference
        label=O.class_delta(int(q["tap"][k]-test["los"]["tap"][k]))
        probs=fitted["categorical"][edge]["p"]
        labels.append(dict(case=args.case,k=k,quality=edge,
             source_true_class_SCORING_ONLY=label,train_prob_observed_class=probs[label],
             prior_mismatch_class_NOT_A_MODEL_FIT="",
             predicted_clean_prob=probs["0"],source_tap=int(test["los"]["tap"][k]),
             observed_tap=int(q["tap"][k])))
    must(all(0<p["train_prob_observed_class"]<=1 for p in labels),"ERR_CATEGORICAL_PROB")
    write_csv(out/"RA5_ONLINE_P0_SCORES.csv",result)
    write_csv(out/"RA5_ONLINE_P0_FIRST_FLIPS.csv",first)
    write_csv(out/"RA5_ONLINE_P0_TAP_CATEGORICAL.csv",labels)
    for key,run in runs.items():
        write_csv(out/("RA5_ONLINE_P0_TRACE_"+str(key[0])+"_"+key[1]+".csv"),run["logs"])
    detail=train_details(fitted)
    (out/"RA5_TRAIN_MODEL.json").write_text(json.dumps(detail,indent=2,default=native_json)+"\n")
    qa=dict(status="PASS_RA5_P0_IMPLEMENTER_TECHNICAL_REPLAY",
       contract_status="DRAFT_NOT_FROZEN",role="IMPLEMENTER",
       case=args.case,level=args.level,source_commit=ORIGINAL_SHA,
       governance_git_sha="250d617ad89a4105fa1af546cc83ceed9de98f42",
       source_H_sha256=test["full_H_sha"],samples_sha256=test["samples_sha"],
       train_routes=fitted["source_routes"],held_route=test["route"],
       n_train_rows=fitted["n_train"],n_test_packets=len(D["t"]),
       native_source_max_r=dr,native_source_max_s=ds0,
       full_baseline_state_max=xdiff,full_baseline_cov_max=pdiff,
       full_baseline_mask_parity=True,
       n_comparison_arms=len(result),n_gate_pairs=len(first),
       failed_source_model_updates=sum(r["n_source_invalid"] for r in result),
       native_invalid_updates=sum(r["n_native_invalid"] for r in result),
       first_flip_status=[r["status"] for r in first],
       negative_controls=negative,
       covariance_kind="TRAIN_ONLY_DETERMINISTIC_FULL_MINUS_LOS_MODEL_ERROR",
       categorical_kind="TRAIN_ONLY_FULL_MINUS_LOS_TAP_CLASS_CONDITIONAL_ON_OBSERVED_EDGE_MARGIN",
       source_true_pose_in_filter=False,source_true_pose_used_for_train=True,
       source_true_pose_used_to_score_after_filter=True,
       no_new_RT=True,independent_Rf_scenes=1,
       no_scientific_calibration_claim=True,independent_auditor=False,
       created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_ONLINE_P0_QA.json").write_text(json.dumps(qa,indent=2,default=native_json)+"\n")
    print("RA5_ONLINE_P0_FINAL "+json.dumps(qa,default=native_json),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--rf-root",required=True)
    ap.add_argument("--input-manifest",required=True)
    ap.add_argument("--case",choices=CASES,required=True)
    ap.add_argument("--level",choices=A.LEVELS,default="B0")
    ap.add_argument("--out",required=True)
    args=ap.parse_args();main(args)
