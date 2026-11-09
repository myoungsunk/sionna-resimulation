#!/usr/bin/env python3
"""P1: same-prior action opportunity on archived B traces.

This is an evaluator, never an inference policy.  Truth chooses oracle actions
only to measure an unattainable upper bound.  Each arm/row starts from its own
stored baseline prior; modified posteriors are NOT propagated to the next row.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np


DEFAULT_ACTIONS = {
    "FULL": (1.0, 1.0),
    "R_SOFT": (0.25, 1.0),
    "S_SOFT": (1.0, 0.25),
    "RS_SOFT": (0.25, 0.25),
    "DROP_R": (0.0, 1.0),
    "DROP_S": (1.0, 0.0),
    "R_SOFT_DROP_S": (0.25, 0.0),
    "DROP_R_S_SOFT": (0.0, 0.25),
    "SKIP": (0.0, 0.0),
}
LOSS_NAMES = ("heading_deg2", "xy_m2")
LOSS_TOL = np.array([1e-12, 1e-14])


def wrap(x):
    return (x + np.pi) % (2 * np.pi) - np.pi


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_npz(path):
    with np.load(path, allow_pickle=False) as f:
        return {k: f[k] for k in f.files}


def apply_action(prior, Pprior, H, nu, Rbase, beta, permitted=True):
    """Joseph update with diagonal PSD addition, or exact row removal.

    Inputs are a single 4D state/2D observation.  Returned x/P/K never alias
    inputs.  K keeps two columns even if an observation row is removed.
    `permitted=False` is an actual legacy rejection, not a hypothetical update.
    """
    x = np.array(prior, dtype=float, copy=True)
    P = np.array(Pprior, dtype=float, copy=True)
    H = np.asarray(H, dtype=float)
    nu = np.asarray(nu, dtype=float)
    R = np.array(Rbase, dtype=float, copy=True)
    b = np.asarray(beta, dtype=float)
    if b.shape != (2,) or not np.isfinite(b).all() or np.any(b < 0) or np.any(b > 1):
        raise ValueError("beta must be two finite values in [0,1]")
    if x.shape != (4,) or P.shape != (4, 4) or H.shape != (2, 4) or nu.shape != (2,) or R.shape != (2, 2):
        raise ValueError("Unexpected state or observation shape")
    if not all(np.isfinite(a).all() for a in (x, P, H, nu, R)):
        raise ValueError("Nonfinite update ingredients")
    K = np.zeros((4, 2))
    rows = np.flatnonzero(b > 0)
    for c in rows:
        R[c, c] += (1 / b[c] - 1) * Rbase[c, c]
    if not permitted or len(rows) == 0:
        return x, P, K, R
    Hr = H[rows]
    Rr = R[np.ix_(rows, rows)]
    S = Hr @ P @ Hr.T + Rr
    S = (S + S.T) / 2
    gain = np.linalg.solve(S, Hr @ P).T
    K[:, rows] = gain
    x += gain @ nu[rows]
    x[2] = wrap(x[2])
    A = np.eye(4) - gain @ Hr
    cov = A @ P @ A.T + gain @ Rr @ gain.T
    return x, (cov + cov.T) / 2, K, R


def pose_losses(x, truth):
    x = np.asarray(x)
    truth = np.asarray(truth)
    e = x[..., :3] - truth
    return np.stack((np.degrees(wrap(e[..., 2])) ** 2,
                     np.sum(e[..., :2] ** 2, axis=-1)), axis=-1)


def evaluate_actions(truth, tr, beta_list=None, *, permitted=None):
    """Return candidate posterior/loss arrays in N x A order.

    beta_list may be a name->(beta_r,beta_s) mapping or a list of pairs.
    The default enforces the original per-row gate mask. To evaluate rejected
    rows hypothetically, explicitly pass permitted=np.ones(N,dtype=bool).
    """
    if beta_list is None:
        actions = DEFAULT_ACTIONS
    elif hasattr(beta_list, "items"):
        actions = dict(beta_list)
    else:
        actions = {f"action_{i}": tuple(b) for i, b in enumerate(beta_list)}
    n = len(tr["prior"])
    truth = np.asarray(truth)
    if truth.shape != (n, 3):
        raise ValueError("Truth must align exactly with trace rows")
    mask = np.asarray(tr["mask"] if permitted is None else permitted, bool)
    if mask.shape != (n,):
        raise ValueError("Gate shape mismatch")
    names = list(actions)
    x = np.empty((n, len(names), 4))
    cov = np.empty((n, len(names), 4, 4))
    gain = np.empty((n, len(names), 4, 2))
    for i in range(n):
        for j, name in enumerate(names):
            x[i, j], cov[i, j], gain[i, j], _ = apply_action(
                tr["prior"][i], tr["Pprior"][i], tr["H"][i],
                tr["nu"][i], tr["Reff"][i], actions[name], mask[i])
    return {"actions": names, "betas": np.asarray(list(actions.values())),
            "x": x, "P": cov, "K": gain,
            "losses": pose_losses(x, truth[:, None]), "mask": mask.copy()}


def relative_max(actual, expected, angle_column=None):
    d = np.asarray(actual, float) - np.asarray(expected, float)
    if angle_column is not None:
        d[..., angle_column] = wrap(d[..., angle_column])
    return float(np.max(np.abs(d) / np.maximum(1.0, np.abs(expected))))


def summarize(losses, mask, names):
    losses = np.asarray(losses)
    mask = np.asarray(mask, bool)
    fi, si = names.index("FULL"), names.index("SKIP")
    full, skip = losses[:, fi], losses[:, si]
    diff = full - skip
    accepted = int(mask.sum())
    full_good = diff < -LOSS_TOL
    full_bad = diff > LOSS_TOL
    counts = {
        "full_benefits_both": int(np.sum(mask & full_good.all(axis=1))),
        "full_harms_both": int(np.sum(mask & full_bad.all(axis=1))),
        "full_benefits_heading_harms_xy": int(np.sum(mask & full_good[:, 0] & full_bad[:, 1])),
        "full_harms_heading_benefits_xy": int(np.sum(mask & full_bad[:, 0] & full_good[:, 1])),
        "full_tie_in_at_least_one": int(np.sum(mask & ~(full_good | full_bad).all(axis=1))),
    }
    delta = losses - full[:, None]
    no_worse = np.all(delta <= LOSS_TOL, axis=2)
    strict_any = np.any(delta < -LOSS_TOL, axis=2)
    pareto = no_worse & strict_any
    out = {"n": len(mask), "accepted": accepted, "rejected": len(mask) - accepted,
           "accepted_action_vs_skip_counts": counts,
           "accepted_with_pareto_improving_action": int(np.sum(mask & pareto.any(axis=1))),
           "accepted_with_action_strictly_better_both": int(np.sum(mask & (delta < -LOSS_TOL).all(axis=2).any(axis=1))),
           "metrics": {}, "actions": {}}
    for d, metric in enumerate(LOSS_NAMES):
        helpful = mask & (skip[:, d] > full[:, d] + LOSS_TOL[d])
        harmful = mask & (full[:, d] > skip[:, d] + LOSS_TOL[d])
        budget = float(np.sum(skip[helpful, d] - full[helpful, d]))
        oracle = losses[:, :, d].min(axis=1)
        constrained = np.where(no_worse, losses[:, :, d], np.inf).min(axis=1)
        out["metrics"][metric] = {
            "full_mean_loss": float(full[:, d].mean()),
            "skip_mean_loss": float(skip[:, d].mean()),
            "beneficial_update_count": int(helpful.sum()),
            "harmful_update_count": int(harmful.sum()),
            "beneficial_gain_sum": budget,
            "harmful_loss_sum": float(np.sum(full[harmful, d] - skip[harmful, d])),
            "metric_specific_oracle_mean_loss": float(oracle.mean()),
            "metric_specific_oracle_saving_sum": float(np.sum(full[:, d] - oracle)),
            "pareto_constrained_metric_oracle_mean_loss": float(constrained.mean()),
            "note": "Per-metric oracle selections can differ. No joint deployed policy implied.",
        }
    for j, name in enumerate(names):
        row = {"pareto_improvement_accepted_count": int(np.sum(mask & pareto[:, j])),
               "harmful_in_both_accepted_count": int(np.sum(mask & (delta[:, j] > LOSS_TOL).all(axis=1)))}
        for d, metric in enumerate(LOSS_NAMES):
            helpful = mask & (skip[:, d] > full[:, d] + LOSS_TOL[d])
            budget = out["metrics"][metric]["beneficial_gain_sum"]
            lost = float(np.sum(np.maximum(losses[helpful, j, d] - full[helpful, d], 0)))
            row[metric] = {
                "mean_loss": float(losses[:, j, d].mean()),
                "net_saving_sum_vs_full": float(np.sum(full[:, d] - losses[:, j, d])),
                "beneficial_lost_gain_sum": lost,
                "beneficial_lost_gain_ratio": lost / budget if budget > 0 else None,
                "lost_gain_status": "ESTIMABLE" if budget > 0 else "NOT_ESTIMABLE",
                "five_percent_budget_pass": bool(lost / budget <= .05) if budget > 0 else None,
            }
        out["actions"][name] = row
    return out


def run_one(route, arm, traces, assets, out, lock):
    path = traces / route / f"{route}_{arm}.npz"
    expected = json.loads((path.parent / "SHA256.json").read_text())[path.name]
    assert sha256(path) == expected, ("TRACE_SHA", path)
    tr = load_npz(path)
    ep = assets / f"{route}_B0_Full_10__evaluator.npz"
    op = assets / f"{route}_B0_Full_10__online.npz"
    for p in (ep, op):
        record = next(r for r in lock["files"] if r["asset_name"] == p.name)
        assert p.stat().st_size == record["size"] and sha256(p) == record["sha256"], ("INPUT_SHA", p)
    ev, on = load_npz(ep), load_npz(op)
    assert np.array_equal(ev["t"], on["t"]) and np.array_equal(ev["pose_id"], on["pose_id"])
    assert len(tr["x"]) == len(ev["truth"])
    actual = evaluate_actions(ev["truth"], tr)
    # Independently verify the algebraic reconstruction before any oracle claim.
    parity = {"x": relative_max(actual["x"][:, 0], tr["x"], 2),
              "P": relative_max(actual["P"][:, 0], tr["P"]),
              "K": relative_max(actual["K"][:, 0], tr["K"])}
    assert max(parity.values()) <= 1e-10, ("SAME_PRIOR_PARITY", route, arm, parity)
    if (~tr["mask"]).any():
        assert np.max(abs(actual["K"][~tr["mask"]])) == 0
        assert np.max(abs(actual["x"][~tr["mask"]] - tr["prior"][~tr["mask"], None])) == 0
    assert np.linalg.eigvalsh(actual["P"]).min() > -1e-12
    reported = json.loads((path.parent / "RESULTS.json").read_text())["score"][arm]
    h_mse, xy_mse = actual["losses"][:, 0].mean(axis=0)
    assert abs(h_mse - reported["heading_mse_deg2"]) < 1e-10
    assert abs(xy_mse - reported["xy_mse_m2"]) < 1e-12
    rejected = ~tr["mask"]
    forced = None
    if rejected.any():
        subset = {k: v[rejected] for k, v in tr.items() if np.ndim(v) > 0 and len(v) == len(rejected)}
        forced = evaluate_actions(ev["truth"][rejected], subset, permitted=np.ones(rejected.sum(), bool))
    result = {"route": route, "arm": arm, "input_hashes": {str(p): sha256(p) for p in (path, ep, op)},
              "same_prior_full_parity": parity, "baseline_mse_reconciled": True,
              "actual_gate": summarize(actual["losses"], tr["mask"], actual["actions"]),
              "legacy_rejected_forced_update_hypothetical": summarize(forced["losses"], forced["mask"], forced["actions"]) if forced else None}
    np.savez_compressed(out / f"{route}_{arm}_ACTIONS.npz", actions=actual["actions"], betas=actual["betas"],
                        losses=actual["losses"], x=actual["x"], P=actual["P"], K=actual["K"],
                        mask=tr["mask"], truth=ev["truth"], t=ev["t"], pose_id=ev["pose_id"],
                        rejected_indices=np.flatnonzero(rejected),
                        rejected_forced_losses=forced["losses"] if forced else np.empty((0, len(actual["actions"]), 2)))
    (out / f"{route}_{arm}_SUMMARY.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return result, actual


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--traces", type=Path, required=True)
    p.add_argument("--assets", type=Path, required=True)
    p.add_argument("--input-lock", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--routes", nargs="+", default=["R2", "R4", "R5"])
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    lock = json.loads(a.input_lock.read_text())
    all_results, pooled, arrays = [], {}, {}
    for arm in ("B_FROZEN", "B_BIAS_COV"):
        parts, masks = [], []
        for route in a.routes:
            result, actual = run_one(route, arm, a.traces, a.assets, a.out, lock)
            all_results.append(result)
            parts.append(actual["losses"])
            masks.append(actual["mask"])
            arrays[(route, arm)] = actual
            print("P1_COMPLETED", route, arm, flush=True)
        pooled[arm] = summarize(np.concatenate(parts), np.concatenate(masks), actual["actions"])
    report = {"status": "PASS_RECONSTRUCTION_AND_EVALUATOR_CHECKS",
              "scientific_adoption_status": "NOT_TESTED_BY_P1",
              "scope": "Exposed R2/R4/R5 B0 Full seed10; local same-prior interventions only",
              "code_sha256": sha256(__file__), "input_lock_sha256": sha256(a.input_lock),
              "actions_predefined": {k: list(v) for k, v in DEFAULT_ACTIONS.items()},
              "metric_order": list(LOSS_NAMES), "comparison_tolerance": LOSS_TOL.tolist(),
              "selection_note": "Truth selected per-metric oracle is an opportunity upper bound, not runtime utility or a deployable policy.",
              "same_prior_note": "Each intervention resets to stored baseline prior; no modified state feeds the next time step. Natural B shadow mask retained.",
              "pooled": pooled, "cases": all_results}
    (a.out / "RESULTS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    with (a.out / "ACTION_METRICS.csv").open("w", newline="", encoding="utf-8-sig") as f:
        fields = ["arm", "action", "metric", "mean_loss", "net_saving_sum_vs_full", "beneficial_lost_gain_sum", "beneficial_lost_gain_ratio", "lost_gain_status", "five_percent_budget_pass"]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for arm, summary in pooled.items():
            for action, values in summary["actions"].items():
                for metric in LOSS_NAMES:
                    w.writerow({"arm": arm, "action": action, "metric": metric, **values[metric]})
    (a.out / "SHA256.json").write_text(json.dumps({p.name: sha256(p) for p in sorted(a.out.iterdir()) if p.is_file() and p.name != "SHA256.json" and p.suffix != ".log"}, indent=2) + "\n")
    print(json.dumps({k: {"n": v["n"], "accepted": v["accepted"], "metrics": v["metrics"], "counts": v["accepted_action_vs_skip_counts"], "pareto_opportunity": v["accepted_with_pareto_improving_action"]} for k, v in pooled.items()}, indent=2))


if __name__ == "__main__":
    main()
