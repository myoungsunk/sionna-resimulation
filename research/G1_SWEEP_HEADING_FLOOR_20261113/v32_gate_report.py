"""Summarize the executed v3.2 entry gates without manufacturing a §8 verdict."""
from argparse import ArgumentParser
import csv
import json
from pathlib import Path

def read(path):
    return json.loads(path.read_bytes())

def main():
    parser = ArgumentParser()
    parser.add_argument("out", type=Path)
    a = parser.parse_args()
    o = a.out
    obs = read(o/"S1P_OBS_PREFLIGHT.json")
    r0 = read(o/"R0.json")
    first = read(o/"S1P_G_INT_RESULT_sparse_initial.json")
    refined = read(o/"S1P_G_INT_RESULT_sparse_refined.json")
    check_files = [o/f"EXIT_{phase}.txt" for phase in ("PREFLIGHT","GINT","GINT_REFINED")]
    phases = [int(p.read_text()) for p in check_files]
    if phases != [0, 1, 1] or first["passed"] or refined["passed"]:
        raise ValueError(f"Unexpected status for gate-failure report: {phases}")
    if first["diagnostic_subset"] or refined["diagnostic_subset"]:
        raise ValueError("Full six-case gate outputs are required")
    names = obs["primary"]
    for result in (first, refined):
        if set(result["probes"]) != set(names):
            raise ValueError("Gate result has missing cases")
        for name, rows in result["probes"].items():
            nodes = result["sigma_by_case"][name]
            if [r["sigma_interval"] for r in rows] != [list(x) for x in zip(nodes,nodes[1:])]:
                raise ValueError(f"{name}: gap or duplicate sigma interval")
            if any(r["paired"] != 100 or r["samples"] != 100 for r in rows):
                raise ValueError(f"{name}: incomplete paired probes")
            for r in rows:
                expected = (r["yaw_p95"] <= .25 and r["variance_rel_p95"] <= .20
                            and r["candidate_count_agreement"] >= .95)
                if r["passed"] != expected:
                    raise ValueError(f"{name}: gate classification mismatch")
    with (o/"S1P_G_INT_SUMMARY.csv").open("w", encoding="utf-8", newline="") as f:
        keys = list(first["probes"][names[0]][0])
        writer = csv.DictWriter(f, ["phase","case",*keys])
        writer.writeheader()
        for phase, res in (("initial",first),("refined",refined)):
            for name in names:
                writer.writerows(dict(phase=phase,case=name,**r) for r in res["probes"][name])
    def counts(res):
        rows = [row for v in res["probes"].values() for row in v]
        return dict(total=len(rows), failed=sum(not row["passed"] for row in rows),
                    yaw_fail=sum(r["yaw_p95"] > .25 for r in rows),
                    variance_fail=sum(r["variance_rel_p95"] > .20 for r in rows),
                    candidate_fail=sum(r["candidate_count_agreement"] < .95 for r in rows),
                    max_yaw=max(r["yaw_p95"] for r in rows),
                    max_variance=max(r["variance_rel_p95"] for r in rows),
                    min_candidates=min(r["candidate_count_agreement"] for r in rows))
    a0, a1 = counts(first), counts(refined)
    gates = {
        "question_id":"G1-MODEL-001",
        "spec_commit":"ebd55913519e852364a07fb33ec3188c9cbe7bca",
        "status":"BLOCKED_G_INT_A",
        "R0": r0,
        "G-OBS-1_and_2": {c:obs["by_case"][c]["gates"] for c in obs["by_case"]},
        "G-INT-a":{"passed":False,"initial":a0,"refined":a1},
        "G-INT-b":"NOT_RUN",
        "G-OBS-3":"NOT_RUN_OPTIONAL_M2",
        "eligible_m1_mount0_cases":names,
        "step2_primary":"NOT_RUN",
        "section_8_verdict":None,
        "scientific_pass":False,
        "step3":"HELD",
    }
    (o/"S1P_GATES.json").write_text(json.dumps(gates,indent=2)+"\n",encoding="utf-8")
    text = """# G1-MODEL-001 v3.2 1차 계산 기록

사양 ebd55913519e852364a07fb33ec3188c9cbe7bca, A2 1차 진입 검사. **G-INT-a 재검사 미달로 S2′를 시작하지 않았다.** §8의 과학 판정은 미산출이고 Step 3는 보류다.

## 통과한 검사

- R0의 5개 mount-0 J 배열은 기존 배열과 SHA-256이 일치했다. 1,000회 station bootstrap을 포함한 기존 코드를 같은 Windows NumPy/SciPy 버전에서 실행했고, 세 모형의 1–17 누적 비율·NEES·포함률 차이는 모두 0이었다. 원래 공간 상관과 DR 입력값은 동결 기록을 그대로 사용했다.
- mount-0 6개가 G-OBS-1/2를 통과했다. mount-45의 별도 민감도 관측 검사도 통과했다. R2_aB_m0의 M1-T p90은 6.80e-7, M1-R 무잡음 heading p95는 0.148°였다. 동일 case의 M0 p90은 0.02092였다.
- 초기 저장 후보 축은 0, .03, .06, .09, .12, .16, .195984, .231967 m였다. 명목 station과 k=0…50의 거리 투영식으로 범위를 사전 산출했다.

## G-INT-a 직접 계산 대비 보간

| 검사 | 미달 case×구간 | yaw p95 최대 | E1 분산 상대차 p95 최대 | 후보 수 일치율 최소 |
|---|---:|---:|---:|---:|
"""
    for label, v in (("초기 0.10 m",a0),("재검사 0.05 m",a1)):
        text += (f"| {label} | {v['failed']}/{v['total']} | {v['max_yaw']:.3f}° | "
                 f"{v['max_variance']:.1%} | {v['min_candidates']:.1%} |\n")
    text += (f"\n재검사에서는 yaw p95 0.25°를 넘은 구간이 {a1['yaw_fail']}개, "
             f"E1 분산 상대차 p95 20%를 넘은 구간이 {a1['variance_fail']}개, "
             f"후보 수 일치율 95% 미만 구간이 {a1['candidate_fail']}개였다.\n")
    text += """
- case마다 고정한 비격자 XY 100개에서 모든 σ 구간의 중점을 검사했다. RF station과 seed는 복원 추출했고, 후보 탐색 창은 참 heading 중심 ±10°였다. 분산은 두 방식의 J 최저 후보에서 비교했고, 후보 수는 C1 직후에 셌다.
- 검증에 필요한 격자 노드만 계산했다. 저장 형식에 맞춰 노드 J와 최소 GH 노드 잔차를 float32로 변환한 뒤 float64로 보간했다. 직접 계산은 float64였다. 직접 계산한 LORO 보정값을 두 방식에 공통 적용했다.
- 초기에는 모든 σ 구간이 미달해 모든 구간을 이등분했다. XY 간격도 0.10 m에서 0.05 m로 줄였고, 같은 XY·RF 표본과 새 σ 중점에서 재검사했다. 기준 수치는 유지했다.
- 보간 검사에서 원래 각도·분산·후보 수 기준만으로 구간 판정을 재집계했다. 이 결과는 지정된 보간 방법의 적합성에 한정한다.

증거는 R0.json, S1P_OBS_PREFLIGHT.json, S1P_G_INT_SUMMARY.csv, 초기·재검사 JSON 및 로그, MANIFEST.json에 있다. 전체 J 격자, A2 본 시뮬레이션, §8 판정, DR 민감도 및 Step 3는 실행 범위에 진입하지 않았다.
"""
    (o/"REPORT_KO.md").write_text(text,encoding="utf-8")
    print(json.dumps(dict(initial=a0,refined=a1),indent=2))

if __name__ == "__main__":
    main()
