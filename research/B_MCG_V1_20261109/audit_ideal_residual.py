#!/usr/bin/env python3
"""Truth-assisted diagnostic: synthetic ideal observer and channel residuals.

This executable intentionally reads evaluator truth to synthesize observations.
It is forbidden as a runtime policy.  The ideal observer is not a physical
clean CIR/LOS receiver; it removes every discrepancy from the frozen observer,
including detector/model/calibration error as well as noise and multipath.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import time

for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
import numpy as np
from scipy.stats import chi2

ARMS = ("RAW_B", "IDEAL_OBSERVER", "R_RESIDUAL_ONLY", "S_RESIDUAL_ONLY")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wrap(x):
    return (x + np.pi) % (2*np.pi) - np.pi


def json_save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def trace_metrics(tr, truth):
    e = tr["x"][:, :3] - truth
    e[:, 2] = wrap(e[:, 2])
    e4 = np.column_stack((e, tr["x"][:, 3]))
    cov = tr["P"][:, :3, :3]
    nees3 = np.einsum("ni,ni->n", e, np.linalg.solve(cov, e[..., None])[..., 0])
    nees4 = np.einsum("ni,ni->n", e4, np.linalg.solve(tr["P"], e4[..., None])[..., 0])
    bh = tr["x"][:, 3]**2 / tr["P"][:, 3, 3]
    return {
        "n": len(e), "accepted": int(tr["mask"].sum()),
        "heading_mse_deg2": float(np.mean(np.degrees(e[:, 2])**2)),
        "heading_rmse_deg": float(np.sqrt(np.mean(np.degrees(e[:, 2])**2))),
        "xy_mse_m2": float(np.mean(np.sum(e[:, :2]**2, axis=1))),
        "xy_rmse_cm": float(100*np.sqrt(np.mean(np.sum(e[:, :2]**2, axis=1)))),
        "bg_mse_deg2_s2": float(np.mean(np.degrees(tr["x"][:, 3])**2)),
        "bg_rmse_deg_s": float(np.sqrt(np.mean(np.degrees(tr["x"][:, 3])**2))),
        "bg_p99_abs_deg_s": float(np.quantile(abs(np.degrees(tr["x"][:, 3])), .99)),
        "bg_max_abs_deg_s": float(np.max(abs(np.degrees(tr["x"][:, 3])))),
        "bg_final_deg_s": float(np.degrees(tr["x"][-1, 3])),
        "bg95_coverage": float(np.mean(bh <= chi2.ppf(.95, 1))),
        "mean_nees3": float(nees3.mean()), "mean_nees4": float(nees4.mean()),
        "pose95_coverage": float(np.mean(nees3 <= chi2.ppf(.95, 3))),
        "state4_95_coverage": float(np.mean(nees4 <= chi2.ppf(.95, 4))),
    }


def parity(actual, archived):
    result = {}
    for key in ("x", "P", "prior", "Pprior", "h", "H", "mu", "Reff", "K", "nu", "mask"):
        a, b = actual[key], archived[key]
        assert a.shape == b.shape
        if a.dtype == bool:
            result[key] = int(np.count_nonzero(a != b))
        else:
            result[key] = float(np.max(abs(a-b)/np.maximum(1., abs(b))))
    assert max(result.values()) <= 1e-10, ("RAW_B_ARCHIVE_PARITY_FAILED", result)
    return result


def pool(cases):
    n = sum(x["n"] for x in cases)
    pooled = {}
    for arm in ARMS:
        means = ("heading_mse_deg2", "xy_mse_m2", "bg_mse_deg2_s2", "mean_nees3", "mean_nees4",
                 "bg95_coverage", "pose95_coverage", "state4_95_coverage")
        m = {key: float(sum(c["n"]*c["metrics"][arm][key] for c in cases)/n) for key in means}
        m.update(n=n, accepted=sum(c["metrics"][arm]["accepted"] for c in cases),
                 heading_rmse_deg=float(np.sqrt(m["heading_mse_deg2"])),
                 xy_rmse_cm=float(100*np.sqrt(m["xy_mse_m2"])),
                 bg_rmse_deg_s=float(np.sqrt(m["bg_mse_deg2_s2"])))
        pooled[arm] = m
    return pooled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--traces", type=Path, required=True)
    ap.add_argument("--control-provenance", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--model-truth-out", type=Path, required=True)
    args = ap.parse_args()
    repo = args.repo.resolve()
    sys.path.insert(0, str(repo/"research/FP_NATIVE_B_CAUSAL_ABLATION_20261108"))
    from fp_ns_ablation import load_original_replay, identical_input_condition
    args.out.mkdir(parents=True, exist_ok=True)
    args.model_truth_out.mkdir(parents=True, exist_ok=True)
    provenance = json.loads(args.control_provenance.read_text())
    assert provenance["status"] == "PASS_CONTROL_PROVENANCE_AND_P2_ALGEBRA"
    for r in ("R2", "R4", "R5"):
        assert provenance["routes"][r]["B0_true_bias_maxabs_rad_s"] == 0.
        assert provenance["routes"][r]["B0_recipe_maxabs_gyro_rad"] == 0.
    start = time.monotonic()
    print("LOAD_PINNED_SOURCE_FFD", flush=True)
    r45, core, online, model, hashes = load_original_replay(repo)
    contract = {
        "status": "RUNNING", "diagnostic_only": True, "runtime_eligible": False,
        "source_commit": "c141839093d1a2e4a76f91eea632cb6467163e28",
        "code_sha256": sha(__file__), "source_hashes": hashes,
        "control_provenance_sha256": sha(args.control_provenance),
        "arms": list(ARMS), "primary_calibration": "B_FROZEN_ONLY",
        "ideal_definition": "z_ideal[k]=SourceFFD_h(truth[k])+original_muMB[k]",
        "R_RESIDUAL_ONLY": "raw B range and ideal observer s",
        "S_RESIDUAL_ONLY": "ideal observer range and raw B s",
        "unchanged": ["raw controls", "Q", "initial state/P", "original SourceFFD", "muMB", "muBASE", "base R", "distance-dependent main s variance"],
        "gating": "Original own raw-observation legacy shadow per arm; muBASE unchanged. Ideal observer is main-model-consistent; shadow still differs by muMB-muBASE.",
        "causal_scope": "Full recursive intervention in observation components; observed effects include shadow-gate/state interactions. It does not isolate physical multipath alone.",
        "no_physical_clean_claim": "Ideal observer observations are synthetic values, not a re-detected clean CIR or Native_LOS.",
        "exposed_scope": "R2/R4/R5, one corridor, B0, seed10. Routes share gyro-noise prefix; no scene/seed generalization.",
    }
    json_save(args.out/"CONTRACT.json", contract)
    cases = []
    for route in ("R2", "R4", "R5"):
        case = route+"_B0_Full_10"
        on, ev = r45.data(case, "online.npz"), r45.data(case, "evaluator.npz")
        assert np.array_equal(on["t"], ev["t"]) and np.array_equal(on["pose_id"], ev["pose_id"])
        controls = {k: on[k] for k in ("ds", "gy", "dt")}
        controls["x0"] = on["x0"][:3]
        B, native, zN, zB = identical_input_condition(on, r45, case)
        truth = ev["truth"]
        htruth = np.concatenate([model.batch(truth[i:i+64], r45.SPEC, gradient=False)[0] for i in range(0, len(truth), 64)])
        assert htruth.shape == (len(truth), 2) and np.isfinite(htruth).all()
        hp = args.model_truth_out/f"{route}_htruth.npz"
        np.savez_compressed(hp, htruth=htruth, truth=truth, t=on["t"], pose_id=on["pose_id"],
                            source_hashes_json=json.dumps(hashes, sort_keys=True),
                            evaluator_sha256=provenance["routes"][route]["evaluator_sha256"])
        json_save(args.model_truth_out/f"{route}_htruth.json", {"diagnostic_only": True, "npz_sha256": sha(hp),
                  "htruth_array_sha256": hashlib.sha256(np.ascontiguousarray(htruth).tobytes()).hexdigest(),
                  "n": len(truth), "source_hashes": hashes})
        zI = htruth + on["muMB"]
        zs = {"RAW_B": zB, "IDEAL_OBSERVER": zI,
              "R_RESIDUAL_ONLY": np.column_stack((zB[:, 0], zI[:, 1])),
              "S_RESIDUAL_ONLY": np.column_stack((zI[:, 0], zB[:, 1]))}
        metrics, traces = {}, {}
        for arm in ARMS:
            print("REPLAY", route, arm, flush=True)
            packet = dict(on); packet["z"] = zs[arm]
            tr = online.replay(packet, controls, "W0", core, model, r45.SPEC)
            assert all(np.isfinite(v).all() for v in tr.values())
            assert np.linalg.eigvalsh(tr["P"]).min() > -1e-12
            if arm == "RAW_B":
                archive = args.traces/route/f"{route}_B_FROZEN.npz"
                expected = json.loads((archive.parent/"SHA256.json").read_text())[archive.name]
                assert sha(archive) == expected
                with np.load(archive, allow_pickle=False) as old:
                    par = parity(tr, old)
            metrics[arm] = trace_metrics(tr, truth)
            traces[arm] = tr
            np.savez_compressed(args.out/f"{route}_{arm}.npz", **tr, z=zs[arm], truth=truth, t=on["t"],
                                pose_id=on["pose_id"], B_tap=B, ideal_htruth=htruth)
            json_save(args.out/f"{route}_{arm}_METRICS.json", metrics[arm])
        result = {"route": route, "n": len(truth), "raw_B_parity": par,
                  "htruth_sha256": sha(hp), "metrics": metrics,
                  "gate_disagreements_vs_rawB": {arm: int(np.count_nonzero(traces[arm]["mask"] != traces["RAW_B"]["mask"])) for arm in ARMS},
                  "observation_discrepancy_from_ideal": {
                      "range_bias_m": float(np.mean(zB[:, 0]-zI[:, 0])),
                      "range_rmse_m": float(np.sqrt(np.mean((zB[:, 0]-zI[:, 0])**2))),
                      "s_bias": float(np.mean(zB[:, 1]-zI[:, 1])),
                      "s_rmse": float(np.sqrt(np.mean((zB[:, 1]-zI[:, 1])**2)))},
                  "interactions": {}}
        for metric in ("heading_mse_deg2", "xy_mse_m2", "bg_mse_deg2_s2"):
            m = {arm: metrics[arm][metric] for arm in ARMS}
            result["interactions"][metric] = {
                "range_residual_minus_ideal": m["R_RESIDUAL_ONLY"]-m["IDEAL_OBSERVER"],
                "s_residual_minus_ideal": m["S_RESIDUAL_ONLY"]-m["IDEAL_OBSERVER"],
                "raw_minus_ideal": m["RAW_B"]-m["IDEAL_OBSERVER"],
                "coupled_interaction": m["RAW_B"]-m["R_RESIDUAL_ONLY"]-m["S_RESIDUAL_ONLY"]+m["IDEAL_OBSERVER"]}
        json_save(args.out/f"{route}_SUMMARY.json", result)
        cases.append(result)
        json_save(args.out/"PARTIAL.json", {"cases": cases})
        print("COMPLETE", route, flush=True)
    contract["status"] = "PASS_REPLAY_AND_BASELINE_PARITY"
    output = {"status": "PASS_REPLAY_AND_BASELINE_PARITY", "contract": contract, "cases": cases,
              "pooled": pool(cases), "elapsed_s": time.monotonic()-start}
    json_save(args.out/"RESULTS.json", output)
    json_save(args.out/"CONTRACT.json", contract)
    json_save(args.out/"SHA256.json", {p.name: sha(p) for p in sorted(args.out.iterdir()) if p.is_file() and p.name != "SHA256.json" and p.suffix != ".log"})
    print(json.dumps(output["pooled"], indent=2), flush=True)


if __name__ == "__main__":
    main()
