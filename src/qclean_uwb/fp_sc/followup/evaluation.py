"""Evaluator-only labels, denominator-explicit metrics and clustered inference."""
from __future__ import annotations
import math
import numpy as np
from .contracts import ContractError, covariance, finite


def rate(n: int, d: int) -> float | None:
    return float(n/d) if d else None


def error_stats(values) -> dict:
    a = np.asarray(values, dtype=float)
    if a.ndim != 1 or not np.isfinite(a).all():
        raise ContractError("INVALID_ERROR_VECTOR")
    if not len(a):
        return {"n": 0, "status": "NOT_TESTED", "mae": None, "rmse": None}
    return dict(n=len(a), status="DESCRIPTIVE", bias=float(a.mean()),
                mae=float(np.mean(abs(a))), rmse=float(np.sqrt(np.mean(a*a))),
                p95=float(np.quantile(abs(a), .95)), p99=float(np.quantile(abs(a), .99)),
                maximum=float(np.max(abs(a))))


def selection_summary(rows: list[dict]) -> dict:
    """Rows contain evaluator-only labels; no labels are returned to a selector."""
    valid = [r for r in rows if r["reference_valid"] and r["raw_valid"]]
    normal = [r for r in valid if r["raw_tap"] == r["reference_tap"]]
    wrong = [r for r in valid if r["raw_tap"] != r["reference_tap"]]
    replaced = [r for r in valid if r["selected_tap"] != r["raw_tap"]]
    false = sum(r["selected_tap"] != r["reference_tap"] for r in normal)
    rescue = sum(r["selected_tap"] == r["reference_tap"] for r in wrong)
    high = [r for r in replaced if r.get("confidence_score") is not None and r["confidence_score"] >= .5]
    high_correct = sum(r["selected_tap"] == r["reference_tap"] for r in high)
    correct_replacements = sum(r["selected_tap"] == r["reference_tap"] for r in replaced)
    flags = [r for r in valid if r.get("flag") is not None]
    tp = sum(bool(r["flag"]) and r["raw_tap"] != r["reference_tap"] for r in flags)
    fp = sum(bool(r["flag"]) and r["raw_tap"] == r["reference_tap"] for r in flags)
    fn = sum(not r["flag"] and r["raw_tap"] != r["reference_tap"] for r in flags)
    tn = sum(not r["flag"] and r["raw_tap"] == r["reference_tap"] for r in flags)
    large = [r for r in wrong if abs(r["raw_tap"]-r["reference_tap"]) >= 2]
    recall = sum(r.get("reference_in_usable_pool", False) for r in large)
    out = dict(total=len(rows), eligible=len(valid), reference_unknown=sum(not r["reference_valid"] for r in rows),
               raw_invalid=sum(not r["raw_valid"] for r in rows), normal=len(normal), wrong=len(wrong),
               large_error=len(large), corrected=len(replaced), false_corrections=false, rescues=rescue,
               false_correction_rate=rate(false, len(normal)), rescue_rate=rate(rescue, len(wrong)),
               replacement_precision=rate(correct_replacements, len(replaced)),
               high_confidence_corrected=len(high), high_confidence_precision=rate(high_correct,len(high)),
               replacement_coverage=rate(len(replaced), len(valid)), large_candidate_recall=rate(recall, len(large)),
               detection=dict(tp=tp, fp=fp, fn=fn, tn=tn, available=len(flags), unavailable=len(valid)-len(flags),
                              tpr=rate(tp, tp+fn), fpr=rate(fp, fp+tn), precision=rate(tp, tp+fp)),
               inference="DESCRIPTIVE_NOT_IID_SAFETY_PROBABILITY")
    subsets = {"all_valid": valid, "normal": normal, "wrong": wrong, "changed": replaced,
               "unchanged": [r for r in valid if r["selected_tap"] == r["raw_tap"]],
               "abstained": [r for r in valid if str(r.get("reason", "")).startswith(("HOLD", "ABSTAIN", "NO_", "NULL_"))]}
    out["subsets"] = {}
    for name, subset in subsets.items():
        metrics = {"n": len(subset)}
        for field in ("raw_range_error", "selected_range_error", "raw_s_error", "selected_s_error"):
            vals = [r[field] for r in subset if r.get(field) is not None]
            metrics[field] = error_stats(vals)
            metrics[field]["unavailable"] = len(subset)-len(vals)
        for field in ("range", "s"):
            available = [r for r in subset if r.get(f"raw_{field}_error") is not None and r.get(f"selected_{field}_error") is not None]
            metrics[f"{field}_harmful"] = sum(abs(r[f"selected_{field}_error"]) > abs(r[f"raw_{field}_error"])+1e-12 for r in available)
            metrics[f"{field}_harm_denominator"] = len(available)
        out["subsets"][name] = metrics
    # Passing these observed rates alone does not establish a population safety rate.
    out["observed_numeric_gate"] = bool(replaced and wrong and normal and
        out["false_correction_rate"] <= .01 and out["rescue_rate"] >= .30 and
        out["high_confidence_precision"] is not None and out["high_confidence_precision"] >= .95)
    out["scientific_gate"] = "HOLD_STATISTICAL_SUPPORT" if out["observed_numeric_gate"] else "NOT_SUPPORTED"
    return out


