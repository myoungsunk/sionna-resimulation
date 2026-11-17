"""Additive R5 passage diagnostics for M7 plan §6, never a replay.

The accepted sum H_nav.T R_eff^-1 H_nav is a nominal local measurement term.
For GM arms it conditions on the added bias state; it is not the marginalized
navigation information, independent packet information, or a causal attribution.
Importing this module performs no data access or execution.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import numpy as np

from m7_inputs import arrays, checked, resolve_input
from m7_score_run import _cell_receipt, _contract, _csv_text, _group_directory, _verify_records
from m7_score_run import expected_groups, group_key, read, record, sha, write_new
from m7_spec import ARMS, ROUTES, STRESS

INFORMATION_LIMIT = ("Nominal accepted local H_nav^T Reff^-1 H_nav only; conditional on GM bias state, "
                     "not marginalized navigation or independent-packet information")


def _information_summary(matrix):
    if matrix is None:
        return dict(J_yy=None, J_psipsi=None, J_ypsi=None, matrix=None)
    return dict(J_yy=float(matrix[1, 1]), J_psipsi=float(matrix[2, 2]),
                J_ypsi=float(matrix[1, 2]), matrix=matrix.tolist())


def local_information(trace, selection):
    """Actual accepted observation shape, with range-first conditional split."""
    t, mask = np.asarray(trace["t"]), np.asarray(trace["mask"])
    selection = np.asarray(selection)
    if mask.shape != t.shape or mask.dtype.kind != "b" or selection.shape != t.shape or selection.dtype.kind != "b":
        raise ValueError("Window and accepted masks must match the trace grid")
    arm = str(np.asarray(trace["metadata_arm"]).item())
    if arm not in ARMS:
        raise ValueError("Unknown M7 arm")
    if arm == "H0":
        if mask.any():
            raise ValueError("DR cannot contain accepted measurement packets")
        return dict(status="NOT_APPLICABLE_DR", accepted=0, channel_count=0,
                    total=_information_summary(None), range_first=_information_summary(None),
                    conditional_polarization=_information_summary(None), claim_limit=INFORMATION_LIMIT)
    h, r = np.asarray(trace["H"]), np.asarray(trace["Reff"])
    channels = 1 if arm == "H1" else 2
    if (h.shape != (len(t), channels, 4) or r.shape != (len(t), channels, channels)
            or not np.isfinite(h).all() or not np.isfinite(r).all()):
        raise ValueError("Actual observation/Jacobian shape differs from arm")
    np.testing.assert_allclose(r, r.swapaxes(-1, -2), atol=1e-12, rtol=0.)
    np.linalg.cholesky(r)
    use = np.flatnonzero(mask & selection)
    total, range_first, conditional_s = (np.zeros((4, 4)) for _ in range(3))
    maximum_error = 0.
    for i in use:
        observed = h[i].T @ np.linalg.solve(r[i], h[i])
        range_term = np.outer(h[i, 0], h[i, 0]) / r[i, 0, 0]
        pol_term = np.zeros((4, 4))
        if channels == 2:
            # Valid with correlated R: first range, then s conditional on range.
            conditional_h = h[i, 1] - (r[i, 1, 0] / r[i, 0, 0]) * h[i, 0]
            conditional_variance = r[i, 1, 1] - r[i, 1, 0]**2 / r[i, 0, 0]
            pol_term = np.outer(conditional_h, conditional_h) / conditional_variance
        np.testing.assert_allclose(observed, range_term + pol_term, atol=1e-10, rtol=1e-10)
        maximum_error = max(maximum_error, float(np.max(np.abs(observed - range_term - pol_term))))
        total += observed
        range_first += range_term
        conditional_s += pol_term
    return dict(status="NOMINAL_LOCAL_MEASUREMENT_TERM", accepted=len(use), channel_count=channels,
                total=_information_summary(total), range_first=_information_summary(range_first),
                conditional_polarization=_information_summary(conditional_s if channels == 2 else None),
                decomposition="range-first conditional polarization; diagonal R reduces to channel split",
                max_channel_sum_abs_error=maximum_error,
                units="Jyy m^-2; Jpsipsi rad^-2; Jypsi (m rad)^-1", claim_limit=INFORMATION_LIMIT)


def _snapshot(trace, index, requested_time):
    t = np.asarray(trace["t"])
    fields = ("x", "P", "prior", "Pprior", "b_g", "b_g_prior", "b_theta", "b_theta_prior", "q_s", "distance", "s_infl")
    if any(not np.isfinite(np.asarray(trace[field])[index]).all() for field in fields):
        raise ValueError("Nonfinite passage entry state")
    return dict(packet_index=int(index), time_s=float(t[index]), requested_time_s=float(requested_time),
                time_offset_s=float(t[index] - requested_time), pose_id=np.asarray(trace["pose_id"])[index].item(),
                posterior_nav_xypsi=trace["x"][index, :3].tolist(),
                posterior_nav_P_diagonal=np.diag(trace["P"][index]).tolist(),
                prior_nav_xypsi=trace["prior"][index, :3].tolist(),
                prior_nav_P_diagonal=np.diag(trace["Pprior"][index]).tolist(),
                b_g_deg_s=float(np.degrees(trace["b_g"][index])),
                b_g_prior_deg_s=float(np.degrees(trace["b_g_prior"][index])),
                b_theta_deg=float(np.degrees(trace["b_theta"][index])),
                b_theta_prior_deg=float(np.degrees(trace["b_theta_prior"][index])),
                q_s=float(trace["q_s"][index]), distance_m=float(trace["distance"][index]),
                s_infl=float(trace["s_infl"][index]), accepted=bool(trace["mask"][index]),
                units="pose [m,m,rad]; P diagonal [m^2,m^2,rad^2,(rad/s)^2]; biases deg/s,deg; q_s s^2")


def passage_diagnostics(trace, passages):
    """Pure helper; passage times and branch flags are inherited, not refitted."""
    t = np.asarray(trace["t"])
    if (t.ndim != 1 or len(t) == 0 or not np.isfinite(t).all() or np.any(np.diff(t) <= 0)
            or len(passages) != 3):
        raise ValueError("R5 requires a finite ordered trace and exactly three passages")
    values = [float(passage["time_s"]) for passage in passages]
    if not all(np.isfinite(values)) or any(b <= a for a, b in zip(values, values[1:])):
        raise ValueError("Passage times must be finite and strictly ordered")
    output = []
    for number, passage in enumerate(passages, 1):
        center = float(passage["time_s"])
        if not t[0] <= center <= t[-1]:
            raise ValueError("Passage is outside the trace")
        lower, upper = center - 10., center + 10.
        selected = (t >= lower) & (t <= upper)
        if not selected.any():
            raise ValueError("Passage window contains no packet")
        nearest = lambda time: int(np.argmin(np.abs(t - time)))
        state = {label: _snapshot(trace, nearest(time), time)
                 for label, time in (("start", lower), ("passage", center), ("end", upper))}
        series = {"time_s": t[selected].tolist(), "accepted": trace["mask"][selected].tolist()}
        summaries = {}
        for field in ("q_s", "distance", "s_infl"):
            data = np.asarray(trace[field])[selected]
            if not np.isfinite(data).all():
                raise ValueError("Nonfinite passage observation diagnostics")
            series[field] = data.tolist()
            summaries[field] = dict(min=float(np.min(data)), max=float(np.max(data)),
                                    mean=float(np.mean(data)), median=float(np.median(data)))
        output.append(dict(passage_number=number, passage_time_s=center, requested_window_s=[lower, upper],
            observed_window_s=[float(t[selected][0]), float(t[selected][-1])], samples=int(selected.sum()),
            snapshots=state, nominal_local_information=local_information(trace, selected),
            observation_summaries=summaries, series=series,
            branch={name: passage.get(name) for name in ("MIRROR_FAIL", "PRE_PASS_OVERCONFIDENT",
                "longest_mirror_duration_s", "warning_y_z", "post_support_end_s")},
            index_rule="nearest packet; earlier packet wins an exact tie; requested +/-10 s mask scored separately"))
    return output


def _passage_contract(path):
    data, identity, replay_contract, generation = _contract(path)
    source = Path(__file__).resolve()
    if sum(Path(item["path"]).resolve() == source for item in data["sources"]) != 1:
        raise ValueError("Scoring contract must pin this exact m7_passages.py once")
    return data, identity, replay_contract, generation


def _passage_directory(score_root, key):
    key = group_key(key)
    return Path(score_root).resolve() / "passages" / "groups" / key["condition"] / key["mode"] / f"seed{key['seed']}"


def annotate_group(contract_path, key, score_root):
    """Verify existing full score group; add R5 diagnostics in a separate folder."""
    key = group_key(key)
    data, identity, replay_contract, _ = _passage_contract(contract_path)
    directory = _passage_directory(score_root, key)
    if directory.exists():
        receipt = read(directory / "EXECUTION.json")
        if receipt.get("status") != "PASS_PASSAGE_DIAGNOSTICS" or receipt.get("contract") != identity or receipt.get("group") != key:
            raise FileExistsError("Preserve incomplete/old passage evidence; use a new score attempt")
        _verify_records(receipt["dependencies"])
        checked(receipt["passage_output"])
        return receipt
    group_receipt_path = _group_directory(score_root, key) / "EXECUTION.json"
    group_receipt = read(group_receipt_path)
    if group_receipt.get("status") != "PASS_SCORING" or group_receipt.get("contract") != identity or group_receipt.get("group") != key:
        raise ValueError("Existing score group receipt identity/status differs")
    _verify_records(group_receipt["dependencies"])
    scored = read(checked(group_receipt["group_output"]))
    if any(scored[name] != value for name, value in key.items()):
        raise ValueError("Existing GROUP identity differs")
    if set(scored["branches"]) != set(ROUTES) or set(scored["branches"]["R5"]) != set(ARMS):
        raise ValueError("Existing branch score grid is incomplete")
    index = read(checked(data["input_index"]))
    lookup = {cell["id"]: cell for cell in replay_contract["expected_cells"]}
    dependencies = [record(group_receipt_path), group_receipt["group_output"]]
    r5_traces = {}
    evaluator = arrays(checked(data["evaluator_inputs"]["R5"]))
    dependencies.append(data["evaluator_inputs"]["R5"])
    for route in ROUTES:
        inp = resolve_input(index, key["condition"], key["seed"], route)
        checked(inp)
        dependencies.append(inp)
        for arm in ARMS:
            cell = lookup[f"{key['condition']}/{key['mode']}/seed{key['seed']}/{route}/{arm}"]
            execution, pin = _cell_receipt(data["replay_root"], cell, data["replay_contract"], inp)
            dependencies.extend((pin, execution["trace"]))
            if cell["trace_alias_of"]:
                dependencies.append(execution["alias_receipt"])
            if route == "R5":
                trace = arrays(checked(execution["trace"]))
                for field in ("t", "pose_id"):
                    np.testing.assert_array_equal(trace[field], evaluator[field])
                if (str(np.asarray(trace["metadata_arm"]).item()) != arm
                        or str(np.asarray(trace["metadata_condition"]).item()) != key["condition"]
                        or str(np.asarray(trace["metadata_rref_policy"]).item()) != "own"):
                    raise ValueError("R5 passage trace identity differs")
                gate_mode = str(np.asarray(trace["metadata_gate_mode"]).item())
                if gate_mode != key["mode"] and not (arm == "H0" and key["mode"] == "fixed" and gate_mode == "own"):
                    raise ValueError("R5 passage gate mode differs")
                r5_traces[arm] = trace
    directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="FAIL_PASSAGE_DIAGNOSTICS", exit_code=1, contract=identity, group=key,
                   dependencies=dependencies, started_utc=datetime.now(timezone.utc).isoformat(),
                   command=[sys.executable, *sys.argv], independent_audit=False)
    try:
        result = dict(**key, arms={arm: passage_diagnostics(r5_traces[arm], scored["branches"]["R5"][arm]["passages"])
                                   for arm in ARMS}, claim_limit=INFORMATION_LIMIT,
                      classification="DIAGNOSTIC_ONLY_NO_NEW_THRESHOLDS", checked_replay_receipts=21,
                      loaded_R5_traces=7, original_group=group_receipt["group_output"], contract=identity)
        _verify_records(dependencies)
        if _passage_contract(contract_path)[1] != identity:
            raise ValueError("Scoring contract changed during passage diagnostics")
        path = directory / "PASSAGES.json"
        write_new(path, result)
        receipt.update(status="PASS_PASSAGE_DIAGNOSTICS", exit_code=0, passage_output=record(path))
    except BaseException as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_new(directory / "EXECUTION.json", receipt)
    return receipt


def passage_table(results):
    rows = []
    for result in results:
        for arm in ARMS:
            passages = result["arms"][arm]
            if [p["passage_number"] for p in passages] != [1, 2, 3]:
                raise ValueError("Missing/reordered R5 passage diagnostics")
            for passage in passages:
                row = dict(condition=result["condition"], mode=result["mode"], seed=result["seed"], arm=arm,
                           passage=passage["passage_number"], passage_time_s=passage["passage_time_s"],
                           report_only=result["condition"] == STRESS or result["mode"] == "fixed",
                           samples=passage["samples"], MIRROR_FAIL=passage["branch"]["MIRROR_FAIL"],
                           PRE_PASS_OVERCONFIDENT=passage["branch"]["PRE_PASS_OVERCONFIDENT"])
                for label in ("start", "passage", "end"):
                    snapshot = passage["snapshots"][label]
                    for field in ("packet_index", "time_s", "requested_time_s", "time_offset_s", "b_g_deg_s",
                                  "b_theta_deg", "b_g_prior_deg_s", "b_theta_prior_deg", "q_s", "distance_m", "s_infl"):
                        row[f"{label}_{field}"] = snapshot[field]
                    for state, suffix in (("posterior", ""), ("prior", "_prior")):
                        for name, value in zip(("x_m", "y_m", "psi_rad"), snapshot[f"{state}_nav_xypsi"], strict=True):
                            row[f"{label}_{name}{suffix}"] = value
                        for name, value in zip(("x", "y", "psi", "bg"), snapshot[f"{state}_nav_P_diagonal"], strict=True):
                            row[f"{label}_P_{name}{suffix}"] = value
                for field, summary in passage["observation_summaries"].items():
                    for name, value in summary.items():
                        row[f"{field}_{name}"] = value
                information = passage["nominal_local_information"]
                row["information_status"], row["accepted_information_packets"] = information["status"], information["accepted"]
                for channel in ("total", "range_first", "conditional_polarization"):
                    for term in ("J_yy", "J_psipsi", "J_ypsi"):
                        row[f"nominal_{channel}_{term}"] = information[channel][term]
                rows.append(row)
    return rows


def aggregate_passages(contract_path, score_root, output_dir):
    data, identity, _, _ = _passage_contract(contract_path)
    score_root, output = Path(score_root).resolve(), Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError("Preserve previous passage aggregate; use a new directory")
    expected = {_passage_directory(score_root, key) / "EXECUTION.json" for key in expected_groups()}
    actual = set((score_root / "passages" / "groups").rglob("EXECUTION.json"))
    if actual != expected:
        raise ValueError("Missing/extra passage diagnostic group receipt")
    results, dependencies = [], []
    for key in expected_groups():
        path = _passage_directory(score_root, key) / "EXECUTION.json"
        receipt = read(path)
        if receipt.get("status") != "PASS_PASSAGE_DIAGNOSTICS" or receipt.get("contract") != identity or receipt.get("group") != key:
            raise ValueError("Passage diagnostic receipt identity/status differs")
        _verify_records(receipt["dependencies"])
        result = read(checked(receipt["passage_output"]))
        if any(result[name] != value for name, value in key.items()) or set(result["arms"]) != set(ARMS):
            raise ValueError("Passage output grid identity differs")
        results.append(result)
        dependencies.extend((record(path), receipt["passage_output"]))
    rows = passage_table(results)
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="FAIL_PASSAGE_AGGREGATION", exit_code=1, contract=identity,
                   dependencies=dependencies, started_utc=datetime.now(timezone.utc).isoformat(), independent_audit=False)
    try:
        with (output / "R5_PASSAGE_INFORMATION.csv").open("x", encoding="utf-8-sig", newline="") as stream:
            stream.write(_csv_text(rows))
        write_new(output / "PASSAGE_SUMMARY.json", dict(status="COMPLETE_PASSAGE_DIAGNOSTICS", score_groups=70,
            arm_passage_rows=len(rows), expected_arm_passage_rows=70*7*3, claim_limit=INFORMATION_LIMIT,
            classification="DIAGNOSTIC_ONLY_NO_NEW_THRESHOLDS", contract=identity))
        _verify_records(dependencies)
        if _passage_contract(contract_path)[1] != identity:
            raise ValueError("Scoring contract changed during passage aggregation")
        receipt.update(status="PASS_PASSAGE_AGGREGATION", exit_code=0,
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
    parser.add_argument("--score-root", required=True, type=Path)
    parser.add_argument("--group-key")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.aggregate:
        if args.group_key or args.output_dir is None:
            parser.error("Aggregation requires --output-dir and no --group-key")
        result = aggregate_passages(args.contract, args.score_root, args.output_dir)
    else:
        if not args.group_key or args.output_dir:
            parser.error("Annotation requires --group-key and writes below --score-root/passages")
        result = annotate_group(args.contract, args.group_key, args.score_root)
    print(json.dumps(result, ensure_ascii=False), flush=True)
