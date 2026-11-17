"""Immutable paired M7 condition/gate diagnostics; no new acceptance criteria.

Within each seed, every condition/mode/arm shares the original moving-block
bootstrap indices. Deltas and intervals are target minus baseline. A seed is
one stochastic wheel/gyro realization of the same frozen RF, not an RF repeat.
Importing this module performs no data access, scoring or replay.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

import numpy as np

from m7_inputs import arrays, checked, resolve_input
from m7_report import METRICS
from m7_score_run import _cell_receipt, _contract, _csv_text, _load_scorers, _verify_records
from m7_score_run import independent_point, independent_rows, read, record, sha, write_new
from m7_spec import ARMS, CONDITIONS, FIXED_SEEDS, ROUTES, SEEDS, STRESS

BOOTSTRAP_REPS = 1500
BOOTSTRAP_SEED = 20261115
BLOCKS = (5, 10, 20)


def contexts(seed):
    if type(seed) is not int or seed not in SEEDS:
        raise ValueError("Require integer seed10–29")
    result = [("B0", "own"), ("L2_GYRO_ARW", "own"), (STRESS, "own")]
    if seed in FIXED_SEEDS:
        result += [("B0", "fixed"), ("L2_GYRO_ARW", "fixed")]
    return result


def pair_definitions(seed):
    contexts(seed)
    result = [dict(id="B0_to_L2", baseline=["B0", "own"], target=["L2_GYRO_ARW", "own"]),
              dict(id="L2_to_Q_mismatch_stress", baseline=["L2_GYRO_ARW", "own"], target=[STRESS, "own"])]
    if seed in FIXED_SEEDS:
        result += [dict(id=f"{condition}_own_to_fixed", baseline=[condition, "own"], target=[condition, "fixed"])
                   for condition in ("B0", "L2_GYRO_ARW")]
    return result


def composite(condition, mode, arm):
    return f"{condition}|{mode}|{arm}"


def _trace_identity(trace, condition, mode, arm, t):
    for field, value in (("metadata_condition", condition), ("metadata_arm", arm), ("metadata_rref_policy", "own")):
        if str(np.asarray(trace[field]).item()) != value:
            raise ValueError(f"Composite trace identity differs: {field}")
    gate_mode = str(np.asarray(trace["metadata_gate_mode"]).item())
    if gate_mode != mode and not (arm == "H0" and mode == "fixed" and gate_mode == "own"):
        raise ValueError("Composite gate mode differs")
    for field, value in (("injected_gyro_N_deg_sqrt_s", CONDITIONS[condition]["injected_N_deg_sqrt_s"]),
                         ("filter_gyro_N_deg_sqrt_s", CONDITIONS[condition]["filter_N_deg_sqrt_s"])):
        if np.asarray(trace[field]).shape != t.shape or not np.all(np.asarray(trace[field]) == value):
            raise ValueError("Composite gyro Q policy differs")
    np.testing.assert_array_equal(trace["t"], t)
    for name in ("mask", "q_supported"):
        array = np.asarray(trace[name])
        if array.shape != t.shape or array.dtype.kind != "b":
            raise ValueError(f"Invalid Boolean diagnostic series: {name}")
    bins, nis = np.asarray(trace["q_bin"]), np.asarray(trace["nis"])
    if bins.shape != t.shape or bins.dtype.kind not in "iu" or nis.shape != t.shape or not np.isfinite(nis).all():
        raise ValueError("Invalid support bin or NIS diagnostic series")


def exposure_summary(trace):
    mask, supported, bins = (np.asarray(trace[name]) for name in ("mask", "q_supported", "q_bin"))
    n, accepted = len(mask), int(mask.sum())
    bg = np.degrees(np.asarray(trace["x"])[:, 3])
    if n == 0 or not np.isfinite(bg).all():
        raise ValueError("Empty/nonfinite bias diagnostic")
    counts = lambda use: {str(int(value)): int(np.sum(bins[use] == value)) for value in np.unique(bins[use])}
    return dict(packets=n, accepted=accepted, accepted_rate=accepted/n,
                q_supported_all_count=int(supported.sum()), q_supported_all_rate=float(supported.mean()),
                q_supported_accepted_count=int(np.sum(supported & mask)),
                q_supported_accepted_rate=float(supported[mask].mean()) if accepted else None,
                q_bin_all_counts=counts(np.ones(n, bool)), q_bin_accepted_counts=counts(mask),
                b_g_true_deg_s=0., b_g_error_signed_mean_deg_s=float(bg.mean()),
                b_g_error_rmse_deg_s=float(np.sqrt(np.mean(bg**2))))


def _gate_summary(baseline, target, truth):
    t, before, after = baseline["t"], baseline["mask"], target["mask"]
    xor, common = before ^ after, before & after
    result = dict(packets=len(t), baseline_accepted=int(before.sum()), target_accepted=int(after.sum()),
                  accepted_delta=int(after.sum()) - int(before.sum()), xor_count=int(xor.sum()),
                  common_accepted=int(common.sum()), common_rejected=int((~before & ~after).sum()),
                  baseline_only=int((before & ~after).sum()), target_only=int((~before & after).sum()),
                  xor_time_s=t[xor].tolist(), baseline_only_time_s=t[before & ~after].tolist(),
                  target_only_time_s=t[~before & after].tolist(),
                  baseline_nis_at_xor=np.asarray(baseline["nis"])[xor].tolist(),
                  target_nis_at_xor=np.asarray(target["nis"])[xor].tolist())
    result["common_accepted_point"] = {
        label: independent_point(independent_rows(trace, truth)[common]) if common.any()
        else {"n": 0, **dict.fromkeys(METRICS)}
        for label, trace in (("baseline", baseline), ("target", target))}
    return result


def score_paired_traces(seed, traces, truth, times, *, from_trace, scores_with_blocks):
    """Pure complete-grid adapter; one original block scorer call per seed."""
    expected_contexts = contexts(seed)
    if any(set(value) != set(ROUTES) for value in (traces, truth, times)):
        raise ValueError("Require all three paired routes")
    definitions = pair_definitions(seed)
    ordered_keys = [composite(condition, mode, arm) for condition, mode in expected_contexts for arm in ARMS]
    contrasts = [(composite(*pair["target"], arm), composite(*pair["baseline"], arm))
                 for pair in definitions for arm in ARMS]
    rows, exposure, gates, errors = {}, {}, {}, []
    for route in ROUTES:
        t = np.asarray(times[route])
        if (t.ndim != 1 or len(t) < 2 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0)
                or np.asarray(truth[route]).shape != (len(t), 3)
                or set(traces[route]) != set(ordered_keys)):
            raise ValueError("Incomplete/misaligned composite grid")
        rows[route], exposure[route], gates[route] = {}, {}, {}
        for condition, mode in expected_contexts:
            for arm in ARMS:
                key = composite(condition, mode, arm)
                trace = traces[route][key]
                _trace_identity(trace, condition, mode, arm, t)
                original, independent = np.asarray(from_trace(trace, truth[route])), independent_rows(trace, truth[route])
                np.testing.assert_allclose(original, independent, atol=1e-10, rtol=1e-12)
                rows[route][key] = original
                errors.append(float(np.max(np.abs(original-independent))))
                exposure[route][key] = exposure_summary(trace)
        for pair in definitions:
            gates[route][pair["id"]] = {
                arm: _gate_summary(traces[route][composite(*pair["baseline"], arm)],
                                   traces[route][composite(*pair["target"], arm)], truth[route])
                for arm in ARMS}
    scores = scores_with_blocks(rows, times, contrasts, blocks=BLOCKS)
    if set(scores["point"]) != {*ROUTES, "pooled"}:
        raise ValueError("Paired scorer dropped route/pooled group")
    point_error = []
    for group in (*ROUTES, "pooled"):
        if set(scores["point"][group]) != set(ordered_keys):
            raise ValueError("Paired scorer dropped a composite arm")
        for key in ordered_keys:
            independent = independent_point(rows[group][key] if group in ROUTES else
                                             np.concatenate([rows[route][key] for route in ROUTES]))
            for metric, value in independent.items():
                archived = scores["point"][group][key][metric]
                np.testing.assert_allclose(value, archived, atol=1e-10, rtol=1e-12)
                point_error.append(abs(value-archived))
        for seconds in BLOCKS:
            current = scores["blocks"][str(seconds)]["by_group"][group]
            if set(current["paired_ci95"]) != {f"{target}-{base}" for target, base in contrasts}:
                raise ValueError("Missing/extra paired contrast CI")
    return dict(seed=seed, contexts=[dict(condition=c, mode=m) for c, m in expected_contexts],
                comparisons=definitions, scores=scores, gates=gates, exposure=exposure,
                bootstrap_policy=dict(block_seconds=list(BLOCKS), repetitions=BOOTSTRAP_REPS, seed=BOOTSTRAP_SEED,
                                      scope="same indices across all condition/mode/arm composites within each route/seed",
                                      direction="target minus baseline"),
                implementation_checks=dict(independent_cholesky_row_max_abs=max(errors),
                                           independent_point_max_abs=max(point_error),
                                           independent_audit=False),
                classification="DIAGNOSTIC_ONLY_NO_NEW_THRESHOLDS")


def _pair_contract(path):
    data, identity, replay_contract, generation = _contract(path)
    source = Path(__file__).resolve()
    if sum(Path(item["path"]).resolve() == source for item in data["sources"]) != 1:
        raise ValueError("Scoring contract must pin this exact m7_pairs.py once")
    return data, identity, replay_contract, generation


def _pair_directory(root, seed):
    contexts(seed)
    return Path(root).resolve() / "pairs" / f"seed{seed}"


def pair_seed(contract_path, seed, output_root):
    """One immutable seed result, safe for independent process-pool workers."""
    contexts(seed)
    data, identity, replay_contract, _ = _pair_contract(contract_path)
    directory = _pair_directory(output_root, seed)
    if directory.exists():
        receipt = read(directory / "EXECUTION.json")
        if receipt.get("status") != "PASS_PAIRED_SCORING" or receipt.get("contract") != identity or receipt.get("seed") != seed:
            raise FileExistsError("Preserve old/incomplete paired result; use a new attempt")
        _verify_records(receipt["dependencies"])
        checked(receipt["pair_output"])
        return receipt
    stop = os.environ.get("MANAGED_PROCESS_STOP_FILE")
    if stop and Path(stop).exists():
        raise InterruptedError("Managed stop requested before paired seed")
    original, block_scorer, _ = _load_scorers(data["scorer_assets"])
    if (block_scorer.__globals__.get("BOOTSTRAP_REPS") != BOOTSTRAP_REPS
            or block_scorer.__globals__.get("BOOTSTRAP_SEED") != BOOTSTRAP_SEED):
        raise ValueError("Original bootstrap repetition/seed policy differs")
    index = read(checked(data["input_index"]))
    cells = {cell["id"]: cell for cell in replay_contract["expected_cells"]}
    traces, truth, times, dependencies = {}, {}, {}, []
    for route in ROUTES:
        evaluator_record = data["evaluator_inputs"][route]
        evaluator = arrays(checked(evaluator_record))
        truth[route], times[route], traces[route] = evaluator["truth"], evaluator["t"], {}
        dependencies.append(evaluator_record)
        for condition, mode in contexts(seed):
            inp = resolve_input(index, condition, seed, route)
            packet = arrays(checked(inp))
            for field in ("t", "pose_id"):
                np.testing.assert_array_equal(packet[field], evaluator[field])
            dependencies.append(inp)
            for arm in ARMS:
                cell = cells[f"{condition}/{mode}/seed{seed}/{route}/{arm}"]
                execution, pin = _cell_receipt(data["replay_root"], cell, data["replay_contract"], inp)
                trace = arrays(checked(execution["trace"]))
                for field in ("t", "pose_id"):
                    np.testing.assert_array_equal(trace[field], evaluator[field])
                traces[route][composite(condition, mode, arm)] = trace
                dependencies.extend((pin, execution["trace"]))
                if cell["trace_alias_of"]:
                    dependencies.append(execution["alias_receipt"])
    directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="FAIL_PAIRED_SCORING", exit_code=1, contract=identity, seed=seed,
                   started_utc=datetime.now(timezone.utc).isoformat(), dependencies=dependencies,
                   command=[sys.executable, *sys.argv], role="IMPLEMENTER", independent_audit=False)
    try:
        result = score_paired_traces(seed, traces, truth, times, from_trace=original, scores_with_blocks=block_scorer)
        result["provenance"] = dict(contract=identity, replay_contract=data["replay_contract"],
                                    checked_logical_replay_cells=len(ROUTES) * len(contexts(seed)) * len(ARMS),
                                    replay_receipts=[r for r in dependencies if Path(r["path"]).name == "EXECUTION.json"])
        _verify_records(dependencies)
        if _pair_contract(contract_path)[1] != identity:
            raise ValueError("Scoring contract changed during paired scoring")
        path = directory / "PAIR.json"
        write_new(path, result)
        receipt.update(status="PASS_PAIRED_SCORING", exit_code=0, pair_output=record(path))
    except BaseException as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_new(directory / "EXECUTION.json", receipt)
    return receipt


def paired_table(results):
    rows = []
    for result in results:
        for pair in result["comparisons"]:
            for arm in ARMS:
                before, after = composite(*pair["baseline"], arm), composite(*pair["target"], arm)
                contrast = f"{after}-{before}"
                for group in (*ROUTES, "pooled"):
                    score = result["scores"]
                    row = dict(seed=result["seed"], comparison=pair["id"], arm=arm, group=group,
                               baseline_condition=pair["baseline"][0], baseline_mode=pair["baseline"][1],
                               target_condition=pair["target"][0], target_mode=pair["target"][1],
                               classification="DIAGNOSTIC_ONLY", direction="target minus baseline")
                    for metric in METRICS:
                        row[f"{metric}_baseline"] = score["point"][group][before][metric]
                        row[f"{metric}_target"] = score["point"][group][after][metric]
                        row[f"{metric}_delta"] = row[f"{metric}_target"] - row[f"{metric}_baseline"]
                        for seconds in BLOCKS:
                            ci = score["blocks"][str(seconds)]["by_group"][group]["paired_ci95"][contrast][metric]
                            row[f"{metric}_ci{seconds}_lower"], row[f"{metric}_ci{seconds}_upper"] = ci
                    for seconds in BLOCKS:
                        row[f"block{seconds}_reference_only"] = score["blocks"][str(seconds)]["by_group"][group]["reference_only"]
                    rows.append(row)
    return rows


def gate_table(results):
    rows = []
    for result in results:
        for pair in result["comparisons"]:
            for route in ROUTES:
                for arm in ARMS:
                    gate = result["gates"][route][pair["id"]][arm]
                    row = dict(seed=result["seed"], comparison=pair["id"], route=route, arm=arm,
                               **{key: gate[key] for key in ("packets", "baseline_accepted", "target_accepted", "accepted_delta",
                                  "xor_count", "common_accepted", "common_rejected", "baseline_only", "target_only")})
                    for label in ("xor_time_s", "baseline_only_time_s", "target_only_time_s"):
                        row[label] = json.dumps(gate[label], separators=(",", ":"))
                    for label, context in (("baseline", pair["baseline"]), ("target", pair["target"])):
                        diagnostic = result["exposure"][route][composite(*context, arm)]
                        for key in ("q_supported_all_count", "q_supported_all_rate", "q_supported_accepted_count",
                                    "q_supported_accepted_rate", "b_g_error_signed_mean_deg_s", "b_g_error_rmse_deg_s"):
                            row[f"{label}_{key}"] = diagnostic[key]
                        for key in ("q_bin_all_counts", "q_bin_accepted_counts"):
                            row[f"{label}_{key}"] = json.dumps(diagnostic[key], sort_keys=True)
                    rows.append(row)
    return rows


def delta_distributions(rows):
    result = []
    for pair_id in dict.fromkeys(row["comparison"] for row in rows):
        available = [row for row in rows if row["comparison"] == pair_id]
        subsets = (("all_seeds", available), ("seed10_14", [r for r in available if r["seed"] < 15]),
                   ("seed15_29", [r for r in available if r["seed"] >= 15]))
        for subset, selected in subsets:
            if not selected:
                continue
            for arm in ARMS:
                for group in (*ROUTES, "pooled"):
                    data = [r for r in selected if r["arm"] == arm and r["group"] == group]
                    for metric in METRICS:
                        values = np.array([r[f"{metric}_delta"] for r in data])
                        result.append(dict(comparison=pair_id, subset=subset, arm=arm, group=group, metric=metric,
                            seed_denominator=len(data), summary_unit="per_seed", mean=float(np.mean(values)),
                            median=float(np.median(values)), min=float(np.min(values)), max=float(np.max(values)),
                            p05=float(np.percentile(values, 5)), p95=float(np.percentile(values, 95)),
                            interval_interpretation="descriptive seed variation, not confidence limits"))
    return result


def aggregate_pairs(contract_path, pair_root, output_dir):
    """Validate exactly20 seed receipts, then write immutable diagnostic tables."""
    data, identity, _, _ = _pair_contract(contract_path)
    pair_root, output = Path(pair_root).resolve(), Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError("Preserve old paired aggregate; use new output directory")
    expected = {_pair_directory(pair_root, seed) / "EXECUTION.json" for seed in SEEDS}
    if set((pair_root / "pairs").rglob("EXECUTION.json")) != expected:
        raise ValueError("Missing/extra paired seed receipt")
    results, dependencies = [], []
    for seed in SEEDS:
        path = _pair_directory(pair_root, seed) / "EXECUTION.json"
        receipt = read(path)
        if receipt.get("status") != "PASS_PAIRED_SCORING" or receipt.get("contract") != identity or receipt.get("seed") != seed:
            raise ValueError("Paired receipt identity/status differs")
        _verify_records(receipt["dependencies"])
        result = read(checked(receipt["pair_output"]))
        if result["seed"] != seed or result["comparisons"] != pair_definitions(seed):
            raise ValueError("Paired output identity/grid differs")
        results.append(result)
        dependencies.extend((record(path), receipt["pair_output"]))
    rows, gates = paired_table(results), gate_table(results)
    distributions = delta_distributions(rows)
    summary = dict(status="COMPLETE_PAIRED_DIAGNOSTICS", seeds=list(SEEDS), seed_count=20,
                   seed_comparisons=sum(len(pair_definitions(seed)) for seed in SEEDS),
                   arm_group_comparisons=len(rows), arm_route_gate_comparisons=len(gates),
                   bootstrap_policy=results[0]["bootstrap_policy"], new_acceptance_thresholds=False,
                   limitation="20 wheel/gyro seeds share one frozen RF realization",
                   direction="target minus baseline", report_only="Paired diagnostics do not change M7 acceptance",
                   distributions=distributions)
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="FAIL_PAIRED_AGGREGATION", exit_code=1, contract=identity,
                   started_utc=datetime.now(timezone.utc).isoformat(), dependencies=dependencies,
                   command=[sys.executable, *sys.argv], independent_audit=False)
    try:
        write_new(output / "PAIRED_SUMMARY.json", summary)
        for name, table in (("PAIRED_COMPARISONS.csv", rows), ("PAIRED_GATES_SUPPORT_BG.csv", gates),
                            ("PAIRED_SEED_DISTRIBUTIONS.csv", distributions)):
            with (output / name).open("x", encoding="utf-8-sig", newline="") as stream:
                stream.write(_csv_text(table))
        _verify_records(dependencies)
        if _pair_contract(contract_path)[1] != identity:
            raise ValueError("Frozen scoring contract changed during paired aggregation")
        receipt.update(status="PASS_PAIRED_AGGREGATION", exit_code=0,
                       outputs={p.name: sha(p) for p in output.iterdir() if p.is_file()})
    except BaseException as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_new(output / "EXECUTION.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--pair-root", type=Path)
    args = parser.parse_args()
    if args.aggregate:
        if args.seed is not None or args.pair_root is None:
            parser.error("Aggregation requires --pair-root and no --seed")
        result = aggregate_pairs(args.contract, args.pair_root, args.output_dir)
    else:
        if args.seed is None:
            parser.error("Single paired seed requires --seed")
        result = pair_seed(args.contract, args.seed, args.output_dir)
    print(json.dumps(result, ensure_ascii=False), flush=True)
