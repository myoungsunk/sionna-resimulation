"""G1-INT-SIGNED-COV-001 P0. Read original data; never replay/fit an EKF.

SourceFFD is loaded with explicit frozen banks (no load_banks side effects).
All writes are restricted to a fresh attempt directory. No covariance fitting.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import hashlib
import importlib
import json
import os
from pathlib import Path
import platform
import sys
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
BASE = Path(__file__).resolve().parent
PLAN = BASE.parent / "PLAN_SIGNED_AA_SLOW_COV_VALIDATION_KO.md"
ART = Path("D:/SLAM_bot/artifacts")
RAW = ART / "DRIVE_SIM_POST_A23_UPLOAD_20261010/supplement_retrieved/BLOCK_C"
LOCK = ART / "G1_CHAR002_S2_INPUTS_20261115/locked_release"
NATIVE = ART / "G1_CHAR002_S2_INPUTS_20261115/source_minimal/research/FP_SC_RECOVERY_R0_R5_20261107/R45_sources"
PLAN_COMMIT = "bd28eac6a0e235412bdced9f08505148191e39d2"
BANKS = {
    "LP_plus45_bank.npz": "b29ae471a64617eacb0cf02ddbbcc3b2db190de171fba85f05dddb9cec0c453b",
    "LP_minus45_bank.npz": "39729fe9f02cf80119a8492be8fcc43e08e2e9e00beebda2909e7c9819c76eb9",
}
ROUTES = {"R2": 979, "R4": 742, "R5": 1415}
CONTRACT = {
    "question_id": "G1-INT-SIGNED-COV-001", "stage": "P0_ONLY",
    "plan_commit": PLAN_COMMIT, "status": "FROZEN_BEFORE_P0",
    "primary": "original noise-free Full O30 - original noise-free LoS O30; tx0",
    "sensitivity": "signed analytic SourceFFD d(s)/d(body yaw), s/rad, at truth",
    "scope": "BLOCK_C R2/R4/R5 B mount0 B0 seed10 timed pose grid only",
    "appended_sweeps": "excluded from chronological primary; no invented times",
    "gates": {
        "rf_sha256": "CASES.json exact", "banks_sha256": BANKS,
        "raw_los_vs_evaluator_clean_H": "bitwise equal tx0 at pose_id",
        "raw_full_vs_online_clean_Hrf": "bitwise equal tx0 at pose_id",
        "truth_pose_max_abs_m_rad": 1e-10,
        "independent_O30_s_max_abs": 1e-12, "independent_O30_tap": "exact",
        "sourceFFD_vs_raw_los_s_max_abs": 1e-4,
        "sourceFFD_vs_raw_los_tap": "exact",
        "source_parity_policy": "new conservative maximum-error guard fixed before P0; not inherited p90 gate",
        "FD_steps_deg": [0.1, 0.01],
        "FD_max_normalized_error": [1e-4, 1e-5],
        "FD_normalization": "abs(FD-a)/max(1,abs(a))",
        "FD_stable": "tap AND strong_port AND all interpolation cells unchanged at +/- step",
        "nonsmooth": "enumerate all; FD exemption does not exclude covariance packets/pairs",
        "failure": "STOP_UNSUPPORTED_INPUT; preserve failed evidence; no threshold relaxation",
    },
    "pair_support": {
        "lag_s": [0.4, 5.0], "min_abs_a_per_endpoint": 0.1,
        "rho_bins_m": [0, 1.5, 3, 6, 10], "cluster_s": 10,
        "cluster_owner": "earlier endpoint; cross-boundary pairs retained with both cluster ids",
        "matching": "within route and rho stratum; exact coarsened cells; equal sign counts per cell",
        "matching_rho_mean_bin_m": 0.5,
        "matching_log_abs_aiaj_bin": 0.5,
        "matching_lag_bin_s": 0.4,
        "tie_break": "ascending (pose_i,pose_j), no residual used",
        "minimum_pairs_each_sign": 30, "minimum_clusters_each_sign": 3,
        "max_standardized_signed_design_condition": 30,
    },
    "preserved": ["G-T2/G-V SEALED", "S2prime STOP", "Step3 HOLD", "all M7 evidence"],
    "later_stages": "NOT_RUN; covariance fit requires frozen P1 contract and independent synthetic audit",
}


def sha(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def put(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def quant(value):
    v = np.asarray(value)
    return dict(zip(["min", "p50", "p90", "p99", "max"], map(float, np.quantile(v, [0, .5, .9, .99, 1])))) if v.size else None


def independent_o30(h):
    n = h.shape[1]
    window = .5 - .5 * np.cos(2 * np.pi * np.arange(n) / (n - 1))
    cir = np.fft.ifft(h * window[None, :, None], n=4*n, axis=1)*n
    mag = np.abs(cir)
    branch = mag.max(axis=1).argmax(axis=1)
    strong = mag[np.arange(len(h)), :, branch]
    assert np.all(strong.max(axis=1) > 0)
    tap = (strong >= .3*strong.max(axis=1)[:, None]).argmax(axis=1)
    p = np.abs(cir[np.arange(len(h)), tap])**2
    return (p[:, 0]-p[:, 1])/p.sum(axis=1), tap, cir


def pairs_for(t, a, rho, arc, yaw):
    ii, jj = [], []
    for i in range(len(t)):
        lo = np.searchsorted(t, t[i]+.4-1e-9, side="left")
        hi = np.searchsorted(t, t[i]+5+1e-9, side="right")
        for j in range(max(i+1, lo), hi):
            if abs(a[i]) >= .1 and abs(a[j]) >= .1:
                ii.append(i); jj.append(j)
    i, j = np.asarray(ii, int), np.asarray(jj, int)
    bins = np.array(CONTRACT["pair_support"]["rho_bins_m"])
    bi, bj = np.digitize(rho[i], bins)-1, np.digitize(rho[j], bins)-1
    keep = (bi == bj) & (bi >= 0) & (bi < len(bins)-1)
    i, j, b = i[keep], j[keep], bi[keep]
    prod = a[i]*a[j]
    k = np.exp(-abs(arc[j]-arc[i])-abs(yaw[j]-yaw[i])/np.radians(10))
    return dict(i=i, j=j, rho_bin=b, sign=np.sign(prod).astype(int), prod=prod, K=k,
                lag=t[j]-t[i], rho_mean=(rho[i]+rho[j])/2, cluster=(t[i]//10).astype(int),
                cluster_j=(t[j]//10).astype(int))


def match_signs(p, subset):
    # Eligibility and deterministic matching use no residuals or prediction scores.
    groups = {}
    for z in np.flatnonzero(subset):
        key = (int(p["rho_mean"][z]//.5), int(np.floor(np.log(abs(p["prod"][z]))/.5)),
               int(np.floor((p["lag"][z]-.4+1e-9)/.4)))
        groups.setdefault(key, {1: [], -1: []})[int(p["sign"][z])].append(int(z))
    selected = []
    for key in sorted(groups):
        n = min(len(groups[key][1]), len(groups[key][-1]))
        selected.extend(groups[key][1][:n]); selected.extend(groups[key][-1][:n])
    return np.asarray(sorted(selected), int)


def support_report(p, t):
    rows = []
    for b in range(4):
        sel = p["rho_bin"] == b
        matched = match_signs(p, sel)
        row = {"rho_bin": b, "raw_pairs": int(sel.sum()), "matched_pairs": len(matched)}
        for sign, name in [(1, "positive"), (-1, "negative")]:
            raw = np.flatnonzero(sel & (p["sign"] == sign))
            mm = matched[p["sign"][matched] == sign]
            row[name] = {"raw_pairs": len(raw), "matched_pairs": len(mm),
                         "matched_clusters": len(np.unique(p["cluster"][mm])),
                         "matched_distinct_poses": len(np.unique(np.r_[p["i"][mm], p["j"][mm]])),
                         "abs_aiaj": quant(abs(p["prod"][mm])), "lag_s": quant(p["lag"][mm]),
                         "rho_mean_m": quant(p["rho_mean"][mm])}
        if len(matched) > 2:
            X = np.c_[p["K"][matched], p["prod"][matched]*p["K"][matched]]
            scale = X.std(axis=0)
            cond = float(np.linalg.cond((X-X.mean(axis=0))/scale)) if np.all(scale > 0) else None
        else:
            cond = None
        row["standardized_signed_design_condition"] = cond
        adequate = all(row[n]["matched_pairs"] >= 30 and row[n]["matched_clusters"] >= 3
                       for n in ("positive", "negative"))
        row["status"] = ("NO_SIGN_SUPPORT" if not adequate else
                         "NON_IDENTIFIABLE" if cond is None or cond > 30 else "SUPPORT_AVAILABLE")
        rows.append(row)
    return rows


def load_source():
    sys.path[:0] = [str(NATIVE/"src"), str(NATIVE/"research/FFD_P0P3_20261016"),
                    str(NATIVE/"research/EKF4_RANGE_S_STAGED_20261014")]
    from qclean_uwb.fp_sc.e0_baseline import load_original_model
    _, _, model, sources = load_original_model(NATIVE)
    from qclean_uwb.drivesim import observation
    return model, observation, sources


def run(out):
    if out.exists():
        raise FileExistsError("Fresh output directory required: " + str(out))
    out.mkdir(parents=True)
    contract = dict(CONTRACT, plan_sha256=sha(PLAN), implementation_sha256=sha(__file__),
                    started_utc=dt.datetime.now(dt.timezone.utc).isoformat(), command=sys.argv,
                    python=sys.version, numpy=np.__version__, platform=platform.platform(),
                    thread_id=os.environ.get("CODEX_THREAD_ID"),
                    managed_process_id=os.environ.get("MANAGED_PROCESS_ID"))
    put(out/"RUN_CONTRACT.json", contract)
    hashes = {str(PLAN): sha(PLAN), str(Path(__file__)): sha(__file__)}
    inputs, checks, supports = {}, {}, {}
    try:
        for name, h in BANKS.items():
            actual = sha(NATIVE/name)
            hashes[str(NATIVE/name)] = actual
            assert actual == h, "BANK_SHA_MISMATCH"
        print("Frozen contract written. Loading source-only model.", flush=True)
        model, observation, sources = load_source()
        hashes.update({str(NATIVE/k): v for k, v in sources.items()})
        cases = json.loads((RAW/"CASES.json").read_bytes())
        hashes[str(RAW/"CASES.json")] = sha(RAW/"CASES.json")
        assert np.array_equal(model.freqs, np.load(RAW/"freqs_hz.npy")), "FREQ_MISMATCH"
        for route, expected_n in ROUTES.items():
            print("P0", route, "loading original Full/LoS", flush=True)
            meta = next(c for c in cases if c["case"] == f"{route}_aB_m0")
            paths = dict(full=RAW/"FULL_RF"/f"H_{route}_aB_m0.npy",
                         los=RAW/f"H_LoS_{route}_aB_m0.npy",
                         samples=RAW/f"{route}_aB_m0/SAMPLES.json",
                         online=LOCK/f"{route}_B0_Full_10__online.npz",
                         evaluator=LOCK/f"{route}_B0_Full_10__evaluator.npz")
            for p in paths.values(): hashes[str(p)] = sha(p)
            assert hashes[str(paths["full"])] == meta["input_H_sha256"], "FULL_SHA_MISMATCH"
            assert hashes[str(paths["los"])] == meta["H_sha256"], "LOS_SHA_MISMATCH"
            assert hashes[str(paths["samples"])] == meta["samples_sha256"], "POSE_SHA_MISMATCH"
            full, los = np.load(paths["full"], mmap_mode="r"), np.load(paths["los"], mmap_mode="r")
            poses = json.loads(paths["samples"].read_bytes())
            with np.load(paths["online"], allow_pickle=False) as on, np.load(paths["evaluator"], allow_pickle=False) as ev:
                t, pid, truth = ev["t"], ev["pose_id"], ev["truth"]
                assert len(t) == expected_n and len(np.unique(pid)) == len(pid), "TIMED_POSE_COUNT"
                assert np.array_equal(t, on["t"]) and np.array_equal(pid, on["pose_id"]), "TIME_ALIGNMENT"
                assert np.all(np.diff(t) > 0), "NONINCREASING_TIME"
                assert np.array_equal(ev["clean_H"], los[pid, :, :, 0]), "LOS_EVALUATOR_MISMATCH"
                assert np.array_equal(on["clean_Hrf"], full[pid, :, :, 0]), "FULL_ONLINE_MISMATCH"
                truth_raw = np.array([[poses[k]["x"], poses[k]["y"], np.radians(poses[k]["yaw_body_deg"])] for k in pid])
                error = abs(truth-truth_raw)
                error[:, 2] = abs((truth[:, 2]-truth_raw[:, 2]+np.pi)%(2*np.pi)-np.pi)
                assert error.max() <= 1e-10, "TRUTH_MISMATCH"
            arrays = dict(t=t, pose_id=pid, truth=truth)
            route_checks = {"raw_hashes": True, "timed_alignment": True,
                            "truth_max_abs": float(error.max()), "FD": {}}
            pred_list, a_list, los_s, full_s, los_tap = [], [], [], [], []
            fd_store = {step: {"stable": [], "error": []} for step in [0.1, 0.01]}
            spec = dict(anchor=meta["anchor_xyz"], robot_z_m=meta["robot_z"], mount_deg=0)
            tap_errors, obs_errors = [], []
            for start in range(0, len(t), 64):
                stop = min(start+64, len(t)); state = truth[start:stop]
                h, H, diag = model.batch(state, spec, gradient=True, return_diagnostics=True)
                pred_list.append(h[:, 1]); a_list.append(H[:, 1, 2])
                for tag, raw_h in [("los", los), ("full", full)]:
                    s, tap, cir = independent_o30(raw_h[pid[start:stop], :, :, 0])
                    ref = observation.first_path_batch(cir, float(model.freqs[1]-model.freqs[0]))
                    obs_errors.append(float(abs(s-ref["s"]).max()))
                    assert np.array_equal(tap, ref["index"]), "O30_TAP_MISMATCH"
                    if tag == "los":
                        los_s.append(s); los_tap.append(tap)
                        tap_errors.append(diag["tap"] != tap)
                    else: full_s.append(s)
                for step in fd_store:
                    shift = np.zeros_like(state); shift[:, 2] = np.radians(step)
                    hm, _, dm = model.batch(state-shift, spec, gradient=False, return_diagnostics=True)
                    hp, _, dp = model.batch(state+shift, spec, gradient=False, return_diagnostics=True)
                    stable = np.ones(len(state), bool)
                    for name in ["tap", "strong_port", "cells"]:
                        same = (dm[name] == diag[name]) & (dp[name] == diag[name])
                        stable &= same.reshape(len(state), -1).all(axis=1)
                    fd = (hp[:, 1]-hm[:, 1])/(2*np.radians(step))
                    fd_store[step]["stable"].append(stable)
                    fd_store[step]["error"].append(abs(fd-H[:, 1, 2])/np.maximum(1, abs(H[:, 1, 2])))
            arrays.update(s_los=np.concatenate(los_s), s_full=np.concatenate(full_s),
                          a_truth=np.concatenate(a_list), source_s=np.concatenate(pred_list))
            arrays["e_rf"] = arrays["s_full"]-arrays["s_los"]
            arrays["arc_m"] = np.r_[0, np.cumsum(np.linalg.norm(np.diff(truth[:, :2], axis=0), axis=1))]
            arrays["yaw_arc_rad"] = np.r_[0, np.cumsum(abs((np.diff(truth[:, 2])+np.pi)%(2*np.pi)-np.pi))]
            arrays["rho_m"] = np.linalg.norm(truth[:, :2]-np.array(spec["anchor"][:2]), axis=1)
            arrays["los_tap"] = np.concatenate(los_tap)
            route_checks["O30_max_abs"] = max(obs_errors)
            parity = abs(arrays["source_s"]-arrays["s_los"])
            route_checks["source_los_abs"] = quant(parity)
            route_checks["source_los_tap_mismatches"] = int(np.concatenate(tap_errors).sum())
            passed = max(obs_errors) <= 1e-12 and parity.max() <= 1e-4 and not np.concatenate(tap_errors).any()
            for step, threshold in [(0.1, 1e-4), (0.01, 1e-5)]:
                stable, error = [np.concatenate(fd_store[step][k]) for k in ["stable", "error"]]
                arrays[f"fd_{step:g}_stable"] = stable
                arrays[f"fd_{step:g}_normalized_error"] = error
                ok = stable.any() and error[stable].max() <= threshold
                passed = passed and bool(ok)
                route_checks["FD"][str(step)] = dict(stable_count=int(stable.sum()), nonsmooth_count=int((~stable).sum()),
                    stable_error=quant(error[stable]), all_error=quant(error), passed=bool(ok),
                    stable_failing_pose_ids=pid[stable & (error > threshold)].tolist(),
                    nonsmooth_pose_ids=pid[~stable].tolist())
            np.savez_compressed(out/f"P0_{route}.npz", **arrays)
            pairs = pairs_for(t, arrays["a_truth"], arrays["rho_m"], arrays["arc_m"], arrays["yaw_arc_rad"])
            np.savez_compressed(out/f"P0_PAIRS_{route}.npz", **pairs)
            supports[route] = support_report(pairs, t)
            route_checks["passed"] = bool(passed)
            checks[route] = route_checks
            inputs[route] = dict(paths={k: str(v) for k, v in paths.items()}, timed_count=len(t),
                                 raw_count=len(full), appended_count=len(full)-len(t), case=meta)
            put(out/"P0_CHECKS.json", checks); put(out/"INPUT_INDEX.json", inputs)
            put(out/"SUPPORT.json", supports); put(out/"SOURCE_HASHES.json", hashes)
            print(route, "P0", "PASS" if passed else "STOP", "parity_max", float(parity.max()),
                  "support", [x["status"] for x in supports[route]], flush=True)
            if not passed:
                raise RuntimeError("P0_SOURCE_OR_DERIVATIVE_GATE_FAILED:"+route)
        put(out/"P0_STATUS.json", dict(status="PASS_INPUTS", later_stages="NOT_RUN", checks=checks,
                                     finished_utc=dt.datetime.now(dt.timezone.utc).isoformat()))
    except Exception as exc:
        put(out/"P0_STATUS.json", dict(status="STOP_UNSUPPORTED_INPUT", error=str(exc), traceback=traceback.format_exc(),
                                     finished_utc=dt.datetime.now(dt.timezone.utc).isoformat(), later_stages="NOT_RUN"))
        put(out/"SOURCE_HASHES.json", hashes)
        raise
    finally:
        files = sorted(p for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS")
        (out/"SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in files), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(); run(args.out.resolve())
