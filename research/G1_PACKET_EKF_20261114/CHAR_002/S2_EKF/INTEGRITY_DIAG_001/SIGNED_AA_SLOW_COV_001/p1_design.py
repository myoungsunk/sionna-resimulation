"""Freeze eligibility/splits without reading residual values. P1 only, no fits."""
from __future__ import annotations
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
import sys
import numpy as np
from scipy.spatial import cKDTree
from p0_inputs_v2 import sha, put, pairs_for, match_signs, support_report

DESIGN = {
    "question_id": "G1-INT-SIGNED-COV-001", "stage": "P1",
    "scope": "R2/R4/R5 B mount0 timed noise-free RF; no new RF or EKF",
    "score": "Gaussian composite block log predictive score, nats/packet",
    "score_components": "each 10s cluster -> two 5s halves x alternating 0.2s-grid index (4 components), then rho-bin; every eligible packet once; off-diagonal lags 0.4..4.8s",
    "models": {"S0": "q*K", "S1": "q*K+theta*diag(a)*K*diag(a)",
               "S2": "q*K+u*diag(abs(a))*K*diag(abs(a))", "S3": "theta*diag(a)*K*diag(a)"},
    "kernel": {"ell_arc_m": 1, "ell_yaw_deg": 10,
               "sensitivity_grid_m_deg": [[.5, 5], [.5, 20], [2, 5], [2, 20]],
               "coordinates": "cumulative original RF pose arc and cumulative absolute wrapped yaw"},
    "pair_lag_s": [.4, 5], "min_abs_a": .1, "rho_bins_m": [0, 1.5, 3, 6, 10],
    "pair_primary": "same 10s cluster; cross-boundary pairs preserved as descriptive only",
    "P0_P1_boundary_change": "P0 inventory retains boundary pairs; P1 primary excludes them before scores to avoid shared-endpoint bootstrap leakage; raw pairs retained",
    "matching": "P0 deterministic equal counts per sign within rho_mean0.5m,log|aiaj|0.5,lag0.4s cells; no residuals",
    "support": {"minimum_pairs_per_sign": 30, "minimum_clusters_per_sign": 3, "max_signed_condition": 30},
    "endpoint_support": "within each rho-bin x sign(a), inclusive min/max donor abs(a); missing cells excluded as EXTRAPOLATION",
    "fold_eligibility": "both holdout matched sign support and pooled donor matched sign support after site purge, boundary exclusion, endpoint envelope",
    "mean": "one scalar mean of eligible donor packets only; same mean all models; no holdout centering",
    "fitting": "nonnegative scalar q/theta/u Gaussian composite ML; analytic scale with fixed mixing-fraction grid+bounded scalar refinement; no heldout objective",
    "epsilon": "fit unregularized donor S0 scale first; epsilon=1e-8*max(q0,1e-6), fixed for all models and test components",
    "numerics": "double, Cholesky; no epsilon increase; report condition and failures",
    "development": {"train_cluster_mod10": [0, 1, 2], "validation_mod10": [5, 6],
                    "guard_mod10": [3, 4, 7, 8, 9], "gap": "at least two unused 10s blocks on both sides",
                    "D3_extra_guard_s": 5},
    "loro": "donor routes only, all eligible donor blocks except shared heldout RF sites; fixed kernel; no model selection on heldout scores",
    "revisit": {"xy_radius_m": .05, "yaw_radius_deg": 10,
                "within_route_min_time_s": 10,
                "purge": "whole donor/train10s block if any site overlaps heldout/validation site",
                "bootstrap": "link holdout10s clusters containing same/revisit site; resample linked cluster groups as units"},
    "bootstrap": {"replicates": 2000, "seed": 20261116, "primary_seconds": 10, "sensitivity_seconds": [5, 20],
                  "paired": True, "pairs_individually_resampled": False},
    "controls": {"N0": "S0 theta0", "N1": "S2 unsigned",
                 "N2_N3": "100 block-stratified conditional permutations; no exact randomization p value",
                 "strata": "rho-bin and fixed abs(a) bins [.1,.3,.6,1,1.5,2,3,4,6,inf]; complete10s block only if homogeneous stratum, otherwise ineligible",
                 "N4": "independent white through original D3 slow decomposition; descriptive synthetic null"},
    "winsor": "donor abs residual p99, fixed before holdout score; auxiliary only",
    "decision": "exact plan section7; no supported route implies no signed claim; same-scene conditional only",
    "fit_execution": "WAIT_INDEPENDENT_SYNTHETIC_AUDIT",
    "preserved": ["attempt01 STOP", "G-T2/G-V SEALED", "S2prime STOP", "Step3 HOLD", "M7 unchanged"],
}


