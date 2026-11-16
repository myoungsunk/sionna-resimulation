"""Authenticate the follow-up artifacts and export a flat review table."""
import csv
from pathlib import Path

import numpy as np
from scipy.stats import chi2

from run_followup import HERE, RESULT, BASE_TRACES, ROUTES, TOLERANCE, load, read, sha, write


RUN = HERE / "run_01"
RETRY = HERE / "run_c4_retry_03"
METRICS = ("heading_rmse_deg", "xy_rmse_cm", "mean_nees3",
           "pose95_coverage", "xy95_coverage", "heading95_coverage")


def authenticate_outputs(folder, name, status):
    receipt = read(folder / "EXECUTION.json")
    assert receipt["status"] == status
    key = "contract_sha256" if folder == RUN else "retry_contract_sha256"
    assert receipt[key] == sha(HERE / name)
    observed = {p.name for p in folder.iterdir() if p.is_file() and p.name != "EXECUTION.json"}
    assert observed == set(receipt["outputs"])
    for path, expected in receipt["outputs"].items():
        assert sha(folder / path) == expected
    return len(observed)


def terms(trace, evaluator):
    for key in ("pose_id", "t"):
        np.testing.assert_array_equal(trace[key], evaluator[key])
    difference = trace["x"][:, :3] - evaluator["truth"]
    difference[:, 2] = np.arctan2(np.sin(difference[:, 2]), np.cos(difference[:, 2]))
    covariance = trace["P"][:, :3, :3]
    pose_nees = np.einsum("ni,ni->n", difference, np.linalg.solve(covariance, difference[..., None])[..., 0])
    xy = difference[:, :2]
    xy_nees = np.einsum("ni,ni->n", xy, np.linalg.solve(covariance[:, :2, :2], xy[..., None])[..., 0])
    return np.column_stack([np.rad2deg(difference[:, 2])**2, 1e4 * (xy**2).sum(axis=1), pose_nees,
                            pose_nees <= chi2.ppf(.95, 3), xy_nees <= chi2.ppf(.95, 2),
                            abs(difference[:, 2]) <= 1.96 * np.sqrt(covariance[:, 2, 2])])


def point(values):
    means = values.mean(axis=0)
    means[:2] = np.sqrt(means[:2])
    return dict(n=len(values), **dict(zip(METRICS, means.tolist())))


def file_for(stage, route, arm):
    if arm == "LORO":
        return HERE.parent / "attempt_02" / "d5" / f"B_B0_{route}.npz"
    if arm in BASE_TRACES:
        return RESULT / f"V3_{arm}.npz"
    folder = RETRY if stage == "C4" else RUN
    return folder / f"{stage}_{route}_{arm}.npz"


def make_table():
    counts = {"run_01": authenticate_outputs(RUN, "RUN_CONTRACT_C1_C6.json", "FAIL_EXECUTION"),
              "run_c4_retry": authenticate_outputs(RETRY, "RUN_CONTRACT_C4_RETRY_03.json", "PASS_EXECUTION")}
    contract = read(HERE.parent / "RUN_CONTRACT.json")
    evaluator = {}
    for cell in contract["cells"]:
        if cell["anchor"] == "B" and cell["bias"] == "B0":
            source = cell["evaluator"]
            assert sha(source["path"]) == source["sha256"]
            evaluator[cell["route"]] = load(Path(source["path"]))
    assert set(evaluator) == set(ROUTES)
    results = []
    max_error = 0.
    for stage in ("C1", "C2", "C3", "C6", "C5", "C4"):
        path = (RETRY if stage == "C4" else RUN) / f"{stage}.json"
        payload = read(path)
        score = payload if stage == "C1" else payload["scores"]
        by_point = score["point"]
        computed = {}
        for group, items in by_point.items():
            for arm, expected in items.items():
                trace = None
                if group == "pooled":
                    values = np.concatenate([computed[r, arm] for r in ROUTES])
                else:
                    trace = load(file_for(stage, group, arm))
                    if stage == "C6" and arm.endswith("_own"):
                        nis = np.einsum("ni,ni->n", trace["nu"], np.linalg.solve(trace["S"], trace["nu"][..., None])[..., 0])
                        np.testing.assert_allclose(trace["nis"], nis, atol=TOLERANCE, rtol=1e-12)
                        np.testing.assert_array_equal(trace["mask"], nis <= 9.210340371976184)
                    else:
                        ref = load(file_for(stage, group, "LORO"))["mask"]
                        np.testing.assert_array_equal(trace["mask"], ref)
                    values = terms(trace, evaluator[group])
                    computed[group, arm] = values
                actual = point(values)
                for key in expected:
                    max_error = max(max_error, abs(actual[key] - expected[key]))
                    np.testing.assert_allclose(actual[key], expected[key], atol=TOLERANCE, rtol=0.)
                intervals = {f"{m}_{seconds}s_{side}": bound
                             for seconds in ("5", "10")
                             for m, bounds in score["blocks"][seconds]["by_group"][group]["absolute_ci95"][arm].items()
                             if m.endswith("_coverage")
                             for side, bound in zip(("lo", "hi"), bounds)}
                n_admitted = None if trace is None else int(trace["mask"].sum())
                results.append(dict(stage=stage, group=group, arm=arm, admitted=n_admitted,
                                    **actual, **intervals))
    table = HERE / "SUMMARY_SCORES.csv"
    with table.open("x", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=results[0])
        writer.writeheader()
        writer.writerows(results)
    write(HERE / "VERIFICATION.json", dict(status="PASS_REAGGREGATION", role="IMPLEMENTER_SELF_CHECK",
                                           outputs_checked=counts, score_rows=len(results),
                                           errors_max_abs=max_error, review_table_sha256=sha(table)))


if __name__ == "__main__":
    make_table()
