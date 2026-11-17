"""Immutable, hash-pinned offline M7 scoring after replay has completed.

Importing this module performs no work. Each score_one_group call reads one
complete 21-trace group. Scoring never alters online replay files. Aggregation
requires all 70 groups and all 1,470 replay receipts, including DR aliases.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import sys

import numpy as np

from m7_assess import bias_metrics
from m7_inputs import arrays, checked, resolve_input
from m7_report import H5_CLAIM_LIMIT, METRICS, summarize_all
from m7_score import score_comparison
from m7_spec import ARMS, CONDITIONS, FIXED_SEEDS, MAIN_CONDITIONS, PLAN_COMMIT, PLAN_SHA256
from m7_spec import ROUTES, SEEDS, STRESS, expected_cells, validate_cell_index


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=sha(path))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _verify_records(node):
    if isinstance(node, dict):
        if {"path", "sha256"} <= node.keys():
            checked(node)
        else:
            for value in node.values():
                _verify_records(value)
    elif isinstance(node, list):
        for value in node:
            _verify_records(value)


def _contract(path):
    path = Path(path).resolve()
    data, identity = read(path), record(path)
    if data.get("authorization", {}).get("scoring") != "GO":
        raise ValueError("Scoring GO is absent")
    if data["plan"]["commit"] != PLAN_COMMIT or data["plan"]["sha256"] != PLAN_SHA256:
        raise ValueError("Revised M7 plan identity differs")
    _verify_records(data)
    root = Path(__file__).resolve().parent
    for name in ("m7_score_run.py", "m7_score.py", "m7_report.py", "m7_assess.py", "m7_spec.py", "m7_inputs.py"):
        if sum(Path(item["path"]).resolve() == root / name for item in data["sources"]) != 1:
            raise ValueError(f"Scoring contract must pin this exact {name} once")
    replay_contract = read(checked(data["replay_contract"]))
    if replay_contract.get("authorization", {}).get("replay") != "GO":
        raise ValueError("Referenced replay contract is not authorized")
    if replay_contract["plan"] != data["plan"] or replay_contract["input_index"] != data["input_index"]:
        raise ValueError("Scoring and replay plan/input identities differ")
    validate_cell_index(replay_contract["expected_cells"])
    if set(data["evaluator_inputs"]) != set(ROUTES):
        raise ValueError("Every frozen evaluator is required")
    latent = data["offline_latents"]
    receipt = read(checked(latent["receipt"]))
    if receipt.get("status") != "PASS_EXECUTION" or receipt.get("candidate_count") != 120:
        raise ValueError("Input generation/latent receipt did not pass")
    if Path(latent["root"]).resolve() != Path(latent["receipt"]["path"]).resolve().parent:
        raise ValueError("Latent root must be the generation receipt directory")
    return data, identity, replay_contract, receipt


def expected_groups():
    return [dict(condition=condition, mode=mode, seed=seed)
            for condition in CONDITIONS
            for mode in (("own", "fixed") if condition in MAIN_CONDITIONS else ("own",))
            for seed in (SEEDS if mode == "own" else FIXED_SEEDS)]


def group_key(key):
    if isinstance(key, str):
        condition, mode, seed = key.split("/")
        if not seed.startswith("seed"):
            raise ValueError("Group key requires condition/mode/seedN")
        key = dict(condition=condition, mode=mode, seed=int(seed[4:]))
    if (not isinstance(key, dict) or set(key) != {"condition", "mode", "seed"}
            or type(key["seed"]) is not int or key not in expected_groups()):
        raise ValueError("Unknown/relabelled score group")
    return dict(key)


def _group_directory(root, key):
    key = group_key(key)
    root = Path(root).resolve()
    directory = root / "groups" / key["condition"] / key["mode"] / f"seed{key['seed']}"
    directory.relative_to(root)
    return directory


def _cell_receipt(root, cell, replay_identity, input_record):
    path = Path(root).resolve().joinpath("cells", *cell["id"].split("/"), "EXECUTION.json")
    receipt = read(path)
    if (receipt.get("status") != "PASS_EXECUTION" or receipt.get("exit_code") != 0
            or receipt.get("cell") != cell or receipt.get("input") != input_record
            or receipt.get("contract", {}).get("sha256") != replay_identity["sha256"]
            or Path(receipt["contract"]["path"]).resolve() != Path(replay_identity["path"]).resolve()
            or receipt.get("executed") is not cell["execute"]
            or receipt.get("trace_alias_of") != cell["trace_alias_of"]):
        raise ValueError(f"Unverified replay cell receipt: {cell['id']}")
    checked(receipt["trace"])
    if cell["trace_alias_of"]:
        alias_path = Path(root).resolve().joinpath("cells", *cell["trace_alias_of"].split("/"), "EXECUTION.json")
        if Path(checked(receipt["alias_receipt"])).resolve() != alias_path:
            raise ValueError("DR alias receipt points outside its own-mode cell")
        alias = read(alias_path)
        if (alias.get("status") != "PASS_EXECUTION" or alias.get("trace") != receipt["trace"]
                or alias.get("cell", {}).get("id") != cell["trace_alias_of"]
                or alias.get("input") != input_record or alias.get("executed") is not True
                or alias.get("contract", {}).get("sha256") != replay_identity["sha256"]):
            raise ValueError("DR alias does not preserve the exact verified trace")
    return receipt, record(path)


def _load_scorers(assets):
    files = assets["files"]
    pins = {Path(item["path"]).resolve(): item["sha256"] for item in files}
    if len(pins) != len(files):
        raise ValueError("Duplicate scorer asset paths")
    for item in files:
        checked(item)
    directories = [Path(path).resolve() for path in assets["module_dirs"]]
    for path in reversed(directories):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    modules = []
    for key, default in (("verify_module", "verify_s2"), ("block_module", "ks_diagnostics"),
                         ("branch_module", "exposure_score")):
        module = importlib.import_module(assets.get(key, default))
        source = Path(module.__file__).resolve()
        if source not in pins or sha(source) != pins[source]:
            raise ValueError(f"Scorer module is not the pinned source: {source}")
        modules.append(module)
    # The block scorer imports this lazily; resolve it before checking closure.
    importlib.import_module(assets.get("metrics_module", "metrics_s2"))
    # Local transitive Python imports must also be in the frozen scorer closure.
    for module in tuple(sys.modules.values()):
        file = getattr(module, "__file__", None)
        if file is None or not str(file).endswith(".py"):
            continue
        source = Path(file).resolve()
        if any(source.is_relative_to(directory) for directory in directories):
            if source not in pins or sha(source) != pins[source]:
                raise ValueError(f"Unpinned transitive scorer source: {source}")
    return modules[0].from_trace, modules[1].scores_with_blocks, modules[2].branch_metrics


def independent_rows(trace, truth):
    """Independent Cholesky residual calculation with fixed 95% quantiles."""
    x, p, truth = np.asarray(trace["x"]), np.asarray(trace["P"]), np.asarray(truth)
    if (x.ndim != 2 or x.shape[1] < 4 or truth.shape != (len(x), 3)
            or p.shape != (len(x), x.shape[1], x.shape[1])
            or not all(np.isfinite(value).all() for value in (x, p, truth))):
        raise ValueError("Invalid evaluator/trace score shapes")
    error = x[:, :3] - truth
    error[:, 2] = (error[:, 2] + np.pi) % (2 * np.pi) - np.pi
    np.testing.assert_allclose(p, p.swapaxes(-1, -2), atol=1e-10, rtol=0.)
    chol = np.linalg.cholesky(p[:, :3, :3])
    whitened3 = np.linalg.solve(chol, error[..., None])[..., 0]
    whitened2 = np.linalg.solve(chol[:, :2, :2], error[:, :2, None])[..., 0]
    nees3, nees2 = np.einsum("ni,ni->n", whitened3, whitened3), np.einsum("ni,ni->n", whitened2, whitened2)
    return np.column_stack((np.degrees(error[:, 2])**2, 10000 * np.einsum("ni,ni->n", error[:, :2], error[:, :2]),
                            nees3, nees3 <= 7.814727903251179, nees2 <= 5.991464547107979,
                            np.abs(error[:, 2]) <= 1.96 * np.sqrt(p[:, 2, 2])))


def independent_point(rows):
    values = np.mean(rows, axis=0)
    return dict(n=len(rows), heading_rmse_deg=float(np.sqrt(values[0])), xy_rmse_cm=float(np.sqrt(values[1])),
                mean_nees3=float(values[2]), pose95_coverage=float(values[3]),
                xy95_coverage=float(values[4]), heading95_coverage=float(values[5]))


def _latent_arrays(data, receipt, seed, route, condition, packet):
    relative = f"offline_latents/seed{seed}/{route}_gyro.npz"
    pin = dict(path=str(Path(data["offline_latents"]["root"]) / relative), sha256=receipt["outputs"][relative])
    latent = arrays(checked(pin))
    np.testing.assert_array_equal(latent["t"], packet["t"])
    name = "B0" if condition == "B0" else "L2"
    np.testing.assert_array_equal(latent[f"{name}_true_bias_rad_s"], np.zeros_like(packet["t"]))
    noise = latent[f"{name}_white"]
    np.testing.assert_allclose(packet["gy"] - latent["gyro_clean"], noise, atol=1e-14, rtol=1e-12)
    return noise, pin


def _window_diagnostic(trace, truth, packet, noise, lower, upper):
    t = trace["t"]
    use = (t >= max(lower, t[0])) & (t <= min(upper, t[-1]))
    if not use.any():
        return dict(status="NO_SAMPLES", requested_seconds=[lower, upper])
    heading = (trace["x"][:, 2] - truth[:, 2] + np.pi) % (2 * np.pi) - np.pi
    series = dict(time_s=t[use].tolist(), heading_error_deg=np.degrees(heading[use]).tolist(),
                  heading_sd_deg=np.degrees(np.sqrt(trace["P"][use, 2, 2])).tolist(),
                  y_error_cm=(100 * (trace["x"][use, 1] - truth[use, 1])).tolist(),
                  gyro_error_cumulative_deg=np.degrees(np.cumsum(noise))[use].tolist(),
                  b_theta_deg=np.degrees(trace["b_theta"][use]).tolist(),
                  s_infl=trace["s_infl"][use].tolist(), distance_m=trace["distance"][use].tolist(),
                  accepted=trace["mask"][use].tolist())
    return dict(status="DIAGNOSTIC_ONLY", requested_seconds=[lower, upper], samples=int(use.sum()),
                point=independent_point(independent_rows(trace, truth)[use]),
                window_summary=dict(y_rmse_cm=float(np.sqrt(np.mean(np.asarray(series["y_error_cm"])**2))),
                    median_heading_sd_deg=float(np.median(series["heading_sd_deg"])),
                    median_s_infl=float(np.median(series["s_infl"])),
                    median_b_theta_deg=float(np.median(series["b_theta_deg"]))),
                bias=bias_metrics(trace, controls={"dt": packet["dt"]}, window=(max(lower, t[0]), min(upper, t[-1])),
                                  gyro_error_increment=noise), series=series)


def score_one_group(contract_path, key, output_root):
    """Process-safe single complete group; exclusive writes preserve old evidence."""
    key = group_key(key)
    data, identity, replay_contract, generation = _contract(contract_path)
    directory = _group_directory(output_root, key)
    if directory.exists():
        receipt = read(directory / "EXECUTION.json")
        if receipt.get("status") != "PASS_SCORING" or receipt.get("contract") != identity or receipt.get("group") != key:
            raise FileExistsError("Preserve old/incomplete scoring evidence; use a fresh attempt")
        _verify_records(receipt["dependencies"])
        checked(receipt["group_output"])
        return receipt
    stop = os.environ.get("MANAGED_PROCESS_STOP_FILE")
    if stop and Path(stop).exists():
        raise InterruptedError("Managed stop requested before scoring group")
    original_from_trace, block_scorer, branch_scorer = _load_scorers(data["scorer_assets"])
    index = read(checked(data["input_index"]))
    lookup = {cell["id"]: cell for cell in replay_contract["expected_cells"]}
    traces, truth, times, packets, noises, dependencies, diagnostics = {}, {}, {}, {}, {}, [], {}
    replay_identity = data["replay_contract"]
    for route in ROUTES:
        input_pin = resolve_input(index, key["condition"], key["seed"], route)
        packet = arrays(checked(input_pin))
        evaluator = arrays(checked(data["evaluator_inputs"][route]))
        for field in ("t", "pose_id"):
            np.testing.assert_array_equal(packet[field], evaluator[field])
        truth[route], times[route], packets[route] = evaluator["truth"], packet["t"], packet
        noises[route], latent_pin = _latent_arrays(data, generation, key["seed"], route, key["condition"], packet)
        dependencies.extend((input_pin, data["evaluator_inputs"][route], latent_pin))
        traces[route] = {}
        for arm in ARMS:
            cell_id = f"{key['condition']}/{key['mode']}/seed{key['seed']}/{route}/{arm}"
            cell = lookup[cell_id]
            receipt, pin = _cell_receipt(data["replay_root"], cell, replay_identity, input_pin)
            trace = arrays(checked(receipt["trace"]))
            for field in ("t", "pose_id"):
                np.testing.assert_array_equal(trace[field], evaluator[field])
            traces[route][arm] = trace
            dependencies.extend((pin, receipt["trace"]))
            if cell["trace_alias_of"]:
                dependencies.append(receipt["alias_receipt"])
    point_checks = []

    def checked_rows(trace, reference):
        actual, independent = original_from_trace(trace, reference), independent_rows(trace, reference)
        np.testing.assert_allclose(actual, independent, atol=1e-10, rtol=1e-12)
        point_checks.append(float(np.max(np.abs(actual - independent))))
        return actual

    directory.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="FAIL_SCORING", exit_code=1, started_utc=datetime.now(timezone.utc).isoformat(),
                   contract=identity, group=key, dependencies=dependencies,
                   command=[sys.executable, *sys.argv], role="IMPLEMENTER",
                   question_id="G1-INT-001/M7-STAGE1", independent_audit=False)
    try:
        result = score_comparison(key["seed"], key["condition"], key["mode"], traces, truth, times,
            from_trace=checked_rows, scores_with_blocks=block_scorer, branch_metrics=branch_scorer,
            controls={r: {"dt": packets[r]["dt"]} for r in ROUTES}, gyro_error_increments=noises)
        summary_errors = []
        for arm in ARMS:
            joined = []
            for route in ROUTES:
                row = independent_rows(traces[route][arm], truth[route])
                joined.append(row)
                check = independent_point(row)
                for metric, value in check.items():
                    archived = result["scores"]["point"][route][arm][metric]
                    np.testing.assert_allclose(value, archived, atol=1e-10, rtol=1e-12)
                    summary_errors.append(abs(value - archived))
            check = independent_point(np.concatenate(joined))
            for metric, value in check.items():
                archived = result["scores"]["point"]["pooled"][arm][metric]
                np.testing.assert_allclose(value, archived, atol=1e-10, rtol=1e-12)
                summary_errors.append(abs(value - archived))
        for route in ("R2", "R5"):
            diagnostics[route] = {}
            for arm in ARMS:
                trace = traces[route][arm]
                if route == "R2":
                    windows = [("80_120s", 80., 120.), ("120_160s", 120., 160.)]
                else:
                    windows = [(f"pass{i+1}", passage["time_s"] - 10., passage["time_s"] + 10.)
                               for i, passage in enumerate(result["branches"][route][arm]["passages"])]
                diagnostics[route][arm] = {name: _window_diagnostic(trace, truth[route], packets[route], noises[route], lo, hi)
                                           for name, lo, hi in windows}
        result["diagnostics"] = diagnostics
        result["implementation_checks"] = dict(status="PASS_IMPLEMENTER_SCORE_CHECKS",
            independent_cholesky_row_max_abs=max(point_checks), independent_point_max_abs=max(summary_errors),
            checked_traces=21, checked_replay_receipts=21, evaluator_join="exact t and pose_id",
            bootstrap="original deterministic indices shared across arms; 5/10/20 s", audit="not an independent audit")
        result["provenance"] = dict(contract=identity, replay_contract=replay_identity, replay_cell_receipts=[
            dep for dep in dependencies if Path(dep["path"]).name == "EXECUTION.json"], sources=data["sources"])
        _verify_records(dependencies)
        _, final_identity, _, _ = _contract(contract_path)
        if final_identity != identity:
            raise ValueError("Frozen scoring contract changed during scoring")
        path = directory / "GROUP.json"
        write_new(path, result)
        receipt.update(status="PASS_SCORING", exit_code=0, group_output=record(path))
    except BaseException as exc:
        receipt["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        receipt["finished_utc"] = datetime.now(timezone.utc).isoformat()
        write_new(directory / "EXECUTION.json", receipt)
    return receipt


def _csv_text(rows):
    buffer = io.StringIO(newline="")
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return buffer.getvalue()


def comparison_table(comparisons):
    rows = []
    for result in comparisons:
        for group in (*ROUTES, "pooled"):
            for arm in ARMS:
                point = result["scores"]["point"][group][arm]
                assessed = result["seed_assessments"][arm]
                group_assessed = assessed["groups"][group]
                row = dict(condition=result["condition"], mode=result["mode"], seed=result["seed"], group=group,
                           arm=arm, report_only=result["condition"] == STRESS or result["mode"] == "fixed",
                           **{metric: point[metric] for metric in ("n", *METRICS)},
                           group_integrity_pass=group_assessed["integrity_pass"], group_accuracy_pass=group_assessed["accuracy_pass"],
                           group_joint_pass=group_assessed["joint_pass"], I_seed=assessed["I_seed"], A_seed=assessed["A_seed"],
                           J_seed=assessed["J_seed"], mirror_fail=group_assessed["mirror_fail"])
                for metric in ("heading_rmse_deg", "xy_rmse_cm"):
                    value = point[metric]
                    for baseline in ("H2", "H0", "H1"):
                        reference = result["scores"]["point"][group][baseline][metric]
                        row[f"{metric}_{'cost' if baseline == 'H2' else 'improvement'}_vs_{baseline}_pct"] = (
                            None if reference == 0 else 100 * (value/reference - 1 if baseline == "H2" else 1-value/reference))
                endpoint = result["endpoint"][group][arm] if group in ROUTES else {}
                for name in ("heading_signed_deg", "heading_abs_deg", "xy_error_cm"):
                    row[f"endpoint_{name}"] = endpoint.get(name)
                for field in ("bias_error_deg_s", "sqrt_P_bg_deg_s", "normalized_error"):
                    stats = result["bias"][group][arm][field] if group in ROUTES else None
                    for name in ("signed_mean", "rmse", "abs_p95", "abs_max", "endpoint"):
                        row[f"{field}_{name}"] = None if stats is None else stats[name]
                for metric in ("pose95_coverage", "heading95_coverage", "xy95_coverage"):
                    row[f"{metric}_ci10_lower"] = group_assessed["ci10_lower"][metric]
                rows.append(row)
    return rows


def count_table(summary):
    rows = []
    for campaign in summary["campaigns"].values():
        for arm, data in campaign["arms"].items():
            assessment = data["assessment"]
            for subset, counts in (("all_seeds", assessment), *assessment["subsets"].items()):
                row = dict(condition=campaign["condition"], mode=campaign["mode"], arm=arm, subset=subset,
                    denominator=counts["denominator"], N_integrity=counts["N_integrity"], N_accuracy=counts["N_accuracy"],
                    N_joint=counts["N_joint"], mirror_passage_events=counts["mirror_passage_events"],
                    mirror_route_runs=counts["mirror_route_runs"], report_only=campaign["report_only"],
                    CONDITION_PASS=assessment["CONDITION_PASS"] if subset == "all_seeds" else None,
                    CONDITION_INTEGRITY_PASS=assessment["CONDITION_INTEGRITY_PASS"] if subset == "all_seeds" else None,
                    CONDITION_ACCURACY_PASS=assessment["CONDITION_ACCURACY_PASS"] if subset == "all_seeds" else None)
                for label in ("integrity", "accuracy", "joint", "mirror_seed"):
                    row[f"{label}_rate"] = counts[f"{label}_rate"]
                    row[f"{label}_ci95_lower"], row[f"{label}_ci95_upper"] = counts[f"{label}_ci95"]
                rows.append(row)
    return rows


def aggregate(contract_path, score_root, output_dir):
    data, identity, replay_contract, _ = _contract(contract_path)
    root, output = Path(score_root).resolve(), Path(output_dir).resolve()
    if output.exists():
        raise FileExistsError("Preserve aggregate evidence; use a fresh output directory")
    expected_receipts = {Path(data["replay_root"]).resolve().joinpath("cells", *cell["id"].split("/"), "EXECUTION.json")
                         for cell in replay_contract["expected_cells"]}
    actual_receipts = set((Path(data["replay_root"]).resolve() / "cells").rglob("EXECUTION.json"))
    if actual_receipts != expected_receipts:
        raise ValueError("Missing/extra replay receipt grid")
    groups, group_receipts = [], []
    expected_group_receipts = {_group_directory(root, key) / "EXECUTION.json" for key in expected_groups()}
    if set((root / "groups").rglob("EXECUTION.json")) != expected_group_receipts:
        raise ValueError("Missing/extra scoring group grid")
    index = read(checked(data["input_index"]))
    for cell in replay_contract["expected_cells"]:
        inp = resolve_input(index, cell["condition"], cell["seed"], cell["route"])
        _cell_receipt(data["replay_root"], cell, data["replay_contract"], inp)
    for key in expected_groups():
        path = _group_directory(root, key) / "EXECUTION.json"
        receipt = read(path)
        if receipt.get("status") != "PASS_SCORING" or receipt.get("contract") != identity or receipt.get("group") != key:
            raise ValueError("Unverified scoring group receipt")
        _verify_records(receipt["dependencies"])
        group = read(checked(receipt["group_output"]))
        if any(group[name] != key[name] for name in key):
            raise ValueError("Scored group identity differs")
        groups.append(group)
        group_receipts.append(record(path))
    summary = summarize_all(groups)
    decision = dict(status="COMPLETE_NUMERIC_ASSESSMENT", overall_by_arm=summary["overall_by_arm"],
                    H5_claim_limit=H5_CLAIM_LIMIT, adoption="Separate user/scientific decision", audit="Implementer checks only",
                    limitation="20 wheel/gyro seeds share one frozen RF realization; not independent RF/environment replications")
    lines = ["# M7 Stage 1 검증 결과", "", "20개 seed는 같은 RF 실현을 공유합니다. RF·환경 일반화의 독립 검증이 아닙니다.", "",
             "주 판정은 B0와 Q가 일치하는 L2입니다. Q 불일치 stress와 고정 mask 대조는 보고 전용입니다.", "",
             "| 조건 | gate | arm | 무결성 | 정확도 | 동시 | mirror | 판정 |", "|---|---|---|---:|---:|---:|---:|---|"]
    for row in count_table(summary):
        if row["subset"] == "all_seeds":
            state = "REPORT_ONLY" if row["report_only"] else ("PASS" if row["CONDITION_PASS"] else "FAIL")
            lines.append(f"| {row['condition']} | {row['mode']} | {row['arm']} | {row['N_integrity']}/{row['denominator']} | {row['N_accuracy']}/{row['denominator']} | {row['N_joint']}/{row['denominator']} | {row['mirror_passage_events']} | {state} |")
    lines += ["", "H5는 GM 몫을 뺀 잔여 q_s를 사용하므로 H5 실패만으로 b_θ 필요성을 주장할 수 없습니다. H5′를 함께 봅니다.",
              "", "seed 10–14와 진단에 사용하지 않은 seed 15–29를 COUNTS_SUBSETS.csv에 별도 집계했습니다. 기존 기준은 완화하지 않았습니다.",
              "", "본 결과는 실행·구현 검사와 수치 판정이며, 독립 감사 완료나 모델 채택을 뜻하지 않습니다."]
    output.mkdir(parents=True, exist_ok=False)
    receipt = dict(status="FAIL_AGGREGATION", exit_code=1, contract=identity,
                   started_utc=datetime.now(timezone.utc).isoformat(), group_receipts=group_receipts,
                   checked_replay_receipts=1470, checked_score_groups=70, command=[sys.executable, *sys.argv])
    try:
        write_new(output / "SUMMARY.json", summary)
        write_new(output / "DECISION.json", decision)
        for name, rows in (("BY_TRAJECTORY_SEED.csv", comparison_table(groups)), ("COUNTS_SUBSETS.csv", count_table(summary))):
            with (output / name).open("x", encoding="utf-8-sig", newline="") as stream:
                stream.write(_csv_text(rows))
        with (output / "REPORT_KO.md").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("\n".join(lines) + "\n")
        _verify_records(group_receipts)
        _, final_identity, _, _ = _contract(contract_path)
        if final_identity != identity:
            raise ValueError("Scoring contract drift during aggregation")
        receipt.update(status="PASS_AGGREGATION", exit_code=0,
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
    parser.add_argument("--group-key")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--score-root", type=Path)
    args = parser.parse_args()
    if args.aggregate:
        if args.group_key or args.score_root is None:
            parser.error("Aggregation requires --score-root and no --group-key")
        result = aggregate(args.contract, args.score_root, args.output_dir)
    else:
        if not args.group_key:
            parser.error("Single-group scoring requires --group-key condition/mode/seedN")
        result = score_one_group(args.contract, args.group_key, args.output_dir)
    print(json.dumps(result, ensure_ascii=False), flush=True)
