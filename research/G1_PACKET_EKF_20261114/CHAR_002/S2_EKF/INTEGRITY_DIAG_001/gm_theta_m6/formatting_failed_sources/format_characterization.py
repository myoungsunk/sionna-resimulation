"""Tabulate the completed M6 characterization without data replay or resampling."""

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "characterization_tables"
INPUT = ROOT / "characterization"
INPUT_NAMES = ("K1_PRIME_K2.json", "RUN_CONTRACT.json", "CHECKS.json", "EXECUTION.json")


def utc():
    return datetime.now(timezone.utc).isoformat()


def item(path):
    return {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def freeze():
    OUT.mkdir(parents=True, exist_ok=True)
    contract = dict(question_id="G1-INT-001/M6", role="IMPLEMENTER", stage="characterization tabulation",
                    frozen_utc=utc(), classification="DIAGNOSTIC_ONLY", sources=[item(Path(__file__))],
                    inputs=[item(INPUT / name) for name in INPUT_NAMES],
                    operations="Saved result rows to CSV and Korean report; fixed row-only slope/leverage summaries",
                    resampling=False, new_filter_replays=False,
                    expected_counts=dict(k1_rows=72, k1_strata=24, k2_cells=36, k2_donor_cells=72,
                                         k2_donors=3, k2_folds=3, hybrid_bins=12, hybrid_donor_bins=24))
    write_json(OUT / "RUN_CONTRACT.json", contract)


def table(name, rows):
    if not rows:
        raise ValueError(f"Missing expected table {name}")
    keys = list(dict.fromkeys(key for row in rows for key in row))
    path = OUT / f"{name}.csv"
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                             for key, value in row.items()})
    return len(rows)


def fmt(value, digits=4):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}g}"


def deg(value):
    return None if value is None else math.degrees(value)


def md(headers, rows):
    return ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)] + [
        "| " + " | ".join(fmt(value) for value in row) + " |" for row in rows] + [""]


def row_summary(saved_rows):
    eligible = [r for r in saved_rows if r["eligible"] and r["accepted_stratum"]]
    summaries = []
    for route in ("R2", "R4", "R5"):
        numerator, denominator = 0., 0.
        rows = [r for r in eligible if r["route"] == route]
        for bin_id in sorted({r["distance_bin"] for r in rows}):
            group = [r for r in rows if r["distance_bin"] == bin_id]
            x = [math.log(r["g_rms"]) for r in group]
            y = [math.log(r["variance_s"]) for r in group]
            mx, my = sum(x) / len(x), sum(y) / len(y)
            numerator += sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True))
            denominator += sum((a - mx)**2 for a in x)
        summaries.append(dict(route=route, eligible_rows=len(rows),
                              descriptive_slope=numerator / denominator if denominator else None,
                              centered_log_g_sum_squares=denominator, centered_cross_sum=numerator))
    total = sum(r["centered_log_g_sum_squares"] for r in summaries)
    for row in summaries:
        row["slope_leverage_fraction"] = row["centered_log_g_sum_squares"] / total if total else None
    return summaries


