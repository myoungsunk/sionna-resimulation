#!/usr/bin/env python3
"""RA5 source H 7-case LORO read-only deterministic distance bias validation.
Compare old integer-leading-edge, fractional crossing + simple train-only
distance/geometry mean bias correction. Ground-truth pose used to construct
teacher labels and OFFLINE features: not online deployment or sensor R.
"""
from __future__ import annotations
import argparse,csv,datetime,hashlib,json,math,pathlib,sys
import numpy as np
from raw_tap_covariance import make_cir
from range_likelihood_three_way import fractional_edge,C0

CASES=("R2_aA_m0","R2_aB_m0","R2_aA_m45","R4_aA_m0","R4_aB_m0","R5_aA_m0","R5_aB_m0")
ROUTES=("R2","R4","R5")
EXP_N={"R2":979,"R4":742,"R5":1415}
def require(x,m):
    if not x:raise RuntimeError(m)
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def csv_out(p,r):
    fields=list(r[0]);withopen=p.open("w",newline="")
    with withopen as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(r)
def sample_features(case,x,y,yaw):
    ax=4. if "aA" in case else 10.
    gx=x-ax;gy=y;rho=np.hypot(gx,gy)
    d=np.sqrt(rho*rho+2.2**2)
    psi=np.deg2rad(yaw+(45. if "m45" in case else 0.))
    bearing=np.arctan2(-gy,-gx)
    angle=psi-bearing
    # NO angles or positions from test should enter an online predictor unless derived from the
    # prior state; this analysis uses GT ONLY for conditional model error audit.
    v=np.column_stack([np.ones(len(x)),d,np.sin(angle),np.cos(angle),
                       np.sin(2*angle),np.cos(2*angle),
                       np.full(len(x),int("m45" in case)),
                       np.full(len(x),int("aB" in case))])
    return d,v
def ridge_train(X,y,sel,alpha=1.):
    require(len(X)==len(y) and len(y)>=500,"ERR_TRAIN_ROWS")
    F=X[:,sel];center=F[:,1:].mean(axis=0);scale=np.maximum(F[:,1:].std(axis=0),1e-12)
    W=np.c_[np.ones(len(F)),(F[:,1:]-center)/scale]
    G=W.T@W+np.diag(np.r_[0.,np.repeat(alpha,W.shape[1]-1)])
    theta=np.linalg.solve(G,W.T@y)
    return center,scale,theta
def ridge_predict(X,sel,model):
    c,s,th=model;F=X[:,sel];W=np.c_[np.ones(len(F)),(F[:,1:]-c)/s]
    return W@th
def load_case(root,case,freq,assets,src):
    h=root/("H_"+case+".npy");p=root/("SAMPLES_"+case+".json")
    mustH=next(a for a in assets if a.endswith("FULL_RF/H_"+case+".npy"))
    mustS=next(a for a in assets if a.endswith(case+"/SAMPLES.json"))
    require(sha(h)==assets[mustH]["sha256"] and sha(p)==assets[mustS]["sha256"],"ERR_SOURCE_H_SAMPLES "+case)
    H=np.load(h,mmap_mode="r",allow_pickle=False)
    samples=json.loads(p.read_text())
    n=EXP_N[case[:2]]
    require(len(samples)==len(H) and len(H)>=n,"ERR_POSE_COUNT")
    x=np.array([s["x"] for s in samples[:n]],float)
    y=np.array([s["y"] for s in samples[:n]],float)
    yaw=np.array([s["yaw_body_deg"] for s in samples[:n]],float)
    d,feat=sample_features(case,x,y,yaw)
    intR=[];subR=[];tap_valid=[]
    df=float(freq[1]-freq[0])
    for st in range(0,n,64):
        C=make_cir(np.asarray(H[st:min(st+64,n),:,:,0]))
        ri,rs,_,_,vsub,vraw=fractional_edge(C,df)
        intR.extend(ri);subR.extend(rs);tap_valid.extend(vsub)
    ri=np.array(intR);rs=np.array(subR)
    require(np.isfinite(ri).all() and np.mean(np.isfinite(rs))>.97,"ERR_INVALID_OBSERVATION "+case)
    return dict(route=case[:2],case=case,n=n,features=feat,d=d,r_int=ri,r_sub=rs,tapvalid=np.asarray(tap_valid),
        source_original_H_sha256=assets[mustH]["sha256"],src_commit=src)

