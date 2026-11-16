"""Reaggregate hashes, fixed-mask scores and the M6 decision from saved traces."""

import argparse
from pathlib import Path

import numpy as np

from diagnostics import passage_budget, variogram
from run_characterization import ROOT, characterization_inputs, m5, receipt, verified_native
from run_replay import GRID, SEEDS, setup, verify_receipt

GROUPS = (*m5.ROUTES, "pooled")
BASELINE = "BASE"


def grid_bands(passes):
    bands = []
    for i, value in enumerate(GRID):
        if value in passes:
            if i == 0 or GRID[i - 1] not in passes:
                bands.append([])
            bands[-1].append(value)
    return [band for band in bands if len(band) >= 2]


def summarize_bands(scores, omissions):
    grid = {}
    for group in GROUPS:
        grid[group] = {
            field: [deg for deg in GRID
                    if scores["10"]["common"]["gates"].get(f"G1_{deg:g}", {}).get(group, {}).get(field, False)]
            for field in ("pass", "integrity_ok", "accuracy_ok")
        }
    common = [deg for deg in GRID if all(deg in grid[g]["pass"] for g in GROUPS)]
    bands = grid_bands(common)
    contrast = {}
    for arm in ("G1_LORO", "G1_KI", "G1d"):
        by_seed = {}
        for seed, data in scores.items():
            gate = data["common"]["gates"].get(arm)
            if gate is not None:
                by_seed[seed] = dict(routes_pass=all(gate[r]["pass"] for r in m5.ROUTES),
                                     pooled_pass=gate["pooled"]["pass"],
                                     mirror_count=gate["pooled"]["mirror_fail_count"])
        complete = len(by_seed) == len(SEEDS)
        passes = sum(row["pooled_pass"] for row in by_seed.values())
        contrast[arm] = dict(seed_results=by_seed, complete=complete,
                             pooled_pass_seed_count=passes,
                             five_seed_pass=complete and passes >= 4 and
                             all(row["routes_pass"] and row["mirror_count"] == 0 for row in by_seed.values()))
    requested_grid_omitted = any(name.startswith("G1_") and name.rsplit("_", 1)[1] in
                                 {f"{value:g}" for value in GRID}
                                 for route in omissions["10"].values() for name in route)
    return dict(grid_by_group=grid, joint_grid_pass_deg=common, adjacent_pass_bands_deg=bands,
                grid_status="INCOMPLETE" if requested_grid_omitted else "BAND_PASS" if bands else "NO_BAND",
                five_seed=contrast,
                gm_theta_adoption_candidate=bool(bands) and not requested_grid_omitted
                and contrast["G1_LORO"]["five_seed_pass"], omissions=omissions)


def read_seed(out, spec, lock, cases, seed, checks):
    stage = "seed10" if seed == 10 else "seed11_14"
    baseline_path = out / "implementation" / f"seed{seed}"
    candidates_path = out / stage / f"seed{seed}"
    by_route, omissions = {}, {}
    for route, case in cases.items():
        base = m5.arrays(baseline_path / f"{route}_G0.npz")
        m5.grid_equal(case["packet"], base)
        m5.parity(base, m5.arrays(m5.checked(lock["archived_a0"][str(seed)][route])))
        by_arm = by_route[route] = {BASELINE: base}
        omitted = omissions[route] = {}
        planned = [row["name"] for row in spec["variants"] if row["route"] == route and seed in row["seeds"]]
        statuses = checks[str(seed)][route]
        if set(statuses) != set(planned):
            raise ValueError(f"Replay manifest differs for {seed}/{route}")
        for name in planned:
            info = statuses[name]
            if info["status"] != "PASS":
                omitted[name] = info
                continue
            candidate = m5.arrays(candidates_path / f"{route}_{name}.npz")
            m5.grid_equal(case["packet"], candidate)
            np.testing.assert_array_equal(candidate["mask"], base["mask"])
            np.testing.assert_array_equal(candidate["R_ref"], base["Reff"])
            by_arm[name] = candidate
    return by_route, omissions


