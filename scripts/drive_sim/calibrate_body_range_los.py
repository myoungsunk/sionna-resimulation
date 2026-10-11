#!/usr/bin/env python3
"""Independent, FFD-based LoS first-arrival *measurement* range calibration.

Input: frozen FFD banks, bank manifest, predeclared OTHER physical sites.
Never reads RF evaluation run, its true pose, ranges, EKF states, or labels.
Fits a robust constant additive prediction offset b = detector_range - geometric_range
per mount, with site-disjoint train and holdout grids. Reports detector-only flat
spectrum biases as a control; no claim of measuring hardware antenna group delay.

The source's exact Hann -> 4N IFFT -> 30% leading-edge receiver is reused.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from qclean_uwb.drivesim import observation as O
from qclean_uwb.drivesim import hs_lut as L
from qclean_uwb.drivesim.pattern_apply import Bank
from qclean_uwb.scenarios.corridor import CorridorSetup

# These XY groups were fixed before accessing the heldout (x=7, y=0.1) RF
# outcome. Each is a *distinct* physical site, not thermal repetitions.
TRAIN_SITES = (
    (2.20, -0.45), (2.80, 0.30), (3.40, -0.35),
    (4.90, 0.45), (5.30, -0.48), (5.90, 0.33),
    (8.10, -0.37), (8.70, 0.45), (9.60, -0.31),
    (10.50, 0.42), (11.40, -0.40), (12.90, 0.29),
    (14.20, -0.35), (15.30, 0.40), (17.10, -0.22),
)
VALID_SITES = (
    (2.50, 0.35), (3.90, -0.43), (5.65, 0.45),
    (8.50, -0.47), (10.90, 0.35), (13.50, -0.22),
    (16.20, 0.32),
)
YAW_DEG = (0., 10., 20.)
CALIBRATION_EXCLUSION_XY = (7., 0.1)
MIN_EXCLUSION_M = 0.70


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def load_verified_banks(bank_dir, manifest):
    bdir = Path(bank_dir)
    mp = Path(manifest)
    doc = json.loads(mp.read_text(encoding="utf8"))
    expected = doc["npz_sha256"]
    banks, bank_hashes = [], {}
    for port in ("LP_plus45", "LP_minus45"):
        p = bdir / (port + "_bank.npz")
        with p.open("rb") as stream:
            if stream.read(64).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError("LFS_POINTER_NOT_A_BANK: " + str(p))
        digest = sha256(p)
        if digest != expected[p.name]:
            raise ValueError("FFD_SHA_MISMATCH " + p.name)
        with np.load(p, allow_pickle=False) as n:
            data = {k:n[k] for k in n.files}
        banks.append(Bank(data))
        bank_hashes[p.name] = digest
    f = banks[0].freqs_hz
    if f.shape != (257,) or not np.array_equal(f, banks[1].freqs_hz):
        raise ValueError("BANK_FREQ_PARITY_FAILURE")
    if not np.isfinite(f).all() or not np.all(np.diff(f)>0):
        raise ValueError("BANK_NONMONOTONIC_FREQUENCIES")
    return banks, dict(bank_sha256=bank_hashes, bank_manifest_sha256=sha256(mp))


def flat_los_detected_range(distance_m, freqs_hz):
    f = np.asarray(freqs_hz,float)
    phase = np.exp(-2j * np.pi * f * distance_m / O.C0)
    h = np.zeros((1,len(f),2,2),complex)
    h[0,:,0,0] = phase
    h[0,:,1,0] = phase
    return float(O.observe(h,f,None,None,tx=0)["range_m"][0])


def one_site(banks, anchor_x_m, x_m, y_m, body_yaw_deg, mount_deg):
    setup = CorridorSetup(anchor_x_m=float(anchor_x_m))
    x,y=float(x_m),float(y_m)
    if not (setup.robot_x_range_m[0]<=x<=setup.robot_x_range_m[1]) or abs(y)>setup.robot_y_limit_m:
        raise ValueError("CALIBRATION_SITE_OUTSIDE_SCENE")
    d = setup.robot_position(x,y) - setup.anchor_position
    distance = float(np.linalg.norm(d))
    H = L.los_h(banks,d/distance,body_yaw_deg+mount_deg,dist_m=distance)
    f = banks[0].freqs_hz
    obs = O.observe(H[None],f,None,None,tx=0)
    meas = float(obs["range_m"][0])
    control = flat_los_detected_range(distance,f)
    if not math.isfinite(meas):
        raise ValueError("LoS detector produced nonfinite measurement")
    return dict(x_m=x,y_m=y,body_yaw_deg=float(body_yaw_deg),
        rx_mount_deg=float(mount_deg),geometric_range_m=distance,
        detector_los_range_m=meas,detector_flat_range_m=control,
        ffd_los_bias_m=meas-distance,flat_detector_bias_m=control-distance,
        ffd_minus_flat_detector_m=meas-control,
        first_arrival_tap=int(obs["index"][0]),rx0_power=float(obs["power"][0,0]),
        rx1_power=float(obs["power"][0,1]))


def robust_fit_and_validation(train,valid):
    tr=np.asarray([r["ffd_los_bias_m"] for r in train],float)
    va=np.asarray([r["ffd_los_bias_m"] for r in valid],float)
    if not len(tr) or not len(va):raise ValueError("empty calibration or independent holdout")
    b=float(np.median(tr))
    residual=va-b
    return dict(range_offset_m=b, model="CONSTANT_FIRST_ARRIVAL_LOS_OFFSET",
        convention="forward model h_range = geometric_3D_range + range_offset_m",
        n_train_sites=len(set((r["x_m"],r["y_m"]) for r in train)),
        n_train_observations=len(train),
        n_holdout_sites=len(set((r["x_m"],r["y_m"]) for r in valid)),
        n_holdout_observations=len(valid),
        training_bias_median_m=b,
        training_bias_mean_m=float(np.mean(tr)),
        training_bias_sd_m=float(np.std(tr,ddof=1)),
        holdout_bias_mean_m=float(np.mean(va)),
        holdout_residual_mean_m=float(np.mean(residual)),
        holdout_residual_rmse_m=float(np.sqrt(np.mean(residual**2))),
        holdout_abs_residual_p95_m=float(np.quantile(np.abs(residual),.95)),
        holdout_abs_residual_max_m=float(np.max(np.abs(residual))),
        flat_only_mean_bias_m=float(np.mean([r["flat_detector_bias_m"] for r in train])),
        ffd_vs_flat_mean_delta_m=float(np.mean([r["ffd_minus_flat_detector_m"] for r in train])),
        prereg_holdout_rmse_limit_m=0.15,
        prereg_holdout_p95_limit_m=0.25,
        independent_site_validation_pass=bool(np.sqrt(np.mean(residual**2))<=.15
                                              and np.quantile(np.abs(residual),.95)<=.25),
        disclaimer="No test location used; receiver noise or multipath variance NOT tuned here")


def calibrate(banks,*,anchor_x_m=4.,exclude_xy=CALIBRATION_EXCLUSION_XY,
              mounts_deg=(0.,45.)):
    xy=np.asarray(exclude_xy,float)
    if xy.shape!=(2,) or not np.isfinite(xy).all():raise ValueError("bad evaluation exclusion")
    sites=TRAIN_SITES+VALID_SITES
    if len(set(sites))!=len(sites):
        raise ValueError("CALIBRATION_TRAIN_HOLDOUT_XY_OVERLAP")
    if min(np.linalg.norm(np.asarray(s)-xy) for s in sites)<=MIN_EXCLUSION_M:
        raise ValueError("CALIBRATION_SITE_TOO_CLOSE_TO_EVALUATION_XY")
    records=[];models={}
    for m in mounts_deg:
        train=[one_site(banks,anchor_x_m,*s,yaw,m) for s in TRAIN_SITES for yaw in YAW_DEG]
        valid=[one_site(banks,anchor_x_m,*s,yaw,m) for s in VALID_SITES for yaw in YAW_DEG]
        records += [dict(r,split="TRAIN_OTHER_XY") for r in train]
        records += [dict(r,split="HOLDOUT_OTHER_XY") for r in valid]
        models[str(int(m)) if float(m).is_integer() else str(m)] = robust_fit_and_validation(train,valid)
    return records,models


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bank-dir",type=Path,required=True)
    ap.add_argument("--bank-manifest",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--anchor-x-m",type=float,default=4.)
    ap.add_argument("--exclude-evaluation-xy",type=float,nargs=2,default=[7.,.1])
    ap.add_argument("--mounts-deg",type=float,nargs="+",default=[0.,45.])
    args=ap.parse_args()
    if args.out.exists():raise FileExistsError("calibration never overwrites existing output")
    banks,bankreceipt=load_verified_banks(args.bank_dir,args.bank_manifest)
    observations,models=calibrate(banks,anchor_x_m=args.anchor_x_m,
        exclude_xy=args.exclude_evaluation_xy,mounts_deg=args.mounts_deg)
    meta=dict(schema_version="INDEPENDENT_FFD_LOS_DETECTOR_CAL_V1",
        status="INDEPENDENT_SITES_CALIBRATED_NOT_HARDWARE_VALIDATED",
        source="analytic direct FFD LoS from frozen banks, same receiver threshold and window",
        anchor_x_m=args.anchor_x_m,
        train_site_xy=[list(x) for x in TRAIN_SITES],
        holdout_site_xy=[list(x) for x in VALID_SITES],
        yaw_deg=list(YAW_DEG),evaluation_xy_exclusion=list(args.exclude_evaluation_xy),
        min_evaluation_exclusion_m=MIN_EXCLUSION_M,mount_models=models,
        frequencies_sha256=hashlib.sha256(np.ascontiguousarray(banks[0].freqs_hz).tobytes()).hexdigest(),
        receiver_source_sha256=sha256(ROOT/"src/qclean_uwb/drivesim/observation.py"),
        los_source_sha256=sha256(ROOT/"src/qclean_uwb/drivesim/hs_lut.py"),
        calibration_source_sha256=sha256(Path(__file__)),
        full_native_pathsolver="NOT_INVOKED_IN_CALIBRATION",
        true_evaluation_RF_input="NOT_USED",
        pathsolver_los_parity="REQUIRES_INDEPENDENT_POST_FIT_CHECK",
        physical_antenna_group_delay="NOT_SEPARATELY_IDENTIFIED",
        scientific_PASS=False,F01="OPEN",F02="OPEN",**bankreceipt)
    canonical=json.dumps(meta,sort_keys=True,separators=(",",":"),allow_nan=False)
    meta["calibration_sha256"]=hashlib.sha256(canonical.encode()).hexdigest()
    args.out.mkdir(parents=True,exist_ok=False)
    p=args.out/"OTHER_SITE_LOS_CALIBRATION.csv"
    with p.open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=list(observations[0]))
        writer.writeheader();writer.writerows(observations)
    (args.out/"INDEPENDENT_LOS_CALIBRATION.json").write_text(
        json.dumps(meta,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf8")
    print(json.dumps(dict(status="CALIBRATED",models=models,
        n_observations=len(observations),
        scientific_PASS=False),ensure_ascii=False,allow_nan=False),flush=True)


if __name__=="__main__":
    main()
