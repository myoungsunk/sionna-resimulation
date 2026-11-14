"""Validate and summarize G1-MODEL-003 S3 G-T1 fold receipts."""

import argparse
from collections import defaultdict
import hashlib
import itertools
import json
import math
from pathlib import Path
import re

import numpy as np

from tb3_model003_integrity import ARM_ORDER, BOOTSTRAP_REPLICATES, evaluate_integrity, select_primary_arm
from tb3_model003_motion import BIAS_DEG_PER_S, DEFAULT_SEEDS, SIGNS, TB3_SCALE


CASES = ("G-T1_A", "G-T1_B", "G-T1_C")
PATHS = ("TEACH_REPEAT", "P-B", "C1", "C2", "C3", "C4")
LEVELS = (*BIAS_DEG_PER_S, *TB3_SCALE)
CANDIDATES = (*ARM_ORDER, *(f"{arm}+K" for arm in ARM_ORDER))
BASELINES = ("DR", "R4", "J4", "J4+K")
BOOTSTRAP_SEED = 20261118
PAIR_FIELDS = ("case", "path", "level", "site_id", "checkpoint_id", "checkpoint_order", "phase", "seed", "sign")
HASH = re.compile(r"[a-f0-9]{64}")
NUMERIC_LOG = re.compile(r"LinAlgError|FloatingPointError|OverflowError|non.?finite|positive.definite|quadrature distance", re.I)


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _check(condition, message):
    if not condition:
        raise ValueError(message)


def _row_key(row):
    return tuple(row[key] for key in PAIR_FIELDS)


def _source_identity(receipt):
    keys = ("s1_sha256", "parity_sha256", "s2_sha256", "timeline_sha256", "source_file_sha256")
    identity = {key: receipt[key] for key in keys}
    _check(all(isinstance(digest, str) and HASH.fullmatch(digest) for digest in identity.values()), "Invalid source SHA")
    for key in ("source_sha256", "banks_sha256"):
        digests = receipt[key]
        _check(bool(digests) and all(isinstance(digest, str) and HASH.fullmatch(digest)
                                     for digest in digests.values()), f"Invalid {key}")
        identity[key] = digests
    return identity


