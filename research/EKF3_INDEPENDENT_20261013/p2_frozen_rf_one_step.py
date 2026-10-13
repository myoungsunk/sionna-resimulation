#!/usr/bin/env python3
"""P2 frozen RF one-step comparison from one common DR predicted x3/P3.

Does NOT run full-route recursively fused A/B/C or claim scientific consistency.
All RF H/LUT/observer and motion source are P0-pinned and read-only.
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

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
P0 = json.loads((HERE / "P0_INPUT_MANIFEST.json").read_text(encoding="utf-8"))
ARCHIVE = REPO / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff"
SOURCE = ARCHIVE / "source/src"
# Frozen snapshot wins over mutable src/; EKF3 never imports archived 6-state code.
sys.path.insert(0, str(SOURCE))

from qclean_uwb.drivesim.hs_lut import HsLut  # noqa: E402
from qclean_uwb.drivesim.observation import observe  # noqa: E402
from qclean_uwb.drivesim.sensor_v2 import (  # noqa: E402
    SensorV2Config, generate, motion_increments, rng as sensor_rng,
)
from ekf3 import EKF3, archived_direct_s_model, wrap  # noqa: E402

ARMS = ("A", "B", "C")
RS = 0.09 ** 2
RR = 0.0068578637
RSR = 0.0
OFFSET = -0.5315983906250129
P0_COV = np.diag([0.1**2, 0.1**2, math.radians(5)**2])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1 << 20), b""):
            h.update(part)
    return h.hexdigest()


def freeze_assert(path: Path) -> None:
    key = str(path.relative_to(REPO)).replace("\\", "/")
    match = next((x for x in P0["assets"] if x["path"] == key), None)
    if match is None:
        raise RuntimeError(f"not P0-listed input: {key}")
    if not path.is_file() or path.stat().st_size != match["bytes"]:
        raise RuntimeError(f"P0 missing/size mismatch: {key}")
    if match.get("sha256") and sha256(path) != match["sha256"]:
        raise RuntimeError(f"P0 SHA256 mismatch: {key}")


def read_tnone(route: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    path = REPO / route["path"]
    freeze_assert(path)
    with path.open(encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    if len(rows) != route["samples"]:
        raise RuntimeError(f"timeline length mismatch: {route['id']}")
    t = np.array([float(r["t_s"]) for r in rows])
    truth = np.array([[float(r["x"]), float(r["y"]),
                       math.radians(float(r["yaw_body_deg"]))] for r in rows], float)
    pose_id = np.array([int(r["pose_id"]) for r in rows], int)
    if not np.isfinite(truth).all() or not np.all(np.diff(t) > 0):
        raise RuntimeError("nonfinite timeline or nonmonotonic clock")
    return t, truth, pose_id


def read_rf(case: dict, mode: str, pose_ids: np.ndarray,
            frequencies: np.ndarray) -> dict:
    file = REPO / case[f"{mode}_path"]
    samples_path = REPO / case["samples_path"]
    freeze_assert(file)
    freeze_assert(samples_path)
    samples = json.loads(samples_path.read_text(encoding="utf-8"))
    index = {int(s["pose_id"]): i for i, s in enumerate(samples)}
    if len(index) != len(samples):
        raise RuntimeError("duplicate RF pose ids")
    positions = [index[int(pid)] for pid in pose_ids]
    H = np.load(file, mmap_mode="r", allow_pickle=False)
    if list(H.shape) != case["H_shape"]:
        raise RuntimeError("changed RF H shape")
    if not np.isfinite(H[positions[0]]).all():
        raise RuntimeError("nonfinite RF channel")
    # Chunk to avoid allocating FFT of every pose at once.
    pieces = []
    for k in range(0, len(positions), 128):
        chunk = np.asarray(H[positions[k:k + 128]])
        pieces.append(observe(chunk, frequencies, None, None, tx=0))
    out = {}
    for key in ("s", "range_m", "power", "index", "detected", "peak"):
        out[key] = np.concatenate([p[key] for p in pieces], axis=0)
    return out


def dr_only_pred(t: np.ndarray, truth: np.ndarray, seed: int) -> tuple[np.ndarray, np.ndarray, dict]:
    # Frozen trajectory is legacy-Euler. Keep the generator contract; do not
    # rewrite truth to make an SE(2) motion estimator appear perfect.
    ds_true, dtheta_true = motion_increments(t, truth, convention="legacy-euler")
    cfg = SensorV2Config(level=1, condition="noise_pair", common_scale=0.0,
                         bias_rw_rad_s_sqrt_s=0.0, slip_mode="time")
    inputs, _eval_only = generate(t, ds_true, dtheta_true, cfg, seed)
    noise = sensor_rng(seed, "initial").standard_normal(3) * np.array(
        [0.1, 0.1, math.radians(5.0)]
    )
    x0 = truth[0].copy() + noise
    x0[2] = wrap(x0[2])
    d0 = EKF3(x0, P0_COV)
    xprior = np.empty((len(t), 3))
    pprior = np.empty((len(t), 3, 3))
    for k in range(len(t)):
        if k > 0:
            d0.predict(float(inputs["ds_odom"][k]),
                       float(inputs["dtheta_gyro"][k]),
                       float(inputs["dt_s"][k]))
        xprior[k] = d0.x
        pprior[k] = d0.P
    return xprior, pprior, {
        "noise_pair": True,
        "seed": int(seed),
        "initial_error_x_y_yaw": noise.tolist(),
        "final_DR_only_x": d0.x.tolist(),
        "true_motion_contract": "legacy-euler; exact SE2 predictor mismatch retained",
    }


def write_case(outdir: Path, case: dict, mode: str, seed: int, t: np.ndarray,
               truth: np.ndarray, ids: np.ndarray,
               xprior: np.ndarray, pprior: np.ndarray, obs: dict,
               lut: HsLut) -> dict:
    case_id = case["id"]
    model = archived_direct_s_model(
        lut, anchor_xyz_m=tuple(case["anchor"]),
        tag_height_m=float(case["robot_z_m"]), mount_deg=float(case["mount_deg"])
    )
    n = len(t)
    post_x = np.full((n, 3, 3), np.nan)
    post_P = np.full((n, 3, 3, 3), np.nan)
    H = np.full((n, 3, 2, 3), np.nan)
    R = np.full((n, 3, 2, 2), np.nan)
    S = np.full((n, 3, 2, 2), np.nan)
    K = np.full((n, 3, 3, 2), np.nan)
    innovation = np.full((n, 3, 2), np.nan)
    predicted_z = np.full((n, 3, 2), np.nan)
    nis = np.full((n, 3), np.nan)
    status = np.full((n, 3), "NOT_RUN", dtype="<U32")
    approx_rho_m = np.full(n, np.nan)
    joseph_discrepancy = 0.
    identical_prior_count = 0
    loewner_pass = 0
    all_accepted = 0

    for i in range(n):
        prior = EKF3(xprior[i], pprior[i])
        x_before, P_before = prior.x.copy(), prior.P.copy()
        ms = float(obs["s"][i]) if obs["detected"][i] else None
        mr = float(obs["range_m"][i]) if obs["detected"][i] else None
        rho = math.hypot(prior.x[0] - case["anchor"][0], prior.x[1] - case["anchor"][1])
        approx_rho_m[i] = rho
        for j, name in enumerate(ARMS):
            ekf = prior.clone()
            if name == "A":
                step = ekf.update_heading(ms, RS, s_model=model)
            elif name == "B":
                step = ekf.update_range(
                    mr, RR, anchor_xyz_m=tuple(case["anchor"]),
                    tag_height_m=float(case["robot_z_m"]), range_offset_m=OFFSET)
            else:
                step = ekf.update_joint(
                    ms, mr, RS, RR, RSR, s_model=model,
                    anchor_xyz_m=tuple(case["anchor"]),
                    tag_height_m=float(case["robot_z_m"]), range_offset_m=OFFSET)
            if not np.array_equal(step.prior_x, x_before) or not np.array_equal(step.prior_P, P_before):
                raise AssertionError("A/B/C not using identical DR-only xminus/Pminus")
            identical_prior_count += 1
            post_x[i, j], post_P[i, j] = step.post_x, step.post_P
            status[i, j] = step.status
            if step.H is not None:
                nobs = len(step.innovation)
                H[i, j, :nobs] = step.H
                R[i, j, :nobs, :nobs] = step.R
                S[i, j, :nobs, :nobs] = step.S
                K[i, j, :, :nobs] = step.K
                innovation[i, j, :nobs] = step.innovation
                predicted_z[i, j, :nobs] = step.predicted_measurement
                nis[i, j] = step.NIS
                if step.status == "applied":
                    M = np.eye(3) - step.K @ step.H
                    P_joseph = M @ P_before @ M.T + step.K @ step.R @ step.K.T
                    joseph_discrepancy = max(joseph_discrepancy, float(np.max(np.abs(P_joseph - step.post_P))))
                    if joseph_discrepancy > 1e-9:
                        raise AssertionError("Joseph covariance identity mismatch")
        if all(status[i, j] == "applied" for j in range(3)):
            all_accepted += 1
            # Under the same linearisation and R_sr=0, joint update must carry
            # at least the information of either single observation.
            delta_a = (post_P[i, 0] - post_P[i, 2] + (post_P[i, 0] - post_P[i, 2]).T) / 2
            delta_b = (post_P[i, 1] - post_P[i, 2] + (post_P[i, 1] - post_P[i, 2]).T) / 2
            if min(np.linalg.eigvalsh(delta_a).min(), np.linalg.eigvalsh(delta_b).min()) < -1e-9:
                raise AssertionError("joint covariance Loewner ordering fails under independent R")
            loewner_pass += 1

    evaluation = t >= 30.
    shape_status = {}
    for j, name in enumerate(ARMS):
        counts = Counter(status[evaluation, j].tolist())
        delta = post_x[evaluation, j] - xprior[evaluation]
        delta[:, 2] = (delta[:, 2] + math.pi) % (2*math.pi) - math.pi
        shape_status[name] = {
            "gate_counts": dict(counts),
            "mean_post_traceP": float(np.mean(np.trace(post_P[evaluation, j], axis1=1, axis2=2))),
            "mean_pre_traceP": float(np.mean(np.trace(pprior[evaluation], axis1=1, axis2=2))),
            "mean_abs_heading_correction_deg": float(np.degrees(np.mean(np.abs(delta[:, 2])))),
            "mean_position_correction_m": float(np.mean(np.linalg.norm(delta[:, :2], axis=1))),
            "median_pre_gate_NIS": float(np.nanmedian(nis[evaluation, j])) if np.isfinite(nis[evaluation, j]).any() else None,
        }
    candidates = np.flatnonzero(
        evaluation & np.all(status == "applied", axis=1)
    )
    if len(candidates) == 0:
        candidates = np.flatnonzero(evaluation)
    if len(candidates) == 0:
        raise AssertionError("empty evaluation timeline")
    k = int(candidates[0])
    example = {
        "k":k, "t_s":float(t[k]), "pose_id":int(ids[k]),
        "raw_s":float(obs["s"][k]), "raw_range_m":float(obs["range_m"][k]),
        "common_xminus":xprior[k].tolist(),"common_Pminus":pprior[k].tolist(),
        "by_arm":{
            name:{
                "status":str(status[k,j]), "H":H[k,j,:1 if name!="C" else 2].tolist(),
                "R":R[k,j,:1 if name!="C" else 2,:1 if name!="C" else 2].tolist(),
                "S":S[k,j,:1 if name!="C" else 2,:1 if name!="C" else 2].tolist(),
                "K":K[k,j,:,:1 if name!="C" else 2].tolist(),
                "innovation":innovation[k,j,:1 if name!="C" else 2].tolist(),
                "NIS":float(nis[k,j]) if np.isfinite(nis[k,j]) else None,
                "Pplus":post_P[k,j].tolist(),
                "delta_x":(post_x[k,j]-xprior[k]).tolist()
            } for j,name in enumerate(ARMS)
        }
    }
    outdir.mkdir(parents=True, exist_ok=True)
    trace = outdir/f"{case_id}_{mode}_seed{seed}_ONE_STEP.npz"
    np.savez_compressed(
        trace, t_s=t, pose_id=ids,
        truth_for_offline_scoring_only=truth,
        xminus=xprior, Pminus=pprior,
        z_s=obs["s"],z_r_m=obs["range_m"],detected=obs["detected"],
        power=obs["power"],first_arrival_tap=obs["index"],
        xplus=post_x,Pplus=post_P,H=H,R=R,S=S,K=K,
        innovation=innovation,predicted_z=predicted_z,NIS=nis,status=status,
        estimated_pole_rho_m=approx_rho_m
    )
    return {
        "case":case_id,"channel":mode,"seed":seed,"n_steps":n,
        "evaluation_steps":int(np.sum(evaluation)),
        "matched_same_xminus_Pminus_updates":identical_prior_count,
        "all_three_accepted_in_evaluation":int(sum(np.all(status[evaluation]=="applied",axis=1))),
        "all_three_accepted_all_steps":all_accepted,
        "joint_Loewner_verifications":loewner_pass,
        "max_Joseph_residual":joseph_discrepancy,
        "estimated_rho_le_0p1_m_count":int(np.sum(approx_rho_m<=0.1)),
        "obs_detected":int(np.sum(obs["detected"])),
        "metrics_by_arm":shape_status,"example":example,
        "trace_file":trace.name,"trace_sha256":sha256(trace)
    }


def run(seed: int, modes: list[str], output_dir: Path, cases: list[str]) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    lut_path=ARCHIVE/"LUT/hs_lut_2deg.npy"
    freq_path=REPO / "results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy"
    freeze_assert(lut_path)
    freeze_assert(freq_path)
    loaded=np.load(lut_path,allow_pickle=True)
    if loaded.shape!=() or not isinstance(loaded.item(),dict):
        raise RuntimeError("LUT contract mismatch")
    lut=HsLut(loaded.item())
    frequencies=np.load(freq_path,allow_pickle=False)
    if len(frequencies)!=257 or not np.all(np.diff(frequencies)>0):
        raise RuntimeError("frequency grid invalid")
    route_records={}
    for route in P0["routes"]:
        t,truth,pose_ids=read_tnone(route)
        xprior,pprior,meta=dr_only_pred(t,truth,seed)
        route_records[route["id"]]=(t,truth,pose_ids,xprior,pprior,meta)
    per_case=[]
    for case in P0["cases"]:
        if cases and case["id"] not in cases:
            continue
        t,truth,ids,xprior,pprior,dr_metadata=route_records[case["route"]]
        for mode in modes:
            ob=read_rf(case,mode,ids,frequencies)
            entry=write_case(output_dir,case,mode,seed,t,truth,ids,xprior,pprior,ob,lut)
            per_case.append(entry)
            print(f"{case['id']} / {mode}: equal-prior={entry['matched_same_xminus_Pminus_updates']}, joint_accepted={entry['all_three_accepted_in_evaluation']}, max_Joseph={entry['max_Joseph_residual']:.2g}",flush=True)
    if len(per_case)==0:
        raise RuntimeError("no cases matched")
    result={
      "schema":"EKF3_P2_FROZEN_RF_ONE_STEP_V1",
      "status":"ONE_STEP_FROZEN_RF_EXECUTED_MATHEMATICAL_CHECKS_PASS",
      "scientific_PASS":False,
      "parent_p0_pass_commit":"b0957181e0e5238e160e69a04d052f23559e666c",
      "mode":"same prior per timestep from DR-only; this is NOT recursively fused full-route A/B/C",
      "source":"archived read-only Sensor-v2 + original H/LoS and frozen LUT",
      "channel_modes":modes,"seed":seed,"cases":cases or "all_7",
      "R0":{"Rs":RS,"Rr_m2":RR,"Rsr":RSR,"range_offset_m":OFFSET},
      "num_case_channel_runs":len(per_case),
      "sums":{
        "equal_prior_comparisons":sum(x["matched_same_xminus_Pminus_updates"] for x in per_case),
        "joint_Loewner_verifications":sum(x["joint_Loewner_verifications"] for x in per_case),
        "max_Joseph_residual":max(x["max_Joseph_residual"] for x in per_case),
      },
      "caveats":[
        "R_sr=0 is an R0 comparison assumption, not calibrated RF independence",
        "cases share one corridor, saved noise-free RF H reused across motion seed",
        "inverse-LUT RF heading is not used as an independent absolute angle",
        "legacy-Euler truth versus SE2 prediction mismatch remains",
        "F01/F02, near-pole LUT and temporal RF error calibration remain OPEN",
        "one-step common DR prior cannot establish recursively fused localization performance"
      ],
      "per_case":per_case
    }
    summary_path=output_dir/"P2_ONE_STEP_SUMMARY.json"
    summary_path.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"summary":str(summary_path),
                      "case_channel_runs":len(per_case),
                      "same_prior":result["sums"]["equal_prior_comparisons"],
                      "joint_Loewner_checks":result["sums"]["joint_Loewner_verifications"],
                      "max_Joseph_residual":result["sums"]["max_Joseph_residual"],
                      "scientific_PASS":False},indent=2),flush=True)
    return result


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--seed",type=int,default=0)
    parser.add_argument("--channels",nargs="+",choices=["full","los"],default=["los","full"])
    parser.add_argument("--cases",nargs="*",default=[])
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    run(args.seed,args.channels,args.out,args.cases)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
