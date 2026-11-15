"""Reaggregate and verify D0/D5/D1 artifacts from their measured scores."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

from d1_shuffle import CONDITIONS, dump, sha, verify_file


METRICS = ("heading_rmse_deg", "xy_rmse_cm", "mean_nees3", "pose95_coverage",
           "xy95_coverage", "heading95_coverage")
SQUARE_METRICS = METRICS[:2]
LEVELS = ("B_B0", "B_L2", "A_B0", "A_L2")
ROUTES = ("R2", "R4", "R5")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def dispersion(scores, base):
    if not scores:
        return None
    result = {}
    for key in METRICS:
        median, lo, hi = np.quantile([x[key] for x in scores], [.50, .025, .975])
        result[key] = {"median": float(median), "p025_p975": [float(lo), float(hi)],
                       "delta_from_e0": float(median - base[key])}
    return result


def summarize(conditions, base, min_valid):
    results = {}
    for name, rows in conditions.items():
        scores = [row["score"] for row in rows if row["valid"]]
        results[name] = {"valid_reps": len(scores), "all_reps": len(rows),
                         "status": "SUPPORTED_SAMPLE" if len(scores) >= min_valid else "INCONCLUSIVE",
                         "all": dispersion([row["score"] for row in rows], base),
                         "eligible": dispersion(scores, base)}
    return results


def weighted(rows, weights):
    pooled = {}
    for key in METRICS:
        values = np.array([row[key] for row in rows])
        pooled[key] = float(np.sqrt(np.average(values**2, weights=weights)) if key in SQUARE_METRICS
                            else np.average(values, weights=weights))
    return pooled


def factorial_effects(conditions, baseline):
    valid = np.logical_and.reduce([[row["valid"] for row in conditions[name]] for name in ("s_only", "r_only", "both")])
    result = {"valid_reps": int(valid.sum()), "by_metric": {}}
    for metric in METRICS[3:]:
        s, r, sr = [np.array([rep["score"][metric] for rep in conditions[name]]) for name in ("s_only", "r_only", "both")]
        o = baseline[metric]
        estimates = {"s_effect": ((s - o) + (sr - r)) / 2, "r_effect": ((r - o) + (sr - s)) / 2,
                     "interaction": sr - s - r + o}
        result["by_metric"][metric] = {
            key: {"all_median": float(np.median(values)),
                  "eligible_median": float(np.median(values[valid])) if valid.any() else None}
            for key, values in estimates.items()}
    return result


def verdict(summary, metric, floor, original, necessary=False):
    if summary["status"] == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    value = summary["eligible"][metric]["median"]
    return "SUPPORTED" if value >= floor and (not necessary or value > original) else "NOT_SUPPORTED"


def verify_baseline_scores(root, contract, d0, d5):
    sys.path.insert(0, contract["s2"])
    from replay_s2 import read_npz
    from verify_s2 import check_metric_rows, from_trace

    pools = {}
    for cell in contract["cells"]:
        level = f"{cell['anchor']}_{cell['bias']}"
        key = f"{level}_{cell['route']}"
        evaluator = read_npz(verify_file(cell["evaluator"]))
        traces = {stage: read_npz(root / stage / f"{key}.npz") for stage in ("d0", "d5")}
        for stage, trace in traces.items():
            if any(not np.array_equal(trace[field], evaluator[field]) for field in ("t", "pose_id")):
                raise ValueError(f"Evaluator grid changed for {stage}/{key}")
        if not np.array_equal(traces["d0"]["mask"], traces["d5"]["mask"]):
            raise ValueError(f"Fixed gate changed for {key}")
        rows = {stage: from_trace(trace, evaluator["truth"]) for stage, trace in traces.items()}
        for stage, arm in (("d0", "e0"), ("d5", "loro")):
            check_metric_rows(rows[stage], d5["by_cell"][key][arm])
            pools.setdefault((level, arm), []).append(rows[stage])
        check_metric_rows(rows["d0"], d0["by_cell"][key]["e0"])
    for (level, arm), rows in pools.items():
        check_metric_rows(np.concatenate(rows), d5["pooled"][level][arm])


def verify_and_summarize(root):
    contract_path = root / "RUN_CONTRACT.json"
    contract = load(contract_path)
    fingerprint = sha(contract_path)
    d0 = load(root / "d0" / "RESULTS.json")
    d5 = load(root / "d5" / "RESULTS.json")
    receipts = {stage: root / stage / "EXECUTION.json" for stage in ("d0", "d5")}
    stage_executions = {}
    for stage, receipt in receipts.items():
        execution = load(receipt)
        if execution["status"] != "PASS_EXECUTION" or execution["run_contract_sha256"] != fingerprint:
            raise ValueError(f"{stage} did not pass under this contract")
        for file, expected in execution["outputs"].items():
            if sha(root / stage / file) != expected:
                raise ValueError(f"{stage} output changed: {file}")
        stage_executions[stage] = execution
    if stage_executions["d0"]["finished_utc"] >= stage_executions["d5"]["started_utc"]:
        raise ValueError("D5 started before D0 completed")
    min_valid = contract["D1"]["minimum_valid_reps"]
    n_reps = contract["D1"]["repetitions"]
    by_cell, summaries = {}, {}
    expected_ids = {f"{level}_{route}" for level in LEVELS for route in ROUTES}
    if set(d0["by_cell"]) != expected_ids or set(d5["by_cell"]) != expected_ids:
        raise ValueError("Incomplete D0 or D5 cells")
    verify_baseline_scores(root, contract, d0, d5)
    actual_ids = {p.parent.name for p in (root / "d1").glob("*/RESULTS.json")}
    if actual_ids != expected_ids:
        raise ValueError(f"D1 missing {sorted(expected_ids - actual_ids)} or extra {sorted(actual_ids - expected_ids)}")

    output_shas = {}
    for level in LEVELS:
        for route in ROUTES:
            cell = f"{level}_{route}"
            folder = root / "d1" / cell
            path = folder / "RESULTS.json"
            case = load(path)
            if case["status"] != "PASS" or case["cell"] != cell or case["contract_sha256"] != fingerprint:
                raise ValueError(f"Invalid D1 execution identity: {cell}")
            if case["start_utc"] <= stage_executions["d5"]["finished_utc"]:
                raise ValueError(f"D1 started before D5 completed: {cell}")
            if any(case[f"{stage}_sha256"] != sha(root / stage / "RESULTS.json") for stage in receipts):
                raise ValueError(f"Invalid D1 preceding stage identity: {cell}")
            maps = folder / "permutations.npz"
            if case["permutations_sha256"] != sha(maps):
                raise ValueError(f"Invalid D1 permutation artifact: {cell}")
            with np.load(maps, allow_pickle=False) as data:
                permutation = data["maps"]
                expected = np.arange(case["n"], dtype=permutation.dtype)
                if permutation.shape != (n_reps, 3, case["n"]) or not np.all(np.sort(permutation, axis=-1) == expected):
                    raise ValueError(f"Invalid D1 permutation arrays: {cell}")
                if "_L2_" in cell:
                    original = cell.replace("_L2_", "_B0_")
                    with np.load(root / "d1" / original / "permutations.npz", allow_pickle=False) as b0:
                        if not np.array_equal(b0["maps"], permutation):
                            raise ValueError(f"D1 matched-factor permutation mismatch: {cell}")
            reference = d0["by_cell"][cell]["e0"]
            if (case["n"] != reference["n"] or case["accepted"] != d0["by_cell"][cell]["accepted"] or
                    not np.allclose([case["identity"][key] for key in METRICS], [reference[key] for key in METRICS],
                                    atol=1e-12, rtol=1e-12)):
                raise ValueError(f"D1 identity score mismatch: {cell}")
            if set(case["conditions"]) != set(CONDITIONS):
                raise ValueError(f"D1 condition mismatch: {cell}")
            for name, rows in case["conditions"].items():
                if [v["repetition"] for v in rows] != list(range(n_reps)):
                    raise ValueError(f"D1 repetitions incomplete: {cell}/{name}")
                for row in rows:
                    eligible = min(row["moved_fractions"]) >= contract["D1"]["minimum_moved_fraction"]
                    eligible &= all(abs(row["lag1"][c]) <= max(contract["D1"]["lag_floor"],
                                                              contract["D1"]["lag_orig_fraction"] * abs(case["lags_before"][c]))
                                    for c in CONDITIONS[name])
                    if eligible != row["valid"] or not np.isfinite(list(row["score"].values())).all():
                        raise ValueError(f"D1 stored eligibility or score invalid: {cell}/{name}")
            by_cell[cell] = case
            summaries[cell] = summarize(case["conditions"], case["identity"], min_valid)
            output_shas[cell] = {"results": sha(path), "permutations": sha(maps)}

    pooled = {}
    for level in LEVELS:
        cases = [by_cell[f"{level}_{route}"] for route in ROUTES]
        weights = [case["n"] for case in cases]
        baseline = weighted([case["identity"] for case in cases], weights)
        arms = {}
        for name in CONDITIONS:
            arms[name] = []
            for i in range(n_reps):
                rows = [case["conditions"][name][i] for case in cases]
                arms[name].append({"valid": all(v["valid"] for v in rows),
                                   "score": weighted([v["score"] for v in rows], weights)})
        pooled[level] = {"identity": baseline, "conditions": summarize(arms, baseline, min_valid),
                         "paired_factorial": factorial_effects(arms, baseline)}

    key = "B_B0_R4"
    r4 = summaries[key]
    e0 = by_cell[key]["identity"]
    h7 = r4["s_only"]["eligible"]
    h7_gain = h7["xy95_coverage"]["delta_from_e0"] if h7 else None
    h7_state = ("INCONCLUSIVE" if r4["s_only"]["status"] == "INCONCLUSIVE" else
                "D2_REQUIRED" if h7_gain >= contract["D1"]["H7_s_only_xy95_gain_median_min"] else "D1_THRESHOLD_NOT_MET")
    hypothesis = {"H1": verdict(r4["s_only"], "heading95_coverage", contract["D1"]["H1_R4_s_only_heading95_median_min"],
                                e0["heading95_coverage"], necessary=True),
                  "H4": d5["h4"]["verdict"],
                  "H6": verdict(r4["r_only"], "xy95_coverage", contract["D1"]["H6_R4_r_only_xy95_median_min"],
                                e0["xy95_coverage"]),
                  "H7": h7_state, "H2": "PENDING_D2", "H3": "PENDING_D4", "H5": "PENDING_D6"}
    total = sum(1 + sum(len(rows) for rows in case["conditions"].values()) for case in by_cell.values())
    if total != contract["D1"]["total_replays"]:
        raise ValueError("D1 replay count differed from contract")
    result = {"question": "G1-INT-DIAG-001", "status": "COMPLETE_D0_D5_D1", "contract_sha256": fingerprint,
              "hypotheses": hypothesis, "total_d1_replays": total,
              "D0": d0, "D5": d5, "D1": {"by_cell": summaries, "pooled": pooled,
              "paired_factorial_by_cell": {key: factorial_effects(case["conditions"], case["identity"])
                                           for key, case in by_cell.items()}}}
    dump(root / "RESULTS.json", result)
    render_report(root, result)
    dump(root / "VERIFICATION.json", {"status": "PASS_REAGGREGATION", "role": "IMPLEMENTER_SELF_CHECK",
                                       "contract_sha256": fingerprint, "d0_d5_execution_sha256": {k: sha(v) for k, v in receipts.items()},
                                       "d1_outputs_sha256": output_shas, "aggregator_sha256": sha(Path(__file__)),
                                       "report_results_sha256": sha(root / "RESULTS.json"),
                                       "report_markdown_sha256": sha(root / "REPORT_KO.md")})
    print(json.dumps({"hypotheses": hypothesis, "d1_replays": total}))


def render_report(root, result, *, replace=False):
    d5 = result["D5"]
    identity = d5["by_cell"]["B_B0_R4"]["e0"]
    r4 = result["D1"]["by_cell"]["B_B0_R4"]
    diff = d5["pooled"]["B_B0"]["moving_block_bootstrap_paired"]
    b0_delta = -d5["h4"]["b_b0_pose95_drop"] * 100
    headings = {"s_only": "편파만", "r_only": "거리만", "both": "두 채널 별도 순열", "both_paired": "두 채널 공통 순열"}
    lines = ["# G1-INT-DIAG-001 실행 결과", "",
             "Full seed 10, mount 0°, 앵커 B/A, B0/L2, R2/R4/R5. D0 → D5 → D1 순서로 실행했다.",
             "D0에서 9개 셀은 보관 E0 trace와 일치했고, 새로 결합한 A·L2 3개 셀은 별도 Joseph 재귀와 shadow gate 검사를 통과했다.",
             "B·L2의 R4/R5 controls는 Stage 2에서 재생성한 동결본이다. B0와 L2는 같은 RF 기록의 자이로 조건 비교다.",
             "첫 D0의 거리 조회 기록 오류를 수정하면서 실패본과 재실행 근거를 보존했다. 동결 계약의 입력과 판정 기준을 재실행에 사용했다.",
             "", "## D5 σ_b 표 교체", "",
             "| 조건 | Pose95 E0 | Pose95 LORO | heading RMSE E0 → LORO | XY RMSE E0 → LORO |",
             "|---|---:|---:|---:|---:|"]
    for level, row in d5["pooled"].items():
        e0, loro = row["e0"], row["loro"]
        lines.append(f"| {level.replace('_', '·')} | {e0['pose95_coverage']:.1%} | {loro['pose95_coverage']:.1%} | "
                     f"{e0['heading_rmse_deg']:.2f} → {loro['heading_rmse_deg']:.2f}° | "
                     f"{e0['xy_rmse_cm']:.2f} → {loro['xy_rmse_cm']:.2f} cm |")
    lo5, hi5 = (100*x for x in diff["5"]["pose95_coverage"])
    lo10, hi10 = (100*x for x in diff["10"]["pose95_coverage"])
    lines += ["", f"B·B0 Pose95 차이 {b0_delta:+.2f} %p. 5 s 블록 95% 구간 [{lo5:+.2f}, {hi5:+.2f}] %p, "
              f"10 s [{lo10:+.2f}, {hi10:+.2f}] %p. H4 사전 판정은 `{result['hypotheses']['H4']}`.",
              "", "## D1 B·B0 R4 편파·거리 잔차 순열", "",
              "| 순열 조건 | 적격 반복 | Pose95 | heading95 | XY95 |", "|---|---:|---:|---:|---:|",
              f"| E0 동일성 대조 | 1 | {identity['pose95_coverage']:.1%} | {identity['heading95_coverage']:.1%} | {identity['xy95_coverage']:.1%} |"]
    for key, name in headings.items():
        arm = r4[key]
        values = arm["eligible"] or arm["all"]
        qualifier = " (전 반복)" if not arm["eligible"] else ""
        columns = " | ".join(f"{values[field]['median']:.1%}"
                             for field in ("pose95_coverage", "heading95_coverage", "xy95_coverage"))
        lines.append(f"| {name}{qualifier} | {arm['valid_reps']}/{arm['all_reps']} | {columns} |")
    lines += ["", "대조를 제외한 표의 수치는 적격 반복의 중앙값이다. 순열은 전체 패킷 격자의 층별 표준화 잔차 분포를 보존한다. "
              "gate를 고정한 수용 표본의 주변분포와 채널 간 동시 상관은 달라질 수 있다. 순열 산포는 같은 RF 기록에 대한 조건부 결과다.",
              "", "## 진단 표", "", "| ID | 검사 | 결과 |", "|---|---|---|"]
    for key, name in {"H1": "D1 편파 시간 순서", "H4": "D5 hand table 기여", "H6": "D1 거리 시간 순서",
                      "H7": "D1·D2 편파에서 XY로 전달"}.items():
        lines.append(f"| {key} | {name} | `{result['hypotheses'][key]}` |")
    lines += ["| M3 | D2·D3 prior 간 거리·wrapped yaw로 묶은 donor 상관과 재방문 잔차 | 계약에 추가 |", "",
              f"D1은 {result['total_d1_replays']:,}회 재생을 완료했다. D2·D3·D4·D6과 SC·GM·KI는 이번 실행 범위 밖이다.",
              "", "[원자료 집계](RESULTS.json) · [입출력 검증](VERIFICATION.json) · [동결 계약](RUN_CONTRACT.json) · "
              "[개정 수식과 판정](../CONTRACT_AMENDMENT_KO.md)", ""]
    with (root / "REPORT_KO.md").open("w" if replace else "x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    verify_and_summarize(parser.parse_args().run.resolve())