def by_availability(traces, cases):
    available = {key: tuple(route for route in m5.ROUTES if key in traces[route])
                 for key in sorted({name for row in traces.values() for name in row if name != BASELINE})}
    full = [arm for arm, routes in available.items() if routes == m5.ROUTES]
    common = m5.scores({route: {arm: traces[route][arm] for arm in (BASELINE, *full)}
                        for route in m5.ROUTES}, cases)
    subsets = {}
    for routes in sorted(set(available.values()) - {m5.ROUTES}):
        subset_arms = [arm for arm, have in available.items() if have == routes]
        subset = m5.scores({route: {arm: traces[route][arm] for arm in (BASELINE, *subset_arms)}
                            for route in routes}, {route: cases[route] for route in routes})
        subsets["+ ".join(routes)] = dict(routes=routes, arms=subset_arms, scores=subset)
    return dict(common=common, subsets=subsets)


def local_r2(traces, case):
    from metrics_s2 import _summarize
    from verify_s2 import from_trace

    t = case["packet"]["t"]
    in_window = (t - t[0] >= 120.) & (t - t[0] <= 140.)
    result = {}
    for arm in (BASELINE, "G1_LORO", "G1_KI"):
        if arm in traces:
            trace = traces[arm]
            err_y = trace["x"][in_window, 1] - case["truth"][in_window, 1]
            result[arm] = dict(all_packet_scores=_summarize(from_trace(trace, case["truth"])[in_window]),
                               y_rmse_cm=float(100. * np.sqrt(np.mean(err_y ** 2))),
                               count=int(in_window.sum()),
                               q_nonzero_accepted=int((trace.get("q_s", np.zeros(len(t)))[in_window] > 0.)
                                                      [trace["mask"][in_window]].sum()))
    return result


def hybrid_paired(traces, cases):
    from ks_diagnostics import scores_with_blocks
    from verify_s2 import from_trace

    arms = ("G1_LORO", "G1_KI")
    rows = {route: {arm: from_trace(traces[route][arm], case["truth"]) for arm in arms}
            for route, case in cases.items() if all(arm in traces[route] for arm in arms)}
    if not rows:
        return {}
    scores = scores_with_blocks(rows, {r: cases[r]["packet"]["t"] for r in rows},
                                [("G1_KI", "G1_LORO")], blocks=(5, 10, 20))
    return {str(seconds): {route: data["paired_ci95"]["G1_KI-G1_LORO"]
                           for route, data in block["by_group"].items()
                           if route != "pooled" or tuple(rows) == m5.ROUTES}
            for seconds, block in scores["blocks"].items()}


