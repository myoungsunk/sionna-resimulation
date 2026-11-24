"""Rebuild the V1 range calibrator from the archived BLOCK_C sweep."""

import argparse
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import pickle
import platform
import sys
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import scipy
import sklearn
from threadpoolctl import threadpool_limits


PINS = {
    "v1_common": "0c727d9e79c680f83eb1f51fa2288319a6108ad45af4745c399165d726353f0e",
    "sweep_features": "2917a06c8317fa81f3729e90d4c65a077af14c73c56137c75777eea6d710c320",
    "v0_block_rss": "9c4370454c9583733d03450d37fe70b1960917bf5bc413afd56e75eb68c2e80b",
    "v1_tables": "6173229b2eb350ec9cfff2b1202b23f7a9e325f11809036bbc24b772db7960e1",
}
SWEEP_PATH = "/home/claude/m8cal/SWEEP_FEATURES.csv.gz"
V0_PATH = "/home/claude/v0/V0_BLOCK_RSS.json"
TABLE_ATOL = 1e-12


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_calibrator(source, sweep_features, v0_block_rss):
    namespace = {"__name__": "frozen_v1_common"}
    saved_paths = sys.path[:]
    try:
        exec(compile(source.read_bytes(), str(source), "exec"), namespace)
    finally:
        sys.path[:] = saved_paths

    def read_sweep(path):
        if path != SWEEP_PATH:
            raise ValueError("Unexpected V1 sweep path: " + path)
        return pd.read_csv(sweep_features)

    def read_v0(path):
        if path != V0_PATH:
            raise ValueError("Unexpected V0 calibration path: " + path)
        return v0_block_rss.open("r", encoding="utf-8")

    namespace["pd"] = SimpleNamespace(read_csv=read_sweep)
    namespace["open"] = read_v0
    return namespace["build_cal"], tuple(namespace["EXIST"])


def compare_tables(reference, actual):
    comparison = {}
    for name in ("Rrr", "Rss"):
        expected = np.asarray(reference[name], dtype=float)
        rebuilt = np.asarray(actual[name], dtype=float)
        if expected.shape != (3,) or rebuilt.shape != (3,) or not (
            np.isfinite(expected).all() and np.isfinite(rebuilt).all()
            and (expected > 0).all() and (rebuilt > 0).all()
        ):
            raise ValueError("Invalid V1 table: " + name)
        error = float(np.max(np.abs(rebuilt - expected)))
        comparison[name] = {
            "archived": expected.tolist(), "rebuilt": rebuilt.tolist(),
            "max_abs_delta": error, "bit_exact": expected.tobytes() == rebuilt.tobytes(),
            "within_absolute_tolerance": error <= TABLE_ATOL,
        }
    return comparison


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-common", type=Path, required=True)
    parser.add_argument("--sweep-features", type=Path, required=True)
    parser.add_argument("--v0-block-rss", type=Path, required=True)
    parser.add_argument("--v1-tables", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    for name, digest in PINS.items():
        if sha256(getattr(args, name)) != digest:
            raise ValueError("Frozen input SHA-256 mismatch: " + name)
    reference = json.loads(args.v1_tables.read_text(encoding="utf-8"))
    calibrate, features = load_calibrator(
        args.v1_common, args.sweep_features, args.v0_block_rss,
    )
    args.output_dir.mkdir(exist_ok=False)
    start = time.monotonic()
    # Capture any source diagnostics so stdout stays a machine-readable receipt.
    original_stdout = io.StringIO()
    with threadpool_limits(limits=1), redirect_stdout(original_stdout):
        model, rrr, rss = calibrate()
    if tuple(model.feature_names_in_) != features:
        raise ValueError("Rebuilt V1 model feature order differs from frozen order")
    tables = compare_tables(reference, {"Rrr": rrr, "Rss": rss})
    passed = all(row["within_absolute_tolerance"] for row in tables.values())
    report = {
        "status": "PASS_TABLES" if passed else "FAIL_TABLES",
        "model_identity": "reconstructed_candidate",
        "original_serialized_model_compared": False,
        "sha256": {**PINS, "adapter": sha256(Path(__file__))},
        "table_absolute_tolerance": TABLE_ATOL,
        "tables": tables,
        "feature_order": features,
        "fit_wall_s": time.monotonic() - start,
        "runtime": {
            "python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__,
        },
    }
    if original_stdout.getvalue():
        report["frozen_source_stdout"] = original_stdout.getvalue()
    if passed:
        candidate = args.output_dir / "CAL_V1_REBUILT_CANDIDATE.pkl"
        with candidate.open("xb") as stream:
            pickle.dump((model, rrr, rss), stream, protocol=4)
        report["candidate"] = {"filename": candidate.name, "sha256": sha256(candidate)}
    receipt = json.dumps(report, indent=2) + "\n"
    (args.output_dir / "V1_CALIBRATION_REPORT.json").write_text(receipt, encoding="utf-8")
    print(receipt, end="")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
