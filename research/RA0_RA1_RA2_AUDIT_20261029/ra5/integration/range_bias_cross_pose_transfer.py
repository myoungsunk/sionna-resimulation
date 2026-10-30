#!/usr/bin/env python3
"""RA5 A/B cross-pose train-only calibration transfer (no RT).
Test observation generated on heldout original pose, but nuisance mean/bias model
calibrated ONLY on a different source pose. Known geometry used as synthetic
truth conditioner, NOT online test-prior input. No learned target bias.
"""
import argparse,csv,datetime,hashlib,json,math,pathlib
import numpy as np
from raw_tap_covariance import make_cir,extract
from range_likelihood_three_way import generate, fractional_edge,TRAIN_D,TEST_D,seed_for,CFR_SNR

C0=299792458.
def must(v,msg):
    if not v:raise RuntimeError(msg)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def score(a,truth):
    ok=np.isfinite(a)
    if not ok.sum():return dict(valid=0,rmse_m=None,bias_m=None)
    e=np.asarray(a)[ok]-truth[ok]
    return dict(valid=int(ok.sum()),rmse_m=float(np.sqrt(np.mean(e*e))),bias_m=float(np.mean(e)))
def dump(p,rows):
    keys=list(rows[0])
    with p.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def observed(H,freq,delta,n,snr,jit,seed):
    Y=generate(H,freq,delta,n,snr,.3,jit,seed)
    ri,rs,tap,port,ok,_=fractional_edge(make_cir(Y),float(freq[1]-freq[0]))
    return ri,rs,tap,ok
def geom(s,anchor):
    return float(math.hypot(math.hypot(float(s["x"])-anchor[0],float(s["y"])-anchor[1]),2.2))
