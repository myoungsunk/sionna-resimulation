"""Render the S2′ primary and common-case evidence after execution."""
import csv
import json
from pathlib import Path
import sys

run = Path(sys.argv[1])
out = run / "s2_out"
verdict = json.loads((out / "S2P_VERDICT.json").read_text())
b0 = json.loads((out / "B0_COMPARISON.json").read_text())
snap = json.loads((out / "S2P_G_SNAP.json").read_text())
names = {"independent": "독립", "markov": "Markov", "cell": "셀 재사용"}
pct = lambda x: "{:.2%}".format(x)
metrics = {
    "nees": "평균 NEES", "coverage": "누적 포함률", "endpoint_coverage": "끝점 포함률",
    "ratio": "누적 RMSE 비율", "ci_upper": "95% CI 상한", "rmse": "절대 RMSE",
    "all_routes": "route별 DR-cal 대비 개선", "gate_rejection": "gate 기각률",
}
lines = [
    "# G1-MODEL-001 S2′ 1차 계산", "",
    "**§8 판정 `{}` · `{}`{}**".format(verdict["verdict"], verdict["coverage"],
        " · `{}`".format(verdict["correlation"]) if verdict["correlation"] else ""),
    "",
    "v3.4 사양의 N30, mount 0, 19점·90°, M1-R(J_joint) × E1, XY-AR(1), 인과적 탐색창과 gate, "
    "E₀ = 0을 적용했다. DR은 r1.3.1의 σ_w = 0.486°와 σ_β = 0.45°/station을 사용했다.",
    "",
    "6개 case에 90° station 122개를 사용했다. 동결 사양 §5.5의 합계 표기 142를 산술 정정해 "
    "입력의 case별 실측 개수는 {}다. 같은 route의 A/B는 물리 station을 묶어 재추출했다. "
    "명목 200경로를 평가하고, station bootstrap 1,000회마다 공통 난수 200경로를 사용했다.".format(
        ", ".join("{} {}".format(n, v) for n, v in verdict["physical_stations"].items())),
    "격자 RF 실현은 M1-R 2,440개와 M0 2,020개다.",
    "",
    "## Station 1–17", "",
    "| RF 모델 | G1 RMSE | DR-cal RMSE | RMSE 비율 [95% CI] | 평균 NEES | 누적 포함률 | "
    "17 끝점 포함률 | gate 기각률 | 17 끝점 RMSE | 창 누락률 | 연속 창 누락 최대 |",
    "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
]
for model, name in names.items():
    r = verdict["models"][model]
    lines.append(
        "| {} | {:.3f}° | {:.3f}° | {:.3f} [{:.3f}, {:.3f}] | {:.3f} | {} | {} | {} | "
        "{:.3f}° | {} | {} |".format(name, r["rmse_g1_1_to_17"], r["rmse_dr_cal_1_to_17"],
        r["ratio_1_to_17"], *r["ratio_ci_95_1_to_17"], r["nees_1_to_17"], pct(r["coverage_1_to_17"]),
        pct(r["coverage_at_17"]), pct(r["gate_reject_1_to_17"]), r["rmse_g1_at_17"],
        pct(r["window_miss_1_to_17"]), r["longest_window_miss_1_to_17"]))
lines.extend(["", "| RF 모델 | R2 비율 | R4 비율 | R5 비율 | 무결성 미달 | 정확도 미달 |",
              "|---|---:|---:|---:|---|---|"])
for model, name in names.items():
    r = verdict["models"][model]
    fail = [" · ".join(metrics[k] for k in r[key]) or "없음"
            for key in ("integrity_misses", "accuracy_misses")]
    lines.append("| {} | {:.3f} | {:.3f} | {:.3f} | {} | {} |".format(
        name, *(r["routes"][k] for k in ("R2", "R4", "R5")), *fail))
