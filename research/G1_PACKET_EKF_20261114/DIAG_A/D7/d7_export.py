"""Verify and report the complete D7 output with seed/site-paired inference."""
import csv
import gzip
import json
from pathlib import Path

import numpy as np

from check_d7_limits import SPEC_COMMIT
from diag_inputs import CASES, COHORTS, WORK, sha256
from diag_metrics import (
    CHI1_95, CHI2_95, COUNT_COLUMNS, _intervals, bootstrap_design, bootstrap_totals,
    score_sufficient, site_totals,
)
from d7_run import ROOT, VARIANTS
from run_diag import scenario_key, utc, write_json

LEVELS = ("B0", "L0", "L1", "L2")
BASES = ("J4", "R4", "DR4", "J-V")
NEES = ("heading_nees_mean", "xy_nees_mean", "bias_nees_mean")


def from_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def all_hashes(root):
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}


def integrity(row):
    return (row["heading95_coverage"] >= .90
            and all(.5 <= row[key] <= 2.0 for key in NEES))


def validate():
    manifest = from_json(ROOT/"MANIFEST.json")
    if manifest["spec_commit"] != SPEC_COMMIT:
        raise ValueError("Wrong executed spec")
    for k, v in manifest["code_sha256"].items():
        if sha256(ROOT.parent/k) != v:
            raise ValueError(f"Code changed during execution: {k}")
    for k, v in manifest["main_inputs_sha256"].items():
        if sha256(ROOT.parent/k) != v:
            raise ValueError(f"Input changed during execution: {k}")
    expected = {(c, l, s) for c in CASES for l, s in COHORTS}
    rows = from_json(ROOT/"EXECUTION.json")
    ids = {(r["case"], r["level"], r["sign"]) for r in rows}
    if ids != expected or len(rows) != len(expected):
        raise ValueError("Missing, unexpected or duplicate D7 jobs")
    history = from_json(WORK/"MANIFEST.json")["outputs_sha256"]
    for r in rows:
        case, level, sign = r["case"], r["level"], r["sign"]
        key = scenario_key(level, sign)
        log = ROOT/"logs"/f"{case}_{key}.log"
        if r["exit"] != 0 or sha256(log) != r["log_sha256"]:
            raise ValueError(f"Invalid cohort receipt/log: {case}/{key}")
        for stage in ("D5", "D6"):
            rel = f"results/{case}/{key}_{stage}_CHECKPOINT.npz"
            if sha256(WORK/rel) != history[rel]:
                raise ValueError(f"Invalid baseline hash: {rel}")


def load_cohort(path, summary):
    record = {}
    for variant in VARIANTS:
        src = summary["arms"][variant].get("identical_to", variant)
        record[variant] = {field: path[f"{src}_{field}"] for field in
                           ("checkpoint", "frame", "checkpoint_error", "checkpoint_covariance")}
    sites = path["site"]
    shape = (20, len(sites))
    for name, row in record.items():
        for field, arr in row.items():
            if not np.isfinite(arr).all():
                raise ValueError(f"Non-finite D7 arrays: {name} {field}")
        if row["checkpoint"].shape[:2] != shape or row["frame"].shape[0] != 20:
            raise ValueError(f"Incompatible seed/checkpoint dimensions: {name}")
        p = row["checkpoint_covariance"]
        if np.max(np.abs(p-p.swapaxes(-1,-2))) != 0 or np.min(np.linalg.eigvalsh(p)) < -1e-12:
            raise ValueError(f"Invalid marginal covariance: {name}")
    return record, sites


def save_checkpoints(writer, case, level, sign, key, site, data, record):
    for name, row in record.items():
        for seed, (errors, covs, stats) in enumerate(zip(row["checkpoint_error"],
                                                       row["checkpoint_covariance"], row["checkpoint"])):
            for j, (error, p, counts) in enumerate(zip(errors, covs, stats)):
                writer.writerow([case, level, sign, seed, name, key[j], site[j], data["distance"][j],
                                 data["time_s"][j], *error, *p[np.triu_indices(4)], *map(int, counts[7:10]),
                                 int(counts[11])])


