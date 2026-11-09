#!/usr/bin/env python3
"""Evaluator-only decomposition of RF -> estimated gyro bias -> DR reference.

The channel decomposition is exact algebra on frozen archived traces, NOT a
closed-loop channel-removal experiment. Local reference interventions hold the
same pre-RF anchor pose and raw controls fixed while changing only constant bg.
The window-average bias uses target truth and is deliberately oracle-only.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def wrap(x):
    return (x + np.pi) % (2 * np.pi) - np.pi


def statistics(x):
    x = np.asarray(x)
    return {"n": len(x), "mean": float(np.mean(x)), "rmse": float(np.sqrt(np.mean(x*x))),
            "median_abs": float(np.median(abs(x))), "p95_abs": float(np.quantile(abs(x), .95)),
            "p99_abs": float(np.quantile(abs(x), .99)), "max_abs": float(max(abs(x)))}


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def bias_decomposition(tr, on):
    n = len(tr["x"])
    dr = tr["K"][:, 3, 0] * tr["nu"][:, 0]
    ds = tr["K"][:, 3, 1] * tr["nu"][:, 1]
    actual = tr["x"][:, 3] - tr["prior"][:, 3]
    initial = float(tr["prior"][0, 3])
    cr, cs = np.cumsum(dr), np.cumsum(ds)
    pr, ps = np.r_[0., cr[:-1]], np.r_[0., cs[:-1]]
    identities = {
        "per_update_bg_r_plus_s_max_rad_s": float(np.max(abs(actual - dr - ds))),
        "prediction_preserves_bg_max_rad_s": float(np.max(abs(tr["prior"][1:, 3] - tr["x"][:-1, 3]))),
        "cumulative_reconstructs_posterior_bg_max_rad_s": float(np.max(abs(initial + cr + cs - tr["x"][:, 3]))),
        "cumulative_reconstructs_prior_bg_max_rad_s": float(np.max(abs(initial + pr + ps - tr["prior"][:, 3]))),
        "rejected_actual_delta_bg_max_rad_s": float(np.max(abs(actual[~tr["mask"]]))) if (~tr["mask"]).any() else 0.,
        "initial_bg_rad_s": initial,
        "online_x0_bg_rad_s": float(on["x0"][3]),
    }
    assert max(v for k, v in identities.items() if k.endswith("max_rad_s")) < 1e-12
    return {"range_update": dr, "s_update": ds, "range_cumulative": cr, "s_cumulative": cs,
            "range_prior": pr, "s_prior": ps, "initial": initial}, identities


def window_reference(tr, on, truth, span_s, components):
    """Return a constant-bg path ensemble using actual archived pre-RF anchors.

    Output never feeds the main filter. Each row is a separate intervention;
    overlapping windows share samples and are not independent replicates.
    """
    t = on["t"]
    dt_regular = np.median(np.diff(t))
    length = int(round(span_s / dt_regular))
    assert abs(length * dt_regular - span_s) < 1e-9
    starts = np.arange(len(t) - length)
    indices = starts[:, None] + np.arange(1, length + 1)[None]
    ends = starts + length
    raw = on["gy"][indices]
    ds = on["ds"][indices]
    dt = on["dt"][indices]
    T = dt.sum(axis=1)
    assert np.max(abs(T - (t[ends] - t[starts]))) < 1e-10
    true_yaw = np.unwrap(truth[:, 2])
    target = true_yaw[ends] - true_yaw[starts]
    target_path = true_yaw[indices] - true_yaw[starts, None]
    oracle_bg = (raw.sum(axis=1) - target) / T
    anchor_bg = tr["prior"][starts, 3]
    variants = {"ZERO_BG": np.zeros(len(starts)), "ARCHIVED_PRE_RF_BG": anchor_bg,
                "ORACLE_WINDOW_AVERAGE_BG": oracle_bg}
    heading_errors, relative_xy_errors, truth_anchor_xy_errors, path_heading_rmse = {}, {}, {}, {}
    for name, bg in variants.items():
        turn = raw - bg[:, None] * dt
        integrated = np.cumsum(turn, axis=1)
        mid_yaw = integrated - turn/2
        step_lengths = ds * np.sinc(turn / (2*np.pi))
        phi = tr["prior"][starts, 2, None] + mid_yaw
        displacement = np.stack((np.sum(step_lengths*np.cos(phi), axis=1),
                                 np.sum(step_lengths*np.sin(phi), axis=1)), axis=1)
        true_displacement = truth[ends, :2] - truth[starts, :2]
        heading_errors[name] = np.degrees(wrap(integrated[:, -1] - target))
        relative_xy_errors[name] = np.linalg.norm(displacement - true_displacement, axis=1)
        # This distinct pose-oracle ablation changes anchor orientation, whereas
        # the primary three variants above keep that orientation identical.
        phi_truth_anchor = truth[starts, 2, None] + mid_yaw
        truth_anchor_displacement = np.stack((np.sum(step_lengths*np.cos(phi_truth_anchor), axis=1),
                                             np.sum(step_lengths*np.sin(phi_truth_anchor), axis=1)), axis=1)
        truth_anchor_xy_errors[name] = np.linalg.norm(truth_anchor_displacement - true_displacement, axis=1)
        path_error = np.degrees(wrap(integrated - target_path))
        path_heading_rmse[name] = np.sqrt(np.mean(path_error**2, axis=1))
    r_effect = -np.degrees(components["range_prior"][starts] * T)
    s_effect = -np.degrees(components["s_prior"][starts] * T)
    initial_effect = -np.degrees(components["initial"] * T)
    observed = wrap(np.radians(heading_errors["ARCHIVED_PRE_RF_BG"] - heading_errors["ZERO_BG"]))
    reconstructed = np.radians(r_effect + s_effect + initial_effect)
    identity = float(np.max(abs(wrap(observed - reconstructed))))
    assert identity < 1e-12
    assert np.max(abs(heading_errors["ORACLE_WINDOW_AVERAGE_BG"])) < 1e-9
    summary = {"span_s": span_s, "n_overlapping_windows": len(starts),
               "reference_pose": "IDENTICAL_ARCHIVED_PRE_RF_ANCHOR_FOR_ALL_BG_VARIANTS",
               "bg_effect_identity_max_rad": identity,
               "variants": {name: {"endpoint_relative_heading_error_deg": statistics(heading_errors[name]),
                                   "within_window_relative_heading_rmse_deg": statistics(path_heading_rmse[name]),
                                   "endpoint_displacement_error_m": statistics(relative_xy_errors[name]),
                                   "truth_anchor_pose_separate_ablation_displacement_error_m": statistics(truth_anchor_xy_errors[name])}
                            for name in variants}}
    excess = heading_errors["ARCHIVED_PRE_RF_BG"]**2 - heading_errors["ZERO_BG"]**2
    summary["archived_bg_vs_zero_heading_excess_mse_deg2"] = float(excess.mean())
    summary["archived_bg_worsens_relative_heading_fraction"] = float(np.mean(excess > 1e-12))
    rows = []
    for j, a in enumerate(starts):
        rows.append({"start_k": int(a), "end_k": int(ends[j]), "start_t_s": float(t[a]), "end_t_s": float(t[ends[j]]),
                     "span_s": span_s, "anchor_x_m": float(tr["prior"][a, 0]), "anchor_y_m": float(tr["prior"][a, 1]),
                     "anchor_yaw_rad": float(tr["prior"][a, 2]), "anchor_yaw_error_deg": float(np.degrees(wrap(tr["prior"][a, 2] - truth[a, 2]))),
                     "anchor_bg_deg_s": float(np.degrees(anchor_bg[j])), "oracle_window_bg_deg_s": float(np.degrees(oracle_bg[j])),
                     "rf_range_cumulative_bg_effect_deg": float(r_effect[j]), "rf_s_cumulative_bg_effect_deg": float(s_effect[j]),
                     "zero_endpoint_heading_error_deg": float(heading_errors["ZERO_BG"][j]),
                     "archived_bg_endpoint_heading_error_deg": float(heading_errors["ARCHIVED_PRE_RF_BG"][j]),
                     "oracle_endpoint_heading_error_deg": float(heading_errors["ORACLE_WINDOW_AVERAGE_BG"][j]),
                     "heading_excess_loss_vs_zero_deg2": float(excess[j]),
                     "zero_endpoint_displacement_error_m": float(relative_xy_errors["ZERO_BG"][j]),
                     "archived_bg_endpoint_displacement_error_m": float(relative_xy_errors["ARCHIVED_PRE_RF_BG"][j]),
                     "oracle_endpoint_displacement_error_m": float(relative_xy_errors["ORACLE_WINDOW_AVERAGE_BG"][j])})
    episodes = []
    harmful = excess > 1e-12
    boundaries = np.flatnonzero(np.diff(np.r_[False, harmful, False]))
    for a, b in zip(boundaries[::2], boundaries[1::2]):
        segment = slice(a, b)
        peak = int(a + np.argmax(excess[segment]))
        episodes.append({"first_anchor_t_s": float(t[starts[a]]), "last_anchor_t_s": float(t[starts[b-1]]),
                         "last_target_t_s": float(t[ends[b-1]]), "overlapping_windows": int(b-a),
                         "excess_loss_sum_deg2_not_independent": float(excess[segment].sum()),
                         "max_abs_archived_bg_endpoint_error_deg": float(max(abs(heading_errors["ARCHIVED_PRE_RF_BG"][segment]))),
                         "max_abs_zero_endpoint_error_deg": float(max(abs(heading_errors["ZERO_BG"][segment]))),
                         "peak_excess_anchor_t_s": float(t[starts[peak]]),
                         "peak_excess_anchor_bg_deg_s": float(np.degrees(anchor_bg[peak])),
                         "peak_range_effect_deg": float(r_effect[peak]), "peak_s_effect_deg": float(s_effect[peak])})
    episodes.sort(key=lambda r: r["excess_loss_sum_deg2_not_independent"], reverse=True)
    summary["largest_harmful_episode_by_overlapping_loss_sum"] = episodes[0] if episodes else None
    return summary, rows, episodes


def run_case(route, arm, traces, assets, out, lock):
    tp = traces/route/f"{route}_{arm}.npz"
    ep = assets/f"{route}_B0_Full_10__evaluator.npz"
    op = assets/f"{route}_B0_Full_10__online.npz"
    assert sha(tp) == json.loads((tp.parent/"SHA256.json").read_text())[tp.name]
    for p in (ep, op):
        record = next(r for r in lock["files"] if r["asset_name"] == p.name)
        assert p.stat().st_size == record["size"] and sha(p) == record["sha256"]
    tr, on, ev = load(tp), load(op), load(ep)
    assert np.array_equal(on["t"], ev["t"]) and np.array_equal(on["pose_id"], ev["pose_id"])
    components, identities = bias_decomposition(tr, on)
    obs_yaw = np.r_[0., np.diff(np.unwrap(ev["truth"][:, 2]))]
    gyro_increment_error = on["gy"][1:] - obs_yaw[1:]
    result = {"route": route, "arm": arm, "n": len(tr["x"]),
              "identities": identities,
              "input_hashes": {str(p): sha(p) for p in (tp, op, ep)},
              "raw_gyro_increment_error_deg": statistics(np.degrees(gyro_increment_error)),
              "raw_gyro_total_error_deg": float(np.degrees(gyro_increment_error.sum())),
              "posterior_bg_deg_s_about_zero_diagnostic": statistics(np.degrees(tr["x"][:, 3])),
              "final_bg_decomposition_deg_s": {"initial": float(np.degrees(components["initial"])),
                                               "range_cumulative": float(np.degrees(components["range_cumulative"][-1])),
                                               "s_cumulative": float(np.degrees(components["s_cumulative"][-1])),
                                               "posterior": float(np.degrees(tr["x"][-1, 3]))},
              "windows": {}}
    update_rows=[]
    for k in range(len(tr["x"])):
        update_rows.append({"route":route,"arm":arm,"k":k,"t_s":float(on["t"][k]),"accepted":bool(tr["mask"][k]),
                            "prior_bg_deg_s":float(np.degrees(tr["prior"][k,3])),
                            "posterior_bg_deg_s":float(np.degrees(tr["x"][k,3])),
                            "range_delta_bg_deg_s":float(np.degrees(components["range_update"][k])),
                            "s_delta_bg_deg_s":float(np.degrees(components["s_update"][k])),
                            "range_cumulative_bg_deg_s":float(np.degrees(components["range_cumulative"][k])),
                            "s_cumulative_bg_deg_s":float(np.degrees(components["s_cumulative"][k])),
                            "innovation_range_m":float(tr["nu"][k,0]),"innovation_s":float(tr["nu"][k,1]),
                            "K_bg_range_rad_s_per_m":float(tr["K"][k,3,0]),"K_bg_s_rad_s":float(tr["K"][k,3,1])})
    write_csv(out/f"{route}_{arm}_BIAS_UPDATES.csv",update_rows)
    for span in (2.,5.,10.):
        summary, rows, episodes = window_reference(tr,on,ev["truth"],span,components)
        result["windows"][str(int(span))] = summary
        write_csv(out/f"{route}_{arm}_WINDOW_{int(span)}S.csv",rows)
        write_csv(out/f"{route}_{arm}_HARMFUL_EPISODES_{int(span)}S.csv",episodes)
    return result


def source_transition_check(core_path, traces, assets, out):
    """Deterministic crosscheck of the vectorized experiment against source."""
    spec=importlib.util.spec_from_file_location("source_core_bias_audit",core_path)
    core=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=core
    spec.loader.exec_module(core)
    max_yaw,max_xy,trials=0.,0.,0
    for route in ("R2","R4","R5"):
        on=load(assets/f"{route}_B0_Full_10__online.npz")
        ev=load(assets/f"{route}_B0_Full_10__evaluator.npz")
        for arm in ("B_FROZEN","B_BIAS_COV"):
            tr=load(traces/route/f"{route}_{arm}.npz")
            for span in (2,5,10):
                with (out/f"{route}_{arm}_WINDOW_{span}S.csv").open(encoding="utf-8-sig") as f:
                    table=list(csv.DictReader(f))
                for i in (0,len(table)//3,2*len(table)//3,len(table)-1):
                    row=table[i];a=int(row["start_k"]);k=int(row["end_k"])
                    variants=(("zero",0.),("archived_bg",tr["prior"][a,3]),
                              ("oracle",np.radians(float(row["oracle_window_bg_deg_s"]))))
                    for mode,bg in variants:
                        x=tr["prior"][a].copy();x[3]=bg
                        for j in range(a+1,k+1):
                            x=core.transition(x,on["ds"][j],on["gy"][j],on["dt"][j])[0]
                        yaw_error=np.degrees(core.wrap((x[2]-tr["prior"][a,2])-(ev["truth"][k,2]-ev["truth"][a,2])))
                        displacement=(x[:2]-tr["prior"][a,:2])-(ev["truth"][k,:2]-ev["truth"][a,:2])
                        max_yaw=max(max_yaw,abs(float(yaw_error)-float(row[f"{mode}_endpoint_heading_error_deg"])))
                        max_xy=max(max_xy,abs(float(np.linalg.norm(displacement))-float(row[f"{mode}_endpoint_displacement_error_m"])))
                        trials+=1
    assert max_yaw<1e-9 and max_xy<1e-12
    return {"status":"PASS","trials":trials,
            "max_relative_heading_error_vs_source_transition_deg":max_yaw,
            "max_displacement_error_vs_source_transition_m":max_xy,
            "source_core_sha256":sha(core_path),
            "selection":"6 route-arm groups x 2/5/10 seconds x start/thirds/final anchors x zero/archive/oracle bg; deterministic representative samples, not all windows"}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--traces",type=Path,required=True)
    p.add_argument("--assets",type=Path,required=True)
    p.add_argument("--input-lock",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--control-provenance",type=Path)
    p.add_argument("--source-core",type=Path,default=Path(__file__).parents[1]/"FP_SC_RECOVERY_R0_R5_20261107/R45_sources/research/EKF4_RANGE_S_STAGED_20261014/core.py")
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
    lock=json.loads(a.input_lock.read_text())
    results=[]
    for route in ("R2","R4","R5"):
        for arm in ("B_FROZEN","B_BIAS_COV"):
            result=run_case(route,arm,a.traces,a.assets,a.out,lock)
            results.append(result)
            print("BIAS_AUDIT_COMPLETE",route,arm,flush=True)
    source_check=source_transition_check(a.source_core,a.traces,a.assets,a.out)
    (a.out/"SOURCE_TRANSITION_CHECK.json").write_text(json.dumps(source_check,indent=2)+"\n")
    provenance=None
    if a.control_provenance:
        audit=json.loads(a.control_provenance.read_text())
        assert audit["status"]=="PASS_CONTROL_PROVENANCE_AND_P2_ALGEBRA"
        for route in ("R2","R4","R5"):
            assert audit["routes"][route]["B0_true_bias_maxabs_rad_s"]==0.
            assert audit["routes"][route]["B0_recipe_maxabs_gyro_rad"]==0.
            assert audit["routes"][route]["online_sha256"]==sha(a.assets/f"{route}_B0_Full_10__online.npz")
        provenance={"path":str(a.control_provenance),"sha256":sha(a.control_provenance),
                    "true_gyro_bias_rad_s":0.,"generator_recipe_reproduction":"EXACT_GYRO_ALL_THREE_ROUTES"}
    output={"status":"PASS_EXACT_IDENTITIES_AND_ONE_FACTOR_REFERENCE_INTERVENTIONS",
            "causal_scope":"Channel terms are exact bookkeeping at fixed archived gains/innovations. The bg intervention changes only the local DR reference, not the original closed-loop replay.",
            "zero_bg_interpretation":("Zero matches the verified true injected gyro bias for these B0 archives; finite-window random gyro noise remains. It is not a universally valid deployment assumption." if provenance else "Zero is a diagnostic comparator; true injected gyro bias requires separately verified generator provenance. Finite-window residual noise remains even if true bias is zero."),
            "control_provenance":provenance,"source_transition_check":source_check,
            "oracle_warning":"Window-average bg uses current/future evaluator truth and is forbidden in runtime.",
            "anchor":"Immutable pre-RF snapshot; integrate controls a+1..k, no RF reanchor or bg refresh inside window.",
            "uncertainty_note":"Windows overlap; no IID confidence interval or independent sample-count claim.",
            "code_sha256":sha(__file__),"cases":results}
    (a.out/"RESULTS.json").write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    (a.out/"SHA256.json").write_text(json.dumps({p.name:sha(p) for p in sorted(a.out.iterdir()) if p.is_file() and p.name!="SHA256.json" and p.suffix!=".log"},indent=2)+"\n")
    print(json.dumps([{k:v for k,v in r.items() if k in ("route","arm","identities","final_bg_decomposition_deg_s")} | {"5s":r["windows"]["5"]} for r in results],indent=2))


if __name__=="__main__":main()
