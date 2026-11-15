"""Reproduce frozen E0 and replace only its polarization sigma table for D5."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np


ROUTES = ("R2", "R4", "R5")
ROWS = dict(zip(ROUTES, (979, 742, 1415)))
KNOTS = np.array([0., 1.5, 3., 6., 10.])
HAND = np.array([.011, .020, .050, .120, .240])
SIGMA_FLOOR = .005
MIN_WEIGHT = 5.
PARITY_KEYS = ("x", "P", "prior", "Pprior", "h", "H", "Reff", "K", "nu", "mask")
PACKET_KEYS = ("z", "D", "R", "muMB", "muBASE", "x0", "P0", "t", "pose_id", "ds", "gy", "dt")


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def checked_array(record, keys=None):
    from replay_s2 import sha

    path = Path(record["path"])
    if sha(path) != record["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {path}")
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in (data.files if keys is None else keys)}


def key_for(cell):
    return '_'.join(cell[name] for name in ("anchor", "bias", "route"))


def identity(left, right, fields):
    for name in fields:
        if not np.array_equal(left[name], right[name]):
            raise ValueError(f"Packet identity mismatch: {name}")


def bind(cell):
    packet = checked_array(cell["online"], PACKET_KEYS)
    evaluator = checked_array(cell["evaluator"], ("t", "pose_id", "truth"))
    identity(packet, evaluator, ("t", "pose_id"))
    n = ROWS[cell["route"]]
    shapes = {"z": (n, 2), "D": (n,), "R": (n, 2, 2), "muMB": (n, 2), "muBASE": (n, 2),
              "x0": (4,), "P0": (4, 4), **{name: (n,) for name in ("t", "pose_id", "ds", "gy", "dt")}}
    for name, shape in shapes.items():
        if packet[name].shape != shape or not np.isfinite(packet[name]).all():
            raise ValueError(f"Invalid shape or values for {key_for(cell)} {name}")
    if evaluator["truth"].shape != (n, 3) or not np.isfinite(evaluator["truth"]).all():
        raise ValueError("Invalid evaluator truth")
    if (np.any(np.diff(packet["t"]) <= 0) or np.any(np.diff(packet["pose_id"]) <= 0)
            or np.any(packet["z"][:, 0] <= 0) or np.any(np.abs(packet["z"][:, 1]) > 1)
            or not np.array_equal(packet["dt"], np.r_[0., np.diff(packet["t"])])
            or packet["x0"][3] != 0.):
        raise ValueError(f"Unexpected packet identity or ordering: {key_for(cell)}")
    np.linalg.cholesky(packet["R"])
    return packet, evaluator["truth"]


def controls_for(packet):
    return {**{key: packet[key] for key in ("ds", "gy", "dt")}, "x0": packet["x0"][:3]}


def spec_for(anchor, base_spec):
    return base_spec if anchor == "B" else base_spec | {"anchor": (4., 0., 2.65)}


def replay_sigma(packet, controls, mask, core, online, model, spec, table, *, independent=False):
    """Use the frozen transition, observation and gate with a supplied sigma table."""
    from replay_s2 import wrap

    n = len(mask)
    shapes = {"x": (4,), "P": (4, 4), "prior": (4,), "Pprior": (4, 4), "h": (2,), "H": (2, 4),
              "K": (4, 2), "Reff": (2, 2), "nu": (2,), "S": (2, 2), "sigma_b": (), "rho_before": ()}
    trace = {name: np.empty((n, *shape)) for name, shape in shapes.items()}
    trace["mask"] = mask.copy()
    x, P = packet["x0"].copy(), packet["P0"].copy()
    ax, ay = spec["anchor"][:2]
    for k in range(n):
        rho = math.hypot(x[0] - ax, x[1] - ay)
        sigma_b = float(np.interp(rho, KNOTS, table))
        prior, Pprior = online.predict(core, x, P, k, controls)
        h, H = (field[0] for field in model.batch(prior[None], spec))
        nu = packet["z"][k] - h - packet["muMB"][k]
        Reff = packet["R"][k].copy()
        Reff[1, 1] += sigma_b ** 2
        if independent:
            hp = H @ Pprior
            S = hp @ H.T + Reff
            S = (S + S.T) * .5
            K = np.linalg.solve(S, hp).T if mask[k] else np.zeros((4, 2))
            x, P = prior.copy(), Pprior
            if mask[k]:
                x += K @ nu
                x[2] = wrap(x[2])
                A = np.eye(4) - K @ H
                P = A @ Pprior @ A.T + K @ Reff @ K.T
                P = (P + P.T) * .5
        else:
            x, P, K, S = online.joseph(prior, Pprior, H, nu, Reff, mask[k], 1.)
        for name in shapes:
            trace[name][k] = locals()[name]
    return trace


def save_trace(path, trace, packet):
    with path.open("xb") as handle:
        np.savez_compressed(handle, **trace, x_pr=trace["prior"], t=packet["t"], pose_id=packet["pose_id"])


def d0_cell(cell, out, core, online, model, base_spec):
    from metrics_s2 import _summarize
    from replay_s2 import parity, validate_trace
    from run_s2 import a_baseline_check
    from verify_s2 import check_metric_rows, from_trace

    key = key_for(cell)
    packet, truth = bind(cell)
    controls = controls_for(packet)
    spec = spec_for(cell["anchor"], base_spec)
    base = online.replay(packet, controls, "W0", core, model, spec)
    validate_trace(base)
    rows = from_trace(base, truth)
    report = {"e0": _summarize(rows), "accepted": int(base["mask"].sum())}
    archived = cell.get("archive_trace")
    if archived:
        expected = checked_array(archived, (*PARITY_KEYS, "t", "pose_id"))
        identity(packet, expected, ("t", "pose_id"))
        report["archive_trace_parity"] = parity(base, {name: expected[name] for name in PARITY_KEYS})
        archived_results = Path(archived["path"]).parent / "RESULTS.json"
        if archived_results.exists():
            check_metric_rows(rows, read_json(archived_results)["by_case"][cell["route"]]["E0"])
    elif cell["anchor"] == "A" and cell["bias"] == "L2":
        report["archive_trace_parity"] = "ABSENT_FOR_NEW_A_L2_CELL"
    else:
        raise ValueError(f"Required archived E0 trace missing: {key}")
    if cell["anchor"] == "A":
        report["joseph_shadow_self_check"] = a_baseline_check(packet, controls, base, core, online, model, spec)
    if not archived:
        separate = replay_sigma(packet, controls, base["mask"], core, online, model, spec, HAND, independent=True)
        report["recursive_self_check"] = parity(base, {name: separate[name] for name in PARITY_KEYS})
    report["status"] = "PASS" if archived else "PASS_SELF_CHECK"
    save_trace(out / f"{key}.npz", base, packet)
    return report


def residual_donor(cell, model, spec):
    packet, truth = bind(cell)
    h_truth, _ = model.batch(np.column_stack((truth, np.zeros(len(truth)))), spec, gradient=False)
    rho_true = np.linalg.norm(truth[:, :2] - np.array(spec["anchor"][:2]), axis=1)
    eps = packet["z"][:, 1] - h_truth[:, 1] - packet["muMB"][:, 1]
    return np.column_stack((rho_true, eps, packet["R"][:, 1, 1]))


def fit_sigma(rows):
    """Match diag_mbvar.fit_sigma and record each knot's donor support."""
    rho, eps, base_ss = rows.T
    vals = np.full_like(KNOTS, np.nan)
    receipts = []
    for j, knot in enumerate(KNOTS):
        lo = KNOTS[j - 1] if j else knot
        hi = KNOTS[j + 1] if j + 1 < len(KNOTS) else knot + 1e9
        weights = np.where(rho <= knot, (rho - lo) / max(knot - lo, 1e-9), (hi - rho) / max(hi - knot, 1e-9))
        if j == 0:
            weights = np.where(rho <= knot, 1., weights)
        if j == len(KNOTS) - 1:
            weights = np.where(rho >= knot, 1., weights)
        weights = np.clip(weights, 0., 1.)
        support = weights > 0
        den = weights.sum()
        item = {"knot_m": float(knot), "sum_weights": float(den), "support_packets": int(support.sum()),
                "support_rho_range_m": [float(rho[support].min()), float(rho[support].max())] if support.any() else None,
                "supported": bool(den > MIN_WEIGHT), "floor_active": None}
        if den > MIN_WEIGHT:
            mean = np.sum(weights * eps) / den
            second = np.sum(weights * eps ** 2) / den
            excess = np.sum(weights * (eps ** 2 - base_ss)) / den
            vals[j] = math.sqrt(max(excess, SIGMA_FLOOR ** 2))
            item.update(residual_mean=float(mean), residual_second_moment=float(second),
                        residual_centered_variance=float(second - mean ** 2), mean_squared=float(mean ** 2),
                        mean_base_ss=float(np.sum(weights * base_ss) / den),
                        second_moment_minus_base_ss=float(excess), centered_variance_minus_base_ss=float(excess - mean ** 2),
                        floor_active=bool(excess <= SIGMA_FLOOR ** 2))
        receipts.append(item)
    idx = np.flatnonzero(np.isfinite(vals))
    if not idx.size:
        raise ValueError("No supported donor sigma knot")
    vals = np.interp(np.arange(len(vals)), idx, vals[idx])
    for item, value in zip(receipts, vals):
        item["sigma_b"] = float(value)
    return vals, receipts


