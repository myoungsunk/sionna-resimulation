"""Validate and package K9/K10 without changing the K0-K8 publication."""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys


root = Path(sys.argv[1])
out = root / "out"
records = root / "records/k9_k10"
run_id = sys.argv[2]
prior = "b070c8685e03133cfe4b846b530181acf66260b8"
spec = "2068954c07770cffee1a8745e53e0383c5ef8c96"
prev_manifest_sha = "f38a8ccb0e71ec97ba235e83905fd99bb5d8108a247f2c1a1b1936a92cce0733"
sigma = [0, 0.05, 0.08, 0.11, 0.15, 0.25, 0.45]
cases = dict(zip(("R2_aA_m0", "R2_aB_m0", "R4_aA_m0", "R4_aB_m0", "R5_aA_m0", "R5_aB_m0"),
                 (21, 21, 10, 10, 30, 30)))
label = "DIAGNOSTIC_ONLY"
observed, extrapolated = "OBSERVED_STATION_SUPPORT", "EXTRAPOLATED"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def fmt_cross(r):
    n = r["first_crossing_visits"]
    return str(n) if r["support"] == observed else f"{n} (외삽)"


k9 = read(out / "K9_HORIZON.json")
k10 = read(out / "K10_KAPPA_CONVERGENCE.json")
for result in (k9, k10):
    assert list(result["cases"]) == list(cases)
    assert (result["classification"], result["s2_prime_verdict"], result["step3"]) == (label, "STOP", "HELD")
assert k10["analysis_status"] == "EXPLORATORY"
assert k9["driver_sha256"] == sha(root / "code/k9.py")
assert k10["driver_sha256"] == sha(root / "code/k10.py")
assert k9["input_sha256"]["frozen_k4"] == k10["inputs"]["k4_oracle_scale_sha256"]
assert k9["input_sha256"]["frozen_q1"] == k10["inputs"]["q1_sweep_rows_sha256"]

