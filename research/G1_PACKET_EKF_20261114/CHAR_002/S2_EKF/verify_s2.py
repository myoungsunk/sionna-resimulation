"""Reaggregate S2 trace evidence using evaluator truth and Cholesky NEES."""

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import chi2

from replay_s2 import ARMS, D_MAX, NU, read_npz, sha, wrap


def check_metric_rows(rows, archived):
    recalculated = {
        "n": len(rows),
        "heading_rmse_deg": float(np.sqrt(rows[:, 0].mean())),
        "xy_rmse_cm": float(np.sqrt(rows[:, 1].mean())),
        "mean_nees3": float(rows[:, 2].mean()),
        "pose95_coverage": float(rows[:, 3].mean()),
        "xy95_coverage": float(rows[:, 4].mean()),
        "heading95_coverage": float(rows[:, 5].mean()),
    }
    if not np.allclose(list(recalculated.values()), [archived[k] for k in recalculated], rtol=1e-12, atol=1e-12):
        raise ValueError(f"Trace and summary disagree: {recalculated}")


def from_trace(trace, truth):
    d = trace["x"][:, :3] - truth
    d[:, 2] = wrap(d[:, 2])
    P = trace["P"][:, :3, :3]
    L3 = np.linalg.cholesky(P)
    L2 = L3[:, :2, :2]
    n3 = (np.linalg.solve(L3, d[..., None])[:, :, 0]**2).sum(axis=1)
    n2 = (np.linalg.solve(L2, d[:, :2, None])[:, :, 0]**2).sum(axis=1)
    return np.column_stack([np.rad2deg(d[:, 2])**2, 1e4 * (d[:, :2]**2).sum(axis=1), n3,
                            n3 <= chi2.ppf(.95, 3), n2 <= chi2.ppf(.95, 2),
                            abs(d[:, 2]) <= 1.96 * np.sqrt(P[:, 2, 2])])


def check_dynamics(trace, stage, arm, anchor, fit):
    prior = trace["prior"]
    delta = anchor[:2] - prior[:, :2]
    distance = np.sqrt((delta**2).sum(axis=1) + (anchor[2] - .45)**2)
    bearing = np.mod(np.rad2deg(prior[:, 2]) - np.rad2deg(np.arctan2(delta[:, 1], delta[:, 0])), 180)
    if not (np.allclose(bearing, trace["prior_bearing_deg"], atol=1e-12, rtol=0) and
            np.array_equal(distance > D_MAX, trace["extrapolated"])):
        raise ValueError(f"Prior conditioning geometry mismatch: {stage}/{arm}")
    if arm == "E0":
        return
    if np.any(trace["mu"][:, 1] != 0.) or np.any(trace["Reff"][:, 0, 1] != 0.):
        raise ValueError(f"Unexpected learned s mean or R cross term: {stage}/{arm}")
    if arm == "E4":
        move = np.linalg.norm(np.diff(prior[:, :2], axis=0), axis=1)
        turn = abs(wrap(np.diff(prior[:, 2])))
        expected_phi = np.r_[0., np.where(move <= .02, np.exp(-turn / fit["ell_yaw_rad"]), 0.)]
        if not np.allclose(expected_phi, trace["phi"], atol=1e-15, rtol=0):
            raise ValueError(f"E4 yaw transition mismatch: {stage}")
    if arm in ("E3", "E4"):
        H = trace["H"][:, 1, :]
        HPHT = np.einsum("ni,nij,nj->n", H, trace["Pprior"], H)
        r = trace["Rvar"][:, 1, 1]
        for _ in range(3):
            r = r * (NU + trace["nu"][:, 1]**2 / (HPHT + r)) / (NU + 1)
        if not np.allclose(r, trace["Reff"][:, 1, 1], atol=1e-14, rtol=1e-12):
            raise ValueError(f"Student-t variance mismatch: {stage}/{arm}")


def verify(run, stages):
    verified = {}
    contract = run / "RUN_CONTRACT.json"
    fit = json.loads((run / "FIT_S2.json").read_bytes())
    for stage in stages:
        stage_dir = run / stage
        execution = json.loads((stage_dir / "EXECUTION.json").read_bytes())
        if execution["status"] != "PASS_EXECUTION" or execution["run_contract_sha256"] != sha(contract):
            raise ValueError(f"Stage execution evidence mismatch: {stage}")
        for name, digest in execution["outputs"].items():
            if sha(stage_dir / name) != digest:
                raise ValueError(f"Output SHA mismatch: {stage}/{name}")
        result = json.loads((stage_dir / "RESULTS.json").read_bytes())
        inputs = json.loads((stage_dir / "INPUTS.json").read_bytes())
        by_arm = {arm: [] for arm in ARMS}
        masks = {}
        anchor = np.array([4. if stage == "2c" else 10., 0., 2.65])
        for route in ("R2", "R4", "R5"):
            path = Path(inputs[route]["evaluator"]["path"])
            if sha(path) != inputs[route]["evaluator"]["sha256"]:
                raise ValueError(f"Evaluator hash mismatch: {stage}/{route}")
            ev = read_npz(path)
            for arm in ARMS:
                trace = read_npz(stage_dir / f"{route}_{arm}_trace.npz")
                if not all(np.array_equal(trace[key], ev[key]) for key in ("t", "pose_id")):
                    raise ValueError(f"Wrong evaluator join: {stage}/{route}/{arm}")
                if arm == "E0":
                    masks[route] = trace["mask"]
                elif not np.array_equal(trace["mask"], masks[route]):
                    raise ValueError(f"W0 gate differs between arms: {stage}/{route}/{arm}")
                check_dynamics(trace, stage, arm, anchor, fit)
                rows = from_trace(trace, ev["truth"])
                check_metric_rows(rows, result["by_case"][route][arm])
                by_arm[arm].append(rows)
        for arm in ARMS:
            check_metric_rows(np.concatenate(by_arm[arm]), result["pooled"][arm])
        verified[stage] = {"trace_count": 18, "rows_per_arm": sum(len(m) for m in masks.values()),
                           "gate_accepted": {route: int(mask.sum()) for route, mask in masks.items()},
                           "result_sha256": sha(stage_dir / "RESULTS.json")}
    return {"status": "PASS_IMPLEMENTER_CHECK", "verified": verified, "verifier_sha256": sha(__file__)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("stages", nargs="+", choices=("2a", "2b", "2c"))
    args = parser.parse_args()
    output = verify(args.run, args.stages)
    print(json.dumps(output, indent=2, allow_nan=False))