diagnostic = json.loads((out / "MARKOV_COVERAGE_DIAGNOSTIC.json").read_text())
r4 = diagnostic["case"]["R4_aB_m0"]
d_ind, d_markov = r4["independent"], r4["markov"]
lines.extend([
    "", "## Markov 누적 포함률 미달", "",
    "R4_aB_m0에서 독립 대비 Markov 포함률이 {}에서 {}로 내려갔다. 이 case의 미포함은 {}건 늘었고 "
    "6개 case 합계는 170건 늘었다. R4_aB_m0의 RMSE는 {:.3f}°에서 {:.3f}°로 늘었지만, "
    "평균 95% 구간 반폭은 {:.3f}°에서 {:.3f}°로 거의 같았다. "
    "Markov 전체의 창 누락은 {}건이었고 gate 기각은 {}건이었다. "
    "R4_aB_m0의 ρ는 0이고 Markov는 같은 lane의 다음 station을 순서대로 방문한다. "
    "관측 순서에서 오차가 커진 경로에 대해 필터 구간이 좁게 유지됐다.".format(
        pct(d_ind["coverage"]), pct(d_markov["coverage"]), d_markov["misses"] - d_ind["misses"],
        d_ind["rmse_deg"], d_markov["rmse_deg"], d_ind["mean_interval_halfwidth_deg"],
        d_markov["mean_interval_halfwidth_deg"], diagnostic["markov_window_miss"], diagnostic["markov_gate_reject"]),
    "", "## 5개 공통 case 짝 비교", "",
    "M0 parity에서 제외된 R2_aB_m0을 뺀 {}경로에 같은 DR, XY, RF 행을 사용했다. "
    "신뢰구간은 §8 1차 비교에 적용했다.".format(b0["paired_paths"]), "",
    "| RF 모델 | B0 M0 × E0 비율 | M1-R × E1 비율 | B0 포함률 | M1-R × E1 포함률 |",
    "|---|---:|---:|---:|---:|",
])
for model, name in names.items():
    pair = b0["models"][model]
    a, b = pair["M0_E0"], pair["M1_R_E1"]
    lines.append("| {} | {:.3f} | {:.3f} | {} | {} |".format(
        name, a["ratio_1_to_17"], b["ratio_1_to_17"], pct(a["coverage_1_to_17"]), pct(b["coverage_1_to_17"])))
sens = out / "S2P_SIGMA_BETA_STAR.csv"
if sens.is_file():
    sensitivity = json.loads((out / "S2P_SIGMA_BETA.json").read_text())
    lines.extend(["", "## DR 잔여 편향 민감도", "",
                  "M1-R(J_joint) × E1의 명목 경로에서 σ_β를 바꿨다. "
                  "RMSE 비율 0.8 교차점은 계산된 격자에서 구간을 확인해 선형 보간했다.", "",
                  "| RF 모델 | σ_β* (°/station) | 탐색 또는 교차 구간 |",
                  "|---|---:|---|"])
    with sens.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            value = "{:.3f}".format(float(r["root_deg_per_station"])) if r["root_deg_per_station"] else r["status"]
            lines.append("| {} | {} | [{}, {}] |".format(
                names[r["model"]], value, r["bracket_lo"], r["bracket_hi"]))
    lines.extend(["", "| RF 모델 | σ_β = 0 비율 | σ_β = 0.32 비율 | σ_β = 0.93 비율 |",
                  "|---|---:|---:|---:|"])
    for model, name in names.items():
        m = sensitivity["models"][model]["metrics"]
        lines.append("| {} | {:.3f} | {:.3f} | {:.3f} |".format(
            name, *(m[s]["ratio_1_to_17"] for s in ("0.0", "0.32", "0.93"))))
lines.extend([
    "", "## 검증 및 적용 범위", "",
    "- R0, G-OBS-1/2와 G-E2E′ 결과를 동결 입력 및 산출물 해시로 확인했다. G-SNAP 축별 RMS는 "
    "{:.4f} m와 {:.4f} m이고 격자 밖 직접 계산 비율은 {}였다.".format(
        *snap["all_station_quantization"]["axis_rms_m"], pct(snap["direct_station_rate"])),
    "- 격자점·반올림 경계·격자 밖 좌표에서 기준 J 조회와 bit 일치를 확인했다. "
    "배치와 단일 반복의 필터 출력도 bit 일치했다.",
    "- `S2P_CURVES.csv`의 초기 5° DR-only 및 DR-nosweep 결정론적 드리프트 행은 참고값이다. "
    "A1과 A2′는 별도 평가가 필요하다.",
    "- 이번 범위는 A2 1차 판정, B0 짝 비교 및 1차 arm의 DR 잔여 편향 민감도다. "
    "E2–E4와 M1-RI는 보정 또는 갱신 규칙의 명시가 필요하다. J_diag와 기타 민감도 arm, Step 3는 미실행이다.",
    "- 보정의 첫 실행은 R5 보정 JSON의 중첩 구조를 읽는 단계에서 종료했다. "
    "동일한 동결 보정값을 읽도록 수정하고 보정을 완료한 뒤 1차 계산을 시작했다.",
    "",
    "사양 커밋 `{}` · 진입 검사 `{}` · 본 계산 `{}`".format(
        verdict["spec_commit"], verdict["gate_run"], run.name),
])
with (out / "REPORT_KO.md").open("x", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