def _load_receipt(file, key):
    case, path, level, arm, snr = key
    raw = file.read_bytes()
    receipt = json.loads(raw)
    expected = dict(case=case, path=path, level=level, arm=arm, snr=snr,
                    question_id="G1-MODEL-003", or_rule="O30", train_anchors="".join(a for a in "ABC" if a != case[-1]))
    _check(all(receipt[k] == v for k, v in expected.items()), "Unexpected fold identity")
    identity = _source_identity(receipt)
    record = dict(identity=identity, sha256=_digest(raw), paired_dr_sha256=receipt["paired_dr_sha256"],
                  status=receipt["status"])
    if receipt["status"] == "NUMERICAL_FAIL":
        _check(isinstance(receipt["reason"], str) and bool(receipt["reason"]), "Missing numerical failure reason")
        return record | dict(reason=receipt["reason"])
    _check(receipt["status"] == "PASS", f"Fold execution status {receipt['status']}")
    rows = receipt["receipt_rows"]
    _check(isinstance(rows, list) and bool(rows), "No checkpoint rows")
    slots = defaultdict(set)
    normalized = {}
    index_fields = ("seed", "sign", "checkpoint_id", "checkpoint_order", "s_total", "s_rejected", "s_unavailable")
    float_fields = ("heading_error_rad", "xy_error_m", "dr_heading_error_rad", "nees_heading", "nees_xy_normalized", "nees_bg")
    s_totals = defaultdict(int)
    for row in rows:
        _check(all(row[k] == expected[k] for k in ("case", "path", "level", "arm")), "Checkpoint fold identity differs")
        _check(all(type(row[k]) is int for k in index_fields), "Checkpoint counters and IDs must be integers")
        if any(type(row[k]) not in (int, float) or not math.isfinite(row[k]) for k in float_fields):
            raise FloatingPointError("Nonfinite or invalid numeric checkpoint fields")
        if (min(row[k] for k in ("xy_error_m", "nees_heading", "nees_xy_normalized", "nees_bg")) < 0
                or max(abs(row[k]) for k in ("heading_error_rad", "dr_heading_error_rad")) > math.pi
                or row["xy_error_m"] > 1e150):
            raise FloatingPointError("Invalid NEES or error magnitude")
        _check(all(type(row[k]) is bool for k in ("heading_included", "xy_included")), "Coverage flags must be boolean")
        _check(row["heading_included"] == (row["nees_heading"] <= 3.841458820694124)
               and row["xy_included"] == (row["nees_xy_normalized"] <= 5.991464547107979 / 2),
               "Coverage flags disagree with checkpoint NEES")
        _check(0 <= row["s_unavailable"] <= row["s_rejected"] <= row["s_total"], "Impossible s packet counts")
        _check(row["checkpoint_order"] >= 0 and row["checkpoint_id"] >= 0
               and isinstance(row["site_id"], str) and row["site_id"].startswith(path + "/")
               and isinstance(row["phase"], str) and row["phase"], "Invalid checkpoint metadata")
        pair = _row_key(row)
        _check(pair not in normalized, "Duplicate checkpoint/seed/sign row")
        slots[pair[:-2]].add(pair[-2:])
        s_totals[pair[-2:]] += row["s_total"]
        normalized[pair] = row | {"heading_error_signed_rad": row["heading_error_rad"]}
    expected_runs = set(itertools.product(DEFAULT_SEEDS, SIGNS))
    _check(all(runs == expected_runs for runs in slots.values()), "Incomplete checkpoint seed/sign grid")
    _check(len({slot[4] for slot in slots}) == len({slot[5] for slot in slots}) == len(slots),
           "Checkpoint identities and chronological order must be one-to-one")
    s_counts = list(s_totals.values())
    _check(len(set(s_counts)) == 1 and (s_counts[0] == 0 if arm in ("DR", "R4") else s_counts[0] > 0),
           "s packet counts incomplete across runs or inconsistent with arm")
    contributions = receipt["contributions"]
    for phase, counts in contributions.items():
        _check(phase in ("move", "sweep") and len(counts) == 3
               and all(type(n) in (int, float) and math.isfinite(n) and n >= 0 for n in counts)
               and counts[1] <= counts[0], "Invalid move/sweep contributions")
    _check(sum(c[0] for c in contributions.values()) == sum(row["s_total"] for row in rows)
           and sum(c[1] for c in contributions.values()) == sum(row["s_total"] - row["s_rejected"] for row in rows),
           "Move/sweep counts disagree with checkpoint accounting")
    return record | dict(rows=normalized, contributions=contributions)


def _fold_file(root, snr, case, path, level, arm):
    return root / str(snr) / f"{case}_{path}_{level}_{arm}.json"


def _missing_status(log):
    if log is not None and log.is_file():
        with log.open("rb") as stream:
            stream.seek(max(0, log.stat().st_size - 8192))
            lines = stream.read().decode("utf-8", errors="replace").strip().splitlines()
        if lines and NUMERIC_LOG.search("\n".join(lines)):
            return dict(status="NUMERIC_FAILURE", detail=lines[-1])
        if lines and any("Traceback" in line for line in lines):
            return dict(status="EXECUTION_FAILURE", detail=lines[-1])
    return dict(status="MISSING", detail="No completed fold receipt")


def _load_group(root, logs, snr, level, arm, identity, dr=None):
    records, failures = {}, {}
    for case, path in itertools.product(CASES, PATHS):
        file = _fold_file(root, snr, case, path, level, arm)
        try:
            record = _load_receipt(file, (case, path, level, arm, snr))
            _check(record["identity"] == identity.setdefault("source", record["identity"]), "Fold source/frozen input SHA differs")
            if dr is None:
                _check(record["paired_dr_sha256"] is None, "DR receipt is itself paired to a DR receipt")
            elif (case, path) not in dr:
                failures[f"{case}/{path}"] = dict(status="UNPAIRED_DR", detail="Matching DR fold unavailable")
                continue
            else:
                base = dr[case, path]
                _check(record["paired_dr_sha256"] == base["sha256"], "Matching DR receipt SHA differs")
            if record["status"] == "NUMERICAL_FAIL":
                failures[f"{case}/{path}"] = dict(status="NUMERICAL_FAIL", detail=record["reason"], sha256=record["sha256"])
                continue
            if dr is not None:
                _check(record["rows"].keys() == base["rows"].keys(), "Checkpoint identities do not match paired DR")
                _check(all(row["dr_heading_error_rad"] == base["rows"][key]["heading_error_rad"]
                           for key, row in record["rows"].items()), "Paired DR heading errors disagree")
            records[case, path] = record
        except FileNotFoundError:
            log = _fold_file(logs, snr, case, path, level, arm).with_suffix(".log") if logs else None
            failures[f"{case}/{path}"] = _missing_status(log)
        except FloatingPointError as exc:
            failures[f"{case}/{path}"] = dict(status="NUMERIC_FAILURE", detail=str(exc))
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            failures[f"{case}/{path}"] = dict(status="INVALID_RECEIPT", detail=str(exc))
    return records, failures


