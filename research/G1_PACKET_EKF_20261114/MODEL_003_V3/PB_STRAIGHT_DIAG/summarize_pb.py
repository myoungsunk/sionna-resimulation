"""Paired P-B checkpoint and per-packet summaries, in degrees; DIAGNOSTIC_ONLY."""
import csv
import hashlib
from itertools import product
import json
from pathlib import Path
import sys
import tarfile

import numpy as np

ROOT = Path(sys.argv[1]).resolve()
CASES = ("G-T1_A", "G-T1_B", "G-T1_C")
ARMS = ("S-V", "S-C")
LEVELS = ("B0", "B0_ZERO", "L0", "L1", "L2", "TB3_r1.3.1", "TB3_r2.1.0")
TRACED_LEVELS = ("B0", "TB3_r2.1.0")
NEAR_ZERO = 0.01  # s/rad, frozen S2-F floor; diagnostic here only
EPS = 1e-12


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_archive():
    content = {}
    expected = {}
    for line in (ROOT/"ARCHIVED_CHECKPOINT_SHA256SUMS").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        assert path not in expected
        expected[path] = digest
    with tarfile.open(ROOT/"ARCHIVED_PB_CHECKPOINTS.tar.gz") as tar:
        for member in tar.getmembers():
            assert member.isfile() and member.name in expected and member.name not in content
            data = tar.extractfile(member).read()
            assert sha_bytes(data) == expected[member.name]
            content[member.name] = json.loads(data)
    assert set(content) == set(expected) and len(content) == 63
    return content, expected


def stats(estimate, baseline):
    estimate, baseline = np.asarray(estimate), np.asarray(baseline)
    assert estimate.shape == baseline.shape
    if not estimate.size:
        return dict(pairs=0, dr_rmse_deg=None, pol_rmse_deg=None, ratio=None, delta_mse_deg2=None, worse_pct=None)
    a, b = np.degrees(estimate), np.degrees(baseline)
    assert np.isfinite(a).all() and np.isfinite(b).all()
    dr_rmse = float(np.sqrt(np.mean(b*b)))
    pol_rmse = float(np.sqrt(np.mean(a*a)))
    return dict(pairs=a.size, dr_rmse_deg=dr_rmse, pol_rmse_deg=pol_rmse,
                ratio=pol_rmse/dr_rmse if dr_rmse else None,
                delta_mse_deg2=float(np.mean(a*a-b*b)),
                worse_pct=float(100*np.mean(np.abs(a) > np.abs(b)+EPS)))


def unique_checkpoints(receipt, level):
    unique = {}
    for row in receipt["rows"]:
        key = row["checkpoint_order"], row["seed"]
        if level not in ("B0", "B0_ZERO"):
            key += (row["sign"],)
        prior = unique.get(key)
        if prior is not None:
            assert receipt["level"] in ("B0", "B0_ZERO") and prior["sign"] != row["sign"]
            assert {k:v for k,v in prior.items() if k != "sign"} == {k:v for k,v in row.items() if k != "sign"}
        unique[key] = row
    signs = 1 if level in ("B0", "B0_ZERO") else 2
    assert len(unique) == 5*40*signs and len(receipt["rows"]) == 5*40*2
    return unique


def checkpoints(content, hashes):
    values = {}
    records = []
    for case, level, arm in product(CASES, LEVELS, ARMS):
        dr_path = f"OR/30/{case}_P-B_{level}_DR.json"
        s_path = f"joint/OR/30/{case}_P-B_{level}_{arm}.json"
        s, dr = content[s_path], content[dr_path]
        assert s["phase"] == "DIAGNOSTIC_ONLY" and s["status"] == dr["status"] == "PASS"
        assert s["paired_dr_sha256"] == hashes[dr_path] and s["rule"] == "O10"
        dr_rows, sr = unique_checkpoints(dr, level), unique_checkpoints(s, level)
        assert set(dr_rows) == set(sr)
        baseline, estimate = [], []
        for key in sorted(sr):
            a, b = sr[key], dr_rows[key]
            assert a["checkpoint_id"] == b["checkpoint_id"]
            assert a["dr_heading_error_rad"] == b["heading_error_rad"]
            assert a["dr_xy_error_m"] == b["xy_error_m"]
            baseline.append(b["heading_error_rad"])
            estimate.append(a["heading_error_rad"])
        values[(case, level, arm)] = (estimate, baseline)
        records.append(dict(case=case, level=level, arm=arm, **stats(estimate, baseline)))
    for level, arm in product(LEVELS, ARMS):
        subsets = [values[(case, level, arm)] for case in CASES]
        records.append(dict(case="pooled", level=level, arm=arm,
                            **stats(*(np.concatenate(x) for x in zip(*subsets)))))
    return records


