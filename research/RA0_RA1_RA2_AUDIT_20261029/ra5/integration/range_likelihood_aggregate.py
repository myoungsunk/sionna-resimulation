#!/usr/bin/env python3
"""Aggregate source-locked A/B/C range likelihood experiments without pseudo-replication.
Each case/pose/snr/jitter cell contributes one conditional comparison; tests are NOT
independent scenes and raw template is a known-H information upper bound.
"""
import argparse,csv,datetime,hashlib,json,math,pathlib
import numpy as np
def req(ok,msg):
    if not ok:raise RuntimeError(msg)
def load(path):
    with path.open(newline="") as f:return list(csv.DictReader(f))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def out_csv(path,rows):
    keys=list(rows[0])
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def main(root,out):
    root=pathlib.Path(root);out=pathlib.Path(out);out.mkdir(exist_ok=True,parents=True)
    scorefiles=list(root.rglob("RA5_RANGE_THREE_WAY_SCORES.csv"))
    qafiles=list(root.rglob("RA5_RANGE_THREE_WAY_QA.json"))
    req(len(scorefiles)==len(qafiles)==2,"ERR_SOURCE_COUNT")
    allrows=[];qa=[];inputs=[]
    for f in scorefiles:
        p=f.parent/"RA5_RANGE_THREE_WAY_QA.json"
        req(p.is_file(),"ERR_PAIR_QA "+str(f))
        q=json.loads(p.read_text())
        req(q["status"]=="PASS_CONTROLLED_THREE_WAY_RANGE_COMPARISON","ERR_NONPASS_SOURCE")
        rows=load(f)
        req(len(rows)==192 and len(set(r["case"] for r in rows))==1,"ERR_N_PER_SOURCE")
        req({r["case"] for r in rows}=={q["case"]},"ERR_CASE_QA")
        qa.append(q);allrows.extend(rows)
        inputs.append(dict(case=q["case"],H_sha=q["original_H_SHA256"],score_sha=sha(f),qa_sha=sha(p),n_score_rows=len(rows)))
    req(len(allrows)==384 and len({r["case"] for r in allrows})==2,"ERR_TOTAL_SCOPE")
    arms=sorted({r["arm"] for r in allrows})
    req(len(arms)==4,"ERR_ARM_COUNT")
    by=[]
    for case in sorted({r["case"] for r in allrows}):
        for snr in [-5.,5.,20.]:
            for jitter in [0.,150.]:
                for arm in arms:
                    group=[r for r in allrows if r["case"]==case and float(r["snr_db"])==snr and float(r["jitter_ps"])==jitter and r["arm"]==arm]
                    req(len(group)==8,"ERR_CASE_CELLS "+str((case,snr,jitter,arm,len(group))))
                    n=sum(int(r["n_valid"]) for r in group)
                    req(n>0,"ERR_ZERO_VALID "+arm)
                    mse=sum(int(r["n_valid"])*float(r["rmse_m"])**2 for r in group)/n
                    bias=sum(int(r["n_valid"])*float(r["bias_m"]) for r in group)/n
                    coverage=[r for r in group if r["cov95"] not in ("None","",None)]
                    valid_cov=sum(int(r["n_valid"]) for r in coverage)
                    cov=sum(int(r["n_valid"])*float(r["cov95"]) for r in coverage)/valid_cov if valid_cov else None
                    by.append(dict(case=case,snr_db=snr,jitter_ps=jitter,arm=arm,
                      n_valid=n,n_proposed=8*192,n_independent_RF_scenes=1,
                      rmse_m=math.sqrt(mse),bias_m=bias,coverage95=cov,
                      calibration_method="SCENE_POSE_AND_NOISE_CONDITIONAL_ORACLE",
                      source="ORIGINAL_FULL_H_RIGID_DELAY_SHIFT_NOT_PHYSICAL_MOTION"))
    out_csv(out/"RA5_RANGE_AGG_BY_CASE_SNR_JITTER.csv",by)
    pair=[]
    for case in sorted({r["case"] for r in allrows}):
        for snr in [-5.,5.,20.]:
            for jitter in [0.,150.]:
                group={r["arm"]:r for r in by if r["case"]==case and r["snr_db"]==snr and r["jitter_ps"]==jitter}
                b=group["B_ORIGINAL_INT_CAL_GAUSS"]["rmse_m"]
                a=group["A_FRACTIONAL_LEADING_EDGE"]["rmse_m"]
                c=group["C_RAW_COMPLEX_CFR_PROFILE"]["rmse_m"]
                d=group["B_DISCRETE_TAP_POSTERIOR"]["rmse_m"]
                pair.append(dict(case=case,snr_db=snr,jitter_ps=jitter,
                  baseline_integer_rmse_m=b,subtap_rmse_m=a,
                  categorical_tap_rmse_m=d,raw_profile_rmse_m=c,
                  subtap_relative_change=(a/b)-1,
                  categorical_relative_change=(d/b)-1,
                  raw_relative_change=(c/b)-1,
                  winner_by_rmse=min((("integer",b),("subtap",a),("categorical",d),("raw_known_H",c)),key=lambda z:z[1])[0],
                  note="same saved scene; raw profile knows actual H template; no real pose transfer"))
    out_csv(out/"RA5_RANGE_PAIRED_COMPARISONS.csv",pair)
    out_csv(out/"RA5_RANGE_INPUT_HASHES.csv",inputs)
    qaresult=dict(status="PASS_TWO_CASE_RANGE_THREE_WAY_AGGREGATE",
       n_source_runs=2,n_source_cases=2,n_pose_per_case=2,
       n_score_rows=len(allrows),n_conditional_comparisons=len(pair),
       n_test_realizations_per_arm=2*2*3*2*4*192,
       n_snr_jitter_case_pairs=len(pair),
       n_subtap_better_than_integer=sum(p["subtap_rmse_m"]<p["baseline_integer_rmse_m"] for p in pair),
       n_discrete_posterior_better_than_integer=sum(p["categorical_tap_rmse_m"]<p["baseline_integer_rmse_m"] for p in pair),
       n_raw_knownH_better_than_integer=sum(p["raw_profile_rmse_m"]<p["baseline_integer_rmse_m"] for p in pair),
       n_raw_knownH_best=sum(p["winner_by_rmse"]=="raw_known_H" for p in pair),
       known_bias_source_per_case_pose_noise="YES, TRAIN ONLY",
       no_real_pose_motion="RIGID_ALL_PATH_DELAY_ONLY",
       true_new_physical_RF_scenes=0,n_RT_calls=0,
       original_archive_mutated=False,independent_auditor=False,science_release=False,
       input_shas=inputs,utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/"RA5_RANGE_AGG_QA.json").write_text(json.dumps(qaresult,indent=2)+"\n")
    print("RA5_RANGE_AGG_FINAL "+json.dumps({k:v for k,v in qaresult.items() if k!="input_shas"}),flush=True)
    for x in pair:print("RA5_RANGE_PAIRED "+json.dumps(x),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--source",required=True);p.add_argument("--out",required=True);a=p.parse_args();main(a.source,a.out)