def geometry(path):
    with np.load(path, allow_pickle=False) as a:
        # Deliberately do not load e_rf/s_full/s_los into support/split design.
        return {k: a[k] for k in ["t", "pose_id", "truth", "a_truth", "arc_m", "yaw_arc_rad", "rho_m"]}


def bin_ids(d):
    return np.digitize(d["rho_m"], DESIGN["rho_bins_m"])-1


def base_valid(d):
    b = bin_ids(d)
    return (abs(d["a_truth"]) >= .1) & (b >= 0) & (b < 4)


def overlapping_blocks(train, test):
    """Whole training block purge; geometry only, exact radius and wrapped yaw."""
    tree = cKDTree(test["truth"][:, :2])
    overlaps = []
    for i, candidates in enumerate(tree.query_ball_point(train["truth"][:, :2], .05)):
        if candidates:
            delta = abs((test["truth"][candidates, 2]-train["truth"][i, 2]+np.pi)%(2*np.pi)-np.pi)
            if np.any(delta <= np.radians(10)+1e-12): overlaps.append(i)
    return np.unique((train["t"][overlaps]//10).astype(int)).tolist() if overlaps else []


def revisit_groups(d, seconds=10):
    ids = np.unique((d["t"]//seconds).astype(int))
    parent = {int(i): int(i) for i in ids}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    links = []
    for i, j in sorted(cKDTree(d["truth"][:, :2]).query_pairs(.05)):
        if abs(d["t"][j]-d["t"][i]) < 10: continue
        yaw = abs((d["truth"][j, 2]-d["truth"][i, 2]+np.pi)%(2*np.pi)-np.pi)
        if yaw <= np.radians(10)+1e-12:
            bi, bj = int(d["t"][i]//seconds), int(d["t"][j]//seconds)
            parent[find(bi)] = find(bj); links.append([int(i), int(j), bi, bj])
    groups = {}
    for i in ids: groups.setdefault(find(int(i)), []).append(int(i))
    return list(groups.values()), links


def envelope(donors, masks):
    rows = []
    for b in range(4):
        for sign in [-1, 1]:
            values = np.concatenate([abs(d["a_truth"])[m & (bin_ids(d) == b) & (np.sign(d["a_truth"]) == sign)]
                                     for d, m in zip(donors, masks)])
            rows.append(dict(rho_bin=b, sign=sign, count=len(values),
                             min=float(values.min()) if len(values) else None,
                             max=float(values.max()) if len(values) else None))
    return rows


def in_envelope(d, env):
    valid = np.zeros(len(d["t"]), bool)
    for row in env:
        if row["count"]:
            valid |= ((bin_ids(d) == row["rho_bin"]) & (np.sign(d["a_truth"]) == row["sign"]) &
                      (abs(d["a_truth"]) >= row["min"]-1e-12) & (abs(d["a_truth"]) <= row["max"]+1e-12))
    return valid


def supported_pairs(d, mask):
    p = pairs_for(d["t"], d["a_truth"], d["rho_m"], d["arc_m"], d["yaw_arc_rad"])
    primary = mask[p["i"]] & mask[p["j"]] & (p["cluster"] == p["cluster_j"])
    q = {k: v[primary] for k, v in p.items()}
    return p, primary, q, support_report(q, d["t"])


def pooled_support(ds, masks):
    all_p = []
    for r, (d, mask) in enumerate(zip(ds, masks)):
        _, _, q, _ = supported_pairs(d, mask)
        q = {k: v.copy() for k, v in q.items()}
        q["cluster"] += 1000*r; q["cluster_j"] += 1000*r
        q["i"] += 100000*r; q["j"] += 100000*r
        all_p.append(q)
    pooled = {k: np.concatenate([p[k] for p in all_p]) for k in all_p[0]}
    return support_report(pooled, np.empty(0))


def components(d, mask):
    # Fixed components cover each eligible packet once, with no score-dependent thinning.
    bins = bin_ids(d); time = d["t"]
    cluster = (time//10).astype(int)
    half = ((time-cluster*10)//5).astype(int)
    parity = np.arange(len(time))%2
    rows = []
    for cl in np.unique(cluster):
        for h in [0, 1]:
            for phase in [0, 1]:
                for b in range(4):
                    idx = np.flatnonzero(mask & (cluster == cl) & (half == h) & (parity == phase) & (bins == b))
                    if len(idx):
                        rows.append(dict(cluster=int(cl), half=h, phase=phase, rho_bin=b, indices=idx.tolist()))
    covered = np.array([i for row in rows for i in row["indices"]], int)
    assert np.array_equal(np.sort(covered), np.flatnonzero(mask)), "COMPONENT_PARTITION_NOT_EXACT_ONCE"
    for row in rows:
        tt = time[row["indices"]]
        if len(tt) > 1:
            assert np.diff(tt).min() >= .4-1e-9 and tt.max()-tt.min() <= 5+1e-9, "COMPONENT_LAG_OUTSIDE_CONTRACT"
    return rows


def run(attempt):
    out = attempt/"p1"
    if out.exists(): raise FileExistsError(out)
    out.mkdir()
    assert json.loads((attempt/"P0_STATUS.json").read_bytes())["status"] == "PASS_INPUTS"
    contract = dict(DESIGN, implementation_sha256=sha(__file__), command=sys.argv,
                    frozen_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
                    p0_contract_sha256=sha(attempt/"RUN_CONTRACT.json"), p0_status_sha256=sha(attempt/"P0_STATUS.json"))
    put(out/"PRE_REGISTERED_CONTRACT.json", contract)
    ds = {r: geometry(attempt/f"P0_{r}.npz") for r in ["R2", "R4", "R5"]}
    splits, reports = {}, {}
    pair_rows = []
    for holdout, test in ds.items():
        names = [r for r in ds if r != holdout]
        donors = [ds[r] for r in names]
        purges = {r: overlapping_blocks(ds[r], test) for r in names}
        masks = [base_valid(ds[r]) & ~np.isin((ds[r]["t"]//10).astype(int), purges[r]) for r in names]
        env = envelope(donors, masks)
        bv = base_valid(test); tv = bv & in_envelope(test, env)
        p, primary, q, test_support = supported_pairs(test, tv)
        donor_support = pooled_support(donors, masks)
        eligible_bins = [b for b in range(4) if test_support[b]["status"] == "SUPPORT_AVAILABLE"
                         and donor_support[b]["status"] == "SUPPORT_AVAILABLE"]
        scoring_mask = tv & np.isin(bin_ids(test), eligible_bins)
        # Training uses only bins eligible in this heldout fold; no heldout residuals enter fitting.
        final_donor_masks = [m & np.isin(bin_ids(d), eligible_bins) for d, m in zip(donors, masks)]
        groups, links = revisit_groups(test)
        dtrain = np.isin((test["t"]//10).astype(int)%10, [0, 1, 2]) & bv
        dval = np.isin((test["t"]//10).astype(int)%10, [5, 6]) & bv
        temp_test = {k: v[dval] for k, v in test.items()}
        train_purge = overlapping_blocks(test, temp_test) if dval.any() else []
        dtrain &= ~np.isin((test["t"]//10).astype(int), train_purge)
        splits[holdout] = dict(donor_routes=names, purged_donor_blocks=purges, donor_envelope=env,
            eligible_rho_bins=eligible_bins, test_valid_indices=np.flatnonzero(scoring_mask).tolist(),
            donor_valid_indices={r: np.flatnonzero(m).tolist() for r, m in zip(names, final_donor_masks)},
            components_test=components(test, scoring_mask),
            components_donor={r: components(ds[r], m) for r, m in zip(names, final_donor_masks)},
            bootstrap_revisit_groups={str(sec): revisit_groups(test, sec)[0] for sec in [5, 10, 20]},
            revisit_pairs=links,
            temporal_train_indices=np.flatnonzero(dtrain).tolist(), temporal_validation_indices=np.flatnonzero(dval).tolist(),
            temporal_purged_train_blocks=train_purge)
        matched = set()
        for b in eligible_bins:
            selected = match_signs(p, primary & (p["rho_bin"] == b))
            matched.update(selected.tolist())
        for z in range(len(p["i"])):
            pair_rows.append(dict(route=holdout, pose_i=int(test["pose_id"][p["i"][z]]),
                pose_j=int(test["pose_id"][p["j"][z]]), index_i=int(p["i"][z]), index_j=int(p["j"][z]),
                rho_bin=int(p["rho_bin"][z]), sign=int(p["sign"][z]), aiaj=float(p["prod"][z]),
                lag=float(p["lag"][z]), cluster_i=int(p["cluster"][z]), cluster_j=int(p["cluster_j"][z]),
                primary_eligible=bool(primary[z] and int(p["rho_bin"][z]) in eligible_bins), matched=z in matched))
        reports[holdout] = dict(eligible_rho_bins=eligible_bins, donor_support=donor_support, holdout_support=test_support,
            base_eligible_packets=int(bv.sum()), extrapolated_packets=int((bv & ~tv).sum()),
            extrapolated_pose_ids=test["pose_id"][bv & ~tv].tolist(), primary_score_packets=int(scoring_mask.sum()),
            raw_pair_count=len(p["i"]), boundary_pairs=int((p["cluster"] != p["cluster_j"]).sum()),
            effective_revisit_cluster_groups=len(groups), status="ELIGIBLE" if eligible_bins else "NO_SUPPORTED_FOLD")
    with (out/"PAIR_INDEX.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(pair_rows[0])); writer.writeheader(); writer.writerows(pair_rows)
    put(out/"SPLITS.json", splits); put(out/"SUPPORT_FINAL.json", reports)
    put(out/"CHECKS_P1.json", dict(residuals_read=False, eligibility_fixed_before_scores=True,
        raw_primary_pose_used=True, unsupported_fold_action="NO_SUPPORTED_FOLD; no fit", timestamp=dt.datetime.now(dt.timezone.utc).isoformat()))
    put(out/"P1_STATUS.json", dict(status="DESIGN_FROZEN", eligible_routes=[r for r in reports if reports[r]["eligible_rho_bins"]],
                                  fitting_status="WAIT_INDEPENDENT_SYNTHETIC_AUDIT"))
    (out/"SHA256SUMS").write_text("".join(f"{sha(p)}  {p.name}\n" for p in sorted(out.iterdir()) if p.is_file() and p.name != "SHA256SUMS"), encoding="utf-8")
    print({r: {k: reports[r][k] for k in ["eligible_rho_bins", "extrapolated_packets", "primary_score_packets", "status"]} for r in reports}, flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--attempt", type=Path, required=True)
    run(ap.parse_args().attempt.resolve())
