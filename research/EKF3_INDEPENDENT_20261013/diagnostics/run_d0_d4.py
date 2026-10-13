#!/usr/bin/env python3
"""D0-D4: diagnostic-only frozen P2 one-step replay and range correction A/B/C.

Input P2 NPZs: download Actions 38331588521 artifact into --p2-dir/P2_OUT.
Online inputs: P0-pinned complex Full/LoS RF H, original observer, frozen
LoS LUT, and route-held-out P3 E1 coefficients (no true position in correction).
Offline truth: used ONLY to score errors and construct flat-channel controls.

NO fitting to heldout truth, RF regeneration, 6-state modification,
full-route recursively fused EKF or performance/scientific PASS declaration.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
PROJECT = HERE.parent
ARCHIVED_SRC = REPO / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"
sys.path.insert(0, str(ARCHIVED_SRC))
sys.path.insert(0, str(PROJECT))

from qclean_uwb.drivesim.hs_lut import HsLut, s_model  # noqa: E402
from qclean_uwb.drivesim import observation as O  # noqa: E402
from ekf3 import EKF3, archived_direct_s_model, wrap  # noqa: E402
from p3_compat import B_OLD, frozen_detector, corrected_ranges, assert_observation_parity, tap_metres  # noqa: E402

P0_PATH = PROJECT / "P0_INPUT_MANIFEST.json"
P3_MODEL = HERE / "E1_P3_FROZEN_LORO_20261012.json"
P3_SHA256 = "10fdb76f0fe0236400afd10cd53d79845582182a79151bec390d3ea968ceca95"
RS = 0.0081
RR = 0.0068578637
THR_POSE95 = 7.814727903251179
THR_YAW95 = 3.841458820694124
ARMS = ("A", "B", "C")
P2_BASELINE = {"A": 0, "B": 1, "C": 2}
NO_MODEL_CHANGE = {"B_OLD", "C_CONST_LOS", "D1_FRACTIONAL", "E1_FULL_LORO", "E1_ON_LOS_NEGCTRL"}


def hash_file(file: Path) -> str:
    s = hashlib.sha256()
    with file.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            s.update(b)
    return s.hexdigest()


def safe_float(v):
    x = float(v)
    return x if math.isfinite(x) else None


def read_p0() -> dict:
    return json.loads(P0_PATH.read_text(encoding="utf-8"))


def checked_path(p0: dict, field: str) -> Path:
    path = REPO / field
    descriptor = next((r for r in p0["assets"] if r["path"] == field), None)
    if descriptor is None or not path.is_file() or path.stat().st_size != descriptor["bytes"]:
        raise RuntimeError(f"P0 file missing/size mismatch: {field}")
    if descriptor.get("sha256") and hash_file(path) != descriptor["sha256"]:
        raise RuntimeError(f"P0 frozen SHA256 failed: {field}")
    return path


def verify_p2_artifact_integrity(p2_dir: Path, seed: int) -> dict:
    """D0 fail-closed: compare each trace and summary to frozen P2 receipt hashes."""
    receipt_path = PROJECT / "P2_RUN_RECEIPT.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected = receipt["artifact"]["summary_sha256"]
    summary_path = p2_dir / "P2_ONE_STEP_SUMMARY.json"
    if not summary_path.is_file() or hash_file(summary_path) != expected:
        raise RuntimeError("P2 summary absent/changed: download the verified Actions 38331588521 artifact")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("seed") != seed or summary.get("schema") != "EKF3_P2_FROZEN_RF_ONE_STEP_V1":
        raise RuntimeError("unexpected P2 seed or summary schema")
    if summary.get("num_case_channel_runs") != 14:
        raise RuntimeError("P2 requires seven cases x Full/LoS channels")
    for trace in summary["per_case"]:
        file = p2_dir / trace["trace_file"]
        if not file.is_file() or hash_file(file) != trace["trace_sha256"]:
            raise RuntimeError(f"P2 trace hash absent/mismatch: {file}")
    return dict(summary_sha256=expected,trace_count=len(summary["per_case"]),
                full_artifact_url=receipt["artifact"]["github_artifact_url"])


def load_p2_one_step(p2_dir: Path, case: str, channel: str, seed: int) -> dict:
    file = p2_dir / f"{case}_{channel}_seed{seed}_ONE_STEP.npz"
    if not file.is_file():
        raise FileNotFoundError(f"P2 NPZ missing: {file}. Download Actions artifact first.")
    with np.load(file, allow_pickle=False) as archive:
        x = {key: archive[key] for key in archive.files}
    shape = x["xminus"].shape[0]
    expected = {"xminus": (shape,3), "Pminus":(shape,3,3),
                "xplus":(shape,3,3),"Pplus":(shape,3,3,3),
                "H":(shape,3,2,3),"R":(shape,3,2,2),
                "S":(shape,3,2,2),"K":(shape,3,3,2),
                "innovation":(shape,3,2),"NIS":(shape,3),
                "status":(shape,3),"truth_for_offline_scoring_only":(shape,3)}
    for key, dims in expected.items():
        if key not in x or x[key].shape != dims:
            raise RuntimeError(f"bad frozen P2 trace {file}: {key} shape not {dims}")
    if not np.all(np.diff(x["t_s"]) > 0):
        raise RuntimeError("P2 clock nonmonotonic")
    return x


def original_lut(p0: dict) -> HsLut:
    base = "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/LUT"
    fn = checked_path(p0, base + "/hs_lut_2deg.npy")
    meta = json.loads(checked_path(p0, base + "/hs_lut_meta.json").read_text())["meta"]
    data = np.load(fn, mmap_mode="r", allow_pickle=False)
    theta = np.asarray(meta["theta_deg"], float)
    a,b,step = map(float,meta["phi_deg"])
    phi = np.arange(a,b+step/2,step)
    if data.shape != (len(theta),len(phi),len(phi)):
        raise RuntimeError("P0 LUT dimensions changed")
    return HsLut(dict(theta_deg=theta, phi_deg=phi, s=data))


def flat_eval_range(distances: np.ndarray, freqs: np.ndarray, chunk_size: int = 128) -> np.ndarray:
    """Oracle-only ideal flat complex LoS for decomposition; NEVER feed to EKF."""
    output = []
    for a in range(0,len(distances),chunk_size):
        d = np.asarray(distances[a:a+chunk_size],float)
        h = np.exp(-2j*np.pi*freqs[None,:]*(d[:,None]/O.C0))
        # identical receive ports, exactly the V04/P2 flat detector construction
        h2 = np.repeat(h[:,:,None],2,axis=2)[:,:,:,None]
        obs = O.observe(h2,freqs,None,None,tx=0)
        output.append(obs["range_m"])
    return np.concatenate(output)


def yaw_error(est: np.ndarray,truth: np.ndarray) -> np.ndarray:
    return (est - truth + np.pi)%(2*np.pi)-np.pi


def covariance_terms(err: np.ndarray, P: np.ndarray) -> dict:
    if not np.all(np.isfinite(P)) or not np.all(np.isfinite(err)):
        raise RuntimeError("nonfinite posterior covariance/true error")
    p = (P+P.T)/2
    if np.linalg.eigvalsh(p)[0] <= 0:
        raise RuntimeError("singular/indefinite P: no hidden jitter or projection")
    pose_nees = float(err @ np.linalg.solve(p,err))
    yaw_nees = float(err[2]**2 / p[2,2])
    cross = p[:2,2]
    Pxy_given_yaw = p[:2,:2] - np.outer(cross,cross)/p[2,2]
    e_xy_given_yaw = err[:2] - cross*err[2]/p[2,2]
    conditional = float(e_xy_given_yaw @ np.linalg.solve(Pxy_given_yaw,e_xy_given_yaw))
    if not np.isclose(pose_nees, yaw_nees+conditional, atol=1e-8, rtol=1e-9):
        raise RuntimeError("Schur pose-NEES decomposition failed")
    return dict(pose_nees=pose_nees,yaw_nees=yaw_nees,conditional_xy_nees=conditional,
                covered95_pose=pose_nees<=THR_POSE95,covered95_heading=yaw_nees<=THR_YAW95,
                sigma_yaw_deg=math.degrees(math.sqrt(p[2,2])),trace_xy=float(p[0,0]+p[1,1]))


def metrics_from_steps(steps: list[dict],truth:np.ndarray) -> dict:
    pos2=[];yaw2=[];nees=[];n_head=[];n_xy=[];pose95=[];h95=[];accepted=Counter()
    for i,row in enumerate(steps):
        x=np.asarray(row["x"],float);P=np.asarray(row["P"],float)
        e=np.array([x[0]-truth[i,0],x[1]-truth[i,1],yaw_error(x[2],truth[i,2])],float)
        cov=covariance_terms(e,P)
        pos2.append(float(e[:2]@e[:2]))
        yaw2.append(math.degrees(e[2])**2)
        nees.append(cov["pose_nees"]);n_head.append(cov["yaw_nees"]);n_xy.append(cov["conditional_xy_nees"])
        pose95.append(cov["covered95_pose"]);h95.append(cov["covered95_heading"])
        accepted[row["status"]]+=1
    return dict(n=len(steps),rmse_xy_m=float(np.sqrt(np.mean(pos2))),rmse_heading_deg=float(np.sqrt(np.mean(yaw2))),
                mean_pose_NEES=float(np.mean(nees)),mean_heading_NEES=float(np.mean(n_head)),
                mean_conditional_xy_NEES=float(np.mean(n_xy)),
                pose_coverage95=float(np.mean(pose95)),heading_coverage95=float(np.mean(h95)),
                gate_counts=dict(accepted))


def replay(p2: dict, case: dict, lut: HsLut,
           range_physical: np.ndarray, *, use_joint: bool, channel: str) -> tuple[list[dict], list[dict]]:
    """Recalculate B or C with corrected range only; same DR prior, same direct-s."""
    model = archived_direct_s_model(
        lut,anchor_xyz_m=tuple(case["anchor"]),
        tag_height_m=float(case["robot_z_m"]),
        mount_deg=float(case["mount_deg"]),
    )
    outputs=[]
    diagnostics=[]
    for i in range(len(p2["t_s"])):
        ekf=EKF3(p2["xminus"][i],p2["Pminus"][i])
        value=range_physical[i]
        mr = (float(value)+B_OLD if np.isfinite(value) and bool(p2["detected"][i]) else None)
        ms = float(p2["z_s"][i]) if bool(p2["detected"][i]) and np.isfinite(p2["z_s"][i]) else None
        if use_joint:
            step=ekf.update_joint(ms,mr,RS,RR,0.0,s_model=model,
                                  anchor_xyz_m=tuple(case["anchor"]),
                                  tag_height_m=float(case["robot_z_m"]),
                                  range_offset_m=B_OLD)
        else:
            step=ekf.update_range(mr,RR,anchor_xyz_m=tuple(case["anchor"]),
                                  tag_height_m=float(case["robot_z_m"]),
                                  range_offset_m=B_OLD)
        outputs.append(dict(x=step.post_x,P=step.post_P,status=step.status))
        diagnostics.append(dict(H=step.H,R=step.R,S=step.S,K=step.K,
                                innovation=step.innovation,NIS=step.NIS,
                                status=step.status))
    return outputs,diagnostics


def parity_with_p2(p2: dict, rows: list[dict], diagnostics: list[dict], arm: str) -> float:
    """B_OLD must reproduce the pre-existing P2 matrix trace exactly."""
    idx=P2_BASELINE[arm]
    worst=0.
    for i,(result,meta) in enumerate(zip(rows,diagnostics)):
        if result["status"] != str(p2["status"][i,idx]):
            raise RuntimeError(f"P2 {arm} gate status not reproduced at sample {i}")
        n=2 if arm=="C" and meta["H"] is not None and meta["H"].shape[0]==2 else 1
        for a,b in ((result["x"],p2["xplus"][i,idx]),(result["P"],p2["Pplus"][i,idx])):
            diff=float(np.max(np.abs(np.asarray(a)-b)))
            worst=max(worst,diff)
            if diff > 1e-9:
                raise RuntimeError(f"P2 {arm} posterior matrix mismatch k={i}: {diff}")
        for key,orig in (("H",p2["H"][i,idx,:n]),("R",p2["R"][i,idx,:n,:n]),
                         ("S",p2["S"][i,idx,:n,:n]),("K",p2["K"][i,idx,:,:n])):
            if meta[key] is None:
                if str(p2["status"][i,idx])!="skipped_missing":
                    raise RuntimeError("unexpected missing matrix in replay")
                continue
            val=np.asarray(meta[key]);diff=float(np.nanmax(np.abs(val-orig)))
            worst=max(worst,diff)
            if diff>1e-9:
                raise RuntimeError(f"P2 {arm} {key} mismatch k={i}: {diff}")
    return worst


def subset_metric(rows: list[dict], truth: np.ndarray, mask: np.ndarray) -> dict:
    ids=np.flatnonzero(mask)
    if not len(ids):
        raise RuntimeError("empty evaluation mask")
    return metrics_from_steps([rows[i] for i in ids],truth[ids])


def sample_slope(lut: HsLut, case: dict, states: np.ndarray) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    s_true=np.empty(len(states)); ds_dyaw_true=np.empty(len(states));ds_dyaw_prior=np.empty(len(states))
    for i,state in enumerate(states):
        v,j=s_model(lut,case["anchor"],case["robot_z_m"],*state,case["mount_deg"],with_jac=True)
        s_true[i]=float(v);ds_dyaw_true[i]=float(j[2])
    return s_true,ds_dyaw_true,ds_dyaw_prior


def write_csv(path: Path, rows: list[dict], compressed: bool = False) -> None:
    if not rows:
        raise RuntimeError(f"no rows for {path.name}")
    path.parent.mkdir(parents=True,exist_ok=True)
    columns=list(rows[0].keys())
    op=gzip.open if compressed else open
    with op(path,mode="wt",encoding="utf-8",newline="") as dest:
        writer=csv.DictWriter(dest,fieldnames=columns,extrasaction="ignore")
        writer.writeheader();writer.writerows(rows)


def run(*,p2_dir:Path,output_dir:Path,seed:int=0,include_los_e1_control:bool=True) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"output exists, preserving previous diagnostic: {output_dir}")
    if not p2_dir.is_dir():
        raise FileNotFoundError(f"P2_OUT directory missing: {p2_dir}")
    verified_p2=verify_p2_artifact_integrity(p2_dir, seed)
    p0=read_p0()
    if hash_file(P3_MODEL)!=P3_SHA256:
        raise RuntimeError("Frozen P3 E1 model hash does not match freeze addendum")
    p3=json.loads(P3_MODEL.read_text(encoding="utf-8"))
    if p3["chosen"]!="E1_on_B" or p3.get("feature_schema") is None:
        raise RuntimeError("Unexpected E1 model contract")
    lut=original_lut(p0)
    root_rf=p0["cases"]
    frequency=checked_path(p0,"results/DRIVE_SIM_20261007/POST_A23_RESULTS_20261010/SUPPLEMENT_01a12449/BLOCK_C/freqs_hz.npy")
    freqs=np.load(frequency,allow_pickle=False)
    bycase={}
    detector={}
    for case in root_rf:
        identifier=case["id"]
        for channel in ("los","full"):
            p2=load_p2_one_step(p2_dir,identifier,channel,seed)
            data_file=checked_path(p0,case[channel+"_path"])
            samples_path=checked_path(p0,case["samples_path"])
            samples=json.loads(samples_path.read_text(encoding="utf-8"))
            ids={int(s["pose_id"]):i for i,s in enumerate(samples)}
            if len(ids)!=len(samples):
                raise RuntimeError("duplicate pose_id in frozen samples")
            row_indexes=np.asarray([ids[int(pid)] for pid in p2["pose_id"]],int)
            H=np.load(data_file,mmap_mode="r",allow_pickle=False)
            measured=frozen_detector(H,freqs,float(case["mount_deg"]),O)
            assert_observation_parity(measured,p2,row_indexes)
            detector[identifier,channel]={
                key:np.asarray(arr)[row_indexes] for key,arr in measured.items()
            }
            bycase[identifier,channel]=p2
    # At this point all paired Full/LoS records exist, passed observation parity.
    all_metrics=[]; per_sample=[]; paired=[]; range_error_bins=[];n_replays=0;parity_max=0.
    example={}
    for case in root_rf:
        identifier=case["id"];route=case["route"];fold=p3["loro_fold_params"][route]
        full=bycase[identifier,"full"];los=bycase[identifier,"los"]
        f=detector[identifier,"full"];l=detector[identifier,"los"]
        if not np.array_equal(full["pose_id"],los["pose_id"]) or not np.array_equal(full["t_s"],los["t_s"]):
            raise RuntimeError(f"Full-LoS timeline not paired: {identifier}")
        if not np.array_equal(full["xminus"],los["xminus"]) or not np.array_equal(full["Pminus"],los["Pminus"]):
            raise RuntimeError(f"Full-LoS has different DR prior: {identifier}")
        t=np.asarray(full["t_s"]); eval_mask=t>=30.; n=len(t);truth=full["truth_for_offline_scoring_only"]
        if not np.array_equal(truth,los["truth_for_offline_scoring_only"]):
            raise RuntimeError(f"truth pairing mismatch {identifier}")
        anchor=np.asarray(case["anchor"],float)
        dist=np.linalg.norm(np.column_stack((truth[:,:2]-anchor[:2],np.full(n,case["robot_z_m"]-anchor[2]))),axis=1)
        flat=flat_eval_range(dist,freqs)
        e_flat=flat-dist
        e_ffd=los["z_r_m"]-flat
        e_mp=full["z_r_m"]-los["z_r_m"]
        if not np.allclose(e_flat+e_ffd+e_mp, full["z_r_m"]-dist,atol=1e-12,rtol=1e-12):
            raise RuntimeError("Flat/FFD/MP range causal identity failed")
        s_true=np.array([float(s_model(lut,case["anchor"],case["robot_z_m"],*x,case["mount_deg"])) for x in truth])
        s_mp=full["z_s"]-los["z_s"]
        s_lut=los["z_s"]-s_true
        if not np.allclose(s_mp+s_lut,full["z_s"]-s_true,atol=1e-12):
            raise RuntimeError("Full/LoS/LUT s identity failed")
        tap_switch=f["index"]!=l["index"]
        case_models={}
        for channel in ("los","full"):
            p2=bycase[identifier,channel]
            det=detector[identifier,channel]
            range_candidates=corrected_ranges(det,fold,allow_e1_on_los=include_los_e1_control,channel=channel)
            case_models[channel]=range_candidates
            d0=[dict(x=p2["xminus"][i],P=p2["Pminus"][i],status="DR_only") for i in range(n)]
            a=[dict(x=p2["xplus"][i,0],P=p2["Pplus"][i,0],status=str(p2["status"][i,0])) for i in range(n)]
            for arm,rows in (("D0",d0),("A",a)):
                m=subset_metric(rows,truth,eval_mask)
                all_metrics.append(dict(case=identifier,channel=channel,range_model="UNMODIFIED",arm=arm,**m))
            for name,phys in range_candidates.items():
                for arm in ("B","C"):
                    results,diag=replay(p2,case,lut,phys,use_joint=(arm=="C"),channel=channel)
                    n_replays+=n
                    if name=="B_OLD":
                        parity_max=max(parity_max,parity_with_p2(p2,results,diag,arm))
                    m=subset_metric(results,truth,eval_mask)
                    all_metrics.append(dict(case=identifier,channel=channel,range_model=name,arm=arm,**m))
                    for i in range(n):
                        if not eval_mask[i]:
                            continue
                        p_yaw=float(p2["xminus"][i,2])
                        e_pre=wrap(p_yaw-float(truth[i,2]))
                        e_post=wrap(float(results[i]["x"][2])-float(truth[i,2]))
                        dpsi=wrap(float(results[i]["x"][2])-p_yaw)
                        d_s=0.;d_r=0.
                        z=diag[i]
                        if z["status"]=="applied" and z["K"] is not None:
                            if arm=="C" and z["K"].shape[1]==2:
                                d_s=float(z["K"][2,0]*z["innovation"][0])
                                d_r=float(z["K"][2,1]*z["innovation"][1])
                            else:
                                d_r=float(z["K"][2,0]*z["innovation"][0])
                        if abs(wrap(dpsi-d_s-d_r))>1e-8:
                            raise RuntimeError(f"heading gain decomposition failed: {identifier} {i}")
                        exact_sq=(abs((e_pre+dpsi)-e_post)<1e-8)
                        per_sample.append(dict(
                            case=identifier,route=route,channel=channel,model=name,arm=arm,
                            pose_id=int(p2["pose_id"][i]),t_s=float(t[i]),status=z["status"],
                            anchor_range_m=float(dist[i]),tap_switch=int(tap_switch[i]),
                            rho_est_m=float(np.linalg.norm(p2["xminus"][i,:2]-anchor[:2])),
                            s_mp=float(s_mp[i]),s_lut=float(s_lut[i]),
                            prior_yaw_error_deg=math.degrees(e_pre),post_yaw_error_deg=math.degrees(e_post),
                            dpsi_s_deg=math.degrees(d_s),dpsi_r_deg=math.degrees(d_r),
                            dpsi_total_deg=math.degrees(dpsi),
                            mse_pre_deg2=math.degrees(e_pre)**2,mse_post_deg2=math.degrees(e_post)**2,
                            mse_cross_prior_s_deg2=2*math.degrees(e_pre)*math.degrees(d_s),
                            mse_cross_prior_r_deg2=2*math.degrees(e_pre)*math.degrees(d_r),
                            mse_s2_deg2=math.degrees(d_s)**2,mse_r2_deg2=math.degrees(d_r)**2,
                            mse_cross_sr_deg2=2*math.degrees(d_s)*math.degrees(d_r),
                            squared_identity_valid=int(exact_sq),
                            s_obs=float(p2["z_s"][i]),r_obs_raw_m=float(p2["z_r_m"][i]),
                            r_calibrated_m=float(phys[i]),
                            range_bias_residual_m=float(phys[i]-dist[i]),
                            NIS=safe_float(z["NIS"]),K_yaw_s=safe_float(z["K"][2,0]) if z["K"] is not None and arm=="C" and z["K"].shape[1]==2 else None,
                            K_yaw_r=safe_float(z["K"][2,-1]) if z["K"] is not None else None,
                            Ppost_yaw_rad2=float(results[i]["P"][2,2])
                        ))
            # Original heading-only A must be IDENTICAL for all range corrections.
            # It is deliberately not re-run; any perceived A improvement from E1 range
            # would signal an evaluation leak or a changed prior/measurement model.
        for i in np.flatnonzero(eval_mask):
            full_s=float(full["z_s"][i]);los_s=float(los["z_s"][i])
            h_s_prior=float(s_model(lut,case["anchor"],case["robot_z_m"],*full["xminus"][i],case["mount_deg"]))
            if abs((full_s-h_s_prior) - (s_mp[i]+s_lut[i]+s_true[i]-h_s_prior)) >1e-9:
                raise RuntimeError("full s innovation decomposition failed")
            prior_psi=wrap(float(full["xminus"][i,2])-float(truth[i,2]))
            for channel,p2 in (("los",los),("full",full)):
                model_s_channel=channel
                row_a=0
                applied=p2["status"][i,row_a]=="applied"
                gain=p2["K"][i,row_a,2,0]
                delta_psi=wrap(float(p2["xplus"][i,row_a,2])-float(p2["xminus"][i,2]))
                e_after=wrap(float(p2["xplus"][i,row_a,2])-float(truth[i,2]))
                paired.append(dict(case=identifier,route=route,channel=model_s_channel,pose_id=int(p2["pose_id"][i]),t_s=float(t[i]),
                    distance_m=float(dist[i]),tap_full=int(f["index"][i]),tap_los=int(l["index"][i]),tap_switch=int(tap_switch[i]),
                    tap_fraction_true=float((dist[i]/tap_metres(freqs))%1),
                    e_flat_m=float(e_flat[i]),e_ffd_m=float(e_ffd[i]),e_mp_m=float(e_mp[i]),
                    e_raw_full_m=float(full["z_r_m"][i]-dist[i]),e_raw_los_m=float(los["z_r_m"][i]-dist[i]),
                    e_range_B_full_m=float(full["z_r_m"][i]-B_OLD-dist[i]),
                    e_s_mp=float(s_mp[i]),e_s_lut=float(s_lut[i]),e_s_full_model=float(full_s-s_true[i]),
                    s_obs=float(p2["z_s"][i]),s_loS=los_s,s_true_lut=float(s_true[i]),
                    h_s_prior=float(h_s_prior),s_innovation=float(p2["z_s"][i]-h_s_prior),
                    H_s_x=float(p2["H"][i,0,0,0]),H_s_y=float(p2["H"][i,0,0,1]),H_s_psi=float(p2["H"][i,0,0,2]),
                    K_psi_s=float(gain),Pprior_psi=float(p2["Pminus"][i,2,2]),
                    accepted_s=int(applied),NIS_s=safe_float(p2["NIS"][i,0]),
                    dpsi_s_deg=math.degrees(delta_psi),prior_heading_err_deg=math.degrees(prior_psi),
                    post_heading_err_deg=math.degrees(e_after),
                    heading_harmed=int(applied and abs(e_after)>abs(prior_psi)+1e-12),
                    first_mag=float(detector[identifier,channel]["first_mag"][i]),
                    peak=float(detector[identifier,channel]["peak"][i])
                ))
        for channel in ("los","full"):
            r=case_models[channel]
            for k,name in enumerate(r):
                resid=r[name][eval_mask]-dist[eval_mask]
                mid=dist[eval_mask]
                for a,b,label in ((0,5,"lt5m"),(5,10,"5to10m"),(10,np.inf,"ge10m")):
                    selected=(mid>=a)&(mid<b)&np.isfinite(resid)
                    if selected.sum()==0:
                        continue
                    v=resid[selected]
                    range_error_bins.append(dict(case=identifier,channel=channel,correction=name,distance_bin=label,
                        n=int(len(v)),mean_residual_m=float(np.mean(v)),sd_residual_m=float(np.std(v)),
                        rms_residual_m=float(np.sqrt(np.mean(v*v))),p95_abs_m=float(np.quantile(np.abs(v),.95))))
        if not example:
            example={"case":identifier,"seed":seed,"method":"P2 existing common prior; offline counterfactual range-only correction"}
        print(f"[{identifier}] paired LoS/Full, flat+FFD+MP, one-step B/C replays verified",flush=True)
    output_dir.mkdir(parents=True,exist_ok=False)
    write_csv(output_dir/"D0_D1_METRICS.csv",all_metrics)
    write_csv(output_dir/"D2_HEADING_DECOMPOSITION.csv.gz",per_sample,compressed=True)
    write_csv(output_dir/"D3_FLAT_FFD_MP_AND_POLARIZATION.csv.gz",paired,compressed=True)
    write_csv(output_dir/"D4_RANGE_RESIDUAL_BY_DISTANCE.csv",range_error_bins)

    # D4: correlation/temporal audit is descriptive within the frozen corridor.
    rows_corr=[]
    for case in root_rf:
        identifier=case["id"]
        orig=[r for r in paired if r["case"]==identifier and r["channel"]=="full"]
        def correlation(a,b):
            a=np.asarray(a,float);b=np.asarray(b,float)
            if len(a)<3 or np.std(a)<=0 or np.std(b)<=0:return None
            return float(np.corrcoef(a,b)[0,1])
        rows_corr.append(dict(
            case=identifier,n=len(orig),
            corr_eRangeMp_eSMp=correlation([q["e_mp_m"] for q in orig],[q["e_s_mp"] for q in orig]),
            lag1_eRangeMp=correlation([q["e_mp_m"] for q in orig[:-1]],[q["e_mp_m"] for q in orig[1:]]),
            lag1_eSMp=correlation([q["e_s_mp"] for q in orig[:-1]],[q["e_s_mp"] for q in orig[1:]]),
            tap_switch_rate=float(np.mean([q["tap_switch"] for q in orig])),
            A_s_accepted_rate=float(np.mean([q["accepted_s"] for q in orig])),
            A_accepted_harmed_rate=float(
                np.mean([q["heading_harmed"] for q in orig if q["accepted_s"]])
            ) if any(q["accepted_s"] for q in orig) else None,
        ))
    write_csv(output_dir/"D4_CROSS_CHANNEL_AND_TEMPORAL_AUDIT.csv",rows_corr)

    # Aggregate correlated rows only descriptively; never treat as independent RF draws.
    by_arm=defaultdict(list)
    for row in all_metrics:
        by_arm[row["channel"],row["range_model"],row["arm"]].append(row)
    aggregate=[]
    for (ch,range_model,arm),grp in sorted(by_arm.items()):
        aggregate.append(dict(channel=ch,range_model=range_model,arm=arm,case_count=len(grp),
            avg_of_case_rmse_xy_m=float(np.mean([r["rmse_xy_m"] for r in grp])),
            avg_of_case_rmse_heading_deg=float(np.mean([r["rmse_heading_deg"] for r in grp])),
            avg_of_case_pose_NEES=float(np.mean([r["mean_pose_NEES"] for r in grp])),
            avg_of_case_pose95_coverage=float(np.mean([r["pose_coverage95"] for r in grp])),
        ))
    write_csv(output_dir/"D0_D4_ARM_SUMMARY_DESCRIPTIVE.csv",aggregate)
    manifest={
        "schema":"EKF3_DIAG_D0_D4_V1",
        "status":"DIAGNOSTIC_EXECUTED_NO_SCIENTIFIC_PASS",
        "seed":seed,"source_P2":str(p2_dir),"P2_seed":seed,
        "P0_sha256":hash_file(P0_PATH),"P3_frozen_model_sha256":hash_file(P3_MODEL),
        "P2_artifact_integrity":verified_p2,
        "anchor_case_count":len(root_rf),
        "case_channel_count":len(root_rf)*2,
        "replayed_B_C_one_step_count":n_replays,
        "B0_matrix_max_abs_replay_difference":parity_max,
        "range_arms":["B_OLD","C_CONST_LOS","D1_FRACTIONAL","E1_FULL_LORO","E1_ON_LOS_NEGCTRL"],
        "observation_parity":"PASS_ALL_CASES_FULL_AND_LOS",
        "range_noise_model":"original R0 fixed, Q and DR prior unchanged; diagnostic only",
        "A_heading_only":"unchanged by any range-only correction; original P2 A",
        "flat_detector":"oracle-only synthesized flat-spectrum H from truth d; no oracle input into filter",
        "model_e1":"P3 route-held-out frozen coefficient; online H CIR features; not re-fit",
        "range_E1_scope":"Full RF; LoS only as explicit negative control",
        "time_correlation":"lag1 is descriptive under shared RF trajectory, not iid ensemble",
        "extra_unresolved":["same corridor","strong RF site/time correlation","uncalibrated R_s and R_sr","same-DR one-step, not recursive EKF","no independent held-out scene"],
        "scientific_PASS":False,
        "outputs":{},
    }
    for file in sorted(output_dir.iterdir()):
        if file.is_file():
            manifest["outputs"][file.name]={"sha256":hash_file(file),"bytes":file.stat().st_size}
    (output_dir/"D0_D4_RUN_MANIFEST.json").write_text(
        json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"
    )
    return manifest


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--p2-dir",type=Path,required=True,help="Extracted P2_OUT directory from Actions artifact")
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--seed",type=int,default=0)
    p.add_argument("--skip-los-e1-negative-control",action="store_true")
    args=p.parse_args()
    result=run(p2_dir=args.p2_dir.resolve(),output_dir=args.out.resolve(),
               seed=args.seed,
               include_los_e1_control=not args.skip_los_e1_negative_control)
    print(json.dumps({key:result[key] for key in (
        "status","anchor_case_count","replayed_B_C_one_step_count",
        "B0_matrix_max_abs_replay_difference","observation_parity",
        "scientific_PASS",
    )},indent=2,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