def _stats(rows):
    count = len(rows)
    result = {name: math.fsum(row[key] for row in rows) / count for name, key in (
        ("heading_coverage", "heading_included"), ("xy_coverage", "xy_included"), ("nees_heading", "nees_heading"),
        ("nees_xy_normalized", "nees_xy_normalized"), ("nees_bg", "nees_bg"),
    )}
    result.update(rows=count, heading_rmse_deg=math.degrees(math.sqrt(math.fsum(r["heading_error_rad"]**2 for r in rows)/count)),
                  xy_rmse_m=math.sqrt(math.fsum(r["xy_error_m"]**2 for r in rows)/count))
    return result


def _rows(records):
    return [row for record in records.values() for row in record["rows"].values()]


def _logit_sd(rows, level):
    """DerSimonian–Laird tau on logits using cluster-bootstrap variances."""
    records = {}
    level_index = sorted(LEVELS).index(level)
    for i, case in enumerate(CASES):
        cells = defaultdict(list)
        for row in rows:
            if row["case"] == case:
                cells[row["seed"], row["site_id"]].append(row["heading_included"])
        sites = sorted({site for _, site in cells})
        successes = np.asarray([[sum(cells[seed, site]) for site in sites] for seed in DEFAULT_SEEDS])
        count = np.asarray([[len(cells[seed, site]) for site in sites] for seed in DEFAULT_SEEDS])
        rng = np.random.default_rng(BOOTSTRAP_SEED + (level_index + 1)*1000003 + i*9176)
        logits, rates = [], []
        for _ in range(BOOTSTRAP_REPLICATES):
            seed_counts = np.bincount(rng.integers(len(DEFAULT_SEEDS), size=len(DEFAULT_SEEDS)), minlength=len(DEFAULT_SEEDS))
            site_counts = np.bincount(rng.integers(len(sites), size=len(sites)), minlength=len(sites))
            included = int(seed_counts @ successes @ site_counts)
            total = int(seed_counts @ count @ site_counts)
            # Half-count correction only for boundary samples keeps logits finite.
            probability = (included + 0.5) / (total + 1) if included in (0, total) else included / total
            rates.append(probability)
            logits.append(math.log(probability / (1 - probability)))
        total, included = int(count.sum()), int(successes.sum())
        p = (included + 0.5) / (total + 1) if included in (0, total) else included / total
        variance = float(np.var(logits, ddof=1))
        rate_variance = float(np.var(rates, ddof=1))
        effective_n = None if rate_variance < 1e-18 else min(total, p*(1-p)/rate_variance)
        records[case] = dict(heading_coverage=included/total, logit=math.log(p/(1-p)),
                             logit_bootstrap_variance=variance, heading_coverage_effective_n=effective_n)
    variances = np.asarray([r["logit_bootstrap_variance"] for r in records.values()])
    logit = np.asarray([r["logit"] for r in records.values()])
    method = "DerSimonian–Laird tau with site/seed bootstrap on logits and half-count boundary correction"
    if (variances < 1e-18).any():
        return dict(method=method, status="NOT_EVALUABLE", detail="Degenerate case logit bootstrap variance",
                    case_logit_random_effect_sd=None, cases=records)
    weight = 1 / variances
    mu = np.average(logit, weights=weight)
    q = float(np.sum(weight * (logit - mu)**2))
    denominator = float(weight.sum() - np.sum(weight**2)/weight.sum())
    tau = math.sqrt(max(0.0, (q - (len(weight)-1)) / denominator))
    return dict(method=method, status="EVALUATED", case_logit_random_effect_sd=tau, cases=records)