def main(args):
    root=pathlib.Path(args.source);out=pathlib.Path(args.out);out.mkdir(exist_ok=True,parents=True)
    manifest=json.loads(pathlib.Path(args.input_manifest).read_text())
    assets={p["path"]:p for p in manifest["assets"] if p.get("sha256")}
    f=root/"freqs_hz.npy";match=next(k for k in assets if k.endswith("/freqs_hz.npy"))
    require(sha(f)==assets[match]["sha256"],"ERR_FREQUENCY_SHA")
    freq=np.load(f,allow_pickle=False)
    source=[load_case(root,c,freq,assets,manifest.get("base_commit")) for c in CASES]
    inputs=[dict(case=c["case"],n=c["n"],H_sha=c["source_original_H_sha256"],
       n_valid_subtap=int(c["tapvalid"].sum()),valid_fraction=float(c["tapvalid"].mean())) for c in source]
    tests=[];folds=[]
    # 1) Free scalar prior bias, 2) linear range, 3) geometry-dependent yaw and mount/anchor effects.
    models={"CONSTANT":[0],"RANGE":[0,1],"GEOMETRY":[0,1,2,3,4,5,6,7]}
    for held in ROUTES:
        train=[a for a in source if a["route"]!=held]
        test=[a for a in source if a["route"]==held]
        require(train and test,"ERR_ZERO_HOLDOUT")
        for modality in ("INT","SUB"):
            tr_f=[];tr_err=[]
            for c in train:
                obs=c["r_int"] if modality=="INT" else c["r_sub"]
                valid=np.isfinite(obs)
                tr_f.append(c["features"][valid]);tr_err.append((obs-c["d"])[valid])
            Xt=np.concatenate(tr_f);yt=np.concatenate(tr_err)
            for model_name,selected in models.items():
                fitted=ridge_train(Xt,yt,selected,alpha=1.)
                for c in test:
                    obs=c["r_int"] if modality=="INT" else c["r_sub"]
                    valid=np.isfinite(obs);d=c["d"]
                    pred=ridge_predict(c["features"],selected,fitted)
                    before=obs[valid]-d[valid]
                    err=obs[valid]-pred[valid]-d[valid]
                    tests.append(dict(held_route=held,case=c["case"],modality=modality,
                       bias_model=model_name,n_train=len(yt),n_test=len(obs),n_valid=int(valid.sum()),
                       rmse_uncalibrated_m=float(np.sqrt(np.mean(before**2))),
                       rmse_after_m=float(np.sqrt(np.mean(err**2))),
                       mean_error_after_m=float(np.mean(err)),median_abs_error_after_m=float(np.median(abs(err))),
                       ninety_fifth_abs_error_m=float(np.quantile(abs(err),.95)),
                       train_pose_truth_only=True,test_pose_truth_only=True,
                       independent_scene=False,
                       source_data="ORIGINAL_SAVED_FULL_H_NO_RECEIVER_NOISE"))
                folds.append(dict(held_route=held,modality=modality,bias_model=model_name,
                   n_train=len(yt),n_test=sum(c["n"] for c in test),
                   coef_intercept=float(fitted[2][0]),number_of_coefficients=len(fitted[2])))
    require(len(tests)==(3*(3+2+2)*2),"ERR_EXPECTED_SCORE_ROWS "+str(len(tests)))
    csv_out(out/"RA5_RANGE_LORO_CASE_SCORES.csv",tests)
    csv_out(out/"RA5_RANGE_LORO_FOLDS.csv",folds)
    csv_out(out/"RA5_RANGE_LORO_SOURCE.csv",inputs)
    qa=dict(status="PASS_SEVEN_CASE_RETROSPECTIVE_LORO_DISTANCE_BIAS_DIAGNOSTIC",
        cases=list(CASES),routes=list(ROUTES),
        n_full_h_pose_rows=sum(c["n"] for c in source),
        n_model_scores=len(tests),n_source_cases=7,
        original_H_unchanged=True,train_label_leakage=False,
        truth_pose_as_online_input="YES_OFFLINE_ONLY_NOT_DEPLOYABLE",
        receiver_noise_mc="NOT_IN_THIS_FOLD",probabilistic_R_calibration="NOT_DONE",
        physical_generalization="NOT_TESTED",independent_scene_count=1,rt_calls=0,
        independent_auditor=False,science_release=False,
        utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_RANGE_LORO_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_RANGE_LORO_FINAL "+json.dumps(qa),flush=True)
    for x in tests:
        if x["bias_model"] in ("CONSTANT","GEOMETRY"):
            print("RA5_RANGE_LORO_CASE "+json.dumps({k:x[k] for k in ("held_route","case","modality","bias_model","rmse_after_m","mean_error_after_m")}),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--source",required=True);ap.add_argument("--input-manifest",required=True)
    ap.add_argument("--out",required=True);a=ap.parse_args();main(a)
