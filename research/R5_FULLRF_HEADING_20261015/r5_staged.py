"""R5-0 immutable baseline audit; R5-1 offline Full/LoS error decomposition.
Independent read-only scorer: archived ground truth is used ONLY for scoring.
No estimator, LUT, gate, covariance or original R2 results are changed.
"""
from __future__ import annotations
import argparse
import ast
import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import zipfile
from pathlib import Path


REPO=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
R2=REPO/"research/EKF4_RANGE_S_STAGED_20261014"
PINNED={
"research/EKF4_RANGE_S_STAGED_20261014/core.py":"0a0851e6867c14fec5eefe02df471100cb9e9e1d",
"research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py":"cb676aea8e6710ff2c0e175e1e422271b696cebe",
"research/EKF4_RANGE_S_STAGED_20261014/p3_frozen_inputs.py":"3ba19cf01bd225ccf98335e5e92448530713b045",
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py":"b1de0de13e82cd414306cba3182af18ac97607bf",
"research/EKF4_RANGE_S_STAGED_20261014/r2_bias_score.py":"03a6616c082788a0d796458ca505964843fe897f",
"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json":"8bf216cf606f5e3c11139cacbf42f15a44556feb",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_2deg.npy":"9a53057f6f646f63574574b9a70186452cb5aca9",
"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT/hs_lut_meta.json":"5a24bf5f371eb3ad49b77e972b2bc77abecd679f",
}
RF_ZIP="88b0e89e752b482a54e882c25c72908ed115088a3f5783321945b627467ecd63"
R2_ZIP="ac98c5b50077484f10bb3898138c46115d4921ac099753c5f935db33521da399"
CASES=["R2_aA_m0","R2_aA_m45"]
CHANNELS=["los","full"]
LEVELS={"B0":0.,"L0":.01,"L1":.05,"L2":.2}
METHODS=["DR3","DR4","S3","S4","J3","J4","SR3","SR4"]
EVAL_METHODS=["DR4","S4","J4","SR4"]
CHI1=3.841458820694124
CHI3=7.814727903251179

def hash_file(path):
    hh=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""): hh.update(chunk)
    return hh.hexdigest()

def git_blob_sha(p):
    p=Path(p)
    h=hashlib.sha1()
    h.update(b"blob "+str(p.stat().st_size).encode()+b"\x00")
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()

def write_json(p,v):
    Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+"\n")

def preflight(folder):
    folder.mkdir(parents=True,exist_ok=False)
    failures=[]
    observed={}
    if os.getenv("GITHUB_ACTIONS")!="true":
        failures.append("GITHUB_ACTIONS_REQUIRED_FOR_PINNED_SOURCE_AUDIT")
    try:
        rev=subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip()
        if rev!=os.getenv("GITHUB_SHA"):failures.append("GIT_REV_NOT_EXACT")
    except Exception as ex:failures.append("REV_CHECK_ERROR:"+str(ex))
    for rel,expected in PINNED.items():
        f=REPO/rel
        if not f.is_file():
            failures.append("MISSING_FROZEN:"+rel)
            continue
        actual=git_blob_sha(f);observed[rel]=actual
        if actual!=expected:failures.append("HASH_MISMATCH:"+rel)
    for rel in ["research/EKF4_RANGE_S_STAGED_20261014/r2_bias_replay.py",
                "research/EKF4_RANGE_S_STAGED_20261014/p3_rf_adapter4.py",
                "research/R5_FULLRF_HEADING_20261015/r5_staged.py"]:
        f=REPO/rel
        if f.exists():
            try:ast.parse(f.read_text(encoding="utf-8"),filename=rel)
            except Exception as ex:failures.append("PARSE_FAIL:"+rel+":"+repr(ex))
    legacy=(R2/"r2_bias_replay.py").read_text()
    if ('if alg in ("S3","S4"):' not in legacy or
        'if alg.startswith("S"):' in legacy or
        'if not alg.startswith("SR"):' not in legacy):
        failures.append("LEGACY_SR_DISPATCH_REGRESSION")
    if "truth" in ast.dump(ast.parse(legacy).body[0])[:0]:
        failures.append("UNREACHABLE_GUARD")
    workflow=REPO/".github/workflows/r5-fullrf-heading-staged.yml"
    if not workflow.is_file():
        failures.append("WORKFLOW_MISSING")
    else:
        wf=workflow.read_text()
        for phrase in ("r5_staged.py --phase pre","gh api","r5_staged.py --phase run","if: always()","set -euo pipefail","actions: read"):
            if phrase not in wf:failures.append("WORKFLOW_CONTRACT_MISSING:"+phrase)
        if not wf.index("r5_staged.py --phase pre")<wf.index("gh api")<wf.index("r5_staged.py --phase run"):
            failures.append("WORKFLOW_AUDIT_NOT_FIRST")
    result={"schema":"R5_0_STATIC_SOURCE_AUDIT_V1",
            "decision":"GO" if not failures else "HOLD",
            "git_sha":os.getenv("GITHUB_SHA"),"frozen_git_blobs":observed,
            "expected_original_RF_zip_sha256":RF_ZIP,
            "expected_R2_output_zip_sha256":R2_ZIP,
            "errors":failures,"scientific_PASS":False}
    write_json(folder/"PRE_AUDIT.json",result)
    print("R5_0_PRE_AUDIT "+json.dumps({"decision":result["decision"],"errors":failures}),flush=True)
    return 0 if not failures else 2