def compare(cases):
    from metrics_s2 import METRICS, _moving_block_indices, _reduce, _summarize

    results = {arm: _summarize(np.concatenate([case[arm] for case in cases])) for arm in ("e0", "loro")}
    results["loro_minus_e0"] = {metric: results["loro"][metric] - results["e0"][metric] for metric in METRICS}
    results["moving_block_bootstrap_paired"] = {}
    for block_s in (5, 10):
        reps = 1500
        rng = np.random.default_rng(20261115)
        sum_e0 = np.zeros((reps, len(METRICS)))
        sum_loro = np.zeros_like(sum_e0)
        for case in cases:
            ind = _moving_block_indices(case["time"], block_s, reps, rng)
            for j in range(len(METRICS)):
                sum_e0[:, j] += case["e0"][:, j][ind].sum(axis=1)
                sum_loro[:, j] += case["loro"][:, j][ind].sum(axis=1)
        n = results["e0"]["n"]
        low, high = np.quantile(_reduce(sum_loro / n) - _reduce(sum_e0 / n), [.025, .975], axis=0)
        results["moving_block_bootstrap_paired"][str(block_s)] = {
            metric: [float(lo), float(hi)] for metric, lo, hi in zip(METRICS, low, high)}
    return results


def d5(cells, out, d0_out, d0_result, core, online, model, base_spec):
    from replay_s2 import parity, validate_trace
    from verify_s2 import from_trace

    donors = {cell["route"]: residual_donor(cell, model, base_spec)
              for cell in cells if cell["anchor"] == "B" and cell["bias"] == "B0"}
    if set(donors) != set(ROUTES):
        raise ValueError("D5 requires frozen B/B0 inputs for R2, R4 and R5")
    folds = {}
    for route in ROUTES:
        train = [d for d in ROUTES if d != route]
        rows = np.concatenate([donors[d] for d in train])
        vals, knot_summary = fit_sigma(rows)
        folds[route] = {"donor_routes": train, "n_donor_packets": len(rows), "knots": knot_summary,
                        "sigma_b": vals.tolist(), "donor_outside_endpoints_fraction": float((rows[:, 0] > KNOTS[-1]).mean())}
    write_json(out / "FOLDS.json", folds)

    results = {}
    packet_rows = {}
    for cell in cells:
        key = key_for(cell)
        packet, truth = bind(cell)
        base = checked_array({"path": d0_out / f"{key}.npz", "sha256": d0_result["outputs"][f"{key}.npz"]},
                             ("x", "P", "mask", "t", "pose_id"))
        identity(base, packet, ("t", "pose_id"))
        spec = spec_for(cell["anchor"], base_spec)
        vals = np.array(folds[cell["route"]]["sigma_b"])
        trace = replay_sigma(packet, controls_for(packet), base["mask"], core, online, model, spec, vals)
        validate_trace(trace)
        parity(trace, {"mask": base["mask"]})
        save_trace(out / f"{key}.npz", trace, packet)
        row_set = {"time": packet["t"], "e0": from_trace(base, truth), "loro": from_trace(trace, truth)}
        packet_rows[key] = row_set
        results[key] = compare([row_set]) | {
            "accepted": int(base["mask"].sum()),
            "outside_endpoints_fraction": float((trace["rho_before"] > KNOTS[-1]).mean()),
            "rho_before_range_m": [float(trace["rho_before"].min()), float(trace["rho_before"].max())],
        }
        print(f"D5 COMPLETE {key}", flush=True)
    pooled = {}
    for anchor, bias in dict.fromkeys((cell["anchor"], cell["bias"]) for cell in cells):
        pool = [packet_rows[key_for(cell)] for cell in cells if (cell["anchor"], cell["bias"]) == (anchor, bias)]
        pooled[f"{anchor}_{bias}"] = compare(pool)
    drop = -pooled["B_B0"]["loro_minus_e0"]["pose95_coverage"]
    write_json(out / "RESULTS.json", {"status": "PASS_EXECUTION", "by_cell": results, "pooled": pooled,
                                     "h4": {"b_b0_pose95_drop": drop, "threshold": .10,
                                            "verdict": "SUPPORTED" if drop >= .10 else "NOT_SUPPORTED"}})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("d0", "d5"))
    parser.add_argument("--contract", required=True, type=Path)
    args = parser.parse_args()
    contract_path = args.contract.resolve()
    contract = read_json(contract_path)
    native = Path(contract["native"])
    sys.path[:0] = [contract["s2"], str(native / "src")]
    from qclean_uwb.fp_sc.e0_baseline import BANKS, SPEC, load_original_model
    from replay_s2 import sha

    cells = contract["cells"]
    if not cells or len({key_for(cell) for cell in cells}) != len(cells):
        raise ValueError("Contract cells must be nonempty and unique")
    out = contract_path.parent / args.stage
    d0_out = contract_path.parent / "d0"
    fingerprint = sha(contract_path)
    prior = None
    if args.stage == "d5":
        prior = read_json(d0_out / "EXECUTION.json")
        if prior["status"] != "PASS_EXECUTION" or prior["run_contract_sha256"] != fingerprint:
            raise ValueError("D5 requires a passing D0 run under the same contract")

    out.mkdir()
    report = {"question": f"G1-INT-DIAG-001/{args.stage.upper()}",
              "started_utc": datetime.now(timezone.utc).isoformat(), "run_contract_sha256": fingerprint,
              "driver_sha256": sha(Path(__file__)), "command": sys.argv, "numpy_version": np.__version__}
    try:
        core, online, model, native_hashes = load_original_model(native)
        report["native_hashes"] = native_hashes | BANKS
        if args.stage == "d0":
            checks = {}
            for cell in cells:
                key = key_for(cell)
                checks[key] = d0_cell(cell, out, core, online, model, SPEC)
                print(f"D0 {checks[key]['status']} {key}", flush=True)
            write_json(out / "RESULTS.json", {"status": "PASS_EXECUTION", "tolerance": 1e-10, "by_cell": checks})
        else:
            d5(cells, out, d0_out, prior, core, online, model, SPEC)
        report.update(status="PASS_EXECUTION", exit_code=0)
    except Exception as exc:
        report.update(status="FAIL_EXECUTION", exit_code=1, error=str(exc))
        raise
    finally:
        report.update(finished_utc=datetime.now(timezone.utc).isoformat(),
                      outputs={p.name: sha(p) for p in out.iterdir() if p.is_file()})
        write_json(out / "EXECUTION.json", report)


if __name__ == "__main__":
    main()