by_key = {}
with (out / "K9_horizon.csv").open(encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        key = (row["case"], row["calibration"], float(row["sigma_beta_deg_per_visit"]))
        assert row["classification"] == label
        by_key.setdefault(key, []).append(row)
assert len(by_key) == 84
calibrations = ("frozen", "oracle_scale")
for name, horizon in cases.items():
    for method in calibrations:
        values = k9["cases"][name][method]
        assert [v["sigma_beta_deg_per_visit"] for v in values] == sigma
        assert k9["frozen_reference_max_abs_metrics_difference"][name][method] <= 1e-11
        for summary in values:
            sb = summary["sigma_beta_deg_per_visit"]
            rows = by_key[name, method, sb]
            assert [int(r["visit"]) for r in rows] == list(range(1, len(rows) + 1))
            first = {observed: None, extrapolated: None}
            for row in rows:
                n = int(row["visit"])
                support = observed if n <= horizon else extrapolated
                assert row["support"] == support
                g1, dr = (float(row[k]) for k in ("rmse_g1_deg", "rmse_dr_cal_deg"))
                assert math.isfinite(g1) and math.isfinite(dr) and dr > 0
                assert math.isclose(float(row["ratio_g1_over_dr_cal"]), g1/dr, rel_tol=1e-14)
                assert row["dr_exceeds_g1"] == str(dr > g1)
                if dr > g1 and first[support] is None:
                    first[support] = n
                if n > horizon:
                    assert math.isclose(dr**2, n * .40**2 + n*n*sb**2, rel_tol=1e-13)
                    assert g1 == summary["last5_g1_plateau_deg"]
            assert first[observed] == summary["first_observed_crossing_visits"]
            assert first[extrapolated] == summary["first_extrapolated_crossing_visits"] == len(rows)
            winner = observed if first[observed] is not None else extrapolated
            assert summary["support"] == winner and summary["first_crossing_visits"] == first[winner]
    t = k10["cases"][name]
    hits = t["first_hit_counts_by_visit"]
    assert t["orders"] == 200 and len(hits) == horizon
    assert t["orders_crossed_by_10"] == sum(hits[:10])
    assert t["orders_crossed_by_end"] == sum(hits)
    assert t["orders_right_censored_at_end"] == 200 - sum(hits)
    m = next((j for j in range(1, horizon + 1) if sum(hits[:j]) >= 100), None)
    assert t["median_first_hit_visit"] == m
    assert t["median_first_hit_status"] == ("OBSERVED" if m is not None else "RIGHT_CENSORED")

stages = {}
for stage in ("k9", "k10"):
    stages[stage] = dict(started_utc=(records / f"START_{stage}.txt").read_text().strip(),
                         finished_utc=(records / f"FINISH_{stage}.txt").read_text().strip(),
                         exit=int((records / f"EXIT_{stage}.txt").read_text()),
                         command=(records / f"COMMAND_{stage}.txt").read_text().strip())
    assert stages[stage]["exit"] == 0
assert stages["k9"]["finished_utc"] <= stages["k10"]["started_utc"]
lines = [
    "DIAGNOSTIC_ONLY — S2′ 판정 STOP", "",
    "# G1-DIAG-002 K9/K10 후속 결과", "",
    f"- 실행 ID {run_id}. Step 3 보류.",
    "- [기존 K0–K8 보고서](REPORT_KO.md) · [후속 실행 조건](records/k9_k10/EXECUTION_RECORD_KO.md) · [매니페스트](MANIFEST_K9_K10.json)",
    "", "## K9 r2.1.0 DR의 heading RMSE 교차점", "",
    "기존 6 case의 NR-rand 경로에서 각 방문의 G1과 DR-cal RMSE를 비교했다. 교차점 N*는 DR-cal이 G1보다 처음으로 커진 방문이다. 결과는 나중 방문에서 우위가 유지되는지와 별개다. 표의 숫자는 방문 수다. «외삽» 표시는 DR 해석식과 G1의 마지막 5개 RMSE 평균을 이용한 가정을 뜻한다.", "",
    "| case | station 범위 | 보정 | σβ 0 | 0.05 | 0.08 | 0.11 | 0.15 | 0.25 | 0.45 |",
    "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|",
]
for name, bound in cases.items():
    for method, text in (("frozen", "동결"), ("oracle_scale", "K4 oracle")):
        r = k9["cases"][name][method]
        lines.append(f"| {name} | 1–{bound} | {text} | " + " | ".join(map(fmt_cross, r)) + " |")
lines += ["",
          "사양 §4의 σβ=0.11과 20방문 기준을 기존 station 범위 내 결과에만 적용했다. NR-rand의 N*를 주행 거리나 실측 주행 성능으로 환산하지 않는다.", "",
          "| case | σβ=0.11 동결 N* | σβ=0.11 K4 oracle N* | 외삽 구간 첫 충족 방문 동결 / oracle |",
          "|---|---|---|---|"]
for name in cases:
    summary = []
    for method in calibrations:
        r = k9["cases"][name][method][3]
        n = r["first_crossing_visits"]
        if r["support"] == extrapolated:
            summary.append(f"N*={n}, 외삽")
        else:
            summary.append(f"N*={n}, 범위 내 " + ("≤20" if n <= 20 else ">20"))
    tail = [k9["cases"][name][method][3]["first_extrapolated_crossing_visits"] for method in calibrations]
    lines.append(f"| {name} | {' | '.join(summary)} | {tail[0]} / {tail[1]} |")
lines += [
    "", "- 모든 조건의 최초 N*는 기존 station 지원 범위 안에 있었다. 따로 계산한 외삽 구간 첫 충족 방문은 각 case의 station 지원 범위 직후였다.",
    "- R4_aB에서 σβ=0.11일 때 DR-cal RMSE가 G1보다 컸던 방문은 동결 7/10, K4 oracle 8/10이다.",
    "- 같은 DR, XY, 열잡음 실현을 사용했다. r2.1.0의 공칭 0.482°/visit은 보정하고, σ_w=0.40°/visit과 지정된 σβ의 잔여 bias를 G1과 DR-cal에 공유했다.",
    "- 첫 10개 NR-rand 행을 K3와 일치시켰다. 동결 및 oracle 조건의 K3/K4 요약 지표와 미포함 건수를 각각 재현한 뒤 K9 결과를 산출했다.",
    "- [교차점 원자료](out/K9_HORIZON.json) · [방문별 RMSE 및 비교 범위](out/K9_horizon.csv)",
    "", "## K10 탐색 결과", "",
    "고정 station 집합을 각 case에서 200번 비복원 순열로 배열해 사후 중앙값 κ가 1.5를 처음 초과하는 방문을 기록했다. 오른쪽 검열은 마지막 방문까지 임계값을 넘지 않은 순서의 수다.", "",
    "| case | 10방문 내 초과 | 전체 지원 범위 내 초과 | 우측 검열 | 첫 초과 방문 중앙값 |",
    "|---|---:|---:|---:|---|",
]
for name, n in cases.items():
    t = k10["cases"][name]
    median = t["median_first_hit_visit"]
    listed = str(median) if median is not None else f">{n} (우측 검열)"
    lines.append(f"| {name} | {t['orders_crossed_by_10']}/200 | {t['orders_crossed_by_end']}/200 | {t['orders_right_censored_at_end']}/200 | {listed} |")
lines += [
    "", "순열은 현재 station 집합의 순서 민감도만 나타낸다. 최초 초과 사건의 지속성, 운용 중 수렴 및 실제 오경보율은 평가 범위 밖이다. 이 결과의 파라미터 채택은 보류한다. [K10 원자료](out/K10_KAPPA_CONVERGENCE.json)",
    "", "S2′ 판정은 STOP이다. Step 3는 계속 보류한다.",
]
manifest = dict(question_id="G1-DIAG-002", classification=label, role="IMPLEMENTER", run_id=run_id,
                branch="research/g1-sweep-heading-floor-spec-20261113", spec_commit=spec,
                prior_publication=prior, prior_manifest_sha256=prev_manifest_sha,
                s2_prime_verdict="STOP", step3="HELD", k10_analysis_status="EXPLORATORY",
                stages=stages, cases=cases, k9_inputs=k9["input_sha256"], k10_inputs=k10["inputs"],
                environment=dict(python=k10["python"], numpy=k10["numpy"], scipy=k10["scipy"],
                    docker="sha256:18a2a931b69ef39a028ee6b81e5e0a9dcb2ae0382d07c0093a22efd266eb3b9f"),
                frozen_runner_sha256=k9["direct_code_sha256"],
                governance_sha256=dict(
                    common="a5cca7d8a8d5f20f4a89ea9b6509da0b8d7506626aac4a47fa1d27891ff5ebdb",
                    implementer="2380fb1fe7302870a6c2d825cc2e65a73e91138677e095b4e51db43ab9ea90da"))
(root / "REPORT_K9_K10_KO.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
manifest["files_sha256"] = {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob("*"))
                            if p.is_file() and p.name != "MANIFEST_K9_K10.json"}
(root / "MANIFEST_K9_K10.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                         encoding="utf-8", newline="\n")
print(f"Validated {len(by_key)} K9 case/scale/sigma combinations and 6 K10 case summaries")
