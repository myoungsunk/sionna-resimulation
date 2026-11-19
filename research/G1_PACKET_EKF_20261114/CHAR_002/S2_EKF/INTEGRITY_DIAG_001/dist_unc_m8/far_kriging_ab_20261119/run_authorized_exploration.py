#!/usr/bin/env python3
"""Explicitly authorized exploratory replay; never claims frozen parity PASS."""
import argparse
import csv
import datetime
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import run_far_kriging_ab as R
import aggregate_far_kriging_ab as A

STATUS = "EXPLORATORY_USER_AUTHORIZED_BASELINE_MISMATCH"
AUTHORIZATION = "2026-11-19 user: 우선 그냥 진행하도록 해"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise RuntimeError(f"Refusing to overwrite evidence: {path}")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, default=R.asjson, ensure_ascii=False,
                              allow_nan=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def run(args):
    if not args.acknowledge_baseline_mismatch:
        raise RuntimeError("Explicit baseline-mismatch acknowledgement required")
    if not 30 <= args.first <= args.last <= 49:
        raise ValueError("Only original exploratory seeds 30..49 authorized")
    B, table, published = R.load_frozen()
    env, scorers = R.C.env(), R.C.scorers()
    receipt = dict(status=STATUS, authorization=AUTHORIZATION,
        source_commit=args.source_commit, python=platform.python_version(),
        numpy=np.__version__, predictor="original krige_online.py; stable repair NOT applied",
        condition=args.condition, seeds=[args.first, args.last],
        baseline_tolerance=1e-8, started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256={p.name: sha(p) for p in Path(__file__).parent.glob("*.py")},
        inputs={}, outputs={})
    for seed in range(args.first, args.last + 1):
        dest = args.out / args.condition / f"seed{seed}"
        if dest.exists():
            raise RuntimeError(f"Refusing to reuse prior group: {dest}")
        print("RUN", args.condition, seed, flush=True)
        for route in R.ROUTES:
            p = R.M8 / "inputs_ext" / args.condition / f"seed{seed}" / f"{route}_online.npz"
            receipt["inputs"][str(p)] = sha(p)
        result = R.report_one(args.condition, seed, env, scorers, B, table, published,
            allow_baseline_mismatch=True, trace_dir=dest / "traces")
        result.update(status=STATUS, authorization=AUTHORIZATION,
                      stable_kriging_applied=False, source_commit=args.source_commit)
        write(dest / "RESULT.json", result)
        receipt["outputs"][str(dest / "RESULT.json")] = sha(dest / "RESULT.json")
        print("DONE", args.condition, seed,
              "frozen_parity_pass", result["frozen_parity_pass"],
              "max_gap", result["frozen_parity_max_abs"], flush=True)
    receipt["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    write(args.out / f"RUN_{args.condition}_{args.first}_{args.last}.json", receipt)


def aggregate(args):
    results, checks, traces = {}, [], []
    for condition in A.CONDITIONS:
        for seed in A.SEEDS:
            dest = args.out / condition / f"seed{seed}"
            path = dest / "RESULT.json"
            d = json.loads(path.read_text())
            assert (d["condition"], d["seed"]) == (condition, seed)
            assert d["status"] == STATUS and d["baseline_mismatch_authorized"]
            assert not d["stable_kriging_applied"]
            assert len(d["frozen_parity_checks"]) == 60
            keys = {(r["route"], r["arm"], r["metric"]) for r in d["frozen_parity_checks"]}
            assert keys == {(r, a, m) for r in A.ROUTES for a in ("H2", "H2S", R.BASE) for m in R.PAIR_PARAMS}
            for row in d["frozen_parity_checks"]:
                assert np.isfinite([row["actual"], row["expected"], row["abs_gap"]]).all()
                assert row["passed"] == (row["abs_gap"] <= 1e-8)
                assert row["abs_gap"] == abs(row["actual"] - row["expected"])
                checks.append(dict(condition=condition, seed=seed, **row))
            assert d["frozen_parity_pass"] == all(r["passed"] for r in d["frozen_parity_checks"])
            assert d["frozen_parity_max_abs"] == max(r["abs_gap"] for r in d["frozen_parity_checks"])
            for route in A.ROUTES:
                for arm in R.ARMS:
                    assert np.isfinite([d["point"][route][arm][m] for m in A.METRICS]).all()
            for route in R.ROUTES:
                for arm in R.ARMS:
                    trpath = dest / "traces" / f"{route}_{arm}.npz"
                    with np.load(trpath) as tr:
                        assert np.isfinite(tr["x"]).all() and np.isfinite(tr["P"]).all()
                        assert len(tr["t"]) == len(tr["x"]) == len(tr["mask"])
                    traces.append(dict(path=str(trpath), size=trpath.stat().st_size, sha256=sha(trpath)))
                with np.load(dest / "traces" / f"{route}_{R.BASE}.npz") as old, np.load(dest / "traces" / f"{route}_{R.FAR}.npz") as new:
                    assert np.array_equal(old["t"], new["t"]) and np.array_equal(old["pose_id"], new["pose_id"])
            results[condition, seed] = d
    assert len(results) == 40 and len(checks) == 2400 and len(traces) == 480
    detail, decisions, paired = A.summarize(results)
    for row in decisions:
        row["descriptive_thresholds_met"] = row.pop("condition_pass")
        row["scientific_adoption_pass"] = False
    out = args.out / "summary"
    out.mkdir(exist_ok=False)
    for name, rows in (("FAR_AB_POINTS.csv", detail), ("FAR_AB_DESCRIPTIVE_RULES.csv", decisions),
                       ("FAR_AB_PAIRED.csv", paired), ("BASELINE_PARITY.csv", checks)):
        with (out / name).open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=rows[0].keys(), lineterminator="\n")
            writer.writeheader(); writer.writerows(rows)
    summary = dict(status=STATUS, authorization=AUTHORIZATION, n=40,
        conditions=A.CONDITIONS, seeds=[30, 49], arms=A.ARMS,
        baseline_tolerance=1e-8, parity_failed_groups=sum(not d["frozen_parity_pass"] for d in results.values()),
        parity_failed_scalars=sum(not r["passed"] for r in checks),
        parity_max_abs=max(r["abs_gap"] for r in checks),
        independent_audit=False, scientific_adoption_pass=False,
        decisions=decisions, paired=paired,
        limitations=["Historical baseline reproduction failed; explicit user authorization to continue.",
                    "Original predictor, no stable-neighbor repair applied.",
                    "Same recovered online inputs paired across arms; historical 30..49 NPZ arrays unavailable.",
                    "Seeds 30..49 are exploratory; bootstrap does not provide independent scene replication."])
    write(out / "SUMMARY.json", summary)
    write(out / "RETAINED_TRACE_MANIFEST.json", traces)
    write(out / "VALIDATION.json", dict(kind="IMPLEMENTER_SELF_CHECK", independent_audit=False,
        complete_groups=40, point_rows=len(detail), paired_rows=len(paired),
        unique_baseline_checks=len(checks), finite_trace_files=len(traces),
        scientific_adoption_pass=False, baseline_parity_pass=summary["parity_failed_groups"] == 0))
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    subs = ap.add_subparsers(dest="action", required=True)
    rp = subs.add_parser("run")
    rp.add_argument("--condition", choices=A.CONDITIONS, required=True)
    rp.add_argument("--first", type=int, default=30)
    rp.add_argument("--last", type=int, default=49)
    rp.add_argument("--source-commit", required=True)
    rp.add_argument("--acknowledge-baseline-mismatch", action="store_true")
    for sub in (rp, subs.add_parser("aggregate")):
        sub.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    (run if args.action == "run" else aggregate)(args)


if __name__ == "__main__":
    main()
