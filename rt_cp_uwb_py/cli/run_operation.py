from __future__ import annotations

import argparse
import json
from pathlib import Path

from rt_cp_uwb_py.operations import list_operations, run_named_operation, write_result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a MATLAB-compatible rt_cp_uwb operation in Python.")
    parser.add_argument("operation", nargs="?", help="Operation name, e.g. sanity.runImplementedChecks")
    parser.add_argument("--kwargs-json", help="JSON object with keyword arguments")
    parser.add_argument("--kwargs-file", help="Path to JSON object with keyword arguments")
    parser.add_argument("--out", help="Output CSV/text path")
    parser.add_argument("--list", action="store_true", help="List supported operations")
    args = parser.parse_args()
    if args.list:
        print("\n".join(list_operations()))
        return
    if not args.operation:
        raise SystemExit("operation is required unless --list is used")
    kwargs = {}
    if args.kwargs_file:
        kwargs.update(json.loads(Path(args.kwargs_file).read_text(encoding="utf-8-sig")))
    if args.kwargs_json:
        kwargs.update(json.loads(args.kwargs_json))
    result = run_named_operation(args.operation, kwargs)
    if args.out:
        write_result(result, args.out)
        print(args.out)
    else:
        print(result)


if __name__ == "__main__":
    main()
