"""Render saved M6 passage, variogram, and local diagnostics without replays."""

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "diagnostics_tables" / "attempt_02"
CHAR = ROOT / "characterization"
RESULTS = ROOT / "attempt_02/results"
MAIN_ARMS = ("BASE", "G1_LORO", "G1_KI")


def utc():
    return datetime.now(timezone.utc).isoformat()


def record(path):
    return dict(path=str(path.resolve()), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def verify_receipt(directory):
    receipt = read(directory / "EXECUTION.json")
    if receipt["exit_code"] != 0 or receipt["status"] != "PASS_EXECUTION":
        raise ValueError(f"Source execution incomplete: {directory}")
    if receipt["contract_sha256"] != record(directory / "RUN_CONTRACT.json")["sha256"]:
        raise ValueError("Source contract hash differs")
    for name, sha in receipt["outputs"].items():
        if record(directory / name)["sha256"] != sha:
            raise ValueError(f"Source result hash differs: {name}")


def freeze():
    for directory in (CHAR, RESULTS):
        verify_receipt(directory)
    paths = [CHAR / name for name in ("K4_BASELINE.json", "K5.json", "RUN_CONTRACT.json", "EXECUTION.json")]
    paths += [RESULTS / name for name in ("K4.json", "K3.json", "R2_LOCAL.json", "RUN_CONTRACT.json", "EXECUTION.json")]
    paths += [ROOT / "diagnostics.py"]
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "RUN_CONTRACT.json", dict(
        question_id="G1-INT-001/M6", stage="diagnostic tabulation", role="IMPLEMENTER",
        frozen_utc=utc(), classification="DIAGNOSTIC_ONLY", sources=[record(Path(__file__))],
        inputs=[record(path) for path in paths], new_replays=False, new_resampling=False,
        supersedes={"path": str(OUT.parent), "reason": "Correct signed warning_y_z column label"},
        expected_counts=dict(k4_passages=63, k4_main_seed_summary=15, k5_passages=10,
                             k5_paired_intervals=30, k3_semivariance=66, r2_local=15)))


def flatten_passage(seed, arm, window, passage):
    row = {"seed": int(seed), "arm": "G0" if arm == "BASE" else arm,
           "crossing_s": window["crossing_s"], "packets": window["packets"],
           "accepted": window["accepted"], "accepted_fraction": window["accepted_fraction"]}
    channel_fields = ("J_yy", "J_psipsi", "J_ypsi", "y_update_sum_m", "y_update_abs_sum_m",
                      "psi_update_sum_rad", "psi_update_abs_sum_rad")
    for key in channel_fields:
        values = window[key]
        if len(values) != 2:
            raise ValueError("Expected range then conditional-polarization channels")
        row.update({f"{key}_{label}": value for label, value in zip(("range", "pol"), values, strict=True)})
    for key in ("mean_Pyy", "mean_Pypsi", "first_opposite_s", "first_update_increasing_abs_y_error_s",
                "increase_precedes_opposite", "window_y_rmse_m", "window_heading_rmse_deg"):
        row[key] = window[key]
    for key in ("MIRROR_FAIL", "PRE_PASS_OVERCONFIDENT", "longest_mirror_duration_s", "warning_y_z"):
        row[key] = passage[key]
    return row


def csv_table(name, rows):
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (OUT / (name + ".csv")).open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value):
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "예" if value else "아니오"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value).replace("|", "\\|")


def md(headers, rows):
    return ["| " + " | ".join(map(fmt, headers)) + " |", "|" + "---|" * len(headers)] + [
        "| " + " | ".join(map(fmt, row)) + " |" for row in rows] + [""]


