"""Independent point-score and frozen-threshold checks for the completed M6 archive."""

import argparse
from pathlib import Path

import numpy as np

from run_characterization import m5
from run_replay import SEEDS, setup, verify_receipt


def rows(trace, truth):
    delta = trace["x"][:, :3] - truth
    delta[:, 2] = (delta[:, 2] + np.pi) % (2 * np.pi) - np.pi
    covariance = trace["P"][:, :3, :3]
    n3 = np.einsum("ni,ni->n", delta, np.linalg.solve(covariance, delta[..., None])[..., 0])
    n2 = np.einsum("ni,ni->n", delta[:, :2],
                   np.linalg.solve(covariance[:, :2, :2], delta[:, :2, None])[..., 0])
    return np.column_stack([
        (delta[:, 2] * 180 / np.pi) ** 2, np.sum(delta[:, :2] ** 2, axis=1) * 10000., n3,
        n3 <= 7.814727903251179, n2 <= 5.991464547107979,
        abs(delta[:, 2]) <= 1.96 * np.sqrt(covariance[:, 2, 2]),
    ])


def reduce(values):
    mean = values.mean(axis=0)
    return dict(n=len(values), heading_rmse_deg=float(np.sqrt(mean[0])), xy_rmse_cm=float(np.sqrt(mean[1])),
                mean_nees3=float(mean[2]), pose95_coverage=float(mean[3]), xy95_coverage=float(mean[4]),
                heading95_coverage=float(mean[5]))


def check_gates(score, independent, routes):
    coverage = ("heading95_coverage", "xy95_coverage", "pose95_coverage")
    rmse = ("heading_rmse_deg", "xy_rmse_cm")
    for arm, groups in score["gates"].items():
        for group, gate in groups.items():
            point = independent[group][arm]
            reference = independent[group]["BASE"]
            pooled = group == "pooled"
            required = coverage[::2] if pooled else coverage
            level, lower_level, maximum = (.90, .80, 1.10) if pooled else (.75, .60, 1.25)
            ci = score["blocks"]["10"]["by_group"][group]
            selected_routes = routes if pooled else [group]
            mirrors = sum(score["branch"][route][arm]["mirror_fail_count"] for route in selected_routes)
            integrity = (all(point[name] >= level and ci["absolute_ci95"][arm][name][0] >= lower_level
                             for name in required) and not ci["reference_only"] and mirrors == 0
                         and (not pooled or 1.5 <= point["mean_nees3"] <= 6.))
            accuracy = all(point[name] <= maximum * reference[name] for name in rmse)
            if (integrity, accuracy, integrity and accuracy) != (
                gate["integrity_ok"], gate["accuracy_ok"], gate["pass"]
            ):
                raise ValueError(f"Gate differs {group}/{arm}")


def verify(out, result):
    spec, lock, _, cases = setup(out)
    for stage in ("implementation", "seed10", "seed11_14"):
        verify_receipt(out / stage)
    execution = verify_receipt(result)
    score_all = m5.read(result / "SCORES.json")
    checked_count, max_error, gates_checked = 0, 0., 0
    for seed in SEEDS:
        stage = out / ("seed10" if seed == 10 else "seed11_14") / f"seed{seed}"
        data = {}
        for route, case in cases[seed].items():
            files = {"BASE": out / "implementation" / f"seed{seed}" / f"{route}_G0.npz"}
            files.update({path.name[len(route) + 1:-4]: path for path in stage.glob(f"{route}_*.npz")})
            data[route] = {}
            for arm, path in files.items():
                trace = m5.arrays(path)
                data[route][arm] = rows(trace, case["truth"])
                checked_count += 1
        score = score_all[str(seed)]
        sections = [score["common"], *(row["scores"] for row in score["subsets"].values())]
        for section in sections:
            eligible = [route for route in section["point"] if route != "pooled"]
            independent = {}
            for group, values in section["point"].items():
                independent[group] = {}
                for arm, point in values.items():
                    independent[group][arm] = fresh = reduce(
                        np.concatenate([data[route][arm] for route in eligible])
                        if group == "pooled" else data[group][arm])
                    for name in fresh:
                        np.testing.assert_allclose(fresh[name], point[name], atol=1e-12, rtol=1e-12,
                                                   err_msg=f"{seed}/{group}/{arm}/{name}")
                        max_error = max(max_error, abs(fresh[name] - point[name]))
            check_gates(section, independent, eligible)
            gates_checked += sum(len(row) for row in section["gates"].values())
    verification = dict(status="PASS", code=m5.item(Path(__file__)),
                        replay_contract=m5.item(out / "RUN_CONTRACT.json"),
                        aggregation_receipt=m5.item(result / "EXECUTION.json"),
                        trace_conditions_checked=checked_count, point_max_absolute_delta=max_error,
                        threshold_decisions_checked=gates_checked,
                        method="direct covariance solve; independent frozen-threshold reconstruction",
                        bootstrap_method="intervals hash-verified; original fixed block bootstrap reused",
                        finished_utc=m5.utc(), execution_status=execution["status"])
    m5.write(result.parent / "VERIFICATION.json", verification)
    print(verification, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("replay", type=Path)
    parser.add_argument("results", type=Path)
    args = parser.parse_args()
    verify(args.replay, args.results)
