"""P2 null/P3 covariance validation. Requires separate auditor approval hashes.

Fits receive donor blocks only. Fixed holdout indices/geometry were frozen by P1.
No model selection from holdout scores, no EKF, no sealed data, no new RF.
"""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
import sys
import traceback
import numpy as np
import covariance_core_v2 as C
from p0_inputs_v2 import put, sha, match_signs
from p1_design_v2 import geometry, base_valid, bin_ids, envelope, in_envelope, supported_pairs, components, revisit_groups
from reference_d3 import decompose

BASE = Path(__file__).resolve().parent
DEFINITION = "ORIGINAL_NOISE_FREE_FULL_O30_MINUS_LOS_O30"


def read_raw(path):
    with np.load(path, allow_pickle=False) as z: d = {k: z[k] for k in z.files}
    C.validate_primary(d, DEFINITION)
    return d


def blocks(d, specs, mean, ell=1., yaw_deg=10., raw_e=None):
    values = d["e_rf"] if raw_e is None else raw_e
    result = []
    for spec in specs:
        idx = np.array(spec["indices"], int)
        result.append(dict(K=C.kernel(d["arc_m"][idx], d["yaw_arc_rad"][idx], ell, yaw_deg),
            a=d["a_truth"][idx], e=values[idx]-mean, arc=d["arc_m"][idx], yaw=d["yaw_arc_rad"][idx],
            cluster=int(spec["cluster"]), time=float(d["t"][idx].mean())))
    return result


def prepare_donors(ds, split, holdout):
    donors = split["donor_routes"]
    if holdout in donors: raise ValueError("HOLDOUT_IN_DONORS")
    donor_values = np.concatenate([ds[r]["e_rf"][split["donor_valid_indices"][r]] for r in donors])
    mean, winsor = float(donor_values.mean()), float(np.quantile(abs(donor_values), .99))
    train = [block for r in donors for block in blocks(ds[r], split["components_donor"][r], mean)]
    return mean, winsor, train, len(donor_values)