def run():
    lock = read(OUT / "RUN_CONTRACT.json")
    for item in lock["inputs"] + lock["sources"]:
        if record(Path(item["path"]))["sha256"] != item["sha256"]:
            raise ValueError("Frozen tabulation input differs")
    for directory in (CHAR, RESULTS):
        verify_receipt(directory)
    k4, k3, local = (read(RESULTS / name) for name in ("K4.json", "K3.json", "R2_LOCAL.json"))
    baseline = read(CHAR / "K4_BASELINE.json")
    if k4["10"]["BASE"] != baseline:
        raise ValueError("Seed 10 K4 baseline differs from characterization")
    k4_rows = []
    for seed, arms in k4.items():
        for arm, value in arms.items():
            for window, passage in zip(value["windows"], value["passages"], strict=True):
                if window["crossing_s"] != passage["time_s"]:
                    raise ValueError("Passage and window grids differ")
                k4_rows.append(flatten_passage(seed, arm, window, passage))
    summaries = []
    summed_keys = [k for k in k4_rows[0] if k.startswith(("J_", "y_update", "psi_update"))]
    for seed in range(10, 15):
        for arm in ("G0", "G1_LORO", "G1_KI"):
            rows = [r for r in k4_rows if r["seed"] == seed and r["arm"] == arm]
            if len(rows) != 3:
                raise ValueError("Expected all three R5 passages")
            summaries.append(dict(seed=seed, arm=arm, passages=len(rows),
                                  MIRROR_FAIL=sum(r["MIRROR_FAIL"] for r in rows),
                                  PRE_PASS_OVERCONFIDENT=sum(r["PRE_PASS_OVERCONFIDENT"] for r in rows),
                                  **{k: sum(r[k] for r in rows) for k in summed_keys}))
    k5 = read(CHAR / "K5.json")
    k5_rows, intervals = [], []
    for route, passages in k5.items():
        for comparison in passages:
            bootstrap = comparison["reference_only_window_bootstrap"]
            if bootstrap["reference_only"] is not True:
                raise ValueError("Expected local bootstrap reference-only marker")
            for arm in ("A0", "A2_2"):
                entry = comparison[arm]
                row = flatten_passage(10, arm, entry["window"], entry["passage"])
                row.update(route=route, truth_y_at_crossing_m=comparison["truth_y_at_crossing_m"],
                           sd_y_5s_before_m=entry["sd_y_5s_before_m"])
                k5_rows.append(row)
            for metric, bounds in bootstrap["paired_ci95"]["A2_2-A0"].items():
                intervals.append(dict(route=route, crossing_s=comparison["crossing_s"], contrast="A2_2-A0",
                                      metric=metric, lower_95=bounds[0], upper_95=bounds[1], reference_only=True))
    variograms = [dict(route=route, coordinate=coordinate, lower_bound=r["bounds"][0],
                       upper_bound=r["bounds"][1], pairs=r["pairs"], empirical_s2=r["empirical_s2"],
                       frozen_unit_sill=r["frozen_unit_sill"])
                  for route, groups in k3.items() for coordinate, rows in groups.items() for r in rows]
    local_rows = [dict(seed=int(seed), arm="G0" if arm == "BASE" else arm,
                       **value["all_packet_scores"], y_rmse_cm=value["y_rmse_cm"],
                       count=value["count"], q_nonzero_accepted=value["q_nonzero_accepted"])
                  for seed, arms in local.items() for arm, value in arms.items()]
    tables = dict(k4_passages=k4_rows, k4_main_seed_summary=summaries, k5_passages=k5_rows,
                  k5_paired_intervals=intervals, k3_semivariance=variograms, r2_local=local_rows)
    counts = {key: len(rows) for key, rows in tables.items()}
    if counts != lock["expected_counts"]:
        raise ValueError(f"Unexpected diagnostic table rows: {counts}")
    for name, rows in tables.items():
        csv_table(name, rows)
    main = [r for r in k4_rows if r["seed"] == 10 and r["arm"] in ("G0", "G1_LORO", "G1_KI")]
    lines = ["# M6 K4·K5·K3와 R2 국소 진단 표", "",
             "mount 0°, 앵커 B, B0의 완료된 특성화와 M6 재생 결과를 표로 정리했다. 원본 JSON·계약·성공 영수증과 이 실행 코드의 SHA-256을 새 RUN_CONTRACT.json에 묶었다.", "",
             "## K4 R5 앵커 통과별 정보와 실제 갱신", "",
             "각 통과 ±10 s 창이다. 채널 순서는 거리, 거리 조건부 편파다. 명목 J=HᵀR⁻¹H는 수용 packet 합이다. y–ψ 교차항의 부호를 유지했다. 전체 augmented H와 실제 gain을 쓰며, 직접 편미분 J_yy만으로 bias 주변화 후 y 정보를 판정할 수 없다. G0는 원본 JSON의 BASE다.", ""]
    lines += md(["arm", "통과 s", "수용/전체", "Jyy 거리", "Jyy 편파", "Jψψ 편파", "Jyψ 편파"],
                [[r["arm"], r["crossing_s"], f"{r['accepted']}/{r['packets']}", r["J_yy_range"],
                  r["J_yy_pol"], r["J_psipsi_pol"], r["J_ypsi_pol"]] for r in main])
    lines += ["실제 갱신량은 |Kν|의 채널별 합이다. y는 m, ψ는 rad로 표시했다. y RMSE는 통과 창의 값이고 MIRROR_FAIL은 해당 통과의 동결 지속시간 규칙이다. 첫 반대 부호 시점은 별도 순간 진단이다.", ""]
    lines += md(["arm", "통과 s", "Σ|Kν| y 거리", "Σ|Kν| y 편파", "Σ|Kν| ψ 거리", "Σ|Kν| ψ 편파", "y RMSE m", "평균 Pyy", "MIRROR_FAIL"],
                [[r["arm"], r["crossing_s"], r["y_update_abs_sum_m_range"], r["y_update_abs_sum_m_pol"],
                  r["psi_update_abs_sum_rad_range"], r["psi_update_abs_sum_rad_pol"], r["window_y_rmse_m"],
                  r["mean_Pyy"], r["MIRROR_FAIL"]] for r in main])
    lines += ["## K4의 seed별 세 통과 합", "",
              "세 통과 창의 명목 정보·절대 갱신량을 seed별로 합했다. 같은 RF 실현의 wheel·gyro 잡음 민감도이며, 독립 RF 반복의 구간으로 해석할 근거는 이 표에 없다.", ""]
    lines += md(["seed", "arm", "Jyy 편파", "Jψψ 편파", "Jyψ 편파", "Σ|Kν| y 편파", "Σ|Kν| ψ 편파", "mirror", "과신 경고"],
                [[r["seed"], r["arm"], r["J_yy_pol"], r["J_psipsi_pol"], r["J_ypsi_pol"],
                  r["y_update_abs_sum_m_pol"], r["psi_update_abs_sum_rad_pol"], r["MIRROR_FAIL"],
                  r["PRE_PASS_OVERCONFIDENT"]] for r in summaries])
    lines += ["## K5 R2/R5 앵커 통과 대조", "",
              "M5의 A0와 A2 2° 보관 trace에서 계산된 통과 ±10 s 비교다. 아래 σ_y는 통과 5 s 전이다. 거울 지속시간은 통과 뒤 동결 관찰 구간의 최장값이다. 국소 시간 순서와 부호는 기전 검토를 위한 관찰값이다.", ""]
    lines += md(["궤적", "arm", "통과 s", "참 y m", "5 s 전 σ_y m", "5 s 전 signed z_y", "창 y RMSE m", "창 ψ RMSE °", "최장 mirror s"],
                [[r["route"], r["arm"], r["crossing_s"], r["truth_y_at_crossing_m"], r["sd_y_5s_before_m"],
                  r["warning_y_z"], r["window_y_rmse_m"], r["window_heading_rmse_deg"],
                  r["longest_mirror_duration_s"]] for r in k5_rows])
    lines += ["기존 10 s 블록 짝 차이 구간은 reference_only로 표시돼 있다. 약 20 s 길이의 통과 창은 독립 블록이 적으므로 이 구간을 정식 통과 판정이나 인과 검증에 사용하지 않는다. 아래 값은 A2_2−A0이고, 포함률 차이는 원본 비율 단위다. 모든 지표는 k5_paired_intervals.csv에 보관했다.", ""]
    lines += md(["궤적", "통과 s", "지표", "95% 하한", "95% 상한", "reference_only"],
                [[r["route"], r["crossing_s"], r["metric"], r["lower_95"], r["upper_95"], r["reference_only"]]
                 for r in intervals if r["metric"] in ("heading_rmse_deg", "xy_rmse_cm", "heading95_coverage")])
    lines += ["## R2 120–140 s 국소 구간", "",
              "시각은 첫 packet 기준 경과시간이다. 전체 101 packet에서 계산한 점수를 그대로 표시했다. q_nonzero는 해당 구간에서 KI q가 양수인 수용 packet 수다. 포함률은 %다. 이 표는 사전 지정 국소 구간의 기술 통계다.", ""]
    lines += md(["seed", "arm", "Pose95 %", "Heading95 %", "XY95 %", "NEES3", "ψ RMSE °", "XY RMSE cm", "y RMSE cm", "q_nonzero"],
                [[r["seed"], r["arm"], 100*r["pose95_coverage"], 100*r["heading95_coverage"], 100*r["xy95_coverage"],
                  r["mean_nees3"], r["heading_rmse_deg"], r["xy_rmse_cm"], r["y_rmse_cm"],
                  r["q_nonzero_accepted"]] for r in local_rows])
    lines += ["## K3 후순위 variogram", "",
              "수용 packet 쌍의 원래 편파 잔차로 0.5(e_j−e_i)²를 계산한 보관 결과다. 누적 arc·누적 yaw·시간의 각 [하한, 상한) 구간을 사용했다. empirical_s2는 s² 단위이고 frozen_unit_sill은 1−exp(−Δarc/1 m−Δyaw/10°)의 무차원 쌍 평균이다. 두 열의 절대 크기를 같은 분산 단위로 대조하려면 sill 규모가 필요하다. 이 후순위 표로 길이나 구조를 다시 선택하지 않았다.", ""]
    lines += md(["궤적", "좌표", "하한", "상한", "쌍 수", "경험 반분산 s²", "동결 단위 sill"],
                [[r["route"], r["coordinate"], r["lower_bound"], r["upper_bound"], r["pairs"],
                  r["empirical_s2"], r["frozen_unit_sill"]] for r in variograms])
    lines += ["모든 후보·seed의 63개 K4 통과 행은 k4_passages.csv에 저장했다. 이 표 문서 생성은 완료된 결과의 집계·표시만 수행했다. 실행·구현·무결성·정확도·채택 판정은 M6 전체 결과 보고서와 연결해 해석한다.", ""]
    width = None
    for line in lines:
        if not line.startswith("|"):
            width = None
            continue
        n = line.replace("\\|", "").count("|")
        if width is None:
            width = n
        if width != n:
            raise ValueError("Inconsistent Markdown table width")
    with (OUT / "REPORT_KO.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines))
    write(OUT / "CHECKS.json", dict(status="PASS", expected=lock["expected_counts"], actual=counts,
                                     source_receipts_verified=True, seed10_baseline_equal=True,
                                     markdown_table_widths=True, new_replays=False, new_resampling=False))
    outputs = [record(p) for p in sorted(OUT.iterdir()) if p.name != "EXECUTION.json"]
    write(OUT / "EXECUTION.json", dict(status="PASS_EXECUTION", exit_code=0, command=sys.argv,
                                        completed_utc=utc(), contract_sha256=record(OUT / "RUN_CONTRACT.json")["sha256"],
                                        outputs=outputs))
    print(json.dumps(dict(status="PASS", rows=counts, report=str(OUT / "REPORT_KO.md"))))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("freeze", "run"))
    args = parser.parse_args()
    {"freeze": freeze, "run": run}[args.command]()