def detection_curve(rows: list[dict], *, split: str) -> list[dict]:
    if split not in {"TRAIN", "CAL", "EXPOSED_DEV", "SYNTHETIC"}:
        raise ContractError("THRESHOLD_CURVE_ON_SEALED_DATA_FORBIDDEN")
    valid = [r for r in rows if r["raw_valid"] and r["reference_valid"] and r.get("wrong_score") is not None]
    scores = sorted({float(r["wrong_score"]) for r in valid})
    if not np.isfinite(scores).all():
        raise ContractError("NONFINITE_DETECTION_SCORE")
    curve = [{"threshold": None, "flag_none": True, "tp": 0, "fp": 0,
              "fn": sum(r["raw_tap"] != r["reference_tap"] for r in valid),
              "tn": sum(r["raw_tap"] == r["reference_tap"] for r in valid)}]
    for threshold in scores:
        items = [dict(r, flag=r["wrong_score"] >= threshold) for r in valid]
        curve.append(dict(threshold=threshold, flag_none=False, **selection_summary(items)["detection"]))
    return curve


def episodes(rows: list[dict], *, gap_s: float = .4) -> list[dict]:
    """Contiguous reference errors, split at route/channel/ID/time gaps."""
    output, current = [], []
    for row in rows:
        large = row["reference_valid"] and row["raw_valid"] and abs(row["raw_tap"]-row["reference_tap"]) >= 2
        contiguous = (current and row["case_id"] == current[-1]["case_id"] and
                      row["pose_id"] == current[-1]["pose_id"]+1 and 0 < row["t"]-current[-1]["t"] <= gap_s)
        if current and (not large or not contiguous):
            output.append(current)
            current = []
        if large:
            current.append(row)
    if current:
        output.append(current)
    return [dict(case_id=g[0]["case_id"], first_pose=g[0]["pose_id"], last_pose=g[-1]["pose_id"],
                 n=len(g), usable_reference_count=sum(r.get("reference_in_usable_pool", False) for r in g),
                 rescue_count=sum(r["selected_tap"] == r["reference_tap"] for r in g)) for g in output]


def confidence_report(rows: list[dict], edges=(0., .25, .5, 1.)) -> list[dict]:
    e = np.asarray(edges, float)
    if len(e) < 2 or not np.isfinite(e).all() or np.any(np.diff(e) <= 0):
        raise ContractError("INVALID_CONFIDENCE_BINS")
    output = []
    for i in range(len(e)-1):
        selected = [r for r in rows if r.get("confidence_score") is not None and
                    e[i] <= r["confidence_score"] and (r["confidence_score"] < e[i+1] or
                    i == len(e)-2 and r["confidence_score"] == e[i+1])]
        output.append(dict(low=float(e[i]), high=float(e[i+1]), summary=selection_summary(selected),
                           confidence_is_probability=False))
    return output


def paired_seed_bootstrap(baseline: dict[str, float], candidate: dict[str, float],
                          *, seed: int = 0, replicates: int = 2000) -> dict:
    if set(baseline) != set(candidate) or not baseline or replicates < 100:
        raise ContractError("PAIRED_SEED_KEYS_OR_BOOTSTRAP_BUDGET_INVALID")
    keys = sorted(baseline)
    a = finite([baseline[k] for k in keys], (len(keys),), "BASELINE_METRICS")
    b = finite([candidate[k] for k in keys], (len(keys),), "CANDIDATE_METRICS")
    if len(keys) < 2:
        return {"status": "INCONCLUSIVE_SUPPORT", "seed_count": len(keys), "CI": None}
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(a), (replicates, len(a)))
    means = (b-a)[indices].mean(axis=1)
    return dict(status="CONDITIONAL_ON_SAME_RF", seed_count=len(a),
                mean_delta=float((b-a).mean()), CI=np.quantile(means, [.025, .975]).tolist(),
                method="PAIRED_SEED_BOOTSTRAP", replicates=replicates)