def packet_strata(data, idx, case, level, arm):
    est, dr, pri, jac = (data[key][idx] for key in ("post_error_rad", "dr_error_rad", "prior_error_rad", "jac_s_per_rad"))
    accepted = data["accepted"][idx]
    available = data["available"][idx]
    distance = data["distance_m"][idx]
    finite = np.isfinite(jac)
    absj = np.abs(jac)
    finite_by_packet = finite.any(axis=1)
    packet_jac = np.full(len(idx), np.nan)
    packet_jac[finite_by_packet] = np.nanmedian(np.where(finite[finite_by_packet], absj[finite_by_packet], np.nan), axis=1)
    assert finite_by_packet.any()
    relative_cut = float(np.quantile(packet_jac[finite_by_packet], 0.25))
    weakest = finite_by_packet & (packet_jac <= relative_cut)
    near_zero = finite & (absj < NEAR_ZERO)
    delta_heading_deg = np.degrees(np.abs((est-pri+np.pi)%(2*np.pi)-np.pi))
    def subset_stats(take):
        correction = delta_heading_deg[take]
        return stats(est[take], dr[take]) | {
            "p50_abs_heading_update_deg": float(np.median(correction)) if correction.size else None,
            "p95_abs_heading_update_deg": float(np.quantile(correction, 0.95)) if correction.size else None,
        }

    key = dict(case=case, level=level, arm=arm)
    metrics = dict(**key, **stats(est,dr), packets=len(idx), unique_runs=est.shape[1],
                   truth_yaw_span_deg=float(np.degrees(np.ptp(np.unwrap(data["truth_yaw_rad"][idx])))),
                   accept_pct=float(100*np.mean(accepted)), unavailable_pct=float(100*np.mean(~available)),
                   jac_uncomputable_pairs=int(np.sum(~finite)), jac_min_s_per_rad=float(np.min(absj[finite])),
                   jac_p50_s_per_rad=float(np.median(absj[finite])),
                   p50_abs_heading_update_deg=float(np.median(delta_heading_deg)),
                   accepted_worse_from_prior_pct=float(100*np.mean(np.abs(np.degrees(est[accepted])) >
                                                                   np.abs(np.degrees(pri[accepted]))+EPS)),
                   accepted_changed_heading_pct=float(100*np.mean(est[accepted] != pri[accepted])),
                   accepted_packets_with_change=int(np.sum((accepted & (est != pri)).any(axis=1))))
    weak_summary = dict(**key, absolute_near_zero=dict(**subset_stats(near_zero),
                                                       packets=int(near_zero.any(axis=1).sum())),
                        relative_weak=dict(**subset_stats(weakest), cut_s_per_rad=relative_cut,
                                           packets=int(weakest.sum()), min_distance_m=float(distance[weakest].min()),
                                           max_distance_m=float(distance[weakest].max())),
                        remaining=subset_stats(finite_by_packet & ~weakest))
    distance_bin = np.floor(distance).astype(int)
    segments = []
    for k in np.unique(distance_bin):
        take = distance_bin == k
        sect = dict(**key, bin=int(k), packets=int(take.sum()),
                    first_packet=int(data["packet"][idx][take][0]), last_packet=int(data["packet"][idx][take][-1]),
                    from_m=float(distance[take].min()), to_m=float(distance[take].max()),
                    from_s=float(data["elapsed_s"][idx][take].min()), to_s=float(data["elapsed_s"][idx][take].max()),
                    median_s_per_rad=float(np.median(absj[take][finite[take]])),
                    near_zero_pairs=int(near_zero[take].sum()), relative_weak_packets=int(weakest[take].sum()),
                    accepted_pct=float(100*np.mean(accepted[take])), **stats(est[take],dr[take]))
        segments.append(sect | {"worse_than_dr": sect["delta_mse_deg2"] > 0})
    return metrics, weak_summary, segments, est, dr


