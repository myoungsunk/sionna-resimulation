#!/usr/bin/env python3
"""One-factor diagnosis of one clean-return false conflict.

Evaluator-only interventions. The current observation, main prior/covariance,
Jacobian, residual, R, and legacy gate stay fixed. Historical RF or the monitor
anchor alone changes. These are hindsight diagnostics, not deployable policy.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
import numpy as np
from experiment import context, config_for, read_npz
from evaluate_delivery import independent_joseph, losses
from mcg import profile_history, score_current, weights


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def dump(path, value):
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    if (args.out / "RESULTS.json").exists():
        raise FileExistsError("Completed diagnostic is immutable; choose a new output directory")
    code_dir = Path(__file__).parent
    code_names = ("mcg.py", "experiment.py", "evaluate_delivery.py", Path(__file__).name)
    code_hashes = {name: sha(code_dir / name) for name in code_names}
    contract = json.loads((args.recovery / "CONTRACT.json").read_text())
    assert contract["runtime_code_sha256"]["mcg.py"] == code_hashes["mcg.py"]
    assert contract["runtime_code_sha256"]["experiment.py"] == code_hashes["experiment.py"]
    path = args.recovery / "R4_A186_ACTIVE_RS_TAU2.npz"
    trace = read_npz(path)
    k = 26
    a = int(trace["anchor_index"][k])
    assert a == 1 and int(trace["original_k"][k]) == 212
    assert np.array_equal(trace["constructed_z"][k], trace["ideal_z"][k])
    r45, core, online, model, source_hashes = context()
    original = r45.data("R4_B0_Full_10", "online.npz")
    original_ids = trace["original_k"][a:k + 1]
    controls = np.column_stack([original[name][original_ids] for name in ("ds", "gy", "dt")])
    anchor = trace["prior"][a].copy()
    anchor_true_pose = anchor.copy()
    anchor_true_pose[:3] = trace["truth"][a]
    anchor_zero_bg = anchor.copy()
    anchor_zero_bg[3] = 0.
    interventions = (
        ("ACTUAL_HISTORY", anchor, trace["constructed_z"][a:k]),
        ("IDEAL_HISTORY_ONLY", anchor, trace["ideal_z"][a:k]),
        ("TRUTH_ANCHOR_POSE_ONLY", anchor_true_pose, trace["constructed_z"][a:k]),
        ("ZERO_ANCHOR_BG_ONLY", anchor_zero_bg, trace["constructed_z"][a:k]),
    )
    truth_current = trace["truth"][k:k + 1]
    update_args = tuple(trace[name][k].copy() for name in ("prior", "Pprior", "H", "nu", "Rbase"))
    allowed = bool(trace["mask"][k])
    full = independent_joseph(*update_args, np.ones(2), allowed)[0]
    skip_loss = losses(trace["prior"][k:k + 1], truth_current)[0]
    full_loss = losses(full[None], truth_current)[0]
    cases = []
    started = time.perf_counter()
    for name, reference, history_z in interventions:
        print("RECOVERY_CAUSE", name, flush=True)
        cfg = config_for(tau=2., span=5.)
        profile = profile_history(core, model, r45.SPEC, reference, controls,
                                  trace["t"][a:k + 1], history_z,
                                  trace["mu"][a:k], trace["Rbase"][a:k + 1], cfg)
        scored = score_current(profile, trace["constructed_z"][k], trace["mu"][k])
        arms = []
        for tau in (2., 3.):
            decision_cfg = config_for(tau=tau, span=5.)
            beta, status = weights(scored, decision_cfg, "ACTIVE_RS")
            x, P, K, Reff, rows = independent_joseph(*update_args, beta, allowed)
            loss = losses(x[None], truth_current)[0]
            arms.append({"tau": tau, "beta": beta, "status": status, "loss_heading_deg2_xy_m2": loss,
                         "loss_minus_full_heading_deg2_xy_m2": loss - full_loss,
                         "loss_minus_skip_heading_deg2_xy_m2": loss - skip_loss,
                         "used_rows": rows.tolist(), "post_state": x})
            if name == "ACTUAL_HISTORY" and tau == 2.:
                assert np.max(abs(scored["scores"] - trace["scores"][k])) <= 1e-11, "ORIGINAL_SCORE_NOT_REPRODUCED"
                assert np.max(abs(beta - trace["beta"][k])) <= 1e-11, "ORIGINAL_WEIGHT_NOT_REPRODUCED"
                assert np.max(abs(x - trace["x"][k])) <= 1e-11, "ORIGINAL_UPDATE_NOT_REPRODUCED"
        np.savez_compressed(args.out / f"{name}.npz", candidate_h=profile["candidate_h"],
                            scores=scored["scores"], reference_anchor=reference, history_z=history_z,
                            controls=controls, t=trace["t"][a:k + 1],
                            current_z=trace["constructed_z"][k], prior=update_args[0],
                            Pprior=update_args[1], H=update_args[2], nu=update_args[3],
                            Rbase=update_args[4], truth_current=truth_current)
        cases.append({"name": name, "reference_anchor": reference,
                      "profile": {q: v for q, v in profile.items() if q != "candidate_h"},
                      "score": scored, "decisions": arms})
        assert code_hashes == {name: sha(code_dir / name) for name in code_names}, "SOURCE_CHANGED_DURING_DIAGNOSTIC"
    executed = args.out / "executed_code"
    executed.mkdir(exist_ok=True)
    for name in code_names:
        shutil.copyfile(code_dir / name, executed / name)
    result = {
        "status": "PASS_FIXED_CURRENT_ONE_FACTOR_RECONSTRUCTION",
        "diagnostic_only": True,
        "selected_episode": {"route": "R4", "episode_anchor_original_k": 186,
                             "episode_current_k": k, "original_current_k": 212,
                             "absolute_current_t_s": float(trace["absolute_t"][k]),
                             "monitor_anchor_episode_k": a, "history_n": k - a,
                             "current_sample_phase": "FIRST_IDEAL_CLEAN_RETURN"},
        "frozen_quantities": ["current_z", "current_mu", "main_prior", "main_Pprior", "main_H", "main_nu", "main_Rbase", "legacy_gate", "raw_controls", "historical_Rbase", "historical_mu"],
        "source_trace_sha256": sha(path), "runtime_code_sha256": code_hashes,
        "source_hashes": source_hashes,
        "same_current_full_loss_heading_deg2_xy_m2": full_loss,
        "same_current_skip_loss_heading_deg2_xy_m2": skip_loss,
        "same_current_full_gain_vs_skip_heading_deg2_xy_m2": skip_loss - full_loss,
        "legacy_accepted": allowed, "cases": cases,
        "limitations": [
            "Four interventions at one hindsight-selected synthetic transition do not establish an error rate.",
            "Ideal historical RF and true anchor pose are evaluator-only oracle interventions.",
            "A low finite candidate spread is not a globally complete feasible-set certificate; a separate exact feasibility audit is required.",
            "Changing only the monitor history or anchor does not rerun the main filter before the current sample.",
            "Thresholds were not tuned from this diagnostic; tau2 and tau3 are fixed sensitivity settings."
        ],
        "elapsed_s": time.perf_counter() - started,
    }
    dump(args.out / "RESULTS.json", result)
    manifest = {str(p.relative_to(args.out)): sha(p) for p in args.out.rglob("*") if p.is_file() and p.name != "SHA256.json"}
    dump(args.out / "SHA256.json", manifest)
    print(json.dumps(clean({"status": result["status"], "elapsed_s": result["elapsed_s"], "cases": [{"name": c["name"], "score": c["score"], "decisions": c["decisions"]} for c in cases]})), flush=True)


if __name__ == "__main__":
    main()
