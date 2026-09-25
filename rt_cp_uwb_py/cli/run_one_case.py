from __future__ import annotations

import argparse
import json
from pathlib import Path

from rt_cp_uwb_py.sweep import read_case_json, run_one_case, write_dict_csv


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case-json", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    row = read_case_json(args.case_json)
    result = run_one_case(row)
    out = Path(args.out)
    if out.suffix.lower() == ".json":
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    else:
        write_dict_csv(result, out)


if __name__ == "__main__":
    main()