def group_cohorts(output):
    grouped, sums, rotation, by_case = {}, {}, {}, {}
    csv_path = output/"checkpoint_rows.csv.gz"
    with gzip.open(csv_path, "wt", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        p_names = [f"P_{i}{j}" for i,j in zip(*np.triu_indices(4))]
        writer.writerow(["case", "bias", "sign", "seed", "arm", "checkpoint_index", "site",
                         "distance_m", "time_s", "dx_m", "dy_m", "yaw_error_rad", "bias_error_rad_s",
                         *p_names, "heading95", "xy95", "bias95", "range_accepted"])
        for case in CASES:
            by_case[case] = {}
            for level, sign in COHORTS:
                key = scenario_key(level, sign)
                summary = from_json(ROOT/case/f"{key}.json")
                if summary["seeds"] != list(range(20)) or summary["case"] != case:
                    raise ValueError("Unexpected cohort contents")
                with np.load(ROOT/case/f"{key}.npz", allow_pickle=False) as data:
                    arms, sites = load_cohort(data, summary)
                    save_checkpoints(writer, case, level, sign, data["checkpoint_index"], sites, data, arms)
                    arrays = {**{a: arms[a]["checkpoint"] for a in VARIANTS},
                              **{a: data[a] for a in BASES}}
                    for name, arr in arrays.items():
                        if name in VARIANTS:
                            r = summary["arms"][name]
                            rotation[case, level, sign, name] = np.array([
                                np.sum(r["heading_update_straight_rad_per_seed"]),
                                np.sum(r["heading_update_rotation_rad_per_seed"]),
                            ])
                            sums[case, level, sign, name] = np.sum(arms[name]["frame"], axis=0)
                        grouped[case, level, sign, name] = site_totals(arr, sites)
                    by_case[case][key] = {name: {"checkpoint": score_sufficient(
                        g.sum(axis=(0,1))), "site_count": g.shape[1]}
                        for name in arrays
                        for g in (grouped[case, level, sign, name],)}
    return grouped, sums, rotation, by_case


def pooled_stats(grouped, names, cohorts, cases=CASES):
    point, resampled = {}, {}
    for case_index, case in enumerate(cases):
        for name in names:
            g = sum(grouped[case, l, s, name] for l, s in cohorts)
            design = bootstrap_design(g.shape[0], g.shape[1], seed=20261114+case_index)
            point[name] = point.get(name, 0.0) + g.sum(axis=(0,1))
            resampled[name] = resampled.get(name, 0.0) + bootstrap_totals(g, design)
    return {a: score_sufficient(v) for a, v in point.items()}, {
        a: score_sufficient(v) for a, v in resampled.items()}


def compact(score):
    return {k: v for k,v in score.items() if k not in COUNT_COLUMNS}


def present_pooled(grouped, sums, rotation):
    result = {}
    group_keys = [(scenario_key(l, s), [(l,s)]) for l,s in COHORTS]
    group_keys += [(l, [(l2,s) for l2,s in COHORTS if l2 == l]) for l in LEVELS if l != "B0"]
    for key, cohorts in group_keys:
        p, b = pooled_stats(grouped, VARIANTS + BASES, cohorts)
        row = {}
        for arm in VARIANTS:
            rot = sum(rotation[c, l, s, arm] for c in CASES for l,s in cohorts)
            frame = sum(sums[c, l, s, arm] for c in CASES for l,s in cohorts)
            paired = {}
            for baseline in BASES:
                delta = {m: p[arm][m]-p[baseline][m] for m in ("heading_rmse_deg", "xy_rmse_m")}
                d_boot = {m: b[arm][m]-b[baseline][m] for m in delta}
                paired[baseline] = {metric: {"difference": value,
                                             "ci95": tuple(np.percentile(d_boot[metric], (2.5,97.5)))}
                                    for metric,value in delta.items()}
            row[arm] = {"checkpoint": compact(p[arm]), "frame": compact(score_sufficient(frame)),
                        "integrity_pass": integrity(p[arm]), "paired_checkpoint": paired,
                        "heading_rotation_share": rot[1]/rot.sum()}
        row["baseline_checkpoint"] = {a: compact(p[a]) for a in BASES}
        result[key] = row
    return result


def format_report(pooled, by_case):
    lines = [
        "# G1-DIAG-003 D7 결과 — DIAGNOSTIC_ONLY",
        "",
        "S2′ STOP (FULL_6) · Step 3 보류.",
        "",
        f"사양 커밋 {SPEC_COMMIT}. B0 seed 0–19의 네 case에서 J4·J-V 기준 재현 검산을 통과했다.",
        "D7.1 본 계산은 네 case × 7개 bias·부호 조건 × 20 sensor seed를 사용했다.",
        "RF 입력은 네 동결 경로이고 seed는 그 경로 안에서의 반복이다.",
        "",
        "## Pooled checkpoint 무결성과 DR 비교",
        "",
        "L0–L2는 두 부호를 합쳤다. 표의 NEES 순서는 heading, XY, b_g다.",
        "RMSE 차이는 D7−DR이다. CI는 case 안에서 seed와 1 m site를 짝지어 2,000회 재표집했다.",
        "",
        "| Bias | Arm | Heading 포함률 | 평균 NEES | Heading RMSE | DR 대비 차이 (95% CI), ° | 회전 갱신 몫 | 무결성 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for level in LEVELS:
        for a in VARIANTS:
            r = pooled["B0_+0" if level == "B0" else level][a]
            c = r["checkpoint"]
            v = r["paired_checkpoint"]["DR4"]["heading_rmse_deg"]
            nees = ", ".join(f"{c[k]:.2f}" for k in NEES)
            lo, hi = v["ci95"]
            lines.append(f"| {level} | {a} | {c['heading95_coverage']:.1%} | {nees} | "
                         f"{c['heading_rmse_deg']:.3f}° | {v['difference']:+.3f} [{lo:+.3f}, {hi:+.3f}] | "
                         f"{r['heading_rotation_share']:.1%} | {'PASS' if r['integrity_pass'] else 'FAIL'} |")
    lines.extend(["", "## 판정 범위", ""])
    primary = {l: pooled["B0_+0" if l == "B0" else l] for l in LEVELS}
    for a in VARIANTS:
        integrity_levels = [l for l,r in primary.items() if r[a]["integrity_pass"]]
        accuracy_levels = [l for l in integrity_levels
                           if primary[l][a]["paired_checkpoint"]["DR4"]["heading_rmse_deg"]["ci95"][1] < 0]
        turn_levels = [l for l,r in primary.items() if r[a]["heading_rotation_share"] >= .70]
        lines.append(f"- {a} 무결성 충족 {integrity_levels or '없음'}, "
                     f"동시 DR 우위(H3) {accuracy_levels or '없음'}, 회전 몫 70% 이상 {turn_levels or '없음'}.")
    lines.extend(["", "## 미식별 상관길이 두 조건",
                  "", "| Case | 조건 | JC(상한) 포함률 | JC(∞) 포함률 | 무결성 상한 / ∞ |",
                  "|---|---|---:|---:|---|"])
    for c in ("R2_aB_m0", "R4_aB_m0"):
        for l,s in COHORTS:
            k = scenario_key(l,s)
            a = by_case[c][k]["JC_upper"]["checkpoint"]
            b = by_case[c][k]["JC_infinite"]["checkpoint"]
            lines.append(f"| {c} | {k} | {a['heading95_coverage']:.1%} | {b['heading95_coverage']:.1%} | "
                         f"{'PASS' if integrity(a) else 'FAIL'} / {'PASS' if integrity(b) else 'FAIL'} |")
    lines.extend([
        "",
        "두 조건이 갈린 case와 bias에서 원인 귀속을 유보했다. +K를 포함한 세부 조건·부호별 "
        "지표와 D1 분해는 cohort JSON에 있다.",
        "",
        "R2-aB의 거리·편파 및 R4-B 편파에서 상한을 적용했다. R5-B 거리 상관길이 "
        "0.0353 m는 0.04 m 이동 packet 간격 이하여서 거리 오차 분산을 백색 공분산으로 반영했다.",
        "상한 채널의 consider 분산에는 명시된 같은 anchor의 다른 경로를 사용했다. "
        "재현 검산의 거리 상태 비활성화는 기준 재현 검산에 한정했다.",
        "",
        "## 파일",
        "",
        "- out/D7_JC.json에 입력 및 판정 근거와 pooled·case·부호별 지표를 기록했다.",
        "- out/checkpoint_rows.csv.gz에 D7 상태 오차·공분산·포함 지표가 있다.",
        "- main/ 아래 cohort별 계산·paired CI·D1 분해, 로그와 종료 기록을 보존했다.",
    ])
    return "\n".join(lines)+"\n"


def main():
    validate()
    out = ROOT.parent/"out"
    out.mkdir(exist_ok=False)
    grouped, sums, rotation, case = group_cohorts(out)
    pooled = present_pooled(grouped, sums, rotation)
    params = from_json(ROOT/"PARAMETERS.json")
    write_json(out/"D7_JC.json", {"classification": "DIAGNOSTIC_ONLY", "spec_commit": SPEC_COMMIT,
                "S2_prime": "STOP (FULL_6)", "Step_3": "HOLD", "cases": case,
                "pooled": pooled, "parameters": params, "generated_utc": utc(),
                "bootstrap": "seed and site resampled within case; common draws paired across arms and bias signs"})
    report = ROOT.parent/"REPORT_KO.md"
    report.write_text(format_report(pooled, case), encoding="utf-8")
    write_json(ROOT.parent/"ARTIFACT_MANIFEST.json", {"status": "D7_COMPLETE", "spec_commit": SPEC_COMMIT,
               "exporter_sha256": sha256(Path(__file__)), "report_sha256": sha256(report),
               "main_sha256": all_hashes(ROOT), "out_sha256": all_hashes(out)})
    print("D7 report, manifest and checkpoint export completed", utc(), flush=True)


if __name__ == "__main__":
    main()