def find_unique(zf,basename):
    matches=[p for p in zf.namelist() if p.endswith("/"+basename) or p==basename]
    if len(matches)!=1:raise ValueError("ZIP_FILE_NOT_UNIQUE:"+basename+":count="+str(len(matches)))
    return matches[0]

def read_npz(zf,path):
    with np.load(io.BytesIO(zf.read(path)),allow_pickle=False) as z:
        return {name:z[name].copy() for name in z.files}

def to_csv(path,rows):
    if not rows:raise ValueError("NO_ROWS_TO_EXPORT")
    with Path(path).open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)

def simple_stats(res):
    res=np.asarray(res,dtype=float)
    return {"mean":float(np.mean(res)),"median":float(np.median(res)),
            "std":float(np.std(res)),"rmse":float(np.sqrt(np.mean(res**2))),
            "abs_p95":float(np.quantile(np.abs(res),.95))}

def corr(a,b):
    if np.std(a)<1e-13 or np.std(b)<1e-13:return None
    return float(np.corrcoef(a,b)[0,1])

def wrap(v):return (np.asarray(v)+np.pi)%(2*np.pi)-np.pi

def score(x,P,status,true,t,true_bias):
    ok=(t>=30)
    if not(np.isfinite(x[ok,:4]).all() and np.isfinite(P[ok,:,:]).all()):
        raise ValueError("NONFINITE_SCORED_STATE")
    err=x[ok,:3]-true[ok,:3]
    err[:,2]=wrap(err[:,2])
    p=P[ok,:3,:3]
    if np.min(np.linalg.eigvalsh(p))<=0:raise ValueError("NON_PD_POSE_POSTERIOR")
    hn=err[:,2]**2/p[:,2,2]
    pn=np.einsum("bi,bi->b",err,np.linalg.solve(p,err[...,None])[:,:,0])
    bad_conf=(np.abs(np.rad2deg(err[:,2]))>5.)&(hn>CHI1)
    biases=np.degrees(x[ok,3])
    return {
     "frames":int(ok.sum()),
     "heading_rmse_deg":float(np.degrees(np.sqrt(np.mean(err[:,2]**2)))),
     "heading_signed_mean_deg":float(np.degrees(np.mean(err[:,2]))),
     "heading_sigma_rms_deg":float(np.degrees(np.sqrt(np.mean(p[:,2,2])))),
     "heading_nees_mean":float(np.mean(hn)),
     "heading95_coverage":float(np.mean(hn<=CHI1)),
     "pose_rmse_m":float(np.sqrt(np.mean(np.sum(err[:,:2]**2,axis=1)))),
     "pose_nees_mean":float(np.mean(pn)),
     "pose95_coverage":float(np.mean(pn<=CHI3)),
     "wrong_over_5deg_and_overconfident_count":int(np.sum(bad_conf)),
     "wrong_over_5deg_and_overconfident_frac":float(np.mean(bad_conf)),
     "bias_rmse_dps":float(np.sqrt(np.mean((biases-true_bias)**2))),
     "bias_final_dps":float(biases[-1]),
     "gate_rejected_eval":int(np.sum(status[ok]=="REJECT")),
     "gate_applied_eval":int(np.sum(status[ok]=="APPLIED"))
    }

