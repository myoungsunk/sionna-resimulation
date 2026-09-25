from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from rt_cp_uwb_py.config import default_config
from rt_cp_uwb_py.sweep import run_sweep_batch


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases-csv", required=True)
    ap.add_argument("--out-csv", required=True)
    ap.add_argument("--manifest", required=True)
    args = ap.parse_args()
    cases = pd.read_csv(args.cases_csv)
    out = run_sweep_batch(cases, default_config(), verbose=True)
    out_path = Path(args.out_csv)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases_csv": str(Path(args.cases_csv).resolve()),
        "out_csv": str(out_path.resolve()),
        "n_cases": len(cases),
        "failed_cases": int(out.get("failed", pd.Series(dtype=bool)).fillna(False).astype(bool).sum()),
    }
    mpath = Path(args.manifest)
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
