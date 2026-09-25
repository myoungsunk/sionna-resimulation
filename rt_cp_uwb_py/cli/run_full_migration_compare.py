from __future__ import annotations

import argparse
from pathlib import Path

from rt_cp_uwb_py.migration import build_migration_comparison


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Python replacements for active MATLAB files and compare Python outputs with previous results.")
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-parity", action="store_true")
    args = parser.parse_args()
    summary = build_migration_comparison(args.project_root, args.out, run_parity=not args.no_parity)
    print(summary["wrapper_dir"])


if __name__ == "__main__":
    main()
