#!/usr/bin/env python3
"""P4 full-factorial frozen R0 paired ONE-STEP EKF approximation comparison.

Not recursive. Not exact nonlinear G2/G3. Every time: independent DR-only
prior (same motion/seed) is copied then updated ONCE with frozen s/r.  Trace
and per-case denominators are preserved. No truth enters the filter.
"""
from __future__ import annotations
import argparse,csv,gzip,json,math,sys,time,traceback
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
from scipy.stats import chi2

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
H3=REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics/h3_offline/results/H3_OFFLINE_20261014_01a1380d"
sys.path.insert(0,str(REPO/"research/EKF3_INDEPENDENT_20261013/diagnostics"))
sys.path.insert(0,str(H3))
import d6_d9_common as c
import h3_offline as h
h.REPO=REPO
METHODS=("DR","G0_S_EKF","G2_RANGE_S_EKF","G3_JOINT_EKF_GATE","G3_JOINT_EKF_NOGATE")
RF_ARMS=(("los","B_OLD"),("full","B_OLD"),("full","E1_FULL_LORO"))
DR_CONDITIONS=(("noise_pair",1),("gyro_bias",0),("gyro_bias",1),("gyro_bias",2))
SEEDS=(0,1,2)
COV3_95=float(chi2.ppf(.95,3))
EPS=1e-9
def wrap(a):return float((a+math.pi)%(2*math.pi)-math.pi)
def jsafe(x):
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,np.ndarray):return x.tolist()
    raise TypeError(type(x).__name__)
def stats(rows):
    err_xy=np.asarray([r["squared_xy_m2"] for r in rows],float)
    err_psi=np.asarray([r["squared_heading_deg2"] for r in rows],float)
    nees=np.asarray([r["pose_NEES"] for r in rows],float)
    return dict(n=len(rows),xy_RMSE_m=float(np.sqrt(err_xy.mean())),
          heading_RMSE_deg=float(np.sqrt(err_psi.mean())),
          mean_pose_NEES=float(nees.mean()),
          pose95_fraction=float(np.mean(nees<=COV3_95)),
          xy_P95_m=float(np.percentile(np.sqrt(err_xy),95)),
          heading_P95_deg=float(np.percentile(np.sqrt(err_psi),95)),
          min_P_eigen=float(min(r["min_P_eigen"] for r in rows)),
          mean_cross_cov_xy_psi=float(np.mean([abs(r["Pxpsi"])+abs(r["Pypsi"]) for r in rows])),
          gate_reject_fraction=float(np.mean([r["rejected"] for r in rows])))
def rowscore(method,ft,truth,gate_info,base):
    err=np.asarray(ft.x,float)-truth
    err[2]=wrap(err[2])
    P=np.asarray(ft.P,float)
    mine=float(np.linalg.eigvalsh((P+P.T)/2).min())
    if not np.isfinite(P).all() or mine<=0:raise RuntimeError("CASE_RESULT_INVALID: posterior non-PD")
    n=float(err@np.linalg.solve(P,err))
    return dict(base,method=method,
        mean_x=float(ft.x[0]),mean_y=float(ft.x[1]),mean_psi_rad=float(ft.x[2]),
        Pxx=float(P[0,0]),Pyy=float(P[1,1]),Ppsipsi=float(P[2,2]),
        Pxy=float(P[0,1]),Pxpsi=float(P[0,2]),Pypsi=float(P[1,2]),
        min_P_eigen=mine,
        squared_xy_m2=float(err[:2]@err[:2]),
        squared_heading_deg2=float((err[2]*180/math.pi)**2),
        signed_heading_error_deg=float(err[2]*180/math.pi),
        pose_NEES=n,
        rejected=int("rejected_NIS" in gate_info),
        gate_status=gate_info)
def make_one_step(x,P,zs,zr,case,lut):
    base=c.EKF3(x,P)
    adapter=c.EKF3(x,P).clone()
    model=c.EKF3.__module__
    from ekf3 import archived_direct_s_model
    sfun=archived_direct_s_model(lut,
        anchor_xyz_m=tuple(case["anchor"]),
        tag_height_m=float(case["robot_z_m"]),
        mount_deg=float(case["mount_deg"]))
    zraw=float(zr+c.B_OLD)
    results={"DR":(base,"DR_only")}
    sf=c.EKF3(x,P)
    st=sf.update_heading(zs,c.RS,s_model=sfun)
    results["G0_S_EKF"]=(sf,st.status)
    rf=c.EKF3(x,P)
    a=rf.update_range(zraw,c.RR,anchor_xyz_m=tuple(case["anchor"]),
             tag_height_m=float(case["robot_z_m"]),range_offset_m=c.B_OLD)
    b=rf.update_heading(zs,c.RS,s_model=sfun)
    results["G2_RANGE_S_EKF"]=(rf,a.status+";S="+b.status)
    joint=c.EKF3(x,P)
    v=joint.update_joint(zs,zraw,c.RS,c.RR,0.,s_model=sfun,
             anchor_xyz_m=tuple(case["anchor"]),tag_height_m=float(case["robot_z_m"]),
             range_offset_m=c.B_OLD)
    results["G3_JOINT_EKF_GATE"]=(joint,v.status)
    joint2=c.EKF3(x,P)
    v2=joint2.update_joint(zs,zraw,c.RS,c.RR,0.,s_model=sfun,
             anchor_xyz_m=tuple(case["anchor"]),tag_height_m=float(case["robot_z_m"]),
             range_offset_m=c.B_OLD,gate=False)
    results["G3_JOINT_EKF_NOGATE"]=(joint2,v2.status)
    return results