def _scope(futility):
    _check(futility["status"] == "PASS" and futility["question_id"] == "G1-MODEL-003"
           and futility["governing_chain"] == "OR", "Expected frozen S2-F scope")
    or_chain = futility["chains"]["OR"]
    _check(or_chain["rule"] == futility["chains"]["O30"]["rule"] == "O30", "S3 requires the frozen OR == O30 chain")
    result = {path: {level: or_chain["paths"][path]["levels"][level]["accuracy_scope"] for level in LEVELS} for path in PATHS}
    _check(all(scope in ("INCLUDE", "EXCLUDE", "NOT_EVALUABLE") for path in result.values() for scope in path.values())
           and "INCLUDE" not in result["P-B"].values(), "Invalid frozen S2-F scope values")
    return result


def _paired_path(records, dr, r4, scope, level):
    result = {}
    for path in PATHS:
        if scope[path][level] != "INCLUDE":
            result[path] = dict(status=scope[path][level])
            continue
        datasets = []
        for arm_records in (records, dr, r4):
            if all((c, path) in arm_records for c in CASES):
                datasets.append(_rows({(c, path): arm_records[c, path] for c in CASES}))
        if len(datasets) != 3:
            result[path] = dict(status="INCOMPLETE_PAIRING")
            continue
        result[path] = dict(status="PAIRED_DEVELOPMENT_DESCRIPTIVE", by_sign={})
        for sign in SIGNS:
            arm, dr_stats, r4_stats = [_stats([row for row in rows if row["sign"] == sign]) for rows in datasets]
            result[path]["by_sign"][str(sign)] = dict(
                arm=arm, DR=dr_stats, R4=r4_stats,
                heading_delta_vs_dr_deg=arm["heading_rmse_deg"] - dr_stats["heading_rmse_deg"],
                heading_delta_vs_r4_deg=arm["heading_rmse_deg"] - r4_stats["heading_rmse_deg"],
                xy_delta_vs_dr_m=arm["xy_rmse_m"] - dr_stats["xy_rmse_m"],
                xy_delta_vs_r4_m=arm["xy_rmse_m"] - r4_stats["xy_rmse_m"],
            )
    return result