def main(args):
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    root=pathlib.Path(args.source)
    manifest=json.loads(pathlib.Path(args.lock).read_text())
    case=args.case
    Hfile=root/("H_"+case+".npy");freqfile=root/"freqs_hz.npy"
    smpl=root/("SAMPLES_"+case+".json")
    must(sha(Hfile)==manifest["H_sha256"] and sha(freqfile)==manifest["freq_sha256"],"ERR_H_FREQ_SOURCE")
    must(sha(smpl)==manifest["samples_sha256"],"ERR_SAMPLES_SOURCE")
    H=np.load(Hfile,mmap_mode="r",allow_pickle=False);freq=np.load(freqfile,allow_pickle=False)
    samples=json.loads(smpl.read_text())
    poses=[int(i) for i in args.poses.split(",")]
    must(len(poses)==2 and len(set(poses))==2 and all(0<=p<len(H) for p in poses),"ERR_POSE_IDS")
    anchor=(4.,0.) if "aA" in case else (10.,0.)
    gg={p:geom(samples[p],anchor) for p in poses}
    print("RA5_TRANSFER_GEOMETRY "+json.dumps({str(p):gg[p] for p in poses}),flush=True)
    rows=[];checks=[]
    for idx,train_pose in enumerate(poses):
        test_pose=poses[1-idx]
        ht=np.asarray(H[train_pose,:,:,0],complex)
        he=np.asarray(H[test_pose,:,:,0],complex)
        for snr in (5.,20.):
            for jit in (0.,150.):
                tr_ri=[];tr_rs=[];tr_delta=[]
                for j,d in enumerate(TRAIN_D):
                    ri,rs,_,ok=observed(ht,freq,float(d),args.train,snr,jit,seed_for("XPOSE",case,train_pose,snr,jit,j,"train"))
                    tr_ri.append(ri);tr_rs.append(rs)
                    tr_delta.append(np.full(args.train,d))
                tr_r=np.concatenate(tr_ri);tr_s=np.concatenate(tr_rs);truth=np.concatenate(tr_delta)
                ri_bias=float(np.mean(tr_r-truth-gg[train_pose]))
                su=np.isfinite(tr_s);must(su.sum()>=.95*len(su),"ERR_TRAIN_SUBINVALID")
                rs_bias=float(np.mean(tr_s[su]-truth[su]-gg[train_pose]))
                ri_sd=float(np.std(tr_r-truth-gg[train_pose]-ri_bias,ddof=1))
                rs_sd=float(np.std(tr_s[su]-truth[su]-gg[train_pose]-rs_bias,ddof=1))
                # Heldout absolute receiver range requires only the declared geometric truth
                # in this scoring probe; in an EKF h_r would be evaluated at a prior estimate.
                test1=[];test2=[];testtruth=[]
                for j,d in enumerate(TEST_D):
                    ri,rs,_,_=observed(he,freq,float(d),args.test,snr,jit,seed_for("XPOSE",case,test_pose,snr,jit,j,"test"))
                    test1.append(ri);test2.append(rs);testtruth.append(np.full(args.test,d))
                z1=np.concatenate(test1);z2=np.concatenate(test2);zt=np.concatenate(testtruth)
                models=[("B_INTEGER_BIAS_TRANSFER",z1-ri_bias-gg[test_pose],ri_sd),
                        ("A_SUBTAP_BIAS_TRANSFER",z2-rs_bias-gg[test_pose],rs_sd)]
                for arm,estimate,sd in models:
                    met=score(estimate,zt)
                    valid=np.isfinite(estimate)
                    e=estimate[valid]-zt[valid]
                    coverage=float(np.mean(abs(e)<=1.96*sd)) if np.any(valid) else None
                    rows.append(dict(case=case,train_pose=train_pose,test_pose=test_pose,
                         snr_db=snr,jitter_ps=jit,arm=arm,n_train=len(truth),
                         n_test=len(zt),n_valid=met["valid"],rmse_m=met["rmse_m"],
                         bias_m=met["bias_m"],coverage95=coverage,
                         source_bias_m=ri_bias if arm.startswith("B_") else rs_bias,
                         source_sd_m=sd,
                         geometry_train_m=gg[train_pose],geometry_test_m=gg[test_pose],
                         provenance="TEST_POSE_H_USED_ONLY_TO_SIMULATE_OBSERVATION_NOT_FOR_CALIBRATION",
                         statistical_unit="FIXED_ORIGINAL_POSE_PAIR_NOT_INDEPENDENT_SCENE"))
                checks.append(dict(case=case,train_pose=train_pose,test_pose=test_pose,
                    snr_db=snr,jitter_ps=jit,source_integer_bias_m=ri_bias,
                    source_subtap_bias_m=rs_bias,source_integer_sd_m=ri_sd,
                    source_subtap_sd_m=rs_sd))
                print("RA5_TRANSFER_CELL "+json.dumps(rows[-2:]),flush=True)
    must(len(rows)==16,"ERR_N_RESULT")
    dump(out/"RA5_RANGE_TRANSFER_SCORES.csv",rows)
    dump(out/"RA5_RANGE_TRANSFER_SOURCE_BIASES.csv",checks)
    qa=dict(status="PASS_CROSSPOSE_CALIBRATION_TRANSFER_PROBE",case=case,poses=poses,
       n_comparisons=len(rows),n_source_test_strata=len(checks),
       test_snr=[5,20],test_jitter_ps=[0,150],
       source_H_SHA256=manifest["H_sha256"],source_samples_sha256=manifest["samples_sha256"],
       source_calibration_train_only=True,pose_group_heldout=True,
       truth_geometry_in_test="SCORING_DIAGNOSTIC_ONLY_NOT_FILTER_INPUT",
       site_independent=False,physical_motion=False,RT_calls=0,
       independent_auditor=False,science_release=False,
       utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_TRANSFER_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_TRANSFER_FINAL "+json.dumps(qa),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--case",required=True);ap.add_argument("--poses",required=True)
    ap.add_argument("--source",required=True);ap.add_argument("--lock",required=True)
    ap.add_argument("--train",type=int,default=128);ap.add_argument("--test",type=int,default=192)
    ap.add_argument("--out",required=True)
    a=ap.parse_args();main(a)
