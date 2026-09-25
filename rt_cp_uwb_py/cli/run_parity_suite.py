from __future__ import annotations

import argparse
from pathlib import Path

from rt_cp_uwb_py.parity import run_parity_suite


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-root", default="results")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cases-csv", default=None)
    ap.add_argument("--baseline-csv", default=None)
    ap.add_argument("--max-cases", type=int, default=30)
    ap.add_argument("--replay-fp-hints", action="store_true")
    args = ap.parse_args()
    manifest = run_parity_suite(
        Path(args.baseline_root),
        Path(args.out),
        cases_csv=args.cases_csv,
        baseline_csv=args.baseline_csv,
        max_cases=args.max_cases,
        replay_fp_hints=args.replay_fp_hints,
    )
    print(manifest["python_output"])


if __name__ == "__main__":
    main()
