#!/usr/bin/env python3
"""RA5 P2 read-only source-locked fitted joint R diagnostic WITHOUT any EKF run.

Train one Corridor route-block fold, hold the other out for source-model residual
verification and covariance calibration *diagnosis*. The covariance is
deterministic Full-minus-LoS RF error, NOT calibrated receiver stochastic R.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,pathlib,sys
import numpy as np
import run_prior_joint_canary as F
import online_observer as O

def assert_ok(x,m):
    if not x:raise RuntimeError(m)
def filehash(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for data in iter(lambda:f.read(1<<20),b""):h.update(data)
    return h.hexdigest()
def csvwrite(path,rows):
    with open(path,"w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    root=pathlib.Path(args.rf_root);source=json.loads(pathlib.Path(args.input_manifest).read_text())
    assets={x["path"]:x for x in source["assets"] if x.get("sha256")}
    ff=root/"freqs_hz.npy"
    key=next(x for x in assets if x.endswith("/freqs_hz.npy"))
    assert_ok(filehash(ff)==assets[key]["sha256"],"ERR_FREQ_HASH")
    fr=np.load(ff,allow_pickle=False)
    model=F.A.C.base_model()
    sources=[F.load_source(c,root,assets,fr,model) for c in F.CASES]
    held=args.held_route
    train=[c for c in sources if c["route"]!=held]
    test=[c for c in sources if c["route"]==held]
    assert_ok(len(train)>2 and len(test)>0 and len(set(c["route"] for c in train))==2,"ERR_FOLD")
    fitted=F.fit_train(train)
    R3=fitted["cov"]
    rows=[]
    for quality in ("AMBIG","STABLE"):
        r=R3[quality]["R3"]
        r2=R3[quality]["R2"]
        det=float(np.linalg.det(r))
        eig=np.linalg.eigvalsh(r)
        T=np.array([[1.,0.,0.],[0.,1.,0.],[0.,1.,1.]])
        Rraw=T@r@T.T
        Rback=np.linalg.solve(T,np.linalg.solve(T,Rraw.T).T)
        # Schur complement of second adjacent feature given r,s0.
        cond=float(r[2,2]-r[2,:2]@np.linalg.solve(r[:2,:2],r[:2,2]))
        assert_ok(eig.min()>1e-10 and cond>1e-10 and np.max(abs(Rback-r))<1e-12,
            "ERR_RANK_COV_TRANSFORM_"+quality)
        rows.append(dict(held_route=held,quality=quality,n_train_quality=fitted["cov"][quality]["n"],
             r_rr_m2=float(r[0,0]),r_s0=float(r[0,1]),r_ds=float(r[0,2]),
             s0_s0=float(r[1,1]),s0_ds=float(r[1,2]),ds_ds=float(r[2,2]),
             det3=det,eigen_min=float(eig.min()),condition_number=float(np.linalg.cond(r)),
             schur_ds_given_r_s0=cond,
             exact_basis_maxabs=float(np.max(abs(Rback-r))),
             source_cov_type="TRAIN_ONLY_FULL_MINUS_LOS_DETERMINISTIC_MODEL_DISCREPANCY"))
    valid=[];true=[];pred=[];quality=[]
    for c in test:
        m=c["valid"]
        x=c["gt"][m];fx=c["features"][m]
        z=c["full"];los=c["los"]
        # Evaluation of mean/residual uses true pose strictly OFFLINE to audit
        # calibrated residual spread; this is not an online filter.
        bias=np.array([O.predict_bias(fitted["bias"],c["case"],q,c["anchor"]) for q in x])
        E=np.column_stack([
           (z["r_sub"]-los["r_sub"])[m]-bias,
           (z["s0"]-los["s0"])[m]-fitted["means"][1],
           (z["ds1"]-los["ds1"])[m]-fitted["means"][2]])
        true.extend(E);quality.extend(O.quality_bin(v) for v in z["margin"][m])
        valid.append(dict(case=c["case"],n=len(E),mean_r_m=float(E[:,0].mean()),
             rms_r_m=float(np.sqrt(np.mean(E[:,0]**2))),
             mean_s=float(E[:,1].mean()),rms_s=float(np.sqrt(np.mean(E[:,1]**2))),
             mean_ds=float(E[:,2].mean()),rms_ds=float(np.sqrt(np.mean(E[:,2]**2)))))
    tr=np.asarray(true,float);q=np.asarray(quality)
    assert_ok(np.isfinite(tr).all() and len(tr)>500,"ERR_TEST_DATA")
    for qq in ("AMBIG","STABLE"):
        m=(q==qq)
        if m.sum()<20:continue
        C=R3[qq]["R3"]
        sq=np.sum(tr[m]*np.linalg.solve(C,tr[m].T).T,axis=1)
        vals=dict(held_route=held,quality=qq,n_test=int(m.sum()),
             mean_NIS3=float(sq.mean()),empirical_3d_95pct=float(np.mean(sq<=7.814727903251179)),
             expected_mean_NIS3=3.,source_noise="DETERMINISTIC_MODEL_ERROR_NOT_WHITE",
             not_approved_for_filter=True)
        rows.append(dict(held_route=held,quality=qq,n_train_quality=fitted["cov"][qq]["n"],
             r_rr_m2=None,r_s0=None,r_ds=None,s0_s0=None,s0_ds=None,ds_ds=None,
             det3=None,eigen_min=None,condition_number=None,schur_ds_given_r_s0=None,
             exact_basis_maxabs=None,source_cov_type="HELDOUT_CONDITIONAL_MAHALANOBIS_DIAGNOSTIC",
             **{k:vals[k] for k in ("n_test","mean_NIS3","empirical_3d_95pct")}))
        print("RA5_P2_HELD_QA "+json.dumps(vals),flush=True)
    csvwrite(out/"RA5_P2_COVARIANCE_AND_HELDOUT.csv",rows)
    csvwrite(out/"RA5_P2_CASE_TEST_MODEL_RESIDUAL.csv",valid)
    model_rec=F.train_details(fitted)
    (out/"RA5_P2_SOURCE_MODEL.json").write_text(json.dumps(model_rec,indent=2,default=F.native_json)+"\n")
    qa=dict(status="PASS_RA5_P2_SOURCE_COVARIANCE_ALGEBRA_AND_HELDOUT_DIAG",
      held_route=held,train_routes=fitted["source_routes"],n_train=fitted["n_train"],
      n_test=sum(x["n"] for x in valid),n_valid_source_cases=len(test),n_total_source_cases=len(sources),
      R3_all_quality_PSD=True,posterior_filter_recursion="NOT_RUN_IN_THIS_JOB",
      independent_scene_count=1,hardware_noise_calibrated=False,
      original_data_mutated=False,new_RT_calls=0,
      role="IMPLEMENTER",independent_auditor=False,science_release=False,
      utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_P2_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_P2_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--rf-root",required=True);p.add_argument("--input-manifest",required=True)
    p.add_argument("--held-route",required=True,choices=("R2","R4","R5"))
    p.add_argument("--out",required=True)
    args=p.parse_args();main(args)