def summarize(folds, *, snr=30, futility=None, logs=None, partial=False):
    """Return complete §4 selection or a non-adopting, B0-only status snapshot."""
    _check(snr in (20, 30), "Expected 20 or 30 dB SNR")
    _check(partial or futility is not None, "Complete summaries require frozen S2-F scope")
    scope = _scope(futility) if futility is not None else None
    identity = {}
    levels = ("B0",) if partial else LEVELS
    arms = ("DR", *CANDIDATES) if partial else (*BASELINES, *CANDIDATES)
    findings = {arm: {} for arm in arms}
    receipt_shas = {}
    for level in levels:
        dr, r4 = {}, {}
        for arm in arms:
            records, failures = _load_group(folds, logs, snr, level, arm, identity, dr=None if arm == "DR" else dr)
            if arm == "DR":
                dr = records
            elif arm == "R4":
                r4 = records
            receipt_shas.update({str(_fold_file(Path("."), snr, c, p, level, arm).as_posix()): v["sha256"]
                                 for (c, p), v in records.items()})
            info = dict(status="INCOMPLETE", folds_valid=len(records), fold_issues=failures)
            findings[arm][level] = info
            terminal = {key: v for key, v in failures.items() if v["status"] == "NUMERICAL_FAIL"}
            for name, issue in terminal.items():
                case, path = name.split("/")
                receipt_shas[_fold_file(Path("."), snr, case, path, level, arm).as_posix()] = issue["sha256"]
            if failures:
                if failures == terminal:
                    info["status"] = "NUMERICAL_FAIL"
                if scope is not None and not partial and arm not in ("DR", "R4"):
                    info["paired_accuracy"] = _paired_path(records, dr, r4, scope, level)
                continue
            rows = _rows(records)
            if arm in ("DR", "R4"):
                info.update(status="BASELINE", pooled=_stats(rows),
                            cases={case: _stats([row for row in rows if row["case"] == case]) for case in CASES})
                continue
            # Match the frozen helper's level-specific seed in isolated calls.
            seed = BOOTSTRAP_SEED + sorted(LEVELS).index(level) * 1000003
            try:
                assessed = evaluate_integrity(rows, bootstrap_seed=seed)["levels"][level]
            except (ValueError, ArithmeticError) as exc:
                info.update(status="NOT_EVALUABLE", metric_error=str(exc))
                continue
            info.update(status=assessed["status"], integrity=assessed,
                        gate_counts=dict(s_total=sum(r["s_total"] for r in rows),
                                         s_unavailable=sum(r["s_unavailable"] for r in rows),
                                         s_rejected=sum(r["s_rejected"] for r in rows)),
                        contributions_by_fold={f"{c}/{p}": v["contributions"] for (c, p), v in records.items()})
            if scope is not None and not partial:
                info["paired_accuracy"] = _paired_path(records, dr, r4, scope, level)
                info["heading_logit_heterogeneity"] = _logit_sd(rows, level)

    if futility is not None and "source" in identity:
        src = identity["source"]
        _check(src["timeline_sha256"] == futility["timeline_sha256"]
               and src["s1_sha256"] == futility["s1_receipts_sha256"]["RANGING_RULE_SELECTION.json"]
               and src["parity_sha256"] == futility["s1_receipts_sha256"]["PARITY.json"]
               and src["source_sha256"] == futility["source_sha256"] and src["banks_sha256"] == futility["banks_sha256"],
               "FUTILITY input identity differs from fold receipts")
    b0_completion = {arm: findings[arm]["B0"]["status"] for arm in CANDIDATES}
    b0_excluded = [arm for arm, status in b0_completion.items() if status in ("FAIL", "NUMERICAL_FAIL")]
    complete = not partial and all(v["status"] == "BASELINE" for arm in ("DR", "R4") for v in findings[arm].values())
    complete = complete and all(v["status"] in ("PASS", "FAIL", "NUMERICAL_FAIL")
                                for arm in (*CANDIDATES, "J4", "J4+K") for v in findings[arm].values())
    selection = None
    if complete and snr == 30:
        numerical_ineligible = {arm: [level for level in LEVELS if findings[arm][level]["status"] == "NUMERICAL_FAIL"]
                                for arm in CANDIDATES}
        candidates = {arm: dict(
            integrity={"levels": {level: findings[arm][level]["integrity"] for level in LEVELS}},
            l1_pooled_heading_rmse_deg=math.degrees(findings[arm]["L1"]["integrity"]["pooled"]["point"]["heading_rmse_rad"]),
        ) for arm in CANDIDATES if not numerical_ineligible[arm]}
        selection = select_primary_arm(candidates, LEVELS)
        selection["numerically_ineligible"] = {arm: levels for arm, levels in numerical_ineligible.items() if levels}
    status = "PARTIAL" if partial else (selection["status"] if selection else ("SENSITIVITY_COMPLETE" if complete else "INCOMPLETE"))
    return dict(question_id="G1-MODEL-003", stage="S3", status=status, snr_db=snr,
                or_rule="O30", o30_shares_or=True, source=identity.get("source"),
                receipt_sha256=receipt_shas, design=dict(cases=CASES, paths=PATHS, levels=levels, candidates=CANDIDATES),
                early_b0=dict(status_by_arm=b0_completion, permanently_ineligible=b0_excluded,
                              all_candidates_ineligible=len(b0_excluded) == len(CANDIDATES)),
                findings=findings, primary_selection=selection, s2_accuracy_scope=scope,
                accuracy_claims_supported=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folds", type=Path, required=True)
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--futility", type=Path)
    parser.add_argument("--snr", type=int, choices=(20, 30), default=30)
    parser.add_argument("--partial", action="store_true", help="Read B0 only and never select or close S3")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if not args.partial and (args.futility is None or args.out is None):
        parser.error("Complete summaries require --futility and --out")
    raw = args.futility.read_bytes() if args.futility else None
    report = summarize(args.folds, snr=args.snr, futility=json.loads(raw) if raw else None,
                       logs=args.logs, partial=args.partial)
    if raw:
        report["futility_sha256"] = _digest(raw)
    if args.out is not None:
        with args.out.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
    headline = dict(status=report["status"], early_b0=report["early_b0"], selection=report["primary_selection"])
    if args.partial:
        headline["arms"] = {arm: dict(folds_valid=report["findings"][arm]["B0"]["folds_valid"],
                                      gates=report["findings"][arm]["B0"].get("integrity", {}).get("gates"),
                                      numerical_failures=sum(issue["status"] == "NUMERICAL_FAIL" for issue in
                                                             report["findings"][arm]["B0"]["fold_issues"].values()))
                            for arm in CANDIDATES}
    print(json.dumps(headline, indent=2, allow_nan=False))
    return 0 if report["status"] != "INCOMPLETE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
