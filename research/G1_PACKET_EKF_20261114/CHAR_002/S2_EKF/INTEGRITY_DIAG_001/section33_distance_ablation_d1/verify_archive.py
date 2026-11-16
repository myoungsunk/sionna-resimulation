"""Verify the published section 3.3 archive using Python and NumPy."""

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent
PARITY_ATOL = 1e-10
ROUNDING_ATOL = 5.1e-7
POSE95_LIMIT = 7.814727903251179
XY95_LIMIT = 5.991464547107979
NAV = ("x", "P", "prior", "Pprior", "h", "H", "Reff", "K", "nu", "S")
PHASES = {
    "A1": ("BASE", "ALL", "NEAR", "FAR"),
    "A2_4": ("BASE", "ALL", "NEAR", "FAR", "NEAR_Y", "NEAR_PSI", "FAR_Y", "FAR_PSI"),
    "A2_4_weak": ("BASE", "ALL", "NEAR", "FAR", "WEAK_Y", "WEAK_PSI"),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_npz(path):
    with np.load(path, allow_pickle=False) as packed:
        return {key: packed[key] for key in packed.files}


def verify_inventory():
    entries = {}
    for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, relative = line[:64], line[64:].strip().removeprefix("*")
        require(len(expected) == 64 and all(c in "0123456789abcdef" for c in expected),
                f"Invalid SHA256SUMS record {relative}")
        path = (ROOT / relative).resolve()
        require(path.is_relative_to(ROOT), f"Manifest path leaves archive {relative}")
        require(relative not in entries, f"Duplicate manifest record {relative}")
        require(path.is_file() and digest(path) == expected, f"File hash differs {relative}")
        entries[relative] = expected
    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*")
              if path.is_file() and path.name != "SHA256SUMS"}
    require(set(entries) == actual, "SHA256SUMS file inventory differs")
    receipt = read_json(ROOT / "runs/EXECUTION.json")
    require(receipt["contract_sha256"] == digest(ROOT / "RUN_CONTRACT.json"),
            "Execution receipt contract hash differs")
    for relative, expected in receipt["outputs"].items():
        candidates = (ROOT / relative, ROOT / "runs" / relative)
        require(any(path.is_file() and path.resolve().is_relative_to(ROOT)
                    and digest(path) == expected for path in candidates),
                f"Execution receipt output differs {relative}")
    return dict(files=len(entries), receipt_outputs=len(receipt["outputs"]))


def parity(actual, expected):
    np.testing.assert_array_equal(actual["mask"], expected["mask"])
    maximum = 0.
    for key in NAV:
        np.testing.assert_allclose(actual[key], expected[key], atol=PARITY_ATOL, rtol=0., err_msg=key)
        maximum = max(maximum, float(np.max(np.abs(actual[key] - expected[key]))))
    return maximum


def point_metrics(trace, truth, near):
    error = trace["x"][:, :3] - truth
    error[:, 2] = (error[:, 2] + np.pi) % (2. * np.pi) - np.pi
    covariance = trace["P"][:, :3, :3]
    nees3 = np.einsum("ni,ni->n", error, np.linalg.solve(covariance, error[..., None])[..., 0])
    nees2 = np.einsum("ni,ni->n", error[:, :2],
                      np.linalg.solve(covariance[:, :2, :2], error[:, :2, None])[..., 0])
    y_error = 100. * error[:, 1]
    return dict(
        n=len(error),
        heading_rmse_deg=float(np.sqrt(np.mean(np.rad2deg(error[:, 2])**2))),
        xy_rmse_cm=float(100. * np.sqrt(np.mean(np.sum(error[:, :2]**2, axis=1)))),
        mean_nees3=float(np.mean(nees3)),
        pose95_coverage=float(np.mean(nees3 <= POSE95_LIMIT)),
        xy95_coverage=float(np.mean(nees2 <= XY95_LIMIT)),
        heading95_coverage=float(np.mean(np.abs(error[:, 2]) <= 1.96 * np.sqrt(covariance[:, 2, 2]))),
        y_cm=float(np.sqrt(np.mean(y_error**2))),
        y_cm_near=float(np.sqrt(np.mean(y_error[near]**2))),
        y_cm_far=float(np.sqrt(np.mean(y_error[~near]**2))),
    )


