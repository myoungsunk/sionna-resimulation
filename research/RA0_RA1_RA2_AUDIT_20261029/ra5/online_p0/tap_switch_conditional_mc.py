#!/usr/bin/env python3
"""RA5 P0 separate detector-switch noise experiment.
Label is noisy tap != CLEAN Full-H tap, not Full-minus-LoS model discrepancy.
Fit p(switch|observed edge quality,SNR,jitter) on train poses; validate on
different poses. Clean Full H only for OFFLINE teacher labels / evaluation.
"""
import argparse,csv,datetime,hashlib,json,math,pathlib,sys
import numpy as np
HERE=pathlib.Path(__file__).resolve()
sys.path.insert(0,str(HERE.parents[1]/"integration"))
import raw_tap_covariance as RAW
import range_likelihood_three_way as R
import online_observer as O

def req(v,msg):
    if not v:raise RuntimeError(msg)
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for x in iter(lambda:f.read(1<<20),b""):h.update(x)
    return h.hexdigest()
def outcsv(path,rows):
    keys=list(rows[0])
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def get_rows(H,freq,case,pose,snr,jitter,draw,split):
    seed=int(hashlib.sha256((f"{case}|{pose}|{snr}|{jitter}|{split}|RA5-20261030").encode()).hexdigest()[:15],16)
    clean=O.observer(H[None],float(freq[1]-freq[0]))
    req(clean["valid_sub"][0],"ERR_CLEAN_TAP")
    Y=R.generate(H,freq,0.,draw,snr,.3,jitter,seed)
    observed=O.observer(Y,float(freq[1]-freq[0]))
    # Invalid and all switch labels remain in denominator. Missing margin -> AMBIG.
    rows=[]
    for k in range(draw):
        valid=bool(observed["valid_sub"][k])
        margin=float(observed["margin"][k])
        q=O.quality_bin(margin)
        rows.append(dict(case=case,pose_id=pose,snr_db=snr,jitter_ps=jitter,
          sensor_draw=k,partition=split,quality=q,edge_margin=margin,
          noisy_tap=int(observed["tap"][k]),
          teacher_clean_full_tap_SCORING_ONLY=int(clean["tap"][0]),
          tap_switch_label_SCORING_ONLY=int(observed["tap"][k]!=clean["tap"][0]),
          invalid_observation=int(not valid),source="SAVED_FULL_H_ASSUMED_COMPLEX_NOISE"))
    return rows
def probs(train):
    """Beta(0.5,0.5) smoothing, no test labels."""
    p={}
    for s in (-5.,5.,20.):
        for j in (0.,150.):
            group=[r for r in train if r["snr_db"]==s and r["jitter_ps"]==j]
            req(group,"ERR_EMPTY_REGIME")
            uncond=(.5+sum(r["tap_switch_label_SCORING_ONLY"] for r in group))/(1+len(group))
            for q in ("AMBIG","STABLE"):
                sub=[r for r in group if r["quality"]==q]
                conditional=(.5+sum(r["tap_switch_label_SCORING_ONLY"] for r in sub))/(1+len(sub))
                # If a quality bin is empty, report exact prior .5 not train-fitted precision.
                p[(s,j,q)]=dict(n_train=len(sub),switch_probability=conditional,
                                unconditional_reference=uncond)
    return p
def mean(values):return sum(values)/len(values)
def logloss(y,p):return -y*math.log(p)-(1-y)*math.log1p(-p)
def main(args):
    src=pathlib.Path(args.source);out=pathlib.Path(args.out);out.mkdir(exist_ok=True,parents=True)
    lock=json.loads(pathlib.Path(args.lock).read_text())
    req(sha(src/("H_"+args.case+".npy"))==lock["H_sha256"] and
        sha(src/"freqs_hz.npy")==lock["freq_sha256"],"ERR_SOURCE_SHA")
    h=np.load(src/("H_"+args.case+".npy"),mmap_mode="r",allow_pickle=False)
    f=np.load(src/"freqs_hz.npy",allow_pickle=False)
    ids=[int(x) for x in args.poses.split(",")]
    req(len(ids)==2 and len(set(ids))==2 and all(0<=i<len(h) for i in ids),"ERR_POSES")
    train=[];test=[]
    for idx,p in enumerate(ids):
        for s in (-5.,5.,20.):
            for j in (0.,150.):
                row=get_rows(np.asarray(h[p,:,:,0]),f,args.case,p,s,j,args.draw,
                             "TRAIN" if idx==0 else "TEST")
                (train if idx==0 else test).extend(row)
    req(len(train)==len(test)==args.draw*6,"ERR_DENOMINATORS")
    estimates=probs(train)
    output=[];raw=[]
    for key,info in estimates.items():
        s,j,q=key
        group=[r for r in test if (r["snr_db"],r["jitter_ps"],r["quality"])==key]
        for row in group:
            yy=row["tap_switch_label_SCORING_ONLY"]
            ps=info["switch_probability"];pu=info["unconditional_reference"]
            raw.append(dict(case=args.case,held_pose=ids[1],snr_db=s,jitter_ps=j,quality=q,
                            label_SCORING_ONLY=yy,predicted_switch=ps,
                            unconditional_train_ref=pu,invalid_observation=row["invalid_observation"]))
        if group:
            yp=[r["tap_switch_label_SCORING_ONLY"] for r in group]
            p=info["switch_probability"];u=info["unconditional_reference"]
            output.append(dict(case=args.case,train_pose=ids[0],test_pose=ids[1],
               snr_db=s,jitter_ps=j,quality=q,
               n_train_bin=info["n_train"],n_test_bin=len(group),
               empirical_switch_rate_test=mean(yp),
               predicted_switch_rate_train_only=p,
               brier_conditional=mean([(y-p)**2 for y in yp]),
               brier_unconditional=mean([(y-u)**2 for y in yp]),
               logloss_conditional=mean([logloss(y,p) for y in yp]),
               logloss_unconditional=mean([logloss(y,u) for y in yp]),
               independent_rf_scenes=1,calibration_mode="TRAIN_POSE_ONLY"))
    req(len(raw)==len(test) and output,"ERR_MISSING_TEST")
    outcsv(out/"RA5_TAP_NOISE_CLASS_BY_STRATUM.csv",output)
    outcsv(out/"RA5_TAP_NOISE_TEST_SAMPLES.csv",raw)
    qa=dict(status="PASS_SOURCE_LOCKED_NOISE_SWITCH_DISTRIBUTION_TECHNICAL",
      case=args.case,train_pose=ids[0],test_pose=ids[1],
      n_train_draws=len(train),n_test_draws=len(test),
      n_regime_strata=len(output),unknown_receiver_noise=True,
      train_test_pose_disjoint=True,noise_source="CIRCULAR_COMPLEX_CFR_SYNTHETIC",
      clean_full_tap_available_to_filter=False,
      test_truth_used_only_scoring=True,
      actual_filter_gating_with_switch_distribution="NOT_RUN",
      original_RF_unchanged=True,RT_calls=0,independent_auditor=False,
      science_release=False,
      utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_TAP_NOISE_CLASS_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
    print("RA5_TAP_CLASS_FINAL "+json.dumps(qa),flush=True)
    for r in output:print("RA5_TAP_CLASS_STRATUM "+json.dumps(r),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--case",required=True);p.add_argument("--poses",required=True)
    p.add_argument("--source",required=True);p.add_argument("--lock",required=True)
    p.add_argument("--draw",type=int,default=512);p.add_argument("--out",required=True)
    a=p.parse_args();req(a.draw>=200,"ERR_SAMPLING");main(a)