def run():
    lock = read_json(OUT / "RUN_CONTRACT.json")
    for record in lock["inputs"] + lock["sources"]:
        if item(Path(record["path"]))["sha256"] != record["sha256"]:
            raise ValueError(f"Frozen input changed: {record['path']}")
    source = read_json(INPUT / "K1_PRIME_K2.json")
    k1, k2, hybrid = (source[key] for key in ("k1", "k2", "hybrid"))
    populations = {"accepted_supported": k1, "all_supported": k1["all_d3_supported_sensitivity"]}
    k1_rows = [dict(population=pop, **r) for pop, value in populations.items() for r in value["rows"]]
    strata = [dict(population=pop, **r) for pop, value in populations.items() for r in value["strata"]]
    k2_rows = k2["main_cells"]["rows"]
    donor_cells = [dict(holdout=route, **r) for route, fold in k2["folds"].items()
                   for r in fold["donor_cells"]["rows"]]
    donors = {}
    for fold in k2["folds"].values():
        for route, donor in fold["donors"].items():
            if route in donors and donors[route] != donor:
                raise ValueError("Donor summaries differ between folds")
            donors[route] = donor
    donor_rows = []
    for route, donor in donors.items():
        primary = donor["primary"]
        donor_rows.append(dict(route=route, n_d3_supported=donor["n_d3_supported"],
                               excluded_g_lt_1=donor["n_excluded_by_g_cutoff"],
                               **primary,
                               accepted_n=donor["accepted"]["n"],
                               accepted_sigma_rad=donor["accepted"]["sigma_rad"],
                               window_n=donor["window_mean_denominator"]["n"],
                               window_sigma_rad=donor["window_mean_denominator"]["sigma_rad"]))
    fold_rows = [dict(holdout=route, donors=list(fold["donors"]), n=fold["primary"]["n"],
                      sigma_rad=fold["sigma_rad"], sigma_deg=deg(fold["sigma_rad"]),
                      centered_sigma_deg=deg(fold["centered_per_donor_sensitivity"]["sigma_rad"]),
                      accepted_sigma_deg=deg(fold["accepted_sensitivity"]["sigma_rad"]),
                      window_sigma_deg=deg(fold["window_mean_sensitivity"]["sigma_rad"]),
                      distance_status=fold["distance_status"])
                 for route, fold in k2["folds"].items()]
    hybrid_rows, hybrid_donors = [], []
    for route, fold in hybrid["folds"].items():
        for b in fold["bins"]:
            hybrid_rows.append(dict(holdout=route, **{key: value for key, value in b.items() if key != "donors"}))
            for donor_route, donor in b["donors"].items():
                hybrid_donors.append(dict(holdout=route, distance_bin=b["distance_bin"], donor=donor_route,
                                          supported_blocks=donor["supported_blocks"],
                                          numerator=donor["numerator"], denominator=donor["denominator"],
                                          pair_counts_by_block=[r["n_pairs"] for r in donor["blocks"]]))
    tables = dict(k1_rows=k1_rows, k1_strata=strata, k2_cells=k2_rows, k2_donor_cells=donor_cells,
                  k2_donors=donor_rows, k2_folds=fold_rows, hybrid_bins=hybrid_rows,
                  hybrid_donor_bins=hybrid_donors)
    counts = {name: len(rows) for name, rows in tables.items()}
    if counts != lock["expected_counts"]:
        raise ValueError(f"Table count mismatch {counts}")
    for name, rows in tables.items():
        table(name, rows)
    summary = row_summary(k1["rows"])
    denominator = sum(r["centered_log_g_sum_squares"] for r in summary)
    reproduced = sum(r["centered_cross_sum"] for r in summary) / denominator
    if abs(reproduced - k1["slope"]) > 1e-12:
        raise ValueError("Saved row-only common slope differs from recorded fit")
    write_json(OUT / "ROW_SUMMARY.json", dict(routes=summary, reproduced_common_slope=reproduced))
    edges = source["distance_edges_m"]
    distance = lambda k: f"[{edges[k]:g}, {edges[k+1]:g})"
    lines = ["# M6 K1′·K2 특성화 표", "",
             "mount 0°, 앵커 B, B0, R2/R4/R5, seed 10의 완료된 특성화 결과를 표로 정리했다. 원본 결과와 실행 계약의 해시를 이 폴더의 RUN_CONTRACT.json에 연결했다.", "",
             f"K1′의 공통 지수는 {k1['slope']:.6f}, 95% 구간은 [{k1['ci_95'][0]:.6f}, {k1['ci_95'][1]:.6f}]이고 판정은 {k1['verdict']}다. 동결 규칙에 따라 G1+KI가 재생 arm에 추가됐다. K2 일정성 판정은 {k2['verdict']}다.", "",
             "## K1′의 감도·거리 지원", "",
             "거리는 m, g는 rad⁻¹, slow 분산은 s² 단위다. 수용·D3 지원의 주 표이며 그룹당 30 packet, 서로 다른 10 s 블록 2개, 층 내 g_rms 비 1.2를 적용했다. 분위 경계 동률은 같은 하위 그룹에 배정했다. 전체 지원 민감도는 k1_rows.csv와 k1_strata.csv에 함께 남겼다.", ""]
    lines += md(["궤적", "거리", "감도 그룹", "n", "10 s 블록", "g_rms", "slow 평균", "slow 분산", "행 지원", "층 지원"],
                [[r["route"], distance(r["distance_bin"]), r["g_group"], r["n"], r["n_blocks"], r["g_rms"],
                  r["mean_s"], r["variance_s"], r["eligible"], r["accepted_stratum"]] for r in k1["rows"]])
    lines += ["## K1′의 지수와 기울기 기여", ""]
    lines += md(["모집단", "공통 k", "95% 하한", "95% 상한", "적격 궤적", "적격 거리 bin", "유한 bootstrap"],
                [[pop, value["slope"], *(value["ci_95"] or [None, None]), ", ".join(value["eligible_routes"]),
                  ", ".join(map(str, value["eligible_distance_bins"])), value["bootstrap_finite_replicates"]]
                 for pop, value in populations.items()])
    lines += md(["거리", "주 표의 층별 k", "전체 지원 k"],
                [[distance(int(k)), value, k1["all_d3_supported_sensitivity"]["slopes_by_distance_bin"][k]]
                 for k, value in k1["slopes_by_distance_bin"].items()])
    lines += md(["궤적", "적격 행", "개별 기술 지수", "공통 기울기 기여 비율 (%)"],
                [[r["route"], r["eligible_rows"], r["descriptive_slope"], 100*r["slope_leverage_fraction"]] for r in summary])
    r4 = next(r for r in summary if r["route"] == "R4")
    lines += [f"R4의 공통 기울기 기여는 {100*r4['slope_leverage_fraction']:.2f}%이고, R4 자체의 기술 지수는 {r4['descriptive_slope']:.3f}다. 공통 k의 상한 < 2는 R2/R5의 층 내 감도 변화가 주로 지지한다. R4만의 k < 2를 뒷받침하는 결과로 확대할 근거는 이 표에 없다. 이 비율과 개별 지수는 저장된 적격 행의 중심화 log g 제곱합·교차합으로 계산한 보조 표이며, 새 bootstrap 구간이나 arm 선택 기준을 추가하지 않았다.", "",
              f"거리만 절편으로 둔 주 표 민감도 지수는 {k1['distance_only_intercept_slope']:.6f}다. K1′는 분산 스케일링을 검사하며 signed 적재의 인과 기전과 성분 비중은 후속 재생에서 확인한다.", ""]
    lines += md(["국소 구간", "n", "블록", "g_rms", "slow 평균", "slow 분산"],
                [[label, r["n"], r["n_blocks"], r["g_rms"], r["mean_s"], r["variance_s"]]
                 for label, r in k1["local"].items()])
    lines += ["## K2의 g 하한·중심화와 donor 규모", "",
              "g_ref ≥ 1.0 rad⁻¹인 D3 지원 packet을 사용하며 gate 탈락도 포함했다. D3가 제거한 경로 잔차 평균과 지원 slow 평균을 그대로 따랐다. 주 값은 b_eq = slow_s / signed a_ref의 영점 기준 1.4826 × median(|b_eq|)이며, b_eq의 경로별 중심은 추가 제거하지 않았다. 중심화 민감도는 각 donor의 b_eq 중앙값을 제거한 뒤 donor 둘을 합친 값이다. 아래 각도는 °다.", ""]
    lines += md(["donor", "D3 지원", "g 하한 제외", "사용 n", "σ", "signed 중앙값", "중심화 MAD", "|b| p75", "|b| p95", "수용만 σ", "창 평균 분모 σ"],
                [[r["route"], r["n_d3_supported"], r["excluded_g_lt_1"], r["n"], deg(r["sigma_rad"]),
                  deg(r["signed_median_rad"]), deg(r["centered_mad_rad"]), deg(r["abs_p75_rad"]),
                  deg(r["abs_p95_rad"]), deg(r["accepted_sigma_rad"]), deg(r["window_sigma_rad"])] for r in donor_rows])
    lines += md(["holdout", "donor", "n", "LORO σ", "donor별 중심화 σ", "수용만 σ", "창 분모 σ", "거리 분기"],
                [[r["holdout"], ", ".join(r["donors"]), r["n"], r["sigma_deg"], r["centered_sigma_deg"],
                  r["accepted_sigma_deg"], r["window_sigma_deg"], r["distance_status"]] for r in fold_rows])
    lines += [f"세 궤적에 공통 지원을 갖는 감도×거리 셀은 {len(k2['main_cells']['common_cells'])}개다. 따라서 상수 규모의 궤적 간 일정성은 미결이고, LORO 상수는 진단값으로 사용한다. g cutoff가 낮은 감도 packet을 많이 제외한 영향은 위 표의 n으로 확인할 수 있다. 세 궤적 표 {len(k2_rows)}행과 fold별 donor 표 {len(donor_cells)}행을 CSV로 보관했다.", "",
              "## G1+KI 잔여 s 영역 공분산 적합", "",
              "동일 donor의 route_mean_s를 뺀 raw 잔차 쌍 공분산에서, G1의 LORO σ² a_i a_j kernel을 먼저 뺐다. 거리 bin마다 donor 동일 가중, donor 안 10 s 블록 동일 가중, 블록 안 쌍 동일 가중으로 남은 q_s를 적합했다. 0.4–5 s 쌍과 donor별 10쌍 이상인 블록 2개가 지원 조건이다. 음수 q_s는 사전 규칙에 따라 0으로 제한했다.", ""]
    lines += md(["holdout", "거리", "지원", "제한 전 q_s", "적용 q_s", "0 제한"],
                [[r["holdout"], distance(r["distance_bin"]), r["supported"], r["unconstrained_q_s"],
                  r["q_s"], r["clamped_to_zero"]] for r in hybrid_rows])
    lines += [f"지원 bin은 {sum(r['supported'] for r in hybrid_rows)}/{len(hybrid_rows)}개이고, 음수 적합의 0 제한은 {sum(r['clamped_to_zero'] for r in hybrid_rows)}개다. q_s=0인 bin에서는 G1과 결합 arm의 KI 증분이 같다. 이는 현재 signed heading 모형을 먼저 뺀 조건에서의 잔여 적합 결과이며, s 영역 상관 자체가 존재하지 않는다는 판정으로 확대하지 않는다. donor별 지원 블록·쌍 수와 적합 분자·분모는 hybrid_donor_bins.csv에서 확인할 수 있다.", "",
              "## 기록과 범위", "",
              "이 문서는 완료된 K1_PRIME_K2.json을 표로 옮기고 저장된 행의 결정적 요약만 계산했다. 원본 특성화 계약·체크·실행 영수증의 해시가 새 RUN_CONTRACT.json에 묶여 있다. 표 개수와 공통 지수 재구성을 CHECKS.json에 기록하고 출력 해시는 EXECUTION.json에 남겼다. 다른 RF·장면이나 seed 재생의 일반화는 이 표의 평가 범위에 포함되지 않는다.", ""]
    report = OUT / "REPORT_KO.md"
    with report.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
    write_json(OUT / "CHECKS.json", dict(status="PASS", expected=lock["expected_counts"], actual=counts,
                                         common_slope_reproduction_abs_error=abs(reproduced-k1["slope"]),
                                         input_sha256_verified=True, no_new_resampling=True, no_new_replays=True))
    outputs = [item(path) for path in sorted(OUT.iterdir()) if path.name != "EXECUTION.json"]
    write_json(OUT / "EXECUTION.json", dict(completed_utc=utc(), command=sys.argv, exit_code=0,
                                            contract_sha256=item(OUT / "RUN_CONTRACT.json")["sha256"], outputs=outputs))
    print(json.dumps(dict(status="PASS", report=str(report), rows=counts), ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "run"))
    args = parser.parse_args()
    {"freeze": freeze, "run": run}[args.command]()