def paired_report(rows, d, split):
    result = {}
    for seconds in [5, 10, 20]:
        assigned = [dict(r, cluster=int((r["time"]+1e-10)//seconds)) for r in rows]
        # Components never straddle5s boundaries, hence time assignment is exact.
        result[str(seconds)] = C.cluster_ci(assigned, split["bootstrap_revisit_groups"][str(seconds)])
    return result


def contrast(d, rows, donor_mean, winsor, groups, fit):
    i = np.array([int(r["index_i"]) for r in rows]); j = np.array([int(r["index_j"]) for r in rows])
    sign = np.array([int(r["sign"]) for r in rows]); owner = (d["t"][i]//10).astype(int)
    raw = d["e_rf"]-donor_mean
    robust = np.clip(d["e_rf"], -winsor, winsor)-donor_mean
    arc, yaw = d["arc_m"], d["yaw_arc_rad"]
    K = np.exp(-abs(arc[i]-arc[j])-abs(yaw[i]-yaw[j])/np.radians(10))
    q, theta = fit["models"]["S1"]["parameters"]
    predicted = q*K+theta*d["a_truth"][i]*d["a_truth"][j]*K
    def difference(v): return float(v[sign > 0].mean()-v[sign < 0].mean())
    result = dict(pairs=len(i), positive_pairs=int((sign > 0).sum()), negative_pairs=int((sign < 0).sum()),
                  predicted_signed_contrast=difference(predicted))
    for name, values in [("raw", raw), ("winsor_p99", robust)]:
        prod = values[i]*values[j]
        grouped = []
        for group in groups:
            keep = np.isin(owner, group)
            pos, neg = keep & (sign > 0), keep & (sign < 0)
            if keep.any(): grouped.append([pos.sum(), prod[pos].sum(), neg.sum(), prod[neg].sum()])
        arr = np.array(grouped, float)
        rng = np.random.default_rng(20261116)
        draw = rng.integers(0, len(arr), (2000, len(arr)))
        sums = arr[draw].sum(axis=1)
        valid = (sums[:, 0] > 0) & (sums[:, 2] > 0)
        diffs = sums[valid, 1]/sums[valid, 0]-sums[valid, 3]/sums[valid, 2]
        result[name] = dict(difference=difference(prod), ci95=np.quantile(diffs, [.025, .975]).tolist(),
                            valid_bootstrap=int(valid.sum()), active_groups=len(arr))
    return result


def nulls(d, split, fit, mean):
    """Fixed-donor conditional holdout perturbations; no exact permutation p-value."""
    t = d["t"]; cluster = (t//10).astype(int)
    gbin = np.digitize(abs(d["a_truth"]), [.1, .3, .6, 1, 1.5, 2, 3, 4, 6, np.inf])-1
    strata = {}
    for cl in np.unique(cluster):
        idx = np.flatnonzero(cluster == cl)
        if len(idx) != 50: continue
        keys = np.c_[bin_ids(d)[idx], gbin[idx]]
        if np.all(keys == keys[0]) and keys[0, 0] in split["eligible_rho_bins"]:
            strata.setdefault(tuple(map(int, keys[0])), []).append(idx)
    usable = [group for group in strata.values() if len(group) >= 3]
    report = dict(kind="fixed donor predictive conditional diagnostic; not exact randomization inference",
        complete_homogeneous_blocks=sum(len(g) for g in usable), strata=len(usable), repetitions=100,
        eligible_clusters=[[int(cluster[idx[0]]) for idx in group] for group in usable])
    if not usable:
        return dict(report, status="NO_PERMUTABLE_BLOCK_SUPPORT", N2=None, N3=None)
    rng = np.random.default_rng(20261116)
    deltas = {"N2": [], "N3": []}
    for iteration in range(100):
        alternate = dict(d); signs = np.sign(d["a_truth"]).copy(); permuted_e = d["e_rf"].copy()
        changed_signs = 0
        for group in usable:
            order = rng.permutation(len(group))
            for original, donor in zip(group, [group[k] for k in order]):
                new = np.sign(d["a_truth"][donor])
                changed_signs += int(np.count_nonzero(signs[original] != new))
                signs[original] = new; permuted_e[original] = d["e_rf"][donor]
        alternate["a_truth"] = abs(d["a_truth"])*signs
        for name, source, e in [("N2", alternate, None), ("N3", d, permuted_e)]:
            scored, _ = C.score_models(blocks(source, split["components_test"], mean, raw_e=e), fit)
            count = sum(r["n"] for r in scored)
            deltas[name].append(dict(delta10=sum(r["scores"]["S1"]-r["scores"]["S0"] for r in scored)/count,
                                     delta12=sum(r["scores"]["S1"]-r["scores"]["S2"] for r in scored)/count,
                                     changed_signs=changed_signs if name == "N2" else None))
    return dict(report, status="COMPUTED", N2=deltas["N2"], N3=deltas["N3"])


def temporal_design(ds, splits):
    design = {}
    for route, d in ds.items():
        sp = splits[route]
        train = np.zeros(len(d["t"]), bool); val = train.copy()
        train[sp["temporal_train_indices"]] = True; val[sp["temporal_validation_indices"]] = True
        env = envelope([d], [train]); val &= in_envelope(d, env)
        _, _, _, ts = supported_pairs(d, train); _, _, _, vs = supported_pairs(d, val)
        bins = [b for b in range(4) if ts[b]["status"] == "SUPPORT_AVAILABLE" and vs[b]["status"] == "SUPPORT_AVAILABLE"]
        train &= np.isin(bin_ids(d), bins); val &= np.isin(bin_ids(d), bins)
        design[route] = dict(status="ELIGIBLE" if bins else "NO_SUPPORTED_TEMPORAL_FOLD", eligible_bins=bins,
                            train=np.flatnonzero(train).tolist(), validation=np.flatnonzero(val).tolist(),
                            support_train=ts, support_validation=vs)
    return design


def run(attempt, audit_path):
    # Hash-bound approval is checked before any actual residual is loaded or fit.
    audit = json.loads(audit_path.read_bytes())
    assert audit["verdict"] == "ACCEPT_PRE_FIT", "INDEPENDENT_APPROVAL_REQUIRED"
    sources = audit["approved_sources"]
    for filename, expected in sources.items():
        assert sha(BASE/filename) == expected, "AUDITED_SOURCE_CHANGED:"+filename
    assert Path(__file__).name in sources and "covariance_core_v2.py" in sources, "RUNNER_CORE_NOT_APPROVED"
    p1 = attempt/"p1_revision_02"
    for filename, expected in audit["approved_design"].items():
        assert sha(p1/filename) == expected, "AUDITED_DESIGN_CHANGED:"+filename
    for filename, expected in audit["approved_inputs"].items():
        assert sha(attempt/filename) == expected, "AUDITED_INPUT_CHANGED:"+filename
    assert json.loads((attempt/"p2_synthetic_revision_02/TESTS.json").read_bytes())["passed"]
    out = attempt/"p3"
    if out.exists(): raise FileExistsError(out)
    out.mkdir()
    contract = dict(question_id="G1-INT-SIGNED-COV-001", stage="P3", status="FROZEN_BEFORE_FIT",
        parent_design_sha256=sha(p1/"PRE_REGISTERED_CONTRACT.json"), split_sha256=sha(p1/"SPLITS.json"),
        audit_sha256=sha(audit_path), sources=sources, command=sys.argv, residual_definition=DEFINITION,
        source_P0="attempt02", numeric_contract="p2_synthetic_revision02; donor-RMS a normalization; unique-coordinate S0 scale; fixed common epsilon",
        nulls="fixed-donor conditional holdout-only block perturbations, no exact permutation p value",
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat())
    put(out/"RUN_CONTRACT.json", contract)
    splits = json.loads((p1/"SPLITS.json").read_bytes())
    # Freeze temporal support using geometry only, before loading residual values.
    geo = {r: geometry(attempt/f"P0_{r}.npz") for r in splits}
    td = temporal_design(geo, splits); put(out/"TEMPORAL_DESIGN.json", td)
    ds = {r: read_raw(attempt/f"P0_{r}.npz") for r in splits}
    with (p1/"PAIR_INDEX.csv").open(encoding="utf-8", newline="") as f: pair_rows = list(csv.DictReader(f))
    fits, scores, contrasts, controls, sensitivity, temporal = {}, {}, {}, {}, {}, {}
    try:
        for route, split in splits.items():
            if not split["eligible_rho_bins"]:
                fits[route] = dict(status="NO_SUPPORTED_FOLD"); scores[route] = dict(status="NO_SUPPORTED_FOLD")
                print(route, "NO_SUPPORTED_FOLD", flush=True); continue
            donors = split["donor_routes"]
            mean, winsor, train, donor_count = prepare_donors(ds, split, route)
            print(route, "fitting donor only", len(train), "components", flush=True)
            fit = C.fit_models(train)
            fits[route] = dict(status="FITTED_DONORS_ONLY", donor_routes=donors, donor_mean=mean,
                               donor_abs_e_p99=winsor, donor_count=donor_count, **fit)
            test = blocks(ds[route], split["components_test"], mean)
            rows, check = C.score_models(test, fit)
            scores[route] = dict(status="SCORED", primary_and_block_sensitivity=paired_report(rows, ds[route], split),
                                 component_scores=rows, numerics=check)
            selected = [r for r in pair_rows if r["route"] == route and r["matched"] == "True"]
            contrasts[route] = contrast(ds[route], selected, mean, winsor, split["bootstrap_revisit_groups"]["10"], fit)
            controls[route] = nulls(ds[route], split, fit, mean)
            sensitivity[route] = {}
            for ell, yaw_deg in [[.5, 5], [.5, 20], [2, 5], [2, 20]]:
                tr = [b for r in donors for b in blocks(ds[r], split["components_donor"][r], mean, ell, yaw_deg)]
                ff = C.fit_models(tr)
                rr, nn = C.score_models(blocks(ds[route], split["components_test"], mean, ell, yaw_deg), ff)
                sensitivity[route][f"ell{ell}_yaw{yaw_deg}"] = dict(fits=ff,
                    scores=paired_report(rr, ds[route], split), numerics=nn, primary_selection=False)
            # Donor route-centered fit; same holdout centering as primary.
            tr = [b for r in donors for b in blocks(ds[r], split["components_donor"][r],
                    float(ds[r]["e_rf"][split["donor_valid_indices"][r]].mean()))]
            ff = C.fit_models(tr); rr, _ = C.score_models(test, ff)
            sensitivity[route]["donor_route_centered"] = dict(fits=ff, scores=paired_report(rr, ds[route], split), primary_selection=False)
            # Holdout truth mean is oracle sensitivity only, never fed to a fit.
            oracle_mean = float(ds[route]["e_rf"][split["test_valid_indices"]].mean())
            rr, _ = C.score_models(blocks(ds[route], split["components_test"], oracle_mean), fit)
            sensitivity[route]["ORACLE_holdout_centered"] = dict(mean=oracle_mean, scores=paired_report(rr, ds[route], split), primary_selection=False)
            robust = np.clip(ds[route]["e_rf"], -winsor, winsor)
            rr, _ = C.score_models(blocks(ds[route], split["components_test"], mean, raw_e=robust), fit)
            sensitivity[route]["winsorized_p99"] = dict(scores=paired_report(rr, ds[route], split), primary_selection=False)
            put(out/"FITS.json", fits); put(out/"HOLDOUT_SCORES.json", scores)
            put(out/"SIGN_CONTRAST.json", contrasts); put(out/"NULL_CONTROLS.json", controls); put(out/"SENSITIVITY.json", sensitivity)
            print(route, "completed primary and fixed sensitivities", scores[route]["primary_and_block_sensitivity"]["10"], flush=True)
        for route, design in td.items():
            if not design["eligible_bins"]:
                temporal[route] = dict(status=design["status"]); continue
            d = ds[route]; train_idx = design["train"]
            mean = float(d["e_rf"][train_idx].mean())
            train_mask = np.zeros(len(d["t"]), bool); val_mask = train_mask.copy()
            train_mask[train_idx] = True; val_mask[design["validation"]] = True
            fit = C.fit_models(blocks(d, components(d, train_mask), mean))
            rows, numerics = C.score_models(blocks(d, components(d, val_mask), mean), fit)
            temporal[route] = dict(status="SCORED", fit=fit, donor_mean=mean, scores=paired_report(rows, d, splits[route]), numerics=numerics)
        # Original D3 slow is auxiliary definition only, not silently used as raw RF.
        n4, auxiliary = {}, {}
        rng = np.random.default_rng(20261116)
        for route, d in ds.items():
            white = rng.standard_normal((len(d["t"]), 2))
            parts = decompose(white, d["t"], d["arc_m"], d["yaw_arc_rad"],
                              dict(half_seconds=5., half_distance_m=.25, half_yaw_deg=5., min_window_packets=10))
            use = parts["support"]
            neighbor = use[:-1] & use[1:]
            n4[route] = dict(definition="SYNTHETIC_WHITE_THROUGH_ORIGINAL_D3", support=int(use.sum()),
                raw_lag1=float(np.corrcoef(white[:-1, 1], white[1:, 1])[0, 1]),
                smoothed_lag1=float(np.corrcoef(parts["slow"][:-1, 1][neighbor], parts["slow"][1:, 1][neighbor])[0, 1]))
            source = Path("D:/SLAM_bot/artifacts/G1_INT_DIAG_001_20261115/continuation_d2_d3/d3")/f"B_B0_{route}.npz"
            with np.load(source, allow_pickle=False) as a:
                assert np.array_equal(a["t"], d["t"]) and np.array_equal(a["pose_id"], d["pose_id"])
                auxiliary[route] = dict(source=str(source), sha256=sha(source), definition="D3_EKF_TRUTH_RESIDUAL_NOT_PHYSICAL_RF",
                    support=int(a["decomposition_support"].sum()), slow_s_variance=float(a["slow"][a["decomposition_support"], 1].var()),
                    raw_RF_vs_D3_eps_max_difference=float(abs(d["e_rf"]-a["eps"][:, 1]).max()), primary_fit=False)
        put(out/"D3_AUXILIARY.json", auxiliary)
        controls["N4"] = n4; put(out/"NULL_CONTROLS.json", controls); put(out/"TEMPORAL_SCORES.json", temporal)
        put(out/"P3_STATUS.json", dict(status="EXECUTION_COMPLETE", adoption="NOT_ASSESSED", finished_utc=dt.datetime.now(dt.timezone.utc).isoformat()))
    except Exception as exc:
        put(out/"P3_STATUS.json", dict(status="STOP", error=str(exc), traceback=traceback.format_exc(),
                                     finished_utc=dt.datetime.now(dt.timezone.utc).isoformat()))
        raise
    finally:
        (out/"SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(out.iterdir()) if p.is_file() and p.name != "SHA256SUMS"), encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--attempt", type=Path, required=True); ap.add_argument("--audit", type=Path, required=True)
    args = ap.parse_args(); run(args.attempt.resolve(), args.audit.resolve())
