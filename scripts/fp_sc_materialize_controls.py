#!/usr/bin/env python3
"""Prepare explicit E0-A2 inputs only; never execute a filter or selector."""
from pathlib import Path
import argparse
import json
import os
import sys

# The primary A2 materialization runtime was selected before any recursion.
for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from qclean_uwb.fp_sc.e0_rematerialized import materialize_controls
from qclean_uwb.fp_sc.e0_baseline import sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New controls directory inside this repository")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else REPO / args.output
    registry = materialize_controls(REPO, output, command=sys.argv)
    print(json.dumps({"status": registry["status"], "entries": len(registry["entries"]),
                      "identity": registry["identity"], "historical_byte_identity_status": registry["historical_byte_identity_status"],
                      "registry": str(output / "REGISTRY.json"), "registry_sha256": sha256(output / "REGISTRY.json")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
