"""V0: safely audit D6 caches WITHOUT executing/rewriting a single task.

python v0_cache_audit.py --out followup_runs/v0_001
python v0_cache_audit.py --out followup_runs/v0_002 --hash-ready
"""
from __future__ import annotations

import argparse
import json

import common as C


def scan(cache_root=None, min_age_s=120, hash_ready=False, full_psd=False):
    spec = json.loads(C.D6_SPEC.read_text())
    seeds = C.parse_seed_range(spec["seeds"])
    records = []
    for arm in spec["arms"]:
        for route, level in C.H.CELLS:
            path = C.cache_path(arm, seeds, route, level, cache_root)
            summary, _ = C.validated_cache(
                path, seeds, route, min_age_s=min_age_s, sha=hash_ready,
                full_psd=full_psd)
            summary.update(arm=arm, route=route, drift=level)
            records.append(summary)
    counts = {k: sum(x["status"] == k for x in records)
              for k in sorted(set(x["status"] for x in records))}
    return dict(status="READY_FOR_D6" if counts.get("VALID", 0) == len(records)
                else "INCOMPLETE_NO_D6_VERDICT",
                records=records, counts=counts, expected_cells=len(spec["arms"]) * 9,
                verified_cells=counts.get("VALID", 0),
                note="Read-only audit, no D6 C1-C7/S1 evaluation or PASS/FAIL")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="NEW directory; never D6 out/cache")
    ap.add_argument("--cache-root", type=C.Path, default=None)
    ap.add_argument("--min-age-s", type=float, default=120)
    ap.add_argument("--hash-ready", action="store_true")
    ap.add_argument("--full-psd", action="store_true")
    a = ap.parse_args()
    C.git_frozen_spec()
    report = scan(a.cache_root, a.min_age_s, a.hash_ready, a.full_psd)
    out = C.new_dir(a.out)
    C.write_json_new(out / "V0_CACHE_INTEGRITY.json", report)
    C.write_json_new(out / "V0_MANIFEST.json", C.provenance(
        dict(settings=vars(a), expected=report["expected_cells"])))
    print(report["status"], report["counts"], "verified", report["verified_cells"])


if __name__ == "__main__":
    main()