def metrics_table(data, group_order=GROUPS):
    lines = ["| Arm | 궤적 | Heading95 | XY95 | Pose95 | NEES3 | Heading RMSE | XY RMSE | 거울해 | 무결성 | 정확도 |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for arm, gates in data["gates"].items():
        for group in group_order:
            if group not in gates:
                continue
            values = data["point"][group][arm]
            gate = gates[group]
            changes = gate["rmse_increase_pct"]
            accuracy = data["accuracy"][arm][group].removeprefix("ACCURACY_")
            lines.append(
                f"| {('G0' if arm == BASELINE else arm)} | {group} | {values['heading95_coverage']:.1%} | "
                f"{values['xy95_coverage']:.1%} | {values['pose95_coverage']:.1%} | {values['mean_nees3']:.2f} | "
                f"{values['heading_rmse_deg']:.2f}° ({changes['heading_rmse_deg']:+.1f}%) | "
                f"{values['xy_rmse_cm']:.2f} cm ({changes['xy_rmse_cm']:+.1f}%) | "
                f"{gate['mirror_fail_count']} | {'PASS' if gate['integrity_ok'] else 'FAIL'} | {accuracy} |"
            )
    return lines


def report(directory, spec, prediction, scores, bands, local):
    lines = ["# M6 검증 결과", "",
             "질문 G1-INT-001/M6 · mount 0°, 앵커 B, B0, Full RF · DIAGNOSTIC_ONLY", "",
             f"계획 커밋 `{spec['plan']['commit']}`. 고정 seed 10 gate의 R2/R4/R5는 971/979, "
             "728/742, 1384/1415입니다. seed마다 G0의 R_ref와 초기 분포를 공유했습니다. "
             "seed 10–14는 같은 RF 실현에서 wheel·gyro 잡음만 바꾼 재생입니다.", "",
             "## 특성화", "",
             f"K1′ 지수 {prediction['k1']['slope']:.3f}, 95% 구간 "
             f"[{prediction['k1']['ci_95'][0]:.3f}, {prediction['k1']['ci_95'][1]:.3f}]. "
             "동결한 상한 <2 조건에서 G1+KI를 실행했습니다. 지수는 느린 잔차 분산의 감도 스케일링을 "
             "측정합니다.", "",
             f"K2 판정 `{prediction['k2']['verdict']}`. LORO σθ (R2/R4/R5) "
             + "/".join(f"{np.rad2deg(prediction['k2']['folds'][r]['sigma_rad']):.3f}°" for r in m5.ROUTES)
             + ". K2의 g 하한은 1.0 rad⁻¹이며 D3 중심화 뒤 b_eq의 영점 기준 규모를 사용했습니다.", "",
             "K1′ 공통 지수에서 R4의 기울기 정보 몫은 약 1.09%입니다. R4 자체의 기술적 지수는 "
             "약 2.38이고 적격 거리는 3–6 m·6–10 m입니다. 공통 지수를 R4의 가산형 오차 확정에 "
             "사용할 근거는 이 표본에서 부족합니다. K2는 세 궤적 공통 지원 셀이 0개이며, 약 2° "
             "규모는 고감도 donor 표본에 조건부입니다.", "",
             "## 채택 판정", "",
             f"- G1 grid `{bands['grid_status']}`. 전체 공통 통과 σθ {bands['joint_grid_pass_deg']}.",
             f"- G1 LORO의 pooled 통과 seed {bands['five_seed']['G1_LORO']['pooled_pass_seed_count']}/5. "
             f"5-seed 판정 `{bands['five_seed']['G1_LORO']['five_seed_pass']}`.",
             f"- G1+KI의 pooled 통과 seed {bands['five_seed']['G1_KI']['pooled_pass_seed_count']}/5. "
             f"5-seed 판정 `{bands['five_seed']['G1_KI']['five_seed_pass']}`.",
             f"- GM-θ 채택 후보 `{bands['gm_theta_adoption_candidate']}`.", "",
             "## Seed 10 전체 궤적 비교", ""]
    lines += metrics_table(scores["10"]["common"])
    for subset in scores["10"]["subsets"].values():
        lines += ["", "### 적용 궤적 한정 · " + "/".join(subset["routes"]), ""]
        lines += metrics_table(subset["scores"], subset["routes"])
    lines += ["", "R5의 3 m 제외 탐색은 보관된 §3.3의 4° 조건입니다. "
              "기록값은 Heading95 93.4%, heading RMSE 0.77°, XY RMSE 5.00 cm, 거울해 0건입니다. "
              "M6의 G4는 R2/R4의 2° 스케줄을 사용했습니다.", "",
              "## Seed 11–14", ""]
    for seed in SEEDS[1:]:
        lines += [f"### Seed {seed}", "", *metrics_table(scores[str(seed)]["common"]), ""]
    lines += ["## R2 120–140 s", "",
              "| Seed | Arm | Heading95 | y RMSE | XY RMSE | KI 증가 수용 패킷 |",
              "|---:|---|---:|---:|---:|---:|"]
    for seed, rows in local.items():
        for arm, row in rows.items():
            point = row["all_packet_scores"]
            lines.append(f"| {seed} | {('G0' if arm == BASELINE else arm)} | {point['heading95_coverage']:.1%} "
                         f"| {row['y_rmse_cm']:.2f} cm | {point['xy_rmse_cm']:.2f} cm | "
                         f"{row['q_nonzero_accepted']} |")
    if any(arms for routes in bands["omissions"].values() for arms in routes.values()):
        lines += ["", "구현 검사를 통과하지 못한 arm은 BAND.json의 omissions에 기록했습니다."]
    lines += ["", "5/10/20초 블록 구간과 paired 차이는 SCORES.json에 있습니다. R5 통과별 정보와 "
              "실제 갱신량은 K4.json, 후순위 variogram은 K3.json에 저장했습니다."]
    with (directory / "REPORT_KO.md").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(lines) + "\n")


