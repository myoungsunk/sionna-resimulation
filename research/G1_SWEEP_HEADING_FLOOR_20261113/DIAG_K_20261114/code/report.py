"""Render the G1-DIAG-002 report and manifest from recorded artifacts."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
out = root / "out"
records = root / "records"
spec = "2068954c07770cffee1a8745e53e0383c5ef8c96"
baseline = "d7a35296b287fe46d9da0741c950bdfd51bcf14e"
q1_blob = "db19ca2d71a7f5f4d7eb8df9d6a0d4ea5274bccd"
run = root.name
url = "https://github.com/myoungsunk/sionna-resimulation/blob/" + spec + "/research/G1_SWEEP_HEADING_FLOOR_20261113/DIAG_K_20261114/SPEC_KO.md"
diagnostics = {
    0: "K0_REPRODUCTION.json", 1: "K1_CASE_ARM.json", 2: "K2_REVISIT_SPLIT.json",
    3: "K3_NR.json", 4: "K4_ORACLE_SCALE.json", 5: "K5_ORACLE_BIAS.json",
    6: "K6_INTERACTION.json", 7: "K7_LOS_ATTRIBUTION.json", 8: "K8_TAP_CONTAMINATION.json",
}

def read(p):
    return json.loads(p.read_text(encoding="utf-8"))

def sha(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for x in iter(lambda: f.read(1024 * 1024), b""):
            h.update(x)
    return h.hexdigest()

def pct(x):
    return f"{100*x:.2f}%"

def both(r):
    if "coverage" not in r:
        return "미적용"
    mark = "통과" if r["case_integrity_pass"] else "미통과"
    return f'{pct(r["coverage"])} / {r["nees"]:.2f} ({mark})'

phases = ["k0", "k1_k2", "k7_k8", "k3_k6"]
run_info = {}
for p in phases:
    run_info[p] = {"start_utc": (records / f"START_{p}.txt").read_text().strip(),
                   "finish_utc": (records / f"FINISH_{p}.txt").read_text().strip(),
                   "exit": int((records / f"EXIT_{p}.txt").read_text()),
                   "command": (records / f"COMMAND_{p}.txt").read_text().strip()}
assert all(v["exit"] == 0 for v in run_info.values())
assert all(run_info[a]["finish_utc"] <= run_info[b]["start_utc"] for a,b in zip(phases, phases[1:]))
d = {i: read(out / name) for i, name in diagnostics.items()}
assert d[0]["status"] == "PASS" and all(d[0]["draws_exact"].values())
assert all(all(m["array_equal_all_50_visits"].values()) for m in d[0]["models"].values())
assert sha(out / "K0_NOMINAL.npz") == d[0]["reproduced_npz_sha256"]
names = list(d[0]["models"]["cell"]["cases"])
assert len(names) == 6
assert list(d[7]["cases"]) == names == list(d[8]["cases"])
assert d[7]["provenance"]["q1_rows_checked"] == 2440
assert all(d[7]["cases"][name]["n_paired_stations"] == d[8]["cases"][name]["n_common_stations"]
           for name in names)
assert sum(d[7]["cases"][name]["n_paired_stations"] for name in names) == 122
assert sum(d[7]["cases"][name]["n_paired_sweeps"] for name in names) == 2440
for i in (3,4,5,6):
    assert d[i]["classification"] == "DIAGNOSTIC_ONLY"
    assert all(list(arm) == names for arm in d[i]["arms"].values())

r4 = "R4_aB_m0"
v7 = d[7]["cases"][r4]
v8 = d[8]["cases"][r4]
sp = v8["spearman_common_station_sample"]
markers = ["independent","markov","cell"]
lines = [
    "DIAGNOSTIC_ONLY — S2′ 판정 STOP", "",
    "# G1-DIAG-002 BLOCK_C 진단 결과", "",
    f"- 실행 ID `{run}`. [실행 전 개정 사양]({url})",
    "- 실행 순서 K0 → K1/K2 → K7/K8 → K3–K6. K0 통과 후 후속 단계 실행.",
    "- 대상은 BLOCK_C mount 0의 6 case, 122개 물리 station이다. 지표는 현재 데이터와 oracle 개입에 한정한다.",
    "- K9/K10 및 Step 3 보류. 수치를 다음 모델의 파라미터로 이전하는 작업은 보류한다.", "",
    "## K0 재현", "",
    "동결 코드로 200개 경로의 50방문 nominal을 재실행했다. 난수·경로 배열, 8개 결과 배열, case RMSE와 평균 구간 반폭이 일치했다. 미포함 수는 방문 1–17 기준이다.", "",
    "| case | 독립 | Markov | 셀 |", "|---|---:|---:|---:|",
]
for name in names:
    vals = [d[0]["models"][m]["cases"][name]["live"]["misses"] for m in markers]
    lines.append(f"| {name} | {vals[0]} | {vals[1]} | {vals[2]} |")
totals = [d[0]["models"][m]["total_misses"] for m in markers]
lines.append(f"| **합계** | **{totals[0]}** | **{totals[1]}** | **{totals[2]}** |")
lines.extend(["", "## K1/K2 case 및 재방문 분해", "",
    "| R4_aB arm | 1–17 포함률 | NEES | 고유 station 중앙값 | 첫 방문 | 두 번째 | 세 번째 이상 |",
    "|---|---:|---:|---:|---:|---:|---:|"])
for m in markers:
    c1 = d[1]["models"][m][r4]
    c2 = d[2]["models"][m][r4]
    cuts = [pct(c2[k]["coverage"]) for k in ("first","second","third_or_later")]
    lines.append(f"| {m} | {pct(c1['coverage'])} | {c1['mean_nees']:.2f} | {c1['distinct_stations_q25_median_q75'][1]:g} | {' | '.join(cuts)} |")
lines.extend(["", f"셀 전체 미포함 중 R4_aB 몫은 {pct(d[1]['cell_r4_aB_miss_fraction'])}이다.",
    "", "## K7/K8 관측 진단", "",
    "| case | 짝 station | full RMS (°) | LoS RMS (°) | V_model | tap 전환 |",
    "|---|---:|---:|---:|---:|---:|"])
for name in names:
    a = d[7]["cases"][name]
    b = d[8]["cases"][name]
    af, al = [a["paired_station_error_means"][c]["rms"] for c in ("e_full","e_los")]
    lines.append(f"| {name} | {a['n_paired_stations']} | {af:.3f} | {al:.3f} | {a['V_model']:.6f} | {b['n_common_yaw_tap_switches']}/{b['n_common_yaws']} |")
means = v7["paired_station_error_means"]
lines.extend(["",
    f"- R4_aB의 LoS 평균 편향은 {means['e_los']['mean']:+.3f}°, full–LoS 차이 RMS는 {means['e_mp']['rms']:.3f}°, station 짝 공분산은 {v7['cov_los_mp']:+.3f}°²다. 2,440개 full 관측을 Q1과 재대조했고 모든 sweep 쌍이 유효했다.",
    f"- R4_aB의 오염도와 |오차| Spearman은 {sp['abs_e_full_q1_vs_max_c']:+.3f}, 오염도와 √R_E1은 {sp['sqrt_r_full_q1_vs_max_c']:+.3f}다. §4의 동시 기준 중 √R_E1 쪽(≤0.2)을 충족하지 않았다.",
    f"- |오차|와 |Δs|의 Spearman은 고정 tap {sp['abs_e_full_q1_vs_max_abs_delta_s_fixed']:+.3f}, 각 채널 검출 tap {sp['abs_e_full_q1_vs_max_abs_delta_s_adaptive']:+.3f}이다. 전 case 2,318 yaw 중 {d[8]['pooled']['n_common_yaw_tap_switches']}개에서 검출 tap이 달라졌다.",
    "- 모든 station의 천장 영상 경로가 기하상 한 tap 간격 이내다. standoff 관측 범위가 단일 값이라 천장 대조는 추정 불가다.",
    "", "## K3–K6 10방문 필터 대비", "",
    "각 칸은 누적 포함률 / 평균 NEES다. §4 case 통과 기준은 포함률 ≥88%, NEES 0.5–2.0이다.", "",
    "| case | Markov 동결 | NR-rand 동결 | Markov 스케일 | NR-rand 스케일 | Markov 편향 | K6-OB | K6-SKIP |",
    "|---|---|---|---|---|---|---|---|"])
for n in names:
    arms = [d[3]["arms"]["markov"][n], d[3]["arms"]["nr_rand"][n], d[4]["arms"]["markov"][n],
            d[4]["arms"]["nr_rand"][n], d[5]["arms"]["markov"][n], d[6]["arms"]["K6-OB"][n],
            d[6]["arms"]["K6-SKIP"][n]]
    lines.append("| " + " | ".join([n, *[both(a) for a in arms]]) + " |")
contrast = d[6]["paired_contrasts"][r4]
delta = 100*contrast["skip_minus_ob"]["coverage"]
lo, hi = [100*x for x in contrast["skip_minus_ob_station_cluster_ci95"]["coverage"]]
kappa = {p["case"]: p["kappa"] for p in d[4]["oracle_parameters"]}
lines.extend(["",
    f"- R4_aB의 κ는 {kappa[r4]:.4f}. Q1의 station 평균 오차를 평균 표준편차로 나눈 뒤 제곱하여 station 간 평균했다. Markov AR 분산과 초기 공분산은 동결했다.",
    f"- R4_aB에서 K6-SKIP−OB 포함률은 {delta:+.2f}%p, station-cluster 95% CI [{lo:+.2f}, {hi:+.2f}]%p다. 두 arm의 RF 경로와 oracle 설정을 맞췄다.",
    "- NR-seq는 차선 내 길이 10 창이 있는 case에서만 계산했다. NR-rand·NR-seq의 구간은 고정 station 집합을 조건으로 한 경로 구간이다. 무재방문 arm의 station-cluster CI는 산출하지 않았다.", "",
    "## 사양 §4 항목 대조", "",
    "| 조건 | 결과 |", "|---|---|"])
def all_case(arm):
    return all(arm[n]["case_integrity_pass"] for n in names)
nr = d[3]["arms"]["nr_rand"]
a6 = d[6]["arms"]
k6_fail = [n for n in names if not a6["K6-SKIP"][n]["case_integrity_pass"]]
cond_k3 = (all(nr[n]["case_integrity_pass"] for n in names if n != r4) and not nr[r4]["case_integrity_pass"])
cond_a6 = all_case(a6["K6-10"])
cond_orig_k6 = not cond_a6 and not k6_fail
cond_paired_k6 = not all_case(a6["K6-OB"]) and not k6_fail
rows = [
    ("K7 V_model ≥0.5", "해당" if v7["V_model"] >= .5 else "미해당"),
    ("K7 V_model ≤0.2", f"{v7['V_model']:.6f}. 해당. 동일 잡음 LoS 대체에서 오차가 크게 줄어 multipath가 이 조건의 주 원인이라는 해석을 지지한다."),
    ("K7 0.2 < V_model < 0.5", "해당" if .2 < v7["V_model"] < .5 else "미해당"),
    ("K8 상관 두 조건", "미충족. √R_E1 상관이 0.2를 넘는다."),
    ("K8 천장 대조", "추정 불가. 비교 집단이 비어 있다."),
    ("K3 NR-rand에서 R4_aB만 미통과", ("해당" if cond_k3 else "미해당") + ". 매칭한 K4의 분산 개입과 함께 검토한다."),
    ("K6-10 6 case 통과", "해당" if cond_a6 else "미해당"),
    ("K6-10 미통과, K6-SKIP 통과", ("해당" if cond_orig_k6 else "미해당") + ". 이 대비에서는 편향 보정도 함께 바뀐다."),
    ("K6-OB 미통과, K6-SKIP 통과", ("해당" if cond_paired_k6 else "미해당") + ". 같은 oracle 설정의 재방문 갱신 생략 대비다."),
    ("K6-SKIP 미통과", f"{', '.join(k6_fail)}. 잔여 기전 검토가 필요하다." if k6_fail else "미해당"),
    ("K9 두 교차점 조건", "실행 범위 밖"),
    ("K10 수렴 station 수", "실행 범위 밖"),
]
lines.extend(f"| {key} | {value} |" for key,value in rows)
lines.extend(["", "## 재현 기록", "",
    "- [실행 범위와 구현 선택](EXECUTION_RECORD_KO.md), [입출력 SHA 및 실행 명령](MANIFEST.json).",
    "- K1/K2 첫 시도의 seed 개수 처리 오류를 고친 뒤 재집계했다. 최초 로그는 records/attempts 아래 보존했다.",
    "- 참값 및 LoS 참조를 사용한 결과는 운용 중 heading 성능과 별개다."])

manifest = dict(question_id="G1-DIAG-002", classification="DIAGNOSTIC_ONLY",
                role="IMPLEMENTER", run_id=run, remote_root=f"/home/KMS/{run}",
                repository="myoungsunk/sionna-resimulation",
                branch="research/g1-sweep-heading-floor-spec-20261113",
                spec_commit=spec, baseline_commit=baseline,
                spec_git_blob="49f624e10fcad0b60f7439c7bcf298ec609d3e8a",
                q1_commit="42fe9c7", q1_csv_git_blob=q1_blob,
                q1_csv_sha256="ede1a041dc275a57ca49751257d5c264f861a147e58b42166e0d737902111c3e",
                block_c_commit="047cce2", lut_commit="f9a7691",
                seed=dict(s2_path=2026111303,s2_xy=2026111322,s2_bootstrap=20261113,
                          q1_xy=2026111336,nr=2026111401),
                governance_sha256=d[0]["governance_sha256"],
                frozen_source_manifest_sha256=d[0]["source_manifest_sha256"],
                python=d[0]["python"], numpy=d[0]["numpy"],
                stages=run_info, s2_prime_verdict="STOP", step3="HELD",
                case_count=len(names), station_count=122, phase_status="COMPLETE")
for filename, data in [("REPORT_KO.md","\n".join(lines)+"\n")]:
    (root / filename).write_text(data, encoding="utf-8")
manifest["files_sha256"] = {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*"))
                            if p.is_file() and p.name != "MANIFEST.json"}
(root / "MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
print("Verified run", run, "files", len(manifest["files_sha256"]))
