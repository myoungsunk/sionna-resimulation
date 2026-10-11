#!/usr/bin/env python3
"""Pre-registered independent-LoS range bias replay on saved *real* native RF packets.

Side-by-side exactly paired replay:
  0: saved native range-only, offset=0; MUST reproduce native EKF bytes/numbers
  A: same inertial+encoder input, all RF disabled
  B: identical input and original noisy full-RF packets, calibrated offset ONLY

The training calibrator never reads evaluation site. This script reads EVAL_ONLY
truth exclusively after all EKF updates, to measure errors. No gateway/Q/R tuning,
no change to first-arrival tap, no substitution of LoS H for full RF.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"src"))
from qclean_uwb.drivesim.body_ekf_bridge import ProbeEKF6,V2BodyFilterConfig
from qclean_uwb.drivesim.body_sensor_stream import MeasuredIncrement
from qclean_uwb.drivesim.body_pose_channel import RFFilterPacket

C95_3=7.814727903251179
LOWER95_3=0.215795282623898
RANGE_NAMES=("rf_original_zero_offset","rf_off_paired","rf_flat_detector_only_calibrated","rf_independent_los_calibrated")


def digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1048576),b""):h.update(chunk)
    return h.hexdigest()


def load_calibration(path,mount):
    info=json.loads(Path(path).read_text(encoding="utf8"))
    ref=info.get("calibration_sha256")
    meta={k:v for k,v in info.items() if k!="calibration_sha256"}
    sha=hashlib.sha256(json.dumps(meta,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    if ref!=sha:raise ValueError("INDEPENDENT_CALIBRATION_SHA_MISMATCH")
    if info.get("schema_version")!="INDEPENDENT_FFD_LOS_DETECTOR_CAL_V1":
        raise ValueError("UNSUPPORTED_CALIBRATION")
    if info.get("true_evaluation_RF_input")!="NOT_USED":
        raise ValueError("CALIBRATION_ORACLE_LEAKAGE")
    key=str(int(mount)) if float(mount).is_integer() else str(mount)
    if key not in info["mount_models"]:raise ValueError("MOUNT_HAS_NO_INDEPENDENT_CALIBRATION")
    model=info["mount_models"][key]
    value=float(model["range_offset_m"])
    if not math.isfinite(value) or not -2.<value<0.:
        raise ValueError("UNPHYSICAL_OR_UNSIGNED_DETECTOR_OFFSET")
    return info,model,value


def read_npz(p):
    with np.load(p,allow_pickle=False) as f:
        return {k:f[k] for k in f.files}


def finite_or_none(x):
    val=float(x)
    return val if math.isfinite(val) else None


def make_increment(trace,i,cfg):
    radius=float(cfg["physical"]["nominal_radius_m"])
    return MeasuredIncrement(
        t_s=float(trace["t_s"][i]),dt_s=float(trace["dt_s"][i]),
        ds_odom=float(trace["ds_odom"][i]),
        dtheta_odom=float(trace["dtheta_odom"][i]),
        dtheta_gyro=float(trace["dtheta_gyro"][i]),
        encoder_left_rad=float(trace["encoder_left_rad"][i]),
        encoder_right_rad=float(trace["encoder_right_rad"][i]),
        wheel_nominal_left_m=radius*float(trace["encoder_left_rad"][i]),
        wheel_nominal_right_m=radius*float(trace["encoder_right_rad"][i]))


def replay(trace,rf,manifest,base_filter,*,rf_mode,offset):
    config=replace(base_filter,range_offset=float(offset),
                   use_range=rf_mode!="off",use_s=False)
    p0=np.diag(np.asarray(manifest["config"]["initial_filter"]["P0_diagonal"],float))
    x0=np.asarray(manifest["config"]["initial_filter"]["x0"],float)
    ekf=ProbeEKF6(config,None,x0,P0=p0,rf_mode="off" if rf_mode=="off" else "range_only")
    n=len(trace["t_s"])
    index=np.asarray(rf["corresponding_state_index"],int)
    if len(set(index))!=len(index) or np.any(index<0) or np.any(index>=n):
        raise ValueError("INVALID_RF_PACKET_INDICES")
    packet_by_tick={int(t):j for j,t in enumerate(index)}
    recs=[]
    for i in range(n):
        ekf.start_interval(make_increment(trace,i,manifest["config"]),
                           phase=str(trace["phase"][i]))
        if i in packet_by_tick and rf_mode!="off":
            j=packet_by_tick[i]
            pkt=RFFilterPacket(packet_id=f"replay_native_RF_packet_{j}",
                              t_s=float(rf["time_rf_s"][j]),
                              detected=bool(rf["detected"][j]),
                              range_m=float(rf["range_m"][j]),
                              s=float(rf["s_firstpath"][j]),
                              power=(float(rf["P1_firstpath"][j]),
                                     float(rf["P2_firstpath"][j])),
                              selected_tap=int(rf["selected_tap"][j]))
            ekf.apply_rf(pkt)
        recs.append(ekf.finish_interval())
    return dict(x=np.stack([r["x_after_RF"] for r in recs]),
                P=np.stack([r["P_after_RF"] for r in recs]),
                rf_packet_states=[recs[i] for i in index],
                rf_event_updates=[
                dict(t_s=float(r["t_s"]),state_index=int(idx),innovation_m=finite_or_none(r["range_innovation"]),
                     R_m2=finite_or_none(r["range_R"]),S_m2=finite_or_none(r["range_S"]),
                     nis=float(r["range_innovation"]**2/r["range_S"])
                         if r["range_S"]>0 else None,
                     status=r["range_status"])
                for idx,r in zip(index,[recs[i] for i in index])])


def pose_errors(x,truth):
    e=np.asarray(x[:,:3]-truth,dtype=float)
    e[:,2]=(e[:,2]+np.pi)%(2*np.pi)-np.pi
    return e


def score(x,P,truth,mask):
    select=np.flatnonzero(mask)
    if not len(select):return {"status":"NO_SAMPLES"}
    diff=pose_errors(x,truth)[select]
    p3=P[select,:3,:3]
    nees=np.array([float(e@np.linalg.solve(p,e)) for e,p in zip(diff,p3)])
    pos=np.linalg.norm(diff[:,:2],axis=1)
    return dict(n_samples=len(select),
                heading_RMSE_deg=float(np.degrees(np.sqrt(np.mean(diff[:,2]**2)))),
                heading_P95_abs_deg=float(np.degrees(np.quantile(np.abs(diff[:,2]),.95))),
                heading_final_abs_deg=float(np.degrees(abs(diff[-1,2]))),
                position_RMSE_m=float(np.sqrt(np.mean(pos**2))),
                final_position_error_m=float(pos[-1]),
                pose_NEES_df3_mean=float(np.mean(nees)),
                pose_NEES_df3_p95=float(np.quantile(nees,.95)),
                pose_95_coverage_descriptive=float(np.mean(nees<=C95_3)),
                pose_nees_lower_025_fraction=float(np.mean(nees<LOWER95_3)),
                heading_95_coverage_descriptive=float(np.mean(np.abs(diff[:,2]) <=
                    1.95996398454 * np.sqrt(P[select,2,2]))))


def check_paired(run,calibration):
    root=Path(run)
    cfg=json.loads((root/"MANIFEST.json").read_text(encoding="utf8"))
    trace=read_npz(root/"STATE_TRACE.npz")
    rf=read_npz(root/"PROBE_RF_PACKETS.npz")
    # No evaluation oracle is even opened before all three EKF replays.
    status=json.loads((root/"EXECUTION_STATUS.json").read_text(encoding="utf8"))
    if cfg["config"]["rf"]["mode"]!="range_only" or status["status"]!="CONTROL_COMPLETE_RF_COLLECTED":
        raise ValueError("ONLY_COMPLETED_NATIVE_RANGE_ONLY_SOURCE_SUPPORTED")
    actual_config=status["filter_config"]
    if float(actual_config["range_offset"])!=0:
        raise ValueError("UNMODIFIED_RANGE_OFFSET_ZERO_SOURCE_REQUIRED")
    original=V2BodyFilterConfig(**actual_config)
    meta,model,offset=load_calibration(calibration,float(original.mount_deg))
    n=len(trace["t_s"])
    # The physical initial-site exclusion is pre-registered in the run config,
    # not inferred from recorded evaluation outcomes.
    initial_xy=np.asarray(cfg["config"]["physical"]["init_true_xyyaw_rad"][:2],float)
    sites=meta["train_site_xy"]+meta["holdout_site_xy"]
    if (min(float(np.linalg.norm(np.asarray(site)-initial_xy)) for site in sites)
            <= float(meta["min_evaluation_exclusion_m"])):
        raise ValueError("EVALUATION_POSITION_LEAKED_INTO_CALIBRATION")
    a=replay(trace,rf,cfg,original,rf_mode="range_only",offset=0.)
    # Exact source numeric parity mandatory before accepting any corrected replay.
    max_x=float(np.max(np.abs(a["x"]-trace["x_after_RF"])))
    max_p=float(np.max(np.abs(a["P"]-trace["P_after_RF"])))
    if max_x>1e-10 or max_p>1e-10:
        raise ValueError(f"ORIGINAL_NATIVE_EKF_PARITY_FAILED x={max_x} P={max_p}")
    off=replay(trace,rf,cfg,original,rf_mode="off",offset=0.)
    flat_offset=float(model["flat_only_mean_bias_m"])
    flat_baseline=replay(trace,rf,cfg,original,rf_mode="range_only",offset=flat_offset)
    calibrated=replay(trace,rf,cfg,original,rf_mode="range_only",offset=offset)
    # Only now read the oracle trace, for evaluation metrics; no online filter
    # or calibrated prediction has access to its recorded true poses.
    oracle=read_npz(root/"ORACLE_EVAL_ONLY.npz")
    true=np.asarray(oracle["true_xyyaw"],float)
    if true.shape!=(n,3):raise ValueError("TRUTH_ALIGNMENT_MISSING")
    id0=np.asarray(rf["corresponding_state_index"],int)
    after=np.arange(n)>=int(np.min(id0))
    mask=np.ones(n,bool)
    stats={}
    for name,dat in zip(RANGE_NAMES,[a,off,flat_baseline,calibrated]):
        stats[name]={"all_probe_ticks":score(dat["x"],dat["P"],true,mask),
                     "first_RF_to_end":score(dat["x"],dat["P"],true,after),
                     "RF_observation_update_records":dat["rf_event_updates"],
                     "n_accepted_RF_packets":sum(1 for r in dat["rf_event_updates"] if r["status"]=="applied")}
    xcal=calibrated["x"]
    Pcal=calibrated["P"]
    return dict(schema_version="NATIVE_HELDOUT_INDEPENDENT_RANGE_CAL_REPLAY_V1",
        status="REPLAY_EVALUATED_ONE_SEED_NOT_FULL_CLOSED_LOOP",
        scientific_PASS=False,F01="OPEN",F02="OPEN",
        source_run_dir=str(root),source_manifest_sha256=digest(root/"MANIFEST.json"),
        source_native_RF_H_sha256=digest(root/"RF_NATIVE_CHANNELS_ORACLE_ONLY.npz"),
        calibration_file_sha256=digest(calibration),
        calibration_sha256=meta["calibration_sha256"],
        calibration_source="Independent analytic FFD LoS at other XY, never this site's RF or truth",
        calibration_range_offset_m=offset,
        flat_spectrum_detector_baseline_offset_m=flat_offset,
        calibration_mount_deg=float(original.mount_deg),
        independent_holdout_fit=model,
        frozen_source_parity_max_state_abs_diff=max_x,
        frozen_source_parity_max_P6_abs_diff=max_p,
        applied_filter_diff={"range_offset_old":0.,"range_offset_new":offset,
            "R_Q_gate_prior_and_sensor_inputs":"UNCHANGED"},
        n_source_RF_packets=int(len(id0)),
        n_source_EKF_ticks=int(n),
        metrics=stats,
        final_estimate_corrected=xcal[-1].tolist(),
        final_P6_corrected=Pcal[-1].tolist(),
        trajectory_control="SAVED_ORIGINAL_RF_CONTROL_NOT_RECOMPUTED",
        evaluation_truth_used_only_after_EKF=True,
        limitations=["ONE_SEED","NEUTRAL_PHYSICAL_SLIP","RANGE_ONLY_NO_s_YAW_UPDATE",
                    "NOT_FULL_CLOSED_LOOP_CONTROL_REEXECUTION",
                    "ANALYTIC_LOS_SIONNA_PARITY_NOT_YET_PASSED",
                    "SITE_CORRELATED_RF_AND_NEES_NOT_ESTABLISHED"])


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--run-dir",type=Path,required=True)
    ap.add_argument("--calibration",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    if a.out.exists():raise FileExistsError("NEVER_OVERWRITE_CALIBRATED_REPORT")
    report=check_paired(a.run_dir,a.calibration)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf8")
    print(json.dumps({key:report[key] for key in
       ("status","calibration_range_offset_m","n_source_RF_packets","scientific_PASS")},indent=2),flush=True)
    print(json.dumps({name:{"accepted":arm["n_accepted_RF_packets"],
        "pos_rmse_m":arm["all_probe_ticks"]["position_RMSE_m"],
        "heading_rmse_deg":arm["all_probe_ticks"]["heading_RMSE_deg"],
        "pose_nees":arm["all_probe_ticks"]["pose_NEES_df3_mean"]}
        for name,arm in report["metrics"].items()},indent=2),flush=True)


if __name__=="__main__":
    raise SystemExit(main())
