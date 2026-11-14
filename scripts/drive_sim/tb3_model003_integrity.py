"""B-mode integrity metrics and deterministic S3 primary-arm selection.

Input API
---------
``evaluate_integrity(rows, bootstrap_seed=...)`` accepts one mapping per
case/level/sign/seed/site/checkpoint. Required fields are ``case``, ``level``,
``sign``, ``seed``, ``site_id``, ``checkpoint_id``, ``heading_included``,
``xy_included``, ``nees_heading``, ``nees_xy_normalized`` (XY NEES divided by
two degrees of freedom), ``nees_bg``, ``s_rejected``, ``s_total``, and signed
``heading_error_rad``. B0 rows also need matched ``dr_heading_error_rad``.
Optional ``path``/``phase`` enable descriptive strata; optional
``heading_error_signed_rad`` or ``heading_miss_direction`` summarizes miss
direction; optional ``checkpoint_order`` yields continuous-miss run lengths.

The bootstrap fixes the observed case strata, resamples sites with replacement
within each case, then resamples the common seed set with replacement. All
checkpoints in a selected site/seed cell stay together. B0 primary/DR RMSE uses
the same weighted rows, so its ratio interval is paired. This module consumes
metrics only; it does not generate motion/RF data or calculate an estimator.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from typing import Iterable, Mapping

import numpy as np


BOOTSTRAP_REPLICATES = 2000
CONFIDENCE = 0.95
NEES_LIMITS = (0.5, 2.0)
HEADING_COVERAGE_MIN = 0.92
HEADING_COVERAGE_UPPER_MIN = 0.95
CASE_COVERAGE_UPPER_FLOOR = 0.80
S_REJECTION_MAX = 0.20
B0_RMSE_RATIO_UPPER_MAX = 1.10
ARM_ORDER = {"J-V": 0, "J-C": 1, "J-CS": 2, "J-CI": 3}
REQUIRED_FIELDS = {
    "case", "level", "sign", "seed", "site_id", "checkpoint_id",
    "heading_included", "xy_included", "nees_heading", "nees_xy_normalized",
    "nees_bg", "s_rejected", "s_total", "heading_error_rad",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _finite_number(value, name: str, *, nonnegative: bool = False) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    _require(math.isfinite(result), f"{name} must be finite")
    if nonnegative:
        _require(result >= 0.0, f"{name} must be nonnegative")
    return result


def _validate_rows(rows: Iterable[Mapping], *, require_b0_pair: bool = True) -> list[dict]:
    result = []
    seen = set()
    for raw in rows:
        row = dict(raw)
        missing = REQUIRED_FIELDS - row.keys()
        _require(not missing, f"Missing integrity row fields: {sorted(missing)}")
        for key in ("case", "level", "sign", "seed", "site_id", "checkpoint_id"):
            _require(row[key] is not None, f"Null integrity key: {key}")
        key = tuple(row[k] for k in ("case", "level", "sign", "seed", "site_id", "checkpoint_id"))
        _require(key not in seen, f"Duplicate integrity row key: {key}")
        seen.add(key)
        for field in ("heading_included", "xy_included"):
            _require(isinstance(row[field], (bool, np.bool_)), f"{field} must be boolean")
            row[field] = bool(row[field])
        for field in ("nees_heading", "nees_xy_normalized", "nees_bg"):
            row[field] = _finite_number(row[field], field, nonnegative=True)
        row["s_rejected"] = _finite_number(row["s_rejected"], "s_rejected", nonnegative=True)
        row["s_total"] = _finite_number(row["s_total"], "s_total", nonnegative=True)
        _require(row["s_rejected"] <= row["s_total"], "s_rejected exceeds s_total")
        row["heading_error_rad"] = _finite_number(row["heading_error_rad"], "heading_error_rad")
        if str(row["level"]).upper() == "B0" and require_b0_pair:
            _require("dr_heading_error_rad" in row, "B0 requires paired DR heading errors")
            row["dr_heading_error_rad"] = _finite_number(row["dr_heading_error_rad"], "dr_heading_error_rad")
        if "heading_error_signed_rad" in row:
            row["heading_error_signed_rad"] = _finite_number(row["heading_error_signed_rad"],
                                                               "heading_error_signed_rad")
        if "checkpoint_order" in row:
            row["checkpoint_order"] = _finite_number(row["checkpoint_order"], "checkpoint_order")
        if "heading_miss_direction" in row:
            _require(row["heading_miss_direction"] in ("above", "below", "+", "-", "positive", "negative", None),
                     "heading_miss_direction must be above/below or signed")
        result.append(row)
    _require(bool(result), "No integrity rows")
    return result


def _prepare_level(rows: list[dict]):
    cases = sorted({str(row["case"]) for row in rows})
    seeds = sorted({row["seed"] for row in rows}, key=str)
    _require(len(cases) >= 1 and len(seeds) >= 2, "Need cases and at least two independent sensor seeds")
    by_case = defaultdict(list)
    cells = defaultdict(list)
    for i, row in enumerate(rows):
        case, seed, site = str(row["case"]), row["seed"], row["site_id"]
        by_case[case].append(i)
        cells[(case, seed, site)].append(i)
    sites_by_case = {case: sorted({rows[i]["site_id"] for i in indices}, key=str)
                     for case, indices in by_case.items()}
    require_seed_sets = {case: {seed for c, seed, _ in cells if c == case} for case in cases}
    _require(all(seed_set == set(seeds) for seed_set in require_seed_sets.values()),
             "Every case must contain the same resampled seed set")
    for case, sites in sites_by_case.items():
        for seed in seeds:
            for site in sites:
                _require((case, seed, site) in cells,
                         f"Incomplete case/seed/site crossing: {case}/{seed}/{site}")
    case_index = {case: i for i, case in enumerate(cases)}
    seed_index = {seed: i for i, seed in enumerate(seeds)}
    site_indices = {case: {site: i for i, site in enumerate(sites)} for case, sites in sites_by_case.items()}
    row_case = np.asarray([case_index[str(row["case"])] for row in rows], dtype=np.int64)
    row_seed = np.asarray([seed_index[row["seed"]] for row in rows], dtype=np.int64)
    row_site = np.asarray([site_indices[str(row["case"])][row["site_id"]] for row in rows], dtype=np.int64)
    return cases, seeds, sites_by_case, row_case, row_seed, row_site


def _row_values(rows):
    arrays = {
        "heading_coverage": np.asarray([row["heading_included"] for row in rows], dtype=np.float64),
        "xy_coverage": np.asarray([row["xy_included"] for row in rows], dtype=np.float64),
        "nees_heading": np.asarray([row["nees_heading"] for row in rows], dtype=np.float64),
        "nees_xy": np.asarray([row["nees_xy_normalized"] for row in rows], dtype=np.float64),
        "nees_bg": np.asarray([row["nees_bg"] for row in rows], dtype=np.float64),
        "s_rejected": np.asarray([row["s_rejected"] for row in rows], dtype=np.float64),
        "s_total": np.asarray([row["s_total"] for row in rows], dtype=np.float64),
        "heading_sq": np.asarray([row["heading_error_rad"] ** 2 for row in rows], dtype=np.float64),
    }
    if all("dr_heading_error_rad" in row for row in rows):
        arrays["dr_heading_sq"] = np.asarray([row["dr_heading_error_rad"] ** 2 for row in rows], dtype=np.float64)
    return arrays


def _weighted_statistics(values, weights):
    total = float(weights.sum())
    _require(total > 0.0, "Bootstrap produced an empty weighted sample")
    result = {name: float(np.dot(values[name], weights) / total)
              for name in ("heading_coverage", "xy_coverage", "nees_heading", "nees_xy", "nees_bg")}
    s_total = float(np.dot(values["s_total"], weights))
    _require(s_total > 0.0, "No s packets in weighted sample")
    result["s_rejection_rate"] = float(np.dot(values["s_rejected"], weights) / s_total)
    result["heading_rmse_rad"] = math.sqrt(max(0.0, float(np.dot(values["heading_sq"], weights) / total)))
    if "dr_heading_sq" in values:
        dr_rmse = math.sqrt(max(0.0, float(np.dot(values["dr_heading_sq"], weights) / total)))
        _require(dr_rmse > 0.0, "Paired DR heading RMSE must be positive for B0 ratio")
        result["dr_heading_rmse_rad"] = dr_rmse
        result["b0_rmse_ratio"] = result["heading_rmse_rad"] / dr_rmse
    return result


def _bootstrap(rows: list[dict], *, bootstrap_seed: int, replicates: int):
    cases, seeds, sites_by_case, row_case, row_seed, row_site = _prepare_level(rows)
    values = _row_values(rows)
    rng = np.random.default_rng(int(bootstrap_seed))
    n_case, n_seed = len(cases), len(seeds)
    n_site = np.asarray([len(sites_by_case[c]) for c in cases], dtype=np.int64)
    draws = {name: np.empty(replicates, dtype=np.float64) for name in (
        "heading_coverage", "xy_coverage", "nees_heading", "nees_xy", "nees_bg", "s_rejection_rate",
        "heading_rmse_rad")}
    paired = "dr_heading_sq" in values
    if paired:
        draws["dr_heading_rmse_rad"] = np.empty(replicates, dtype=np.float64)
        draws["b0_rmse_ratio"] = np.empty(replicates, dtype=np.float64)
    for b in range(replicates):
        seed_counts = np.bincount(rng.integers(n_seed, size=n_seed), minlength=n_seed)
        site_counts = np.zeros((n_case, int(n_site.max())), dtype=np.int64)
        for c in range(n_case):
            site_counts[c, :n_site[c]] = np.bincount(
                rng.integers(int(n_site[c]), size=int(n_site[c])), minlength=int(n_site[c]))
        weights = site_counts[row_case, row_site] * seed_counts[row_seed]
        stat = _weighted_statistics(values, weights.astype(np.float64))
        for name in draws:
            draws[name][b] = stat[name]
    point = _weighted_statistics(values, np.ones(len(rows), dtype=np.float64))
    alpha = (1.0 - CONFIDENCE) / 2.0
    intervals = {name: [float(np.quantile(sample, alpha)), float(np.quantile(sample, 1.0-alpha))]
                 for name, sample in draws.items()}
    return point, intervals


def _metrics(rows, seed, replicates):
    point, ci = _bootstrap(rows, bootstrap_seed=seed, replicates=replicates)
    return dict(point=point, ci95=ci)


def _path_descriptives(rows):
    if not any("path" in row or "phase" in row for row in rows):
        return {}
    groups = defaultdict(list)
    for row in rows:
        groups[(str(row["case"]), str(row.get("phase", "")), str(row.get("path", "")))].append(row)
    output = {}
    for (case, phase, path), group in sorted(groups.items()):
        key = f"{case}|{phase}|{path}"
        heading_misses = [row for row in group if not row["heading_included"]]
        xy_misses = [row for row in group if not row["xy_included"]]
        direction_counts = {"above": 0, "below": 0, "unknown": 0}
        for row in heading_misses:
            direction = row.get("heading_miss_direction")
            if direction in ("above", "+", "positive"):
                direction_counts["above"] += 1
            elif direction in ("below", "-", "negative"):
                direction_counts["below"] += 1
            elif "heading_error_signed_rad" in row:
                direction_counts["above" if row["heading_error_signed_rad"] > 0 else "below"] += 1
            else:
                direction_counts["unknown"] += 1
        run_max = None
        ordered_groups = defaultdict(list)
        for row in group:
            if "checkpoint_order" in row:
                ordered_groups[(row["seed"], row.get("sign"))].append(row)
        if ordered_groups:
            run_max = 0
            for sequence in ordered_groups.values():
                sequence.sort(key=lambda row: row["checkpoint_order"])
                run = 0
                for row in sequence:
                    run = run + 1 if not row["heading_included"] else 0
                    run_max = max(run_max, run)
        output[key] = dict(
            checkpoints=len(group),
            heading_coverage=float(np.mean([row["heading_included"] for row in group])),
            xy_coverage=float(np.mean([row["xy_included"] for row in group])),
            nees_heading_mean=float(np.mean([row["nees_heading"] for row in group])),
            nees_xy_normalized_mean=float(np.mean([row["nees_xy_normalized"] for row in group])),
            nees_bg_mean=float(np.mean([row["nees_bg"] for row in group])),
            s_rejection_rate=(sum(row["s_rejected"] for row in group) /
                              max(1.0, sum(row["s_total"] for row in group))),
            directional_heading_misses=direction_counts,
            xy_misses=len(xy_misses),
            maximum_continuous_heading_miss_checkpoints=run_max,
        )
    return output


def evaluate_integrity(rows: Iterable[Mapping], *, bootstrap_seed: int,
                       bootstrap_replicates: int = BOOTSTRAP_REPLICATES) -> dict:
    """Evaluate §4 B-mode integrity by level using the two-level cluster bootstrap.

    A pooled level report passes when heading coverage point estimate is at
    least 0.92, its 95% upper bound at least 0.95, all three mean NEES values
    are in [0.5, 2], the pooled s rejection rate is at most 0.20, every
    case-level heading and XY coverage upper bound is at least 0.80, and (for
    B0) the paired primary/DR heading RMSE ratio 95% upper bound is at most
    1.10. The source contract specifies the upper-bound tests as written.
    """
    _require(isinstance(bootstrap_seed, (int, np.integer)), "bootstrap_seed must be an integer")
    _require(bootstrap_replicates == BOOTSTRAP_REPLICATES,
             "SPEC_B freezes exactly 2,000 bootstrap replicates")
    validated = _validate_rows(rows)
    levels = sorted({str(row["level"]) for row in validated})
    output_levels = {}
    for level_index, level in enumerate(levels):
        level_rows = [row for row in validated if str(row["level"]) == level]
        metrics = _metrics(level_rows, int(bootstrap_seed) + level_index * 1000003, bootstrap_replicates)
        cases = {}
        for case_index, case in enumerate(sorted({str(row["case"]) for row in level_rows})):
            subset = [row for row in level_rows if str(row["case"]) == case]
            cases[case] = _metrics(subset, int(bootstrap_seed) + (level_index+1)*1000003 + case_index*9176,
                                   bootstrap_replicates)
        point, ci = metrics["point"], metrics["ci95"]
        case_severe = {case: (cases[case]["ci95"]["heading_coverage"][1] < CASE_COVERAGE_UPPER_FLOOR
                              or cases[case]["ci95"]["xy_coverage"][1] < CASE_COVERAGE_UPPER_FLOOR)
                       for case in cases}
        nees_pass = all(NEES_LIMITS[0] <= point[key] <= NEES_LIMITS[1]
                        for key in ("nees_heading", "nees_xy", "nees_bg"))
        b0_ratio = ci.get("b0_rmse_ratio")
        b0_pass = True
        if level.upper() == "B0":
            b0_pass = b0_ratio is not None and b0_ratio[1] <= B0_RMSE_RATIO_UPPER_MAX
        gates = dict(
            pooled_heading_coverage_point=point["heading_coverage"] >= HEADING_COVERAGE_MIN,
            pooled_heading_coverage_ci_upper=ci["heading_coverage"][1] >= HEADING_COVERAGE_UPPER_MIN,
            mean_nees=nees_pass,
            no_case_severe_failure=not any(case_severe.values()),
            pooled_s_rejection=point["s_rejection_rate"] <= S_REJECTION_MAX,
            b0_heading_noninferiority=b0_pass,
        )
        output_levels[level] = dict(
            status="PASS" if all(gates.values()) else "FAIL",
            bootstrap=dict(method="case-stratified site resampling then common-seed resampling",
                           replicates=bootstrap_replicates, seed=int(bootstrap_seed) + level_index*1000003,
                           confidence=CONFIDENCE),
            pooled=metrics,
            cases=cases,
            case_severe_failure=case_severe,
            gates=gates,
            path_descriptives=_path_descriptives(level_rows),
        )
    return dict(question_id="G1-MODEL-003", method="B", status=(
        "PASS" if all(item["status"] == "PASS" for item in output_levels.values()) else "FAIL"),
        levels=output_levels, pairing_keys=[
            [row["case"], row["level"], row["sign"], row["seed"], row["site_id"], row["checkpoint_id"]]
            for row in validated],
        thresholds=dict(heading_coverage_point_min=HEADING_COVERAGE_MIN,
                        heading_coverage_ci_upper_min=HEADING_COVERAGE_UPPER_MIN,
                        case_coverage_ci_upper_floor=CASE_COVERAGE_UPPER_FLOOR,
                        nees_mean_limits=list(NEES_LIMITS), s_rejection_max=S_REJECTION_MAX,
                        b0_rmse_ratio_ci_upper_max=B0_RMSE_RATIO_UPPER_MAX,
                        bootstrap_replicates=bootstrap_replicates))


def _arm_simplicity(arm: str):
    label = str(arm)
    parts = label.split("+")
    base = parts[0]
    _require(base in ARM_ORDER and set(parts[1:]).issubset({"K"}) and len(parts) <= 2,
             f"Unknown S3 arm name: {arm}")
    return ARM_ORDER[base] * 2 + int("K" in parts[1:])


def select_primary_arm(candidates: Mapping[str, Mapping], required_levels: Iterable[str], *,
                       tie_tolerance_deg: float = 0.1) -> dict:
    """Apply the frozen LOAO integrity-then-L1-RMSE S3 selection rule.

    ``candidates`` maps each arm to ``{"integrity": report,
    "l1_pooled_heading_rmse_deg": float}``. The integrity report is from
    :func:`evaluate_integrity` on its LOAO rows.
    """
    required = tuple(map(str, required_levels))
    _require(bool(required), "required_levels must be nonempty")
    _require(_finite_number(tie_tolerance_deg, "tie_tolerance_deg", nonnegative=True) == 0.1,
             "SPEC_B freezes the tie window at 0.1 degrees")
    evaluated = {}
    eligible = []
    for arm, candidate in candidates.items():
        _arm_simplicity(arm)
        integrity = candidate.get("integrity", {})
        levels = integrity.get("levels", {})
        level_pass = {level: levels.get(level, {}).get("status") == "PASS" for level in required}
        rmse = _finite_number(candidate.get("l1_pooled_heading_rmse_deg"),
                              f"{arm}.l1_pooled_heading_rmse_deg", nonnegative=True)
        valid = all(level_pass.values())
        evaluated[arm] = dict(integrity_pass_by_level=level_pass, integrity_eligible=valid,
                              l1_pooled_heading_rmse_deg=rmse,
                              simplicity_rank=_arm_simplicity(arm))
        if valid:
            eligible.append(arm)
    if not eligible:
        return dict(question_id="G1-MODEL-003", stage="S3", status="DEV_FAIL",
                    selected_arm=None, candidates=evaluated,
                    rule="No arm passed §4 integrity at every required LOAO bias level; keep seal closed.")
    best_rmse = min(evaluated[arm]["l1_pooled_heading_rmse_deg"] for arm in eligible)
    tied = [arm for arm in eligible
            if evaluated[arm]["l1_pooled_heading_rmse_deg"] - best_rmse < tie_tolerance_deg]
    selected = min(tied, key=lambda arm: (_arm_simplicity(arm),
                                          evaluated[arm]["l1_pooled_heading_rmse_deg"], arm))
    return dict(question_id="G1-MODEL-003", stage="S3", status="PASS", selected_arm=selected,
                eligible_arms=sorted(eligible), best_l1_heading_rmse_deg=best_rmse,
                tie_set=sorted(tied), candidates=evaluated,
                rule="Pass §4 at all required LOAO levels; minimize pooled L1 heading RMSE; among arms <0.1° from best choose the simplest. Base order J-V < J-C < J-CS < J-CI; +K adds complexity.")


def synthetic_self_check() -> dict:
    """Deterministic metric/selection smoke check using synthetic rows only."""
    rows = []
    for case_index, case in enumerate(("G-T1_A", "G-T1_B", "G-T1_C")):
        for level in ("B0", "L0", "L1", "L2"):
            for seed in range(8):
                for site in range(4):
                    for checkpoint in range(2):
                        include_heading = (seed + site + checkpoint) % 20 != 0
                        include_xy = (seed + 2*site + checkpoint) % 20 != 0
                        rows.append(dict(
                            case=case, level=level, sign="+" if seed % 2 else "-", seed=seed,
                            site_id=f"{case}-site-{site}", checkpoint_id=f"{checkpoint}",
                            path="P-C", phase="sweep", checkpoint_order=checkpoint,
                            heading_included=include_heading, xy_included=include_xy,
                            nees_heading=1.0+0.01*case_index, nees_xy_normalized=1.05,
                            nees_bg=0.95, s_rejected=1 if checkpoint == 0 else 0, s_total=5,
                            heading_error_rad=0.05+0.001*case_index,
                            dr_heading_error_rad=0.05 if level == "B0" else 0.06,
                            heading_error_signed_rad=(-1)**checkpoint * 0.05,
                            heading_miss_direction="above" if not include_heading and checkpoint else None,
                        ))
    first = evaluate_integrity(rows, bootstrap_seed=271828)
    second = evaluate_integrity(rows, bootstrap_seed=271828)
    _require(first == second, "Synthetic bootstrap is not deterministic")
    _require(first["status"] == "PASS", "Synthetic integrity fixture should pass")
    _require(first["levels"]["B0"]["gates"]["b0_heading_noninferiority"],
             "Synthetic paired B0 noninferiority should pass")
    _require(all(row["directional_heading_misses"] for row in first["levels"]["B0"]["path_descriptives"].values()),
             "Synthetic directional miss report missing")
    integrity = {"levels": {level: {"status": "PASS"} for level in ("B0", "L0", "L1", "L2")}}
    selection = select_primary_arm({
        "J-V": {"integrity": integrity, "l1_pooled_heading_rmse_deg": 1.00},
        "J-C": {"integrity": integrity, "l1_pooled_heading_rmse_deg": 0.95},
        "J-CS": {"integrity": integrity, "l1_pooled_heading_rmse_deg": 1.20},
    }, ("B0", "L0", "L1", "L2"))
    _require(selection["selected_arm"] == "J-V", "Simplicity tie-break is incorrect")
    _require(select_primary_arm({"J-V": {"integrity": {"levels": {}},
                                         "l1_pooled_heading_rmse_deg": 0.5},
                                }, ("B0",))["status"] == "DEV_FAIL",
             "No-candidate case must produce DEV_FAIL")
    return dict(status="PASS", synthetic_rows=len(rows), levels=list(first["levels"]),
                selected_arm=selection["selected_arm"], b0_rmse_ratio_ci95=first["levels"]["B0"]["pooled"]["ci95"]["b0_rmse_ratio"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="Run synthetic-only metric checks")
    args = parser.parse_args()
    if not args.self_check:
        parser.error("This helper has no RF-data CLI; call its Python API or use --self-check")
    result = synthetic_self_check()
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