def check_zip(path,expected):
    sha=hash_file(path)
    if sha!=expected:raise RuntimeError("SOURCE_ARCHIVE_SHA_MISMATCH:"+path.name+" "+sha)
    with zipfile.ZipFile(path) as zf:
        bad=zf.testzip()
        if bad:raise RuntimeError("ZIP_CRC_FAIL:"+bad)
    return sha

def run(raw_path,r2_path,out,pre_path):
    global np
    import numpy as np
    out.mkdir(parents=True,exist_ok=False)
    pre=json.loads(Path(pre_path).read_text())
    if pre.get("decision")!="GO" or pre.get("git_sha")!=os.getenv("GITHUB_SHA"):
        raise RuntimeError("PRE_AUDIT_NOT_GO")
    rfsha=check_zip(raw_path,RF_ZIP)
    r2sha=check_zip(r2_path,R2_ZIP)
    sys.path.insert(0,str(R2))
    from p3_rf_adapter4 import FrozenLut
    lut=FrozenLut(REPO)
    manifest=json.loads((REPO/"research/EKF3_INDEPENDENT_20261013/P0_INPUT_MANIFEST.json").read_text())
    case_meta={p["id"]:p for p in manifest["cases"]}
    if not set(CASES).issubset(case_meta):raise RuntimeError("FROZEN_R2_CASES_MISSING")
    residuals=[]
    scores=[]
    paired=[]
    all_input_checks=[]
    by_case={}
    with zipfile.ZipFile(raw_path) as archive,zipfile.ZipFile(r2_path) as replay:
        summary=json.loads(archive.read("P2_OUT/P2_ONE_STEP_SUMMARY.json"))
        entry_index={(q["case"],q["channel"]):q for q in summary["per_case"]}
        # Honor original per-NPZ SHA; no generator used in evaluation.
        for case in CASES:
            for channel in CHANNELS:
                ent=entry_index[(case,channel)]
                member="P2_OUT/"+ent["trace_file"]
                blob=archive.read(member)
                if hashlib.sha256(blob).hexdigest()!=ent["trace_sha256"]:
                    raise RuntimeError("ORIGINAL_TRACE_HASH_CHANGED:"+member)
                with np.load(io.BytesIO(blob),allow_pickle=False) as zz:
                    z={key:zz[key].copy() for key in ("t_s","pose_id","truth_for_offline_scoring_only","z_r_m","z_s")}
                if len(z["t_s"])!=979 or not np.isfinite(np.r_[z["z_r_m"],z["z_s"]]).all():
                    raise RuntimeError("ORIGINAL_TRACE_BAD_SHAPE:"+case+"/"+channel)
                by_case[(case,channel)]=z
                t=z["t_s"];truth=z["truth_for_offline_scoring_only"];valid=t>=30
                h=np.array([lut.model(np.r_[truth[k,:3],0.],case_meta[case])[0] for k in range(len(t))])
                dr=z["z_r_m"]-h[:,0]
                ds=z["z_s"]-h[:,1]
                residuals.append({
                    "case":case,"channel":channel,"frames_eval":int(valid.sum()),
                    **{"range_"+k:v for k,v in simple_stats(dr[valid]).items()},
                    **{"s_"+k:v for k,v in simple_stats(ds[valid]).items()},
                    "corr_range_s":corr(dr[valid],ds[valid]),
                    "s_lag1_corr":corr(ds[valid][:-1],ds[valid][1:]),
                    "delta_model":"z minus frozen LoS h evaluated at offline GT",
                    "method":"GT_OFFLINE_ONLY"
                })
                for level,bias in LEVELS.items():
                    wanted=case+"_"+channel+"_"+level+"_seed0_recursive.npz"
                    data=read_npz(replay,find_unique(replay,wanted))
                    if (data["estimate"].shape!=(979,8,4) or
                        data["covariance"].shape!=(979,8,4,4) or
                        list(data["names"])!=METHODS or
                        not np.array_equal(data["t_s"],t) or
                        not np.array_equal(data["pose_id"],z["pose_id"])):
                        raise RuntimeError("REPLAY_PROVENANCE_SHAPE_MISMATCH:"+wanted)
                    all_input_checks.append(wanted)
                    for name in EVAL_METHODS:
                        j=METHODS.index(name)
                        full_state=data["estimate"][:,j]
                        full_cov=data["covariance"][:,j]
                        # DR4 4-state is well-defined for this study.
                        metrics=score(full_state,full_cov,data["status"][:,j],truth,t,bias)
                        scores.append({"case":case,"channel":channel,"level":level,"true_bias_dps":bias,
                                       "method":name,**metrics})
        for case in CASES:
            los=by_case[(case,"los")];full=by_case[(case,"full")]
            for key in ("t_s","pose_id","truth_for_offline_scoring_only"):
                if not np.array_equal(los[key],full[key]):
                    raise RuntimeError("LOS_FULL_NOT_PAIRED:"+case+":"+key)
            valid=los["t_s"]>=30
            for field in ("z_s","z_r_m"):
                d=full[field][valid]-los[field][valid]
                paired.append({"case":case,"field":field,"frames":int(valid.sum()),
                               **simple_stats(d),
                               "lag1_corr":corr(d[:-1],d[1:])})
        # Existence and declared range of the archival R2 scorer.
        metricfiles=[n for n in replay.namelist() if n.endswith("/R2_BIAS_METRICS.csv") or n=="R2_BIAS_METRICS.csv"]
        if len(metricfiles)!=1:raise RuntimeError("SCORED_REFERENCE_MISSING")
        with io.StringIO(replay.read(metricfiles[0]).decode("utf-8")) as f:
            prior_scores=list(csv.DictReader(f))
        if len(prior_scores)!=256:raise RuntimeError("REFERENCE_SCORE_COUNT_BAD")
        idx={(q["case"],q["rf_channel"],q["level"],q["evaluation_mode"],q["method"]):q for q in prior_scores}
        for row in scores:
            key=(row["case"],row["channel"],row["level"],"recursive",row["method"])
            ref=idx[key]
            for name in ("heading_rmse_deg","pose_nees_mean","heading95_coverage"):
                delta=abs(float(ref[name])-row[name])
                if delta>1e-8*max(1.0,abs(float(ref[name]))):
                    raise RuntimeError("INDEPENDENT_REFERENCE_PARITY_FAIL:"+name+":"+str(key)+":"+str(delta))
    input_receipt={
        "schema":"R5_0_FULL_INPUT_AUDIT_V1",
        "status":"INPUT_AUDIT_PASS","decision":"GO",
        "git_sha":os.getenv("GITHUB_SHA"),
        "RF_original_sha256":rfsha,"R2_recursive_output_sha256":r2sha,
        "original_case_channels":4,"recursive_traces":len(all_input_checks),
        "methods_scored":["DR4","S4","J4","SR4"],
        "score_rows_verified_against_original_scorer":len(scores),
        "frames_total_all_case_channel":3916,
        "frozen_R0":[0.0068578637,0.0081],
        "single_seed":0,"one_corridor":True,
        "scientific_PASS":False,
    }
    write_json(out/"R5_0_INPUT_AUDIT.json",input_receipt)
    to_csv(out/"R5_1_GT_OBSERVATION_RESIDUALS.csv",residuals)
    to_csv(out/"R5_1_FULL_MINUS_LOS_RF.csv",paired)
    to_csv(out/"R5_1_RECURSIVE_SCORES.csv",scores)
    by={(r["case"],r["channel"],r["level"],r["method"]):r for r in scores}
    transitions=[]
    for case in CASES:
        for level in LEVELS:
            for channel in CHANNELS:
                dr=by[(case,channel,level,"DR4")]
                for method in ("S4","J4","SR4"):
                    r=by[(case,channel,level,method)]
                    transitions.append({
                      "case":case,"channel":channel,"level":level,"method":method,
                      "heading_rmse_minus_DR4_deg":r["heading_rmse_deg"]-dr["heading_rmse_deg"],
                      "heading_nees_minus_DR4":r["heading_nees_mean"]-dr["heading_nees_mean"],
                      "heading_coverage_minus_DR4":r["heading95_coverage"]-dr["heading95_coverage"],
                      "bias_rmse_minus_DR4_dps":r["bias_rmse_dps"]-dr["bias_rmse_dps"]
                    })
    to_csv(out/"R5_1_RF_VS_DR_RECURSIVE.csv",transitions)
    focus=[]
    for level in LEVELS:
        for method in EVAL_METHODS:
            r=by[("R2_aA_m0","full",level,method)]
            focus.append({"bias_level":level,"method":method,
               "heading_rmse_deg":r["heading_rmse_deg"],
               "heading_nees_mean":r["heading_nees_mean"],
               "heading95_coverage":r["heading95_coverage"],
               "bias_final_dps":r["bias_final_dps"],
               "wrong_high_confidence_frac":r["wrong_over_5deg_and_overconfident_frac"]})
    final={
      "schema":"R5_1_PAIRED_RF_RESIDUAL_AND_RECURSIVE_DIAGNOSTIC_V1",
      "status":"OFFLINE_DECOMPOSITION_COMPLETE",
      "audit_pass":True,"source_sha":os.getenv("GITHUB_SHA"),
      "evaluation":"archived RF with GT exclusively for offline diagnostic; no new estimator fitted",
      "focus_full_mount0":focus,
      "observed_residuals":residuals,
      "full_minus_los":paired,
      "n_case_channels":4,"n_levels":4,"n_models":4,
      "input_from_previously_validated_R2_replay":True,
      "new_active_full_scan_available":False,
      "multipath_features_CIR": "NOT_IN_P2_NPZ_CHECK_SEPARATE_SOURCE_BEFORE_CLAIM",
      "new_scientific_generalization_PASS":False,
      "next":{"R5_2":"SOURCE_AVAILABILITY_AND_FEATURE_AUDIT",
              "R5_4":"FROZEN_LOS_LUT_GRADIENT_AUDIT_CAN_RUN_INDEPENDENTLY",
              "R5_5":"BLOCKED_UNTIL_NEW_YAW_RESOLVED_FULL_RF_CREATED"}
    }
    write_json(out/"R5_1_FINAL.json",final)
    print("R5_0_INPUT_AUDIT "+json.dumps(input_receipt),flush=True)
    print("R5_1_FINAL "+json.dumps({"status":final["status"],
          "residual_rows":len(residuals),"score_rows":len(scores),
          "paired_rows":len(paired),"focus":focus}),flush=True)
    return 0

