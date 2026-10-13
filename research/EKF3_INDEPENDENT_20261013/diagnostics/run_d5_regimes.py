#!/usr/bin/env python3
"""D5 multi-seed/full-route recursive A/B/C regime diagnostic with frozen RF.

Only developer/exploratory reproduction of the P0 sensor-world assumption;
NOT a scientific consistency or hardware-performance certification.

All conditions share the same IMU/wheel measurements and initialization
per seed/case; channel H is reused.  Unmodeled gyro and wheel calibration
are intentionally present under sensor_v2 condition='all'.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
PROJECT=HERE.parent
ARCHIVED=REPO/"results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
sys.path.insert(0,str(ARCHIVED))
sys.path.insert(0,str(PROJECT))
from ekf3 import EKF3,archived_direct_s_model,wrap  # noqa: E402
from qclean_uwb.drivesim.sensor_v2 import (  # noqa: E402
    SensorV2Config, generate, motion_increments, rng as sensor_rng
)
from qclean_uwb.drivesim.observation import observe  # noqa: E402
from run_d0_d4 import (  # noqa: E402
    P3_MODEL, P3_SHA256, RR, RS, B_OLD, hash_file, checked_path,
    read_p0, original_lut, covariance_terms, yaw_error
)
from p3_compat import frozen_detector,corrected_ranges,assert_observation_parity  # noqa: E402

P0_COV=np.diag([.1**2,.1**2,math.radians(5)**2])


def timelines(p0:dict) -> dict[str,tuple[np.ndarray,np.ndarray,np.ndarray]]:
    result={}
    for route in p0["routes"]:
        file=checked_path(p0,route["path"])
        with file.open(encoding="utf-8",newline="") as h:
            rows=list(csv.DictReader(h))
        if len(rows)!=route["samples"]:raise RuntimeError("changed timeline")
        t=np.asarray([float(r["t_s"]) for r in rows])
        truth=np.asarray([[float(r["x"]),float(r["y"]),math.radians(float(r["yaw_body_deg"]))] for r in rows])
        ids=np.asarray([int(r["pose_id"]) for r in rows],int)
        result[route["id"]]=(t,truth,ids)
    return result


def observed_case(p0:dict,case:dict,channel:str,freqs:np.ndarray,pose_ids:np.ndarray) -> dict:
    file=checked_path(p0,case[channel+"_path"])
    samples_path=checked_path(p0,case["samples_path"])
    s=json.loads(samples_path.read_text())
    byid={int(p["pose_id"]):i for i,p in enumerate(s)}
    if len(byid)!=len(s):raise RuntimeError("duplicate pose ids")
    inds=np.asarray([byid[int(pid)] for pid in pose_ids],int)
    H=np.load(file,mmap_mode="r",allow_pickle=False)
    features=frozen_detector(H,freqs,float(case["mount_deg"]),__import__(
        "qclean_uwb.drivesim.observation",fromlist=["cir_batch"]))
    all_fields={key:np.asarray(a)[inds] for key,a in features.items()}
    # Canonical range/s must be identical to the original frozen receiver.
    if np.any(~np.isfinite(all_fields["s"])):raise RuntimeError("nonfinite frozen RF s")
    return all_fields


def run_one(
    case:dict,channel:str,level:int,condition:str,seed:int,
    time:np.ndarray,truth:np.ndarray,obs:dict,range_model:str,
    range_physical:np.ndarray,lut:object,
) -> tuple[list[dict],dict]:
    ds_true,dyaw_true=motion_increments(time,truth,convention="legacy-euler")
    cfg=SensorV2Config(level=level,condition=condition,common_scale=0.,bias_rw_rad_s_sqrt_s=0.,slip_mode="time")
    measurements,_truth_eval_only=generate(time,ds_true,dyaw_true,cfg,seed)
    # The same sampled initial error is reused for every arm and correction.
    initial_noise=sensor_rng(seed,"initial").standard_normal(3)*np.array([.1,.1,math.radians(5)])
    start=truth[0].copy()+initial_noise;start[2]=wrap(start[2])
    filters={arm:EKF3(start,P0_COV) for arm in ("D0","A","B","C")}
    model=archived_direct_s_model(lut,anchor_xyz_m=tuple(case["anchor"]),
                                 tag_height_m=float(case["robot_z_m"]),
                                 mount_deg=float(case["mount_deg"]))
    outputs=[]
    summary={name:{"pos2":[],"yaw2":[],"nees":[],"yaw_nees":[],"cover":[],"improvement_heading":[],"statuses":Counter()}
             for name in filters}
    for k in range(len(time)):
        for name,f in filters.items():
            if k>0:
                f.predict(float(measurements["ds_odom"][k]),
                          float(measurements["dtheta_gyro"][k]),
                          float(measurements["dt_s"][k]))
            prior=f.x.copy()
            z_s=float(obs["s"][k]) if np.isfinite(obs["s"][k]) else None
            r=range_physical[k]
            z_r=float(r+B_OLD) if np.isfinite(r) else None
            step=None
            if name=="A":
                step=f.update_heading(z_s,RS,s_model=model)
            elif name=="B":
                step=f.update_range(z_r,RR,anchor_xyz_m=tuple(case["anchor"]),
                                    tag_height_m=float(case["robot_z_m"]),range_offset_m=B_OLD)
            elif name=="C":
                step=f.update_joint(z_s,z_r,RS,RR,0.,s_model=model,
                                     anchor_xyz_m=tuple(case["anchor"]),
                                     tag_height_m=float(case["robot_z_m"]),range_offset_m=B_OLD)
            if time[k] < 30.:continue
            truth_k=truth[k]
            e=np.array([f.x[0]-truth_k[0],f.x[1]-truth_k[1],wrap(f.x[2]-truth_k[2])])
            c=covariance_terms(e,f.P)
            d=summary[name]
            d["pos2"].append(float(e[0]**2+e[1]**2))
            d["yaw2"].append(math.degrees(e[2])**2)
            d["nees"].append(c["pose_nees"])
            d["yaw_nees"].append(c["yaw_nees"])
            d["cover"].append(c["covered95_pose"])
            if step is not None:
                d["statuses"][step.status]+=1
                if step.status=="applied":
                    err_prior=abs(wrap(prior[2]-truth_k[2]))
                    d["improvement_heading"].append(abs(e[2])<err_prior)
            outputs.append(dict(
                case=case["id"],channel=channel,level=level,condition=condition,seed=seed,
                range_model=range_model,arm=name,t_s=float(time[k]),pose_id=k,
                x=float(f.x[0]),y=float(f.x[1]),yaw_rad=float(f.x[2]),
                yaw_error_deg=math.degrees(e[2]),
                Pxx=float(f.P[0,0]),Pyy=float(f.P[1,1]),Ppsi=float(f.P[2,2]),
                NIS=float(step.NIS) if step is not None and step.NIS is not None else None,
                gate_status=(step.status if step else "DR_only"),
                pose_nees=c["pose_nees"],heading_nees=c["yaw_nees"],
            ))
    groups=[]
    for name,d in summary.items():
        groups.append(dict(case=case["id"],channel=channel,condition=condition,level=level,
            seed=seed,range_model=range_model,arm=name,
            n=len(d["pos2"]),heading_rmse_deg=float(np.sqrt(np.mean(d["yaw2"]))),
            xy_rmse_m=float(np.sqrt(np.mean(d["pos2"]))),
            mean_pose_NEES=float(np.mean(d["nees"])),
            mean_heading_NEES=float(np.mean(d["yaw_nees"])),
            pose95=float(np.mean(d["cover"])),
            accepted_heading_improvement_fraction=(
                float(np.mean(d["improvement_heading"])) if d["improvement_heading"] else None),
            accepted_updates=int(d["statuses"]["applied"]),rejected_updates=int(d["statuses"]["rejected_NIS"])))
    return outputs,groups


def main()->int:
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument("--out",type=Path,required=True)
    a.add_argument("--seeds",type=int,nargs="+",required=True,
                   help="e.g. development 0 1 2; confirmation 10000...10049")
    a.add_argument("--levels",type=int,nargs="+",choices=[0,1,2],default=[0,1,2])
    a.add_argument("--conditions",nargs="+",choices=["noise_pair","all"],default=["noise_pair","all"])
    a.add_argument("--channels",nargs="+",choices=["los","full"],default=["los","full"])
    a.add_argument("--cases",nargs="*",default=[])
    a.add_argument("--range-models",nargs="+",choices=["B_OLD","D1_FRACTIONAL","E1_FULL_LORO"],default=["B_OLD","E1_FULL_LORO"])
    a.add_argument("--save-full-sample-trace",action="store_true")
    args=a.parse_args()
    if args.out.exists():raise FileExistsError(f"refusing to overwrite diagnostic output: {args.out}")
    if hash_file(P3_MODEL)!=P3_SHA256:raise RuntimeError("P3 model hash mismatch")
    frozen=json.loads(P3_MODEL.read_text())
    p0=read_p0();lut=original_lut(p0)
    freq_path="results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy"
    freqs=np.load(checked_path(p0,freq_path),allow_pickle=False)
    tl=timelines(p0)
    arms=[];traces=[]
    for case in p0["cases"]:
        if args.cases and case["id"] not in args.cases:continue
        t,truth,pids=tl[case["route"]]
        for channel in args.channels:
            det=observed_case(p0,case,channel,freqs,pids)
            correction=corrected_ranges(det,frozen["loro_fold_params"][case["route"]],
                                        allow_e1_on_los=False,channel=channel)
            for range_model in args.range_models:
                if range_model not in correction:continue
                for condition in args.conditions:
                    for level in args.levels:
                        for seed in args.seeds:
                            trace,rows=run_one(case,channel,level,condition,seed,t,truth,det,
                                                range_model,correction[range_model],lut)
                            arms.extend(rows)
                            if args.save_full_sample_trace:traces.extend(trace)
                            print(f"{case['id']} {channel} {range_model} {condition} level={level} seed={seed}",flush=True)
    if not arms:raise RuntimeError("no matched case/range correction")
    args.out.mkdir(parents=True,exist_ok=False)
    def write_csv(file,rows):
        columns=list(rows[0])
        with file.open("w",newline="",encoding="utf-8") as handle:
            writer=csv.DictWriter(handle,fieldnames=columns);writer.writeheader();writer.writerows(rows)
    write_csv(args.out/"D5_MULTI_SEED_FULL_ROUTE_METRICS.csv",arms)
    if args.save_full_sample_trace:write_csv(args.out/"D5_FULL_ROUTE_SAMPLE_TRACE.csv",traces)
    manifest=dict(schema="EKF3_D5_FULL_ROUTE_V1",status="EXPLORATORY",
                  no_new_RF_realizations=True,seed_list=args.seeds,levels=args.levels,
                  conditions=args.conditions,channels=args.channels,
                  correction_models=args.range_models,all_model_altered_states_fully_recurrent=True,
                  single_scene_limitation=True,seed_reuse_per_case=True,
                  p0_sha256=hash_file(PROJECT/"P0_INPUT_MANIFEST.json"),
                  p3_sha256=hash_file(P3_MODEL),
                  n_rows=len(arms),scientific_PASS=False,
                  outputs={f.name:hash_file(f) for f in args.out.glob("*.csv")})
    (args.out/"D5_RUN_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print(json.dumps({k:manifest[k] for k in ("status","n_rows","scientific_PASS")},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