def packets():
    metrics, weak, segments = [], [], []
    pooled = {}
    verified_baseline = {}
    verified_geometry = {}
    for case, level, arm in product(CASES, TRACED_LEVELS, ARMS):
        stem = ROOT/"capture"/f"{case}_P-B_{level}_{arm}"
        meta = json.loads(stem.with_suffix(stem.suffix+".json").read_text(encoding="utf-8"))
        binary = stem.with_suffix(stem.suffix+".npz")
        assert meta["classification"] == "DIAGNOSTIC_ONLY"
        assert meta["checkpoint_match"] == meta["contributions_match"] == "EXACT"
        assert sha_bytes(binary.read_bytes()) == meta["output_sha256"]
        with np.load(binary, allow_pickle=False) as file:
            data = dict(file)
        assert data["dr_error_rad"].shape == (meta["n_packet"], meta["n_unique_runs"])
        assert np.all(np.diff(data["distance_m"]) >= 0.)
        assert set(data["motion"]) == {"straight", "end"}
        assert np.isfinite(data["truth_yaw_rad"]).all()
        baseline_key = case, level
        if baseline_key in verified_baseline:
            dr_reference, rf_reference = verified_baseline[baseline_key]
            np.testing.assert_array_equal(data["dr_error_rad"], dr_reference)
            assert meta["rf_observations_sha256"] == rf_reference
        else:
            verified_baseline[baseline_key] = data["dr_error_rad"], meta["rf_observations_sha256"]
        # Packet sequence numbers are absolute within each anchor recording.
        relative_packet = data["packet"] - data["packet"][0]
        np.testing.assert_array_equal(relative_packet, verified_geometry.setdefault("relative_packet", relative_packet))
        for key in ("motion", "distance_m", "elapsed_s", "truth_yaw_rad"):
            np.testing.assert_array_equal(data[key], verified_geometry.setdefault(key, data[key]))
        mask = (data["motion"] == "straight") & (np.diff(data["distance_m"],prepend=0.) > 0.)
        result, weakness, distance, est, dr = packet_strata(data, np.flatnonzero(mask), case, level, arm)
        metrics.append(result)
        weak.append(weakness)
        segments.extend(distance)
        pooled.setdefault((level,arm), []).append((est,dr))
    for (level,arm), entries in pooled.items():
        metrics.append(dict(case="pooled", level=level, arm=arm,
                            **stats(*(np.concatenate(x) for x in zip(*entries)))))
    return metrics, weak, segments


def write_csv(name, data):
    with (ROOT/name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(data[0]))
        writer.writeheader()
        writer.writerows(data)


def main():
    archived, hashes = read_archive()
    checkpoint_rows = checkpoints(archived, hashes)
    write_csv("CHECKPOINTS.csv", checkpoint_rows)
    summary = dict(classification="DIAGNOSTIC_ONLY", s2prime="STOP (FULL_6)", step3="HOLD",
                   checkpoint_scenarios=list(LEVELS), checkpoints=checkpoint_rows)
    if (ROOT/"capture").is_dir():
        pkt, weak, segments = packets()
        summary.update(packet_scenarios=list(TRACED_LEVELS), packet_trajectory=pkt, weakness=weak,
                       worse_distance_bins=[r for r in segments if r["worse_than_dr"]])
        write_csv("PACKETS_BY_DISTANCE.csv", segments)
    (ROOT/"SUMMARY.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print("CHECKPOINT (pooled):")
    for row in checkpoint_rows:
        if row["case"] == "pooled":
            print(row["level"], row["arm"], row["dr_rmse_deg"], row["pol_rmse_deg"])
    for row in summary.get("packet_trajectory", []):
        if row["case"] == "pooled":
            print("PACKET", row["level"], row["arm"], row["dr_rmse_deg"], row["pol_rmse_deg"])


if __name__ == "__main__":
    main()

