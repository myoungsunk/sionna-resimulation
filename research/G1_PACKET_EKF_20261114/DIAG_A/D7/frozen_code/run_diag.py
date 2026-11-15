"""Run frozen G1-DIAG-003 D4/D5/D6/D1/D2/D3 after corrected S0."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import sys
import traceback

# One BLAS worker per case, with cases distributed independently by the driver.
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import numpy as np
import scipy

from diag_inputs import (WORK, BASE, STAGED, CASES, COHORTS, anchor_evidence,
                         control_paths, init_modules, load_case, sha256, stage, verify_s0)
from diag_mechanism import decompose_d1, phase_configs, phase_summary, synthetic_checks
from diag_metrics import (checkpoints, paired_bootstrap, score_sufficient, trajectory_statistics,
                          synthetic_checks as check_metrics, RATE_COLUMNS, site_totals,
                          bootstrap_design, bootstrap_totals, _intervals)
from diag_replay import replay, wrap
from diag_spatial import clean_channels, moving_mean, spatial_summary, distance_variogram


def utc():
    return datetime.now(timezone.utc).isoformat()


def serial(value):
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return serial(value.tolist())
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    if isinstance(value, np.generic):
        return serial(value.item())
    return None if isinstance(value, float) and not np.isfinite(value) else value


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(serial(value), ensure_ascii=False, allow_nan=False,
                                    indent=2)+"\n", encoding="utf-8")
    temporary.replace(path)


def run(data, level, sign, configs, *, seeds=range(20), **kwargs):
    controls, initial, bias = control_paths(data, level, sign, seeds)
    args = [data[k] for k in ("model", "case", "z", "mu", "R", "t")]
    return replay(*args, controls, initial, configs, ffd=data["ffd"], **kwargs), bias


def stats(result, data, cp, bias):
    a = result
    idx = cp["checkpoint_index"]
    out = trajectory_statistics(a["state"], a["covariance"], a["accepted"], a["joint"],
                                 data["t"], data["pose"], bias, cp["checkpoint_index"], a["proposal"])
    error = a["state"][:,idx].copy()
    error[:,:, :3] -= data["pose"][None,idx]
    error[:,:,2] = wrap(error[:,:,2])
    error[:,:,3] -= bias
    out["checkpoint_error"] = error
    out["checkpoint_covariance"] = a["covariance"][:,idx]
    return out


def parity(data, name):
    actual, _ = run(data, "B0", 0, [(1, 0)], seeds=[0])
    reference = data["reference"]
    if reference is None:
        from r2_bias_replay import run_filters, METHODS
        from p3_rf_adapter4 import FrozenLut
        controls, x0, _ = control_paths(data, "B0", 0, [0])
        controls = {k: v[0] for k,v in controls.items()}
        controls["dt_s"] = np.r_[0., np.diff(data["t"])]
        src = run_filters(data["t"], controls, data["z"], data["case"], FrozenLut(BASE/"source"),
                          x0[0])["recursive"]
        j = METHODS.index("J4")
        reference = {"state": src["estimate"][:, j], "cov": src["covariance"][:, j],
                     "accepted": src["status"][:, j] == "APPLIED", "nis": src["nis"][:, j]}
    comparisons = {}
    for field, old in (("state", "state"), ("covariance", "cov"), ("nis", "nis")):
        new, ref = actual[field][0], reference[old]
        delta = new-ref
        if field == "state":
            delta[:, 2] = wrap(delta[:, 2])
        comparisons[field] = float(np.max(np.abs(delta)))
    comparisons["accepted_mask_difference"] = int(np.count_nonzero(actual["accepted"][0] != reference["accepted"]))
    mask = data["t"] >= 30
    error = wrap(actual["state"][0,mask,2]-data["pose"][mask,2])
    comparisons["heading_rmse_deg"] = float(np.degrees(np.sqrt(np.mean(error**2))))
    expected_report = {"R2_aA_m0": ("7.49", 2), "R4_aB_m0": ("1.323", 3), "R5_aB_m0": ("2.541", 3)}
    check_rounding = (name not in expected_report or
                      f"{comparisons['heading_rmse_deg']:.{expected_report[name][1]}f}" == expected_report[name][0])
    # Verifies a new batch implementation against the original scalar/reference path.
    # This implementation check does not change either S0 historical gate.
    comparisons["status"] = ("PASS" if comparisons["state"] <= 2e-10
                             and comparisons["covariance"] <= 2e-10
                             and comparisons["nis"] <= 2e-8
                             and comparisons["accepted_mask_difference"] == 0 and check_rounding else "FAIL")
    return comparisons


def d4(data, cp, path):
    distance, pose = cp["distance_m"], data["pose"]
    full = np.load(data["h_full"], mmap_mode="r", allow_pickle=False)[data["position"]]
    los = np.load(data["h_los"], mmap_mode="r", allow_pickle=False)[data["position"]]
    channels = clean_channels(full, los, np.load(data["frequencies"], allow_pickle=False))
    error = channels["error"]
    pose4 = np.column_stack([pose, np.zeros(len(pose))])
    true_prediction, jacobian = (np.concatenate(items) for items in zip(*[
        data["model"](pose4[start:start+64], data["case"]) for start in range(0, len(pose), 64)
    ]))
    evaluate = data["t"] >= 30
    result = spatial_summary(distance, pose, error, jacobian[:,1,2],
                             evaluation_mask=evaluate, rotation_mask=data["rotation"])
    windows = {m: moving_mean(distance, pose, error, m) for m in (2, 5, 10)}
    if not all(np.isfinite(w["mean"]).all() for w in windows.values()):
        raise ValueError("Undefined oracle correction window")
    xy = pose[:, :2] - np.asarray(data["case"]["anchor"][:2])
    rho = np.linalg.norm(xy, axis=1)
    # Nearest-node bins with fixed midpoints between the original five knots.
    nodes = np.array([0, 1.5, 3, 6, 10])
    bins = np.searchsorted((nodes[1:]+nodes[:-1])/2, rho)
    result["distance_scale"] = [
        {"rho_m": float(node), "n_timeline_packets": int(np.count_nonzero(bins == i)),
         "s_rms": float(np.sqrt(np.mean(error[bins == i]**2))) if (bins == i).any() else None}
        for i, node in enumerate(nodes)
    ]
    range_residual = data["z"][:, 0]-data["mu"][:, 0]-true_prediction[:, 0]
    result["range_residual_variogram"] = distance_variogram(distance, pose, range_residual)
    result["range_residual_variance_m2"] = float(np.var(range_residual))
    result["jacobian_straight_rotation_abs_quantiles"] = {
        key: np.quantile(abs(jacobian[mask,1,2]), [.05,.5,.95]).tolist() if mask.any() else None
        for key, mask in (("straight", evaluate & ~data["rotation"]), ("rotation", evaluate & data["rotation"]))
    }
    np.savez_compressed(path/"D4_PACKET_WINDOW.npz", pose=pose, t=data["t"], distance_m=distance,
                        ds_dpsi=jacobian[:,1,2], **channels, **{
        f"W{w}_{key}": arr for w, record in windows.items() for key, arr in record.items()})
    write_json(path/"D4_SPATIAL.json", result)
    return windows, data["z"]-data["mu"]-true_prediction, result


def bootstrap_phase_comparison(cp_first, cp_second, site):
    grouped = [site_totals(a, site) for a in cp_first]
    design = bootstrap_design(*grouped[0].shape[:2])
    result = []
    for group in (grouped, [site_totals(a, site) for a in cp_second]):
        points = score_sufficient(np.stack([a.sum(axis=(0,1)) for a in group]))
        rep = {key: [] for key in RATE_COLUMNS}
        for a in group:
            scored = score_sufficient(bootstrap_totals(a, design))
            for key in RATE_COLUMNS:
                rep[key].append(scored[key])
        point = {key: average_finite(points[key]) for key in RATE_COLUMNS}
        result.append((point, {k: average_finite(np.asarray(v)) for k,v in rep.items()}))
    a,b = result
    delta = _intervals({k:a[0][k]-b[0][k] for k in RATE_COLUMNS},
                       {k:a[1][k]-b[1][k] for k in RATE_COLUMNS})
    return {"A": _intervals(*a), "B": _intervals(*b), "A_minus_B": delta}


def average_finite(a):
    count = np.isfinite(a).sum(axis=0)
    return np.divide(np.nansum(a, axis=0), count, out=np.full(np.shape(count), np.nan), where=count>0)


def phase_runs(data, cp, level, sign, width, windows, base_stats):
    config = phase_configs()
    frames, points, gate, errors, covariances = [], [], [], [], []
    # Batch 11 phases x 20 seed paths with one observer call per packet.
    for a in range(0, len(config), 11):
        group = list(config[a:a+11])
        result, bias = run(data, level, sign, group, oracle=windows[width]["mean"] if width else None)
        s = stats(result, data, cp, bias)
        frames.extend(s["frame"].reshape(len(group),20,-1))
        points.extend(s["checkpoint"].reshape(len(group),20,len(cp["checkpoint_index"]),-1))
        errors.extend(s["checkpoint_error"].reshape(len(group),20,len(cp["checkpoint_index"]),4))
        covariances.extend(s["checkpoint_covariance"].reshape(len(group),20,len(cp["checkpoint_index"]),4,4))
        accepted = result["accepted"] & result["joint"]
        gate.extend(np.packbits(accepted, axis=-1).reshape(len(group),20,-1))
    frame, point = np.stack(frames), np.stack(points)
    if width == 0:
        np.testing.assert_allclose(frame[0], base_stats["frame"], rtol=1e-8, atol=1e-8,
                                   err_msg="D2 m=1 baseline changed")
        np.testing.assert_allclose(point[0], base_stats["checkpoint"], rtol=1e-8, atol=1e-8,
                                   err_msg="D2 m=1 checkpoint baseline changed")
    return frame, point, np.stack(gate), np.stack(errors), np.stack(covariances)


def phase_report(data, cp, frame, point, comparison, *, gate=None, original_gate=None):
    result = []
    keys = ("heading_rmse_deg", "heading95_coverage", "heading_nees_mean", "range_proposed",
            "range_accepted", "s_proposed", "s_accepted")
    all_rows = []
    for i, (m,p) in enumerate(phase_configs()):
        u = cp["distance_m"][np.arange(len(data["t"])) % m == p]
        gap = np.diff(u)
        score = score_sufficient(frame[i].sum(axis=0))
        all_rows.append({"m": m, "p": p, **score,
                         "proposed_s_spacing_m_p10_p50_p90": np.quantile(gap,[.1,.5,.9]).tolist()
                         if len(gap) else None})
        if original_gate is not None:
            selected = data["t"] >= 30
            before = np.unpackbits(original_gate[i], count=len(selected), axis=-1)[:,selected].astype(bool)
            after = np.unpackbits(gate[i], count=len(selected), axis=-1)[:,selected].astype(bool)
            all_rows[-1]["joint_gate_changed_to_accept"] = np.count_nonzero(after & ~before)
            all_rows[-1]["joint_gate_changed_to_reject"] = np.count_nonzero(before & ~after)
    means = phase_summary(all_rows, keys)
    for m in (1,2,5,10,20,50):
        indices = [i for i, (mm,p) in enumerate(phase_configs()) if m == mm]
        result.append({"m": m, "phases": [all_rows[i] for i in indices],
                       "phase_mean_and_range": next(a for a in means if a["m"] == m),
                       "checkpoint_pair_2000": bootstrap_phase_comparison(point[indices],
                            comparison[indices], cp["site_id"])})
    return result


def prepare_case(name):
    init_modules()
    data = load_case(name)
    cp = checkpoints(data["t"], data["pose"])
    path = WORK/"results"/name
    path.mkdir(exist_ok=True, parents=True)
    return data, cp, path


def scenario_key(level, sign):
    return f"{level}_{sign:+d}"


def execute_case(name, arm, cohort=None):
    data, cp, path = prepare_case(name)
    if arm == "D4":
        comparison = parity(data, name)
        write_json(path/"BASELINE_PARITY.json", comparison)
        if comparison["status"] != "PASS":
            raise RuntimeError(f"Batched baseline fails for {name}: {comparison}")
        d4(data, cp, path)
        print(name, arm, "COMPLETE", utc(), flush=True)
        return
    with np.load(path/"D4_PACKET_WINDOW.npz", allow_pickle=False) as source:
        windows = {w: {"mean": source[f"W{w}_mean"]} for w in (2,5,10)}
    for level, sign in (COHORTS if cohort is None else [cohort]):
        key = scenario_key(level, sign)
        storage = path/f"{key}_{arm}_CHECKPOINT.npz"
        summary = path/f"{key}_{arm}.json"
        if storage.exists() and summary.exists():
            continue
        print(name, arm, key, "START", utc(), flush=True)
        if arm == "D5":
            base, bias = run(data, level, sign, [(1,0)], save_linearization=True)
            controls, _ = run(data, level, sign, [(0,0),(-1,0)])
            baseline = stats(base, data, cp, bias)
            stats_other = stats(controls, data, cp, bias)
            r4_f, dr_f = stats_other["frame"].reshape(2,20,-1)
            r4_cp, dr_cp = stats_other["checkpoint"].reshape(2,20,len(cp["checkpoint_index"]),-1)
            f = {k: score_sufficient(a.sum(axis=0)) for k,a in
                 (("J4",baseline["frame"]),("R4",r4_f),("DR4",dr_f))}
            with np.load(path/"D4_PACKET_WINDOW.npz", allow_pickle=False) as d4x:
                from diag_spatial import trajectory_inputs, unique_pose_indices
                _, pp, e = trajectory_inputs(cp["distance_m"], data["pose"], d4x["error"])
                idx = unique_pose_indices(pp, np.flatnonzero((data["t"]>=30)&np.isfinite(e)
                        &np.isfinite(d4x["W5_mean"])&np.isfinite(d4x["ds_dpsi"])))
            dr_error = wrap(controls["state"][20:,idx,2]-data["pose"][idx,2])
            record = {"scores_frame":f, "paired_J4_minus_R4": paired_bootstrap(
                       baseline["checkpoint"],r4_cp, site_id=cp["site_id"]),
                      "DR4_heading_rmse_deg_D4_pose_set": np.degrees(np.sqrt(np.mean(dr_error**2)))}
            np.savez_compressed(storage, base_frame=baseline["frame"], base=baseline["checkpoint"],
                                r4=r4_cp, dr=dr_cp, site=cp["site_id"],
                                base_error=baseline["checkpoint_error"],
                                base_covariance=baseline["checkpoint_covariance"],
                                range_dr_error=stats_other["checkpoint_error"],
                                range_dr_covariance=stats_other["checkpoint_covariance"],
                                checkpoint_index=cp["checkpoint_index"], **{
                k: base[k] for k in ("state","covariance","accepted","innovation","gain","jacobian","transition")})
        else:
            with np.load(path/f"{key}_D5_CHECKPOINT.npz", allow_pickle=False) as b:
                base_stats = {"frame":b["base_frame"], "checkpoint":b["base"]}
                if arm == "D1":
                    pose4 = np.column_stack([data["pose"], np.zeros(len(data["pose"]))])
                    expected = np.concatenate([data["model"](pose4[i:i+64],data["case"])[0]
                                              for i in range(0,len(pose4),64)])
                    e = wrap(b["state"][...,2]-data["pose"][:,2])
                    record = decompose_d1(observation_error=data["z"]-data["mu"]-expected,
                             innovation=b["innovation"], transition=b["transition"],
                             jacobian=b["jacobian"], gain=b["gain"], accepted=b["accepted"],
                             heading_error_rad=e, heading_nees=e**2/b["covariance"][...,2,2],
                             checkpoint_index=cp["checkpoint_index"], distance_m=cp["distance_m"])
                    np.savez_compressed(storage, checkpoint_index=cp["checkpoint_index"])
            if arm == "D6":
                result, bias = run(data, level, sign, [(1,0)], variance=True)
                s = stats(result, data, cp, bias)
                record = {"J4_variance_frame": score_sufficient(s["frame"].sum(axis=0)),
                          "paired_variance_minus_J4": paired_bootstrap(s["checkpoint"],
                                   base_stats["checkpoint"],site_id=cp["site_id"])}
                np.savez_compressed(storage, variance=s["checkpoint"], site=cp["site_id"],
                                    error=s["checkpoint_error"], covariance=s["checkpoint_covariance"],
                                    checkpoint_index=cp["checkpoint_index"])
            if arm == "D2":
                frame, point, gate, error, covariance = phase_runs(data,cp,level,sign,0,windows,base_stats)
                paired = np.broadcast_to(base_stats["checkpoint"], point.shape)
                record = phase_report(data,cp,frame,point,paired)
                np.savez_compressed(storage, frame=frame, checkpoints=point, joint_accepted=gate, site=cp["site_id"],
                                    checkpoint_index=cp["checkpoint_index"], phases=phase_configs(),
                                    error=error, covariance=covariance)
            if arm == "D3":
                with np.load(path/f"{key}_D2_CHECKPOINT.npz", allow_pickle=False) as original:
                    paired = original["checkpoints"]
                    original_gate = original["joint_accepted"]
                record, streams = {}, {}
                for w in (2,5,10):
                    frame, point, gate, error, covariance = phase_runs(data,cp,level,sign,w,windows,base_stats)
                    record[str(w)] = phase_report(data,cp,frame,point,paired, gate=gate,
                                                   original_gate=original_gate)
                    streams[f"W{w}_frame"], streams[f"W{w}_checkpoints"] = frame, point
                    streams[f"W{w}_joint_accepted"] = gate
                    streams[f"W{w}_error"] = error
                    streams[f"W{w}_covariance"] = covariance
                    print(name,arm,key,"WIDTH_DONE",w,utc(),flush=True)
                np.savez_compressed(storage, **streams, site=cp["site_id"],
                                    checkpoint_index=cp["checkpoint_index"], phases=phase_configs())
        write_json(summary, {"classification":"DIAGNOSTIC_ONLY", "case":name, "bias":level,
                             "sign":sign, "n_sensor_seeds":20, "value":record})
        print(name, arm, key, "COMPLETE", utc(), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--arm", choices=("D4","D5","D6","D1","D2","D3"))
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--cohort", nargs=2)
    args = parser.parse_args()
    if args.prepare:
        s0 = verify_s0()
        write_json(WORK/"S0_REGRESSION.json", s0)
        stage()
        contract = {
            "classification":"DIAGNOSTIC_ONLY", "campaign":"G1-DIAG-003",
            "s2_prime":"STOP (FULL_6)", "step_3":"HOLD", "started_utc":utc(),
            "spec_commit":"ca80a52d8b66d5f96b3ab6de6549b751c835aa88",
            "branch_snapshot":"273ae66bf6bbc39c5daad8ff42de4e4e2ab86790",
            "R2_source":"81cdffbdedf43b318ebf8eddb4fcbac1fd30d878",
            "anchor_source":"5dd61292538c3e95858c9050a60c4d4ddb03a214",
            "r2_s0_run":43606841242, "anchor_s0_run":43608230392,
            "governance_common_sha256":"a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
            "governance_implementer_sha256":"2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da",
            "ordered_stages":["D4","D5","D6","D1","D2","D3"],
            "inputs_sha256":{p.name:h for p,h in STAGED.items()},
            "code_sha256":{p.name:sha256(p) for p in sorted(Path(__file__).parent.glob("*.py"))},
            "case_arm_contract":"R2: noisy frozen RF and LUT; Anchor B R4/R5: historical clean RF, SourceFFD and original R, mu. R2_aB extends same R2 mount-0 frozen replay.",
            "D1_covariance":"Zero-padded empirical within-route lag covariance with global centering and N denominator. Gains and gates fixed by seed. C not causal identification alone.",
            "D4_variogram":"Positive cumulative path lags and unique pose pairs. Domain choices in diag_spatial.py.",
            "D6_sigma_lookup":"Frozen knots, interpolate standard deviation on previous posterior horizontal distance; square after interpolation.",
            "sensor_seeds":list(range(20)), "cohorts":COHORTS,
            "python":sys.version,"platform":platform.platform(),"numpy":np.__version__,"scipy":scipy.__version__,
            "synthetic_D1_and_phase":synthetic_checks(),"synthetic_metrics":check_metrics(),
        }
        write_json(WORK/"MANIFEST.json",contract)
        print("S0 verified, inputs staged, specification recorded",flush=True)
    else:
        if json.loads((WORK/"S0_REGRESSION.json").read_text(encoding="utf-8"))["s0_overall"] != "REPORT_LEVEL_PASS":
            raise RuntimeError("D1–D6 requires corrected S0 pass")
        execute_case(args.case, args.arm, (args.cohort[0],int(args.cohort[1])) if args.cohort else None)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
