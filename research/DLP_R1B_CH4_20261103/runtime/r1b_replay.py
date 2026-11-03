#!/usr/bin/env python3
"""DLP-R1B-CH4-001: guarded paired raw-error accounting and 4-state replay.

Prepared IMPLEMENTER adapter; executing it requires a frozen R1 contract and
PASS canary whose hashes bind the exact RF archive.  It never grants scientific
approval.  No original source, calibration, RF, or previous result is modified.

The recursive function receives controls, initial state and RF only.  Truth is
used outside inference for the frozen synthetic sensor generator and offline
diagnostics.  A rejected packet has a potential K*nu but zero applied update;
both are retained.  Mean correction and additional observation variance are zero.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
P2_DIR = ROOT / "research/DUAL_LP_PAPER_GAP_20261030/contracts/DLP-EKF-GAPS-001/P2_20261101"
P2_CONFIG_SHA256 = "99c4f6303ece8d19b2a30f1217f62c852df3074583dff6c388245a54c555cc43"
P2_TOLERANCE_SHA256 = "ab385d88538b0f2485fdcf1cceef31262a08a7a5c214751c4dfc6949e6101ae3"
POSE_SHA256 = "53e76f41cb95b32b25f2cc58844bac09c09ffd0803aa287cc69e025bb97225c4"
RR, RS = 0.0068578637, 0.0081
OFFSET = -0.5315983906250129
GATE = 9.210340371976184
R0 = np.diag([RR, RS])
P0 = np.diag([.1**2, .1**2, math.radians(5.)**2, math.radians(.1)**2])
CASE = dict(id="R1_aB_m0", anchor=[10., 0., 2.65], robot_z_m=.45, mount_deg=0.)
DEFAULT_DISTANCE_EDGES = [0., .5, 1., 2., 4., 8., 20.]
AZIMUTH_EDGES_DEG = np.arange(-180., 181., 30.)
HSPSI_EDGES = np.array([0., .25, .5, 1., 2., 4., 8., np.inf])
STATE_LABELS = ["x_m", "y_m", "psi_rad", "bg_rad_s"]
MEAS_LABELS = ["r_m", "s"]
CREATED_OUTPUT_THIS_INVOCATION = False


def need(ok, reason):
    if not bool(ok):
        raise RuntimeError(reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_blob(path):
    content = Path(path).read_bytes()
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()


def json_read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve(path):
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    need(bool(rows), "NO_ROWS_FOR:" + str(path))
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def wrap(value):
    return (np.asarray(value) + np.pi) % (2 * np.pi) - np.pi


def max_abs(array):
    values = np.asarray(array)
    return float(np.max(np.abs(values))) if values.size else 0.


def locked_inputs(args):
    """Validate authorization and byte identity before any data calculation."""
    contract_path = Path(args.contract).resolve()
    contract = json_read(contract_path)
    contract_sha = sha(contract_path)
    need(contract.get("contract_id") == "DLP-R1B-CH4-001", "WRONG_CONTRACT")
    need(contract.get("status") == "FROZEN", "CONTRACT_NOT_FROZEN")
    need({"P2", "P3"}.issubset(contract.get("authorized_stages", [])), "REPLAY_NOT_AUTHORIZED")
    cfg = contract["replay"]
    need(cfg["seed"] == 0, "SEED_DIFFERS_FROM_FROZEN_RECIPE")
    need(cfg["bias_levels"] in (["B0"], ["B0", "L2"]), "UNAUTHORIZED_BIAS_SET")
    need(cfg["R0_diag"] == [RR, RS] and cfg["range_offset_m"] == OFFSET and cfg["joint_gate"] == GATE,
         "FROZEN_R_OR_OFFSET_OR_GATE_CHANGED")
    need(cfg.get("mu", [0., 0.]) == [0., 0.], "MEAN_CORRECTION_NOT_ZERO")
    need(cfg.get("extra_variance", [0., 0.]) == [0., 0.], "ADDITIONAL_VARIANCE_NOT_ZERO")
    canary_path = Path(args.canary_qa).resolve()
    canary = json_read(canary_path)
    need(canary.get("status") == "PASS", "RF_CANARY_NOT_PASS")
    need(canary.get("contract_sha256") == contract_sha, "CANARY_NOT_BOUND_TO_THIS_CONTRACT")
    manifest = json_read(args.rf_manifest)
    need(manifest.get("status") == "PASS", "RF_PRODUCTION_OR_ASSEMBLY_NOT_PASS")
    need(manifest.get("n_pose") == 917 and manifest.get("paired_pose_count") == 917 and
         manifest.get("missing_pose_count") == 0, "RF_PRODUCTION_POSE_COVERAGE_INCOMPLETE")
    need(manifest.get("channels") == ["FULL", "LOS"], "RF_PRODUCTION_CHANNELS_NOT_PAIRED")
    need(manifest.get("port_layout") == "[pose,frequency,rx(+45,-45),tx(+45,-45)]",
         "RF_PRODUCTION_PORT_LAYOUT_UNVERIFIED")
    need(manifest.get("actual_native_solver") is True, "RF_NOT_ACTUAL_NATIVE_SOLVER")
    need(manifest.get("contract_sha256") == contract_sha, "RF_NOT_BOUND_TO_THIS_CONTRACT")
    need(manifest.get("canary_qa_sha256") == sha(canary_path), "RF_NOT_BOUND_TO_PASS_CANARY")
    need(manifest.get("rf_sha256") == sha(args.rf), "RF_FILE_HASH_MISMATCH")
    need(sha(P2_DIR / "P2_CONFIG_LOCK.json") == P2_CONFIG_SHA256, "INHERITED_P2_CONFIG_DRIFT")
    need(sha(P2_DIR / "P2_NUMERIC_TOLERANCES.json") == P2_TOLERANCE_SHA256, "INHERITED_P2_TOLERANCE_DRIFT")
    inherited = json_read(P2_DIR / "P2_CONFIG_LOCK.json")
    for item in inherited["pinned_sources"]:
        need(git_blob(ROOT / item["path"]) == item["git_blob"], "PINNED_SOURCE_DRIFT:" + item["path"])
    self_path = Path(__file__).resolve()
    need(any(resolve(item["path"]).resolve() == self_path for item in contract["code_files"]),
         "REPLAY_SOURCE_NOT_INCLUDED_IN_FROZEN_CODE_LOCK")
    for item in contract["code_files"]:
        need(sha(resolve(item["path"])) == item["sha256"], "R1_CODE_HASH_DRIFT:" + item["path"])
    pose_item = contract["inputs"]["pose_csv"]
    pose_path = resolve(pose_item["path"])
    need(sha(pose_path) == pose_item["sha256"] == POSE_SHA256, "ORIGINAL_R1_POSE_HASH_DRIFT")
    bank_items = contract["inputs"]["banks"]
    need(len(bank_items) == 2, "TWO_ORIGINAL_LP_BANKS_REQUIRED")
    expected = {"LP_plus45_bank.npz": inherited["ffd_plus45_sha256"],
                "LP_minus45_bank.npz": inherited["ffd_minus45_sha256"]}
    banks = {}
    for item in bank_items:
        path = resolve(item["path"])
        need(path.name in expected and sha(path) == item["sha256"] == expected[path.name],
             "ORIGINAL_FFD_BANK_HASH_DRIFT:" + str(path))
        banks[path.name] = path
    need(set(banks) == set(expected), "LP_BANK_PAIR_INCOMPLETE")
    return contract, contract_sha, pose_path, banks


def load_modules(bank_paths):
    # Historical observer and sensor source take priority over current package.
    for path in [ROOT / "research/EKF4_RANGE_S_STAGED_20261014",
                 ROOT / "research/FFD_P0P3_20261016",
                 ROOT / "results/DRIVE_SIM_HEADING_SENSOR_V2_20261010/RUN_01a124ff/source/src"]:
        sys.path.insert(0, str(path))
    import core
    import r2_bias_replay
    from source_model import SourceFFD
    from p0_initial import O, P
    banks = []
    for name in ["LP_plus45_bank.npz", "LP_minus45_bank.npz"]:
        with np.load(bank_paths[name], allow_pickle=False) as data:
            bank = P.Bank(dict(data))
        need(bank.e_theta.shape == (257, 181, 361), "FFD_SHAPE_CHANGED")
        need(np.isfinite(bank.e_theta).all() and np.isfinite(bank.e_phi).all(), "FFD_NONFINITE")
        banks.append(bank)
    # Supplying banks avoids source load_banks()'s historical output side effect.
    return core, r2_bias_replay, SourceFFD(banks=banks), O


def load_rf_and_pose(rf_path, pose_path, freqs):
    with pose_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    need(len(rows) == 917, "R1_NOT_917_POSES")
    original = dict(t_s=np.array([float(row["t_s"]) for row in rows]),
                    x_m=np.array([float(row["x"]) for row in rows]),
                    y_m=np.array([float(row["y"]) for row in rows]),
                    psi_rad=np.radians([float(row["yaw_body_deg"]) for row in rows]),
                    pose_id=np.array([int(row["pose_id"]) for row in rows]),
                    phase=np.array([row["phase"] for row in rows]))
    with np.load(rf_path, allow_pickle=False) as archive:
        required = {"freq_hz", "H_full", "H_los", *original}
        need(required.issubset(archive.files), "RF_SCHEMA_FIELDS_MISSING")
        rf = {key: archive[key].copy() for key in archive.files}
    need(np.array_equal(rf["freq_hz"], freqs), "RF_FREQUENCY_GRID_NOT_SOURCE_GRID")
    need(len(freqs) == 257 and np.array_equal(freqs, 6250400000. + 1950000. * np.arange(257)),
         "WRONG_257_BIN_CHAIN")
    need(np.array_equal(rf["pose_id"], original["pose_id"]) and
         np.array_equal(rf["phase"], original["phase"]), "RF_POSE_OR_PHASE_NOT_ORIGINAL")
    for key, tolerance in [("t_s", 1e-9), ("x_m", 1e-6), ("y_m", 1e-6)]:
        need(rf[key].shape == (917,) and max_abs(rf[key] - original[key]) <= tolerance,
             "RF_POSE_COORDINATE_DRIFT:" + key)
    need(rf["psi_rad"].shape == (917,) and max_abs(np.degrees(wrap(rf["psi_rad"] - original["psi_rad"]))) <= 1e-6,
         "RF_BODY_YAW_DRIFT")
    need(np.all(np.diff(original["t_s"]) > 0) and np.unique(original["pose_id"]).size == 917,
         "BAD_ORIGINAL_TIMELINE")
    for channel in ("full", "los"):
        channel_h = rf["H_" + channel]
        need(channel_h.shape == (917, 257, 2, 2), "RF_PORT_AXIS_UNSUPPORTED:" + channel)
        need(np.iscomplexobj(channel_h) and np.isfinite(channel_h).all(), "RF_COMPLEX_CHANNEL_INVALID:" + channel)
    need(rf["H_full"].shape == rf["H_los"].shape, "FULL_LOS_PORT_AXES_DIFFER")
    for key in ("direct_full_visible", "direct_los_visible"):
        if key in rf:
            need(rf[key].shape == (917,) and rf[key].dtype == np.dtype(bool),
                 "DIRECT_VISIBILITY_FLAG_SHAPE_OR_DTYPE:" + key)
    return rf, original


def observe_rf(rf, observer):
    """Keep native Tx columns in RF archive; select only frozen Tx+45 column."""
    output = {}
    for channel in ("full", "los"):
        h = rf["H_" + channel]
        if h.ndim == 3:
            h = h[..., None]
        result = observer.observe(h, rf["freq_hz"], None, None, tx=0)
        cir = observer.cir_batch(h[..., 0])
        strong = np.abs(cir).max(axis=1).argmax(axis=1)
        z = np.column_stack([result["range_m"], result["s"]])
        valid = np.asarray(result["detected"], bool) & np.isfinite(z).all(axis=1)
        need(np.all(result["power"] >= 0), "NEGATIVE_POWER")
        need(np.all(np.abs(z[valid, 1]) <= 1.), "SIGNED_S_OUT_OF_RANGE")
        output[channel] = dict(z=z, valid=valid, tap=result["index"],
                               power=result["power"], strong_port=strong,
                               peak=result["peak"], cir=cir)
    return output


def array_digest(arrays):
    digest = hashlib.sha256()
    for key in sorted(arrays):
        value = np.ascontiguousarray(arrays[key])
        digest.update(key.encode() + str(value.dtype).encode() + repr(value.shape).encode() + value.tobytes())
    return digest.hexdigest()


def run_filter(controls, observed, valid, initial_pose, core, source):
    """Estimator boundary: NO truth, target errors, labels, or future states."""
    n = len(observed)
    data = {"xprior": np.full((n, 4), np.nan), "Pprior": np.full((n, 4, 4), np.nan),
            "xpost": np.full((n, 4), np.nan), "Ppost": np.full((n, 4, 4), np.nan),
            "h": np.full((n, 2), np.nan), "H": np.full((n, 2, 4), np.nan),
            "S": np.full((n, 2, 2), np.nan), "K": np.full((n, 4, 2), np.nan),
            "innovation": np.full((n, 2), np.nan), "nis": np.full(n, np.nan),
            "accepted": np.zeros(n, bool), "status": np.full(n, "NOT_RUN", dtype="<U24"),
            "source_tap": np.full(n, -1, int), "source_strong_port": np.full(n, -1, int),
            "source_fp_margin": np.full(n, np.nan), "F": np.full((n, 4, 4), np.nan),
            "G": np.full((n, 4, 3), np.nan), "Q_input": np.full((n, 3, 3), np.nan)}
    x, cov = np.r_[np.asarray(initial_pose, float), 0.], P0.copy()
    failures = []
    for k in range(n):
        try:
            if k:
                ds, angle, delta_t = (float(controls[key][k]) for key in ("ds_odom", "dtheta_gyro", "dt_s"))
                q = np.diag([2e-5 * abs(ds), math.radians(.015)**2 * delta_t, 0.])
                x, cov, f, g = core.predict(x, cov, ds, angle, delta_t, q)
                data["F"][k], data["G"][k], data["Q_input"][k] = f, g, q
            else:
                data["F"][k], data["G"][k], data["Q_input"][k] = np.eye(4), np.zeros((4, 3)), np.zeros((3, 3))
            data["xprior"][k], data["Pprior"][k] = x, cov
            h, jac, source_diag = source.batch(x[None], CASE, gradient=True, return_diagnostics=True)
            data["h"][k], data["H"][k] = h[0], jac[0]
            data["source_tap"][k] = source_diag["tap"][0]
            data["source_strong_port"][k] = source_diag["strong_port"][0]
            data["source_fp_margin"][k] = source_diag["fp_margin"][0]
            if valid[k]:
                # Actual source model is evaluated at this arm's current prior.
                post, post_cov, info = core.gaussian_update(
                    x, cov, observed[k], lambda state: source.model(state, CASE), R0, gate_threshold=GATE)
                for dest, key in [("S", "S"), ("K", "K"), ("innovation", "innovation"), ("nis", "NIS")]:
                    data[dest][k] = info[key]
                data["accepted"][k] = bool(info["accepted"])
                data["status"][k] = "APPLIED" if info["accepted"] else "REJECT"
            else:
                post, post_cov = x.copy(), cov.copy()
                data["status"][k] = "MISSING"
            need(np.isfinite(post).all() and np.isfinite(post_cov).all(), "NONFINITE_POSTERIOR")
            need(np.linalg.eigvalsh((post_cov + post_cov.T) / 2.).min() >= -1e-12, "POSTERIOR_NOT_PSD")
            need(max_abs(post_cov - post_cov.T) <= 1e-10, "POSTERIOR_NOT_SYMMETRIC")
            data["xpost"][k], data["Ppost"][k] = post, post_cov
            x, cov = post, post_cov
        except Exception as error:
            data["status"][k] = "INVALID"
            data["status"][k + 1:] = "INVALID_PREVIOUS"
            failures.append(dict(index=k, t_s=float(controls["t_s"][k]), reason=repr(error)))
            break
    return data, failures


def raw_error_accounting(pose, observations, h_gt, j_gt, out, edges, rf):
    z_full, z_los = observations["full"]["z"], observations["los"]["z"]
    e0, delta_z, e_los = z_full - h_gt, z_full - z_los, z_los - h_gt
    common = observations["full"]["valid"] & observations["los"]["valid"]
    identity_error = max_abs((e0 - delta_z - e_los)[common])
    need(identity_error <= 1e-10, "RAW_ERROR_IDENTITY_FAILED")
    rho = np.hypot(pose["x_m"] - 10., pose["y_m"])
    azimuth_deg = np.degrees(np.arctan2(pose["y_m"], pose["x_m"] - 10.))
    # This wrap makes the final angular interval half-open like every other bin.
    azimuth_deg = (azimuth_deg + 180.) % 360. - 180.
    abs_hspsi = abs(j_gt[:, 1, 2])
    rows, rf_rows = [], []
    for k in range(len(rho)):
        metadata = dict(pose_id=int(pose["pose_id"][k]), t_s=float(pose["t_s"][k]), phase=str(pose["phase"][k]),
                        evaluation_t_ge30=bool(pose["t_s"][k] >= 30.), common_finite_pre_gate=bool(common[k]))
        row = dict(**metadata, x_gt_m=pose["x_m"][k], y_gt_m=pose["y_m"][k], psi_gt_rad=pose["psi_rad"][k],
                   rho_gt_m=rho[k], anchor_azimuth_rad=math.radians(azimuth_deg[k]),
                   H_gt_s_psi=j_gt[k, 1, 2], range_bridge_m=OFFSET)
        rf_row = dict(**metadata)
        for axis, label in enumerate(MEAS_LABELS):
            for name, array in [("h_gt", h_gt), ("z_full", z_full), ("z_los", z_los),
                                ("e0", e0), ("delta_z", delta_z), ("e_los", e_los)]:
                row[name + "_" + label] = float(array[k, axis])
        for channel in ("full", "los"):
            obs = observations[channel]
            for name, value in [("r_m", obs["z"][k, 0]), ("s", obs["z"][k, 1]),
                                ("fp_tap", int(obs["tap"][k])), ("strong_port", int(obs["strong_port"][k])),
                                ("P_plus", obs["power"][k, 0]), ("P_minus", obs["power"][k, 1]),
                                ("detected_finite", bool(obs["valid"][k]))]:
                rf_row[channel + "_" + name] = value
            flag_key = "direct_" + channel + "_visible"
            visibility = bool(rf[flag_key][k]) if flag_key in rf else "MISSING"
            rf_row[flag_key] = row[flag_key] = visibility
        mismatch = bool(observations["full"]["tap"][k] != observations["los"]["tap"][k])
        row["tap_mismatch"] = rf_row["tap_mismatch"] = mismatch
        rows.append(row)
        rf_rows.append(rf_row)
    write_csv(out / "raw_observation_errors.csv", rows)
    write_csv(out / "rf_observations.csv", rf_rows)
    # Both evaluation and full-run pre-gate masks are explicit in each row.
    group_sets = {"summary": [("ALL", np.ones(len(rho), bool))],
                  "phase_bins": [(phase, pose["phase"] == phase) for phase in ("drive_out", "turn", "drive_back")],
                  "distance_bins": [(f"[{a:g},{b:g})m", (rho >= a) & (rho < b)) for a, b in zip(edges[:-1], edges[1:])],
                  "angle_bins": [(f"[{a:g},{b:g})deg", (azimuth_deg >= a) & (azimuth_deg < b))
                                 for a, b in zip(AZIMUTH_EDGES_DEG[:-1], AZIMUTH_EDGES_DEG[1:])],
                  "abs_Hspsi_bins": [(f"[{a:g},{b:g})per_rad", (abs_hspsi >= a) & (abs_hspsi < b))
                                     for a, b in zip(HSPSI_EDGES[:-1], HSPSI_EDGES[1:])]}
    mismatch = observations["full"]["tap"] != observations["los"]["tap"]
    for filename, groups in group_sets.items():
        summary = []
        for window, time_mask in [("all_t", np.ones(len(rho), bool)), ("t_ge30", pose["t_s"] >= 30.)]:
            for group_name, group in groups:
                mask = common & time_mask & group
                for component, values in [("e0_full", e0), ("delta_z_full_minus_los", delta_z), ("e_los", e_los)]:
                    for axis, label in enumerate(MEAS_LABELS):
                        sample = values[mask, axis]
                        summary.append(dict(window=window, group=group_name, component=component, observation=label,
                                            mask="common_finite_pre_gate", n=int(mask.sum()),
                                            mean=float(sample.mean()) if len(sample) else math.nan,
                                            rms=float(np.sqrt(np.mean(sample**2))) if len(sample) else math.nan,
                                            centered_std_ddof0=float(sample.std(ddof=0)) if len(sample) else math.nan,
                                            median=float(np.median(sample)) if len(sample) else math.nan,
                                            p05=float(np.quantile(sample, .05)) if len(sample) else math.nan,
                                            p95=float(np.quantile(sample, .95)) if len(sample) else math.nan,
                                            tap_mismatch_rate=float(mismatch[mask].mean()) if mask.any() else math.nan,
                                            direct_full_visibility_rate=(float(rf["direct_full_visible"][mask].mean())
                                                                         if mask.any() and "direct_full_visible" in rf else math.nan),
                                            direct_los_visibility_rate=(float(rf["direct_los_visible"][mask].mean())
                                                                        if mask.any() and "direct_los_visible" in rf else math.nan)))
        write_csv(out / ("raw_error_" + filename + ".csv"), summary)
    return dict(e0=e0, delta_z=delta_z, e_los=e_los, common_finite=common,
                identity_max_abs=identity_error, rho_gt_m=rho)


def offline_diagnostics(data, observed, valid, h_gt, source):
    """GT model values enter only after the complete autonomous recursion."""
    e = observed - h_gt
    delta_h = h_gt - data["h"]
    potential = np.einsum("nsi,ni->ns", data["K"], data["innovation"])
    ke = np.einsum("nsi,ni->ns", data["K"], e)
    k_delta_h = np.einsum("nsi,ni->ns", data["K"], delta_h)
    applied = np.zeros_like(potential)
    applied[data["accepted"]] = potential[data["accepted"]]
    completed = np.isfinite(data["xpost"]).all(axis=1)
    pre_gate = valid & np.isfinite(data["innovation"]).all(axis=1)
    nu_error = max_abs((data["innovation"] - e - delta_h)[pre_gate])
    update_error = max_abs((potential - ke - k_delta_h)[pre_gate])
    actual = data["xpost"] - data["xprior"]
    actual[:, 2] = wrap(actual[:, 2])
    expected_wrapped = applied.copy()
    expected_wrapped[:, 2] = wrap(expected_wrapped[:, 2])
    applied_error = max_abs((actual - expected_wrapped)[completed])
    qa = dict(innovation_identity_max_abs=nu_error, potential_update_identity_max_abs=update_error,
              applied_wrapped_update_max_abs=applied_error,
              evaluated_packet_count=int(pre_gate.sum()), completed_count=int(completed.sum()))
    need(max(nu_error, update_error, applied_error) <= 1e-10, "PACKET_IDENTITY_FAILED")
    n = len(observed)
    nis_error, state_error, covariance_error, prediction_error = 0., 0., 0., 0.
    innovation_covariance_error, gain_error = 0., 0.
    for k in range(n):
        if not completed[k]:
            continue
        if k:
            predicted_cov = data["F"][k] @ data["Ppost"][k-1] @ data["F"][k].T
            predicted_cov += data["G"][k] @ data["Q_input"][k] @ data["G"][k].T
            prediction_error = max(prediction_error, max_abs(data["Pprior"][k] - predicted_cov))
        if not pre_gate[k]:
            continue
        p, h, nu = data["Pprior"][k], data["H"][k], data["innovation"][k]
        s = h @ p @ h.T + R0
        k_gain = np.linalg.solve(s, h @ p).T
        # Includes REJECT rows: their stored potential gain is still auditable.
        innovation_covariance_error = max(innovation_covariance_error, max_abs(data["S"][k] - s))
        gain_error = max(gain_error, max_abs(data["K"][k] - k_gain))
        nis_value = float(nu @ np.linalg.solve(s, nu))
        nis_error = max(nis_error, abs(nis_value - data["nis"][k]))
        need(bool(nis_value <= GATE) == bool(data["accepted"][k]), "JOINT_NIS_GATE_MISMATCH")
        target = data["xprior"][k].copy()
        target_cov = p.copy()
        if data["accepted"][k]:
            target += k_gain @ nu
            target[2] = wrap(target[2])
            a = np.eye(4) - k_gain @ h
            target_cov = a @ p @ a.T + k_gain @ R0 @ k_gain.T
        difference = target - data["xpost"][k]
        difference[2] = wrap(difference[2])
        state_error = max(state_error, max_abs(difference))
        covariance_error = max(covariance_error, max_abs(target_cov - data["Ppost"][k]))
    need(nis_error <= 1e-9 and max(state_error, covariance_error, prediction_error,
                                 innovation_covariance_error, gain_error) <= 1e-10,
         "INDEPENDENT_JOSEPH_NIS_OR_PREDICTION_PARITY_FAILED")
    qa.update(nis_recompute_max_abs=nis_error, state_recompute_max_abs=state_error,
              joseph_recompute_max_abs=covariance_error, prediction_covariance_max_abs=prediction_error,
              stored_S_recompute_max_abs=innovation_covariance_error, stored_K_recompute_max_abs=gain_error)
    # Same smooth-cell FD policy as P1 T09, evaluated on saved online priors.
    fd_rows, stable_count, fd_fail_count = [], 0, 0
    indices = np.flatnonzero(np.isfinite(data["xprior"]).all(axis=1))
    for begin in range(0, len(indices), 32):
        chosen = indices[begin:begin + 32]
        states = data["xprior"][chosen]
        _, jac, base = source.batch(states, CASE, True, True)
        for axis in range(3):
            plus, minus = states.copy(), states.copy()
            plus[:, axis] += 1e-5
            minus[:, axis] -= 1e-5
            yp, _, dp = source.batch(plus, CASE, False, True)
            ym, _, dm = source.batch(minus, CASE, False, True)
            boundary = (dp["tap"] != base["tap"]) | (dm["tap"] != base["tap"])
            boundary |= (dp["strong_port"] != base["strong_port"]) | (dm["strong_port"] != base["strong_port"])
            boundary |= np.any(dp["cells"] != base["cells"], axis=1) | np.any(dm["cells"] != base["cells"], axis=1)
            fd = (yp[:, 1] - ym[:, 1]) / 2e-5
            err = abs(fd - jac[:, 1, axis])
            passed = (err <= 2e-5) | ((abs(jac[:, 1, axis]) > 1e-6) & (err / np.maximum(abs(jac[:, 1, axis]), 1e-30) <= 1e-4))
            stable_count += int((~boundary).sum())
            fd_fail_count += int(((~boundary) & (~passed)).sum())
            for j, idx in enumerate(chosen):
                fd_rows.append(dict(index=int(idx), axis=STATE_LABELS[axis], epsilon=1e-5,
                                    analytic=float(jac[j, 1, axis]), fd=float(fd[j]), abs_error=float(err[j]),
                                    boundary_crossing=bool(boundary[j]),
                                    status="BOUNDARY_NOT_FD_PASS" if boundary[j] else ("PASS" if passed[j] else "FAIL")))
    qa.update(jacobian_stable_count=stable_count, jacobian_failure_count=fd_fail_count,
              jacobian_boundary_count=sum(row["boundary_crossing"] for row in fd_rows))
    need(fd_fail_count == 0 and stable_count > 0, "SOURCE_STABLE_CELL_JACOBIAN_FAILED")
    return dict(e=e, delta_h=delta_h, K_e=ke, K_delta_h=k_delta_h,
                potential_update=potential, applied_unwrapped_update=applied,
                actual_wrapped_state_difference=actual), qa, fd_rows


def flatten_row(prefix, array):
    array = np.asarray(array)
    if array.ndim == 1:
        return {f"{prefix}_{i}": float(value) for i, value in enumerate(array)}
    return {f"{prefix}_{i}_{j}": float(array[i, j]) for i in range(array.shape[0]) for j in range(array.shape[1])}


def packet_rows(data, diagnostics, pose, observed, bias, channel):
    rows = []
    for k, t_s in enumerate(pose["t_s"]):
        row = dict(bias_level=bias, channel=channel, index=k, pose_id=int(pose["pose_id"][k]),
                   t_s=float(t_s), phase=str(pose["phase"][k]), status=str(data["status"][k]),
                   accepted=bool(data["accepted"][k]), nis=float(data["nis"][k]),
                   gate_threshold=GATE, mu_r=0., mu_s=0., R_r=RR, R_s=RS,
                   source_tap=int(data["source_tap"][k]), source_strong_port=int(data["source_strong_port"][k]),
                   source_fp_margin=float(data["source_fp_margin"][k]))
        row.update(flatten_row("z", observed[k]))
        for name in ["xprior", "Pprior", "xpost", "Ppost", "h", "H", "S", "K", "innovation"]:
            row.update(flatten_row(name, data[name][k]))
        for name, value in diagnostics.items():
            row.update(flatten_row(name, value[k]))
        row["potential_dpsi_from_range_rad"] = float(data["K"][k, 2, 0] * data["innovation"][k, 0])
        row["potential_dpsi_from_s_rad"] = float(data["K"][k, 2, 1] * data["innovation"][k, 1])
        rows.append(row)
    return rows


def scores(data, pose, bias, channel):
    truth = np.column_stack([pose["x_m"], pose["y_m"], pose["psi_rad"]])
    error = data["xpost"][:, :3] - truth
    error[:, 2] = wrap(error[:, 2])
    rows = []
    for name, mask in [("all_t", np.ones(len(truth), bool)), ("t_ge30", pose["t_s"] >= 30.)]:
        need(np.isfinite(error[mask]).all(), "MISSING_POSTERIOR_CANNOT_DROP_FROM_SCORE")
        accepted_times = pose["t_s"][mask & data["accepted"]]
        window_times = pose["t_s"][mask]
        # Maximum elapsed interval between accepted updates, including window endpoints.
        endpoints = np.r_[window_times[0], accepted_times, window_times[-1]]
        rows.append(dict(bias_level=bias, channel=channel, window=name,
                         n=int(mask.sum()), gate_rejected_in_score=True,
                         heading_rmse_deg=float(np.degrees(np.sqrt(np.mean(error[mask, 2]**2)))),
                         xy_rmse_cm=float(100 * np.sqrt(np.mean(np.sum(error[mask, :2]**2, axis=1)))),
                         accepted=int(np.count_nonzero(data["accepted"] & mask)),
                         rejected=int(np.count_nonzero((data["status"] == "REJECT") & mask)),
                         missing=int(np.count_nonzero((data["status"] == "MISSING") & mask)),
                         max_accepted_update_gap_s=float(np.diff(endpoints).max()),
                         true_gyro_bias_dps=0. if bias == "B0" else .2))
    return rows


def run(args):
    global CREATED_OUTPUT_THIS_INVOCATION
    started = time.monotonic()
    contract, contract_sha, pose_path, bank_paths = locked_inputs(args)
    out = Path(args.out).resolve()
    need(not out.exists(), "OUTPUT_DIRECTORY_EXISTS_REFUSE_OVERWRITE")
    out.mkdir(parents=True)
    CREATED_OUTPUT_THIS_INVOCATION = True
    write_json(out / "REPLAY_STARTED.json", dict(contract_id=contract["contract_id"],
               contract_sha256=contract_sha, rf_sha256=sha(args.rf),
               source_sha256=sha(__file__), utc=dt.datetime.now(dt.timezone.utc).isoformat(),
               status="STARTED_NOT_SCIENTIFIC_APPROVAL"))
    core, legacy, source, observer = load_modules(bank_paths)
    rf, pose = load_rf_and_pose(args.rf, pose_path, source.freqs)
    observations = observe_rf(rf, observer)
    truth = np.column_stack([pose["x_m"], pose["y_m"], pose["psi_rad"]])
    h_gt, j_gt = source.batch(truth, CASE, gradient=True)
    edges = contract["replay"].get("distance_bin_edges_m", DEFAULT_DISTANCE_EDGES)
    need(np.all(np.diff(edges) > 0) and edges[0] <= 0 and edges[-1] > np.hypot(pose["x_m"] - 10., pose["y_m"]).max(),
         "DISTANCE_BINS_NOT_ORDERED_OR_INCOMPLETE")
    raw = raw_error_accounting(pose, observations, h_gt, j_gt, out, edges, rf)
    np.savez_compressed(out / "observation_arrays.npz", **pose, h_gt=h_gt, H_gt=j_gt,
                        z_full=observations["full"]["z"], z_los=observations["los"]["z"],
                        cir_full=observations["full"]["cir"], cir_los=observations["los"]["cir"],
                        **{key: value for key, value in raw.items() if key != "identity_max_abs"})
    completeness = {channel: dict(n_finite_detected=int(observations[channel]["valid"].sum()),
                                 n_nonpositive_total_fp_power=int(np.count_nonzero(
                                     observations[channel]["power"].sum(axis=1) <= 0.)))
                    for channel in ("full", "los")}
    complete = all(item["n_finite_detected"] == 917 and item["n_nonpositive_total_fp_power"] == 0
                   for item in completeness.values())
    write_json(out / "P2_OBSERVATION_COMPLETENESS.json",
               dict(status="PASS" if complete else "HOLD", expected_paired_pose_count=917,
                    common_finite_pose_count=int(raw["common_finite"].sum()), channels=completeness,
                    failed_observations_preserved=True))
    need(complete and int(raw["common_finite"].sum()) == 917,
         "P2_REQUIRES_ALL_917_PAIRED_FINITE_DETECTIONS_FAILURE_EVIDENCE_PRESERVED")
    all_scores, qa_rows = [], []
    csv_by_channel = {"los": [], "full": []}
    controls_reference = None
    for bias in contract["replay"]["bias_levels"]:
        # Only this input simulator consumes trajectory truth before inference.
        controls, initial_pose = legacy.build_positive_bias_controls(pose["t_s"], truth, bias, seed=0)
        if controls_reference is None:
            controls_reference = {key: value.copy() for key, value in controls.items()}
            initial_reference = initial_pose.copy()
        else:
            need(np.array_equal(controls["ds_odom"], controls_reference["ds_odom"]) and
                 np.array_equal(initial_pose, initial_reference), "B0_L2_COMMON_INPUT_DRIFT")
        controls_sha = array_digest(controls)
        np.savez_compressed(out / f"controls_{bias}.npz", **controls, initial_pose=initial_pose, initial_P0=P0)
        for value in controls.values():
            value.flags.writeable = False
        for channel in ("los", "full"):
            observed = observations[channel]
            data, failures = run_filter(controls, observed["z"], observed["valid"], initial_pose, core, source)
            # Preserve every trace before offline checks, including any failure.
            trace_path = out / f"ekf_trace_{channel}_{bias}.npz"
            np.savez_compressed(trace_path, **pose, **data, z=observed["z"],
                                valid=observed["valid"], initial_pose=initial_pose, initial_P0=P0,
                                **{key: value for key, value in controls.items() if key != "t_s"})
            write_json(out / f"ekf_failures_{channel}_{bias}.json", failures)
            need(not failures, "FILTER_FAILURE_PRESERVED:" + channel + "/" + bias)
            diagnostic, qa, fd_rows = offline_diagnostics(data, observed["z"], observed["valid"], h_gt, source)
            np.savez_compressed(out / f"ekf_offline_diagnostics_{channel}_{bias}.npz", **diagnostic)
            write_csv(out / f"source_jacobian_fd_{channel}_{bias}.csv", fd_rows)
            csv_by_channel[channel].extend(packet_rows(data, diagnostic, pose, observed["z"], bias, channel))
            all_scores.extend(scores(data, pose, bias, channel))
            qa_rows.append(dict(bias_level=bias, channel=channel, controls_array_sha256=controls_sha,
                                trace_sha256=sha(trace_path), **qa))
            need(array_digest(controls) == controls_sha, "INFERENCE_MUTATED_SHARED_CONTROLS")
            print("R1B_REPLAY_COMPLETE", bias, channel, "accepted", int(data["accepted"].sum()), flush=True)
    for channel, rows in csv_by_channel.items():
        write_csv(out / f"ekf_packet_log_{channel}.csv", rows)
    write_csv(out / "ekf_scores_los_full.csv", all_scores)
    contrasts = []
    for bias in contract["replay"]["bias_levels"]:
        for window in ("all_t", "t_ge30"):
            pair = {row["channel"]: row for row in all_scores if row["bias_level"] == bias and row["window"] == window}
            row = dict(bias_level=bias, window=window, n=pair["los"]["n"])
            need(pair["los"]["n"] == pair["full"]["n"], "PAIRED_SCORE_DENOMINATOR_MISMATCH")
            for metric in ("heading_rmse_deg", "xy_rmse_cm"):
                los, full = pair["los"][metric], pair["full"][metric]
                row[metric + "_los"], row[metric + "_full"] = los, full
                row[metric + "_delta_full_minus_los"] = full - los
                row[metric + "_percent_change"] = 100 * (full - los) / los if los else math.nan
            contrasts.append(row)
    write_csv(out / "ekf_los_full_contrasts.csv", contrasts)
    receipt = dict(contract_id=contract["contract_id"], status="TECHNICAL_PASS_AUDIT_PENDING",
                   scientific_supported=False, independent_audit="PENDING_SEPARATE_EXECUTION",
                   n_original=917, n_eval=int((pose["t_s"] >= 30.).sum()),
                   contract_sha256=contract_sha, rf_sha256=sha(args.rf),
                   canary_qa_sha256=sha(args.canary_qa), source_sha256=sha(__file__),
                   raw_error_identity_max_abs=raw["identity_max_abs"],
                   distance_bin_edges_m=edges, centered_std_ddof=0, samples_independent_scenes=1,
                   azimuth_bin_edges_deg=AZIMUTH_EDGES_DEG.tolist(),
                   abs_Hspsi_bin_edges_per_rad=[0., .25, .5, 1., 2., 4., 8., "+inf"],
                   conditional_bin_scope="GT-only offline descriptive pre-gate bins; Hspsi bins do not assert smooth-cell FD PASS",
                   direct_visibility_flags={channel: ("PRESERVED" if "direct_"+channel+"_visible" in rf else "MISSING")
                                            for channel in ("full", "los")},
                   range_model="distance3d + inherited continuous offset; not a learned first-tap likelihood",
                   gate_semantics="self gate per arm; potential correction kept even if rejected; applied correction zero",
                   prior_Gaussian_R0_independence="fixed assumption; not empirically validated by these runs",
                   checks=qa_rows, score_files=["ekf_scores_los_full.csv", "ekf_los_full_contrasts.csv"],
                   runtime=dict(seconds=time.monotonic()-started, python=sys.version, numpy=np.__version__,
                                platform=platform.platform(), argv=sys.argv,
                                git_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                                utc=dt.datetime.now(dt.timezone.utc).isoformat()))
    write_json(out / "REPLAY_QA.json", receipt)
    files = [{"path": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}
             for path in sorted(out.iterdir()) if path.is_file()]
    write_json(out / "REPLAY_OUTPUT_MANIFEST.json", dict(contract_sha256=contract_sha, files=files))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--canary-qa", required=True)
    parser.add_argument("--rf-manifest", required=True)
    parser.add_argument("--rf", required=True)
    parser.add_argument("--out", required=True, help="New directory; existing results are never overwritten")
    args = parser.parse_args()
    try:
        result = run(args)
        print(json.dumps({"status": result["status"], "n_eval": result["n_eval"]}))
        return 0
    except Exception as error:
        # Preserve failure only in a directory this invocation created.
        out = Path(args.out)
        started = out / "REPLAY_STARTED.json"
        if CREATED_OUTPUT_THIS_INVOCATION and started.exists() and not (out / "REPLAY_QA.json").exists():
            write_json(out / "REPLAY_FATAL.json", dict(status="HOLD", error=repr(error), traceback=traceback.format_exc(),
                       source_sha256=sha(__file__), utc=dt.datetime.now(dt.timezone.utc).isoformat()))
        print("R1B_REPLAY_HOLD", repr(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