def check_trace(trace, online, baseline, rho, near):
    count = len(rho)
    require(trace["x"].shape == (count, 4), "Unexpected navigation state shape")
    require(trace["P"].shape == (count, 4, 4), "Unexpected navigation covariance shape")
    for key in ("t", "pose_id"):
        np.testing.assert_array_equal(trace[key], online[key])
    np.testing.assert_array_equal(trace["mask"], baseline["mask"])
    np.testing.assert_array_equal(trace["near"], near)
    np.testing.assert_allclose(trace["rho"], rho, atol=PARITY_ATOL, rtol=0.)
    for key in NAV:
        require(np.isfinite(trace[key]).all(), f"Nonfinite trace field {key}")
    for key in ("P", "Pprior", "Reff", "S"):
        covariance = trace[key]
        np.testing.assert_allclose(covariance, covariance.transpose(0, 2, 1),
                                   atol=PARITY_ATOL, rtol=0., err_msg=key)
        require(float(np.linalg.eigvalsh(covariance).min()) >= -1e-12,
                f"Covariance loses positive semidefiniteness {key}")
    rejected = ~trace["mask"]
    np.testing.assert_array_equal(trace["x"][rejected], trace["prior"][rejected])
    np.testing.assert_array_equal(trace["P"][rejected], trace["Pprior"][rejected])
    np.testing.assert_array_equal(trace["K"][rejected], 0.)


def verify_traces():
    inputs = {name: load_npz(ROOT / "inputs" / f"{name}.npz")
              for name in ("online", "evaluator", "baseline", "fixed_gate", "A1", "A2_4")}
    online, baseline = inputs["online"], inputs["baseline"]
    truth = inputs["evaluator"]["truth"]
    rho = np.linalg.norm(baseline["prior"][:, :2] - np.array([10., 0.]), axis=1)
    near = rho < 3.
    require(len(rho) == 1415 and int(baseline["mask"].sum()) == 1384,
            "R5 packet or accepted count differs")
    require(int(near.sum()) == 448 and int((~near).sum()) == 967, "Prior distance partition differs")
    np.testing.assert_array_equal(baseline["mask"], inputs["fixed_gate"]["mask"])
    for record in inputs.values():
        for key in ("t", "pose_id"):
            np.testing.assert_array_equal(record[key], online[key])
    require(truth.shape == (len(rho), 3), "Unexpected evaluator truth shape")
    traces, maximum_parity, maximum_score, scored_arms = {}, 0., 0., 0
    for phase, expected_arms in PHASES.items():
        directory = ROOT / "runs" / phase
        files = {path.stem: path for path in directory.glob("*.npz")}
        require(set(files) == set(expected_arms), f"Trace arm inventory differs {phase}")
        result = read_json(directory / "RESULT.json")
        original = read_json(ROOT / "original_results" / f"{phase}.json")
        require(result == original, f"Replayed six-decimal result differs from original {phase}")
        by_arm = {name: load_npz(path) for name, path in files.items()}
        traces[phase] = by_arm
        schedule = inputs["A1" if phase == "A1" else "A2_4"]["Reff"]
        for arm, trace in by_arm.items():
            check_trace(trace, online, baseline, rho, near)
            if arm in original["arms"]:
                for key, actual in point_metrics(trace, truth, near).items():
                    archived = original["arms"][arm][key]
                    delta = abs(actual - archived)
                    require(delta <= ROUNDING_ATOL, f"Independent score differs {phase}/{arm}/{key}")
                    maximum_score = max(maximum_score, delta)
                scored_arms += 1
            expected_r = schedule.copy()
            if arm == "BASE":
                expected_r = baseline["Reff"]
            elif arm in ("NEAR", "WEAK_Y", "WEAK_PSI"):
                expected_r[near] = baseline["Reff"][near]
            elif arm == "FAR":
                expected_r[~near] = baseline["Reff"][~near]
            np.testing.assert_array_equal(trace["Reff"], expected_r)
        maximum_parity = max(maximum_parity, parity(by_arm["BASE"], baseline),
                             parity(by_arm["ALL"], inputs["A1" if phase == "A1" else "A2_4"]))
    for arm in ("BASE", "ALL", "NEAR", "FAR"):
        maximum_parity = max(maximum_parity, parity(traces["A2_4_weak"][arm], traces["A2_4"][arm]))
    return dict(trace_conditions=sum(len(value) for value in traces.values()),
                independently_scored_arms=scored_arms, max_absolute_parity_delta=maximum_parity,
                max_absolute_rounded_metric_delta=maximum_score, near_packets=int(near.sum()),
                far_packets=int((~near).sum()), accepted_packets=int(baseline["mask"].sum()))


if __name__ == "__main__":
    print(json.dumps(dict(status="PASS", inventory=verify_inventory(), traces=verify_traces()),
                     ensure_ascii=False, indent=2))