def numeric_self_tests():
    global np
    import numpy as np
    from scipy.stats import chi2
    rng=np.random.default_rng(15)
    d=np.diff(np.eye(11),axis=0)
    R=.0081
    C=R*d@d.T
    if not np.allclose(d@np.ones(11),0,atol=1e-14):raise RuntimeError("GRAD_OFFSET_NOT_NULL")
    if np.linalg.eigvalsh(C).min()<=0:raise RuntimeError("GRAD_COV_NOT_PD")
    z=rng.normal(0,math.sqrt(R),size=(20000,11))
    t=np.linalg.solve(np.linalg.cholesky(C),np.diff(z,axis=1).T)
    false_alarm=float(np.mean(np.sum(t*t,axis=0)>chi2.ppf(.95,10)))
    if abs(false_alarm-.05)>.01:raise RuntimeError("GRAD_NULL_CALIBRATION_FAIL")
    assert np.max(np.abs(wrap(np.array([-3*math.pi,3*math.pi]))+math.pi))<1e-12
    print("R5_0_UNIT_PASS "+json.dumps({"gradient_null_rate":false_alarm,"tests":4}),flush=True)
    return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--phase",required=True,choices=("pre","test","run"))
    ap.add_argument("--out")
    ap.add_argument("--raw")
    ap.add_argument("--r2")
    ap.add_argument("--pre")
    a=ap.parse_args()
    if a.phase=="pre":return preflight(Path(a.out))
    if a.phase=="test":return numeric_self_tests()
    if not all((a.out,a.raw,a.r2,a.pre)):raise RuntimeError("MISSING_RUN_ARGUMENT")
    return run(Path(a.raw),Path(a.r2),Path(a.out),Path(a.pre))

if __name__=="__main__":raise SystemExit(main())