def aggregate(out, directory):
    spec, lock, base, cases = setup(out)
    barrier = ROOT / "online_barrier"
    verify_receipt(barrier)
    barrier_checks = m5.read(barrier / "CHECKS.json")
    if len(barrier_checks) != len(spec["variants"]) or any(
        check["status"] != "PASS" for check in barrier_checks.values()
    ):
        raise ValueError("Supplementary information-blocking checks have unresolved failures")
    for stage in ("implementation", "seed10", "seed11_14"):
        verify_receipt(out / stage)
    verify_receipt(Path(spec["inputs"]["contract"]["path"]).parent)
    prediction = m5.read(spec["inputs"]["characterization"]["path"])
    checks = m5.read(out / "seed10/CHECKS.json") | m5.read(out / "seed11_14/CHECKS.json")
    planned_keys = {(seed, row["route"], row["name"]) for row in spec["variants"] for seed in row["seeds"]}
    expected_count = sum(len(row["seeds"]) for row in spec["variants"])
    if len(planned_keys) != expected_count:
        raise ValueError("Duplicate planned condition")
    seen = set()
    for stage, seeds in (("seed10", (10,)), ("seed11_14", SEEDS[1:])):
        expected_paths = set()
        for seed in seeds:
            for route, arms in checks[str(seed)].items():
                for name, check in arms.items():
                    key = (seed, route, name)
                    if key not in planned_keys or key in seen:
                        raise ValueError("Unplanned or duplicated executed condition")
                    seen.add(key)
                    if check["status"] == "PASS" or (out / stage / f"seed{seed}" / f"{route}_{name}.npz").exists():
                        expected_paths.add(f"seed{seed}/{route}_{name}.npz")
        actual_paths = {p.relative_to(out / stage).as_posix() for p in (out / stage).rglob("*.npz")}
        if actual_paths != expected_paths:
            raise ValueError("Unexpected/missing archived trace")
    if seen != planned_keys:
        raise ValueError("Missing planned execution")
    baseline_files = {p.relative_to(out / "implementation").as_posix()
                      for p in (out / "implementation").rglob("*.npz")}
    if baseline_files != {f"seed{seed}/{route}_G0.npz" for seed in SEEDS for route in m5.ROUTES}:
        raise ValueError("Baseline condition matrix differs")
    directory.mkdir(parents=True, exist_ok=True)
    m5.write(directory / "RUN_CONTRACT.json", dict(
        stage="aggregation", frozen_utc=m5.utc(), source=m5.item(Path(__file__).resolve()),
        replay=m5.item(out / "RUN_CONTRACT.json"),
        online_barrier=m5.item(barrier / "EXECUTION.json"),
        inputs={stage: m5.item(out / stage / "EXECUTION.json")
                for stage in ("implementation", "seed10", "seed11_14")}))
    with receipt(directory, "aggregation") as run:
        scores, omissions, local, k4 = {}, {}, {}, {}
        for seed in SEEDS:
            key = str(seed)
            traces, omissions[key] = read_seed(out, spec, lock, cases[seed], seed, checks)
            scores[key] = by_availability(traces, cases[seed])
            scores[key]["G1_KI_vs_G1_LORO_paired"] = hybrid_paired(traces, cases[seed])
            local[key] = local_r2(traces["R2"], cases[seed]["R2"])
            k4[key] = {arm: passage_budget(cases[seed]["R5"], trace)
                       for arm, trace in traces["R5"].items()}
            print(f"Aggregation: seed {seed} archive and scores checked", flush=True)
        bands = summarize_bands(scores, omissions)
        m5.write(directory / "CHECKS.json",
                 dict(status="PASS", planned_candidate_conditions=expected_count,
                      seen_candidate_conditions=len(seen), baseline_conditions=len(baseline_files),
                      omitted_candidate_conditions=sum(len(names) for routes in omissions.values()
                                                        for names in routes.values()),
                      additional_barrier_settings=len(barrier_checks),
                      hash_receipts_verified=["implementation", "seed10", "seed11_14", "online_barrier",
                                              "characterization"]))
        m5.write(directory / "SCORES.json", scores)
        m5.write(directory / "BAND.json", bands)
        m5.write(directory / "K4.json", k4)
        m5.write(directory / "R2_LOCAL.json", local)
        native, run["native_source_hashes"] = verified_native(base)
        data, _ = characterization_inputs(lock, cases[10], native)
        m5.write(directory / "K3.json", variogram(data))
        report(directory, spec, prediction, scores, bands, local)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    aggregate(args.replay, args.results)