def run(caseid,out):
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    receipt=dict(stage="P4_FULL_FACTORIAL_EKF_ONE_STEP_ONLY",case=caseid,status="RUNNING",
        full_nonlinear_G3="NOT_RUN_IN_THIS_JOB",scientific_PASS=False,
        full_RF_D0_truth_after_inference_only=True,failed_updates=[],method_attempts=Counter(),
        method_valid=Counter(),condition_summary=[])
    t0=time.time()
    try:
        p0=c.check_inputs(full_p0=False)
        case=next(x for x in p0["cases"] if x["id"]==caseid)
        lut=c.original_lut(p0)
        freqs=c.spectrum(p0)
        firstt,firsttruth,ids,_,_=c.case_motion(p0,case,0,2,"gyro_bias")
        detectors={ch:c.rf_case(p0,case,ch,freqs,ids) for ch in ("los","full")}
        folds=json.loads(c.P3_MODEL.read_text())["loro_fold_params"]
        corrections={ch:c.corrected_ranges(detectors[ch],folds[case["route"]],
                    allow_e1_on_los=False,channel=ch) for ch in ("los","full")}
        for cond,lev in DR_CONDITIONS:
            for seed in SEEDS:
                t,tr,pids,motion,_=c.case_motion(p0,case,seed,lev,cond)
                if not np.array_equal(firstt,t) or not np.array_equal(ids,pids) or not np.array_equal(firsttruth,tr):
                    raise RuntimeError("HARD_EXECUTION_BLOCK: DR prior timeline/pose alignment wrong")
                df=c.DiagnosticFilter(c.initial_state(tr[0],seed))
                grouped=defaultdict(list)
                attempts=Counter()
                for k in range(len(t)):
                    if k:df.predict(float(motion["ds_odom"][k]),
                                    float(motion["dtheta_gyro"][k]),float(motion["dt_s"][k]))
                    if float(t[k])<30:continue
                    x,P=df.pose.copy(),df.Ppose.copy()
                    for channel,rmod in RF_ARMS:
                        zs=float(detectors[channel]["s"][k])
                        zr=float(corrections[channel][rmod][k])
                        base=dict(case=caseid,condition=cond,level=lev,seed=seed,
                            sample=int(k),time_s=float(t[k]),channel=channel,range_model=rmod)
                        try:
                            methods=make_one_step(x,P,zs,zr,case,lut)
                            for method in METHODS:
                                attempts[channel,rmod,method]+=1
                                receipt["method_attempts"][method]+=1
                                f,gate=methods[method]
                                r=rowscore(method,f,tr[k],gate,base)
                                grouped[channel,rmod,method].append(r)
                                receipt["method_valid"][method]+=1
                                # Only aggregate records saved for 5 methods, store
                                # complete input/output for 30 seconds intervals.
                                if k%150==0:
                                    trace_rows.append(r)
                        except Exception as exc:
                            for method in METHODS:
                                attempts[channel,rmod,method]+=1
                                receipt["method_attempts"][method]+=1
                            receipt["failed_updates"].append(dict(base,exception_type=type(exc).__name__,
                                            detail=str(exc)))
                for (ch,rm,method),sub in grouped.items():
                    r=dict(case=caseid,route=case["route"],condition=cond,level=lev,seed=seed,
                         channel=ch,range_model=rm,method=method,**stats(sub),
                         attempted=int(attempts[ch,rm,method]),
                         numeric_invalid=int(attempts[ch,rm,method]-len(sub)))
                    receipt["condition_summary"].append(r)
                print("P4_CELL",caseid,cond,lev,seed,"invalids",len(receipt["failed_updates"]),flush=True)
        report_rows=receipt["condition_summary"]
        if report_rows:
            with (out/"P4_APPROX_SUMMARY.csv").open("w",newline="") as f:
                cols=list(report_rows[0]);w=csv.DictWriter(f,fieldnames=cols)
                w.writeheader();w.writerows(report_rows)
        if trace_rows:
            with gzip.open(out/"P4_STATE_COV_TRACES.csv.gz","wt",newline="") as f:
                cols=list(trace_rows[0]);w=csv.DictWriter(f,fieldnames=cols)
                w.writeheader();w.writerows(trace_rows)
        receipt["status"]="EXECUTED_FULL_FACTORIAL_EKF_ONE_STEP"
        receipt["elapsed_s"]=time.time()-t0
    except Exception as ex:
        receipt["status"]="HARD_EXECUTION_BLOCK";receipt["error"]=str(ex);receipt["traceback"]=traceback.format_exc()[-3000:]
    finally:
        receipt["method_attempts"]=dict(receipt["method_attempts"])
        receipt["method_valid"]=dict(receipt["method_valid"])
        receipt["failed_count"]=len(receipt["failed_updates"])
        (out/"P4_RECEIPT.json").write_text(json.dumps(receipt,allow_nan=False,indent=2,default=jsafe))
        print("P4_FINAL",json.dumps({k:receipt[k] for k in ("case","status","failed_count","elapsed_s") if k in receipt}),flush=True)
    return 0 if receipt["status"]=="EXECUTED_FULL_FACTORIAL_EKF_ONE_STEP" else 2

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--case",required=True)
    a.add_argument("--out",type=Path,required=True)
    arg=a.parse_args()
    return run(arg.case,arg.out)
if __name__=="__main__":sys.exit(main())
