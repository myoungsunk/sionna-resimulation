#!/usr/bin/env python3
"""Create an immutable, independently calibrated native-Sionna run config.

Only accepted independent other-XY FFD LoS calibration may set range_offset.
No filter noise Q, R, gate, threshold or RF s policy is changed. This file
prepares a future actual-PathSolver run; --execute-native remains explicit in
run_body_probe_v2_cloud.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def load_validated_model(calibration, mount):
    meta=json.loads(Path(calibration).read_text(encoding="utf8"))
    sig=meta.get("calibration_sha256","")
    raw={k:v for k,v in meta.items() if k!="calibration_sha256"}
    actual=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()
    if sig!=actual or meta.get("true_evaluation_RF_input")!="NOT_USED":
        raise ValueError("CALIBRATION_PROVENANCE_ORACLE_OR_HASH_FAILURE")
    key=str(int(mount)) if float(mount).is_integer() else str(mount)
    model=meta["mount_models"].get(key)
    if model is None or not model["independent_site_validation_pass"]:
        raise ValueError("INDEPENDENT_HOLDOUT_CALIBRATION_NOT_PASSED_FOR_MOUNT")
    return meta,model


def prepare(template, calibration, *, mount_deg, seed, slip_mode, prior_random_seed=None):
    cfg=json.loads(Path(template).read_text(encoding="utf8"))
    meta,model=load_validated_model(calibration,mount_deg)
    expected=cfg["cloud_assets"]["bank_sha256"]
    if expected!=meta["bank_sha256"]:
        raise ValueError("CALIBRATION_AND_RUN_BANK_SHA_DO_NOT_MATCH")
    if cfg["cloud_assets"]["manifest_sha256"]!=meta["bank_manifest_sha256"]:
        raise ValueError("CALIBRATION_AND_RUN_FFD_MANIFEST_DIFFER")
    if cfg["rf"]["mode"]!="range_only":
        raise ValueError("RANGE_ONLY_CALIBRATION_REQUIRES_RANGE_ONLY_FILTER")
    if slip_mode not in ("neutral","hypothesis"):
        raise ValueError("SLIP_MUST_BE_EXPLICIT_NEUTRAL_OR_UNCALIBRATED_HYPOTHESIS")
    cfg["rf"]["mount_deg"]=float(mount_deg)
    cfg["sensor"]["seed"]=int(seed)
    cfg["initial_filter"]["range_offset_m"]=float(model["range_offset_m"])
    cfg["physical"]["slip_mode"]=slip_mode
    if slip_mode=="hypothesis":
        # GUARANTEED nonzero right-wheel slip with a lateral ICR offset.
        # Scenario ONLY; never present as measured TurtleBot3 coefficient.
        cfg["physical"]["baseline_slip_left"]=0.0
        cfg["physical"]["baseline_slip_right"]=.05
        cfg["physical"]["baseline_icr_offset_m"]=.005
        cfg["physical"]["physical_slip_event_rate_per_s"]=.0502516793
        cfg["physical"]["physical_slip_mean_duration_s"]=.15
        cfg["physical"]["physical_slip_event_longitudinal_scale"]=.02
        cfg["physical"]["physical_slip_event_icr_scale_m"]=.005
    else:
        cfg["physical"]["baseline_slip_left"]=0.0
        cfg["physical"]["baseline_slip_right"]=0.0
        cfg["physical"]["baseline_icr_offset_m"]=0.0
    if prior_random_seed is not None:
        # The distribution is centred on externally specified nominal x0, not
        # on an oracle physical pose encountered later in the run.
        nominal=np.asarray(cfg["initial_filter"]["x0"],float)
        rng=np.random.default_rng([2301026,int(prior_random_seed)])
        offset=rng.normal(size=3)*np.array([.10,.10,math.radians(5.)])
        nominal[:3]+=offset
        cfg["initial_filter"]["x0"]=nominal.tolist()
        cfg["prior_sampling"]=dict(model="nominal_position_independent_stochastic_prior",
            prior_random_seed=int(prior_random_seed),
            init_covariance_unchanged=True,
            true_run_pose_not_read=True)
    cfg["calibration_provenance"]=dict(
        model="other-site analytic FFD LoS first-arrival",
        calibration_sha256=meta["calibration_sha256"],
        validation_passed=True,
        train_site_xy=meta["train_site_xy"],
        holdout_site_xy=meta["holdout_site_xy"],
        evaluation_site_exclusion=meta["evaluation_xy_exclusion"],
        offset_m=float(model["range_offset_m"]),
        Q_R_gate_unchanged=True,
        no_evaluation_oracle_used=True)
    cfg["status"]="CALIBRATED_RANGE_NATIVE_SIONNA_NOT_YET_RUN"
    cfg["claims"]["scientific_PASS"]=False
    return cfg


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--template",type=Path,required=True)
    p.add_argument("--calibration",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--mount-deg",type=float,default=0.)
    p.add_argument("--seed",type=int,default=0)
    p.add_argument("--slip-mode",choices=("neutral","hypothesis"),default="neutral")
    p.add_argument("--randomize-prior-seed",type=int)
    a=p.parse_args()
    if a.out.exists():raise FileExistsError("NO_OVERWRITE_CONFIG")
    out=prepare(a.template,a.calibration,mount_deg=a.mount_deg,seed=a.seed,
                slip_mode=a.slip_mode,prior_random_seed=a.randomize_prior_seed)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out,indent=2,allow_nan=False)+"\n")
    print(json.dumps(dict(status=out["status"],range_offset_m=out["initial_filter"]["range_offset_m"],
        mount_deg=out["rf"]["mount_deg"],slip_mode=out["physical"]["slip_mode"],
        scientific_PASS=False)))


if __name__=="__main__":main()