def moving_block_bootstrap(deltas, *, block_length: int, seed: int = 0, replicates: int = 2000) -> dict:
    a = np.asarray(deltas, float)
    if a.ndim != 1 or not np.isfinite(a).all() or block_length < 1 or replicates < 100:
        raise ContractError("INVALID_BLOCK_BOOTSTRAP")
    if len(a) < 2*block_length:
        return {"status": "INCONCLUSIVE_SUPPORT", "CI": None}
    rng = np.random.default_rng(seed)
    stats = []
    for _ in range(replicates):
        starts = rng.integers(0, len(a)-block_length+1, math.ceil(len(a)/block_length))
        sample = np.concatenate([a[i:i+block_length] for i in starts])[:len(a)]
        stats.append(float(sample.mean()))
    return dict(status="SAME_ROUTE_CONTIGUOUS_BLOCK_CONDITIONAL", block_length=block_length,
                mean_delta=float(a.mean()), CI=np.quantile(stats, [.025, .975]).tolist())


def chi2_threshold(probability: float, dof: int) -> float:
    if not 0 < probability < 1 or dof not in (1, 2, 4):
        raise ContractError("UNSUPPORTED_CHI2_REQUEST")
    def cdf(x):
        if dof == 1:
            return math.erf(math.sqrt(x/2))
        return 1-math.exp(-x/2)*(1+x/2 if dof == 4 else 1)
    low, high = 0., 256.
    for _ in range(80):
        mid = (low+high)/2
        if cdf(mid) < probability:
            low = mid
        else:
            high = mid
    return (low+high)/2


def trajectory_metrics(x, P, truth, times, *, anchor=(10., 0.), near_radius_m=None, late_start_s=None) -> dict:
    x, P, truth, t = np.asarray(x), np.asarray(P), np.asarray(truth), np.asarray(times)
    n = len(t)
    finite(x, (n, 4), "TRAJECTORY")
    truth_dim = truth.shape[1] if truth.ndim == 2 and len(truth) == n else None
    if truth_dim not in (3, 4):
        raise ContractError("TRUTH_NEEDS_THREE_OR_FOUR_STATE_COLUMNS")
    finite(truth, (n, truth_dim), "TRUTH")
    finite(P, (n, 4, 4), "COVARIANCE_TRAJECTORY")
    finite(t, (n,), "TIMES")
    if n == 0 or np.any(np.diff(t) <= 0):
        raise ContractError("EMPTY_OR_NONMONOTONE_TRAJECTORY")
    err = x[:, :truth_dim]-truth
    err[:, 2] = (err[:, 2]+np.pi) % (2*np.pi)-np.pi
    d = truth[:, :2]-np.asarray(anchor)
    radius = np.linalg.norm(d, axis=1)
    radial = np.divide(np.sum(err[:, :2]*d, axis=1), radius, out=np.zeros(n), where=radius > 0)
    tangential = np.divide(-err[:, 0]*d[:, 1]+err[:, 1]*d[:, 0], radius, out=np.zeros(n), where=radius > 0)
    nees4 = np.empty(n) if truth_dim == 4 else None
    nees2, nees1 = np.empty(n), np.empty(n)
    for k in range(n):
        p = covariance(P[k], 4, positive=True)
        if truth_dim == 4:
            nees4[k] = err[k]@np.linalg.solve(p, err[k])
        nees2[k] = err[k, :2]@np.linalg.solve(p[:2, :2], err[k, :2])
        nees1[k] = err[k, 2]**2/p[2, 2]
    windows = {"primary_t_ge_30": t >= 30., "initial": t < 30., "all": np.ones(n, bool)}
    if near_radius_m is not None:
        windows["near"] = radius <= near_radius_m
    if late_start_s is not None:
        windows["late"] = t >= late_start_s
    output = {}
    for name, mask in windows.items():
        if not mask.any():
            output[name] = {"n": 0, "status": "NOT_TESTED"}
            continue
        radial_mask = mask & (radius > 0)
        item = dict(n=int(mask.sum()), heading_deg=error_stats(np.degrees(err[mask, 2])),
                    xy_m=error_stats(np.linalg.norm(err[mask, :2], axis=1)),
                    radial_m=error_stats(radial[radial_mask]), tangential_m=error_stats(tangential[radial_mask]),
                    radial_undefined=int(np.sum(mask & (radius == 0))),
                    nees4_mean=None if nees4 is None else float(nees4[mask].mean()),
                    nees_xy_mean=float(nees2[mask].mean()),
                    covariance_xy_trace_mean=float(np.trace(P[mask, :2, :2], axis1=1, axis2=2).mean()),
                    heading_std_deg_mean=float(np.degrees(np.sqrt(P[mask, 2, 2])).mean()))
        item["coverage"] = {str(p): {"state4": None if nees4 is None else
                                      float(np.mean(nees4[mask] <= chi2_threshold(p, 4))),
                                      "xy": float(np.mean(nees2[mask] <= chi2_threshold(p, 2))),
                                      "heading": float(np.mean(nees1[mask] <= chi2_threshold(p, 1)))} for p in (.68, .95, .99)}
        item["bias_truth_status"] = "NOT_TESTED_NO_TRUE_GYRO_BIAS" if truth_dim == 3 else "EVALUATED"
        output[name] = item
    return output
