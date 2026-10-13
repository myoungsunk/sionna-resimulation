"""V1: compare the pre-registered D6 final result against a read-only recomputation.

Does NOT call ensure(), run_arm() or any generator. If official results are absent
or even one cache is incomplete, NO primary verdict is computed or emitted.
python v1_verdict_audit.py --out followup_runs/v1_001
"""
from __future__ import annotations

import argparse
import json

import common as C
import v0_cache_audit as V0

from confirm_dr_independent import evaluate, verdict
from ablate_dr_calibration import load_rows

OFFICIAL = C.DIAG / "out" / "D6_CONFIRMATION_s8100-8399.json"


def audit(cache_root=None, min_age_s=120, official_path=OFFICIAL):
    state = V0.scan(cache_root=cache_root, min_age_s=min_age_s)
    result = dict(status="NOT_READY", cache_counts=state["counts"],
                  immutable_spec=C.git_frozen_spec(),
                  official_file=str(official_path),
                  note="No D6 verdict unless every cache complete and official result exists")
    if state["status"] != "READY_FOR_D6":
        result["reason"] = "One or more cache cells missing/invalid/recent; no evaluation"
        return result
    if not official_path.is_file():
        result["reason"] = "Original D6 official evaluator has not written its result"
        return result
    # Original evaluator wrote a result. Independent auditing may now *read*
    # cached data but MUST NOT call any execution path.
    spec = json.loads(C.D6_SPEC.read_text())
    seeds = C.parse_seed_range(spec["seeds"])
    if cache_root is not None and cache_root.resolve() != (C.DIAG / "cache").resolve():
        raise ValueError("Original evaluation helpers read only default cache root")
    rows = load_rows(spec["arms"], seeds)
    recomputed = evaluate(spec, rows, seeds)
    projected = verdict(recomputed)
    official = json.loads(official_path.read_text())
    original = official.get("criteria", {})
    diff = {k: dict(original=original.get(k, {}).get("status"),
                    recomputed=v.get("status"))
            for k, v in recomputed.items()
            if original.get(k, {}).get("status") != v.get("status")}
    # Numeric reconciliation as well as statuses. A tampered/partial JSON with
    # the right PASS labels must NOT pass the audit.
    def compare(a, b, location="criteria"):
        if isinstance(a, dict) and isinstance(b, dict):
            issues = []
            for k in set(a) | set(b):
                issues += compare(a.get(k), b.get(k), location + "." + str(k))
            return issues
        if isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                return [location + ".length"]
            return [x for i, (aa, bb) in enumerate(zip(a, b))
                    for x in compare(aa, bb, location + "." + str(i))]
        if isinstance(a, (float, int)) and isinstance(b, (float, int)):
            return [] if abs(a - b) <= 1e-8 * max(1., abs(a), abs(b)) else [location]
        return [] if a == b else [location]
    value_diffs = compare(original, recomputed)
    answer = official.get("verdict")
    result.update(status="RECONCILED" if not diff and not value_diffs and projected == answer
                  else "MISMATCH_INVESTIGATE",
                  mismatched_criteria=diff, mismatched_values=value_diffs[:100],
                  cause_verdict_equal=answer == projected,
                  original_cause=answer, recomputed_cause=projected,
                  official_sha256=C.sha256(official_path))
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-age-s", type=float, default=120)
    ap.add_argument("--official", type=C.Path, default=OFFICIAL)
    a = ap.parse_args()
    report = audit(min_age_s=a.min_age_s, official_path=a.official)
    out = C.new_dir(a.out)
    C.write_json_new(out / "V1_D6_VERDICT_AUDIT.json", report)
    C.write_json_new(out / "V1_MANIFEST.json", C.provenance())
    print(report["status"], report.get("reason", "see V1_D6_VERDICT_AUDIT.json"))


if __name__ == "__main__":
    main()
