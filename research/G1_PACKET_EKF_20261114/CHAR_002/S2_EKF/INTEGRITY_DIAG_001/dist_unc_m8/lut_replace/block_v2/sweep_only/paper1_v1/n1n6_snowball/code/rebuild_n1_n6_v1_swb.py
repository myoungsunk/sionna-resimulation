"""Reconstruct the full-column-out SWB candidate and retain the native FFD range."""

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import scipy
from threadpoolctl import threadpool_limits

from rebuild_n1_n6_v1_cal import PINS, TABLE_ATOL, sha256


FARST_SHA256 = "d9bc2179391184095edce6a42abdd9b9a417f06fdcaa11506f977784f5b13d1a"
ARCHIVED_SWEEP_CALL = b'pd.read_csv("/home/claude/m8cal/SWEEP_FEATURES.csv.gz")'


class FfdRangeSwbPolarization:
    """Keep native range and its Jacobian, use SWB for polarization."""

    def __init__(self, ffd, swb):
        self.ffd = ffd
        self.polarization = swb.s_fn()

    def batch(self, states, case, gradient=True):
        native, native_jacobian = self.ffd.batch(states, case, gradient=gradient)
        polarization, derivative = self.polarization(states, case)
        values = native.copy()
        values[:, 1] = polarization
        jacobian = None
        if gradient:
            jacobian = native_jacobian.copy()
            jacobian[:, 1, :3] = derivative
            jacobian[:, 1, 3] = 0.0
        return values, jacobian


def swap_env(env, swb):
    """Create the M8 observation environment for the SWB counterfactual."""
    return dict(env, model=FfdRangeSwbPolarization(env["model"], swb))


def load_swb(swb_source, sweep_features, v0_block_rss):
    pins = {
        "swb_source": FARST_SHA256,
        "sweep_features": PINS["sweep_features"],
        "v0_block_rss": PINS["v0_block_rss"],
    }
    for name, path in (
        ("swb_source", swb_source), ("sweep_features", sweep_features),
        ("v0_block_rss", v0_block_rss),
    ):
        if sha256(path) != pins[name]:
            raise ValueError("Frozen input SHA-256 mismatch: " + name)
    source = swb_source.read_bytes()
    if source.count(b"FAR_STATION = True") != 1 or source.count(ARCHIVED_SWEEP_CALL) != 1:
        raise ValueError("Unexpected frozen SWB source layout")
    source = source.replace(b"FAR_STATION = True", b"FAR_STATION = False", 1)
    source = source.replace(ARCHIVED_SWEEP_CALL, b"load_archived_sweep()", 1)
    namespace = {
        "__name__": "reconstructed_fullco_swb",
        "load_archived_sweep": lambda: pd.read_csv(sweep_features),
    }
    with threadpool_limits(limits=1):
        exec(compile(source, str(swb_source), "exec"), namespace)
        block = SimpleNamespace(**namespace)
        coefficients, _ = block.build_station_coefs()
        table, residual, _ = block.column_out_table()
        swb = block.SWB()

    archive = json.loads(v0_block_rss.read_text(encoding="utf-8"))
    archived_grid = archive["block"]
    x_min, x_max, n_x = archived_grid["XS"]
    if (
        coefficients.shape != (n_x, len(archived_grid["YS"]), archived_grid["K"])
        or [float(block.XS[0]), float(block.XS[-1])] != [x_min, x_max]
        or len(block.PS) != archived_grid["n_yaw"]
        or block.YS.tolist() != archived_grid["YS"]
        or not np.isfinite(coefficients).all()
    ):
        raise ValueError("Reconstructed SWB grid differs from archived grid")
    coefficient_bytes = np.ascontiguousarray(
        np.concatenate((coefficients.real, coefficients.imag), axis=2)
    ).tobytes()
    coefficient_sha = hashlib.sha256(coefficient_bytes).hexdigest()

    bins = np.clip(np.searchsorted(block.EDG, block.RHO, side="right") - 1, 0, 2)
    rss = np.array([np.mean(residual[bins == i] ** 2) for i in range(3)])
    archive_rss = np.array([row["var"] + row["mean"] ** 2 for row in archive["simple"]])
    rss_error = float(np.max(np.abs(rss - archive_rss)))
    table_errors = {
        col: float(np.max(np.abs(np.asarray(table[col]) - archive["c1a2c0_reproduced"][col])))
        for col in ("c1", "c0")
    }
    exact_coefficients = coefficient_sha == archive["block"]["coef_sha256"]
    if not all(error <= TABLE_ATOL for error in (*table_errors.values(), rss_error)):
        raise ValueError("Archived SWB calibration summaries failed numerical parity")
    report = {
        "status": "PASS_ARCHIVED_CALIBRATION_SUMMARIES",
        "coefficient_bit_exact": exact_coefficients,
        "coefficient_sha256": coefficient_sha,
        "archived_coefficient_sha256": archive["block"]["coef_sha256"],
        "approved_claim": "reconstructed_candidate_pending_archived_replay_parity",
        "Rss": rss.tolist(),
        "archived_Rss": archive_rss.tolist(),
        "max_abs_Rss_delta": rss_error,
        "max_abs_fitted_table_delta": table_errors,
        "absolute_tolerance": TABLE_ATOL,
        "sha256": {**pins, "adapter": sha256(Path(__file__))},
        "runtime": {"numpy": np.__version__, "scipy": scipy.__version__, "pandas": pd.__version__},
    }
    return swb, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--swb-source", type=Path, required=True)
    parser.add_argument("--sweep-features", type=Path, required=True)
    parser.add_argument("--v0-block-rss", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    _, report = load_swb(args.swb_source, args.sweep_features, args.v0_block_rss)
    body = json.dumps(report, indent=2) + "\n"
    with args.report.open("x", encoding="utf-8") as stream:
        stream.write(body)
    print(body, end="")


if __name__ == "__main__":
    main()
